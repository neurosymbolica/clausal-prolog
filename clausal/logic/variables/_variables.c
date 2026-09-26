/*
 * _variables.c — Logic variables with trail-based backtracking
 *                and attributed variables (AttVar)
 *
 * Design notes:
 *
 *   Plain Var (unchanged from original):
 *     - Unbound variable: binding == NULL, self-referential by convention.
 *     - Age-ordered binding: newer var (larger var_id) binds to older one.
 *     - Trail: (var, old_binding) pairs; undo in reverse order.
 *
 *   AttVar (new, extends Var):
 *     - Carries an optional attrs dict {key: value}.
 *     - Inspired by SWI-Prolog / Scryer attributed variables and SICStus.
 *     - When an AttVar with attrs is unified, a wakeup is deferred until
 *       structural unification is complete, then hooks are fired.
 *     - Hook signature: hook(attr_value, bound_to, trail) -> bool
 *     - Hooks are registered globally per key via register_attr_hook().
 *     - Attribute mutations (put_attr / del_attr) are trailed separately.
 *
 *   Scryer Prolog reference (machine/attributed_variables.rs):
 *     - AttrVar is a distinct heap-cell tag from Var.
 *     - bind_attr_var() queues the binding in attr_var_init.bindings and
 *       sets up a verify_attr_interrupt before the next instruction.
 *     - After structural unification, driver/2 calls verify_attributes/3
 *       per module that owns an attribute on the variable.
 *
 *   Our adaptation (WAM-less, Python heap):
 *     - AttVar IS-A Var (C tp_base inheritance) so Var_Check passes.
 *     - Wakeup queue is a temporary list on Trail, swapped in/out by
 *       py_unify so nested unify() calls from hooks get their own slice.
 *     - Constraint propagation is entirely in user-supplied hooks.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stddef.h>
#include <stdint.h>
#include "_ft_compat.h"

/* ================================================================
 * Forward declarations
 * ================================================================ */

typedef struct VarObject    VarObject;
typedef struct AttVarObject AttVarObject;
typedef struct TrailObject  TrailObject;

/* Provider: we define the struct types ourselves, so skip the header's copies.
 * Must come after the forward declarations above since the VariablesCAPI
 * struct references VarObject, AttVarObject, TrailObject. */
#define VARIABLES_CAPI_PROVIDER
#include "_variables_capi.h"

static PyTypeObject VarType;
static PyTypeObject AttVarType;
static PyTypeObject TrailType;

/* Global monotonic creation counter.  Atomic under free-threaded builds. */
static FT_ATOMIC_UINT64_T g_next_var_id = 0;

/* Module-level attribute hook registry: {key -> callable}.
 * Mirrors the Prolog model where verify_attributes/3 is a module predicate. */
static PyObject *g_attr_hooks = NULL;

/* ================================================================
 * Var type
 *
 * An unbound logic variable.  binding == NULL means unbound.
 * When bound, binding points to the bound value (another Var or
 * any Python object).
 *
 * var_id is a monotonic creation counter used to orient var-var
 * bindings: the newer var (larger id) is bound to the older one,
 * matching Scryer / GNU Prolog age-based convention.
 * ================================================================ */

struct VarObject {
    PyObject_HEAD
    PyObject *binding;   /* NULL = unbound; non-NULL = bound value */
    uint64_t  var_id;    /* monotonic creation id */
};

#define Var_Check(op)    PyObject_TypeCheck((op), &VarType)
#define Var_CAST(op)     ((VarObject *)(op))
#define AttVar_Check(op) PyObject_TypeCheck((op), &AttVarType)
#define AttVar_CAST(op)  ((AttVarObject *)(op))

/*
 * var_deref — follow the binding chain to the root term.
 * Returns a borrowed reference.
 */
static PyObject *
var_deref(PyObject *term)
{
    while (Var_Check(term)) {
        VarObject *v = Var_CAST(term);
        PyObject *b = FT_ATOMIC_LOAD_PTR(v->binding);
        if (b == NULL)
            return term;
        term = b;
    }
    return term;
}

static PyObject *
Var_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
        return NULL;
    VarObject *self = (VarObject *)PyObject_GC_New(VarObject, type);
    if (self) {
        self->binding = NULL;
        self->var_id  = FT_ATOMIC_FETCH_ADD(g_next_var_id, 1);
    }
    PyObject_GC_Track(self);
    return (PyObject *)self;
}

static void
Var_dealloc(VarObject *self)
{
    PyObject_GC_UnTrack(self);
    Py_XDECREF(self->binding);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
Var_traverse(VarObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->binding);
    return 0;
}

static int
Var_clear(VarObject *self)
{
    Py_CLEAR(self->binding);
    return 0;
}

static PyObject *
Var_repr(VarObject *self)
{
    PyObject *root = var_deref((PyObject *)self);
    if (root == (PyObject *)self)
        return PyUnicode_FromFormat("Var(_%llu)", (unsigned long long)self->var_id);
    PyObject *r = PyObject_Repr(root);
    if (!r) return NULL;
    PyObject *res = PyUnicode_FromFormat("Var(_%llu=%U)",
                                         (unsigned long long)self->var_id, r);
    Py_DECREF(r);
    return res;
}

/* __str__: deref, then str() on the resolved value.
 * Unbound vars produce "_N" (no wrapper). */
static PyObject *
Var_str(VarObject *self)
{
    PyObject *root = var_deref((PyObject *)self);
    if (root == (PyObject *)self)
        return PyUnicode_FromFormat("_%llu", (unsigned long long)self->var_id);
    return PyObject_Str(root);
}

/* __format__(spec): deref, then format(resolved, spec).
 * Enables natural f-string usage: f"{X_}" auto-derefs. */
static PyObject *
Var_format(VarObject *self, PyObject *args)
{
    PyObject *spec = NULL;
    if (!PyArg_ParseTuple(args, "|U", &spec))
        return NULL;

    PyObject *root = var_deref((PyObject *)self);
    if (root == (PyObject *)self) {
        /* Unbound var — ignore format spec, return _N */
        return PyUnicode_FromFormat("_%llu", (unsigned long long)self->var_id);
    }
    /* Delegate to format(resolved_value, spec) */
    if (spec == NULL || PyUnicode_GET_LENGTH(spec) == 0)
        return PyObject_Str(root);
    return PyObject_Format(root, spec);
}

/* ── UnboundVarCoercionError ─────────────────────────────────────────
 * Raised when an unbound Var is coerced to int, float, bool, etc.    */
static PyObject *UnboundVarCoercionError = NULL;

static int
_check_bound(VarObject *self, PyObject **out)
{
    PyObject *root = var_deref((PyObject *)self);
    if (root == (PyObject *)self) {
        PyErr_SetString(UnboundVarCoercionError,
            "Cannot coerce an unbound logic variable to a Python value. "
            "The variable has not been bound to a concrete value yet.");
        return -1;
    }
    *out = root;
    return 0;
}

static PyObject *
Var_int(VarObject *self)
{
    PyObject *root;
    if (_check_bound(self, &root) < 0) return NULL;
    return PyNumber_Long(root);
}

static PyObject *
Var_float(VarObject *self)
{
    PyObject *root;
    if (_check_bound(self, &root) < 0) return NULL;
    return PyNumber_Float(root);
}

static int
Var_bool(VarObject *self)
{
    PyObject *root;
    if (_check_bound(self, &root) < 0) return -1;
    return PyObject_IsTrue(root);
}

static PyNumberMethods Var_as_number = {
    .nb_int        = (unaryfunc)Var_int,
    .nb_float      = (unaryfunc)Var_float,
    .nb_bool       = (inquiry)Var_bool,
};

static PyMethodDef Var_methods[] = {
    {"__format__", (PyCFunction)Var_format, METH_VARARGS,
     "Format the dereferenced value of this variable."},
    {NULL, NULL, 0, NULL}
};

static PyObject *
Var_get_is_bound(VarObject *self, void *closure)
{
    (void)closure;
    return PyBool_FromLong(FT_ATOMIC_LOAD_PTR(self->binding) != NULL);
}

static PyObject *
Var_get_value(VarObject *self, void *closure)
{
    (void)closure;
    PyObject *root = var_deref((PyObject *)self);
    Py_INCREF(root);
    return root;
}

static PyObject *
Var_get_id(VarObject *self, void *closure)
{
    (void)closure;
    return PyLong_FromUnsignedLongLong((unsigned long long)self->var_id);
}

static PyGetSetDef Var_getset[] = {
    {"is_bound", (getter)Var_get_is_bound, NULL,
     "True if this variable has been bound to a value.", NULL},
    {"value",    (getter)Var_get_value,    NULL,
     "The dereferenced value.  Returns self if unbound.", NULL},
    {"_id",      (getter)Var_get_id,       NULL,
     "Monotonic creation ID used for binding-direction decisions.", NULL},
    {NULL, NULL, NULL, NULL, NULL}
};

static PyTypeObject VarType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name      = "clausal.logic.variables.Var",
    .tp_doc       = (
        "An unbound logic variable.\n"
        "\n"
        "Create with ``Var()``.  Bind by passing to ``unify()``.\n"
        "Test with ``is_bound`` or ``is_var()``.\n"
        "Read the bound value with the ``value`` property.\n"
    ),
    .tp_basicsize = sizeof(VarObject),
    .tp_itemsize  = 0,
    .tp_flags     = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_HAVE_GC,
    .tp_new       = Var_new,
    .tp_dealloc   = (destructor)Var_dealloc,
    .tp_traverse  = (traverseproc)Var_traverse,
    .tp_clear     = (inquiry)Var_clear,
    .tp_repr      = (reprfunc)Var_repr,
    .tp_str       = (reprfunc)Var_str,
    .tp_as_number = &Var_as_number,
    .tp_methods   = Var_methods,
    .tp_getset    = Var_getset,
};


/* ================================================================
 * AttVar type  (extends Var)
 *
 * An attributed logic variable.  Like Var but may carry a dict of
 * per-key attributes.  When the variable is unified with a value
 * (or another variable), registered hooks are called after structural
 * unification completes, one per attribute key.
 *
 * Inspired by:
 *   SWI-Prolog:  put_attr/3, get_attr/3, attr_unify_hook/2
 *   SICStus:     put_atts/2, get_atts/2, verify_attributes/3
 *   Scryer:      AttrVar heap tag, bind_attr_var(), attr_var_init queue
 *
 * Constraint propagation is entirely left to user-supplied hooks.
 * ================================================================ */

struct AttVarObject {
    VarObject  base;   /* MUST be first — AttVar IS-A Var */
    PyObject  *attrs;  /* PyDict {key: value} or NULL (no attrs yet) */
};

static PyObject *
AttVar_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
        return NULL;
    AttVarObject *self = (AttVarObject *)PyObject_GC_New(AttVarObject, type);
    if (self) {
        self->base.binding = NULL;
        self->base.var_id  = FT_ATOMIC_FETCH_ADD(g_next_var_id, 1);
        self->attrs        = NULL;
    }
    PyObject_GC_Track(self);
    return (PyObject *)self;
}

static void
AttVar_dealloc(AttVarObject *self)
{
    PyObject_GC_UnTrack(self);
    Py_XDECREF(self->base.binding);
    Py_XDECREF(self->attrs);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
AttVar_traverse(AttVarObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->base.binding);
    Py_VISIT(self->attrs);
    return 0;
}

static int
AttVar_clear(AttVarObject *self)
{
    Py_CLEAR(self->base.binding);
    Py_CLEAR(self->attrs);
    return 0;
}

static PyObject *
AttVar_repr(AttVarObject *self)
{
    PyObject *root = var_deref((PyObject *)self);
    if (root == (PyObject *)self) {
        if (self->attrs) {
            PyObject *ar = PyObject_Repr(self->attrs);
            if (!ar) return NULL;
            PyObject *res = PyUnicode_FromFormat("AttVar(_%llu, attrs=%U)",
                                                  (unsigned long long)self->base.var_id, ar);
            Py_DECREF(ar);
            return res;
        }
        return PyUnicode_FromFormat("AttVar(_%llu)",
                                     (unsigned long long)self->base.var_id);
    }
    PyObject *r = PyObject_Repr(root);
    if (!r) return NULL;
    PyObject *res = PyUnicode_FromFormat("AttVar(_%llu=%U)",
                                          (unsigned long long)self->base.var_id, r);
    Py_DECREF(r);
    return res;
}

static PyObject *
AttVar_get_attrs(AttVarObject *self, void *closure)
{
    (void)closure;
    if (!self->attrs)
        Py_RETURN_NONE;
    Py_INCREF(self->attrs);
    return self->attrs;
}

static PyGetSetDef AttVar_getset[] = {
    {"attrs", (getter)AttVar_get_attrs, NULL,
     "Attribute dict {key: value}, or None if no attributes are set.", NULL},
    {NULL, NULL, NULL, NULL, NULL}
};

static PyTypeObject AttVarType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name      = "clausal.logic.variables.AttVar",
    .tp_doc       = (
        "An attributed logic variable.\n"
        "\n"
        "Like ``Var`` but can carry per-key attributes.  When unified with a\n"
        "value (or another variable), hooks registered via\n"
        "``register_attr_hook(key, fn)`` are called for each attribute key.\n"
        "\n"
        "Hook signature::\n"
        "\n"
        "    def hook(attr_value, bound_to, trail) -> bool\n"
        "\n"
        "Returning ``False`` causes the unification to fail and roll back.\n"
        "The hook may call ``unify()`` to propagate constraints.\n"
    ),
    .tp_basicsize = sizeof(AttVarObject),
    .tp_itemsize  = 0,
    .tp_flags     = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_HAVE_GC,
    /* tp_base is set to &VarType in PyMODINIT_FUNC before PyType_Ready */
    .tp_new       = AttVar_new,
    .tp_dealloc   = (destructor)AttVar_dealloc,
    .tp_traverse  = (traverseproc)AttVar_traverse,
    .tp_clear     = (inquiry)AttVar_clear,
    .tp_repr      = (reprfunc)AttVar_repr,
    .tp_getset    = AttVar_getset,
};


/* ================================================================
 * Trail type
 *
 * Extended from the original to handle two kinds of trail entries:
 *
 *   TRAIL_BINDING — a variable binding (original behaviour).
 *     Stores (var, old_binding); undo restores var->binding.
 *
 *   TRAIL_ATTR — an attribute mutation via put_attr / del_attr.
 *     Stores (attvar, key, old_attr); undo restores attrs[key].
 *     old_attr == NULL means the key was absent before put_attr.
 *
 * The wakeup_list field is NULL by default and is set to a fresh
 * Python list by py_unify / py_unify_with_occurs_check before calling
 * do_unify.  do_unify appends (attvar, bound_to) pairs to it for any
 * AttVar bound during structural unification.  After do_unify the
 * caller processes the list (firing hooks) then restores the field.
 * This scoping ensures that nested unify() calls from inside hooks
 * each get their own wakeup slice.
 * ================================================================ */

typedef enum { TRAIL_BINDING = 0, TRAIL_ATTR = 1, TRAIL_CALLBACK = 2 } TrailEntryKind;

typedef struct {
    TrailEntryKind kind;
    union {
        struct {
            VarObject *var;        /* owned ref */
            PyObject  *old_value;  /* owned ref, NULL = var was unbound */
        } binding;
        struct {
            PyObject *attvar;      /* AttVarObject *, owned ref */
            PyObject *key;         /* owned ref */
            PyObject *old_attr;    /* owned ref, NULL = key was absent */
        } attr;
        struct {
            PyObject *fn;          /* callable(), owned ref */
        } callback;
    } u;
} TrailEntry;

struct TrailObject {
    PyObject_HEAD
    TrailEntry *entries;
    Py_ssize_t  length;
    Py_ssize_t  capacity;
    /* Wakeup queue: NULL outside py_unify; a Python list inside it.
     * do_unify appends (attvar, bound_to) tuples when binding an AttVar. */
    PyObject   *wakeup_list;
    /* Thread ownership: set once at creation, checked on every mutation.
     * Trails must not be shared between threads — each thread needs its
     * own Trail.  See the threading contract in _ft_compat.h. */
    unsigned long owner_thread_id;
    /* Weak-reference support (tp_weaklistoffset). */
    PyObject   *weakrefs;
};

/*
 * TRAIL_CHECK_OWNER — assert the current thread owns this trail.
 *
 * Trails are not thread-safe.  Each thread must create its own Trail.
 * This check catches cross-thread misuse early (returns -1 with
 * RuntimeError set) rather than silently corrupting the trail.
 */
static inline int
trail_check_owner(TrailObject *trail)
{
    if (trail->owner_thread_id != PyThread_get_thread_ident()) {
        PyErr_SetString(PyExc_RuntimeError,
            "Trail accessed from a different thread than it was created in. "
            "Each thread must use its own Trail object.");
        return -1;
    }
    return 0;
}

static PyObject *
Trail_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
        return NULL;
    TrailObject *self = (TrailObject *)PyObject_GC_New(TrailObject, type);
    if (self) {
        self->entries         = NULL;
        self->length          = 0;
        self->capacity        = 0;
        self->wakeup_list     = NULL;
        self->owner_thread_id = PyThread_get_thread_ident();
        self->weakrefs        = NULL;
    }
    PyObject_GC_Track(self);
    return (PyObject *)self;
}

