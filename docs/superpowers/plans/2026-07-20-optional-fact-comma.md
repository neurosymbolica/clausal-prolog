# Optional Fact Comma Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a declared predicate's bodyless fact omit its trailing comma, and give a clear "missing comma" diagnostic when an undeclared bare call fails to load.

**Architecture:** Two changes in the `.clausal` AST rewriter (`EmbedTransformer.visit_Expr`). (A) A bare module-level `Call`/`Name` whose functor is in `_seen_functors` is rewritten into a fact, reusing the trailing-comma fact path (extracted into shared helpers). (B) A bare call whose functor is **not** declared is wrapped in a `try: <functor> / except NameError: $unterminated_fact_error(...) / else: <original call>` guard, so an undefined functor produces a terminator diagnostic while a real call (and any argument error) runs untouched.

**Tech Stack:** Python 3.13, `ast` module, pytest. Source lives in `clausal/`.

## Global Constraints

- Run all commands with: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix` (the repo venv lacks pytest; use pyenv 3.13.3).
- `clausal/templating/term_rewriting.py` does `from ast import *`; `load = Load()` and `replace(new, start, end=None)` (copies source locations) are module globals. `node_ast`, `make_keyword_node`, `_derive_field_names`, `_make_functor_class_ast`, `_is_logic_var_name` already exist in that module.
- `$`-prefixed names (`$define_predicate`, `$assert_fact`, `$module`) are injected into every module namespace and cannot be shadowed by user source; the new helper follows the same convention as `$unterminated_fact_error`.
- `ast.fix_missing_locations(tree)` runs after transformation (in `_parse_clausal_source`), so newly-built nodes need locations only on their outermost node (set via `replace(node, expr_stmt)`); children inherit.
- The new bare-fact cases MUST be placed in the `match` **after** the existing `case Starred()` and `case Call(func=Name(id="_clausal_star_query_"))` cases and **before** the final `return transformer.generic_visit(expr_stmt)`.
- TDD: write the failing test first, watch it fail, then implement. Commit after each green step.

---

## File Structure

- `clausal/templating/term_rewriting.py` — extract `_build_fact_statements`, `_build_zero_arity_fact_statements`, `_make_define_stmt`; add `_guard_bare_call`; add the declared-fact and undeclared-guard `case`s in `visit_Expr`.
- `clausal/import_hook.py` — add `_unterminated_fact_error` and inject it into `predicate_builtins` and `_simple_ast_builtins`.
- `tests/test_optional_fact_comma.py` — new test module (created in Task 1, extended in Tasks 2–3).

---

### Task 1: Extract shared fact-building helpers (behavior-preserving refactor)

Pull the two trailing-comma fact `case` bodies into reusable helpers so the comma-optional path (Task 2) reuses them verbatim. No behavior change.

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — `visit_Expr` Tuple-fact cases (~lines 2580–2708); add three helpers near the other `_make_*` module functions / transformer methods.
- Test: `tests/test_optional_fact_comma.py` (create)

**Interfaces:**
- Produces:
  - `_make_define_stmt(predicate_ast, expr_stmt) -> stmt` (module-level function)
  - `EmbedTransformer._build_fact_statements(functor_name, orig_pos_args, orig_kw_args, anchor, src_node, expr_stmt) -> stmt | list[stmt]`
  - `EmbedTransformer._build_zero_arity_fact_statements(functor_name, name_node, expr_stmt) -> stmt | list[stmt]`

- [ ] **Step 1: Write the characterization test**

Create `tests/test_optional_fact_comma.py`:

```python
"""Comma-optional bodyless facts + undeclared-fact diagnostic.

See docs/superpowers/specs/2026-07-20-optional-fact-comma-design.md
"""
import pytest

from clausal.import_hook import _load_module


def load_src(tmp_path, name, src):
    """Write *src* to <tmp>/<name>.clausal and load it, returning the module."""
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p))


