# `'='`/2 and `'is'`/2 conflate int and float (ISO says they must not)

Filed 2026-09-09, from the ISO canonical comparison builtins branch
(`feat/iso-compare-builtins-2026-09-09`). OPEN, deliberately deferred.

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
`is`-as-unification site in `.clausal` source, `'\='`/2's own trial-unify,
`dif`/2, tabling answer unification, the CLP posting paths. Narrowing its
cross-type numeric behaviour is an engine-wide semantic change and is the
operator's call, not a comparison-builtins branch's.

It is also entangled with two decisions already parked in the same direction:

* `structural_eq`'s int/float conflation (A05-D001 / A01-D001,
  `todo/audit-2026-07-05/done/fix-A05-structural-eq-asymmetry-consistency.md`:
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

Both are characterization tests in
`tests/iso/test_iso_compare_scryer.py`, engine half and oracle half:

* `test_iso_unify_conflates_int_and_float_OPEN_iso_divergence` (+ `_oracle`)
* `test_iso_is_conflates_int_and_float_OPEN_iso_divergence` (+ `_oracle`)

They document the current behaviour rather than blessing it: a change in
either direction becomes a visible, deliberate decision instead of a silent
regression. The related `'#='` pin is
`test_hash_eq_int_float_OPEN_iso_divergence` in the same file.

## What closing this would take

An operator ruling on whether `unify` narrows engine-wide, then (in one
change, to keep A05-D001's consistency rule) `unify`, `structural_eq` and the
CLP posting path together, with downstream code re-run. Out of scope for the
comparison-builtins branch, which changed no engine behaviour at all.
