# Native .pl: clause/2 bodies are unexpanded, because there are no user expansion hooks (pre-existing)

**Found:** 2026-10-16, re-review 3 of the conjunction-body retract fix (Note N1). This is pre-existing,
not caused by that fix. It is the clause/2 side of todo/iso-term-and-goal-expansion-2026-10-12.md.

## What happens

The native front end has no user `term_expansion/2` or `goal_expansion/2` hook. Such clauses are
ordinary predicates, so a stored body is the body as written:

```prolog
:- dynamic(c/1).
term_expansion((c(N) :- old), (c(N) :- new1, new2)).
goal_expansion(gold, gnew).
c(1) :- old.
c(2) :- foo, gold.

?- clause(c(N), B).
%  Clausal: N = 1, B = old ;            N = 2, B = (foo, gold)
%  Scryer:  N = 1, B = (new1, new2) ;   N = 2, B = (foo, gnew)
```

Clausal is consistent with itself: what clause/2 shows is what runs, because nothing was expanded.
What differs from Scryer is that the hooks are missing; the clause/2 storage itself is correct.

## Wanted

When the hooks land (todo/iso-term-and-goal-expansion-2026-10-12.md), `Clause.source_body` must be
the body AFTER user expansion. That means `iso_l3._source_body_kw` lowers the expanded term, not the
term as read.

- Add tests that clause/2 and retract/1 see the expanded body: the rows above, against Scryer.
- The engine's own regex goal expansion (`goal_expansion._expand_predicate`) keeps the as-written
  body on purpose (`dataclasses.replace` carries `source_body`), because that expansion is an engine
  detail. Keep that distinction: user expansion changes the clause, engine expansion does not.
- Repro: scratchpad `rr3/p1/tex.pl` of the 2026-10-16 review.
