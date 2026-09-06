"""Tests for _resolve Var guards, _runtime_arg_key fast paths, and
unify vs unify_with_occurs_check through the C API.

Verifies that:
- fd_eq/fd_ne/fd_lt/fd_le skip _resolve() when an operand is a Var
- _runtime_arg_key returns correct keys for int, str, bool, and other types
- unify (no occurs check) allows circular terms
- unify_with_occurs_check rejects circular terms
- C extensions using VarAPI->unify vs VarAPI->unify_oc get correct behavior
"""

from __future__ import annotations

from clausal.logic.atoms import mint
from clausal.logic.variables import Var, Trail, deref, is_var, get_attr, unify, unify_with_occurs_check
from clausal.logic.clpfd import (
    FD_KEY, fd_eq, fd_ne, fd_lt, fd_le, fd_gt, fd_ge,
    _ensure_fd, in_domain,
)
from clausal.logic.compiler.arg_index import _INDEX_VAR, _runtime_arg_key
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
        # nv
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
        # nv
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_ne(5, x, trail)
        state = get_attr(x, FD_KEY)
        from clausal.logic.clpfd import domain_contains
        assert not domain_contains(state.domain, 5)

    def test_fd_lt_var_vs_int(self):
        """fd_lt(Var, 5) → Var's domain narrowed to [1,4]."""
        # nv
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_lt(x, 5, trail)
        from clausal.logic.clpfd import domain_max
        state = get_attr(x, FD_KEY)
        assert domain_max(state.domain) == 4

    def test_fd_le_var_vs_int(self):
        """fd_le(Var, 5) → Var's domain narrowed to [1,5]."""
        # nv
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_le(x, 5, trail)
        from clausal.logic.clpfd import domain_max
        state = get_attr(x, FD_KEY)
        assert domain_max(state.domain) == 5

    def test_fd_eq_var_vs_int(self):
        """fd_eq(Var, 5) → Var bound to 5."""
        # nv
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5

    def test_fd_eq_var_vs_var(self):
        """fd_eq(Var, Var) — both sides are Vars, both skip _resolve."""
        # nv
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
        # nv
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_gt(x, 3, trail)
        from clausal.logic.clpfd import domain_min
        state = get_attr(x, FD_KEY)
        assert domain_min(state.domain) >= 4

    def test_fd_ge_delegates_to_fd_le(self):
        """fd_ge(Var, 3) → fd_le(3, Var) — Var guard works through delegation."""
        # nv
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
        # nv
        assert _runtime_arg_key(42) == 42

    def test_atom_returns_its_spelling_key(self):
        # nv — spec §6.9: an ATOM keys ``(spelling, 0)``; a ``str`` is a
        # STRING, which is NOT indexable and keys ``_INDEX_VAR``.
        assert _runtime_arg_key(mint("hello")) == ("hello", 0)
        assert _runtime_arg_key("hello") is _INDEX_VAR

    def test_bool_true_returns_self(self):
        """bool goes through isinstance fallback, not type(a) is int."""
        # nv
        result = _runtime_arg_key(True)
        assert result is True

    def test_bool_false_returns_self(self):
        # nv
        result = _runtime_arg_key(False)
        assert result is False

    def test_bool_not_equal_to_int(self):
        """True and 1 should produce the same key (both indexable), but
        type(True) is int is False — bool goes through isinstance path."""
        # Both should be indexable (returned as-is)
        # nv
        assert _runtime_arg_key(True) is True
        assert _runtime_arg_key(1) == 1

    def test_float_returns_self(self):
        # nv
        assert _runtime_arg_key(3.14) == 3.14

    def test_none_returns_self(self):
        # nv
        assert _runtime_arg_key(None) is None

    def test_bytes_returns_self(self):
        # nv
        assert _runtime_arg_key(b"data") == b"data"

    def test_compound_returns_functor_arity(self):
        # nv
        c = Compound("f", (1, 2))
        assert _runtime_arg_key(c) == ("f", 2)

    def test_empty_string(self):
        # nv — ``""``/``[]``/``b""`` all key consistently (spec §6.9).
        assert _runtime_arg_key("") is _INDEX_VAR
        assert _runtime_arg_key([]) is _INDEX_VAR

    def test_large_int(self):
        # nv
        assert _runtime_arg_key(2**100) == 2**100


