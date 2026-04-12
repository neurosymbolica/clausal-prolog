# Compiler module split

## Status: Structural split complete (phases 0–18)

All 16 submodules extracted; 10400 tests pass at every phase.
`_monolith.py` is now a 366-line residual shared-state + re-export hub
containing only the Phase 0.5a hoisted runtime-helper aliases
(`_fd_eq_fn`, `_DictTerm_t`, …), the thread-local
`_compile_context_local`, and `from .<submodule> import …` lines that
preserve the public attribute surface on `clausal.logic.compiler`.

Phase 19 (per-submodule docstrings) was done inline — each extracted
submodule got a docstring as part of its move commit.

Deleting `_monolith.py` outright (the original phase 18 aim) would
require either distributing the Phase 0.5a aliases into every consuming
submodule or creating a dedicated `_state.py`.  Left as a deferred
cleanup — see "Deferred refactors" below.

## As-shipped deltas from the original plan

Small deviations discovered during execution.  Recorded here so the
plan and the code agree.

1. **Naming constants live in `_ast_helpers.py`, not `_monolith.py`.**
   The plan placed `_MARK_PREFIX`, `_TRAIL_PARAM_NAME`, `_K_PARAM_NAME`,
   `_DISP_PREFIX`, `_TRAMP_PARENT_NAME`, `_THIS_GEN_NAME` in the
   naming-constants block of `_monolith`.  During phase 6 we hit a
   `star_segments → _monolith` import cycle, so the constants moved to
   the deepest leaf (`_ast_helpers`) where any submodule can import
   them without cycling.

2. **Star-list parsing leaves live in `terms_to_ast.py`, not
   `star_segments.py`.**  `term_to_ast_expr` uses `_parse_star_segments`
   and `_count_stars`; `star_segments._compile_*_is` use
   `term_to_ast_expr`.  To break this cycle the four parsing leaves
   (`_is_star_list`, `_parse_star_segments`, `_count_stars`,
   `_dotted_name_from_loadattr`) moved into `terms_to_ast.py`.
   `star_segments.py` keeps only the three `_compile_*_is` functions.

3. **Cross-strategy calls use `_m.` lazy attribute access, not
   direct imports.**  `goal_trampoline.compile_goal_trampoline`'s
   `forall/2` handler rewrites into shallow form and calls
   `_m.compile_goal(…)`.  Similarly, `ite_reified`, `control_constructs`,
   and `tro` all reach the goal compilers through the `_m` alias on
   `_monolith`.  The alias is bound at import time; the attribute
   lookup is at call time, which sidesteps the module-load-order
   cycles.  `_EXTRA_FUNCDEF` is referenced the same way from submodules
   that load before `predicate.py`.

4. **`predicate.py` bulk-copies Phase 0.5a aliases via `for _n in
   dir(_m)`.**  The ~50 hoisted runtime-helper aliases
   (`_fd_eq_fn`, `_DictTerm_t`, `_KWTerm_s`, …) and the runtime helpers
   (`_head_list_unify_input`, `_body_star_unify`, `_in_iter`,
   `_build_star_list`, …) stayed in `_monolith`'s namespace.  Rather
   than enumerate them, `predicate.py` ends its header with::

       for _n in dir(_m):
           if not _n.startswith("__"):
               globals().setdefault(_n, getattr(_m, _n))
       del _n

   so the moved function bodies resolve bare-name references without
   any rewriting.

5. **Phase 19 was folded into each move commit.**  Every extracted
   submodule got a module docstring as part of its phase — there is no
   separate documentation phase.

6. **Phase 18 did not delete `_monolith.py`.**  It remains as a
   366-line residual hub (hoisted imports, thread-local state,
   re-export shims) because removing it would require a non-trivial
   redistribution of shared state.  Listed in "Deferred refactors" as
   candidate #8.

7. **`__init__.py` keeps its `__getattr__` delegation.**  The plan
   originally intended phase 18 to replace delegation with an explicit
   re-export list.  Enumerating every private helper that tests /
   builtins / tools import (e.g. `_body_multi_star_unify`,
   `_extract_first_arg_key`, `_build_star_list`) would be
   several dozen names with no readability benefit; delegation stays.

## Deferred refactors (after Phase 18)

These are real smells worth fixing — just **not during the structural
move**. Each one becomes its own PR, scoped to the relevant submodule.

