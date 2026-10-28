# Clausal's CLP spans ℝ∪ℤ; clpz is ℤ-only — the `#` family diverges twice

**Status: PARTLY RESOLVED (2026-10-28).** §2 and the minor point are fixed (2026-09-30, the `#` family's own operand check, `clpfd.clpz_refuse_non_numeric`): on the `.pl` and seam surfaces alike `'#='(1, foo)`, `'#\\='(1, foo)`, `'#<'(1, foo)` and `'#='(X, foo)` all raise `domain_error(clpz_expression, foo)` with the comparison's own indicator (`(#=)/2`, ...), never `(==)/2`; Scryer's context is its library's internal `unknown(foo)-1`, a recorded convention difference. Pinned in tests/iso/test_iso_compare_errors.py and tests/iso/test_iso_alignment_arg_clpz_number_chars.py. §1 (floats) is still open and needs a ruling -- see "Status 2026-10-28" at the end.

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


## Status 2026-10-28: §1 (floats) needs a ruling

Re-measured against Scryer (`/workspace/scryer-prolog-clpq`, `library(clpz)`):
every float operand of the `#` family is `domain_error(clpz_expression, F)`
in Scryer -- `'#='(1, 1.0)`, `'#\\='(1, 1.0)`, `'#<'(1, 2.0)`, `X #> 1.0`,
`X #= Y + 1.0`, `1.0 #= X`, `X #\\= 1.5`, `X in 1..3, X #= 2.0`.  Clausal:
`'#='(1, 1.0)`, `'#<'(1, 2.0)`, `X #> 1.0, X = 3`, `1.0 #= X` and
`X #\\= 1.5` SUCCEED (CLP(R) dispatch), `'#\\='(1, 1.0)` and
`X #= 1.5, X = 1` FAIL, `X #= Y + 1.0` raises the right formal with an
unbound context, and a reified `B #<==> (X #= 1.0)` already raises
Scryer's formal.

Not changed here, because making the `#` family integer-only is not a local
fix: it is DOCUMENTED that `#=` dispatches to CLP(R) on a float and to
CLP(Q) on a rational (docs/clpq.md, "Dispatch table": "`X #= 5.0` (no
declaration) | CLP(R): float literal triggers R dispatch"), and Clausal
Prolog programs use it (tests/fixtures/docs/clpr_examples.clausal,
tests/fixtures/docs/constraints_sig_tests.clausal: `X * X #= 2.0`).  There
is no surface distinction at the builtin: `.pl` and `.clausal` reach the
same `#=`.

Options:

- (a) The `#` family is integer-only everywhere (Scryer exactly): a float
  or rational operand raises `domain_error(clpz_expression, F)`; CLP(R)
  and CLP(Q) are reached only through `{}/1` (as in Scryer/SICStus) and the
  seam's `==`.  Breaking for `.clausal` programs and docs that post reals
  with `#=`.
- (b) Integer-only on the ISO `.pl` surface only: the native front end binds
  `#=`/... to a strict variant (or the loaded `library(clpz)` does), the
  `.clausal` surface keeps the documented CLP(R)/CLP(Q) dispatch.
  Conforming where conformity is measured, at the price of one name with
  two behaviours across surfaces.
- (c) Keep it broader than clpz everywhere, and only make the two odd
  answers consistent (`'#\\='(1, 1.0)` and `X #= 1.5, X = 1` should then
  succeed/fail as CLP(R) says, `X #= Y + 1.0` should name `(#=)/2`).

Recommendation: (a) for `.pl` and `.clausal` alike is the cleanest reading
of ruling 2026-10-24, since `{}/1` already covers CLP(R)/CLP(Q) on every
surface; (b) if the documented `#=`-over-reals of `.clausal` must stay.

## Ruling 2026-10-28, and why it is not landed yet

Operator ruling (2026-10-28, relayed): option (a), "INTEGER-ONLY everywhere,
matching Scryer. A float operand in #=, #\=, #<, #=<, #>, #>= (and in their
reified forms) raises error(domain_error(clpz_expression, F), Context) with
Scryer's context, on BOTH .pl and .clausal. CLP(R)/CLP(Q) are reached only
via {}/1."

Implemented on branch `wip/clpz-integer-only-2026-10-28` (commit 571697a7,
pinned by tests/iso/test_clpz_float_operands_scryer.py against Scryer), but
held back: the ruling assumes `{}/1` reaches CLP(R), and in Clausal it does
not.

- `{}/1` is CLP(Q): `{X = 5.0}` gives `X = 5` (the float read as an exact
  rational), and a non-linear `{X*X = 2.0}` raises a Python
  `TypeError('CLP(Q) requires linear constraints')`.  Scryer's
  `library(clpr)` `{X = 5.0}` gives `X = 5.0`.
- An `in_real` variable under the `#` family with integer operands does not
  propagate: `in_real(X, 0.0, 2.0), X*X #= 2` leaves X in 0.0..2.0 and
  `in_real(X), 2*X #= 7` leaves X unbounded (the same on 285bdb8e).

So with the float operand refused, Clausal Prolog has no working route to
CLP(R), and the CLP(R) examples (docs/clpr.md, docs/constraints.md's CLP(R)
section, tests/fixtures/docs/clpr_examples.clausal,
tests/fixtures/docs/constraints_sig_tests.clausal) have nothing to be
rewritten to.  One of these has to come first: `{}/1` over the reals (as
Scryer's `library(clpr)`: a float in `{}` dispatches to CLP(R)), or the `#`
family propagating over `in_real` variables with integer operands.
