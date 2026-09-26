/*
 * _tabling_core.c — C-accelerated tabling key computation
 *
 * Provides C implementations of the hot-path functions in tabling.py
 * and solve.py that dominate tabling benchmarks:
 *
 *   _normalize_for_key(term)       — variant key normalisation
 *   make_subgoal_key(args, trail)  — tuple of normalised args
 *   _deref_walk(term)              — deep dereference / freeze
 *   freeze_args(args, trail)       — tuple of deref-walked args
 *   _unify_answer(args, stored, trail) — pairwise unification
 *
 * These are called hundreds of thousands of times with shallow per-call
 * work.  The bottleneck is Python function-call / frame-creation overhead,
 * which C eliminates.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

/* Import the C API capsule from _variables — gives us deref, is_var,
 * is_term_instance, term_field_names, unify, etc. as direct C calls. */
#define VARIABLES_CAPI_CONSUMER
#include "variables/_variables_capi.h"

/* ================================================================
 * Forward declarations and cached references
 * ================================================================ */

static PyObject *Compound_type = NULL;

/* Cached interned strings */
static PyObject *str_functor = NULL;
static PyObject *str_args = NULL;
static PyObject *str___name__ = NULL;
static PyObject *str___list__ = NULL;
static PyObject *str___tuple__ = NULL;   /* A04-F005 */
static PyObject *str___dict__ = NULL;    /* A04-F005 */
static PyObject *str___set__ = NULL;     /* A04-F005 */
/* _VAR sentinel — set by _register_var_sentinel() from tabling.py */
static PyObject *VAR_sentinel = NULL;

#define MAX_DEPTH 50000

/* ================================================================
 * Inline helpers using the C API capsule
 * ================================================================ */

static inline int
is_var_unbound(PyObject *term)
{
    /* term has already been deref'd via VarAPI->deref */
    return VarAPI->is_var(term);
}

/* ================================================================
 * _normalize_for_key — recursive variant-key normalisation
 * ================================================================ */