static void
Trail_dealloc(TrailObject *self)
{
    /* Untrack BEFORE clearing weakrefs.  PyObject_ClearWeakRefs runs the
     * weakref callbacks -- arbitrary Python code (clpb's trail finalizer
     * among them) -- and Python code can run a pending GC collection.  With
     * this object still tracked at refcount 0, the collector sees it as
     * garbage, tp_clear()s it and deallocates it a second time; the rest
     * of this function then operates on freed memory (2026-09-11, SIGSEGV
     * in PyObject_GC_UnTrack).  Same order as CPython's subtype_dealloc. */
    PyObject_GC_UnTrack(self);
    if (self->weakrefs)
        PyObject_ClearWeakRefs((PyObject *)self);
    for (Py_ssize_t i = 0; i < self->length; i++) {
        TrailEntry *e = &self->entries[i];
        if (e->kind == TRAIL_BINDING) {
            Py_DECREF(e->u.binding.var);
            Py_XDECREF(e->u.binding.old_value);
        } else if (e->kind == TRAIL_ATTR) {
            Py_DECREF(e->u.attr.attvar);
            Py_DECREF(e->u.attr.key);
            Py_XDECREF(e->u.attr.old_attr);
        } else {
            /* TRAIL_CALLBACK */
            Py_DECREF(e->u.callback.fn);
        }
    }
    PyMem_Free(self->entries);
    Py_XDECREF(self->wakeup_list);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
Trail_traverse(TrailObject *self, visitproc visit, void *arg)
{
    for (Py_ssize_t i = 0; i < self->length; i++) {
        TrailEntry *e = &self->entries[i];
        if (e->kind == TRAIL_BINDING) {
            Py_VISIT(e->u.binding.var);
            Py_VISIT(e->u.binding.old_value);
        } else if (e->kind == TRAIL_ATTR) {
            Py_VISIT(e->u.attr.attvar);
            Py_VISIT(e->u.attr.key);
            Py_VISIT(e->u.attr.old_attr);
        } else {
            /* TRAIL_CALLBACK */
            Py_VISIT(e->u.callback.fn);
        }
    }
    Py_VISIT(self->wakeup_list);
    return 0;
}

static int
Trail_clear(TrailObject *self)
{
    Py_ssize_t len = self->length;
    self->length = 0;
    for (Py_ssize_t i = 0; i < len; i++) {
        TrailEntry *e = &self->entries[i];
        if (e->kind == TRAIL_BINDING) {
            Py_DECREF(e->u.binding.var);
            Py_XDECREF(e->u.binding.old_value);
        } else if (e->kind == TRAIL_ATTR) {
            Py_DECREF(e->u.attr.attvar);
            Py_DECREF(e->u.attr.key);
            Py_XDECREF(e->u.attr.old_attr);
        } else {
            /* TRAIL_CALLBACK */
            Py_DECREF(e->u.callback.fn);
        }
    }
    Py_CLEAR(self->wakeup_list);
    return 0;
}

/* Grow entries buffer. Returns 0 on success, -1 on OOM. */
static int
trail_grow(TrailObject *trail)
{
    if (trail->length < trail->capacity)
        return 0;
    Py_ssize_t newcap = (trail->capacity == 0) ? 64 : trail->capacity * 2;
    TrailEntry *buf = (TrailEntry *)PyMem_Realloc(
        trail->entries, (size_t)newcap * sizeof(TrailEntry));
    if (!buf) { PyErr_NoMemory(); return -1; }
    trail->entries  = buf;
    trail->capacity = newcap;
    return 0;
}

/*
 * trail_push — record var's current binding before overwriting it.
 *
 * Analogous to Trail_UV / Bind_UV in GNU Prolog and MachineState::trail()
 * in Scryer Prolog (machine_state_impl.rs).
 */
static int
trail_push(TrailObject *trail, VarObject *var)
{
    if (trail_check_owner(trail) < 0) return -1;
    if (trail_grow(trail) < 0) return -1;
    TrailEntry *e = &trail->entries[trail->length++];
    e->kind = TRAIL_BINDING;
    Py_INCREF(var);
    PyObject *old_binding = FT_ATOMIC_LOAD_PTR(var->binding);
    Py_XINCREF(old_binding);
    e->u.binding.var       = var;
    e->u.binding.old_value = old_binding;
    return 0;
}

/*
 * trail_bind — bind var to value, recording the previous binding on trail.
 *
 * Analogous to MachineState::bind() in Scryer and Bind_UV in GNU Prolog.
 */
static int
trail_bind(TrailObject *trail, VarObject *var, PyObject *value)
{
    if (trail_push(trail, var) < 0)
        return -1;
    Py_INCREF(value);
    PyObject *old = var->binding;
    FT_ATOMIC_STORE_PTR(var->binding, value);
    Py_XDECREF(old);
    return 0;
}

/*
 * trail_push_attr — record an attribute's current value before modifying it.
 *
 * old_attr is a borrowed reference (or NULL if the key was absent).
 * The trail takes its own owned reference.
 */
static int
trail_push_attr(TrailObject *trail, AttVarObject *attvar,
                PyObject *key, PyObject *old_attr)
{
    if (trail_check_owner(trail) < 0) return -1;
    if (trail_grow(trail) < 0) return -1;
    TrailEntry *e = &trail->entries[trail->length++];
    e->kind = TRAIL_ATTR;
    Py_INCREF(attvar);
    Py_INCREF(key);
    Py_XINCREF(old_attr);
    e->u.attr.attvar    = (PyObject *)attvar;
    e->u.attr.key       = key;
    e->u.attr.old_attr  = old_attr;
    return 0;
}

/*
 * trail_push_callback — record a Python no-arg callable to be called on undo.
 *
 * When trail_undo_to processes a TRAIL_CALLBACK entry it calls fn() with no
 * arguments.  Exceptions are cleared (undo must always complete).
 *
 * The trail takes an owned reference to fn.
 */
static int
trail_push_callback(TrailObject *trail, PyObject *fn)
{
    if (trail_check_owner(trail) < 0) return -1;
    if (trail_grow(trail) < 0) return -1;
    TrailEntry *e = &trail->entries[trail->length++];
    e->kind = TRAIL_CALLBACK;
    Py_INCREF(fn);
    e->u.callback.fn = fn;
    return 0;
}

/*
 * trail_enqueue_wakeup — append (attvar, bound_to) to trail->wakeup_list.
 *
 * Does nothing if wakeup_list is NULL (i.e. we are not inside py_unify).
 * Mirrors Scryer's push_attr_var_binding() which queues the binding in
 * attr_var_init.bindings for later processing by verify_attr_interrupt.
 */
static int
trail_enqueue_wakeup(TrailObject *trail, PyObject *attvar, PyObject *bound_to)
{
    if (!trail->wakeup_list)
        return 0;
    PyObject *pair = PyTuple_New(2);
    if (!pair) return -1;
    Py_INCREF(attvar);
    Py_INCREF(bound_to);
    PyTuple_SET_ITEM(pair, 0, attvar);
    PyTuple_SET_ITEM(pair, 1, bound_to);
    int r = PyList_Append(trail->wakeup_list, pair);
    Py_DECREF(pair);
    return r;
}

/*
 * trail_undo_to — restore all bindings and attribute changes after mark.
 *
 * Processes entries in reverse order (newest first), exactly as
 * Scryer's unwind_trail() and GNU Prolog's Pl_Untrail() do.
 */
static void
trail_undo_to(TrailObject *trail, Py_ssize_t mark)
{
    for (Py_ssize_t i = trail->length - 1; i >= mark; i--) {
        TrailEntry *e = &trail->entries[i];
        if (e->kind == TRAIL_BINDING) {
            VarObject *var = e->u.binding.var;
            PyObject  *old = e->u.binding.old_value;
            PyObject *cur = FT_ATOMIC_LOAD_PTR(var->binding);
            FT_ATOMIC_STORE_PTR(var->binding, old);  /* transfer ownership: trail → var */
            Py_XDECREF(cur);
            Py_DECREF(var);
        } else if (e->kind == TRAIL_ATTR) {
            /* Restore attribute */
            AttVarObject *av  = (AttVarObject *)e->u.attr.attvar;
            PyObject     *key = e->u.attr.key;
            PyObject     *old = e->u.attr.old_attr;
            if (av->attrs) {
                if (old == NULL) {
                    /* Key was absent before put_attr — delete it again */
                    PyDict_DelItem(av->attrs, key);  /* ignore errors */
                    PyErr_Clear();
                } else {
                    /* Restore previous value */
                    PyDict_SetItem(av->attrs, key, old);  /* ignoring errors */
                }
            }
            Py_DECREF(e->u.attr.attvar);
            Py_DECREF(key);
            Py_XDECREF(old);    /* release trail's owned ref */
        } else {
            /* TRAIL_CALLBACK — call fn() to perform undo */
            PyObject *fn  = e->u.callback.fn;
            PyObject *ret = PyObject_CallNoArgs(fn);
            if (ret == NULL)
                PyErr_Clear();  /* undo must always complete */
            else
                Py_DECREF(ret);
            Py_DECREF(fn);
        }
    }
    trail->length = mark;
}

/* ---- Trail Python methods ---- */

static PyObject *
Trail_mark(TrailObject *self, PyObject *Py_UNUSED(args))
{
    return PyLong_FromSsize_t(self->length);
}

static PyObject *
Trail_undo(TrailObject *self, PyObject *arg)
{
    if (trail_check_owner(self) < 0) return NULL;
    Py_ssize_t mark = PyLong_AsSsize_t(arg);
    if (mark == -1 && PyErr_Occurred()) return NULL;
    if (mark < 0) {
        PyErr_SetString(PyExc_ValueError, "trail mark out of range");
        return NULL;
    }
    /* If mark > length, an outer context already rewound past this mark
       (common when generators with try/finally are abandoned mid-execution
       during NAF, ForAll, or find_all).  Silently skip — the bindings are
       already undone. */
    if (mark <= self->length)
        trail_undo_to(self, mark);
    Py_RETURN_NONE;
}

static PyObject *
Trail_reset(TrailObject *self, PyObject *Py_UNUSED(args))
{
    if (trail_check_owner(self) < 0) return NULL;
    trail_undo_to(self, 0);
    Py_RETURN_NONE;
}

static PyObject *
Trail_record(TrailObject *self, PyObject *fn)
{
    /* trail.record(callable) — push a no-arg undo callback onto the trail.
     *
     * The callable will be invoked (with no arguments) when trail.undo()
     * processes this entry during backtracking.  Exceptions raised by the
     * callable are silently cleared so that undo always completes.
     *
     * Typical usage from Python::
     *
     *     old = self._data.get(key, _ABSENT)
     *     def _undo():
     *         if old is _ABSENT:
     *             self._data.pop(key, None)
     *         else:
     *             self._data[key] = old
     *     trail.record(_undo)
     *     self._data[key] = value
     */
    if (!PyCallable_Check(fn)) {
        PyErr_SetString(PyExc_TypeError, "trail.record() argument must be callable");
        return NULL;
    }
    if (trail_push_callback(self, fn) < 0)
        return NULL;
    Py_RETURN_NONE;
}

static PyObject *
Trail_repr(TrailObject *self)
{
    return PyUnicode_FromFormat("Trail(length=%zd)", self->length);
}

static Py_ssize_t
Trail_sq_len(TrailObject *self)
{
    return self->length;
}

static PyMethodDef Trail_methods[] = {
    {"mark",  (PyCFunction)Trail_mark,  METH_NOARGS,
     "mark() -> int\n"
     "\n"
     "Return the current trail length as an integer backtrack mark.\n"
     "Pass this mark to undo() to restore all bindings made since here."},
    {"undo",  (PyCFunction)Trail_undo,  METH_O,
     "undo(mark)\n"
     "\n"
     "Restore all variable bindings and attribute changes recorded after\n"
     "*mark* was taken.  Processes entries in reverse chronological order."},
    {"reset", (PyCFunction)Trail_reset, METH_NOARGS,
     "reset()\n"
     "\n"
     "Undo every binding and attribute change on this trail (undo(0))."},
    {"record", (PyCFunction)Trail_record, METH_O,
     "record(callable)\n"
     "\n"
     "Push a no-arg undo callback onto the trail.  The callable will be\n"
     "invoked (with no arguments) when trail.undo() processes this entry\n"
     "during backtracking.  Useful for recording mutable-state mutations\n"
     "that must be reversed on backtrack (e.g. MutableDict, MutableSet)."},
    {NULL, NULL, 0, NULL}
};

static PySequenceMethods Trail_as_sequence = {
    .sq_length = (lenfunc)Trail_sq_len,
};

static PyTypeObject TrailType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name      = "clausal.logic.variables.Trail",
    .tp_doc       = (
        "Trail for recording and undoing variable bindings and attribute changes.\n"
        "\n"
        "Usage pattern::\n"
        "\n"
        "    trail = Trail()\n"
        "    mark  = trail.mark()\n"
        "    if not unify(t1, t2, trail):\n"
        "        trail.undo(mark)   # already done automatically on failure\n"
        "    # ... explore this branch ...\n"
        "    trail.undo(mark)       # backtrack\n"
        "\n"
        "len(trail) returns the number of recorded entries (bindings + attr changes).\n"
    ),
    .tp_basicsize   = sizeof(TrailObject),
    .tp_itemsize    = 0,
    .tp_flags           = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_new             = Trail_new,
    .tp_dealloc         = (destructor)Trail_dealloc,
    .tp_traverse        = (traverseproc)Trail_traverse,
    .tp_clear           = (inquiry)Trail_clear,
    .tp_repr            = (reprfunc)Trail_repr,
    .tp_methods         = Trail_methods,
    .tp_as_sequence     = &Trail_as_sequence,
    .tp_weaklistoffset  = offsetof(TrailObject, weakrefs),
};


/* ================================================================
 * Occurs check
 *
 * Mirrors GNU Prolog's Check_If_Var_Occurs (unify.c:186) and
 * Scryer's bind_with_occurs_check (unify.rs).
 *
 * Returns 1 if var appears free in term, 0 if not, -1 on error.
 * ================================================================ */

#define MAX_DEPTH 50000

static int
do_occurs_check(VarObject *var, PyObject *term, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "occurs_check: term nesting too deep");
        return -1;
    }
    term = var_deref(term);
    if (term == (PyObject *)var)
        return 1;
    if (Var_Check(term))
        return 0;
    if (PyTuple_Check(term)) {
        Py_ssize_t n = PyTuple_GET_SIZE(term);
        for (Py_ssize_t i = 0; i < n; i++) {
            int r = do_occurs_check(var, PyTuple_GET_ITEM(term, i), depth + 1);
            if (r) return r;
        }
        return 0;
    }
    if (PyList_Check(term)) {
        Py_ssize_t n = PyList_GET_SIZE(term);
        for (Py_ssize_t i = 0; i < n; i++) {
            int r = do_occurs_check(var, PyList_GET_ITEM(term, i), depth + 1);
            if (r) return r;
        }
        return 0;
    }
    /* __occurs_check__ protocol: delegate to Python method if present */
    {
        PyObject *hook = PyObject_GetAttrString(term, "__occurs_check__");
        if (hook) {
            PyObject *result = PyObject_CallOneArg(hook, (PyObject *)var);
            Py_DECREF(hook);
            if (!result) return -1;
            int r = PyObject_IsTrue(result);
            Py_DECREF(result);
            return r;
        }
        PyErr_Clear();
    }
    return 0;
}


/* ================================================================
 * Unification  (extended for AttVar)
 *
 * When an AttVar with attributes is bound (Var-Term or Var-Var where
 * the AttVar is the "newer" variable being bound), a wakeup is
 * enqueued via trail_enqueue_wakeup().  Hooks are fired after
 * do_unify() returns from py_unify().
 *
 * This mirrors Scryer's bind_attr_var() which calls
 * push_attr_var_binding() to defer hook execution.
 * ================================================================ */

/* ── The char atom (atoms-as-cells/strings §6.2) ──────────────────────────
 *
 * ``char_atom_from_ucs4(c)`` is the C twin of
 * ``clausal.logic.atoms.char_atom``: the arity-0 CELL ``("a",)`` whose
 * spelling is the single character *c*.  New reference.
 *
 * ASCII is served from a 128-entry cache built at module init, so the
 * str↔list unification arms below allocate nothing for ordinary text; a
 * non-ASCII character packs a fresh cell.  The cache is bounded and
 * process-lived by construction (128 entries, one per ASCII codepoint) —
 * it is NOT the process-wide atom table §5.2 rules out, which would have
 * grown with every enumerated spelling.
 */
static PyObject *g_ascii_char_atoms[128] = {NULL};

static PyObject *
char_atom_from_ucs4(Py_UCS4 c)
{
    if (c < 128 && g_ascii_char_atoms[c] != NULL)
        return Py_NewRef(g_ascii_char_atoms[c]);
    return PyUnicode_FromOrdinal((int)c);   /* STAGE 2: the char atom is the 1-char str */
}

/* Interned "__unify__", set in PyInit__variables before any unify runs. */
static PyObject *str_dunder_unify = NULL;

/* Probe *obj* for a ``__unify__`` attribute without paying for an
 * AttributeError on the (overwhelmingly common) miss.  Returns 1 with
 * *hook_out* set to a strong ref, 0 with *hook_out* NULL on a clean miss,
 * -1 on error.  Instance attributes are honoured exactly as
 * PyObject_GetAttr would (the protocol is an attribute lookup, not a
 * type-only special-method lookup — pinned by
 * tests/test_unify.py::TestUnifyHookProbe). */
static inline int
probe_unify_hook(PyObject *obj, PyObject **hook_out)
{
#if PY_VERSION_HEX >= 0x030D0000
    return PyObject_GetOptionalAttr(obj, str_dunder_unify, hook_out);
#else
    *hook_out = PyObject_GetAttr(obj, str_dunder_unify);
    if (*hook_out)
        return 1;
    if (!PyErr_ExceptionMatches(PyExc_AttributeError))
        return -1;
    PyErr_Clear();
    return 0;
#endif
}

/* True for any spelling of the empty list: [], "", b"", ().  All four are
 * the reserved atom '[]' (ISO; Scryer round-trips it), so unification must
 * not tell them apart -- see the nil branch inside do_unify below. */
static inline int is_nil_spelling(PyObject *t)
{
    if (PyList_Check(t))    return PyList_GET_SIZE(t) == 0;
    /* STAGE 2: a bare str is an ATOM -- '' is not nil; the empty CARRIER below is */
    if (PyBytes_Check(t))   return PyBytes_GET_SIZE(t) == 0;
    /* the EMPTY chars carrier ('$chars', "") is nil too (stage 1; review 2026-09-18) */
    if (PyTuple_CheckExact(t) && PyTuple_GET_SIZE(t) == 2
        && PyUnicode_Check(PyTuple_GET_ITEM(t, 0))
        && PyUnicode_CompareWithASCIIString(PyTuple_GET_ITEM(t, 0), "$chars") == 0
        && PyUnicode_Check(PyTuple_GET_ITEM(t, 1)))
        return PyUnicode_GET_LENGTH(PyTuple_GET_ITEM(t, 1)) == 0;
    if (PyTuple_Check(t))   return PyTuple_GET_SIZE(t) == 0;
    return 0;
}


