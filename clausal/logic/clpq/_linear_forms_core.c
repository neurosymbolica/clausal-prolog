/* clausal/logic/clpq/_linear_forms_core.c
 *
 * C twins of the hot loops of the clp(q,r) 1.3.3 port (DEVIATIONS.md D24,
 * Low 8): the merge of store.pl add_linear_f1h/4,6
 * (linear_forms.add_homogeneous_parts_first_scaled), the scan of
 * nf_coeff_hom/3 (normal_form_coefficient_homogeneous), the scan of
 * delete_factor_hom/4, nf_substitute/4 whole (normal_form_substitute), the
 * row loops of bv.pl bs/3 (bounded_simplex.back_substitute_variables) and
 * of the binding hook's stand-in pass (attribute_hooks._rename_in_component),
 * the walk of a member list (components.list_elements), and arithmetic.py's
 * add and multiply.
 *
 * Each is an exact twin of its Python reference: the same reads, the same
 * comparisons in the same order, the same calls into Python at the same
 * points, the same terms out, the same exceptions.  In particular:
 *
 *  - An index or an unpacking is checked as Python checks it (IndexError,
 *    ValueError, TypeError with Python's messages), and a list is read by
 *    index after any call that can run Python code, never through a
 *    pointer kept across it.  Everything held across such a call is a
 *    strong reference.
 *  - Order keys are compared as Python compares order_key's tuples.  Two
 *    keys whose comparison runs no Python code (unbound order values, or
 *    bound ones that are exact ints) are compared in C; any other pair is
 *    built as the two tuples and compared with PyObject_RichCompare, as
 *    `key_a == key_b` and `key_a < key_b` do.
 *  - The row loops write as they go, through a callback, so a member that
 *    appears twice reads the row its first visit wrote.
 *
 * The Python stays the reference (linear_forms.python_* and the others;
 * CLAUSAL_CLPQ_PYTHON_LOOPS=1 runs it); tests/clpq_port/
 * test_linear_forms_core.py holds the two equal on the pure-Python
 * reference.  Rationals take a machine-integer path when every part is
 * below 2^31 in magnitude (no product or sum can overflow int64), and call
 * arithmetic.python_add/python_multiply otherwise.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include <stdint.h>

#define VARIABLES_CAPI_CONSUMER
#include "variables/_variables_capi.h"

static PyObject *CLPQ_KEY = NULL;          /* "clpq_holzbaur" */
static PyObject *py_add = NULL;            /* arithmetic.python_add */
static PyObject *py_multiply = NULL;       /* arithmetic.python_multiply */
static PyObject *str_variable_order, *str_id, *str_variable_ids, *str_base,
                *str_start, *str_terms, *str_constant, *str_rest, *str_head,
                *str_linear_form;
static PyObject *int_zero, *int_one;

/* attributes.SolverState and the offsets of its variable_order and
 * linear_form slots: a state of exactly that class is read at the offset,
 * any other object by getattr. */
static PyTypeObject *SolverState_type = NULL;
static Py_ssize_t offset_variable_order = -1, offset_linear_form = -1;

static Py_ssize_t
slot_offset(PyObject *cls, const char *name)
{
    PyObject *descr = PyObject_GetAttrString(cls, name);
    if (!descr) { PyErr_Clear(); return -1; }
    Py_ssize_t offset = -1;
    if (Py_TYPE(descr) == &PyMemberDescr_Type) {
        PyMemberDef *member = ((PyMemberDescrObject *)descr)->d_member;
        if (member->type == Py_T_OBJECT_EX) offset = member->offset;
    }
    Py_DECREF(descr);
    return offset;
}

/* The Python objects the module reads, fetched on first use: arithmetic.py
 * imports this module, so its init imports nothing of the package. */
static int
ensure_globals(void)
{
    if (CLPQ_KEY && py_add && py_multiply) return 0;
    PyObject *attributes = PyImport_ImportModule("clausal.logic.clpq.attributes");
    if (!attributes) return -1;
    PyObject *key = PyObject_GetAttrString(attributes, "CLPQ_KEY");
    PyObject *cls = PyObject_GetAttrString(attributes, "SolverState");
    Py_DECREF(attributes);
    if (!key || !cls) { Py_XDECREF(key); Py_XDECREF(cls); return -1; }
    if (PyType_Check(cls)) {
        offset_variable_order = slot_offset(cls, "variable_order");
        offset_linear_form = slot_offset(cls, "linear_form");
        Py_XSETREF(SolverState_type, (PyTypeObject *)cls);
    } else {
        Py_DECREF(cls);
    }
    PyObject *arithmetic = PyImport_ImportModule("clausal.logic.clpq.arithmetic");
    if (!arithmetic) { Py_DECREF(key); return -1; }
    PyObject *a = PyObject_GetAttrString(arithmetic, "python_add");
    PyObject *m = PyObject_GetAttrString(arithmetic, "python_multiply");
    Py_DECREF(arithmetic);
    if (!a || !m) { Py_DECREF(key); Py_XDECREF(a); Py_XDECREF(m); return -1; }
    Py_XSETREF(CLPQ_KEY, key);
    Py_XSETREF(py_add, a);
    Py_XSETREF(py_multiply, m);
    return 0;
}

/* state.<field> (new ref), at the slot's offset where it can be. */
static PyObject *
state_field(PyObject *state, Py_ssize_t offset, PyObject *name)
{
    if (offset >= 0 && Py_TYPE(state) == SolverState_type) {
        PyObject *value = *(PyObject **)((char *)state + offset);
        if (value) {
            Py_INCREF(value);
            return value;
        }
    }
    return PyObject_GetAttr(state, name);
}

/* ── Python's reads ───────────────────────────────────────────────── */

/* seq[i] for a list, as Python reads it now (new ref, IndexError). */
static PyObject *
list_item(PyObject *list, Py_ssize_t i)
{
    if (PyList_CheckExact(list)) {
        if (i < 0 || i >= PyList_GET_SIZE(list)) {
            PyErr_SetString(PyExc_IndexError, "list index out of range");
            return NULL;
        }
        PyObject *item = PyList_GET_ITEM(list, i);
        Py_INCREF(item);
        return item;
    }
    return PySequence_GetItem(list, i);
}

/* obj[k], as Python subscripts it (new ref). */
static PyObject *
subscript(PyObject *obj, Py_ssize_t k)
{
    if (PyTuple_CheckExact(obj) && k < PyTuple_GET_SIZE(obj)) {
        PyObject *item = PyTuple_GET_ITEM(obj, k);
        Py_INCREF(item);
        return item;
    }
    PyObject *index = PyLong_FromSsize_t(k);
    if (!index) return NULL;
    PyObject *item = PyObject_GetItem(obj, index);
    Py_DECREF(index);
    return item;
}

