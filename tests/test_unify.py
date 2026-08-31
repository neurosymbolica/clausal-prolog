"""Tests for structural_unify — Step 9.

structural_unify (clausal.logic.builtins) extends the C-extension unify with
Python-level recursive unification for Compound, KWTerm, and dataclass terms.

Covers:
  - Compound ↔ Compound: same functor/arity, mismatches, recursive, with Var
  - list ↔ list: element-wise unification
  - Dataclass ↔ dataclass: same-type field-by-field unification
  - KWTerm ↔ KWTerm: order-independent key-matching unification
  - Var arguments: binding and trail integration
  - Trail undo: partial unification is rolled back on failure
  - Fall-through: atomics and mixed types delegate to C unify
"""

from __future__ import annotations

import dataclasses
import pytest

from clausal.logic.builtins import structural_unify
from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.terms import Compound, KWTerm


# ── Helpers ────────────────────────────────────────────────────────────────────


def fresh() -> Trail:
    return Trail()


# ── Synthetic functor dataclasses ─────────────────────────────────────────────


@dataclasses.dataclass
class point:
    x: object = None
    y: object = None


@dataclasses.dataclass
class vec3:
    x: object = None
    y: object = None
    z: object = None


@dataclasses.dataclass
class pair:
    left: object = None
    right: object = None


# ── TestStructuralUnifyCompound ────────────────────────────────────────────────


class TestStructuralUnifyCompound:
    def test_same_ground_succeeds(self):
        # nv
        t = fresh()
        assert structural_unify(Compound("f", (1, 2)), Compound("f", (1, 2)), t)

    def test_different_functor_fails(self):
        # nv
        t = fresh()
        assert not structural_unify(Compound("f", (1,)), Compound("g", (1,)), t)

    def test_different_arity_fails(self):
        # nv
        t = fresh()
        assert not structural_unify(Compound("f", (1,)), Compound("f", (1, 2)), t)

    def test_unify_with_var_arg(self):
        # nv
        t = fresh()
        v = Var()
        assert structural_unify(Compound("f", (v, 2)), Compound("f", (99, 2)), t)
        assert deref(v) == 99

    def test_var_on_right_side(self):
        # nv
        t = fresh()
        v = Var()
        assert structural_unify(Compound("f", (1,)), Compound("f", (v,)), t)
        assert deref(v) == 1

    def test_var_var_in_compound(self):
        # nv
        t = fresh()
        v1, v2 = Var(), Var()
        assert structural_unify(Compound("f", (v1,)), Compound("f", (v2,)), t)
        assert deref(v1) is deref(v2)

    def test_nested_compound(self):
        # nv
        t = fresh()
        v = Var()
        lhs = Compound("f", (Compound("g", (v,)),))
        rhs = Compound("f", (Compound("g", (42,)),))
        assert structural_unify(lhs, rhs, t)
        assert deref(v) == 42

    def test_nested_mismatch_fails(self):
        # nv
        t = fresh()
        lhs = Compound("f", (Compound("g", (1,)),))
        rhs = Compound("f", (Compound("h", (1,)),))
        assert not structural_unify(lhs, rhs, t)

    def test_arity_zero(self):
        # nv
        t = fresh()
        assert structural_unify(Compound("nil", ()), Compound("nil", ()), t)
        assert not structural_unify(Compound("nil", ()), Compound("cons", ()), t)

    def test_trail_undo_on_failure(self):
        """Partial bindings inside a Compound unify are rolled back on failure."""
        # nv
        t = fresh()
        v1, v2 = Var(), Var()
        # f(V1, 99) vs f(42, 100) — V1 would bind to 42 but 99 != 100 → fail
        lhs = Compound("f", (v1, 99))
        rhs = Compound("f", (42, 100))
        mark = t.mark()
        result = structural_unify(lhs, rhs, t)
        assert not result
        assert not is_var(v1) or not v1.is_bound  # v1 was rolled back
        # Confirm: trail is back at mark
        t.undo(mark)  # should be a no-op already
        assert not v1.is_bound


