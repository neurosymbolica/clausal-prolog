"""Slice F: phase-boundary invariant assertions — negative tests.

For each invariant assertion, deliberately construct a state that
violates it and confirm the assertion fires with an
:class:`InvariantError` carrying a readable message.

Positive coverage (the assertions don't fire on valid compiles) is
provided by every other test in the suite — the assertions are
always-on, so the existing 10497-test pass count is the affirmative
gate.  The tests below pin the **failure path**: each one verifies
that a known-broken state actually triggers the assertion.

When new invariants land (F2+), this file gains one negative test
per invariant, mirroring the existing pattern.
"""

from __future__ import annotations

import pytest

import ast

from clausal.logic.compiler.invariants import (
    InvariantError,
    assert_body_vars_preallocated,
    assert_call_targets_resolved,
    assert_mark_undo_paired,
    assert_trampoline_done_yield_present,
)
from clausal.logic.database import Database
from clausal.logic.variables import Var
from clausal.terms import Unify


def _funcdef(name: str, body: list) -> ast.FunctionDef:
    """Build a minimal FunctionDef with *body* and *name*."""
    fd = ast.FunctionDef(
        name=name,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=body or [ast.Pass()],
        decorator_list=[], returns=None, type_comment=None,
    )
    ast.fix_missing_locations(fd)
    return fd


def _mark(name: str) -> ast.Assign:
    """``<name> = trail.mark()`` synthetic AST."""
    return ast.Assign(
        targets=[ast.Name(id=name, ctx=ast.Store())],
        value=ast.Call(
            func=ast.Attribute(value=ast.Name(id="trail", ctx=ast.Load()),
                               attr="mark", ctx=ast.Load()),
            args=[], keywords=[],
        ),
    )


def _undo(name: str) -> ast.Expr:
    """``trail.undo(<name>)`` synthetic AST."""
    return ast.Expr(value=ast.Call(
        func=ast.Attribute(value=ast.Name(id="trail", ctx=ast.Load()),
                           attr="undo", ctx=ast.Load()),
        args=[ast.Name(id=name, ctx=ast.Load())], keywords=[],
    ))


def _yield_done(parent: str = "parent") -> ast.Expr:
    """``yield (<parent>, $DONE)`` synthetic AST."""
    return ast.Expr(value=ast.Yield(value=ast.Tuple(
        elts=[
            ast.Name(id=parent, ctx=ast.Load()),
            ast.Name(id="$DONE", ctx=ast.Load()),
        ],
        ctx=ast.Load(),
    )))


def _ctx(var_context: dict):
    """Build a minimal CompilationContext with an explicit var_context."""
    from clausal.logic.compiler.compile_ctx import CompilationContext
    return CompilationContext(
        db=None, var_context=var_context, trail_name="trail",
    )


def test_body_vars_preallocated_passes_when_complete():
    """Positive path: every body Var is in var_context → no raise."""
    x, y = Var(), Var()
    goals = [Unify(left=x, right=y)]
    var_context = {x._id: f"_v{x._id}", y._id: f"_v{y._id}"}
    # Should not raise.
    assert_body_vars_preallocated(_ctx(var_context), goals)


def test_body_vars_preallocated_fires_on_missing_var():
    """Negative path: skip a Var → assertion fires with diagnostic."""
    x, y = Var(), Var()
    goals = [Unify(left=x, right=y)]
    # Deliberately omit y from var_context.
    var_context = {x._id: f"_v{x._id}"}
    with pytest.raises(InvariantError) as exc_info:
        assert_body_vars_preallocated(_ctx(var_context), goals)
    msg = str(exc_info.value)
    assert "Phase 5 entry" in msg
    assert "body-vars-preallocated" in msg
    assert "_preallocate_body_vars" in msg
    # The missing Var should appear in the sample diagnostic.
    assert repr(y) in msg


