/*
 * _clpfd_core.c — C-accelerated CLP(FD) domain operations.
 *
 * Domains are represented as Python tuples of (lo, hi) 2-tuples,
 * where each pair is an inclusive integer interval.  Intervals are
 * sorted by lo, non-overlapping, non-adjacent.
 *
 * Example: {1,2,3,5,7,8} = ((1,3), (5,5), (7,8))
 *
 * This module accelerates the hot-path domain operations that are
 * called millions of times during constraint propagation.
 */

#include "_clpfd_domain_ops.h"

/* ================================================================
 * domain_from_range(lo, hi) -> Domain
 * ================================================================ */

static PyObject *
py_domain_from_range(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *lo_obj, *hi_obj;
    if (!PyArg_ParseTuple(args, "OO", &lo_obj, &hi_obj))
        return NULL;

    int64_t lo, hi;

    /* Parse lo */
    if (PyFloat_Check(lo_obj)) {
        double v = PyFloat_AS_DOUBLE(lo_obj);
        if (v == -HUGE_VAL || v == -(1.0/0.0))
            lo = INT64_MIN;
        else {
            PyErr_SetString(PyExc_TypeError, "lo must be int or -inf");
            return NULL;
        }
    } else {
        lo = PyLong_AsLongLong(lo_obj);
        if (lo == -1 && PyErr_Occurred()) return NULL;
    }

    /* Parse hi */
    if (PyFloat_Check(hi_obj)) {
        double v = PyFloat_AS_DOUBLE(hi_obj);
        if (v == HUGE_VAL || v == (1.0/0.0))
            hi = INT64_MAX;
        else {
            PyErr_SetString(PyExc_TypeError, "hi must be int or +inf");
            return NULL;
        }
    } else {
        hi = PyLong_AsLongLong(hi_obj);
        if (hi == -1 && PyErr_Occurred()) return NULL;
    }

    if (lo > hi) {
        /* Empty domain */
        return PyTuple_New(0);
    }

    PyObject *pair = make_interval(lo, hi);
    if (!pair) return NULL;

    PyObject *result = PyTuple_New(1);
    if (!result) { Py_DECREF(pair); return NULL; }
    PyTuple_SET_ITEM(result, 0, pair);
    return result;
}

/* ================================================================
 * domain_contains(domain, value) -> bool
 * ================================================================ */

static PyObject *
py_domain_contains(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *domain;
    long long value;
    if (!PyArg_ParseTuple(args, "O!L", &PyTuple_Type, &domain, &value))
        return NULL;

    Py_ssize_t n = PyTuple_GET_SIZE(domain);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *pair = PyTuple_GET_ITEM(domain, i);
        int64_t lo, hi;
        if (unpack_interval(pair, &lo, &hi) < 0) return NULL;
        if (lo <= (int64_t)value && (int64_t)value <= hi)
            Py_RETURN_TRUE;
        if ((int64_t)value < lo)
            Py_RETURN_FALSE;
    }
    Py_RETURN_FALSE;
}

/* ================================================================
 * domain_min(domain) -> int
 * ================================================================ */

static PyObject *
py_domain_min(PyObject *self, PyObject *arg)
{
    (void)self;
    if (!PyTuple_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected tuple");
        return NULL;
    }
    if (PyTuple_GET_SIZE(arg) == 0) {
        PyErr_SetString(PyExc_ValueError, "empty domain");
        return NULL;
    }
    PyObject *first = PyTuple_GET_ITEM(arg, 0);
    PyObject *lo = PyTuple_GET_ITEM(first, 0);
    Py_INCREF(lo);
    return lo;
}

/* ================================================================
 * domain_max(domain) -> int
 * ================================================================ */

static PyObject *
py_domain_max(PyObject *self, PyObject *arg)
{
    (void)self;
    if (!PyTuple_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected tuple");
        return NULL;
    }
    Py_ssize_t n = PyTuple_GET_SIZE(arg);
    if (n == 0) {
        PyErr_SetString(PyExc_ValueError, "empty domain");
        return NULL;
    }
    PyObject *last = PyTuple_GET_ITEM(arg, n - 1);
    PyObject *hi = PyTuple_GET_ITEM(last, 1);
    Py_INCREF(hi);
    return hi;
}

