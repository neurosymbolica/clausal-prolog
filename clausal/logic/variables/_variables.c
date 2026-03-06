/*
 * logicvars.c — Logic variables with trail-based backtracking
 *
 * A WAM-less Python C extension implementing Prolog-style unification.
 *
 * Design notes (from studying GNU Prolog and Scryer Prolog):
 *
 *   GNU Prolog (wam_inst.h / unify.c):
 *     - Variables are tagged words; unbound = self-referential pointer.
 *     - Bind_UV: records old value on trail iff var was created before the
 *       current choice point (h < HB).  We always trail (no HB optimization).
 *     - Trail entry types: TUV (restore to self-ref), TOV (restore one word),
 *       TMV (multi-word), TFC (function callback).  We use the TUV/TOV pattern.
 *     - Pl_Untrail: pops trail in reverse order, restores by tag.
 *
 *   Scryer Prolog (machine_state_impl.rs / unify.rs):
 *     - Unbound var = heap cell whose value equals its own address.
 *     - trail(): only records when h < hb (heap barrier = mark at choice point).
 *     - unwind_trail(): reverse-order iteration restoring vars to self-ref.
 *     - bind(): age-ordered — newer var (larger id) binds to older (smaller id),
 *       matching GNU Prolog's "bind higher address to lower address" convention.
 *     - Unification uses a PDL (push-down list) to flatten recursion.
 *
 *   WAM-less adaptation:
 *     - Variables are Python heap objects; GC manages memory.
 *     - No WAM stacks/heap or high-water mark — we always trail every binding.
 *     - Trail mark = saved trail length; undo = restore in reverse from mark.
 *     - Age ordering is by monotonic creation counter (var_id).
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>

/* ================================================================
 * Forward declarations
 * ================================================================ */

typedef struct VarObject   VarObject;
typedef struct TrailObject TrailObject;

static PyTypeObject VarType;
static PyTypeObject TrailType;

/* ================================================================
 * Var type
 *
 * An unbound logic variable.  binding == NULL means unbound.
 * When bound, binding points to the bound value (another Var* or
 * any Python object).
 *
 * var_id is a monotonic creation counter used to orient var-var
 * bindings: the newer var (larger id) is bound to the older one,
 * matching Scryer / GNU Prolog's age-based convention and preventing
 * trivial reference cycles.
 * ================================================================ */

struct VarObject {
    PyObject_HEAD
    PyObject *binding;   /* NULL = unbound; non-NULL = bound value */
    uint64_t  var_id;    /* monotonic creation id */
};

/* Global monotonic counter.  Not thread-safe without the GIL. */
static uint64_t g_next_var_id = 0;

#define Var_Check(op)  PyObject_TypeCheck((op), &VarType)
#define Var_CAST(op)   ((VarObject *)(op))

/*
 * var_deref — follow the binding chain and return the root term.
 *
 * Mirrors the DEREF macro in GNU Prolog (wam_inst.h:447) and
 * MachineState::deref in Scryer (machine_state_impl.rs:87).
 * Returns a borrowed reference.
 */
