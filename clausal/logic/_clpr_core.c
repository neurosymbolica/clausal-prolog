/*
 * _clpr_core.c — C-accelerated CLP(R) interval arithmetic.
 *
 * Intervals are represented as pairs of IEEE 754 doubles (lo, hi)
 * with outward rounding: lo is rounded toward -inf and hi toward +inf
 * after every operation, guaranteeing the true real value is always
 * inside the interval.
 *
 * Outward rounding uses nextafter() for portability (same as the
 * Python reference implementation).
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <float.h>

/* ── Outward rounding helpers ─────────────────────────────────────── */

static inline double dn(double x) {
    return nextafter(x, -INFINITY);
}

static inline double up(double x) {
    return nextafter(x, INFINITY);
}

/* ── Helper: build a 2-tuple of floats ────────────────────────────── */

static inline PyObject *
make_pair(double lo, double hi)
{
    PyObject *result = PyTuple_New(2);
    if (!result) return NULL;
    PyObject *lo_obj = PyFloat_FromDouble(lo);
    if (!lo_obj) { Py_DECREF(result); return NULL; }
    PyObject *hi_obj = PyFloat_FromDouble(hi);
    if (!hi_obj) { Py_DECREF(lo_obj); Py_DECREF(result); return NULL; }
    PyTuple_SET_ITEM(result, 0, lo_obj);
    PyTuple_SET_ITEM(result, 1, hi_obj);
    return result;
}

/* ── Helper: NaN-safe min/max of 4 doubles ────────────────────────── */
/* fmin/fmax (C99) treat NaN as missing: fmin(NaN,x)=x, fmax(NaN,x)=x.
 * This gives correct interval bounds when 0*inf produces NaN corners. */

static inline double min4(double a, double b, double c, double d) {
    return fmin(fmin(a, b), fmin(c, d));
}

static inline double max4(double a, double b, double c, double d) {
    return fmax(fmax(a, b), fmax(c, d));
}

/* ================================================================
 * _dn(x) -> float
 * ================================================================ */

static PyObject *
py_dn(PyObject *self, PyObject *args)
{
    (void)self;
    double x;
    if (!PyArg_ParseTuple(args, "d", &x))
        return NULL;
    return PyFloat_FromDouble(dn(x));
}

/* ================================================================
 * _up(x) -> float
 * ================================================================ */

static PyObject *
py_up(PyObject *self, PyObject *args)
{
    (void)self;
    double x;
    if (!PyArg_ParseTuple(args, "d", &x))
        return NULL;
    return PyFloat_FromDouble(up(x));
}

