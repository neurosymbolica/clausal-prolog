/*
 * _list_unify.c — C implementation of _head_list_unify_input/output
 *
 * These functions are the runtime hot path for list pattern matching
 * in compiled clause heads ([H, *T], [A, B, C], [H, *M, T], etc.).
 *
 * Moving them to C eliminates Python frame creation, loop overhead,
 * and per-iteration attribute lookups.  The per-element unify() call
 * goes through cached Python function objects.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "../variables/_chars_carrier.h"

/* ================================================================
 * Cached references (set during module init)
 * ================================================================ */

static PyObject *fn_unify  = NULL;  /* clausal.logic.variables.unify */
static PyObject *fn_deref  = NULL;  /* clausal.logic.variables.deref */
static PyObject *fn_is_var = NULL;  /* clausal.logic.variables.is_var */

/* clausal.logic.runtime.list_unify._seglist_input_fallback, looked up on
 * first use: that module imports this one, so it cannot be bound at init. */
static PyObject *fn_seglist_fallback = NULL;

/* clausal.logic.runtime.list_unify._cons_cell_input_fallback, looked up on
 * first use for the same reason. */
static PyObject *fn_cons_fallback = NULL;

static PyTypeObject *SegListType     = NULL;
static PyTypeObject *SegStringType   = NULL;
static PyTypeObject *SegBytesType    = NULL;
static PyTypeObject *ConcreteSegType = NULL;
static PyTypeObject *VarSegType      = NULL;

/* ================================================================
 * Helpers
 * ================================================================ */

/* Call deref(term) — returns a new reference. */
static inline PyObject *
call_deref(PyObject *term)
{
    return PyObject_CallOneArg(fn_deref, term);
}

/* Call is_var(term) — returns 1 if var, 0 if not, -1 on error. */
static inline int
call_is_var(PyObject *term)
{
    PyObject *r = PyObject_CallOneArg(fn_is_var, term);
    if (!r) return -1;
    int result = PyObject_IsTrue(r);
    Py_DECREF(r);
    return result;
}

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

/* ── The char term (atoms-as-cells/strings §6.2) ──────────────────────────
 *
 * Three one-line helpers, deliberately duplicated per .c file (these
 * extensions share no header): every place the list machinery MAKES a char,
 * TESTS for one, or reads a char's spelling goes through them, so the
 * Stage B representation flip is an edit to these three bodies alone.
 * Twins of ``clausal.logic.atoms.char_atom`` / ``is_char_atom`` /
 * ``spelling`` — keep the three copies in lockstep.
 *
 * THE FLIP (Stage B): a char IS the arity-0 cell ``("a",)`` — an ordinary
 * atom whose spelling is one character — and a 1-char ``str`` is a
 * one-element STRING, not a char.  The str arms these helpers carried for
 * Stage A's dual acceptance are gone with the representation that needed
 * them.
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

/* Get item from list or string at index i.
 * For lists: borrows from list, returns new ref.
 * For strings: builds the CHAR at that index (char_atom_obj).
 * For bytes: the int code (codes model — never a char).
 */

/* the chars carrier reads as its text in every sequence helper: is_chars_carrier,
 * carrier_text, unwrap_chars and make_chars_carrier come from _chars_carrier.h */

static inline PyObject *
seq_getitem(PyObject *seq, Py_ssize_t i)
{
    if (is_chars_carrier(seq)) {
        seq = PyTuple_GET_ITEM(seq, 1);
        if (!PyUnicode_Check(seq))
            return PySequence_GetItem(seq, i);   /* a view: its char, no copy */
    }
    if (PyList_Check(seq)) {
        PyObject *item = PyList_GET_ITEM(seq, i);
        Py_INCREF(item);
        return item;
    }
    if (PyUnicode_Check(seq)) {
        PyObject *ch = PySequence_GetItem(seq, i);
        if (!ch) return NULL;
        PyObject *a = char_atom_obj(ch);
        Py_DECREF(ch);
        return a;
    }
    /* bytes and friends: PySequence_GetItem returns new ref */
    return PySequence_GetItem(seq, i);
}

/* Split the str *s* into its CHARS — the C twin of ``str_chars``.
 * Appends each char to *out* (a list). Returns 0 on success, -1 on error. */
static int
extend_with_str_chars(PyObject *out, PyObject *s)
{
    Py_ssize_t slen = PyUnicode_GET_LENGTH(s);
    for (Py_ssize_t i = 0; i < slen; i++) {
        PyObject *piece = PyUnicode_Substring(s, i, i + 1);
        if (!piece) return -1;
        PyObject *ch = char_atom_obj(piece);
        Py_DECREF(piece);
        if (!ch) return -1;
        int rc = PyList_Append(out, ch);
        Py_DECREF(ch);
        if (rc < 0) return -1;
    }
    return 0;
}

/* Join a list of CHARS into a str via their spellings — the C twin of
 * ``join_chars``. Returns a new reference, or NULL on error. */