static PyObject *
var_deref(PyObject *term)
{
    while (Var_Check(term)) {
        VarObject *v = Var_CAST(term);
        if (v->binding == NULL)
            return term;      /* unbound — stop */
        term = v->binding;    /* follow chain */
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
    if (self != NULL) {
        self->binding = NULL;
        self->var_id  = g_next_var_id++;
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

    /* Bound: show id and value */
    PyObject *r = PyObject_Repr(root);
    if (!r) return NULL;
    PyObject *res = PyUnicode_FromFormat("Var(_%llu=%U)",
                                         (unsigned long long)self->var_id, r);
    Py_DECREF(r);
    return res;
}

static PyObject *
Var_get_is_bound(VarObject *self, void *closure)
{
    (void)closure;
    /* True if this variable has any binding (even to another Var).
     * Use is_var() to test whether a term dereferences to an unbound variable. */
    return PyBool_FromLong(self->binding != NULL);
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
    {"is_bound",
     (getter)Var_get_is_bound, NULL,
     "True if this variable has been bound to a value.", NULL},
    {"value",
     (getter)Var_get_value, NULL,
     "The dereferenced value.  Returns self if unbound.", NULL},
    {"_id",
     (getter)Var_get_id, NULL,
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
        "Test with ``is_bound`` or ``logicvars.is_var()``.\n"
        "Read the bound value with the ``value`` property.\n"
        "\n"
        "Variables are ordered by creation time (``_id``); in a var-var\n"
        "unification the newer variable is bound to the older one, following\n"
        "the convention used by GNU Prolog and Scryer Prolog.\n"
    ),
    .tp_basicsize = sizeof(VarObject),
    .tp_itemsize  = 0,
    .tp_flags     = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_HAVE_GC,
    .tp_new       = Var_new,
    .tp_dealloc   = (destructor)Var_dealloc,
    .tp_traverse  = (traverseproc)Var_traverse,
    .tp_clear     = (inquiry)Var_clear,
    .tp_repr      = (reprfunc)Var_repr,
    .tp_getset    = Var_getset,
};


/* ================================================================
 * Trail type
 *
 * Records variable bindings so they can be undone (backtracking).
 *
 * Each entry stores a (var, old_binding) pair where old_binding is
 * the value of var->binding *before* the bind, so undo can restore it.
 * NULL old_binding means the variable was unbound before binding.
 *
 * Mirrors the trail Vec<TrailEntry> in Scryer (machine_state.rs) and
 * the TR stack in GNU Prolog, but without the WAM high-water-mark
 * optimisation — we always trail every binding.
 * ================================================================ */

typedef struct {
    VarObject *var;        /* the variable that was bound  (owned ref) */
    PyObject  *old_value;  /* binding before bind          (owned ref, NULL = unbound) */
} TrailEntry;

struct TrailObject {
    PyObject_HEAD
    TrailEntry *entries;
    Py_ssize_t  length;
    Py_ssize_t  capacity;
};

static PyObject *
Trail_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
        return NULL;

    TrailObject *self = (TrailObject *)PyObject_GC_New(TrailObject, type);
    if (self) {
        self->entries  = NULL;
        self->length   = 0;
        self->capacity = 0;
    }
    PyObject_GC_Track(self);
    return (PyObject *)self;
}

static void
Trail_dealloc(TrailObject *self)
{
    PyObject_GC_UnTrack(self);
    /* Release refs without restoring bindings (the vars may be dead). */
    for (Py_ssize_t i = 0; i < self->length; i++) {
        Py_DECREF(self->entries[i].var);
        Py_XDECREF(self->entries[i].old_value);
    }
    PyMem_Free(self->entries);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
Trail_traverse(TrailObject *self, visitproc visit, void *arg)
{
    for (Py_ssize_t i = 0; i < self->length; i++) {
        Py_VISIT(self->entries[i].var);
        Py_VISIT(self->entries[i].old_value);
    }
    return 0;
}

static int
Trail_clear(TrailObject *self)
{
    Py_ssize_t len = self->length;
    self->length = 0;          /* prevent double-free if called re-entrantly */
    for (Py_ssize_t i = 0; i < len; i++) {
        Py_DECREF(self->entries[i].var);
        Py_XDECREF(self->entries[i].old_value);
    }
    return 0;
}

/*
 * trail_push — record var's current binding before overwriting it.
 *
 * Analogous to Trail_Push / Trail_UV in GNU Prolog (wam_inst.h:211,513)
 * and MachineState::trail() in Scryer (machine_state_impl.rs:100).
 *
 * Returns 0 on success, -1 with Python exception set on OOM.
 */
static int
trail_push(TrailObject *trail, VarObject *var)
{
    if (trail->length >= trail->capacity) {
        Py_ssize_t newcap = (trail->capacity == 0) ? 64 : trail->capacity * 2;
        TrailEntry *buf = (TrailEntry *)PyMem_Realloc(
            trail->entries, (size_t)newcap * sizeof(TrailEntry));
        if (!buf) { PyErr_NoMemory(); return -1; }
        trail->entries  = buf;
        trail->capacity = newcap;
    }
    /* Take ownership of references for the trail entry. */
    Py_INCREF(var);
    Py_XINCREF(var->binding);   /* may be NULL — Py_XINCREF handles that */
    trail->entries[trail->length].var       = var;
    trail->entries[trail->length].old_value = var->binding;
    trail->length++;
    return 0;
}

/*
 * trail_bind — bind var to value, recording the previous binding on trail.
 *
 * value must already be dereferenced (no raw Var with its own chain).
 * Returns 0 on success, -1 on OOM.
 *
 * Analogous to Bind_UV + Trail_UV in GNU Prolog and
 * MachineState::bind() in Scryer.
 */
static int
trail_bind(TrailObject *trail, VarObject *var, PyObject *value)
{
    if (trail_push(trail, var) < 0)
        return -1;

    Py_XDECREF(var->binding);
    Py_INCREF(value);
    var->binding = value;
    return 0;
}

/*
 * trail_undo_to — restore all bindings recorded after mark.
 *
 * Iterates trail entries in reverse order (newest first), exactly as
 * Scryer's unwind_trail (mod.rs:1194) and GNU Prolog's Pl_Untrail
 * (wam_inst.c:1730) do.  Each entry's old_value is transferred back to
 * var->binding; the trail entry's refs are released.
 */
static void
trail_undo_to(TrailObject *trail, Py_ssize_t mark)
{
    for (Py_ssize_t i = trail->length - 1; i >= mark; i--) {
        VarObject *var = trail->entries[i].var;
        PyObject  *old = trail->entries[i].old_value;
        Py_XDECREF(var->binding);
        var->binding = old;    /* transfer ownership: trail → var */
        Py_DECREF(var);        /* release trail's ref to var */
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
    Py_ssize_t mark = PyLong_AsSsize_t(arg);
    if (mark == -1 && PyErr_Occurred()) return NULL;
    if (mark < 0 || mark > self->length) {
        PyErr_SetString(PyExc_ValueError,
                        "trail mark out of range");
        return NULL;
    }
    trail_undo_to(self, mark);
    Py_RETURN_NONE;
}

static PyObject *
Trail_reset(TrailObject *self, PyObject *Py_UNUSED(args))
{
    trail_undo_to(self, 0);
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
     "Restore all variable bindings recorded after *mark* was taken.\n"
     "Processes entries in reverse chronological order."},
    {"reset", (PyCFunction)Trail_reset, METH_NOARGS,
     "reset()\n"
     "\n"
     "Undo every binding on this trail (equivalent to undo(0))."},
    {NULL, NULL, 0, NULL}
};

static PySequenceMethods Trail_as_sequence = {
    .sq_length = (lenfunc)Trail_sq_len,
};

static PyTypeObject TrailType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name      = "clausal.logic.variables.Trail",
    .tp_doc       = (
        "Trail for recording and undoing variable bindings.\n"
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
        "len(trail) returns the number of recorded bindings.\n"
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
 * Scryer's bind_with_occurs_check (unify.rs:459).
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
        return 1;           /* found it */

    if (Var_Check(term))
        return 0;           /* different unbound var */

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

    return 0;   /* atomic — can't contain a free variable */
}


/* ================================================================
 * Unification
 *
 * Structural unification following the standard Robinson algorithm.
 * Mirrors GNU Prolog's Pl_Unify (unify.c:49) and Scryer's
 * Unifier::unify_internal (unify.rs:357).
 *
 * Terms recognised:
 *   - Var  → follow chain, then bind if unbound
 *   - tuple → compound term; elements unified pairwise
 *   - list  → sequence; elements unified pairwise
 *   - anything else → atomic; compared with PyObject_RichCompareBool(==)
 *
 * Returns 1 (success), 0 (failure), -1 (Python exception).
 *
 * The `oc` flag enables the occurs check before each var-to-nonvar binding,
 * preventing creation of circular/rational-tree terms.
 * ================================================================ */

static int
do_unify(PyObject *t1, PyObject *t2, TrailObject *trail, int depth, int oc)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "unify: term nesting too deep");
        return -1;
    }

    /* Deref both — follow binding chains to find the representative. */
    t1 = var_deref(t1);
    t2 = var_deref(t2);

    /* Identical objects always unify (handles same unbound var, same atom, etc.) */
    if (t1 == t2)
        return 1;

    int t1v = Var_Check(t1);
    int t2v = Var_Check(t2);

    /* ---- Var-Var ---- */
    if (t1v && t2v) {
        VarObject *v1 = Var_CAST(t1), *v2 = Var_CAST(t2);
        /*
         * Age-ordered binding: bind the newer var (larger id) to the older
         * one.  Mirrors Scryer bind() (machine_state_impl.rs:192) and GNU
         * Prolog's "bind higher address to lower" convention in unify.c:68.
         * This keeps the older variable as the canonical representative,
         * which matters for efficient union-find behaviour.
         */
        VarObject *newer = (v1->var_id > v2->var_id) ? v1 : v2;
        VarObject *older = (v1->var_id > v2->var_id) ? v2 : v1;
        return trail_bind(trail, newer, (PyObject *)older) < 0 ? -1 : 1;
    }

    /* ---- Var-Term ---- */
    if (t1v) {
        if (oc) {
            int found = do_occurs_check(Var_CAST(t1), t2, 0);
            if (found < 0) return -1;
            if (found)     return 0;  /* would create cycle */
        }
        return trail_bind(trail, Var_CAST(t1), t2) < 0 ? -1 : 1;
    }
    if (t2v) {
        if (oc) {
            int found = do_occurs_check(Var_CAST(t2), t1, 0);
            if (found < 0) return -1;
            if (found)     return 0;
        }
        return trail_bind(trail, Var_CAST(t2), t1) < 0 ? -1 : 1;
    }

    /* ---- Both non-Var: structural comparison ---- */

    /* Tuples: treat as compound terms (functor/arity encoded by element 0). */
    if (PyTuple_Check(t1) && PyTuple_Check(t2)) {
        Py_ssize_t n = PyTuple_GET_SIZE(t1);
        if (n != PyTuple_GET_SIZE(t2)) return 0;
        /* Optimise last element with tail-call-like loop */
        for (Py_ssize_t i = 0; i < n - 1; i++) {
            int r = do_unify(PyTuple_GET_ITEM(t1, i),
                             PyTuple_GET_ITEM(t2, i),
                             trail, depth + 1, oc);
            if (r != 1) return r;
        }
        if (n == 0) return 1;
        /* Last element — tail position, one less stack frame needed */
        return do_unify(PyTuple_GET_ITEM(t1, n - 1),
                        PyTuple_GET_ITEM(t2, n - 1),
                        trail, depth + 1, oc);
    }

    /* Lists: elements unified pairwise, partial lists not supported here
     * (use tuples for structures with variable tails). */
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
        return do_unify(PyList_GET_ITEM(t1, n - 1),
                        PyList_GET_ITEM(t2, n - 1),
                        trail, depth + 1, oc);
    }

    /* Type mismatch for structured types */
    if (PyTuple_Check(t1) || PyList_Check(t1) ||
        PyTuple_Check(t2) || PyList_Check(t2))
        return 0;

    /* Atomic: compare by Python equality */
    int cmp = PyObject_RichCompareBool(t1, t2, Py_EQ);
    if (cmp < 0) return -1;
    return cmp;
}

