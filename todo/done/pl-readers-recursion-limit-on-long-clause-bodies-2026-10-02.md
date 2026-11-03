# .pl readers hit Python's recursion limit on long clause bodies

**Status: FIXED 2026-11-03 (commit see git log of this file).** The parser's operator loop, the reader's term transform, the lowering's walks (Uses, _show, clause/2's source body, DCG bodies), the compiler's final_yields pass and the translator's collectors are iterative and produce what the recursive walks did; long `;` chains compile as a balanced Or tree and long one-operator chains are built over flat lists, so the generated AST stays shallow. Pinned in tests/test_long_pl_bodies_no_recursion.py.

What is left (not this todo's walks):

- **The engine's code generation is the real limit for a long conjunction.**
  Each goal's continuation runs inside the loop over the previous goal's
  answers, so the generated function nests as deep as the body is long;
  `codegen.split_deep_nesting` outlines it into helpers nested inside each
  other. Measured (native, `q(X,Vi)` goals, 2026-11-03): 1000 goals load in
  2.5 s, 3000 in ~21 s, 5000 in 75 s, 7000 in 189 s (almost all in
  `functiondef_to_function`: `localise` is quadratic, and CPython's compile
  of the nested helpers too); 10000 fail after ~170 s with a
  `GeneratedCodeError` naming the clause (CPython's compiler recursion
  limit). The front end alone (read + lower + compile the module) takes
  ~33 s at 100k goals. Fixing it means generating long bodies without
  nesting (or splitting them into auxiliary predicates): a codegen design
  question, not a recursive walk.
- Bracketed nesting the text writes (`s(s(...))`, `[[...]]`, `((...))`)
  still recurses in the parser (~4 frames a level: ~250 deep), and an
  if-then-else chain `C1 -> T1 ; C2 -> T2 ; ...` nests by meaning (~200).
  Both now fail with a load error naming the line and
  `resource_error(stack)`.
- A long conjunction as DATA in a body (`assertz((h :- a1, ..., aN))`, a
  `.pl` meta-call body holding a variable) loads only up to the engine
  compiler's own recursive walks over data terms (`term_to_ast_expr`,
  `_collect_vars`, `globals_env`): 400 operands load, 500 do not; past
  that a `GeneratedCodeError` naming the clause and `resource_error(stack)`.
- Evaluating a deep arithmetic term (`X is 1+1+...`) at run time raises
  `resource_error(stack)` (it loads).

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
