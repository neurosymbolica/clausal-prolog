# listing/1 prints the compiler's head patterns and loses variable sharing

**Status: FIXED 2026-11-04 (commit COMMIT).** Option A for ISO-surface modules, B for seam modules (operator ruling 2026-09-25, "do what Scryer does", applied under the owner's 2026-11-03 "proceed"): `_format_clause` reads each clause through `clause_ops.clause_terms`; a `.pl` / Clausal Prolog clause prints as Scryer's `listing/1` prints it (`_portray_clause_iso`, a port of `portray_clause_//1`), with no header line; a seam clause keeps its header and seam spelling, with `[H, *T]` partial lists and `_0`, `_1`, ... variables by first occurrence. Pinned in tests/iso/test_listing_portray_clause_scryer.py (byte-compared with Scryer: facts, rules, partial lists, strings, operators, quoted atoms, numbers, negation, if-then-else, cut; `.pl` and `.clausal`) and tests/test_listing_seam_clause_terms.py. Still different from Scryer: (1) a default alphanumeric operator's layout (`C is -A` vs Scryer's `C is-A`), a writeq difference filed as todo/writeq-alphanumeric-operator-layout-differs-from-scryer-2026-11-04.md; (2) Scryer's listing/1 of a STATIC predicate raises `permission_error(access, private_procedure, PI)` (it reads clauses with clause/2); Clausal still lists it, unchanged here; (3) on the legacy `.pl` translator (`CLAUSAL_PL_FRONTEND=translator`) a module is not on the ISO surface, so it lists in the seam spelling (see todo/pl-translator-clause-2-rule-body-is-the-seam-tuple-2026-11-04.md).

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
