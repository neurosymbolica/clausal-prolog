/*
 * _lists_core.c — C helpers for core list predicate inner loops
 *
 * These functions move the mark/unify/undo inner loops of list predicates
 * to C, eliminating Python bytecode overhead.  The Python generator
 * structure is preserved — these helpers are called from Python generators
 * that handle the trampoline protocol.
 *
 * Pattern: each "find" function iterates from a start index, tries
 * unification at each candidate, and returns (next_index, trail_mark)
 * on the first success — or None when exhausted.  The Python caller
 * yields, undoes the trail mark, and calls the finder again.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* ================================================================
 * Cached references (set during module init)
 * ================================================================ */

static PyObject *fn_unify  = NULL;   /* clausal.logic.variables.unify  */

static PyObject *empty_string = NULL;  /* "" for PyUnicode_Join */

/* ================================================================
 * Helpers
 * ================================================================ */

/* Call unify(t1, t2, trail) — returns 1 if success, 0 if fail, -1 on error. */
static inline int
call_unify(PyObject *t1, PyObject *t2, PyObject *trail)
{
    PyObject *r = PyObject_CallFunctionObjArgs(fn_unify, t1, t2, trail, NULL);
    if (!r) return -1;
    int result = PyObject_IsTrue(r);
    Py_DECREF(r);
    return result;
}

/* trail.mark() → Py_ssize_t (always >= 0); returns -1 on error. */
static inline Py_ssize_t
trail_mark(PyObject *trail)
{
    PyObject *r = PyObject_CallMethod(trail, "mark", NULL);
    if (!r) return -1;
    Py_ssize_t mark = PyLong_AsSsize_t(r);
    Py_DECREF(r);
    return mark;
}

/* trail.undo(mark) — returns 0 on success, -1 on error. */
static inline int
trail_undo(PyObject *trail, Py_ssize_t mark)
{
    PyObject *mark_obj = PyLong_FromSsize_t(mark);
    if (!mark_obj) return -1;
    PyObject *r = PyObject_CallMethod(trail, "undo", "O", mark_obj);
    Py_DECREF(mark_obj);
    if (!r) return -1;
    Py_DECREF(r);
    return 0;
}

/*
 * make_seq_result(items, was_string) — C version of Python _seq_result().
 * If was_string and all items are single-char strings, joins into a string.
 * Otherwise returns items with an incremented refcount.
 * Returns a new reference.
 */
static PyObject *
make_seq_result(PyObject *items, int was_string)
{
    if (!was_string) {
        Py_INCREF(items);
        return items;
    }
    Py_ssize_t n = PyList_GET_SIZE(items);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *c = PyList_GET_ITEM(items, i);
        if (!PyUnicode_Check(c) || PyUnicode_GET_LENGTH(c) != 1) {
            Py_INCREF(items);
            return items;
        }
    }
    return PyUnicode_Join(empty_string, items);
}

/*
 * build_remainder(items, skip_idx) — build items[:i] + items[i+1:]
 * More efficient than two slices + concatenation.
 * Returns a new reference.
 */
static PyObject *
build_remainder(PyObject *items, Py_ssize_t skip_idx)
{
    Py_ssize_t len = PyList_GET_SIZE(items);
    PyObject *result = PyList_New(len - 1);
    if (!result) return NULL;

    Py_ssize_t j = 0;
    for (Py_ssize_t i = 0; i < len; i++) {
        if (i == skip_idx) continue;
        PyObject *item = PyList_GET_ITEM(items, i);
        Py_INCREF(item);
        PyList_SET_ITEM(result, j++, item);
    }
    return result;
}


/* ================================================================
 * member_find  —  inner loop for in_/2 (member)
 * ================================================================ */

/*
 * member_find(items, start, elem, trail) → (next_start, mark) | None
 *
 * Iterates items[start:], calling mark/unify for each element.
 * On first successful unify: returns (i+1, mark) with bindings active.
 * On exhaustion: returns None.
 */
static PyObject *
py_member_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *items, *elem, *trail;
    Py_ssize_t start;

    if (!PyArg_ParseTuple(args, "OnOO", &items, &start, &elem, &trail))
        return NULL;

    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = start; i < len; i++) {
        Py_ssize_t mark = trail_mark(trail);
        if (mark < 0) return NULL;

        PyObject *item = PyList_GET_ITEM(items, i);
        int ok = call_unify(elem, item, trail);
        if (ok < 0) return NULL;

        if (ok) {
            /* Success — bindings active, caller will undo after yield */
            return Py_BuildValue("(nn)", i + 1, mark);
        }

        if (trail_undo(trail, mark) < 0) return NULL;
    }

    Py_RETURN_NONE;
}


/* ================================================================
 * memberchk_find  —  inner loop for in_check/2 (memberchk)
 * ================================================================ */

/*
 * memberchk_find(items, elem, trail) → True | False
 *
 * Finds the first item that unifies with elem.  Bindings for the
 * successful match are left active.  Returns True/False.
 */
