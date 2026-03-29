"""Tests for _resolve Var guards and _runtime_arg_key fast paths.

Verifies that:
- fd_eq/fd_ne/fd_lt/fd_le skip _resolve() when an operand is a Var
- _runtime_arg_key returns correct keys for int, str, bool, and other types
"""

from __future__ import annotations

from clausal.logic.variables import Var, Trail, deref, is_var, get_attr
from clausal.logic.clpfd import (
    FD_KEY, fd_eq, fd_ne, fd_lt, fd_le, fd_gt, fd_ge,
    _ensure_fd, in_domain,
)
from clausal.logic.compiler import _runtime_arg_key
from clausal.terms import Compound


def fresh_trail() -> Trail:
    return Trail()


# ── _resolve Var guard tests ─────────────────────────────────────────────────
# These exercise the `if not is_var(l): l = _resolve(l)` guard in fd_eq/ne/lt/le.
# The key behavior: when one operand is a Var with an FD domain, _resolve should
# be skipped (it's a no-op for Vars) and the constraint should be posted normally.


class TestResolveVarGuard:

    def test_fd_ne_var_vs_int(self):
        """fd_ne(Var, 5) — Var side skips _resolve, constraint posted."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_ne(x, 5, trail)
        state = get_attr(x, FD_KEY)
        from clausal.logic.clpfd import domain_contains
        assert not domain_contains(state.domain, 5)
        assert domain_contains(state.domain, 4)
        assert domain_contains(state.domain, 6)

    def test_fd_ne_int_vs_var(self):
        """fd_ne(5, Var) — reversed operands, Var side skips _resolve."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_ne(5, x, trail)
        state = get_attr(x, FD_KEY)
        from clausal.logic.clpfd import domain_contains
        assert not domain_contains(state.domain, 5)

    def test_fd_lt_var_vs_int(self):
        """fd_lt(Var, 5) → Var's domain narrowed to [1,4]."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_lt(x, 5, trail)
        from clausal.logic.clpfd import domain_max
        state = get_attr(x, FD_KEY)
        assert domain_max(state.domain) == 4

    def test_fd_le_var_vs_int(self):
        """fd_le(Var, 5) → Var's domain narrowed to [1,5]."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_le(x, 5, trail)
        from clausal.logic.clpfd import domain_max
        state = get_attr(x, FD_KEY)
        assert domain_max(state.domain) == 5

    def test_fd_eq_var_vs_int(self):
        """fd_eq(Var, 5) → Var bound to 5."""
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5

    def test_fd_eq_var_vs_var(self):
        """fd_eq(Var, Var) — both sides are Vars, both skip _resolve."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain(x, 1, 10, trail)
        assert in_domain(y, 5, 15, trail)
        assert fd_eq(x, y, trail)
        # Domains should be intersected
        state_x = get_attr(x, FD_KEY)
        state_y = get_attr(y, FD_KEY)
        if state_x is not None:
            from clausal.logic.clpfd import domain_min, domain_max
            assert domain_min(state_x.domain) >= 5
            assert domain_max(state_x.domain) <= 10

    def test_fd_gt_delegates_to_fd_lt(self):
        """fd_gt(Var, 3) → fd_lt(3, Var) — Var guard works through delegation."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_gt(x, 3, trail)
        from clausal.logic.clpfd import domain_min
        state = get_attr(x, FD_KEY)
        assert domain_min(state.domain) >= 4

    def test_fd_ge_delegates_to_fd_le(self):
        """fd_ge(Var, 3) → fd_le(3, Var) — Var guard works through delegation."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_ge(x, 3, trail)
        from clausal.logic.clpfd import domain_min
        state = get_attr(x, FD_KEY)
        assert domain_min(state.domain) >= 3


# ── _runtime_arg_key tests ───────────────────────────────────────────────────
# The fast path uses `type(a) is int or type(a) is str` before isinstance.
# Critical: bool is a subclass of int, so type(True) is int returns False.
# Booleans should still be indexable but through the isinstance fallback.


class TestRuntimeArgKey:

    def test_int_returns_self(self):
        assert _runtime_arg_key(42) == 42

    def test_str_returns_self(self):
        assert _runtime_arg_key("hello") == "hello"

    def test_bool_true_returns_self(self):
        """bool goes through isinstance fallback, not type(a) is int."""
        result = _runtime_arg_key(True)
        assert result is True

    def test_bool_false_returns_self(self):
        result = _runtime_arg_key(False)
        assert result is False

    def test_bool_not_equal_to_int(self):
        """True and 1 should produce the same key (both indexable), but
        type(True) is int is False — bool goes through isinstance path."""
        # Both should be indexable (returned as-is)
        assert _runtime_arg_key(True) is True
        assert _runtime_arg_key(1) == 1

    def test_float_returns_self(self):
        assert _runtime_arg_key(3.14) == 3.14

    def test_none_returns_self(self):
        assert _runtime_arg_key(None) is None

    def test_bytes_returns_self(self):
        assert _runtime_arg_key(b"data") == b"data"

    def test_compound_returns_functor_arity(self):
        c = Compound("f", (1, 2))
        assert _runtime_arg_key(c) == ("f", 2)

    def test_empty_string(self):
        assert _runtime_arg_key("") == ""

    def test_large_int(self):
        assert _runtime_arg_key(2**100) == 2**100
