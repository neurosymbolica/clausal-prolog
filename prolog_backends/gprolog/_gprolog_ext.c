/*
 * _gprolog_ext — Python C extension embedding GNU Prolog.
 *
 * Exposes RawGnuPrologMachine and GnuQueryIterator to Python.
 *
 * GNU Prolog constraints:
 *   - Single engine per process (global state).
 *   - Engine cannot be restarted after Pl_Stop_Prolog().
 *   - Must be compiled with --disable-regs for shared-library use.
 *   - pl2wam must be on PATH for consult/1.
 *
 * Query model:
 *   A helper predicate '__clausal_qw__'/2 is consulted at init:
 *
 *     '__clausal_qw__'(GoalAtom, Bindings) :-
 *         read_term_from_atom(GoalAtom, Goal, [variable_names(Bindings)]),
 *         call(Goal).
 *
 *   Each query passes [GoalAtom, BindingsVar] to Pl_Query_Call.
 *   read_term_from_atom parses the goal string (must end with '.')
 *   and returns variable_names as a list of =(Name, Var) pairs.
 *   On backtracking, the Var slots are rebound by call(Goal).
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include "gprolog.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* ── Singleton state ─────────────────────────────────────────── */

static int engine_alive = 0;
static int engine_ever_started = 0;

/* Cached atom IDs */
static int atom_consult = -1;
static int atom_qw = -1;  /* '__clausal_qw__' */

/* ── Forward declarations ────────────────────────────────────── */

static PyObject *GnuPrologError;

static PyObject *term_to_py(PlTerm term);
static PyObject *list_to_py(PlTerm term);
static PyObject *read_bindings(PlTerm bindings_term);

/* ── Helpers ─────────────────────────────────────────────────── */

static int consult_file_raw(const char *path) {
    PlTerm args[1];
    /* Use Pl_Create_Allocate_Atom to copy the path string into the atom
     * table — the caller may free it after this function returns. */
    args[0] = Pl_Mk_Atom(Pl_Create_Allocate_Atom((char *)path));

    Pl_Query_Begin(PL_TRUE);
    int r = Pl_Query_Call(atom_consult, 1, args);
    if (r == PL_EXCEPTION) {
        PlTerm exc = Pl_Get_Exception();
        char *msg = Pl_Write_To_String(exc);
        PyErr_Format(GnuPrologError, "Failed to consult %s: %s", path, msg);
        Pl_Query_End(PL_RECOVER);
        return -1;
    }
    Pl_Query_End(PL_RECOVER);
    if (r == PL_FAILURE) {
        PyErr_Format(GnuPrologError, "Failed to consult: %s", path);
        return -1;
    }
    return 0;
}

static char *write_temp_pl(const char *source) {
    /* Write source to a temp file with .pl suffix, return path (caller frees).
     * Uses stdio for reliable flushing. */
    char tmpl[] = "/tmp/clausal_gp_XXXXXX";
    int fd = mkstemp(tmpl);
    if (fd < 0) {
        PyErr_SetString(GnuPrologError, "Failed to create temp file");
        return NULL;
    }
    close(fd);

    /* Rename to add .pl suffix */
    char *pl_path = malloc(strlen(tmpl) + 4);
    if (!pl_path) { unlink(tmpl); return PyErr_NoMemory(), (char*)NULL; }
    sprintf(pl_path, "%s.pl", tmpl);
    rename(tmpl, pl_path);

    FILE *f = fopen(pl_path, "w");
    if (!f) {
        unlink(pl_path);
        free(pl_path);
        PyErr_SetString(GnuPrologError, "Failed to open temp file");
        return NULL;
    }
    fputs(source, f);
    fclose(f);
    return pl_path;
}

static int init_wrapper(void) {
    /* Consult the query wrapper predicate */
    const char *src =
        "'__clausal_qw__'(GoalAtom, Bindings) :-\n"
        "    read_term_from_atom(GoalAtom, Goal, [variable_names(Bindings)]),\n"
        "    call(Goal).\n";
    char *path = write_temp_pl(src);
    if (!path) return -1;
    int r = consult_file_raw(path);
    unlink(path);
    free(path);
    return r;
}

/* ── GnuQueryIterator ────────────────────────────────────────── */

typedef struct {
    PyObject_HEAD
    PlTerm args[2];      /* [GoalAtom, Bindings] */
    int has_args;        /* 1 if args are valid (query had solutions) */
    int exhausted;
    int first_consumed;
    int *query_active;   /* pointer to machine's query_active flag */
} GnuQueryIterator;

static void
GnuQueryIterator_finish(GnuQueryIterator *self)
{
    if (!self->exhausted) {
        if (self->has_args) {
            Pl_Query_End(PL_RECOVER);
        }
        self->exhausted = 1;
        if (self->query_active)
            *(self->query_active) = 0;
    }
}