static PyObject *
join_char_spellings(PyObject *chars)
{
    Py_ssize_t n = PyList_GET_SIZE(chars);
    PyObject *spellings = PyList_New(n);
    if (!spellings) return NULL;
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *sp = char_spelling_obj(PyList_GET_ITEM(chars, i));
        if (!sp) { Py_DECREF(spellings); return NULL; }
        Py_INCREF(sp);
        PyList_SET_ITEM(spellings, i, sp);
    }
    PyObject *empty = PyUnicode_FromStringAndSize("", 0);
    if (!empty) { Py_DECREF(spellings); return NULL; }
    PyObject *joined = PyUnicode_Join(empty, spellings);
    Py_DECREF(empty);
    Py_DECREF(spellings);
    return joined;
}


/* Slice seq[start:end] — returns new ref.  The carrier slices as its text,
 * and a str slice (a text target's star tail) is handed out as the CARRIER
 * (stage 1): what a Var binds to is never a bare str. */
static inline PyObject *
seq_slice(PyObject *seq, Py_ssize_t start, Py_ssize_t end)
{
    if (is_chars_carrier(seq))
        return carrier_slice(seq, start, end);   /* a long tail is a view, not a copy */
    PyObject *s = PySequence_GetSlice(seq, start, end);
    if (s && PyUnicode_Check(s)) {
        PyObject *c = make_chars_carrier(s);
        Py_DECREF(s);
        return c;
    }
    return s;
}

/* The ISO cons cell ('.', H, T) -- the term an improper list such as
 * [b|foo] is (D50).  Twin of ``clausal.terms._is_cons_cell``. */
static inline int
is_cons_cell(PyObject *t)
{
    if (!PyTuple_CheckExact(t) || PyTuple_GET_SIZE(t) != 3)
        return 0;
    PyObject *f = PyTuple_GET_ITEM(t, 0);
    return PyUnicode_Check(f) && PyUnicode_CompareWithASCIIString(f, ".") == 0;
}

/* Get length of a list or string. */
static inline Py_ssize_t
seq_length(PyObject *seq)
{
    if (is_chars_carrier(seq))
        return carrier_len(seq);
    if (PyList_Check(seq))
        return PyList_GET_SIZE(seq);
    if (PyUnicode_Check(seq))
        return PyUnicode_GET_LENGTH(seq);
    return PyObject_Length(seq);
}

/* maybe_promote_to_str(result) — F033 / C1 type-preservation:
 *
 * If *result* is a non-empty list whose every element is a ground
 * CHAR, return the equivalent str. Otherwise return *result*
 * unchanged (with its refcount incremented).
 *
 * Mirrors the Python ``_seg_helpers.maybe_promote_to_str`` helper
 * applied at every result-construction site in ``list_unify.py``
 * /  ``body_star_unify.py`` under the Liskov "strings-as-lists" rule:
 * the default output type is list; str is produced only when the
 * upgrade is provable from the result elements.
 *
 * Returns a new reference to either the promoted str or the
 * unchanged (refcount-incremented) input. Returns NULL on error.
 */
static PyObject *
maybe_promote_to_str(PyObject *result)
{
    if (!PyList_Check(result)) {
        Py_INCREF(result);
        return result;
    }
    Py_ssize_t n = PyList_GET_SIZE(result);
    if (n == 0) {
        Py_INCREF(result);
        return result;
    }
    /* Verify every element is a char. */
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *e = PyList_GET_ITEM(result, i);
        if (!is_char_atom_obj(e)) {
            Py_INCREF(result);
            return result;
        }
    }
    /* All chars — build the promoted str from their spellings. */
    PyObject *joined = join_char_spellings(result);
    if (!joined) return NULL;
    /* stage 1: a promoted text result is the CARRIER, never a bare str */
    PyObject *carrier = make_chars_carrier(joined);
    Py_DECREF(joined);
    return carrier;
}

/* maybe_promote_to_bytes(result) — codes-model parallel of
 * maybe_promote_to_str. If *result* is a non-empty list whose every element
 * is a ground int in [0, 255] (excluding bool), return the equivalent bytes;
 * otherwise return *result* unchanged (refcount-incremented). Called ONLY at
 * sites where a bytes / SegBytes source was present. Returns NULL on error. */
static PyObject *
maybe_promote_to_bytes(PyObject *result)
{
    if (!PyList_Check(result)) {
        Py_INCREF(result);
        return result;
    }
    Py_ssize_t n = PyList_GET_SIZE(result);
    if (n == 0) {
        Py_INCREF(result);
        return result;
    }
    /* Validate codes domain and fill a byte buffer. */
    char *buf = (char *)PyMem_Malloc(n);
    if (!buf) return PyErr_NoMemory();
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *e = PyList_GET_ITEM(result, i);
        if (!PyLong_Check(e) || PyBool_Check(e)) {
            PyMem_Free(buf);
            Py_INCREF(result);
            return result;
        }
        int overflow = 0;
        long v = PyLong_AsLongAndOverflow(e, &overflow);
        if (overflow || v < 0 || v > 255) {
            PyMem_Free(buf);
            Py_INCREF(result);
            return result;
        }
        buf[i] = (char)(unsigned char)v;
    }
    PyObject *out = PyBytes_FromStringAndSize(buf, n);
    PyMem_Free(buf);
    return out;
}

