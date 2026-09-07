/*
 * _chars_core.c — C helpers for char/string predicate inner loops
 *
 * Moves the mark/unify/undo inner loops of char/atom predicates to C,
 * eliminating Python bytecode overhead.  The Python generator structure
 * is preserved — these helpers are called from Python generators that
 * handle the trampoline protocol.
 *
 * Uses the _variables C API capsule for direct C-level access to unify,
 * deref, is_var, trail_mark, and trail_undo.
 *
 * Pattern: each "find" function iterates from a start index, tries
 * unification at each candidate, and returns (next_index, trail_mark)
 * on the first success — or None when exhausted.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* Import the C API from _variables */
#define VARIABLES_CAPI_CONSUMER
#include "variables/_variables_capi.h"


/* ================================================================
 * Helpers
 * ================================================================ */

/* atom_from_str(s): the atom whose spelling is *s* (new reference).
 * THE FLIP (atoms-as-cells/strings §6.1): an atom is the arity-0 CELL, so
 * this packs the spelling into a 1-tuple.  Keep every result that is an
 * ATOM (not a code, not a position) going through here.
 *
 * Deliberately does NOT intern, unlike ``clausal.logic.atoms.mint`` — this
 * is the twin of ``atoms.char_atom`` in that respect, and for the same
 * reason (see that function's docstring).  Every RUNTIME caller here is an
 * enumerator: char_type/2 over the Unicode alphabet, sub_atom/5's
 * substrings, atom_concat/3's splits.  Interning is permanent on CPython,
 * so interning an enumerated spelling pins it for the life of the process —
 * exactly the "enumeration garbage must not be pinned" rule spec §5.2 gives
 * for the atom table.  Equality is unaffected: two atoms of the same
 * spelling compare equal by tuple ``==`` whether or not slot 0 is shared.
 * The two pre-built tables below are the exception, and a bounded one: they
 * are built here at module init from spellings already interned with
 * PyUnicode_InternFromString.
 *
 * The PYTHON twins of sub_atom/5 and atom_concat/3 (``builtins/chars.py``)
 * do mint, so they DO pin their substrings and split halves.  That is a
 * deliberate divergence, not an oversight: interning is an optimisation with
 * no semantic weight (equality is by ``==``), and the fallback paths run only
 * when this extension is unavailable.  ``atoms.mint``'s docstring records the
 * same split from the other side. */
static inline PyObject *atom_from_str(PyObject *s)
{
    return PyTuple_Pack(1, s);
}


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


/* ================================================================
 * Pre-computed char type tables (built at module init)
 * ================================================================ */

/* Type names — same order as Python _CHAR_TYPES */
static const char *type_names[] = {
    "alpha", "digit", "alnum", "space", "upper",
    "lower", "ascii", "punct", "print", "control",
};
#define NUM_TYPES 10

/* Classification functions — one per type, index matches type_names */
static int
is_alpha(Py_UCS4 c) { return Py_UNICODE_ISALPHA(c); }
static int
is_digit(Py_UCS4 c) { return Py_UNICODE_ISDECIMAL(c) || Py_UNICODE_ISDIGIT(c); }
static int
is_alnum(Py_UCS4 c) { return Py_UNICODE_ISALPHA(c) || Py_UNICODE_ISDECIMAL(c) || Py_UNICODE_ISDIGIT(c) || Py_UNICODE_ISNUMERIC(c); }
static int
is_space(Py_UCS4 c) { return Py_UNICODE_ISSPACE(c); }
static int
is_upper(Py_UCS4 c) { return Py_UNICODE_ISUPPER(c); }
static int
is_lower(Py_UCS4 c) { return Py_UNICODE_ISLOWER(c); }
static int
is_ascii(Py_UCS4 c) { return c < 128; }
static int
is_punct(Py_UCS4 c) {
    return !is_alnum(c) && !Py_UNICODE_ISSPACE(c) && Py_UNICODE_ISPRINTABLE(c);
}
static int
is_print(Py_UCS4 c) { return Py_UNICODE_ISPRINTABLE(c); }
static int
is_control(Py_UCS4 c) { return c < 32 || c == 127; }

