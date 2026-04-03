"""Tests for Z3 advanced theories — Phase 6.

Covers: arrays, sets, strings, uninterpreted functions, quantifiers,
        algebraic datatypes, and on_fixed integration test.
"""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    get_z3_state, z3_check,
    z3_array, z3_select, z3_store, z3_const_array,
    z3_set, z3_set_member, z3_set_not_member, z3_set_subset,
    z3_set_union, z3_set_intersect, z3_set_add,
    z3_string, z3_str_length, z3_str_contains, z3_str_concat,
    z3_str_regex, label_z3_str,
    z3_function, z3_app, Z3FuncInfo,
    z3_forall, z3_exists,
    z3_declare_datatype,
    ClausalPropagator, in_z3, label_z3, z3_push,
)


# ══════════════════════════════════════════════════════════════════════════════
# Arrays
# ══════════════════════════════════════════════════════════════════════════════

class TestArrays:
    def test_declare_array(self):
        trail = Trail()
        a = Var()
        assert z3_array(a, z3.IntSort(), z3.IntSort(), trail)
        state = get_z3_state(trail)
        assert state.var_map[id(a)].sort() == z3.ArraySort(z3.IntSort(), z3.IntSort())

    def test_store_then_select_same_index(self):
        """Store 42 at index 0 then select index 0 → 42."""
        trail = Trail()
        a, a2, v = Var(), Var(), Var()
        z3_array(a, z3.IntSort(), z3.IntSort(), trail)
        z3_store(a, 0, 42, a2, trail)
        z3_select(a2, 0, v, trail)
        assert z3_check(trail)
        from clausal.logic.clpz3 import label_z3
        from clausal.logic.clpz3 import in_z3
        in_z3(v, 0, 100, trail)
        sols = []
        for _ in label_z3([v], trail):
            sols.append(deref(v))
        assert sols == [42]

    def test_store_then_select_different_index(self):
        """Store at 0, select at 1 → value unconstrained by the store."""
        trail = Trail()
        a, a2, v0, v1 = Var(), Var(), Var(), Var()
        z3_array(a, z3.IntSort(), z3.IntSort(), trail)
        z3_store(a, 0, 99, a2, trail)
        z3_select(a2, 0, v0, trail)
        z3_select(a2, 1, v1, trail)
        in_z3([v0, v1], 0, 200, trail)
        # v0 must be 99, v1 is unconstrained in 0..200
        from clausal.logic.clpz3 import z3_eq
        z3_eq(v0, 99, trail)
        assert z3_check(trail)

    def test_two_stores_same_index_last_wins(self):
        """Overwrite index 0 twice: final value is the second store."""
        trail = Trail()
        a, a1, a2, v = Var(), Var(), Var(), Var()
        z3_array(a, z3.IntSort(), z3.IntSort(), trail)
        z3_store(a, 0, 10, a1, trail)
        z3_store(a1, 0, 20, a2, trail)
        z3_select(a2, 0, v, trail)
        in_z3(v, 0, 100, trail)
        sols = []
        for _ in label_z3([v], trail):
            sols.append(deref(v))
        assert sols == [20]

    def test_const_array(self):
        """Constant array: every element is 7."""
        trail = Trail()
        a, v = Var(), Var()
        z3_const_array(7, z3.IntSort(), a, trail)
        z3_select(a, 42, v, trail)
        in_z3(v, 0, 100, trail)
        sols = []
        for _ in label_z3([v], trail):
            sols.append(deref(v))
        assert sols == [7]

    def test_ground_non_var_raises(self):
        trail = Trail()
        with pytest.raises(TypeError, match="expected Var"):
            z3_array(42, z3.IntSort(), z3.IntSort(), trail)


# ══════════════════════════════════════════════════════════════════════════════
# Sets
# ══════════════════════════════════════════════════════════════════════════════

