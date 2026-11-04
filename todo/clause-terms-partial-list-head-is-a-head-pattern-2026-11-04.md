# clause_terms hands back a partial-list head as the compiler's head pattern

Reported 2026-11-04 by a team using `clause_ops.clause_terms` for
explanation/provenance over loaded programs. Severity: high for clause/2 and
retract/1 on any dynamic procedure with a `[H|T]` head.

## What / Repro

```prolog
:- dynamic(p/2).
p([H|T], H-T).
p([a|_], x).
t1 :- clause(p([a,b], X), B), write(X-B), nl, fail.
t2 :- clause(p(L, X), B), write(L/X/B), nl, fail.
```

Before the fix (`.pl` native and translator front ends, `.clausal`):

```
t1:  (nothing; Scryer: a-[b]-true and x-true)
t2:  [_20,StarUnpack(value=AttVar(_21))]/(_20-_21)/true
     [a,StarUnpack(value=AttVar(_22))]/x/true
```

A head list pattern `[H|T]` is stored as the compiler's pattern
`[H, StarUnpack(T)]` (it compiles to a list match). `clause_terms(clause,
home_db)` (shared by clause/2, retract/1 and outside callers) put the
hoisted head arguments back and copied the stored head as it was, so the
Head held the AST node; `head_matches` probed with the same pattern, so a
bound query list never selected the clause. Bodies were right: they are
built through the query compiler (`_source_built` / `_full_built`), which
lowers `[H|T]` to the partial list.
