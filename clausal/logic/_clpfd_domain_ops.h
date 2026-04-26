/*
 * _clpfd_domain_ops.h — Shared domain operation helpers for CLP(FD) C modules.
 *
 * Included by both _clpfd_core.c (domain operations) and
 * _clpfd_propagate.c (constraint propagation).
 *
 * Domain representation: sorted tuple of (lo, hi) 2-tuples,
 * where each pair is an inclusive integer interval.
 * Intervals are non-overlapping, non-adjacent.
 * float('-inf') maps to INT64_MIN, float('inf') maps to INT64_MAX.
 */

#ifndef _CLPFD_DOMAIN_OPS_H
#define _CLPFD_DOMAIN_OPS_H

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <math.h>

/* Max intervals we'll stack-allocate. Beyond this, heap-allocate. */
#define STACK_INTERVALS 64

/*
 * Unpack a (lo, hi) 2-tuple into C int64_t values.
 * Returns 0 on success, -1 on error.
 *
 * For bignum bounds (Python ints exceeding int64 range), this raises
 * OverflowError via PyLong_AsLongLong.  Callers that want to fall back to
 * a Python implementation for bignum bounds must call has_bignum_bound()
 * up front before invoking this — the design is "gate at the wrapper, not
 * mid-loop", to avoid partial-state cleanup.
 */
static inline int
unpack_interval(PyObject *pair, int64_t *lo, int64_t *hi)
{
    PyObject *lo_obj = PyTuple_GET_ITEM(pair, 0);
    PyObject *hi_obj = PyTuple_GET_ITEM(pair, 1);

    /* Handle float('-inf') and float('inf') */
    if (PyFloat_Check(lo_obj)) {
        double v = PyFloat_AS_DOUBLE(lo_obj);
        if (v == -HUGE_VAL || v == -(1.0/0.0))
            *lo = INT64_MIN;
        else {
            PyErr_SetString(PyExc_TypeError,
                "domain interval bounds must be int or +/-inf");
            return -1;
        }
    } else {
        *lo = PyLong_AsLongLong(lo_obj);
        if (*lo == -1 && PyErr_Occurred()) return -1;
    }

    if (PyFloat_Check(hi_obj)) {
        double v = PyFloat_AS_DOUBLE(hi_obj);
        if (v == HUGE_VAL || v == (1.0/0.0))
            *hi = INT64_MAX;
        else {
            PyErr_SetString(PyExc_TypeError,
                "domain interval bounds must be int or +/-inf");
            return -1;
        }
    } else {
        *hi = PyLong_AsLongLong(hi_obj);
        if (*hi == -1 && PyErr_Occurred()) return -1;
    }
    return 0;
}

/*
 * Detect whether a domain tuple contains any bound that doesn't fit in
 * int64_t (i.e., a Python int >= 2**63 in magnitude).  Such domains arise
 * from CLP(Z) propagation on bignum values (e.g. Fibonacci above N=92).
 *
 * Returns 1 if any bound is bignum, 0 otherwise.  Never raises — domains
 * are always well-formed tuples; non-int / non-inf bounds are caught by
 * unpack_interval at use time.
 */
static inline int
has_bignum_bound(PyObject *domain)
{
    Py_ssize_t n = PyTuple_GET_SIZE(domain);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *pair = PyTuple_GET_ITEM(domain, i);
        for (int j = 0; j < 2; j++) {
            PyObject *b = PyTuple_GET_ITEM(pair, j);
            if (!PyLong_Check(b)) continue;  /* float +/-inf — fits */
            int ov = 0;
            (void)PyLong_AsLongLongAndOverflow(b, &ov);
            if (ov != 0) return 1;
        }
    }
    return 0;
}

/*
 * Detect whether a single Python object is a bignum int (out of int64
 * range).  Used by domain_from_range to short-circuit to the Python
 * reference impl when constructing a bignum-bounded domain.
 *
 * Returns 1 if obj is a Python int outside int64 range, 0 otherwise.
 * Floats (+/-inf) and non-int objects return 0 (handled elsewhere).
 */
static inline int
is_bignum_int(PyObject *obj)
{
    if (!PyLong_Check(obj)) return 0;
    int ov = 0;
    (void)PyLong_AsLongLongAndOverflow(obj, &ov);
    return ov != 0;
}

/*
 * Build a Python (lo, hi) 2-tuple from C int64_t values.
 * Restores float('-inf') / float('inf') for sentinel values.
 */