1. **Shallow/trampoline de-duplication** (the 3000-line prize). With
   twins co-located per submodule, each de-dup is a single-file diff.
   Likely approach: extract the shared control-flow skeleton and
   parameterise on a "strategy adapter" that provides leaf-yield, call
   dispatch, and continuation protocol. Start with the smallest pair
   (`compile_body` / `compile_body_trampoline`, ~90% identical) to
   prove the pattern.

   **Status (partial, in progress):** 13 pairs deduped so far —
   `compile_body`, `_make_body_compiler`, `_compile_reified_ite`
   dispatcher, `_compile_reified_ite_eq`, `_compile_reified_ite_fd`,
   `_compile_predicate_call`, `_compile_catch`, `_make_indexed_dispatch`,
   `_make_secondary_dispatch`, `_make_joint_dispatch` (non-TRO),
   `_make_groundness_dispatch` (non-TRO), plus three partial extractions
   from `compile_goal` (12 deterministic arms, 13 meta-predicate arms,
   2 membership arms).  Key patterns: (a) pass the strategy-specific
   ``compile_goal_fn`` as a kwarg, with trampoline using a closure that
   binds ``self_name``/``parent_name``; (b) ``arg_offset`` + ``tail_yield``
   for dispatch builders; (c) ``preprocess_clause`` hook for trampoline-
   only pre-passes like destructive-reuse.

   **Note on the earlier flagged "semantic asymmetry" in `_compile_reified_ite_eq`
   / `_fd`:** the concern was that shallow's double-compile of then/else
   arms could diverge from trampoline's single-compile if body-only Vars
   got walrus-introduced in one branch but referenced bare in another.
   Investigation (see commit "resolve + dedup reified-ITE _eq and _fd
   pairs") showed ``_preallocate_body_vars`` in ``compile_body`` walks
   the whole clause tree and pre-emits ``_vN = Var()`` for every body-only
   Var recursively, including inside ITE arms.  By the time the ITE
   compilers run, no walrus fires.  The "asymmetry" was redundant work,
   not a correctness difference — resolved and deduped.

   **Still not deduped:**

   - `_compile_general_ite` / `_trampoline` pair (non-reifiable ITE —
     trampoline has a ~100-line mini-trampoline that has no shallow
     counterpart).  This is a genuine structural difference; dedup
     requires a strategy-object or substantial refactor.
   - Full `compile_goal` / `_trampoline` dedup — the remaining ~11
     strategy-specific arms (And, Or, Not, IfExpr, TupleLiteral,
     catch-family, forall, predicate-call family) need a proper
     strategy adapter rather than mechanical extraction.
2. **Context object for compile-time threading**. Replace
   `(db, var_context, trail_name, k_stmts[, self_name, parent_name])`
   with a `CompileCtx` dataclass. Large touch but mechanical.
3. **Break up the 300–500 line functions**. Top targets:
   `compile_predicate_trampoline` (489), `compile_goal_trampoline`
   (464), `compile_goal` (383). Each `match` arm is a natural
   extraction point.
4. **Naming normalisation**: decide on `_py` suffix convention for
   runtime helpers; rename `compile_goal` → `compile_goal_shallow`
   (with a deprecated alias) for symmetry.
5. **Builtin-call name table**: extract `"unify"`, `"_dif"`, `"_fd_eq"`
   etc. to a single registry shared by shallow and trampoline paths.
6. **Inline `_shallow_to_trampoline`** (single caller).
7. **Head-matching nesting** in `head_to_match_pattern` (depth 10) —
   extract per-pattern-kind helpers.
8. **Retire `_monolith.py`**.  Either distribute the Phase 0.5a
   hoisted aliases back into their consuming submodules, or move them
   into a dedicated `_shared_state.py` alongside `_compile_context_local`.
   Also re-decide whether each submodule should import the aliases
   directly or whether `predicate.py`'s bulk-copy pattern generalises.

**Suggested ordering:** #1 first (start with the `compile_body` pair —
smallest, ~90% identical, cleanest proof of the strategy-adapter
pattern).  #8 is cosmetic and can wait.  #2 + #3 are big touches worth
doing together once #1 has defined the shape of the post-dedup code.

Out of scope even after the split unless specifically requested:

- Changing the public API.
- Unifying `compiler.py` and `compiler_v2.py`.
- Touching the C extension codepaths (`_list_unify.c` etc.).

Goal: turn the monolithic `clausal/logic/compiler.py` (8725 lines) into a
cohesive package `clausal/logic/compiler/` organised by **functional
cohesion** (things used together live together), without refactoring
behaviour. Once the structural move is stable and green, a separate
follow-up phase tackles the real smells (shallow/trampoline duplication,
long functions, parameter bloat, naming).

**Golden rule for every phase below**: no behaviour change, no dead-code
removal, no renaming, no API change. If a phase is tempted to fix
something, stop and add it to the "Deferred refactors" appendix instead.

After every phase: `pytest` must pass and
`from clausal.logic.compiler import *` must yield the same names as
before. Each phase is one reviewable commit (or a tight series).

---

## External API surface (must remain importable from `clausal.logic.compiler`)

Public entrypoints used elsewhere in the repo:

