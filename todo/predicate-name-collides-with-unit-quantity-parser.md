# Predicate name that parses as a unit/quantity crashes at load when self-referenced

Found 2026-07-20 while building repros for
[[tro-signal-flag-clobbered-by-later-match-arms]] (a red herring for that fix,
but a real defect on its own).

## Symptom

A predicate whose name parses as an SI unit / quantity, when that name is
referenced inside a clause BODY (e.g. a self-recursive call), crashes at module
load with:

    TypeError: 'clausal.logic.variables.AttVar' object is not callable

Minimal repro (crashes):

    -module(m, [P(N, X)])
    P(N, X) <- (N > 0, M is N - 1, P(M, X))   # the body ref `P(M, X)` is the trigger
    P(N, X) <- (X is N)

Rename `P` -> `Foo` and it loads and runs fine. The crash is at the module-exec
of the clause whose HEAD is the offending name; the generated code evaluates the
name as a Quantity/AttVar and then tries to call it.

## Which names collide

It is NOT simply "single uppercase letter" and NOT the variable-naming rule
(`Xx`, `Bp`, `Pq`, `Foo` all work as predicates). It tracks the SI-prefix / unit
grammar in `clausal/terms.py` (the `Quantity` constructor — cf. the `Y`=yotta
"SI prefixes cannot be used as units" error seen elsewhere):

    CRASH:  P, PP, Pp, A1, P1        (P=Peta, A=atto/Ampere, digit suffixes, …)
    OK:     Foo, Ab, Xx, Bp, Pq

The exact collision set needs to be read off the unit/prefix tables. A name only
triggers the crash when it appears in a body position that the compiler lowers to
a term-evaluated expression (heads are fine; a name used ONLY as a head, never in
a body, does not crash — e.g. non-recursive `P/1` loads).

## Impact / priority

Low. Real predicate names (multi-letter, non-unit) are unaffected, and the
canonical convention already uses descriptive names. But the error is cryptic —
it gives no hint that the predicate NAME is the problem.

## Fix directions

1. Diagnostic: when compilation of a body call target resolves to a Quantity /
   non-callable, raise a clear error naming the predicate and suggesting a
   rename ("predicate name `P` collides with unit parsing").
2. Or: reserve predicate-name resolution ahead of unit/quantity parsing for
   names that are declared as predicates in the module header.
