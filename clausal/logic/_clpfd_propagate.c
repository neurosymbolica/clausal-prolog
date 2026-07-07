/*
 * _clpfd_propagate.c — C-accelerated CLP(FD) constraint propagation.
 *
 * Tiers 2-4: narrowing, constraint types, public API, and fd_hook.
 * Uses cached function pointers from _variables and direct domain ops
 * from the shared header _clpfd_domain_ops.h.
 */

#include "_clpfd_domain_ops.h"
#include <structmember.h>

/* ================================================================
 * Cached references (set during module init)
 * ================================================================ */

/* From clausal.logic.variables */
static PyObject *fn_deref  = NULL;
static PyObject *fn_is_var = NULL;
static PyObject *fn_unify  = NULL;
static PyObject *fn_put_attr = NULL;
static PyObject *fn_get_attr = NULL;
static PyObject *fn_register_attr_hook = NULL;

/* From clausal.logic.clpfd (Python-level helpers) */
static PyObject *fn_expr_domain = NULL;
static PyObject *fn_resolve = NULL;
static PyObject *fn_eval_ground = NULL;
static PyObject *fn_any_real = NULL;
static PyObject *fn_both_ground = NULL;
static PyObject *fn_collect_constraint_vars = NULL;
static PyObject *fn_collect_vars_from = NULL;

/* Bignum-fallback propagate helpers (Slice 3 of clpz_bignum.md) — invoked
 * when a constraint's operand domains contain bounds outside int64 range. */
static PyObject *fn_eq_propagate_bignum = NULL;
static PyObject *fn_ne_propagate_bignum = NULL;
static PyObject *fn_lt_propagate_bignum = NULL;
static PyObject *fn_le_propagate_bignum = NULL;
static PyObject *fn_sum_propagate_bignum = NULL;
static PyObject *fn_scalar_propagate_bignum = NULL;

/*
 * Convert a Python truth value returned by a bignum-fallback propagate
 * helper into the int contract used by the C propagators
 * (1 = success, 0 = wipeout, -1 = error).
 */
static inline int
result_to_int(PyObject *result)
{
    if (!result) return -1;
    int truth = PyObject_IsTrue(result);
    Py_DECREF(result);
    return truth;
}

/* Mixed rational/real check */
static PyObject *fn_check_no_mixed = NULL;

/* CLP(Q) dispatch (may be NULL if clpq not available) */
static PyObject *fn_any_rational = NULL;
static PyObject *fn_q_eq = NULL;
static PyObject *fn_q_ne = NULL;
static PyObject *fn_q_lt = NULL;
static PyObject *fn_q_le = NULL;

/* CLP(R) dispatch (may be NULL if clpr not available) */
static PyObject *fn_real_eq = NULL;
static PyObject *fn_real_ne = NULL;
static PyObject *fn_real_lt = NULL;
static PyObject *fn_real_le = NULL;
static PyObject *REAL_KEY = NULL;

/* CLP(R) sync helper (from clpfd.py) */
static PyObject *fn_sync_real = NULL;

/* Linearisation for fd_eq */
static PyObject *fn_linearise = NULL;
static PyObject *fn_ensure_fd_py = NULL;

/* Cached expression type objects for fd_eq isinstance check (may be NULL) */
static PyTypeObject *type_Add = NULL;
static PyTypeObject *type_Sub = NULL;
static PyTypeObject *type_Mult = NULL;
static PyTypeObject *type_Negate = NULL;

/* Cached constants */
static PyObject *FD_KEY_STR = NULL;  /* "fd" */
static PyObject *DEFAULT_DOMAIN = NULL;  /* ((-inf, +inf),) */

/* Forward declarations */
static PyTypeObject FDVarType;
static PyTypeObject ConstraintBaseType;
static PyTypeObject EqConstraintType;
static PyTypeObject NeConstraintType;
static PyTypeObject LtConstraintType;
static PyTypeObject LeConstraintType;
static PyTypeObject AllDiffConstraintType;
static PyTypeObject SumConstraintType;
static PyTypeObject ScalarProductConstraintType;

/* ================================================================
 * Inline call helpers
 * ================================================================ */

static inline PyObject *
call_deref(PyObject *term)
{
    return PyObject_CallOneArg(fn_deref, term);
}

static inline int
call_is_var(PyObject *term)
{
    PyObject *r = PyObject_CallOneArg(fn_is_var, term);
    if (!r) return -1;
    int result = PyObject_IsTrue(r);
    Py_DECREF(r);
    return result;
}

static inline int
call_unify(PyObject *t1, PyObject *t2, PyObject *trail)
{
    PyObject *r = PyObject_CallFunctionObjArgs(fn_unify, t1, t2, trail, NULL);
    if (!r) return -1;
    int result = PyObject_IsTrue(r);
    Py_DECREF(r);
    return result;
}

static inline int
call_put_attr(PyObject *var, PyObject *key, PyObject *value, PyObject *trail)
{
    PyObject *r = PyObject_CallFunctionObjArgs(fn_put_attr, var, key, value, trail, NULL);
    if (!r) return -1;
    int ok = PyObject_IsTrue(r);
    Py_DECREF(r);
    return ok;
}

static inline PyObject *
call_get_attr(PyObject *var, PyObject *key)
{
    return PyObject_CallFunctionObjArgs(fn_get_attr, var, key, NULL);
}

/* ================================================================
 * FDVar type — immutable (domain, constraints) pair
 * ================================================================ */

typedef struct {
    PyObject_HEAD
    PyObject *domain;       /* tuple of (lo, hi) tuples */
    PyObject *constraints;  /* tuple of Constraint objects */
} FDVarObject;

#define FDVar_Check(op) PyObject_TypeCheck(op, &FDVarType)

static PyObject *
FDVar_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"domain", "constraints", NULL};
    PyObject *domain;
    PyObject *constraints = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|O", kwlist,
                                     &domain, &constraints))
        return NULL;

    FDVarObject *self = (FDVarObject *)type->tp_alloc(type, 0);
    if (!self) return NULL;

    Py_INCREF(domain);
    self->domain = domain;

    if (constraints) {
        Py_INCREF(constraints);
        self->constraints = constraints;
    } else {
        self->constraints = PyTuple_New(0);
        if (!self->constraints) {
            Py_DECREF(self);
            return NULL;
        }
    }
    return (PyObject *)self;
}

static void
FDVar_dealloc(FDVarObject *self)
{
    Py_XDECREF(self->domain);
    Py_XDECREF(self->constraints);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
FDVar_traverse(FDVarObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->domain);
    Py_VISIT(self->constraints);
    return 0;
}

static int
FDVar_clear(FDVarObject *self)
{
    Py_CLEAR(self->domain);
    Py_CLEAR(self->constraints);
    return 0;
}

static PyMemberDef FDVar_members[] = {
    {"domain", T_OBJECT_EX, offsetof(FDVarObject, domain), READONLY, "Domain tuple"},
    {"constraints", T_OBJECT_EX, offsetof(FDVarObject, constraints), READONLY, "Constraint tuple"},
    {NULL}
};

static PyTypeObject FDVarType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "clausal.logic._clpfd_propagate.FDVar",
    .tp_basicsize = sizeof(FDVarObject),
    .tp_dealloc = (destructor)FDVar_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = (traverseproc)FDVar_traverse,
    .tp_clear = (inquiry)FDVar_clear,
    .tp_members = FDVar_members,
    .tp_new = FDVar_new,
};

/* ================================================================
 * Constraint tag enum (for fast dispatch in propagation loop)
 * ================================================================ */

typedef enum {
    CONSTRAINT_PYTHON = 0,
    CONSTRAINT_EQ = 1,
    CONSTRAINT_NE = 2,
    CONSTRAINT_LT = 3,
    CONSTRAINT_LE = 4,
    CONSTRAINT_ALLDIFF = 5,
    CONSTRAINT_SUM = 6,
    CONSTRAINT_SCALAR = 7,
} ConstraintTag;

/* ================================================================
 * Constraint base type
 * ================================================================ */

typedef struct {
    PyObject_HEAD
    ConstraintTag tag;
    PyObject *vars;  /* tuple of Var objects */
} ConstraintBaseObject;

#define ConstraintBase_Check(op) PyObject_TypeCheck(op, &ConstraintBaseType)

static void
ConstraintBase_dealloc(ConstraintBaseObject *self)
{
    Py_XDECREF(self->vars);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
ConstraintBase_traverse(ConstraintBaseObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->vars);
    return 0;
}

static int
ConstraintBase_clear(ConstraintBaseObject *self)
{
    Py_CLEAR(self->vars);
    return 0;
}

static PyMemberDef ConstraintBase_members[] = {
    {"vars", T_OBJECT_EX, offsetof(ConstraintBaseObject, vars), READONLY, "Constraint variables"},
    {NULL}
};

/* Forward: propagate method callable from Python */
static PyObject *Constraint_propagate_py(PyObject *self, PyObject *args);

static PyMethodDef ConstraintBase_methods[] = {
    {"propagate", Constraint_propagate_py, METH_VARARGS, "Propagate constraint."},
    {NULL}
};

static PyTypeObject ConstraintBaseType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "clausal.logic._clpfd_propagate.Constraint",
    .tp_basicsize = sizeof(ConstraintBaseObject),
    .tp_dealloc = (destructor)ConstraintBase_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    .tp_traverse = (traverseproc)ConstraintBase_traverse,
    .tp_clear = (inquiry)ConstraintBase_clear,
    .tp_members = ConstraintBase_members,
    .tp_methods = ConstraintBase_methods,
};

/* ================================================================
 * Binary constraint type (Eq, Ne, Lt, Le share this struct)
 * ================================================================ */

typedef struct {
    ConstraintBaseObject base;
    PyObject *lhs;
    PyObject *rhs;
} BinaryConstraintObject;

static void
BinaryConstraint_dealloc(BinaryConstraintObject *self)
{
    Py_XDECREF(self->lhs);
    Py_XDECREF(self->rhs);
    Py_XDECREF(self->base.vars);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
BinaryConstraint_traverse(BinaryConstraintObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->lhs);
    Py_VISIT(self->rhs);
    Py_VISIT(self->base.vars);
    return 0;
}

static int
BinaryConstraint_clear(BinaryConstraintObject *self)
{
    Py_CLEAR(self->lhs);
    Py_CLEAR(self->rhs);
    Py_CLEAR(self->base.vars);
    return 0;
}

static PyMemberDef BinaryConstraint_members[] = {
    {"lhs", T_OBJECT_EX, offsetof(BinaryConstraintObject, lhs), READONLY, "Left operand"},
    {"rhs", T_OBJECT_EX, offsetof(BinaryConstraintObject, rhs), READONLY, "Right operand"},
    {NULL}
};

/* Shared __new__ for binary constraints */
static PyObject *
BinaryConstraint_new(PyTypeObject *type, ConstraintTag tag, PyObject *args)
{
    PyObject *lhs, *rhs;
    if (!PyArg_ParseTuple(args, "OO", &lhs, &rhs))
        return NULL;

    BinaryConstraintObject *self = (BinaryConstraintObject *)type->tp_alloc(type, 0);
    if (!self) return NULL;

    self->base.tag = tag;
    Py_INCREF(lhs);
    self->lhs = lhs;
    Py_INCREF(rhs);
    self->rhs = rhs;

    /* Build vars tuple via _collect_constraint_vars(lhs, rhs) */
    PyObject *vars = PyObject_CallFunctionObjArgs(fn_collect_constraint_vars, lhs, rhs, NULL);
    if (!vars) { Py_DECREF(self); return NULL; }
    self->base.vars = vars;

    return (PyObject *)self;
}

/* ================================================================
 * AllDiff constraint type
 * ================================================================ */

typedef struct {
    ConstraintBaseObject base;
    PyObject *all_vars;  /* tuple */
} AllDiffConstraintObject;

static void
AllDiffConstraint_dealloc(AllDiffConstraintObject *self)
{
    Py_XDECREF(self->all_vars);
    Py_XDECREF(self->base.vars);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
AllDiffConstraint_traverse(AllDiffConstraintObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->all_vars);
    Py_VISIT(self->base.vars);
    return 0;
}

static int
AllDiffConstraint_clear(AllDiffConstraintObject *self)
{
    Py_CLEAR(self->all_vars);
    Py_CLEAR(self->base.vars);
    return 0;
}

static PyMemberDef AllDiffConstraint_members[] = {
    {"all_vars", T_OBJECT_EX, offsetof(AllDiffConstraintObject, all_vars), READONLY, "All variables"},
    {NULL}
};

/* ================================================================
 * Sum constraint type
 * ================================================================ */

typedef struct {
    ConstraintBaseObject base;
    PyObject *sum_vars;  /* tuple */
    PyObject *total;     /* Var or int */
} SumConstraintObject;

static void
SumConstraint_dealloc(SumConstraintObject *self)
{
    Py_XDECREF(self->sum_vars);
    Py_XDECREF(self->total);
    Py_XDECREF(self->base.vars);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
SumConstraint_traverse(SumConstraintObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->sum_vars);
    Py_VISIT(self->total);
    Py_VISIT(self->base.vars);
    return 0;
}

static int
SumConstraint_clear(SumConstraintObject *self)
{
    Py_CLEAR(self->sum_vars);
    Py_CLEAR(self->total);
    Py_CLEAR(self->base.vars);
    return 0;
}

static PyMemberDef SumConstraint_members[] = {
    {"sum_vars", T_OBJECT_EX, offsetof(SumConstraintObject, sum_vars), READONLY, "Sum variables"},
    {"total", T_OBJECT_EX, offsetof(SumConstraintObject, total), READONLY, "Total"},
    {NULL}
};

/* ================================================================
 * ScalarProduct constraint type
 * ================================================================ */

typedef struct {
    ConstraintBaseObject base;
    PyObject *coeffs;    /* tuple of ints */
    PyObject *sum_vars;  /* tuple */
    PyObject *total;     /* Var or int */
} ScalarProductConstraintObject;

static void
ScalarProductConstraint_dealloc(ScalarProductConstraintObject *self)
{
    Py_XDECREF(self->coeffs);
    Py_XDECREF(self->sum_vars);
    Py_XDECREF(self->total);
    Py_XDECREF(self->base.vars);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
ScalarProductConstraint_traverse(ScalarProductConstraintObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->coeffs);
    Py_VISIT(self->sum_vars);
    Py_VISIT(self->total);
    Py_VISIT(self->base.vars);
    return 0;
}

static int
ScalarProductConstraint_clear(ScalarProductConstraintObject *self)
{
    Py_CLEAR(self->coeffs);
    Py_CLEAR(self->sum_vars);
    Py_CLEAR(self->total);
    Py_CLEAR(self->base.vars);
    return 0;
}

static PyMemberDef ScalarProductConstraint_members[] = {
    {"coeffs", T_OBJECT_EX, offsetof(ScalarProductConstraintObject, coeffs), READONLY, "Coefficients"},
    {"sum_vars", T_OBJECT_EX, offsetof(ScalarProductConstraintObject, sum_vars), READONLY, "Sum variables"},
    {"total", T_OBJECT_EX, offsetof(ScalarProductConstraintObject, total), READONLY, "Total"},
    {NULL}
};

/* ================================================================
 * Helper: get domain for an expression (int, Var, or expr tree)
 * Inlines the fast paths, falls back to Python _expr_domain
 * ================================================================ */

static inline PyObject *
expr_domain_fast(PyObject *expr)
{
    /* Fast path 1: integer → singleton domain */
    if (PyLong_Check(expr) && !PyBool_Check(expr)) {
        int ov = 0;
        int64_t val = PyLong_AsLongLongAndOverflow(expr, &ov);
        if (ov != 0) {
            /* Bignum int — build a singleton domain via the Python
             * reference path which handles arbitrary-precision bounds. */
            PyObject *pair = PyTuple_Pack(2, expr, expr);
            if (!pair) return NULL;
            PyObject *result = PyTuple_Pack(1, pair);
            Py_DECREF(pair);
            return result;
        }
        if (val == -1 && PyErr_Occurred()) return NULL;
        return domain_from_range_i64(val, val);
    }

    /* Fast path 2: Var with FD attr → read domain directly */
    int isv = call_is_var(expr);
    if (isv < 0) return NULL;
    if (isv) {
        PyObject *state = call_get_attr(expr, FD_KEY_STR);
        if (!state) return NULL;
        if (state != Py_None) {
            PyObject *domain;
            if (FDVar_Check(state)) {
                domain = ((FDVarObject *)state)->domain;
            } else {
                domain = PyObject_GetAttrString(state, "domain");
                Py_DECREF(state);
                if (!domain) return NULL;
                return domain;  /* already a new ref */
            }
            Py_INCREF(domain);
            Py_DECREF(state);
            return domain;
        }
        Py_DECREF(state);
        /* No FD attr — return default unbounded domain */
        Py_INCREF(DEFAULT_DOMAIN);
        return DEFAULT_DOMAIN;
    }

    /* Slow path: call Python _expr_domain */
    /* We need to pass trail, but we don't have it here.
       The Python _expr_domain is called from propagate contexts. */
    return NULL;  /* Caller must use expr_domain_with_trail */
}