/* `a, b = obj` (new refs), with Python's errors. */
static int
unpack2(PyObject *obj, PyObject **a, PyObject **b)
{
    *a = *b = NULL;
    if (PyTuple_CheckExact(obj) || PyList_CheckExact(obj)) {
        Py_ssize_t n = PySequence_Fast_GET_SIZE(obj);
        if (n < 2) {
            PyErr_Format(PyExc_ValueError,
                         "not enough values to unpack (expected 2, got %zd)", n);
            return -1;
        }
        if (n > 2) {
            PyErr_SetString(PyExc_ValueError,
                            "too many values to unpack (expected 2)");
            return -1;
        }
        *a = PySequence_Fast_GET_ITEM(obj, 0);
        *b = PySequence_Fast_GET_ITEM(obj, 1);
        Py_INCREF(*a);
        Py_INCREF(*b);
        return 0;
    }
    PyObject *it = PyObject_GetIter(obj);
    if (!it) {
        if (PyErr_ExceptionMatches(PyExc_TypeError)) {
            PyErr_Clear();
            PyErr_Format(PyExc_TypeError, "cannot unpack non-iterable %.200s object",
                         Py_TYPE(obj)->tp_name);
        }
        return -1;
    }
    PyObject *items[2] = {NULL, NULL};
    for (int k = 0; k < 2; k++) {
        items[k] = PyIter_Next(it);
        if (!items[k]) {
            if (!PyErr_Occurred())
                PyErr_Format(PyExc_ValueError,
                             "not enough values to unpack (expected 2, got %d)", k);
            Py_XDECREF(items[0]);
            Py_DECREF(it);
            return -1;
        }
    }
    PyObject *extra = PyIter_Next(it);
    Py_DECREF(it);
    if (extra || PyErr_Occurred()) {
        Py_XDECREF(extra);
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_ValueError, "too many values to unpack (expected 2)");
        Py_DECREF(items[0]);
        Py_DECREF(items[1]);
        return -1;
    }
    *a = items[0];
    *b = items[1];
    return 0;
}

/* ── order keys ───────────────────────────────────────────────────── */

/* order_key's answer: None, (0, var_id) or (1, value); or, for a key
 * handed in from Python that is none of these, the object itself. */
typedef struct {
    int kind;           /* -1 None, 0 (0, id), 1 (1, value), 2 other */
    uint64_t id;        /* kind 0 */
    PyObject *obj;      /* kind 1: the value; kind 2: the key (new refs) */
} Key;

#define KEY_INIT {-1, 0, NULL}

static void
key_clear(Key *k)
{
    Py_CLEAR(k->obj);
    k->kind = -1;
}

/* variable_ordering.order_value_key of an order value. */
static int
order_value_key(PyObject *order, Key *out)
{
    key_clear(out);
    PyObject *d = VarAPI->deref(order);           /* borrowed */
    if (VarAPI->is_var(d)) {
        if (Var_Check(d)) {
            out->id = Var_CAST(d)->var_id;
        } else {
            PyObject *id = PyObject_GetAttr(d, str_id);
            if (!id) return -1;
            out->id = (uint64_t)PyLong_AsUnsignedLongLong(id);
            Py_DECREF(id);
            if (PyErr_Occurred()) return -1;
        }
        out->kind = 0;
        return 0;
    }
    Py_INCREF(d);
    out->obj = d;
    out->kind = 1;
    return 0;
}

/* variable_ordering.order_key(variable). */
static int
order_key(PyObject *variable, Key *out)
{
    key_clear(out);
    if (ensure_globals() < 0) return -1;
    PyObject *state = VarAPI->get_attr(variable, CLPQ_KEY);   /* new */
    if (!state) return -1;
    if (state == Py_None) {
        Py_DECREF(state);
        return 0;
    }
    PyObject *order = state_field(state, offset_variable_order, str_variable_order);
    Py_DECREF(state);
    if (!order) return -1;
    if (order == Py_None) {
        Py_DECREF(order);
        return 0;
    }
    int r = order_value_key(order, out);
    Py_DECREF(order);
    return r;
}

/* A key handed in from Python (an element of keys_a). */
static int
key_from_python(PyObject *k, Key *out)
{
    key_clear(out);
    if (k == Py_None) return 0;
    if (PyTuple_CheckExact(k) && PyTuple_GET_SIZE(k) == 2
            && PyLong_CheckExact(PyTuple_GET_ITEM(k, 0))) {
        int overflow = 0;
        long kind = PyLong_AsLongAndOverflow(PyTuple_GET_ITEM(k, 0), &overflow);
        PyObject *v = PyTuple_GET_ITEM(k, 1);
        if (!overflow && kind == 0 && PyLong_CheckExact(v)) {
            unsigned long long id = PyLong_AsUnsignedLongLong(v);
            if (!PyErr_Occurred()) {
                out->id = (uint64_t)id;
                out->kind = 0;
                return 0;
            }
            PyErr_Clear();
        } else if (!overflow && kind == 1) {
            Py_INCREF(v);
            out->obj = v;
            out->kind = 1;
            return 0;
        }
    }
    Py_INCREF(k);
    out->obj = k;
    out->kind = 2;
    return 0;
}

/* The key as the Python object order_key would give (new ref). */
static PyObject *
key_as_python(const Key *k)
{
    if (k->kind == 2) {
        Py_INCREF(k->obj);
        return k->obj;
    }
    if (k->kind == 0) {
        PyObject *id = PyLong_FromUnsignedLongLong((unsigned long long)k->id);
        if (!id) return NULL;
        PyObject *t = PyTuple_Pack(2, int_zero, id);
        Py_DECREF(id);
        return t;
    }
    return PyTuple_Pack(2, int_one, k->obj);
}

/* `a == b` (op Py_EQ) or `a < b` (op Py_LT) on two keys that are not
 * None, as Python evaluates it on order_key's tuples: 1, 0, or -1 on
 * error.  Where no Python code can run (each key unbound, or bound to an
 * exact int) the answer is computed here; otherwise on the tuples. */
static int
key_test(const Key *a, const Key *b, int op)
{
    if (a->kind != 2 && b->kind != 2) {
        if (a->kind != b->kind)
            return op == Py_EQ ? 0 : a->kind < b->kind;
        if (a->kind == 0)
            return op == Py_EQ ? a->id == b->id : a->id < b->id;
        if (PyLong_CheckExact(a->obj) && PyLong_CheckExact(b->obj))
            return PyObject_RichCompareBool(a->obj, b->obj, op);
    }
    PyObject *ta = key_as_python(a);
    if (!ta) return -1;
    PyObject *tb = key_as_python(b);
    if (!tb) { Py_DECREF(ta); return -1; }
    PyObject *r = PyObject_RichCompare(ta, tb, op);
    Py_DECREF(ta);
    Py_DECREF(tb);
    if (!r) return -1;
    int truth = PyObject_IsTrue(r);
    Py_DECREF(r);
    return truth;
}

/* ── rationals ────────────────────────────────────────────────────── */

#define SMALL_LIMIT ((long long)1 << 31)

/* The parts of a rational pair when both are exact ints below 2^31: 1,
 * else 0 (the Python arithmetic is called instead). */
