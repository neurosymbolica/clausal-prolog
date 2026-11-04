# listing/1 prints the compiler's head patterns and loses variable sharing

Found 2026-11-04 while fixing
`todo/done/clause-terms-partial-list-head-is-a-head-pattern-2026-11-04.md`.
Needs an operator ruling on the output format (see Options).

## What / Repro

```prolog
:- dynamic(p/2).
p([H|T], H-T).
p([a,[b|T]|T], f("ab")).
p(X, Y) :- X = [Y|Z], w([x|Z]).
w(_).
```

`clausal t.pl -g "listing(p/2)"` prints

```
% p/2 — 3 clause(s)
p([_0, StarUnpack((2, 5, 2, 6), _1)], -(_, _)).
p([a, [b, StarUnpack((3, 8, 3, 9), _2)], StarUnpack((3, 11, 3, 12), _2)], f("ab")).
p(_3, _4) <- (=(_3, [_4, StarUnpack((4, 18, 4, 19), _5)]), w([x, StarUnpack((4, 27, 4, 28), _5)])).
```

Three defects:

1. A partial list prints as the compiler's head pattern node
   (`StarUnpack(...)`), not `[H|T]` (or the seam's `[H, *T]`).
2. Variables inside a compound argument print as `_` (`term_str`'s
   anonymous spelling), so `H-T` lists as `-(_, _)`, losing that they are
   the head's `_0` and `_1`.
3. An ISO (`.pl`/`.clausal`) clause lists in the seam's syntax (`<-`).

`listing/1` (`clausal/logic/builtins/io.py`, `_format_clause`) formats the
STORED clause (head pattern plus lowered body goals), not the clause as a
term. clause/2 and retract/1 read clauses through
`clause_ops.clause_terms`, which since the fix above hands back proper
terms; listing/1 does not use it.

## Options

A. Print each clause the way Scryer's listing/1 does
   (`portray_clause/1`): `clause_terms` gives `(Head, Body)`, printed with
   writeq and lettered variables (`p([A|B],A-B).`). ISO-surface modules
   would then list in ISO syntax; seam modules need a seam spelling of the
   same terms (or keep today's dump). Changes every listing/1 line, so
   tests pinning listing output move.
B. Keep the seam-flavoured dump, and only render `StarUnpack` as `*T` and
   variables in compound arguments by their `_N` names. Smallest change;
   leaves defect 3.

Recommendation: A for ISO-surface modules (operator ruling 2026-09-25 on
listing/1 was "do what Scryer does"), B for seam modules.
