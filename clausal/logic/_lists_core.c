/*
 * _lists_core.c — C helpers for core list predicate inner loops
 *
 * These functions move the mark/unify/undo inner loops of list predicates
 * to C, eliminating Python bytecode overhead.  The Python generator
 * structure is preserved — these helpers are called from Python generators
 * that handle the trampoline protocol.
 *
 * Uses the _variables C API capsule for direct C-level access to unify,
 * trail_mark, and trail_undo — bypassing Python method dispatch entirely.
 *
 * Pattern: each "find" function iterates from a start index, tries
 * unification at each candidate, and returns (next_index, trail_mark)
 * on the first success — or None when exhausted.  The Python caller
 * yields, undoes the trail mark, and calls the finder again.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* Import the C API from _variables */
#define VARIABLES_CAPI_CONSUMER
#include "variables/_variables_capi.h"

/* ================================================================
 * Cached references (set during module init)
 * ================================================================ */

static PyObject *empty_string = NULL;  /* "" for PyUnicode_Join */

/* ================================================================
 * Helpers
 * ================================================================ */

/*
 * Call unify(t1, t2, trail) via the direct C API (no occurs check).
 * Returns 1 if success, 0 if fail, -1 on error.
 */
static inline int
call_unify(PyObject *t1, PyObject *t2, TrailObject *trail)
{
    PyObject *r = VarAPI->unify(t1, t2, trail);
    if (!r) return -1;
    int result = PyObject_IsTrue(r);
    Py_DECREF(r);
    return result;
}

/* ── The char term (atoms-as-cells/strings §6.2) ──────────────────────────
 *
 * The second copy of the three char helpers (the first is in
 * ``runtime/_list_unify.c``; these extensions share no header). Every place
 * this file MAKES a char, TESTS for one, or reads a char's spelling goes
 * through them, so the Stage B representation flip is an edit to these
 * bodies alone — in every copy. Twins of ``clausal.logic.atoms.char_atom``
 * / ``is_char_atom`` / ``spelling``.
 *
 * THE FLIP (Stage B): a char IS the arity-0 cell ``("a",)`` — an ordinary
 * atom whose spelling is one character — and a 1-char ``str`` is a
 * one-element STRING, not a char.
 */

/* Build the char whose spelling is the 1-char str *ch1*. New reference. */
static inline PyObject *
char_atom_obj(PyObject *ch1)
{
    return Py_NewRef(ch1);   /* STAGE 2: the char atom is the 1-char str itself */
}

/* True iff *e* is a char — the arity-0 cell of a 1-char str. */
static inline int
is_char_atom_obj(PyObject *e)
{
    return PyUnicode_Check(e) && PyUnicode_GET_LENGTH(e) == 1;   /* STAGE 2: a char is the 1-char str */
}

/* The spelling of the char *e* — BORROWED reference, valid while *e* is.
 * The size test keeps this total: a non-cell object is returned unchanged
 * rather than indexed out of range (``seq_join_chars``'s callers pass
 * trusted-but-unvalidated lists). */
static inline PyObject *
char_spelling_obj(PyObject *e)
{
    return e;   /* STAGE 2: a char atom is its own spelling */
}

/*
 * Join a list of CHARS into a Python str via their spellings.
 * Caller guarantees all items are chars (no validation).
 * Returns a new reference, or NULL on error.
 */
static PyObject *
seq_join_chars(PyObject *items)
{
    Py_ssize_t n = PyList_GET_SIZE(items);
    PyObject *spellings = PyList_New(n);
    if (!spellings) return NULL;
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *sp = char_spelling_obj(PyList_GET_ITEM(items, i));
        if (!sp) { Py_DECREF(spellings); return NULL; }
        Py_INCREF(sp);
        PyList_SET_ITEM(spellings, i, sp);
    }
    PyObject *joined = PyUnicode_Join(empty_string, spellings);
    Py_DECREF(spellings);
    if (!joined) return NULL;
    /* stage 1 of the atoms-as-str flip (spec 2026-09-18): a text RESULT is
     * the chars CARRIER ('$chars', text), never a bare str -- every caller
     * of this join (append/3 splits, select/3 remainders, permutation/2)
     * is handing a term out. */
    PyObject *tag = PyUnicode_FromString("$chars");
    if (!tag) { Py_DECREF(joined); return NULL; }
    PyObject *carrier = PyTuple_Pack(2, tag, joined);
    Py_DECREF(tag); Py_DECREF(joined);
    return carrier;
}