def clause_count(mod, functor, arity):
    return len(mod.__clausal_module__.db.clauses_for(functor, arity))


class TestTrailingCommaStillWorks:
    def test_comma_facts_land(self, tmp_path):
        mod = load_src(tmp_path, "t1_comma", "edge(1, 2),\nedge(3, 4),\n")
        assert clause_count(mod, "edge", 2) == 2

    def test_zero_arity_comma_fact_lands(self, tmp_path):
        mod = load_src(tmp_path, "t1_zero", "flag,\n")
        assert clause_count(mod, "flag", 0) == 1
```

- [ ] **Step 2: Run it to confirm it passes on current code**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest tests/test_optional_fact_comma.py -v`
Expected: 2 passed. (This is a characterization test guarding the refactor.)

- [ ] **Step 3: Add the three helpers**

Add this module-level function next to `_make_functor_class_ast` in `clausal/templating/term_rewriting.py`:

```python
def _make_define_stmt(predicate_ast, expr_stmt):
    """Wrap a Predicate node in a ``$define_predicate(pred, $module)`` stmt."""
    return replace(
        Expr(
            value=replace(
                Call(
                    func=replace(
                        Name(id="$define_predicate", ctx=load), expr_stmt.value
                    ),
                    args=[
                        predicate_ast,
                        replace(Name(id="$module", ctx=load), expr_stmt.value),
                    ],
                    keywords=[],
                ),
                expr_stmt.value,
            )
        ),
        expr_stmt,
    )
```

Add these two methods to the `EmbedTransformer` class (near `_unseat_directive_minted`):

```python
    def _build_fact_statements(transformer, functor_name, orig_pos_args,
                               orig_kw_args, anchor, src_node, expr_stmt):
        """Build AST for a bodyless fact ``functor(args)`` (arity >= 0 via args).

        Shared by the trailing-comma fact case and the comma-optional
        declared-predicate case. Returns ``[functor_class_def?, define_stmt]``
        (a single statement when no class needs emitting).
        """
        arg_field_names = _derive_field_names(orig_pos_args)
        kwarg_field_names = [kw.arg for kw in orig_kw_args]
        all_field_names = arg_field_names + kwarg_field_names

        transformer._unseat_directive_minted(functor_name)
        prev_fields = transformer._seen_functors.get(functor_name)
        if prev_fields is not None:
            for i in range(len(arg_field_names)):
                if i < len(prev_fields):
                    arg_field_names[i] = prev_fields[i]
            all_field_names = arg_field_names + kwarg_field_names

        term_transformer = transformer._make_term_transformer()
        transformed_pos = [term_transformer.visit(a) for a in orig_pos_args]
        transformed_kw = [term_transformer.visit(kw.value) for kw in orig_kw_args]

        head_keywords = [
            make_keyword_node(fname, term, orig)
            for fname, term, orig in zip(arg_field_names, transformed_pos, orig_pos_args)
        ] + [
            make_keyword_node(fname, term, orig)
            for fname, term, orig in zip(kwarg_field_names, transformed_kw, orig_kw_args)
        ]
        head_ast = replace(
            Call(
                func=replace(Name(id=functor_name, ctx=load), anchor),
                args=[],
                keywords=head_keywords,
            ),
            src_node,
        )
        predicate_ast = node_ast(
            "Predicate", expr_stmt.value,
            head=head_ast,
            body=replace(Constant(value=True), expr_stmt.value),
        )
        define_stmt = _make_define_stmt(predicate_ast, expr_stmt)

        statements = []
        if functor_name not in transformer._seen_functors:
            transformer._seen_functors[functor_name] = all_field_names
            statements.append(
                _make_functor_class_ast(functor_name, all_field_names, expr_stmt)
            )
        statements.append(define_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _build_zero_arity_fact_statements(transformer, functor_name, name_node,
                                          expr_stmt):
        """Build AST for a zero-arity bodyless fact ``flag`` / ``flag,``."""
        head_ast = replace(
            Call(
                func=replace(Name(id=functor_name, ctx=load), name_node),
                args=[],
                keywords=[],
            ),
            name_node,
        )
        predicate_ast = node_ast(
            "Predicate", expr_stmt.value,
            head=head_ast,
            body=replace(Constant(value=True), expr_stmt.value),
        )
        define_stmt = _make_define_stmt(predicate_ast, expr_stmt)
        statements = []
        if functor_name not in transformer._seen_functors:
            transformer._seen_functors[functor_name] = []
            statements.append(
                _make_functor_class_ast(functor_name, [], expr_stmt)
            )
        statements.append(define_stmt)
        return statements if len(statements) > 1 else statements[0]
```

