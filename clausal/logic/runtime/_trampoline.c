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
 * Exception unwinding: when a generator raises, the trampoline walks up the
 * parent chain via .throw() until some catch/3 handler absorbs it — exactly
 * mirroring the Python trampoline.  See is_routable_exception() below for
 * which exceptions take that path and why.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* The Trail layout, for the pending-goal check on a solution step. */
#define VARIABLES_CAPI_CONSUMER
#include "_variables_capi.h"

/* ── DONE / FINAL sentinels ─────────────────────────────────────────────── */

static PyObject *g_DONE = NULL;    /* module-level singleton */
static PyObject *g_FINAL = NULL;   /* third yield-action sentinel; see
                                    * trampoline.py and CONTINUATION_TCO_PLAN.md
                                    * §4.1.  Phase 4a lands sentinel + root
                                    * driver handling; no producer emits it
                                    * yet. */

/* ── Lazily-cached exception / sentinel types ─────────────────────────── */

static PyObject *g_TABLING_SUSPEND = NULL; /* clausal.logic.tabling._TABLING_SUSPEND */

/* ── Which exceptions the drive loops route to catch/3 ─────────────────
 *
 * A trampoline-compiled predicate does not CALL its callees: it yields
 * (child, None) and the driver runs the child.  So a callee raises inside the
 * driver's frame, never inside the ``try`` that a compiled catch/3 put in the
 * caller — the driver is the only place that can put the exception back where
 * the author wrote the handler, which it does by throwing it into the failing
 * generator's ``catcher`` chain.
 *
 * This used to be done for LogicException alone, which quietly made catch/3
 * type-dependent: throw/1 and the typed builtin errors were routed, while a
 * ValueError out of a ``++`` escape or a NameError from an unimported
 * predicate walked past every enclosing handler.  The shallow route has always
 * caught both (_compile_catch_impl emits ``except Exception`` and converts
 * non-LogicExceptions with python_error_term), so routing every Exception is
 * what makes the two routes agree.
 *
 * The exclusions are the exceptions that are PROTOCOL, not errors:
 *
 *   - BaseException-only classes — GeneratorExit (an abandoned search),
 *     KeyboardInterrupt / SystemExit (halt/1).  The catch frame's
 *     ``except Exception`` declines these anyway; routing them would park a
 *     shutdown signal in a handler that cannot act on it.
 *   - StopIteration, the generator protocol's own end-of-iteration marker: a
 *     drive loop must see exhaustion as exhaustion, and a catch/3 that
 *     swallowed it would turn a finished search into a recovery goal.  (The
 *     PEP-479 RuntimeError wrapper around one is consumed as exhaustion by
 *     solutions_func and drive_until_yield_func BEFORE this test —
 *     A04-F009, converged 2026-08-26.)
 *
 * Precondition: an exception is currently set.  Leaves it unchanged.
 * KEEP IN SYNC with ``_is_routable`` in ../trampoline.py.
 */
static int is_pep479_stopiteration_wrapper(void);  /* defined below */
static int is_engine_protocol_error(void);        /* defined below */

static int
is_routable_exception(void)
{
    if (!PyErr_ExceptionMatches(PyExc_Exception)
            || PyErr_ExceptionMatches(PyExc_StopIteration))
        return 0;
    /* Two RuntimeErrors are the ENGINE talking to itself, not errors the
     * author wrote a handler for.  drive_until_yield_func tests the first of
     * these before it ever asks about routing (A04-F009); testing both here
     * as well is what stops trampoline_func / solutions_func / _tramp_call
     * from offering a converted exhaustion or a compiler bug to a catch/3
     * with a variable catcher, which would turn an engine anomaly into a
     * recovery goal and make one program shape behave differently depending
     * on which drive loop happened to run it (review finding, 2026-08-25). */
    if (PyErr_ExceptionMatches(PyExc_RuntimeError)
            && (is_pep479_stopiteration_wrapper() || is_engine_protocol_error()))
        return 0;
    return 1;
}

/*
 * Lazy-import helper.  Called once per process, result cached.
 * Returns a borrowed reference (the module keeps the real ref).
 */
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
    PyObject *proceed;      /* solution target (or Py_None) */
    PyObject *fail;         /* exhaustion target (or Py_None) */
    PyObject *catcher;      /* exception handler chain (or Py_None) */
    int       started;      /* 0 = first send does next(); 1 = delegates */
    int       retired;      /* 1 = a pull-driver saw this root yield FINAL
                             * ("solution AND retiring"): later pulls answer
                             * exhaustion without resuming the generator. */
    PyObject *trail;        /* the Trail passed as the last argument, or NULL */
    PyObject *drain;        /* running pending-goal drain, or NULL */
    PyObject *drain_step;   /* the solution step being re-answered by it */
    int       draining;     /* 1 while the drain runs (Python goal code):
                             * re-entering this generator then is an error */
} StepGenObject;