- `compile_predicate_trampoline`
- `compile_predicate_trampoline_ast`
- `compile_predicate_shallow`
- `compile_goal`
- `compile_goal_trampoline`
- `compile_body`
- `compile_body_trampoline`
- `term_to_ast_expr`
- `arith_to_ast_expr`
- `head_to_match_pattern`
- `compile_head_to_match_case`

Importers (verified 2026-04-11):

- `clausal/logic/specialization.py` (3 call sites, all inner imports)
- `clausal/logic/solve.py` (1 inner import)
- `clausal/logic/term_expansion.py`
- `clausal/logic/builtins/database_ops.py` (3 inner imports)
- `clausal/logic/compiler_v2.py`
- `clausal/tools/visualize.py`

Any symbol referenced by `visualize.py` that is private (`_…`) must be
re-exported explicitly from `compiler/__init__.py` to preserve the
current contract.

---

## Code-smell audit summary (informs the plan; not fixed during the split)

Full details below under "Audit findings". Headlines:

1. **Massive shallow/trampoline duplication** (~40–50% of ~3000 lines).
   Pairs: `compile_goal`/`…_trampoline`, `compile_body`/`…_trampoline`,
   `_compile_catch`/`…_trampoline`, all ITE variants, four dispatch-builder
   pairs, `_make_body_compiler`/`…_trampoline`,
   `_compile_predicate_call`/`…_trampoline`.
2. **25 function-local imports** across 44 call sites.
3. **No dead code, no TODO/FIXME, no commented-out blocks.**
4. **11 functions >150 lines**; longest 489
   (`compile_predicate_trampoline`), 464 (`compile_goal_trampoline`),
   383 (`compile_goal`).
5. **Nesting depth up to 10** in `head_to_match_pattern`.
6. **Repeated magic strings** (`"_m"` ×24, `"trail"` ×11,
   `"_tramp_parent"` ×10, `"this_generator"` ×7, `"_disp_"` ×2,
   `"k"` ×4, builtin names `"unify"`/`"_dif"`/`"_fd_eq"`).
7. **Parameter bloat**: one function with 9 positional args; the tuple
   `(db, var_context, trail_name, k_stmts[, self_name, parent_name])` is
   threaded through 20+ callees.
8. **Thread-local state**: only `_compile_context_local` at line 75
   (documented Phase 7).
9. **Naming inconsistencies**: `_py` suffix on some runtime helpers but
   not others; `compile_goal` (shallow) has no suffix while its peer is
   `compile_goal_trampoline`.
10. Otherwise clean: no bare `except`, no debug prints, no mutable
    defaults.

---

## Target layout (`clausal/logic/compiler/`)

