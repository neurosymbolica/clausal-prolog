# Clausal's CLP spans ℝ∪ℤ; clpz is ℤ-only — the `#` family diverges twice

Found 2026-09-09 while landing the ISO canonical comparison builtins
(`feat/iso-compare-builtins-2026-09-09`). Both divergences are PINNED as
`OPEN_iso_divergence` tests in `tests/iso/`, so they are checked facts, not
recollections. Neither is a bug to fix blind — each is a design question.

## 1. Floats

    '#='(1, 1.0)     Clausal: succeeds     Scryer clpz: domain_error

`#=` in Clausal names the behaviour infix `==` already had — the same
`fd_eq` function. Clausal's constraint domain covers reals and integers;
clpz is integers-only, so it rejects the float outright.

## 2. Non-numeric operands (the sharper one)

    '#='(1, foo)     Clausal: FAILS SILENTLY          clpz: domain_error(clpz_expression, foo)
    '#\='(1, foo)    Clausal: SUCCEEDS                clpz: domain_error
    '#<'(1, foo)     Clausal: type_error(orderable, foo)  ctx '(<)/2'
    '#='(X, foo)     Clausal: type_error(evaluable, foo)  ctx '(==)/2'  <- names (==)/2 for a '#=' call

Four spellings of one operand shape, three behaviours. The first is a
DIAGNOSABILITY REGRESSION for migration: a site that used to raise loudly now
fails silently, and silent failure is the hardest kind of wrong answer to
find in a corpus. Spec §1 argues the loud error is the correct behaviour, and
the 33 FORCED corpus sites `#=` exists to serve are exactly the ones most
likely to meet a non-numeric operand — a `type_error(evaluable, date/3)` is
what started this work.

## Why it was not fixed here

Changing it means changing `fd_eq`, which infix `==` compiles to. Two
constraint spellings that disagree would be worse than one that is broader
than clpz. The ruling was: `#=` names an existing behaviour, so pin it and
raise the design question separately.

## The question for the operator

Should Clausal's `#` family (a) stay broader than clpz and accept reals,
(b) narrow to ℤ and match clpz exactly, or (c) keep the domain and at least
make the non-numeric cases raise consistently rather than one of them
failing silently? (c) is separable from (a)/(b) and is the one with a
migration cost attached today.

Minor, whichever way it goes: the `(==)/2` error context is wrong for a
`'#='` call. See [[is-and-eq-are-swapped-relative-to-iso-2026-09-09]].
