/* Prototype: marshal functor-first Clausal term-tuples straight into Z3_mk_*.
 *
 * Term shape (exactly Clausal's runtime form):
 *     ('+', L, R)  ('-', L, R)  ('*', L, R)
 *     ('=', L, R)  ('<', L, R)  ('=<', L, R)  ('>', L, R)  ('>=', L, R)
 *     ('v', i)     -- logic variable, index into a pre-declared var array
 *     python int   -- integer literal
 *
 * Dispatch is a POINTER COMPARE on the interned functor string, which is the
 * whole reason the tuple representation makes this cheap: no attribute
 * lookup, no dict, no per-node Python object.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <z3.h>

static Z3_context CTX;
static Z3_sort    INT_SORT;
static Z3_ast    *VARS;
static Py_ssize_t NVARS;

/* interned functor pointers, filled at init */
static PyObject *F_ADD, *F_SUB, *F_MUL, *F_EQ, *F_LT, *F_LE, *F_GT, *F_GE, *F_VAR;

static Z3_ast marshal(PyObject *t)
{
    /* integer literal */
    if (PyLong_CheckExact(t)) {
        long v = PyLong_AsLong(t);
        if (v == -1 && PyErr_Occurred()) return NULL;
        return Z3_mk_int(CTX, (int)v, INT_SORT);
    }
    if (!PyTuple_CheckExact(t) || PyTuple_GET_SIZE(t) < 1) {
        PyErr_SetString(PyExc_TypeError, "not a term tuple");
        return NULL;
    }
    PyObject *f = PyTuple_GET_ITEM(t, 0);          /* functor, interned */

    /* Fast path is a POINTER compare, valid only when the functor came from
     * the atom table (Clausal's mint() interns).  A non-interned equal string
     * must still work, so re-intern it once and retry -- correctness first,
     * and the cost lands only on terms that did not come from the atom table. */
    if (f != F_ADD && f != F_SUB && f != F_MUL && f != F_EQ && f != F_LT
        && f != F_LE && f != F_GT && f != F_GE && f != F_VAR) {
        if (!PyUnicode_CheckExact(f)) {
            PyErr_Format(PyExc_TypeError, "functor not a string: %R", f);
            return NULL;
        }
        Py_INCREF(f);
        PyUnicode_InternInPlace(&f);
        Py_DECREF(f);
    }

    if (f == F_VAR) {                               /* ('v', i) */
        Py_ssize_t i = PyLong_AsSsize_t(PyTuple_GET_ITEM(t, 1));
        if (i < 0 || i >= NVARS) {
            PyErr_SetString(PyExc_IndexError, "var index out of range");
            return NULL;
        }
        return VARS[i];
    }

    Z3_ast l = marshal(PyTuple_GET_ITEM(t, 1));
    if (!l) return NULL;
    Z3_ast r = marshal(PyTuple_GET_ITEM(t, 2));
    if (!r) return NULL;

    if (f == F_ADD) { Z3_ast a[2] = {l, r}; return Z3_mk_add(CTX, 2, a); }
    if (f == F_SUB) { Z3_ast a[2] = {l, r}; return Z3_mk_sub(CTX, 2, a); }
    if (f == F_MUL) { Z3_ast a[2] = {l, r}; return Z3_mk_mul(CTX, 2, a); }
    if (f == F_EQ)  return Z3_mk_eq(CTX, l, r);
    if (f == F_LT)  return Z3_mk_lt(CTX, l, r);
    if (f == F_LE)  return Z3_mk_le(CTX, l, r);
    if (f == F_GT)  return Z3_mk_gt(CTX, l, r);
    if (f == F_GE)  return Z3_mk_ge(CTX, l, r);

    PyErr_Format(PyExc_ValueError, "unknown functor %R", f);
    return NULL;
}

static PyObject *py_init(PyObject *self, PyObject *args)
{
    Py_ssize_t nvars;
    if (!PyArg_ParseTuple(args, "n", &nvars)) return NULL;
    Z3_config cfg = Z3_mk_config();
    CTX = Z3_mk_context(cfg);
    Z3_del_config(cfg);
    INT_SORT = Z3_mk_int_sort(CTX);
    NVARS = nvars;
    VARS = PyMem_Malloc(sizeof(Z3_ast) * (size_t)nvars);
    for (Py_ssize_t i = 0; i < nvars; i++) {
        char buf[32]; snprintf(buf, sizeof buf, "x%zd", i);
        VARS[i] = Z3_mk_const(CTX, Z3_mk_string_symbol(CTX, buf), INT_SORT);
    }
    Py_RETURN_NONE;
}

/* Marshal a LIST of constraint terms; returns how many nodes were built. */
static PyObject *py_marshal_all(PyObject *self, PyObject *arg)
{
    if (!PyList_CheckExact(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected a list");
        return NULL;
    }
    Py_ssize_t n = PyList_GET_SIZE(arg);
    for (Py_ssize_t i = 0; i < n; i++) {
        if (!marshal(PyList_GET_ITEM(arg, i))) return NULL;
    }
    return PyLong_FromSsize_t(n);
}

/* POSITIVE CONTROL: marshal one term and hand back what Z3 actually built. */
static PyObject *py_marshal_str(PyObject *self, PyObject *arg)
{
    Z3_ast a = marshal(arg);
    if (!a) return NULL;
    return PyUnicode_FromString(Z3_ast_to_string(CTX, a));
}

static PyMethodDef M[] = {
    {"marshal_str", py_marshal_str, METH_O,       "marshal one term -> Z3's own string"},
    {"init",        py_init,        METH_VARARGS, "create ctx + n int consts"},
    {"marshal_all", py_marshal_all, METH_O,       "marshal a list of terms"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef mod = {PyModuleDef_HEAD_INIT, "_z3bridge", NULL, -1, M};

PyMODINIT_FUNC PyInit__z3bridge(void)
{
    F_ADD = PyUnicode_InternFromString("+");
    F_SUB = PyUnicode_InternFromString("-");
    F_MUL = PyUnicode_InternFromString("*");
    F_EQ  = PyUnicode_InternFromString("=");
    F_LT  = PyUnicode_InternFromString("<");
    F_LE  = PyUnicode_InternFromString("=<");
    F_GT  = PyUnicode_InternFromString(">");
    F_GE  = PyUnicode_InternFromString(">=");
    F_VAR = PyUnicode_InternFromString("v");
    return PyModule_Create(&mod);
}