```
compiler/
    __init__.py               # explicit re-exports of public API
    _ast_helpers.py           # _name, _attr, _call, _fresh, _assign, _if,
                              #   _yield_none_stmt, _undo_stmt, _assign_mark,
                              #   _in_iter_expr
    _vars.py                  # _var_python_name, _collect_vars,
                              #   _collect_var_ids, _collect_bound_vars
    head_list_unify.py        # _head_list_unify_input_py / output_py,
                              #   _body_star_unify, _build_star_list,
                              #   _build_multi_star_list, _in_iter,
                              #   _body_multi_star_unify, _tramp_call,
                              #   _head_multi_star_error   (runtime helpers)
    terms_to_ast.py           # term_to_ast_expr, arith_to_ast_expr
    star_segments.py          # _is_star_list, _parse_star_segments,
                              #   _count_stars, _compile_star_is,
                              #   _compile_single_star_is,
                              #   _compile_multi_star_is
    globals_env.py            # _GlobalsDb, _DbDispatchAdapter,
                              #   _collect_head_types, _collect_py_thunks,
                              #   _collect_types_from_term,
                              #   _collect_call_targets, _collect_globals_info,
                              #   _inject_call_targets, _inject_resolved_targets,
                              #   _preallocate_body_vars, _merge_builtin,
                              #   _disp_key, _set_of_dedup,
                              #   _dotted_name_from_loadattr
    head_match.py             # head_to_match_pattern, compile_head_to_match_case,
                              #   _head_arg_patterns,
                              #   _wrap_yields_with_output_guards,
                              #   _compile_multi_star_guard
    ite_reified.py            # _is_reifiable, _compile_reified_ite(+_eq/+_fd),
                              #   _compile_general_ite, and their _trampoline
                              #   twins (keep pairs together so later
                              #   de-dup is a one-file diff)
    tabled_naf.py             # _is_tabled_naf, _compile_tabled_naf_simple
    control_constructs.py     # _compile_once, _compile_call_nth,
                              #   _compile_count_all, _compile_setup_call_cleanup,
                              #   _compile_freeze, _compile_when,
                              #   _compile_find_all_core, _compile_throw,
                              #   _compile_catch(+_trampoline),
                              #   _catcher_to_structural, _compile_goal_lambda,
                              #   _hoist_lambda_args, _flatten_conjunction,
                              #   _compile_arith_cmp, _deref_cmp
    goal_shallow.py           # compile_goal, compile_body, _make_body_compiler,
                              #   _compile_predicate_call, _dispatch_call_iter
    goal_trampoline.py        # compile_goal_trampoline, compile_body_trampoline,
                              #   _make_body_compiler_trampoline,
                              #   _compile_predicate_call_trampoline,
                              #   _dispatch_call_trampoline,
                              #   _inject_bucket_refs_trampoline,
                              #   _step_expr, _yield_step_stmt,
                              #   _assign_yield_step
    list_dispatch.py          # _classify_list_key, _find_list_dispatch_pos,
                              #   _build_list_dispatch_guard,
                              #   _get_head_arg, _lift_clause_at_pos
    arg_index.py              # _arg_to_index_key, _runtime_arg_key,
                              #   _static_call_key, _bucket_key,
                              #   _joint_bucket_key, _extract_arg_key,
                              #   _extract_first_arg_key, _build_arg_index,
                              #   _build_first_arg_index,
                              #   _analyze_index_positions,
                              #   _build_joint_arg_index,
                              #   _analyze_joint_index_positions,
                              #   _make_joint_dispatch_simple/_trampoline,
                              #   _build_secondary_index,
                              #   _make_secondary_dispatch_simple/_trampoline,
                              #   _make_indexed_dispatch_simple/_trampoline,
                              #   _make_groundness_dispatch_simple/_trampoline
    destructive_reuse.py      # _head_aliased_var_ids,
                              #   _collect_unify_pairs_from_and,
                              #   _flatten_and_goals, _flatten_and_single,
                              #   _find_destructive_reuse_goals,
                              #   _apply_destructive_reuse
    tro.py                    # _is_deterministic_goal, _detect_tro_clause,
                              #   _get_tro_check_indices, _tro_args_safe,
                              #   _head_has_unifying_list_pattern,
                              #   _list_has_nonvar_constant,
                              #   _contains_star_unpack,
                              #   _compile_tro_tail, _compile_tro_body
    predicate.py              # compile_predicate_trampoline(+_ast),
                              #   compile_predicate_shallow,
                              #   _build_predicate_funcdef,
                              #   _build_predicate_trampoline_funcdef,
                              #   _shallow_to_trampoline,
                              #   _compile_always_fail_trampoline,
                              #   _compile_context_local  (thread-local)
```

---

## Phase 0 — Audit & inventory (this document)

Deliverable: this file, containing:

- External API surface (above).
- Code-smell audit (above).
- Target layout (above).
- Full inventory of every top-level `def`/`class` with its target
  submodule (see "Function inventory" below).
- Dependency notes for cross-group cycles.
- Phase ordering rationale.
- Deferred refactors appendix.

No source changes in this phase.

---

## Phase 0.5 — Pre-split tidy (two small commits, behaviour-preserving)

Rationale: two mechanical clean-ups that **make the split cleaner**. Any
larger refactor waits until after the split, because it's far easier to
review a 500-line focused submodule than an 8725-line monolith.

### 0.5a — Hoist function-local imports

Move all 25 inner `import` statements to the module top.

Known inner imports (line numbers from current HEAD):

- `PyThunk` at 2156, 3863, 5115
- `DictTerm, SetTerm` at 705, 1338
- `get_builtin_predicate, BuiltinPredicate` at 1021, 1105
- `KWTerm` at 725, 1473
- `import sys as _sys` at 1056, 1143
- `Keyword as KWNode` at 3561, 4315
- `clpfd`, `constraints`, `coroutining`, `variables` submodules in the
  5855–5870 and 5920–5931 ranges (trampoline path)

**Process**: hoist one at a time; run tests after each. If any hoist
produces a circular import, **stop** and record it in the
"Split-boundary signals" appendix — that cycle tells us where the module
boundary actually lies and may change the target layout.

### 0.5b — Extract magic-string constants

Introduce at module top:

```python
_MARK_PREFIX = "_m"              # fresh mark variable prefix, 24 sites
_TRAIL_PARAM_NAME = "trail"      # 11 sites
_K_PARAM_NAME = "k"              # 4 sites
_DISP_PREFIX = "_disp_"          # 2 sites
_TRAMP_PARENT_NAME = "_tramp_parent"   # 10 sites
_THIS_GEN_NAME = "this_generator"      # 7 sites
```

Replace all string-literal call sites with the constants. Do **not**
extract builtin-call names (`"unify"`, `"_dif"`, `"_fd_eq"`) yet — those
tie into a later builtin-table refactor and are out of scope here.

One commit. Full test suite. Done.

---

## Phase 1 — Convert file to package (no symbol moves)

