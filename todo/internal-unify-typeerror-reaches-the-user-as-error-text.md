# `functor/3` can surface a raw internal `__unify__()` TypeError as the error text

**Filed:** 2026-07-30, from study-12 run logs in
`/workspace/clausify-executor-train/_reruns/`.
**Status: OBSERVED IN THE FIELD, NOT REDUCED.** See "What I could not reproduce"
before spending time on it — this may already be fixed.

## What was seen

```
FAILURES:
  test_load.clausal:57 :: cite term constructs correctly — _make_unify.<locals>.__unify__() missing 1 required positional argument: 'trail'
    goal 2 of 2 raised:
      functor(CITE_TERM, eu.schengen_90_180_max_stay.citations.cite, 1)
      TypeError: _make_unify.<locals>.__unify__() missing 1 required positional argument: 'trail'

4 tests: 3 passed, 1 failed [FAILED]
```

The authored source of that test (model-written, so treat the *input* as
arbitrary — the complaint is about the *output*):

```clausal
Test("cite term constructs correctly") <- (
    CITE_TERM is cite(eu_reg_2016_399_art_6_1),
    functor(CITE_TERM, FUNCTOR_NAME, ARITY),
    FUNCTOR_NAME is cite,
    ...
```

Note the rendered goal is post-binding — the diagnostic substitutes the values
live at the raise, so `FUNCTOR_NAME`/`ARITY` appear filled in. The call in
source is decomposition mode (both free), not verification mode. Don't chase
the wrong mode on the strength of the rendered line.

`cite` here is a package-qualified atom
(`eu.schengen_90_180_max_stay.citations.cite`) imported into the test module,
so the call crosses a package boundary. That is the one feature the failing
case has that none of my repros did — start there.
Related: [[functor-identity-leaks-across-modules-in-one-process]].

## Why it is worth fixing regardless of the trigger

`_make_unify.<locals>.__unify__() missing 1 required positional argument:
'trail'` names a closure inside the engine and a parameter the user cannot see,
has never written, and cannot act on. Whatever the caller did wrong, an
internal Python `TypeError` is not an acceptable user-facing error — and
clausal already has the right shape of error for the neighbouring case
(`PredicateArityMismatchError: assess takes 6 arguments, but this call
passes 3` appears in the same corpus). Either the call is legal and this is an
engine bug, or it is illegal and it should raise a named clausal error.

Cost of the current behaviour, measured: **10 attempts across 2 runs, neither
recovering.** `study_schengen_max_stay_r2` burned 7 attempts at P3a3 over 89
minutes on it and terminated stuck; `study_working_time_average_r1` burned 3 at
P3b. A local 27B model given this message has nothing to act on, so it edits at
random until the attempt budget runs out.

## What I could not reproduce

Three minimal repros, all **PASS** at pin `9f3f0720`:

1. `-private([cite(X)])` + `functor(T, cite, 1)` (construction mode)
2. `-module(cits, [cite])` + `-import_from(cits, [cite])` + `functor(T, cite, 1)`
3. `T is cite(1), functor(T, NAME, ARITY)` (decomposition mode, private atom)

A fourth attempt at the package-qualified form was blocked by an unrelated
`strict_atoms` error on the test harness scaffolding I wrote, so the actual
distinguishing case is still untested.

The run predates the `clausal_sha` provenance field on the formalizer side, so
the exact engine revision it ran against is **unrecorded**. `/workspace/clausal`
was at `297e506f` (2026-07-24) around the study and `9f3f0720` by 2026-07-30, so
the fix may already be in. First step for whoever picks this up is to reproduce
against the scratch tree preserved at
`/workspace/clausify-executor-train/_reruns/study_schengen_max_stay_r2/scratch/`,
which still holds the failing `eu/schengen_90_180_max_stay/tests/test_load.clausal`
and its package. If it passes there at HEAD, close this as already-fixed and
say which commit did it.