static PyObject *
do_normalize(PyObject *term, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "_normalize_for_key: term nesting too deep");
        return NULL;
    }

    term = VarAPI->deref(term);

    /* Fast path: int (most common in benchmarks) */
    if (PyLong_CheckExact(term)) {
        Py_INCREF(term);
        return term;
    }

    /* Unbound Var → _VAR sentinel */
    if (is_var_unbound(term)) {
        Py_INCREF(VAR_sentinel);
        return VAR_sentinel;
    }

    /* None */
    if (term == Py_None) {
        Py_INCREF(term);
        return term;
    }

    /* A04-F006: type-tag numeric leaves (bool/float/complex) as (type, value)
     * so 1/True/1.0 do not conflate in variant keys or answer dedup. Exact int
     * is canonical (the fast path above); non-exact int, str and bytes stay
     * raw. Keep in lock-step with _normalize_for_key_py. Decimal/Fraction are
     * intentionally left raw in BOTH (documented residual, A01-D001). */
    if (PyBool_Check(term) || PyFloat_Check(term) || PyComplex_Check(term)) {
        return PyTuple_Pack(2, (PyObject *)Py_TYPE(term), term);
    }
    if (PyLong_Check(term) || PyUnicode_Check(term) || PyBytes_Check(term)) {
        Py_INCREF(term);
        return term;
    }

    /* List → ("__list__", elem0, elem1, ...) */
    if (PyList_Check(term)) {
        Py_ssize_t n = PyList_GET_SIZE(term);
        PyObject *result = PyTuple_New(n + 1);
        if (!result) return NULL;
        Py_INCREF(str___list__);
        PyTuple_SET_ITEM(result, 0, str___list__);
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *elem = do_normalize(PyList_GET_ITEM(term, i), depth + 1);
            if (!elem) { Py_DECREF(result); return NULL; }
            PyTuple_SET_ITEM(result, i + 1, elem);
        }
        return result;
    }

    /* A04-F005: tuple → ("__tuple__", elem0, ...) */
    if (PyTuple_Check(term)) {
        Py_ssize_t n = PyTuple_GET_SIZE(term);
        PyObject *result = PyTuple_New(n + 1);
        if (!result) return NULL;
        Py_INCREF(str___tuple__);
        PyTuple_SET_ITEM(result, 0, str___tuple__);
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *elem = do_normalize(PyTuple_GET_ITEM(term, i), depth + 1);
            if (!elem) { Py_DECREF(result); return NULL; }
            PyTuple_SET_ITEM(result, i + 1, elem);
        }
        return result;
    }

    /* A04-F005: dict → ("__dict__", frozenset{(nk, nv), ...}) — order-free so
     * a rebuilt answer dict keys identically regardless of insertion order. */
    if (PyDict_Check(term)) {
        PyObject *pairs = PySet_New(NULL);
        if (!pairs) return NULL;
        PyObject *k, *v;
        Py_ssize_t pos = 0;
        while (PyDict_Next(term, &pos, &k, &v)) {
            PyObject *nk = do_normalize(k, depth + 1);
            if (!nk) { Py_DECREF(pairs); return NULL; }
            PyObject *nv = do_normalize(v, depth + 1);
            if (!nv) { Py_DECREF(nk); Py_DECREF(pairs); return NULL; }
            PyObject *pair = PyTuple_Pack(2, nk, nv);
            Py_DECREF(nk); Py_DECREF(nv);
            if (!pair) { Py_DECREF(pairs); return NULL; }
            int rc = PySet_Add(pairs, pair);
            Py_DECREF(pair);
            if (rc < 0) { Py_DECREF(pairs); return NULL; }
        }
        PyObject *frozen = PyFrozenSet_New(pairs);
        Py_DECREF(pairs);
        if (!frozen) return NULL;
        PyObject *result = PyTuple_Pack(2, str___dict__, frozen);
        Py_DECREF(frozen);
        return result;
    }

    /* A04-F005: set/frozenset → ("__set__", frozenset{ne, ...}) */
    if (PyAnySet_Check(term)) {
        PyObject *elems = PySet_New(NULL);
        if (!elems) return NULL;
        PyObject *iter = PyObject_GetIter(term);
        if (!iter) { Py_DECREF(elems); return NULL; }
        PyObject *item;
        while ((item = PyIter_Next(iter))) {
            PyObject *ne = do_normalize(item, depth + 1);
            Py_DECREF(item);
            if (!ne) { Py_DECREF(iter); Py_DECREF(elems); return NULL; }
            int rc = PySet_Add(elems, ne);
            Py_DECREF(ne);
            if (rc < 0) { Py_DECREF(iter); Py_DECREF(elems); return NULL; }
        }
        Py_DECREF(iter);
        if (PyErr_Occurred()) { Py_DECREF(elems); return NULL; }
        PyObject *frozen = PyFrozenSet_New(elems);
        Py_DECREF(elems);
        if (!frozen) return NULL;
        PyObject *result = PyTuple_Pack(2, str___set__, frozen);
        Py_DECREF(frozen);
        return result;
    }

    /* Compound → (functor, arg0, arg1, ...) */
    if (Compound_type) {
        int r = PyObject_IsInstance(term, Compound_type);
        if (r < 0) return NULL;
        if (r) {
            PyObject *functor = PyObject_GetAttr(term, str_functor);
            if (!functor) return NULL;
            PyObject *args = PyObject_GetAttr(term, str_args);
            if (!args) { Py_DECREF(functor); return NULL; }
            if (!PyTuple_Check(args)) {
                Py_DECREF(functor);
                Py_DECREF(args);
                PyErr_SetString(PyExc_TypeError, "Compound.args is not a tuple");
                return NULL;
            }
            Py_ssize_t n = PyTuple_GET_SIZE(args);
            PyObject *result = PyTuple_New(n + 1);
            if (!result) { Py_DECREF(functor); Py_DECREF(args); return NULL; }
            PyTuple_SET_ITEM(result, 0, functor);  /* steals ref */
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *elem = do_normalize(PyTuple_GET_ITEM(args, i), depth + 1);
                if (!elem) { Py_DECREF(args); Py_DECREF(result); return NULL; }
                PyTuple_SET_ITEM(result, i + 1, elem);
            }
            Py_DECREF(args);
            return result;
        }
    }

    /* Term instance (a @dataclass instance) → (class_name, field0, ...) */
    {
        int ti = VarAPI->is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) {
            PyObject *cls_name = PyObject_GetAttr(
                (PyObject *)Py_TYPE(term), str___name__);
            if (!cls_name) return NULL;
            PyObject *fields = VarAPI->term_field_names(term);
            if (!fields) { Py_DECREF(cls_name); return NULL; }
            if (!PyTuple_Check(fields)) {
                Py_DECREF(cls_name);
                Py_DECREF(fields);
                PyErr_SetString(PyExc_TypeError,
                                "term_field_names did not return a tuple");
                return NULL;
            }
            Py_ssize_t n = PyTuple_GET_SIZE(fields);
            PyObject *result = PyTuple_New(n + 1);
            if (!result) { Py_DECREF(cls_name); Py_DECREF(fields); return NULL; }
            PyTuple_SET_ITEM(result, 0, cls_name);  /* steals ref */
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *val = PyObject_GetAttr(
                    term, PyTuple_GET_ITEM(fields, i));
                if (!val) {
                    Py_DECREF(fields);
                    Py_DECREF(result);
                    return NULL;
                }
                PyObject *normed = do_normalize(val, depth + 1);
                Py_DECREF(val);
                if (!normed) {
                    Py_DECREF(fields);
                    Py_DECREF(result);
                    return NULL;
                }
                PyTuple_SET_ITEM(result, i + 1, normed);
            }
            Py_DECREF(fields);
            return result;
        }
    }

    /* Fallback: return as-is */
    Py_INCREF(term);
    return term;
}