1. Create `clausal/logic/compiler/` directory.
2. Rename `clausal/logic/compiler.py` → `clausal/logic/compiler/_monolith.py`
   byte-for-byte (single `git mv`).
3. Create `clausal/logic/compiler/__init__.py` with:
   ```python
   from ._monolith import *  # noqa: F401,F403
   from ._monolith import (   # explicit private re-exports for visualize.py
       # list generated from Phase 0 audit of visualize.py usage
   )
   __all__ = [...]            # exact list of public entrypoints above
   ```
4. `pytest`.
5. Confirm `python -c "import clausal"` and
   `python -c "from clausal.logic.compiler import compile_predicate_trampoline"`
   both succeed.

This phase proves the packaging shim before any symbol moves, so any
import fallout is isolated to a trivial commit.

---

## Phases 2–17 — One cohesive group per phase

Each phase uses the **same mechanical recipe**:

1. Create the target submodule file with a one-line module docstring.
2. **Cut** the block of functions (and their block comments) from
   `_monolith.py`; **paste** into the new submodule.
3. Copy whatever imports the block needs from `_monolith.py`'s header —
   do **not** prune unused imports in the source yet.
4. At the appropriate point in `_monolith.py`, add
   `from .<submodule> import *` (or explicit names) so still-resident
   code keeps working.
5. Update `compiler/__init__.py` to re-export any public symbols that
   moved.
6. `pytest` + `python -c "import clausal"`.
7. Commit.

**Ordering principle**: leaves first. A module moves only after all its
internal-compiler dependencies have already moved, so that each new
submodule imports only from earlier ones and from `_monolith` (never the
reverse).

| # | Target submodule | Rationale |
|---|---|---|
| 2 | `_ast_helpers.py` | Pure leaves; no compiler deps. |
| 3 | `_vars.py` | Pure leaves. |
| 4 | `head_list_unify.py` | Runtime helpers; no compile-time deps. |
| 5 | `terms_to_ast.py` | Needs `_ast_helpers`, `_vars`. |
| 6 | `star_segments.py` | Needs `terms_to_ast`, `_ast_helpers`. |
| 7 | `globals_env.py` | Needs `_vars`. |
| 8 | `head_match.py` | Needs `terms_to_ast`, `head_list_unify`. |
| 9 | `ite_reified.py` | Needs `terms_to_ast`. |
| 10 | `tabled_naf.py` | Small, isolated. |
| 11 | `control_constructs.py` | See cycle note below. |
| 12 | `goal_shallow.py` + `goal_trampoline.py` (paired) | Cycle with control_constructs. |
| 13 | `list_dispatch.py` | Standalone. |
| 14 | `arg_index.py` | Largest self-contained bloc. |
| 15 | `destructive_reuse.py` | Standalone. |
| 16 | `tro.py` | Depends on dispatch utilities. |
| 17 | `predicate.py` | Top-level entrypoints — last, so everything it calls is in place. Also owns the `_compile_context_local` thread-local. |

### Cycle handling (Phase 11/12)

`control_constructs` calls back into `compile_goal` / `compile_goal_trampoline`,
which in turn dispatch into control constructs. Two options:

- **(Chosen, refactor-free)** Move `control_constructs` and both
  `goal_*` modules as a linked trio; accept a module-level
  `from . import goal_shallow as _gs` inside `control_constructs.py` and
  resolve the cycle via lazy attribute access at call time (which is what
  happens today anyway, since both live in the same module).
- (Rejected for this pass) Inject the goal-compiler as a callable
  parameter. That's a refactor — defer to after the split.

### Phase 18 — Retire `_monolith.py`

Once every phase 2–17 has completed, `_monolith.py` contains only
`from .<submodule> import *` lines. Replace `__init__.py` with explicit
re-exports of the public API (verified against the Phase 0 external-API
list) and delete `_monolith.py`. `pytest`. Final commit.

### Phase 19 — Per-submodule docstrings

Each new file gets a module docstring summarising its role. Content is
copied (not rewritten) from the block comments already present in the
original source. No behavioural change.

---

## Function inventory (source of truth for phase moves)

Line numbers are from current HEAD (commit `aae90b0`). All `def`/`class`
definitions at module level. Target column = submodule each function
moves to.

