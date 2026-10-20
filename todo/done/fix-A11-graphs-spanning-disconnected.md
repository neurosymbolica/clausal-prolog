# fix(A11-F050): spanning_tree/min_spanning_tree return a partial tree on disconnected graphs

`modules/graphs.py:515-542, 545-578`: BFS/Prim run from verts[0] only, no
`len(visited) == len(verts)` success check —
`min_spanning_tree([["a","b",1],["c","d",2]], T, C)` → `[["a","b",1]]`, cost
1; vertices c,d silently dropped. No spanning TREE exists for a disconnected
graph.

**Fix**: fail when `len(visited) < len(verts)` (symmetric with
topological_sort failing on cycles); a spanning-forest variant can be added
separately if wanted.

**Test**: test_F050_mst_disconnected_fails (xfail).