/* ================================================================
 * domain_size(domain) -> int | float('inf')
 * ================================================================ */

static PyObject *
py_domain_size(PyObject *self, PyObject *arg)
{
    (void)self;
    if (!PyTuple_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected tuple");
        return NULL;
    }
    Py_ssize_t n = PyTuple_GET_SIZE(arg);
    long long total = 0;
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *pair = PyTuple_GET_ITEM(arg, i);
        int64_t lo, hi;
        if (unpack_interval(pair, &lo, &hi) < 0) return NULL;
        if (lo == INT64_MIN || hi == INT64_MAX)
            return PyFloat_FromDouble(HUGE_VAL);
        total += (hi - lo + 1);
    }
    return PyLong_FromLongLong(total);
}

/* ================================================================
 * domain_singleton(domain) -> int | None
 * ================================================================ */

static PyObject *
py_domain_singleton(PyObject *self, PyObject *arg)
{
    (void)self;
    if (!PyTuple_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected tuple");
        return NULL;
    }
    if (PyTuple_GET_SIZE(arg) == 1) {
        PyObject *pair = PyTuple_GET_ITEM(arg, 0);
        PyObject *lo = PyTuple_GET_ITEM(pair, 0);
        PyObject *hi = PyTuple_GET_ITEM(pair, 1);
        int eq = PyObject_RichCompareBool(lo, hi, Py_EQ);
        if (eq < 0) return NULL;
        if (eq) {
            Py_INCREF(lo);
            return lo;
        }
    }
    Py_RETURN_NONE;
}

/* ================================================================
 * domain_intersection(d1, d2) -> Domain
 * ================================================================ */

static PyObject *
py_domain_intersection(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *d1, *d2;
    if (!PyArg_ParseTuple(args, "O!O!", &PyTuple_Type, &d1,
                          &PyTuple_Type, &d2))
        return NULL;

    Py_ssize_t n1 = PyTuple_GET_SIZE(d1);
    Py_ssize_t n2 = PyTuple_GET_SIZE(d2);

    /* Fast path: either empty */
    if (n1 == 0 || n2 == 0)
        return PyTuple_New(0);

    /* Allocate workspace for result intervals */
    Py_ssize_t max_result = n1 + n2;  /* upper bound */
    int64_t stack_buf[STACK_INTERVALS * 2];
    int64_t *buf = stack_buf;
    if (max_result > STACK_INTERVALS) {
        buf = (int64_t *)PyMem_Malloc(max_result * 2 * sizeof(int64_t));
        if (!buf) return PyErr_NoMemory();
    }

    Py_ssize_t i = 0, j = 0, count = 0;
    int64_t a_lo, a_hi, b_lo, b_hi;

    /* Unpack first intervals */
    if (unpack_interval(PyTuple_GET_ITEM(d1, 0), &a_lo, &a_hi) < 0) goto error;
    if (unpack_interval(PyTuple_GET_ITEM(d2, 0), &b_lo, &b_hi) < 0) goto error;

    while (i < n1 && j < n2) {
        int64_t lo = a_lo > b_lo ? a_lo : b_lo;
        int64_t hi = a_hi < b_hi ? a_hi : b_hi;
        if (lo <= hi) {
            buf[2*count] = lo;
            buf[2*count+1] = hi;
            count++;
        }
        if (a_hi < b_hi) {
            i++;
            if (i < n1) {
                if (unpack_interval(PyTuple_GET_ITEM(d1, i), &a_lo, &a_hi) < 0)
                    goto error;
            }
        } else {
            j++;
            if (j < n2) {
                if (unpack_interval(PyTuple_GET_ITEM(d2, j), &b_lo, &b_hi) < 0)
                    goto error;
            }
        }
    }

    PyObject *result = intervals_to_tuple(buf, count);
    if (buf != stack_buf) PyMem_Free(buf);
    return result;

error:
    if (buf != stack_buf) PyMem_Free(buf);
    return NULL;
}

/* ================================================================
 * domain_remove(domain, value) -> Domain
 * ================================================================ */