static int
small_parts(PyObject *q, long long *n, long long *d)
{
    if (!PyTuple_CheckExact(q) || PyTuple_GET_SIZE(q) != 2) return 0;
    PyObject *a = PyTuple_GET_ITEM(q, 0), *b = PyTuple_GET_ITEM(q, 1);
    if (!PyLong_CheckExact(a) || !PyLong_CheckExact(b)) return 0;
    int overflow = 0;
    long long x = PyLong_AsLongLongAndOverflow(a, &overflow);
    if (overflow || (x == -1 && PyErr_Occurred())) { PyErr_Clear(); return 0; }
    long long y = PyLong_AsLongLongAndOverflow(b, &overflow);
    if (overflow || (y == -1 && PyErr_Occurred())) { PyErr_Clear(); return 0; }
    if (x <= -SMALL_LIMIT || x >= SMALL_LIMIT || y <= -SMALL_LIMIT
            || y >= SMALL_LIMIT)
        return 0;
    *n = x;
    *d = y;
    return 1;
}

static long long
gcd_ll(long long a, long long b)
{
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    while (b) {
        long long t = a % b;
        a = b;
        b = t;
    }
    return a;
}

/* arithmetic.make_rational on machine integers (|n|, |d| < 2^63, d != 0). */
static PyObject *
make_small(long long n, long long d)
{
    if (d < 0) {
        n = -n;
        d = -d;
    }
    long long g = gcd_ll(n, d);
    if (g > 1) {
        n /= g;
        d /= g;
    }
    PyObject *pn = PyLong_FromLongLong(n);
    if (!pn) return NULL;
    PyObject *pd = PyLong_FromLongLong(d);
    if (!pd) { Py_DECREF(pn); return NULL; }
    PyObject *r = PyTuple_Pack(2, pn, pd);
    Py_DECREF(pn);
    Py_DECREF(pd);
    return r;
}

/* arithmetic.multiply(x, y) */
static PyObject *
q_multiply(PyObject *x, PyObject *y)
{
    long long xn, xd, yn, yd;
    if (small_parts(x, &xn, &xd) && small_parts(y, &yn, &yd)
            && xd != 0 && yd != 0)
        return make_small(xn * yn, xd * yd);
    if (ensure_globals() < 0) return NULL;
    return PyObject_CallFunctionObjArgs(py_multiply, x, y, NULL);
}

/* arithmetic.add(x, y) */
static PyObject *
q_add(PyObject *x, PyObject *y)
{
    long long xn, xd, yn, yd;
    if (small_parts(x, &xn, &xd) && small_parts(y, &yn, &yd)
            && xd != 0 && yd != 0)
        return make_small(xn * yd + yn * xd, xd * yd);
    if (ensure_globals() < 0) return NULL;
    return PyObject_CallFunctionObjArgs(py_add, x, y, NULL);
}

/* arithmetic.is_zero(x): `x[0] == 0`.  1, 0, or -1 on error. */
static int
q_is_zero(PyObject *x)
{
    PyObject *n = subscript(x, 0);
    if (!n) return -1;
    int r;
    if (PyLong_CheckExact(n)) {
        r = PyObject_RichCompareBool(n, int_zero, Py_EQ);
    } else {
        PyObject *c = PyObject_RichCompare(n, int_zero, Py_EQ);
        r = c ? PyObject_IsTrue(c) : -1;
        Py_XDECREF(c);
    }
    Py_DECREF(n);
    return r;
}

/* multiply(x, factor) is equal to x itself: factor is exactly (1, 1)
 * and x a normalised pair of small exact ints (no Python code runs in
 * either multiply). */
static int
times_one_is_itself(PyObject *x, PyObject *factor)
{
    long long n, d, fn, fd;
    return small_parts(factor, &fn, &fd) && fn == 1 && fd == 1
        && small_parts(x, &n, &d) && d > 0 && gcd_ll(n, d) == 1;
}

/* (variable, coefficient) pair (new ref), stealing the coefficient. */
static PyObject *
pair_stealing(PyObject *variable, PyObject *coefficient)
{
    if (!coefficient) return NULL;
    PyObject *t = PyTuple_Pack(2, variable, coefficient);
    Py_DECREF(coefficient);
    return t;
}

static int
append_stealing(PyObject *list, PyObject *item)
{
    if (!item) return -1;
    int r = PyList_Append(list, item);
    Py_DECREF(item);
    return r;
}

/* ── add_homogeneous_parts_first_scaled ───────────────────────────── */

/* order_key(terms[j][0]) into *key. */
static int
key_of_term(PyObject *terms, Py_ssize_t j, Key *key)
{
    PyObject *term = list_item(terms, j);
    if (!term) return -1;
    PyObject *variable = subscript(term, 0);
    Py_DECREF(term);
    if (!variable) return -1;
    int r = order_key(variable, key);
    Py_DECREF(variable);
    return r;
}

/* (terms_a[i][0], multiply(terms_a[i][1], factor_a)) (new ref). */
static PyObject *
scaled_term(PyObject *terms_a, Py_ssize_t i, PyObject *factor_a)
{
    PyObject *term = list_item(terms_a, i);
    if (!term) return NULL;
    PyObject *variable = subscript(term, 0);
    if (!variable) { Py_DECREF(term); return NULL; }
    PyObject *coefficient = subscript(term, 1);
    if (!coefficient) { Py_DECREF(term); Py_DECREF(variable); return NULL; }
    if (PyTuple_CheckExact(term) && PyTuple_GET_SIZE(term) == 2
            && times_one_is_itself(coefficient, factor_a)) {
        /* (term[0], multiply(term[1], ONE)) is equal to term */
        Py_DECREF(coefficient);
        Py_DECREF(variable);
        return term;
    }
    Py_DECREF(term);
    PyObject *scaled = q_multiply(coefficient, factor_a);
    Py_DECREF(coefficient);
    PyObject *pair = pair_stealing(variable, scaled);
    Py_DECREF(variable);
    return pair;
}

