/*
 * _trampoline — C-accelerated StepGenerator and trampoline for clausal.
 *
 * StepGenerator wraps a Python generator function, passing itself as the
 * ``this_generator`` parameter so the generator body can refer to its own
 * wrapper without a bootstrap ``self = yield`` round-trip.
 *
 * The trampoline drives a chain of StepGenerators via plain tuples
 * ``(target, value)`` — no dataclass Step, no ``started`` set, just a tight
 * C while loop.
 *
 * DONE is a singleton sentinel yielded as ``(parent, DONE)`` to signal
 * search exhaustion.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* ── DONE sentinel ──────────────────────────────────────────────────────── */

static PyObject *g_DONE = NULL;   /* module-level singleton */


/* ── StepGenerator type ─────────────────────────────────────────────────── */

typedef struct {
    PyObject_HEAD
    PyObject *gen;          /* inner Python generator */
    int       started;      /* 0 = first send does next(); 1 = delegates */
} StepGenObject;

static PyTypeObject StepGenType;   /* forward decl */

#define StepGen_Check(op)   PyObject_TypeCheck((op), &StepGenType)
#define StepGen_CAST(op)    ((StepGenObject *)(op))


/* ── StepGenerator.__init__(func, *args) ─────────────────────────────────
 *
 * Calls func(self, *args) and stores the resulting generator.
 */
static int
StepGen_init(StepGenObject *self, PyObject *args, PyObject *kwds)
{
    Py_ssize_t nargs = PyTuple_GET_SIZE(args);
    if (nargs < 1) {
        PyErr_SetString(PyExc_TypeError,
                        "StepGenerator requires at least one argument (func)");
        return -1;
    }

    PyObject *func = PyTuple_GET_ITEM(args, 0);

    /* Build (self, *remaining_args) tuple for func(self, ...) */
    Py_ssize_t n_remaining = nargs - 1;
    PyObject *call_args = PyTuple_New(n_remaining + 1);
    if (!call_args) return -1;

    Py_INCREF((PyObject *)self);
    PyTuple_SET_ITEM(call_args, 0, (PyObject *)self);

    for (Py_ssize_t i = 0; i < n_remaining; i++) {
        PyObject *a = PyTuple_GET_ITEM(args, i + 1);
        Py_INCREF(a);
        PyTuple_SET_ITEM(call_args, i + 1, a);
    }

    PyObject *gen = PyObject_Call(func, call_args, kwds);
    Py_DECREF(call_args);
    if (!gen) return -1;

    Py_XDECREF(self->gen);
    self->gen = gen;
    self->started = 0;
    return 0;
}

static void
StepGen_dealloc(StepGenObject *self)
{
    PyObject_GC_UnTrack(self);
    Py_XDECREF(self->gen);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
StepGen_traverse(StepGenObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->gen);
    return 0;
}

static int
StepGen_clear(StepGenObject *self)
{
    Py_CLEAR(self->gen);
    return 0;
}


/* ── StepGenerator.send(value) ───────────────────────────────────────────
 *
 * First call: next(inner_gen)  — starts execution to first yield.
 * Subsequent: inner_gen.send(value).
 *
 * Returns the yielded tuple (target, value).
 */
static PyObject *
StepGen_send(StepGenObject *self, PyObject *value)
{
    if (!self->gen) {
        PyErr_SetString(PyExc_RuntimeError,
                        "StepGenerator has no inner generator");
        return NULL;
    }

    PyObject *send_val;
    if (self->started) {
        send_val = value;
    } else {
        self->started = 1;
        send_val = Py_None;  /* first call: equivalent to next(gen) */
    }

    PyObject *result;
    PySendResult sr = PyIter_Send(self->gen, send_val, &result);

    if (sr == PYGEN_NEXT) {
        return result;   /* yielded value — a (target, value) tuple */
    }

    if (sr == PYGEN_RETURN) {
        /* Generator returned normally — protocol error */
        Py_XDECREF(result);
        PyErr_SetString(PyExc_RuntimeError,
                        "StepGenerator inner generator returned "
                        "unexpectedly (no final yield)");
        return NULL;
    }

    /* PYGEN_ERROR — exception already set */
    return NULL;
}