/*
 * make_seq_result(items, was_string) — C version of Python _seq_result().
 * If was_string and all items are chars, joins their spellings into a string.
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
        if (!is_char_atom_obj(c)) {
            Py_INCREF(items);
            return items;
        }
    }
    return seq_join_chars(items);
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
    PyObject *items, *elem, *trail_obj;
    Py_ssize_t start;

    if (!PyArg_ParseTuple(args, "OnOO", &items, &start, &elem, &trail_obj))
        return NULL;

    if (!PyList_Check(items)) {  /* F021: public attr — guard before GET_SIZE */
        PyErr_SetString(PyExc_TypeError, "items must be a list");
        return NULL;
    }
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = start; i < len; i++) {
        Py_ssize_t mark = VarAPI->trail_mark(trail);

        PyObject *item = PyList_GET_ITEM(items, i);
        int ok = call_unify(elem, item, trail);
        if (ok < 0) return NULL;

        if (ok) {
            /* Success — bindings active, caller will undo after yield */
            return Py_BuildValue("(nn)", i + 1, mark);
        }

        VarAPI->trail_undo(trail, mark);
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
    PyObject *items, *elem, *trail_obj;

    if (!PyArg_ParseTuple(args, "OOO", &items, &elem, &trail_obj))
        return NULL;

    if (!PyList_Check(items)) {  /* F021: public attr — guard before GET_SIZE */
        PyErr_SetString(PyExc_TypeError, "items must be a list");
        return NULL;
    }
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = 0; i < len; i++) {
        Py_ssize_t mark = VarAPI->trail_mark(trail);

        PyObject *item = PyList_GET_ITEM(items, i);
        int ok = call_unify(elem, item, trail);
        if (ok < 0) return NULL;

        if (ok) Py_RETURN_TRUE;

        VarAPI->trail_undo(trail, mark);
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
 * When out_str is true, items are guaranteed to be single-char strings
 * (from _as_items on a string input), so validation is skipped.
 *
 * On first successful double-unify: returns (i+1, mark).
 * On exhaustion: returns None.
 */
static PyObject *
py_append_split_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *items, *l1, *l2, *trail_obj;
    Py_ssize_t start;
    int out_str;

    if (!PyArg_ParseTuple(args, "OnOOpO",
                          &items, &start, &l1, &l2, &out_str, &trail_obj))
        return NULL;

    if (!PyList_Check(items)) {  /* F021: public attr — guard before GET_SIZE */
        PyErr_SetString(PyExc_TypeError, "items must be a list");
        return NULL;
    }
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = start; i <= len; i++) {
        PyObject *prefix = PyList_GetSlice(items, 0, i);
        if (!prefix) return NULL;
        PyObject *suffix = PyList_GetSlice(items, i, len);
        if (!suffix) { Py_DECREF(prefix); return NULL; }

        /* Apply string joining if string mode (trusted — items from a string) */
        if (out_str) {
            PyObject *p2 = seq_join_chars(prefix);
            Py_DECREF(prefix);
            if (!p2) { Py_DECREF(suffix); return NULL; }
            PyObject *s2 = seq_join_chars(suffix);
            Py_DECREF(suffix);
            if (!s2) { Py_DECREF(p2); return NULL; }
            prefix = p2;
            suffix = s2;
        }

        Py_ssize_t mark = VarAPI->trail_mark(trail);

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

        VarAPI->trail_undo(trail, mark);
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
 * and rest with items[:i]+items[i+1:] (joined if was_str).
 *
 * When was_str is true, all items are single-char strings, so the
 * remainder is joined without per-element validation.
 *
 * On first successful double-unify: returns (i+1, mark).
 * On exhaustion: returns None.
 */
static PyObject *
py_select_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *items, *elem, *rest, *trail_obj;
    Py_ssize_t start;
    int was_str;

    if (!PyArg_ParseTuple(args, "OnOOpO",
                          &items, &start, &elem, &rest, &was_str, &trail_obj))
        return NULL;

    if (!PyList_Check(items)) {  /* F021: public attr — guard before GET_SIZE */
        PyErr_SetString(PyExc_TypeError, "items must be a list");
        return NULL;
    }
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = start; i < len; i++) {
        PyObject *item = PyList_GET_ITEM(items, i);

        PyObject *remainder = build_remainder(items, i);
        if (!remainder) return NULL;

        PyObject *rem_val;
        if (was_str) {
            rem_val = seq_join_chars(remainder);
            Py_DECREF(remainder);
            if (!rem_val) return NULL;
        } else {
            rem_val = remainder;
        }

        Py_ssize_t mark = VarAPI->trail_mark(trail);

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

        VarAPI->trail_undo(trail, mark);
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
 * When was_str is true, the permutation elements are all single-char
 * strings, so joining skips per-element validation.
 *
 * The iterator is stateful, so repeated calls advance through permutations.
 */
static PyObject *
py_permutation_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *iter, *perm_var, *trail_obj;
    int was_str;

    if (!PyArg_ParseTuple(args, "OOpO", &iter, &perm_var, &was_str, &trail_obj))
        return NULL;

    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);

    PyObject *item;
    while ((item = PyIter_Next(iter)) != NULL) {
        /* item is a tuple from itertools.permutations — convert to list */
        PyObject *perm_list = PySequence_List(item);
        Py_DECREF(item);
        if (!perm_list) return NULL;

        PyObject *result;
        if (was_str) {
            result = seq_join_chars(perm_list);
            Py_DECREF(perm_list);
            if (!result) return NULL;
        } else {
            result = perm_list;
        }

        Py_ssize_t mark = VarAPI->trail_mark(trail);

        int ok = call_unify(perm_var, result, trail);
        Py_DECREF(result);
        if (ok < 0) return NULL;

        if (ok) {
            return PyLong_FromSsize_t(mark);
        }

        VarAPI->trail_undo(trail, mark);
    }

    /* Check if iteration ended due to an error */
    if (PyErr_Occurred()) return NULL;

    Py_RETURN_NONE;
}