/* Full expr_domain with trail argument */
static inline PyObject *
expr_domain_with_trail(PyObject *expr, PyObject *trail)
{
    /* Try fast paths first */
    if (PyLong_Check(expr) && !PyBool_Check(expr)) {
        int ov = 0;
        int64_t val = PyLong_AsLongLongAndOverflow(expr, &ov);
        if (ov != 0) {
            /* Bignum int — build a singleton domain that preserves the
             * Python int.  Downstream callers detect bignum bounds via
             * has_bignum_bound() and dispatch to the Python helpers. */
            PyObject *pair = PyTuple_Pack(2, expr, expr);
            if (!pair) return NULL;
            PyObject *result = PyTuple_Pack(1, pair);
            Py_DECREF(pair);
            return result;
        }
        if (val == -1 && PyErr_Occurred()) return NULL;
        return domain_from_range_i64(val, val);
    }

    int isv = call_is_var(expr);
    if (isv < 0) return NULL;
    if (isv) {
        PyObject *state = call_get_attr(expr, FD_KEY_STR);
        if (!state) return NULL;
        if (state != Py_None) {
            PyObject *domain;
            if (FDVar_Check(state)) {
                domain = ((FDVarObject *)state)->domain;
            } else {
                domain = PyObject_GetAttrString(state, "domain");
                Py_DECREF(state);
                if (!domain) return NULL;
                return domain;
            }
            Py_INCREF(domain);
            Py_DECREF(state);
            return domain;
        }
        Py_DECREF(state);
        Py_INCREF(DEFAULT_DOMAIN);
        return DEFAULT_DOMAIN;
    }

    /* Fall back to Python _expr_domain(expr, trail) */
    return PyObject_CallFunctionObjArgs(fn_expr_domain, expr, trail, NULL);
}

/* ================================================================
 * Tier 2: Narrowing + Propagation infrastructure
 * ================================================================ */

/* Forward declarations */
static int c_propagate(PyObject *queue, PyObject *trail);
static int c_narrow(PyObject *var, PyObject *new_domain, PyObject *trail, PyObject *queue);

/*
 * c_ensure_fd(var, trail) -> FDVarObject* (new ref), or NULL on error
 * Gets or creates FD state for a variable.
 */
static FDVarObject *
c_ensure_fd(PyObject *var, PyObject *trail)
{
    PyObject *state = call_get_attr(var, FD_KEY_STR);
    if (!state) return NULL;
    if (state != Py_None) {
        if (FDVar_Check(state))
            return (FDVarObject *)state;
        /* A non-FDVar object under the engine-reserved "fd" key (only
         * reachable via a user put_attr(x, "fd", <obj>)) cannot be treated as
         * an FDVarObject: callers read ->domain / ->constraints at fixed
         * struct offsets, which is undefined behaviour for any other type.
         * Reject cleanly rather than crash (A06-F016). */
        Py_DECREF(state);
        PyErr_SetString(PyExc_TypeError,
                        "fd attribute must be an FDVar (engine-reserved key)");
        return NULL;
    }
    Py_DECREF(state);

    /* Create default FDVar */
    PyObject *args = PyTuple_Pack(1, DEFAULT_DOMAIN);
    if (!args) return NULL;
    FDVarObject *fdvar = (FDVarObject *)FDVar_new(&FDVarType, args, NULL);
    Py_DECREF(args);
    if (!fdvar) return NULL;

    if (call_put_attr(var, FD_KEY_STR, (PyObject *)fdvar, trail) < 0) {
        Py_DECREF(fdvar);
        return NULL;
    }
    return fdvar;
}

/*
 * c_narrow(var, new_domain, trail, queue) -> 1 success, 0 wipeout, -1 error
 */
static int
c_narrow(PyObject *var, PyObject *new_domain, PyObject *trail, PyObject *queue)
{
    /* Wipeout check */
    if (PyTuple_GET_SIZE(new_domain) == 0)
        return 0;

    /* Get old constraints */
    PyObject *old_state = call_get_attr(var, FD_KEY_STR);
    if (!old_state) return -1;

    PyObject *old_constraints;
    if (old_state != Py_None) {
        if (FDVar_Check(old_state))
            old_constraints = ((FDVarObject *)old_state)->constraints;
        else {
            old_constraints = PyObject_GetAttrString(old_state, "constraints");
            Py_DECREF(old_state);
            if (!old_constraints) return -1;
            /* old_constraints is now a new ref, handle below */
            goto have_constraints_newref;
        }
        Py_INCREF(old_constraints);
        Py_DECREF(old_state);
    } else {
        Py_DECREF(old_state);
        old_constraints = PyTuple_New(0);
        if (!old_constraints) return -1;
    }
    goto have_constraints;

have_constraints_newref:
have_constraints:
    ;

    /* Create new FDVar */
    PyObject *fdvar_args = PyTuple_Pack(2, new_domain, old_constraints);
    Py_DECREF(old_constraints);
    if (!fdvar_args) return -1;

    PyObject *new_state = FDVar_new(&FDVarType, fdvar_args, NULL);
    Py_DECREF(fdvar_args);
    if (!new_state) return -1;

    /* Store it */
    if (call_put_attr(var, FD_KEY_STR, new_state, trail) < 0) {
        Py_DECREF(new_state);
        return -1;
    }
    Py_DECREF(new_state);

    /* CLP(R) sync: delegate to Python _sync_real(var, fd_lo, fd_hi, trail)
     * so we never depend on the RealVar constructor signature.
     * Gate on REAL_KEY so we skip entirely when clpr isn't loaded.
     *
     * Bounds may be bignum (CLP(Z) propagation produces bounds outside
     * int64 range — e.g. Fib above N=92).  Convert directly via
     * PyFloat_AsDouble, which yields ±inf for sentinel floats and the
     * nearest double for any other Python int (including bignum).  CLP(R)
     * loses precision past 2^53 either way, so this is the right
     * representation. */
    if (REAL_KEY && fn_sync_real) {
        Py_ssize_t n = PyTuple_GET_SIZE(new_domain);
        PyObject *first_pair = PyTuple_GET_ITEM(new_domain, 0);
        PyObject *last_pair = PyTuple_GET_ITEM(new_domain, n - 1);
        PyObject *lo_obj = PyTuple_GET_ITEM(first_pair, 0);
        PyObject *hi_obj = PyTuple_GET_ITEM(last_pair, 1);
        double fd_lo_f = PyFloat_AsDouble(lo_obj);
        if (fd_lo_f == -1.0 && PyErr_Occurred()) return -1;
        double fd_hi_f = PyFloat_AsDouble(hi_obj);
        if (fd_hi_f == -1.0 && PyErr_Occurred()) return -1;
        PyObject *lo_py = PyFloat_FromDouble(fd_lo_f);
        PyObject *hi_py = PyFloat_FromDouble(fd_hi_f);
        if (!lo_py || !hi_py) {
            Py_XDECREF(lo_py);
            Py_XDECREF(hi_py);
            return -1;
        }
        PyObject *sr = PyObject_CallFunctionObjArgs(
            fn_sync_real, var, lo_py, hi_py, trail, NULL);
        Py_DECREF(lo_py);
        Py_DECREF(hi_py);
        if (!sr) return -1;
        int ok = PyObject_IsTrue(sr);
        Py_DECREF(sr);
        if (ok <= 0) return ok;  /* 0 = wipeout, -1 = error */
    }

    /* Singleton → unify */
    PyObject *val = domain_singleton_c(new_domain);
    if (!val) return -1;
    if (val != Py_None) {
        int ok = call_unify(var, val, trail);
        Py_DECREF(val);
        if (ok <= 0) return ok;
    } else {
        Py_DECREF(val);
    }

    /* Enqueue for propagation */
    if (PyList_Check(queue)) {
        if (PyList_Append(queue, var) < 0)
            return -1;
    } else {
        /* deque.append(var) */
        PyObject *r = PyObject_CallMethod(queue, "append", "O", var);
        if (!r) return -1;
        Py_DECREF(r);
    }

    return 1;
}

/*
 * c_narrow_if_changed — skip no-op narrows
 */
static int
c_narrow_if_changed(PyObject *var, PyObject *new_domain, PyObject *trail, PyObject *queue)
{
    PyObject *old_state = call_get_attr(var, FD_KEY_STR);
    if (!old_state) return -1;

    if (old_state != Py_None) {
        PyObject *old_domain;
        if (FDVar_Check(old_state))
            old_domain = ((FDVarObject *)old_state)->domain;
        else {
            old_domain = PyObject_GetAttrString(old_state, "domain");
            Py_DECREF(old_state);
            if (!old_domain) return -1;
            int eq = PyObject_RichCompareBool(old_domain, new_domain, Py_EQ);
            Py_DECREF(old_domain);
            if (eq < 0) return -1;
            if (eq) return 1;  /* no change */
            return c_narrow(var, new_domain, trail, queue);
        }
        int eq = PyObject_RichCompareBool(old_domain, new_domain, Py_EQ);
        Py_DECREF(old_state);
        if (eq < 0) return -1;
        if (eq) return 1;  /* no change */
    } else {
        Py_DECREF(old_state);
    }

    return c_narrow(var, new_domain, trail, queue);
}

/*
 * c_add_constraint — attach constraint to variable
 */
static int
c_add_constraint(PyObject *var, PyObject *constraint, PyObject *trail)
{
    /* Ensure FD state exists */
    FDVarObject *state = c_ensure_fd(var, trail);
    if (!state) return -1;

    /* Build new constraints tuple: old + (constraint,) */
    Py_ssize_t n = PyTuple_GET_SIZE(state->constraints);
    PyObject *new_constraints = PyTuple_New(n + 1);
    if (!new_constraints) { Py_DECREF(state); return -1; }
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *c = PyTuple_GET_ITEM(state->constraints, i);
        Py_INCREF(c);
        PyTuple_SET_ITEM(new_constraints, i, c);
    }
    Py_INCREF(constraint);
    PyTuple_SET_ITEM(new_constraints, n, constraint);

    /* Create new FDVar */
    PyObject *fdvar_args = PyTuple_Pack(2, state->domain, new_constraints);
    Py_DECREF(new_constraints);
    Py_DECREF(state);
    if (!fdvar_args) return -1;

    PyObject *new_state = FDVar_new(&FDVarType, fdvar_args, NULL);
    Py_DECREF(fdvar_args);
    if (!new_state) return -1;

    if (call_put_attr(var, FD_KEY_STR, new_state, trail) < 0) {
        Py_DECREF(new_state);
        return -1;
    }
    Py_DECREF(new_state);
    return 1;
}

/* Forward: constraint propagate dispatch */
static int constraint_propagate_c(PyObject *constraint, PyObject *trail, PyObject *queue);

/*
 * c_post_constraint — attach to all vars and run initial propagation
 */
static int
c_post_constraint(PyObject *constraint, PyObject *trail)
{
    PyObject *vars;
    if (ConstraintBase_Check(constraint))
        vars = ((ConstraintBaseObject *)constraint)->vars;
    else {
        vars = PyObject_GetAttrString(constraint, "vars");
        if (!vars) return -1;
    }

    int vars_is_newref = !ConstraintBase_Check(constraint);

    Py_ssize_t n = PyTuple_GET_SIZE(vars);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *v = PyTuple_GET_ITEM(vars, i);
        PyObject *dv = call_deref(v);
        if (!dv) { if (vars_is_newref) Py_DECREF(vars); return -1; }
        int isv = call_is_var(dv);
        if (isv < 0) { Py_DECREF(dv); if (vars_is_newref) Py_DECREF(vars); return -1; }
        if (isv) {
            if (c_add_constraint(dv, constraint, trail) < 0) {
                Py_DECREF(dv);
                if (vars_is_newref) Py_DECREF(vars);
                return -1;
            }
        }
        Py_DECREF(dv);
    }
    if (vars_is_newref) Py_DECREF(vars);

    /* Initial propagation with a fresh queue */
    PyObject *queue = PyList_New(0);
    if (!queue) return -1;

    int ok = constraint_propagate_c(constraint, trail, queue);
    if (ok <= 0) { Py_DECREF(queue); return ok; }

    ok = c_propagate(queue, trail);
    Py_DECREF(queue);
    return ok;
}

/*
 * c_propagate — AC-3 fixpoint loop
 */
static int
c_propagate(PyObject *queue, PyObject *trail)
{
    for (;;) {
        Py_ssize_t len;
        if (PyList_Check(queue)) {
            len = PyList_GET_SIZE(queue);
            if (len == 0) break;
        } else {
            len = PyObject_Length(queue);
            if (len < 0) return -1;
            if (len == 0) break;
        }

        /* Pop from end — O(1) for PyList.  AC-3 converges regardless of
         * traversal order (BFS vs DFS); popping from end avoids the O(n)
         * element shift that PyList_SetSlice(queue, 0, 1, NULL) incurs. */
        PyObject *var;
        if (PyList_Check(queue)) {
            var = PyList_GET_ITEM(queue, len - 1);
            Py_INCREF(var);
            if (PyList_SetSlice(queue, len - 1, len, NULL) < 0) {
                Py_DECREF(var);
                return -1;
            }
        } else {
            var = PyObject_CallMethod(queue, "popleft", NULL);
            if (!var) return -1;
        }

        PyObject *dvar = call_deref(var);
        Py_DECREF(var);
        if (!dvar) return -1;

        int isv = call_is_var(dvar);
        if (isv < 0) { Py_DECREF(dvar); return -1; }
        if (!isv) { Py_DECREF(dvar); continue; }

        PyObject *state_obj = call_get_attr(dvar, FD_KEY_STR);
        if (!state_obj) { Py_DECREF(dvar); return -1; }
        if (state_obj == Py_None) {
            Py_DECREF(state_obj);
            Py_DECREF(dvar);
            continue;
        }

        PyObject *constraints;
        int constraints_newref = 0;
        if (FDVar_Check(state_obj)) {
            constraints = ((FDVarObject *)state_obj)->constraints;
        } else {
            constraints = PyObject_GetAttrString(state_obj, "constraints");
            if (!constraints) {
                Py_DECREF(state_obj);
                Py_DECREF(dvar);
                return -1;
            }
            constraints_newref = 1;
        }

        Py_ssize_t nc = PyTuple_GET_SIZE(constraints);
        for (Py_ssize_t i = 0; i < nc; i++) {
            PyObject *c = PyTuple_GET_ITEM(constraints, i);
            int ok = constraint_propagate_c(c, trail, queue);
            if (ok <= 0) {
                if (constraints_newref) Py_DECREF(constraints);
                Py_DECREF(state_obj);
                Py_DECREF(dvar);
                return ok;
            }
        }

        if (constraints_newref) Py_DECREF(constraints);
        Py_DECREF(state_obj);
        Py_DECREF(dvar);
    }
    return 1;
}

/* ================================================================
 * Tier 3: Constraint propagation implementations
 * ================================================================ */

/*
 * ne_propagate — NeConstraint.propagate(trail, queue)
 */
