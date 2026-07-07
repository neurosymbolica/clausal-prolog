# fix(A09-F021): _lists_core.c segfaults on non-list `items` (PyList_GET_SIZE unchecked)

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F021
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F021_lists_core_non_list_segfault (xfail — flip to pass)
**Cross-ref:** todo/cross_cutting_issues.md #6 (unchecked GET_SIZE macros).

## Bug

member_find/memberchk_find/append_split_find/select_find/nth0_find call
`PyList_GET_SIZE(items)` / `PyList_GET_ITEM` on the raw argument
(_lists_core.c:132, 176, 228, 306, 444). The Python callers always pass a
list, but the functions are public module attributes:
`member_find("abc", 0, Var(), Trail())` → SIGSEGV (confirmed rc=-11).

## Fix direction

`if (!PyList_Check(items)) { PyErr_SetString(PyExc_TypeError, "items must be
a list"); return NULL; }` at each entry. Zero hot-path cost (one check per
resume). Rebuild ext in-place before testing.

## Acceptance

- xfail passes (TypeError, rc=0); builtin fast paths unchanged.