/* An engine-protocol RuntimeError: marked so catch/3 never sees it
 * (is_routable_exception), as StepGen_send's "returned unexpectedly". */
static void
set_protocol_error(const char *msg)
{
    PyObject *perr = PyObject_CallFunction(PyExc_RuntimeError, "s", msg);
    if (!perr) return;
    if (PyObject_SetAttrString(perr, "__clausal_engine_protocol__", Py_True) < 0)
        PyErr_Clear();      /* best-effort marker; the error still raises */
    PyErr_SetObject(PyExc_RuntimeError, perr);
    Py_DECREF(perr);
}

static int
stepgen_refuse_while_draining(StepGenObject *self)
{
    if (!self->draining)
        return 0;
    set_protocol_error("StepGenerator re-entered while running its pending goals");
    return -1;
}

/* Advance *drain* by one answer, guarded against re-entry; the caller holds
 * its own references.  Returns the PyIter_Send result. */
static PySendResult
stepgen_drain_next(StepGenObject *self, PyObject *drain)
{
    PyObject *res = NULL;
    self->draining = 1;
    PySendResult sr = PyIter_Send(drain, Py_None, &res);
    self->draining = 0;
    Py_XDECREF(res);
    return sr;
}

static PyTypeObject *StepGenType = NULL;   /* heap type, set at module init */

#define StepGen_Check(op)   PyObject_TypeCheck((op), StepGenType)
#define StepGen_CAST(op)    ((StepGenObject *)(op))


/* ── StepGenerator.__init__(func, proceed, fail, catcher, *args) ─────────
 *
 * Stores the three continuation slots, then calls
 *   func(self, proceed, fail, catcher, *args)
 * to build the inner generator.  Compiled-predicate signature is
 * (this_generator, _proceed, _fail, _catcher, *args, trail).
 */
static int
StepGen_init(StepGenObject *self, PyObject *args, PyObject *kwds)
{
    /* Before any state changes: a drain running this generator's goals
     * must find it as it left it. */
    if (stepgen_refuse_while_draining(self) < 0)
        return -1;
    Py_ssize_t nargs = PyTuple_GET_SIZE(args);
    if (nargs < 4) {
        PyErr_SetString(PyExc_TypeError,
                        "StepGenerator requires at least four arguments "
                        "(func, proceed, fail, catcher)");
        return -1;
    }

    PyObject *func    = PyTuple_GET_ITEM(args, 0);
    PyObject *proceed = PyTuple_GET_ITEM(args, 1);
    PyObject *fail    = PyTuple_GET_ITEM(args, 2);
    PyObject *catcher = PyTuple_GET_ITEM(args, 3);

    Py_INCREF(proceed);
    Py_XDECREF(self->proceed);
    self->proceed = proceed;

    Py_INCREF(fail);
    Py_XDECREF(self->fail);
    self->fail = fail;

    Py_INCREF(catcher);
    Py_XDECREF(self->catcher);
    self->catcher = catcher;

    /* func(self, proceed, fail, catcher, *args[4:])
     * — generator body sees
     * (this_generator, _proceed, _fail, _catcher, *rest). */
    Py_ssize_t n_rest = nargs - 4;
    PyObject *call_args = PyTuple_New(n_rest + 4);
    if (!call_args) return -1;

    Py_INCREF((PyObject *)self);
    PyTuple_SET_ITEM(call_args, 0, (PyObject *)self);
    Py_INCREF(proceed);
    PyTuple_SET_ITEM(call_args, 1, proceed);
    Py_INCREF(fail);
    PyTuple_SET_ITEM(call_args, 2, fail);
    Py_INCREF(catcher);
    PyTuple_SET_ITEM(call_args, 3, catcher);

    for (Py_ssize_t i = 0; i < n_rest; i++) {
        PyObject *a = PyTuple_GET_ITEM(args, i + 4);
        Py_INCREF(a);
        PyTuple_SET_ITEM(call_args, i + 4, a);
    }

    PyObject *gen = PyObject_Call(func, call_args, kwds);
    Py_DECREF(call_args);
    if (!gen) return -1;

    /* Compiled predicates and builtins take the trail last. */
    Py_CLEAR(self->trail);
    Py_CLEAR(self->drain);
    Py_CLEAR(self->drain_step);
    if (n_rest > 0) {
        PyObject *last = PyTuple_GET_ITEM(args, nargs - 1);
        if (Trail_Check(last))
            self->trail = Py_NewRef(last);
    }

    Py_XDECREF(self->gen);
    self->gen = gen;
    self->started = 0;
    self->retired = 0;
    return 0;
}

