# `'='`/2 and `'is'`/2 conflate int and float (ISO says they must not)

Filed 2026-09-09, from the ISO canonical comparison builtins branch
(`feat/iso-compare-builtins-2026-09-09`). The `'is'`/2 half is CLOSED
2026-10-15 (see "`'is'`/2 half: CLOSED 2026-10-15" below); the `'='`/2 half
remains OPEN, deliberately deferred.


**Status: FIXED 2026-10-23 (operator ruling 2026-10-23, ISO 7.3).** The `'='`/2
half is closed: `unify` itself (`clausal/logic/variables/_variables.c`,
`numeric_kind` and the arm before its `==` fallback) refuses a number against a
number of another kind -- int, float, complex, Decimal (with its scale) and
Fraction, the kinds `'=='`/2 already kept apart, spelled once in
`clausal/logic/number_kinds.py` -- so `'='(1, 1.0)`, `f(1) = f(1.0)`,
`X = 1, X = 1.0`, `[1] = [1.0]`, `p(1.0)` against `p(1)`, `retract(q(1.0))` of
`q(1)` and `X #= 1, X = 1.0` fail and `dif(X, 1.0), X = 1` succeeds, as Scryer
answers, on `.pl`, `.clausal` and the seam alike. `structural_eq`'s atomic fast
path, the constant-list membership set, setof/3's dedup, Decimal head literals
and the tabling variant keys follow the same rule (the "one change" this file
asked for). The former OPEN pin is
`tests/iso/test_iso_compare_scryer.py::test_iso_unify_int_float_distinct_CLOSED_2026_10_23`;
the matrix is `tests/test_iso_int_float_unify.py` (three surfaces, the API,
the keys) and `tests/iso/test_int_float_unify_scryer.py` (against Scryer).
This supersedes the A01-D001 (c) split of 2026-07-07 ("keep `1 == 1.0`"); the
`'#='` pin `test_hash_eq_int_float_OPEN_iso_divergence` is a separate question
(`fd_eq` routing a float operand to CLP(R)) and stays open.

## The divergence

ISO unification never unifies terms of different types, so `1 = 1.0` fails and
`7.0 is 3 + 4` fails. Clausal's `'='`/2 is `clausal.logic.variables.unify`
verbatim and `'is'`/2 ends in the same `unify`, so both succeed.

Measured 2026-09-09 — engine from the branch worktree, oracle
`/workspace/scryer-prolog/target/release/scryer-prolog`:

| goal | Clausal | Scryer |
|---|---|---|
| `'='(1, 1.0)` | yes | no |
| `'is'(7.0, 3 + 4)` | yes | no |
| `'is'(7, 3 + 4)` | yes | yes |
| `'=='(1, 1.0)` | no (ISO-correct, fixed on this branch) | no |
| `structural_eq(1, 1.0)` | yes (pre-existing, PARKED) | — |

## Why it is deferred rather than fixed

ISO `=`/2 IS unification — there is no wrapper that makes `'='`/2 ISO-correct
without narrowing `unify` itself, and `unify` has a very large number of
existing callers throughout the engine: every clause-head match, every
`is`-as-unification site in `.seam` source, ISO `is`/2's result unification in `.clausal`/`.pl` (where `1 = 1.0` and `7.0 is 3 + 4` also succeed, checked 2026-10-05), `'\='`/2's own trial-unify,
`dif`/2, tabling answer unification, the CLP posting paths. Narrowing its
cross-type numeric behaviour is an engine-wide semantic change and is the
operator's call, not a comparison-builtins branch's.

It is also entangled with two decisions already parked in the same direction:

* `structural_eq`'s int/float conflation (A05-D001 / A01-D001,
  `todo/done/fix-A05-structural-eq-asymmetry-consistency.md`:
  "do not change direction here, only keep it consistent with whatever unify
  does"). Narrowing `unify` without `structural_eq` breaks that consistency
  rule; narrowing both is a much bigger change again.
