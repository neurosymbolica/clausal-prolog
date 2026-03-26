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
 *
 * LogicException unwinding: when a generator raises LogicException, the
 * trampoline walks up the parent chain via .throw() until some catch/3
 * handler absorbs it — exactly mirroring the Python trampoline.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* ── DONE sentinel ──────────────────────────────────────────────────────── */

static PyObject *g_DONE = NULL;   /* module-level singleton */

/* ── Lazily-cached exception / sentinel types ─────────────────────────── */

static PyObject *g_LogicException = NULL;  /* clausal.logic.exceptions.LogicException */
static PyObject *g_TABLING_SUSPEND = NULL; /* clausal.logic.tabling._TABLING_SUSPEND */

/*
 * Lazy-import helpers.  Called once per process, result cached.
 * Returns a borrowed reference (the module keeps the real ref).
 */
static PyObject *
get_LogicException(void)
{
    if (g_LogicException)
        return g_LogicException;
    PyObject *mod = PyImport_ImportModule("clausal.logic.exceptions");
    if (!mod) return NULL;
    g_LogicException = PyObject_GetAttrString(mod, "LogicException");
    Py_DECREF(mod);
    return g_LogicException;   /* owned by this static */
}

static PyObject *
get_TABLING_SUSPEND(void)
{
    if (g_TABLING_SUSPEND)
        return g_TABLING_SUSPEND;
    PyObject *mod = PyImport_ImportModule("clausal.logic.tabling");
    if (!mod) return NULL;
    g_TABLING_SUSPEND = PyObject_GetAttrString(mod, "_TABLING_SUSPEND");
    Py_DECREF(mod);
    return g_TABLING_SUSPEND;  /* owned by this static */
}


/* ── StepGenerator type ─────────────────────────────────────────────────── */

typedef struct {
    PyObject_HEAD
    PyObject *gen;          /* inner Python generator */
    PyObject *parent;       /* parent StepGenerator (or Py_None) */
    int       started;      /* 0 = first send does next(); 1 = delegates */
} StepGenObject;

static PyTypeObject *StepGenType = NULL;   /* heap type, set at module init */

#define StepGen_Check(op)   PyObject_TypeCheck((op), StepGenType)
#define StepGen_CAST(op)    ((StepGenObject *)(op))


/* ── StepGenerator.__init__(func, parent, *args) ─────────────────────────
 *
 * Calls func(self, parent, *args) and stores the resulting generator.
 * Stores parent for LogicException unwinding.
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

    /* parent is args[1] (first arg after func), or None if absent */
    PyObject *parent = (nargs >= 2) ? PyTuple_GET_ITEM(args, 1) : Py_None;
    Py_INCREF(parent);
    Py_XDECREF(self->parent);
    self->parent = parent;

    /* Build (self, *remaining_args) tuple for func(self, parent, ...) */
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
    Py_XDECREF(self->parent);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
StepGen_traverse(StepGenObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->gen);
    Py_VISIT(self->parent);
    return 0;
}