static int
ne_propagate(BinaryConstraintObject *self, PyObject *trail, PyObject *queue)
{
    PyObject *lhs = call_deref(self->lhs);
    if (!lhs) return -1;
    PyObject *rhs = call_deref(self->rhs);
    if (!rhs) { Py_DECREF(lhs); return -1; }

    /* Aliased operands (e.g. unify merged the two vars after posting):
     * X != X can never hold — fail (A06-F010). */
    if (lhs == rhs) {
        Py_DECREF(lhs); Py_DECREF(rhs);
        return 0;
    }

    int l_isvar = call_is_var(lhs);
    if (l_isvar < 0) goto error;
    int r_isvar = call_is_var(rhs);
    if (r_isvar < 0) goto error;

    /* Bignum fallback: either operand is a bignum int, or a var's domain
     * has a bignum bound.  Slice 4 of clpz_bignum.md.  Otherwise
     * domain_remove_c / PyLong_AsLongLong below would overflow. */
    {
        int needs_bignum = is_bignum_int(lhs) || is_bignum_int(rhs);
        if (!needs_bignum && l_isvar) {
            PyObject *st = call_get_attr(lhs, FD_KEY_STR);
            if (!st) goto error;
            if (st != Py_None) {
                PyObject *dom = FDVar_Check(st)
                    ? ((FDVarObject *)st)->domain
                    : PyObject_GetAttrString(st, "domain");
                if (!dom) { Py_DECREF(st); goto error; }
                needs_bignum = has_bignum_bound(dom);
                if (!FDVar_Check(st)) Py_DECREF(dom);
            }
            Py_DECREF(st);
        }
        if (!needs_bignum && r_isvar) {
            PyObject *st = call_get_attr(rhs, FD_KEY_STR);
            if (!st) goto error;
            if (st != Py_None) {
                PyObject *dom = FDVar_Check(st)
                    ? ((FDVarObject *)st)->domain
                    : PyObject_GetAttrString(st, "domain");
                if (!dom) { Py_DECREF(st); goto error; }
                needs_bignum = has_bignum_bound(dom);
                if (!FDVar_Check(st)) Py_DECREF(dom);
            }
            Py_DECREF(st);
        }
        if (needs_bignum) {
            Py_DECREF(lhs); Py_DECREF(rhs);
            PyObject *result = PyObject_CallFunctionObjArgs(
                fn_ne_propagate_bignum,
                self->lhs, self->rhs, trail, queue, NULL);
            return result_to_int(result);
        }
    }

    /* Both ground */
    if (!l_isvar && !r_isvar) {
        /* Evaluate expression operands (e.g. Add(X, 1)) before comparing:
         * a structural compare of the expression node against an int is
         * always "different" and would wrongly satisfy the constraint
         * (A06-F001).  Plain ints skip the eval. */
        PyObject *lv = lhs, *rv = rhs;
        int owns_lv = 0, owns_rv = 0;
        if (!PyLong_Check(lhs)) {
            lv = PyObject_CallOneArg(fn_eval_ground, lhs);
            if (!lv) goto error;
            owns_lv = 1;
        }
        if (!PyLong_Check(rhs)) {
            rv = PyObject_CallOneArg(fn_eval_ground, rhs);
            if (!rv) { if (owns_lv) Py_DECREF(lv); goto error; }
            owns_rv = 1;
        }
        if (lv == Py_None || rv == Py_None) {
            /* An expression still has unbound vars — keep pending. */
            if (owns_lv) Py_DECREF(lv);
            if (owns_rv) Py_DECREF(rv);
            Py_DECREF(lhs); Py_DECREF(rhs);
            return 1;
        }
        int eq = PyObject_RichCompareBool(lv, rv, Py_NE);
        if (owns_lv) Py_DECREF(lv);
        if (owns_rv) Py_DECREF(rv);
        Py_DECREF(lhs); Py_DECREF(rhs);
        return eq < 0 ? -1 : eq;
    }

    /* lhs ground int, rhs var */
    if (!l_isvar && PyLong_Check(lhs) && r_isvar) {
        PyObject *state = call_get_attr(rhs, FD_KEY_STR);
        if (!state) goto error;
        if (state != Py_None) {
            PyObject *domain;
            if (FDVar_Check(state))
                domain = ((FDVarObject *)state)->domain;
            else {
                domain = PyObject_GetAttrString(state, "domain");
                Py_DECREF(state);
                if (!domain) goto error;
                int64_t val = PyLong_AsLongLong(lhs);
                if (val == -1 && PyErr_Occurred()) { Py_DECREF(domain); goto error; }
                PyObject *new_d = domain_remove_c(domain, val);
                Py_DECREF(domain);
                Py_DECREF(lhs); Py_DECREF(rhs);
                if (!new_d) return -1;
                int ok = c_narrow_if_changed(rhs, new_d, trail, queue);
                Py_DECREF(new_d);
                return ok;
            }
            int64_t val = PyLong_AsLongLong(lhs);
            if (val == -1 && PyErr_Occurred()) { Py_DECREF(state); goto error; }
            PyObject *new_d = domain_remove_c(domain, val);
            Py_DECREF(state);
            Py_DECREF(lhs); Py_DECREF(rhs);
            if (!new_d) return -1;
            int ok = c_narrow_if_changed(rhs, new_d, trail, queue);
            Py_DECREF(new_d);
            return ok;
        }
        Py_DECREF(state);
    }

    /* rhs ground int, lhs var */
    if (!r_isvar && PyLong_Check(rhs) && l_isvar) {
        PyObject *state = call_get_attr(lhs, FD_KEY_STR);
        if (!state) goto error;
        if (state != Py_None) {
            PyObject *domain;
            if (FDVar_Check(state))
                domain = ((FDVarObject *)state)->domain;
            else {
                domain = PyObject_GetAttrString(state, "domain");
                Py_DECREF(state);
                if (!domain) goto error;
                int64_t val = PyLong_AsLongLong(rhs);
                if (val == -1 && PyErr_Occurred()) { Py_DECREF(domain); goto error; }
                PyObject *new_d = domain_remove_c(domain, val);
                Py_DECREF(domain);
                Py_DECREF(lhs); Py_DECREF(rhs);
                if (!new_d) return -1;
                int ok = c_narrow_if_changed(lhs, new_d, trail, queue);
                Py_DECREF(new_d);
                return ok;
            }
            int64_t val = PyLong_AsLongLong(rhs);
            if (val == -1 && PyErr_Occurred()) { Py_DECREF(state); goto error; }
            PyObject *new_d = domain_remove_c(domain, val);
            Py_DECREF(state);
            Py_DECREF(lhs); Py_DECREF(rhs);
            if (!new_d) return -1;
            int ok = c_narrow_if_changed(lhs, new_d, trail, queue);
            Py_DECREF(new_d);
            return ok;
        }
        Py_DECREF(state);
    }

    /* Both vars — check singletons */
    if (l_isvar && r_isvar) {
        PyObject *ls = call_get_attr(lhs, FD_KEY_STR);
        if (!ls) goto error;
        PyObject *rs = call_get_attr(rhs, FD_KEY_STR);
        if (!rs) { Py_DECREF(ls); goto error; }
        if (ls != Py_None && rs != Py_None) {
            PyObject *ld, *rd;
            if (FDVar_Check(ls)) ld = ((FDVarObject *)ls)->domain;
            else {
                ld = PyObject_GetAttrString(ls, "domain");
                if (!ld) { Py_DECREF(ls); Py_DECREF(rs); goto error; }
            }
            if (FDVar_Check(rs)) rd = ((FDVarObject *)rs)->domain;
            else {
                rd = PyObject_GetAttrString(rs, "domain");
                if (!rd) {
                    if (!FDVar_Check(ls)) Py_DECREF(ld);
                    Py_DECREF(ls); Py_DECREF(rs);
                    goto error;
                }
            }

            PyObject *lv = domain_singleton_c(ld);
            PyObject *rv = domain_singleton_c(rd);
            if (!FDVar_Check(ls)) Py_DECREF(ld);
            if (!FDVar_Check(rs)) Py_DECREF(rd);
            if (!lv || !rv) {
                Py_XDECREF(lv); Py_XDECREF(rv);
                Py_DECREF(ls); Py_DECREF(rs);
                goto error;
            }

            if (lv != Py_None && rv != Py_None) {
                int neq = PyObject_RichCompareBool(lv, rv, Py_NE);
                Py_DECREF(lv); Py_DECREF(rv);
                Py_DECREF(ls); Py_DECREF(rs);
                Py_DECREF(lhs); Py_DECREF(rhs);
                return neq < 0 ? -1 : neq;
            }
            if (lv != Py_None) {
                int64_t val = PyLong_AsLongLong(lv);
                Py_DECREF(lv); Py_DECREF(rv);
                if (val == -1 && PyErr_Occurred()) { Py_DECREF(ls); Py_DECREF(rs); goto error; }
                PyObject *r_domain;
                if (FDVar_Check(rs)) r_domain = ((FDVarObject *)rs)->domain;
                else {
                    r_domain = PyObject_GetAttrString(rs, "domain");
                    Py_DECREF(ls); Py_DECREF(rs);
                    if (!r_domain) goto error;
                    PyObject *new_d = domain_remove_c(r_domain, val);
                    Py_DECREF(r_domain);
                    Py_DECREF(lhs); Py_DECREF(rhs);
                    if (!new_d) return -1;
                    int ok = c_narrow_if_changed(rhs, new_d, trail, queue);
                    Py_DECREF(new_d);
                    return ok;
                }
                Py_DECREF(ls); Py_DECREF(rs);
                PyObject *new_d = domain_remove_c(r_domain, val);
                Py_DECREF(lhs); Py_DECREF(rhs);
                if (!new_d) return -1;
                int ok = c_narrow_if_changed(rhs, new_d, trail, queue);
                Py_DECREF(new_d);
                return ok;
            }
            if (rv != Py_None) {
                int64_t val = PyLong_AsLongLong(rv);
                Py_DECREF(lv); Py_DECREF(rv);
                if (val == -1 && PyErr_Occurred()) { Py_DECREF(ls); Py_DECREF(rs); goto error; }
                PyObject *l_domain;
                if (FDVar_Check(ls)) l_domain = ((FDVarObject *)ls)->domain;
                else {
                    l_domain = PyObject_GetAttrString(ls, "domain");
                    Py_DECREF(ls); Py_DECREF(rs);
                    if (!l_domain) goto error;
                    PyObject *new_d = domain_remove_c(l_domain, val);
                    Py_DECREF(l_domain);
                    Py_DECREF(lhs); Py_DECREF(rhs);
                    if (!new_d) return -1;
                    int ok = c_narrow_if_changed(lhs, new_d, trail, queue);
                    Py_DECREF(new_d);
                    return ok;
                }
                Py_DECREF(ls); Py_DECREF(rs);
                PyObject *new_d = domain_remove_c(l_domain, val);
                Py_DECREF(lhs); Py_DECREF(rhs);
                if (!new_d) return -1;
                int ok = c_narrow_if_changed(lhs, new_d, trail, queue);
                Py_DECREF(new_d);
                return ok;
            }
            Py_DECREF(lv); Py_DECREF(rv);
        }
        Py_DECREF(ls); Py_DECREF(rs);
    }

    Py_DECREF(lhs); Py_DECREF(rhs);
    return 1;

error:
    Py_DECREF(lhs); Py_DECREF(rhs);
    return -1;
}

/*
 * eq_propagate — EqConstraint.propagate(trail, queue)
 */
static int
eq_propagate(BinaryConstraintObject *self, PyObject *trail, PyObject *queue)
{
    PyObject *lhs = call_deref(self->lhs);
    if (!lhs) return -1;
    PyObject *rhs = call_deref(self->rhs);
    if (!rhs) { Py_DECREF(lhs); return -1; }

    PyObject *ld = expr_domain_with_trail(lhs, trail);
    if (!ld) { Py_DECREF(lhs); Py_DECREF(rhs); return -1; }
    PyObject *rd = expr_domain_with_trail(rhs, trail);
    if (!rd) { Py_DECREF(ld); Py_DECREF(lhs); Py_DECREF(rhs); return -1; }

    /* Bignum fallback: defer to Python helper when either operand domain has
     * bounds outside int64 range.  Slice 3 of clpz_bignum.md. */
    if (has_bignum_bound(ld) || has_bignum_bound(rd)) {
        Py_DECREF(ld); Py_DECREF(rd);
        Py_DECREF(lhs); Py_DECREF(rhs);
        PyObject *result = PyObject_CallFunctionObjArgs(
            fn_eq_propagate_bignum, self->lhs, self->rhs, trail, queue, NULL);
        return result_to_int(result);
    }

    PyObject *inter = domain_intersection_c(ld, rd);
    Py_DECREF(ld); Py_DECREF(rd);
    if (!inter) { Py_DECREF(lhs); Py_DECREF(rhs); return -1; }

    if (PyTuple_GET_SIZE(inter) == 0) {
        Py_DECREF(inter); Py_DECREF(lhs); Py_DECREF(rhs);
        return 0;
    }

    int l_isvar = call_is_var(lhs);
    if (l_isvar < 0) { Py_DECREF(inter); Py_DECREF(lhs); Py_DECREF(rhs); return -1; }
    if (l_isvar) {
        int ok = c_narrow_if_changed(lhs, inter, trail, queue);
        if (ok <= 0) { Py_DECREF(inter); Py_DECREF(lhs); Py_DECREF(rhs); return ok; }
    }

    int r_isvar = call_is_var(rhs);
    if (r_isvar < 0) { Py_DECREF(inter); Py_DECREF(lhs); Py_DECREF(rhs); return -1; }
    if (r_isvar) {
        int ok = c_narrow_if_changed(rhs, inter, trail, queue);
        if (ok <= 0) { Py_DECREF(inter); Py_DECREF(lhs); Py_DECREF(rhs); return ok; }
    }

    Py_DECREF(inter); Py_DECREF(lhs); Py_DECREF(rhs);
    return 1;
}

/*
 * lt_propagate — LtConstraint.propagate(trail, queue)
 * X < Y: X's max < max(Y), Y's min > min(X)
 */
static int
lt_propagate(BinaryConstraintObject *self, PyObject *trail, PyObject *queue)
{
    PyObject *lhs = call_deref(self->lhs);
    if (!lhs) return -1;
    PyObject *rhs = call_deref(self->rhs);
    if (!rhs) { Py_DECREF(lhs); return -1; }

    PyObject *ld = expr_domain_with_trail(lhs, trail);
    if (!ld) goto error;
    PyObject *rd = expr_domain_with_trail(rhs, trail);
    if (!rd) { Py_DECREF(ld); goto error; }

    if (PyTuple_GET_SIZE(ld) == 0 || PyTuple_GET_SIZE(rd) == 0) {
        Py_DECREF(ld); Py_DECREF(rd); Py_DECREF(lhs); Py_DECREF(rhs);
        return 0;
    }

    /* Bignum fallback: defer to Python helper when either operand domain has
     * bounds outside int64 range.  Slice 3 of clpz_bignum.md. */
    if (has_bignum_bound(ld) || has_bignum_bound(rd)) {
        Py_DECREF(ld); Py_DECREF(rd);
        Py_DECREF(lhs); Py_DECREF(rhs);
        PyObject *result = PyObject_CallFunctionObjArgs(
            fn_lt_propagate_bignum, self->lhs, self->rhs, trail, queue, NULL);
        return result_to_int(result);
    }

    int64_t ld_min, ld_max, rd_min, rd_max;
    if (domain_min_i64(ld, &ld_min) < 0 || domain_max_i64(ld, &ld_max) < 0 ||
        domain_min_i64(rd, &rd_min) < 0 || domain_max_i64(rd, &rd_max) < 0) {
        Py_DECREF(ld); Py_DECREF(rd); goto error;
    }

    /* X < Y → X upper bound = max(Y) - 1 */
    int64_t new_l_hi = (rd_max == INT64_MAX) ? INT64_MAX : rd_max - 1;
    /* Y lower bound = min(X) + 1 */
    int64_t new_r_lo = (ld_min == INT64_MIN) ? INT64_MIN : ld_min + 1;

    PyObject *new_ld = domain_remove_above_c(ld, new_l_hi);
    if (!new_ld) { Py_DECREF(ld); Py_DECREF(rd); goto error; }
    PyObject *new_rd = domain_remove_below_c(rd, new_r_lo);
    if (!new_rd) { Py_DECREF(new_ld); Py_DECREF(ld); Py_DECREF(rd); goto error; }

    Py_DECREF(ld); Py_DECREF(rd);

    if (PyTuple_GET_SIZE(new_ld) == 0 || PyTuple_GET_SIZE(new_rd) == 0) {
        Py_DECREF(new_ld); Py_DECREF(new_rd);
        Py_DECREF(lhs); Py_DECREF(rhs);
        return 0;
    }

    int l_isvar = call_is_var(lhs);
    if (l_isvar < 0) { Py_DECREF(new_ld); Py_DECREF(new_rd); goto error; }
    if (l_isvar) {
        int ok = c_narrow_if_changed(lhs, new_ld, trail, queue);
        if (ok <= 0) { Py_DECREF(new_ld); Py_DECREF(new_rd); Py_DECREF(lhs); Py_DECREF(rhs); return ok; }
    } else {
        /* Ground lhs: check ld_min < rd_max */
        if (ld_min >= rd_max) {
            Py_DECREF(new_ld); Py_DECREF(new_rd); Py_DECREF(lhs); Py_DECREF(rhs);
            return 0;
        }
    }

    int r_isvar = call_is_var(rhs);
    if (r_isvar < 0) { Py_DECREF(new_ld); Py_DECREF(new_rd); goto error; }
    if (r_isvar) {
        int ok = c_narrow_if_changed(rhs, new_rd, trail, queue);
        if (ok <= 0) { Py_DECREF(new_ld); Py_DECREF(new_rd); Py_DECREF(lhs); Py_DECREF(rhs); return ok; }
    }

    Py_DECREF(new_ld); Py_DECREF(new_rd);
    Py_DECREF(lhs); Py_DECREF(rhs);
    return 1;

error:
    Py_DECREF(lhs); Py_DECREF(rhs);
    return -1;
}

/*
 * le_propagate — LeConstraint.propagate(trail, queue)
 * X <= Y
 */
static int
le_propagate(BinaryConstraintObject *self, PyObject *trail, PyObject *queue)
{
    PyObject *lhs = call_deref(self->lhs);
    if (!lhs) return -1;
    PyObject *rhs = call_deref(self->rhs);
    if (!rhs) { Py_DECREF(lhs); return -1; }

    PyObject *ld = expr_domain_with_trail(lhs, trail);
    if (!ld) goto error;
    PyObject *rd = expr_domain_with_trail(rhs, trail);
    if (!rd) { Py_DECREF(ld); goto error; }

    if (PyTuple_GET_SIZE(ld) == 0 || PyTuple_GET_SIZE(rd) == 0) {
        Py_DECREF(ld); Py_DECREF(rd); Py_DECREF(lhs); Py_DECREF(rhs);
        return 0;
    }

    /* Bignum fallback: defer to Python helper when either operand domain has
     * bounds outside int64 range.  Slice 3 of clpz_bignum.md. */
    if (has_bignum_bound(ld) || has_bignum_bound(rd)) {
        Py_DECREF(ld); Py_DECREF(rd);
        Py_DECREF(lhs); Py_DECREF(rhs);
        PyObject *result = PyObject_CallFunctionObjArgs(
            fn_le_propagate_bignum, self->lhs, self->rhs, trail, queue, NULL);
        return result_to_int(result);
    }

    int64_t ld_min, ld_max_unused, rd_min_unused, rd_max;
    if (domain_min_i64(ld, &ld_min) < 0 || domain_max_i64(ld, &ld_max_unused) < 0 ||
        domain_min_i64(rd, &rd_min_unused) < 0 || domain_max_i64(rd, &rd_max) < 0) {
        Py_DECREF(ld); Py_DECREF(rd); goto error;
    }

    PyObject *new_ld = domain_remove_above_c(ld, rd_max);
    if (!new_ld) { Py_DECREF(ld); Py_DECREF(rd); goto error; }
    PyObject *new_rd = domain_remove_below_c(rd, ld_min);
    if (!new_rd) { Py_DECREF(new_ld); Py_DECREF(ld); Py_DECREF(rd); goto error; }

    Py_DECREF(ld); Py_DECREF(rd);

    if (PyTuple_GET_SIZE(new_ld) == 0 || PyTuple_GET_SIZE(new_rd) == 0) {
        Py_DECREF(new_ld); Py_DECREF(new_rd);
        Py_DECREF(lhs); Py_DECREF(rhs);
        return 0;
    }

    int l_isvar = call_is_var(lhs);
    if (l_isvar < 0) { Py_DECREF(new_ld); Py_DECREF(new_rd); goto error; }
    if (l_isvar) {
        int ok = c_narrow_if_changed(lhs, new_ld, trail, queue);
        if (ok <= 0) { Py_DECREF(new_ld); Py_DECREF(new_rd); Py_DECREF(lhs); Py_DECREF(rhs); return ok; }
    } else {
        if (ld_min > rd_max) {
            Py_DECREF(new_ld); Py_DECREF(new_rd); Py_DECREF(lhs); Py_DECREF(rhs);
            return 0;
        }
    }

    int r_isvar = call_is_var(rhs);
    if (r_isvar < 0) { Py_DECREF(new_ld); Py_DECREF(new_rd); goto error; }
    if (r_isvar) {
        int ok = c_narrow_if_changed(rhs, new_rd, trail, queue);
        if (ok <= 0) { Py_DECREF(new_ld); Py_DECREF(new_rd); Py_DECREF(lhs); Py_DECREF(rhs); return ok; }
    }

    Py_DECREF(new_ld); Py_DECREF(new_rd);
    Py_DECREF(lhs); Py_DECREF(rhs);
    return 1;

error:
    Py_DECREF(lhs); Py_DECREF(rhs);
    return -1;
}