- [ ] **Step 4: Rewire the two Tuple-fact cases to call the helpers**

Replace the body of the `case Tuple(elts=[single_element], ctx=Load()) if (...)` block (the Call fact, ~lines 2585–2660) with:

```python
                # Trailing-comma fact: ``edge(1, 2),`` — build via shared helper.
                return transformer._build_fact_statements(
                    single_element.func.id,
                    single_element.args,
                    single_element.keywords,
                    single_element.func,
                    single_element,
                    expr_stmt,
                )
```

Replace the body of the `case Tuple(elts=[Name(id=functor_name) as name_node], ctx=Load()) if (...)` block (the zero-arity fact, ~lines 2670–2708) with:

```python
                # A10-F011: zero-arity trailing-comma fact ``flag,`` — shared helper.
                return transformer._build_zero_arity_fact_statements(
                    functor_name, name_node, expr_stmt,
                )
```

- [ ] **Step 5: Run the characterization test + the transformer suite**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest tests/test_optional_fact_comma.py tests/test_transform_nodes.py tests/test_comma_separated_rules.py -q`
Expected: all pass (no behavior change).

- [ ] **Step 6: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_optional_fact_comma.py
git commit -m "refactor(embed): extract shared bodyless-fact builders"
```

---

### Task 2: Part A — comma-optional facts for declared predicates

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — add two `case`s at the end of `visit_Expr`'s `match` (after the `_clausal_star_query_` case, before the final `return transformer.generic_visit(expr_stmt)`).
- Test: `tests/test_optional_fact_comma.py`