/* ---- numeric-type census state (default OFF) ----
 * Declared here rather than beside its accessors because do_unify() below is
 * the only writer and C needs the declaration first.
 */
static int unify_census_on = 0;
static unsigned long long unify_census_count = 0;
static PyObject *unify_census_sites = NULL;   /* {"int/float": n, ...}, unordered pair */


/* THE CHARS CARRIER (stage 1 of the atoms-as-str flip, spec 2026-09-18):
 * ('$chars', "abc") is the compact form of the char list and EQUAL to it.
 * Unwrapped to its str right before the str<->list arms, and only there --
 * a Var must bind to the carrier itself, never to the bare str. */
static inline int
is_chars_carrier(PyObject *t)
{
    return PyTuple_CheckExact(t) && PyTuple_GET_SIZE(t) == 2
        && PyUnicode_Check(PyTuple_GET_ITEM(t, 0))
        && PyUnicode_CompareWithASCIIString(PyTuple_GET_ITEM(t, 0), "$chars") == 0
        && PyUnicode_Check(PyTuple_GET_ITEM(t, 1));
}

static inline PyObject *
unwrap_chars(PyObject *t)
{
    return is_chars_carrier(t) ? PyTuple_GET_ITEM(t, 1) : t;
}

/* Forward declarations: defined with the term-inspection cache further down
 * (``Compound_type`` is set by ``_register_term_types``). */
static PyObject *Compound_type;
static PyObject *str_functor;
static PyObject *str_args;

/*
 * compound_to_cell(obj, &out) -- C twin of ``clausal.terms.compound_as_cell``.
 *
 * Ruling 2026-09-26: a Compound whose functor dereferences to an atom (a str)
 * and whose arity is >= 1 IS the cell (functor, *args) -- except the functors
 * '$chars' (its cell is the chars carrier) and '()' (TUPLE_TAG: its cell is
 * tuple data).  Returns 1 with *out a
 * NEW reference to that cell; 0 (and *out NULL) when obj is not a Compound or
 * has no cell equivalent (Var / non-atom functor, arity 0); -1 on error.
 * Before ``_register_term_types`` runs, Compound_type is NULL and this answers
 * 0 -- the Python ``Compound.__unify__`` tuple arm then decides instead.
 */
static int
compound_to_cell(PyObject *obj, PyObject **out)
{
    *out = NULL;
    if (Compound_type == NULL || !PyType_Check(Compound_type)) return 0;
    if (!PyObject_TypeCheck(obj, (PyTypeObject *)Compound_type)) return 0;
    PyObject *functor = PyObject_GetAttr(obj, str_functor);
    if (!functor) return -1;
    PyObject *f = var_deref(functor);          /* borrowed */
    /* '$chars' and '()' are excluded: their cells are the chars CARRIER
     * (text) and tuple DATA, not compounds -- see compound_as_cell. */
    if (!PyUnicode_Check(f)
            || PyUnicode_CompareWithASCIIString(f, "$chars") == 0
            || PyUnicode_CompareWithASCIIString(f, "()") == 0) {
        Py_DECREF(functor);
        return 0;
    }
    PyObject *args = PyObject_GetAttr(obj, str_args);
    if (!args) { Py_DECREF(functor); return -1; }
    if (!PyTuple_Check(args) || PyTuple_GET_SIZE(args) == 0) {
        Py_DECREF(functor); Py_DECREF(args);
        return 0;
    }
    Py_ssize_t n = PyTuple_GET_SIZE(args);
    PyObject *cell = PyTuple_New(n + 1);
    if (!cell) { Py_DECREF(functor); Py_DECREF(args); return -1; }
    Py_INCREF(f);
    PyTuple_SET_ITEM(cell, 0, f);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *a = PyTuple_GET_ITEM(args, i);
        Py_INCREF(a);
        PyTuple_SET_ITEM(cell, i + 1, a);
    }
    Py_DECREF(functor);
    Py_DECREF(args);
    *out = cell;
    return 1;
}

static int
do_unify(PyObject *t1, PyObject *t2, TrailObject *trail, int depth, int oc)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "unify: term nesting too deep");
        return -1;
    }

    t1 = var_deref(t1);
    t2 = var_deref(t2);

    if (t1 == t2)
        return 1;

    int t1v = Var_Check(t1);
    int t2v = Var_Check(t2);

    /* ---- Var-Var ---- */
    if (t1v && t2v) {
        VarObject *v1 = Var_CAST(t1), *v2 = Var_CAST(t2);
        /*
         * Age-ordered binding: bind the newer var (larger id) to the older.
         * Mirrors Scryer bind() and GNU Prolog's "bind higher address to lower"
         * convention.  Keeps the older variable as canonical representative.
         */
        VarObject *newer = (v1->var_id > v2->var_id) ? v1 : v2;
        VarObject *older = (v1->var_id > v2->var_id) ? v2 : v1;

        FtCriticalSection2 cs2;
        FT_CS2_BEGIN(&cs2, newer, older);
        /* Re-check after acquiring lock — another thread may have bound newer */
        PyObject *nb = FT_ATOMIC_LOAD_PTR(newer->binding);
        if (nb != NULL) {
            FT_CS2_END(&cs2);
            /* Variable was bound by another thread — retry unification
             * with the now-bound value. */
            return do_unify((PyObject *)newer, (PyObject *)older,
                            trail, depth, oc);
        }
        if (trail_bind(trail, newer, (PyObject *)older) < 0) {
            FT_CS2_END(&cs2);
            return -1;
        }

        /*
         * If the variable being bound (newer) is an AttVar with attributes,
         * enqueue a wakeup so hooks are called after structural unification.
         * The "value" the AttVar is being unified with is the older var;
         * hooks receive it as bound_to and can inspect / constrain further.
         */
        if (AttVar_Check(newer) && AttVar_CAST(newer)->attrs != NULL) {
            if (trail_enqueue_wakeup(trail, (PyObject *)newer,
                                     (PyObject *)older) < 0) {
                FT_CS2_END(&cs2);
                return -1;
            }
        }
        FT_CS2_END(&cs2);
        return 1;
    }

    /* ---- Var-Term ---- */
    if (t1v) {
        if (oc) {
            int found = do_occurs_check(Var_CAST(t1), t2, 0);
            if (found < 0) return -1;
            if (found)     return 0;
        }
        FtCriticalSection cs;
        FT_CS_BEGIN(&cs, t1);
        PyObject *b1 = FT_ATOMIC_LOAD_PTR(Var_CAST(t1)->binding);
        if (b1 != NULL) {
            FT_CS_END(&cs);
            return do_unify(t1, t2, trail, depth, oc);  /* retry with bound value */
        }
        if (trail_bind(trail, Var_CAST(t1), t2) < 0) {
            FT_CS_END(&cs);
            return -1;
        }
        if (AttVar_Check(t1) && AttVar_CAST(t1)->attrs != NULL) {
            if (trail_enqueue_wakeup(trail, t1, t2) < 0) {
                FT_CS_END(&cs);
                return -1;
            }
        }
        FT_CS_END(&cs);
        return 1;
    }
    if (t2v) {
        if (oc) {
            int found = do_occurs_check(Var_CAST(t2), t1, 0);
            if (found < 0) return -1;
            if (found)     return 0;
        }
        FtCriticalSection cs;
        FT_CS_BEGIN(&cs, t2);
        PyObject *b2 = FT_ATOMIC_LOAD_PTR(Var_CAST(t2)->binding);
        if (b2 != NULL) {
            FT_CS_END(&cs);
            return do_unify(t2, t1, trail, depth, oc);  /* retry with bound value */
        }
        if (trail_bind(trail, Var_CAST(t2), t1) < 0) {
            FT_CS_END(&cs);
            return -1;
        }
        if (AttVar_Check(t2) && AttVar_CAST(t2)->attrs != NULL) {
            if (trail_enqueue_wakeup(trail, t2, t1) < 0) {
                FT_CS_END(&cs);
                return -1;
            }
        }
        FT_CS_END(&cs);
        return 1;
    }

    /* ---- Both non-Var: structural comparison ---- */

    /* Every spelling of the EMPTY LIST is the one reserved atom '[]' (fix
     * round 2, item 2, operator-ruled 2026-09-07), so they all unify with
     * each other.  [] vs "" and [] vs b"" already did, through the str/list
     * and bytes/list branches further down; the empty TUPLE -- atoms.NIL_KEY,
     * the hashable spelling a dict key uses -- did not, because the
     * tuple/list pair never meets in this dispatch.  Decided here, before
     * the type-paired branches, so all four agree.  A non-empty tuple is a
     * CELL (or tuple-data) and is unaffected. */
    if (is_nil_spelling(t1) && is_nil_spelling(t2)) return 1;

    if (PyTuple_Check(t1) && PyTuple_Check(t2)) {
        Py_ssize_t n = PyTuple_GET_SIZE(t1);
        if (n != PyTuple_GET_SIZE(t2)) return 0;
        for (Py_ssize_t i = 0; i < n - 1; i++) {
            int r = do_unify(PyTuple_GET_ITEM(t1, i),
                             PyTuple_GET_ITEM(t2, i),
                             trail, depth + 1, oc);
            if (r != 1) return r;
        }
        if (n == 0) return 1;
        return do_unify(PyTuple_GET_ITEM(t1, n-1),
                        PyTuple_GET_ITEM(t2, n-1),
                        trail, depth + 1, oc);
    }

    /* A Compound meeting a tuple (ruling 2026-09-26): an atom-functor
     * Compound of arity >= 1 IS its cell, so unify the cell -- here, before
     * the __unify__ hooks, so the occurs-check flag carries through (the
     * Python hook cannot see it).  A Compound with no cell equivalent falls
     * through and fails against the tuple as before. */
    if (PyTuple_CheckExact(t1) != PyTuple_CheckExact(t2)) {
        PyObject *comp = PyTuple_CheckExact(t1) ? t2 : t1;
        PyObject *cell;
        int c = compound_to_cell(comp, &cell);
        if (c < 0) return -1;
        if (c) {
            int r = (comp == t1)
                ? do_unify(cell, t2, trail, depth + 1, oc)
                : do_unify(t1, cell, trail, depth + 1, oc);
            Py_DECREF(cell);
            return r;
        }
    }

    /* STAGE 2 (spec 2026-09-18): the chars carrier is the ONLY text.  It
     * walks to its str here, and the str<->list arms below are reachable
     * only through it (the flags): a bare str is an ATOM, equal to itself,
     * never to a list and never to the carrier of the same text. */
    int t1_text = 0, t2_text = 0;
    PyObject *t1_term = t1, *t2_term = t2;   /* the carrier itself, for the __unify__ hooks below */
    if (is_chars_carrier(t1)) { t1 = unwrap_chars(t1); t1_text = 1; }
    if (is_chars_carrier(t2)) { t2 = unwrap_chars(t2); t2_text = 1; }
    if (t1_text && t2_text)
        return PyUnicode_Compare(t1, t2) == 0;
    if ((t1_text && PyUnicode_Check(t2)) || (t2_text && PyUnicode_Check(t1)))
        return 0;   /* a string is not the atom of its text */
    if (PyList_Check(t1) && PyList_Check(t2)) {
        Py_ssize_t n = PyList_GET_SIZE(t1);
        if (n != PyList_GET_SIZE(t2)) return 0;
        for (Py_ssize_t i = 0; i < n - 1; i++) {
            /* FT-safe element access: PyList_GetItemRef returns a new
             * strong reference (NULL on error) and applies the appropriate
             * critical section on free-threaded builds. */
            PyObject *e1 = PyList_GetItemRef(t1, i);
            if (e1 == NULL) return -1;
            PyObject *e2 = PyList_GetItemRef(t2, i);
            if (e2 == NULL) {
                Py_DECREF(e1);
                return -1;
            }
            int r = do_unify(e1, e2, trail, depth + 1, oc);
            Py_DECREF(e1);
            Py_DECREF(e2);
            if (r != 1) return r;
        }
        if (n == 0) return 1;
        {
            PyObject *e1 = PyList_GetItemRef(t1, n - 1);
            if (e1 == NULL) return -1;
            PyObject *e2 = PyList_GetItemRef(t2, n - 1);
            if (e2 == NULL) {
                Py_DECREF(e1);
                return -1;
            }
            int r = do_unify(e1, e2, trail, depth + 1, oc);
            Py_DECREF(e1);
            Py_DECREF(e2);
            return r;
        }
    }

    /* ---- String ↔ List unification (atoms-as-cells/strings §6.2) ----
     * A str DENOTES the list of its char atoms, so the two spellings of
     * one term unify: "abc" with [("a",), ("b",), ("c",)], and "" with [].
     * P3-1 §1b had retired this arm because a char was then a 1-char str
     * and the rule made an atom indistinguishable from a one-element
     * list; a char is a CELL now, and the rule is sound again.
     *
     * Modelled on the bytes↔list arms below: a Var element binds to the
     * char atom; an element that is already a char atom compares code
     * points with no allocation; anything else (a SegString, a custom
     * term with __unify__) delegates to do_unify against the char atom.
     *
     * A 1-char str on the other side does NOT match a char atom — ``("a",)
     * = "a"`` stays FALSE via the mixed list/tuple guard further down,
     * because "a" is the one-element LIST [("a",)], not the char.
     */
    if (t1_text && PyList_Check(t2)) {   /* carrier vs list */
        Py_ssize_t n = PyUnicode_GET_LENGTH(t1);
        if (n != PyList_GET_SIZE(t2)) return 0;
        if (n == 0) return 1;
        int kind = PyUnicode_KIND(t1);
        const void *data = PyUnicode_DATA(t1);
        for (Py_ssize_t i = 0; i < n; i++) {
            Py_UCS4 c1 = PyUnicode_READ(kind, data, i);
            PyObject *elem_raw = PyList_GetItemRef(t2, i);
            if (elem_raw == NULL) return -1;
            PyObject *elem = var_deref(elem_raw);
            if (!Var_Check(elem) && PyUnicode_Check(elem)
                    && PyUnicode_GET_LENGTH(elem) == 1) {
                Py_UCS4 c2 = PyUnicode_READ_CHAR(elem, 0);
                Py_DECREF(elem_raw);
                if (c1 != c2) return 0;
            } else {
                PyObject *a = char_atom_from_ucs4(c1);
                if (!a) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(a, elem, trail, depth + 1, oc);
                Py_DECREF(a);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            }
        }
        return 1;
    }
    if (PyList_Check(t1) && t2_text) {   /* list vs carrier */
        /* Symmetric: list on left, str on right. */
        Py_ssize_t n = PyUnicode_GET_LENGTH(t2);
        if (PyList_GET_SIZE(t1) != n) return 0;
        if (n == 0) return 1;
        int kind = PyUnicode_KIND(t2);
        const void *data = PyUnicode_DATA(t2);
        for (Py_ssize_t i = 0; i < n; i++) {
            Py_UCS4 c2 = PyUnicode_READ(kind, data, i);
            PyObject *elem_raw = PyList_GetItemRef(t1, i);
            if (elem_raw == NULL) return -1;
            PyObject *elem = var_deref(elem_raw);
            if (!Var_Check(elem) && PyUnicode_Check(elem)
                    && PyUnicode_GET_LENGTH(elem) == 1) {
                Py_UCS4 c1 = PyUnicode_READ_CHAR(elem, 0);
                Py_DECREF(elem_raw);
                if (c1 != c2) return 0;
            } else {
                PyObject *a = char_atom_from_ucs4(c2);
                if (!a) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(elem, a, trail, depth + 1, oc);
                Py_DECREF(a);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            }
        }
        return 1;
    }

    /* ---- Bytes ↔ List unification (codes model) ----
     * Treat a Python bytes as a list of ints in [0, 255]:
     * b"abc" unifies element-wise with [97, 98, 99].
     * bytes-vs-bytes still falls through to PyObject_RichCompareBool below.
     * Mirror of the str↔list branch above; the fast path compares int
     * values with no allocation, allocating a PyLong only to bind a Var or
     * delegate to a custom term's __unify__. */
    if (PyBytes_Check(t1) && PyList_Check(t2)) {
        Py_ssize_t n = PyBytes_GET_SIZE(t1);
        if (n != PyList_GET_SIZE(t2)) return 0;
        if (n == 0) return 1;
        const unsigned char *data = (const unsigned char *)PyBytes_AS_STRING(t1);
        for (Py_ssize_t i = 0; i < n; i++) {
            long c1 = (long)data[i];
            PyObject *elem_raw = PyList_GetItemRef(t2, i);
            if (elem_raw == NULL) return -1;
            PyObject *elem = var_deref(elem_raw);
            if (Var_Check(elem)) {
                PyObject *code = PyLong_FromLong(c1);
                if (!code) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(code, elem, trail, depth + 1, oc);
                Py_DECREF(code);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            } else if (PyLong_Check(elem)) {
                /* Ground int element — compare value, no allocation. A
                 * bool is a PyLong subclass (True==1) and matches by value. */
                int overflow = 0;
                long v = PyLong_AsLongAndOverflow(elem, &overflow);
                Py_DECREF(elem_raw);
                if (overflow || v != c1) return 0;
            } else {
                /* Not a Var, not an int — could be a SegBytes or other
                 * custom term. Allocate the code and delegate to do_unify. */
                PyObject *code = PyLong_FromLong(c1);
                if (!code) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(code, elem, trail, depth + 1, oc);
                Py_DECREF(code);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            }
        }
        return 1;
    }
    if (PyList_Check(t1) && PyBytes_Check(t2)) {
        /* Symmetric: list on left, bytes on right. */
        Py_ssize_t n = PyBytes_GET_SIZE(t2);
        if (PyList_GET_SIZE(t1) != n) return 0;
        if (n == 0) return 1;
        const unsigned char *data = (const unsigned char *)PyBytes_AS_STRING(t2);
        for (Py_ssize_t i = 0; i < n; i++) {
            long c2 = (long)data[i];
            PyObject *elem_raw = PyList_GetItemRef(t1, i);
            if (elem_raw == NULL) return -1;
            PyObject *elem = var_deref(elem_raw);
            if (Var_Check(elem)) {
                PyObject *code = PyLong_FromLong(c2);
                if (!code) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(elem, code, trail, depth + 1, oc);
                Py_DECREF(code);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            } else if (PyLong_Check(elem)) {
                int overflow = 0;
                long v = PyLong_AsLongAndOverflow(elem, &overflow);
                Py_DECREF(elem_raw);
                if (overflow || v != c2) return 0;
            } else {
                PyObject *code = PyLong_FromLong(c2);
                if (!code) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(elem, code, trail, depth + 1, oc);
                Py_DECREF(code);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            }
        }
        return 1;
    }

    /* __unify__ protocol: delegate to Python method if present.
     * Allows custom term types (DictTerm, SetTerm, SegList, etc.) to define
     * their own unification behaviour without hardcoding each type in C.
     * Checked BEFORE the mixed list/tuple guard so that custom types like
     * SegList can unify against plain Python lists.
     * The method signature is: __unify__(other, trail) -> bool | NotImplemented
     *
     * The probe is exception-free (probe_unify_hook): the old
     * GetAttrString+PyErr_Clear tail raised and discarded two
     * AttributeErrors on every failing unification of ordinary terms —
     * ~83% of the failure cost (todo/done/unify-failure-pays-two-
     * attributeerrors.md).  One deliberate tightening rides along: a
     * broken __getattr__ raising something other than AttributeError now
     * propagates instead of being silently cleared into an ==-compare.
     */
    if (!PyList_Check(t1) && !PyTuple_Check(t1)) {
        PyObject *hook;
        if (probe_unify_hook(t1, &hook) < 0) return -1;
        if (hook) {
            PyObject *result = PyObject_CallFunctionObjArgs(
                hook, t2_term, (PyObject *)trail, NULL);   /* STAGE 2: a Seg* hook must see the CARRIER -- a bare str is an atom to it */
            Py_DECREF(hook);
            if (result == NULL) return -1;
            if (result != Py_NotImplemented) {
                int r = PyObject_IsTrue(result);
                Py_DECREF(result);
                return r;
            }
            Py_DECREF(result);
            /* Fall through: NotImplemented — try symmetric or list guard */
        }
    }
    /* Symmetric: try t2.__unify__ if t1 didn't handle it */
    if (!PyList_Check(t2) && !PyTuple_Check(t2)) {
        PyObject *hook;
        if (probe_unify_hook(t2, &hook) < 0) return -1;
        if (hook) {
            PyObject *result = PyObject_CallFunctionObjArgs(
                hook, t1_term, (PyObject *)trail, NULL);
            Py_DECREF(hook);
            if (result == NULL) return -1;
            if (result != Py_NotImplemented) {
                int r = PyObject_IsTrue(result);
                Py_DECREF(result);
                return r;
            }
            Py_DECREF(result);
        }
    }

    if (PyTuple_Check(t1) || PyList_Check(t1) ||
        PyTuple_Check(t2) || PyList_Check(t2))
        return 0;

    int cmp = PyObject_RichCompareBool(t1, t2, Py_EQ);
    if (cmp < 0) return -1;

    /* ---- numeric-type census (spec: todo/iso-unify-conflates-int-and-float) ----
     *
     * ISO says 1 and 1.0 are DISTINCT terms; `PyObject_RichCompareBool` says
     * they are equal, so unification conflates them. Before changing that on
     * the hottest path in the engine, count how often it actually happens.
     *
     * Cost when disabled: one load of a global int and a predictable
     * not-taken branch, on the FALLBACK path only — reached solely for two
     * dereferenced, non-variable, non-container ground terms. Variable
     * binding and structure walking never arrive here.
     *
     * Counted: the comparison SUCCEEDED but the two terms have different
     * Python types and both are numbers. That is exactly the population a
     * type-strict unify would start rejecting.
     */
    if (unify_census_on && cmp == 1 && Py_TYPE(t1) != Py_TYPE(t2)
            && PyNumber_Check(t1) && PyNumber_Check(t2)) {
        unify_census_count++;
        if (unify_census_sites) {
            /* Keyed by the UNORDERED type pair: unify(2, Fraction(2, 1)) and
             * unify(Fraction(2, 1), 2) are one phenomenon and must sum under
             * one key, whichever side each term arrived on. The two names go
             * in descending strcmp order, which keeps the documented
             * "int/float" spelling. */
            const char *n1 = Py_TYPE(t1)->tp_name;
            const char *n2 = Py_TYPE(t2)->tp_name;
            if (strcmp(n1, n2) < 0) { const char *tmp = n1; n1 = n2; n2 = tmp; }
            PyObject *key = PyUnicode_FromFormat("%s/%s", n1, n2);
            if (key) {
                PyObject *cur = PyDict_GetItemWithError(unify_census_sites, key);
                long n = (cur && PyLong_Check(cur)) ? PyLong_AsLong(cur) : 0;
                PyObject *nv = PyLong_FromLong(n + 1);
                if (nv) { PyDict_SetItem(unify_census_sites, key, nv); Py_DECREF(nv); }
                Py_DECREF(key);
            }
            PyErr_Clear();   /* census must never perturb the caller */
        }
    }
    return cmp;
}


