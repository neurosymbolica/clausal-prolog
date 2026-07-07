/*
 * _arithmetic_core.c — C-accelerated arithmetic predicates.
 *
 * Provides C implementations of: between/3, succ/2, plus/3, abs_/2,
 * max_/3, min_/3, sign/2, gcd/3, divmod_/4, lcm/3, exp_mod/4,
 * popcount/2, msb/2, lsb/2.
 *
 * Uses the _variables C API capsule for direct deref / is_var / unify /
 * trail_mark / trail_undo access.
 *
 * Return protocol for each predicate function:
 *   - PyLong (mark):  unification succeeded; caller should yield then
 *                     trail.undo(mark).
 *   - Py_True:        success with no trail to undo (between/3 check mode).
 *   - Py_None:        no solution (type-check fail, unify fail, etc.).
 *   - Py_False:       Quantity detected — fall back to Python impl.
 *   - Tuple:          special (between/3 generate mode returns (lo, hi)).
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#define VARIABLES_CAPI_CONSUMER
#include "variables/_variables_capi.h"

/* ── Cached references (set during module init) ──────────────────────── */

static PyObject *Quantity_type = NULL;   /* clausal.terms.Quantity */
static PyObject *cached_zero = NULL;     /* PyLong(0) */
static PyObject *cached_one = NULL;      /* PyLong(1) */
static PyObject *math_gcd_func = NULL;   /* math.gcd */

/* Check if obj is a Quantity instance.  Returns 1/0/-1 (error). */
static inline int
is_quantity(PyObject *obj)
{
    if (!Quantity_type) return 0;
    return PyObject_IsInstance(obj, Quantity_type);
}

/*
 * Check is_quantity and propagate errors.  Returns:
 *   1  → is Quantity (caller should Py_RETURN_FALSE to fall back)
 *   0  → not Quantity (continue in C)
 *  -1  → error (caller should return NULL)
 */
#define CHECK_QUANTITY(obj) do { \
    int _q = is_quantity(obj); \
    if (_q < 0) return NULL; \
    if (_q) Py_RETURN_FALSE; \
} while (0)

/* ── Helpers ──────────────────────────────────────────────────────────── */

/*
 * Check that val is a plain int (not bool).
 */
static inline int
is_plain_int(PyObject *val)
{
    return PyLong_Check(val) && !PyBool_Check(val);
}

/*
 * Check that val is a plain int or float (not bool).
 */
static inline int
is_numeric(PyObject *val)
{
    if (PyBool_Check(val)) return 0;
    return PyLong_Check(val) || PyFloat_Check(val);
}

/*
 * Do mark + unify + conditional undo.  On success returns new-ref
 * PyLong(mark).  On failure (unify returned False) undoes and returns
 * new-ref Py_None.  On error returns NULL.
 */
static PyObject *
mark_unify(PyObject *target, PyObject *value, TrailObject *trail)
{
    Py_ssize_t mark = VarAPI->trail_mark(trail);
    PyObject *u = VarAPI->unify(target, value, trail);
    if (!u) { VarAPI->trail_undo(trail, mark); return NULL; }
    int ok = (u == Py_True);
    Py_DECREF(u);
    if (ok) {
        return PyLong_FromSsize_t(mark);
    }
    VarAPI->trail_undo(trail, mark);
    Py_RETURN_NONE;
}

/*
 * Two-arg unification: unify both target1=val1 and target2=val2 under
 * a single trail mark.  Returns PyLong(mark) on full success, Py_None
 * on any failure (trail undone), NULL on error.
 */