static PyObject *
py_domain_remove(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *domain;
    long long value;
    if (!PyArg_ParseTuple(args, "O!L", &PyTuple_Type, &domain, &value))
        return NULL;

    Py_ssize_t n = PyTuple_GET_SIZE(domain);
    if (n == 0)
        return PyTuple_New(0);

    /* Worst case: one interval splits into two, so max n+1 */
    int64_t stack_buf[(STACK_INTERVALS + 1) * 2];
    int64_t *buf = stack_buf;
    if (n + 1 > STACK_INTERVALS) {
        buf = (int64_t *)PyMem_Malloc((n + 1) * 2 * sizeof(int64_t));
        if (!buf) return PyErr_NoMemory();
    }

    Py_ssize_t count = 0;
    int64_t val = (int64_t)value;

    for (Py_ssize_t i = 0; i < n; i++) {
        int64_t lo, hi;
        if (unpack_interval(PyTuple_GET_ITEM(domain, i), &lo, &hi) < 0)
            goto error;

        if (val < lo || val > hi) {
            /* Value not in this interval — keep as-is */
            buf[2*count] = lo;
            buf[2*count+1] = hi;
            count++;
        } else {
            /* Value is in [lo, hi] — split */
            if (lo < val) {
                buf[2*count] = lo;
                buf[2*count+1] = val - 1;
                count++;
            }
            if (val < hi) {
                buf[2*count] = val + 1;
                buf[2*count+1] = hi;
                count++;
            }
        }
    }

    PyObject *result = intervals_to_tuple(buf, count);
    if (buf != stack_buf) PyMem_Free(buf);
    return result;

error:
    if (buf != stack_buf) PyMem_Free(buf);
    return NULL;
}

/* ================================================================
 * domain_remove_above(domain, limit) -> Domain
 * ================================================================ */

static PyObject *
py_domain_remove_above(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *domain, *limit_obj;
    if (!PyArg_ParseTuple(args, "O!O", &PyTuple_Type, &domain, &limit_obj))
        return NULL;

    int64_t lim;
    if (PyFloat_Check(limit_obj)) {
        double v = PyFloat_AS_DOUBLE(limit_obj);
        if (v == HUGE_VAL || v == (1.0/0.0)) {
            /* remove_above(+inf) is a no-op — return domain unchanged */
            Py_INCREF(domain);
            return domain;
        } else if (v == -HUGE_VAL || v == -(1.0/0.0)) {
            lim = INT64_MIN;
        } else {
            lim = (int64_t)v;
        }
    } else {
        lim = PyLong_AsLongLong(limit_obj);
        if (lim == -1 && PyErr_Occurred()) return NULL;
    }

    Py_ssize_t n = PyTuple_GET_SIZE(domain);
    int64_t stack_buf[STACK_INTERVALS * 2];
    int64_t *buf = stack_buf;
    if (n > STACK_INTERVALS) {
        buf = (int64_t *)PyMem_Malloc(n * 2 * sizeof(int64_t));
        if (!buf) return PyErr_NoMemory();
    }

    Py_ssize_t count = 0;

    for (Py_ssize_t i = 0; i < n; i++) {
        int64_t lo, hi;
        if (unpack_interval(PyTuple_GET_ITEM(domain, i), &lo, &hi) < 0)
            goto error;
        if (lo > lim)
            break;
        buf[2*count] = lo;
        buf[2*count+1] = hi < lim ? hi : lim;
        count++;
    }

    PyObject *result = intervals_to_tuple(buf, count);
    if (buf != stack_buf) PyMem_Free(buf);
    return result;

error:
    if (buf != stack_buf) PyMem_Free(buf);
    return NULL;
}

/* ================================================================
 * domain_remove_below(domain, limit) -> Domain
 * ================================================================ */