| Line | Name | Target |
|------|------|--------|
| 78 | `_set_of_dedup` | `globals_env` |
| 106 | `class _DbDispatchAdapter` | `globals_env` |
| 135 | `class _GlobalsDb` | `globals_env` |
| 218 | `_head_list_unify_input_py` | `head_list_unify` |
| 280 | `_head_multi_star_error` | `head_list_unify` |
| 287 | `_head_list_unify_output_py` | `head_list_unify` |
| 349 | `_body_star_unify` | `head_list_unify` |
| 373 | `_build_star_list` | `head_list_unify` |
| 452 | `_build_multi_star_list` | `head_list_unify` |
| 531 | `_in_iter` | `head_list_unify` |
| 544 | `_body_multi_star_unify` | `head_list_unify` |
| 634 | `_tramp_call` | `head_list_unify` |
| 656 | `_var_python_name` | `_vars` |
| 661 | `_collect_vars` | `_vars` |
| 757 | `_collect_head_types` | `globals_env` |
| 789 | `_collect_py_thunks` | `globals_env` |
| 820 | `_collect_types_from_term` | `globals_env` |
| 851 | `_dotted_name_from_loadattr` | `globals_env` |
| 869 | `_collect_call_targets` | `globals_env` |
| 911 | `_collect_globals_info` | `globals_env` |
| 987 | `_disp_key` | `globals_env` |
| 998 | `_merge_builtin` | `globals_env` |
| 1007 | `_inject_call_targets` | `globals_env` |
| 1087 | `_inject_resolved_targets` | `globals_env` |
| 1170 | `_preallocate_body_vars` | `globals_env` |
| 1199 | `_name` | `_ast_helpers` |
| 1203 | `_attr` | `_ast_helpers` |
| 1207 | `_call` | `_ast_helpers` |
| 1217 | `_fresh` | `_ast_helpers` |
| 1226 | `term_to_ast_expr` | `terms_to_ast` |
| 1539 | `arith_to_ast_expr` | `terms_to_ast` |
| 1589 | `_yield_none_stmt` | `_ast_helpers` |
| 1593 | `_assign` | `_ast_helpers` |
| 1602 | `_assign_mark` | `_ast_helpers` |
| 1606 | `_undo_stmt` | `_ast_helpers` |
| 1610 | `_if` | `_ast_helpers` |
| 1614 | `_in_iter_expr` | `_ast_helpers` |
| 1629 | `_compile_arith_cmp` | `control_constructs` |
| 1642 | `_deref_cmp` | `control_constructs` |
| 1656 | `_dispatch_call_iter` | `goal_shallow` |
| 1693 | `_is_star_list` | `star_segments` |
| 1698 | `_parse_star_segments` | `star_segments` |
| 1718 | `_count_stars` | `star_segments` |
| 1722 | `_compile_star_is` | `star_segments` |
| 1744 | `_compile_single_star_is` | `star_segments` |
| 1788 | `_compile_multi_star_is` | `star_segments` |
| 1834 | `_is_tabled_naf` | `tabled_naf` |
| 1847 | `_compile_tabled_naf_simple` | `tabled_naf` |
| 1897 | `_is_reifiable` | `ite_reified` |
| 1914 | `_compile_reified_ite` | `ite_reified` |
| 1938 | `_compile_reified_ite_eq` | `ite_reified` |
| 1992 | `_compile_reified_ite_fd` | `ite_reified` |
| 2037 | `_compile_general_ite` | `ite_reified` |
| 2127 | `compile_goal` | `goal_shallow` |
| 2510 | `_compile_once` | `control_constructs` |
| 2542 | `_compile_call_nth` | `control_constructs` |
| 2644 | `_compile_count_all` | `control_constructs` |
| 2715 | `_compile_setup_call_cleanup` | `control_constructs` |
| 2844 | `_compile_freeze` | `control_constructs` |
| 2947 | `_compile_when` | `control_constructs` |
| 3031 | `_compile_find_all_core` | `control_constructs` |
| 3141 | `_catcher_to_structural` | `control_constructs` |
| 3157 | `_compile_throw` | `control_constructs` |
| 3171 | `_compile_catch` | `control_constructs` |
| 3328 | `_compile_catch_trampoline` | `control_constructs` |
| 3441 | `_compile_goal_lambda` | `control_constructs` |
| 3513 | `_flatten_conjunction` | `control_constructs` |
| 3520 | `_hoist_lambda_args` | `control_constructs` |
| 3546 | `_compile_predicate_call` | `goal_shallow` |
| 3602 | `compile_body` | `goal_shallow` |
| 3626 | `_make_body_compiler` | `goal_shallow` |
| 3645 | `_step_expr` | `goal_trampoline` |
| 3650 | `_yield_step_stmt` | `goal_trampoline` |
| 3655 | `_assign_yield_step` | `goal_trampoline` |
| 3667 | `_inject_bucket_refs_trampoline` | `goal_trampoline` |
| 3746 | `_dispatch_call_trampoline` | `goal_trampoline` |
| 3823 | `compile_goal_trampoline` | `goal_trampoline` |
| 4287 | `_compile_predicate_call_trampoline` | `goal_trampoline` |
| 4372 | `_compile_reified_ite_trampoline` | `ite_reified` |
| 4393 | `_compile_reified_ite_eq_trampoline` | `ite_reified` |
| 4438 | `_compile_reified_ite_fd_trampoline` | `ite_reified` |
| 4481 | `_compile_general_ite_trampoline` | `ite_reified` |
| 4646 | `compile_body_trampoline` | `goal_trampoline` |
| 4694 | `_head_aliased_var_ids` | `destructive_reuse` |
| 4733 | `_collect_unify_pairs_from_and` | `destructive_reuse` |
| 4747 | `_flatten_and_goals` | `destructive_reuse` |
| 4761 | `_flatten_and_single` | `destructive_reuse` |
| 4771 | `_find_destructive_reuse_goals` | `destructive_reuse` |
| 4834 | `_apply_destructive_reuse` | `destructive_reuse` |
| 4862 | `_make_body_compiler_trampoline` | `goal_trampoline` |
| 4880 | `_get_head_arg` | `list_dispatch` |
| 4891 | `_lift_clause_at_pos` | `list_dispatch` |
| 4966 | `_classify_list_key` | `list_dispatch` |
| 4982 | `_find_list_dispatch_pos` | `list_dispatch` |
| 5007 | `_build_list_dispatch_guard` | `list_dispatch` |
| 5103 | `_is_deterministic_goal` | `tro` |
| 5184 | `_detect_tro_clause` | `tro` |
| 5247 | `_get_tro_check_indices` | `tro` |
| 5262 | `_tro_args_safe` | `tro` |
| 5344 | `_head_has_unifying_list_pattern` | `tro` |
| 5363 | `_list_has_nonvar_constant` | `tro` |
| 5377 | `_contains_star_unpack` | `tro` |
| 5386 | `_collect_var_ids` | `_vars` |
| 5410 | `_collect_bound_vars` | `_vars` |
| 5427 | `_compile_tro_tail` | `tro` |
| 5566 | `_build_predicate_trampoline_funcdef` | `predicate` |
| 5747 | `_compile_tro_body` | `tro` |
| 5796 | `compile_predicate_trampoline` | `predicate` |
| 6285 | `compile_predicate_trampoline_ast` | `predicate` |
| 6318 | `_compile_always_fail_trampoline` | `predicate` |
| 6346 | `_wrap_yields_with_output_guards` | `head_match` |
| 6415 | `head_to_match_pattern` | `head_match` |
| 6732 | `_compile_multi_star_guard` | `head_match` |
| 7063 | `compile_head_to_match_case` | `head_match` |
| 7338 | `_head_arg_patterns` | `head_match` |
| 7378 | `_arg_to_index_key` | `arg_index` |
| 7397 | `_runtime_arg_key` | `arg_index` |
| 7417 | `_static_call_key` | `arg_index` |
| 7438 | `_bucket_key` | `arg_index` |
| 7450 | `_joint_bucket_key` | `arg_index` |
| 7456 | `_extract_arg_key` | `arg_index` |
| 7502 | `_extract_first_arg_key` | `arg_index` |
| 7510 | `_build_arg_index` | `arg_index` |
| 7552 | `_build_first_arg_index` | `arg_index` |
| 7562 | `_analyze_index_positions` | `arg_index` |
| 7586 | `_build_joint_arg_index` | `arg_index` |
| 7633 | `_analyze_joint_index_positions` | `arg_index` |
| 7668 | `_make_joint_dispatch_simple` | `arg_index` |
| 7706 | `_make_joint_dispatch_trampoline` | `arg_index` |
| 7778 | `_build_secondary_index` | `arg_index` |
| 7823 | `_make_secondary_dispatch_simple` | `arg_index` |
| 7877 | `_make_secondary_dispatch_trampoline` | `arg_index` |
| 7927 | `_make_indexed_dispatch_simple` | `arg_index` |
| 7952 | `_make_indexed_dispatch_trampoline` | `arg_index` |
| 7982 | `_make_groundness_dispatch_simple` | `arg_index` |
| 8033 | `_make_groundness_dispatch_trampoline` | `arg_index` |
| 8155 | `_build_predicate_funcdef` | `predicate` |
| 8228 | `_shallow_to_trampoline` | `predicate` |
| 8251 | `compile_predicate_shallow` | `predicate` |