/* ================================================================
 * _head_list_unify_input
 * ================================================================ */

static PyObject *
py_head_list_unify_input(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *target, *var_vals, *star_val, *after_vals, *trail;

    if (!PyArg_ParseTuple(args, "OOOOO",
                          &target, &var_vals, &star_val, &after_vals, &trail))
        return NULL;

    /* deref(target) */
    PyObject *d = call_deref(target);
    if (!d) return NULL;

    Py_ssize_t n_before = PyList_GET_SIZE(var_vals);
    int has_star = (star_val != Py_None);
    Py_ssize_t n_after = PyList_GET_SIZE(after_vals);

    /* ── Fast path: [H, *T] on a plain list ── */
    if (PyList_Check(d) && has_star && n_after == 0) {
        Py_ssize_t dlen = PyList_GET_SIZE(d);
        if (dlen < n_before) {
            Py_DECREF(d);
            Py_RETURN_FALSE;
        }
        for (Py_ssize_t i = 0; i < n_before; i++) {
            PyObject *v = PyList_GET_ITEM(var_vals, i);
            PyObject *elem = PyList_GET_ITEM(d, i);
            int ok = call_unify(v, elem, trail);
            if (ok < 0) { Py_DECREF(d); return NULL; }
            if (!ok) { Py_DECREF(d); Py_RETURN_FALSE; }
        }
        PyObject *tail = PyList_GetSlice(d, n_before, dlen);
        if (!tail) { Py_DECREF(d); return NULL; }
        int ok = call_unify(star_val, tail, trail);
        Py_DECREF(tail);
        Py_DECREF(d);
        if (ok < 0) return NULL;
        if (ok) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }

    /* ── Normalise SegList / SegString ──
     * F031 / F032 (C3 audit): SegString gets the same walk treatment as
     * SegList so the head/body input-mode pattern accepts ground
     * SegStrings (which walk to plain str and route through the
     * (list, str) arm below).
     *
     * For non-ground walked values the two types diverge: SegString
     * returns Py_None (defer to output mode so the body can constrain
     * the unbound holes); an open SegList is unified with the pattern as
     * a term by the Python twin's _seglist_input_fallback (F030), which
     * both implementations share. */
    if (PyObject_TypeCheck(d, SegStringType)) {
        PyObject *walked = PyObject_CallMethod(d, "__walk__", NULL);
        Py_DECREF(d);
        if (!walked) return NULL;
        d = walked;
        if (!PyList_Check(d) && !is_chars_carrier(d)) {   /* STAGE 2: a bare str is an atom */
            Py_DECREF(d);
            Py_RETURN_NONE;
        }
    }
    if (PyObject_TypeCheck(d, SegBytesType)) {
        PyObject *walked = PyObject_CallMethod(d, "__walk__", NULL);
        Py_DECREF(d);
        if (!walked) return NULL;
        d = walked;
        if (!PyList_Check(d) && !PyBytes_Check(d)) {
            Py_DECREF(d);
            Py_RETURN_NONE;
        }
    }
    if (PyObject_TypeCheck(d, SegListType)) {
        PyObject *walked = PyObject_CallMethod(d, "__walk__", NULL);
        Py_DECREF(d);
        if (!walked) return NULL;
        d = walked;
        if (!PyList_Check(d) && !is_chars_carrier(d)) {   /* STAGE 2: a bare str is an atom */
            /* Still open: unify it with the pattern as a term (F030). */
            if (!fn_seglist_fallback) {
                PyObject *mod = PyImport_ImportModule(
                    "clausal.logic.runtime.list_unify");
                if (!mod) { Py_DECREF(d); return NULL; }
                fn_seglist_fallback = PyObject_GetAttrString(
                    mod, "_seglist_input_fallback");
                Py_DECREF(mod);
                if (!fn_seglist_fallback) { Py_DECREF(d); return NULL; }
            }
            PyObject *r = PyObject_CallFunctionObjArgs(
                fn_seglist_fallback, d, var_vals, star_val, after_vals,
                trail, NULL);
            Py_DECREF(d);
            return r;
        }
    }

    /* ── list, str, or bytes ── */
    if (PyList_Check(d) || is_chars_carrier(d) || PyBytes_Check(d)) {   /* STAGE 2 */
        Py_ssize_t dlen = seq_length(d);
        Py_ssize_t min_len = n_before + n_after;

        if (!has_star) {
            if (dlen != min_len) {
                Py_DECREF(d);
                Py_RETURN_FALSE;
            }
        } else {
            if (dlen < min_len) {
                Py_DECREF(d);
                Py_RETURN_FALSE;
            }
        }

        /* Unify before-star elements */
        for (Py_ssize_t i = 0; i < n_before; i++) {
            PyObject *v = PyList_GET_ITEM(var_vals, i);
            PyObject *elem = seq_getitem(d, i);
            if (!elem) { Py_DECREF(d); return NULL; }
            int ok = call_unify(v, elem, trail);
            Py_DECREF(elem);
            if (ok < 0) { Py_DECREF(d); return NULL; }
            if (!ok) { Py_DECREF(d); Py_RETURN_FALSE; }
        }

        /* Unify star element */
        if (has_star) {
            Py_ssize_t star_end = n_after ? (dlen - n_after) : dlen;
            PyObject *star_slice = seq_slice(d, n_before, star_end);
            if (!star_slice) { Py_DECREF(d); return NULL; }
            int ok = call_unify(star_val, star_slice, trail);
            Py_DECREF(star_slice);
            if (ok < 0) { Py_DECREF(d); return NULL; }
            if (!ok) { Py_DECREF(d); Py_RETURN_FALSE; }
        }

        /* Unify after-star elements */
        for (Py_ssize_t i = 0; i < n_after; i++) {
            PyObject *v = PyList_GET_ITEM(after_vals, i);
            PyObject *elem = seq_getitem(d, dlen - n_after + i);
            if (!elem) { Py_DECREF(d); return NULL; }
            int ok = call_unify(v, elem, trail);
            Py_DECREF(elem);
            if (ok < 0) { Py_DECREF(d); return NULL; }
            if (!ok) { Py_DECREF(d); Py_RETURN_FALSE; }
        }

        Py_DECREF(d);
        Py_RETURN_TRUE;
    }

    /* ── Unbound Var → defer to output mode ── */
    {
        int isv = call_is_var(d);
        if (isv < 0) { Py_DECREF(d); return NULL; }
        if (isv) { Py_DECREF(d); Py_RETURN_NONE; }
    }

    /* ── An improper list, the cons cell ('.', H, T) (D50): take it apart
     * as body unification does, via the Python twin's
     * _cons_cell_input_fallback, which both implementations share. ── */
    if (is_cons_cell(d)) {
        if (!fn_cons_fallback) {
            PyObject *mod = PyImport_ImportModule(
                "clausal.logic.runtime.list_unify");
            if (!mod) { Py_DECREF(d); return NULL; }
            fn_cons_fallback = PyObject_GetAttrString(
                mod, "_cons_cell_input_fallback");
            Py_DECREF(mod);
            if (!fn_cons_fallback) { Py_DECREF(d); return NULL; }
        }
        PyObject *r = PyObject_CallFunctionObjArgs(
            fn_cons_fallback, d, var_vals, star_val, after_vals, trail, NULL);
        Py_DECREF(d);
        return r;
    }

    /* ── Otherwise: fail ── */
    Py_DECREF(d);
    Py_RETURN_FALSE;
}