# ── TestStructuralUnifyList ────────────────────────────────────────────────────


class TestStructuralUnifyList:
    def test_empty_lists(self):
        # nv
        assert structural_unify([], [], fresh())

    def test_same_ground_lists(self):
        # nv
        assert structural_unify([1, 2, 3], [1, 2, 3], fresh())

    def test_different_lengths_fail(self):
        # nv
        assert not structural_unify([1, 2], [1, 2, 3], fresh())

    def test_list_with_var(self):
        # nv
        t = fresh()
        v = Var()
        assert structural_unify([1, v, 3], [1, 99, 3], t)
        assert deref(v) == 99

    def test_list_partial_fail_undoes(self):
        # nv
        t = fresh()
        v = Var()
        # [V, 99] vs [42, 100] — V would bind to 42 but 99 != 100
        result = structural_unify([v, 99], [42, 100], t)
        assert not result
        assert not v.is_bound

    def test_nested_lists(self):
        # nv
        t = fresh()
        v = Var()
        assert structural_unify([[1, v], [3]], [[1, 2], [3]], t)
        assert deref(v) == 2


# ── TestStructuralUnifyDataclass ───────────────────────────────────────────────


class TestStructuralUnifyDataclass:
    def test_same_ground_succeeds(self):
        # nv
        t = fresh()
        assert structural_unify(point(x=1, y=2), point(x=1, y=2), t)

    def test_field_mismatch_fails(self):
        # nv
        t = fresh()
        assert not structural_unify(point(x=1, y=2), point(x=1, y=99), t)

    def test_with_var_field(self):
        # nv
        t = fresh()
        v = Var()
        assert structural_unify(point(x=v, y=2), point(x=42, y=2), t)
        assert deref(v) == 42

    def test_var_on_both_sides(self):
        # nv
        t = fresh()
        v1, v2 = Var(), Var()
        assert structural_unify(point(x=v1, y=0), point(x=v2, y=0), t)
        # Both vars should refer to the same root after unification
        assert deref(v1) is deref(v2)

    def test_different_types_fail(self):
        """Different dataclass types do not unify via structural_unify."""
        # nv
        t = fresh()
        p = point(x=1, y=2)
        pair_term = pair(left=1, right=2)
        # Different types — falls back to C unify which tests ==, fails
        assert not structural_unify(p, pair_term, t)

    def test_nested_dataclass(self):
        # nv
        t = fresh()
        v = Var()
        lhs = pair(left=point(x=v, y=0), right=10)
        rhs = pair(left=point(x=99, y=0), right=10)
        assert structural_unify(lhs, rhs, t)
        assert deref(v) == 99

    def test_trail_undo_on_failure(self):
        # nv
        t = fresh()
        v = Var()
        # point(V, 2) vs point(42, 99) — V binds to 42 but 2 != 99 → fail
        result = structural_unify(point(x=v, y=2), point(x=42, y=99), t)
        assert not result
        assert not v.is_bound

    def test_three_field_dataclass(self):
        # nv
        t = fresh()
        vx, vy, vz = Var(), Var(), Var()
        lhs = vec3(x=vx, y=vy, z=vz)
        rhs = vec3(x=1, y=2, z=3)
        assert structural_unify(lhs, rhs, t)
        assert deref(vx) == 1
        assert deref(vy) == 2
        assert deref(vz) == 3


# ── TestStructuralUnifyKWTerm ──────────────────────────────────────────────────