(Module-level thread-local at line 75: `_compile_context_local` → moves
to `predicate.py` with the compile entrypoints that set/read it.)

---

## Audit findings (detail)

### Duplicate / near-duplicate code

Shallow/trampoline twin pairs (similarity approximate, line spans from
current HEAD):

| Shallow | Trampoline | Similarity |
|---|---|---|
| `compile_goal` (2127–2509, 383 ln) | `compile_goal_trampoline` (3823–4286, 464 ln) | ~70% — Unify/Evaluate/ArithEq/cmp/And/Or/Not arms mirror verbatim |
| `compile_body` (3602–3623) | `compile_body_trampoline` (4646–4666) | ~90% — only leaf yield differs |
| `_make_body_compiler` | `_make_body_compiler_trampoline` | ~85% |
| `_compile_predicate_call` | `_compile_predicate_call_trampoline` | ~65% |
| `_compile_reified_ite` | `_compile_reified_ite_trampoline` | ~85% |
| `_compile_reified_ite_eq` | `…_eq_trampoline` | ~75% |
| `_compile_reified_ite_fd` | `…_fd_trampoline` | ~80% |
| `_compile_general_ite` | `_compile_general_ite_trampoline` | ~70% |
| `_compile_catch` | `_compile_catch_trampoline` | ~60% |
| `_make_joint_dispatch_simple` | `…_trampoline` | ~60% |
| `_make_secondary_dispatch_simple` | `…_trampoline` | ~75% |
| `_make_indexed_dispatch_simple` | `…_trampoline` | ~70% |
| `_make_groundness_dispatch_simple` | `…_trampoline` | ~50% |

