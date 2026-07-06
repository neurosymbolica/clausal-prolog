# fix-A07: clpb "Python reference implementations" break when C is loaded (global rebinding)

**Finding:** A07-F008.
**Severity:** latent correctness / maintenance.

`clausal/logic/clpb.py:764-799` saves `_apply_py`, `_negate_py`,
`_restrict_py`, `_count_paths_py`, `_collect_bdd_var_ids_py` "so the module
works without C", then rebinds the public names to C wrappers. But the saved
functions' *bodies* recurse through the rebound module globals:

- `_count_paths_py` calls global `_count_paths` for children → the C wrapper
  signature drops `current_level` and `memo`, restarting every subtree at
  level 0 → **wrong counts** (162/300 diffs vs a self-contained oracle;
  results can exceed 2^n). Anything using it as an oracle or fallback while
  C is loaded silently miscounts.
- `_apply_py`/`_restrict_py` recurse into the C path too — results happen to
  stay correct (identical hash-consed nodes) but they are NOT pure-Python
  references.

**Fix:** make the reference implementations self-contained (recurse via local
names / explicit self-reference), or drop the `_py` aliases entirely and keep
a separate `_pure.py` module that never sees the rebinding. If keeping them,
add a regression test that runs them WITH C loaded (the audit test does).

**Test:** `test_A07_F008_count_paths_py_reference_correct` (xfail strict=False).