**Interfaces:**
- Consumes: `_build_fact_statements`, `_build_zero_arity_fact_statements` (Task 1).
- Produces: comma-optional fact semantics gated on `transformer._seen_functors`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_optional_fact_comma.py`:

```python
class TestCommaOptionalWhenDeclared:
    def test_canonical_repro_module_declared(self, tmp_path):
        # p declared via -module; bare fact with `_` in head, no trailing comma.
        src = (
            "-module(r1, [ p(A, B), q(A) ])\n"
            "-strict_atoms\n"
            "p(_, 1)\n"
            "q(X) <- ( p(X, 1) )\n"
        )
        mod = load_src(tmp_path, "t2_canon", src)
        assert clause_count(mod, "p", 2) == 1

    def test_block_last_fact_no_comma_lands(self, tmp_path):
        # The silent-drop bug: last fact in a block omits its comma.
        src = "-dynamic(counter/1)\ncounter(0),\ncounter(1),\ncounter(2)\n"
        mod = load_src(tmp_path, "t2_block", src)
        assert clause_count(mod, "counter", 1) == 3

    def test_prior_clause_declares_functor(self, tmp_path):
        # First fact has a comma (registers the functor); second omits it.
        src = "edge(1, 2),\nedge(3, 4)\n"
        mod = load_src(tmp_path, "t2_prior", src)
        assert clause_count(mod, "edge", 2) == 2

    def test_zero_arity_declared_bare_fact(self, tmp_path):
        src = "-module(z, [ flag ])\nflag\n"
        mod = load_src(tmp_path, "t2_zero", src)
        assert clause_count(mod, "flag", 0) == 1

    def test_declared_later_still_requires_comma(self, tmp_path):
        # Single-pass boundary: `foo(9)` before any declaration is NOT a fact.
        # foo(9) is ground, so it does not raise; it is silently a no-op call
        # and no clause is asserted (documents the ordering limitation).
        src = "foo(9)\nfoo(1),\n"
        mod = load_src(tmp_path, "t2_later", src)
        assert clause_count(mod, "foo", 1) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest tests/test_optional_fact_comma.py::TestCommaOptionalWhenDeclared -v`
Expected: `test_canonical_repro_module_declared` FAILS with `name '_' is not defined`; `test_block_last_fact_no_comma_lands` FAILS (count 2, not 3); `test_zero_arity_declared_bare_fact` FAILS (count 0). `test_prior_clause_declares_functor` FAILS (count 1). `test_declared_later_still_requires_comma` passes already.

- [ ] **Step 3: Add the declared-fact cases**

In `visit_Expr`, immediately before the final `return transformer.generic_visit(expr_stmt)`, add:

```python
            case Call(func=Name(id=functor_name)) if (
                transformer._scope_depth == 0
                and functor_name in transformer._seen_functors
            ):
                # Comma-optional bodyless fact for a DECLARED predicate:
                # ``p(_, 1)`` with no trailing comma, where p is known
                # (-module export, -dynamic/-private, or a prior clause).
                src = expr_stmt.value
                return transformer._build_fact_statements(
                    functor_name, src.args, src.keywords, src.func, src, expr_stmt,
                )
            case Name(id=functor_name) if (
                transformer._scope_depth == 0
                and not _is_logic_var_name(functor_name)
                and functor_name in transformer._seen_functors
            ):
                # Zero-arity comma-optional fact: bare ``flag`` for declared flag/0.
                return transformer._build_zero_arity_fact_statements(
                    functor_name, expr_stmt.value, expr_stmt,
                )
```

- [ ] **Step 4: Run to verify pass**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest tests/test_optional_fact_comma.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_optional_fact_comma.py
git commit -m "feat(embed): trailing comma optional for declared bodyless facts"
```

---

### Task 3: Part B — diagnostic guard for undeclared bare calls

**Files:**
- Modify: `clausal/import_hook.py` — add `_unterminated_fact_error`; inject as `$unterminated_fact_error` into `predicate_builtins` (after line ~240) and `_simple_ast_builtins` (in the IPython section, after line ~713).
- Modify: `clausal/templating/term_rewriting.py` — add `EmbedTransformer._guard_bare_call`; add two undeclared-functor `case`s at the end of `visit_Expr`.
- Test: `tests/test_optional_fact_comma.py`

**Interfaces:**
- Consumes: `$unterminated_fact_error(name: str, lineno: int, src: str)` (raises `NameError`).
- Produces: `EmbedTransformer._guard_bare_call(functor_name, expr_stmt) -> Try`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_optional_fact_comma.py`:

```python
class TestUndeclaredDiagnostic:
    def test_undeclared_bare_fact_hints_comma(self, tmp_path):
        # p undeclared, no -module: functor name is undefined.
        src = "-strict_atoms\np(_ATOM, 1)\n"
        with pytest.raises(NameError) as ei:
            load_src(tmp_path, "t3_undecl", src)
        msg = str(ei.value)
        assert "bodyless fact" in msg
        assert "trailing" in msg
        assert "p" in msg

    def test_legit_undeclared_call_still_runs(self, tmp_path):
        # `print` resolves (a real callable), so the else-branch runs it: no error.
        src = 'print("clausal-ok")\n'
        mod = load_src(tmp_path, "t3_legit", src)  # must not raise
        assert mod is not None

    def test_functor_resolves_but_arg_typo_is_honest(self, tmp_path):
        # `print` resolves; the undefined ARG error must NOT be reported as a
        # missing-comma fact.
        src = "print(nope_undefined_arg)\n"
        with pytest.raises(NameError) as ei:
            load_src(tmp_path, "t3_argtypo", src)
        msg = str(ei.value)
        assert "nope_undefined_arg" in msg
        assert "bodyless fact" not in msg