static PyObject *
py_normalize_for_key(PyObject *Py_UNUSED(module), PyObject *term)
{
    if (!VAR_sentinel) {
        PyErr_SetString(PyExc_RuntimeError,
                        "_normalize_for_key: _VAR sentinel not registered");
        return NULL;
    }
    return do_normalize(term, 0);
}

/* ================================================================
 * make_subgoal_key(args, trail) → tuple
 * ================================================================ */

static PyObject *
py_make_subgoal_key(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *py_args, *trail;
    if (!PyArg_ParseTuple(args, "OO", &py_args, &trail))
        return NULL;

    if (!PyTuple_Check(py_args) && !PyList_Check(py_args)) {
        PyErr_SetString(PyExc_TypeError,
                        "make_subgoal_key: args must be a tuple or list");
        return NULL;
    }

    Py_ssize_t n;
    int is_tuple = PyTuple_Check(py_args);
    if (is_tuple)
        n = PyTuple_GET_SIZE(py_args);
    else
        n = PyList_GET_SIZE(py_args);

    PyObject *result = PyTuple_New(n);
    if (!result) return NULL;

    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *item = is_tuple
            ? PyTuple_GET_ITEM(py_args, i)
            : PyList_GET_ITEM(py_args, i);
        PyObject *normed = do_normalize(item, 0);
        if (!normed) { Py_DECREF(result); return NULL; }
        PyTuple_SET_ITEM(result, i, normed);
    }
    return result;
}

/* ================================================================
 * _deref_walk — deep dereference, preserving structure
 * ================================================================ */