/*
 * alldiff_propagate — AllDiffConstraint.propagate(trail, queue)
 */
static int
alldiff_propagate(AllDiffConstraintObject *self, PyObject *trail, PyObject *queue)
{
    PyObject *all_vars = self->all_vars;
    Py_ssize_t n = PyTuple_GET_SIZE(all_vars);

    /* Collect ground values */
    PyObject *ground_set = PySet_New(NULL);
    if (!ground_set) return -1;

    /* We'll store free vars in a temporary list */
    PyObject *free_list = PyList_New(0);
    if (!free_list) { Py_DECREF(ground_set); return -1; }

    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *v = PyTuple_GET_ITEM(all_vars, i);
        PyObject *dv = call_deref(v);
        if (!dv) goto ad_error;

        int isv = call_is_var(dv);
        if (isv < 0) { Py_DECREF(dv); goto ad_error; }

        if (isv) {
            if (PyList_Append(free_list, dv) < 0) { Py_DECREF(dv); goto ad_error; }
        } else if (PyLong_Check(dv)) {
            int already = PySet_Contains(ground_set, dv);
            if (already < 0) { Py_DECREF(dv); goto ad_error; }
            if (already) {
                Py_DECREF(dv); Py_DECREF(ground_set); Py_DECREF(free_list);
                return 0;  /* duplicate ground value */
            }
            if (PySet_Add(ground_set, dv) < 0) { Py_DECREF(dv); goto ad_error; }
        } else {
            Py_DECREF(dv); Py_DECREF(ground_set); Py_DECREF(free_list);
            return 0;  /* non-integer */
        }
        Py_DECREF(dv);
    }

    /* For each free var, remove all ground values */
    Py_ssize_t nfree = PyList_GET_SIZE(free_list);
    Py_ssize_t nground = PySet_GET_SIZE(ground_set);

    if (nground > 0) {
        /* Get ground values as a list for iteration */
        PyObject *gv_iter = PyObject_GetIter(ground_set);
        if (!gv_iter) goto ad_error;
        PyObject *gv_list = PySequence_List(ground_set);
        Py_DECREF(gv_iter);
        if (!gv_list) goto ad_error;

        for (Py_ssize_t i = 0; i < nfree; i++) {
            PyObject *v = PyList_GET_ITEM(free_list, i);
            PyObject *state = call_get_attr(v, FD_KEY_STR);
            if (!state) { Py_DECREF(gv_list); goto ad_error; }
            if (state == Py_None) { Py_DECREF(state); continue; }

            PyObject *domain;
            int domain_newref = 0;
            if (FDVar_Check(state))
                domain = ((FDVarObject *)state)->domain;
            else {
                domain = PyObject_GetAttrString(state, "domain");
                if (!domain) { Py_DECREF(state); Py_DECREF(gv_list); goto ad_error; }
                domain_newref = 1;
            }

            /* Remove each ground value */
            PyObject *new_d = domain;
            Py_INCREF(new_d);
            if (domain_newref) Py_DECREF(domain);

            for (Py_ssize_t j = 0; j < PyList_GET_SIZE(gv_list); j++) {
                PyObject *gv = PyList_GET_ITEM(gv_list, j);
                int64_t val = PyLong_AsLongLong(gv);
                if (val == -1 && PyErr_Occurred()) {
                    Py_DECREF(new_d); Py_DECREF(state); Py_DECREF(gv_list);
                    goto ad_error;
                }
                PyObject *tmp = domain_remove_c(new_d, val);
                Py_DECREF(new_d);
                if (!tmp) { Py_DECREF(state); Py_DECREF(gv_list); goto ad_error; }
                new_d = tmp;
            }

            Py_DECREF(state);
            int ok = c_narrow_if_changed(v, new_d, trail, queue);
            Py_DECREF(new_d);
            if (ok <= 0) { Py_DECREF(gv_list); Py_DECREF(ground_set); Py_DECREF(free_list); return ok; }
        }
        Py_DECREF(gv_list);
    }

    Py_DECREF(ground_set);
    Py_DECREF(free_list);
    return 1;

ad_error:
    Py_DECREF(ground_set);
    Py_DECREF(free_list);
    return -1;
}

/*
 * Helper: safe multiply handling 0 * inf → 0
 */
static inline double
safe_mult_d(double a, double b)
{
    if (a == 0.0 || b == 0.0) return 0.0;
    return a * b;
}

/* Exact integer floor/ceil division (C's / truncates toward zero); b != 0.
 * Callers guarantee |a| < 2^53 (the DOUBLE_ABS_SUM_LIMIT guard), so no
 * overflow.  Used for scalar_propagate's exact division (A06-F003). */
static inline int64_t
floor_div_i64(int64_t a, int64_t b)
{
    int64_t q = a / b, r = a % b;
    if (r != 0 && ((r < 0) != (b < 0))) q--;
    return q;
}
static inline int64_t
ceil_div_i64(int64_t a, int64_t b)
{
    int64_t q = a / b, r = a % b;
    if (r != 0 && ((r < 0) == (b < 0))) q++;
    return q;
}

/* Threshold past which IEEE 754 double loses integer precision.  Used by
 * sum_propagate / scalar_propagate to decide when to fall back to the
 * bignum-safe Python helper. */
#define DOUBLE_PRECISE_INT_LIMIT 9007199254740992.0 /* 2^53 */
/* Σ|finite bound| ceiling: if the sum of the absolute values of all finite
 * operand bounds stays under 2^52, then every partial sum AND every
 * back-substitution difference (total - other, bounded by 2·Σ|bound|) stays
 * under 2^53 and is represented exactly in double.  Above it, an intermediate
 * such as `total - other` can need >53 bits and round (ties-to-even), so we
 * hand off to the exact-integer Python helper (A06-F003). */
#define DOUBLE_ABS_SUM_LIMIT 4503599627370496.0 /* 2^52 */

/*
 * sum_propagate — SumConstraint.propagate(trail, queue)
 */
static int
sum_propagate(SumConstraintObject *self, PyObject *trail, PyObject *queue)
{
    Py_ssize_t nv = PyTuple_GET_SIZE(self->sum_vars);

    double min_sum = 0, max_sum = 0;
    /* Finite-only running sums plus counts of ±inf contributions, so a var's
     * "other side" bound (total minus every OTHER var) is finite whenever its
     * OWN domain is the sole infinite contributor.  The old subtraction trick
     * (max_sum - own_max) produced inf - inf = nan and skipped narrowing,
     * leaving output-mode vars unbounded (A06-F002). */
    double finite_hi_sum = 0, finite_lo_sum = 0;
    int pos_inf_count = 0, neg_inf_count = 0;
    double abs_bound = 0;  /* Σ|finite bound| — see DOUBLE_ABS_SUM_LIMIT */
    int needs_bignum = 0;
    for (Py_ssize_t i = 0; i < nv; i++) {
        PyObject *v = PyTuple_GET_ITEM(self->sum_vars, i);
        PyObject *dv = call_deref(v);
        if (!dv) return -1;
        PyObject *d = expr_domain_with_trail(dv, trail);
        Py_DECREF(dv);
        if (!d) return -1;
        if (PyTuple_GET_SIZE(d) == 0) { Py_DECREF(d); return 0; }

        if (has_bignum_bound(d)) { needs_bignum = 1; Py_DECREF(d); break; }

        int64_t lo, hi;
        if (domain_min_i64(d, &lo) < 0 || domain_max_i64(d, &hi) < 0) { Py_DECREF(d); return -1; }
        Py_DECREF(d);

        double lo_f = (lo == INT64_MIN) ? -HUGE_VAL : (double)lo;
        double hi_f = (hi == INT64_MAX) ? HUGE_VAL : (double)hi;
        min_sum += lo_f;
        max_sum += hi_f;
        if (hi_f == HUGE_VAL) pos_inf_count++; else { finite_hi_sum += hi_f; abs_bound += fabs(hi_f); }
        if (lo_f == -HUGE_VAL) neg_inf_count++; else { finite_lo_sum += lo_f; abs_bound += fabs(lo_f); }
    }

    /* Bignum fallback: any operand has bignum bounds, or the sum of absolute
     * finite bounds is large enough that an intermediate could lose integer
     * precision in double (A06-F003).  Subsumes the old aggregate check —
     * cancelling terms (e.g. -2^53 + [2^53, 2^53+2]) keep the aggregate small
     * yet still overflow 53 bits under back-substitution. */
    if (!needs_bignum && abs_bound >= DOUBLE_ABS_SUM_LIMIT) {
        needs_bignum = 1;
    }
    if (needs_bignum) {
        PyObject *result = PyObject_CallFunctionObjArgs(
            fn_sum_propagate_bignum,
            self->sum_vars, self->total, trail, queue, NULL);
        return result_to_int(result);
    }

    PyObject *total_d_expr = call_deref(self->total);
    if (!total_d_expr) return -1;
    PyObject *total_d = expr_domain_with_trail(total_d_expr, trail);
    if (!total_d) { Py_DECREF(total_d_expr); return -1; }

    /* Bignum fallback: total domain is bignum.  Same as the operand check
     * above but deferred until total_d is fetched. */
    if (has_bignum_bound(total_d)) {
        Py_DECREF(total_d); Py_DECREF(total_d_expr);
        PyObject *result = PyObject_CallFunctionObjArgs(
            fn_sum_propagate_bignum,
            self->sum_vars, self->total, trail, queue, NULL);
        return result_to_int(result);
    }

    /* Intersect total domain with [min_sum, max_sum] */
    int64_t ms_lo = (min_sum == -HUGE_VAL) ? INT64_MIN :
                    (min_sum >= (double)INT64_MAX) ? INT64_MAX : (int64_t)min_sum;
    int64_t ms_hi = (max_sum == HUGE_VAL) ? INT64_MAX :
                    (max_sum <= (double)INT64_MIN) ? INT64_MIN : (int64_t)max_sum;
    PyObject *range_d = domain_from_range_i64(ms_lo, ms_hi);
    if (!range_d) { Py_DECREF(total_d); Py_DECREF(total_d_expr); return -1; }

    PyObject *new_total_d = domain_intersection_c(total_d, range_d);
    Py_DECREF(total_d); Py_DECREF(range_d);
    if (!new_total_d) { Py_DECREF(total_d_expr); return -1; }
    if (PyTuple_GET_SIZE(new_total_d) == 0) {
        Py_DECREF(new_total_d); Py_DECREF(total_d_expr);
        return 0;
    }

    int t_isvar = call_is_var(total_d_expr);
    if (t_isvar < 0) { Py_DECREF(new_total_d); Py_DECREF(total_d_expr); return -1; }
    if (t_isvar) {
        int ok = c_narrow_if_changed(total_d_expr, new_total_d, trail, queue);
        if (ok <= 0) { Py_DECREF(new_total_d); Py_DECREF(total_d_expr); return ok; }
    }

    int64_t total_lo, total_hi;
    if (domain_min_i64(new_total_d, &total_lo) < 0 ||
        domain_max_i64(new_total_d, &total_hi) < 0) {
        Py_DECREF(new_total_d); Py_DECREF(total_d_expr);
        return -1;
    }
    double tlo = (total_lo == INT64_MIN) ? -HUGE_VAL : (double)total_lo;
    double thi = (total_hi == INT64_MAX) ? HUGE_VAL : (double)total_hi;
    Py_DECREF(new_total_d); Py_DECREF(total_d_expr);

    /* Narrow individual variables */
    for (Py_ssize_t i = 0; i < nv; i++) {
        PyObject *v = PyTuple_GET_ITEM(self->sum_vars, i);
        PyObject *dv = call_deref(v);
        if (!dv) return -1;
        int isv = call_is_var(dv);
        if (isv < 0) { Py_DECREF(dv); return -1; }
        if (!isv) { Py_DECREF(dv); continue; }

        PyObject *d = expr_domain_with_trail(dv, trail);
        if (!d) { Py_DECREF(dv); return -1; }

        int64_t v_lo_i, v_hi_i;
        if (domain_min_i64(d, &v_lo_i) < 0 || domain_max_i64(d, &v_hi_i) < 0) {
            Py_DECREF(d); Py_DECREF(dv); return -1;
        }
        double v_max_f = (v_hi_i == INT64_MAX) ? HUGE_VAL : (double)v_hi_i;
        double v_min_f = (v_lo_i == INT64_MIN) ? -HUGE_VAL : (double)v_lo_i;

        /* other_max = Σ_{j≠i} hi_j : +inf iff some OTHER var is +inf, else
         * the finite hi sum with var i's own finite hi removed (A06-F002). */
        int others_pos_inf = pos_inf_count - (v_max_f == HUGE_VAL ? 1 : 0);
        double other_max = (others_pos_inf > 0) ? HUGE_VAL
                         : finite_hi_sum - (v_max_f == HUGE_VAL ? 0.0 : v_max_f);
        int others_neg_inf = neg_inf_count - (v_min_f == -HUGE_VAL ? 1 : 0);
        double other_min = (others_neg_inf > 0) ? -HUGE_VAL
                         : finite_lo_sum - (v_min_f == -HUGE_VAL ? 0.0 : v_min_f);

        /* var_i ∈ [total_lo - other_max, total_hi - other_min].  An infinite
         * other-side bound leaves the corresponding var bound unconstrained. */
        double new_lo_f = (other_max == HUGE_VAL) ? -HUGE_VAL : (tlo - other_max);
        double new_hi_f = (other_min == -HUGE_VAL) ? HUGE_VAL : (thi - other_min);

        int64_t new_lo_i = (new_lo_f <= (double)INT64_MIN) ? INT64_MIN :
                           (new_lo_f >= (double)INT64_MAX) ? INT64_MAX : (int64_t)new_lo_f;
        int64_t new_hi_i = (new_hi_f >= (double)INT64_MAX) ? INT64_MAX :
                           (new_hi_f <= (double)INT64_MIN) ? INT64_MIN : (int64_t)new_hi_f;

        PyObject *range = domain_from_range_i64(new_lo_i, new_hi_i);
        if (!range) { Py_DECREF(d); Py_DECREF(dv); return -1; }
        PyObject *new_d = domain_intersection_c(d, range);
        Py_DECREF(d); Py_DECREF(range);
        if (!new_d) { Py_DECREF(dv); return -1; }

        if (PyTuple_GET_SIZE(new_d) == 0) {
            Py_DECREF(new_d); Py_DECREF(dv);
            return 0;
        }

        int ok = c_narrow_if_changed(dv, new_d, trail, queue);
        Py_DECREF(new_d); Py_DECREF(dv);
        if (ok <= 0) return ok;
    }

    return 1;
}

/*
 * scalar_propagate — ScalarProductConstraint.propagate(trail, queue)
 */