/* ================================================================
 * fire_wakeups
 *
 * Called after do_unify() succeeds.  For each (attvar, bound_to) pair
 * in wakeup_list:
 *
 *   1. Snapshot the attvar's attrs dict (so hooks may mutate it safely).
 *   2. Deref bound_to in case it was further constrained.
 *   3. For each (key, attr_val) in the snapshot:
 *        hook = g_attr_hooks.get(key)
 *        if hook: result = hook(attr_val, bound_to, trail)
 *        if result is falsy → return 0 (failure).
 *
 * Returns 1 (success), 0 (hook failure), -1 (Python exception).
 *
 * Mirrors Scryer's driver/2 → call_verify_attributes → verify_attrs
 * sequence in machine/attributed_variables.pl.
 * ================================================================ */

static int
fire_wakeups(PyObject *wakeup_list, TrailObject *trail)
{
    Py_ssize_t n = PyList_GET_SIZE(wakeup_list);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *pair     = PyList_GET_ITEM(wakeup_list, i);
        PyObject *attvar   = PyTuple_GET_ITEM(pair, 0);
        PyObject *bound_to = PyTuple_GET_ITEM(pair, 1);

        /* Follow any further bindings made after the initial bind */
        bound_to = var_deref(bound_to);

        AttVarObject *av = AttVar_CAST(attvar);
        if (!av->attrs)
            continue;

        /*
         * Take a snapshot of the attrs items before calling hooks.
         * This prevents issues if a hook modifies the attrs dict.
         * PyDict_Items returns a new list of (key, value) tuples.
         */
        PyObject *items = PyDict_Items(av->attrs);
        if (!items) return -1;

        Py_ssize_t nitems = PyList_GET_SIZE(items);
        for (Py_ssize_t j = 0; j < nitems; j++) {
            PyObject *kv       = PyList_GET_ITEM(items, j);
            PyObject *key      = PyTuple_GET_ITEM(kv, 0);
            PyObject *attr_val = PyTuple_GET_ITEM(kv, 1);

            /* PyDict_GetItemRef returns a strong ref (3.13+).
             * Fall back to PyDict_GetItemWithError + Py_XINCREF on older builds. */
#if PY_VERSION_HEX >= 0x030D0000
            PyObject *hook = NULL;
            int has = PyDict_GetItemRef(g_attr_hooks, key, &hook);
            if (has < 0) {
                Py_DECREF(items);
                return -1;
            }
            if (has == 0)
                continue;   /* no hook registered for this key */
#else
            PyObject *hook = PyDict_GetItemWithError(g_attr_hooks, key);
            if (!hook) {
                if (PyErr_Occurred()) {
                    Py_DECREF(items);
                    return -1;
                }
                continue;   /* no hook registered for this key */
            }
            Py_INCREF(hook);
#endif

            PyObject *result = PyObject_CallFunctionObjArgs(
                hook, attr_val, bound_to, (PyObject *)trail, NULL);
            if (!result) {
                Py_DECREF(hook);
                Py_DECREF(items);
                return -1;
            }
            int truthy = PyObject_IsTrue(result);
            Py_DECREF(result);
            if (truthy < 0) {
                Py_DECREF(hook);
                Py_DECREF(items);
                return -1;
            }
            if (!truthy) {
                Py_DECREF(hook);
                Py_DECREF(items);
                return 0;   /* hook rejected the unification */
            }
            Py_DECREF(hook);
        }
        Py_DECREF(items);
    }
    return 1;
}


/* ================================================================
 * do_unify_and_wake — shared core for py_unify / py_unify_with_occurs_check
 *
 * Protocol:
 *   1. Swap in a fresh wakeup_list on the trail (scoped to this call).
 *   2. Run structural unification (do_unify).
 *   3. Restore the old wakeup_list so any hooks calling unify() get
 *      their own fresh list (nested calls are self-contained).
 *   4. Fire wakeups; roll back on failure or exception.
 * ================================================================ */

static PyObject *
do_unify_and_wake(PyObject *t1, PyObject *t2, TrailObject *trail, int oc)
{
    Py_ssize_t mark = trail->length;

    /* Swap in a fresh wakeup list scoped to this unify() invocation */
    PyObject *saved_wl = trail->wakeup_list;
    PyObject *my_wl    = PyList_New(0);
    if (!my_wl) return NULL;
    trail->wakeup_list = my_wl;

    int result = do_unify(t1, t2, trail, 0, oc);

    /* Restore wakeup_list before firing hooks so nested unify() calls
     * (from within hooks) each get their own scope. */
    trail->wakeup_list = saved_wl;

    if (result < 0) {
        trail_undo_to(trail, mark);
        Py_DECREF(my_wl);
        return NULL;
    }
    if (!result) {
        trail_undo_to(trail, mark);
        Py_DECREF(my_wl);
        Py_RETURN_FALSE;
    }

    /* Fire attribute wakeup hooks */
    int wake = fire_wakeups(my_wl, trail);
    Py_DECREF(my_wl);

    if (wake < 0) {
        trail_undo_to(trail, mark);
        return NULL;
    }
    if (!wake) {
        trail_undo_to(trail, mark);
        Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
}


/* ================================================================
 * Module-level functions
 * ================================================================ */

/*
 * unify(t1, t2, trail) -> bool
 */
static PyObject *
py_unify(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *t1, *t2, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &t1, &t2, &trail_obj))
        return NULL;
    if (!PyObject_TypeCheck(trail_obj, &TrailType)) {
        PyErr_SetString(PyExc_TypeError,
                        "unify() third argument must be a Trail");
        return NULL;
    }
    return do_unify_and_wake(t1, t2, (TrailObject *)trail_obj, 0);
}

/*
 * unify_with_occurs_check(t1, t2, trail) -> bool
 */
static PyObject *
py_unify_with_occurs_check(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *t1, *t2, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &t1, &t2, &trail_obj))
        return NULL;
    if (!PyObject_TypeCheck(trail_obj, &TrailType)) {
        PyErr_SetString(PyExc_TypeError,
                        "unify_with_occurs_check() third argument must be a Trail");
        return NULL;
    }
    return do_unify_and_wake(t1, t2, (TrailObject *)trail_obj, 1);
}

/*
 * deref(term) -> term
 */
static PyObject *
py_deref(PyObject *Py_UNUSED(module), PyObject *arg)
{
    PyObject *result = var_deref(arg);
    Py_INCREF(result);
    return result;
}

/* Forward declarations — defined later, used by do_walk's term-instance arm
 * (A01-F008). */
static int c_is_term_instance(PyObject *obj);
static PyObject *py_term_field_names(PyObject *module, PyObject *obj);

/*
 * walk(term) -> term  — deep substitution
 */
static PyObject *
do_walk(PyObject *term, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "walk: term nesting too deep");
        return NULL;
    }
    term = var_deref(term);
    if (Var_Check(term)) {
        Py_INCREF(term);
        return term;
    }
    if (PyTuple_Check(term)) {
        Py_ssize_t n = PyTuple_GET_SIZE(term);
        PyObject *result = PyTuple_New(n);
        if (!result) return NULL;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *elem = do_walk(PyTuple_GET_ITEM(term, i), depth + 1);
            if (!elem) { Py_DECREF(result); return NULL; }
            PyTuple_SET_ITEM(result, i, elem);
        }
        return result;
    }
    if (PyList_Check(term)) {
        Py_ssize_t n = PyList_GET_SIZE(term);
        PyObject *result = PyList_New(n);
        if (!result) return NULL;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *elem = do_walk(PyList_GET_ITEM(term, i), depth + 1);
            if (!elem) { Py_DECREF(result); return NULL; }
            PyList_SET_ITEM(result, i, elem);
        }
        return result;
    }
    /* A04-F005: plain dict / set — deep-substitute so walk() stays consistent
     * with _deref_walk (both must cover the same container types). */
    if (PyDict_Check(term)) {
        PyObject *result = PyDict_New();
        if (!result) return NULL;
        PyObject *k, *v;
        Py_ssize_t pos = 0;
        while (PyDict_Next(term, &pos, &k, &v)) {
            PyObject *wk = do_walk(k, depth + 1);
            if (!wk) { Py_DECREF(result); return NULL; }
            PyObject *wv = do_walk(v, depth + 1);
            if (!wv) { Py_DECREF(wk); Py_DECREF(result); return NULL; }
            int rc = PyDict_SetItem(result, wk, wv);
            Py_DECREF(wk); Py_DECREF(wv);
            if (rc < 0) { Py_DECREF(result); return NULL; }
        }
        return result;
    }
    if (PyAnySet_Check(term)) {
        PyObject *walked = PyList_New(0);
        if (!walked) return NULL;
        PyObject *iter = PyObject_GetIter(term);
        if (!iter) { Py_DECREF(walked); return NULL; }
        PyObject *item;
        while ((item = PyIter_Next(iter))) {
            PyObject *we = do_walk(item, depth + 1);
            Py_DECREF(item);
            if (!we) { Py_DECREF(iter); Py_DECREF(walked); return NULL; }
            int rc = PyList_Append(walked, we);
            Py_DECREF(we);
            if (rc < 0) { Py_DECREF(iter); Py_DECREF(walked); return NULL; }
        }
        Py_DECREF(iter);
        if (PyErr_Occurred()) { Py_DECREF(walked); return NULL; }
        PyObject *result = PyFrozenSet_Check(term)
            ? PyFrozenSet_New(walked) : PySet_New(walked);
        Py_DECREF(walked);
        return result;
    }
    /* __walk__ protocol: delegate to Python method if present.
     * Compound, KWTerm, the Seg types and DictTerm all supply __walk__
     * (A01-F008). */
    {
        PyObject *hook = PyObject_GetAttrString(term, "__walk__");
        if (hook) {
            PyObject *result = PyObject_CallNoArgs(hook);
            Py_DECREF(hook);
            return result;  /* NULL propagates error */
        }
        PyErr_Clear();
    }
    /* Term instance (a @dataclass instance) — A01-F008: rebuild with
     * walked fields so walk() deep-substitutes term-instance children, keeping
     * walk consistent with _deref_walk (the tabling/findall snapshot walker).
     * Without this, a term instance nested inside a Compound would not be
     * frozen and would decay after backtracking. */
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) {
            /* c_term_field_names used to answer for a PredicateMeta
             * INSTANCE; W4a made that shape impossible and turned it into
             * an unconditional NULL-without-exception stub, so every call
             * here fell straight through to this @dataclass route on every
             * term. Retired in W4b, 2026-09-23 -- call it directly. */
            PyObject *fields = py_term_field_names(NULL, term);
            if (!fields) return NULL;
            Py_ssize_t n = PyTuple_GET_SIZE(fields);

            /* The Phase-0 fast-path gate that used to precede this (calling
             * a "_clausal_new" positional classmethod when PredicateMeta
             * had attached one) was retired alongside the above: that
             * classmethod and its minter are gone since W4a, so the gate
             * always fell through to the kwargs reconstruction below on
             * every call -- see solve.py's _deref_walk_py.
             */

            PyObject *kwargs = PyDict_New();
            if (!kwargs) { Py_DECREF(fields); return NULL; }
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *fname = PyTuple_GET_ITEM(fields, i);
                PyObject *val = PyObject_GetAttr(term, fname);
                if (!val) { Py_DECREF(fields); Py_DECREF(kwargs); return NULL; }
                PyObject *walked = do_walk(val, depth + 1);
                Py_DECREF(val);
                if (!walked) { Py_DECREF(fields); Py_DECREF(kwargs); return NULL; }
                if (PyDict_SetItem(kwargs, fname, walked) < 0) {
                    Py_DECREF(walked); Py_DECREF(fields); Py_DECREF(kwargs);
                    return NULL;
                }
                Py_DECREF(walked);
            }
            Py_DECREF(fields);
            PyObject *cls = (PyObject *)Py_TYPE(term);
            PyObject *empty = PyTuple_New(0);
            if (!empty) { Py_DECREF(kwargs); return NULL; }
            PyObject *result = PyObject_Call(cls, empty, kwargs);
            Py_DECREF(empty);
            Py_DECREF(kwargs);
            return result;
        }
    }
    Py_INCREF(term);
    return term;
}

static PyObject *
py_walk(PyObject *Py_UNUSED(module), PyObject *arg)
{
    return do_walk(arg, 0);
}

/*
 * is_var(term) -> bool
 */
static PyObject *
py_is_var(PyObject *Py_UNUSED(module), PyObject *arg)
{
    PyObject *root = var_deref(arg);
    return PyBool_FromLong(Var_Check(root));
}