static PyObject *
py_memberchk_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *items, *elem, *trail;

    if (!PyArg_ParseTuple(args, "OOO", &items, &elem, &trail))
        return NULL;

    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = 0; i < len; i++) {
        Py_ssize_t mark = trail_mark(trail);
        if (mark < 0) return NULL;

        PyObject *item = PyList_GET_ITEM(items, i);
        int ok = call_unify(elem, item, trail);
        if (ok < 0) return NULL;

        if (ok) Py_RETURN_TRUE;

        if (trail_undo(trail, mark) < 0) return NULL;
    }

    Py_RETURN_FALSE;
}


/* ================================================================
 * append_split_find  —  inner loop for append/3 split mode
 * ================================================================ */

/*
 * append_split_find(items, start, l1, l2, out_str, trail)
 *   → (next_start, mark) | None
 *
 * Enumerate splits of items at positions [start, len].  For each split
 * index i, constructs prefix=items[:i] and suffix=items[i:], applies
 * seq_result if out_str, and tries to unify l1=prefix and l2=suffix.
 *
 * On first successful double-unify: returns (i+1, mark).
 * On exhaustion: returns None.
 */
static PyObject *
py_append_split_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *items, *l1, *l2, *trail;
    Py_ssize_t start;
    int out_str;

    if (!PyArg_ParseTuple(args, "OnOOpO",
                          &items, &start, &l1, &l2, &out_str, &trail))
        return NULL;

    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = start; i <= len; i++) {
        PyObject *prefix = PyList_GetSlice(items, 0, i);
        if (!prefix) return NULL;
        PyObject *suffix = PyList_GetSlice(items, i, len);
        if (!suffix) { Py_DECREF(prefix); return NULL; }

        /* Apply _seq_result if string mode */
        if (out_str) {
            PyObject *p2 = make_seq_result(prefix, 1);
            Py_DECREF(prefix);
            if (!p2) { Py_DECREF(suffix); return NULL; }
            PyObject *s2 = make_seq_result(suffix, 1);
            Py_DECREF(suffix);
            if (!s2) { Py_DECREF(p2); return NULL; }
            prefix = p2;
            suffix = s2;
        }

        Py_ssize_t mark = trail_mark(trail);
        if (mark < 0) { Py_DECREF(prefix); Py_DECREF(suffix); return NULL; }

        int ok1 = call_unify(l1, prefix, trail);
        if (ok1 < 0) { Py_DECREF(prefix); Py_DECREF(suffix); return NULL; }

        int ok2 = 0;
        if (ok1) {
            ok2 = call_unify(l2, suffix, trail);
            if (ok2 < 0) { Py_DECREF(prefix); Py_DECREF(suffix); return NULL; }
        }

        Py_DECREF(prefix);
        Py_DECREF(suffix);

        if (ok1 && ok2) {
            return Py_BuildValue("(nn)", i + 1, mark);
        }

        if (trail_undo(trail, mark) < 0) return NULL;
    }

    Py_RETURN_NONE;
}


/* ================================================================
 * select_find  —  inner loop for select/3
 * ================================================================ */

/*
 * select_find(items, start, elem, rest, was_str, trail)
 *   → (next_start, mark) | None
 *
 * For each index i in [start, len), tries to unify elem with items[i]
 * and rest with items[:i]+items[i+1:] (with seq_result if was_str).
 *
 * On first successful double-unify: returns (i+1, mark).
 * On exhaustion: returns None.
 */
static PyObject *
py_select_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *items, *elem, *rest, *trail;
    Py_ssize_t start;
    int was_str;

    if (!PyArg_ParseTuple(args, "OnOOpO",
                          &items, &start, &elem, &rest, &was_str, &trail))
        return NULL;

    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = start; i < len; i++) {
        PyObject *item = PyList_GET_ITEM(items, i);

        PyObject *remainder = build_remainder(items, i);
        if (!remainder) return NULL;

        PyObject *rem_val;
        if (was_str) {
            rem_val = make_seq_result(remainder, 1);
            Py_DECREF(remainder);
            if (!rem_val) return NULL;
        } else {
            rem_val = remainder;
        }

        Py_ssize_t mark = trail_mark(trail);
        if (mark < 0) { Py_DECREF(rem_val); return NULL; }

        int ok1 = call_unify(elem, item, trail);
        if (ok1 < 0) { Py_DECREF(rem_val); return NULL; }

        int ok2 = 0;
        if (ok1) {
            ok2 = call_unify(rest, rem_val, trail);
            if (ok2 < 0) { Py_DECREF(rem_val); return NULL; }
        }

        Py_DECREF(rem_val);

        if (ok1 && ok2) {
            return Py_BuildValue("(nn)", i + 1, mark);
        }

        if (trail_undo(trail, mark) < 0) return NULL;
    }

    Py_RETURN_NONE;
}


/* ================================================================
 * permutation_find  —  inner loop for permutation/2
 * ================================================================ */

/*
 * permutation_find(iter, perm_var, was_str, trail) → mark | None
 *
 * Gets the next permutation from iter (an itertools.permutations iterator),
 * converts it to a list (or string if was_str), and tries to unify with
 * perm_var.  On success, returns the trail mark (bindings active).
 * On exhaustion, returns None.
 *
 * The iterator is stateful, so repeated calls advance through permutations.
 */
