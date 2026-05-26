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

/* ================================================================
 * Cached references (set during module init)
 * ================================================================ */

static PyObject *fn_unify  = NULL;  /* clausal.logic.variables.unify */
static PyObject *fn_deref  = NULL;  /* clausal.logic.variables.deref */
static PyObject *fn_is_var = NULL;  /* clausal.logic.variables.is_var */

static PyTypeObject *SegListType     = NULL;
static PyTypeObject *SegStringType   = NULL;
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

/* Get item from list or string at index i.
 * For lists: borrows from list, returns new ref.
 * For strings: creates new 1-char string.
 */
static inline PyObject *
seq_getitem(PyObject *seq, Py_ssize_t i)
{
    if (PyList_Check(seq)) {
        PyObject *item = PyList_GET_ITEM(seq, i);
        Py_INCREF(item);
        return item;
    }
    /* String: PySequence_GetItem returns new ref */
    return PySequence_GetItem(seq, i);
}

/* Slice seq[start:end] — returns new ref. */
static inline PyObject *
seq_slice(PyObject *seq, Py_ssize_t start, Py_ssize_t end)
{
    return PySequence_GetSlice(seq, start, end);
}

/* Get length of a list or string. */
static inline Py_ssize_t
seq_length(PyObject *seq)
{
    if (PyList_Check(seq))
        return PyList_GET_SIZE(seq);
    if (PyUnicode_Check(seq))
        return PyUnicode_GET_LENGTH(seq);
    return PyObject_Length(seq);
}

/* maybe_promote_to_str(result) — F033 / C1 type-preservation:
 *
 * If *result* is a non-empty list whose every element is a ground
 * 1-char str, return the equivalent str. Otherwise return *result*
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
    /* Verify every element is a 1-char str. */
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *e = PyList_GET_ITEM(result, i);
        if (!PyUnicode_Check(e) || PyUnicode_GET_LENGTH(e) != 1) {
            Py_INCREF(result);
            return result;
        }
    }
    /* All 1-char strs — build the promoted str via str.join. */
    PyObject *empty = PyUnicode_FromStringAndSize("", 0);
    if (!empty) return NULL;
    PyObject *joined = PyUnicode_Join(empty, result);
    Py_DECREF(empty);
    return joined;
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
     * the unbound holes); SegList keeps the historical silent-False
     * behaviour (SegList-vs-SegList unification is blocked by F030,
     * Phase 6). The Python fallback mirrors this asymmetry. */
    if (PyObject_TypeCheck(d, SegStringType)) {
        PyObject *walked = PyObject_CallMethod(d, "__walk__", NULL);
        Py_DECREF(d);
        if (!walked) return NULL;
        d = walked;
        if (!PyList_Check(d) && !PyUnicode_Check(d)) {
            Py_DECREF(d);
            Py_RETURN_NONE;
        }
    }
    if (PyObject_TypeCheck(d, SegListType)) {
        PyObject *walked = PyObject_CallMethod(d, "__walk__", NULL);
        Py_DECREF(d);
        if (!walked) return NULL;
        d = walked;
        if (!PyList_Check(d) && !PyUnicode_Check(d)) {
            Py_DECREF(d);
            Py_RETURN_FALSE;
        }
    }

    /* ── list or str ── */
    if (PyList_Check(d) || PyUnicode_Check(d)) {
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
        Py_DECREF(d);
        if (isv < 0) return NULL;
        if (isv) Py_RETURN_NONE;
    }

    /* ── Otherwise: fail ── */
    Py_RETURN_FALSE;
}


/* ================================================================
 * _head_list_unify_output
 * ================================================================ */

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

    /* Build result list from [deref(v) for v in var_vals] */
    Py_ssize_t n_before = PyList_GET_SIZE(var_vals);
    Py_ssize_t n_after  = PyList_GET_SIZE(after_vals);
    int has_star = (star_val != Py_None);

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
        } else if (PyUnicode_Check(s)) {
            /* Liskov "strings-as-lists" rule: a str-bound star is
             * treated as a list of 1-char strs. Splat its chars into
             * the result; the final ``maybe_promote_to_str`` will
             * re-promote when every element is a 1-char str. */
            Py_ssize_t slen = PyUnicode_GET_LENGTH(s);
            for (Py_ssize_t i = 0; i < slen; i++) {
                PyObject *ch = PyUnicode_Substring(s, i, i + 1);
                if (!ch) { Py_DECREF(s); goto error; }
                int rc = PyList_Append(result, ch);
                Py_DECREF(ch);
                if (rc < 0) { Py_DECREF(s); goto error; }
            }
            Py_DECREF(s);
        } else if (PyObject_TypeCheck(s, SegListType) ||
                   PyObject_TypeCheck(s, SegStringType)) {
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

            if (PyList_Check(walked) || PyUnicode_Check(walked)) {
                /* Ground SegList (→ list) or ground SegString (→ str):
                 * extend result with the elements / chars. */
                Py_ssize_t wlen = PyObject_Length(walked);
                if (wlen < 0) { Py_DECREF(walked); goto error; }
                for (Py_ssize_t i = 0; i < wlen; i++) {
                    PyObject *item = PyList_Check(walked)
                        ? PyList_GET_ITEM(walked, i)
                        : PyUnicode_Substring(walked, i, i + 1);
                    if (!item) { Py_DECREF(walked); goto error; }
                    int rc = PyList_Append(result, item);
                    if (!PyList_Check(walked)) Py_DECREF(item);
                    if (rc < 0) { Py_DECREF(walked); goto error; }
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
                    if (walked_is_segstring && PyUnicode_Check(iseg)) {
                        /* Convert str segment to ConcreteSeg(list(seg)). */
                        PyObject *chars = PySequence_List(iseg);
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
        /* F033: promote list-of-1-char-strs back to str under the Liskov
         * "strings-as-lists" rule. */
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
    PyObject *cs = PyObject_GetAttrString(terms_mod, "ConcreteSeg");
    PyObject *vs = PyObject_GetAttrString(terms_mod, "VarSeg");
    Py_DECREF(terms_mod);

    if (!sl || !ss || !cs || !vs) return NULL;
    SegListType     = (PyTypeObject *)sl;
    SegStringType   = (PyTypeObject *)ss;
    ConcreteSegType = (PyTypeObject *)cs;
    VarSegType      = (PyTypeObject *)vs;

    PyObject *m = PyModule_Create(&moduledef);
    return m;
}