/*
 * occurs_check(var, term) -> bool
 */
static PyObject *
py_occurs_check(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *var_obj, *term;
    if (!PyArg_ParseTuple(args, "OO", &var_obj, &term))
        return NULL;
    PyObject *root = var_deref(var_obj);
    if (!Var_Check(root))
        Py_RETURN_FALSE;
    int r = do_occurs_check(Var_CAST(root), term, 0);
    if (r < 0) return NULL;
    return PyBool_FromLong(r);
}


/* ================================================================
 * Attributed variable API
 * ================================================================ */

/*
 * put_attr(var, key, value, trail)
 *
 * Set attribute `key` on AttVar `var` to `value`.  The previous value
 * (or absence) is recorded on `trail` and restored on backtrack.
 *
 * Mirrors SWI-Prolog's put_attr/3 and SICStus's put_atts/2.
 * Attribute mutations are trailed via TRAIL_ATTR entries, analogous to
 * Scryer's TrailedAttrVarListLink trail entries.
 */
static PyObject *
py_put_attr(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *var_obj, *key, *value, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOO", &var_obj, &key, &value, &trail_obj))
        return NULL;

    PyObject *root = var_deref(var_obj);
    if (!AttVar_Check(root)) {
        PyErr_SetString(PyExc_TypeError,
                        "put_attr(): first argument must dereference to an unbound AttVar");
        return NULL;
    }
    if (!PyObject_TypeCheck(trail_obj, &TrailType)) {
        PyErr_SetString(PyExc_TypeError,
                        "put_attr(): fourth argument must be a Trail");
        return NULL;
    }

    AttVarObject *av    = AttVar_CAST(root);
    TrailObject  *trail = (TrailObject *)trail_obj;

    /* Lazily create the attrs dict */
    if (!av->attrs) {
        av->attrs = PyDict_New();
        if (!av->attrs) return NULL;
    }

    /* Get current value (borrowed ref, NULL if absent) */
    PyObject *old_attr = PyDict_GetItemWithError(av->attrs, key);
    if (!old_attr && PyErr_Occurred()) return NULL;

    if (trail_push_attr(trail, av, key, old_attr) < 0)
        return NULL;

    if (PyDict_SetItem(av->attrs, key, value) < 0)
        return NULL;

    Py_RETURN_NONE;
}

/*
 * get_attr(var, key) -> value or None
 *
 * Return the attribute stored under `key` on AttVar `var`, or None
 * if the variable has no such attribute (or is not an AttVar).
 *
 * Mirrors SWI-Prolog's get_attr/3 (without unification semantics).
 */
static PyObject *
py_get_attr(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *var_obj, *key;
    if (!PyArg_ParseTuple(args, "OO", &var_obj, &key))
        return NULL;

    PyObject *root = var_deref(var_obj);
    if (!AttVar_Check(root))
        Py_RETURN_NONE;

    AttVarObject *av = AttVar_CAST(root);
    if (!av->attrs)
        Py_RETURN_NONE;

    PyObject *val = PyDict_GetItemWithError(av->attrs, key);
    if (!val) {
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;
    }
    Py_INCREF(val);
    return val;
}

/*
 * del_attr(var, key, trail)
 *
 * Delete attribute `key` from AttVar `var`.  The deletion is recorded
 * on `trail` and reversed on backtrack.  A no-op if the key is absent.
 */
static PyObject *
py_del_attr(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *var_obj, *key, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &var_obj, &key, &trail_obj))
        return NULL;

    PyObject *root = var_deref(var_obj);
    if (!AttVar_Check(root)) {
        PyErr_SetString(PyExc_TypeError,
                        "del_attr(): first argument must dereference to an unbound AttVar");
        return NULL;
    }
    if (!PyObject_TypeCheck(trail_obj, &TrailType)) {
        PyErr_SetString(PyExc_TypeError,
                        "del_attr(): third argument must be a Trail");
        return NULL;
    }

    AttVarObject *av    = AttVar_CAST(root);
    TrailObject  *trail = (TrailObject *)trail_obj;

    if (!av->attrs)
        Py_RETURN_NONE;   /* nothing to delete */

    PyObject *old_attr = PyDict_GetItemWithError(av->attrs, key);
    if (!old_attr) {
        if (PyErr_Occurred()) return NULL;
        Py_RETURN_NONE;   /* key absent */
    }

    if (trail_push_attr(trail, av, key, old_attr) < 0)
        return NULL;

    if (PyDict_DelItem(av->attrs, key) < 0)
        return NULL;

    Py_RETURN_NONE;
}

/*
 * register_attr_hook(key, callable)
 *
 * Register a hook to be called when an AttVar carrying attribute `key`
 * is unified with a value.
 *
 * Hook signature::
 *
 *     def hook(attr_value, bound_to, trail) -> bool
 *
 * `attr_value` — the attribute stored under `key` on the AttVar.
 * `bound_to`   — the value (or variable) the AttVar was unified with,
 *                after following any binding chains.
 * `trail`      — the Trail used in the unify() call; the hook may call
 *                unify() or put_attr() with this trail to propagate
 *                constraints.
 *
 * Returning a falsy value causes the entire unification to fail and
 * roll back all bindings made since the enclosing unify() call started.
 *
 * Pass callable=None to unregister.
 *
 * This is the Python equivalent of Scryer's attr_unify_hook/2 (per
 * module key) or SICStus's verify_attributes/3.
 */
static PyObject *
py_register_attr_hook(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *key, *callable;
    if (!PyArg_ParseTuple(args, "OO", &key, &callable))
        return NULL;

    FtCriticalSection cs;
    FT_CS_BEGIN(&cs, g_attr_hooks);
    if (callable == Py_None) {
        if (PyDict_DelItem(g_attr_hooks, key) < 0) {
            if (PyErr_ExceptionMatches(PyExc_KeyError))
                PyErr_Clear();   /* unregistering a non-existent key is fine */
            else {
                FT_CS_END(&cs);
                return NULL;
            }
        }
    } else {
        if (!PyCallable_Check(callable)) {
            FT_CS_END(&cs);
            PyErr_SetString(PyExc_TypeError,
                            "register_attr_hook(): callable must be callable or None");
            return NULL;
        }
        if (PyDict_SetItem(g_attr_hooks, key, callable) < 0) {
            FT_CS_END(&cs);
            return NULL;
        }
    }
    FT_CS_END(&cs);
    Py_RETURN_NONE;
}


/* ================================================================
 * Predicate helpers — term inspection moved from Python to C
 * ================================================================ */

/* (The cached ``PredicateMeta`` slot and its ``_register_predicate_meta``
 * entry point were removed at W4b-3 slice 8, 2026-09-26: the class was
 * deleted at slice 7, and every arm that tested the slot answered "not a
 * class" for every object.) */

/* Cached interned strings for fast attr lookup -- set in PyInit__variables
 * (init_term_inspection_cache), before anything can inspect a term. */
static PyObject *str_dataclass_fields = NULL;  /* "__dataclass_fields__" */
static PyObject *str_name = NULL;              /* "name" */
static PyObject *str_functor = NULL;           /* "functor" */
static PyObject *str_args = NULL;              /* "args" */

/* Cached reference to dataclasses.fields() for dataclass field introspection */
static PyObject *dc_fields_func = NULL;

/* Cached references for Compound and KWTerm types */
static PyObject *Compound_type = NULL;
static PyObject *KWTerm_type = NULL;

/*
 * init_term_inspection_cache() — the interned attribute names and the
 * ``dataclasses.fields`` reference the term-inspection helpers read.  Called
 * ONCE from PyInit__variables.  The readers:
 *
 *   str_dataclass_fields  c_is_term_instance
 *   dc_fields_func        py_term_field_names
 *   str_name              py_term_field_names
 *   str_functor           the Compound arms of c_is_ground, c_copy_term and
 *                         c_collect_vars; c_copy_term's KWTerm arm;
 *                         py_functor_name (Compound and KWTerm)
 *   str_args              the Compound arms of c_is_ground, c_copy_term and
 *                         c_collect_vars; py_arity, py_nth_arg, py_args_list
 *
 * This used to be the second job of ``_register_predicate_meta(cls)``, which
 * predicate.py called at import time (Fix #5).  Anything that inspected a
 * term before that call -- including another extension through the
 * ``_C_API`` capsule's ``is_term_instance`` -- read a NULL interned name and
 * crashed; skipping the call segfaulted the first ``head_key`` on a load
 * (measured, W4b-3 slice 7).  Module init removes the ordering dependency.
 * Returns 0, or -1 with an exception set.
 */
static int
init_term_inspection_cache(void)
{
    str_dataclass_fields = PyUnicode_InternFromString("__dataclass_fields__");
    if (!str_dataclass_fields) return -1;
    str_name = PyUnicode_InternFromString("name");
    if (!str_name) return -1;
    str_functor = PyUnicode_InternFromString("functor");
    if (!str_functor) return -1;
    str_args = PyUnicode_InternFromString("args");
    if (!str_args) return -1;
    PyObject *mod = PyImport_ImportModule("dataclasses");
    if (!mod) return -1;
    dc_fields_func = PyObject_GetAttrString(mod, "fields");
    Py_DECREF(mod);
    if (!dc_fields_func) return -1;
    return 0;
}

/*
 * _register_term_types(compound_cls, kwterm_cls) — called at import time
 */
static PyObject *
py_register_term_types(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *comp, *kw;
    if (!PyArg_ParseTuple(args, "OO", &comp, &kw))
        return NULL;
    Py_XDECREF(Compound_type);
    Py_XDECREF(KWTerm_type);
    Py_INCREF(comp);
    Py_INCREF(kw);
    Compound_type = comp;
    KWTerm_type = kw;
    Py_RETURN_NONE;
}

/* Internal: check if obj is a term instance (a @dataclass instance).
 * Returns 1 (yes), 0 (no), or -1 (error with exception set). */
static int
c_is_term_instance(PyObject *obj)
{
    /* (Fix #7's "PredicateMeta not registered yet -> 0" guard went with the
     * instance arm in W4a: this no longer consults the registration at all,
     * and answering 0 for a @dataclass instance because an unrelated class
     * had not registered would be the misclassification that guard existed
     * to avoid -- and a divergence from the Python twin.) */
    /* Exclude types/classes themselves */
    if (PyType_Check(obj)) return 0;
    /* W4a (2026-09-22): the PredicateMeta-INSTANCE arm that stood here is
     * gone with the instance path -- a predicate class builds a CELL, and a
     * cell is a tuple, not a term instance.  A @dataclass instance is the
     * one shape left, and its probe is below.  (The CLASS arms elsewhere in
     * this file and the registration went at W4b-3 slice 8.) */
    /* Fix #2: C-level fast-reject for dataclass check.
     * dataclasses.is_dataclass() internally checks for __dataclass_fields__.
     * We do the same attribute probe at C level — no Python call needed. */
    if (PyObject_HasAttr((PyObject *)Py_TYPE(obj), str_dataclass_fields))
        return 1;
    return 0;
}

/*
 * is_term_instance(obj) -> bool
 */
static PyObject *
py_is_term_instance(PyObject *Py_UNUSED(module), PyObject *obj)
{
    int r = c_is_term_instance(obj);
    if (r < 0) return NULL;
    return PyBool_FromLong(r);
}

/*
 * term_field_names(obj) -> tuple of str
 */
static PyObject *
py_term_field_names(PyObject *Py_UNUSED(module), PyObject *obj)
{
    /* W4a: the PredicateMeta-INSTANCE arm is gone (see c_is_term_instance);
     * a @dataclass instance is the only term instance there is. */
    /* @dataclass route — dc_fields_func is set in PyInit__variables
     * (init_term_inspection_cache), which fails the import if it cannot. */
    {
        PyObject *dc_fields = PyObject_CallOneArg(dc_fields_func, obj);
        if (!dc_fields) return NULL;
        /* Fix #4: verify dc_fields is a tuple */
        if (!PyTuple_Check(dc_fields)) {
            Py_DECREF(dc_fields);
            PyErr_SetString(PyExc_TypeError,
                            "dataclasses.fields() did not return a tuple");
            return NULL;
        }
        Py_ssize_t n = PyTuple_GET_SIZE(dc_fields);
        PyObject *result = PyTuple_New(n);
        if (!result) { Py_DECREF(dc_fields); return NULL; }
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *fname = PyObject_GetAttr(
                PyTuple_GET_ITEM(dc_fields, i), str_name);
            if (!fname) { Py_DECREF(dc_fields); Py_DECREF(result); return NULL; }
            PyTuple_SET_ITEM(result, i, fname);
        }
        Py_DECREF(dc_fields);
        return result;
    }
}

/*
 * _is_ground(term) -> bool — recursive groundness check
 */
static int
c_is_ground(PyObject *term, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "_is_ground: term nesting too deep");
        return -1;
    }
    term = var_deref(term);
    if (Var_Check(term))
        return 0;
    /* Primitives */
    if (term == Py_None || PyBool_Check(term) || PyLong_Check(term) ||
        PyFloat_Check(term) || PyUnicode_Check(term) || PyBytes_Check(term))
        return 1;
    /* Lists */
    if (PyList_Check(term)) {
        Py_ssize_t n = PyList_GET_SIZE(term);
        for (Py_ssize_t i = 0; i < n; i++) {
            int r = c_is_ground(PyList_GET_ITEM(term, i), depth + 1);
            if (r <= 0) return r;
        }
        return 1;
    }
    /* Cell — a plain tuple (see the branch in ``c_copy_term``).  Without this
     * a cell fell through the "unknown shape -> ground" tail, so
     * ``ground(pt(1, Y))`` answered TRUE and ``_findall_copy_row``
     * (``compiler/globals_env.py``) skipped the ISO per-solution copy for a
     * cell row, sharing the caller's Var (A03-F006 for cell rows).
     *
     * PyTuple_CheckEXACT, the same check its copy/collect siblings use.  The
     * first cut of this branch used the inclusive PyTuple_Check, mirroring
     * ``_is_ground_py``'s then-``isinstance`` on the grounds that this
     * predicate only READS.  Task 2C fix round 1 (controller ruling) reverses
     * that: a tuple SUBCLASS is not a cell (``is_cell`` excludes one by
     * design), and reading through one HERE while ``c_copy_term`` and
     * ``c_collect_vars`` treat it as opaque made the trio incoherent -- a
     * namedtuple holding a free Var was NON-ground yet had no enumerable
     * variables and could not be copied, which also changed pre-flip
     * behaviour for a non-cell shape.  All three exact keeps the answers
     * consistent; ``_is_ground_py``'s branch is ``type(term) is tuple`` to
     * match. */
    if (PyTuple_CheckExact(term)) {
        Py_ssize_t n = PyTuple_GET_SIZE(term);
        for (Py_ssize_t i = 0; i < n; i++) {
            int r = c_is_ground(PyTuple_GET_ITEM(term, i), depth + 1);
            if (r <= 0) return r;
        }
        return 1;
    }
    /* Compound */
    if (Compound_type) {
        int r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return -1;  /* Fix #3 */
        if (r) {
            PyObject *functor = PyObject_GetAttr(term, str_functor);
            if (!functor) return -1;
            /* A01-F003: deref a functor Var before the str check — a functor
             * bound to a str is ground; an unbound functor Var is not. */
            int is_str = PyUnicode_Check(var_deref(functor));
            Py_DECREF(functor);
            if (!is_str) return 0;
            PyObject *args = PyObject_GetAttr(term, str_args);
            if (!args) return -1;
            /* Fix #4: guard against non-tuple args */
            if (!PyTuple_Check(args)) {
                Py_DECREF(args);
                PyErr_SetString(PyExc_TypeError, "Compound.args is not a tuple");
                return -1;
            }
            Py_ssize_t n = PyTuple_GET_SIZE(args);
            for (Py_ssize_t i = 0; i < n; i++) {
                int gr = c_is_ground(PyTuple_GET_ITEM(args, i), depth + 1);
                if (gr <= 0) { Py_DECREF(args); return gr; }
            }
            Py_DECREF(args);
            return 1;
        }
    }
    /* KWTerm */
    if (KWTerm_type) {
        int r = PyObject_IsInstance(term, KWTerm_type);
        if (r < 0) return -1;  /* Fix #3 */
        if (r) {
            PyObject *values = PyObject_CallMethod(term, "values", NULL);
            if (!values) return -1;
            PyObject *iter = PyObject_GetIter(values);
            Py_DECREF(values);
            if (!iter) return -1;
            PyObject *item;
            while ((item = PyIter_Next(iter))) {
                int gr = c_is_ground(item, depth + 1);
                Py_DECREF(item);
                if (gr <= 0) { Py_DECREF(iter); return gr; }
            }
            Py_DECREF(iter);
            if (PyErr_Occurred()) return -1;
            return 1;
        }
    }
    /* Term instances (PredicateMeta or @dataclass) */
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return -1;  /* Fix #3 */
        if (ti) {
            /* c_term_field_names used to answer for a PredicateMeta
             * INSTANCE; W4a made that shape impossible and turned it into
             * an unconditional NULL-without-exception stub, so every call
             * here fell straight through to this @dataclass route on every
             * term. Retired in W4b, 2026-09-23 -- call it directly. */
            PyObject *fields = py_term_field_names(NULL, term);
            if (!fields) return -1;
            Py_ssize_t n = PyTuple_GET_SIZE(fields);
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *val = PyObject_GetAttr(term, PyTuple_GET_ITEM(fields, i));
                if (!val) { Py_DECREF(fields); return -1; }
                int gr = c_is_ground(val, depth + 1);
                Py_DECREF(val);
                if (gr <= 0) { Py_DECREF(fields); return gr; }
            }
            Py_DECREF(fields);
            return 1;
        }
    }
    return 1;
}

static PyObject *
py_is_ground(PyObject *Py_UNUSED(module), PyObject *arg)
{
    int r = c_is_ground(arg, 0);
    if (r < 0) return NULL;
    return PyBool_FromLong(r);
}

/*
 * _functor_name(term) -> str | None
 */
