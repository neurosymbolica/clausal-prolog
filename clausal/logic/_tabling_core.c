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
#include "variables/_chars_carrier.h"

/* ================================================================
 * Forward declarations and cached references
 * ================================================================ */

/* Cached interned strings */
static PyObject *str___name__ = NULL;
static PyObject *str___list__ = NULL;
static PyObject *str___tuple__ = NULL;   /* A04-F005 */
static PyObject *str___dict__ = NULL;    /* A04-F005 */
static PyObject *str___set__ = NULL;     /* A04-F005 */
static PyObject *str___chars__ = NULL;   /* char-list key */
static PyObject *str_chars_tag = NULL;   /* "$chars", the carrier's tag */
static PyObject *nil_key = NULL;         /* ("__list__",), the key of [] */
/* Seg* classes and tabling._seg_key -- set by _register_seg_key() */
static PyObject *seg_types = NULL;
static PyObject *seg_key_fn = NULL;
/* _VAR sentinel — set by _register_var_sentinel() from tabling.py */
static PyObject *VAR_sentinel = NULL;

#define MAX_DEPTH 50000

/* The depth reached when do_normalize hands a Seg* to tabling._seg_key,
 * which re-enters _normalize_for_key for its elements.  The re-entry
 * resumes counting from here, so MAX_DEPTH bounds the WHOLE term and not
 * each partial-list layer.  Per thread: the callback runs Python code. */
static _Thread_local int seg_depth_base = 0;

/* _seg_key walks its Seg* (the engine's own deep C walk) before keying it.
 * Started under thousands of do_normalize frames, that walk overflowed the
 * C stack, so a Seg* is keyed only this near the top of the term; deeper
 * is RecursionError (a Seg* key was a TypeError before it had one). */
#define SEG_MAX_DEPTH 1000
/* Each partial-list layer costs this much depth: its round trip through
 * Python (_seg_key, a generator, the eval loop) uses far more C stack than
 * one do_normalize frame, so ~20 nested layers fit under SEG_MAX_DEPTH and
 * a tail under them still gets the rest of MAX_DEPTH. */
