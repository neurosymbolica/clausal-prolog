# `('decimal', M, S)` orders as a TERM in compare/3 and msort/2 — silently wrong numeric order

Found 2026-09-16. Demonstrated with a case where mantissa order and value order DISAGREE:

    to_term(Decimal("9.9"))   = ('decimal', 99, 1)
    to_term(Decimal("1.000")) = ('decimal', 1000, 3)      truth: 9.9 > 1.000

    compare(O, 9.9, 1.0)                                 -> ('>',)       control, correct
    msort([9.9, 1.0], L)                                 -> [1.0, 9.9]   control, correct
    compare(O, ('decimal',99,1), ('decimal',1000,3))     -> ('<',)       WRONG, silent
    msort([('decimal',99,1), ('decimal',1000,3)], L)     -> unchanged    WRONG, silent
    sum_list/2 on a decimal term                         -> type_error(number, ...)   loud

The probes reached the builtin through a `++` escape, because a Python Decimal could not be lowered
as a goal literal (`term_to_ast_expr: unsupported term type Decimal`).

Status at the time: LATENT. Nothing auto-converted a Decimal at a crossing (the `++` hook was
reverted at f74d0f61), so the term appeared only when something called `to_term` explicitly. It
would have gone LIVE with any `++` auto-conversion that included Decimal: a narrowed hook turned
exactly one suite row red, `test_sum_list_still_accepts_every_numeric_kind`.

Ruling in force then: the decimal term is first-class; its arithmetic half (evaluator, compare/3,
CLP recognising `('decimal', M, E)` and `('rdiv', N, D)` as NUMBERS) was sequenced with the CLP(Q)
work. compare/3 was the priority item because its failure is silent, while sum_list's is loud.

## The same shapes in Scryer and Trealla (2026-09-17)

Both engines give identical results, so the defect is what ISO standard order does to these
compound shapes anywhere, not an artefact of the Clausal representation:

    date(2023,6,15) @< date(2026,6,15)      correct
    date(2023,12,1) @< date(2024,1,1)       correct   (carry across the year)
    decimal(99,1)   @> decimal(1000,3)      WRONG     9.9 > 1.000, mantissas order opposite
    rdiv(1,2)       @> rdiv(1,3)            WRONG     1/2 > 1/3, denominators order opposite

    A is 1 rdiv 2, B is 1 rdiv 3, A @> B    correct   evaluation makes it a number
    rdiv(1,2) @> rdiv(1,3)                  WRONG     the unevaluated compound

A term is mis-ordered by `@<` exactly while it remains a COMPOUND; evaluation moves it into the
number region. Standard order is chronologically right for `date(Y,M,D)` only because its
arguments are most-significant-first on one scale, which is a property of dates, not of compound
terms.

## 2026-09-17 design session

Design: `docs/superpowers/specs/2026-09-17-rdiv-decimal-arithmetic-design.md`. It recommends the
ordering GUARD first (numeric order key and an evaluator leaf for the two cells), then option B
(numbers stay Python number objects; the cells are transfer forms and source spellings, so a cell
never survives as a compound). Also measured then: the evaluator refused a Python Decimal leaf.

## CLOSED 2026-10-07 (re-measured on bf67d2e7)

Fixed by e52a3171 (2026-09-17, "order guard: decimal/rdiv cells order and evaluate as the numbers
they denote"), an ancestor of main. Re-measured from a Clausal Prolog (`.clausal`) module:

    compare(O, rdiv(1,2), rdiv(1,3))               -> '>'   (structural order would give '<')
    compare(O, decimal(99,1), decimal(1000,3))     -> '>'   (structural order would give '<')
    msort([decimal(99,1), decimal(1000,3)], L)     -> [decimal(1000,3), decimal(99,1)]   numeric
    compare(O, 9.9, 1.0)                           -> '>'   control
    A is rdiv(1,2), B is rdiv(1,3), compare(O,A,B) -> '>'   control

Each wrong answer the probe would catch is the one this note recorded. The Scryer and Trealla rows
above describe those engines' own standard order and are kept as history; they are not defects of
ours.