static PyObject *
py_domain_remove_below(PyObject *self, PyObject *args)
{
    (void)self;
    PyObject *domain, *limit_obj;
    if (!PyArg_ParseTuple(args, "O!O", &PyTuple_Type, &domain, &limit_obj))
        return NULL;

    int64_t lim;
    if (PyFloat_Check(limit_obj)) {
        double v = PyFloat_AS_DOUBLE(limit_obj);
        if (v == -HUGE_VAL || v == -(1.0/0.0)) {
            /* remove_below(-inf) is a no-op — return domain unchanged */
            Py_INCREF(domain);
            return domain;
        } else if (v == HUGE_VAL || v == (1.0/0.0)) {
            lim = INT64_MAX;
        } else {
            lim = (int64_t)v;
        }
    } else {
        lim = PyLong_AsLongLong(limit_obj);
        if (lim == -1 && PyErr_Occurred()) return NULL;
    }

    Py_ssize_t n = PyTuple_GET_SIZE(domain);
    int64_t stack_buf[STACK_INTERVALS * 2];
    int64_t *buf = stack_buf;
    if (n > STACK_INTERVALS) {
        buf = (int64_t *)PyMem_Malloc(n * 2 * sizeof(int64_t));
        if (!buf) return PyErr_NoMemory();
    }

    Py_ssize_t count = 0;

    for (Py_ssize_t i = 0; i < n; i++) {
        int64_t lo, hi;
        if (unpack_interval(PyTuple_GET_ITEM(domain, i), &lo, &hi) < 0)
            goto error;
        if (hi < lim)
            continue;
        buf[2*count] = lo > lim ? lo : lim;
        buf[2*count+1] = hi;
        count++;
    }

    PyObject *result = intervals_to_tuple(buf, count);
    if (buf != stack_buf) PyMem_Free(buf);
    return result;

error:
    if (buf != stack_buf) PyMem_Free(buf);
    return NULL;
}

/* ================================================================
 * domain_values(domain) -> list of ints
 *
 * Unlike the Python generator version, returns a list for simplicity.
 * Raises ValueError on unbounded domains.
 * ================================================================ */

static PyObject *
py_domain_values(PyObject *self, PyObject *arg)
{
    (void)self;
    if (!PyTuple_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected tuple");
        return NULL;
    }

    Py_ssize_t n = PyTuple_GET_SIZE(arg);

    /* First pass: check for unbounded and compute total size */
    Py_ssize_t total = 0;
    for (Py_ssize_t i = 0; i < n; i++) {
        int64_t lo, hi;
        if (unpack_interval(PyTuple_GET_ITEM(arg, i), &lo, &hi) < 0)
            return NULL;
        if (lo == INT64_MIN || hi == INT64_MAX) {
            PyErr_SetString(PyExc_ValueError,
                "Cannot enumerate unbounded domain. "
                "Use in_domain/3 to declare bounds before labeling.");
            return NULL;
        }
        total += (hi - lo + 1);
    }

    PyObject *result = PyList_New(total);
    if (!result) return NULL;

    Py_ssize_t idx = 0;
    for (Py_ssize_t i = 0; i < n; i++) {
        int64_t lo, hi;
        /* Already validated above, won't fail */
        unpack_interval(PyTuple_GET_ITEM(arg, i), &lo, &hi);
        for (int64_t v = lo; v <= hi; v++) {
            PyObject *val = PyLong_FromLongLong(v);
            if (!val) { Py_DECREF(result); return NULL; }
            PyList_SET_ITEM(result, idx++, val);
        }
    }

    return result;
}

/* ================================================================
 * Module definition
 * ================================================================ */

static PyMethodDef module_methods[] = {
    {"domain_from_range",   py_domain_from_range,   METH_VARARGS,
     "Create a single-interval domain [lo, hi]."},
    {"domain_contains",     py_domain_contains,     METH_VARARGS,
     "Check if value is in the domain."},
    {"domain_min",          py_domain_min,          METH_O,
     "Minimum value in domain."},
    {"domain_max",          py_domain_max,          METH_O,
     "Maximum value in domain."},
    {"domain_size",         py_domain_size,         METH_O,
     "Number of values in domain, or inf if unbounded."},
    {"domain_singleton",    py_domain_singleton,    METH_O,
     "If domain is a single value, return it; otherwise None."},
    {"domain_intersection", py_domain_intersection, METH_VARARGS,
     "Intersection of two domains."},
    {"domain_remove",       py_domain_remove,       METH_VARARGS,
     "Remove a single value from domain."},
    {"domain_remove_above", py_domain_remove_above, METH_VARARGS,
     "Remove all values > limit from domain."},
    {"domain_remove_below", py_domain_remove_below, METH_VARARGS,
     "Remove all values < limit from domain."},
    {"domain_values",       py_domain_values,       METH_O,
     "List of all values in a finite domain."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_clpfd_core",
    "C-accelerated CLP(FD) domain operations.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__clpfd_core(void)
{
    return PyModule_Create(&moduledef);
}
