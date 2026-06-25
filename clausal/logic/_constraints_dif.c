/*
 * _constraints_dif.c — C-accelerated dif/2 disequality constraint.
 *
 * Uses the _variables C API capsule for direct C-level access to
 * var_deref, Var_Check, Trail operations, get_attr, put_attr, and
 * unify_with_occurs_check — eliminating Python call overhead on the
 * hot path.
 *
 * Provides:
 *   _collect_free_vars(term)              → list of unbound Vars
 *   _structural_unify_oc(t1, t2, trail)   → bool
 *   dif(x, y, trail)                      → bool
 *   _dif_hook(attr_value, bound_to, trail) → bool
 *   reify_eq(x, y, trail)                → True / False / None
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* Import the C API from _variables */
#define VARIABLES_CAPI_CONSUMER
#include "variables/_variables_capi.h"

#define MAX_DEPTH 50000

/* ── Cached references (set during module init) ─────────────────────── */

/* From clausal.terms */
static PyObject *Compound_type = NULL;

/* Interned strings */
static PyObject *DIF_KEY_STR = NULL;    /* "dif" */
static PyObject *str_functor = NULL;    /* "functor" */
static PyObject *str_args = NULL;       /* "args" */


/* ── Inline helpers ──────────────────────────────────────────────────── */

/* is Compound instance? */
static inline int
is_compound(PyObject *obj)
{
    if (!Compound_type) return 0;
    return PyObject_IsInstance(obj, Compound_type);
}

/* is_term_instance: direct C API call → 1/0/-1 */
static inline int
call_is_term_instance(PyObject *term)
{
    return VarAPI->is_term_instance(term);
}

/* term_field_names: direct C API call → new ref (tuple of str) */
static inline PyObject *
call_term_field_names(PyObject *term)
{
    return VarAPI->term_field_names(term);
}


/* ── _collect_free_vars ──────────────────────────────────────────────── */

/*
 * Recursive walk collecting unbound Vars.
 * Returns 0 on success, -1 on error.
 */
static int
collect_walk(PyObject *term, PyObject *seen, PyObject *result, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "_collect_free_vars: term nesting too deep");
        return -1;
    }

    /* Direct C deref — borrowed ref, no refcount overhead */
    PyObject *t = VarAPI->deref(term);

    /* Var? */
    if (Var_Check(t)) {
        PyObject *tid = PyLong_FromVoidPtr(t);
        if (!tid) return -1;
        int contains = PySet_Contains(seen, tid);
        if (contains < 0) { Py_DECREF(tid); return -1; }
        if (!contains) {
            if (PySet_Add(seen, tid) < 0) { Py_DECREF(tid); return -1; }
            if (PyList_Append(result, t) < 0) { Py_DECREF(tid); return -1; }
        }
        Py_DECREF(tid);
        return 0;
    }

    /* tuple */
    if (PyTuple_Check(t)) {
        Py_ssize_t n = PyTuple_GET_SIZE(t);
        for (Py_ssize_t i = 0; i < n; i++) {
            if (collect_walk(PyTuple_GET_ITEM(t, i), seen, result, depth + 1) < 0)
                return -1;
        }
        return 0;
    }

    /* list */
    if (PyList_Check(t)) {
        Py_ssize_t n = PyList_GET_SIZE(t);
        for (Py_ssize_t i = 0; i < n; i++) {
            if (collect_walk(PyList_GET_ITEM(t, i), seen, result, depth + 1) < 0)
                return -1;
        }
        return 0;
    }

    /* Compound */
    int ic = is_compound(t);
    if (ic < 0) return -1;
    if (ic) {
        PyObject *args = PyObject_GetAttr(t, str_args);
        if (!args) return -1;
        if (PyTuple_Check(args)) {
            Py_ssize_t n = PyTuple_GET_SIZE(args);
            for (Py_ssize_t i = 0; i < n; i++) {
                if (collect_walk(PyTuple_GET_ITEM(args, i), seen, result, depth + 1) < 0) {
                    Py_DECREF(args);
                    return -1;
                }
            }
        }
        Py_DECREF(args);
        return 0;
    }

    /* Term instance (PredicateMeta / dataclass) */
    int iti = call_is_term_instance(t);
    if (iti < 0) return -1;
    if (iti) {
        PyObject *fields = call_term_field_names(t);
        if (!fields) return -1;
        Py_ssize_t n = PyTuple_GET_SIZE(fields);
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *val = PyObject_GetAttr(t, PyTuple_GET_ITEM(fields, i));
            if (!val) { Py_DECREF(fields); return -1; }
            int rc = collect_walk(val, seen, result, depth + 1);
            Py_DECREF(val);
            if (rc < 0) { Py_DECREF(fields); return -1; }
        }
        Py_DECREF(fields);
        return 0;
    }

    /* Scalar — skip */
    return 0;
}

