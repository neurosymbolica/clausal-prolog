# Phase 1: funnel refactor — fill the accessor gaps, migrate the safe probe sites

Spec: implementation_plans/tagged-tuple-term-representation.md §Phases Phase 1 ("prep that pays
regardless"), reshaped 2026-09-03 by a full site inventory: gap-fill first, then a TARGETED
migration with an explicit exclusion list — not a blind sweep. CLONE ONLY.

## Global Constraints

- Work ONLY in /workspace/clausal-bug-fix/.claude/worktrees/phase1-funnel (branch feat/phase1-funnel); all commands from there with /workspace/clausal/venv/bin/python.
- NEVER `git add -A`; NEVER `git stash`. Explicit paths. Commit trailer (two lines):
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01G7xiWqatWtL6zNQDc7nspk
- Full-suite runs: exactly `/workspace/clausal/venv/bin/python -m pytest tests/ -q --tb=no --continue-on-collection-errors`; failure-set NAME-diff vs baseline_failures.txt (worktree root) must be empty for every task.
- This phase is BEHAVIOR-PRESERVING. Every migration must keep observable semantics identical; where the inventory marked a site as semantics-diverging, it is excluded below. One sanctioned exception: repl.py (see Task 3) where funneling fixes a latent crash on dataclass terms — that fix is deliberate and must be tested.
- **EXCLUSION LIST — do not touch these (from the 2026-09-03 inventory), each for cause:**
  1. `arg_index.py` `_runtime_arg_key`/`_arg_to_index_key` (hand-ordered hot cascade; branch order load-bearing).
  2. `tabling.py` `_normalize_for_key_py` (byte-parity with `_tabling_core.c` twin).
  3. The five synced walkers: `solve.py:_deref_walk_py`, `inspection.py:_copy_term_py`/`_collect_vars_py`, and their three C arms.
  4. `constraints.py` `_structural_unify_oc` (unify inner loop, already funneled).
  5. `head_match.py` `_matched_field_names` (deliberately narrower than term_field_names — drops compare=False dataclass fields).
  6. `coroutining.py` nonvar/ground name probes (nominal-only by design; funnel would WIDEN matching).
  7. `clausal/terms.py` lines ~180–280 (`KWTerm._fields` is a keyword dict, NOT PredicateMeta._fields).
  8. `specialization.py` / `compiler_v2.py` / `compiler/predicate.py` class-registry `_fields`/`PredicateMeta` uses (class-level ops, not term probes) — EXCEPT the two class-arity reads named in Task 3.
  9. All CPython-`ast` sites: `codegen.py`, `compiler/_ast_helpers.py`, `compiler/predicate.py:1293`, `compiler/invariants.py`, `templating/*`, `tools/prolog_ast.py`, `reflection.py:1027`.
  10. All `type(x).__name__`-in-error-message sites (clp*/clportools*/modules/py/*/exceptions.py/_trampoline_py.py etc.).
  11. `predicate_diagnostics.py` / `import_diagnostics.py` (deliberately tolerant getattr for foreign-copy objects).
  12. `terms_to_ast.py:741` (predicate-class-in-term-position ERROR check — not an atom probe).
  13. `modules/reflection.py:291` — the name lookup may be funneled but the follow-up CLASS IDENTITY re-check must stay.
  14. `goal_expansion.py` — has an unrelated module-local `_functor_name`; if a funnel import is ever needed there, alias it (`from ... import _functor_name as _term_functor_name`). Prefer not touching the file.
- pythonic_ast dataclass handling: new accessors must treat dataclass term instances exactly as `term_field_names`/`is_term_instance` do today.

## Task 1: fill the funnel gaps (new accessors + is_atom adoption inside the funnel)

Files: `clausal/logic/builtins/_helpers.py`, `clausal/logic/predicate.py`, new `tests/test_funnel_accessors.py`.

New accessors (Python implementations; route through existing C-accelerated funnels internally where applicable; no new C code in this phase):
1. `term_field_names_of_class(cls) -> tuple[str, ...] | None` in `predicate.py` next to `term_field_names`: PredicateMeta class → `cls._fields`; dataclass class → dataclass field names in order, EXCLUDING nothing (same set `term_field_names` yields for an instance); anything else → None. Model on `head_match.py:201 _resolved_field_names` (read it first) but live in predicate.py as the canonical version.
2. `functor_arity(term) -> tuple[str, int] | None` in `_helpers.py`: one traversal; for term instances `(type(term).__name__, len(term_field_names(term)))`; Compound → `(functor, len(args))`; PredicateMeta atom class → `(name, 0)`; else None. Must agree with `_functor_name`/`_arity` composed (add a hypothesis-style or loop-corpus test asserting agreement on a shape corpus).
3. `term_field_values(term) -> tuple` in `predicate.py`: declared-field values in `term_field_names` order (term instances only; TypeError otherwise, mirroring `term_field_names`).
4. `term_field_dict(term) -> dict[str, Any]` in `predicate.py`: name→value for declared fields (the reconstruct-pattern helper).
5. `is_atom` adoption inside the funnel itself: replace the four hand-rolled `isinstance(x, PredicateMeta) and not x._fields` sites in `_helpers.py` (~lines 54, 79, 172, 368) with `is_atom` (import from predicate.py; check for import-cycle safety — _helpers already imports from predicate.py).
All exported via the modules' existing `__all__` conventions. TDD: tests first covering PredicateMeta terms, atoms, dataclass nodes, Compound, KWTerm, non-terms, and the field-order corpus (["b","a"]).

Run: focused new tests + `tests/test_predicate_meta.py tests/test_fast_construction.py`; full suite once, empty name-diff vs baseline.

## Task 2: migrate batch A — builtins + small compiler sites (mechanical, per-file list)

Files and exact changes (batched dispatch; every file listed must show a hunk):
- `clausal/logic/builtins/type_checks.py` (~66-76, ~152-158, ~323): three hand-rolled atom checks → `is_atom`.
- `clausal/logic/builtins/chars.py` (~63): hand-rolled atom check → `is_atom`.
- `clausal/logic/builtins/inspection.py` (~269-270): `_functor_name` + `_arity` double-walk → single `functor_arity`.
- `clausal/logic/builtins/io.py` (~128 `_format_clause_head`, ~175 class-arity): funnel via `functor_arity` / `term_field_names_of_class`.
- `clausal/logic/builtins/keyword_ops.py` (~32): reconstruct pattern → `term_field_dict` (do NOT change `vary/3` construction semantics — the `cls(**kwargs)` call itself STAYS; only the dict-building is funneled; unknown-key TypeError behavior is load-bearing).
- `clausal/logic/compiler/list_dispatch.py` (~170): reconstruct dict-building → `term_field_dict` (same rule: the `cls(**...)` call stays).
- `clausal/logic/compiler/_lower_goalop_shared.py` (one is_atom shape): → `is_atom`.
- `clausal/logic/compiler/terms_to_ast.py` (~191, ~633 is_atom shapes ONLY; 741 excluded): → `is_atom`.
- `clausal/logic/term_expansion.py` (~40): hand-rolled functor+arity probe → `functor_arity(head) == ("TermExpansion", 4)`.
- `clausal/logic/database.py` (~515 reconstruct dict): → `term_field_dict`; leave `head_key` itself as-is (it is the canonical pair function; do not rewrite it this phase).
TDD-light: for each file, the existing tests covering it must stay green (name the suites you ran per file in the report); add a regression test only where a migration has no existing coverage (report which).
Full suite once, empty name-diff.

## Task 3: migrate batch B — compiler walkers + reflection + repl (judgment sites)

Files and changes:
- `clausal/logic/compiler/globals_env.py`: the four near-identical `cls = type(term); types[cls.__name__] = cls` collector walkers — funnel the probe (`is_term_instance` guard + `type(term).__name__` read stays as the KEY on purpose; do NOT alter the name-keyed semantics — the known last-writer-wins collision bug in `_collect_globals_info` is out of scope, todo `assertz-foreign-same-named-functor-head-collision-2026-09-03.md`). Mechanical dedup into one local helper inside the module is allowed and encouraged.
- `clausal/logic/compiler/head_match.py` (~201 `_resolved_field_names`): delegate its PredicateMeta/dataclass class-cases to `term_field_names_of_class` (keep the function, keep any extra cases it handles; `_matched_field_names` untouched per exclusion 5).
- `clausal/logic/compiler_v2.py` (~650, ~679): class-arity reads → `term_field_names_of_class`.
- `clausal/repl.py` (~152, ~196-197): `type(goal)._fields` / `isinstance(type(goal), PredicateMeta)` → `is_term_instance` + `term_field_names`/`term_field_values`. THIS IS THE SANCTIONED BEHAVIOR FIX: today's code crashes on plain-dataclass terms; add a test proving a dataclass term now round-trips where it previously raised (mark the old behavior in the test docstring).
- `clausal/testing.py` (~799, ~1187 `__dataclass_fields__` direct reads → `term_field_names`; ~2089 hand-rolled functor-name fallback → `_functor_name` IF AND ONLY IF the fallback semantics match — check what `_functor_name` returns for a Compound head vs the current `getattr(head, "functor", None) or type(head).__name__` and keep current behavior if they differ; report the determination).
- `clausal/logic/clpb.py` (~387): the ad-hoc probe → `is_term_instance(expr)` + `_functor_name(expr)` (verify against the current double-check semantics; keep behavior identical for non-terms).
- `clausal/modules/reflection.py` (~291-292): funnel the name read; KEEP the class-identity re-check and its comment (exclusion 13).
Per-file test evidence as in Task 2. Full suite once, empty name-diff.

## Task 4: guard the funnel — bypass lint + perf non-regression

1. New test `tests/test_funnel_lint.py`: a grep-driven check (run via subprocess or pure-Python file scan) asserting no NEW direct-probe patterns appear outside the funnel modules and the exclusion list. Encode the exclusion list as data in the test with a comment pointing at this plan. The lint must pass on the migrated tree and FAIL if a disallowed `isinstance(x, PredicateMeta) and not x._fields` (or a `type(x).__name__`-as-functor probe in a non-excluded runtime file) is introduced — prove both directions in the test (self-test with a synthetic bad snippet in a tmp file, not by mutating the repo).
2. Perf non-regression: run `benchmarks/microbench.py` and `benchmarks/bench_term_construction.py` interleaved before/after the branch (A = merge-base c8503a97 via a throwaway worktree with build_ext, B = branch HEAD), 5 rounds; report medians. The funnel adds function-call indirection at cold/warm sites only — hot paths are excluded — so the acceptance bar is: no microbench worsens by >3% median. If one does, identify the site and report; do not tune benchmarks.
3. Full suite once, empty name-diff; cleanup any throwaway worktree (`git worktree remove --force` sanctioned for it).
