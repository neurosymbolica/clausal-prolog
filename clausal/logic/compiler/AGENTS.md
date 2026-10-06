# clausal/logic/compiler/ — the per-predicate compiler

Turns one predicate's clause list into a Python generator function (built as
`ast`, then `compile()`d via `clausal/codegen.py`) and installs it as the
predicate's dispatch. Called per predicate by `../compiler_v2.py`
(`compile_module`), by `assertz` recompiles, and by `../solve.py` for ad hoc
queries. The source surface does not matter here: all three arrive as
`Clause` objects. Up: [../AGENTS.md](../AGENTS.md)

**Read [README.md](README.md) first**: the full architecture guide (pipeline,
data structures, the two strategies, invariants §10, gotchas §11, public API
§12). This file only maps it.

## Two strategies

- **Trampoline** (default): yields `(parent, None)` per solution and
  `(parent, DONE)` at exhaustion; flat Python stack. `goal_trampoline.py`.
- **Shallow** (`-shallow([...])`): plain generator with `for` loops over
  sub-generators. `goal_shallow.py`.

## Map

| Role | Files |
|---|---|
| Entry points | `predicate.py` (`compile_predicate_trampoline` / `_shallow` / `_ast`, `_install`, the `base_globals` runtime aliases); `__init__.py` (public API) |
| Globals (phase 1) | `globals_env.py`: call-target resolution into the function's `__globals__`; also asks `../dialect_edge.py` at call sites |
| Indexing / dispatch (2-3) | `arg_index.py` (first-arg, joint, secondary, groundness-keyed), `list_dispatch.py` |
| Heads (4) | `head_match.py`: head -> `match` case patterns, list/star patterns |
| Bodies (5): IR path | `terms_to_goalop.py` (body -> `GoalOp` IR in `ir.py`), `lower_python_shallow.py` / `lower_python_trampoline.py`, shared `_lower_goalop_shared.py` |
| Bodies (5): goals | `goal_shallow.py`, `goal_trampoline.py`, `control_constructs.py` (once, catch, findall, freeze, setup_call_cleanup, ...), `ite_reified.py`, `tabled_naf.py`, `star_segments.py` |
| Terms -> AST | `terms_to_ast.py` (`term_to_ast_expr`, `arith_to_ast_expr`) |
| Optimisations | `optimisations/` (`analyse -> apply` passes: `tro.py`, `continuation_tco.py`, `destructive_reuse.py`, `call_site.py`) wrapping the analyses in `tro.py` and `destructive_reuse.py` here |
| Plumbing | `strategy.py`, `compile_ctx.py` (`CompilationContext`), `invariants.py` (phase-boundary assertions), `_ast_helpers.py`, `_vars.py` |

Runtime helpers that generated code calls (list unification, star lists,
`_tramp_call`) live in `../runtime/`, which must not import this package.

## Where to start

- A goal compiles wrong: find its `GoalOp` in `ir.py`, trace
  `terms_to_goalop.py`, then the lowering in `_lower_goalop_shared.py`.
- A new control construct: `control_constructs.py` plus its case in
  `terms_to_goalop.py`.
- Indexing/performance: `arg_index.py`; see
  [indexing.md](../../../docs/indexing.md).
- To see generated code: the `*_ast` entry points return the `FunctionDef`.

## Gotchas

- The compiler's plans and open design todos live in
  `implementation_plans/compiler/` (and its `todo/`), not the top-level
  `todo/`.
- Cycles are broken with function-local imports (README §11).
- `compiler/predicate.py` (compilation) is not `../predicate.py` (the
  predicate-row / handle model).

Docs: [compiler.md](../../../docs/compiler.md) ·
[reified_ite.md](../../../docs/reified_ite.md)
