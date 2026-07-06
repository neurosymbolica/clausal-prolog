# fix(A03-F005): setof/3 returns insertion order — docs and ISO promise sorted

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F005
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF005F006FindallFamily::test_setof_is_sorted` (xfail — flip to pass)

## Bug

`_compile_find_all_core(dedup=True)` (`control_constructs.py:621-624`)
emits `$set_of_dedup`, which is dedup-only (`globals_env.py:42-50`,
`dict.fromkeys` order-preserving). `docs/meta_predicates.md` §setof:
"returns a **sorted** list with duplicates removed" (also ISO):

    setof(X, in_(X, [3,1,3,2]), L)  →  L = [3,1,2]   # want [1,2,3]

## Fix direction

Sort before dedup in the setof path (either a `sorted=True` flag on the
emission or a `$set_of_sort_dedup` helper reusing the standard-order
comparison that `sort/2` (msort) already implements — do NOT invent a
second term ordering). Mind unhashable/heterogeneous elements: reuse
`sort/2`'s existing key machinery; `_set_of_dedup`'s TypeError fallback
shows the mixed-type case is expected.

## Acceptance

- `[3,1,3,2]` → `[1,2,3]`; dedup-content guard stays green; findall/bagof
  untouched (order + dups preserved, bagof fails on empty).
- Cross-check with `sort/2` on the same inputs for ordering parity.