static PyObject *
py_functor_name(PyObject *Py_UNUSED(module), PyObject *term)
{
    int r;
    /* Compound */
    if (Compound_type) {
        r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return NULL;
        if (r) {
            PyObject *functor = PyObject_GetAttr(term, str_functor);
            if (!functor) return NULL;
            if (PyUnicode_Check(functor)) return functor;
            Py_DECREF(functor);
            Py_RETURN_NONE;
        }
    }
    /* KWTerm */
    if (KWTerm_type) {
        r = PyObject_IsInstance(term, KWTerm_type);
        if (r < 0) return NULL;
        if (r) return PyObject_GetAttr(term, str_functor);
    }
    /* PredicateMeta instance */
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) return PyObject_GetAttrString((PyObject *)Py_TYPE(term), "__name__");
    }
    /* List — ISO cons-cell semantics (user decision 2026-06-13). */
    if (PyList_Check(term)) {
        if (PyList_GET_SIZE(term) == 0)
            return PyUnicode_FromString("[]");
        else
            return PyUnicode_FromString(".");
    }
    /* Str — cons-cell decomposition, the SAME reading as the list above.
     * THE FLIP (atoms-as-cells/strings §6.4): a str is a STRING, i.e. the
     * list of its char atoms, so it answers what that list answers.  P3-1
     * §1b/R2 had retired strs from cons-cell decomposition (a str was
     * always an atom, hence its own functor name with arity 0); Task 12b
     * retired that reading here and in the Python twin _functor_name_py
     * together, so calling this accessor directly agrees with the funnel
     * wrapper in builtins/_helpers.py.  The empty string keeps the ISO
     * nil-atom spelling "[]", as the empty list does. */
    if (is_chars_carrier(term)) {   /* STAGE 2: the carrier is the STRING -- cons-cell reading */
        if (PyUnicode_GET_LENGTH(unwrap_chars(term)) == 0)
            return PyUnicode_FromString("[]");
        return PyUnicode_FromString(".");
    }
    if (PyUnicode_Check(term)) {    /* STAGE 2: a str IS the atom -- its own functor name */
        Py_INCREF(term);
        return term;
    }
    /* Bytes — codes-model cons-cell, untouched by the str~list retirement
     * (§1b: "the adjacent bytes<->list block is KEPT — codes model
     * untouched"). */
    if (PyBytes_Check(term)) {
        if (PyBytes_GET_SIZE(term) == 0)
            return PyUnicode_FromString("[]");
        else
            return PyUnicode_FromString(".");
    }
    /* Primitives — A09-F027: an atomic constant IS its own functor name
       (ISO: functor(3, N, A) → N=3, A=0), so it roundtrips. Returning
       repr(term) ("3") broke functor(T, "3", 0) → T="3" != 3. */
    if (term == Py_None || PyBool_Check(term) || PyLong_Check(term) ||
        PyFloat_Check(term)) {
        Py_INCREF(term);
        return term;
    }
    /* Zero-arity PredicateMeta class (atom) */
    /* STAGE 2 (spec §4): no class is a term -- the zero-field-class arm is retired with the cell. */
    Py_RETURN_NONE;
}

/*
 * _arity(term) -> int | None
 */
static PyObject *
py_arity(PyObject *Py_UNUSED(module), PyObject *term)
{
    int r;
    /* Compound */
    if (Compound_type) {
        r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return NULL;
        if (r) {
            PyObject *args = PyObject_GetAttr(term, str_args);
            if (!args) return NULL;
            if (!PyTuple_Check(args)) {
                Py_ssize_t n = PyObject_Length(args);
                Py_DECREF(args);
                if (n < 0) return NULL;
                return PyLong_FromSsize_t(n);
            }
            Py_ssize_t n = PyTuple_GET_SIZE(args);
            Py_DECREF(args);
            return PyLong_FromSsize_t(n);
        }
    }
    /* KWTerm */
    if (KWTerm_type) {
        r = PyObject_IsInstance(term, KWTerm_type);
        if (r < 0) return NULL;
        if (r) {
            Py_ssize_t n = PyObject_Length(term);
            if (n < 0) return NULL;
            return PyLong_FromSsize_t(n);
        }
    }
    /* Term instance (PredicateMeta or @dataclass) */
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) {
            /* c_term_field_names used to answer for a PredicateMeta
             * INSTANCE; W4a made that shape impossible and turned it into
             * an unconditional NULL-without-exception stub, so every call
             * here fell straight through to this @dataclass route on every
             * term. Retired in W4b, 2026-09-23 -- call it directly. */
            PyObject *fields = py_term_field_names(NULL, term);
            if (!fields) return NULL;
            Py_ssize_t n = PyTuple_GET_SIZE(fields);
            Py_DECREF(fields);
            return PyLong_FromSsize_t(n);
        }
    }
    /* List — ISO cons-cell (user decision 2026-06-13). */
    if (PyList_Check(term)) {
        return PyLong_FromLong(PyList_GET_SIZE(term) == 0 ? 0 : 2);
    }
    /* Str — cons-cell decomposition, the SAME reading as the list above.
     * THE FLIP (atoms-as-cells/strings §6.4): a str is a STRING, i.e. the
     * list of its char atoms, so a non-empty one has arity 2 and the empty
     * one arity 0.  P3-1 §1b/R2 had retired strs from cons-cell
     * decomposition (a str was always atomic, empty or not); Task 12b
     * retired that reading here and in the Python twin _arity_py together,
     * so calling this accessor directly agrees with the funnel wrapper in
     * builtins/_helpers.py. */
    if (is_chars_carrier(term)) {   /* STAGE 2: the carrier is the STRING -- cons-cell reading */
        return PyLong_FromLong(PyUnicode_GET_LENGTH(unwrap_chars(term)) == 0 ? 0 : 2);
    }
    if (PyUnicode_Check(term)) {    /* STAGE 2: a str IS the atom, arity 0 */
        return PyLong_FromLong(0);
    }
    /* Bytes — codes-model cons-cell. */
    if (PyBytes_Check(term)) {
        return PyLong_FromLong(PyBytes_GET_SIZE(term) == 0 ? 0 : 2);
    }
    /* Primitives */
    if (term == Py_None || PyBool_Check(term) || PyLong_Check(term) ||
        PyFloat_Check(term)) {
        return PyLong_FromLong(0);
    }
    /* Zero-arity atom */
    /* STAGE 2 (spec §4): no class is a term -- the zero-field-class arm is retired with the cell. */
    Py_RETURN_NONE;
}

/*
 * _nth_arg(term, n) -> value  (1-based index)
 */
/* Fix #8: helper to raise IndexError with term repr */
static PyObject *
raise_arg_index_error(Py_ssize_t n, PyObject *term)
{
    PyObject *repr = PyObject_Repr(term);
    if (repr) {
        PyErr_Format(PyExc_IndexError,
                     "arg index %zd out of range for %U", n, repr);
        Py_DECREF(repr);
    } else {
        PyErr_Clear();
        PyErr_Format(PyExc_IndexError, "arg index %zd out of range", n);
    }
    return NULL;
}

static PyObject *
py_nth_arg(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *term;
    Py_ssize_t n;
    int r;
    if (!PyArg_ParseTuple(args, "On", &term, &n))
        return NULL;
    /* Compound */
    if (Compound_type) {
        r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return NULL;
        if (r) {
            PyObject *cargs = PyObject_GetAttr(term, str_args);
            if (!cargs) return NULL;
            /* Fix #4: handle non-tuple args gracefully */
            if (!PyTuple_Check(cargs)) {
                Py_ssize_t len = PyObject_Length(cargs);
                if (len < 0) { Py_DECREF(cargs); return NULL; }
                if (n < 1 || n > len) {
                    Py_DECREF(cargs);
                    return raise_arg_index_error(n, term);
                }
                PyObject *result = PySequence_GetItem(cargs, n - 1);
                Py_DECREF(cargs);
                return result;
            }
            Py_ssize_t len = PyTuple_GET_SIZE(cargs);
            if (n < 1 || n > len) {
                Py_DECREF(cargs);
                return raise_arg_index_error(n, term);
            }
            PyObject *result = PyTuple_GET_ITEM(cargs, n - 1);
            Py_INCREF(result);
            Py_DECREF(cargs);
            return result;
        }
    }
    /* KWTerm */
    if (KWTerm_type) {
        r = PyObject_IsInstance(term, KWTerm_type);
        if (r < 0) return NULL;
        if (r) {
            PyObject *values = PyObject_CallMethod(term, "values", NULL);
            if (!values) return NULL;
            PyObject *vlist = PySequence_List(values);
            Py_DECREF(values);
            if (!vlist) return NULL;
            Py_ssize_t len = PyList_GET_SIZE(vlist);
            if (n < 1 || n > len) {
                Py_DECREF(vlist);
                return raise_arg_index_error(n, term);
            }
            PyObject *result = PyList_GET_ITEM(vlist, n - 1);
            Py_INCREF(result);
            Py_DECREF(vlist);
            return result;
        }
    }
    /* Term instance (PredicateMeta or @dataclass) */
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) {
            /* c_term_field_names used to answer for a PredicateMeta
             * INSTANCE; W4a made that shape impossible and turned it into
             * an unconditional NULL-without-exception stub, so every call
             * here fell straight through to this @dataclass route on every
             * term. Retired in W4b, 2026-09-23 -- call it directly. */
            PyObject *fields = py_term_field_names(NULL, term);
            if (!fields) return NULL;
            Py_ssize_t len = PyTuple_GET_SIZE(fields);
            if (n < 1 || n > len) {
                Py_DECREF(fields);
                return raise_arg_index_error(n, term);
            }
            PyObject *result = PyObject_GetAttr(term, PyTuple_GET_ITEM(fields, n - 1));
            Py_DECREF(fields);
            return result;
        }
    }
    /* List — ISO cons-cell (user decision 2026-06-13): n=1 → head,
     * n=2 → tail (slice). */
    if (PyList_Check(term)) {
        Py_ssize_t len = PyList_GET_SIZE(term);
        if (len == 0) {
            return raise_arg_index_error(n, term);
        }
        if (n == 1) {
            PyObject *result = PyList_GET_ITEM(term, 0);
            Py_INCREF(result);
            return result;
        }
        if (n == 2) {
            return PyList_GetSlice(term, 1, len);
        }
        return raise_arg_index_error(n, term);
    }
    /* Str: RETIRED cons-cell decomposition (P3-1 §1b/R2) — a str was
     * always atomic (arity 0), so every index was out of range: it falls
     * through to the bytes check (never matches) and the final
     * ``raise_arg_index_error`` below.
     * SUPERSEDED by THE FLIP (atoms-as-cells/strings §6.4): a str is a
     * STRING and answers what its char list answers.  The Python
     * wrapper in builtins/_helpers.py takes every str before this
     * accessor is reached, so this arm is unreachable for a str and is
     * kept only so the C accessor and its Python fallback
     * (_functor_name_py and friends) stay twins. */
    /* Bytes — codes-model cons-cell: n=1 → int head (b[0] is an int, no
     * fixed point), n=2 → bytes tail (type preserved). */
    if (PyBytes_Check(term)) {
        Py_ssize_t len = PyBytes_GET_SIZE(term);
        if (len == 0) {
            return raise_arg_index_error(n, term);
        }
        if (n == 1) {
            const unsigned char *data =
                (const unsigned char *)PyBytes_AS_STRING(term);
            return PyLong_FromLong((long)data[0]);
        }
        if (n == 2) {
            const char *data = PyBytes_AS_STRING(term);
            return PyBytes_FromStringAndSize(data + 1, len - 1);
        }
        return raise_arg_index_error(n, term);
    }
    return raise_arg_index_error(n, term);
}

/*
 * _args_list(term) -> list
 */
static PyObject *
py_args_list(PyObject *Py_UNUSED(module), PyObject *term)
{
    int r;
    /* Compound */
    if (Compound_type) {
        r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return NULL;
        if (r) {
            PyObject *args = PyObject_GetAttr(term, str_args);
            if (!args) return NULL;
            PyObject *result = PySequence_List(args);
            Py_DECREF(args);
            return result;
        }
    }
    /* KWTerm */
    if (KWTerm_type) {
        r = PyObject_IsInstance(term, KWTerm_type);
        if (r < 0) return NULL;
        if (r) {
            PyObject *values = PyObject_CallMethod(term, "values", NULL);
            if (!values) return NULL;
            PyObject *result = PySequence_List(values);
            Py_DECREF(values);
            return result;
        }
    }
    /* Term instance (PredicateMeta or @dataclass) */
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) {
            /* c_term_field_names used to answer for a PredicateMeta
             * INSTANCE; W4a made that shape impossible and turned it into
             * an unconditional NULL-without-exception stub, so every call
             * here fell straight through to this @dataclass route on every
             * term. Retired in W4b, 2026-09-23 -- call it directly. */
            PyObject *fields = py_term_field_names(NULL, term);
            if (!fields) return NULL;
            Py_ssize_t n = PyTuple_GET_SIZE(fields);
            PyObject *result = PyList_New(n);
            if (!result) { Py_DECREF(fields); return NULL; }
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *val = PyObject_GetAttr(term, PyTuple_GET_ITEM(fields, i));
                if (!val) { Py_DECREF(fields); Py_DECREF(result); return NULL; }
                PyList_SET_ITEM(result, i, val);
            }
            Py_DECREF(fields);
            return result;
        }
    }
    /* List — ISO cons-cell (user decision 2026-06-13): non-empty
     * → [head, tail]; empty → []. */
    if (PyList_Check(term)) {
        Py_ssize_t len = PyList_GET_SIZE(term);
        if (len == 0) {
            return PyList_New(0);
        }
        PyObject *head = PyList_GET_ITEM(term, 0);
        PyObject *tail = PyList_GetSlice(term, 1, len);
        if (!tail) return NULL;
        PyObject *result = PyList_New(2);
        if (!result) { Py_DECREF(tail); return NULL; }
        Py_INCREF(head);
        PyList_SET_ITEM(result, 0, head);
        PyList_SET_ITEM(result, 1, tail);  /* steals tail's reference */
        return result;
    }
    /* Str: RETIRED cons-cell decomposition (P3-1 §1b/R2) — a str was
     * always atomic (arity 0), so it had no arguments: it falls through
     * to the bytes check (never matches) and the final "empty list"
     * default below.
     * SUPERSEDED by THE FLIP (atoms-as-cells/strings §6.4): a str is a
     * STRING and answers what its char list answers.  The Python
     * wrapper in builtins/_helpers.py takes every str before this
     * accessor is reached, so this arm is unreachable for a str and is
     * kept only so the C accessor and its Python fallback
     * (_functor_name_py and friends) stay twins. */
    /* Bytes — codes-model cons-cell: non-empty → [int_head, bytes_tail];
     * empty → []. Head is an int (no fixed point); tail preserves bytes. */
    if (PyBytes_Check(term)) {
        Py_ssize_t len = PyBytes_GET_SIZE(term);
        if (len == 0) {
            return PyList_New(0);
        }
        const unsigned char *udata =
            (const unsigned char *)PyBytes_AS_STRING(term);
        PyObject *head = PyLong_FromLong((long)udata[0]);
        if (!head) return NULL;
        PyObject *tail =
            PyBytes_FromStringAndSize((const char *)udata + 1, len - 1);
        if (!tail) { Py_DECREF(head); return NULL; }
        PyObject *result = PyList_New(2);
        if (!result) { Py_DECREF(head); Py_DECREF(tail); return NULL; }
        PyList_SET_ITEM(result, 0, head);  /* steals */
        PyList_SET_ITEM(result, 1, tail);  /* steals */
        return result;
    }
    /* Default: empty list */
    return PyList_New(0);
}

/*
 * _is_compound(term) -> bool
 */
static PyObject *
py_is_compound(PyObject *Py_UNUSED(module), PyObject *term)
{
    int r;
    if (Compound_type) {
        r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return NULL;
        if (r) Py_RETURN_TRUE;
    }
    if (KWTerm_type) {
        r = PyObject_IsInstance(term, KWTerm_type);
        if (r < 0) return NULL;
        if (r) Py_RETURN_TRUE;
    }
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}


/* ================================================================
 * _copy_term_impl — deep copy with fresh Vars
 * ================================================================ */

/*
 * c_copy_term(term, var_map, depth) -> new reference
 *
 * Recursively copies term, replacing each unbound Var with a fresh one.
 * var_map is a PyDict mapping id(original_var) -> fresh_var (as PyLong keys).
 * Sharing is preserved: two references to the same Var get the same fresh copy.
 */