/* ── StepGenerator.throw(*args) ──────────────────────────────────────── */

static PyObject *
StepGen_throw(StepGenObject *self, PyObject *args)
{
    if (!self->gen) {
        PyErr_SetString(PyExc_RuntimeError,
                        "StepGenerator has no inner generator");
        return NULL;
    }
    PyObject *meth = PyObject_GetAttrString(self->gen, "throw");
    if (!meth) return NULL;
    PyObject *result = PyObject_Call(meth, args, NULL);
    Py_DECREF(meth);
    return result;
}


/* ── StepGenerator.close() ───────────────────────────────────────────── */

static PyObject *
StepGen_close(StepGenObject *self, PyObject *Py_UNUSED(ignored))
{
    if (self->gen) {
        PyObject *meth = PyObject_GetAttrString(self->gen, "close");
        if (!meth) return NULL;
        PyObject *result = PyObject_CallNoArgs(meth);
        Py_DECREF(meth);
        if (!result) return NULL;
        Py_DECREF(result);
    }
    Py_RETURN_NONE;
}


/* ── StepGenerator methods table ─────────────────────────────────────── */

static PyMethodDef StepGen_methods[] = {
    {"send",  (PyCFunction)StepGen_send,  METH_O,       "send(value) → tuple"},
    {"throw", (PyCFunction)StepGen_throw, METH_VARARGS, "throw(*args)"},
    {"close", (PyCFunction)StepGen_close, METH_NOARGS,  "close()"},
    {NULL}
};


/* ── StepGenerator type object ───────────────────────────────────────── */

static PyTypeObject StepGenType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name      = "_trampoline.StepGenerator",
    .tp_doc       = "Wraps a generator function, injecting this_generator as first arg.",
    .tp_basicsize = sizeof(StepGenObject),
    .tp_flags     = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_new       = PyType_GenericNew,
    .tp_init      = (initproc)StepGen_init,
    .tp_dealloc   = (destructor)StepGen_dealloc,
    .tp_traverse  = (traverseproc)StepGen_traverse,
    .tp_clear     = (inquiry)StepGen_clear,
    .tp_methods   = StepGen_methods,
};


/* ── trampoline(root_step_gen) ───────────────────────────────────────────
 *
 * Tight C loop driving the tuple-based step protocol.
 *
 *   step = root.send(None)
 *   while step[0] is not None:
 *       step = step[0].send(step[1])
 *   return step[1]
 */
static PyObject *
trampoline_func(PyObject *Py_UNUSED(module), PyObject *root)
{
    if (!StepGen_Check(root)) {
        PyErr_SetString(PyExc_TypeError,
                        "trampoline() argument must be a StepGenerator");
        return NULL;
    }

    /* step = root.send(None) */
    PyObject *step = StepGen_send(StepGen_CAST(root), Py_None);
    if (!step) return NULL;

    while (1) {
        /* Unpack tuple: (gen, value) */
        if (!PyTuple_CheckExact(step) || PyTuple_GET_SIZE(step) != 2) {
            PyErr_SetString(PyExc_TypeError,
                            "trampoline: generator must yield 2-tuples");
            Py_DECREF(step);
            return NULL;
        }

        PyObject *gen   = PyTuple_GET_ITEM(step, 0);  /* borrowed */
        PyObject *value = PyTuple_GET_ITEM(step, 1);  /* borrowed */

        if (gen == Py_None) {
            /* Root computation done */
            Py_INCREF(value);
            Py_DECREF(step);
            return value;
        }

        if (!StepGen_Check(gen)) {
            PyErr_Format(PyExc_TypeError,
                         "trampoline: step target must be StepGenerator or None, "
                         "got %.200s", Py_TYPE(gen)->tp_name);
            Py_DECREF(step);
            return NULL;
        }

        /* Keep value alive across the send */
        Py_INCREF(value);
        Py_DECREF(step);

        step = StepGen_send(StepGen_CAST(gen), value);
        Py_DECREF(value);

        if (!step) return NULL;
    }
}