Asymmetric runtime pair: `_head_list_unify_input_py` (218–277) vs
`_head_list_unify_output_py` (287–331).

### Function-local imports (25 distinct, 44 call sites)

- `PyThunk` at 2156, 3863, 5115
- `DictTerm, SetTerm` at 705, 1338
- `get_builtin_predicate, BuiltinPredicate` at 1021, 1105
- `KWTerm` at 725, 1473
- `import sys as _sys` at 1056, 1143
- `Keyword as KWNode` at 3561, 4315
- `clpfd`, `constraints`, `coroutining`, `variables` submodules in
  5855–5870, 5920–5931

### Long functions (>150 lines)

- `compile_predicate_trampoline` — 489 (5796–6284)
- `compile_goal_trampoline` — 464 (3823–4286)
- `compile_goal` — 383 (2127–2509)
- `_compile_multi_star_guard` — 331 (6732–7062)
- `compile_predicate_shallow` — 320 (8251–8570)
- `head_to_match_pattern` — 317 (6415–6731)
- `term_to_ast_expr` — 313 (1226–1538)
- `compile_head_to_match_case` — 275 (7063–7337)
- `_build_predicate_trampoline_funcdef` — 181 (5566–5746)
- `_compile_general_ite_trampoline` — 165 (4481–4645)
- `_compile_catch` — 157 (3171–3327)

### Deep nesting

- `head_to_match_pattern` — depth 10
- `compile_goal_trampoline` — depth 9
- `compile_goal` — depth 8
- `_compile_multi_star_guard` — depth 7

### Magic strings

`"_m"` ×24 (mark-var prefix); `"trail"` ×11; `"_tramp_parent"` ×10;
`"this_generator"` ×7; `"k"` ×4; `"_disp_"` ×2; builtin names `"unify"`
×23, `"_dif"` ×6, `"_fd_eq"` ×6.

### Parameter bloat

Only one function exceeds 7 positional args: `_compile_reified_ite_eq`
(9). The tuple `(db, var_context, trail_name, k_stmts[, self_name,
parent_name])` threads through 20+ callees — candidate for a context
object (deferred).

### Mutable state

Only `_compile_context_local: threading.local()` at line 75 (documented
Phase 7). No other module-level mutables. No mutable defaults.

### Naming inconsistencies

- `_py` suffix inconsistent on runtime helpers
  (`_head_list_unify_input_py` vs `_body_star_unify`).
- `compile_goal` (shallow) has no suffix but peer is
  `compile_goal_trampoline`.
- `compile_predicate_shallow` / `compile_predicate_trampoline` are
  explicit — preferred pattern.
- Public/private mixing: `compile_goal` public,
  `_compile_catch_trampoline` private despite similar role.

### Clean aspects

- No bare `except` / `except Exception:`.
- No `print` / debug statements.
- No `if False:`, no commented-out code, no TODO/FIXME/XXX.
- No dead private helpers.
- No mutable default arguments.

---

## Split-boundary signals (populated during Phase 0.5a)

Record here any circular-import conflicts discovered while hoisting
inner imports. A cycle between modules A and B is a signal that:

- They belong in the same submodule, **or**
- One depends on the other's *interface* only (candidate for lazy
  import that survives the split), **or**
- The boundary as drawn in "Target layout" above is wrong and needs
  revision.

(Empty until Phase 0.5a runs.)

---

## Rollback plan

Every phase is a separate commit. If any phase breaks something the
tests don't catch:

- `git revert` the offending phase leaves prior phases intact.
- Phase 1 (package conversion) is the only "risky" step in the sense
  that it touches the packaging shape — revert is still clean because
  it's a pure rename plus a shim.
- The `_monolith.py` staging file exists from Phase 1 through Phase 17
  specifically to make partial rollback possible: if phase N
  misbehaves, revert puts the symbols back in `_monolith.py` without
  touching already-migrated submodules.