static PyObject *
c_copy_term(PyObject *term, PyObject *var_map, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "_copy_term: term nesting too deep");
        return NULL;
    }
    term = var_deref(term);

    /* Unbound variable: look up or create fresh Var in var_map */
    if (Var_Check(term)) {
        PyObject *key = PyLong_FromVoidPtr(term);
        if (!key) return NULL;
        PyObject *existing = PyDict_GetItemWithError(var_map, key);
        if (existing) {
            Py_DECREF(key);
            Py_INCREF(existing);
            return existing;
        }
        if (PyErr_Occurred()) { Py_DECREF(key); return NULL; }
        /* Create fresh AttVar (Var = AttVar in Python, so all fresh vars must
         * be AttVar instances to be recognised by var_deref in other modules). */
        PyObject *fresh = PyObject_CallNoArgs((PyObject *)&AttVarType);
        if (!fresh) { Py_DECREF(key); return NULL; }
        if (PyDict_SetItem(var_map, key, fresh) < 0) {
            Py_DECREF(key); Py_DECREF(fresh); return NULL;
        }
        Py_DECREF(key);
        return fresh;  /* new ref (ref count raised by SetItem, returned here) */
    }

    /* Primitives: ground, return as-is */
    if (term == Py_None || PyBool_Check(term) || PyLong_Check(term) ||
        PyFloat_Check(term) || PyUnicode_Check(term) || PyBytes_Check(term)) {
        Py_INCREF(term);
        return term;
    }

    /* List: copy element-by-element */
    if (PyList_Check(term)) {
        Py_ssize_t n = PyList_GET_SIZE(term);
        PyObject *result = PyList_New(n);
        if (!result) return NULL;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *elem = c_copy_term(PyList_GET_ITEM(term, i), var_map, depth + 1);
            if (!elem) { Py_DECREF(result); return NULL; }
            PyList_SET_ITEM(result, i, elem);  /* steals ref */
        }
        return result;
    }

    /* Cell — a plain tuple.  P3-2 Task 2 (THE FLIP) makes ``("pt", X, Y)`` how
     * every compound DATA term is represented, so a tuple can no longer fall
     * through to the "unknown term type: return as-is" tail: that handed the
     * caller a "copy" still sharing the ORIGINAL's variables.  A
     * meta-interpreter's ``copy_term(CLAUSE, [HEAD, BODY])`` then bound the
     * PROGRAM's variables on the first resolution step and ``Solve/2``
     * enumerated forever (``clausal/examples/metainterpreters.clausal``).
     *
     * PyTuple_CheckEXACT, not PyTuple_Check, because that is what the Python
     * twin's ``type(term) is tuple`` decides (``_copy_term_py``,
     * ``builtins/inspection.py``): a namedtuple or other tuple subclass would
     * lose its type through the rebuild, and rebuilding one is not this
     * function's business.  Its siblings in ``c_collect_vars`` and
     * ``c_is_ground`` use the exact check too — a tuple subclass is opaque to
     * all three, which is what keeps their three answers coherent.
     *
     * Slot 0 needs no special case: a str functor and the TUPLE_TAG type
     * object both contain no Vars and are returned by identity, while an
     * unbound functor Var must be freshened like any other — the same
     * reasoning as the A01-F003 functor recursion in the Compound branch
     * below, but for free.
     *
     * The reuse-if-unchanged tail mirrors the twin's identity short-circuit
     * (``if all(new is old ...): return term``), so a GROUND cell — the
     * overwhelmingly common case — stays allocation-free. */
    if (PyTuple_CheckExact(term)) {
        Py_ssize_t n = PyTuple_GET_SIZE(term);
        PyObject *result = PyTuple_New(n);
        if (!result) return NULL;
        int changed = 0;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *slot = PyTuple_GET_ITEM(term, i);  /* borrowed */
            PyObject *copied = c_copy_term(slot, var_map, depth + 1);
            if (!copied) { Py_DECREF(result); return NULL; }
            if (copied != slot) changed = 1;
            PyTuple_SET_ITEM(result, i, copied);  /* steals ref */
        }
        if (!changed) {
            Py_DECREF(result);
            Py_INCREF(term);
            return term;
        }
        return result;
    }

    /* Compound: copy args tuple, construct new Compound(functor, new_args) */
    if (Compound_type) {
        int r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return NULL;
        if (r) {
            PyObject *functor = PyObject_GetAttr(term, str_functor);
            if (!functor) return NULL;
            PyObject *args = PyObject_GetAttr(term, str_args);
            if (!args) { Py_DECREF(functor); return NULL; }
            if (!PyTuple_Check(args)) {
                Py_DECREF(functor); Py_DECREF(args);
                PyErr_SetString(PyExc_TypeError, "Compound.args is not a tuple");
                return NULL;
            }
            Py_ssize_t n = PyTuple_GET_SIZE(args);
            PyObject *new_args = PyTuple_New(n);
            if (!new_args) { Py_DECREF(functor); Py_DECREF(args); return NULL; }
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *copied = c_copy_term(PyTuple_GET_ITEM(args, i), var_map, depth + 1);
                if (!copied) {
                    Py_DECREF(functor); Py_DECREF(args); Py_DECREF(new_args);
                    return NULL;
                }
                PyTuple_SET_ITEM(new_args, i, copied);  /* steals ref */
            }
            Py_DECREF(args);
            /* A01-F003: freshen the functor too — an unbound functor Var must
             * be remapped like any arg Var; a str functor derefs to itself and
             * is returned as-is by c_copy_term. */
            PyObject *new_functor = c_copy_term(functor, var_map, depth + 1);
            Py_DECREF(functor);
            if (!new_functor) { Py_DECREF(new_args); return NULL; }
            PyObject *result = PyObject_CallFunctionObjArgs(Compound_type, new_functor, new_args, NULL);
            Py_DECREF(new_functor);
            Py_DECREF(new_args);
            return result;
        }
    }

    /* KWTerm: copy each value, construct new KWTerm(functor, **{k: copied_v, ...}) */
    if (KWTerm_type) {
        int r = PyObject_IsInstance(term, KWTerm_type);
        if (r < 0) return NULL;
        if (r) {
            /* Issue 1 fix: get functor for correct reconstruction */
            PyObject *functor = PyObject_GetAttr(term, str_functor);
            if (!functor) return NULL;
            /* Issue 2 fix: use items() call instead of PyMapping_Items */
            PyObject *items_view = PyObject_CallMethod(term, "items", NULL);
            if (!items_view) { Py_DECREF(functor); return NULL; }
            PyObject *iter = PyObject_GetIter(items_view);
            Py_DECREF(items_view);
            if (!iter) { Py_DECREF(functor); return NULL; }
            PyObject *new_dict = PyDict_New();
            if (!new_dict) { Py_DECREF(functor); Py_DECREF(iter); return NULL; }
            int err = 0;
            PyObject *pair;
            while ((pair = PyIter_Next(iter))) {
                PyObject *k = PyTuple_GET_ITEM(pair, 0);
                PyObject *v = PyTuple_GET_ITEM(pair, 1);
                PyObject *copied_v = c_copy_term(v, var_map, depth + 1);
                if (!copied_v) { Py_DECREF(pair); err = 1; break; }
                int ok = PyDict_SetItem(new_dict, k, copied_v);
                Py_DECREF(copied_v);
                Py_DECREF(pair);
                if (ok < 0) { err = 1; break; }
            }
            Py_DECREF(iter);
            if (err || PyErr_Occurred()) {
                Py_DECREF(functor); Py_DECREF(new_dict); return NULL;
            }
            /* Reconstruct: KWTerm(functor, **new_dict) */
            PyObject *pos_args = PyTuple_Pack(1, functor);
            Py_DECREF(functor);
            if (!pos_args) { Py_DECREF(new_dict); return NULL; }
            PyObject *result = PyObject_Call(KWTerm_type, pos_args, new_dict);
            Py_DECREF(pos_args);
            Py_DECREF(new_dict);
            return result;
        }
    }

    /* Term instance (PredicateMeta or @dataclass): copy each field, reconstruct */
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) {
            /* c_term_field_names used to answer for a PredicateMeta
             * INSTANCE; W4a made that shape impossible and turned it into
             * an unconditional NULL-without-exception stub, so every call
             * here fell straight through to this @dataclass route on every
             * term. Retired in W4b, 2026-09-23 -- call it directly. */
            PyObject *fields = py_term_field_names(NULL, term);
            if (!fields) return NULL;
            Py_ssize_t n = PyTuple_GET_SIZE(fields);

            /* The Phase-0 fast-path gate that used to precede this (calling
             * a "_clausal_new" positional classmethod when PredicateMeta
             * had attached one; c_copy_term is wired in as
             * clausal.logic.builtins.inspection's runtime _copy_term, so it
             * had to decide identically to _copy_term_py's own gate) was
             * retired in W4b, 2026-09-23: that classmethod and its minter
             * are gone since W4a, so the gate always fell through to the
             * kwargs reconstruction below on every call -- see solve.py's
             * _deref_walk_py.
             */

            PyObject *kwargs = PyDict_New();
            if (!kwargs) { Py_DECREF(fields); return NULL; }
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *fname = PyTuple_GET_ITEM(fields, i);
                PyObject *fval = PyObject_GetAttr(term, fname);
                if (!fval) { Py_DECREF(fields); Py_DECREF(kwargs); return NULL; }
                PyObject *copied_val = c_copy_term(fval, var_map, depth + 1);
                Py_DECREF(fval);
                if (!copied_val) { Py_DECREF(fields); Py_DECREF(kwargs); return NULL; }
                int ok = PyDict_SetItem(kwargs, fname, copied_val);
                Py_DECREF(copied_val);
                if (ok < 0) { Py_DECREF(fields); Py_DECREF(kwargs); return NULL; }
            }
            Py_DECREF(fields);
            PyObject *empty_args = PyTuple_New(0);
            if (!empty_args) { Py_DECREF(kwargs); return NULL; }
            PyObject *result = PyObject_Call((PyObject *)Py_TYPE(term), empty_args, kwargs);
            Py_DECREF(empty_args);
            Py_DECREF(kwargs);
            return result;
        }
    }

    /* Unknown term type: return as-is */
    Py_INCREF(term);
    return term;
}

/*
 * _copy_term_impl(term, var_map) -> copied_term
 *
 * Python-callable wrapper.  var_map must be a dict (initially empty {}).
 * Implements the recursive copy used by copy_term/2.
 */
static PyObject *
py_copy_term_impl(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *term, *var_map;
    if (!PyArg_ParseTuple(args, "OO!", &term, &PyDict_Type, &var_map))
        return NULL;
    return c_copy_term(term, var_map, 0);
}


/* ================================================================
 * UIntSet — minimal open-addressing hash set over uintptr_t keys.
 * Used by c_collect_vars to deduplicate Var pointers without
 * allocating a Python object per variable (issue 6).
 * ================================================================ */

#define UINT_SET_INIT_CAP 64

typedef struct {
    uintptr_t *keys;   /* 0 == empty slot; 1 == tombstone (unused here) */
    Py_ssize_t cap;
    Py_ssize_t count;
} UIntSet;

static int
uint_set_init(UIntSet *s)
{
    s->cap   = UINT_SET_INIT_CAP;
    s->count = 0;
    s->keys  = (uintptr_t *)PyMem_Calloc((size_t)s->cap, sizeof(uintptr_t));
    if (!s->keys) { PyErr_NoMemory(); return -1; }
    return 0;
}

static void
uint_set_free(UIntSet *s)
{
    PyMem_Free(s->keys);
    s->keys = NULL;
}

/*
 * Insert key into set.
 * Returns 0 if newly inserted, 1 if already present, -1 on OOM.
 * key == 0 is remapped to UINTPTR_MAX (PyObject* is never NULL).
 */
static int
uint_set_add(UIntSet *s, uintptr_t key)
{
    if (key == 0) key = UINTPTR_MAX;

    /* Grow at 70% load */
    if (s->count * 10 >= s->cap * 7) {
        Py_ssize_t new_cap = s->cap * 2;
        uintptr_t *new_keys = (uintptr_t *)PyMem_Calloc((size_t)new_cap,
                                                          sizeof(uintptr_t));
        if (!new_keys) { PyErr_NoMemory(); return -1; }
        for (Py_ssize_t i = 0; i < s->cap; i++) {
            if (!s->keys[i]) continue;
            Py_ssize_t j = (Py_ssize_t)(s->keys[i] % (uintptr_t)new_cap);
            while (new_keys[j])
                j = (j + 1) % new_cap;
            new_keys[j] = s->keys[i];
        }
        PyMem_Free(s->keys);
        s->keys = new_keys;
        s->cap  = new_cap;
    }

    Py_ssize_t i = (Py_ssize_t)(key % (uintptr_t)s->cap);
    while (s->keys[i]) {
        if (s->keys[i] == key) return 1;  /* already present */
        i = (i + 1) % s->cap;
    }
    s->keys[i] = key;
    s->count++;
    return 0;  /* newly inserted */
}


/* ================================================================
 * _collect_vars_impl — collect all unbound Vars left-to-right
 * ================================================================ */

/*
 * c_collect_vars(term, seen, result, depth) -> 0 ok, -1 error
 *
 * Appends each unique unbound Var in term to result (a PyList),
 * in left-to-right traversal order.  seen is a C-level UIntSet
 * tracking pointer-based ids for O(1) dedup without PyLong allocation.
 */
static int
c_collect_vars(PyObject *term, UIntSet *seen, PyObject *result, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "_collect_vars: term nesting too deep");
        return -1;
    }
    term = var_deref(term);

    /* Unbound variable */
    if (Var_Check(term)) {
        int r = uint_set_add(seen, (uintptr_t)term);
        if (r < 0) return -1;
        if (r == 0) {  /* newly inserted */
            if (PyList_Append(result, term) < 0) return -1;
        }
        return 0;
    }

    /* Primitives: no variables */
    if (term == Py_None || PyBool_Check(term) || PyLong_Check(term) ||
        PyFloat_Check(term) || PyUnicode_Check(term) || PyBytes_Check(term))
        return 0;

    /* List */
    if (PyList_Check(term)) {
        Py_ssize_t n = PyList_GET_SIZE(term);
        for (Py_ssize_t i = 0; i < n; i++) {
            if (c_collect_vars(PyList_GET_ITEM(term, i), seen, result, depth + 1) < 0)
                return -1;
        }
        return 0;
    }

    /* Cell — a plain tuple (see the branch in ``c_copy_term`` for why a tuple
     * is no longer a leaf).  Without this, ``term_variables/2`` and
     * ``numbervars/3`` missed every variable inside a cell.
     *
     * Slot 0 is walked like any other slot: an unbound functor Var IS a
     * variable of the term, and a str functor / the TUPLE_TAG type object
     * collects nothing.  PyTuple_CheckEXACT keeps this in step with the
     * Python twin's ``type(term) is tuple`` (``_collect_vars_py``), for which
     * a namedtuple stays a leaf. */
    if (PyTuple_CheckExact(term)) {
        Py_ssize_t n = PyTuple_GET_SIZE(term);
        for (Py_ssize_t i = 0; i < n; i++) {
            if (c_collect_vars(PyTuple_GET_ITEM(term, i), seen, result, depth + 1) < 0)
                return -1;
        }
        return 0;
    }

    /* Compound */
    if (Compound_type) {
        int r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return -1;
        if (r) {
            /* A01-F003: visit the functor slot first — an unbound functor Var
             * is a variable of the term; a str functor derefs to a primitive
             * and collects nothing. */
            PyObject *functor = PyObject_GetAttr(term, str_functor);
            if (!functor) return -1;
            int fr = c_collect_vars(functor, seen, result, depth + 1);
            Py_DECREF(functor);
            if (fr < 0) return -1;
            PyObject *args = PyObject_GetAttr(term, str_args);
            if (!args) return -1;
            if (!PyTuple_Check(args)) {
                Py_DECREF(args);
                PyErr_SetString(PyExc_TypeError, "Compound.args is not a tuple");
                return -1;
            }
            Py_ssize_t n = PyTuple_GET_SIZE(args);
            for (Py_ssize_t i = 0; i < n; i++) {
                if (c_collect_vars(PyTuple_GET_ITEM(args, i), seen, result, depth + 1) < 0) {
                    Py_DECREF(args);
                    return -1;
                }
            }
            Py_DECREF(args);
            return 0;
        }
    }

    /* KWTerm */
    if (KWTerm_type) {
        int r = PyObject_IsInstance(term, KWTerm_type);
        if (r < 0) return -1;
        if (r) {
            PyObject *values = PyObject_CallMethod(term, "values", NULL);
            if (!values) return -1;
            PyObject *iter = PyObject_GetIter(values);
            Py_DECREF(values);
            if (!iter) return -1;
            PyObject *item;
            while ((item = PyIter_Next(iter))) {
                int r2 = c_collect_vars(item, seen, result, depth + 1);
                Py_DECREF(item);
                if (r2 < 0) { Py_DECREF(iter); return -1; }
            }
            Py_DECREF(iter);
            if (PyErr_Occurred()) return -1;
            return 0;
        }
    }

    /* Term instance (PredicateMeta or @dataclass) */
    {
        int ti = c_is_term_instance(term);
        if (ti < 0) return -1;
        if (ti) {
            /* c_term_field_names used to answer for a PredicateMeta
             * INSTANCE; W4a made that shape impossible and turned it into
             * an unconditional NULL-without-exception stub, so every call
             * here fell straight through to this @dataclass route on every
             * term. Retired in W4b, 2026-09-23 -- call it directly. */
            PyObject *fields = py_term_field_names(NULL, term);
            if (!fields) return -1;
            Py_ssize_t n = PyTuple_GET_SIZE(fields);
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *val = PyObject_GetAttr(term, PyTuple_GET_ITEM(fields, i));
                if (!val) { Py_DECREF(fields); return -1; }
                int r2 = c_collect_vars(val, seen, result, depth + 1);
                Py_DECREF(val);
                if (r2 < 0) { Py_DECREF(fields); return -1; }
            }
            Py_DECREF(fields);
            return 0;
        }
    }

    return 0;
}

/*
 * _collect_vars_impl(term, result_list) -> None
 *
 * Python-callable wrapper.  Appends unbound Vars from term into result_list.
 * Uses an internal C-level UIntSet for deduplication (no Python set needed).
 * Implements the traversal used by term_variables/2 and numbervars/3.
 */
static PyObject *
py_collect_vars_impl(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *term, *result;
    if (!PyArg_ParseTuple(args, "OO!", &term, &PyList_Type, &result))
        return NULL;
    UIntSet seen;
    if (uint_set_init(&seen) < 0) return NULL;
    int ok = c_collect_vars(term, &seen, result, 0);
    uint_set_free(&seen);
    if (ok < 0) return NULL;
    Py_RETURN_NONE;
}


/* ================================================================
 * C API capsule — exported for other C extensions
 * ================================================================ */

/* Wrapper: is_var(term) → 1 if term dereferences to unbound Var */
static int
capi_is_var(PyObject *term)
{
    PyObject *d = var_deref(term);
    return Var_Check(d) ? 1 : 0;
}

/* Wrapper: unify_with_occurs_check returning new ref */
static PyObject *
capi_unify_oc(PyObject *t1, PyObject *t2, TrailObject *trail)
{
    return do_unify_and_wake(t1, t2, trail, 1);
}

/* Wrapper: unify (no occurs check) returning new ref */
static PyObject *
capi_unify(PyObject *t1, PyObject *t2, TrailObject *trail)
{
    return do_unify_and_wake(t1, t2, trail, 0);
}

