# Non-integer arithmetic: no operator set exists, and what to do about it

**Filed 2026-09-13 by engine-lane.** Measured against the real binaries throughout. This is the
residue of the `#=` ruling meeting fractional money.

## What is actually available — measured, both reference engines

    library(clpz)   Scryer YES   Trealla YES
    library(clpb)   Scryer YES   Trealla YES
    library(clpq)   Scryer existence_error   Trealla WARNS and provides nothing ({}/1 missing)
    library(clpr)   same

**Neither shipped engine has usable CLP(Q) or CLP(R).** Trealla's `use_module(library(clpq))`
prints no error and the library is absent — a first probe reported it as present because the
program still RAN. Ask whether the library loaded, not whether the file ran.

## `#=` is integer-only in the STRONG sense — it fails, it does not complain

    X #= 10/5      ->  2               exact division binds
    X #= 10/3      ->  GOAL FAILS      no rational, no residual, no error
    X * 3 #= 10    ->  GOAL FAILS      same, backward
    X #= 155.05    ->  GOAL FAILS

Identical in both engines. Markus Triska, via the operator: **`#=/2` et al mandate integer
arithmetic throughout.**

**This is the dangerous shape for a legal rulebase.** An exported rule doing `Rate #= Total/Count`
does not error and does not warn — it silently does not fire, so the rulebase yields NO ANSWER.
That is harder to notice than a wrong number, because "no answer" also looks like "the rule
correctly did not apply".

## The operator's ruling, RELAYED via iso-export-lane 2026-09-13

CLP(Q) uses `{...}`. Clausal's `{}` is a **set literal**, so: **a set in goal position is a set of
CONSTRAINTS, and calling the goal solves them.** Fractional money goes to CLP(Q) through `{...}`.
A construct the language already has, reinterpreted rather than invented.

**Recorded as RELAYED, not direct.** The operator separately raised an `arithmetic(...)` wrapper
with engine-lane, following the `z3.` precedent, minutes before this relay arrived. The two are
not the same surface. **Whoever implements should get the surface confirmed directly** rather than
pick one from two second-hand accounts.

## The precedent the operator pointed at: `z3.`

`docs/z3.md` — the solver is a MODULE and its operations are module-qualified goals:

    z3.minimize(2 * Bread + 3.5 * Milk, Cost),
    z3.maximize(X + Y, Cost),  z3.check(),  z3.entailed(...), z3.all_different(...)

Note `3.5 * Milk`: **the Z3 wrapper already carries non-integer arithmetic.** The shape is
qualification, not new operators — the enclosing goal names which solver interprets the
expression, so there is no need for a `#=`-alike per numeric domain. Engine module is `clpz3.py`
while the surface is `z3.`, so surface and implementation names already differ here.

## THE FLOAT TRAP — this decides the emission (iso-export-lane, on a clpq build)

    {X = 155.05}       ->  2727668446186701 rdiv 17592186044416    WRONG
    {X = 15505/100}    ->  3101 rdiv 20                            EXACT
    {10.5 = X + 4.25}  ->  25 rdiv 4                               correct, backward

A float LITERAL is converted to its binary-float rational before clpq sees it. **Emission must be
the RATIO, never the decimal.** Currency is an exact `Fraction` engine-side since `d2411c72`, so
numerator and denominator are both in hand; this is about not flattening them on the way out.

The two paths are then symmetrical and neither goes through a float:

    integral money     V #= 15505          clpz
    fractional money   {V = 15505/100}     clpq

## GATING FACT

**CLP(Q) is in neither ladder engine.** It exists in a branch build at
`/workspace/scryer-prolog-clpq` (ships `clpq.pl`, `clpr.pl`). So the emission would depend on a
capability the ladder does not test. iso-export-lane is raising this with the operator.

## Ownership

Surface + engine: engine-lane. Emission + the `#=` conversion: iso-export-lane. The float trap
binds both.