/* Helper: undo trail from trail->length back to mark, used on failure. */
static void
undo_partial(TrailObject *trail, Py_ssize_t mark)
{
    trail_undo_to(trail, mark);
}


/* ================================================================
 * Module-level functions
 * ================================================================ */

/*
 * unify(t1, t2, trail) -> bool
 *
 * Try to unify terms t1 and t2.  On success, bindings are recorded on
 * trail.  On failure, any partial bindings are automatically rolled back
 * and False is returned — callers do NOT need to call trail.undo().
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
    TrailObject *trail = (TrailObject *)trail_obj;
    Py_ssize_t mark = trail->length;

    int result = do_unify(t1, t2, trail, 0, 0);
    if (result < 0) {
        undo_partial(trail, mark);
        return NULL;
    }
    if (!result) {
        undo_partial(trail, mark);
        Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
}

/*
 * unify_with_occurs_check(t1, t2, trail) -> bool
 *
 * Like unify() but performs the occurs check before each variable binding
 * to prevent creation of circular terms.  Slower but sound.
 *
 * Mirrors Pl_Unify_Occurs_Check in GNU Prolog and
 * CompositeUnifierForOccursCheck in Scryer.
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
    TrailObject *trail = (TrailObject *)trail_obj;
    Py_ssize_t mark = trail->length;

    int result = do_unify(t1, t2, trail, 0, 1);
    if (result < 0) {
        undo_partial(trail, mark);
        return NULL;
    }
    if (!result) {
        undo_partial(trail, mark);
        Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
}

/*
 * deref(term) -> term
 *
 * Follow the variable binding chain one level at a time until an unbound
 * variable or a non-variable is reached.  Returns the root of the chain.
 */