static PyObject *
mark_unify2(PyObject *t1, PyObject *v1,
            PyObject *t2, PyObject *v2,
            TrailObject *trail)
{
    Py_ssize_t mark = VarAPI->trail_mark(trail);

    PyObject *u1 = VarAPI->unify(t1, v1, trail);
    if (!u1) { VarAPI->trail_undo(trail, mark); return NULL; }
    int ok1 = (u1 == Py_True);
    Py_DECREF(u1);
    if (!ok1) { VarAPI->trail_undo(trail, mark); Py_RETURN_NONE; }

    PyObject *u2 = VarAPI->unify(t2, v2, trail);
    if (!u2) { VarAPI->trail_undo(trail, mark); return NULL; }
    int ok2 = (u2 == Py_True);
    Py_DECREF(u2);
    if (!ok2) { VarAPI->trail_undo(trail, mark); Py_RETURN_NONE; }

    return PyLong_FromSsize_t(mark);
}

/* ── between/3 ────────────────────────────────────────────────────────── */

static PyObject *
py_arith_between(PyObject *self, PyObject *args)
{
    PyObject *low, *high, *x, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOO", &low, &high, &x, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *low_val = VarAPI->deref(low);
    PyObject *high_val = VarAPI->deref(high);
    if (VarAPI->is_var(low_val) || VarAPI->is_var(high_val))
        Py_RETURN_NONE;
    if (!is_plain_int(low_val) || !is_plain_int(high_val))
        Py_RETURN_NONE;

    PyObject *x_val = VarAPI->deref(x);
    if (!VarAPI->is_var(x_val)) {
        /* Check mode: x already bound */
        if (!is_plain_int(x_val)) Py_RETURN_NONE;
        int ge = PyObject_RichCompareBool(x_val, low_val, Py_GE);
        if (ge < 0) return NULL;
        if (!ge) Py_RETURN_NONE;
        int le = PyObject_RichCompareBool(x_val, high_val, Py_LE);
        if (le < 0) return NULL;
        if (!le) Py_RETURN_NONE;
        /* In range — x is already bound, no unification needed.
           Return True as a sentinel for "success, no mark to undo". */
        Py_RETURN_TRUE;
    }
    /* Generate mode: return (lo, hi) tuple for Python to iterate */
    return Py_BuildValue("(OO)", low_val, high_val);
}

/* ── succ/2 ───────────────────────────────────────────────────────────── */

static PyObject *
py_arith_succ(PyObject *self, PyObject *args)
{
    PyObject *x, *y, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &x, &y, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *x_val = VarAPI->deref(x);
    PyObject *y_val = VarAPI->deref(y);

    if (!VarAPI->is_var(x_val)) {
        if (!is_plain_int(x_val)) Py_RETURN_NONE;
        /* x >= 0 */
        int ge = PyObject_RichCompareBool(x_val, cached_zero, Py_GE);
        if (ge < 0) return NULL;
        if (!ge) Py_RETURN_NONE;
        PyObject *result = PyNumber_Add(x_val, cached_one);
        if (!result) return NULL;
        PyObject *ret = mark_unify(y, result, trail);
        Py_DECREF(result);
        return ret;
    }
    if (!VarAPI->is_var(y_val)) {
        if (!is_plain_int(y_val)) Py_RETURN_NONE;
        /* y > 0  (i.e. y >= 1) */
        int gt = PyObject_RichCompareBool(y_val, cached_zero, Py_GT);
        if (gt < 0) return NULL;
        if (!gt) Py_RETURN_NONE;
        PyObject *result = PyNumber_Subtract(y_val, cached_one);
        if (!result) return NULL;
        PyObject *ret = mark_unify(x, result, trail);
        Py_DECREF(result);
        return ret;
    }
    /* Both unbound — no solution */
    Py_RETURN_NONE;
}

/* ── plus/3 ───────────────────────────────────────────────────────────── */