/* ================================================================
 * _iadd(alo, ahi, blo, bhi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_iadd(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi, blo, bhi;
    if (!PyArg_ParseTuple(args, "dddd", &alo, &ahi, &blo, &bhi))
        return NULL;
    return make_pair(dn(alo + blo), up(ahi + bhi));
}

/* ================================================================
 * _isub(alo, ahi, blo, bhi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_isub(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi, blo, bhi;
    if (!PyArg_ParseTuple(args, "dddd", &alo, &ahi, &blo, &bhi))
        return NULL;
    return make_pair(dn(alo - bhi), up(ahi - blo));
}

/* ================================================================
 * _imul(alo, ahi, blo, bhi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_imul(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi, blo, bhi;
    if (!PyArg_ParseTuple(args, "dddd", &alo, &ahi, &blo, &bhi))
        return NULL;
    double c1 = alo * blo, c2 = alo * bhi, c3 = ahi * blo, c4 = ahi * bhi;
    return make_pair(dn(min4(c1, c2, c3, c4)), up(max4(c1, c2, c3, c4)));
}

/* ================================================================
 * _idiv(alo, ahi, blo, bhi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_idiv(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi, blo, bhi;
    if (!PyArg_ParseTuple(args, "dddd", &alo, &ahi, &blo, &bhi))
        return NULL;
    if (blo <= 0.0 && 0.0 <= bhi)
        return make_pair(-INFINITY, INFINITY);
    double c1 = alo / blo, c2 = alo / bhi, c3 = ahi / blo, c4 = ahi / bhi;
    return make_pair(dn(min4(c1, c2, c3, c4)), up(max4(c1, c2, c3, c4)));
}

/* ================================================================
 * _ipow_int(alo, ahi, n) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_ipow_int(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    int n;
    if (!PyArg_ParseTuple(args, "ddi", &alo, &ahi, &n))
        return NULL;

    if (n == 0)
        return make_pair(1.0, 1.0);

    if (n < 0) {
        /* Recurse for positive power, then invert */
        double lo, hi;
        int pn = -n;
        /* Inline the positive-power logic */
        if (pn % 2 == 0) {
            if (alo <= 0.0 && 0.0 <= ahi) {
                lo = 0.0;
            } else {
                double a1 = fabs(alo), a2 = fabs(ahi);
                double mn = a1 < a2 ? a1 : a2;
                lo = pow(mn, pn);
            }
            double a1 = fabs(alo), a2 = fabs(ahi);
            double mx = a1 > a2 ? a1 : a2;
            hi = pow(mx, pn);
            lo = dn(lo);
            hi = up(hi);
        } else {
            lo = dn(pow(alo, pn));
            hi = up(pow(ahi, pn));
        }
        /* Invert: [1,1] / [lo,hi] */
        if (lo <= 0.0 && 0.0 <= hi)
            return make_pair(-INFINITY, INFINITY);
        double c1 = 1.0 / lo, c2 = 1.0 / hi;
        double rlo = c1 < c2 ? c1 : c2;
        double rhi = c1 > c2 ? c1 : c2;
        return make_pair(dn(rlo), up(rhi));
    }

    if (n % 2 == 0) {
        double lo_val, hi_val;
        if (alo <= 0.0 && 0.0 <= ahi) {
            lo_val = 0.0;
        } else {
            double a1 = fabs(alo), a2 = fabs(ahi);
            double mn = a1 < a2 ? a1 : a2;
            lo_val = pow(mn, n);
        }
        double a1 = fabs(alo), a2 = fabs(ahi);
        double mx = a1 > a2 ? a1 : a2;
        hi_val = pow(mx, n);
        return make_pair(dn(lo_val), up(hi_val));
    }

    /* Odd power: monotone increasing */
    return make_pair(dn(pow(alo, n)), up(pow(ahi, n)));
}

/* ================================================================
 * _isqrt(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_isqrt(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;
    double lo = alo > 0.0 ? alo : 0.0;
    if (lo > ahi)
        return make_pair(NAN, NAN);
    return make_pair(dn(sqrt(lo)), up(sqrt(ahi)));
}

/* ================================================================
 * _iabs(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_iabs(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;
    if (alo >= 0.0)
        return make_pair(alo, ahi);
    if (ahi <= 0.0)
        return make_pair(-ahi, -alo);
    double mx = -alo > ahi ? -alo : ahi;
    return make_pair(0.0, mx);
}

/* ================================================================
 * _isin(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_isin(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;

    if (ahi - alo >= 2.0 * M_PI)
        return make_pair(-1.0, 1.0);

    double half_pi = M_PI / 2.0;
    double lo_val = sin(alo);
    double hi_val = sin(ahi);
    double mn = fmin(lo_val, hi_val);
    double mx = fmax(lo_val, hi_val);

    /* Use double for loop bounds to avoid long overflow on large angles.
     * The loop runs at most ~4 iterations (critical points of sin are at
     * multiples of pi/2, and we already returned [-1,1] if width >= 2pi). */
    double k_lo = ceil(alo / half_pi);
    double k_hi = floor(ahi / half_pi);

    for (double k = k_lo; k <= k_hi; k += 1.0) {
        double v = sin(k * half_pi);
        mn = fmin(mn, v);
        mx = fmax(mx, v);
    }

    return make_pair(dn(mn), up(mx));
}