class TestStructuralUnifyKWTerm:
    def test_same_ground_succeeds(self):
        # nv
        t = fresh()
        k1 = KWTerm("r", a=1, b=2)
        k2 = KWTerm("r", a=1, b=2)
        assert structural_unify(k1, k2, t)

    def test_order_independent(self):
        """KWTerm unification matches by key name, not insertion order."""
        # nv
        t = fresh()
        k1 = KWTerm("r", a=1, b=2)
        k2 = KWTerm("r", b=2, a=1)
        assert structural_unify(k1, k2, t)

    def test_different_functor_fails(self):
        # nv
        t = fresh()
        assert not structural_unify(KWTerm("r", a=1), KWTerm("s", a=1), t)

    def test_different_keys_fail(self):
        # nv
        t = fresh()
        assert not structural_unify(KWTerm("r", a=1), KWTerm("r", b=1), t)

    def test_value_mismatch_fails(self):
        # nv
        t = fresh()
        assert not structural_unify(KWTerm("r", a=1), KWTerm("r", a=2), t)

    def test_with_var_field(self):
        # nv
        t = fresh()
        v = Var()
        assert structural_unify(KWTerm("r", a=v, b=2), KWTerm("r", a=99, b=2), t)
        assert deref(v) == 99

    def test_trail_undo_on_failure(self):
        # nv
        t = fresh()
        v = Var()
        # a=V, b=1 vs a=42, b=99 — V binds to 42 but 1 != 99 → fail
        result = structural_unify(
            KWTerm("r", a=v, b=1), KWTerm("r", a=42, b=99), t
        )
        assert not result
        assert not v.is_bound

    def test_extra_keys_in_one_fails(self):
        # nv
        t = fresh()
        k1 = KWTerm("r", a=1, b=2, c=3)
        k2 = KWTerm("r", a=1, b=2)
        assert not structural_unify(k1, k2, t)


# ── TestStructuralUnifyVarArgs ─────────────────────────────────────────────────


class TestStructuralUnifyVarArgs:
    def test_top_level_var_binds(self):
        # nv
        t = fresh()
        v = Var()
        assert structural_unify(v, Compound("f", (1,)), t)
        assert deref(v) == Compound("f", (1,))

    def test_var_var_binds(self):
        # nv
        t = fresh()
        v1, v2 = Var(), Var()
        assert structural_unify(v1, v2, t)
        assert deref(v1) is deref(v2)

    def test_var_on_right_binds(self):
        # nv
        t = fresh()
        v = Var()
        assert structural_unify(99, v, t)
        assert deref(v) == 99

    def test_bound_var_left(self):
        # nv
        t = fresh()
        v = Var()
        unify(v, 42, t)
        # structural_unify should deref v and unify 42 with 42
        assert structural_unify(v, 42, t)

    def test_bound_var_mismatch(self):
        # nv
        t = fresh()
        v = Var()
        unify(v, 42, t)
        assert not structural_unify(v, 99, t)


# ── TestStructuralUnifyAtomics ─────────────────────────────────────────────────


class TestStructuralUnifyAtomics:
    """Atomics fall through to C unify — smoke tests."""

    def test_int_equal(self):
        # nv
        assert structural_unify(1, 1, fresh())

    def test_int_unequal(self):
        # nv
        assert not structural_unify(1, 2, fresh())

    def test_str_equal(self):
        # nv
        assert structural_unify("foo", "foo", fresh())

    def test_str_unequal(self):
        # nv
        assert not structural_unify("foo", "bar", fresh())

    def test_none_equal(self):
        # nv
        assert structural_unify(None, None, fresh())

    def test_bool_equal(self):
        # nv
        assert structural_unify(True, True, fresh())

    def test_mixed_types_fail(self):
        # nv
        assert not structural_unify(1, "1", fresh())


# ── TestUnifyOperatorNodes ─────────────────────────────────────────────────────