/*
 * py_collect_free_vars(term) → list of Var
 */
static PyObject *
py_collect_free_vars(PyObject *Py_UNUSED(module), PyObject *term)
{
    PyObject *seen = PySet_New(NULL);
    if (!seen) return NULL;
    PyObject *result = PyList_New(0);
    if (!result) { Py_DECREF(seen); return NULL; }

    if (collect_walk(term, seen, result, 0) < 0) {
        Py_DECREF(seen);
        Py_DECREF(result);
        return NULL;
    }
    Py_DECREF(seen);
    return result;
}


/* ── _structural_unify_oc ────────────────────────────────────────────── */

/*
 * Structural unify with occurs check.
 * Returns 1 (unified), 0 (failed), -1 (error).
 */
static int
c_structural_unify_oc(PyObject *t1, PyObject *t2, TrailObject *trail, int depth)
{
    if (depth > MAX_DEPTH) {
        PyErr_SetString(PyExc_RecursionError,
                        "_structural_unify_oc: term nesting too deep");
        return -1;
    }

    PyObject *d1 = VarAPI->deref(t1);  /* borrowed */
    PyObject *d2 = VarAPI->deref(t2);  /* borrowed */

    /* Both Compound? */
    int ic1 = is_compound(d1);
    if (ic1 < 0) return -1;
    int ic2 = is_compound(d2);
    if (ic2 < 0) return -1;

    if (ic1 && ic2) {
        /* Compare functor */
        PyObject *f1 = PyObject_GetAttr(d1, str_functor);
        if (!f1) return -1;
        PyObject *f2 = PyObject_GetAttr(d2, str_functor);
        if (!f2) { Py_DECREF(f1); return -1; }
        int feq = PyObject_RichCompareBool(f1, f2, Py_EQ);
        Py_DECREF(f1);
        Py_DECREF(f2);
        if (feq < 0) return -1;
        if (!feq) return 0;

        /* Compare args */
        PyObject *a1 = PyObject_GetAttr(d1, str_args);
        if (!a1) return -1;
        PyObject *a2 = PyObject_GetAttr(d2, str_args);
        if (!a2) { Py_DECREF(a1); return -1; }

        Py_ssize_t n1 = PyTuple_Check(a1) ? PyTuple_GET_SIZE(a1) : PyObject_Length(a1);
        Py_ssize_t n2 = PyTuple_Check(a2) ? PyTuple_GET_SIZE(a2) : PyObject_Length(a2);
        if (n1 != n2) {
            Py_DECREF(a1); Py_DECREF(a2);
            return 0;
        }

        for (Py_ssize_t i = 0; i < n1; i++) {
            PyObject *arg1 = PyTuple_GET_ITEM(a1, i);
            PyObject *arg2 = PyTuple_GET_ITEM(a2, i);
            int r = c_structural_unify_oc(arg1, arg2, trail, depth + 1);
            if (r <= 0) {
                Py_DECREF(a1); Py_DECREF(a2);
                return r;
            }
        }
        Py_DECREF(a1); Py_DECREF(a2);
        return 1;
    }

    /* Both term instances? */
    int ti1 = call_is_term_instance(d1);
    if (ti1 < 0) return -1;
    int ti2 = call_is_term_instance(d2);
    if (ti2 < 0) return -1;

    if (ti1 && ti2) {
        if (Py_TYPE(d1) != Py_TYPE(d2))
            return 0;
        PyObject *fields = call_term_field_names(d1);
        if (!fields) return -1;
        Py_ssize_t n = PyTuple_GET_SIZE(fields);
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *fname = PyTuple_GET_ITEM(fields, i);
            PyObject *v1 = PyObject_GetAttr(d1, fname);
            if (!v1) { Py_DECREF(fields); return -1; }
            PyObject *v2 = PyObject_GetAttr(d2, fname);
            if (!v2) { Py_DECREF(v1); Py_DECREF(fields); return -1; }
            int r = c_structural_unify_oc(v1, v2, trail, depth + 1);
            Py_DECREF(v1);
            Py_DECREF(v2);
            if (r <= 0) { Py_DECREF(fields); return r; }
        }
        Py_DECREF(fields);
        return 1;
    }

    /* Both lists? */
    if (PyList_Check(d1) && PyList_Check(d2)) {
        Py_ssize_t n1 = PyList_GET_SIZE(d1);
        Py_ssize_t n2 = PyList_GET_SIZE(d2);
        if (n1 != n2) return 0;
        for (Py_ssize_t i = 0; i < n1; i++) {
            int r = c_structural_unify_oc(
                PyList_GET_ITEM(d1, i), PyList_GET_ITEM(d2, i),
                trail, depth + 1);
            if (r <= 0) return r;
        }
        return 1;
    }

    /* Fall through to unify_with_occurs_check (direct C call) */
    {
        PyObject *r = VarAPI->unify_oc(d1, d2, trail);
        if (!r) return -1;
        int truthy = PyObject_IsTrue(r);
        Py_DECREF(r);
        return truthy;
    }
}