/* linear_forms.add_homogeneous_parts_first_scaled, line for line. */
static PyObject *
merge_impl(PyObject *terms_a, PyObject *factor_a, PyObject *terms_b,
           PyObject *keys_a)
{
    int empty = PyObject_Not(terms_a);                 /* if not terms_a */
    if (empty < 0) return NULL;
    if (empty) {
        Py_INCREF(terms_b);
        return terms_b;
    }
    PyObject *result = NULL;
    Key key_a = KEY_INIT, key_b = KEY_INIT;
    Key *own_keys = NULL;          /* keys_a = order_keys(terms_a), held here */
    Py_ssize_t own_count = 0;
    Py_INCREF(terms_a);
    Py_INCREF(terms_b);
    Py_INCREF(factor_a);
    Py_INCREF(keys_a);
    if (keys_a == Py_None) {
        Py_ssize_t capacity = PyList_GET_SIZE(terms_a);
        own_keys = PyMem_Calloc((size_t)(capacity ? capacity : 1), sizeof(Key));
        if (!own_keys) { PyErr_NoMemory(); goto fail; }
        /* [order_key(variable) for variable, _ in terms_a] */
        for (Py_ssize_t x = 0; x < PyList_GET_SIZE(terms_a); x++) {
            if (own_count == capacity) {
                Key *grown = PyMem_Realloc(own_keys, (size_t)(2 * capacity + 1) * sizeof(Key));
                if (!grown) { PyErr_NoMemory(); goto fail; }
                own_keys = grown;
                capacity = 2 * capacity + 1;
            }
            PyObject *term = list_item(terms_a, x), *v, *c;
            if (!term) goto fail;
            int u = unpack2(term, &v, &c);
            Py_DECREF(term);
            if (u < 0) goto fail;
            Py_DECREF(c);
            Key k = KEY_INIT;
            int r = order_key(v, &k);
            Py_DECREF(v);
            own_keys[own_count++] = k;
            if (r < 0) goto fail;
        }
    }
    result = PyList_New(0);
    if (!result) goto fail;
    Py_ssize_t length_a = PySequence_Size(terms_a);
    if (length_a < 0) goto fail;
    Py_ssize_t length_b = PySequence_Size(terms_b);
    if (length_b < 0) goto fail;
    Py_ssize_t i = 0, j = 0;
    if (length_b) {
        if (key_of_term(terms_b, 0, &key_b) < 0) goto fail;
    }
    while (i < length_a && j < length_b) {
        const Key *ka;                                 /* key_a = keys_a[i] */
        if (own_keys) {
            if (i >= own_count) {
                PyErr_SetString(PyExc_IndexError, "list index out of range");
                goto fail;
            }
            ka = &own_keys[i];
        } else {
            PyObject *k = list_item(keys_a, i);
            if (!k) goto fail;
            int r = key_from_python(k, &key_a);
            Py_DECREF(k);
            if (r < 0) goto fail;
            ka = &key_a;
        }
        if (ka->kind < 0 || key_b.kind < 0) {
            Py_CLEAR(result);
            Py_INCREF(Py_None);
            result = Py_None;
            goto done;
        }
        int eq = key_test(ka, &key_b, Py_EQ);
        if (eq < 0) goto fail;
        if (eq) {
            /* coefficient = add(multiply(terms_a[i][1], factor_a), terms_b[j][1]) */
            PyObject *term_a = list_item(terms_a, i);
            if (!term_a) goto fail;
            PyObject *ca = subscript(term_a, 1);
            Py_DECREF(term_a);
            if (!ca) goto fail;
            PyObject *scaled;
            if (times_one_is_itself(ca, factor_a)) {
                scaled = ca;                       /* equal to the product */
            } else {
                scaled = q_multiply(ca, factor_a);
                Py_DECREF(ca);
            }
            if (!scaled) goto fail;
            PyObject *term_b = list_item(terms_b, j);
            if (!term_b) { Py_DECREF(scaled); goto fail; }
            PyObject *cb = subscript(term_b, 1);
            Py_DECREF(term_b);
            if (!cb) { Py_DECREF(scaled); goto fail; }
            PyObject *coefficient = q_add(scaled, cb);
            Py_DECREF(scaled);
            Py_DECREF(cb);
            if (!coefficient) goto fail;
            int z = q_is_zero(coefficient);
            if (z < 0) { Py_DECREF(coefficient); goto fail; }
            if (!z) {                      /* append((terms_a[i][0], coefficient)) */
                term_a = list_item(terms_a, i);
                if (!term_a) { Py_DECREF(coefficient); goto fail; }
                PyObject *va = subscript(term_a, 0);
                Py_DECREF(term_a);
                if (!va) { Py_DECREF(coefficient); goto fail; }
                PyObject *pair = pair_stealing(va, coefficient);
                Py_DECREF(va);
                if (append_stealing(result, pair) < 0) goto fail;
            } else {
                Py_DECREF(coefficient);
            }
            i++;
            j++;
            if (j < length_b) {
                if (key_of_term(terms_b, j, &key_b) < 0) goto fail;
            }
            continue;
        }
        int lt = key_test(ka, &key_b, Py_LT);
        if (lt < 0) goto fail;
        if (lt) {
            if (append_stealing(result, scaled_term(terms_a, i, factor_a)) < 0)
                goto fail;
            i++;
        } else {
            if (append_stealing(result, list_item(terms_b, j)) < 0) goto fail;
            j++;
            if (j < length_b) {
                if (key_of_term(terms_b, j, &key_b) < 0) goto fail;
            }
        }
    }
    while (i < length_a) {                             /* mult_hom on the rest of A */
        if (append_stealing(result, scaled_term(terms_a, i, factor_a)) < 0) goto fail;
        i++;
    }
    if (j < length_b) {                                /* result.extend(terms_b[j:]) */
        PyObject *rest = PySequence_GetSlice(terms_b, j, PY_SSIZE_T_MAX);
        if (!rest) goto fail;
        int extended = PyList_Extend(result, rest);
        Py_DECREF(rest);
        if (extended < 0) goto fail;
    }
    goto done;
fail:
    Py_CLEAR(result);
done:
    Py_DECREF(keys_a);
    if (own_keys) {
        for (Py_ssize_t x = 0; x < own_count; x++) key_clear(&own_keys[x]);
        PyMem_Free(own_keys);
    }
    key_clear(&key_a);
    key_clear(&key_b);
    Py_DECREF(terms_a);
    Py_DECREF(terms_b);
    Py_DECREF(factor_a);
    return result;
}

static PyObject *
merge_first_scaled(PyObject *self, PyObject *args)
{
    PyObject *terms_a, *factor_a, *terms_b, *keys_a = Py_None;
    (void)self;
    if (!PyArg_ParseTuple(args, "O!OO!|O", &PyList_Type, &terms_a, &factor_a,
                          &PyList_Type, &terms_b, &keys_a))
        return NULL;
    return merge_impl(terms_a, factor_a, terms_b, keys_a);
}

/* ── normal_form_coefficient_homogeneous ──────────────────────────── */

static PyObject *
coefficient_homogeneous(PyObject *self, PyObject *args)
{
    PyObject *terms, *order;
    (void)self;
    if (!PyArg_ParseTuple(args, "O!O", &PyList_Type, &terms, &order))
        return NULL;
    Key sought = KEY_INIT, key = KEY_INIT;
    PyObject *answer = NULL;
    Py_INCREF(terms);
    Py_INCREF(order);
    if (order_value_key(order, &sought) < 0) goto done;
    /* for variable, coefficient in terms: (the list as it is at each step) */
    for (Py_ssize_t i = 0; i < PyList_GET_SIZE(terms); i++) {
        PyObject *term = list_item(terms, i), *v, *c;
        if (!term) goto done;
        int u = unpack2(term, &v, &c);
        Py_DECREF(term);
        if (u < 0) goto done;
        int r = order_key(v, &key);
        Py_DECREF(v);
        if (r < 0) { Py_DECREF(c); goto done; }
        if (key.kind < 0) { Py_DECREF(c); break; }      /* return None */
        int eq = key_test(&key, &sought, Py_EQ);
        if (eq < 0) { Py_DECREF(c); goto done; }
        if (eq) { answer = c; goto done; }
        Py_DECREF(c);
        int lt = key_test(&sought, &key, Py_LT);
        if (lt < 0) goto done;
        if (lt) break;                                    /* return None */
    }
    Py_INCREF(Py_None);
    answer = Py_None;
done:
    key_clear(&key);
    key_clear(&sought);
    Py_DECREF(terms);
    Py_DECREF(order);
    return answer;
}

