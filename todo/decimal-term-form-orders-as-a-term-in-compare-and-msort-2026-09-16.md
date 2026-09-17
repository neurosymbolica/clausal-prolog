# `('decimal', M, S)` orders as a TERM in compare/3 and msort/2 — silently wrong numeric order

Reported by harness-batch-lane [803e60] 2026-09-16, measured on feat/iso-l3-lowering-2026-09-14
(worktree at ad63a18c). Fixtures (no harness, nothing sealed):
/workspace/_date-probe-artifacts/decimal_transfer_form_fixture.py <engine-tree>
/workspace/_date-probe-artifacts/sumlist_numeric_kinds_fixture.py <engine-tree>
Both reach the builtin through a `++` escape, because a Python Decimal cannot be lowered as a goal
literal (`term_to_ast_expr: unsupported term type Decimal`) and a compile-route fixture fails at the
wrong door.

Demonstrated with a case where mantissa order and value order DISAGREE:

    to_term(Decimal("9.9"))   = ('decimal', 99, 1)
    to_term(Decimal("1.000")) = ('decimal', 1000, 3)      truth: 9.9 > 1.000

    compare(O, 9.9, 1.0)                                 -> ('>',)       control, correct
    msort([9.9, 1.0], L)                                 -> [1.0, 9.9]   control, correct
    compare(O, ('decimal',99,1), ('decimal',1000,3))     -> ('<',)       WRONG, silent
    msort([('decimal',99,1), ('decimal',1000,3)], L)     -> unchanged    WRONG, silent
    sum_list/2 on a decimal term                         -> type_error(number, ...)   loud

Status: LATENT. Nothing auto-converts a Decimal at a crossing (the ++ hook was reverted at f74d0f61),
so the term appears only when someone calls to_term explicitly. It goes LIVE the moment any ++
auto-conversion that includes Decimal lands — which is how it was found: a narrowed ++ hook
(registry's non-tuple entries only) turned exactly one suite row red,
`test_sum_list_still_accepts_every_numeric_kind`; restricting the hook to the date family made the
failure set byte-identical to baseline.

Also CLOSED, not to re-fix: the 2026-09-11 sum_list/2 regression — `_summable` uses numbers.Number
and Fraction+Fraction / Decimal+Decimal both sum correctly on canonical c69a59b9 and on the branch.

RULING ALREADY IN FORCE (section-4 answer, "RULED 2026-09-14: dates and decimals are TERMS" and
"rdiv/decimal: the TERM half is free; the arithmetic half collides with a parked branch"): the
decimal term IS first-class — the shape is ruled and the arithmetic half (evaluator, compare/3,
CLP recognising ('decimal', M, E) and ('rdiv', N, D) as NUMBERS) is REAL WORK sequenced WITH the
CLP(Q) C port (feat/clpq-c-port-2026-09-13), not against it. The quantity ruling went the OTHER
way (object with a transfer form) and is not the twin of this one.

Consequences:
* ++ auto-conversion of Decimal is not wrong in principle; it is wrong BEFORE the arithmetic half
  lands. The Decimal exclusion in the narrowed hook is the correct sequencing, not a workaround.
* When the arithmetic half is built, compare/3 (standard order) is the priority item because its
  failure is silent; sum_list's is loud. Standard order for decimal/rdiv terms must be NUMERIC
  (the term lives in the number region of the standard order), and the ISO standard-order branch
  (feat/iso-standard-order-2026-09-09, not landed) is where that comparison lives.
* Until then the loud refusal is the guard, and a test should pin that compare/3 on two decimal
  terms is at least not silently mantissa-ordered — either numeric or an error.

Kept so the measurement is not lost (harness-batch-lane, 2026-09-16): a NARROWED ++ hook — the
registry's non-tuple entries only, the tuple entry never consulted, so the seam-built-vs-user tuple
ambiguity that forced the f74d0f61 revert is never reached — is measured clean on ad63a18c for the
DATE FAMILY (full-suite failure set byte-identical, red-then-green positive control). Patch + control
test: /workspace/_date-probe-artifacts/probe-engine.patch. Not proposed by them; the harnesses do not
use the ++ door. Under the sequencing above it becomes correct for Decimal only after the arithmetic
half lands. Any engine change that moves what compare/3 does to a term the sealed bodies handle goes
to harness-batch-lane as a QUESTION first (82-row answer diff, ~3 min; baseline 82/82 unchanged on
canonical c69a59b9, reference committed on their side).

## Measured in the two EXPORT engines, 2026-09-17 (iso-export-lane)

This todo carried a Clausal-side measurement only. The same defect is present in both
ladder engines, identically, so it is not an artefact of the Clausal representation —
it is what ISO standard order does to these shapes anywhere:

```
scryer AND trealla, identical results:

    date(2023,6,15) @< date(2026,6,15)      CORRECT
    date(2023,12,1) @< date(2024,1,1)       CORRECT   (carry across the year)
    decimal(99,1)   @> decimal(1000,3)      WRONG     9.9 > 1.000, mantissas order opposite
    rdiv(1,2)       @> rdiv(1,3)            WRONG     1/2 > 1/3, denominators order opposite
    9.9 > 1.000                             correct   (float control)
```

**THE DISTINCTION THAT BOUNDS THE FIX — evaluated versus unevaluated.** Also measured, both
engines:

```
    A is 1 rdiv 2, B is 1 rdiv 3
      A @> B                    CORRECT     <- evaluation put it in the NUMBER region
      A >  B                    CORRECT
      number(A)                 true        <- not a compound at all
    rdiv(1,2) @> rdiv(1,3)      WRONG       <- the unevaluated compound
```

So the rule is sharper than "decimal and rdiv are dangerous under standard order": **a term
is mis-ordered by `@<` exactly while it remains a COMPOUND, and evaluation is what moves it
into the region where standard order is numeric.** That is what makes the engine-side ruling
(decimal/rdiv belong in the number region) the correct shape rather than one option among
several — it makes the compound behave as evaluation already does.

**Consequence for a helper that must be safe:** compute with `is/2` and the output is a
number by construction, so it orders correctly without relying on the ruling landing. The
export side's `quantity_number/2` (executor-train `cdf0b6d`) is safe on exactly that basis,
and the reason is recorded in its header rather than left to luck.

**Currently latent on the export side: ZERO `decimal(M,S)` or `rdiv(N,D)` terms appear in
staged output.** Cheapest to fix before something starts emitting them — a wrong ORDER
reverses a threshold test and raises nothing, which is worse than a wrong value.

**And a note for whoever lowers the date comparisons.** ISO standard order IS chronologically
correct for `date(Y,M,D)`, and the reason is that its arguments are most-significant-first and
all on one scale. That is a property of DATES, not of compound terms. Do not generalise it to
decimal or rdiv on the strength of the date case — the three rows above are what that
generalisation produces.