/* ================================================================
 * _icos(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_icos(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;

    if (ahi - alo >= 2.0 * M_PI)
        return make_pair(-1.0, 1.0);

    double lo_val = cos(alo);
    double hi_val = cos(ahi);
    double mn = fmin(lo_val, hi_val);
    double mx = fmax(lo_val, hi_val);

    double k_lo = ceil(alo / M_PI);
    double k_hi = floor(ahi / M_PI);

    for (double k = k_lo; k <= k_hi; k += 1.0) {
        double v = cos(k * M_PI);
        mn = fmin(mn, v);
        mx = fmax(mx, v);
    }

    return make_pair(dn(mn), up(mx));
}

/* ================================================================
 * _iexp(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_iexp(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;
    return make_pair(dn(exp(alo)), up(exp(ahi)));
}

/* ================================================================
 * _ilog(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_ilog(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;
    if (ahi <= 0.0)
        return make_pair(NAN, NAN);
    if (alo <= 0.0)
        return make_pair(-INFINITY, up(log(ahi)));
    return make_pair(dn(log(alo)), up(log(ahi)));
}

/* ================================================================
 * _iatan(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_iatan(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;
    return make_pair(dn(atan(alo)), up(atan(ahi)));
}

/* ================================================================
 * _iasin(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_iasin(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;
    double clo = alo > -1.0 ? alo : -1.0;
    double chi = ahi < 1.0 ? ahi : 1.0;
    if (clo > chi)
        return make_pair(NAN, NAN);
    return make_pair(dn(asin(clo)), up(asin(chi)));
}

/* ================================================================
 * _iacos(alo, ahi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_iacos(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi;
    if (!PyArg_ParseTuple(args, "dd", &alo, &ahi))
        return NULL;
    double clo = alo > -1.0 ? alo : -1.0;
    double chi = ahi < 1.0 ? ahi : 1.0;
    if (clo > chi)
        return make_pair(NAN, NAN);
    /* acos is monotone decreasing */
    return make_pair(dn(acos(chi)), up(acos(clo)));
}

/* ================================================================
 * _ifloordiv(alo, ahi, blo, bhi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_ifloordiv(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi, blo, bhi;
    if (!PyArg_ParseTuple(args, "dddd", &alo, &ahi, &blo, &bhi))
        return NULL;
    if (blo <= 0.0 && 0.0 <= bhi)
        return make_pair(-INFINITY, INFINITY);
    double c1 = floor(alo / blo), c2 = floor(alo / bhi);
    double c3 = floor(ahi / blo), c4 = floor(ahi / bhi);
    return make_pair(min4(c1, c2, c3, c4), max4(c1, c2, c3, c4));
}

/* ================================================================
 * _imod(alo, ahi, blo, bhi) -> (lo, hi)
 * ================================================================ */

static PyObject *
py_imod(PyObject *self, PyObject *args)
{
    (void)self;
    double alo, ahi, blo, bhi;
    if (!PyArg_ParseTuple(args, "dddd", &alo, &ahi, &blo, &bhi))
        return NULL;
    if (blo <= 0.0 && 0.0 <= bhi)
        return make_pair(-INFINITY, INFINITY);
    double abs_blo = fabs(blo), abs_bhi = fabs(bhi);
    double abs_max = abs_blo > abs_bhi ? abs_blo : abs_bhi;
    if (blo > 0.0)
        return make_pair(0.0, up(abs_max - 1.0));
    return make_pair(dn(-(abs_max - 1.0)), 0.0);
}

/* ================================================================
 * Module definition
 * ================================================================ */

static PyMethodDef module_methods[] = {
    {"_dn",          py_dn,          METH_VARARGS,
     "Round x toward -inf by one ULP."},
    {"_up",          py_up,          METH_VARARGS,
     "Round x toward +inf by one ULP."},
    {"_iadd",        py_iadd,        METH_VARARGS,
     "Interval addition."},
    {"_isub",        py_isub,        METH_VARARGS,
     "Interval subtraction."},
    {"_imul",        py_imul,        METH_VARARGS,
     "Interval multiplication."},
    {"_idiv",        py_idiv,        METH_VARARGS,
     "Interval division."},
    {"_ipow_int",    py_ipow_int,    METH_VARARGS,
     "Interval integer power."},
    {"_isqrt",       py_isqrt,       METH_VARARGS,
     "Interval square root."},
    {"_iabs",        py_iabs,        METH_VARARGS,
     "Interval absolute value."},
    {"_isin",        py_isin,        METH_VARARGS,
     "Interval sine."},
    {"_icos",        py_icos,        METH_VARARGS,
     "Interval cosine."},
    {"_iexp",        py_iexp,        METH_VARARGS,
     "Interval exponential."},
    {"_ilog",        py_ilog,        METH_VARARGS,
     "Interval natural logarithm."},
    {"_iatan",       py_iatan,       METH_VARARGS,
     "Interval arctangent."},
    {"_iasin",       py_iasin,       METH_VARARGS,
     "Interval arcsine."},
    {"_iacos",       py_iacos,       METH_VARARGS,
     "Interval arccosine."},
    {"_ifloordiv",   py_ifloordiv,   METH_VARARGS,
     "Interval floor division."},
    {"_imod",        py_imod,        METH_VARARGS,
     "Interval modulo."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_clpr_core",
    "C-accelerated CLP(R) interval arithmetic.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__clpr_core(void)
{
    return PyModule_Create(&moduledef);
}
