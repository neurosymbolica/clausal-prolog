# fix(A09-F032): list builtins use isinstance(str) instead of _was_string for output promotion

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F032
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F032_msort_segstring_promotion (xfail — flip to pass), ::test_F032_regression_reverse_segstring_promotion

## Bug

reverse/2 computes its promotion flag via `_was_string(lst_val)` /
`_was_bytes` (handles ground SegString/SegBytes); msort, sort, list_to_set,
take, drop, split_at, select, permutation, split_with use bare
`isinstance(lst_val, str)` (lists.py:442, 464, 479, 504, 594, 697, 711, 729,
792) — a ground SegString input yields a LIST result where reverse yields a
str: `msort(SegString(["ba"]),S)` → ['a','b'] not "ab". Input-type-wins
(option A) says str-shaped in → str out.

## Fix direction

Mechanical: replace `isinstance(lst_val, str)` with `_was_string(lst_val)`
at the nine sites (bytes flags already use `_was_bytes` in most).

## Acceptance

- xfail passes; plain-str and list inputs unchanged (existing
  test_string_list_builtins.py green).
