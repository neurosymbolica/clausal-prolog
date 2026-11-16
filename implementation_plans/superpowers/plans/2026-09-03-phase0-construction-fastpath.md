# Phase 0: term-construction fast path (approved design)

Spec: implementation_plans/tagged-tuple-term-representation.md §Phases "Phase 0" (this repo).
Design approved in-session 2026-09-03. Bounded change; no representation change.

## Global Constraints

- Work ONLY in worktree /workspace/clausal-bug-fix/.claude/worktrees/phase0-construction-fastpath (branch feat/phase0-construction-fastpath). Run all commands from that directory.
- Python: `/workspace/clausal/venv/bin/python` invoked FROM the worktree (cwd controls which clausal package is imported — verify with `python -c "import clausal; print(clausal.__file__)"` if in doubt).
- NEVER `git add -A` / `git add .` — stage explicit file paths only.
- Do NOT modify: any `.c` file, `_get_dispatch` anything, the behavior of `PredicateMeta.__call__` (the slow path stays byte-identical; the fast path is ADDITIVE).
- `pythonic_ast` dataclass nodes must NEVER take the fast path (their `__init__`s have defaults/validation).
- TDD: write the failing test first, watch it fail, then implement.
- End every commit message with:
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01G7xiWqatWtL6zNQDc7nspk

## Task 1: `_clausal_new` generated fast constructor on PredicateMeta classes

Files: `clausal/logic/predicate.py`, new `tests/test_fast_construction.py`.

In `clausal/logic/predicate.py`:
- Add a module-level cache + factory next to `_make_init` (~line 400):
  `_fast_new_cache: dict[tuple[str, ...], Callable] = {}` and `_make_fast_new(fields)` which exec-generates (params named `_a0.._aN` to avoid any field-name clash):
  ```python
  def _clausal_new(cls, _a0, _a1):
      inst = cls.__new__(cls)
      inst.x = _a0
      inst.y = _a1
      return inst
  ```
  (assignment targets are the real field names, in `_fields` order). Cache by the fields tuple, mirroring `_init_cache`.
- In `PredicateMeta.__new__` (~lines 603–650), where the other generated methods are attached: attach `cls._clausal_new = classmethod(_make_fast_new(fields))` ONLY when `fields` is non-empty AND `"_clausal_new" not in fields`. Zero-field (atom) classes get nothing. Attach AFTER class creation (it is not in `__slots__`, so plain assignment on the class is safe).
- No changes to `__call__`, `_make_init`, or any other generated method.

Tests (write FIRST in `tests/test_fast_construction.py`, using `make_predicate` from `clausal.logic.predicate`):
1. `cls._clausal_new(1, 2)` returns an instance with `type` = cls, fields set, `== cls(1, 2)` (slow path), and is a distinct object.
2. Atom classes (`make_predicate("red", [])`) have no `_clausal_new` in `vars(cls)`.
3. A class with a field literally named `_clausal_new` still constructs via the slow path (`cls(_clausal_new=5)` works) and has NO fast constructor attached; class creation does not raise.
4. Two same-named classes (`make_predicate("foo", ["x"])` twice) each get their own working `_clausal_new`; cache sharing by field-tuple is fine (the generated function receives `cls`).
5. Fast-path instances remain unhashable and structurally equal to slow-path instances; `__match_args__`/pattern matching still works on them (`case foo(x=v)`).

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_fast_construction.py tests/test_predicate_meta.py -q` — all new tests pass, `test_predicate_meta.py` unchanged-green.

## Task 2: emitter uses the fast path for saturated PredicateMeta construction

Files: `clausal/logic/compiler/terms_to_ast.py`, extend `tests/test_fast_construction.py`.

In `term_to_ast_expr`, the `is_term_instance(term)` branch (~line 636, currently emits `ast.Call(func=_name(cls_name), keywords=[...])`):
- When ALL of: `isinstance(type(term), PredicateMeta)`; `type(term)` has `_clausal_new` in `vars(type(term))`; and NO field of the term is named `position` or `_position` (those trigger the existing skip-filter — such classes keep today's behavior exactly) — emit instead:
  `ast.Call(func=ast.Attribute(value=_name(cls_name), attr="_clausal_new", ctx=ast.Load()), args=[<recursed term_to_ast_expr of each field value, in term_field_names order>], keywords=[])`.
- Otherwise (dataclass nodes, position-field classes, anything else): the existing keyword emission, byte-identical.
- Name resolution semantics unchanged: the class is still looked up via `_name(cls_name)` in the same namespace as today.

Tests (extend `tests/test_fast_construction.py`):
1. Unit: `ast.unparse(term_to_ast_expr(foo_instance, {}))` contains `_clausal_new` for a plain PredicateMeta term; does NOT contain it for a `pythonic_ast` dataclass node (e.g. `BinOp`) nor for a class with a `position` field.
2. Integration/parity: compile and run a small predicate whose body CONSTRUCTS a compound as data (mirror an existing test that compiles clauses via `compile_predicate_trampoline` with a body building a compound, or reuse the `Database`+`_normalize_fact_clause` pattern from `tests/test_first_arg_index.py` with compound args) — solutions identical to before; constructed answers `==` slow-path-built terms.
3. Regression: `/workspace/clausal/venv/bin/python -m pytest tests/test_fast_construction.py tests/test_predicate_meta.py tests/test_first_arg_index.py tests/test_simple_ast.py -q` green (modulo failures already in baseline_failures.txt at the worktree root, if any of these files appear there).

## Task 3: term-construction benchmark

Files: new `benchmarks/bench_term_construction.py`.

- Read `benchmarks/bench_f046_head_dispatch.py` first and follow its style/CLI conventions.
- Interleaved A/B (this repo's perf-gate convention — no saved baselines): within the same process, alternate timed batches of (A) slow path `cls(v0, .., vn)` via `PredicateMeta.__call__`, (B) fast path `cls._clausal_new(v0, .., vn)`, and (C) reference `(name, v0, .., vn)` tuple literal, for arities 1, 3, 8. Report ns/op per variant per arity and the A/B ratio.
- Run it with `/workspace/clausal/venv/bin/python benchmarks/bench_term_construction.py` and include the numbers in your report file. Expected ballpark: A ≈ 700–900 ns (arity 3), B ≈ 60–120 ns; if B is not at least 4× faster than A, say so loudly in the report rather than tuning the benchmark.