/* ── delete_factor_hom/4's scan ───────────────────────────────────── */

/* `term[0] is variable or deref(term[0]) is variable` for terms[i]:
 * 1, 0, or -1 on error. */
static int
term_holds(PyObject *terms, Py_ssize_t i, PyObject *variable)
{
    PyObject *term = list_item(terms, i);
    if (!term) return -1;
    PyObject *v = subscript(term, 0);
    if (!v) { Py_DECREF(term); return -1; }
    int r = v == variable;
    Py_DECREF(v);
    if (!r) {
        v = subscript(term, 0);
        if (!v) { Py_DECREF(term); return -1; }
        r = VarAPI->deref(v) == variable;
        Py_DECREF(v);
    }
    Py_DECREF(term);
    return r;
}

/* find_term(variable, terms, start=0): the first i >= start whose term
 * holds *variable* (dereferenced by the caller), else -1; the scan of
 * delete_factor_homogeneous and _delete_factor_from_tail. */
static PyObject *
find_term(PyObject *self, PyObject *args)
{
    PyObject *variable, *terms;
    Py_ssize_t start = 0;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO!|n", &variable, &PyList_Type, &terms, &start))
        return NULL;
    Py_INCREF(terms);
    PyObject *answer = NULL;
    for (Py_ssize_t i = start < 0 ? 0 : start; i < PyList_GET_SIZE(terms); i++) {
        int r = term_holds(terms, i, variable);
        if (r < 0) goto done;
        if (r) { answer = PyLong_FromSsize_t(i); goto done; }
    }
    answer = PyLong_FromLong(-1);
done:
    Py_DECREF(terms);
    return answer;
}

/* ── normal_form_substitute ───────────────────────────────────────── */

/* Set by _setup from linear_forms.py. */
static PyObject *LinearForm_type = NULL;
static PyObject *SharedTail_type = NULL;
static PyObject *row_variable_ids_fn = NULL;
static PyObject *with_constant_fn = NULL;
static PyObject *python_merge_fn = NULL;
static Py_ssize_t share_at = 8;

static PyObject *
setup(PyObject *self, PyObject *args)
{
    PyObject *lf, *st, *rv, *wc, *pm;
    Py_ssize_t share;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOOn", &lf, &st, &rv, &wc, &pm, &share))
        return NULL;
    Py_INCREF(lf); Py_XSETREF(LinearForm_type, lf);
    Py_INCREF(st); Py_XSETREF(SharedTail_type, st);
    Py_INCREF(rv); Py_XSETREF(row_variable_ids_fn, rv);
    Py_INCREF(wc); Py_XSETREF(with_constant_fn, wc);
    Py_INCREF(pm); Py_XSETREF(python_merge_fn, pm);
    share_at = share;
    Py_RETURN_NONE;
}

/* The form (new ref) *cls*(constant, rest, args...) of *form*. */
static PyObject *
new_form(PyObject *cls, PyObject *form, PyObject *third, PyObject *fourth)
{
    PyObject *constant = PyObject_GetAttr(form, str_constant);
    if (!constant) return NULL;
    PyObject *rest = PyObject_GetAttr(form, str_rest);
    if (!rest) { Py_DECREF(constant); return NULL; }
    PyObject *r = PyObject_CallFunctionObjArgs(cls, constant, rest, third,
                                               fourth, NULL);
    Py_DECREF(constant);
    Py_DECREF(rest);
    return r;
}

/* linear_forms.delete_factor (its index, _terms_from, the shared first
 * term, delete_factor_homogeneous, _delete_factor_from_tail): 1 with
 * *form_w* and *coefficient* (new refs), 0 where *variable* is not in the
 * row, -1 on error.  *variable* is dereferenced. */
static int
delete_factor_impl(PyObject *variable, PyObject *form, PyObject **form_w,
                   PyObject **coefficient, PyObject **w_base,
                   Py_ssize_t *w_start)
{
    *form_w = *coefficient = *w_base = NULL;
    *w_start = 0;
    PyObject *ids = PyObject_GetAttr(form, str_variable_ids);
    if (!ids) return -1;
    if (ids == Py_None) {
        Py_DECREF(ids);
        if (PyObject_SetAttr(form, str_variable_ids, Py_False) < 0) return -1;
    } else if (VarAPI->is_var(variable)) {
        if (ids == Py_False) {
            Py_DECREF(ids);
            ids = PyObject_CallOneArg(row_variable_ids_fn, form);
            if (!ids) return -1;
        }
        PyObject *key = PyLong_FromVoidPtr(variable);
        if (!key) { Py_DECREF(ids); return -1; }
        int in = PySequence_Contains(ids, key);
        Py_DECREF(key);
        Py_DECREF(ids);
        if (in < 0) return -1;
        if (!in) return 0;
    } else {
        Py_DECREF(ids);
    }
    /* base, start = _terms_from(form) */
    PyObject *base = NULL;
    Py_ssize_t start = 0;
    if ((PyObject *)Py_TYPE(form) == SharedTail_type) {
        base = PyObject_GetAttr(form, str_base);
        if (!base) return -1;
        if (base != Py_None) {
            PyObject *s = PyObject_GetAttr(form, str_start);
            if (!s) { Py_DECREF(base); return -1; }
            start = PyLong_AsSsize_t(s);
            Py_DECREF(s);
            if (start == -1 && PyErr_Occurred()) { Py_DECREF(base); return -1; }
        } else {
            Py_CLEAR(base);
        }
    }
    if (!base) {
        base = PyObject_GetAttr(form, str_terms);
        if (!base) return -1;
        start = 0;
    }
    if (!PyList_Check(base)) {
        PyErr_SetString(PyExc_TypeError, "a form's terms are a list");
        Py_DECREF(base);
        return -1;
    }
    int found = 0;
    if (start) {                                   /* _delete_factor_from_tail */
        Py_ssize_t length = PyList_GET_SIZE(base);
        for (Py_ssize_t i = start; i < length; i++) {
            int r = term_holds(base, i, variable);
            if (r < 0) goto fail;
            if (!r) continue;
            if (i == start && length - start > share_at) {
                PyObject *s = PyLong_FromSsize_t(start + 1);
                if (!s) goto fail;
                *form_w = new_form(SharedTail_type, form, base, s);
                Py_DECREF(s);
                Py_INCREF(base);
                *w_base = base;
                *w_start = start + 1;
            } else {
                PyObject *terms = PyList_GetSlice(base, start, i);
                PyObject *right = terms ? PyList_GetSlice(base, i + 1, length) : NULL;
                PyObject *joined = right ? PySequence_Concat(terms, right) : NULL;
                Py_XDECREF(terms);
                Py_XDECREF(right);
                if (!joined) goto fail;
                *form_w = new_form(LinearForm_type, form, joined, NULL);
                Py_DECREF(joined);
            }
            if (!*form_w) goto fail;
            PyObject *term = list_item(base, i);
            if (!term) goto fail;
            *coefficient = subscript(term, 1);
            Py_DECREF(term);
            if (!*coefficient) goto fail;
            found = 1;
            break;
        }
        Py_DECREF(base);
        return found;
    }
    Py_ssize_t length = PyList_GET_SIZE(base);
    if (length && length > share_at) {             /* delete_factor_hom/4, clause 1 */
        int r = term_holds(base, 0, variable);
        if (r < 0) goto fail;
        if (r) {
            *form_w = new_form(SharedTail_type, form, base, int_one);
            if (!*form_w) goto fail;
            Py_INCREF(base);
            *w_base = base;
            *w_start = 1;
            PyObject *term = list_item(base, 0);
            if (!term) goto fail;
            *coefficient = subscript(term, 1);
            Py_DECREF(term);
            if (!*coefficient) goto fail;
            Py_DECREF(base);
            return 1;
        }
    }
    /* delete_factor_homogeneous(variable, base) */
    for (Py_ssize_t i = 0; i < PyList_GET_SIZE(base); i++) {
        int r = term_holds(base, i, variable);
        if (r < 0) goto fail;
        if (!r) continue;
        Py_ssize_t n = PyList_GET_SIZE(base);
        PyObject *left = PyList_GetSlice(base, 0, i);
        PyObject *right = left ? PyList_GetSlice(base, i + 1, n) : NULL;
        PyObject *joined = right ? PySequence_Concat(left, right) : NULL;
        Py_XDECREF(left);
        Py_XDECREF(right);
        if (!joined) goto fail;
        PyObject *term = list_item(base, i);
        if (!term) { Py_DECREF(joined); goto fail; }
        *coefficient = subscript(term, 1);
        Py_DECREF(term);
        if (!*coefficient) { Py_DECREF(joined); goto fail; }
        *form_w = new_form(LinearForm_type, form, joined, NULL);
        Py_DECREF(joined);
        if (!*form_w) goto fail;
        found = 1;
        break;
    }
    Py_DECREF(base);
    return found;
fail:
    Py_CLEAR(*form_w);
    Py_CLEAR(*coefficient);
    Py_CLEAR(*w_base);
    Py_DECREF(base);
    return -1;
}

