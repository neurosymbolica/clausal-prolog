# fix(A11-F049): path_cost uses last parallel-edge weight; shortest_path uses min

`modules/graphs.py:385-395`: `weight_map[(u,v)] = w` overwrites on duplicate
edges, while the Dijkstra adjacency (:105-118) keeps all parallel edges. On
`[["a","b",3],["a","b",5]]`, shortest_path finds the cost-3 traversal but
path_cost(["a","b"]) reports 5 — path_cost(shortest_path(G)) over-reports.

**Fix**: `weight_map[key] = min(weight_map.get(key, inf), w)`.

**Test**: test_F049_path_cost_parallel_edges_min (xfail).
