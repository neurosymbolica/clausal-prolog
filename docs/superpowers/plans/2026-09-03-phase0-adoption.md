# Phase 0 adoption: `_clausal_new` in the walk/copy rebuilders + macro measurement

Spec: implementation_plans/tagged-tuple-term-representation.md §Phases Phase 0 (the deferred
"rebuilders adopt it later" half). Scope approved in-session 2026-09-03. CLONE ONLY — never
touch /workspace/clausal.

## Global Constraints

- Work ONLY in /workspace/clausal-bug-fix/.claude/worktrees/phase0-adoption (branch feat/phase0-adoption); run everything from there with `/workspace/clausal/venv/bin/python`.
- NEVER `git add -A`; stage explicit paths. Commit trailer (two lines):
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01G7xiWqatWtL6zNQDc7nspk
- The fast-path gate is IDENTICAL at every site: `type(term)`'s OWN dict entry for `"_clausal_new"` is a `classmethod` object → call `cls._clausal_new(<walked field values, in field order>)`; anything else → the existing `cls(**kwargs)` path byte-identical. (The name-only check is WRONG: a field literally named `_clausal_new` puts a member descriptor in the class dict — that bug was already fixed once in terms_to_ast.py; see tests/test_fast_construction.py::test_field_named_clausal_new_keeps_keyword_emission.)
- Sites that build heads from possibly-partial field dicts (specialization.py, reflection.py, modules/reflection.py) are OUT OF SCOPE — slow path stays.
- "KEEP THE THREE WALKERS IN SYNC" (solve.py:78 comment) binds: the Python walkers and their C twins must make the same fast/slow decision on the same terms.
- TDD for Python; C verified by parity tests + full-suite failure-set diff vs baseline_failures.txt (worktree root; capture in flight at plan time — Task 1 must confirm it exists and has ~142-145 lines before relying on it).
- <harness-library> is GATE_CORE — do not touch it.

## Task 1: Python rebuilders adopt the fast path

Files: `clausal/logic/solve.py` (~line 85, `_deref_walk_py`), `clausal/logic/builtins/inspection.py` (~line 77, `_copy_term_py`), new tests in `tests/test_fast_construction.py` (EXTEND, do not rewrite).

Both sites currently do `type(term)(**{name: <recurse>(getattr(term, name)) for name in term_field_names(term)})` — saturated by construction (every field walked). Change each to:

```python
cls = type(term)
fast = vars(cls).get("_clausal_new")
if isinstance(fast, classmethod):
    return cls._clausal_new(*( <recurse>(getattr(term, name)) for name in term_field_names(term) ))
return cls(**{name: <recurse>(getattr(term, name)) for name in term_field_names(term)})
```

