# fix(A11-F052): raw TypeErrors escape for legal-looking graph inputs

- MST heap tie-break (modules/graphs.py:563-565): `(w, u, neighbor)` tuples
  reach vertex comparison on weight ties — mixed int/str vertices →
  `TypeError: '<' not supported` from deep inside heapq (mixed-type graphs
  otherwise fully supported).
- `_extract_vertices` (:66-78) hashes vertices — a dict vertex crashes with
  raw TypeError (lists already get an identity fallback).

**Fix**: heap entries `(w, counter, u, v)` with a monotone counter (also
fixes the id()-based tie-break nondeterminism noted unconfirmed in the
ledger — insertion order is deterministic given the edge list);
identity-fallback for unhashable vertices.

**Tests**: test_F052_mst_mixed_vertex_types,
test_F052_vertices_unhashable_vertex (xfail).
