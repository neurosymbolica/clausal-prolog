/*
 * _variables_capi.h — public C API for the _variables extension module.
 *
 * Other C extensions (e.g. _constraints_dif) include this header and
 * retrieve a function-pointer table via PyCapsule at module init time.
 * This avoids going through Python's call protocol for hot-path
 * operations like deref, is_var, unify, and trail manipulation.
 *
 * Usage from a consumer extension:
 *
 *     #define VARIABLES_CAPI_CONSUMER
 *     #include "_variables_capi.h"
 *
 *     // In PyInit_xxx():
 *     if (import_variables_capi() < 0) return NULL;
 *
 *     // Then use the API:
 *     PyObject *t = VarAPI->deref(term);        // borrowed ref
 *     int isv     = VarAPI->is_var(term);
 *     Py_ssize_t m = VarAPI->trail_mark(trail);
 *     VarAPI->trail_undo(trail, m);
 *     ...
 */

#ifndef VARIABLES_CAPI_H
#define VARIABLES_CAPI_H

#include <Python.h>
#include <stdint.h>
#include "_ft_compat.h"

/* ── Structure layouts ───────────────────────────────────────────────
 *
 * _variables.c defines these structs internally.  Consumer extensions
 * need the layouts for direct field access.  The provider (#defines
 * VARIABLES_CAPI_PROVIDER before including) skips these to avoid
 * duplicate typedefs.
 */

#ifndef VARIABLES_CAPI_PROVIDER

typedef struct VarObject {
    PyObject_HEAD
    PyObject *binding;   /* NULL = unbound */
    uint64_t  var_id;
} VarObject;

typedef struct AttVarObject {
    VarObject  base;     /* IS-A Var */
    PyObject  *attrs;    /* PyDict or NULL */
} AttVarObject;

typedef enum { TRAIL_BINDING = 0, TRAIL_ATTR = 1, TRAIL_CALLBACK = 2 } TrailEntryKind;

typedef struct {
    TrailEntryKind kind;
    union {
        struct { VarObject *var; PyObject *old_value; } binding;
        struct { PyObject *attvar; PyObject *key; PyObject *old_attr; } attr;
        struct { PyObject *fn; } callback;
    } u;
} TrailEntry;

typedef struct TrailObject {
    PyObject_HEAD
    TrailEntry *entries;
    Py_ssize_t  length;
    Py_ssize_t  capacity;
    PyObject   *wakeup_list;
    unsigned long owner_thread_id;
} TrailObject;

#endif  /* !VARIABLES_CAPI_PROVIDER */


/* ── C API function table ────────────────────────────────────────── */

#define VARIABLES_CAPI_CAPSULE_NAME "clausal.logic.variables._variables._C_API"

typedef struct {
    /* Type objects (borrowed refs — valid for the lifetime of the module) */
    PyTypeObject *VarType;
    PyTypeObject *AttVarType;
    PyTypeObject *TrailType;

    /* deref: follow binding chain.  Returns borrowed ref. */
    PyObject *(*deref)(PyObject *term);

    /* is_var: 1 if term dereferences to an unbound Var, else 0 */
    int (*is_var)(PyObject *term);

    /* unify_with_occurs_check: returns new ref (Py_True/Py_False), NULL on error */
    PyObject *(*unify_oc)(PyObject *t1, PyObject *t2, TrailObject *trail);

    /* trail_mark: return trail->length */
    Py_ssize_t (*trail_mark)(TrailObject *trail);

    /* trail_undo: undo to mark */
    void (*trail_undo)(TrailObject *trail, Py_ssize_t mark);

    /* get_attr: return attr value (new ref) or Py_None (new ref) */
    PyObject *(*get_attr)(PyObject *var, PyObject *key);

    /* put_attr: return 0 on success, -1 on error */
    int (*put_attr)(PyObject *var, PyObject *key, PyObject *value, TrailObject *trail);

    /* is_term_instance: 1/0/-1 */
    int (*is_term_instance)(PyObject *obj);

    /* term_field_names: new ref (tuple of str), NULL on error */
    PyObject *(*term_field_names)(PyObject *obj);

    /* unify (no occurs check): returns new ref (Py_True/Py_False), NULL on error */
    PyObject *(*unify)(PyObject *t1, PyObject *t2, TrailObject *trail);

} VariablesCAPI;


/* ── Consumer side: import the capsule ───────────────────────────── */

#ifdef VARIABLES_CAPI_CONSUMER

static VariablesCAPI *VarAPI = NULL;

static int
import_variables_capi(void)
{
    PyObject *mod = PyImport_ImportModule("clausal.logic.variables._variables");
    if (!mod) return -1;

    PyObject *cap = PyObject_GetAttrString(mod, "_C_API");
    Py_DECREF(mod);
    if (!cap) return -1;

    VarAPI = (VariablesCAPI *)PyCapsule_GetPointer(cap, VARIABLES_CAPI_CAPSULE_NAME);
    Py_DECREF(cap);
    if (!VarAPI) return -1;

    return 0;
}

/* Convenience macros */
#define Var_Check(op)     PyObject_TypeCheck((op), VarAPI->VarType)
#define AttVar_Check(op)  PyObject_TypeCheck((op), VarAPI->AttVarType)
#define Trail_Check(op)   PyObject_TypeCheck((op), VarAPI->TrailType)
#define Var_CAST(op)      ((VarObject *)(op))
#define AttVar_CAST(op)   ((AttVarObject *)(op))
#define Trail_CAST(op)    ((TrailObject *)(op))

#endif  /* VARIABLES_CAPI_CONSUMER */


#endif  /* VARIABLES_CAPI_H */