#define SEG_LAYER_COST 50

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
    if (PyBool_Check(term)) {
        /* A truth ATOM (D35): keyed as its spelling, the key the str
         * spelling of the same atom already has -- one atom, one variant.
         * Lock-step with _normalize_for_key_py. */
        return PyUnicode_FromString(term == Py_True ? "true" : "false");
    }
    if (PyFloat_Check(term) || PyComplex_Check(term)) {
        return PyTuple_Pack(2, (PyObject *)Py_TYPE(term), term);
    }
    /* A code list: b"ab" and [97, 98] are one term, so one key (the bytes;
     * b"" keys as []).  Lock-step with _normalize_for_key_py. */
    if (PyBytes_Check(term) && PyBytes_GET_SIZE(term) == 0) {
        Py_INCREF(nil_key);
        return nil_key;
    }
    if (PyLong_Check(term) || PyUnicode_Check(term) || PyBytes_Check(term)) {
        Py_INCREF(term);
        return term;
    }

    /* List → ("__list__", elem0, elem1, ...); a char list keys as the
     * carrier, ("__chars__", text), and a code list as its bytes (_seq_key in
     * tabling.py). */
    if (PyList_Check(term)) {
        Py_ssize_t n = PyList_GET_SIZE(term);
        /* Fast path: a char list or a code list keys straight from its
         * (dereferenced) elements, without the ("__list__", ...) tuple the
         * general path builds and then discards.  Same keys as below. */
        if (n > 0) {
            PyObject *e0 = VarAPI->deref(PyList_GET_ITEM(term, 0));
            if (PyLong_CheckExact(e0)) {
                PyObject *b = PyBytes_FromStringAndSize(NULL, n);
                if (!b) return NULL;
                char *buf = PyBytes_AS_STRING(b);
                Py_ssize_t i = 0;
                for (; i < n; i++) {
                    PyObject *e = VarAPI->deref(PyList_GET_ITEM(term, i));
                    if (!PyLong_CheckExact(e)) break;
                    int overflow = 0;
                    long v = PyLong_AsLongAndOverflow(e, &overflow);
                    if (overflow || v < 0 || v > 255) break;
                    buf[i] = (char)v;
                }
                if (i == n) return b;
                Py_DECREF(b);
            } else if (PyUnicode_CheckExact(e0) && PyUnicode_GET_LENGTH(e0) == 1) {
                Py_UCS4 maxc = 0;
                Py_ssize_t i = 0;
                for (; i < n; i++) {
                    PyObject *e = VarAPI->deref(PyList_GET_ITEM(term, i));
                    if (!(PyUnicode_CheckExact(e) && PyUnicode_GET_LENGTH(e) == 1)) break;
                    Py_UCS4 c = PyUnicode_READ_CHAR(e, 0);
                    if (c > maxc) maxc = c;
                }
                if (i == n) {
                    PyObject *text = PyUnicode_New(n, maxc);
                    if (!text) return NULL;
                    int kind = PyUnicode_KIND(text);
                    void *data = PyUnicode_DATA(text);
                    for (i = 0; i < n; i++) {
                        PyObject *e = VarAPI->deref(PyList_GET_ITEM(term, i));
                        PyUnicode_WRITE(kind, data, i, PyUnicode_READ_CHAR(e, 0));
                    }
                    PyObject *key = PyTuple_Pack(2, str___chars__, text);
                    Py_DECREF(text);
                    return key;
                }
            }
        }
        PyObject *result = PyTuple_New(n + 1);
        if (!result) return NULL;
        Py_INCREF(str___list__);
        PyTuple_SET_ITEM(result, 0, str___list__);
        int all_chars = n > 0, all_codes = n > 0;
        for (Py_ssize_t i = 0; i < n; i++) {
            /* an element's key may run Python code (a Seg* key, a dataclass
             * field) that mutates the list: hold the element, re-check size */
            if (PyList_GET_SIZE(term) != n) {
                Py_DECREF(result);
                PyErr_SetString(PyExc_RuntimeError,
                                "_normalize_for_key: list changed size");
                return NULL;
            }
            PyObject *item = PyList_GET_ITEM(term, i);
            Py_INCREF(item);
            PyObject *elem = do_normalize(item, depth + 1);
            Py_DECREF(item);
            if (!elem) { Py_DECREF(result); return NULL; }
            PyTuple_SET_ITEM(result, i + 1, elem);
            if (all_chars && !(PyUnicode_CheckExact(elem)
                               && PyUnicode_GET_LENGTH(elem) == 1))
                all_chars = 0;
            if (all_codes) {
                if (!PyLong_CheckExact(elem)) {
                    all_codes = 0;
                } else {
                    long v = PyLong_AsLong(elem);
                    if (v == -1 && PyErr_Occurred()) {
                        PyErr_Clear();
                        all_codes = 0;
                    } else if (v < 0 || v > 255) {
                        all_codes = 0;
                    }
                }
            }
        }
        if (all_chars) {
            PyObject *empty = PyUnicode_New(0, 0);
            if (!empty) { Py_DECREF(result); return NULL; }
            PyObject *items = PyTuple_GetSlice(result, 1, n + 1);
            if (!items) { Py_DECREF(empty); Py_DECREF(result); return NULL; }
            PyObject *text = PyUnicode_Join(empty, items);
            Py_DECREF(empty); Py_DECREF(items); Py_DECREF(result);
            if (!text) return NULL;
            PyObject *key = PyTuple_Pack(2, str___chars__, text);
            Py_DECREF(text);
            return key;
        }
        if (all_codes) {
            PyObject *b = PyBytes_FromStringAndSize(NULL, n);
            if (!b) { Py_DECREF(result); return NULL; }
            char *buf = PyBytes_AS_STRING(b);
            for (Py_ssize_t i = 0; i < n; i++)
                buf[i] = (char)PyLong_AsLong(PyTuple_GET_ITEM(result, i + 1));
            Py_DECREF(result);
            return b;
        }
        return result;
    }

    /* A char list: the carrier ('$chars', s) keys as ("__chars__", s), and
     * ('$chars', '') as [] -- the key [a, b] has.  Before the tuple branch.
     * Stricter than is_chars_carrier on purpose: slot 1 must be an EXACT str,
     * as in the Python twin (``cells.is_chars``), since the two must key
     * alike. */
    if (PyTuple_CheckExact(term) && PyTuple_GET_SIZE(term) == 2
            && PyUnicode_CheckExact(PyTuple_GET_ITEM(term, 1))) {
        int is_tag = PyUnicode_Check(PyTuple_GET_ITEM(term, 0))
            ? PyUnicode_Compare(PyTuple_GET_ITEM(term, 0), str_chars_tag) : 1;
        if (is_tag == -1 && PyErr_Occurred()) return NULL;
        if (is_tag == 0) {
            PyObject *text = carrier_text(term);
            if (PyUnicode_GET_LENGTH(text) == 0) {
                Py_INCREF(nil_key);
                return nil_key;
            }
            return PyTuple_Pack(2, str___chars__, text);
        }
    }

    /* () is nil: the key [] has.  Lock-step with _normalize_for_key_py. */
    if (PyTuple_CheckExact(term) && PyTuple_GET_SIZE(term) == 0) {
        Py_INCREF(nil_key);
        return nil_key;
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
        /* iterate an owned snapshot: keying an entry may run Python code
         * (a field, a Seg* key) that mutates the dict under PyDict_Next's
         * borrowed references */
        PyObject *items = PyDict_Items(term);
        if (!items) return NULL;
        PyObject *pairs = PySet_New(NULL);
        if (!pairs) { Py_DECREF(items); return NULL; }
        for (Py_ssize_t i = 0; i < PyList_GET_SIZE(items); i++) {
            PyObject *kv = PyList_GET_ITEM(items, i);   /* items owns it */
            PyObject *nk = do_normalize(PyTuple_GET_ITEM(kv, 0), depth + 1);
            if (!nk) { Py_DECREF(pairs); Py_DECREF(items); return NULL; }
            PyObject *nv = do_normalize(PyTuple_GET_ITEM(kv, 1), depth + 1);
            if (!nv) { Py_DECREF(nk); Py_DECREF(pairs); Py_DECREF(items); return NULL; }
            PyObject *pair = PyTuple_Pack(2, nk, nv);
            Py_DECREF(nk); Py_DECREF(nv);
            if (!pair) { Py_DECREF(pairs); Py_DECREF(items); return NULL; }
            int rc = PySet_Add(pairs, pair);
            Py_DECREF(pair);
            if (rc < 0) { Py_DECREF(pairs); Py_DECREF(items); return NULL; }
        }
        Py_DECREF(items);
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

    /* A partial list/string (SegList/SegString/SegBytes): tabling._seg_key
     * builds the key in Python, so the two twins share one definition. */
    if (seg_types && seg_key_fn) {
        /* an exact type test: PyObject_IsInstance would consult a hostile
         * object's __class__ and run Python code mid-scan */
        int is_seg = 0;
        for (Py_ssize_t i = 0; i < PyTuple_GET_SIZE(seg_types); i++) {
            if (PyObject_TypeCheck(term,
                    (PyTypeObject *)PyTuple_GET_ITEM(seg_types, i))) {
                is_seg = 1;
                break;
            }
        }
        if (is_seg) {
            if (depth > SEG_MAX_DEPTH) {
                PyErr_SetString(PyExc_RecursionError,
                                "_normalize_for_key: partial list nested too deep");
                return NULL;
            }
            int saved = seg_depth_base;
            seg_depth_base = depth + SEG_LAYER_COST;
            PyObject *key = PyObject_CallOneArg(seg_key_fn, term);
            seg_depth_base = saved;
            return key;
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
    return do_normalize(term, seg_depth_base);
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

    /* an owned tuple snapshot: keying an argument may run Python code that
     * mutates a list of arguments under a borrowed reference */
    PyObject *snap = PyTuple_Check(py_args) ? Py_NewRef(py_args)
                                            : PyList_AsTuple(py_args);
    if (!snap) return NULL;
    Py_ssize_t n = PyTuple_GET_SIZE(snap);

    PyObject *result = PyTuple_New(n);
    if (!result) { Py_DECREF(snap); return NULL; }

    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *normed = do_normalize(PyTuple_GET_ITEM(snap, i), seg_depth_base);
        if (!normed) { Py_DECREF(result); Py_DECREF(snap); return NULL; }
        PyTuple_SET_ITEM(result, i, normed);
    }
    Py_DECREF(snap);
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

    /* __walk__ protocol (A01-F008): DictTerm and the Seg types
     * supply __walk__, which deep-substitutes bindings via the canonical
     * walk(). This unifies _deref_walk with walk (they were blind to
     * disjoint type sets) and preserves F018 promotion. */
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
py_register_seg_key(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *types, *fn;
    if (!PyArg_ParseTuple(args, "O!O:_register_seg_key", &PyTuple_Type, &types, &fn))
        return NULL;
    if (!PyCallable_Check(fn)) {
        PyErr_SetString(PyExc_TypeError, "_register_seg_key: fn must be callable");
        return NULL;
    }
    for (Py_ssize_t i = 0; i < PyTuple_GET_SIZE(types); i++) {
        if (!PyType_Check(PyTuple_GET_ITEM(types, i))) {
            PyErr_SetString(PyExc_TypeError, "_register_seg_key: types must be classes");
            return NULL;
        }
    }
    Py_INCREF(types);
    Py_INCREF(fn);
    Py_XSETREF(seg_types, types);
    Py_XSETREF(seg_key_fn, fn);
    Py_RETURN_NONE;
}

static PyObject *
py_register_var_sentinel(PyObject *Py_UNUSED(module), PyObject *sentinel)
{
    Py_XDECREF(VAR_sentinel);
    Py_INCREF(sentinel);
    VAR_sentinel = sentinel;
    Py_RETURN_NONE;
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
    {"_register_seg_key", py_register_seg_key, METH_VARARGS,
     "Register the Seg* classes and the Python key function for them."},
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

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif

    /* Intern frequently-used attribute name strings */
    str___name__ = PyUnicode_InternFromString("__name__");
    str___list__ = PyUnicode_InternFromString("__list__");
    str___tuple__ = PyUnicode_InternFromString("__tuple__");
    str___dict__ = PyUnicode_InternFromString("__dict__");
    str___set__ = PyUnicode_InternFromString("__set__");
    str___chars__ = PyUnicode_InternFromString("__chars__");
    str_chars_tag = PyUnicode_InternFromString("$chars");
    nil_key = str___list__ ? PyTuple_Pack(1, str___list__) : NULL;
    if (!str___name__ || !str___list__ ||
        !str___tuple__ || !str___dict__ || !str___set__ ||
        !str___chars__ || !str_chars_tag || !nil_key) {
        Py_DECREF(m);
        return NULL;
    }

    return m;
}