class TestSets:
    def test_declare_set(self):
        trail = Trail()
        s = Var()
        assert z3_set(s, z3.IntSort(), trail)
        state = get_z3_state(trail)
        assert state.var_map[id(s)].sort() == z3.SetSort(z3.IntSort())

    def _empty_set(self, trail):
        """Helper: return a Z3 empty set expression for IntSort."""
        s = Var()
        z3_const_array(False, z3.IntSort(), s, trail)
        return s

    def test_member_after_add(self):
        """elem added to empty set → IsMember(elem, s2) is satisfiable."""
        trail = Trail()
        s1, s2 = self._empty_set(trail), Var()
        z3_set_add(s1, 5, s2, trail)
        z3_set_member(5, s2, trail)
        assert z3_check(trail)

    def test_not_member_of_empty(self):
        """Empty set has no members."""
        trail = Trail()
        s = self._empty_set(trail)
        z3_set_member(42, s, trail)
        assert not z3_check(trail)

    def test_subset(self):
        """EmptySet ⊆ any set."""
        trail = Trail()
        empty = self._empty_set(trail)
        full = Var()
        z3_const_array(True, z3.IntSort(), full, trail)
        z3_set_subset(empty, full, trail)
        assert z3_check(trail)

    def test_not_subset(self):
        """Full set ⊄ empty set."""
        trail = Trail()
        empty = self._empty_set(trail)
        full = Var()
        z3_const_array(True, z3.IntSort(), full, trail)
        z3_set_subset(full, empty, trail)
        assert not z3_check(trail)

    def test_union(self):
        """Union of two singleton sets contains both elements."""
        trail = Trail()
        s1a, s1b = self._empty_set(trail), Var()
        s2a, s2b = self._empty_set(trail), Var()
        su = Var()
        z3_set_add(s1a, 1, s1b, trail)
        z3_set_add(s2a, 2, s2b, trail)
        z3_set_union(s1b, s2b, su, trail)
        z3_set_member(1, su, trail)
        z3_set_member(2, su, trail)
        assert z3_check(trail)

    def test_intersect_disjoint(self):
        """Intersection of disjoint singleton sets has no members."""
        trail = Trail()
        s1a, s1b = self._empty_set(trail), Var()
        s2a, s2b = self._empty_set(trail), Var()
        si = Var()
        z3_set_add(s1a, 1, s1b, trail)
        z3_set_add(s2a, 2, s2b, trail)
        z3_set_intersect(s1b, s2b, si, trail)
        z3_set_member(1, si, trail)
        assert not z3_check(trail)

    def test_set_not_member(self):
        trail = Trail()
        s = self._empty_set(trail)
        z3_set_not_member(42, s, trail)
        assert z3_check(trail)


# ══════════════════════════════════════════════════════════════════════════════
# Strings
# ══════════════════════════════════════════════════════════════════════════════

class TestStrings:
    def test_declare_string(self):
        trail = Trail()
        s = Var()
        assert z3_string(s, trail)
        state = get_z3_state(trail)
        assert state.var_map[id(s)].sort() == z3.StringSort()

    def test_length_constraint(self):
        trail = Trail()
        s = Var()
        z3_string(s, trail)
        z3_str_length(s, 5, trail)
        assert z3_check(trail)
        sols = []
        for _ in label_z3_str(s, trail):
            sols.append(deref(s))
        assert len(sols) == 1
        assert len(sols[0]) == 5

    def test_contains_hello(self):
        trail = Trail()
        s = Var()
        z3_string(s, trail)
        z3_str_contains(s, "hello", trail)
        z3_str_length(s, 5, trail)
        assert z3_check(trail)
        sols = []
        for _ in label_z3_str(s, trail):
            sols.append(deref(s))
        assert len(sols) == 1
        assert "hello" in sols[0]

    def test_concat_constraint(self):
        """Concat(s1, s2) == s3, s1 == 'foo', s2 == 'bar' → s3 == 'foobar'."""
        from clausal.logic.clpz3 import z3_push
        trail = Trail()
        s1, s2, s3 = Var(), Var(), Var()
        z3_string(s1, trail)
        z3_string(s2, trail)
        state = get_z3_state(trail)
        z3_s1 = state.var_map[id(s1)]
        z3_s2 = state.var_map[id(s2)]
        z3_push(trail)
        state.solver.add(z3_s1 == z3.StringVal("foo"))
        state.solver.add(z3_s2 == z3.StringVal("bar"))
        z3_str_concat(s1, s2, s3, trail)
        sols = []
        for _ in label_z3_str(s3, trail):
            sols.append(deref(s3))
        assert len(sols) == 1
        assert sols[0] == "foobar"

    def test_regex_digits_only(self):
        """s matches [0-9]+ (one or more digits)."""
        trail = Trail()
        s = Var()
        z3_string(s, trail)
        # Z3 regex: one or more digits
        digit = z3.Range(z3.StringVal("0"), z3.StringVal("9"))
        z3_str_regex(s, z3.Plus(digit), trail)
        z3_str_length(s, 3, trail)
        assert z3_check(trail)
        sols = []
        for _ in label_z3_str(s, trail):
            sols.append(deref(s))
        assert len(sols) == 1
        assert sols[0].isdigit()

    def test_unsatisfiable_string(self):
        """Length 5 AND length 3 → unsat."""
        trail = Trail()
        s = Var()
        z3_string(s, trail)
        z3_str_length(s, 5, trail)
        z3_str_length(s, 3, trail)
        assert not z3_check(trail)

    def test_ground_var_yields_immediately(self):
        trail = Trail()
        assert len(list(label_z3_str("hello", trail))) == 1

    def test_clausal_to_z3_handles_str(self):
        """clausal_to_z3 converts Python str to StringVal."""
        from clausal.logic.clpz3 import clausal_to_z3
        trail = Trail()
        result = clausal_to_z3("hello", trail)
        assert z3.is_string_value(result)
        assert result.as_string() == "hello"


