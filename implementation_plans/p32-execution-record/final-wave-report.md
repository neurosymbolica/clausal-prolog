# P3-2 (cell default flip): final fix wave report

Branch: `feat/p32-cell-flip`, starting HEAD `e83c0e3c`. One wave, per the
whole-branch final review's findings list (F1-F5). No other changes.

## F1 (Important, branch-introduced): TRO plan cache keyed on short-lived object ids

**File:** `clausal/logic/compiler/predicate.py`, `_build_predicate_trampoline_funcdef`'s
`_tro_aware_bc` closure (~line 502-560).

**Mechanism confirmed.** The recompute path's old code did
`_plan = _ctx.clause_tro_plans.get(id(clause))` — a GET before checking for
a cache miss — against `ctx_template.clause_tro_plans`, a dict SHARED
across every bucket/default/fallback call to
`_build_predicate_trampoline_funcdef` for one predicate compile. A bucket's
`lifted_bucket` list (built fresh per `(pos, key)` loop iteration) is a
short-lived local with no other referent once its funcdef is built; CPython
recycles its freed `Clause` objects' addresses immediately, so a LATER
bucket's lift can mint a brand-new `Clause` at the SAME id as an earlier,
now-dead one. The unconditional `.get()` would then return the STALE plan
computed for the earlier, unrelated clause's body — a silent miscompile the
`id(clause) in _tset` guard cannot catch (colliding clauses are in `_tset`
by construction, each bucket builds its own `_tset` from its own `clauses`).
The IR cache (`clause_ir_cache`) carried the identical class of hazard one
step further downstream (`goal_shallow._body_compiler` reads it by
`id(clause)` too).

**Mechanism chosen: (b) the recompute gets its own cache, LOCAL to each
`_build_predicate_trampoline_funcdef` call.** Rationale: `clauses` (and
therefore every id `_tset` can ever name) is kept alive by that call's own
stack frame for the call's entire duration, so a dict scoped to the call
cannot collide with a freed-and-recycled id from a sibling call — no
memory-lifetime coupling to reason about across calls at all. Chose (b)
over (a) (keep every `lifted_bucket` alive via a list on `ctx_template`)
because (b) needs no new lifetime management and costs nothing extra
(each clause is visited by `body_compiler` at most once per call today).

For the TRO *plan*: a fresh `_recompute_plans: dict` local to the call,
read/written instead of `_ctx.clause_tro_plans`.

For the *IR* cache specifically: rather than staging the recomputed IR into
the shared `_ctx.clause_ir_cache` (even temporarily, popped after use — an
approach tried and reverted, see below), the fix skips the shared cache for
the recompute path entirely. `_compile_body_impl` already handles a cache
miss safely (`body_ir if body_ir is not None else
terms_to_goalop(goals, ctx.db)` — one redundant rebuild, never a wrong
answer), so there is no correctness reason to touch the shared dict from
this path at all.

**Why the temporary-stage-then-pop approach for the IR cache was rejected**:
built it first, and the new regression test caught it — `clause_ir_cache`
ended up SMALLER than the pre-lift sweep's count after compiling the F1
fixture (5 vs. an expected 7). Root cause: when a bucket's lift is a
no-op (the post-lift object IS the pre-lift one, same id), the recompute's
unconditional `pop()` in the `finally` block evicted a still-valid entry
the initial sweep had legitimately placed there for that same, live object
— a real regression the write/pop approach introduced. Skipping the shared
cache for the recompute path avoids the whole class of question.

Also corrected the now-false comment (former lines ~511-513) claiming "plan
was built by `_sweep_tro_eligible`; `id(clause) in _tset` implies
`plan.eligible` is True" — false for exactly the diverging (post-lift) case
the surrounding comment already explained; reworded to describe the actual
PRE-lift/POST-lift distinction without contradicting itself.

**Test:** `tests/test_tro_lift_recompute_cache_scope.py` (new) +
`tests/fixtures/tro_lift_recompute_cache.clausal` (new fixture). Two
independent str-keyed buckets ("a", "b"), each above `_INDEX_THRESHOLD`
(7 clauses total), TRO-eligible (tail recursion) and lift-eligible (P3-2
Task 4/R8 retired the str half of the lift-skip) — "b"'s recursive clause
carries one extra prefix goal so a cross-bucket plan mix-up would misplace
the tail-call split, not just silently agree. Two tests:
1. `test_correct_answers_for_both_lift_eligible_tro_buckets` — drives both
   buckets through `call()`, reduces the returned (partly symbolic) `Sub`
   chains and asserts the recursion actually ran to depth 4 for both.
