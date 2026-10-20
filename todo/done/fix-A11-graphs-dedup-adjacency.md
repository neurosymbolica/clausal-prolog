# fix(A11-F051): parallel edges produce duplicate solutions/entries

`_build_adj` (modules/graphs.py:81-90) appends per edge with no dedup;
`has_edge` (:150-162) iterates the raw edge list. Executed:
`find_path([["a","b"],["a","b"]], "a","b", P)` yields the identical path
twice; `neighbors(..., "a", N)` → `["b","b"]` (self-loop → `["a","a"]`;
docs show unique neighbor lists); has_edge enumerate repeats pairs. This is
the duplicate-solutions-per-witness class the audit brief flags.

**Fix**: order-preserving dedup in _build_adj/_build_directed_adj; dedup
enumerated (U,V) pairs in has_edge.

**Tests**: test_F051_find_path_dup_edges_single_solution,
test_F051_neighbors_dedup (xfail).