static PyObject *
do_deref_walk(PyObject *term, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "_deref_walk: term nesting too deep");
        return NULL;
    }

    term = VarAPI->deref(term);

    /* Unbound Var — return as-is */
    if (is_var_unbound(term)) {
        Py_INCREF(term);
        return term;
    }

    /* None, bool, int, float, str, bytes, complex — return as-is */
    if (term == Py_None || PyBool_Check(term) || PyLong_Check(term) ||
        PyFloat_Check(term) || PyUnicode_Check(term) || PyBytes_Check(term) ||
        PyComplex_Check(term)) {
        Py_INCREF(term);
        return term;
    }

    /* List → [deref_walk(e) for e in term] */
    if (PyList_Check(term)) {
        Py_ssize_t n = PyList_GET_SIZE(term);
        PyObject *result = PyList_New(n);
        if (!result) return NULL;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *elem = do_deref_walk(PyList_GET_ITEM(term, i), depth + 1);
            if (!elem) { Py_DECREF(result); return NULL; }
            PyList_SET_ITEM(result, i, elem);
        }
        return result;
    }

    /* Tuple → (deref_walk(e) for e in term) — A01-F008: was blind, so tuple
     * templates (findall snapshot path) decayed after backtracking. */
    if (PyTuple_Check(term)) {
        Py_ssize_t n = PyTuple_GET_SIZE(term);
        PyObject *result = PyTuple_New(n);
        if (!result) return NULL;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *elem = do_deref_walk(PyTuple_GET_ITEM(term, i), depth + 1);
            if (!elem) { Py_DECREF(result); return NULL; }
            PyTuple_SET_ITEM(result, i, elem);
        }
        return result;
    }

    /* A04-F005: plain dict → {deref_walk(k): deref_walk(v)} so a frozen answer
     * holding a dict does not share live inner Vars that unbind on backtrack. */
    if (PyDict_Check(term)) {
        PyObject *result = PyDict_New();
        if (!result) return NULL;
        PyObject *k, *v;
        Py_ssize_t pos = 0;
        while (PyDict_Next(term, &pos, &k, &v)) {
            PyObject *wk = do_deref_walk(k, depth + 1);
            if (!wk) { Py_DECREF(result); return NULL; }
            PyObject *wv = do_deref_walk(v, depth + 1);
            if (!wv) { Py_DECREF(wk); Py_DECREF(result); return NULL; }
            int rc = PyDict_SetItem(result, wk, wv);
            Py_DECREF(wk); Py_DECREF(wv);
            if (rc < 0) { Py_DECREF(result); return NULL; }
        }
        return result;
    }

    /* A04-F005: set/frozenset → walk each element, preserving the exact type. */
    if (PyAnySet_Check(term)) {
        PyObject *walked = PyList_New(0);
        if (!walked) return NULL;
        PyObject *iter = PyObject_GetIter(term);
        if (!iter) { Py_DECREF(walked); return NULL; }
        PyObject *item;
        while ((item = PyIter_Next(iter))) {
            PyObject *we = do_deref_walk(item, depth + 1);
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

    /* __walk__ protocol (A01-F008): Compound, KWTerm, DictTerm and the Seg
     * types all supply __walk__, which deep-substitutes bindings via the
     * canonical walk(). This unifies _deref_walk with walk (they were blind to
     * disjoint type sets) and preserves Compound _position + F018 promotion. */
    {
        PyObject *hook = PyObject_GetAttrString(term, "__walk__");
        if (hook) {
            PyObject *result = PyObject_CallNoArgs(hook);
            Py_DECREF(hook);
            return result;  /* NULL propagates error */
        }
        PyErr_Clear();
    }

    /* Term instance (a @dataclass instance) */
    {
        int ti = VarAPI->is_term_instance(term);
        if (ti < 0) return NULL;
        if (ti) {
            PyObject *fields = VarAPI->term_field_names(term);
            if (!fields) return NULL;
            if (!PyTuple_Check(fields)) {
                Py_DECREF(fields);
                PyErr_SetString(PyExc_TypeError,
                                "term_field_names did not return a tuple");
                return NULL;
            }
            Py_ssize_t n = PyTuple_GET_SIZE(fields);

            /* The Phase-0 fast-path gate that used to precede this (calling
             * a "_clausal_new" positional classmethod when PredicateMeta
             * had attached one) was retired in W4b, 2026-09-23: that
             * classmethod and its minter are gone since W4a, so the gate
             * always fell through to the kwargs reconstruction below on
             * every call -- see solve.py's _deref_walk_py. */

            PyObject *kwargs = PyDict_New();
            if (!kwargs) { Py_DECREF(fields); return NULL; }
            for (Py_ssize_t i = 0; i < n; i++) {
                PyObject *fname = PyTuple_GET_ITEM(fields, i);
                PyObject *val = PyObject_GetAttr(term, fname);
                if (!val) {
                    Py_DECREF(fields);
                    Py_DECREF(kwargs);
                    return NULL;
                }
                PyObject *walked = do_deref_walk(val, depth + 1);
                Py_DECREF(val);
                if (!walked) {
                    Py_DECREF(fields);
                    Py_DECREF(kwargs);
                    return NULL;
                }
                if (PyDict_SetItem(kwargs, fname, walked) < 0) {
                    Py_DECREF(walked);
                    Py_DECREF(fields);
                    Py_DECREF(kwargs);
                    return NULL;
                }
                Py_DECREF(walked);
            }
            Py_DECREF(fields);
            PyObject *cls = (PyObject *)Py_TYPE(term);
            PyObject *empty_args = PyTuple_New(0);
            if (!empty_args) { Py_DECREF(kwargs); return NULL; }
            PyObject *result = PyObject_Call(cls, empty_args, kwargs);
            Py_DECREF(empty_args);
            Py_DECREF(kwargs);
            return result;
        }
    }

    /* Fallback */
    Py_INCREF(term);
    return term;
}

static PyObject *
py_deref_walk(PyObject *Py_UNUSED(module), PyObject *term)
{
    return do_deref_walk(term, 0);
}

/* ================================================================
 * freeze_args(args, trail) → tuple
 * ================================================================ */

static PyObject *
py_freeze_args(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *py_args, *trail;
    if (!PyArg_ParseTuple(args, "OO", &py_args, &trail))
        return NULL;

    Py_ssize_t n;
    int is_tuple = PyTuple_Check(py_args);
    if (is_tuple)
        n = PyTuple_GET_SIZE(py_args);
    else if (PyList_Check(py_args))
        n = PyList_GET_SIZE(py_args);
    else {
        PyErr_SetString(PyExc_TypeError,
                        "freeze_args: args must be a tuple or list");
        return NULL;
    }

    PyObject *result = PyTuple_New(n);
    if (!result) return NULL;

    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *item = is_tuple
            ? PyTuple_GET_ITEM(py_args, i)
            : PyList_GET_ITEM(py_args, i);
        PyObject *walked = do_deref_walk(item, 0);
        if (!walked) { Py_DECREF(result); return NULL; }
        PyTuple_SET_ITEM(result, i, walked);
    }
    return result;
}

