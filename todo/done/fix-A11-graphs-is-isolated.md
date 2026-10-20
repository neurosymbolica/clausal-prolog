# fix(A11-F046): is_isolated ?Node enumerate mode is dead code; check mode conflates non-vertices

`modules/graphs.py:210-227`: vertices are extracted only from edges (:66-78)
and every extracted vertex has ≥1 adjacency entry, so the enumerate branch is
unsatisfiable — the documented `?Node` mode (docs/graphs.md:63) can never
yield. Check mode: `is_isolated([["a","b"]], "zzz")` → True (any term counts).

**Fix** (A11-D010): allow 1-element `[v]` vertex entries in
`_extract_vertices` (also makes single-vertex graphs representable — unlocks
the documented mode), and fail check-mode for terms that are not vertices.

**Tests**: test_F046_is_isolated_enumerate (xfail),
test_F046_guard_nonvertex_counts_isolated (current-behavior guard).
