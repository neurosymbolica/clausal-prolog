# A ground WFS truth value depends on what is already in the table store

Found 2026-10-07 by the eighth asyncio review (the operator asked for review
rounds until one comes back clean). It is a synchronous issue: identical on
origin/main, with no async code involved. Related to the
`wfs-undefined-lost-at-query-surface` family.

## Repro

```
-table(path/2)
-table(win/1)
edge(1, 2), edge(2, 3), edge(3, 4),
path(X, Y) <- (path(X, Z), edge(Z, Y))
path(X, Y) <- edge(X, Y)
move(1, 2), move(2, 1), move(2, 3), move(3, 4),
win(X) <- (move(X, Y), not win(Y))
wp(X) <- (path(1, X), not win(X))
```

`query_wfs(wp(X))`:
- on a fresh store: `wp(2) = True`;
- after `path(1, _)` has been completed by an earlier query:
  `wp(2) = Undefined`, which is correct (`win(2)` is undefined in the
  `1 <-> 2` cycle).

Similarly `k(X) <- (a(X), win(Y), X == Y)` gives `k(1)`, `k(2)` as True on a
fresh store and Undefined after another sequence of goals.

Probes: `/tmp/claude-0/review8/pF_history.py`, `pD_korder.py` (session
scratch; they may be gone).

## Why it matters

It makes the same query's answer depend on unrelated earlier queries. Any
A/B harness for tabling must baseline per store history, not per fresh store.
