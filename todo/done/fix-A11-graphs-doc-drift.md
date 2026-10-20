# fix(A11-F054/F058): graphs doc drift — directionality contract + wording batch

- F054: `has_edge/3` is directional while neighbors/degree/paths/components/
  trees treat the same edge list as undirected (has_cycle/topological_sort/
  reverse_edges are directed and say so). Add an explicit per-predicate
  directionality section to docs/graphs.md and a line to has_edge's docs.
- F058 batch: (1) merge_graphs says "union", is concatenation (dups kept) —
  fix wording or dedup; (2) degree counts a self-loop once (standard: 2) —
  doc note; (3) path_cost fails on single-vertex path (cost 0 expected) —
  decide + document; (4) BFS/find_path from an absent source succeed with
  [src] (phantom vertex) — document or fail; (5) malformed edge entries
  silently dropped — document the leniency; (6) is_connected([]) vacuously
  true — one doc line.

**Tests**: test_F054_guard_has_edge_directional, test_F058_guard_doc_drift_batch
(current-behavior guards — flip alongside any behavior change).