static int
scalar_propagate(ScalarProductConstraintObject *self, PyObject *trail, PyObject *queue)
{
    Py_ssize_t nv = PyTuple_GET_SIZE(self->sum_vars);

    double min_sum = 0, max_sum = 0;
    /* Finite-only running contribution sums plus ±inf counts, so a var's
     * "other side" is finite whenever its OWN contribution is the sole
     * infinite one (A06-F002 — see sum_propagate for the rationale). */
    double finite_cmax_sum = 0, finite_cmin_sum = 0;
    int cmax_pos_inf = 0, cmin_neg_inf = 0;
    double abs_bound = 0;  /* Σ|finite contribution| — see DOUBLE_ABS_SUM_LIMIT */
    int needs_bignum = 0;
    for (Py_ssize_t i = 0; i < nv; i++) {
        PyObject *v = PyTuple_GET_ITEM(self->sum_vars, i);
        PyObject *co = PyTuple_GET_ITEM(self->coeffs, i);
        if (is_bignum_int(co)) { needs_bignum = 1; break; }
        int co_overflow = 0;
        long long c_val = PyLong_AsLongLongAndOverflow(co, &co_overflow);
        if (co_overflow != 0) { needs_bignum = 1; break; }
        if (c_val == -1 && PyErr_Occurred()) return -1;
        double c = (double)c_val;

        PyObject *dv = call_deref(v);
        if (!dv) return -1;
        PyObject *d = expr_domain_with_trail(dv, trail);
        Py_DECREF(dv);
        if (!d) return -1;
        if (PyTuple_GET_SIZE(d) == 0) { Py_DECREF(d); return 0; }

        if (has_bignum_bound(d)) { needs_bignum = 1; Py_DECREF(d); break; }

        int64_t lo, hi;
        if (domain_min_i64(d, &lo) < 0 || domain_max_i64(d, &hi) < 0) { Py_DECREF(d); return -1; }
        Py_DECREF(d);

        double lo_f = (lo == INT64_MIN) ? -HUGE_VAL : (double)lo;
        double hi_f = (hi == INT64_MAX) ? HUGE_VAL : (double)hi;

        double contrib_min = (c >= 0) ? safe_mult_d(c, lo_f) : safe_mult_d(c, hi_f);
        double contrib_max = (c >= 0) ? safe_mult_d(c, hi_f) : safe_mult_d(c, lo_f);
        min_sum += contrib_min;
        max_sum += contrib_max;
        if (contrib_max == HUGE_VAL) cmax_pos_inf++; else { finite_cmax_sum += contrib_max; abs_bound += fabs(contrib_max); }
        if (contrib_min == -HUGE_VAL) cmin_neg_inf++; else { finite_cmin_sum += contrib_min; abs_bound += fabs(contrib_min); }
    }

    /* Bignum fallback: any operand/coefficient is bignum, or the sum of
     * absolute finite contributions is large enough that an intermediate
     * could lose integer precision in double (A06-F003). */
    if (!needs_bignum && abs_bound >= DOUBLE_ABS_SUM_LIMIT) {
        needs_bignum = 1;
    }
    if (needs_bignum) {
        PyObject *result = PyObject_CallFunctionObjArgs(
            fn_scalar_propagate_bignum,
            self->coeffs, self->sum_vars, self->total, trail, queue, NULL);
        return result_to_int(result);
    }

    PyObject *total_d_expr = call_deref(self->total);
    if (!total_d_expr) return -1;
    PyObject *total_d = expr_domain_with_trail(total_d_expr, trail);
    if (!total_d) { Py_DECREF(total_d_expr); return -1; }

    /* Bignum fallback: total domain bounds out of int64 range. */
    if (has_bignum_bound(total_d)) {
        Py_DECREF(total_d); Py_DECREF(total_d_expr);
        PyObject *result = PyObject_CallFunctionObjArgs(
            fn_scalar_propagate_bignum,
            self->coeffs, self->sum_vars, self->total, trail, queue, NULL);
        return result_to_int(result);
    }

    int64_t ms_lo = (min_sum == -HUGE_VAL) ? INT64_MIN :
                    (min_sum >= (double)INT64_MAX) ? INT64_MAX : (int64_t)min_sum;
    int64_t ms_hi = (max_sum == HUGE_VAL) ? INT64_MAX :
                    (max_sum <= (double)INT64_MIN) ? INT64_MIN : (int64_t)max_sum;
    PyObject *range_d = domain_from_range_i64(ms_lo, ms_hi);
    if (!range_d) { Py_DECREF(total_d); Py_DECREF(total_d_expr); return -1; }

    PyObject *new_total_d = domain_intersection_c(total_d, range_d);
    Py_DECREF(total_d); Py_DECREF(range_d);
    if (!new_total_d) { Py_DECREF(total_d_expr); return -1; }
    if (PyTuple_GET_SIZE(new_total_d) == 0) {
        Py_DECREF(new_total_d); Py_DECREF(total_d_expr);
        return 0;
    }

    int t_isvar = call_is_var(total_d_expr);
    if (t_isvar < 0) { Py_DECREF(new_total_d); Py_DECREF(total_d_expr); return -1; }
    if (t_isvar) {
        int ok = c_narrow_if_changed(total_d_expr, new_total_d, trail, queue);
        if (ok <= 0) { Py_DECREF(new_total_d); Py_DECREF(total_d_expr); return ok; }
    }

    int64_t total_lo, total_hi;
    if (domain_min_i64(new_total_d, &total_lo) < 0 ||
        domain_max_i64(new_total_d, &total_hi) < 0) {
        Py_DECREF(new_total_d); Py_DECREF(total_d_expr);
        return -1;
    }
    double tlo = (total_lo == INT64_MIN) ? -HUGE_VAL : (double)total_lo;
    double thi = (total_hi == INT64_MAX) ? HUGE_VAL : (double)total_hi;
    Py_DECREF(new_total_d); Py_DECREF(total_d_expr);

    for (Py_ssize_t i = 0; i < nv; i++) {
        PyObject *v = PyTuple_GET_ITEM(self->sum_vars, i);
        PyObject *co = PyTuple_GET_ITEM(self->coeffs, i);
        long long c_val = PyLong_AsLongLong(co);
        if (c_val == -1 && PyErr_Occurred()) return -1;
        double c = (double)c_val;
        if (c == 0) continue;

        PyObject *dv = call_deref(v);
        if (!dv) return -1;
        int isv = call_is_var(dv);
        if (isv < 0) { Py_DECREF(dv); return -1; }
        if (!isv) { Py_DECREF(dv); continue; }

        PyObject *d = expr_domain_with_trail(dv, trail);
        if (!d) { Py_DECREF(dv); return -1; }

        int64_t v_lo_i, v_hi_i;
        if (domain_min_i64(d, &v_lo_i) < 0 || domain_max_i64(d, &v_hi_i) < 0) {
            Py_DECREF(d); Py_DECREF(dv); return -1;
        }
        double v_lo = (v_lo_i == INT64_MIN) ? -HUGE_VAL : (double)v_lo_i;
        double v_hi = (v_hi_i == INT64_MAX) ? HUGE_VAL : (double)v_hi_i;

        double contrib_max = (c > 0) ? safe_mult_d(c, v_hi) : safe_mult_d(c, v_lo);
        double contrib_min = (c > 0) ? safe_mult_d(c, v_lo) : safe_mult_d(c, v_hi);
        /* Σ_{j≠i} of the min/max contributions, inf iff some OTHER var is the
         * infinite one (A06-F002). */
        int others_cmax_inf = cmax_pos_inf - (contrib_max == HUGE_VAL ? 1 : 0);
        double other_max = (others_cmax_inf > 0) ? HUGE_VAL
                         : finite_cmax_sum - (contrib_max == HUGE_VAL ? 0.0 : contrib_max);
        int others_cmin_inf = cmin_neg_inf - (contrib_min == -HUGE_VAL ? 1 : 0);
        double other_min = (others_cmin_inf > 0) ? -HUGE_VAL
                         : finite_cmin_sum - (contrib_min == -HUGE_VAL ? 0.0 : contrib_min);

        /* Bounds on c*var_i, guarding inf - inf.  With the DOUBLE_ABS_SUM_LIMIT
         * guard above, finite num_lo/num_hi are exact integers < 2^53. */
        double num_lo = (other_max == HUGE_VAL) ? -HUGE_VAL : (tlo - other_max);
        double num_hi = (other_min == -HUGE_VAL) ? HUGE_VAL : (thi - other_min);

        /* var_i lower = ceil(lo_num / c), upper = floor(hi_num / c), with the
         * numerator/operand ends swapped for c < 0.  Divide in int64 to avoid
         * float-division rounding near 2^53 (A06-F003). */
        double lo_num = (c_val > 0) ? num_lo : num_hi;
        double hi_num = (c_val > 0) ? num_hi : num_lo;

        int64_t new_lo_i, new_hi_i;
        if (lo_num == -HUGE_VAL || lo_num == HUGE_VAL)
            new_lo_i = INT64_MIN;   /* the infinite lo end always yields -inf */
        else
            new_lo_i = ceil_div_i64((int64_t)lo_num, c_val);

        if (hi_num == HUGE_VAL || hi_num == -HUGE_VAL)
            new_hi_i = INT64_MAX;   /* the infinite hi end always yields +inf */
        else
            new_hi_i = floor_div_i64((int64_t)hi_num, c_val);

        PyObject *range = domain_from_range_i64(new_lo_i, new_hi_i);
        if (!range) { Py_DECREF(d); Py_DECREF(dv); return -1; }
        PyObject *new_d = domain_intersection_c(d, range);
        Py_DECREF(d); Py_DECREF(range);
        if (!new_d) { Py_DECREF(dv); return -1; }

        if (PyTuple_GET_SIZE(new_d) == 0) {
            Py_DECREF(new_d); Py_DECREF(dv);
            return 0;
        }

        int ok = c_narrow_if_changed(dv, new_d, trail, queue);
        Py_DECREF(new_d); Py_DECREF(dv);
        if (ok <= 0) return ok;
    }

    return 1;
}

/* ================================================================
 * Constraint dispatch (tag-based)
 * ================================================================ */

static int
constraint_propagate_c(PyObject *constraint, PyObject *trail, PyObject *queue)
{
    if (ConstraintBase_Check(constraint)) {
        ConstraintBaseObject *cb = (ConstraintBaseObject *)constraint;
        switch (cb->tag) {
        case CONSTRAINT_NE:
            return ne_propagate((BinaryConstraintObject *)constraint, trail, queue);
        case CONSTRAINT_EQ:
            return eq_propagate((BinaryConstraintObject *)constraint, trail, queue);
        case CONSTRAINT_LT:
            return lt_propagate((BinaryConstraintObject *)constraint, trail, queue);
        case CONSTRAINT_LE:
            return le_propagate((BinaryConstraintObject *)constraint, trail, queue);
        case CONSTRAINT_ALLDIFF:
            return alldiff_propagate((AllDiffConstraintObject *)constraint, trail, queue);
        case CONSTRAINT_SUM:
            return sum_propagate((SumConstraintObject *)constraint, trail, queue);
        case CONSTRAINT_SCALAR:
            return scalar_propagate((ScalarProductConstraintObject *)constraint, trail, queue);
        default:
            break;
        }
    }

    /* Python constraint fallback */
    PyObject *result = PyObject_CallMethod(constraint, "propagate", "OO", trail, queue);
    if (!result) return -1;
    int ok = PyObject_IsTrue(result);
    Py_DECREF(result);
    return ok;
}

/* Python-callable propagate method for constraint types */
static PyObject *
Constraint_propagate_py(PyObject *self, PyObject *args)
{
    PyObject *trail, *queue;
    if (!PyArg_ParseTuple(args, "OO", &trail, &queue))
        return NULL;
    int ok = constraint_propagate_c(self, trail, queue);
    if (ok < 0) return NULL;
    if (ok == 0) Py_RETURN_FALSE;
    Py_RETURN_TRUE;
}

/* ================================================================
 * Type __new__ methods for each constraint type
 * ================================================================ */

static PyObject *
EqConstraint_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    return BinaryConstraint_new(type, CONSTRAINT_EQ, args);
}

static PyObject *
NeConstraint_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    return BinaryConstraint_new(type, CONSTRAINT_NE, args);
}

static PyObject *
LtConstraint_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    return BinaryConstraint_new(type, CONSTRAINT_LT, args);
}

static PyObject *
LeConstraint_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    return BinaryConstraint_new(type, CONSTRAINT_LE, args);
}

static PyObject *
AllDiffConstraint_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    PyObject *vars_tuple;
    if (!PyArg_ParseTuple(args, "O", &vars_tuple))
        return NULL;

    AllDiffConstraintObject *self = (AllDiffConstraintObject *)type->tp_alloc(type, 0);
    if (!self) return NULL;

    self->base.tag = CONSTRAINT_ALLDIFF;
    Py_INCREF(vars_tuple);
    self->all_vars = vars_tuple;
    Py_INCREF(vars_tuple);
    self->base.vars = vars_tuple;

    return (PyObject *)self;
}

static PyObject *
SumConstraint_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    PyObject *sum_vars, *total;
    if (!PyArg_ParseTuple(args, "OO", &sum_vars, &total))
        return NULL;

    SumConstraintObject *self = (SumConstraintObject *)type->tp_alloc(type, 0);
    if (!self) return NULL;

    self->base.tag = CONSTRAINT_SUM;
    Py_INCREF(sum_vars);
    self->sum_vars = sum_vars;
    Py_INCREF(total);
    self->total = total;

    /* Build vars: collect from sum_vars + total */
    PyObject *result_list = PyList_New(0);
    if (!result_list) { Py_DECREF(self); return NULL; }
    for (Py_ssize_t i = 0; i < PyTuple_GET_SIZE(sum_vars); i++) {
        PyObject *r = PyObject_CallFunctionObjArgs(fn_collect_vars_from,
            PyTuple_GET_ITEM(sum_vars, i), result_list, NULL);
        if (!r) { Py_DECREF(result_list); Py_DECREF(self); return NULL; }
        Py_DECREF(r);
    }
    PyObject *r = PyObject_CallFunctionObjArgs(fn_collect_vars_from, total, result_list, NULL);
    if (!r) { Py_DECREF(result_list); Py_DECREF(self); return NULL; }
    Py_DECREF(r);
    self->base.vars = PyList_AsTuple(result_list);
    Py_DECREF(result_list);
    if (!self->base.vars) { Py_DECREF(self); return NULL; }

    return (PyObject *)self;
}

static PyObject *
ScalarProductConstraint_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    (void)kwds;
    PyObject *coeffs, *sum_vars, *total;
    if (!PyArg_ParseTuple(args, "OOO", &coeffs, &sum_vars, &total))
        return NULL;

    ScalarProductConstraintObject *self = (ScalarProductConstraintObject *)type->tp_alloc(type, 0);
    if (!self) return NULL;

    self->base.tag = CONSTRAINT_SCALAR;
    Py_INCREF(coeffs);
    self->coeffs = coeffs;
    Py_INCREF(sum_vars);
    self->sum_vars = sum_vars;
    Py_INCREF(total);
    self->total = total;

    /* Build vars */
    PyObject *result_list = PyList_New(0);
    if (!result_list) { Py_DECREF(self); return NULL; }
    for (Py_ssize_t i = 0; i < PyTuple_GET_SIZE(sum_vars); i++) {
        PyObject *r2 = PyObject_CallFunctionObjArgs(fn_collect_vars_from,
            PyTuple_GET_ITEM(sum_vars, i), result_list, NULL);
        if (!r2) { Py_DECREF(result_list); Py_DECREF(self); return NULL; }
        Py_DECREF(r2);
    }
    PyObject *r2 = PyObject_CallFunctionObjArgs(fn_collect_vars_from, total, result_list, NULL);
    if (!r2) { Py_DECREF(result_list); Py_DECREF(self); return NULL; }
    Py_DECREF(r2);
    self->base.vars = PyList_AsTuple(result_list);
    Py_DECREF(result_list);
    if (!self->base.vars) { Py_DECREF(self); return NULL; }

    return (PyObject *)self;
}

/* ================================================================
 * __repr__ for constraint types
 * ================================================================ */

static PyObject *
BinaryConstraint_repr(BinaryConstraintObject *self)
{
    const char *name = Py_TYPE(self)->tp_name;
    /* Use the short name after the last dot */
    const char *dot = strrchr(name, '.');
    if (dot) name = dot + 1;
    PyObject *lhs_repr = PyObject_Repr(self->lhs);
    if (!lhs_repr) return NULL;
    PyObject *rhs_repr = PyObject_Repr(self->rhs);
    if (!rhs_repr) { Py_DECREF(lhs_repr); return NULL; }
    PyObject *result = PyUnicode_FromFormat("%s(%U, %U)", name, lhs_repr, rhs_repr);
    Py_DECREF(lhs_repr);
    Py_DECREF(rhs_repr);
    return result;
}

static PyObject *
AllDiffConstraint_repr(AllDiffConstraintObject *self)
{
    PyObject *vars_repr = PyObject_Repr(self->all_vars);
    if (!vars_repr) return NULL;
    PyObject *result = PyUnicode_FromFormat("AllDiffConstraint(%U)", vars_repr);
    Py_DECREF(vars_repr);
    return result;
}

static PyObject *
SumConstraint_repr(SumConstraintObject *self)
{
    PyObject *sv = PyObject_Repr(self->sum_vars);
    if (!sv) return NULL;
    PyObject *t = PyObject_Repr(self->total);
    if (!t) { Py_DECREF(sv); return NULL; }
    PyObject *result = PyUnicode_FromFormat("SumConstraint(%U, %U)", sv, t);
    Py_DECREF(sv);
    Py_DECREF(t);
    return result;
}

static PyObject *
ScalarProductConstraint_repr(ScalarProductConstraintObject *self)
{
    PyObject *c = PyObject_Repr(self->coeffs);
    if (!c) return NULL;
    PyObject *sv = PyObject_Repr(self->sum_vars);
    if (!sv) { Py_DECREF(c); return NULL; }
    PyObject *t = PyObject_Repr(self->total);
    if (!t) { Py_DECREF(c); Py_DECREF(sv); return NULL; }
    PyObject *result = PyUnicode_FromFormat("ScalarProductConstraint(%U, %U, %U)", c, sv, t);
    Py_DECREF(c);
    Py_DECREF(sv);
    Py_DECREF(t);
    return result;
}

