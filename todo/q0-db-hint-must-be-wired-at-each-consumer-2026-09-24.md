# The Q0 db= hint is additive — each consumer must pass its db as it migrates

**Filed:** 2026-09-24, with the Q0/X3 accessors (roborev Medium on that branch).

The era-agnostic resolvers (`resolve_predicate_row`, `is_declared_predicate`,
`is_declared_predicate_name`, `predicate_binding_name`,
`predicate_arities_for`, all via `_resolve_mangled_owner`) take an optional
`db=` — the CALLER's database — so a handle to a module the `.clausal` runner
popped from `sys.modules` still resolves locally (ruling Q0). When it landed,
NO production caller passed it; before the flip no predicate binding is a
handle, so nothing needed it. Likewise `mint_predicate_handle(db, functor)`
(ruling X3) had no production caller.

**This is a flip checklist item, not optional:** after the flip a resolver
call WITHOUT `db=` silently answers None for every local handle in a popped
test module (43/46 measured descents).

Wire at: F1 rows 58/59 (`_find_pred_cls`/`_namespace_dispatch`), row 60
(`_indicator_row`), and every flip-time call site in `compiler_v2`,
`database.py`, `io.py`, `seam.py`, `constants.py`, `import_diagnostics.py`,
`predicate_diagnostics.py` that has a db in scope (roborev listed them). The
flip itself mints bindings with `mint_predicate_handle`.

Check for done: `grep -rn "resolve_predicate_row\|is_declared_predicate\|predicate_binding_name\|predicate_arities_for" clausal` — every call with a db in scope passes it.

