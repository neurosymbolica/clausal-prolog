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

from clausal.logic.compiler.invariants import (
    InvariantError,
    assert_body_vars_preallocated,
    assert_call_targets_resolved,
)
from clausal.logic.database import Database
from clausal.logic.variables import Var
from clausal.terms import Unify


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