/* ── solutions(root_step_gen, snapshot_fn) ────────────────────────────────
 *
 * Drive a trampoline-mode search, collecting snapshots at each solution.
 *
 *   step = root.send(None)
 *   while True:
 *       gen, value = step
 *       if gen is None:
 *           if value is DONE:
 *               break
 *           results.append(snapshot_fn())
 *           step = root.send(None)
 *       else:
 *           step = gen.send(value)
 *   return results
 */
static PyObject *
solutions_func(PyObject *Py_UNUSED(module), PyObject *args)
{
    PyObject *root, *snapshot_fn;
    if (!PyArg_ParseTuple(args, "OO", &root, &snapshot_fn))
        return NULL;

    if (!StepGen_Check(root)) {
        PyErr_SetString(PyExc_TypeError,
                        "solutions() first argument must be a StepGenerator");
        return NULL;
    }

    PyObject *results = PyList_New(0);
    if (!results) return NULL;

    /* step = root.send(None) */
    PyObject *step = StepGen_send(StepGen_CAST(root), Py_None);
    if (!step) { Py_DECREF(results); return NULL; }

    while (1) {
        if (!PyTuple_CheckExact(step) || PyTuple_GET_SIZE(step) != 2) {
            PyErr_SetString(PyExc_TypeError,
                            "solutions: generator must yield 2-tuples");
            Py_DECREF(step);
            Py_DECREF(results);
            return NULL;
        }

        PyObject *gen   = PyTuple_GET_ITEM(step, 0);
        PyObject *value = PyTuple_GET_ITEM(step, 1);

        if (gen == Py_None) {
            if (value == g_DONE) {
                /* Search exhausted */
                Py_DECREF(step);
                return results;
            }
            /* Solution found — take snapshot */
            Py_DECREF(step);
            PyObject *snap = PyObject_CallNoArgs(snapshot_fn);
            if (!snap) { Py_DECREF(results); return NULL; }
            if (PyList_Append(results, snap) < 0) {
                Py_DECREF(snap);
                Py_DECREF(results);
                return NULL;
            }
            Py_DECREF(snap);

            /* Ask for next solution */
            step = StepGen_send(StepGen_CAST(root), Py_None);
            if (!step) { Py_DECREF(results); return NULL; }
        } else {
            if (!StepGen_Check(gen)) {
                PyErr_Format(PyExc_TypeError,
                             "solutions: step target must be StepGenerator or None, "
                             "got %.200s", Py_TYPE(gen)->tp_name);
                Py_DECREF(step);
                Py_DECREF(results);
                return NULL;
            }
            Py_INCREF(value);
            Py_DECREF(step);

            step = StepGen_send(StepGen_CAST(gen), value);
            Py_DECREF(value);

            if (!step) { Py_DECREF(results); return NULL; }
        }
    }
}


/* ── Module definition ───────────────────────────────────────────────── */

static PyMethodDef module_methods[] = {
    {"trampoline", trampoline_func, METH_O,
     "trampoline(root: StepGenerator) → value\n\n"
     "Drive a chain of tuple-yielding generators to completion."},
    {"solutions", solutions_func, METH_VARARGS,
     "solutions(root: StepGenerator, snapshot_fn: callable) → list\n\n"
     "Drive a search, calling snapshot_fn() at each solution."},
    {NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_trampoline",
    "C-accelerated StepGenerator and trampoline for clausal logic search.",
    -1,
    module_methods,
};

PyMODINIT_FUNC
PyInit__trampoline(void)
{
    /* DONE sentinel */
    g_DONE = PyObject_CallNoArgs((PyObject *)&PyBaseObject_Type);
    if (!g_DONE) return NULL;

    if (PyType_Ready(&StepGenType) < 0)
        return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

    Py_INCREF(&StepGenType);
    if (PyModule_AddObject(m, "StepGenerator", (PyObject *)&StepGenType) < 0) {
        Py_DECREF(&StepGenType);
        Py_DECREF(m);
        return NULL;
    }

    Py_INCREF(g_DONE);
    if (PyModule_AddObject(m, "DONE", g_DONE) < 0) {
        Py_DECREF(g_DONE);
        Py_DECREF(m);
        return NULL;
    }

    return m;
}