/* ================================================================
 * Type objects for constraint types
 * ================================================================ */

#define DEFINE_BINARY_CONSTRAINT_TYPE(NAME, name, tag_val) \
    static PyTypeObject NAME##Type = { \
        PyVarObject_HEAD_INIT(NULL, 0) \
        .tp_name = "clausal.logic._clpfd_propagate." #NAME, \
        .tp_basicsize = sizeof(BinaryConstraintObject), \
        .tp_dealloc = (destructor)BinaryConstraint_dealloc, \
        .tp_repr = (reprfunc)BinaryConstraint_repr, \
        .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC, \
        .tp_traverse = (traverseproc)BinaryConstraint_traverse, \
        .tp_clear = (inquiry)BinaryConstraint_clear, \
        .tp_members = BinaryConstraint_members, \
        .tp_base = &ConstraintBaseType, \
        .tp_new = name##_new, \
    };

DEFINE_BINARY_CONSTRAINT_TYPE(EqConstraint, EqConstraint, CONSTRAINT_EQ)
DEFINE_BINARY_CONSTRAINT_TYPE(NeConstraint, NeConstraint, CONSTRAINT_NE)
DEFINE_BINARY_CONSTRAINT_TYPE(LtConstraint, LtConstraint, CONSTRAINT_LT)
DEFINE_BINARY_CONSTRAINT_TYPE(LeConstraint, LeConstraint, CONSTRAINT_LE)

static PyTypeObject AllDiffConstraintType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "clausal.logic._clpfd_propagate.AllDiffConstraint",
    .tp_basicsize = sizeof(AllDiffConstraintObject),
    .tp_dealloc = (destructor)AllDiffConstraint_dealloc,
    .tp_repr = (reprfunc)AllDiffConstraint_repr,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = (traverseproc)AllDiffConstraint_traverse,
    .tp_clear = (inquiry)AllDiffConstraint_clear,
    .tp_members = AllDiffConstraint_members,
    .tp_base = &ConstraintBaseType,
    .tp_new = AllDiffConstraint_new,
};

static PyTypeObject SumConstraintType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "clausal.logic._clpfd_propagate.SumConstraint",
    .tp_basicsize = sizeof(SumConstraintObject),
    .tp_dealloc = (destructor)SumConstraint_dealloc,
    .tp_repr = (reprfunc)SumConstraint_repr,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = (traverseproc)SumConstraint_traverse,
    .tp_clear = (inquiry)SumConstraint_clear,
    .tp_members = SumConstraint_members,
    .tp_base = &ConstraintBaseType,
    .tp_new = SumConstraint_new,
};

static PyTypeObject ScalarProductConstraintType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "clausal.logic._clpfd_propagate.ScalarProductConstraint",
    .tp_basicsize = sizeof(ScalarProductConstraintObject),
    .tp_dealloc = (destructor)ScalarProductConstraint_dealloc,
    .tp_repr = (reprfunc)ScalarProductConstraint_repr,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = (traverseproc)ScalarProductConstraint_traverse,
    .tp_clear = (inquiry)ScalarProductConstraint_clear,
    .tp_members = ScalarProductConstraint_members,
    .tp_base = &ConstraintBaseType,
    .tp_new = ScalarProductConstraint_new,
};

/* ================================================================
 * Tier 4: Public API functions
 * ================================================================ */

/*
 * c_fd_ne(l, r, trail) -> bool
 */