2. `test_recompute_does_not_grow_the_shared_ctx_template_caches` — spies on
   `_sweep_tro_eligible` to capture `ctx_template`, then asserts
   `len(ctx_template.clause_tro_plans) == len(ctx_template.clause_ir_cache)
   == n_original_clauses` (7) — the structural property the chosen fix
   guarantees, not id behaviour.

Both new tests pass; `tests/test_optimisations_tro.py`,
`tests/test_control.py`, `tests/test_tro_nonlast_arm_clobber.py`,
`tests/test_secondary_dispatch_tro.py`, `tests/test_first_arg_index.py`
(99 tests) all still pass.

## F2 (Important, pre-existing, exposed not caused): indexed dispatch drops partial/keyword head references

Verified byte-identical mechanism present at base `5bcd66ec`
(`git show 5bcd66ec:clausal/logic/compiler/arg_index.py`) — confirmed
PRE-EXISTING, not fixed per the review's instruction (record + pin only).

**Repro verified empirically** (not just theorized) via a throwaway inline
fixture before writing the pinned tests: a `pt(x, y)` data functor, a
6-clause discriminator predicate with `pt(1)` (partial) as one clause's
head, queried with the full backfilled cell `("pt", 1, 9)` — returns `[]`
above `_INDEX_THRESHOLD`, `["hit"]` below it. Keyword form (`pt(y=2)`,
queried `("pt", 7, 2)`) identical. Saturated form (`pt(1, 2)`) returns
`["hit"]` at any clause count (unaffected).

**Delivered:**
1. `todo/indexed-dispatch-drops-partial-head-references-2026-09-05.md` —
   self-contained repro, the `head_to_match_pattern` (declared-arity
   placement) vs. `_arg_to_index_key`'s `Call` branch (written-arity key)
   mechanism, fix direction (thread `globals_` into the key function,
   resolve `cell_signature_for_name` there), OWA cross-reference (already
   unaffected, filed in the sibling `owa-unknown-functor-...` todo).
2. `tests/test_tagged_terms.py::TestPartialHeadReferenceIndexing` (new) —
   one `_load_inline` fixture, 5 SOLVE tests: saturated-above-threshold
   (passes, pinned as a plain test), partial-above and keyword-above
   (`xfail(strict=True)`, reason cites the todo file), partial-below and
   keyword-below (pass, pin the correct unindexed floor).

## F3: packages/ semantic-break record (deferred to the Python seam phase)

`todo/packages-data-functor-reconstruction-breaks-post-flip-2026-09-05.md`.
Read `packages/clausal-provenance`'s `engine.py` (~10 `cls(**kwargs)`
reconstruction sites, all guarded by `is_term_instance(term)` first — a
cell falls through to the earlier `isinstance(term, tuple)` branch instead,
so those specific sites are not where the sharpest break is) and
`_registration.py` directly rather than just repeating the review's
framing. Found and cited the PRECISE, verified break:
`provenance_reach.clausal`'s `bottom_up_(Edge)` (Edge: a declared data
functor with no clauses, registered as an EDB relation) hits
`_RegistrationGoal.__call__`'s `isinstance(cls, PredicateMeta)` check,
which raises `TypeError: bottom_up_ expects a PredicateMeta class, got
'Edge'. ...` at module-load time — because post-flip (R6) `Edge` binds its
interned spelling, not a class. Not independently executed end-to-end
(`clausal.modules.provenance` isn't installed/importable in this session's
venv — installing a package was judged out of scope for a record-only
todo); confirmed by direct source reading instead. Cross-referenced
`implementation_plans/python-seam-classes-as-functors.md` (whose own
"Origin" paragraph already names this exact consequence) and both
migration options from that plan.

## F4 (small code)

- **M1** `clausal/logic/database.py:475-476`: `isinstance(val[0], str)` →
  `type(val[0]) is str`; corrected the adjacent comment (previously false —
  it claimed to already match `cells.is_cell`, which uses exact-type; now
  true).
- **M2** `clausal/testing.py:1612`: same straggler, same fix.
- **M9** `tests/test_term_inspection.py::test_existing_pre_seeded_returned`:
  wrapped the body in `try/finally: del predicate_builtins[name]` so the
  marker doesn't leak into the process-global dict for later tests.

`tests/test_term_inspection.py` (200 tests incl. the two new F1/F2 files
combined run) and the F1/F2 covering runs above all pass with these in
place; no behavioural change expected or observed (both were subclass-proof
strengthenings with the tested inputs already exact-type `str`).

## F5 (docs/prose)

- **M3** `docs/directives.md`, `-implicit_functors`: added the
  `-constants` RHS exception (verified via
  `term_rewriting.py::_transform_constant_rhs`'s `Call` branch — its
  declared/imported-functor check is unconditional, never consults the
  OWA flag) as a new paragraph alongside the existing "Dotted references
  stay loud" / "Predicates are unaffected" caveats.