def test_body_vars_preallocated_invariant_error_is_assertion_error():
    """``InvariantError`` should subclass ``AssertionError`` so existing
    ``pytest.raises(AssertionError)`` callers keep working."""
    assert issubclass(InvariantError, AssertionError)


# ── F2: assert_call_targets_resolved ────────────────────────────────────────


def test_call_targets_resolved_passes_when_all_present():
    """Positive: every collected target has a base_globals entry."""
    targets = {("Foo", 2), ("Bar", 1)}
    base_globals = {"Foo": object(), "Bar": object()}
    assert_call_targets_resolved(targets, base_globals, db=Database())


def test_call_targets_resolved_skips_when_db_is_none():
    """When db is None, the invariant is advisory (no shim floor)."""
    targets = {("Missing", 2)}
    base_globals: dict = {}
    # Should not raise — db=None means missing entries are tolerated.
    assert_call_targets_resolved(targets, base_globals, db=None)


def test_call_targets_resolved_skips_dotted_names():
    """Dotted targets are best-effort; no shim floor applies."""
    targets = {("myapp.utils.Helper", 2)}
    base_globals: dict = {}
    # Should not raise even with a real db — dotted names are skipped.
    assert_call_targets_resolved(targets, base_globals, db=Database())


# ── F3: assert_mark_undo_paired ─────────────────────────────────────────────


def test_mark_undo_paired_passes_when_balanced():
    fd = _funcdef("ok", [_mark("_m0"), _undo("_m0")])
    assert_mark_undo_paired(fd)


def test_mark_undo_paired_fires_on_orphan_mark():
    fd = _funcdef("bad", [_mark("_m0")])
    with pytest.raises(InvariantError) as exc_info:
        assert_mark_undo_paired(fd)
    msg = str(exc_info.value)
    assert "Phase 6 post" in msg
    assert "mark/undo-paired" in msg
    assert "_m0" in msg
    assert "assigned but never undone" in msg


def test_mark_undo_paired_fires_on_orphan_undo():
    fd = _funcdef("bad", [_undo("_stale")])
    with pytest.raises(InvariantError) as exc_info:
        assert_mark_undo_paired(fd)
    assert "_stale" in str(exc_info.value)
    assert "never marked" in str(exc_info.value)


def test_mark_undo_paired_recurses_into_nested_funcdef():
    """Marks inside a nested funcdef pair within that scope."""
    inner = _funcdef("inner_bad", [_mark("_m0")])
    fd = _funcdef("outer", [inner, _mark("_m1"), _undo("_m1")])
    with pytest.raises(InvariantError) as exc_info:
        assert_mark_undo_paired(fd)
    # The nested orphan should be reported, not the outer balanced pair.
    assert "_m0" in str(exc_info.value)


# ── F4: assert_trampoline_done_yield_present ────────────────────────────────


def test_done_yield_present_passes_when_emitted():
    fd = _funcdef("ok", [_yield_done()])
    assert_trampoline_done_yield_present(fd)


def test_done_yield_present_fires_when_missing():
    fd = _funcdef("bad", [
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ])
    with pytest.raises(InvariantError) as exc_info:
        assert_trampoline_done_yield_present(fd)
    msg = str(exc_info.value)
    assert "Phase 6 post" in msg
    assert "trampoline-DONE-yield" in msg
    assert "bad" in msg


def test_call_targets_resolved_fires_on_missing_non_dotted_name():
    """Negative: non-dotted target with db present but no entry."""
    targets = {("Missing", 2), ("Present", 1)}
    base_globals = {"Present": object()}
    with pytest.raises(InvariantError) as exc_info:
        assert_call_targets_resolved(targets, base_globals, db=Database())
    msg = str(exc_info.value)
    assert "Phase 1 exit" in msg
    assert "call-targets-resolved" in msg
    assert "Missing" in msg
    # The entry that *is* present should not be flagged.
    assert "'Present'" not in msg or "Present" not in str(exc_info.value).split("sample")[1]