static void
StepGen_dealloc(StepGenObject *self)
{
    PyObject_GC_UnTrack(self);
    Py_XDECREF(self->gen);
    Py_XDECREF(self->proceed);
    Py_XDECREF(self->fail);
    Py_XDECREF(self->catcher);
    Py_XDECREF(self->trail);
    Py_XDECREF(self->drain);
    Py_XDECREF(self->drain_step);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int
StepGen_traverse(StepGenObject *self, visitproc visit, void *arg)
{
    Py_VISIT(self->gen);
    Py_VISIT(self->proceed);
    Py_VISIT(self->fail);
    Py_VISIT(self->catcher);
    Py_VISIT(self->trail);
    Py_VISIT(self->drain);
    Py_VISIT(self->drain_step);
    return 0;
}

static int
StepGen_clear(StepGenObject *self)
{
    Py_CLEAR(self->gen);
    Py_CLEAR(self->proceed);
    Py_CLEAR(self->fail);
    Py_CLEAR(self->catcher);
    Py_CLEAR(self->trail);
    Py_CLEAR(self->drain);
    Py_CLEAR(self->drain_step);
    return 0;
}


/* ── pending goals on a solution step ──────────────────────────────────────
 *
 * clausal.logic.variables.pending_or_once(trail): the drain generator for
 * the goals queued on *trail* (see clausal/logic/pending.py). */
static PyObject *g_pending_or_once = NULL;

static PyObject *
pending_drain_for(PyObject *trail)
{
    if (!g_pending_or_once) {
        PyObject *mod = PyImport_ImportModule("clausal.logic.variables");
        if (!mod) return NULL;
        g_pending_or_once = PyObject_GetAttrString(mod, "pending_or_once");
        Py_DECREF(mod);
        if (!g_pending_or_once) return NULL;
    }
    PyObject *it = PyObject_CallOneArg(g_pending_or_once, trail);
    if (!it) return NULL;
    if (!PyGen_Check(it)) {
        PyErr_SetString(PyExc_RuntimeError,
                        "pending_or_once() did not return a generator");
        Py_DECREF(it);
        return NULL;
    }
    return it;
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
    PySendResult sr;

    if (stepgen_refuse_while_draining(self) < 0)
        return NULL;

    /* Re-answering a solution step while its pending goals have answers:
     * resume the drain; when it is exhausted, resume the generator.  The
     * drain runs Python code, so hold our own references across it. */
    if (self->drain) {
        PyObject *drain = Py_NewRef(self->drain);
        PyObject *step  = Py_NewRef(self->drain_step);
        sr = stepgen_drain_next(self, drain);
        Py_DECREF(drain);
        if (sr == PYGEN_NEXT)
            return step;
        Py_DECREF(step);
        Py_CLEAR(self->drain);
        Py_CLEAR(self->drain_step);
        if (sr == PYGEN_ERROR)
            return NULL;
    }

    for (;;) {
        sr = PyIter_Send(self->gen, send_val, &result);
        if (sr != PYGEN_NEXT)
            break;
        /* A solution step -- (proceed, None) -- with goals queued on the
         * trail: the goals run here, before the answer reaches anyone, and
         * the step is answered once per answer of theirs. */
        if (self->trail
                && Trail_CAST(self->trail)->pending != NULL
                && PyTuple_CheckExact(result)
                && PyTuple_GET_SIZE(result) == 2
                && PyTuple_GET_ITEM(result, 0) == self->proceed
                && PyTuple_GET_ITEM(result, 1) == Py_None) {
            PyObject *drain = pending_drain_for(self->trail);
            if (!drain) {
                Py_DECREF(result);
                return NULL;
            }
            PySendResult dsr = stepgen_drain_next(self, drain);
            if (dsr == PYGEN_NEXT) {
                Py_XSETREF(self->drain, drain);          /* owned */
                Py_XSETREF(self->drain_step, Py_NewRef(result));
                return result;
            }
            Py_DECREF(drain);
            Py_DECREF(result);
            if (dsr == PYGEN_ERROR)
                return NULL;
            /* No answer: this solution fails; ask for the next one. */
            send_val = Py_None;
            continue;
        }
        return result;   /* yielded value — a (target, value) tuple */
    }

    if (sr == PYGEN_RETURN) {
        /* Generator returned normally — protocol error */
        Py_XDECREF(result);
        /* Marked with an attribute rather than identified by its message:
         * is_routable_exception() must keep this away from catch/3, and
         * matching on message text would break the moment anyone reworded it. */
        PyObject *perr = PyObject_CallFunction(
            PyExc_RuntimeError, "s",
            "StepGenerator inner generator returned "
            "unexpectedly (no final yield)");
        if (perr) {
            if (PyObject_SetAttrString(perr, "__clausal_engine_protocol__",
                                       Py_True) < 0)
                PyErr_Clear();  /* best-effort marker; the error still raises */
            PyErr_SetObject(PyExc_RuntimeError, perr);
            Py_DECREF(perr);
        }
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
    if (stepgen_refuse_while_draining(self) < 0)
        return NULL;
    /* An exception thrown in ends any drain of the last solution step. */
    Py_CLEAR(self->drain);
    Py_CLEAR(self->drain_step);
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
    if (stepgen_refuse_while_draining(self) < 0)
        return NULL;
    Py_CLEAR(self->drain);
    Py_CLEAR(self->drain_step);
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
StepGen_get_proceed(StepGenObject *self, void *Py_UNUSED(closure))
{
    Py_INCREF(self->proceed);
    return self->proceed;
}

static PyObject *
StepGen_get_fail(StepGenObject *self, void *Py_UNUSED(closure))
{
    Py_INCREF(self->fail);
    return self->fail;
}

static PyObject *
StepGen_get_catcher(StepGenObject *self, void *Py_UNUSED(closure))
{
    Py_INCREF(self->catcher);
    return self->catcher;
}

static PyObject *
StepGen_get_retired(StepGenObject *self, void *Py_UNUSED(closure))
{
    return PyBool_FromLong(self->retired);
}

static int
StepGen_set_retired(StepGenObject *self, PyObject *value,
                    void *Py_UNUSED(closure))
{
    if (!value) {
        PyErr_SetString(PyExc_TypeError, "cannot delete retired");
        return -1;
    }
    int truth = PyObject_IsTrue(value);
    if (truth < 0) return -1;
    self->retired = truth;
    return 0;
}

static PyGetSetDef StepGen_getset[] = {
    {"proceed", (getter)StepGen_get_proceed, NULL,
     "Solution target (consumer frame)", NULL},
    {"fail",    (getter)StepGen_get_fail,    NULL,
     "Exhaustion target (completion frame)", NULL},
    {"catcher", (getter)StepGen_get_catcher, NULL,
     "Exception handler chain (catch/3 unwinding)", NULL},
    {"retired", (getter)StepGen_get_retired, (setter)StepGen_set_retired,
     "True once a root-level FINAL was delivered: pull-drivers answer\n"
     "exhaustion without resuming the generator (policy Q3).", NULL},
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


/* ── Exception unwinding helper ───────────────────────────────────────────
 *
 * When a StepGenerator.send() raises a routable exception, walk up the parent
 * chain calling .throw(exc) on each parent until one catches it.
 *
 * On success: sets *out_step to the resumed step (a NEW reference to
 *             whatever the absorbing handler yielded — the drive loop's
 *             own shape checks validate it with the real entry-point
 *             name) and returns 1.
 * On re-raise: the ORIGINAL exception propagates, unchanged and on its
 *              original traceback (the enrichment seam in
 *              solve._drive_trampoline and every embedding caller's ``except``
 *              match on the real type, so an unhandled route is invisible);
 *              returns 0 (caller should return NULL — the exception is
 *              already set).
 * On error:   a different exception is set; returns -1.
 */
static int
unwind_to_catcher(PyObject *failed_gen, PyObject **out_step)
{
    PyObject *exc_type, *exc_val, *exc_tb;
    PyErr_Fetch(&exc_type, &exc_val, &exc_tb);
    PyErr_NormalizeException(&exc_type, &exc_val, &exc_tb);

    /* Walk up the catcher chain */
    PyObject *target = failed_gen;
    if (StepGen_Check(target))
        target = StepGen_CAST(target)->catcher;
    else
        target = NULL;

    while (target != NULL && target != Py_None) {
        if (!StepGen_Check(target)) {
            target = NULL;
            break;
        }

        /* Try target.throw(exc_val).
         *
         * The single-argument form on purpose: gen.throw() re-raises from the
         * instance's own ``__traceback__``, so putting the fetched traceback
         * back on the instance first keeps the RAISING frames (the callee's
         * compiled body, the line the author actually wrote) on the exception
         * as it is handed up the chain.  The legacy (type, value) form drops
         * them, which for an exception nobody catches would leave the author
         * a traceback pointing at the caller instead of the culprit —
         * tests/test_source_locations.py::TestSourceLocationsG6 pins this. */
        if (exc_tb && PyException_SetTraceback(exc_val, exc_tb) < 0)
            /* Cannot fail for a fetched+normalized traceback, but leaving a
             * second exception set going into StepGen_throw would conflate
             * the two.  Drop the nicety, keep the real error. */
            PyErr_Clear();
        PyObject *throw_args = PyTuple_Pack(1, exc_val);
        if (!throw_args) {
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_val);
            Py_XDECREF(exc_tb);
            return -1;
        }
        PyObject *result = StepGen_throw(StepGen_CAST(target), throw_args);
        Py_DECREF(throw_args);

        if (result) {
            /* Parent caught it — hand the resumed step back to the drive
             * loop, whose loop-top shape checks validate it with the real
             * entry-point name (no hardcoded prefix here). */
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_val);
            Py_XDECREF(exc_tb);
            *out_step = result;   /* new reference */
            return 1;
        }

        /* .throw() raised — a declining handler re-raises (bare ``raise`` in
         * the compiled ``else`` branch), so keep unwinding from THIS frame's
         * own catcher as long as the new exception is still routable. */
        if (is_routable_exception()) {
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_val);
            Py_XDECREF(exc_tb);
            PyErr_Fetch(&exc_type, &exc_val, &exc_tb);
            PyErr_NormalizeException(&exc_type, &exc_val, &exc_tb);
            target = StepGen_CAST(target)->catcher;
        } else {
            /* A control signal (GeneratorExit, SystemExit, StopIteration …)
             * is nobody's to handle — let it propagate. */
            Py_XDECREF(exc_type);
            Py_XDECREF(exc_val);
            Py_XDECREF(exc_tb);
            return -1;
        }
    }

    /* Uncaught — re-raise the original exception */
    PyErr_Restore(exc_type, exc_val, exc_tb);
    return 0;
}


/* ── The drive core ──────────────────────────────────────────────────────
 *
 * "Advance the chain to the next ROOT yield."  The three entry points
 * (trampoline / solutions / _drive_until_yield) differ ONLY in their stop
 * condition — what they do with the root-yield value — and in ONE policy
 * flag:
 *
 *   stopiteration_is_exhaustion — treat StopIteration / a PEP-479 wrapper
 *                                 from a send as end-of-search (A04-F009;
 *                                 the pull-drivers.  NOT trampoline, whose
 *                                 contract cannot represent exhaustion.)
 *
 * A mid-chain _TABLING_SUSPEND is intercepted UNCONDITIONALLY (2026-08-26
 * policy convergence; the flag was removed 2026-08-27 so a future call
 * site cannot reintroduce the leak).  Retirement (policy Q3) also lives
 * here, once: a retired root answers DRIVE_RETIRED without being resumed,
 * and a root-level FINAL marks the root retired before delivery.
 *
 * Call it with LITERAL flag values only, so a compiler that specialises the
 * body per call site can constant-fold the flag branches away.  Whether it
 * bothers is its business: gcc 12 at -O2 on aarch64 emits ONE shared body
 * and passes the flags in registers, and the drive-loop benchmarks are
 * unmoved by that (trampoline microbench and every macro workload land
 * inside run-to-run noise of the pre-refactor build, measured interleaved).
 * The flags stay literal so the option remains open, not because any
 * measurement depends on it.  ``who`` feeds the (cold) protocol-error
 * messages.
 *
 * The entry send (root.send(None)) is never routed to a catcher — all six
 * historical loops agreed on that — only the exhaustion flags touch it.
 *
 * On DRIVE_YIELDED, *out_value holds a NEW reference to the root-yield
 * value.  On DRIVE_ERROR the exception is set.  DRIVE_EXHAUSTED is only
 * possible when stopiteration_is_exhaustion is true.
 *
 * KEEP IN SYNC with _drive_to_root_yield in logic/_trampoline_py.py;
 * tests/test_trampoline_parity.py enforces the agreement.
 */
typedef enum { DRIVE_YIELDED, DRIVE_EXHAUSTED, DRIVE_RETIRED,
               DRIVE_ERROR } drive_result;

/* Raise the marked engine-protocol RuntimeError (never offered to a
 * catch/3 — is_routable_exception refuses the marker). */
static void
set_engine_protocol_error(const char *msg)
{
    PyObject *perr = PyObject_CallFunction(PyExc_RuntimeError, "s", msg);
    if (perr) {
        if (PyObject_SetAttrString(perr, "__clausal_engine_protocol__",
                                   Py_True) < 0)
            PyErr_Clear();  /* best-effort marker; the error still raises */
        PyErr_SetObject(PyExc_RuntimeError, perr);
        Py_DECREF(perr);
    }
}

static inline drive_result
drive_to_root_yield_core(PyObject *root, int stopiteration_is_exhaustion,
                         const char *who, PyObject **out_value);

/* While a driver runs, the root's trail defers woken goals: they are queued
 * and run at the next goal boundary with every answer
 * (clausal/logic/pending.py).  The flag is restored on every exit, so a
 * bare unify on the trail between drives runs them in place, as before. */
static inline drive_result
drive_to_root_yield(PyObject *root, int stopiteration_is_exhaustion,
                    const char *who, PyObject **out_value)
{
    PyObject *t = StepGen_CAST(root)->trail;
    TrailObject *trail = NULL;
    int saved = 0;
    if (t) {
        if (Trail_CAST(t)->owner_thread_id != PyThread_get_thread_ident()) {
            /* As the trail's own mutators (and the Python twin) answer. */
            PyErr_SetString(PyExc_RuntimeError,
                "Trail accessed from a different thread than it was created in. "
                "Each thread must use its own Trail object.");
            return DRIVE_ERROR;
        }
        trail = Trail_CAST(Py_NewRef(t));
        saved = trail->defer;
        trail->defer = 1;
    }
    drive_result r = drive_to_root_yield_core(root, stopiteration_is_exhaustion,
                                              who, out_value);
    if (trail) {
        trail->defer = saved;
        Py_DECREF(trail);
    }
    return r;
}

static inline drive_result
drive_to_root_yield_core(PyObject *root, int stopiteration_is_exhaustion,
                         const char *who, PyObject **out_value)
{
    /* Retirement (policy Q3) lives here, once: a retired root answers
     * without being resumed; each wrapper maps DRIVE_RETIRED to its own
     * contract (pull-drivers: benign exhaustion; trampoline: a loud
     * protocol error). */
    if (StepGen_CAST(root)->retired)
        return DRIVE_RETIRED;

    /* Resolve the lazy tabling import while no exception is active.  On
     * failure the ImportError must propagate CLEANLY — running the sends
     * below with a live exception set is a C-API violation, and the
     * Python twin raises the ImportError from its own import statement
     * (review follow-up, 2026-08-27). */
    if (!get_TABLING_SUSPEND())
        return DRIVE_ERROR;

    PyObject *step = StepGen_send(StepGen_CAST(root), Py_None);
    if (!step) {
        if (stopiteration_is_exhaustion &&
            (PyErr_ExceptionMatches(PyExc_StopIteration) ||
             (PyErr_ExceptionMatches(PyExc_RuntimeError) &&
              is_pep479_stopiteration_wrapper()))) {
            PyErr_Clear();
            return DRIVE_EXHAUSTED;
        }
        return DRIVE_ERROR;
    }

    while (1) {
        if (!PyTuple_CheckExact(step) || PyTuple_GET_SIZE(step) != 2) {
            PyErr_Format(PyExc_TypeError,
                         "%s: generator must yield 2-tuples", who);
            Py_DECREF(step);
            return DRIVE_ERROR;
        }

        PyObject *gen   = PyTuple_GET_ITEM(step, 0);  /* borrowed */
        PyObject *value = PyTuple_GET_ITEM(step, 1);  /* borrowed */

        if (gen == Py_None) {
            /* Root-level FINAL: "here is a solution AND I am retiring" —
             * mark the root before delivery so no driver re-pulls it
             * (policy Q3). */
            if (value == g_FINAL)
                StepGen_CAST(root)->retired = 1;
            Py_INCREF(value);
            Py_DECREF(step);
            *out_value = value;
            return DRIVE_YIELDED;
        }

        if (!StepGen_Check(gen)) {
            /* Last path component of tp_name, so the message matches the
             * twin's type(gen).__name__ spelling (parity, 2026-08-27). */
            const char *tn = Py_TYPE(gen)->tp_name;
            const char *dot = strrchr(tn, '.');
            PyErr_Format(PyExc_TypeError,
                         "%s: step target must be StepGenerator or None, "
                         "got %.200s", who, dot ? dot + 1 : tn);
            Py_DECREF(step);
            return DRIVE_ERROR;
        }

        /* Mid-chain _TABLING_SUSPEND is intercepted unconditionally —
         * cache already resolved at entry, so ts is never NULL here. */
        int is_suspend = (value == g_TABLING_SUSPEND);

        /* Keep value alive across the send */
        Py_INCREF(value);
        Py_INCREF(gen);
        Py_DECREF(step);

        step = StepGen_send(StepGen_CAST(gen), is_suspend ? g_DONE : value);
        Py_DECREF(value);

        if (!step) {
            if (stopiteration_is_exhaustion &&
                (PyErr_ExceptionMatches(PyExc_StopIteration) ||
                 (PyErr_ExceptionMatches(PyExc_RuntimeError) &&
                  is_pep479_stopiteration_wrapper()))) {
                /* Tested BEFORE routing so a converted exhaustion is never
                 * offered to a catch/3 as an error (A04-F009). */
                PyErr_Clear();
                Py_DECREF(gen);
                return DRIVE_EXHAUSTED;
            }
            /* Hand it to the enclosing catch/3, if there is one */
            if (is_routable_exception()) {
                PyObject *new_step;
                int r = unwind_to_catcher(gen, &new_step);
                Py_DECREF(gen);
                if (r == 1) {
                    step = new_step;   /* loop top re-validates its shape */
                    continue;
                }
                /* r == 0: uncaught (re-raised), r == -1: different error */
                return DRIVE_ERROR;
            }
            Py_DECREF(gen);
            return DRIVE_ERROR;
        }
        Py_DECREF(gen);
    }
}


/* ── trampoline(root_step_gen) ───────────────────────────────────────────
 *
 * Drive the tuple-based step protocol to the root yield and return its
 * value.  The loop (and its exception unwinding through the parent chain)
 * lives in drive_to_root_yield above.
 */
static PyObject *
trampoline_func(PyObject *Py_UNUSED(module), PyObject *root)
{
    if (!StepGen_Check(root)) {
        PyErr_SetString(PyExc_TypeError,
                        "trampoline() argument must be a StepGenerator");
        return NULL;
    }

    /* The root protocol ends with yield (None, final_value).  A mid-chain
     * _TABLING_SUSPEND is intercepted like every other entry point (policy
     * convergence Q1, 2026-08-26 — it used to leak through as a value).
     * No exhaustion conversion: this contract returns the root-yield
     * value and has no way to represent exhaustion, so StopIteration /
     * a PEP-479 wrapper raises (blessed difference, see
     * todo/done/drive-loop-policy-convergence.md).  For the same reason a
     * retired root and a ROOT-level suspend — benign exhaustion for the
     * pull-drivers — are loud protocol errors here: returning the raw
     * sentinel fabricated success at the clpz3 call site (review
     * follow-up, 2026-08-27). */
    PyObject *value = NULL;
    drive_result r = drive_to_root_yield(root,
                                         /*stopiteration_is_exhaustion=*/0,
                                         "trampoline", &value);
    if (r == DRIVE_RETIRED) {
        set_engine_protocol_error(
            "trampoline: pull on a retired StepGenerator "
            "(FINAL already delivered)");
        return NULL;
    }
    if (r != DRIVE_YIELDED)
        return NULL;   /* DRIVE_EXHAUSTED impossible with the flag off */
    if (g_TABLING_SUSPEND && value == g_TABLING_SUSPEND) {
        Py_DECREF(value);
        set_engine_protocol_error(
            "trampoline: root yielded _TABLING_SUSPEND — an orphaned "
            "tabling consumer cannot be driven to a value");
        return NULL;
    }
    return value;
}


/* ── solutions(root_step_gen, snapshot_fn=None) ──────────────────────────
 *
 * Drive a trampoline-mode search, collecting snapshots at each solution.
 *
 * Handles:
 * - _TABLING_SUSPEND interception (converted to DONE for parent)
 * - exception unwinding through the parent chain
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

    while (1) {
        PyObject *value = NULL;
        /* stopiteration_is_exhaustion: a StopIteration / PEP-479 wrapper
         * from a send is a converted exhaustion — return what was
         * collected, agreeing with _drive_until_yield (policy convergence
         * Q2, 2026-08-26; A04-F009 read across entry points).
         * DRIVE_RETIRED: a FINAL was already delivered from this root
         * (by any driver) — do not resume the retired generator. */
        drive_result r = drive_to_root_yield(root,
                                             /*stopiteration_is_exhaustion=*/1,
                                             "solutions", &value);
        if (r == DRIVE_EXHAUSTED || r == DRIVE_RETIRED)
            return results;
        if (r != DRIVE_YIELDED) {
            Py_DECREF(results);
            return NULL;
        }

        if (value == g_DONE) {
            /* Search exhausted */
            Py_DECREF(value);
            return results;
        }
        {
            /* A04-F008: a root/orphaned consumer yields
             * (None, _TABLING_SUSPEND) — a control sentinel, never a
             * solution; treat it as exhaustion. */
            PyObject *ts = get_TABLING_SUSPEND();
            if (ts && value == ts) {
                Py_DECREF(value);
                return results;
            }
        }
        if (value == g_FINAL) {
            /* Producer is retiring with its last solution: deliver
             * it and stop — no further pull from the (now-retired)
             * root.  FINAL is a sentinel, not a payload, so when
             * snapshot is None there is no raw value to record.
             * (The drive core already marked the root retired.) */
            Py_DECREF(value);
            if (snapshot_fn != Py_None) {
                PyObject *snap = PyObject_CallNoArgs(snapshot_fn);
                if (!snap) { Py_DECREF(results); return NULL; }
                if (PyList_Append(results, snap) < 0) {
                    Py_DECREF(snap);
                    Py_DECREF(results);
                    return NULL;
                }
                Py_DECREF(snap);
            }
            return results;
        }

        /* Solution found — take snapshot or collect the raw value. */
        PyObject *snap;
        if (snapshot_fn != Py_None) {
            Py_DECREF(value);  /* snapshot_fn doesn't need the raw value */
            snap = PyObject_CallNoArgs(snapshot_fn);
        } else {
            snap = value;      /* already a new reference */
        }
        if (!snap) { Py_DECREF(results); return NULL; }
        if (PyList_Append(results, snap) < 0) {
            Py_DECREF(snap);
            Py_DECREF(results);
            return NULL;
        }
        Py_DECREF(snap);
    }
}


