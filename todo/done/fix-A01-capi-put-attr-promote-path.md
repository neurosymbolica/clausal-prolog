# fix-A01: capi_put_attr Var→AttVar promote path is broken C (A01-F002)

**Severity: correctness (latent — no in-tree caller today).**
`_variables.c:3145-3164` (`capi_put_attr`, exported via the `_C_API` capsule):

```c
} else if (Var_Check(root)) {
    /* Promote Var → AttVar (simplified — full promote in py_put_attr) */
    PyObject *result = py_put_attr(NULL, Py_BuildValue("(OOsO)",
        root, key, value, (PyObject *)trail));
```

Three bugs in two lines:
1. **`"(OOsO)"` treats `value` (a `PyObject *`) as a `char *`** — undefined
   behaviour: `Py_BuildValue` reads it as a NUL-terminated C string (garbage
   or segfault).
2. **The args tuple leaks** — never DECREF'd (and `Py_BuildValue` failure
   isn't checked before the call).
3. **The comment lies**: `py_put_attr` does NOT promote — it raises
   `TypeError` unless the var derefs to an `AttVar`, so even a "successful"
   call fails.

Unreachable today: grep (2026-07-05) shows no consumer of the capsule's
`put_attr` (clpfd calls the Python-level `put_attr` via `fn_put_attr`), and
Python-level `Var` is aliased to `AttVar`. Any future C extension calling
`capi.put_attr` with a `PlainVar` hits UB. Logged **unconfirmed —
not executable from Python** in the A01 ledger.

## Fix

Either actually promote (rebind impossible — Var identity must be preserved;
realistically: raise a clean TypeError like `py_put_attr` does), or build the
tuple with `"(OOOO)"`, check for NULL, and DECREF it after the call. Simplest
correct form:

```c
} else if (Var_Check(root)) {
    PyErr_SetString(PyExc_TypeError,
        "put_attr requires an AttVar (plain Var cannot be promoted)");
    return -1;
}
```

Rebuild `_variables` (`setup.py build_ext --inplace`) after editing.

## Verify

No Python-level repro exists; add a C-comment test note or a capsule-level
unit if a test harness for the capsule appears. At minimum: code review +
compile.
