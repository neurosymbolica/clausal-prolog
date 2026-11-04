# A seam list with a leading star does not match a [_, *_] head

Found 2026-11-04 in review of the TRO answer-order work; the same with
`CLAUSAL_DISABLE_OPT=tro`.  Severity: a missing answer.

## What / Repro

```
-module(sg, [run(L)])
-dynamic(ev/1)
q(X, N) <- (N > 0, M is ++(N - 1), q(X, M))
q([_, *_], N) <- (N <= 0)
log(E) <- assertz(ev(E))
go <- (freeze(Z, log(('woke', Z))), X is [*Z, 'a'], log(('x', X)), q(X, 2), log('answer'))
run(L) <- (retractall(ev(_)), findall(1, go, _), findall(E, ev(E), L))
```

`run(L)` gives `[x([*_, 'a'])]`: `q([*Z, 'a'], 2)` has no answer.  The
list `[*Z, 'a']` has at least one element whatever Z is, so `[_, *_]`
unifies with it (binding Z, waking the frozen goal) and the clause should
answer: expected `[x(...), (woke, ...), answer]` or the like, once per
way Z can be split.  The head's `$head_list_unify_input` on a `SegList`
whose first segment is an unbound star seems not to try the split.