class TestUnifyOperatorNodes:
    """The C-extension ``unify`` must structurally unify arithmetic operator
    nodes (Add/Mult/Pow, ...).  They are structural terms per the language
    contract ("operators are matched/constructed, not evaluated"), so a clause
    that builds ``DA + DB`` must unify against another operator term with the
    same shape — binding the variables inside.  Regression for symbolic_diff.
    """

    def test_add_with_var_fields(self):
        # nv
        from clausal.terms import Add
        v1, v2 = Var(), Var()
        t = fresh()
        assert unify(Add(left=v1, right=v2), Add(left=1, right=1), t)
        assert deref(v1) == 1 and deref(v2) == 1

    def test_add_var_on_right(self):
        # nv
        from clausal.terms import Add
        v = Var()
        t = fresh()
        assert unify(Add(left=1, right=2), Add(left=1, right=v), t)
        assert deref(v) == 2

    def test_add_ground_match(self):
        # nv
        from clausal.terms import Add
        assert unify(Add(left=1, right=2), Add(left=1, right=2), fresh())

    def test_add_ground_mismatch(self):
        # nv
        from clausal.terms import Add
        assert not unify(Add(left=1, right=2), Add(left=1, right=3), fresh())

    def test_different_operators_dont_unify(self):
        # nv — Add and Mult are distinct structural terms
        from clausal.terms import Add, Mult
        v = Var()
        assert not unify(Add(left=v, right=1), Mult(left=1, right=1), fresh())

    def test_position_ignored(self):
        # nv — the non-semantic source-position field must not block unification
        from clausal.terms import Add
        t = fresh()
        a = Add(left=1, right=2, position=(1, 2, 3, 4))
        b = Add(left=1, right=2, position=(5, 6, 7, 8))
        assert unify(a, b, t)

    def test_nested_operator_unify(self):
        # nv — recursion into operands
        from clausal.terms import Add, Mult
        v = Var()
        t = fresh()
        assert unify(Add(left=Mult(left=2, right=v), right=1),
                     Add(left=Mult(left=2, right=3), right=1), t)
        assert deref(v) == 3

    def test_trail_undo_on_partial_failure(self):
        # nv — first field binds, second fails: the binding must roll back
        from clausal.terms import Add
        v = Var()
        t = fresh()
        assert not unify(Add(left=v, right=2), Add(left=9, right=3), t)
        assert is_var(deref(v))


# ── __unify__ hook probe semantics ────────────────────────────────────────────
# Pins for the C tail's protocol lookup (do_unify in _variables.c), written
# before the probe was switched from GetAttrString+PyErr_Clear to an
# exception-free optional lookup — the semantics below must survive that.


class TestUnifyHookProbe:
    def _hooked(self, ret):
        class Hooked:
            calls: list = []

            def __unify__(self, other, trail):
                Hooked.calls.append(other)
                return ret
        return Hooked

    def test_class_level_hook_left_operand(self):
        cls = self._hooked(True)
        h = cls()
        assert unify(h, 42, fresh()) is True
        assert cls.calls == [42]

    def test_class_level_hook_right_operand(self):
        """Symmetric probe: hook on the right operand runs when the left has
        none."""
        cls = self._hooked(True)
        h = cls()
        assert unify(42, h, fresh()) is True
        assert cls.calls == [42]

    def test_hook_false_fails(self):
        h = self._hooked(False)()
        assert unify(h, 42, fresh()) is False

    def test_notimplemented_falls_through_to_equality(self):
        """NotImplemented from the left hook falls through: the right operand
        is probed, then plain equality decides."""
        cls = self._hooked(NotImplemented)
        h = cls()
        assert unify(h, h, fresh()) is True   # == via identity
        assert unify(h, 42, fresh()) is False

    def test_instance_level_hook_is_honoured(self):
        """The probe is an instance attribute lookup, not a type-only one — a
        hook attached to a single instance still fires."""
        class Plain:
            pass

        p = Plain()
        p.__unify__ = lambda other, trail: True
        assert unify(p, 42, fresh()) is True

    def test_hook_beats_mixed_list_guard(self):
        """Documented ordering: the probe runs BEFORE the mixed list/tuple
        guard, so a custom type can unify against a plain list."""
        class ListLike:
            def __unify__(self, other, trail):
                return other == [1, 2]

        assert unify(ListLike(), [1, 2], fresh()) is True
        assert unify(ListLike(), [3], fresh()) is False

    def test_ordinary_failing_pairs_still_fail(self):
        class C:
            pass

        assert unify(1, 2, fresh()) is False
        assert unify("a", "b", fresh()) is False
        assert unify(C, int, fresh()) is False

    def test_hook_exception_propagates(self):
        class Boom:
            def __unify__(self, other, trail):
                raise RuntimeError("hook blew up")

        with pytest.raises(RuntimeError, match="hook blew up"):
            unify(Boom(), 42, fresh())