/* add(multiply(a.<name>, factor), b.<name>) (new ref) */
static PyObject *
scaled_sum(PyObject *a, PyObject *factor, PyObject *b, PyObject *name)
{
    PyObject *x = PyObject_GetAttr(a, name);
    if (!x) return NULL;
    PyObject *scaled = q_multiply(x, factor);
    Py_DECREF(x);
    if (!scaled) return NULL;
    PyObject *y = PyObject_GetAttr(b, name);
    if (!y) { Py_DECREF(scaled); return NULL; }
    PyObject *r = q_add(scaled, y);
    Py_DECREF(scaled);
    Py_DECREF(y);
    return r;
}

/* linear_forms.normal_form_substitute: delete_factor, then
 * add_linear_forms_first_scaled(form_variable, coefficient, form_w, keys). */
static PyObject *
substitute_impl(PyObject *variable, PyObject *form_variable, PyObject *form_x,
                PyObject *keys)
{
    if (!LinearForm_type) {
        PyErr_SetString(PyExc_RuntimeError, "_linear_forms_core._setup not run");
        return NULL;
    }
    PyObject *form_w, *coefficient, *w_base, *result = NULL;
    Py_ssize_t w_start;
    PyObject *constant = NULL, *rest = NULL, *terms_a = NULL, *terms_b = NULL;
    variable = VarAPI->deref(variable);
    Py_INCREF(variable);
    Py_INCREF(form_variable);
    Py_INCREF(form_x);
    int found = delete_factor_impl(variable, form_x, &form_w, &coefficient,
                                   &w_base, &w_start);
    if (found <= 0) {
        if (found == 0) { Py_INCREF(Py_None); result = Py_None; }
        goto out;
    }
    constant = scaled_sum(form_variable, coefficient, form_w, str_constant);
    if (!constant) goto done;
    rest = scaled_sum(form_variable, coefficient, form_w, str_rest);
    if (!rest) goto done;
    terms_a = PyObject_GetAttr(form_variable, str_terms);
    if (!terms_a) goto done;
    int empty = PyObject_Not(terms_a);
    if (empty < 0) goto done;
    if (empty) {                                   /* add_linear_f1h/4 */
        result = PyObject_CallFunctionObjArgs(with_constant_fn, form_w,
                                              constant, rest, NULL);
        goto done;
    }
    /* form_w.terms: a shared tail's is base[start:], which its property
     * builds; built here the same, without running the property. */
    terms_b = w_base ? PyList_GetSlice(w_base, w_start, PY_SSIZE_T_MAX)
                     : PyObject_GetAttr(form_w, str_terms);
    if (!terms_b) goto done;
    PyObject *terms;
    if (PyList_CheckExact(terms_a) && PyList_CheckExact(terms_b))
        terms = merge_impl(terms_a, coefficient, terms_b, keys);
    else
        terms = PyObject_CallFunctionObjArgs(python_merge_fn, terms_a,
                                             coefficient, terms_b, keys, NULL);
    if (!terms) goto done;
    if (terms == Py_None) {
        result = terms;
        goto done;
    }
    result = PyObject_CallFunctionObjArgs(LinearForm_type, constant, rest,
                                          terms, NULL);
    Py_DECREF(terms);
done:
    Py_DECREF(form_w);
    Py_DECREF(coefficient);
    Py_XDECREF(w_base);
    Py_XDECREF(constant);
    Py_XDECREF(rest);
    Py_XDECREF(terms_a);
    Py_XDECREF(terms_b);
out:
    Py_DECREF(variable);
    Py_DECREF(form_variable);
    Py_DECREF(form_x);
    return result;
}

static PyObject *
substitute(PyObject *self, PyObject *args)
{
    PyObject *variable, *form_variable, *form_x, *keys = Py_None;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOO|O", &variable, &form_variable, &form_x,
                          &keys))
        return NULL;
    return substitute_impl(variable, form_variable, form_x, keys);
}

/* ── list walks and row loops ─────────────────────────────────────── */

static PyObject *ListCell_type = NULL;

static PyObject *
setup_lists(PyObject *self, PyObject *args)
{
    PyObject *lc;
    (void)self;
    if (!PyArg_ParseTuple(args, "O", &lc)) return NULL;
    Py_INCREF(lc);
    Py_XSETREF(ListCell_type, lc);
    Py_RETURN_NONE;
}

/* node = deref(node.rest): replaces *node (owned). */
static int
next_node(PyObject **node)
{
    PyObject *rest = PyObject_GetAttr(*node, str_rest);
    if (!rest) return -1;
    PyObject *next = VarAPI->deref(rest);
    Py_INCREF(next);
    Py_DECREF(rest);
    Py_SETREF(*node, next);
    return 0;
}