/* ================================================================
 * _unify_answer(args, stored, trail) → bool
 * ================================================================ */

static PyObject *
py_unify_answer(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *py_args, *stored, *trail;
    if (!PyArg_ParseTuple(args, "OOO", &py_args, &stored, &trail))
        return NULL;
    if (!Trail_Check(trail)) {
        PyErr_SetString(PyExc_TypeError, "_unify_answer: third arg must be a Trail");
        return NULL;
    }

    /* Support both tuple and list for args/stored */
    Py_ssize_t n1, n2;
    int args_is_tuple = PyTuple_Check(py_args);
    int stored_is_tuple = PyTuple_Check(stored);

    if (args_is_tuple) n1 = PyTuple_GET_SIZE(py_args);
    else if (PyList_Check(py_args)) n1 = PyList_GET_SIZE(py_args);
    else { PyErr_SetString(PyExc_TypeError, "args must be tuple or list"); return NULL; }

    if (stored_is_tuple) n2 = PyTuple_GET_SIZE(stored);
    else if (PyList_Check(stored)) n2 = PyList_GET_SIZE(stored);
    else { PyErr_SetString(PyExc_TypeError, "stored must be tuple or list"); return NULL; }

    Py_ssize_t n = n1 < n2 ? n1 : n2;

    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *a = args_is_tuple
            ? PyTuple_GET_ITEM(py_args, i)
            : PyList_GET_ITEM(py_args, i);
        PyObject *s = stored_is_tuple
            ? PyTuple_GET_ITEM(stored, i)
            : PyList_GET_ITEM(stored, i);

        PyObject *r = VarAPI->unify(a, s, (TrailObject *)trail);
        if (!r) return NULL;
        int truthy = (r == Py_True);
        Py_DECREF(r);
        if (!truthy)
            Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
}