static inline PyObject *
make_interval(int64_t lo, int64_t hi)
{
    PyObject *lo_obj, *hi_obj, *pair;

    if (lo == INT64_MIN)
        lo_obj = PyFloat_FromDouble(-HUGE_VAL);
    else
        lo_obj = PyLong_FromLongLong(lo);
    if (!lo_obj) return NULL;

    if (hi == INT64_MAX)
        hi_obj = PyFloat_FromDouble(HUGE_VAL);
    else
        hi_obj = PyLong_FromLongLong(hi);
    if (!hi_obj) { Py_DECREF(lo_obj); return NULL; }

    pair = PyTuple_New(2);
    if (!pair) { Py_DECREF(lo_obj); Py_DECREF(hi_obj); return NULL; }
    PyTuple_SET_ITEM(pair, 0, lo_obj);
    PyTuple_SET_ITEM(pair, 1, hi_obj);
    return pair;
}

/*
 * Build a domain tuple from a C array of intervals.
 * buf layout: [lo0, hi0, lo1, hi1, ...] with `count` intervals.
 */
static inline PyObject *
intervals_to_tuple(int64_t *buf, Py_ssize_t count)
{
    PyObject *result = PyTuple_New(count);
    if (!result) return NULL;
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *pair = make_interval(buf[2*i], buf[2*i+1]);
        if (!pair) { Py_DECREF(result); return NULL; }
        PyTuple_SET_ITEM(result, i, pair);
    }
    return result;
}

/* ================================================================
 * Direct C implementations of domain operations
 *
 * These take/return Python objects and call the shared helpers above,
 * allowing the propagation module to use them without going through
 * Python function call overhead.
 * ================================================================ */

/*
 * domain_from_range_c(lo, hi) -> Domain (new ref)
 * lo/hi are Python objects (int or float +-inf).
 */
static inline PyObject *
domain_from_range_c(PyObject *lo_obj, PyObject *hi_obj)
{
    int64_t lo, hi;

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

    if (lo > hi)
        return PyTuple_New(0);

    PyObject *pair = make_interval(lo, hi);
    if (!pair) return NULL;
    PyObject *result = PyTuple_New(1);
    if (!result) { Py_DECREF(pair); return NULL; }
    PyTuple_SET_ITEM(result, 0, pair);
    return result;
}

/* domain_from_range using raw int64_t values */
static inline PyObject *
domain_from_range_i64(int64_t lo, int64_t hi)
{
    if (lo > hi)
        return PyTuple_New(0);
    PyObject *pair = make_interval(lo, hi);
    if (!pair) return NULL;
    PyObject *result = PyTuple_New(1);
    if (!result) { Py_DECREF(pair); return NULL; }
    PyTuple_SET_ITEM(result, 0, pair);
    return result;
}

/*
 * domain_contains_i64(domain, value) -> 1/0/-1(error)
 */
static inline int
domain_contains_i64(PyObject *domain, int64_t value)
{
    Py_ssize_t n = PyTuple_GET_SIZE(domain);
    for (Py_ssize_t i = 0; i < n; i++) {
        int64_t lo, hi;
        if (unpack_interval(PyTuple_GET_ITEM(domain, i), &lo, &hi) < 0)
            return -1;
        if (lo <= value && value <= hi)
            return 1;
        if (value < lo)
            return 0;
    }
    return 0;
}

/*
 * domain_min_i64(domain, out) -> 0 on success, -1 on error
 */
static inline int
domain_min_i64(PyObject *domain, int64_t *out)
{
    if (PyTuple_GET_SIZE(domain) == 0) {
        PyErr_SetString(PyExc_ValueError, "empty domain");
        return -1;
    }
    return unpack_interval(PyTuple_GET_ITEM(domain, 0), out, &(int64_t){0});
}

/*
 * domain_max_i64(domain, out) -> 0 on success, -1 on error
 */
static inline int
domain_max_i64(PyObject *domain, int64_t *out)
{
    Py_ssize_t n = PyTuple_GET_SIZE(domain);
    if (n == 0) {
        PyErr_SetString(PyExc_ValueError, "empty domain");
        return -1;
    }
    return unpack_interval(PyTuple_GET_ITEM(domain, n - 1), &(int64_t){0}, out);
}

/*
 * domain_singleton_val(domain) -> value if singleton, INT64_MIN if not, INT64_MAX on error
 * Special contract: returns INT64_MIN when not singleton (callers must check).
 * To distinguish from actual INT64_MIN value, callers use the Python-level function
 * for unbounded domains.
 */
static inline PyObject *
domain_singleton_c(PyObject *domain)
{
    if (PyTuple_GET_SIZE(domain) == 1) {
        PyObject *pair = PyTuple_GET_ITEM(domain, 0);
        PyObject *lo = PyTuple_GET_ITEM(pair, 0);
        PyObject *hi = PyTuple_GET_ITEM(pair, 1);
        int eq = PyObject_RichCompareBool(lo, hi, Py_EQ);
        if (eq < 0) return NULL;
        if (eq) {
            /* Guard: FD domains are over integers.  If the singleton value
             * is not a Python int (e.g. float('-inf') from an unbounded
             * sentinel), treat it as non-singleton to avoid confusing
             * downstream code that calls PyLong_AsLongLong on the result. */
            if (!PyLong_Check(lo))
                Py_RETURN_NONE;
            Py_INCREF(lo);
            return lo;
        }
    }
    Py_RETURN_NONE;
}