/*
 * py_structural_unify_oc(t1, t2, trail) → bool
 */
static PyObject *
py_structural_unify_oc(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *t1, *t2, *trail;
    if (!PyArg_ParseTuple(args, "OOO", &t1, &t2, &trail))
        return NULL;
    if (!Trail_Check(trail)) {
        PyErr_SetString(PyExc_TypeError, "_structural_unify_oc: third arg must be a Trail");
        return NULL;
    }
    int r = c_structural_unify_oc(t1, t2, Trail_CAST(trail), 0);
    if (r < 0) return NULL;
    return PyBool_FromLong(r);
}


/* ── Shared: attach dif constraint to free vars ──────────────────────── */

/*
 * Collect free vars from x and y, deduplicate, attach pair.
 * If check_identity is true, skip appending pair to existing lists
 * that already contain the exact same pair object (by identity).
 * Returns 0 on success, -1 on error.
 */
static int
attach_dif_pair(PyObject *x, PyObject *y, PyObject *pair,
                TrailObject *trail, int check_identity)
{
    /* Collect free vars from both terms */
    PyObject *seen = PySet_New(NULL);
    if (!seen) return -1;
    PyObject *unique = PyList_New(0);
    if (!unique) { Py_DECREF(seen); return -1; }

    if (collect_walk(x, seen, unique, 0) < 0)
        goto error;
    if (collect_walk(y, seen, unique, 0) < 0)
        goto error;

    Py_DECREF(seen);
    seen = NULL;

    /* Attach pair to each unique var */
    Py_ssize_t nu = PyList_GET_SIZE(unique);
    for (Py_ssize_t i = 0; i < nu; i++) {
        PyObject *v = PyList_GET_ITEM(unique, i);
        PyObject *existing = VarAPI->get_attr(v, DIF_KEY_STR);
        if (!existing) { Py_DECREF(unique); return -1; }

        if (existing == Py_None) {
            Py_DECREF(existing);
            /* put_attr(v, DIF_KEY, [pair], trail) */
            PyObject *new_list = PyList_New(1);
            if (!new_list) { Py_DECREF(unique); return -1; }
            Py_INCREF(pair);
            PyList_SET_ITEM(new_list, 0, pair);
            int rc = VarAPI->put_attr(v, DIF_KEY_STR, new_list, trail);
            Py_DECREF(new_list);
            if (rc < 0) { Py_DECREF(unique); return -1; }
        } else {
            int skip = 0;
            if (check_identity) {
                /* Skip if pair already present (identity check) */
                Py_ssize_t en = PyList_GET_SIZE(existing);
                for (Py_ssize_t j = 0; j < en; j++) {
                    if (PyList_GET_ITEM(existing, j) == pair) {
                        skip = 1;
                        break;
                    }
                }
            }
            if (!skip) {
                /* Replace via put_attr (trailed) instead of mutating the list
                 * in place: an untrailed append survives backtracking and
                 * leaves a stale constraint that wrongly blocks later
                 * unifications (sequential-query state accumulation). */
                PyObject *new_list = PySequence_List(existing);
                if (!new_list) {
                    Py_DECREF(existing); Py_DECREF(unique);
                    return -1;
                }
                if (PyList_Append(new_list, pair) < 0) {
                    Py_DECREF(new_list); Py_DECREF(existing); Py_DECREF(unique);
                    return -1;
                }
                int rc = VarAPI->put_attr(v, DIF_KEY_STR, new_list, trail);
                Py_DECREF(new_list);
                if (rc < 0) {
                    Py_DECREF(existing); Py_DECREF(unique);
                    return -1;
                }
            }
            Py_DECREF(existing);
        }
    }

    Py_DECREF(unique);
    return 0;

error:
    Py_XDECREF(seen);
    Py_DECREF(unique);
    return -1;
}


/* ── dif ─────────────────────────────────────────────────────────────── */

/*
 * dif(x, y, trail) → bool
 */
