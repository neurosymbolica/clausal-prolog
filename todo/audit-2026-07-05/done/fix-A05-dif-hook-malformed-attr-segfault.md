# fix-A05: C _dif_hook segfaults on malformed "dif" attr values (A05-F002)

**Severity: correctness — interpreter crash (SIGSEGV).**
`py_dif_hook` (`clausal/logic/_constraints_dif.c:474-477`) checks that
`attr_value` is a list, but then does unchecked
`PyTuple_GET_ITEM(pair, 0)` / `GET_ITEM(pair, 1)` on each item. The attr
value is user-controllable from pure Clausal code:

```clausal
crash(X) <- (
    put_attr(X, "dif", [42]),   # or [(1,)] or ["ab"]
    X is 1                      # hook fires -> SIGSEGV (exit 139)
)
```

The Python fallback `_dif_hook` raises a clean `TypeError` for the same
inputs (unpack of a non-2-sequence); the C attach path
(`attach_dif_pair` over a malformed *existing* attr) also fails cleanly
via `PySequence_List`. Only the C hook path crashes.

## Fix

In the `py_dif_hook` loop, validate each item before use:

```c
PyObject *pair = PyList_GET_ITEM(attr_value, ci);
if (!PyTuple_Check(pair) || PyTuple_GET_SIZE(pair) != 2) {
    PyErr_SetString(PyExc_TypeError,
                    "_dif_hook: attr pairs must be 2-tuples");
    return NULL;
}
```

Matches the Python impl's clean-exception behaviour (keep them in
lockstep for the parity test). Also audit `attach_dif_pair`'s
`PyList_GET_SIZE(existing)` identity-scan — `existing` is only
guaranteed a list when written by dif itself; a non-list existing value
reaches `PySequence_List` (clean) in the no-skip branch but
`PyList_GET_SIZE` (UB) in the check_identity branch. Guard with
`PyList_Check(existing)`.

Design context: A05-D002 (engine-reserved attr keys are user-writable) —
defensive hook validation is the recommended resolution.

## Verify

Flip `TestF002DifHookMalformedAttr::test_malformed_pair_items_no_crash`
xfails to plain asserts (subprocess must exit 0); the two clean-path
controls must stay green.
