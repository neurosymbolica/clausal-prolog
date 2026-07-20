# `op_node/3` — decompose/construct `simple_ast` operator nodes by class name

STATUS: DONE (2026-07-20). Implemented as `op_node/3` in
`clausal/modules/reflection.py` (next to `goal_functor/3`), with
`tests/test_reflection_op_node.py` covering decompose, construct, match-by-class,
unknown-class / non-operator clean failure, renderer round-trip, and the
end-to-end GtE→Gt operator-swap. The class set is derived from the renderer's
`_RENDER_*_OPS` tables (via the public `RENDER_OP_CLASS_NAMES` seam), so it is
bijective with `render_source` by construction. A Fable review then hardened it:
decompose now matches by **class identity** (a foreign object sharing an
operator's name — e.g. CPython `ast.Gt` — fails cleanly instead of crashing or
false-matching), construct **shallow-derefs** operands, and the excluded kinds
(`CompareChain`) plus unary/boolean coverage are pinned by tests. The
deferred-bound operand → renderer `RenderError` case is a pre-existing renderer
limitation, filed separately as `todo/renderer-deref-bound-var-operands.md`.
Full suite green (9801 passed). Details below reflect the original filing.

Prerequisite for the Clausal-AST mutation
auditor's **operator-swap** mutations (relop `>=`↔`>`, arith, etc.). Without it
the operator catalog cannot be written purely in Clausal (the user's core
requirement: match+replace in Clausal, not Python).

## The gap (probe-confirmed 2026-07-20)
A comparison/arithmetic form in a clause body reifies as a **`simple_ast.Node`**
(`GtE`, `Gt`, `Add`, `Sub`, … in `clausal/pythonic_ast/nodes.py`) — NOT a
`Goal`/Compound. These nodes:
- ARE reached by `reified_subterm/2` (its `_subterms` walker in
  `clausal/modules/reflection.py` special-cases `isinstance(term, simple_ast.Node)`);
- HAVE structural `__unify__` (nodes.py:189 — "same operator class, operands
  unified pairwise");
- can be reconstructed in Python (`Gt(left=n.left, right=n.right)`).

BUT the Clausal term builtins **do not operate on them**:
- `functor/3`, `arg/3`, `unpack/2` (`clausal/logic/builtins/inspection.py`) handle
  only Compound/PredicateMeta — `functor(GtE_node, N, A)` FAILS. (Probed: a
  `.clausal` `functor(SUB, "GtE", 2)` over a reified `X >= 1` fails.)
- surface-syntax patterns don't compile: `op((L >= R), …)` in a fact head →
  `__init__() got an unexpected keyword argument 'arg_0'`; body `OLD = (L >= R)` →
  parser rejects `=` and treats `>=` as a comparison *goal*, not a constructible
  term. So an operator node can neither be **matched by class** nor **rebuilt** from
  Clausal source today.

Net: reified structural wrappers (`Clause`/`Goal`/…) are inspectable from Clausal;
`simple_ast` operator nodes are a blind spot for `functor`/`unpack`.

## Deliverable
A bidirectional reflection predicate (natural home: `clausal/modules/reflection.py`,
next to `goal_functor/3`), e.g.:

    op_node(NODE, CLASS_NAME, ARGS)

- **decompose mode** (NODE bound): `op_node(GtE(L,R), "GtE", [L, R])` — yields the
  node's `simple_ast` class name as a string/atom and its operands as a list
  (field order per `dataclasses.fields`, excluding `position`).
- **construct mode** (CLASS_NAME + ARGS bound, NODE unbound): builds the named
  `simple_ast` node from the args — `op_node(NEW, "Gt", [L, R])` → `NEW = Gt(L,R)`.
- Unknown class name → fail cleanly (or `RenderError`-style loud error, matching the
  module's convention).

This is the `functor`/`unpack` analogue for the operator-node kind. It composes with
the existing `reified_subterm/2` (walk) and the `replace_subterm/4` primitive
(`replace-subterm-reflection-primitive.md`) to give a pure-Clausal
match→rewrite over operator nodes.

## Acceptance
- `op_node(N, "GtE", [L, R])` where N is the reified `X >= 1` comparison binds
  `L`/`R` to the operands and names it `"GtE"`.
- `op_node(M, "Gt", [L, R])` constructs a `Gt` node; `render_source` of a clause
  containing M unparses it as `L > R` and it re-reifies to a `Gt` (round-trip with
  the just-landed renderer).
- Covers the operator classes the auditor mutates first: `Gt`, `GtE`, `Lt`, `LtE`
  (and their `__unify__`-bearing kin); extensible to `Add`/`Sub`/`Mult` etc.
- Bijective with the renderer's operator dispatch table (same class names).

## Why this and not a Python-side operator swap
The auditor could match+replace operator nodes in Python (Python reconstructs
`simple_ast` nodes trivially). That would keep the catalog OUT of Clausal — the
opposite of the stated design intent. `op_node/3` is the minimum engine primitive
that keeps the operator catalog pure-Clausal, and it is generally useful for ANY
Clausal-driven AST tool (lints, refactors) that must reason over arithmetic/
comparison forms — the same reuse argument as the renderer.

## Scope note
Only operator-node mutations need this. **Numeric-literal** mutations (`N`→`N±1`)
work without it — ints are primitives `reified_subterm` reaches and Clausal handles
via `number/1` + `is`. So the auditor's literal-shift operator can ship before this
lands; the relop/arith family is gated on it.
