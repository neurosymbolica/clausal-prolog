# fix(A09-F020): _chars_core.c — no Trail_Check (cross-cutting #1) + empty-string OOB read

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F020
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F020_chars_core_non_trail, ::test_F020_chars_core_empty_string (xfail — flip to pass)
**Cross-ref:** todo/cross_cutting_issues.md #1 — add _chars_core.c to its affected list (the file is missing from it; _lists_core.c has since been fixed and shows the pattern to copy).

## Bug

All 5 trail-taking entry points (`char_type_find_types`:163,
`char_type_find_chars`:223, `atom_concat_split_find`:266, `sub_atom_search`:320,
`sub_atom_enum`:399) do `Trail_CAST(trail_obj)` with NO `Trail_Check` — a
non-Trail arg is reinterpreted as TrailObject memory (UB; today it happens to
surface as a bogus "Trail accessed from a different thread" RuntimeError —
which the engine then swallows, F007). Additionally
`py_char_type_find_types` does `PyUnicode_READ_CHAR(char_str, 0)` (:162)
without a length check — an empty string is an out-of-bounds read returning a
garbage classification (`("",0,…)` → `(7,0)`).

## Fix direction

Copy _lists_core.c's guard into each function
(`if (!Trail_Check(trail_obj)) { PyErr_SetString(PyExc_TypeError, ...);
return NULL; }`) and add `if (PyUnicode_GET_LENGTH(char_str) < 1)
Py_RETURN_NONE;`. Rebuild ext in-place before testing (stale .so masks edits).

## Acceptance

- Both xfails pass (TypeError / None); refcount_stable loop test stays green.
