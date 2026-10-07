# Verify the ISO form answers the same as the seam form

Opened 2026-09-18: once a program is exported from the seam form to Clausal ISO form, check that
the exported `.pl`, loaded NATIVELY (nothing translated back), gives the same answer sets as the
seam module it came from. A disagreement would then indict the two forms, not a translator in
between.

An exported module already loaded back into Clausal and defined every predicate the seam module
did. Two engine gaps blocked running its queries.

## GAP 1 (engine): relative module paths did not resolve

The export emits a filesystem-relative path, correctly for Prolog, e.g.:

```prolog
:- use_module('../../../lib/helper', [twice/2]).
```

Loading such a path failed with `SyntaxError: invalid syntax (..., line 6)`. Rewriting the path to a
plain module name made the module load with all predicates present.

## GAP 2 (engine): a bare compound data term needed declaring

With gap 1 worked around, a query failed with:

```
NameError: Predicate 'attribute/2' is not in scope as a term class.
```

`attribute/2` is only ever built as data, never defined. ISO needs no declaration for that; the
strict regime did.

## The comparison as specified

For each program: run its public queries over its own fixtures in the seam form and in the
natively loaded `.pl`, and compare the answer SETS, not counts or pass/fail. Assert which form
actually ran, include a negative control (a perturbed clause must be caught), and print the
denominator (programs, goals, answers).

## CLOSED 2026-10-07 (re-measured on bf67d2e7)

Both blocking gaps are gone:

- GAP 1: a `.pl` module whose `:- use_module('../../../lib/helper', [twice/2]).` names a
  filesystem-relative path loads, and the imported predicate answers (`go(Y)` -> `[42]`).
- GAP 2: a compound built only as data and never declared (`T = attribute(colour, red)`) answers
  `[attribute(colour, red)]`, with no "not in scope as a term class" error (Clausal Prolog is
  non-strict).

The note's purpose was overtaken by the migration itself: programs moved to Clausal Prolog with the
extension flip (701c44ec, 2026-10-03), and the seam target was retired (ruling R1), so no seam form
is left to compare against. NOT claimed here: that a per-program seam-vs-exported-`.pl` answer-set
comparison as specified above was ever run. If one is still wanted, it is a new todo against the
retired seam form, not this one.