**Wired (branch fix/w4b-self-atom-plain-2026-09-24):** `solve._templatize_query_goal`
(`_compile_as_query` passes `module.db`) and `terms_to_ast.term_to_ast_expr`'s
self-denoting-atom arm (reads the lowering scope's `$module` db via
`_lowering_db()`; the query compile's scope carries it, so a nested handle in a
popped module's query resolves too).

## Status 2026-09-24 (branch fix/q0-wire-db-hint-2026-09-24) — STILL OPEN

Every call site of the five resolvers in `clausal/` was enumerated with the
done-check grep.  Every site with a Database in scope now passes it.  Tests:
`tests/test_q0_db_hint_consumers.py` has one test per consumer family; each
plants a handle minted with `mint_predicate_handle(db, …)` in a module popped
from `sys.modules` and checks the no-hint control first.  Mutation check:
dropping the hint at each tested site (13 mutations) fails exactly that
family's test.

**Measured trap, and why the load channel threads its LOCAL db.** Inside
`compile_module`, `module_dict["$module"]` is still the import hook's
PLACEHOLDER `LogicModule`. Its Database shares the module dict, so its
`module_name()` is the real one: it captures every local handle and answers
from an empty store (probe: `$module.db is not` compile_module's `db` at
`_import_from_origins`; pinned by
`test_a_same_named_placeholder_db_captures_the_handle_and_answers_nothing`).
So the `compiler_v2` helpers take compile_module's `db` as a keyword and do
NOT read `$module`. The namespace-derived hints below (`terms_to_ast`,
`head_match`, `constants`, and the self-atom `_lowering_db()`) still see the
placeholder DURING a load. That is no worse than the no-hint route: the module
is in `sys.modules` mid-load, so `_db_for_module_name` returns the same
placeholder. After the load they get the real db. **At the flip, a
namespace-derived hint needs the real db mid-load**, either by swapping
`$module` before step 3 or by pushing compile_module's db into the lowering
scope.

### Wired (db passed = the caller's)

| site | db passed | tested |
|---|---|---|
| compiler_v2 `_import_from_origins` (predicate_binding_name) | compile_module's `db` (new kw) | yes (M1) |
| compiler_v2 `_belongs_elsewhere` | `db` param | no: a local handle is never "elsewhere", so the answer is the same either way |
| compiler_v2 `_imported_binding_by_canonical_name` | `db` param | no: same reason (None either way) |
| compiler_v2 `_redefinition_error` | compile_module's `db` (new kw, via `_refuse_foreign_writes`/`_load_gate`) | no: diagnostic text only |
| compiler_v2 `_validate_directive_targets` | `db` param | no |
| compiler_v2 `_refuse_untablable_target` | `db` param | no |
| compiler_v2 `_meta_interpreter_row` (3 calls; NOT wired on main before this) | `db` param; `predicate_arities_for`'s class arm uses it only when the class's owner IS this module, which is correct | yes (M2) |
| compiler_v2 `_run_specialization` source check | `db` param | no |
| compiler_v2 `_process_declarations` | compile_module's `db` (new kw) | no: the class arm ignores it |
| database `_write_rows` → `_resolve_through_row` | `self` (the written db; new kw) | yes (M3) |
| solve `call` Phase 5 | `module.db` | yes (M8) |
| solve `_ground_value` | already wired | — |
| builtins/control `_goal_dispatch_and_args` | `db` param | yes (M9) |
| builtins/dcg `phrase/2`, `phrase/3` | `db` param | yes (M10/M10b) |
| builtins/io `_listing__1` class arm | `db` | no-op (inside `isinstance(val, PredicateMeta)`) |
| builtins/io `_is_predicate_handle`, database_ops `_find_pred_cls`/`_canonical_functor`/`_binding_row` | already wired | — |
| globals_env `_is_call_target` (new kw, 3 callers), `_atom_shadows_row`, `_maybe_cache_dispatch`, dotted-name fallback | `_inject_resolved_targets`' `db` | yes (M4/M6) |
| arg_index `hint_row` | `db` (the `_GlobalsDb` shim is tolerated by `predicate._hint_db`: no `module_dict` = no hint) | yes (M5; L1 for the tolerance) |
| control_constructs `_lower_catcher` | `ctx.db` | no |
| terms_to_ast `cell_signature_for_name`, OWA gate (~1118) | the lookup namespace's `$module` db | yes (M7) |
| terms_to_ast `term_to_ast_expr` self-atom arm | already wired (`_lowering_db()`) | — |
| head_match OWA gate (~758) | `globals_`' `$module` db | no |
| specialization `_solve_goal_dispatch` | `module_dict`'s `$module` db (read at run time, after the load) | no |
| constants `constant_functor_term` | namespace's `$module` db | no |
| import_diagnostics `_defined_names` | `mod`'s own `$module` db | yes (M11) |
| predicate_diagnostics `_local_entries` → `_arities_of` (new kw) | `_describe`'s `db`; class arm uses it only for this module's own classes | yes (M12) |

### Left without a hint (reason)

- **No Database reaches these runtime builtins:** higher_order `_is_goal`
  and the 18 list/higher-order builtins that call
  `_ensure_trampoline_dispatch` without a db (maplist, foldl, ...),
  inspection `functor/3` and `=../2`, type_checks `callable/1`. Post-flip
  each one needs to receive a db, or a db-receiving registration.
  `_ensure_trampoline_dispatch` itself now takes `db=` (time_goal passes it).
- `predicate._import_index` (`is_declared_predicate_name(v)`): an IMPORT
  index; a local handle is dropped right after (`owner is db`), so no hint
  is needed.
- **A handle cannot reach these sites:** a `str` arm comes first, or the body
  reads `__name__`. That covers terms_to_ast `_is_opaque_head_literal` and
  `_dictterm_key` (~1284), head_match head-literal (~870), seam `build`
  (~153, whose mangled arm returns first), and arg_index
  `_arg_to_index_key`/`_runtime_arg_key`.
- **No database exists here:** the globals_env `_GlobalsDb.signature_for`
  class fallback runs only when no `$module` is present.
- **The population is foreign:** predicate_diagnostics `_imported_entries` and
  `_defines` look at other modules. The hint only short-circuits the caller's
  OWN module. (The popped cross-module owner is now answered by the
  handle-owner registry -- see "Q0 remainder" below.)
- **Post-flip defects outside Q0, found on the way:**
  `constants.constant_functor_term` calls `binding(*args)`, and a handle str is
  not callable. `import_diagnostics._defined_names` calls
  `field_names_for(value)` without its `db=`. The `cell_signature_for_name`
  predicate arm reads `term_field_names_of_class(binding)`, which answers None
  for a handle.

### Round 2 (roborev on the branch, 2026-09-24)

- **The dispatch funnel, done.** `_dispatch_at(obj, arity, db=None)` and
  `cells.qualify_mangled_goal(goal, db=None)` take the hint.
  `_dispatch_at`'s handle arm resolves a handle naming the caller's own
  module in the caller's db instead of `resolve_module` (sys.modules).
  Threaded from solve.call Phase 5 (`module.db`), phrase/2,3,
  time_goal/1 (via `_ensure_trampoline_dispatch(..., db)`) and
  `_solve_goal_dispatch`. There is one home for the local-first rule:
  `predicate._owner_db_for_module_name`. Tests run call/phrase/time_goal
  END TO END on a popped module's handle. Mutation R1-R9 (dropping the hint
  at each call, gate and funnel) fails them.
