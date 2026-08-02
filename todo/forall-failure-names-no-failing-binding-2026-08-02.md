# forall failure names no failing binding — the repair loop never learns which element broke

**Filed:** 2026-08-02, from the formalizer-training harness team (clausify-executor-train).

Measured representative: `vat_pro_rata_deduction_r2` (`_reruns/resume_vat_r2`). The
domain reached P4 on resume and anchored on a P2 determinism property test. The goal
form is:

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

From `_reruns/resume_vat_r2`, the P2 determinism property failure:

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
