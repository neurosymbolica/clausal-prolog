# clausal/logic/ — the engine core

Everything that runs a program once it has been read: logic variables and the
trail (C), the trampoline that drives compiled predicates, the predicate
compiler, the clause database, builtins, constraint solvers, tabling/WFS,
exceptions, and the term representation (atoms, cells). Source surfaces
(`.clausal`, `.pl`, `.seam`) are parsed elsewhere and arrive here as module
items for `compiler_v2.compile_module`. Tests for this folder live in the
repo-root `tests/`. Up: [../AGENTS.md](../AGENTS.md)

## Map

**Terms and variables**

| Path | What |
|---|---|
| `variables/` | `Var`/`AttVar`, `Trail`, `unify`, `deref`, attribute hooks. `__init__.py` re-exports the C extension `_variables.c` (no Python fallback; `Var` is `AttVar`). `_variables_capi.h` is the capsule API other C extensions include; `_ft_compat.h` holds free-threading shims. |
| `atoms.py` | Atoms are `str`: `mint`, `spelling`, `is_atom`, char atoms, truth atoms, `-hide` mangling. |
| `cells.py` | Compound terms as plain tuples `(functor, *args)`: `make_cell`, `is_cell`, the `('$chars', text)` string carrier, the reserved 1-tuple, cell interning. |
| `python_terms.py`, `to_python.py` | Python object <-> term conversion (registered per class; no generic converter) and term -> Python outbound. |
| `generated_names.py` | The `$`-prefixed runtime names generated code binds. |

**Running programs**

| Path | What |
|---|---|
| `solve.py` | Public query API: `solve`, `query`, `once`, `call`, `query_wfs`, module resolution. Start here for "how does a query run". |
| `trampoline.py` | Step protocol (`(target, value)` tuples, `DONE`, `StepGenerator`); re-exports C `runtime/_trampoline.c`, else `_trampoline_py.py`. |
| `runtime/` | Helpers called *by generated code* via `base_globals`: `list_unify.py` (+ `_list_unify.c`), `body_star_unify.py`, `tramp_call.py` (simple->trampoline bridge), `const_set.py`, `dict_ops.py`, `_seg_helpers.py`. |
| `seam.py` | The `--term` seam: builds a runtime term from Python-hosted code. |
| `continuation_search.py` | Greenlet `Search`; no production callers (only `tests/test_continuation_search.py`). |

**Compiling**

| Path | What |
|---|---|
| `compiler_v2.py` | Module-level compile: `compile_module(...)` (called from `clausal/import_hook.py`) handles imports, directives, clause assertion, predicate compilation, tabling wraps, locking. |
| `compiler/` | Per-predicate compiler: clauses -> Python generator function. See [compiler/AGENTS.md](compiler/AGENTS.md). |
| `database.py` | `Clause`, `PredRow`, `Database`, `Module`: the clause store and write gates. |
| `predicate.py` | Predicates as `Database` rows named by handles (`mint_predicate_handle`, `_dispatch_at`). Not the same as `compiler/predicate.py`. |
| `term_expansion.py`, `goal_expansion.py` | `term_expansion/4` and body goal-expansion passes before compilation. |
| `meta_predicate.py`, `constants.py`, `stratification.py`, `specialization.py`, `translations.py` | `-meta_predicate`, `-constants`, negation-cycle analysis, meta-interpreter partial deduction, `-translations`. |
| `dialect_edge.py` | The one-way gate: `.pl` may call `.clausal`, never the reverse; Clausal Prolog reaches Python only via `.seam`. |

**Builtins, errors, control**

| Path | What |
|---|---|
| `builtins/` | All registered builtin predicates. See [builtins/AGENTS.md](builtins/AGENTS.md). |
| `exceptions.py` | `LogicException`, ISO error-term constructors (`type_error`, `instantiation_error`, ...), `catch_match`. |
| `coroutining.py` | `freeze/2`, `when/2` on attributed variables. |
| `reif.py` | Reified equality/disequality (`eq__3`, `dif_t__3`, `reif_dif__3`), truth values as data. |
| `exact_arith.py` | Shared exact arithmetic and the evaluable-functor table (`EVALUABLE`). |