- `predicate._hint_db`: a db without a real `module_dict` dict is no hint,
  so callers pass the `_GlobalsDb` shim unguarded (L1).
- `predicate.namespace_db(ns)`: the one reader of `ns["$module"].db`. The
  six hint sites, `_lowering_db` and `_db_for_module_name` all use it, and its
  docstring records the placeholder trap. **The flip fix belongs there.**
- Load channel at compile_module's real point:
  `test_load_channel_hint_at_compile_module_s_own_point` spies step 3c. The
  predicate is export-declared with no row yet. The no-hint route and the
  placeholder db both miss the handle; compile_module's local db resolves
  it. The other load-channel tests run after the load, against the finished
  db, and test the helper's wiring, not the load-time state.
- These mutations give the same answer with or without the hint, as
  expected: solve.call's other-arity gate (M8; the dispatch gate after it is
  hinted and reaches the same resolution), `_belongs_elsewhere` (M14) and
  `_imported_binding_by_canonical_name` (M13).

## Round 3 review (landed with these open, 2026-09-24)
- ~~solve.py:1122 -- `call(handle, ..., module=lm)` with the functor itself a handle goes
  through `qualify_mangled_goal(functor)` / `resolve_module` WITHOUT the hint (only the
  alias route is tested).~~ **CLOSED** (branch fix/q0-runtime-registry-2026-09-24):
  `solve.call` passes the calling module's db (a `Module`, or an imported module's
  `__clausal_module__`); test
  `test_runtime_call_with_a_handle_functor_passes_the_module_s_db` (both designator
  shapes), mutation-checked.
- ~~predicate.py `_UnqualifiedName.dispatch_at`: `return _dispatch_at(self.binding, arity)`
  -- pass `db=self.db` (it already feeds binding_grants_arity).~~ **CLOSED** (same
  branch): passes `db=self.db`; test `test_unqualified_name_dispatch_passes_its_db`,
  mutation-checked.
- specialization.py:1383-1389 computes `namespace_db(module_dict)` twice per call.

## Q0 remainder: the handle-owner registry (branch fix/q0-runtime-registry-2026-09-24)

Ruling Q0 (final): the caller's db first; a registry ONLY for the cross-module
remainder. `predicate._owner_db_for_module_name` is the HANDLE-ONLY rule:
caller's db -> by identity, the owner the caller adopted a row from
(`Database.adopted_owner_dbs`) -> `sys.modules` -> the weak registry
`_HANDLE_OWNERS` (filled by `compile_module`). `resolve_module` (a user-written
`M:G`, `module=`) is untouched: `qualify_mangled_goal` carries the owner's Module
OBJECT when `sys.modules` cannot answer the name (`handle_designator`). Name reuse
with two live owners raises `AmbiguousHandleOwnerError` (after one gc pass).
`_field_names_for_name` honours its `db`. Tests: `tests/test_handle_owner_registry.py`.
The hint tests here pop the registry entry so their no-hint controls stay
meaningful.