static PyObject *
py_deref(PyObject *Py_UNUSED(module), PyObject *arg)
{
    PyObject *result = var_deref(arg);
    Py_INCREF(result);
    return result;
}

/*
 * walk(term) -> term
 *
 * Deeply dereference a term: recursively replace all bound variables with
 * their values throughout the term structure (tuples and lists are rebuilt).
 * Unbound variables are left in place.
 *
 * Returns a new object (or the original with an incremented refcount for
 * atomic types).  Does not modify the original term.
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
        /* Unbound variable — return as-is */
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
            PyTuple_SET_ITEM(result, i, elem);   /* steals ref */
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
            PyList_SET_ITEM(result, i, elem);    /* steals ref */
        }
        return result;
    }

    /* Atomic or unknown container — return the dereferenced value as-is */
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
 *
 * Return True if term dereferences to an unbound Var.
 */
static PyObject *
py_is_var(PyObject *Py_UNUSED(module), PyObject *arg)
{
    PyObject *root = var_deref(arg);
    return PyBool_FromLong(Var_Check(root));
}

/*
 * occurs_check(var, term) -> bool
 *
 * Return True if var (or the variable it dereferences to) appears free
 * anywhere inside term.  Used to detect would-be circular bindings.
 *
 * Mirrors Check_If_Var_Occurs in GNU Prolog (unify.c:186).
 */
