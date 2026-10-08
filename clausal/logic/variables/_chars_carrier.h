/* The chars carrier ('$chars', text): the compact form of a char list, EQUAL
 * to it (stage 1 of the atoms-as-str flip, spec 2026-09-18).  Every C
 * extension that reads, builds or tests one goes through these, so that what
 * slot 1 may hold is decided in one place (the Python twins are
 * ``cells.is_chars`` / ``chars_text`` / ``chars``).
 *
 * Included by variables/_variables.c, runtime/_list_unify.c, _lists_core.c
 * and _tabling_core.c. */
#ifndef CLAUSAL_CHARS_CARRIER_H
#define CLAUSAL_CHARS_CARRIER_H

#include <Python.h>

/* True for ('$chars', text): an exact 2-tuple whose slot 0 is the tag and
 * slot 1 a str. */
static inline int
is_chars_carrier(PyObject *t)
{
    return PyTuple_CheckExact(t) && PyTuple_GET_SIZE(t) == 2
        && PyUnicode_Check(PyTuple_GET_ITEM(t, 0))
        && PyUnicode_CompareWithASCIIString(PyTuple_GET_ITEM(t, 0), "$chars") == 0
        && PyUnicode_Check(PyTuple_GET_ITEM(t, 1));
}

/* The text of a carrier -- BORROWED; the caller checked is_chars_carrier. */
static inline PyObject *
carrier_text(PyObject *t)
{
    return PyTuple_GET_ITEM(t, 1);
}

/* A carrier reads as its text in every sequence helper; anything else is
 * itself.  BORROWED. */
static inline PyObject *
unwrap_chars(PyObject *t)
{
    return is_chars_carrier(t) ? carrier_text(t) : t;
}

/* ('$chars', text) for the str *text* (borrowed) -- a new reference. */
static inline PyObject *
make_chars_carrier(PyObject *text)
{
    PyObject *tag = PyUnicode_FromString("$chars");
    if (!tag) return NULL;
    PyObject *carrier = PyTuple_Pack(2, tag, text);
    Py_DECREF(tag);
    return carrier;
}

#endif /* CLAUSAL_CHARS_CARRIER_H */