**Constraints and tabling**

| Path | What | C backing |
|---|---|---|
| `constraints.py` | `dif/2` | `_constraints_dif.c` |
| `clpfd.py` | CLP(Z) solver | `_clpfd_core.c` (domains), `_clpfd_propagate.c` (propagation); both include `_clpfd_domain_ops.h` |
| `clpz_surface.py` | Scryer-named `in/2`, `ins/2`, `labeling/2`, reified connectives over `clpfd` | |
| `clpb.py` | CLP(B) via BDDs | `_clpb_core.c` |
| `clpq.py` / `clpr.py` | CLP(Q) (exact simplex) / CLP(R) (intervals) | `clpr`: `_clpr_core.c` |
| `clpz3.py`, `clportools*.py`, `clpsat.py` | Optional Z3, OR-Tools (CP-SAT, LP, graph, routing), PySAT backends | |
| `units_clp.py`, `units_constraint.py`, `_units_flag.py` | Physical-units side channel around CLP | |
| `tabling.py` | SLG tabling and WFS (delayed negation, `_naf_tabled`) | `_tabling_core.c` |

## C extensions

All listed in the repo-root `setup.py`; built by `pip install -e .`. After editing
any `.c`/`.h` file, rebuild with `python setup.py build_ext --inplace` (the `.so`
files sit next to the sources and are not tracked).

| Extension module | Source | Used by |
|---|---|---|
| `clausal.logic.variables._variables` | `variables/_variables.c` | `variables/__init__.py` (required) |
| `clausal.logic.runtime._trampoline` | `runtime/_trampoline.c` | `trampoline.py` |
| `clausal.logic.runtime._list_unify` | `runtime/_list_unify.c` | `runtime/list_unify.py` |
| `clausal.logic._clpfd_core`, `._clpfd_propagate` | `_clpfd_core.c`, `_clpfd_propagate.c` | `clpfd.py` |
| `clausal.logic._tabling_core` | `_tabling_core.c` | `tabling.py`, `solve.py` |
| `clausal.logic._constraints_dif` | `_constraints_dif.c` | `constraints.py` |
| `clausal.logic._lists_core` | `_lists_core.c` | `builtins/lists.py` |
| `clausal.logic._arithmetic_core` | `_arithmetic_core.c` | `builtins/arithmetic.py` |
| `clausal.logic.builtins._chars_core` | `builtins/_chars_core.c` | `builtins/chars.py` |
| `clausal.logic._clpr_core`, `._clpb_core` | `_clpr_core.c`, `_clpb_core.c` | `clpr.py`, `clpb.py` |

## Gotchas

- Every extension except `_variables` is optional: the Python module does
  `try: import ... except ImportError` and keeps a pure-Python twin. A change to
  behaviour must land in BOTH (C and `_py` twin); `tests/test_trampoline_parity.py`
  runs one corpus against both trampolines.
- Extensions that need fast var access include `variables/_variables_capi.h`
  with `VARIABLES_CAPI_CONSUMER` and fetch the function table by capsule at init.
- `runtime/` must not import `clausal.logic.compiler`
  (`tests/test_runtime_compiler_boundary.py`).
- `Trail` objects are per-thread (enforced); see the threading contract in
  `variables/__init__.py` and [free_threading.md](../../docs/free_threading.md).
- Many cycles are broken with function-local imports (`# noqa: PLC0415`); keep
  new imports local when the module graph is cyclic.

## Docs

[architecture.md](../../docs/architecture.md) ·
[compiler.md](../../docs/compiler.md) · [tabling.md](../../docs/tabling.md) ·
[wfs.md](../../docs/wfs.md) · [constraints.md](../../docs/constraints.md) ·
[clpb.md](../../docs/clpb.md) · [clpq.md](../../docs/clpq.md) ·
[clpr.md](../../docs/clpr.md) · [z3.md](../../docs/z3.md) ·
[exceptions.md](../../docs/exceptions.md) ·
[coroutining.md](../../docs/coroutining.md) ·
[specialization.md](../../docs/specialization.md) ·
[term_expansion.md](../../docs/term_expansion.md)