```

- [ ] **Step 2: Run to verify failure**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest tests/test_optional_fact_comma.py::TestUndeclaredDiagnostic -v`
Expected: `test_undeclared_bare_fact_hints_comma` FAILS (message is bare `name 'p' is not defined`, no "bodyless fact"). The other two may already pass (current bare-call behavior).

- [ ] **Step 3: Add the runtime helper in `import_hook.py`**

Add near `_fact_to_predicate_node` (top "Runtime support" section):

```python
def _unterminated_fact_error(name, lineno, src):
    """Raised when a bare, comma-less clause's functor is undefined — almost
    always a bodyless fact missing its trailing ',' (see the comma-optional
    fact rule in EmbedTransformer).  Emitted from generated guard code."""
    where = f"{src!r} (line {lineno})" if src else f"line {lineno}"
    raise NameError(
        f"name {name!r} is not defined — {where} looks like a bodyless fact "
        f"missing its trailing ','; add a comma to make it a fact, or declare "
        f"the predicate (-module/-dynamic)."
    )
```

Immediately after `predicate_builtins.update(INJECTED_RUNTIME_BUILTINS)` (~line 240):

```python
predicate_builtins["$unterminated_fact_error"] = _unterminated_fact_error
```

In the IPython section, after `_simple_ast_builtins.update(INJECTED_RUNTIME_BUILTINS)` (~line 713):

```python
_simple_ast_builtins["$unterminated_fact_error"] = _unterminated_fact_error
```

- [ ] **Step 4: Add the guard builder in `term_rewriting.py`**

Add this method to `EmbedTransformer` (near `_build_zero_arity_fact_statements`):

```python
    def _guard_bare_call(transformer, functor_name, expr_stmt):
        """Wrap an UNDECLARED bare ``functor(...)`` / ``functor`` statement.

        Emits::

            try:
                functor              # resolve the functor NAME only
            except NameError:
                $unterminated_fact_error('functor', lineno, src)
            else:
                <original statement>  # the real call; arg errors surface here

        So an undefined functor becomes a 'missing comma' diagnostic, while a
        legitimate call (imported macro, builtin) runs normally and its own
        argument errors are reported honestly.
        """
        src_text = ""
        if transformer._source_lines is not None:
            idx = expr_stmt.lineno - 1
            if 0 <= idx < len(transformer._source_lines):
                src_text = transformer._source_lines[idx].strip()

        orig_stmt = transformer.generic_visit(expr_stmt)

        guard = Try(
            body=[Expr(value=Name(id=functor_name, ctx=load))],
            handlers=[
                ExceptHandler(
                    type=Name(id="NameError", ctx=load),
                    name=None,
                    body=[
                        Expr(value=Call(
                            func=Name(id="$unterminated_fact_error", ctx=load),
                            args=[
                                Constant(value=functor_name),
                                Constant(value=expr_stmt.lineno),
                                Constant(value=src_text),
                            ],
                            keywords=[],
                        ))
                    ],
                )
            ],
            orelse=[orig_stmt],
            finalbody=[],
        )
        return replace(guard, expr_stmt)
```

- [ ] **Step 5: Route undeclared bare calls to the guard**

Extend the two cases added in Task 2 so the non-declared branch is guarded. Replace the Task-2 `case Call(...)` and `case Name(...)` with these (drop the `and functor_name in transformer._seen_functors` from the guards; branch inside instead):

```python
            case Call(func=Name(id=functor_name)) if (
                transformer._scope_depth == 0
            ):
                if functor_name in transformer._seen_functors:
                    # Comma-optional bodyless fact for a DECLARED predicate.
                    src = expr_stmt.value
                    return transformer._build_fact_statements(
                        functor_name, src.args, src.keywords, src.func, src,
                        expr_stmt,
                    )
                # Undeclared: guard so an undefined functor yields a comma hint.
                return transformer._guard_bare_call(functor_name, expr_stmt)
            case Name(id=functor_name) if (
                transformer._scope_depth == 0
                and not _is_logic_var_name(functor_name)
            ):
                if functor_name in transformer._seen_functors:
                    return transformer._build_zero_arity_fact_statements(
                        functor_name, expr_stmt.value, expr_stmt,
                    )
                return transformer._guard_bare_call(functor_name, expr_stmt)
```