/* ================================================================
 * _head_list_unify_output
 * ================================================================ */

/* [C1, ..., *S, ..., Cn] where S is bound to a chars carrier and every Ci is
 * a char: the result is the carrier of the joined text, which is what the
 * general path below builds after splitting S into one list entry per char
 * and joining them again.  A clause that builds text cell by cell, like
 * ``rec(N, [a|T]) <- ..., rec(M, T)``, reaches here once per char with a
 * longer S each time, so the general path's per-char work made it
 * quadratic in Python objects; one join copies the text at memcpy speed.
 * Returns a new carrier, Py_None (new reference) when the fast path does
 * not apply, or NULL on error. */
static PyObject *
carrier_star_concat(PyObject *var_vals, PyObject *s, PyObject *after_vals)
{
    Py_ssize_t nb = PyList_GET_SIZE(var_vals);
    Py_ssize_t na = PyList_GET_SIZE(after_vals);
    PyObject *text = carrier_text(s);
    if (!text) return NULL;
    /* an empty result stays the empty list, as maybe_promote_to_str leaves it */
    if (nb + na == 0 && PyUnicode_GET_LENGTH(text) == 0)
        Py_RETURN_NONE;
    PyObject *parts = PyList_New(nb + 1 + na);
    if (!parts) return NULL;
    for (Py_ssize_t i = 0; i < nb + na; i++) {
        PyObject *v = i < nb ? PyList_GET_ITEM(var_vals, i)
                             : PyList_GET_ITEM(after_vals, i - nb);
        PyObject *dv = call_deref(v);
        if (!dv) { Py_DECREF(parts); return NULL; }
        if (!is_char_atom_obj(dv)) {
            Py_DECREF(dv);
            Py_DECREF(parts);
            Py_RETURN_NONE;
        }
        PyList_SET_ITEM(parts, i < nb ? i : i + 1, dv);   /* steals dv */
    }
    PyList_SET_ITEM(parts, nb, Py_NewRef(text));
    PyObject *empty = PyUnicode_FromStringAndSize("", 0);
    if (!empty) { Py_DECREF(parts); return NULL; }
    PyObject *joined = PyUnicode_Join(empty, parts);
    Py_DECREF(empty);
    Py_DECREF(parts);
    if (!joined) return NULL;
    PyObject *carrier = make_chars_carrier(joined);
    Py_DECREF(joined);
    return carrier;
}