static int
StepGen_clear(StepGenObject *self)
{
    Py_CLEAR(self->gen);
    Py_CLEAR(self->parent);
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


/* ── StepGenerator methods & members ─────────────────────────────────── */

static PyMethodDef StepGen_methods[] = {
    {"send",  (PyCFunction)StepGen_send,  METH_O,       "send(value) -> tuple"},
    {"throw", (PyCFunction)StepGen_throw, METH_VARARGS, "throw(*args)"},
    {"close", (PyCFunction)StepGen_close, METH_NOARGS,  "close()"},
    {NULL}
};

static PyObject *
StepGen_get_parent(StepGenObject *self, void *Py_UNUSED(closure))
{
    Py_INCREF(self->parent);
    return self->parent;
}

static PyGetSetDef StepGen_getset[] = {
    {"parent", (getter)StepGen_get_parent, NULL,
     "Parent StepGenerator (for LogicException unwinding)", NULL},
    {NULL}
};


/* ── StepGenerator type spec (heap type — allows __init__ override) ──── */

static PyType_Slot StepGen_slots[] = {
    {Py_tp_doc,      "Wraps a generator function, injecting this_generator as first arg."},
    {Py_tp_new,      PyType_GenericNew},
    {Py_tp_init,     StepGen_init},
    {Py_tp_dealloc,  StepGen_dealloc},
    {Py_tp_traverse, StepGen_traverse},
    {Py_tp_clear,    StepGen_clear},
    {Py_tp_methods,  StepGen_methods},
    {Py_tp_getset,   StepGen_getset},
    {0, NULL}
};

static PyType_Spec StepGen_spec = {
    .name      = "_trampoline.StepGenerator",
    .basicsize = sizeof(StepGenObject),
    .flags     = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC | Py_TPFLAGS_BASETYPE,
    .slots     = StepGen_slots,
};


/* ── LogicException unwinding helper ──────────────────────────────────────
 *
 * When a StepGenerator.send() raises LogicException, walk up the parent
 * chain calling .throw(exc) on each parent until one catches it.
 *
 * On success: sets *out_gen and *out_value to the resumed (gen, value) tuple
 *             and returns 1.
 * On re-raise: the same LogicException propagates; returns 0 (caller
 *              should return NULL — the exception is already set).
 * On error:   a different exception is set; returns -1.
 */
static int
unwind_logic_exception(PyObject *failed_gen, PyObject **out_gen, PyObject **out_value)
{
    PyObject *exc_type, *exc_val, *exc_tb;
    PyErr_Fetch(&exc_type, &exc_val, &exc_tb);
    PyErr_NormalizeException(&exc_type, &exc_val, &exc_tb);

    /* Walk up the parent chain */
    PyObject *target = failed_gen;
    if (StepGen_Check(target))
        target = StepGen_CAST(target)->parent;
    else
        target = NULL;

    while (target != NULL && target != Py_None) {
        if (!StepGen_Check(target)) {
            target = NULL;
            break;
        }

        /* Try target.throw(exc_type, exc_val) */
        PyObject *throw_args = PyTuple_Pack(2, exc_type, exc_val);
        if (!throw_args) {
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_val);
            Py_XDECREF(exc_tb);
            return -1;
        }
        PyObject *result = StepGen_throw(StepGen_CAST(target), throw_args);
        Py_DECREF(throw_args);

        if (result) {
            /* Parent caught it — unpack (gen, value) */
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_val);
            Py_XDECREF(exc_tb);

            if (!PyTuple_CheckExact(result) || PyTuple_GET_SIZE(result) != 2) {
                PyErr_SetString(PyExc_TypeError,
                                "trampoline: generator must yield 2-tuples");
                Py_DECREF(result);
                return -1;
            }
            *out_gen = PyTuple_GET_ITEM(result, 0);
            *out_value = PyTuple_GET_ITEM(result, 1);
            Py_INCREF(*out_gen);
            Py_INCREF(*out_value);
            Py_DECREF(result);
            return 1;
        }

        /* .throw() raised — check if it's still LogicException */
        PyObject *le = get_LogicException();
        if (le && PyErr_ExceptionMatches(le)) {
            /* Same or new LogicException — keep unwinding */
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_val);
            Py_XDECREF(exc_tb);
            PyErr_Fetch(&exc_type, &exc_val, &exc_tb);
            PyErr_NormalizeException(&exc_type, &exc_val, &exc_tb);
            target = StepGen_CAST(target)->parent;
        } else {
            /* Different exception — let it propagate */
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_val);
            Py_XDECREF(exc_tb);
            return -1;
        }
    }

    /* Uncaught — re-raise the original LogicException */
    PyErr_Restore(exc_type, exc_val, exc_tb);
    return 0;
}


