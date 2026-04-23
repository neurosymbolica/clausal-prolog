# Slice H progress tracker

**Goal** (from `COMPILER_MIGRATION_PLAN.md` §10):
The public `clausal.logic.compiler` surface is explicit, documented,
stable, and small.  `__init__.py` has an explicit `__all__` and no
`__getattr__`.  No external file imports a private name from the
compiler.

`__getattr__` was already retired in slice B6; slice H finishes the
job by redirecting every private-name test import to its canonical
submodule, declaring `__all__`, and deleting the private re-export
block in `__init__.py`.

Sliced into six reversible commits (H1–H6).  Each leaves the tree
with a green test suite and passes the two grep assertions from plan
§10 *Validation* at its boundary (H5 onwards).

---

## H1 — runtime-helper re-exports

**Scope:** Move tests that imported runtime list/star unifiers
through the compiler package over to their canonical location in
`clausal.logic.runtime.{body_star_unify,list_unify}`.  Drop the
corresponding re-export block in `compiler/__init__.py`.

**Status:** ✅ done

Delivered:

- `tests/test_segstring.py`, `tests/test_string_list_unification.py`,
  `tests/test_compiler.py`, `tests/test_seglist_creation.py`:
  imports of `_body_multi_star_unify`, `_body_star_unify`,
  `_build_star_list`, `_build_multi_star_list` redirected to
  `clausal.logic.runtime.body_star_unify`; `_head_list_unify_input`,
  `_head_list_unify_output` redirected to
  `clausal.logic.runtime.list_unify`.
- `compiler/__init__.py`: six-name runtime re-export block deleted.

Tests: 10490 / 90 skips.

## H2 — `globals_env` + `terms_to_ast` private helpers

**Scope:** `_dotted_name_from_loadattr`, `_collect_globals_info`,
`_collect_call_targets`, `_collect_head_types`, `_collect_py_thunks`,
`_collect_types_from_term`, `_disp_key`, `_inject_call_targets` —
redirect callers to the owning submodule.

**Status:** ✅ done

Delivered:

- `tests/test_module_imports.py`, `tests/test_compiler_optimizations.py`,
  `tests/test_callsite_specialization.py`: private-name imports
  routed to `compiler.globals_env` and `compiler.terms_to_ast`.
- `clausal/logic/solve.py`: the function-local private-helper import
  (a production caller; see `feedback_cycle_breaks.md`) split into
  `compiler` (public names), `compiler._vars`
  (`_collect_vars`, `_var_python_name`), and `compiler.globals_env`
  (`_collect_types_from_term`).
- `compiler/__init__.py`: `_dotted_name_from_loadattr` line removed
  from the `terms_to_ast` re-export block.

Tests: 10490 / 90 skips.

## H3 — `arg_index` private helpers

**Scope:** Fourteen-name arg_index re-export block (`_INDEX_THRESHOLD`,
`_INDEX_VAR`, `_analyze_{,joint_}index_positions`, `_{,joint_}bucket_key`,
`_static_call_key`, `_runtime_arg_key`, `_extract_{,first_}arg_key`,
`_build_{arg,first_arg,joint_arg,secondary}_index`) — redirect callers.

**Status:** ✅ done

Delivered:

- `tests/test_compiler_optimizations.py` (7 local imports),
  `tests/test_resolve_and_argkey.py`, `tests/test_groundness_dispatch.py`,
  `tests/test_first_arg_index.py`, `tests/test_callsite_specialization.py`:
  all arg_index imports routed to `compiler.arg_index`.
- `show_generated.py`: `_bucket_key` redirected similarly.
- `compiler/__init__.py`: 14-name `arg_index` re-export block deleted.

Tests: 10439 / 90 skips (after moving the baseline to skip the
Scryer backend suite per user preference — see
`reference_test_baseline.md`).

## H4 — residual private helpers

**Scope:** Final batch of small re-export blocks —
`_collect_vars` / `_var_python_name` (`_vars`),
`_tro_args_safe` / `_is_deterministic_goal` (`tro`),
`_compile_goal_lambda` / `_flatten_conjunction` (`control_constructs`),
`_inject_bucket_refs_trampoline` (`goal_trampoline`).