/* ================================================================
 * Registration functions — called from Python at import time
 * ================================================================ */

static PyObject *
py_register_var_sentinel(PyObject *Py_UNUSED(module), PyObject *sentinel)
{
    Py_XDECREF(VAR_sentinel);
    Py_INCREF(sentinel);
    VAR_sentinel = sentinel;
    Py_RETURN_NONE;
}

static int
import_compound_type(void)
{
    PyObject *mod = PyImport_ImportModule("clausal.terms");
    if (!mod) return -1;
    Compound_type = PyObject_GetAttrString(mod, "Compound");
    Py_DECREF(mod);
    if (!Compound_type) return -1;
    return 0;
}

/* ================================================================
 * Module definition
 * ================================================================ */

static PyMethodDef module_methods[] = {
    {"_normalize_for_key", py_normalize_for_key, METH_O,
     "Deref term and replace unbound Vars with _VAR sentinel for variant key."},
    {"make_subgoal_key", (PyCFunction)py_make_subgoal_key, METH_VARARGS,
     "Compute variant key for a tabled call's arguments."},
    {"_deref_walk", py_deref_walk, METH_O,
     "Fully dereference a term, recursively walking all Var bindings."},
    {"freeze_args", (PyCFunction)py_freeze_args, METH_VARARGS,
     "Capture a ground snapshot of current arg bindings."},
    {"_unify_answer", (PyCFunction)py_unify_answer, METH_VARARGS,
     "Unify each arg with the corresponding stored value."},
    {"_register_var_sentinel", py_register_var_sentinel, METH_O,
     "Register the _VAR sentinel object from tabling.py."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_tabling_core",
    "C-accelerated tabling key computation.\n"
    "\n"
    "Provides fast implementations of _normalize_for_key, make_subgoal_key,\n"
    "_deref_walk, freeze_args, and _unify_answer for the tabling subsystem.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__tabling_core(void)
{
    /* Import the C API capsule from _variables */
    if (import_variables_capi() < 0)
        return NULL;

    /* Import the Compound type from clausal.terms */
    if (import_compound_type() < 0)
        return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif

    /* Intern frequently-used attribute name strings */
    str_functor = PyUnicode_InternFromString("functor");
    str_args = PyUnicode_InternFromString("args");
    str___name__ = PyUnicode_InternFromString("__name__");
    str___list__ = PyUnicode_InternFromString("__list__");
    str___tuple__ = PyUnicode_InternFromString("__tuple__");
    str___dict__ = PyUnicode_InternFromString("__dict__");
    str___set__ = PyUnicode_InternFromString("__set__");
    if (!str_functor || !str_args || !str___name__ || !str___list__ ||
        !str___tuple__ || !str___dict__ || !str___set__) {
        Py_DECREF(m);
        return NULL;
    }

    return m;
}
