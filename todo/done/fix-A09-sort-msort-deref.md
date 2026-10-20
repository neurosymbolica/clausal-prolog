# fix(A09-F001): sort/2 & msort/2 do not deref elements — wrong order, broken dedup

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F001
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F001_msort_bound_var_element, ::test_F001_sort_bound_var_element (xfail — flip to pass)

## Bug

`_msort__2` / `_sort__2` (lists.py:432-469) take `items = _as_items(lst_val)`
and sort/compare the RAW elements. A body-bound Var element (e.g. from
`X is 5, msort([X,1,2],S)`) is not deref'd: `sorted()` raises TypeError on
Var-vs-int, and the `(type(x).__name__, repr(x))` fallback sorts by TYPE NAME
— 'AttVar' < 'int' — so the bound var lands first regardless of value:
`msort([X=5,1,2],S)` → `[5,1,2]`. Worse, `sort`'s dedup uses `x not in seen`
with Python `==`, and `AttVar.__eq__` does not deref → `sort([X=5,5,1],S)` →
`[5,1,5]` — unsorted AND duplicate kept ("sort dedups" is the documented
contract). `list_to_set` shares the dedup bug. Contrast: sum_list/max_list/
min_list all `deref(x)` per element and are correct.

## Fix direction

Deref elements once up front (`items = [deref(x) for x in items]`) in
msort/sort/list_to_set before compare/dedup — matches the sum_list pattern.
Unbound Vars keep the existing fallback ordering. Dedup semantics beyond
deref (1 vs 1.0 vs True) is A09-F022/A01-D001 — do not change here.

## Acceptance

- Both xfails pass; ground-input sorts unchanged; `_seq_result` promotion
  unaffected (deref of 1-char strs is identity).