static PyObject *
py_head_list_unify_output(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *target, *var_vals, *star_val, *after_vals, *trail;

    if (!PyArg_ParseTuple(args, "OOOOO",
                          &target, &var_vals, &star_val, &after_vals, &trail))
        return NULL;

    /* deref(target) */
    PyObject *d = call_deref(target);
    if (!d) return NULL;

    /* If already bound, switch to input mode */
    {
        int isv = call_is_var(d);
        if (isv < 0) { Py_DECREF(d); return NULL; }
        if (!isv) {
            Py_DECREF(d);
            /* delegate to input — reuse our C version */
            return py_head_list_unify_input(NULL, args);
        }
    }

    if (star_val != Py_None) {
        PyObject *s0 = call_deref(star_val);
        if (!s0) { Py_DECREF(d); return NULL; }
        PyObject *fast = is_chars_carrier(s0)
            ? carrier_star_concat(var_vals, s0, after_vals) : Py_NewRef(Py_None);
        Py_DECREF(s0);
        if (!fast) { Py_DECREF(d); return NULL; }
        if (fast != Py_None) {
            int ok = call_unify(d, fast, trail);
            Py_DECREF(fast);
            Py_DECREF(d);
            if (ok < 0) return NULL;
            if (ok) Py_RETURN_TRUE;
            Py_RETURN_FALSE;
        }
        Py_DECREF(fast);
    }

    /* Build result list from [deref(v) for v in var_vals] */
    Py_ssize_t n_before = PyList_GET_SIZE(var_vals);
    Py_ssize_t n_after  = PyList_GET_SIZE(after_vals);
    int has_star = (star_val != Py_None);
    /* THE FLIP (atoms-as-cells/strings §6.2) DELETED the ``star_was_str``
     * anti-back-door gate that used to stand here (and its Python twin in
     * ``list_unify.py``).  It guarded a hazard that no longer exists: under
     * P3-1 an atom was a plain ``str``, so a constructed list that happened
     * to hold 1-char atoms would have been "promoted" into a str and
     * silently re-created the retired str~list cons identity.  A char is a
     * CELL now, so a list of chars IS the string — promoting it is not a
     * back door, it is the same term in its compact representation (R-S2).
     * ``maybe_promote_to_str`` therefore fires unconditionally at the tail. */

    PyObject *result = PyList_New(0);
    if (!result) { Py_DECREF(d); return NULL; }

    /* Append deref'd before-star values */
    for (Py_ssize_t i = 0; i < n_before; i++) {
        PyObject *v = PyList_GET_ITEM(var_vals, i);
        PyObject *dv = call_deref(v);
        if (!dv) goto error;
        int rc = PyList_Append(result, dv);
        Py_DECREF(dv);
        if (rc < 0) goto error;
    }

    /* Handle star_val */
    if (has_star) {
        PyObject *s = call_deref(star_val);
        if (!s) goto error;

        int s_text = 0;
        if (is_chars_carrier(s)) {
            /* the carrier splats as its text (owned reference swap); the flag
             * is what makes the text arm below reachable -- a bare str star
             * is an ATOM element and takes the else arm (STAGE 2) */
            PyObject *inner = carrier_text(s);
            if (!inner) { Py_DECREF(s); goto error; }
            Py_INCREF(inner);
            Py_DECREF(s);
            s = inner;
            s_text = 1;
        }
        if (PyList_Check(s)) {
            /* Plain list: extend result */
            Py_ssize_t slen = PyList_GET_SIZE(s);
            for (Py_ssize_t i = 0; i < slen; i++) {
                PyObject *item = PyList_GET_ITEM(s, i);
                if (PyList_Append(result, item) < 0) {
                    Py_DECREF(s);
                    goto error;
                }
            }
            Py_DECREF(s);
        } else if (s_text) {
            /* a carrier-bound star splats as its CHARS; maybe_promote_to_str
             * re-promotes the whole result when every element is a char */
            if (extend_with_str_chars(result, s) < 0) {
                Py_DECREF(s);
                goto error;
            }
            Py_DECREF(s);
        } else if (PyBytes_Check(s)) {
            /* Codes-model parallel of the str-star branch: splat the
             * bytes as its int codes, then promote the whole result back
             * to bytes via maybe_promote_to_bytes (only here, where a
             * bytes source is present). */
            Py_ssize_t slen = PyBytes_GET_SIZE(s);
            const unsigned char *sdata =
                (const unsigned char *)PyBytes_AS_STRING(s);
            for (Py_ssize_t i = 0; i < slen; i++) {
                PyObject *code = PyLong_FromLong((long)sdata[i]);
                if (!code) { Py_DECREF(s); goto error; }
                int rc = PyList_Append(result, code);
                Py_DECREF(code);
                if (rc < 0) { Py_DECREF(s); goto error; }
            }
            Py_DECREF(s);
            for (Py_ssize_t i = 0; i < n_after; i++) {
                PyObject *v = PyList_GET_ITEM(after_vals, i);
                PyObject *dv = call_deref(v);
                if (!dv) goto error;
                int rc = PyList_Append(result, dv);
                Py_DECREF(dv);
                if (rc < 0) goto error;
            }
            PyObject *promoted = maybe_promote_to_bytes(result);
            if (!promoted) { Py_DECREF(d); Py_DECREF(result); return NULL; }
            int ok = call_unify(d, promoted, trail);
            Py_DECREF(promoted);
            Py_DECREF(d);
            Py_DECREF(result);
            if (ok < 0) return NULL;
            if (ok) Py_RETURN_TRUE;
            Py_RETURN_FALSE;
        } else if (PyObject_TypeCheck(s, SegListType) ||
                   PyObject_TypeCheck(s, SegStringType) ||
                   PyObject_TypeCheck(s, SegBytesType)) {
            /* SegList / SegString: walk it.
             * F034 (C3 audit): SegString gets the same walk-and-extend (or
             * walk-and-rebuild-as-SegList) treatment as SegList. A walked
             * str is iterated as a sequence of single-char strs so the
             * result list matches what the "strings as char lists" contract
             * would produce. A walked still-non-ground SegString has its
             * str segments converted to ConcreteSeg(list(seg)) before
             * being spliced into the rebuilt SegList. */
            PyObject *walked = PyObject_CallMethod(s, "__walk__", NULL);
            Py_DECREF(s);
            if (!walked) goto error;

            if (PyBytes_Check(walked)) {
                /* Ground SegBytes → bytes: splat int codes, promote to bytes. */
                Py_ssize_t wlen = PyBytes_GET_SIZE(walked);
                const unsigned char *wdata =
                    (const unsigned char *)PyBytes_AS_STRING(walked);
                for (Py_ssize_t i = 0; i < wlen; i++) {
                    PyObject *code = PyLong_FromLong((long)wdata[i]);
                    if (!code) { Py_DECREF(walked); goto error; }
                    int rc = PyList_Append(result, code);
                    Py_DECREF(code);
                    if (rc < 0) { Py_DECREF(walked); goto error; }
                }
                Py_DECREF(walked);
                for (Py_ssize_t i = 0; i < n_after; i++) {
                    PyObject *v = PyList_GET_ITEM(after_vals, i);
                    PyObject *dv = call_deref(v);
                    if (!dv) goto error;
                    int rc = PyList_Append(result, dv);
                    Py_DECREF(dv);
                    if (rc < 0) goto error;
                }
                PyObject *promoted = maybe_promote_to_bytes(result);
                if (!promoted) { Py_DECREF(d); Py_DECREF(result); return NULL; }
                int ok = call_unify(d, promoted, trail);
                Py_DECREF(promoted);
                Py_DECREF(d);
                Py_DECREF(result);
                if (ok < 0) return NULL;
                if (ok) Py_RETURN_TRUE;
                Py_RETURN_FALSE;
            } else if (is_chars_carrier(walked)) {
                PyObject *inner = carrier_text(walked);
                if (!inner) { Py_DECREF(walked); goto error; }
                Py_INCREF(inner);
                Py_DECREF(walked);
                walked = inner;
                if (extend_with_str_chars(result, walked) < 0) {
                    Py_DECREF(walked);
                    goto error;
                }
                Py_DECREF(walked);
            } else if (PyList_Check(walked) || PyUnicode_Check(walked)) {
                /* Ground SegList (→ list) or ground SegString (→ str):
                 * extend result with the elements / CHARS. */
                if (PyList_Check(walked)) {
                    Py_ssize_t wlen = PyList_GET_SIZE(walked);
                    for (Py_ssize_t i = 0; i < wlen; i++) {
                        PyObject *item = PyList_GET_ITEM(walked, i);
                        if (PyList_Append(result, item) < 0) {
                            Py_DECREF(walked); goto error;
                        }
                    }
                } else if (extend_with_str_chars(result, walked) < 0) {
                    Py_DECREF(walked); goto error;
                }
                Py_DECREF(walked);
                /* Append after_vals and unify */
                for (Py_ssize_t i = 0; i < n_after; i++) {
                    PyObject *v = PyList_GET_ITEM(after_vals, i);
                    PyObject *dv = call_deref(v);
                    if (!dv) goto error;
                    int rc = PyList_Append(result, dv);
                    Py_DECREF(dv);
                    if (rc < 0) goto error;
                }
                /* F033: promote list-of-1-char-strs back to str under
                 * the Liskov "strings-as-lists" rule. */
                PyObject *promoted = maybe_promote_to_str(result);
                if (!promoted) { Py_DECREF(d); Py_DECREF(result); return NULL; }
                int ok = call_unify(d, promoted, trail);
                Py_DECREF(promoted);
                Py_DECREF(d);
                Py_DECREF(result);
                if (ok < 0) return NULL;
                if (ok) Py_RETURN_TRUE;
                Py_RETURN_FALSE;
            } else {
                /* Non-ground SegList / SegString: build new SegList with
                 * segments. For SegString, each segment is either ``str``
                 * (convert to ConcreteSeg(list(seg))) or ``VarSeg`` (carry
                 * through unchanged). For SegList, the inner segments are
                 * already ConcreteSeg / VarSeg. */
                int walked_is_segstring = PyObject_TypeCheck(walked, SegStringType);
                PyObject *after_result = PyList_New(0);
                if (!after_result) { Py_DECREF(walked); goto error; }
                for (Py_ssize_t i = 0; i < n_after; i++) {
                    PyObject *v = PyList_GET_ITEM(after_vals, i);
                    PyObject *dv = call_deref(v);
                    if (!dv) { Py_DECREF(after_result); Py_DECREF(walked); goto error; }
                    int rc = PyList_Append(after_result, dv);
                    Py_DECREF(dv);
                    if (rc < 0) { Py_DECREF(after_result); Py_DECREF(walked); goto error; }
                }

                PyObject *segs = PyList_New(0);
                if (!segs) { Py_DECREF(after_result); Py_DECREF(walked); goto error; }

                /* Add ConcreteSeg(result) if result is non-empty */
                if (PyList_GET_SIZE(result) > 0) {
                    PyObject *cseg = PyObject_CallOneArg((PyObject *)ConcreteSegType, result);
                    if (!cseg) { Py_DECREF(segs); Py_DECREF(after_result); Py_DECREF(walked); goto error; }
                    int rc = PyList_Append(segs, cseg);
                    Py_DECREF(cseg);
                    if (rc < 0) { Py_DECREF(segs); Py_DECREF(after_result); Py_DECREF(walked); goto error; }
                }

                /* Extend segs with walked.segments. For SegString, str
                 * segments must be wrapped in ConcreteSeg(list(seg)). */
                PyObject *inner_segs = PyObject_GetAttrString(walked, "segments");
                Py_DECREF(walked);
                if (!inner_segs) { Py_DECREF(segs); Py_DECREF(after_result); goto error; }
                Py_ssize_t islen = PyList_GET_SIZE(inner_segs);
                for (Py_ssize_t i = 0; i < islen; i++) {
                    PyObject *iseg = PyList_GET_ITEM(inner_segs, i);
                    if ((walked_is_segstring && PyUnicode_Check(iseg)) ||
                        PyBytes_Check(iseg)) {
                        /* str segment → ConcreteSeg of its CHARS; bytes
                         * segment → ConcreteSeg(list(seg)) where
                         * list(bytes) == int codes (never chars). */
                        PyObject *chars;
                        if (PyUnicode_Check(iseg)) {
                            chars = PyList_New(0);
                            if (chars && extend_with_str_chars(chars, iseg) < 0) {
                                Py_CLEAR(chars);
                            }
                        } else {
                            chars = PySequence_List(iseg);
                        }
                        if (!chars) {
                            Py_DECREF(inner_segs); Py_DECREF(segs); Py_DECREF(after_result); goto error;
                        }
                        PyObject *cseg = PyObject_CallOneArg((PyObject *)ConcreteSegType, chars);
                        Py_DECREF(chars);
                        if (!cseg) {
                            Py_DECREF(inner_segs); Py_DECREF(segs); Py_DECREF(after_result); goto error;
                        }
                        int rc = PyList_Append(segs, cseg);
                        Py_DECREF(cseg);
                        if (rc < 0) {
                            Py_DECREF(inner_segs); Py_DECREF(segs); Py_DECREF(after_result); goto error;
                        }
                    } else if (PyList_Append(segs, iseg) < 0) {
                        Py_DECREF(inner_segs); Py_DECREF(segs); Py_DECREF(after_result); goto error;
                    }
                }
                Py_DECREF(inner_segs);

                /* Add ConcreteSeg(after_result) if non-empty */
                if (PyList_GET_SIZE(after_result) > 0) {
                    PyObject *cseg = PyObject_CallOneArg((PyObject *)ConcreteSegType, after_result);
                    if (!cseg) { Py_DECREF(segs); Py_DECREF(after_result); goto error; }
                    int rc = PyList_Append(segs, cseg);
                    Py_DECREF(cseg);
                    if (rc < 0) { Py_DECREF(segs); Py_DECREF(after_result); goto error; }
                }
                Py_DECREF(after_result);

                PyObject *new_seglist = PyObject_CallOneArg((PyObject *)SegListType, segs);
                Py_DECREF(segs);
                if (!new_seglist) goto error;

                int ok = call_unify(d, new_seglist, trail);
                Py_DECREF(new_seglist);
                Py_DECREF(d);
                Py_DECREF(result);
                if (ok < 0) return NULL;
                if (ok) Py_RETURN_TRUE;
                Py_RETURN_FALSE;
            }
        } else {
            int isv = call_is_var(s);
            if (isv < 0) { Py_DECREF(s); goto error; }
            if (isv) {
                /* Unbound Var: build SegList [*before, *s, *after] */
                PyObject *after_result = PyList_New(0);
                if (!after_result) { Py_DECREF(s); goto error; }
                for (Py_ssize_t i = 0; i < n_after; i++) {
                    PyObject *v = PyList_GET_ITEM(after_vals, i);
                    PyObject *dv = call_deref(v);
                    if (!dv) { Py_DECREF(after_result); Py_DECREF(s); goto error; }
                    int rc = PyList_Append(after_result, dv);
                    Py_DECREF(dv);
                    if (rc < 0) { Py_DECREF(after_result); Py_DECREF(s); goto error; }
                }

                PyObject *segs = PyList_New(0);
                if (!segs) { Py_DECREF(after_result); Py_DECREF(s); goto error; }

                if (PyList_GET_SIZE(result) > 0) {
                    PyObject *cseg = PyObject_CallOneArg((PyObject *)ConcreteSegType, result);
                    if (!cseg) { Py_DECREF(segs); Py_DECREF(after_result); Py_DECREF(s); goto error; }
                    int rc = PyList_Append(segs, cseg);
                    Py_DECREF(cseg);
                    if (rc < 0) { Py_DECREF(segs); Py_DECREF(after_result); Py_DECREF(s); goto error; }
                }

                PyObject *vseg = PyObject_CallOneArg((PyObject *)VarSegType, s);
                Py_DECREF(s);
                if (!vseg) { Py_DECREF(segs); Py_DECREF(after_result); goto error; }
                if (PyList_Append(segs, vseg) < 0) {
                    Py_DECREF(vseg); Py_DECREF(segs); Py_DECREF(after_result); goto error;
                }
                Py_DECREF(vseg);

                if (PyList_GET_SIZE(after_result) > 0) {
                    PyObject *cseg = PyObject_CallOneArg((PyObject *)ConcreteSegType, after_result);
                    if (!cseg) { Py_DECREF(segs); Py_DECREF(after_result); goto error; }
                    int rc = PyList_Append(segs, cseg);
                    Py_DECREF(cseg);
                    if (rc < 0) { Py_DECREF(segs); Py_DECREF(after_result); goto error; }
                }
                Py_DECREF(after_result);

                PyObject *new_seglist = PyObject_CallOneArg((PyObject *)SegListType, segs);
                Py_DECREF(segs);
                if (!new_seglist) goto error;

                int ok = call_unify(d, new_seglist, trail);
                Py_DECREF(new_seglist);
                Py_DECREF(d);
                Py_DECREF(result);
                if (ok < 0) return NULL;
                if (ok) Py_RETURN_TRUE;
                Py_RETURN_FALSE;
            } else {
                /* Non-list, non-Var: just append */
                if (PyList_Append(result, s) < 0) {
                    Py_DECREF(s);
                    goto error;
                }
                Py_DECREF(s);
            }
        }
    }

    /* Append deref'd after-star values */
    for (Py_ssize_t i = 0; i < n_after; i++) {
        PyObject *v = PyList_GET_ITEM(after_vals, i);
        PyObject *dv = call_deref(v);
        if (!dv) goto error;
        int rc = PyList_Append(result, dv);
        Py_DECREF(dv);
        if (rc < 0) goto error;
    }

    /* unify(d, result, trail) */
    {
        /* A list of chars IS a string (§6.2), so the compact
         * representation is always the right one to build — see the note
         * where ``star_was_str`` used to be declared. */
        PyObject *promoted = maybe_promote_to_str(result);
        if (!promoted) { Py_DECREF(d); Py_DECREF(result); return NULL; }
        int ok = call_unify(d, promoted, trail);
        Py_DECREF(promoted);
        Py_DECREF(d);
        Py_DECREF(result);
        if (ok < 0) return NULL;
        if (ok) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    }

error:
    Py_DECREF(d);
    Py_DECREF(result);
    return NULL;
}