static PyObject *
py_arith_plus(PyObject *self, PyObject *args)
{
    PyObject *x, *y, *z, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOO", &x, &y, &z, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    PyObject *yv = VarAPI->deref(y);
    PyObject *zv = VarAPI->deref(z);
    int x_known = !VarAPI->is_var(xv);
    int y_known = !VarAPI->is_var(yv);
    int z_known = !VarAPI->is_var(zv);

    /* Check for Quantity → fall back */
    if (x_known) { CHECK_QUANTITY(xv); }
    if (y_known) { CHECK_QUANTITY(yv); }
    if (z_known) { CHECK_QUANTITY(zv); }

    /* plus/3 is a numeric relation: reject non-numeric known operands so a
     * string operand can't silently concatenate (forward) or raise a
     * TypeError from PyNumber_Subtract (inverse) — fail cleanly instead
     * (A06-F015). */
    if (x_known && !is_numeric(xv)) Py_RETURN_NONE;
    if (y_known && !is_numeric(yv)) Py_RETURN_NONE;
    if (z_known && !is_numeric(zv)) Py_RETURN_NONE;

    PyObject *result, *ret;

    if (x_known && y_known) {
        result = PyNumber_Add(xv, yv);
        if (!result) return NULL;
        ret = mark_unify(z, result, trail);
        Py_DECREF(result);
        return ret;
    }
    if (x_known && z_known) {
        result = PyNumber_Subtract(zv, xv);
        if (!result) return NULL;
        ret = mark_unify(y, result, trail);
        Py_DECREF(result);
        return ret;
    }
    if (y_known && z_known) {
        result = PyNumber_Subtract(zv, yv);
        if (!result) return NULL;
        ret = mark_unify(x, result, trail);
        Py_DECREF(result);
        return ret;
    }
    Py_RETURN_NONE;
}

/* ── abs_/2 ───────────────────────────────────────────────────────────── */

static PyObject *
py_arith_abs(PyObject *self, PyObject *args)
{
    PyObject *x, *y, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &x, &y, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    if (VarAPI->is_var(xv)) Py_RETURN_NONE;
    CHECK_QUANTITY(xv);
    if (!is_numeric(xv)) Py_RETURN_NONE;

    PyObject *result = PyNumber_Absolute(xv);
    if (!result) return NULL;
    PyObject *ret = mark_unify(y, result, trail);
    Py_DECREF(result);
    return ret;
}

/* ── max_/3 ───────────────────────────────────────────────────────────── */

static PyObject *
py_arith_max(PyObject *self, PyObject *args)
{
    PyObject *x, *y, *z, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOO", &x, &y, &z, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    PyObject *yv = VarAPI->deref(y);
    if (VarAPI->is_var(xv) || VarAPI->is_var(yv)) Py_RETURN_NONE;
    CHECK_QUANTITY(xv);
    CHECK_QUANTITY(yv);
    if (!is_numeric(xv) || !is_numeric(yv)) Py_RETURN_NONE;  /* A06-F015 */

    int cmp = PyObject_RichCompareBool(xv, yv, Py_GT);
    if (cmp < 0) return NULL;
    PyObject *result = cmp ? xv : yv;
    return mark_unify(z, result, trail);
}

/* ── min_/3 ───────────────────────────────────────────────────────────── */

static PyObject *
py_arith_min(PyObject *self, PyObject *args)
{
    PyObject *x, *y, *z, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOO", &x, &y, &z, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    PyObject *yv = VarAPI->deref(y);
    if (VarAPI->is_var(xv) || VarAPI->is_var(yv)) Py_RETURN_NONE;
    CHECK_QUANTITY(xv);
    CHECK_QUANTITY(yv);
    if (!is_numeric(xv) || !is_numeric(yv)) Py_RETURN_NONE;  /* A06-F015 */

    int cmp = PyObject_RichCompareBool(xv, yv, Py_LT);
    if (cmp < 0) return NULL;
    PyObject *result = cmp ? xv : yv;
    return mark_unify(z, result, trail);
}

/* ── sign/2 ───────────────────────────────────────────────────────────── */