# ══════════════════════════════════════════════════════════════════════════════
# Uninterpreted functions
# ══════════════════════════════════════════════════════════════════════════════

class TestUninterpretedFunctions:
    def test_declare_function(self):
        trail = Trail()
        f = Var()
        assert z3_function(f, [z3.IntSort()], z3.IntSort(), trail)
        from clausal.logic.variables import get_attr
        from clausal.logic.clpz3 import Z3_KEY
        info = get_attr(deref(f), Z3_KEY)
        assert isinstance(info, Z3FuncInfo)

    def test_apply_function(self):
        """f(3) == 7, f(3) == ? → 7."""
        trail = Trail()
        f, r = Var(), Var()
        z3_function(f, [z3.IntSort()], z3.IntSort(), trail)
        z3_app(f, [3], r, trail)
        from clausal.logic.clpz3 import z3_eq, in_z3
        in_z3(r, 0, 100, trail)
        # Force f(3) == 7 by constraining r
        z3_eq(r, 7, trail)
        sols = []
        for _ in label_z3([r], trail):
            sols.append(deref(r))
        assert sols == [7]

    def test_two_calls_same_arg_equal(self):
        """Uninterpreted function: f(3) and f(3) must be equal."""
        trail = Trail()
        f, r1, r2 = Var(), Var(), Var()
        z3_function(f, [z3.IntSort()], z3.IntSort(), trail)
        z3_app(f, [3], r1, trail)
        z3_app(f, [3], r2, trail)
        in_z3([r1, r2], 0, 100, trail)
        # Force r1 != r2 → should be unsat (same f(3) must equal itself)
        from clausal.logic.clpz3 import z3_ne
        z3_ne(r1, r2, trail)
        assert not z3_check(trail)

    def test_two_calls_different_args_independent(self):
        """f(1) and f(2) are independent."""
        trail = Trail()
        f, r1, r2 = Var(), Var(), Var()
        z3_function(f, [z3.IntSort()], z3.IntSort(), trail)
        z3_app(f, [1], r1, trail)
        z3_app(f, [2], r2, trail)
        in_z3([r1, r2], 0, 10, trail)
        from clausal.logic.clpz3 import z3_ne
        z3_ne(r1, r2, trail)
        assert z3_check(trail)  # f(1) != f(2) is satisfiable

    def test_non_function_var_raises(self):
        trail = Trail()
        x = Var()
        with pytest.raises(TypeError, match="not an uninterpreted function"):
            z3_app(x, [1], Var(), trail)


# ══════════════════════════════════════════════════════════════════════════════
# Quantifiers
# ══════════════════════════════════════════════════════════════════════════════