typedef int (*char_classifier)(Py_UCS4);
static char_classifier classifiers[NUM_TYPES] = {
    is_alpha, is_digit, is_alnum, is_space, is_upper,
    is_lower, is_ascii, is_punct, is_print, is_control,
};

/* Interned type name SPELLINGS (Python str objects) — the str→index lookup
 * (type_name_index) receives a plain str from the Python side and compares
 * against these. */
static PyObject *type_name_strs[NUM_TYPES] = {NULL};

/* The type-name ATOMS — what char_type/2 unifies its Type argument with. */
static PyObject *type_name_objs[NUM_TYPES] = {NULL};

/* Pre-computed: for each ASCII char [0..127], which type indices match */
#define MAX_TYPES_PER_CHAR NUM_TYPES
static int char_to_type_indices[128][MAX_TYPES_PER_CHAR + 1]; /* -1 terminated */

/* Pre-computed: for each type index, which ASCII chars match */
static Py_UCS4 type_to_chars[NUM_TYPES][129]; /* 0-terminated (Py_UCS4=0 as sentinel won't work, use count) */
static int type_to_chars_count[NUM_TYPES];

/* Single-char ATOM cache for ASCII [0..127] */
static PyObject *ascii_char_objs[128] = {NULL};


static int
init_char_tables(void)
{
    /* Intern type name strings, then mint the atom for each */
    for (int t = 0; t < NUM_TYPES; t++) {
        type_name_strs[t] = PyUnicode_InternFromString(type_names[t]);
        if (!type_name_strs[t]) return -1;
        type_name_objs[t] = atom_from_str(type_name_strs[t]);
        if (!type_name_objs[t]) {
            /* Plan 0's Py_NewRef cannot fail, but Stage B's PyTuple_Pack can:
             * drop the spelling we just took so the failed init leaves no
             * half-built table entry behind. */
            Py_CLEAR(type_name_strs[t]);
            return -1;
        }
    }

    /* Build ascii_char_objs — use FromOrdinal for endian safety and
     * to benefit from CPython's Latin-1 singleton cache; each spelling
     * is then minted into the char atom actually unified. */
    for (int i = 0; i < 128; i++) {
        PyObject *ch_str = PyUnicode_FromOrdinal(i);
        if (!ch_str) return -1;
        ascii_char_objs[i] = atom_from_str(ch_str);
        Py_DECREF(ch_str);
        if (!ascii_char_objs[i]) return -1;
    }

    /* Build char_to_type_indices */
    for (int i = 0; i < 128; i++) {
        int idx = 0;
        for (int t = 0; t < NUM_TYPES; t++) {
            if (classifiers[t]((Py_UCS4)i)) {
                char_to_type_indices[i][idx++] = t;
            }
        }
        char_to_type_indices[i][idx] = -1;  /* sentinel */
    }

    /* Build type_to_chars */
    for (int t = 0; t < NUM_TYPES; t++) {
        int count = 0;
        for (int i = 0; i < 128; i++) {
            if (classifiers[t]((Py_UCS4)i)) {
                type_to_chars[t][count++] = (Py_UCS4)i;
            }
        }
        type_to_chars_count[t] = count;
    }

    return 0;
}


/* ================================================================
 * char_type_find_types — enumerate types for a bound char
 * ================================================================ */

/*
 * char_type_find_types(char_str, start, type_var, trail)
 *   → (next_start, mark) | None
 *
 * char_str is a single-char Python string (already validated by Python caller).
 * Iterates through matching type names from start index.
 */