/* ================================================================
 * Module definition and init
 * ================================================================ */

static PyMethodDef module_methods[] = {
    {"_head_list_unify_input", py_head_list_unify_input, METH_VARARGS,
     "_head_list_unify_input(target, var_vals, star_val, after_vals, trail)\n"
     "\n"
     "C implementation of list head pattern input-mode unification."},
    {"_head_list_unify_output", py_head_list_unify_output, METH_VARARGS,
     "_head_list_unify_output(target, var_vals, star_val, after_vals, trail)\n"
     "\n"
     "C implementation of list head pattern output-mode unification."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_list_unify",
    "C-accelerated list head pattern unification.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__list_unify(void)
{
    /* Import clausal.logic.variables */
    PyObject *var_mod = PyImport_ImportModule("clausal.logic.variables");
    if (!var_mod) return NULL;

    fn_unify  = PyObject_GetAttrString(var_mod, "unify");
    fn_deref  = PyObject_GetAttrString(var_mod, "deref");
    fn_is_var = PyObject_GetAttrString(var_mod, "is_var");
    Py_DECREF(var_mod);

    if (!fn_unify || !fn_deref || !fn_is_var) return NULL;

    /* Import clausal.terms for SegList, ConcreteSeg, VarSeg */
    PyObject *terms_mod = PyImport_ImportModule("clausal.terms");
    if (!terms_mod) return NULL;

    PyObject *sl = PyObject_GetAttrString(terms_mod, "SegList");
    PyObject *ss = PyObject_GetAttrString(terms_mod, "SegString");
    PyObject *sb = PyObject_GetAttrString(terms_mod, "SegBytes");
    PyObject *cs = PyObject_GetAttrString(terms_mod, "ConcreteSeg");
    PyObject *vs = PyObject_GetAttrString(terms_mod, "VarSeg");
    Py_DECREF(terms_mod);

    if (!sl || !ss || !sb || !cs || !vs) return NULL;
    SegListType     = (PyTypeObject *)sl;
    SegStringType   = (PyTypeObject *)ss;
    SegBytesType    = (PyTypeObject *)sb;
    ConcreteSegType = (PyTypeObject *)cs;
    VarSegType      = (PyTypeObject *)vs;

    PyObject *m = PyModule_Create(&moduledef);
    return m;
}
