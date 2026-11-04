# writeq/1 puts layout around an alphanumeric default operator where Scryer does not

Found 2026-11-04 while byte-comparing listing/1 with Scryer
(`tests/iso/test_listing_portray_clause_scryer.py`, which keeps this case
out of its programs). Affects every ISO writer (writeq/1, print/1,
write_term/2, listing/1), not listing alone.

## What / Repro

```prolog
t :- X = f(a is -b, a mod -1, a is [x], a is 'B', a is (b,c), (-) is a,
           a is - (1)),
     writeq(X), nl.
```

```
Scryer   f(a is-b,a mod-1,a is[x],a is'B',a is (b,c),(-)is a,a is- (1))
Clausal  f(a is -b,a mod -1,a is [x],a is 'B',a is (b,c),(-) is a,a is - (1))
```

Scryer writes layout next to an alphanumeric infix operator only where the
tokens would otherwise glue (`a is b`, `1 is 2`) and before `(`. Clausal does
that for an operator op/3 defined, but keeps a space on both sides of a
DEFAULT alphanumeric operator (`clausal/terms.py`, the `_WQ_OPS` branch of
the infix case: "A default operator (`` mod ``, `` is ``) keeps its spacing
byte for byte"), a deliberate choice made when the writer learned the
operator table (commit 6bba5d3e), not a ruling.

Both outputs re-read as the same term. A listed clause `C is -A` is
`C is-A` in Scryer's listing/1.

## Options

A. Follow Scryer for the default operators too (operator ruling 2026-09-25,
   "do what Scryer does", would cover it). Changes writeq output wherever a
   default alphanumeric operator meets a symbolic or quoted operand, so
   tests pinning such text move.
B. Keep the current layout and record it as a deviation.

Recommendation: A.