static PyObject *
py_dif(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *x, *y, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &x, &y, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "dif: third arg must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *dx = VarAPI->deref(x);  /* borrowed */
    PyObject *dy = VarAPI->deref(y);  /* borrowed */

    Py_ssize_t mark = VarAPI->trail_mark(trail);

    int unified = c_structural_unify_oc(dx, dy, trail, 0);
    if (unified < 0) return NULL;

    if (!unified) {
        VarAPI->trail_undo(trail, mark);
        Py_RETURN_TRUE;
    }

    Py_ssize_t cur_len = trail->length;
    int trail_grew = (cur_len != mark);

    if (!trail_grew) {
        /* No bindings → terms already identical */
        Py_RETURN_FALSE;
    }

    VarAPI->trail_undo(trail, mark);

    /* Build constraint pair and attach */
    PyObject *pair = PyTuple_Pack(2, dx, dy);
    if (!pair) return NULL;

    if (attach_dif_pair(dx, dy, pair, trail, 0) < 0) {
        Py_DECREF(pair);
        return NULL;
    }
    Py_DECREF(pair);
    Py_RETURN_TRUE;
}


/* ── _dif_hook ───────────────────────────────────────────────────────── */

/*
 * _dif_hook(attr_value, bound_to, trail) → bool
 */
static PyObject *
py_dif_hook(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *attr_value, *bound_to, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &attr_value, &bound_to, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "_dif_hook: third arg must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    if (!PyList_Check(attr_value)) {
        PyErr_SetString(PyExc_TypeError, "_dif_hook: attr_value must be a list");
        return NULL;
    }

    Py_ssize_t n = PyList_GET_SIZE(attr_value);
    for (Py_ssize_t ci = 0; ci < n; ci++) {
        PyObject *pair = PyList_GET_ITEM(attr_value, ci);
        PyObject *px = PyTuple_GET_ITEM(pair, 0);
        PyObject *py = PyTuple_GET_ITEM(pair, 1);

        PyObject *dx = VarAPI->deref(px);  /* borrowed */
        PyObject *dy = VarAPI->deref(py);  /* borrowed */

        Py_ssize_t mark = VarAPI->trail_mark(trail);

        int unified = c_structural_unify_oc(dx, dy, trail, 0);
        if (unified < 0) return NULL;

        if (!unified) {
            VarAPI->trail_undo(trail, mark);
            continue;
        }

        Py_ssize_t cur_len = trail->length;
        int trail_grew = (cur_len != mark);

        if (!trail_grew) {
            /* Constraint violated — terms became equal */
            Py_RETURN_FALSE;
        }

        VarAPI->trail_undo(trail, mark);

        /* Re-attach constraint to remaining free vars */
        if (attach_dif_pair(dx, dy, pair, trail, 1) < 0)
            return NULL;
    }

    Py_RETURN_TRUE;
}


/* ── reify_eq ────────────────────────────────────────────────────────── */

/*
 * reify_eq(x, y, trail) → True / False / None
 */
static PyObject *
py_reify_eq(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *x, *y, *trail_obj;
    if (!PyArg_ParseTuple(args, "OOO", &x, &y, &trail_obj))
        return NULL;
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "reify_eq: third arg must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *dx = VarAPI->deref(x);  /* borrowed */
    PyObject *dy = VarAPI->deref(y);  /* borrowed */

    /* Fast path: identical objects */
    if (dx == dy)
        Py_RETURN_TRUE;

    Py_ssize_t mark = VarAPI->trail_mark(trail);

    int unified = c_structural_unify_oc(dx, dy, trail, 0);
    if (unified < 0) return NULL;

    int grew = 0;
    if (unified)
        grew = (trail->length != mark);

    VarAPI->trail_undo(trail, mark);

    if (!unified)
        Py_RETURN_FALSE;
    if (!grew)
        Py_RETURN_TRUE;
    Py_RETURN_NONE;
}


/* ── Module definition ───────────────────────────────────────────────── */

static PyMethodDef module_methods[] = {
    {"_collect_free_vars",   py_collect_free_vars,   METH_O,       NULL},
    {"_structural_unify_oc", py_structural_unify_oc, METH_VARARGS, NULL},
    {"dif",                  py_dif,                 METH_VARARGS, NULL},
    {"_dif_hook",            py_dif_hook,            METH_VARARGS, NULL},
    {"reify_eq",             py_reify_eq,            METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_constraints_dif",
    "C-accelerated dif/2 disequality constraint.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__constraints_dif(void)
{
    /* Import the C API capsule from _variables */
    if (import_variables_capi() < 0) return NULL;

    /* Import clausal.terms.Compound */
    PyObject *terms_mod = PyImport_ImportModule("clausal.terms");
    if (!terms_mod) return NULL;
    Compound_type = PyObject_GetAttrString(terms_mod, "Compound");
    Py_DECREF(terms_mod);
    if (!Compound_type) return NULL;

    /* Intern strings */
    DIF_KEY_STR = PyUnicode_InternFromString("dif");
    if (!DIF_KEY_STR) return NULL;
    str_functor = PyUnicode_InternFromString("functor");
    if (!str_functor) return NULL;
    str_args = PyUnicode_InternFromString("args");
    if (!str_args) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

    return m;
}
