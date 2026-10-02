# .pl readers hit Python's recursion limit on long clause bodies

**Filed:** 2026-10-02, engine lane, after the long-clause codegen fix (22f9428f).
A clause body of ~490-500 goals fails in the NATIVE reader (RecursionError in
`prolog_reader.cell`), ~1000 in the translator parser (`prolog_parser._parse_term`).
Seam is fine at 3000. Same class as the fixed "too many statically nested blocks":
a model-written long clause silently won't load. Witness: generate
`p(X) :- q(X,V1), ..., q(X,V500), true.` and load it with CLAUSAL_PL_FRONTEND=native.
Fix direction: make the conjunction (','/2, right-nested) reader iterative.
The surface parser is operator-owned (Phase 3 parser) - check ownership before editing.
Related, pre-existing: nested if_/3 code size grows ~4x per level (14 levels = 3.3M
nodes, 44 s load); nested \+ \+ ~3.5x per level; the native front end emits no TRO for
`len([_|T],N0,N) :- N1 is N0+1, len(T,N1,N).` while the translator does.