static PyObject *
py_arith_sign(PyObject *self, PyObject *args)
{
    PyObject *x, *s, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &x, &s, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    if (VarAPI->is_var(xv)) Py_RETURN_NONE;
    CHECK_QUANTITY(xv);
    if (!is_numeric(xv)) Py_RETURN_NONE;

    int gt = PyObject_RichCompareBool(xv, cached_zero, Py_GT);
    if (gt < 0) return NULL;
    int lt = PyObject_RichCompareBool(xv, cached_zero, Py_LT);
    if (lt < 0) return NULL;

    long sign_val = gt - lt;
    PyObject *result = PyLong_FromLong(sign_val);
    if (!result) return NULL;
    PyObject *ret = mark_unify(s, result, trail);
    Py_DECREF(result);
    return ret;
}

/* ── gcd/3 ────────────────────────────────────────────────────────────── */

static PyObject *
py_arith_gcd(PyObject *self, PyObject *args)
{
    PyObject *x, *y, *g, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOO", &x, &y, &g, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    PyObject *yv = VarAPI->deref(y);
    if (VarAPI->is_var(xv) || VarAPI->is_var(yv)) Py_RETURN_NONE;
    CHECK_QUANTITY(xv);
    CHECK_QUANTITY(yv);
    if (!is_plain_int(xv) || !is_plain_int(yv)) Py_RETURN_NONE;

    PyObject *result = PyObject_CallFunctionObjArgs(math_gcd_func, xv, yv, NULL);
    if (!result) return NULL;
    PyObject *ret = mark_unify(g, result, trail);
    Py_DECREF(result);
    return ret;
}

/* ── divmod_/4 ────────────────────────────────────────────────────────── */

static PyObject *
py_arith_divmod(PyObject *self, PyObject *args)
{
    PyObject *x, *y, *q, *r, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOOO", &x, &y, &q, &r, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    PyObject *yv = VarAPI->deref(y);
    if (VarAPI->is_var(xv) || VarAPI->is_var(yv)) Py_RETURN_NONE;
    CHECK_QUANTITY(xv);
    CHECK_QUANTITY(yv);
    if (!is_plain_int(xv) || !is_plain_int(yv)) Py_RETURN_NONE;

    /* Check for zero divisor */
    int is_zero = PyObject_RichCompareBool(yv, cached_zero, Py_EQ);
    if (is_zero < 0) return NULL;
    if (is_zero) Py_RETURN_NONE;

    PyObject *dm = PyNumber_Divmod(xv, yv);
    if (!dm) return NULL;
    PyObject *quotient = PyTuple_GET_ITEM(dm, 0);
    PyObject *remainder = PyTuple_GET_ITEM(dm, 1);

    PyObject *ret = mark_unify2(q, quotient, r, remainder, trail);
    Py_DECREF(dm);
    return ret;
}

/* ── lcm/3 ────────────────────────────────────────────────────────────── */

static PyObject *
py_arith_lcm(PyObject *self, PyObject *args)
{
    PyObject *x, *y, *l, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOO", &x, &y, &l, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    PyObject *yv = VarAPI->deref(y);
    if (VarAPI->is_var(xv) || VarAPI->is_var(yv)) Py_RETURN_NONE;
    CHECK_QUANTITY(xv);
    CHECK_QUANTITY(yv);
    if (!is_plain_int(xv) || !is_plain_int(yv)) Py_RETURN_NONE;

    int xz = PyObject_RichCompareBool(xv, cached_zero, Py_EQ);
    if (xz < 0) return NULL;
    int yz = PyObject_RichCompareBool(yv, cached_zero, Py_EQ);
    if (yz < 0) return NULL;

    PyObject *result;
    if (xz || yz) {
        Py_INCREF(cached_zero);
        result = cached_zero;  /* lcm(0, y) = lcm(x, 0) = 0 */
    } else {
        /* lcm = abs(x*y) // gcd(x,y) */
        PyObject *prod = PyNumber_Multiply(xv, yv);
        if (!prod) return NULL;
        PyObject *abs_prod = PyNumber_Absolute(prod);
        Py_DECREF(prod);
        if (!abs_prod) return NULL;

        PyObject *gcd_val = PyObject_CallFunctionObjArgs(math_gcd_func, xv, yv, NULL);
        if (!gcd_val) { Py_DECREF(abs_prod); return NULL; }

        result = PyNumber_FloorDivide(abs_prod, gcd_val);
        Py_DECREF(abs_prod);
        Py_DECREF(gcd_val);
        if (!result) return NULL;
    }

    PyObject *ret = mark_unify(l, result, trail);
    Py_DECREF(result);
    return ret;
}