/* ================================================================
 * nth0_find  —  inner loop for list_item/3 enumerate mode
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
    PyObject *items, *n_var, *elem_var, *trail_obj;
    Py_ssize_t start;

    if (!PyArg_ParseTuple(args, "OnOOO",
                          &items, &start, &n_var, &elem_var, &trail_obj))
        return NULL;

    if (!PyList_Check(items)) {  /* F021: public attr — guard before GET_SIZE */
        PyErr_SetString(PyExc_TypeError, "items must be a list");
        return NULL;
    }

    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    Py_ssize_t len = PyList_GET_SIZE(items);

    for (Py_ssize_t i = start; i < len; i++) {
        Py_ssize_t mark = VarAPI->trail_mark(trail);

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

        VarAPI->trail_undo(trail, mark);
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
     "Inner loop for list_item/3 enumerate mode."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_lists_core",
    "C-accelerated inner loops for core list predicates.\n"
    "\n"
    "Uses the _variables C API for direct trail_mark/trail_undo and unify\n"
    "calls, eliminating Python method dispatch overhead.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__lists_core(void)
{
    /* Import the C API capsule from _variables */
    if (import_variables_capi() < 0)
        return NULL;

    /* Cache empty string for PyUnicode_Join */
    empty_string = PyUnicode_FromString("");
    if (!empty_string) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    return m;
}
