# fix(A02-F002): list-structure dispatch drops non-list/str/Var callers

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/findings.md` A02-F002
**Tests:** `tests/audit_2026_07_05/test_02_compiler_heads.py::TestF002ListDispatchFallthrough` (4 xfail — flip to pass)

## Bug

`_build_list_dispatch_guard` (`list_dispatch.py:193-275`) emits:

    if isinstance(_d, (list, str)):  nil-vs-cons branches
    elif is_var(_d):                 all clauses
    # anything else: nothing — falls through to yield DONE

So when `_find_list_dispatch_pos` selects a position (all clauses nil/cons/var
there, both nil and cons present — requires RULE clauses, since fact
normalization hoists ground `[]` heads):

- an **int/tuple/other** caller loses the var-headed clauses (`ld2(5,R)` →
  `[]` instead of `[("any2",)]`),
- a **bytes** caller loses cons AND var clauses, violating bytes-as-lists
  (`ld2(b"ab",R)` → `[]` instead of cons2+any2; contrast: the same clause
  shapes WITHOUT dispatch — e.g. append-style var+cons — handle bytes fine),
- a **SegList** caller loses everything (a partial SegList can match cons).

## Fix direction

1. Add `bytes` to the isinstance tuple (native indexing/slicing already
   works; the multi-star guard's arm at `head_match.py:884-887` is the
   precedent — it accepts `(list, str, bytes)`).
2. Add an `else:` arm running `var_clauses` (they match any term). Better:
   run ALL clauses through their match arms in the else — the nil/cons
   clauses will simply fail their list guards on a non-list, keeping
   behavior identical to the un-dispatched compile. var-clauses-only is the
   minimal fix; all-clauses is the obviously-equivalent one.
3. SegList callers: either walk a ground SegList to a list before the
   isinstance (mirroring `seglist_normalise` in the multi-star guard) and
   let non-ground SegLists take the else arm, or just rely on the else arm
   (cons clause guards route through `$head_list_unify_input`, which
   understands SegLists).

## Acceptance

- 4 xfails flip; the 4 controls (`ld2` nil/cons/str/var) stay green.
- `test_control_adjacent_stars` etc. unaffected (different guard).
- Sweep existing list-heavy suites (`tests/` append/member fixtures) for
  regressions — per-file runs only.