# ── unify vs unify_with_occurs_check ─────────────────────────────────────────
# The C API capsule exposes both:
#   VarAPI->unify()    — no occurs check (used by _lists_core.c)
#   VarAPI->unify_oc() — with occurs check (used by _constraints_dif.c)
#
# unify() allows circular terms (X = f(X) succeeds).
# unify_with_occurs_check() rejects them (returns False, rolls back).
# Both must handle normal unification identically.


class TestUnifyOccursCheck:

    def test_normal_unify_succeeds(self):
        """Both paths succeed for non-circular terms."""
        # nv
        trail = fresh_trail()
        x = Var()
        assert unify(x, 42, trail)
        assert deref(x) == 42

    def test_normal_unify_oc_succeeds(self):
        # nv
        trail = fresh_trail()
        x = Var()
        assert unify_with_occurs_check(x, 42, trail)
        assert deref(x) == 42

    def test_circular_unify_succeeds(self):
        """unify (no OC) allows X = (X,) — creates circular term."""
        # nv
        trail = fresh_trail()
        x = Var()
        result = unify(x, (x,), trail)
        assert result is True
        # x is now bound to a tuple containing itself
        assert deref(x) == (x,)

    def test_circular_unify_oc_fails(self):
        """unify_with_occurs_check rejects X = (X,) — circular."""
        # nv
        trail = fresh_trail()
        x = Var()
        result = unify_with_occurs_check(x, (x,), trail)
        assert result is False
        # x should be unbound (rolled back)
        assert is_var(deref(x))

    def test_nested_circular_unify_succeeds(self):
        """unify allows X = (1, (X,)) — nested circular."""
        # nv
        trail = fresh_trail()
        x = Var()
        result = unify(x, (1, (x,)), trail)
        assert result is True

    def test_nested_circular_unify_oc_fails(self):
        """unify_with_occurs_check rejects nested circular."""
        # nv
        trail = fresh_trail()
        x = Var()
        result = unify_with_occurs_check(x, (1, (x,)), trail)
        assert result is False
        assert is_var(deref(x))

    def test_var_var_unify(self):
        """Both paths handle Var-Var unification."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        assert unify(x, y, trail)
        # Now bind y → both should see it
        assert unify(y, 99, trail)
        assert deref(x) == 99

    def test_var_var_unify_oc(self):
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        assert unify_with_occurs_check(x, y, trail)
        assert unify_with_occurs_check(y, 99, trail)
        assert deref(x) == 99

    def test_list_unify(self):
        """Both paths unify lists element-wise."""
        # nv
        trail = fresh_trail()
        x = Var()
        assert unify([1, x, 3], [1, 2, 3], trail)
        assert deref(x) == 2

    def test_list_unify_oc(self):
        # nv
        trail = fresh_trail()
        x = Var()
        assert unify_with_occurs_check([1, x, 3], [1, 2, 3], trail)
        assert deref(x) == 2

    def test_list_circular_unify_succeeds(self):
        """unify allows X = [X] — circular list."""
        # nv
        trail = fresh_trail()
        x = Var()
        result = unify(x, [x], trail)
        assert result is True

    def test_list_circular_unify_oc_fails(self):
        """unify_with_occurs_check rejects X = [X]."""
        # nv
        trail = fresh_trail()
        x = Var()
        result = unify_with_occurs_check(x, [x], trail)
        assert result is False
        assert is_var(deref(x))

    def test_failure_rolls_back(self):
        """Failed unification rolls back partial bindings."""
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        # [x, y] vs [1, 2, 3] — length mismatch, fails
        result = unify([x, y], [1, 2, 3], trail)
        assert result is False
        assert is_var(deref(x))  # rolled back

    def test_failure_rolls_back_oc(self):
        # nv
        trail = fresh_trail()
        x, y = Var(), Var()
        result = unify_with_occurs_check([x, y], [1, 2, 3], trail)
        assert result is False
        assert is_var(deref(x))