(Adapt spelling to each site; the `__walk__`-hook delegation above `_deref_walk_py`'s term arm is untouched. `term_field_names` returns `_fields` order for PredicateMeta classes — assert that in a test rather than assuming.)

Tests (write FIRST; RED requires temporarily observing the slow path — e.g. monkeypatch-delete `_clausal_new` is NOT valid RED; instead assert via instrumentation that the fast constructor is used: patch `cls._clausal_new` with a wrapper that records calls, then `_deref_walk_py`/`_copy_term_py` a nested term and assert (a) result equality with the pre-change semantics and (b) the wrapper fired):
1. `_deref_walk_py` on a nested PredicateMeta term with bound Vars: result == old-style `cls(**walked)` reconstruction, fresh object, fully deref'd.
2. Same for `_copy_term_py` (vars renamed via var_map, structure preserved).
3. A dataclass term (e.g. a pythonic_ast node) goes through the slow path unchanged (no `_clausal_new` in vars → kwargs path) — walk result equals input semantics.
4. A class with a field literally named `_clausal_new` walks/copies correctly via the slow path (no crash, correct fields).
5. Field-order assertion: for `make_predicate("p", ["b", "a"])` (non-alphabetical), walked result has `.b`/`.a` correctly assigned.

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_fast_construction.py tests/test_predicate_meta.py -q`; then the full suite ONCE (`-q --tb=no --continue-on-collection-errors`), failure-set name-diff vs baseline_failures.txt must be empty. Commit explicit paths.

## Task 2: C twins adopt the same gate

Files: `clausal/logic/variables/_variables.c` (`do_walk` term-instance arm, ~lines 1720–1755: builds kwargs dict + `PyObject_Call(cls, empty, kwargs)`), `clausal/logic/_tabling_core.c` (`do_deref_walk`'s analogous term-instance arm — find it; it mirrors solve.py's `_deref_walk_py`), tests extended in `tests/test_fast_construction.py`.

In each C arm, before building the kwargs dict:
1. `PyObject *cls = (PyObject *)Py_TYPE(term);`
2. Look up the class's OWN dict: `PyObject *fastm = PyDict_GetItemWithError(((PyTypeObject *)cls)->tp_dict, <interned "_clausal_new">);` (handle error return; borrowed ref).
3. Gate: `fastm != NULL && PyObject_TypeCheck(fastm, &PyClassMethod_Type)`.
4. Fast path: build a positional `PyTuple` of the walked field values (same field iteration as today), get the bound callable via `PyObject_GetAttr(cls, <interned "_clausal_new">)`, `PyObject_Call(bound, args_tuple, NULL)`, decref properly on every path.
5. Slow path (gate false): existing kwargs code byte-identical.
Intern the `"_clausal_new"` string once at module init, following how each file interns other strings.

Verification:
- Rebuild: `/workspace/clausal/venv/bin/python setup.py build_ext --inplace` (must succeed warning-clean for the touched files).
- Parity tests (add to tests/test_fast_construction.py): for a corpus of terms — nested PredicateMeta term with bound+unbound Vars, dataclass node, field-named-`_clausal_new` class, term with `position`-named field — assert `_deref_walk_py(t) == _deref_walk_c(t)` (import from `clausal.logic._tabling_core`) and the `walk()`/copy C path (`clausal.logic.variables._variables`) matches its Python twin. Skip-guard the C imports the way existing tests do if the extension is absent.
- Full suite ONCE + failure-set name-diff vs baseline_failures.txt: must be empty.
- Refcount sanity: run the parity test file twice in one process (`pytest tests/test_fast_construction.py tests/test_fast_construction.py -q`) — no crash/leak blowup.
Commit explicit paths (.c files + test file).

## Task 3: macro A/B measurement (no source changes; report only)

Compare pre-Phase-0 (commit f0db3fb0) against this branch's HEAD (post Task 2) on the repo's macro workloads.

- Create a throwaway baseline worktree: `git worktree add /workspace/clausal-bug-fix/.claude/worktrees/phase0-macro-baseline f0db3fb0` then `build_ext --inplace` inside it (REQUIRED — stale/absent .so files invalidate the comparison).
- Read `benchmarks/workloads.py` and `benchmarks/run_cprofile.py` to find the workload entry points (fib, graph, nqueens, qsort, tabling profiles exist under benchmarks/profiles/).
- Driver (write in the SDD workspace or /tmp scratch, NOT committed): subprocess-run each workload alternately A,B,A,B,... ≥5 rounds each side, same venv python, cwd set to the respective worktree; record wall time per run; report median + spread per workload per side, and B/A ratio.
- Machine must be otherwise quiet: do not run the test suite or other heavy jobs concurrently.
- Report: table of per-workload medians A vs B with ratios, plus an honest one-paragraph read (which workloads are construction-heavy enough to move; "no significant change" is a valid and reportable outcome — do NOT torture the numbers).
- Cleanup: `git worktree remove --force /workspace/clausal-bug-fix/.claude/worktrees/phase0-macro-baseline` (it will contain build artifacts; force is sanctioned for this throwaway).
- Nothing is committed by this task.