/* ── _drive_until_yield(sg) ─────────────────────────────────────────────
 *
 * Inner loop of _drive_trampoline moved to C.
 *
 * Delegates to drive_to_root_yield, which calls sg.send(None) and then
 * loops through the trampoline chain until either:
 *   - A solution is found (gen == None, value != DONE) → returns Py_True
 *   - Search exhausted (gen == None, value == DONE)    → returns Py_None
 *   - StopIteration from send()                        → returns Py_None
 *   - Error (unwound to a catch/3 or propagated)       → returns NULL
 */

/* A04-F009: distinguish a PEP-479 "generator raised StopIteration" wrapper
 * (RuntimeError whose __cause__ is a StopIteration — a converted exhaustion,
 * safe to treat as end-of-search) from a genuine RuntimeError raised by user
 * code (e.g. a ``++`` escape) or by the StepGen protocol (a compiler bug),
 * which MUST propagate rather than be silently reported as zero solutions.
 * Precondition: the active exception matches RuntimeError. The current
 * exception is left unchanged. Returns 1 for a PEP-479 wrapper, else 0. */
static int
is_pep479_stopiteration_wrapper(void)
{
    PyObject *exc = PyErr_GetRaisedException();  /* new ref; clears current */
    if (!exc)
        return 0;
    PyObject *cause = PyException_GetCause(exc);  /* new ref or NULL */
    int is_wrapper = (cause != NULL &&
                      PyObject_TypeCheck(cause,
                                         (PyTypeObject *)PyExc_StopIteration));
    Py_XDECREF(cause);
    PyErr_SetRaisedException(exc);  /* restore (consumes exc ref) */
    return is_wrapper;
}