static PyObject *
py_fd_ne(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *l, *r, *trail;
    if (!PyArg_ParseTuple(args, "OOO", &l, &r, &trail))
        return NULL;

    PyObject *dl = call_deref(l);
    if (!dl) return NULL;
    PyObject *dr = call_deref(r);
    if (!dr) { Py_DECREF(dl); return NULL; }

    /* Fast path: both ground int */
    if (PyLong_CheckExact(dl) && PyLong_CheckExact(dr)) {
        int ne = PyObject_RichCompareBool(dl, dr, Py_NE);
        Py_DECREF(dl); Py_DECREF(dr);
        if (ne < 0) return NULL;
        return PyBool_FromLong(ne);
    }

    /* _resolve */
    PyObject *rl = PyObject_CallOneArg(fn_resolve, dl);
    Py_DECREF(dl);
    if (!rl) { Py_DECREF(dr); return NULL; }
    PyObject *rr = PyObject_CallOneArg(fn_resolve, dr);
    Py_DECREF(dr);
    if (!rr) { Py_DECREF(rl); return NULL; }

    /* Check for mixed rational/real */
    if (fn_check_no_mixed) {
        PyObject *chk = PyObject_CallFunctionObjArgs(fn_check_no_mixed, rl, rr, NULL);
        if (!chk) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(chk);
    }

    /* CLP(Q) dispatch */
    if (fn_any_rational) {
        PyObject *aq = PyObject_CallFunctionObjArgs(fn_any_rational, rl, rr, NULL);
        if (!aq) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        int is_rat = PyObject_IsTrue(aq);
        Py_DECREF(aq);
        if (is_rat < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        if (is_rat && fn_q_ne) {
            PyObject *result = PyObject_CallFunctionObjArgs(fn_q_ne, rl, rr, trail, NULL);
            Py_DECREF(rl); Py_DECREF(rr);
            return result;
        }
    }

    /* CLP(R) dispatch */
    PyObject *ar = PyObject_CallFunctionObjArgs(fn_any_real, rl, rr, NULL);
    if (!ar) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    int is_real = PyObject_IsTrue(ar);
    Py_DECREF(ar);
    if (is_real < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (is_real) {
        if (fn_real_ne) {
            PyObject *result = PyObject_CallFunctionObjArgs(fn_real_ne, rl, rr, trail, NULL);
            Py_DECREF(rl); Py_DECREF(rr);
            return result;
        }
        Py_DECREF(rl); Py_DECREF(rr);
        Py_RETURN_FALSE;
    }

    /* _both_ground */
    PyObject *bg = PyObject_CallFunctionObjArgs(fn_both_ground, rl, rr, NULL);
    if (!bg) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    int is_bg = PyObject_IsTrue(bg);
    Py_DECREF(bg);
    if (is_bg < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (is_bg) {
        int ne = PyObject_RichCompareBool(rl, rr, Py_NE);
        Py_DECREF(rl); Py_DECREF(rr);
        if (ne < 0) return NULL;
        return PyBool_FromLong(ne);
    }

    /* Ensure FD */
    int l_isvar = call_is_var(rl);
    if (l_isvar < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (l_isvar) {
        FDVarObject *s = c_ensure_fd(rl, trail);
        if (!s) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(s);
    }
    int r_isvar = call_is_var(rr);
    if (r_isvar < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (r_isvar) {
        FDVarObject *s = c_ensure_fd(rr, trail);
        if (!s) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(s);
    }

    /* Create NeConstraint and post */
    PyObject *cargs = PyTuple_Pack(2, rl, rr);
    Py_DECREF(rl); Py_DECREF(rr);
    if (!cargs) return NULL;

    PyObject *constraint = NeConstraint_new(&NeConstraintType, cargs, NULL);
    Py_DECREF(cargs);
    if (!constraint) return NULL;

    int ok = c_post_constraint(constraint, trail);
    Py_DECREF(constraint);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok > 0);
}

/*
 * c_fd_lt(l, r, trail) -> bool
 */
static PyObject *
py_fd_lt(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *l, *r, *trail;
    if (!PyArg_ParseTuple(args, "OOO", &l, &r, &trail))
        return NULL;

    PyObject *dl = call_deref(l);
    if (!dl) return NULL;
    PyObject *dr = call_deref(r);
    if (!dr) { Py_DECREF(dl); return NULL; }

    if (PyLong_CheckExact(dl) && PyLong_CheckExact(dr)) {
        int lt = PyObject_RichCompareBool(dl, dr, Py_LT);
        Py_DECREF(dl); Py_DECREF(dr);
        if (lt < 0) return NULL;
        return PyBool_FromLong(lt);
    }

    PyObject *rl = PyObject_CallOneArg(fn_resolve, dl);
    Py_DECREF(dl);
    if (!rl) { Py_DECREF(dr); return NULL; }
    PyObject *rr = PyObject_CallOneArg(fn_resolve, dr);
    Py_DECREF(dr);
    if (!rr) { Py_DECREF(rl); return NULL; }

    /* Check for mixed rational/real */
    if (fn_check_no_mixed) {
        PyObject *chk = PyObject_CallFunctionObjArgs(fn_check_no_mixed, rl, rr, NULL);
        if (!chk) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(chk);
    }

    /* CLP(Q) dispatch */
    if (fn_any_rational) {
        PyObject *aq = PyObject_CallFunctionObjArgs(fn_any_rational, rl, rr, NULL);
        if (!aq) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        int is_rat = PyObject_IsTrue(aq);
        Py_DECREF(aq);
        if (is_rat < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        if (is_rat && fn_q_lt) {
            PyObject *result = PyObject_CallFunctionObjArgs(fn_q_lt, rl, rr, trail, NULL);
            Py_DECREF(rl); Py_DECREF(rr);
            return result;
        }
    }

    PyObject *ar = PyObject_CallFunctionObjArgs(fn_any_real, rl, rr, NULL);
    if (!ar) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    int is_real = PyObject_IsTrue(ar);
    Py_DECREF(ar);
    if (is_real < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (is_real) {
        if (fn_real_lt) {
            PyObject *result = PyObject_CallFunctionObjArgs(fn_real_lt, rl, rr, trail, NULL);
            Py_DECREF(rl); Py_DECREF(rr);
            return result;
        }
        Py_DECREF(rl); Py_DECREF(rr);
        Py_RETURN_FALSE;
    }

    PyObject *bg = PyObject_CallFunctionObjArgs(fn_both_ground, rl, rr, NULL);
    if (!bg) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    int is_bg = PyObject_IsTrue(bg);
    Py_DECREF(bg);
    if (is_bg < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (is_bg) {
        int cmp = PyObject_RichCompareBool(rl, rr, Py_LT);
        Py_DECREF(rl); Py_DECREF(rr);
        if (cmp < 0) return NULL;
        return PyBool_FromLong(cmp);
    }

    int l_isvar = call_is_var(rl);
    if (l_isvar < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (l_isvar) {
        FDVarObject *s = c_ensure_fd(rl, trail);
        if (!s) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(s);
    }
    int r_isvar = call_is_var(rr);
    if (r_isvar < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (r_isvar) {
        FDVarObject *s = c_ensure_fd(rr, trail);
        if (!s) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(s);
    }

    PyObject *cargs = PyTuple_Pack(2, rl, rr);
    Py_DECREF(rl); Py_DECREF(rr);
    if (!cargs) return NULL;

    PyObject *constraint = LtConstraint_new(&LtConstraintType, cargs, NULL);
    Py_DECREF(cargs);
    if (!constraint) return NULL;

    int ok = c_post_constraint(constraint, trail);
    Py_DECREF(constraint);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok > 0);
}

/*
 * c_fd_le(l, r, trail) -> bool
 */
static PyObject *
py_fd_le(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *l, *r, *trail;
    if (!PyArg_ParseTuple(args, "OOO", &l, &r, &trail))
        return NULL;

    PyObject *dl = call_deref(l);
    if (!dl) return NULL;
    PyObject *dr = call_deref(r);
    if (!dr) { Py_DECREF(dl); return NULL; }

    if (PyLong_CheckExact(dl) && PyLong_CheckExact(dr)) {
        int le = PyObject_RichCompareBool(dl, dr, Py_LE);
        Py_DECREF(dl); Py_DECREF(dr);
        if (le < 0) return NULL;
        return PyBool_FromLong(le);
    }

    PyObject *rl = PyObject_CallOneArg(fn_resolve, dl);
    Py_DECREF(dl);
    if (!rl) { Py_DECREF(dr); return NULL; }
    PyObject *rr = PyObject_CallOneArg(fn_resolve, dr);
    Py_DECREF(dr);
    if (!rr) { Py_DECREF(rl); return NULL; }

    /* Check for mixed rational/real */
    if (fn_check_no_mixed) {
        PyObject *chk = PyObject_CallFunctionObjArgs(fn_check_no_mixed, rl, rr, NULL);
        if (!chk) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(chk);
    }

    /* CLP(Q) dispatch */
    if (fn_any_rational) {
        PyObject *aq = PyObject_CallFunctionObjArgs(fn_any_rational, rl, rr, NULL);
        if (!aq) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        int is_rat = PyObject_IsTrue(aq);
        Py_DECREF(aq);
        if (is_rat < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        if (is_rat && fn_q_le) {
            PyObject *result = PyObject_CallFunctionObjArgs(fn_q_le, rl, rr, trail, NULL);
            Py_DECREF(rl); Py_DECREF(rr);
            return result;
        }
    }

    PyObject *ar = PyObject_CallFunctionObjArgs(fn_any_real, rl, rr, NULL);
    if (!ar) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    int is_real = PyObject_IsTrue(ar);
    Py_DECREF(ar);
    if (is_real < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (is_real) {
        if (fn_real_le) {
            PyObject *result = PyObject_CallFunctionObjArgs(fn_real_le, rl, rr, trail, NULL);
            Py_DECREF(rl); Py_DECREF(rr);
            return result;
        }
        Py_DECREF(rl); Py_DECREF(rr);
        Py_RETURN_FALSE;
    }

    PyObject *bg = PyObject_CallFunctionObjArgs(fn_both_ground, rl, rr, NULL);
    if (!bg) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    int is_bg = PyObject_IsTrue(bg);
    Py_DECREF(bg);
    if (is_bg < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (is_bg) {
        int cmp = PyObject_RichCompareBool(rl, rr, Py_LE);
        Py_DECREF(rl); Py_DECREF(rr);
        if (cmp < 0) return NULL;
        return PyBool_FromLong(cmp);
    }

    int l_isvar = call_is_var(rl);
    if (l_isvar < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (l_isvar) {
        FDVarObject *s = c_ensure_fd(rl, trail);
        if (!s) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(s);
    }
    int r_isvar = call_is_var(rr);
    if (r_isvar < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (r_isvar) {
        FDVarObject *s = c_ensure_fd(rr, trail);
        if (!s) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(s);
    }

    PyObject *cargs = PyTuple_Pack(2, rl, rr);
    Py_DECREF(rl); Py_DECREF(rr);
    if (!cargs) return NULL;

    PyObject *constraint = LeConstraint_new(&LeConstraintType, cargs, NULL);
    Py_DECREF(cargs);
    if (!constraint) return NULL;

    int ok = c_post_constraint(constraint, trail);
    Py_DECREF(constraint);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok > 0);
}

/*
 * c_fd_eq(l, r, trail) -> bool
 * This is the most complex: handles linearisation for expression trees
 */
static PyObject *
py_fd_eq(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *l, *r, *trail;
    if (!PyArg_ParseTuple(args, "OOO", &l, &r, &trail))
        return NULL;

    PyObject *dl = call_deref(l);
    if (!dl) return NULL;
    PyObject *dr = call_deref(r);
    if (!dr) { Py_DECREF(dl); return NULL; }

    if (PyLong_CheckExact(dl) && PyLong_CheckExact(dr)) {
        int eq = PyObject_RichCompareBool(dl, dr, Py_EQ);
        Py_DECREF(dl); Py_DECREF(dr);
        if (eq < 0) return NULL;
        return PyBool_FromLong(eq);
    }

    PyObject *rl = PyObject_CallOneArg(fn_resolve, dl);
    Py_DECREF(dl);
    if (!rl) { Py_DECREF(dr); return NULL; }
    PyObject *rr = PyObject_CallOneArg(fn_resolve, dr);
    Py_DECREF(dr);
    if (!rr) { Py_DECREF(rl); return NULL; }

    /* Check for mixed rational/real */
    if (fn_check_no_mixed) {
        PyObject *chk = PyObject_CallFunctionObjArgs(fn_check_no_mixed, rl, rr, NULL);
        if (!chk) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(chk);
    }

    /* CLP(Q) dispatch */
    if (fn_any_rational) {
        PyObject *aq = PyObject_CallFunctionObjArgs(fn_any_rational, rl, rr, NULL);
        if (!aq) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        int is_rat = PyObject_IsTrue(aq);
        Py_DECREF(aq);
        if (is_rat < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        if (is_rat && fn_q_eq) {
            PyObject *result = PyObject_CallFunctionObjArgs(fn_q_eq, rl, rr, trail, NULL);
            Py_DECREF(rl); Py_DECREF(rr);
            return result;
        }
    }

    /* CLP(R) dispatch */
    PyObject *ar = PyObject_CallFunctionObjArgs(fn_any_real, rl, rr, NULL);
    if (!ar) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    int is_real = PyObject_IsTrue(ar);
    Py_DECREF(ar);
    if (is_real < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (is_real) {
        if (fn_real_eq) {
            PyObject *result = PyObject_CallFunctionObjArgs(fn_real_eq, rl, rr, trail, NULL);
            Py_DECREF(rl); Py_DECREF(rr);
            return result;
        }
        Py_DECREF(rl); Py_DECREF(rr);
        Py_RETURN_FALSE;
    }

    /* Try linearisation — only when at least one side is an expression tree
     * (Add/Sub/Mult/Negate).  For plain var==int, EqConstraint suffices.
     * Uses cached type objects for a fast C-level isinstance check. */
    int try_linearise = 0;
    if (type_Add) {  /* types are loaded; check both operands */
        try_linearise = (
            PyObject_TypeCheck(rl, type_Add) || PyObject_TypeCheck(rl, type_Sub) ||
            PyObject_TypeCheck(rl, type_Mult) || PyObject_TypeCheck(rl, type_Negate) ||
            PyObject_TypeCheck(rr, type_Add) || PyObject_TypeCheck(rr, type_Sub) ||
            PyObject_TypeCheck(rr, type_Mult) || PyObject_TypeCheck(rr, type_Negate)
        );
    }

    PyObject *lc = NULL, *rc = NULL;
    if (try_linearise) {
    lc = PyObject_CallOneArg(fn_linearise, rl);
    rc = PyObject_CallOneArg(fn_linearise, rr);
    if (!lc || !rc) {
        /* _linearise may return None for non-linear or non-expressions */
        PyErr_Clear();
        Py_XDECREF(lc);
        Py_XDECREF(rc);
        lc = rc = NULL;
    }

    if (lc && lc != Py_None && rc && rc != Py_None) {
        /* Both sides linearised — merge coefficients and build
         * ScalarProductConstraint for full bounds-consistency propagation.
         *
         * l == r  →  (l_coeffs - r_coeffs)·vars = r_const - l_const
         */
        PyObject *l_coeffs = PyTuple_GET_ITEM(lc, 0);  /* dict {var: coeff} */
        PyObject *r_coeffs = PyTuple_GET_ITEM(rc, 0);
        PyObject *l_const_obj = PyTuple_GET_ITEM(lc, 1);  /* int */
        PyObject *r_const_obj = PyTuple_GET_ITEM(rc, 1);

        /* merged = dict(l_coeffs) */
        PyObject *merged = PyDict_Copy(l_coeffs);
        if (!merged) { Py_DECREF(lc); Py_DECREF(rc); Py_DECREF(rl); Py_DECREF(rr); return NULL; }

        /* for v, c in r_coeffs.items(): merged[v] = merged.get(v, 0) - c
         * Uses overflow-checked conversion; on overflow we abandon the
         * linearisation path and fall through to EqConstraint. */
        PyObject *key, *value;
        Py_ssize_t pos = 0;
        int overflow = 0;
        while (PyDict_Next(r_coeffs, &pos, &key, &value)) {
            int ov1 = 0, ov2 = 0;
            PyObject *existing = PyDict_GetItem(merged, key);  /* borrowed, NULL if absent */
            long long ex_val = existing ? PyLong_AsLongLongAndOverflow(existing, &ov1) : 0;
            long long r_val = PyLong_AsLongLongAndOverflow(value, &ov2);
            if (ov1 || ov2) { overflow = 1; break; }
            if (PyErr_Occurred()) {
                Py_DECREF(merged); Py_DECREF(lc); Py_DECREF(rc);
                Py_DECREF(rl); Py_DECREF(rr);
                return NULL;
            }
            long long new_val = ex_val - r_val;
            if (new_val == 0) {
                if (PyDict_DelItem(merged, key) < 0) {
                    /* Key might not exist if ex_val was 0 via default — ignore KeyError */
                    PyErr_Clear();
                }
            } else {
                PyObject *nv = PyLong_FromLongLong(new_val);
                if (!nv || PyDict_SetItem(merged, key, nv) < 0) {
                    Py_XDECREF(nv);
                    Py_DECREF(merged); Py_DECREF(lc); Py_DECREF(rc);
                    Py_DECREF(rl); Py_DECREF(rr);
                    return NULL;
                }
                Py_DECREF(nv);
            }
        }

        if (overflow) {
            /* Coefficients exceed int64 — fall through to EqConstraint */
            Py_DECREF(merged); Py_DECREF(lc); Py_DECREF(rc);
            goto use_simple_eq;
        }

        /* value = r_const - l_const (with overflow check) */
        int ov_lc = 0, ov_rc = 0;
        long long lc_val = PyLong_AsLongLongAndOverflow(l_const_obj, &ov_lc);
        long long rc_val = PyLong_AsLongLongAndOverflow(r_const_obj, &ov_rc);
        Py_DECREF(lc); Py_DECREF(rc);
        if (ov_lc || ov_rc) {
            /* Constants exceed int64 — fall through to EqConstraint */
            Py_DECREF(merged);
            goto use_simple_eq;
        }
        if (PyErr_Occurred()) {
            Py_DECREF(merged); Py_DECREF(rl); Py_DECREF(rr);
            return NULL;
        }
        long long const_value = rc_val - lc_val;
        Py_DECREF(rl); Py_DECREF(rr);

        Py_ssize_t n = PyDict_Size(merged);
        if (n == 0) {
            /* Purely constant: no vars remain */
            Py_DECREF(merged);
            return PyBool_FromLong(lc_val == rc_val);
        }

        /* Build vars_tuple and coeffs_tuple from merged dict */
        PyObject *vars_tuple = PyTuple_New(n);
        PyObject *coeffs_tuple = PyTuple_New(n);
        if (!vars_tuple || !coeffs_tuple) {
            Py_XDECREF(vars_tuple); Py_XDECREF(coeffs_tuple);
            Py_DECREF(merged);
            return NULL;
        }
        pos = 0;
        Py_ssize_t idx = 0;
        while (PyDict_Next(merged, &pos, &key, &value)) {
            Py_INCREF(key);
            PyTuple_SET_ITEM(vars_tuple, idx, key);
            Py_INCREF(value);
            PyTuple_SET_ITEM(coeffs_tuple, idx, value);
            idx++;
        }
        Py_DECREF(merged);

        /* _ensure_fd on all vars */
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *v = PyTuple_GET_ITEM(vars_tuple, i);
            int isv = call_is_var(v);
            if (isv < 0) { Py_DECREF(vars_tuple); Py_DECREF(coeffs_tuple); return NULL; }
            if (isv) {
                FDVarObject *s = c_ensure_fd(v, trail);
                if (!s) { Py_DECREF(vars_tuple); Py_DECREF(coeffs_tuple); return NULL; }
                Py_DECREF(s);
            }
        }

        /* Build ScalarProductConstraint(coeffs, vars, value) */
        PyObject *value_obj = PyLong_FromLongLong(const_value);
        if (!value_obj) { Py_DECREF(vars_tuple); Py_DECREF(coeffs_tuple); return NULL; }

        PyObject *cargs = PyTuple_Pack(3, coeffs_tuple, vars_tuple, value_obj);
        Py_DECREF(coeffs_tuple); Py_DECREF(vars_tuple); Py_DECREF(value_obj);
        if (!cargs) return NULL;

        PyObject *constraint = ScalarProductConstraint_new(
            &ScalarProductConstraintType, cargs, NULL);
        Py_DECREF(cargs);
        if (!constraint) return NULL;

        int ok = c_post_constraint(constraint, trail);
        Py_DECREF(constraint);
        if (ok < 0) return NULL;
        return PyBool_FromLong(ok > 0);
    }
    Py_XDECREF(lc);
    Py_XDECREF(rc);
    } /* end if (try_linearise) */

use_simple_eq:

    /* _both_ground check */
    {
        PyObject *bg = PyObject_CallFunctionObjArgs(fn_both_ground, rl, rr, NULL);
        if (!bg) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        int is_bg = PyObject_IsTrue(bg);
        Py_DECREF(bg);
        if (is_bg < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        if (is_bg) {
            int eq = PyObject_RichCompareBool(rl, rr, Py_EQ);
            Py_DECREF(rl); Py_DECREF(rr);
            if (eq < 0) return NULL;
            return PyBool_FromLong(eq);
        }
    }

    int l_isvar = call_is_var(rl);
    if (l_isvar < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (l_isvar) {
        FDVarObject *s = c_ensure_fd(rl, trail);
        if (!s) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(s);
    }
    int r_isvar = call_is_var(rr);
    if (r_isvar < 0) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
    if (r_isvar) {
        FDVarObject *s = c_ensure_fd(rr, trail);
        if (!s) { Py_DECREF(rl); Py_DECREF(rr); return NULL; }
        Py_DECREF(s);
    }

    PyObject *cargs = PyTuple_Pack(2, rl, rr);
    Py_DECREF(rl); Py_DECREF(rr);
    if (!cargs) return NULL;

    PyObject *constraint = EqConstraint_new(&EqConstraintType, cargs, NULL);
    Py_DECREF(cargs);
    if (!constraint) return NULL;

    int ok = c_post_constraint(constraint, trail);
    Py_DECREF(constraint);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok > 0);
}

/* ================================================================
 * FD attribute hook
 * ================================================================ */

static PyObject *
py_fd_hook(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *attr_value, *bound_to, *trail;
    if (!PyArg_ParseTuple(args, "OOO", &attr_value, &bound_to, &trail))
        return NULL;

    /* state = attr_value (FDVar) */
    PyObject *domain, *constraints;
    if (FDVar_Check(attr_value)) {
        domain = ((FDVarObject *)attr_value)->domain;
        constraints = ((FDVarObject *)attr_value)->constraints;
    } else {
        domain = PyObject_GetAttrString(attr_value, "domain");
        constraints = PyObject_GetAttrString(attr_value, "constraints");
        if (!domain || !constraints) {
            Py_XDECREF(domain);
            Py_XDECREF(constraints);
            return NULL;
        }
    }

    int domain_newref = !FDVar_Check(attr_value);

    PyObject *bt = call_deref(bound_to);
    if (!bt) {
        if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
        return NULL;
    }

    /* Case 1: bound to integer (or integer-valued Fraction from CLP(Q)) */
    int is_int_val = PyLong_Check(bt) && !PyBool_Check(bt);
    if (!is_int_val) {
        /* Check for Fraction with denominator == 1 */
        PyObject *denom = PyObject_GetAttrString(bt, "denominator");
        if (denom) {
            PyObject *one = PyLong_FromLong(1);
            if (one && PyObject_RichCompareBool(denom, one, Py_EQ) == 1) {
                /* Convert Fraction to int for domain check */
                PyObject *int_bt = PyNumber_Long(bt);
                if (int_bt) {
                    Py_DECREF(bt);
                    bt = int_bt;
                    is_int_val = 1;
                }
            }
            Py_XDECREF(one);
            Py_DECREF(denom);
        } else {
            PyErr_Clear();
        }
    }
    if (is_int_val) {
        /* Bignum-safe domain_contains: check whether the bound int (which
         * may exceed int64) is in any of the domain's intervals using
         * Python rich-compare on the raw PyObject bounds.  Slice 3 of
         * clpz_bignum.md — fast int64 path retained for the common case. */
        int contains;
        int bt_overflow = 0;
        int64_t val_i64 = PyLong_AsLongLongAndOverflow(bt, &bt_overflow);
        if (bt_overflow == 0 && !(val_i64 == -1 && PyErr_Occurred())
            && !has_bignum_bound(domain)) {
            /* Fast path: int64-fitting value, int64-fitting domain */
            contains = domain_contains_i64(domain, val_i64);
        } else {
            /* Bignum path: scan intervals using PyObject comparisons */
            if (PyErr_Occurred()) PyErr_Clear();
            contains = 0;
            Py_ssize_t nd = PyTuple_GET_SIZE(domain);
            for (Py_ssize_t k = 0; k < nd; k++) {
                PyObject *pair = PyTuple_GET_ITEM(domain, k);
                PyObject *lo = PyTuple_GET_ITEM(pair, 0);
                PyObject *hi = PyTuple_GET_ITEM(pair, 1);
                int ge = PyObject_RichCompareBool(bt, lo, Py_GE);
                if (ge < 0) goto hook_error;
                if (!ge) {
                    /* bt < this interval's lo; intervals are sorted, no
                     * further interval can contain bt either. */
                    break;
                }
                int le = PyObject_RichCompareBool(bt, hi, Py_LE);
                if (le < 0) goto hook_error;
                if (le) { contains = 1; break; }
            }
        }
        if (contains < 0) goto hook_error;
        if (!contains) {
            if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
            Py_DECREF(bt);
            Py_RETURN_FALSE;
        }

        /* Propagate all constraints */
        PyObject *queue = PyList_New(0);
        if (!queue) goto hook_error;

        Py_ssize_t nc = PyTuple_GET_SIZE(constraints);
        for (Py_ssize_t i = 0; i < nc; i++) {
            PyObject *c = PyTuple_GET_ITEM(constraints, i);
            int ok = constraint_propagate_c(c, trail, queue);
            if (ok <= 0) {
                Py_DECREF(queue);
                if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
                Py_DECREF(bt);
                if (ok < 0) return NULL;
                Py_RETURN_FALSE;
            }
        }

        int ok = c_propagate(queue, trail);
        Py_DECREF(queue);
        if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
        Py_DECREF(bt);
        if (ok < 0) return NULL;
        return PyBool_FromLong(ok > 0);
    }

    /* Case 2: bound to variable */
    int isv = call_is_var(bt);
    if (isv < 0) goto hook_error;
    if (isv) {
        PyObject *other_state = call_get_attr(bt, FD_KEY_STR);
        if (!other_state) goto hook_error;

        PyObject *merged_domain, *merged_constraints;

        if (other_state == Py_None) {
            Py_DECREF(other_state);

            /* Check for real interval narrowing */
            PyObject *narrowed_domain = domain;
            Py_INCREF(narrowed_domain);
            PyObject *narrowed_constraints = constraints;
            Py_INCREF(narrowed_constraints);

            if (REAL_KEY) {
                PyObject *real_state = call_get_attr(bt, REAL_KEY);
                if (!real_state) {
                    Py_DECREF(narrowed_domain);
                    Py_DECREF(narrowed_constraints);
                    goto hook_error;
                }
                if (real_state != Py_None) {
                    PyObject *r_lo_obj = PyObject_GetAttrString(real_state, "lo");
                    PyObject *r_hi_obj = PyObject_GetAttrString(real_state, "hi");
                    Py_DECREF(real_state);
                    if (!r_lo_obj || !r_hi_obj) {
                        Py_XDECREF(r_lo_obj); Py_XDECREF(r_hi_obj);
                        Py_DECREF(narrowed_domain); Py_DECREF(narrowed_constraints);
                        goto hook_error;
                    }
                    double r_lo = PyFloat_AsDouble(r_lo_obj);
                    double r_hi = PyFloat_AsDouble(r_hi_obj);
                    Py_DECREF(r_lo_obj); Py_DECREF(r_hi_obj);

                    int64_t rlo_i = (r_lo == -HUGE_VAL) ? INT64_MIN : (int64_t)ceil(r_lo);
                    int64_t rhi_i = (r_hi == HUGE_VAL) ? INT64_MAX : (int64_t)floor(r_hi);
                    PyObject *rng = domain_from_range_i64(rlo_i, rhi_i);
                    if (!rng) {
                        Py_DECREF(narrowed_domain); Py_DECREF(narrowed_constraints);
                        goto hook_error;
                    }
                    PyObject *intersected = domain_intersection_c(narrowed_domain, rng);
                    Py_DECREF(rng); Py_DECREF(narrowed_domain);
                    if (!intersected) {
                        Py_DECREF(narrowed_constraints);
                        goto hook_error;
                    }
                    if (PyTuple_GET_SIZE(intersected) == 0) {
                        Py_DECREF(intersected); Py_DECREF(narrowed_constraints);
                        if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
                        Py_DECREF(bt);
                        Py_RETURN_FALSE;
                    }
                    narrowed_domain = intersected;
                } else {
                    Py_DECREF(real_state);
                }
            }

            /* Build new FDVar and put_attr */
            PyObject *fdvar_args = PyTuple_Pack(2, narrowed_domain, narrowed_constraints);
            Py_DECREF(narrowed_domain); Py_DECREF(narrowed_constraints);
            if (!fdvar_args) goto hook_error;
            PyObject *new_state = FDVar_new(&FDVarType, fdvar_args, NULL);
            Py_DECREF(fdvar_args);
            if (!new_state) goto hook_error;

            if (call_put_attr(bt, FD_KEY_STR, new_state, trail) < 0) {
                Py_DECREF(new_state);
                goto hook_error;
            }

            merged_domain = ((FDVarObject *)new_state)->domain;
            merged_constraints = ((FDVarObject *)new_state)->constraints;
            Py_INCREF(merged_domain);
            Py_INCREF(merged_constraints);
            Py_DECREF(new_state);
        } else {
            /* Both have FD — intersect domains, merge constraints */
            PyObject *other_domain, *other_constraints;
            if (FDVar_Check(other_state)) {
                other_domain = ((FDVarObject *)other_state)->domain;
                other_constraints = ((FDVarObject *)other_state)->constraints;
                Py_INCREF(other_domain);
                Py_INCREF(other_constraints);
            } else {
                other_domain = PyObject_GetAttrString(other_state, "domain");
                other_constraints = PyObject_GetAttrString(other_state, "constraints");
                if (!other_domain || !other_constraints) {
                    Py_XDECREF(other_domain); Py_XDECREF(other_constraints);
                    Py_DECREF(other_state);
                    goto hook_error;
                }
            }
            Py_DECREF(other_state);

            PyObject *new_dom = domain_intersection_c(domain, other_domain);
            Py_DECREF(other_domain);
            if (!new_dom) { Py_DECREF(other_constraints); goto hook_error; }
            if (PyTuple_GET_SIZE(new_dom) == 0) {
                Py_DECREF(new_dom); Py_DECREF(other_constraints);
                if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
                Py_DECREF(bt);
                Py_RETURN_FALSE;
            }

            /* Deduplicate constraints by id */
            PyObject *seen = PySet_New(NULL);
            if (!seen) { Py_DECREF(new_dom); Py_DECREF(other_constraints); goto hook_error; }
            PyObject *merged_list = PyList_New(0);
            if (!merged_list) { Py_DECREF(seen); Py_DECREF(new_dom); Py_DECREF(other_constraints); goto hook_error; }

            /* Add constraints from both sides */
            Py_ssize_t nc1 = PyTuple_GET_SIZE(constraints);
            Py_ssize_t nc2 = PyTuple_GET_SIZE(other_constraints);
            for (Py_ssize_t i = 0; i < nc1 + nc2; i++) {
                PyObject *c = (i < nc1) ? PyTuple_GET_ITEM(constraints, i)
                                        : PyTuple_GET_ITEM(other_constraints, i - nc1);
                PyObject *cid = PyLong_FromVoidPtr(c);
                if (!cid) { Py_DECREF(seen); Py_DECREF(merged_list); Py_DECREF(new_dom); Py_DECREF(other_constraints); goto hook_error; }
                int in_set = PySet_Contains(seen, cid);
                if (in_set < 0) { Py_DECREF(cid); Py_DECREF(seen); Py_DECREF(merged_list); Py_DECREF(new_dom); Py_DECREF(other_constraints); goto hook_error; }
                if (!in_set) {
                    PySet_Add(seen, cid);
                    PyList_Append(merged_list, c);
                }
                Py_DECREF(cid);
            }
            Py_DECREF(seen);
            Py_DECREF(other_constraints);

            merged_constraints = PyList_AsTuple(merged_list);
            Py_DECREF(merged_list);
            if (!merged_constraints) { Py_DECREF(new_dom); goto hook_error; }
            merged_domain = new_dom;

            /* Create and store merged FDVar */
            PyObject *fdvar_args = PyTuple_Pack(2, merged_domain, merged_constraints);
            if (!fdvar_args) { Py_DECREF(merged_domain); Py_DECREF(merged_constraints); goto hook_error; }
            PyObject *new_fdvar = FDVar_new(&FDVarType, fdvar_args, NULL);
            Py_DECREF(fdvar_args);
            if (!new_fdvar) { Py_DECREF(merged_domain); Py_DECREF(merged_constraints); goto hook_error; }

            if (call_put_attr(bt, FD_KEY_STR, new_fdvar, trail) < 0) {
                Py_DECREF(new_fdvar); Py_DECREF(merged_domain); Py_DECREF(merged_constraints);
                goto hook_error;
            }
            Py_DECREF(new_fdvar);
        }

        /* Singleton check */
        PyObject *sval = domain_singleton_c(merged_domain);
        if (!sval) { Py_DECREF(merged_domain); Py_DECREF(merged_constraints); goto hook_error; }
        if (sval != Py_None) {
            int ok = call_unify(bt, sval, trail);
            Py_DECREF(sval);
            if (ok <= 0) {
                Py_DECREF(merged_domain); Py_DECREF(merged_constraints);
                if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
                Py_DECREF(bt);
                if (ok < 0) return NULL;
                Py_RETURN_FALSE;
            }
        } else {
            Py_DECREF(sval);
        }

        /* Propagate merged constraints */
        PyObject *queue = PyList_New(0);
        if (!queue) { Py_DECREF(merged_domain); Py_DECREF(merged_constraints); goto hook_error; }

        Py_ssize_t nc = PyTuple_GET_SIZE(merged_constraints);
        for (Py_ssize_t i = 0; i < nc; i++) {
            PyObject *c = PyTuple_GET_ITEM(merged_constraints, i);
            int ok = constraint_propagate_c(c, trail, queue);
            if (ok <= 0) {
                Py_DECREF(queue); Py_DECREF(merged_domain); Py_DECREF(merged_constraints);
                if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
                Py_DECREF(bt);
                if (ok < 0) return NULL;
                Py_RETURN_FALSE;
            }
        }

        int ok = c_propagate(queue, trail);
        Py_DECREF(queue); Py_DECREF(merged_domain); Py_DECREF(merged_constraints);
        if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
        Py_DECREF(bt);
        if (ok < 0) return NULL;
        return PyBool_FromLong(ok > 0);
    }

    /* Non-integer, non-var → fail */
    if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
    Py_DECREF(bt);
    Py_RETURN_FALSE;

hook_error:
    if (domain_newref) { Py_DECREF(domain); Py_DECREF(constraints); }
    Py_DECREF(bt);
    return NULL;
}

/* ================================================================
 * Python-callable wrappers for Tier 2 functions
 * ================================================================ */

static PyObject *
py_ensure_fd(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *var, *trail;
    if (!PyArg_ParseTuple(args, "OO", &var, &trail))
        return NULL;
    FDVarObject *result = c_ensure_fd(var, trail);
    if (!result) return NULL;
    return (PyObject *)result;
}

static PyObject *
py_propagate(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *queue, *trail;
    if (!PyArg_ParseTuple(args, "OO", &queue, &trail))
        return NULL;
    int ok = c_propagate(queue, trail);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok > 0);
}

static PyObject *
py_post_constraint(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *constraint, *trail;
    if (!PyArg_ParseTuple(args, "OO", &constraint, &trail))
        return NULL;
    int ok = c_post_constraint(constraint, trail);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok > 0);
}

static PyObject *
py_narrow(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *var, *new_domain, *trail, *queue;
    if (!PyArg_ParseTuple(args, "OOOO", &var, &new_domain, &trail, &queue))
        return NULL;
    int ok = c_narrow(var, new_domain, trail, queue);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok > 0);
}

static PyObject *
py_narrow_if_changed(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *var, *new_domain, *trail, *queue;
    if (!PyArg_ParseTuple(args, "OOOO", &var, &new_domain, &trail, &queue))
        return NULL;
    int ok = c_narrow_if_changed(var, new_domain, trail, queue);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok > 0);
}

static PyObject *
py_add_constraint(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *var, *constraint, *trail;
    if (!PyArg_ParseTuple(args, "OOO", &var, &constraint, &trail))
        return NULL;
    int ok = c_add_constraint(var, constraint, trail);
    if (ok < 0) return NULL;
    Py_RETURN_NONE;
}

/* ================================================================
 * Module definition
 * ================================================================ */

static PyMethodDef module_methods[] = {
    {"_ensure_fd",          py_ensure_fd,          METH_VARARGS, NULL},
    {"propagate",           py_propagate,          METH_VARARGS, NULL},
    {"_post_constraint",    py_post_constraint,    METH_VARARGS, NULL},
    {"_narrow",             py_narrow,             METH_VARARGS, NULL},
    {"_narrow_if_changed",  py_narrow_if_changed,  METH_VARARGS, NULL},
    {"_add_constraint",     py_add_constraint,     METH_VARARGS, NULL},
    {"fd_eq",               py_fd_eq,              METH_VARARGS, NULL},
    {"fd_ne",               py_fd_ne,              METH_VARARGS, NULL},
    {"fd_lt",               py_fd_lt,              METH_VARARGS, NULL},
    {"fd_le",               py_fd_le,              METH_VARARGS, NULL},
    {"_fd_hook",            py_fd_hook,            METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_clpfd_propagate",
    "C-accelerated CLP(FD) constraint propagation.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__clpfd_propagate(void)
{
    /* Import clausal.logic.variables */
    PyObject *var_mod = PyImport_ImportModule("clausal.logic.variables");
    if (!var_mod) return NULL;

    fn_deref  = PyObject_GetAttrString(var_mod, "deref");
    fn_is_var = PyObject_GetAttrString(var_mod, "is_var");
    fn_unify  = PyObject_GetAttrString(var_mod, "unify");
    fn_put_attr = PyObject_GetAttrString(var_mod, "put_attr");
    fn_get_attr = PyObject_GetAttrString(var_mod, "get_attr");
    fn_register_attr_hook = PyObject_GetAttrString(var_mod, "register_attr_hook");
    Py_DECREF(var_mod);

    if (!fn_deref || !fn_is_var || !fn_unify || !fn_put_attr ||
        !fn_get_attr || !fn_register_attr_hook)
        return NULL;

    /* Import clausal.logic.clpfd for Python helpers */
    PyObject *clpfd_mod = PyImport_ImportModule("clausal.logic.clpfd");
    if (!clpfd_mod) return NULL;

    fn_expr_domain = PyObject_GetAttrString(clpfd_mod, "_expr_domain");
    fn_resolve = PyObject_GetAttrString(clpfd_mod, "_resolve");
    fn_eval_ground = PyObject_GetAttrString(clpfd_mod, "_eval_ground");
    fn_any_real = PyObject_GetAttrString(clpfd_mod, "_any_real");
    fn_both_ground = PyObject_GetAttrString(clpfd_mod, "_both_ground");
    fn_collect_constraint_vars = PyObject_GetAttrString(clpfd_mod, "_collect_constraint_vars");
    fn_collect_vars_from = PyObject_GetAttrString(clpfd_mod, "_collect_vars_from");
    fn_linearise = PyObject_GetAttrString(clpfd_mod, "_linearise");
    fn_ensure_fd_py = PyObject_GetAttrString(clpfd_mod, "_ensure_fd");
    fn_sync_real = PyObject_GetAttrString(clpfd_mod, "_sync_real");
    fn_eq_propagate_bignum = PyObject_GetAttrString(clpfd_mod, "_eq_propagate_bignum");
    fn_ne_propagate_bignum = PyObject_GetAttrString(clpfd_mod, "_ne_propagate_bignum");
    fn_lt_propagate_bignum = PyObject_GetAttrString(clpfd_mod, "_lt_propagate_bignum");
    fn_le_propagate_bignum = PyObject_GetAttrString(clpfd_mod, "_le_propagate_bignum");
    fn_sum_propagate_bignum = PyObject_GetAttrString(clpfd_mod, "_sum_propagate_bignum");
    fn_scalar_propagate_bignum = PyObject_GetAttrString(clpfd_mod, "_scalar_propagate_bignum");
    Py_DECREF(clpfd_mod);

    if (!fn_expr_domain || !fn_resolve || !fn_eval_ground ||
        !fn_any_real || !fn_both_ground ||
        !fn_collect_constraint_vars || !fn_collect_vars_from || !fn_linearise ||
        !fn_eq_propagate_bignum || !fn_ne_propagate_bignum ||
        !fn_lt_propagate_bignum || !fn_le_propagate_bignum ||
        !fn_sum_propagate_bignum || !fn_scalar_propagate_bignum)
        return NULL;

    /* Try to import CLP(R) functions (optional) */
    PyObject *clpr_mod = PyImport_ImportModule("clausal.logic.clpr");
    if (clpr_mod) {
        fn_real_eq = PyObject_GetAttrString(clpr_mod, "real_eq");
        fn_real_ne = PyObject_GetAttrString(clpr_mod, "real_ne");
        fn_real_lt = PyObject_GetAttrString(clpr_mod, "real_lt");
        fn_real_le = PyObject_GetAttrString(clpr_mod, "real_le");
        REAL_KEY = PyObject_GetAttrString(clpr_mod, "REAL_KEY");
        Py_DECREF(clpr_mod);
        /* Clear any errors from missing attributes */
        if (!fn_real_eq || !fn_real_ne || !fn_real_lt || !fn_real_le || !REAL_KEY) {
            PyErr_Clear();
            Py_XDECREF(fn_real_eq); fn_real_eq = NULL;
            Py_XDECREF(fn_real_ne); fn_real_ne = NULL;
            Py_XDECREF(fn_real_lt); fn_real_lt = NULL;
            Py_XDECREF(fn_real_le); fn_real_le = NULL;
            Py_XDECREF(REAL_KEY); REAL_KEY = NULL;
        }
    } else {
        PyErr_Clear();
    }

    /* Try to cache expression type objects for fast isinstance in fd_eq.
     * These are optional — if clausal.terms isn't available yet, fd_eq
     * will simply skip the linearisation fast-path. */
    {
        PyObject *terms_mod = PyImport_ImportModule("clausal.terms");
        if (terms_mod) {
            type_Add    = (PyTypeObject *)PyObject_GetAttrString(terms_mod, "Add");
            type_Sub    = (PyTypeObject *)PyObject_GetAttrString(terms_mod, "Sub");
            type_Mult   = (PyTypeObject *)PyObject_GetAttrString(terms_mod, "Mult");
            type_Negate = (PyTypeObject *)PyObject_GetAttrString(terms_mod, "Negate");
            Py_DECREF(terms_mod);
            if (!type_Add || !type_Sub || !type_Mult || !type_Negate) {
                PyErr_Clear();
                Py_XDECREF(type_Add);    type_Add = NULL;
                Py_XDECREF(type_Sub);    type_Sub = NULL;
                Py_XDECREF(type_Mult);   type_Mult = NULL;
                Py_XDECREF(type_Negate); type_Negate = NULL;
            }
        } else {
            PyErr_Clear();
        }
    }

    /* Try to import mixed rational/real check (optional) */
    {
        PyObject *clpfd_mod = PyImport_ImportModule("clausal.logic.clpfd");
        if (clpfd_mod) {
            fn_check_no_mixed = PyObject_GetAttrString(
                clpfd_mod, "_check_no_mixed_rational_real");
            if (!fn_check_no_mixed) {
                PyErr_Clear();
                fn_check_no_mixed = NULL;
            }
            Py_DECREF(clpfd_mod);
        } else {
            PyErr_Clear();
        }
    }

    /* Try to import CLP(Q) functions (optional) */
    fn_any_rational = PyObject_GetAttrString(
        PyImport_ImportModule("clausal.logic.clpfd"), "_any_rational");
    if (!fn_any_rational) {
        PyErr_Clear();
        fn_any_rational = NULL;
    }
    PyObject *clpq_mod = PyImport_ImportModule("clausal.logic.clpq");
    if (clpq_mod) {
        fn_q_eq = PyObject_GetAttrString(clpq_mod, "q_eq");
        fn_q_ne = PyObject_GetAttrString(clpq_mod, "q_ne");
        fn_q_lt = PyObject_GetAttrString(clpq_mod, "q_lt");
        fn_q_le = PyObject_GetAttrString(clpq_mod, "q_le");
        Py_DECREF(clpq_mod);
        if (!fn_q_eq || !fn_q_ne || !fn_q_lt || !fn_q_le) {
            PyErr_Clear();
            Py_XDECREF(fn_q_eq); fn_q_eq = NULL;
            Py_XDECREF(fn_q_ne); fn_q_ne = NULL;
            Py_XDECREF(fn_q_lt); fn_q_lt = NULL;
            Py_XDECREF(fn_q_le); fn_q_le = NULL;
        }
    } else {
        PyErr_Clear();
    }

    /* Create cached constants */
    FD_KEY_STR = PyUnicode_InternFromString("fd");
    if (!FD_KEY_STR) return NULL;

    /* Default domain: ((-inf, +inf),) */
    DEFAULT_DOMAIN = domain_from_range_i64(INT64_MIN, INT64_MAX);
    if (!DEFAULT_DOMAIN) return NULL;

    /* Ready type objects */
    if (PyType_Ready(&FDVarType) < 0) return NULL;
    if (PyType_Ready(&ConstraintBaseType) < 0) return NULL;
    if (PyType_Ready(&EqConstraintType) < 0) return NULL;
    if (PyType_Ready(&NeConstraintType) < 0) return NULL;
    if (PyType_Ready(&LtConstraintType) < 0) return NULL;
    if (PyType_Ready(&LeConstraintType) < 0) return NULL;
    if (PyType_Ready(&AllDiffConstraintType) < 0) return NULL;
    if (PyType_Ready(&SumConstraintType) < 0) return NULL;
    if (PyType_Ready(&ScalarProductConstraintType) < 0) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

    /* Add types to module */
    Py_INCREF(&FDVarType);
    if (PyModule_AddObject(m, "FDVar", (PyObject *)&FDVarType) < 0) goto error;
    Py_INCREF(&ConstraintBaseType);
    if (PyModule_AddObject(m, "Constraint", (PyObject *)&ConstraintBaseType) < 0) goto error;
    Py_INCREF(&EqConstraintType);
    if (PyModule_AddObject(m, "EqConstraint", (PyObject *)&EqConstraintType) < 0) goto error;
    Py_INCREF(&NeConstraintType);
    if (PyModule_AddObject(m, "NeConstraint", (PyObject *)&NeConstraintType) < 0) goto error;
    Py_INCREF(&LtConstraintType);
    if (PyModule_AddObject(m, "LtConstraint", (PyObject *)&LtConstraintType) < 0) goto error;
    Py_INCREF(&LeConstraintType);
    if (PyModule_AddObject(m, "LeConstraint", (PyObject *)&LeConstraintType) < 0) goto error;
    Py_INCREF(&AllDiffConstraintType);
    if (PyModule_AddObject(m, "AllDiffConstraint", (PyObject *)&AllDiffConstraintType) < 0) goto error;
    Py_INCREF(&SumConstraintType);
    if (PyModule_AddObject(m, "SumConstraint", (PyObject *)&SumConstraintType) < 0) goto error;
    Py_INCREF(&ScalarProductConstraintType);
    if (PyModule_AddObject(m, "ScalarProductConstraint", (PyObject *)&ScalarProductConstraintType) < 0) goto error;

    return m;

error:
    Py_DECREF(m);
    return NULL;
}