static PyObject *
py_char_type_find_types(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *char_str, *type_var, *trail_obj;
    Py_ssize_t start;

    if (!PyArg_ParseTuple(args, "UnOO", &char_str, &start, &type_var, &trail_obj))
        return NULL;

    /* F020 (cross-cutting #1): reject a non-Trail arg before casting it —
       Trail_CAST reinterprets arbitrary memory as a TrailObject (UB). */
    if (!Trail_Check(trail_obj)) {
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    /* F020: guard the empty string — PyUnicode_READ_CHAR(s, 0) on "" is an
       out-of-bounds read returning a garbage classification. */
    if (PyUnicode_GET_LENGTH(char_str) < 1)
        Py_RETURN_NONE;

    Py_UCS4 ch = PyUnicode_READ_CHAR(char_str, 0);
    TrailObject *trail = Trail_CAST(trail_obj);

    if (ch >= 128) {
        /* Non-ASCII: test each type dynamically */
        for (Py_ssize_t t = start; t < NUM_TYPES; t++) {
            if (classifiers[t](ch)) {
                Py_ssize_t mark = VarAPI->trail_mark(trail);
                int ok = call_unify(type_var, type_name_objs[t], trail);
                if (ok < 0) return NULL;
                if (ok) {
                    return Py_BuildValue("(nn)", t + 1, mark);
                }
                VarAPI->trail_undo(trail, mark);
            }
        }
        Py_RETURN_NONE;
    }

    /* ASCII: use pre-computed table */
    int *indices = char_to_type_indices[ch];
    /* Find the first index >= start */
    for (int i = 0; indices[i] != -1; i++) {
        if (indices[i] < (int)start) continue;
        Py_ssize_t t = indices[i];
        Py_ssize_t mark = VarAPI->trail_mark(trail);
        int ok = call_unify(type_var, type_name_objs[t], trail);
        if (ok < 0) return NULL;
        if (ok) {
            return Py_BuildValue("(nn)", t + 1, mark);
        }
        VarAPI->trail_undo(trail, mark);
    }
    Py_RETURN_NONE;
}


/* ================================================================
 * char_type_find_chars — enumerate chars for a bound type
 * ================================================================ */

/*
 * char_type_find_chars(type_idx, start, char_var, trail)
 *   → (next_start, mark) | None
 *
 * type_idx is the index into type_names (0..9), determined by Python caller.
 * Iterates ASCII chars matching that type from start index.
 */
static PyObject *
py_char_type_find_chars(PyObject *Py_UNUSED(module), PyObject *args)
{
    int type_idx;
    Py_ssize_t start;
    PyObject *char_var, *trail_obj;

    if (!PyArg_ParseTuple(args, "inOO", &type_idx, &start, &char_var, &trail_obj))
        return NULL;

    if (type_idx < 0 || type_idx >= NUM_TYPES)
        Py_RETURN_NONE;

    if (!Trail_Check(trail_obj)) {  /* F020: guard before Trail_CAST */
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    int count = type_to_chars_count[type_idx];

    for (Py_ssize_t i = start; i < count; i++) {
        Py_UCS4 ch = type_to_chars[type_idx][i];
        /* type_to_chars is ASCII-only by construction (init loop at L128-136).
         * All values are guaranteed to be in [0, 128), so ascii_char_objs[ch]
         * is always present. The unreachable non-ASCII allocation branch that
         * previously lived here (F078 closure) was removed.  The table
         * already holds ATOMS (built through atom_from_str at init), so
         * the entry is unified as-is. */
        PyObject *ch_obj = ascii_char_objs[ch];

        Py_ssize_t mark = VarAPI->trail_mark(trail);
        int ok = call_unify(char_var, ch_obj, trail);
        if (ok < 0) return NULL;

        if (ok) {
            return Py_BuildValue("(nn)", i + 1, mark);
        }
        VarAPI->trail_undo(trail, mark);
    }
    Py_RETURN_NONE;
}


/* ================================================================
 * atom_concat_split_find — enumerate splits of C into A+B
 * ================================================================ */

/*
 * atom_concat_split_find(c_str, start, a_var, b_var, trail)
 *   → (next_start, mark) | None
 *
 * Enumerates splits c_str[:i], c_str[i:] for i in [start, len(c_str)].
 */
static PyObject *
py_atom_concat_split_find(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *c_str, *a_var, *b_var, *trail_obj;
    Py_ssize_t start;

    if (!PyArg_ParseTuple(args, "UnOOO", &c_str, &start, &a_var, &b_var, &trail_obj))
        return NULL;

    if (!Trail_Check(trail_obj)) {  /* F020: guard before Trail_CAST */
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    Py_ssize_t n = PyUnicode_GET_LENGTH(c_str);

    for (Py_ssize_t i = start; i <= n; i++) {
        /* Both halves of a split are ATOMS. */
        PyObject *prefix_str = PyUnicode_Substring(c_str, 0, i);
        if (!prefix_str) return NULL;
        PyObject *prefix = atom_from_str(prefix_str);
        Py_DECREF(prefix_str);
        if (!prefix) return NULL;
        PyObject *suffix_str = PyUnicode_Substring(c_str, i, n);
        if (!suffix_str) { Py_DECREF(prefix); return NULL; }
        PyObject *suffix = atom_from_str(suffix_str);
        Py_DECREF(suffix_str);
        if (!suffix) { Py_DECREF(prefix); return NULL; }

        Py_ssize_t mark = VarAPI->trail_mark(trail);

        int ok1 = call_unify(a_var, prefix, trail);
        if (ok1 < 0) { Py_DECREF(prefix); Py_DECREF(suffix); return NULL; }

        int ok2 = 0;
        if (ok1) {
            ok2 = call_unify(b_var, suffix, trail);
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
 * sub_atom_search — find occurrences of known Sub in Atom
 * ================================================================ */

/*
 * sub_atom_search(atom_str, sub_str, start, before_var, length_var, after_var, trail)
 *   → (next_start, mark) | None
 *
 * Uses PyUnicode_Find to locate sub_str in atom_str starting from start.
 * On each hit, unifies Before/Length/After and returns.
 */
static PyObject *
py_sub_atom_search(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *atom_str, *sub_str, *before_var, *length_var, *after_var, *trail_obj;
    Py_ssize_t start;

    if (!PyArg_ParseTuple(args, "UUnOOOO",
                          &atom_str, &sub_str, &start,
                          &before_var, &length_var, &after_var, &trail_obj))
        return NULL;

    if (!Trail_Check(trail_obj)) {  /* F020: guard before Trail_CAST */
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    Py_ssize_t atom_len = PyUnicode_GET_LENGTH(atom_str);
    Py_ssize_t sub_len = PyUnicode_GET_LENGTH(sub_str);

    Py_ssize_t search_start = start;
    while (search_start <= atom_len) {
        Py_ssize_t pos = PyUnicode_Find(atom_str, sub_str, search_start, atom_len, 1);
        if (pos == -2) return NULL;  /* error */
        if (pos == -1) break;        /* not found */

        Py_ssize_t b = pos;
        Py_ssize_t l = sub_len;
        Py_ssize_t a = atom_len - pos - sub_len;

        PyObject *b_obj = PyLong_FromSsize_t(b);
        if (!b_obj) return NULL;
        PyObject *l_obj = PyLong_FromSsize_t(l);
        if (!l_obj) { Py_DECREF(b_obj); return NULL; }
        PyObject *a_obj = PyLong_FromSsize_t(a);
        if (!a_obj) { Py_DECREF(b_obj); Py_DECREF(l_obj); return NULL; }

        Py_ssize_t mark = VarAPI->trail_mark(trail);

        int ok = call_unify(before_var, b_obj, trail);
        if (ok < 0) { Py_DECREF(b_obj); Py_DECREF(l_obj); Py_DECREF(a_obj); return NULL; }
        if (ok) {
            ok = call_unify(length_var, l_obj, trail);
            if (ok < 0) { Py_DECREF(b_obj); Py_DECREF(l_obj); Py_DECREF(a_obj); return NULL; }
        }
        if (ok) {
            ok = call_unify(after_var, a_obj, trail);
            if (ok < 0) { Py_DECREF(b_obj); Py_DECREF(l_obj); Py_DECREF(a_obj); return NULL; }
        }

        Py_DECREF(b_obj);
        Py_DECREF(l_obj);
        Py_DECREF(a_obj);

        if (ok) {
            return Py_BuildValue("(nn)", pos + 1, mark);
        }
        VarAPI->trail_undo(trail, mark);
        search_start = pos + 1;
    }
    Py_RETURN_NONE;
}


/* ================================================================
 * sub_atom_enum — general enumeration of (Before, Length) pairs
 * ================================================================ */

/*
 * sub_atom_enum(atom_str, flat_start, before_var, length_var, after_var,
 *               sub_var, vb_fixed, vl_fixed, trail)
 *   → (next_flat, mark) | None
 *
 * Enumerates (b, l) pairs where Before + Length + After = len(Atom).
 * flat_start encodes the resume position.
 *
 * vb_fixed: fixed Before value if bound (int >= 0), or -1 if unbound.
 * vl_fixed: fixed Length value if bound (int >= 0), or -1 if unbound.
 *
 * Flat encoding: flat = b * (n + 2) + l, where n = len(atom).
 * We use (n+2) to ensure unique decoding since l can range 0..n.
 */
static PyObject *
py_sub_atom_enum(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *atom_str, *before_var, *length_var, *after_var, *sub_var, *trail_obj;
    Py_ssize_t flat_start;
    Py_ssize_t vb_fixed, vl_fixed;

    if (!PyArg_ParseTuple(args, "UnOOOOnnO",
                          &atom_str, &flat_start,
                          &before_var, &length_var, &after_var, &sub_var,
                          &vb_fixed, &vl_fixed, &trail_obj))
        return NULL;

    if (!Trail_Check(trail_obj)) {  /* F020: guard before Trail_CAST */
        PyErr_SetString(PyExc_TypeError, "trail argument must be a Trail");
        return NULL;
    }
    TrailObject *trail = Trail_CAST(trail_obj);
    Py_ssize_t n = PyUnicode_GET_LENGTH(atom_str);
    Py_ssize_t stride = n + 2;

    /* Decode start position */
    Py_ssize_t b_start = flat_start / stride;
    Py_ssize_t l_start = flat_start % stride;

    /* Determine b range */
    Py_ssize_t b_lo, b_hi;
    if (vb_fixed >= 0) {
        if (vb_fixed > n || b_start > vb_fixed) Py_RETURN_NONE;
        b_lo = vb_fixed;
        b_hi = vb_fixed + 1;
    } else {
        b_lo = b_start;
        b_hi = n + 1;
    }

    for (Py_ssize_t b = b_lo; b < b_hi; b++) {
        Py_ssize_t l_lo_cur, l_hi_cur;
        if (vl_fixed >= 0) {
            if (b + vl_fixed > n) {
                l_start = 0;
                continue;
            }
            l_lo_cur = vl_fixed;
            l_hi_cur = vl_fixed + 1;
        } else {
            l_lo_cur = 0;
            l_hi_cur = n - b + 1;
        }

        /* Apply l_start only for the first b iteration */
        if (b == b_lo && l_start > l_lo_cur) {
            l_lo_cur = l_start;
        }

        for (Py_ssize_t l = l_lo_cur; l < l_hi_cur; l++) {
            Py_ssize_t a = n - b - l;

            PyObject *b_obj = PyLong_FromSsize_t(b);
            if (!b_obj) return NULL;
            PyObject *l_obj = PyLong_FromSsize_t(l);
            if (!l_obj) { Py_DECREF(b_obj); return NULL; }
            PyObject *a_obj = PyLong_FromSsize_t(a);
            if (!a_obj) { Py_DECREF(b_obj); Py_DECREF(l_obj); return NULL; }

            /* Sub is an ATOM (Before/Length/After stay plain ints). */
            PyObject *s_str = PyUnicode_Substring(atom_str, b, b + l);
            if (!s_str) { Py_DECREF(b_obj); Py_DECREF(l_obj); Py_DECREF(a_obj); return NULL; }
            PyObject *s_obj = atom_from_str(s_str);
            Py_DECREF(s_str);
            if (!s_obj) { Py_DECREF(b_obj); Py_DECREF(l_obj); Py_DECREF(a_obj); return NULL; }

            Py_ssize_t mark = VarAPI->trail_mark(trail);

            int ok = call_unify(before_var, b_obj, trail);
            if (ok < 0) goto error_cleanup;
            if (ok) {
                ok = call_unify(length_var, l_obj, trail);
                if (ok < 0) goto error_cleanup;
            }
            if (ok) {
                ok = call_unify(after_var, a_obj, trail);
                if (ok < 0) goto error_cleanup;
            }
            if (ok) {
                ok = call_unify(sub_var, s_obj, trail);
                if (ok < 0) goto error_cleanup;
            }

            Py_DECREF(b_obj);
            Py_DECREF(l_obj);
            Py_DECREF(a_obj);
            Py_DECREF(s_obj);

            if (ok) {
                /* Encode next position */
                Py_ssize_t next_l = l + 1;
                Py_ssize_t next_b = b;
                if (next_l >= l_hi_cur) {
                    next_b = b + 1;
                    next_l = 0;
                }
                Py_ssize_t next_flat = next_b * stride + next_l;
                return Py_BuildValue("(nn)", next_flat, mark);
            }
            VarAPI->trail_undo(trail, mark);
            continue;

error_cleanup:
            Py_DECREF(b_obj);
            Py_DECREF(l_obj);
            Py_DECREF(a_obj);
            Py_DECREF(s_obj);
            return NULL;
        }

        /* Reset l_start for subsequent b values */
        l_start = 0;
    }
    Py_RETURN_NONE;
}


/* ================================================================
 * type_name_index — look up a type name string → index
 * ================================================================ */

/*
 * type_name_index(type_str) → int index (0..9) or -1
 *
 * Helper for Python side to get the type index for char_type_find_chars.
 */
static PyObject *
py_type_name_index(PyObject *Py_UNUSED(module), PyObject *arg)
{
    if (!PyUnicode_Check(arg)) {
        return PyLong_FromLong(-1);
    }
    for (int t = 0; t < NUM_TYPES; t++) {
        if (PyUnicode_Compare(arg, type_name_strs[t]) == 0) {
            if (PyErr_Occurred()) return NULL;
            return PyLong_FromLong(t);
        }
    }
    if (PyErr_Occurred()) return NULL;
    return PyLong_FromLong(-1);
}


/* ================================================================
 * Module definition and init
 * ================================================================ */

static PyMethodDef module_methods[] = {
    {"char_type_find_types", py_char_type_find_types, METH_VARARGS,
     "char_type_find_types(char_str, start, type_var, trail)\n"
     "  -> (next_start, mark) or None\n"
     "\n"
     "Inner loop for char_type/2: enumerate types matching a bound char."},
    {"char_type_find_chars", py_char_type_find_chars, METH_VARARGS,
     "char_type_find_chars(type_idx, start, char_var, trail)\n"
     "  -> (next_start, mark) or None\n"
     "\n"
     "Inner loop for char_type/2: enumerate ASCII chars matching a type."},
    {"atom_concat_split_find", py_atom_concat_split_find, METH_VARARGS,
     "atom_concat_split_find(c_str, start, a_var, b_var, trail)\n"
     "  -> (next_start, mark) or None\n"
     "\n"
     "Inner loop for atom_concat/3: enumerate all splits of a string."},
    {"sub_atom_search", py_sub_atom_search, METH_VARARGS,
     "sub_atom_search(atom_str, sub_str, start, before, length, after, trail)\n"
     "  -> (next_start, mark) or None\n"
     "\n"
     "Inner loop for sub_atom/5: find occurrences of known Sub in Atom."},
    {"sub_atom_enum", py_sub_atom_enum, METH_VARARGS,
     "sub_atom_enum(atom_str, flat_start, before, length, after, sub,\n"
     "              vb_fixed, vl_fixed, trail)\n"
     "  -> (next_flat, mark) or None\n"
     "\n"
     "Inner loop for sub_atom/5: enumerate (Before, Length) pairs."},
    {"type_name_index", py_type_name_index, METH_O,
     "type_name_index(type_str) -> int\n"
     "\n"
     "Look up a type name string and return its index (0-9), or -1."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_chars_core",
    "C-accelerated inner loops for char/string predicates.\n"
    "\n"
    "Uses the _variables C API for direct trail_mark/trail_undo and unify\n"
    "calls, eliminating Python method dispatch overhead.\n",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit__chars_core(void)
{
    /* Import the C API capsule from _variables */
    if (import_variables_capi() < 0)
        return NULL;

    /* Initialize pre-computed char tables */
    if (init_char_tables() < 0)
        return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    return m;
}
