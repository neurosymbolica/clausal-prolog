# Fix Report: Fable Review Findings — comma-optional/guard rewrites

**Date:** 2026-07-20
**Branch:** main
**Files changed:** `clausal/templating/term_rewriting.py`, `clausal/import_hook.py`, `tests/test_optional_fact_comma.py`, `docs/superpowers/specs/2026-07-20-optional-fact-comma-design.md`

---

## Finding 1 (Critical) — Gate new cases to module compile only

### RED evidence

Added `TestReplModeUnaffected` with three tests. Before the fix, all three failed:

```
FAILED tests/test_optional_fact_comma.py::TestReplModeUnaffected::test_bare_call_stays_expr_in_repl
  AssertionError: assert 'Try' == 'Expr'
FAILED tests/test_optional_fact_comma.py::TestReplModeUnaffected::test_bare_name_stays_expr_in_repl
  AssertionError: assert 'Try' == 'Expr'
FAILED tests/test_optional_fact_comma.py::TestReplModeUnaffected::test_functor_call_stays_expr_in_repl
  AssertionError: assert 'Try' == 'Expr'
```

All three returned `"Try"` — confirming the REPL regression was real.

### Fix

Added `_is_module_compile()` method to `EmbedTransformer` near `_guard_bare_call` (~line 2554):

```python
def _is_module_compile(transformer):
    """True when compiling a .clausal MODULE (source_lines were supplied),
    False for REPL cells transformed by _FreshEmbedTransformer via a bare
    EmbedTransformer().  The comma-optional fact rewrite and the bare-call
    guard apply only to modules; a REPL cell's trailing bare Call/Name must
    stay an ast.Expr so the interactive display hook still echoes it."""
    return transformer._source_lines is not None
```

Added `and transformer._is_module_compile()` to the guard of both tail cases in `visit_Expr`:

- `case Call(func=Name(id=functor_name)) if (transformer._scope_depth == 0 and transformer._is_module_compile()):`
- `case Name(id=functor_name) if (transformer._scope_depth == 0 and not _is_logic_var_name(functor_name) and transformer._is_module_compile()):`

In REPL mode (`_source_lines is None`), both cases no longer match, so the final `return transformer.generic_visit(expr_stmt)` runs and the node stays an `ast.Expr`.

### GREEN evidence

After the fix: all 13 tests pass (10 existing + 3 new REPL tests). Module-mode tests (Parts A/B) unaffected — module paths always supply `source_lines`.

---

## Finding 2 (Important) — Bump bytecode cache tag

`clausal/import_hook.py` line 307: changed `CLAUSAL_BYTECODE_TAG = 2` to `CLAUSAL_BYTECODE_TAG = 3`.

The feature changed codegen (bare facts → `$define_predicate`; undeclared bare calls → `Try` guards), so pre-feature `.pyc` caches would serve stale bytecode. Bumping the tag causes `path_stats` to return a different XOR'd mtime, invalidating all cached `.pyc` files on first load after upgrade. No test added per spec.

---

## Finding 3 (Minor) — Suppress chained exception in diagnostic

`clausal/import_hook.py` `_unterminated_fact_error`: changed

```python
raise NameError(...) 
```
to
```python
raise NameError(...) from None
```

The exception is raised inside the generated `except NameError:` handler. Without `from None`, Python shows "During handling of the above exception, another exception occurred:" which is noise. With `from None` the context is suppressed and only the hinted diagnostic message shows. Message text is unchanged.

---

## Finding 4 (Minor) — Close two test gaps

### 4a — Zero-arity undeclared bare Name diagnostic

Added `test_zero_arity_undeclared_bare_name_hints_comma` to `TestUndeclaredDiagnostic`.

The suggested name `_t2_zero_undeclared_` was rejected: `_is_logic_var_name("_t2_zero_undeclared_")` returns `True` (single-leading-underscore convention), so the `Name` case's guard would exclude it and the test would not hit the diagnostic path. Used `xyzzy_zero_undecl` instead (lowercase, no leading underscore, no ALL-CAPS — `_is_logic_var_name` returns `False`). Test confirms: loading `"xyzzy_zero_undecl\n"` raises `NameError` containing both `"bodyless fact"` and `"xyzzy_zero_undecl"`. PASSES.

### 4b — Strengthen legit-call test with capsys

`test_legit_undeclared_call_still_runs` now takes `capsys` and asserts `"clausal-ok" in capsys.readouterr().out` — verifying the `else`-branch actually ran the `print` call, not just that no exception was raised. PASSES.

---

## Finding 5 (Minor doc) — Spec accuracy

`docs/superpowers/specs/2026-07-20-optional-fact-comma-design.md` Part B "Properties" paragraph: added a sentence noting that functor resolution can succeed spuriously when an undeclared functor collides with a process-wide-minted `predicate_builtins` name from another loaded module (load-order-dependent), so the diagnostic is best-effort — strictly no worse than the prior behavior (which provided no diagnostic at all).

---

## Final suite run

```
PYENV_VERSION=3.13.3 PYTHONPATH=/workspace/clausal-bug-fix python3 -m pytest \
  tests/test_optional_fact_comma.py tests/test_transform_nodes.py \
  tests/test_comma_separated_rules.py tests/test_term_expansion.py -q

78 passed in 0.46s
```

14 tests in `test_optional_fact_comma.py` (up from 10), all transformer suites clean.

---

## Surprises

- The suggested zero-arity Name test identifier (`_t2_zero_undeclared_`) is treated as a logic variable by `_is_logic_var_name` due to its single-leading-underscore prefix; replaced with `xyzzy_zero_undecl` which successfully triggers the guard. Documented in Finding 4a above.
- No other surprises. The fix was minimal and the gating logic (`_source_lines is not None`) is already the established discriminator used by `_guard_bare_call` for `src_text` extraction.