/* ── trampoline(root_step_gen) ───────────────────────────────────────────
 *
 * Tight C loop driving the tuple-based step protocol with LogicException
 * unwinding through the parent chain.
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
        Py_INCREF(gen);
        Py_DECREF(step);

        step = StepGen_send(StepGen_CAST(gen), value);
        Py_DECREF(value);

        if (!step) {
            /* Check for LogicException */
            PyObject *le = get_LogicException();
            if (le && PyErr_ExceptionMatches(le)) {
                PyObject *new_gen, *new_value;
                int r = unwind_logic_exception(gen, &new_gen, &new_value);
                Py_DECREF(gen);
                if (r == 1) {
                    /* Caught — build a new step tuple and continue */
                    step = PyTuple_Pack(2, new_gen, new_value);
                    Py_DECREF(new_gen);
                    Py_DECREF(new_value);
                    if (!step) return NULL;
                    continue;
                }
                /* r == 0: uncaught (re-raised), r == -1: different error */
                return NULL;
            }
            Py_DECREF(gen);
            return NULL;
        }
        Py_DECREF(gen);
    }
}


/* ── solutions(root_step_gen, snapshot_fn=None) ──────────────────────────
 *
 * Drive a trampoline-mode search, collecting snapshots at each solution.
 *
 * Handles:
 * - _TABLING_SUSPEND interception (converted to DONE for parent)
 * - LogicException unwinding through parent chain
 * - Optional snapshot callable (if None, raw value is collected)
 */
static PyObject *
solutions_func(PyObject *Py_UNUSED(module), PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"root", "snapshot", NULL};
    PyObject *root;
    PyObject *snapshot_fn = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist,
                                     &root, &snapshot_fn))
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
            /* Solution found — take snapshot or collect raw value.
             * INCREF value before DECREF step because value is borrowed
             * from step and DECREF may free both. */
            Py_INCREF(value);
            Py_DECREF(step);
            PyObject *snap;
            if (snapshot_fn != Py_None) {
                Py_DECREF(value);  /* snapshot_fn doesn't need value */
                snap = PyObject_CallNoArgs(snapshot_fn);
            } else {
                snap = value;  /* already INCREF'd above */
            }
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

            /* Check for _TABLING_SUSPEND interception */
            PyObject *tabling_suspend = get_TABLING_SUSPEND();
            int is_suspend = (tabling_suspend && value == tabling_suspend);

            Py_INCREF(value);
            Py_INCREF(gen);
            Py_DECREF(step);

            if (is_suspend) {
                /* Convert suspend to DONE so the parent exits normally */
                step = StepGen_send(StepGen_CAST(gen), g_DONE);
            } else {
                step = StepGen_send(StepGen_CAST(gen), value);
            }
            Py_DECREF(value);

            if (!step) {
                /* Check for LogicException */
                PyObject *le = get_LogicException();
                if (le && PyErr_ExceptionMatches(le)) {
                    PyObject *new_gen, *new_value;
                    int r = unwind_logic_exception(gen, &new_gen, &new_value);
                    Py_DECREF(gen);
                    if (r == 1) {
                        step = PyTuple_Pack(2, new_gen, new_value);
                        Py_DECREF(new_gen);
                        Py_DECREF(new_value);
                        if (!step) { Py_DECREF(results); return NULL; }
                        continue;
                    }
                    Py_DECREF(results);
                    return NULL;
                }
                Py_DECREF(gen);
                Py_DECREF(results);
                return NULL;
            }
            Py_DECREF(gen);
        }
    }
}


/* ── Module definition ───────────────────────────────────────────────── */

static PyMethodDef module_methods[] = {
    {"trampoline", trampoline_func, METH_O,
     "trampoline(root: StepGenerator) -> value\n\n"
     "Drive a chain of tuple-yielding generators to completion."},
    {"solutions", (PyCFunction)(void(*)(void))solutions_func, METH_VARARGS | METH_KEYWORDS,
     "solutions(root: StepGenerator, snapshot: callable = None) -> list\n\n"
     "Drive a search, calling snapshot() at each solution."},
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

    /* Create StepGenerator as a heap type (mutable — allows __init__ override) */
    StepGenType = (PyTypeObject *)PyType_FromSpec(&StepGen_spec);
    if (!StepGenType) return NULL;

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif

    Py_INCREF(StepGenType);
    if (PyModule_AddObject(m, "StepGenerator", (PyObject *)StepGenType) < 0) {
        Py_DECREF(StepGenType);
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