/* components.list_elements */
static PyObject *
list_elements_impl(PyObject *items)
{
    if (!ListCell_type) {
        PyErr_SetString(PyExc_RuntimeError, "_linear_forms_core._setup_lists not run");
        return NULL;
    }
    PyObject *result = PyList_New(0);
    if (!result) return NULL;
    PyObject *node = VarAPI->deref(items);
    Py_INCREF(node);
    while ((PyObject *)Py_TYPE(node) == ListCell_type) {
        if (append_stealing(result, PyObject_GetAttr(node, str_head)) < 0) goto fail;
        if (next_node(&node) < 0) goto fail;
    }
    Py_DECREF(node);
    return result;
fail:
    Py_DECREF(node);
    Py_DECREF(result);
    return NULL;
}

static PyObject *
list_elements(PyObject *self, PyObject *items)
{
    (void)self;
    return list_elements_impl(items);
}

/* state_of(member) and, where it has one, its linear_form (new refs):
 * 1 with both, 0 where `state is None or state.linear_form is None`, -1
 * on error. */
static int
row_of(PyObject *member, PyObject **state, PyObject **form)
{
    *state = *form = NULL;
    if (ensure_globals() < 0) return -1;
    PyObject *st = VarAPI->get_attr(member, CLPQ_KEY);
    if (!st) return -1;
    if (st == Py_None) { Py_DECREF(st); return 0; }
    PyObject *f = state_field(st, offset_linear_form, str_linear_form);
    if (!f) { Py_DECREF(st); return -1; }
    if (f == Py_None) { Py_DECREF(f); Py_DECREF(st); return 0; }
    *state = st;
    *form = f;
    return 1;
}

/* bounded_simplex.back_substitute_variables's unmetered loop (and
 * back_substitute_collect_bindings's): for each member, in list order, as
 * the list is walked, whose row holds *variable*, write(member, state,
 * new row) before the next member is read. */
static PyObject *
substitute_rows(PyObject *self, PyObject *args)
{
    PyObject *members, *variable, *form, *keys, *write;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOO", &members, &variable, &form, &keys, &write))
        return NULL;
    if (!ListCell_type) {
        PyErr_SetString(PyExc_RuntimeError, "_linear_forms_core._setup_lists not run");
        return NULL;
    }
    Py_INCREF(variable);
    Py_INCREF(form);
    Py_INCREF(keys);
    PyObject *node = VarAPI->deref(members);
    Py_INCREF(node);
    int ok = 0;
    while ((PyObject *)Py_TYPE(node) == ListCell_type) {
        PyObject *head = PyObject_GetAttr(node, str_head);
        if (!head) goto done;
        PyObject *member = VarAPI->deref(head);
        Py_INCREF(member);
        Py_DECREF(head);
        if (next_node(&node) < 0) { Py_DECREF(member); goto done; }
        PyObject *state, *row;
        int has = row_of(member, &state, &row);
        if (has <= 0) {
            Py_DECREF(member);
            if (has < 0) goto done;
            continue;
        }
        PyObject *new_row = substitute_impl(variable, form, row, keys);
        Py_DECREF(row);
        if (!new_row) { Py_DECREF(state); Py_DECREF(member); goto done; }
        if (new_row != Py_None) {
            PyObject *r = PyObject_CallFunctionObjArgs(write, member, state,
                                                       new_row, NULL);
            Py_XDECREF(r);
            if (!r) {
                Py_DECREF(new_row); Py_DECREF(state); Py_DECREF(member);
                goto done;
            }
        }
        Py_DECREF(new_row);
        Py_DECREF(state);
        Py_DECREF(member);
    }
    ok = 1;
done:
    Py_DECREF(node);
    Py_DECREF(variable);
    Py_DECREF(form);
    Py_DECREF(keys);
    if (!ok) return NULL;
    Py_RETURN_NONE;
}

/* id(obj) in stand_ins, read as stand_ins.get(id(obj)): the value
 * (borrowed) or NULL, with *error* set on an error. */
static PyObject *
stand_in_of(PyObject *stand_ins, PyObject *obj, int *error)
{
    *error = 0;
    PyObject *key = PyLong_FromVoidPtr(obj);
    if (!key) { *error = 1; return NULL; }
    PyObject *value = PyDict_GetItemWithError(stand_ins, key);
    Py_DECREF(key);
    if (!value && PyErr_Occurred()) *error = 1;
    return value;
}

/* attribute_hooks._rename_in_form (new ref): *form* itself where no
 * variable of it has a stand-in, else a LinearForm with them replaced. */
static PyObject *
rename_form_impl(PyObject *form, PyObject *stand_ins)
{
    PyObject *ids = PyObject_GetAttr(form, str_variable_ids);
    if (!ids) return NULL;
    int truthy = PyObject_IsTrue(ids);
    if (truthy < 0) { Py_DECREF(ids); return NULL; }
    if (truthy) {                  /* ids and stand_ins.keys().isdisjoint(ids) */
        PyObject *keys = PyDict_Keys(stand_ins);
        if (!keys) { Py_DECREF(ids); return NULL; }
        int disjoint = 1;
        for (Py_ssize_t k = 0; k < PyList_GET_SIZE(keys); k++) {
            int in = PySequence_Contains(ids, PyList_GET_ITEM(keys, k));
            if (in < 0) { Py_DECREF(keys); Py_DECREF(ids); return NULL; }
            if (in) { disjoint = 0; break; }
        }
        Py_DECREF(keys);
        if (disjoint) {
            Py_DECREF(ids);
            Py_INCREF(form);
            return form;
        }
    }
    Py_DECREF(ids);
    PyObject *terms = PyObject_GetAttr(form, str_terms);
    if (!terms) return NULL;
    PyObject *renamed = NULL, *result = NULL;
    Py_ssize_t n = PySequence_Size(terms);
    if (n < 0) goto done;
    /* stand_ins.keys().isdisjoint(map(id, map(_first, terms))) */
    int disjoint = 1;
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *term = PySequence_GetItem(terms, i);
        if (!term) goto done;
        PyObject *v = subscript(term, 0);
        Py_DECREF(term);
        if (!v) goto done;
        int error;
        PyObject *s = stand_in_of(stand_ins, v, &error);
        Py_DECREF(v);
        if (error) goto done;
        if (s) { disjoint = 0; break; }
    }
    if (disjoint) {
        Py_INCREF(form);
        result = form;
        goto done;
    }
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *term = PySequence_GetItem(terms, i);
        if (!term) goto done;
        PyObject *v = subscript(term, 0);
        if (!v) { Py_DECREF(term); goto done; }
        int error;
        PyObject *s = stand_in_of(stand_ins, v, &error);
        Py_DECREF(v);
        if (error) { Py_DECREF(term); goto done; }
        if (s == NULL || s == Py_None) { Py_DECREF(term); continue; }
        Py_INCREF(s);
        if (!renamed) {
            renamed = PySequence_List(terms);
            if (!renamed) { Py_DECREF(s); Py_DECREF(term); goto done; }
        }
        PyObject *c = subscript(term, 1);
        Py_DECREF(term);
        PyObject *pair = c ? PyTuple_Pack(2, s, c) : NULL;
        Py_DECREF(s);
        Py_XDECREF(c);
        if (!pair) goto done;
        if (PyList_SetItem(renamed, i, pair) < 0) goto done;   /* steals pair */
    }
    if (!renamed) {
        Py_INCREF(form);
        result = form;
        goto done;
    }
    result = new_form(LinearForm_type, form, renamed, NULL);