/* True for the StepGen protocol error raised by StepGen_send — an engine
 * anomaly (a compiled generator that returned instead of yielding), never
 * something an author's catch/3 should absorb.  Precondition: the active
 * exception matches RuntimeError.  Leaves the current exception unchanged. */
static int
is_engine_protocol_error(void)
{
    PyObject *exc = PyErr_GetRaisedException();  /* new ref; clears current */
    if (!exc)
        return 0;
    int marked = PyObject_HasAttrString(exc, "__clausal_engine_protocol__");
    PyErr_SetRaisedException(exc);  /* restore (consumes exc ref) */
    return marked;
}


static PyObject *
drive_until_yield_func(PyObject *Py_UNUSED(module), PyObject *sg_obj)
{
    if (!StepGen_Check(sg_obj)) {
        PyErr_SetString(PyExc_TypeError,
                        "_drive_until_yield() argument must be a StepGenerator");
        return NULL;
    }

    PyObject *value = NULL;
    /* DRIVE_RETIRED: a FINAL was already delivered from this root —
     * benign exhaustion, the generator is not resumed (policy Q3,
     * 2026-08-26; retirement lives in the drive core since the
     * 2026-08-27 review follow-up). */
    drive_result r = drive_to_root_yield(sg_obj,
                                         /*stopiteration_is_exhaustion=*/1,
                                         "_drive_until_yield", &value);
    if (r == DRIVE_EXHAUSTED || r == DRIVE_RETIRED)
        Py_RETURN_NONE;
    if (r == DRIVE_ERROR)
        return NULL;

    /* A04-F008: (None, _TABLING_SUSPEND) is a control sentinel, never a
     * solution — a root/orphaned consumer would otherwise fabricate an
     * unbound answer.  Treat it as exhaustion alongside DONE.  (A
     * root-level FINAL was already recorded by the core; it delivers its
     * solution as True here.) */
    int is_done = (value == g_DONE) ||
                  (g_TABLING_SUSPEND && value == g_TABLING_SUSPEND);
    Py_DECREF(value);
    if (is_done)
        Py_RETURN_NONE;   /* search exhausted */
    Py_RETURN_TRUE;       /* solution found — caller should yield */
}