- [ ] **Step 6: Run to verify pass**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest tests/test_optional_fact_comma.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add clausal/import_hook.py clausal/templating/term_rewriting.py tests/test_optional_fact_comma.py
git commit -m "feat(embed): comma-hint diagnostic for undeclared bare facts"
```

---

### Task 4: Corpus regression reconciliation

Facts that were silently dropped now land, which can shift exact solution counts. Run the full suite and reconcile.

**Files:**
- Modify (as needed): fixtures/tests under `tests/` and `packages/*/tests/` whose assertions counted a fact block missing its final comma.

- [ ] **Step 1: Run the full test suite**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest tests/ -q`
Expected: capture any failures. Likely candidates are the ≥9 fixtures whose last fact previously dropped: `tests/fixtures/docs/tutorial_parallel_clausal_sig_tests.clausal`, `tests/fixtures/docs/indexing_sig_tests.clausal`, `tests/clausal_modules/thread_safe_predicates.clausal`.

- [ ] **Step 2: Run the package suites**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest packages/clausal-provenance/tests -q`
Expected: capture failures (six provenance fixtures use `bottom_up_(...)` bare calls — these must still pass; a failure here means the guard broke a legit call and needs investigation, not a fixture edit).

- [ ] **Step 3: Triage each failure**

For every failure, decide:
- **Newly-landing fact** (a fact block's final comma was missing → an extra clause now exists): the fixture behavior is now *correct*; update the test's expected count/solutions to include the previously-dropped fact. Note each change in the commit message.
- **Broken legit call** (e.g. a `bottom_up_` provenance test): do NOT edit the fixture — the guard's `else` branch or term-rewriting is wrong; return to Task 3 and fix `_guard_bare_call`.

- [ ] **Step 4: Apply reconciliations and re-run**

Run: `PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest tests/ packages/clausal-provenance/tests -q`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(corpus): reconcile counts for now-landing final facts"
```

---

## Self-Review

**Spec coverage:**
- Part A (comma optional for declared) → Task 2 (Call + Name cases, `_seen_functors` gate). ✓
- Part A refactor (`_build_fact_statements`) → Task 1. ✓
- Part B (per-statement guard, functor-resolution split) → Task 3 (`_guard_bare_call`, `$unterminated_fact_error`). ✓
- Silent-drop regression (block last fact) → Task 2 `test_block_last_fact_no_comma_lands`; Task 4 corpus. ✓
- Legit macro untouched (`bottom_up_`/`print`) → Task 3 `test_legit_undeclared_call_still_runs`; Task 4 provenance run. ✓
- Honest arg error (not misattributed) → Task 3 `test_functor_resolves_but_arg_typo_is_honest`. ✓
- Single-pass boundary (declared later) → Task 2 `test_declared_later_still_requires_comma`. ✓
- Zero-arity declared fact → Task 2 `test_zero_arity_declared_bare_fact`. ✓
- `-table`/`-discontiguous`/`-shallow` don't enable optional comma → out of scope, covered implicitly by the `_seen_functors` gate (they don't register there).

**Placeholder scan:** none — every code and test step is complete.

**Type consistency:** `_build_fact_statements`, `_build_zero_arity_fact_statements`, `_make_define_stmt`, `_guard_bare_call`, `_unterminated_fact_error`, `$unterminated_fact_error` are named identically across Tasks 1–3. Task 3 Step 5 replaces (not duplicates) the Task 2 cases, so the final `match` has exactly one `case Call(func=Name(...))` and one `case Name(...)` at the tail.