/* ── exp_mod/4 ────────────────────────────────────────────────────────── */

static PyObject *
py_arith_exp_mod(PyObject *self, PyObject *args)
{
    PyObject *base, *exp, *mod, *result_arg, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOOOO", &base, &exp, &mod, &result_arg,
                          &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *bv = VarAPI->deref(base);
    PyObject *ev = VarAPI->deref(exp);
    PyObject *mv = VarAPI->deref(mod);
    if (VarAPI->is_var(bv) || VarAPI->is_var(ev) || VarAPI->is_var(mv))
        Py_RETURN_NONE;
    if (!is_plain_int(bv) || !is_plain_int(ev) || !is_plain_int(mv))
        Py_RETURN_NONE;

    /* mod == 0 → no solution */
    int mz = PyObject_RichCompareBool(mv, cached_zero, Py_EQ);
    if (mz < 0) return NULL;
    if (mz) Py_RETURN_NONE;

    /* pow(base, exp, mod) */
    PyObject *result = PyNumber_Power(bv, ev, mv);
    if (!result) return NULL;
    PyObject *ret = mark_unify(result_arg, result, trail);
    Py_DECREF(result);
    return ret;
}

/* ── popcount/2 ───────────────────────────────────────────────────────── */

static PyObject *
py_arith_popcount(PyObject *self, PyObject *args)
{
    PyObject *x, *count, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &x, &count, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    if (VarAPI->is_var(xv)) Py_RETURN_NONE;
    if (!is_plain_int(xv)) Py_RETURN_NONE;

    /* x >= 0 */
    int ge = PyObject_RichCompareBool(xv, cached_zero, Py_GE);
    if (ge < 0) return NULL;
    if (!ge) Py_RETURN_NONE;

    /* bit_count() — available since Python 3.10 */
    PyObject *result = PyObject_CallMethod(xv, "bit_count", NULL);
    if (!result) return NULL;
    PyObject *ret = mark_unify(count, result, trail);
    Py_DECREF(result);
    return ret;
}

/* ── msb/2 ────────────────────────────────────────────────────────────── */

static PyObject *
py_arith_msb(PyObject *self, PyObject *args)
{
    PyObject *x, *bit, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &x, &bit, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    if (VarAPI->is_var(xv)) Py_RETURN_NONE;
    if (!is_plain_int(xv)) Py_RETURN_NONE;

    /* x > 0 */
    int gt = PyObject_RichCompareBool(xv, cached_zero, Py_GT);
    if (gt < 0) return NULL;
    if (!gt) Py_RETURN_NONE;

    /* bit_length() - 1 */
    PyObject *bl = PyObject_CallMethod(xv, "bit_length", NULL);
    if (!bl) return NULL;
    PyObject *result = PyNumber_Subtract(bl, cached_one);
    Py_DECREF(bl);
    if (!result) return NULL;
    PyObject *ret = mark_unify(bit, result, trail);
    Py_DECREF(result);
    return ret;
}

/* ── lsb/2 ────────────────────────────────────────────────────────────── */