- **M4** same file, "-tagged_terms (removed)": `below` → `above` (the
  cross-referenced section is near the top of the file, this section is
  near the bottom).
- **M6** `tests/fixtures/{tagged_shapes,tagged_shapes_tagged,
  struct_tabling_tagged,head_list_compound_tagged}.clausal`: rewrote the
  flag-era headers. Removed the false "Compound DATA never crosses a
  module boundary" claim (false post-R5 — verified against
  `implementation_plans/p32-cell-default-flip.md`'s R5 ruling text) from
  the first two; corrected `struct_tabling_tagged.clausal`'s stale "the
  atom `nil` stays a class atom... Phase 3 does the atom pivot, not this
  bridge" (P3-1's atom pivot already happened; `nil` is an interned str
  now); reworded `head_list_compound_tagged.clausal`'s categorical "never
  reaches a compiled MATCH pattern" claim — verified every predicate in
  that fixture has exactly one clause (well under `_INDEX_THRESHOLD`), so
  the claim is still true FOR THIS FILE, but the file now says so as a
  fixture-local fact with a pointer to `TestHeadPatternReachability` for
  the general (now-inverted-above-threshold) picture, instead of stating
  it as an engine-wide invariant.
- **M7** `clausal/logic/cells.py` module docstring: rewrote the opener —
  cells are now the unconditional term representation (P3-2), with a
  one-line historical pointer to the Phase 2 bridge plan instead of
  presenting the bridge framing as current.

## Gate evidence

Covering tests (F1 + F2 + F4, foreground):
```
pytest tests/test_optimisations_tro.py tests/test_control.py \
  tests/test_tro_nonlast_arm_clobber.py tests/test_secondary_dispatch_tro.py \
  tests/test_tro_lift_recompute_cache_scope.py tests/test_first_arg_index.py \
  tests/test_tagged_terms.py tests/test_term_inspection.py -q
-> 300 passed, 2 xfailed
```

Full suite (`pytest tests/ --continue-on-collection-errors --tb=no -q -rf`,
output saved to
`.superpowers/sdd/p32-cell-default-flip/final-wave-full-suite.txt`):
```
144 failed, 12058 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error
```
vs. baseline (`baseline-full.txt`): `145 failed, 11654 passed, 56 skipped,
37 xfailed, 747 warnings, 1 error`.

Failure-NAME diff (both sides normalized by stripping the `-rf` message
suffix, since baseline's file kept it and `--tb=no` truncates it
inconsistently by line length):
```
diff baseline-stripped.txt current-failed-names.txt
1d0
< FAILED tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input
```
Exactly one line of diff: the known C17-perf flake (memory:
"C17-perf flake") — present in the baseline capture, absent (passed) in
this run. No other name differences in either direction.

**xfail accounting:** baseline 37 → this run 39 (both new F2 xfails
present as `xfailed`, not `failed`) — delta of exactly +2, as expected.
The 1 collection error in both runs is the pre-existing ortools collection
error (`--continue-on-collection-errors` exists for exactly this reason,
per project memory) — unrelated to this wave's changes.

## Files touched

Code + tests:
- `clausal/logic/compiler/predicate.py` (F1 fix)
- `tests/test_tro_lift_recompute_cache_scope.py` (new, F1)
- `tests/fixtures/tro_lift_recompute_cache.clausal` (new, F1)
- `tests/test_tagged_terms.py` (F2 tests)
- `clausal/logic/database.py` (F4 M1)
- `clausal/testing.py` (F4 M2)
- `tests/test_term_inspection.py` (F4 M9)

Docs/records:
- `todo/indexed-dispatch-drops-partial-head-references-2026-09-05.md` (new, F2)
- `todo/packages-data-functor-reconstruction-breaks-post-flip-2026-09-05.md` (new, F3)
- `docs/directives.md` (F5 M3, M4)
- `tests/fixtures/tagged_shapes.clausal` (F5 M6)
- `tests/fixtures/tagged_shapes_tagged.clausal` (F5 M6)
- `tests/fixtures/struct_tabling_tagged.clausal` (F5 M6)
- `tests/fixtures/head_list_compound_tagged.clausal` (F5 M6)
- `clausal/logic/cells.py` (F5 M7)

## Not touched

M5, M8, and every DEFER row in the review's table, per triage. Two
untracked files present in the shared clone at session start
(`implementation_plans/subinterpreters-and-cells-2026-09-05.md`,
`todo/r1-revised-separator-us-0x1f-2026-09-05.md`) belong to another
concurrent session — left alone, not staged, not committed (per the
"never `git add -A` in the shared clone" discipline).