/*
 * domain_intersection_c(d1, d2) -> Domain (new ref)
 */
static inline PyObject *
domain_intersection_c(PyObject *d1, PyObject *d2)
{
    Py_ssize_t n1 = PyTuple_GET_SIZE(d1);
    Py_ssize_t n2 = PyTuple_GET_SIZE(d2);

    if (n1 == 0 || n2 == 0)
        return PyTuple_New(0);

    Py_ssize_t max_result = n1 + n2;
    int64_t stack_buf[STACK_INTERVALS * 2];
    int64_t *buf = stack_buf;
    if (max_result > STACK_INTERVALS) {
        buf = (int64_t *)PyMem_Malloc(max_result * 2 * sizeof(int64_t));
        if (!buf) return PyErr_NoMemory();
    }

    Py_ssize_t i = 0, j = 0, count = 0;
    int64_t a_lo, a_hi, b_lo, b_hi;

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

    {
        PyObject *result = intervals_to_tuple(buf, count);
        if (buf != stack_buf) PyMem_Free(buf);
        return result;
    }

error:
    if (buf != stack_buf) PyMem_Free(buf);
    return NULL;
}

/*
 * domain_remove_c(domain, value) -> Domain (new ref)
 */
static inline PyObject *
domain_remove_c(PyObject *domain, int64_t val)
{
    Py_ssize_t n = PyTuple_GET_SIZE(domain);
    if (n == 0)
        return PyTuple_New(0);

    int64_t stack_buf[(STACK_INTERVALS + 1) * 2];
    int64_t *buf = stack_buf;
    if (n + 1 > STACK_INTERVALS) {
        buf = (int64_t *)PyMem_Malloc((n + 1) * 2 * sizeof(int64_t));
        if (!buf) return PyErr_NoMemory();
    }

    Py_ssize_t count = 0;

    for (Py_ssize_t i = 0; i < n; i++) {
        int64_t lo, hi;
        if (unpack_interval(PyTuple_GET_ITEM(domain, i), &lo, &hi) < 0)
            goto error;

        if (val < lo || val > hi) {
            buf[2*count] = lo;
            buf[2*count+1] = hi;
            count++;
        } else {
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

    {
        PyObject *result = intervals_to_tuple(buf, count);
        if (buf != stack_buf) PyMem_Free(buf);
        return result;
    }

error:
    if (buf != stack_buf) PyMem_Free(buf);
    return NULL;
}

/*
 * domain_remove_above_c(domain, lim) -> Domain (new ref)
 */
static inline PyObject *
domain_remove_above_c(PyObject *domain, int64_t lim)
{
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

    {
        PyObject *result = intervals_to_tuple(buf, count);
        if (buf != stack_buf) PyMem_Free(buf);
        return result;
    }

error:
    if (buf != stack_buf) PyMem_Free(buf);
    return NULL;
}

/*
 * domain_remove_below_c(domain, lim) -> Domain (new ref)
 */
static inline PyObject *
domain_remove_below_c(PyObject *domain, int64_t lim)
{
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

    {
        PyObject *result = intervals_to_tuple(buf, count);
        if (buf != stack_buf) PyMem_Free(buf);
        return result;
    }

error:
    if (buf != stack_buf) PyMem_Free(buf);
    return NULL;
}

/*
 * Parse a Python object that might be int or float +-inf into int64_t.
 * Returns 0 on success, -1 on error.
 *
 * Bignum ints raise OverflowError via PyLong_AsLongLong.  Callers with a
 * bignum fallback path should call is_bignum_int() before this.
 */
static inline int
parse_bound(PyObject *obj, int64_t *out)
{
    if (PyFloat_Check(obj)) {
        double v = PyFloat_AS_DOUBLE(obj);
        if (v == -HUGE_VAL || v == -(1.0/0.0)) {
            *out = INT64_MIN;
            return 0;
        } else if (v == HUGE_VAL || v == (1.0/0.0)) {
            *out = INT64_MAX;
            return 0;
        } else {
            PyErr_SetString(PyExc_TypeError, "bound must be int or +/-inf");
            return -1;
        }
    } else {
        *out = PyLong_AsLongLong(obj);
        if (*out == -1 && PyErr_Occurred()) return -1;
        return 0;
    }
}

#endif /* _CLPFD_DOMAIN_OPS_H */