/* Wrapper: trail_mark */
static Py_ssize_t
capi_trail_mark(TrailObject *trail)
{
    return trail->length;
}

/* Wrapper: trail_undo */
static void
capi_trail_undo(TrailObject *trail, Py_ssize_t mark)
{
    if (mark <= trail->length)
        trail_undo_to(trail, mark);
}

/* Wrapper: get_attr → new ref (value or Py_None) */
static PyObject *
capi_get_attr(PyObject *var_obj, PyObject *key)
{
    PyObject *root = var_deref(var_obj);
    if (!AttVar_Check(root)) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    AttVarObject *av = AttVar_CAST(root);
    if (!av->attrs) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    PyObject *val = PyDict_GetItemWithError(av->attrs, key);
    if (!val) {
        if (PyErr_Occurred()) return NULL;
        Py_INCREF(Py_None);
        return Py_None;
    }
    Py_INCREF(val);
    return val;
}

/* Wrapper: put_attr → 0 on success, -1 on error */
static int
capi_put_attr(PyObject *var_obj, PyObject *key, PyObject *value,
              TrailObject *trail)
{
    PyObject *root = var_deref(var_obj);
    AttVarObject *av;

    if (AttVar_Check(root)) {
        av = AttVar_CAST(root);
    } else if (Var_Check(root)) {
        /* A01-F002: a plain Var cannot be promoted in place (Var identity
         * must be preserved), and the old "(OOsO)" promote path was broken
         * three ways — it passed `value` (a PyObject*) where Py_BuildValue
         * expected a char* (UB), leaked the args tuple, and py_put_attr does
         * not actually promote (it raises TypeError unless the arg derefs to
         * an AttVar). Raise a clean TypeError, mirroring py_put_attr. */
        PyErr_SetString(PyExc_TypeError,
            "put_attr requires an AttVar (plain Var cannot be promoted)");
        return -1;
    } else {
        PyErr_SetString(PyExc_TypeError, "put_attr requires a Var");
        return -1;
    }

    if (!av->attrs) {
        av->attrs = PyDict_New();
        if (!av->attrs) return -1;
    }

    PyObject *old_attr = PyDict_GetItemWithError(av->attrs, key);
    if (!old_attr && PyErr_Occurred()) return -1;

    if (trail_push_attr(trail, av, key, old_attr) < 0)
        return -1;

    if (PyDict_SetItem(av->attrs, key, value) < 0)
        return -1;

    return 0;
}

/* Wrapper: term_field_names (calls the full py_term_field_names) */
static PyObject *
capi_term_field_names(PyObject *obj)
{
    return py_term_field_names(NULL, obj);
}

/* The singleton API table — populated in PyInit */
static VariablesCAPI capi_table;


/* ================================================================
 * Module definition
 * ================================================================ */

static PyObject *
py_unify_census_start(PyObject *self, PyObject *Py_UNUSED(ignored))
{
    Py_XDECREF(unify_census_sites);
    unify_census_sites = PyDict_New();
    if (!unify_census_sites) return NULL;
    unify_census_count = 0;
    unify_census_on = 1;
    Py_RETURN_NONE;
}

static PyObject *
py_unify_census_stop(PyObject *self, PyObject *Py_UNUSED(ignored))
{
    unify_census_on = 0;
    Py_RETURN_NONE;
}

/*
 * as_cells_for_match(term, depth) -- C twin of
 * ``clausal.terms.as_cells_for_match`` (keep the two in step; parity is
 * tested in tests/test_compound_cell_same_term.py).
 *
 * The clause-head ``match`` subject normaliser (ruling 2026-09-26): ``term``
 * dereferenced, with every atom-functor Compound in its top *depth* cell
 * levels replaced by its cell (compound_to_cell), so a caller's Compound
 * spelling meets a cell-only head pattern as the cell.  Nothing is copied
 * unless a Compound is converted; an unconverted element keeps its original
 * object.  Generated code calls this INSTEAD of ``$deref`` at the argument
 * positions whose head patterns have cell structure, so the common case
 * costs one C call, as before.
 */
static int
cells_below(PyObject *term, long depth, PyObject **out)
{
    *out = NULL;
    if (PyTuple_CheckExact(term)) {
        Py_ssize_t n = PyTuple_GET_SIZE(term);
        if (depth <= 1 || n < 2) return 0;
        PyObject *copy = NULL;
        for (Py_ssize_t i = 1; i < n; i++) {
            PyObject *elt = var_deref(PyTuple_GET_ITEM(term, i));   /* borrowed */
            if (!PyTuple_CheckExact(elt)
                    && !(Compound_type && PyType_Check(Compound_type)
                         && PyObject_TypeCheck(elt, (PyTypeObject *)Compound_type)))
                continue;
            PyObject *sub;
            int r = cells_below(elt, depth - 1, &sub);
            if (r < 0) { Py_XDECREF(copy); return -1; }
            if (!r) continue;
            if (!copy) {
                copy = PyTuple_New(n);
                if (!copy) { Py_DECREF(sub); return -1; }
                for (Py_ssize_t j = 0; j < n; j++) {
                    PyObject *it = PyTuple_GET_ITEM(term, j);
                    Py_INCREF(it);
                    PyTuple_SET_ITEM(copy, j, it);
                }
            }
            Py_DECREF(PyTuple_GET_ITEM(copy, i));
            PyTuple_SET_ITEM(copy, i, sub);   /* steals */
        }
        if (!copy) return 0;
        *out = copy;
        return 1;
    }
    PyObject *cell;
    int c = compound_to_cell(term, &cell);
    if (c <= 0) return c;
    PyObject *sub;
    int r = cells_below(cell, depth, &sub);
    if (r < 0) { Py_DECREF(cell); return -1; }
    if (r) { Py_DECREF(cell); *out = sub; }
    else   { *out = cell; }
    return 1;
}

static PyObject *
py_as_cells_for_match(PyObject *Py_UNUSED(module), PyObject *const *args,
                      Py_ssize_t nargs)
{
    if (nargs != 2) {
        PyErr_SetString(PyExc_TypeError,
                        "as_cells_for_match(term, depth) takes 2 arguments");
        return NULL;
    }
    long depth = PyLong_AsLong(args[1]);
    if (depth == -1 && PyErr_Occurred()) return NULL;
    PyObject *d = var_deref(args[0]);   /* borrowed */
    if (depth > 0) {
        PyObject *conv;
        int r = cells_below(d, depth, &conv);
        if (r < 0) return NULL;
        if (r) return conv;
    }
    Py_INCREF(d);
    return d;
}

static PyObject *
py_unify_census(PyObject *self, PyObject *Py_UNUSED(ignored))
{
    PyObject *d = PyDict_New();
    if (!d) return NULL;
    PyObject *n = PyLong_FromUnsignedLongLong(unify_census_count);
    if (!n) { Py_DECREF(d); return NULL; }
    if (PyDict_SetItemString(d, "conflations", n) < 0) {
        Py_DECREF(n); Py_DECREF(d); return NULL;
    }
    Py_DECREF(n);
    PyObject *by = unify_census_sites ? unify_census_sites : PyDict_New();
    if (!by) { Py_DECREF(d); return NULL; }
    if (unify_census_sites) Py_INCREF(by);
    if (PyDict_SetItemString(d, "by_type_pair", by) < 0) {
        Py_DECREF(by); Py_DECREF(d); return NULL;
    }
    Py_DECREF(by);
    PyObject *on = PyBool_FromLong(unify_census_on);
    if (!on) { Py_DECREF(d); return NULL; }
    if (PyDict_SetItemString(d, "enabled", on) < 0) {
        Py_DECREF(on); Py_DECREF(d); return NULL;
    }
    Py_DECREF(on);
    return d;
}

static PyMethodDef module_methods[] = {
    {"unify_census_start", py_unify_census_start, METH_NOARGS,
     "unify_census_start() -> None\n\n"
     "Begin counting unifications that succeed ONLY because two numbers of\n"
     "different Python types compare equal (1 vs 1.0, Decimal(1) vs 1).\n"
     "ISO treats those as distinct terms. Resets any previous count.\n"
     "Off by default; costs a not-taken branch on the fallback path."},
    {"unify_census_stop", py_unify_census_stop, METH_NOARGS,
     "unify_census_stop() -> None\n\nStop counting. Results are retained."},
    {"as_cells_for_match", (PyCFunction)(void (*)(void))py_as_cells_for_match,
     METH_FASTCALL,
     "as_cells_for_match(term, depth) -> term\n\n"
     "deref(term) with atom-functor Compounds in its top depth cell levels\n"
     "replaced by their cells (C twin of clausal.terms.as_cells_for_match)."},
    {"unify_census", py_unify_census, METH_NOARGS,
     "unify_census() -> dict\n\n"
     "{'conflations': int, 'by_type_pair': {'int/float': n, ...},\n"
     " 'enabled': bool}"},
    {"unify", py_unify, METH_VARARGS,
     "unify(t1, t2, trail) -> bool\n"
     "\n"
     "Unify two terms under *trail*.\n"
     "\n"
     "Returns True on success; bindings are recorded on *trail* for later\n"
     "backtracking via trail.undo().\n"
     "\n"
     "Returns False on failure; any partial bindings (including those made\n"
     "by attribute hooks) are automatically rolled back.\n"
     "\n"
     "If any AttVar's attribute hook returns False the unification fails\n"
     "and all bindings are rolled back to the state before this call.\n"
     "\n"
     "Terms recognised:\n"
     "  - ``Var`` / ``AttVar`` — logic variable\n"
     "  - tuple  — compound term; elements unified pairwise\n"
     "  - list   — sequence; elements unified pairwise\n"
     "  - anything else — atomic; compared with ``==``\n"},
    {"unify_with_occurs_check", py_unify_with_occurs_check, METH_VARARGS,
     "unify_with_occurs_check(t1, t2, trail) -> bool\n"
     "\n"
     "Like unify() but performs the occurs check before each variable\n"
     "binding.  Prevents creation of circular/infinite terms."},
    {"deref", py_deref, METH_O,
     "deref(term) -> term\n"
     "\n"
     "Follow the variable binding chain to its root.\n"
     "Returns the variable itself if unbound, or the bound value."},
    {"walk", py_walk, METH_O,
     "walk(term) -> term\n"
     "\n"
     "Deeply substitute all bound variables throughout a term.\n"
     "Rebuilds tuples and lists with bound vars replaced by their values.\n"
     "Unbound vars are left in place.  Returns a fresh object."},
    {"is_var", py_is_var, METH_O,
     "is_var(term) -> bool\n"
     "\n"
     "Return True if *term* dereferences to an unbound Var or AttVar."},
    {"occurs_check", py_occurs_check, METH_VARARGS,
     "occurs_check(var, term) -> bool\n"
     "\n"
     "Return True if *var* appears free inside *term*.\n"
     "Used to guard against circular unification."},
    /* Attributed variable API */
    {"put_attr", py_put_attr, METH_VARARGS,
     "put_attr(var, key, value, trail)\n"
     "\n"
     "Set attribute *key* on AttVar *var* to *value*.\n"
     "The change is recorded on *trail* and reversed on backtrack.\n"
     "Analogous to SWI-Prolog's put_attr/3."},
    {"get_attr", py_get_attr, METH_VARARGS,
     "get_attr(var, key) -> value or None\n"
     "\n"
     "Return the attribute stored under *key* on AttVar *var*, or None.\n"
     "Analogous to SWI-Prolog's get_attr/3."},
    {"del_attr", py_del_attr, METH_VARARGS,
     "del_attr(var, key, trail)\n"
     "\n"
     "Delete attribute *key* from AttVar *var*.\n"
     "The deletion is recorded on *trail* and reversed on backtrack."},
    {"register_attr_hook", py_register_attr_hook, METH_VARARGS,
     "register_attr_hook(key, callable)\n"
     "\n"
     "Register a hook called when an AttVar with attribute *key* is unified.\n"
     "\n"
     "Hook signature: hook(attr_value, bound_to, trail) -> bool\n"
     "\n"
     "Returning False fails the unification and rolls back all bindings.\n"
     "The hook may call unify() or put_attr() to propagate constraints.\n"
     "Pass callable=None to unregister.\n"
     "\n"
     "Analogous to SWI/Scryer's attr_unify_hook/2 (per module key) and\n"
     "SICStus's verify_attributes/3."},
    /* Predicate helpers */
    {"_register_term_types", py_register_term_types, METH_VARARGS,
     "_register_term_types(compound_cls, kwterm_cls)\n"
     "Register Compound and KWTerm types for C-level term inspection."},
    {"is_term_instance", py_is_term_instance, METH_O,
     "is_term_instance(obj) -> bool\n"
     "True if obj is a term instance (a @dataclass instance)."},
    {"term_field_names", py_term_field_names, METH_O,
     "term_field_names(obj) -> tuple\n"
     "Return field name strings for a term instance."},
    {"_is_ground", py_is_ground, METH_O,
     "_is_ground(term) -> bool\n"
     "True if term contains no unbound Vars."},
    {"_functor_name", py_functor_name, METH_O,
     "_functor_name(term) -> str | None\n"
     "Return the functor name of a term, or None."},
    {"_arity", py_arity, METH_O,
     "_arity(term) -> int | None\n"
     "Return the arity of a term, or None."},
    {"_nth_arg", py_nth_arg, METH_VARARGS,
     "_nth_arg(term, n) -> value\n"
     "Return the n-th argument (1-based) of a compound term."},
    {"_args_list", py_args_list, METH_O,
     "_args_list(term) -> list\n"
     "Return the argument list of a compound term."},
    {"_is_compound", py_is_compound, METH_O,
     "_is_compound(term) -> bool\n"
     "True if term is a compound term."},
    {"_copy_term_impl", py_copy_term_impl, METH_VARARGS,
     "_copy_term_impl(term, var_map) -> copied_term\n"
     "Deep-copy term, replacing each unbound Var with a fresh one.\n"
     "var_map (a dict) maps original Var id to fresh Var; pass {} initially.\n"
     "Sharing is preserved: two refs to the same Var get the same fresh copy."},
    {"_collect_vars_impl", py_collect_vars_impl, METH_VARARGS,
     "_collect_vars_impl(term, result_list) -> None\n"
     "Append all unbound Vars in term to result_list in left-to-right order.\n"
     "Deduplication is handled internally via a C-level hash set."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_variables",
    "Logic variables with trail-based backtracking and attributed variables.\n"
    "\n"
    "Plain variables (Var) implement Prolog-style unification without a WAM.\n"
    "Attributed variables (AttVar) extend Var with per-key attributes and\n"
    "a hook mechanism for constraint propagation.\n"
    "\n"
    "Studied implementations: GNU Prolog (wam_inst.h / unify.c),\n"
    "Scryer Prolog (machine_state_impl.rs / attributed_variables.rs),\n"
    "SWI-Prolog (pl-attvar.c), SICStus Prolog (attributed variable design).\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__variables(void)
{
    /* AttVarType must inherit from VarType.  Set tp_base before PyType_Ready
     * since static initialisers cannot reference other static objects. */
    AttVarType.tp_base = &VarType;

    if (PyType_Ready(&VarType)    < 0) return NULL;
    if (PyType_Ready(&AttVarType) < 0) return NULL;
    if (PyType_Ready(&TrailType)  < 0) return NULL;

    g_attr_hooks = PyDict_New();
    if (!g_attr_hooks) return NULL;

    /* Interned before any unify can run — do_unify's hook probe uses it. */
    str_dunder_unify = PyUnicode_InternFromString("__unify__");
    if (!str_dunder_unify) return NULL;

    /* The term-inspection helpers' interned names + dataclasses.fields. */
    if (init_term_inspection_cache() < 0) return NULL;

    /* The ASCII char-atom cache the str↔list unification arms read. */
    for (int i = 0; i < 128; i++) {
        PyObject *spelling = PyUnicode_FromOrdinal(i);
        if (!spelling) return NULL;
        PyUnicode_InternInPlace(&spelling);
        g_ascii_char_atoms[i] = spelling;   /* STAGE 2: a char atom IS the interned 1-char str */
    }

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) goto error;

#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif

    Py_INCREF(&VarType);
    if (PyModule_AddObject(m, "Var", (PyObject *)&VarType) < 0)
        goto error;

    Py_INCREF(&AttVarType);
    if (PyModule_AddObject(m, "AttVar", (PyObject *)&AttVarType) < 0)
        goto error;

    Py_INCREF(&TrailType);
    if (PyModule_AddObject(m, "Trail", (PyObject *)&TrailType) < 0)
        goto error;

    /* Create UnboundVarCoercionError exception class */
    UnboundVarCoercionError = PyErr_NewException(
        "clausal.logic.variables.UnboundVarCoercionError", PyExc_TypeError, NULL);
    if (!UnboundVarCoercionError) goto error;
    Py_INCREF(UnboundVarCoercionError);
    if (PyModule_AddObject(m, "UnboundVarCoercionError", UnboundVarCoercionError) < 0)
        goto error;

    /* Populate and export the C API capsule */
    capi_table.VarType         = &VarType;
    capi_table.AttVarType      = &AttVarType;
    capi_table.TrailType       = &TrailType;
    capi_table.deref           = var_deref;
    capi_table.is_var          = capi_is_var;
    capi_table.unify_oc        = capi_unify_oc;
    capi_table.trail_mark      = capi_trail_mark;
    capi_table.trail_undo      = capi_trail_undo;
    capi_table.get_attr        = capi_get_attr;
    capi_table.put_attr        = capi_put_attr;
    capi_table.is_term_instance = c_is_term_instance;
    capi_table.term_field_names = capi_term_field_names;
    capi_table.unify            = capi_unify;

    {
        PyObject *cap = PyCapsule_New(
            &capi_table, VARIABLES_CAPI_CAPSULE_NAME, NULL);
        if (!cap) goto error;
        if (PyModule_AddObject(m, "_C_API", cap) < 0) {
            Py_DECREF(cap);
            goto error;
        }
    }

    return m;

error:
    Py_XDECREF(m);
    return NULL;
}
