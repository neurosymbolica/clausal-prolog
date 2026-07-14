# Dict subscript read `V is P[key]` — evaluate over DictTerm, throw on missing key

**Part of:** [dict-native-profile-api.md](dict-native-profile-api.md) · **Order:** 1 (foundational read)

## Goal
`V is P[filing_status]` where `P` is a `DictTerm`:
- key present → bind `V` to the stored value (a `Var` value participates in unification);
- key **absent** → **throw** a Clausal error (Python `KeyError` analogue), NOT silent fail.

Ground key required (atom/str/int); a non-ground key index is an error (matches the prover's ground-key
constraint and Python's hashable-key rule).

## Where
- Parser already lowers `P[k]` to a `LoadSubscript` node (`clausal/templating/term_rewriting.py:1064-1069`).
- Wire `LoadSubscript` evaluation to `DictTerm.__getitem__` (`clausal/terms.py:1657`) under `is/2`
  evaluation. Confirm the `is/2` evaluator treats `LoadSubscript` as an evaluable RHS (like it does list
  construction), rather than leaving it a literal structure.
- Throw path: raise the standard Clausal runtime error type used for builtin failures-that-are-errors
  (match whatever `throw/1` surfaces, so `catch/3` can intercept).

## Acceptance
New tests in `clausal/tests/` (first DictTerm-read coverage in the repo):
- `V is {a: 1, b: 2}[a]` binds `V=1`; `[b]` binds `2`.
- value-var: `X is {a: V}[a]` then unify `V=7` ⇒ `X=7`.
- missing key `{a:1}[z]` **throws** (assert the error is catchable via `catch/3`).
- non-ground key index errors cleanly.