* `'#='(1, 1.0)`, which succeeds because `fd_eq` routes a float operand to
  CLP(R). `'#='` NAMES the behaviour infix `==` already has, so changing it
  changes infix `==`.

`'=='`/2 was fixable on the branch precisely because it is a BRAND NEW
predicate with zero existing callers, so it could be made ISO-correct without
touching anything else. `'='` and `'is'` have no such freedom.

## Which one matters

`'is'`, by a wide margin. Spec §2 of
`docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md`
records that the ISO-`is/2` role is played today by `==` at **826 corpus goal
positions**, against a handful for `'='`. Migration puts those sites on
`'is'`, so `'is'` is the spelling that will actually meet a float where an
integer was meant. The `'='` instance is the one that reads more naturally in
a bug report; the `'is'` instance is the one that will be hit.

## Where the pins live

Both were characterization tests in `tests/iso/test_iso_compare_scryer.py`,
engine half and oracle half:

* `test_iso_unify_conflates_int_and_float_OPEN_iso_divergence` (+ `_oracle`)
  — still OPEN, still characterizing the current (diverging) behaviour.
* `test_iso_is_conflates_int_and_float_OPEN_iso_divergence` (+ `_oracle`)
  — CLOSED 2026-10-15, renamed
  `test_iso_is_type_sensitive_int_float_CLOSED_2026_10_15` (+ `_oracle`),
  now asserting the FIXED (ISO-correct) direction. See "`'is'`/2 half:
  CLOSED 2026-10-15" below.

The surviving `'='`/2 pin documents the current behaviour rather than
blessing it: a change in either direction becomes a visible, deliberate
decision instead of a silent regression. The related `'#='` pin is
`test_hash_eq_int_float_OPEN_iso_divergence` in the same file, still open.

## What closing the `'='`/2 half would take

An operator ruling on whether `unify` narrows engine-wide, then (in one
change, to keep A05-D001's consistency rule) `unify`, `structural_eq` and the
CLP posting path together, with downstream code re-run. Out of scope for the
comparison-builtins branch, which changed no engine behaviour at all.

## `'is'`/2 half: CLOSED 2026-10-15

Fixed ahead of the Ulrich Neumerkel presentation, from a Ciao `iso_tests`
sweep hit (`is_test4`, `3 is 3.0` — asserted `fails`). Rather than narrow
the shared `unify` (still out of scope, per "What closing the `'='`/2 half
would take" above), `_iso_is` (`clausal/logic/builtins/iso_compare.py`)
now runs `_numeric_types_agree` — the same cross-type-numeric guard
`'=='`/2 already used for the identical question — on `(Result, Value)`
BEFORE calling `unify`: a Result already bound to a numeric leaf of a
DIFFERENT numeric kind than the evaluated expression fails `is`/2 outright,
while an unbound Result is untouched (the guard raises no objection to an
unbound variable) and binds exactly as before. This closes only `is`/2;
`'='`/2 itself is UNCHANGED and still conflates int/float, so
`test_iso_unify_conflates_int_and_float_OPEN_iso_divergence` (just below)
is still open and still pinning the old behaviour.

The former `test_iso_is_conflates_int_and_float_OPEN_iso_divergence` (+
`_oracle`) is renamed
`test_iso_is_type_sensitive_int_float_CLOSED_2026_10_15` (+ `_oracle`) and
now asserts the FIXED direction. The fuller matrix (both numeric
directions, matching-kind cases, the unbound-left-argument case that must
stay unaffected) lives in
`tests/iso/test_is_type_sensitivity_and_cyclic_unify_ulrich.py`, alongside
an unrelated same-day fix (a cyclic-term `RecursionError` in plain
`'='`/2 / `'\='`/2, Ciao `unify_test16` / `not_uni_test15`).

This does NOT touch `structural_eq`'s or `'#='`'s int/float conflation
(both still PARKED, per "Why it is deferred rather than fixed" above) —
`_numeric_types_agree` is a pure, pre-existing guard already used
elsewhere (`'=='`/2); nothing about ITS behaviour changed, only where it is
now also called from.