static void
GnuQueryIterator_dealloc(GnuQueryIterator *self)
{
    GnuQueryIterator_finish(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
GnuQueryIterator_iter(GnuQueryIterator *self)
{
    Py_INCREF(self);
    return (PyObject *)self;
}

static PyObject *
GnuQueryIterator_iternext(GnuQueryIterator *self)
{
    if (self->exhausted)
        return NULL;  /* StopIteration */

    if (!self->first_consumed) {
        self->first_consumed = 1;
        return read_bindings(self->args[1]);
    }

    int r = Pl_Query_Next_Solution();
    if (r != PL_SUCCESS) {
        GnuQueryIterator_finish(self);
        return NULL;  /* StopIteration */
    }

    return read_bindings(self->args[1]);
}

static PyObject *
GnuQueryIterator_close(GnuQueryIterator *self, PyObject *Py_UNUSED(args))
{
    GnuQueryIterator_finish(self);
    Py_RETURN_NONE;
}

static PyMethodDef GnuQueryIterator_methods[] = {
    {"close", (PyCFunction)GnuQueryIterator_close, METH_NOARGS, "Close the iterator."},
    {NULL}
};

static PyTypeObject GnuQueryIteratorType = {
    .ob_base = PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_gprolog_ext.GnuQueryIterator",
    .tp_basicsize = sizeof(GnuQueryIterator),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_dealloc = (destructor)GnuQueryIterator_dealloc,
    .tp_iter = (getiterfunc)GnuQueryIterator_iter,
    .tp_iternext = (iternextfunc)GnuQueryIterator_iternext,
    .tp_methods = GnuQueryIterator_methods,
};

/* ── RawGnuPrologMachine ─────────────────────────────────────── */

typedef struct {
    PyObject_HEAD
    int alive;
    int query_active;
} RawGnuPrologMachine;

static int
RawGnuPrologMachine_init(RawGnuPrologMachine *self, PyObject *args, PyObject *kwds)
{
    if (engine_ever_started) {
        PyErr_SetString(GnuPrologError,
            "GNU Prolog engine cannot be restarted after close(). "
            "Only one engine is allowed per process lifetime.");
        return -1;
    }
    if (engine_alive) {
        PyErr_SetString(GnuPrologError,
            "Only one GnuProlog instance is allowed per process.");
        return -1;
    }

    engine_ever_started = 1;
    engine_alive = 1;

    /* Build argv from GPROLOG_HOME if available */
    char *gprolog_home = getenv("GPROLOG_HOME");
    char argv0_buf[4096];
    if (gprolog_home) {
        snprintf(argv0_buf, sizeof(argv0_buf), "%s/bin/gprolog", gprolog_home);
    } else {
        snprintf(argv0_buf, sizeof(argv0_buf), "gprolog");
    }

    char *argv[] = { argv0_buf, NULL };
    int argc = 1;

    Pl_Start_Prolog(argc, argv);

    /* Cache atoms */
    atom_consult = Pl_Create_Atom("consult");
    atom_qw = Pl_Create_Atom("__clausal_qw__");

    /* Install query wrapper */
    if (init_wrapper() < 0) {
        Pl_Stop_Prolog();
        engine_alive = 0;
        return -1;
    }

    self->alive = 1;
    self->query_active = 0;
    return 0;
}

static void
RawGnuPrologMachine_dealloc(RawGnuPrologMachine *self)
{
    if (self->alive) {
        self->alive = 0;
        Pl_Stop_Prolog();
        engine_alive = 0;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
RawGnuPrologMachine_consult_file(RawGnuPrologMachine *self, PyObject *args)
{
    const char *path;
    if (!PyArg_ParseTuple(args, "s", &path)) return NULL;
    if (!self->alive) {
        PyErr_SetString(GnuPrologError, "GNU Prolog engine has been closed");
        return NULL;
    }
    if (self->query_active) {
        PyErr_SetString(GnuPrologError,
            "Machine is busy — a query iterator is still active.");
        return NULL;
    }
    if (consult_file_raw(path) < 0) return NULL;
    Py_RETURN_NONE;
}

static PyObject *
RawGnuPrologMachine_consult_string(RawGnuPrologMachine *self, PyObject *args)
{
    const char *source;
    if (!PyArg_ParseTuple(args, "s", &source)) return NULL;
    if (!self->alive) {
        PyErr_SetString(GnuPrologError, "GNU Prolog engine has been closed");
        return NULL;
    }
    if (self->query_active) {
        PyErr_SetString(GnuPrologError,
            "Machine is busy — a query iterator is still active.");
        return NULL;
    }

    char *path = write_temp_pl(source);
    if (!path) return NULL;
    int r = consult_file_raw(path);
    unlink(path);
    free(path);
    if (r < 0) return NULL;
    Py_RETURN_NONE;
}

static PyObject *
RawGnuPrologMachine_query(RawGnuPrologMachine *self, PyObject *args)
{
    const char *goal;
    if (!PyArg_ParseTuple(args, "s", &goal)) return NULL;
    if (!self->alive) {
        PyErr_SetString(GnuPrologError, "GNU Prolog engine has been closed");
        return NULL;
    }
    if (self->query_active) {
        PyErr_SetString(GnuPrologError,
            "Machine is busy — a query iterator is still active.");
        return NULL;
    }

    /* Ensure goal ends with '.' for read_term_from_atom */
    size_t len = strlen(goal);
    /* Trim trailing whitespace */
    while (len > 0 && (goal[len-1] == ' ' || goal[len-1] == '\n' || goal[len-1] == '\t'))
        len--;
    /* Trim trailing period if present, we'll add our own */
    size_t trimmed = len;
    if (trimmed > 0 && goal[trimmed-1] == '.') trimmed--;

    char *goal_with_dot = malloc(trimmed + 2);
    if (!goal_with_dot) return PyErr_NoMemory();
    memcpy(goal_with_dot, goal, trimmed);
    goal_with_dot[trimmed] = '.';
    goal_with_dot[trimmed + 1] = '\0';

    /* Create iterator object */
    GnuQueryIterator *iter = PyObject_New(GnuQueryIterator, &GnuQueryIteratorType);
    if (!iter) { free(goal_with_dot); return NULL; }

    /* Must use Pl_Create_Allocate_Atom (not Pl_Create_Atom) because
     * Pl_Create_Atom stores a pointer to the string without copying,
     * while Pl_Create_Allocate_Atom copies it into the atom table. */
    int goal_atom = Pl_Create_Allocate_Atom(goal_with_dot);
    free(goal_with_dot);

    iter->args[0] = Pl_Mk_Atom(goal_atom);
    iter->args[1] = Pl_Mk_Variable();
    iter->has_args = 1;
    iter->exhausted = 0;
    iter->first_consumed = 0;
    iter->query_active = &self->query_active;

    Pl_Query_Begin(PL_TRUE);
    int r = Pl_Query_Call(atom_qw, 2, iter->args);

    if (r == PL_EXCEPTION) {
        PlTerm exc = Pl_Get_Exception();
        char *msg = Pl_Write_To_String(exc);
        Pl_Query_End(PL_RECOVER);
        iter->exhausted = 1;
        iter->has_args = 0;
        PyErr_Format(GnuPrologError, "Prolog exception: %s", msg);
        Py_DECREF(iter);
        return NULL;
    }

    if (r == PL_FAILURE) {
        Pl_Query_End(PL_RECOVER);
        iter->exhausted = 1;
        iter->has_args = 0;
        /* Return an exhausted iterator (will yield 0 results) */
        return (PyObject *)iter;
    }

    /* First solution available */
    self->query_active = 1;
    return (PyObject *)iter;
}

static PyObject *
RawGnuPrologMachine_close(RawGnuPrologMachine *self, PyObject *Py_UNUSED(args))
{
    if (self->alive) {
        self->alive = 0;
        Pl_Stop_Prolog();
        engine_alive = 0;
    }
    Py_RETURN_NONE;
}

static PyMethodDef RawGnuPrologMachine_methods[] = {
    {"consult_file", (PyCFunction)RawGnuPrologMachine_consult_file, METH_VARARGS, "Consult a .pl file."},
    {"consult_string", (PyCFunction)RawGnuPrologMachine_consult_string, METH_VARARGS, "Consult Prolog source from a string."},
    {"query", (PyCFunction)RawGnuPrologMachine_query, METH_VARARGS, "Start a lazy query."},
    {"close", (PyCFunction)RawGnuPrologMachine_close, METH_NOARGS, "Close the engine."},
    {NULL}
};

static PyTypeObject RawGnuPrologMachineType = {
    .ob_base = PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_gprolog_ext.RawGnuPrologMachine",
    .tp_basicsize = sizeof(RawGnuPrologMachine),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)RawGnuPrologMachine_init,
    .tp_dealloc = (destructor)RawGnuPrologMachine_dealloc,
    .tp_methods = RawGnuPrologMachine_methods,
};

/* ── Term conversion ─────────────────────────────────────────── */

static PyObject *
term_to_py(PlTerm term)
{
    int tt = Pl_Type_Of_Term(term);

    switch (tt) {
    case PL_INT:
        return PyLong_FromLong(Pl_Rd_Integer(term));

    case PL_FLT:
        return PyFloat_FromDouble(Pl_Rd_Float(term));

    case PL_ATM: {
        int atom_id = Pl_Rd_Atom(term);
        char *name = Pl_Atom_Name(atom_id);
        return PyUnicode_FromString(name);
    }

    case PL_LST:
        return list_to_py(term);

    case PL_STC: {
        int functor_id, arity;
        PlTerm *cargs = Pl_Rd_Compound(term, &functor_id, &arity);
        char *functor = Pl_Atom_Name(functor_id);

        PyObject *py_args = PyTuple_New(arity);
        if (!py_args) return NULL;
        for (int i = 0; i < arity; i++) {
            PyObject *a = term_to_py(cargs[i]);
            if (!a) { Py_DECREF(py_args); return NULL; }
            PyTuple_SET_ITEM(py_args, i, a);
        }

        /* Import clausal.terms.Compound */
        PyObject *mod = PyImport_ImportModule("clausal.terms");
        if (!mod) { Py_DECREF(py_args); return NULL; }
        PyObject *cls = PyObject_GetAttrString(mod, "Compound");
        Py_DECREF(mod);
        if (!cls) { Py_DECREF(py_args); return NULL; }

        PyObject *ctor_args = PyTuple_Pack(2, PyUnicode_FromString(functor), py_args);
        Py_DECREF(py_args);
        if (!ctor_args) { Py_DECREF(cls); return NULL; }

        PyObject *result = PyObject_Call(cls, ctor_args, NULL);
        Py_DECREF(cls);
        Py_DECREF(ctor_args);
        return result;
    }

    case PL_REF:
        return PyUnicode_FromString("_");

    case PL_FDV:
        return PyUnicode_FromString("_FD");

    default:
        PyErr_Format(GnuPrologError, "Unsupported term type: %d", tt);
        return NULL;
    }
}

static PyObject *
list_to_py(PlTerm term)
{
    PyObject *list = PyList_New(0);
    if (!list) return NULL;

    PlTerm current = term;
    while (Pl_Type_Of_Term(current) == PL_LST) {
        PlTerm *pair = Pl_Rd_List(current);
        PyObject *item = term_to_py(pair[0]);
        if (!item) { Py_DECREF(list); return NULL; }
        if (PyList_Append(list, item) < 0) {
            Py_DECREF(item); Py_DECREF(list); return NULL;
        }
        Py_DECREF(item);
        current = pair[1];
    }

    /* If not terminated by [] atom, append the tail */
    if (Pl_Type_Of_Term(current) != PL_ATM) {
        PyObject *tail = term_to_py(current);
        if (!tail) { Py_DECREF(list); return NULL; }
        if (PyList_Append(list, tail) < 0) {
            Py_DECREF(tail); Py_DECREF(list); return NULL;
        }
        Py_DECREF(tail);
    }

    return list;
}

static PyObject *
read_bindings(PlTerm bindings_term)
{
    PyObject *dict = PyDict_New();
    if (!dict) return NULL;

    PlTerm current = bindings_term;
    while (Pl_Type_Of_Term(current) == PL_LST) {
        PlTerm *pair = Pl_Rd_List(current);
        PlTerm head = pair[0];
        current = pair[1];

        /* Each element: =(Name, Value) */
        if (Pl_Type_Of_Term(head) != PL_STC) continue;

        int func, arity;
        PlTerm *sa = Pl_Rd_Compound(head, &func, &arity);
        if (arity != 2) continue;

        PlTerm name_term = sa[0];
        PlTerm val_term = sa[1];

        if (Pl_Type_Of_Term(name_term) != PL_ATM) continue;

        char *name = Pl_Atom_Name(Pl_Rd_Atom(name_term));
        /* Skip anonymous variables */
        if (name[0] == '_') continue;

        PyObject *val = term_to_py(val_term);
        if (!val) { Py_DECREF(dict); return NULL; }
        if (PyDict_SetItemString(dict, name, val) < 0) {
            Py_DECREF(val); Py_DECREF(dict); return NULL;
        }
        Py_DECREF(val);
    }

    return dict;
}

/* ── Module definition ───────────────────────────────────────── */

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_gprolog_ext",
    "Embedded GNU Prolog engine for Clausal.",
    -1,
    NULL
};

PyMODINIT_FUNC
PyInit__gprolog_ext(void)
{
    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;

    if (PyType_Ready(&RawGnuPrologMachineType) < 0) return NULL;
    if (PyType_Ready(&GnuQueryIteratorType) < 0) return NULL;

    Py_INCREF(&RawGnuPrologMachineType);
    PyModule_AddObject(m, "RawGnuPrologMachine", (PyObject *)&RawGnuPrologMachineType);

    Py_INCREF(&GnuQueryIteratorType);
    PyModule_AddObject(m, "GnuQueryIterator", (PyObject *)&GnuQueryIteratorType);

    GnuPrologError = PyErr_NewException("_gprolog_ext.GnuPrologError", PyExc_Exception, NULL);
    Py_INCREF(GnuPrologError);
    PyModule_AddObject(m, "GnuPrologError", GnuPrologError);

    return m;
}