done:
    Py_XDECREF(renamed);
    Py_DECREF(terms);
    return result;
}

/* attribute_hooks._rename_in_component's row loop: over a snapshot of the
 * members (list_elements), write(member, state, renamed row) for each one
 * whose row changes, before the next is read. */
static PyObject *
rename_rows(PyObject *self, PyObject *args)
{
    PyObject *members, *stand_ins, *write;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO!O", &members, &PyDict_Type, &stand_ins, &write))
        return NULL;
    if (!LinearForm_type) {
        PyErr_SetString(PyExc_RuntimeError, "_linear_forms_core._setup not run");
        return NULL;
    }
    PyObject *elements = list_elements_impl(members);
    if (!elements) return NULL;
    Py_INCREF(stand_ins);
    int ok = 0;
    for (Py_ssize_t i = 0; i < PyList_GET_SIZE(elements); i++) {
        PyObject *member = VarAPI->deref(PyList_GET_ITEM(elements, i));
        Py_INCREF(member);
        if (!VarAPI->is_var(member)) { Py_DECREF(member); continue; }
        PyObject *state, *row;
        int has = row_of(member, &state, &row);
        if (has <= 0) {
            Py_DECREF(member);
            if (has < 0) goto done;
            continue;
        }
        PyObject *renamed = rename_form_impl(row, stand_ins);
        if (!renamed) { Py_DECREF(row); Py_DECREF(state); Py_DECREF(member); goto done; }
        if (renamed != row) {
            PyObject *r = PyObject_CallFunctionObjArgs(write, member, state,
                                                       renamed, NULL);
            Py_XDECREF(r);
            if (!r) {
                Py_DECREF(renamed); Py_DECREF(row); Py_DECREF(state);
                Py_DECREF(member);
                goto done;
            }
        }
        Py_DECREF(renamed);
        Py_DECREF(row);
        Py_DECREF(state);
        Py_DECREF(member);
    }
    ok = 1;
done:
    Py_DECREF(elements);
    Py_DECREF(stand_ins);
    if (!ok) return NULL;
    Py_RETURN_NONE;
}

/* attribute_hooks._rename_in_list's question: does any element (as it
 * is, not dereferenced) have a stand-in, read as stand_ins.get(id(e)) is
 * not None? */
static PyObject *
list_has_stand_in(PyObject *self, PyObject *args)
{
    PyObject *items, *stand_ins;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO!", &items, &PyDict_Type, &stand_ins))
        return NULL;
    PyObject *elements = list_elements_impl(items);
    if (!elements) return NULL;
    for (Py_ssize_t i = 0; i < PyList_GET_SIZE(elements); i++) {
        int error;
        PyObject *s = stand_in_of(stand_ins, PyList_GET_ITEM(elements, i), &error);
        if (error) { Py_DECREF(elements); return NULL; }
        if (s && s != Py_None) { Py_DECREF(elements); Py_RETURN_TRUE; }
    }
    Py_DECREF(elements);
    Py_RETURN_FALSE;
}

/* ── arithmetic.add and arithmetic.multiply ──────────────────────── */

static PyObject *
py_q_add(PyObject *self, PyObject *const *args, Py_ssize_t nargs)
{
    (void)self;
    if (nargs != 2) {
        PyErr_SetString(PyExc_TypeError, "add takes two rationals");
        return NULL;
    }
    return q_add(args[0], args[1]);
}

static PyObject *
py_q_multiply(PyObject *self, PyObject *const *args, Py_ssize_t nargs)
{
    (void)self;
    if (nargs != 2) {
        PyErr_SetString(PyExc_TypeError, "multiply takes two rationals");
        return NULL;
    }
    return q_multiply(args[0], args[1]);
}

/* ── module ───────────────────────────────────────────────────────── */

static PyMethodDef methods[] = {
    {"add_homogeneous_parts_first_scaled", merge_first_scaled, METH_VARARGS,
     "linear_forms.add_homogeneous_parts_first_scaled in C."},
    {"normal_form_coefficient_homogeneous", coefficient_homogeneous,
     METH_VARARGS, "linear_forms.normal_form_coefficient_homogeneous in C."},
    {"normal_form_substitute", substitute, METH_VARARGS,
     "linear_forms.normal_form_substitute in C."},
    {"find_term", find_term, METH_VARARGS,
     "The scan of linear_forms.delete_factor_homogeneous in C."},
    {"list_elements", list_elements, METH_O, "components.list_elements in C."},
    {"substitute_rows", substitute_rows, METH_VARARGS,
     "The unmetered row loop of bounded_simplex.back_substitute_variables in C."},
    {"rename_rows", rename_rows, METH_VARARGS,
     "The row loop of attribute_hooks._rename_in_component in C."},
    {"list_has_stand_in", list_has_stand_in, METH_VARARGS,
     "Whether attribute_hooks._rename_in_list changes a list."},
    {"add", (PyCFunction)(void (*)(void))py_q_add, METH_FASTCALL,
     "arithmetic.add in C."},
    {"multiply", (PyCFunction)(void (*)(void))py_q_multiply, METH_FASTCALL,
     "arithmetic.multiply in C."},
    {"_setup", setup, METH_VARARGS, "The linear_forms classes and helpers."},
    {"_setup_lists", setup_lists, METH_VARARGS, "components.ListCell."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_linear_forms_core",
    "C twins of the hot loops of the clp(q,r) 1.3.3 port (DEVIATIONS.md D24).\n",
    -1,
    methods,
    NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC
PyInit__linear_forms_core(void)
{
    if (import_variables_capi() < 0) return NULL;
#define INTERN(var, text) \
    if (!((var) = PyUnicode_InternFromString(text))) return NULL;
    INTERN(str_variable_order, "variable_order")
    INTERN(str_id, "_id")
    INTERN(str_variable_ids, "variable_ids")
    INTERN(str_base, "base")
    INTERN(str_start, "start")
    INTERN(str_terms, "terms")
    INTERN(str_constant, "constant")
    INTERN(str_rest, "rest")
    INTERN(str_head, "head")
    INTERN(str_linear_form, "linear_form")
#undef INTERN
    int_zero = PyLong_FromLong(0);
    int_one = PyLong_FromLong(1);
    if (!int_zero || !int_one) return NULL;
    PyObject *m = PyModule_Create(&moduledef);
#ifdef Py_GIL_DISABLED
    if (m) PyUnstable_Module_SetGIL(m, Py_MOD_GIL_USED);
#endif
    return m;
}