static PyObject *
py_arith_lsb(PyObject *self, PyObject *args)
{
    PyObject *x, *bit, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &x, &bit, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *xv = VarAPI->deref(x);
    if (VarAPI->is_var(xv)) Py_RETURN_NONE;
    if (!is_plain_int(xv)) Py_RETURN_NONE;

    /* x > 0 */
    int gt = PyObject_RichCompareBool(xv, cached_zero, Py_GT);
    if (gt < 0) return NULL;
    if (!gt) Py_RETURN_NONE;

    /* (x & -x).bit_length() - 1 */
    PyObject *neg = PyNumber_Negative(xv);
    if (!neg) return NULL;
    PyObject *and_val = PyNumber_And(xv, neg);
    Py_DECREF(neg);
    if (!and_val) return NULL;
    PyObject *bl = PyObject_CallMethod(and_val, "bit_length", NULL);
    Py_DECREF(and_val);
    if (!bl) return NULL;
    PyObject *result = PyNumber_Subtract(bl, cached_one);
    Py_DECREF(bl);
    if (!result) return NULL;
    PyObject *ret = mark_unify(bit, result, trail);
    Py_DECREF(result);
    return ret;
}

/* ── Module method table ──────────────────────────────────────────────── */

static PyMethodDef module_methods[] = {
    {"arith_between",   py_arith_between,   METH_VARARGS,
     "C-accelerated between/3."},
    {"arith_succ",      py_arith_succ,      METH_VARARGS,
     "C-accelerated succ/2."},
    {"arith_plus",      py_arith_plus,      METH_VARARGS,
     "C-accelerated plus/3."},
    {"arith_abs",       py_arith_abs,       METH_VARARGS,
     "C-accelerated abs_/2."},
    {"arith_max",       py_arith_max,       METH_VARARGS,
     "C-accelerated max_/3."},
    {"arith_min",       py_arith_min,       METH_VARARGS,
     "C-accelerated min_/3."},
    {"arith_sign",      py_arith_sign,      METH_VARARGS,
     "C-accelerated sign/2."},
    {"arith_gcd",       py_arith_gcd,       METH_VARARGS,
     "C-accelerated gcd/3."},
    {"arith_divmod",    py_arith_divmod,    METH_VARARGS,
     "C-accelerated divmod_/4."},
    {"arith_lcm",       py_arith_lcm,       METH_VARARGS,
     "C-accelerated lcm/3."},
    {"arith_exp_mod",   py_arith_exp_mod,   METH_VARARGS,
     "C-accelerated exp_mod/4."},
    {"arith_popcount",  py_arith_popcount,  METH_VARARGS,
     "C-accelerated popcount/2."},
    {"arith_msb",       py_arith_msb,       METH_VARARGS,
     "C-accelerated msb/2."},
    {"arith_lsb",       py_arith_lsb,       METH_VARARGS,
     "C-accelerated lsb/2."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_arithmetic_core",
    "C-accelerated arithmetic predicates.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__arithmetic_core(void)
{
    /* Import the _variables C API capsule */
    if (import_variables_capi() < 0) return NULL;

    /* Cache frequently-used constants */
    cached_zero = PyLong_FromLong(0);
    if (!cached_zero) return NULL;
    cached_one = PyLong_FromLong(1);
    if (!cached_one) return NULL;

    /* Cache math.gcd */
    PyObject *math_mod = PyImport_ImportModule("math");
    if (!math_mod) return NULL;
    math_gcd_func = PyObject_GetAttrString(math_mod, "gcd");
    Py_DECREF(math_mod);
    if (!math_gcd_func) return NULL;

    /* Cache the Quantity type (optional — may not exist) */
    PyObject *terms_mod = PyImport_ImportModule("clausal.terms");
    if (terms_mod) {
        Quantity_type = PyObject_GetAttrString(terms_mod, "Quantity");
        Py_DECREF(terms_mod);
        if (!Quantity_type) PyErr_Clear();
    } else {
        PyErr_Clear();
    }

    return PyModule_Create(&moduledef);
}