class TestQuantifiers:
    def test_forall_tautology(self):
        """ForAll(x, x == x) is a tautology — always satisfiable."""
        trail = Trail()
        z3_forall([("x", z3.IntSort())], lambda x: x == x, trail)
        assert z3_check(trail)

    def test_forall_contradiction(self):
        """ForAll(x, x > x) is unsatisfiable."""
        trail = Trail()
        z3_forall([("x", z3.IntSort())], lambda x: x > x, trail)
        assert not z3_check(trail)

    def test_exists_simple(self):
        """Exists(x, x == 5) is satisfiable."""
        trail = Trail()
        z3_exists([("x", z3.IntSort())], lambda x: x == 5, trail)
        assert z3_check(trail)

    def test_exists_impossible(self):
        """Exists(x: BoolSort, x & ~x) is unsatisfiable."""
        trail = Trail()
        z3_exists([("x", z3.BoolSort())], lambda x: z3.And(x, z3.Not(x)), trail)
        assert not z3_check(trail)

    def test_forall_with_function(self):
        """ForAll(x, f(x) >= 0) with f :: Int -> Int — satisfiable."""
        trail = Trail()
        f = z3.Function("f_test", z3.IntSort(), z3.IntSort())
        z3_forall([("x", z3.IntSort())], lambda x: f(x) >= 0, trail)
        assert z3_check(trail)

    def test_backtracking_retracts_quantifier(self):
        trail = Trail()
        mark = trail.mark()
        z3_forall([("x", z3.IntSort())], lambda x: x > x, trail)
        assert not z3_check(trail)
        trail.undo(mark)
        assert z3_check(trail)


# ══════════════════════════════════════════════════════════════════════════════
# Algebraic datatypes
# ══════════════════════════════════════════════════════════════════════════════

class TestAlgebraicDatatypes:
    def test_declare_enum(self):
        """Declare a Color enum: red, green, blue."""
        trail = Trail()
        sort = z3_declare_datatype("Color3", [
            ("red3",   []),
            ("green3", []),
            ("blue3",  []),
        ], trail)
        assert sort is not None
        state = get_z3_state(trail)
        assert "Color3" in state.datatypes

    def test_declare_pair(self):
        """Declare Pair(first: Int, second: Int)."""
        trail = Trail()
        sort = z3_declare_datatype("Pair2", [
            ("pair2", [("first2", z3.IntSort()), ("second2", z3.IntSort())]),
        ], trail)
        assert sort is not None

    def test_enum_satisfiable(self):
        """A variable of an enum sort is satisfiable."""
        trail = Trail()
        sort = z3_declare_datatype("Dir", [
            ("north", []), ("south", []), ("east", []), ("west", []),
        ], trail)
        state = get_z3_state(trail)
        d = z3.Const("d", sort)
        state.solver.add(d != sort.north)
        assert z3_check(trail)

    def test_recursive_datatype(self):
        """Declare a singly-linked list: nil | cons(head: Int, tail: IntList2)."""
        trail = Trail()
        sort = z3_declare_datatype("IntList2", [
            ("nil2",  []),
            ("cons2", [("head2", z3.IntSort()), ("tail2", "IntList2")]),
        ], trail)
        assert sort is not None
        state = get_z3_state(trail)
        assert "IntList2" in state.datatypes


# ══════════════════════════════════════════════════════════════════════════════
# on_fixed integration test (Phase 5 Issue 8)
# ══════════════════════════════════════════════════════════════════════════════

class TestOnFixedIntegration:
    def test_on_fixed_records_assignment(self):
        """on_fixed goal is called when Z3 fixes a Bool variable.

        Note: Z3's UserPropagateBase only fires on_fixed for Boolean
        variables (SAT-level atoms), not for theory variables like Int.
        """
        trail = Trail()
        # Create a Z3 state with a Bool variable directly
        state = get_z3_state(trail)
        z3_x = z3.Bool("p")

        recorded = []

        def my_goal(var, value, t):
            recorded.append(value)
            return []

        # Map z3_x into rev_map so _handle_fixed can resolve it
        sentinel = Var()
        state.rev_map[z3_x.get_id()] = sentinel

        prop = ClausalPropagator(
            state.solver, trail, state.var_map, state.rev_map,
            on_fixed_goals=[my_goal],
        )
        prop.add(z3_x)

        # Store propagator to prevent GC during check()
        if not hasattr(state, '_propagators'):
            state._propagators = []
        state._propagators.append(prop)

        # Force p = True
        z3_push(trail)
        state.solver.add(z3_x == True)

        state.solver.check()

        # on_fixed should have been called with True
        assert True in recorded