/* ── Module definition ───────────────────────────────────────────────── */

static PyMethodDef module_methods[] = {
    {"trampoline", trampoline_func, METH_O,
     "trampoline(root: StepGenerator) -> value\n\n"
     "Drive a chain of tuple-yielding generators to completion."},
    {"solutions", (PyCFunction)(void(*)(void))solutions_func, METH_VARARGS | METH_KEYWORDS,
     "solutions(root: StepGenerator, snapshot: callable = None) -> list\n\n"
     "Drive a search, calling snapshot() at each solution."},
    {"_drive_until_yield", drive_until_yield_func, METH_O,
     "_drive_until_yield(sg: StepGenerator) -> bool | None\n\n"
     "Inner loop of _drive_trampoline.  Calls sg.send(None) and loops\n"
     "through the trampoline chain until a solution (returns True) or\n"
     "search exhaustion (returns None)."},
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
    /* DONE / FINAL sentinels */
    g_DONE = PyObject_CallNoArgs((PyObject *)&PyBaseObject_Type);
    if (!g_DONE) return NULL;
    g_FINAL = PyObject_CallNoArgs((PyObject *)&PyBaseObject_Type);
    if (!g_FINAL) return NULL;

    if (import_variables_capi() < 0) return NULL;

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

    Py_INCREF(g_FINAL);
    if (PyModule_AddObject(m, "FINAL", g_FINAL) < 0) {
        Py_DECREF(g_FINAL);
        Py_DECREF(m);
        return NULL;
    }

    return m;
}
