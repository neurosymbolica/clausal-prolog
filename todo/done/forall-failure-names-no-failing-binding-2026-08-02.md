# forall failure names no failing binding — the repair loop never learns which element broke

**Filed:** 2026-08-02, from an external authoring harness team.

Measured representative: a prorated-rate authoring run, resumed from an archived
scratch tree. The domain reached a late authoring phase on resume and anchored on a
determinism property test. The goal form is:

```
forall(SUBJECT in SUBJECT_LIST, (...))
```

The test report prints the whole list and:

```
the predicate has no solution for ANY arguments at this point
```

Eight subjects are listed. The one failing subject is never named. An LLM repair loop
anchored on this report for a full attempt budget without being able to identify which
binding to inspect.

## The gap

`forall/2` over a list reports failure at the outer goal level only. When the body
predicate fails for some element, the engine knows which element caused the failure
at the point it occurs, but that binding is not surfaced in the test report. The
producer sees the list (all candidates) and the summary ("no solution for ANY
arguments") — the element-level diagnostic is dropped.

This is the same family as the goal-level wrong-value gap (see
`goal-level-wrong-value-failures-have-no-derivation-2026-08-02.md` in the harness
todo directory): a goal fails logically and the report shows only the outermost
mismatch, not the conjunct that pruned the last candidate.

## Measured incident (exact report shape)

From the archived rerun of a prorated-rate authoring run, the P2 determinism property failure:

```
forall(SUBJECT in SUBJECT_LIST, (...))
  — the predicate has no solution for ANY arguments at this point
  SUBJECT_LIST = [<subject_1>, <subject_2>, ..., <subject_8>]
```

The eight subjects are listed. The failing subject and the body conjunct that rejected
it are absent. The repair prompt repeats this shape every attempt; the model has no
anchor for a targeted fix.

## Candidate designs

**Candidate 1 — re-run body per element on failure (bounded).**
When `forall(X in LIST, Body)` fails, re-run `Body` for each element of `LIST`
(or up to the first N, e.g. first 3) and collect the elements for which `Body` has no
solution. Report them by name in the failure message. This is a diagnostic re-run only,
not a change to `forall`'s semantics or its first-pass evaluation. The bound keeps the
diagnostic cost proportional.

Example target report shape:

```
forall(SUBJECT in SUBJECT_LIST, (...)) — failed for 1 of 8 elements:
  SUBJECT = <subject_3>
  (body goal 2 of 4 failed: ...)
```

**Candidate 2 — expose failing binding lazily in the existing failure trace.**
When `forall` fails, the engine already holds the binding that caused the failure on
the call stack. Surface it in the same `bindings at failure:` block that the
conjunct-level diagnostic already produces for other goal shapes, without a second
evaluation pass. This is a narrower change if the engine's failure trace is accessible
at `forall`'s failure point.

**Candidate 3 — structured forall failure value.**
Represent a `forall` failure as a structured value (failing element + body failure
reason) rather than a string summary, and let the test reporter render it. This is the
cleanest interface contract but requires the report renderer and the `forall`
implementation to agree on the value shape.

Any of the three gives the repair loop the one fact it needs: which element failed.

## Outcome

**Candidate 1 (bounded per-element re-run)** shipped. It is the most self-contained
of the three: it needs no change to `forall`'s semantics, no new value-shape contract
between the reporter and the compiler, and it slots into the existing diagnostic
descent machinery rather than duplicating it — which is what the brief asked for.

Verified against current `main` first: a `forall(X in LIST, Body)` reaches
`clausal/testing.py:_report_nearest` as an ordinary `Call(func=LoadName('forall'),
args=[in_(left=Var, right=[...]), Body])`. Because `forall` resolves to no clauses,
the generic slot/all-holes/descent ladder falls straight through to the bare rung-3
line *"the predicate has no solution for ANY arguments at this point"* — reproduced
exactly as filed. The gap was real and unchanged since the filing snapshot.

**The change**, all in `clausal/testing.py`:

- `_forall_shape(goal)` (≈733) — recognises the exact runtime shape
  `forall(V in LIST, Body)` where LIST is a ground Python list and V is an unbound
  Var; returns `None` (→ generic ladder) for any other `forall` (generator conditions,
  non-list right side, bound loop var).
- `_forall_var_name(reified_goal)` (≈766) — recovers the source name of the loop
  variable (e.g. `SUBJECT`) from the reified `forall` twin, so the report names the
  binding in the author's own vocabulary; falls back to `"the loop variable"`.
- `_report_forall(diag, goal, reified_goal, logic_module, deadline)` (≈780) — the
  diagnostic re-run. For each element it binds the loop var (`Unify(V, element)`) and
  tests whether Body has a solution in the live prefix context, collecting the elements
  for which it does not. On findings it sets the headline
  *"failed for N of M elements:"* and lists each failing binding as `V = <element>`.
- `_report_nearest` (≈876) gains a single early interception:
  `if _report_forall(...): return`.

**Bound.** Reuses the existing descent knobs, per the related-todo convention — no
second budget: the `$CLAUSAL_TEST_DIAG_BUDGET` deadline is checked each iteration, and
at most `DIAG_MAX_DESCENT_LEAVES` (6) failing elements are named. Past that it stops
probing (each probe re-solves Body) and reports *"failed for at least 6 of M elements
(first 6 shown)"* with a truncation note, rather than walking an unbounded list.

**Safe fall-through.** When the re-run finds a solution for *every* element (the
failure came from element coupling or non-determinism, not one element), it returns
`False` and the generic ladder runs unchanged — the verdict is never touched, matching
the module's observation-only invariant.

**Tests.** Four new cases in `tests/test_testing_descent.py` (section "forall(X in
LIST, Body): name the failing element(s)"): single failing element named; several named
within the bound; the bound + truncation note on a 10-element all-fail list; inline
conjunction body (the measured incident's `forall(SUBJECT in LIST, (...))` shape).
Written test-first (all red before the change, green after).

**Suite.** `10875 passed, 2 failed` — the two failures are exactly the documented
standing baseline (`test_F026_multi_star_splits_bounded_for_moderate_input` load-marginal
timing; `test_no_raw_untested_blocks` docs gap). Zero new failures.

No follow-up todo filed — the scope (name the element) is fully covered. A possible
future enrichment (also naming *which body conjunct* rejected the element, as in the
brief's illustrative shape) was left out deliberately: the load-bearing fact the repair
loop needs is the element identity, and the descent machinery already handles
conjunct-level blame for ordinary calls.