static PyObject *
py_occurs_check(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *var_obj, *term;
    if (!PyArg_ParseTuple(args, "OO", &var_obj, &term))
        return NULL;

    PyObject *root = var_deref(var_obj);
    if (!Var_Check(root))
        Py_RETURN_FALSE;   /* bound — not an unbound variable */

    int r = do_occurs_check(Var_CAST(root), term, 0);
    if (r < 0) return NULL;
    return PyBool_FromLong(r);
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
     "Returns False on failure; any partial bindings made during the attempt\n"
     "are automatically rolled back — callers do not need to call undo().\n"
     "\n"
     "Terms can be:\n"
     "  - ``Var`` — an unbound logic variable\n"
     "  - tuple  — compound term; elements unified pairwise\n"
     "  - list   — sequence; elements unified pairwise\n"
     "  - anything else — atomic; compared with ``==``\n"},
    {"unify_with_occurs_check", py_unify_with_occurs_check, METH_VARARGS,
     "unify_with_occurs_check(t1, t2, trail) -> bool\n"
     "\n"
     "Like unify() but performs the occurs check before each variable\n"
     "binding.  Prevents creation of circular/infinite terms at the cost\n"
     "of additional traversal."},
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
     "Return True if *term* dereferences to an unbound Var."},
    {"occurs_check", py_occurs_check, METH_VARARGS,
     "occurs_check(var, term) -> bool\n"
     "\n"
     "Return True if *var* appears free inside *term*.\n"
     "Used to guard against circular unification."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_variables",
    "Logic variables with trail-based backtracking.\n"
    "\n"
    "Implements Prolog-style unification and deterministic backtracking\n"
    "without a Warren Abstract Machine.\n"
    "\n"
    "Studied implementations: GNU Prolog (wam_inst.h / unify.c) and\n"
    "Scryer Prolog (machine_state_impl.rs / unify.rs).\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__variables(void)
{
    if (PyType_Ready(&VarType)   < 0) return NULL;
    if (PyType_Ready(&TrailType) < 0) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

    Py_INCREF(&VarType);
    if (PyModule_AddObject(m, "Var", (PyObject *)&VarType) < 0)
        goto error;

    Py_INCREF(&TrailType);
    if (PyModule_AddObject(m, "Trail", (PyObject *)&TrailType) < 0)
        goto error;

    return m;

error:
    Py_DECREF(m);
    return NULL;
}
