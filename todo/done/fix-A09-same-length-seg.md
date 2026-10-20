# fix(A09-F019): same_length/2 ground-Seg* support is dead code

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F019
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F019_same_length_ground_segstring (xfail — flip to pass), ::test_F019_regression_same_length_str

## Bug

`_same_length__2` (lists.py:899-911) checks `isinstance(val, (list, str,
bytes))` — a ground SegString/SegBytes is neither, so
`same_length(SegString(["ab"]), L)` FAILS, while the docstring (F053 note)
and `_fresh_same_shape` (lists.py:866-884, which explicitly handles ground
SegString/SegBytes) promise it works. The Seg* branches of
`_fresh_same_shape` are unreachable.

## Fix direction

Normalize both args through `_as_items`/`normalize_seg_input` (walk ground
Seg* to their concrete shape) before the shape checks, keeping
`_fresh_same_shape` for the placeholder side.

## Acceptance

- xfail passes; str/list/bytes modes regression green.