static PyObject *
py_permutation_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *iter, *perm_var, *trail;
    int was_str;

    if (!PyArg_ParseTuple(args, "OOpO", &iter, &perm_var, &was_str, &trail))
        return NULL;

    PyObject *item;
    while ((item = PyIter_Next(iter)) != NULL) {
        /* item is a tuple from itertools.permutations — convert to list */
        PyObject *perm_list = PySequence_List(item);
        Py_DECREF(item);
        if (!perm_list) return NULL;

        PyObject *result;
        if (was_str) {
            result = make_seq_result(perm_list, 1);
            Py_DECREF(perm_list);
            if (!result) return NULL;
        } else {
            result = perm_list;
        }

        Py_ssize_t mark = trail_mark(trail);
        if (mark < 0) { Py_DECREF(result); return NULL; }

        int ok = call_unify(perm_var, result, trail);
        Py_DECREF(result);
        if (ok < 0) return NULL;

        if (ok) {
            return PyLong_FromSsize_t(mark);
        }

        if (trail_undo(trail, mark) < 0) return NULL;
    }

    /* Check if iteration ended due to an error */
    if (PyErr_Occurred()) return NULL;

    Py_RETURN_NONE;
}


/* ================================================================
 * nth0_find  —  inner loop for get_item/3 enumerate mode
 * ================================================================ */

/*
 * nth0_find(items, start, n_var, elem_var, trail)
 *   → (next_start, mark) | None
 *
 * For each index i in [start, len), tries to unify n_var with i
 * and elem_var with items[i].
 *
 * On first successful double-unify: returns (i+1, mark).
 * On exhaustion: returns None.
 */
static PyObject *
py_nth0_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *items, *n_var, *elem_var, *trail;
    Py_ssize_t start;

    if (!PyArg_ParseTuple(args, "OnOOO",
                          &items, &start, &n_var, &elem_var, &trail))
        return NULL;

    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = start; i < len; i++) {
        Py_ssize_t mark = trail_mark(trail);
        if (mark < 0) return NULL;

        PyObject *idx = PyLong_FromSsize_t(i);
        if (!idx) return NULL;

        int ok1 = call_unify(n_var, idx, trail);
        Py_DECREF(idx);
        if (ok1 < 0) return NULL;

        int ok2 = 0;
        if (ok1) {
            PyObject *item = PyList_GET_ITEM(items, i);
            ok2 = call_unify(elem_var, item, trail);
            if (ok2 < 0) return NULL;
        }

        if (ok1 && ok2) {
            return Py_BuildValue("(nn)", i + 1, mark);
        }

        if (trail_undo(trail, mark) < 0) return NULL;
    }

    Py_RETURN_NONE;
}


/* ================================================================
 * Module definition and init
 * ================================================================ */

static PyMethodDef module_methods[] = {
    {"member_find", py_member_find, METH_VARARGS,
     "member_find(items, start, elem, trail) -> (next_start, mark) or None\n"
     "\n"
     "Inner loop for in_/2 (member).  Finds next element that unifies."},
    {"memberchk_find", py_memberchk_find, METH_VARARGS,
     "memberchk_find(items, elem, trail) -> True or False\n"
     "\n"
     "Inner loop for in_check/2 (memberchk).  Finds first matching element."},
    {"append_split_find", py_append_split_find, METH_VARARGS,
     "append_split_find(items, start, l1, l2, out_str, trail)\n"
     "  -> (next_start, mark) or None\n"
     "\n"
     "Inner loop for append/3 enumerate-all-splits mode."},
    {"select_find", py_select_find, METH_VARARGS,
     "select_find(items, start, elem, rest, was_str, trail)\n"
     "  -> (next_start, mark) or None\n"
     "\n"
     "Inner loop for select/3."},
    {"permutation_find", py_permutation_find, METH_VARARGS,
     "permutation_find(iter, perm_var, was_str, trail) -> mark or None\n"
     "\n"
     "Inner loop for permutation/2.  Advances iterator to next matching perm."},
    {"nth0_find", py_nth0_find, METH_VARARGS,
     "nth0_find(items, start, n_var, elem_var, trail)\n"
     "  -> (next_start, mark) or None\n"
     "\n"
     "Inner loop for get_item/3 enumerate mode."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_lists_core",
    "C-accelerated inner loops for core list predicates.\n"
    "\n"
    "These functions replace the Python mark/unify/undo loops in list\n"
    "predicates with tight C loops, reducing bytecode interpreter overhead.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__lists_core(void)
{
    /* Import clausal.logic.variables */
    PyObject *var_mod = PyImport_ImportModule("clausal.logic.variables");
    if (!var_mod) return NULL;

    fn_unify = PyObject_GetAttrString(var_mod, "unify");
    Py_DECREF(var_mod);

    if (!fn_unify) return NULL;

    /* Cache empty string for PyUnicode_Join */
    empty_string = PyUnicode_FromString("");
    if (!empty_string) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    return m;
}
