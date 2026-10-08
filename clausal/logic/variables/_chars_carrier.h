/* The chars carrier ('$chars', text): the compact form of a char list, EQUAL
 * to it (stage 1 of the atoms-as-str flip, spec 2026-09-18).  Every C
 * extension that reads, builds or tests one goes through these, so that what
 * slot 1 may hold is decided in one place (the Python twins are
 * ``cells.is_chars`` / ``chars_text`` / ``chars_payload`` / ``chars``).
 *
 * Slot 1 is a str, or a VIEW: a ``cells._Text`` -- the read-only range
 * ``base[lo:hi]`` of a str.  Taking the rest of a text after a matched prefix
 * (a DCG terminal, a head ``[C|Cs]`` against text) hands out a view of the
 * same str instead of copying the rest, so a parse holds its input once and
 * not once per step.  A view is equal to, and hashes as, its text.
 *
 * Readers that only need the length or one char ask carrier_len /
 * seq helpers and never copy; carrier_text flattens a view once (cached on
 * the view) for readers that need the whole str, and may fail.
 *
 * Included by variables/_variables.c, runtime/_list_unify.c, _lists_core.c
 * and _tabling_core.c; each translation unit keeps its own cache below. */
#ifndef CLAUSAL_CHARS_CARRIER_H
#define CLAUSAL_CHARS_CARRIER_H

#include <Python.h>
#include <string.h>

/* A slice shorter than this is copied, as before; a longer one is a view.
 * The same number as ``cells.VIEW_MIN``. */
#define CHARS_VIEW_MIN 64

static PyObject *g_text_view_type = NULL;   /* cells._Text, looked up once */
static PyObject *g_text_slice_fn = NULL;    /* cells.text_slice */

/* Resolve cells._Text and cells.text_slice.  1, or -1 with an exception.
 * From sys.modules, never through the import machinery: this runs inside
 * compiled clause code, whose import hook refuses engine modules, and
 * clausal.logic.cells is always loaded by then (the engine imports it). */
static int
text_view_lookup(void)
{
    if (g_text_view_type) return 1;
    PyObject *name = PyUnicode_FromString("clausal.logic.cells");
    if (!name) return -1;
    PyObject *mod = PyImport_GetModule(name);
    Py_DECREF(name);
    if (!mod) {
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_RuntimeError, "clausal.logic.cells is not loaded");
        return -1;
    }
    PyObject *tp = PyObject_GetAttrString(mod, "_Text");
    PyObject *fn = tp ? PyObject_GetAttrString(mod, "text_slice") : NULL;
    Py_DECREF(mod);
    if (!fn) { Py_XDECREF(tp); return -1; }
    g_text_slice_fn = fn;
    g_text_view_type = tp;      /* set last: it is the "resolved" flag */
    return 1;
}

/* True for a cells._Text instance (exact type).  Before the first view has
 * been seen, a cheap name test filters everything else; a failed lookup is
 * "not a view" (no view can exist without clausal.logic.cells loaded). */
static inline int
is_text_view(PyObject *o)
{
    if (g_text_view_type) return (PyObject *)Py_TYPE(o) == g_text_view_type;
    if (strcmp(Py_TYPE(o)->tp_name, "_Text") != 0) return 0;
    if (text_view_lookup() < 0) { PyErr_Clear(); return 0; }
    return (PyObject *)Py_TYPE(o) == g_text_view_type;
}

/* True for ('$chars', text): an exact 2-tuple whose slot 0 is the tag and
 * slot 1 a str or a view. */
static inline int
is_chars_carrier(PyObject *t)
{
    if (!(PyTuple_CheckExact(t) && PyTuple_GET_SIZE(t) == 2
          && PyUnicode_Check(PyTuple_GET_ITEM(t, 0))
          && PyUnicode_CompareWithASCIIString(PyTuple_GET_ITEM(t, 0), "$chars") == 0))
        return 0;
    PyObject *p = PyTuple_GET_ITEM(t, 1);
    return PyUnicode_Check(p) || is_text_view(p);
}

/* True for a carrier whose slot 1 is a view (the caller checked
 * is_chars_carrier). */
static inline int
carrier_is_view(PyObject *t)
{
    return !PyUnicode_Check(PyTuple_GET_ITEM(t, 1));
}

/* The text of a carrier as a str -- BORROWED; the caller checked
 * is_chars_carrier.  A view is flattened once and the str cached on it, which
 * keeps it alive as long as the carrier.  NULL with an exception on failure. */
static inline PyObject *
carrier_text(PyObject *t)
{
    PyObject *p = PyTuple_GET_ITEM(t, 1);
    if (PyUnicode_Check(p)) return p;
    PyObject *flat = PyObject_GetAttrString(p, "flat");
    if (!flat) return NULL;
    /* Returned BORROWED, so the view's cache must hold it: an exact str that
     * someone besides this call references.  A tampered view (``flat``
     * replaced by a property that does not cache, ``_flat`` set to a
     * non-str) is an error, never a dangling or mistyped pointer. */
    if (!PyUnicode_CheckExact(flat) || Py_REFCNT(flat) < 2) {
        Py_DECREF(flat);
        PyErr_SetString(PyExc_TypeError,
                        "a text view's flat text must be a str it caches");
        return NULL;
    }
    Py_DECREF(flat);
    return flat;
}

/* The length of a carrier's text, without flattening a view.  -1 with an
 * exception on failure. */
static inline Py_ssize_t
carrier_len(PyObject *t)
{
    PyObject *p = PyTuple_GET_ITEM(t, 1);
    if (PyUnicode_Check(p)) return PyUnicode_GET_LENGTH(p);
    return PyObject_Length(p);
}

/* A carrier reads as its text in every sequence helper; anything else is
 * itself.  BORROWED; NULL with an exception if a view cannot be flattened. */
static inline PyObject *
unwrap_chars(PyObject *t)
{
    return is_chars_carrier(t) ? carrier_text(t) : t;
}

/* ('$chars', text) for the str or view *text* (borrowed) -- a new reference. */
static inline PyObject *
make_chars_carrier(PyObject *text)
{
    PyObject *tag = PyUnicode_FromString("$chars");
    if (!tag) return NULL;
    PyObject *carrier = PyTuple_Pack(2, tag, text);
    Py_DECREF(tag);
    return carrier;
}

/* The carrier of chars [start, end) of the carrier *t* -- a new reference.
 * A long slice is a view of the same str (no copy); a short one a fresh str.
 * The caller checked is_chars_carrier and 0 <= start <= end <= length. */
static inline PyObject *
carrier_slice(PyObject *t, Py_ssize_t start, Py_ssize_t end)
{
    PyObject *p = PyTuple_GET_ITEM(t, 1);
    PyObject *piece;
    if (PyUnicode_Check(p)) {
        if (end - start >= CHARS_VIEW_MIN) {
            if (text_view_lookup() < 0) return NULL;
            if (!g_text_slice_fn) {     /* defensive: the pair is set slice-fn first */
                PyErr_SetString(PyExc_RuntimeError, "text_slice not resolved");
                return NULL;
            }
            piece = PyObject_CallFunction(g_text_slice_fn, "Onn", p, start, end);
        }
        else {
            piece = PyUnicode_Substring(p, start, end);
        }
    }
    else {
        piece = PySequence_GetSlice(p, start, end);     /* a view slices to a view or a str */
    }
    if (!piece) return NULL;
    PyObject *c = make_chars_carrier(piece);
    Py_DECREF(piece);
    return c;
}

#endif /* CLAUSAL_CHARS_CARRIER_H */
