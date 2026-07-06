# fix(A11-F045): shortest_path Dijkstra silently wrong with negative weights

`modules/graphs.py:324-351` has no negative-weight guard; on
`[["a","b",1],["a","c",5],["c","b",-100]]` a→b it returns `["a","b"]`
(cost 1) while the true shortest is `["a","c","b"]` (cost −95). docs/graphs.md
states no precondition.

**Fix**: scan weights and fail/raise a typed error on negatives + document the
Dijkstra precondition (cheapest sound behavior); Bellman-Ford fallback
optional later.

**Test**: test_F045_shortest_path_negative_weight (xfail).
