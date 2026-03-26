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
#include <stdint.h>
#include "_ft_compat.h"

/* ================================================================
 * Forward declarations
 * ================================================================ */

typedef struct VarObject    VarObject;
typedef struct AttVarObject AttVarObject;
typedef struct TrailObject  TrailObject;

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
    }
    PyObject_GC_Track(self);
    return (PyObject *)self;
}

static void
Trail_dealloc(TrailObject *self)
{
    PyObject_GC_UnTrack(self);
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
    .tp_flags       = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_new         = Trail_new,
    .tp_dealloc     = (destructor)Trail_dealloc,
    .tp_traverse    = (traverseproc)Trail_traverse,
    .tp_clear       = (inquiry)Trail_clear,
    .tp_repr        = (reprfunc)Trail_repr,
    .tp_methods     = Trail_methods,
    .tp_as_sequence = &Trail_as_sequence,
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

    if (PyList_Check(t1) && PyList_Check(t2)) {
        Py_ssize_t n = PyList_GET_SIZE(t1);
        if (n != PyList_GET_SIZE(t2)) return 0;
        for (Py_ssize_t i = 0; i < n - 1; i++) {
            int r = do_unify(PyList_GET_ITEM(t1, i),
                             PyList_GET_ITEM(t2, i),
                             trail, depth + 1, oc);
            if (r != 1) return r;
        }
        if (n == 0) return 1;
        return do_unify(PyList_GET_ITEM(t1, n-1),
                        PyList_GET_ITEM(t2, n-1),
                        trail, depth + 1, oc);
    }

    /* ---- String ↔ List unification ----
     * Treat a Python str as a list of single-character strings.
     * "abc" unifies element-wise with ['a', 'b', 'c'].
     * String-vs-string still falls through to PyObject_RichCompareBool below.
     *
     * Fast path: when the list element is a ground single-char string, compare
     * code points directly (no allocation).  Only allocate a PyUnicode when
     * binding an unbound Var.
     */
    if (PyUnicode_Check(t1) && PyList_Check(t2)) {
        Py_ssize_t n = PyUnicode_GET_LENGTH(t1);
        if (n != PyList_GET_SIZE(t2)) return 0;
        if (n == 0) return 1;
        int kind = PyUnicode_KIND(t1);
        void *data = PyUnicode_DATA(t1);
        for (Py_ssize_t i = 0; i < n; i++) {
            Py_UCS4 c1 = PyUnicode_READ(kind, data, i);
            PyObject *elem = var_deref(PyList_GET_ITEM(t2, i));
            if (Var_Check(elem)) {
                /* Unbound var — allocate char string and unify (binds the var) */
                PyObject *ch = PyUnicode_Substring(t1, i, i + 1);
                if (!ch) return -1;
                int r = do_unify(ch, elem, trail, depth + 1, oc);
                Py_DECREF(ch);
                if (r != 1) return r;
            } else if (PyUnicode_Check(elem)
                       && PyUnicode_GET_LENGTH(elem) == 1
                       && PyUnicode_READ_CHAR(elem, 0) == c1) {
                /* Ground single-char match — no allocation */
                continue;
            } else {
                return 0;
            }
        }
        return 1;
    }
    if (PyList_Check(t1) && PyUnicode_Check(t2)) {
        /* Symmetric: list on left, string on right — delegate with swapped args */
        Py_ssize_t n = PyUnicode_GET_LENGTH(t2);
        if (PyList_GET_SIZE(t1) != n) return 0;
        if (n == 0) return 1;
        int kind = PyUnicode_KIND(t2);
        void *data = PyUnicode_DATA(t2);
        for (Py_ssize_t i = 0; i < n; i++) {
            Py_UCS4 c2 = PyUnicode_READ(kind, data, i);
            PyObject *elem = var_deref(PyList_GET_ITEM(t1, i));
            if (Var_Check(elem)) {
                PyObject *ch = PyUnicode_Substring(t2, i, i + 1);
                if (!ch) return -1;
                int r = do_unify(elem, ch, trail, depth + 1, oc);
                Py_DECREF(ch);
                if (r != 1) return r;
            } else if (PyUnicode_Check(elem)
                       && PyUnicode_GET_LENGTH(elem) == 1
                       && PyUnicode_READ_CHAR(elem, 0) == c2) {
                continue;
            } else {
                return 0;
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
     */
    if (!PyList_Check(t1) && !PyTuple_Check(t1)) {
        PyObject *hook = PyObject_GetAttrString(t1, "__unify__");
        if (hook) {
            PyObject *result = PyObject_CallFunctionObjArgs(
                hook, t2, (PyObject *)trail, NULL);
            Py_DECREF(hook);
            if (result == NULL) return -1;
            if (result != Py_NotImplemented) {
                int r = PyObject_IsTrue(result);
                Py_DECREF(result);
                return r;
            }
            Py_DECREF(result);
            /* Fall through: NotImplemented — try symmetric or list guard */
        } else {
            PyErr_Clear();
        }
    }
    /* Symmetric: try t2.__unify__ if t1 didn't handle it */
    if (!PyList_Check(t2) && !PyTuple_Check(t2)) {
        PyObject *hook = PyObject_GetAttrString(t2, "__unify__");
        if (hook) {
            PyObject *result = PyObject_CallFunctionObjArgs(
                hook, t1, (PyObject *)trail, NULL);
            Py_DECREF(hook);
            if (result == NULL) return -1;
            if (result != Py_NotImplemented) {
                int r = PyObject_IsTrue(result);
                Py_DECREF(result);
                return r;
            }
            Py_DECREF(result);
        } else {
            PyErr_Clear();
        }
    }

    if (PyTuple_Check(t1) || PyList_Check(t1) ||
        PyTuple_Check(t2) || PyList_Check(t2))
        return 0;

    int cmp = PyObject_RichCompareBool(t1, t2, Py_EQ);
    if (cmp < 0) return -1;
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
    /* __walk__ protocol: delegate to Python method if present */
    {
        PyObject *hook = PyObject_GetAttrString(term, "__walk__");
        if (hook) {
            PyObject *result = PyObject_CallNoArgs(hook);
            Py_DECREF(hook);
            return result;  /* NULL propagates error */
        }
        PyErr_Clear();
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
 * Module definition
 * ================================================================ */

static PyMethodDef module_methods[] = {
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

    return m;

error:
    Py_XDECREF(m);
    return NULL;
}