**Status:** ✅ done

Delivered:

- `tests/test_dict_set_terms.py`, `tests/test_tail_recursion.py`,
  `tests/test_lambdas.py`, `tests/test_optimisations_call_site.py`,
  `tests/test_bucket_refs_ir_parallel.py`, `show_generated.py`:
  private-name imports routed to owning submodules.
- `compiler/__init__.py`: last private re-export blocks deleted.
  Only `from . import predicate` remained (kept briefly for
  submodule-attribute access from tests; removed in H5).
- Plan §10 grep assertion passes:
  `grep -rE "from clausal\.logic\.compiler import _" clausal tests
  show_generated.py` returns nothing.

Tests: 10439 / 90 skips.

## H5 — `__all__` + final public-API tightening

**Scope:** Redirect the remaining six "quasi-public" helpers that the
plan (§10.3) deliberately omits from the stable surface —
`compile_body`, `compile_goal`, `compile_body_trampoline`,
`compile_goal_trampoline`, `term_to_ast_expr`, `arith_to_ast_expr`,
`head_to_match_pattern`, `compile_head_to_match_case`.  Declare
`__all__`.  Drop all remaining top-level re-exports beyond the 11
stable names.

**Audit result:** all eight helpers are consumed only by unit tests
(`test_compiler_goals.py`, `test_compiler.py`, `test_compiler_trampoline.py`,
`test_compiler_optimizations.py`, `test_lambdas.py`,
`test_trail_elision.py`) plus two function-local imports in
`clausal/logic/solve.py`.  No documented downstream caller — safe to
treat as internal.

**Status:** ✅ done

Delivered:

- Eight helpers redirected to their owning submodules
  (`compiler.goal_shallow`, `compiler.goal_trampoline`,
  `compiler.terms_to_ast`, `compiler.head_match`) in the six test
  files + `solve.py`.
- `compiler/__init__.py` rewritten with a docstring describing the
  public API, explicit `__all__`, and nothing else.  Eleven-name
  surface:
  - `DONE`
  - `compile_predicate`, `compile_predicate_ast`,
    `compile_predicate_shallow`, `compile_predicate_shallow_ast`,
    `compile_predicate_trampoline`, `compile_predicate_trampoline_ast`
  - `Strategy`, `ShallowStrategy`, `TrampolineStrategy`
  - `CompilationContext`
- Plan §10.3's aspirational `CompiledPredicate` / `DispatchPlan` not
  included — neither exists as a class in the codebase (open question
  for a future slice; see §Deferred below).
- Plan §10 grep assertions both pass:
  - `grep -rE "from clausal\.logic\.compiler import _"` → empty.
  - `grep -rE "getattr.*clausal.logic.compiler"` → empty.

Tests: 10439 / 90 skips.

## H6 — documentation sweep

**Scope:** `clausal/logic/compiler/README.md` §12 *Public API*: one
entry per `__all__` name, no stale `__getattr__` references.
Link the migration plan and this progress tracker.

**Status:** ✅ done

Delivered:

- README §12 rewritten: groups the eleven public names into
  *entrypoints*, *AST variants*, *Strategy & context*, and *runtime
  sentinel*; explains that private helpers must be imported from
  their owning submodule, not the package root.
- Stale "`__init__.__getattr__` re-export" bullet removed.
- This tracker created (`implementation_plans/SLICE_H_PROGRESS.md`).

Tests: 10439 / 90 skips.

---

## Deferred / follow-ups

- `CompiledPredicate` / `DispatchPlan` — named in plan §10.3 but do
  not exist as types in the code today.  If the compiler grows a
  structured return type (rather than the current
  `Callable[..., StepGenerator]` / `ast.FunctionDef` pair), add it
  here then extend `__all__`.
- `predicate` submodule re-export (`from . import predicate`) was
  removed in H5; one test (`test_runtime_compiler_boundary.py`) still
  mentions the string `"from clausal.logic.compiler import predicate"`
  inside a `textwrap.dedent` fixture that feeds the boundary-checker
  detector.  That is a string constant, not a live import, and needs
  no further action.
