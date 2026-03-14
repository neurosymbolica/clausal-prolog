"""ISO Prolog conformity: arithmetic evaluation.

ISO §8.6 — is/2 (evaluable functors)
ISO §8.7 — arithmetic comparison (=:=, =\\=, <, >, =<, >=)

Clausal equivalents:
  :=   → arithmetic evaluation (is/2 in Prolog)
  <    → less-than
  <=   → less-or-equal (=< in Prolog)
  >    → greater-than
  >=   → greater-or-equal

Differences from ISO:
  - Prolog: X is 3+2  →  X = 5
    Clausal: X := 3+2  →  X bound to 5
  - Prolog: X is atom  →  type_error
    Clausal: no error — goal simply fails
  - Prolog: =:= (arithmetic equality), =\\= (arithmetic inequality)
    Clausal: no direct equivalent; use := to evaluate then == to compare.
  - Integer division: Python -7 // 2 = -4 (floor), some Prologs = -3 (truncate).
  - Prolog mod follows truncation semantics; Python % follows floor semantics.
"""

from __future__ import annotations

import pytest
from clausal.logic.database import Module
from clausal.logic.solve import solve, once, call
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import (
    Evaluate, Add, Sub, Mult, FloorDiv, Mod, Pow, Negate,
    Lt, LtE, Gt, GtE,
    Call as CallGoal, LoadName,
)


def _goal_succeeds(goal, mod=None):
    if mod is None:
        mod = Module("test")
    return once(goal, mod) is not None


def _eval_to(expr, mod=None):
    """Evaluate expr via :=, return the result."""
    x = Var()
    goal = Evaluate(left=x, right=expr)
    if mod is None:
        mod = Module("test")
    results = [deref(x) for _ in solve(goal, mod)]
    assert len(results) == 1, f"Expected 1 solution, got {len(results)} for {expr}"
    return results[0]


def _call_var(functor, *args, var=None, mod=None):
    """Call builtin, return deref'd values of specified Var per solution.
    If var is None, uses the last arg."""
    if mod is None:
        mod = Module("test")
    if var is None:
        var = args[-1]
    return [deref(var) for _ in call(functor, *args, module=mod)]


# ── is/2 → := (arithmetic evaluation) ────────────────────────────────────────


class TestArithmeticEvaluation:
    """ISO §8.6.1 — is/2."""

    def test_addition(self):
        """ISO: X is 1+2, X = 3."""
        assert _eval_to(Add(left=1, right=2)) == 3

    def test_subtraction(self):
        assert _eval_to(Sub(left=5, right=3)) == 2

    def test_multiplication(self):
        assert _eval_to(Mult(left=3, right=4)) == 12

    def test_integer_division(self):
        """ISO: X is 7//2, X = 3."""
        assert _eval_to(FloorDiv(left=7, right=2)) == 3

    def test_modulo(self):
        """ISO: X is 7 mod 2, X = 1.
        Clausal: 7 % 2 = 1."""
        assert _eval_to(Mod(left=7, right=2)) == 1

    def test_power(self):
        """Clausal extension: X := 2 ** 3 = 8."""
        assert _eval_to(Pow(left=2, right=3)) == 8

    def test_negation(self):
        """ISO: X is -3."""
        assert _eval_to(Negate(operand=3)) == -3

    def test_nested_expression(self):
        """ISO: X is (2+3)*4, X = 20."""
        assert _eval_to(Mult(left=Add(left=2, right=3), right=4)) == 20

    def test_float_addition(self):
        assert _eval_to(Add(left=1.5, right=2.5)) == 4.0

    def test_mixed_int_float(self):
        """Python promotes int+float to float."""
        result = _eval_to(Add(left=1, right=2.0))
        assert result == 3.0
        assert isinstance(result, float)

    def test_eval_binds_var(self):
        """X := 42 binds X to 42."""
        x = Var()
        goal = Evaluate(left=x, right=42)
        mod = Module("test")
        results = [deref(x) for _ in solve(goal, mod)]
        assert results == [42]

    def test_eval_check_mode(self):
        """When LHS is already bound, := checks equality.
        ISO: 3 is 1+2 succeeds."""
        goal = Evaluate(left=3, right=Add(left=1, right=2))
        assert _goal_succeeds(goal)

    def test_eval_check_fails(self):
        """ISO: 4 is 1+2 fails."""
        goal = Evaluate(left=4, right=Add(left=1, right=2))
        assert not _goal_succeeds(goal)

    def test_negative_integer_division(self):
        """DIFFERS from some ISO implementations:
        Python: -7 // 2 = -4 (floor division).
        Some Prologs: -7 // 2 = -3 (truncation toward zero)."""
        assert _eval_to(FloorDiv(left=-7, right=2)) == -4

    def test_negative_modulo(self):
        """DIFFERS: Python mod follows floor division.
        -7 % 2 = 1 in Python, but -7 mod 2 = -1 in some Prologs."""
        assert _eval_to(Mod(left=-7, right=2)) == 1

    def test_large_integer(self):
        """Python supports arbitrary-precision integers (ISO only requires
        min_integer..max_integer)."""
        big = 10**100
        assert _eval_to(Add(left=big, right=1)) == big + 1

    def test_double_negation(self):
        assert _eval_to(Negate(operand=Negate(operand=5))) == 5

    def test_subtraction_negative_result(self):
        assert _eval_to(Sub(left=3, right=5)) == -2


# ── Arithmetic comparison ────────────────────────────────────────────────────


class TestArithmeticComparison:
    """ISO §8.7 — arithmetic comparison.

    In Prolog: =:=, =\\=, <, >, =<, >=.
    In clausal: only <, <=, >, >= are direct.
    """

    def test_lt_succeeds(self):
        """ISO: 1 < 2 succeeds."""
        assert _goal_succeeds(Lt(left=1, right=2))

    def test_lt_fails(self):
        """ISO: 2 < 1 fails."""
        assert not _goal_succeeds(Lt(left=2, right=1))

    def test_lt_equal_fails(self):
        """ISO: 1 < 1 fails."""
        assert not _goal_succeeds(Lt(left=1, right=1))

    def test_lte_succeeds_less(self):
        assert _goal_succeeds(LtE(left=1, right=2))

    def test_lte_succeeds_equal(self):
        """ISO: 1 =< 1 succeeds."""
        assert _goal_succeeds(LtE(left=1, right=1))

    def test_gt_succeeds(self):
        assert _goal_succeeds(Gt(left=2, right=1))

    def test_gt_fails(self):
        assert not _goal_succeeds(Gt(left=1, right=2))

    def test_gte_succeeds(self):
        assert _goal_succeeds(GtE(left=2, right=1))

    def test_gte_equal(self):
        assert _goal_succeeds(GtE(left=1, right=1))

    def test_float_comparison(self):
        assert _goal_succeeds(Lt(left=1.5, right=2.5))

    def test_mixed_int_float_comparison(self):
        """Arithmetic comparison evaluates both sides.
        Python 1 < 1.0 is False, 1 <= 1.0 is True."""
        assert not _goal_succeeds(Lt(left=1, right=1.0))
        assert _goal_succeeds(LtE(left=1, right=1.0))

    def test_expression_comparison(self):
        """ISO: 1+2 < 2+3 (evaluates both sides)."""
        assert _goal_succeeds(Lt(
            left=Add(left=1, right=2),
            right=Add(left=2, right=3),
        ))

    def test_expression_comparison_equal(self):
        """ISO: 1+2 =< 3 succeeds."""
        assert _goal_succeeds(LtE(
            left=Add(left=1, right=2),
            right=3,
        ))


# ── Builtin arithmetic predicates ────────────────────────────────────────────


class TestArithmeticBuiltins:
    """Non-ISO builtins for arithmetic: succ/2, plus/3, between/3,
    abs_/2, max_/3, min_/3."""

    def test_succ_forward(self):
        """succ(3, X) → X = 4."""
        x = Var()
        assert _call_var("Succ", 3, x) == [4]

    def test_succ_backward(self):
        """succ(X, 4) → X = 3."""
        x = Var()
        assert _call_var("Succ", x, 4, var=x) == [3]

    def test_succ_zero(self):
        x = Var()
        assert _call_var("Succ", 0, x) == [1]

    def test_plus_forward(self):
        """plus(2, 3, X) → X = 5."""
        x = Var()
        assert _call_var("Plus", 2, 3, x) == [5]

    def test_plus_backward_x(self):
        """plus(X, 3, 5) → X = 2."""
        x = Var()
        assert _call_var("Plus", x, 3, 5, var=x) == [2]

    def test_plus_backward_y(self):
        """plus(2, Y, 5) → Y = 3."""
        y = Var()
        assert _call_var("Plus", 2, y, 5, var=y) == [3]

    def test_between_generates(self):
        """between(1, 5, X) generates 1,2,3,4,5."""
        x = Var()
        assert _call_var("Between", 1, 5, x) == [1, 2, 3, 4, 5]

    def test_between_check_mode(self):
        """between(1, 5, 3) succeeds."""
        mod = Module("test")
        goal = CallGoal(func=LoadName(name="Between"), args=[1, 5, 3], kwargs=[])
        assert once(goal, mod) is not None

    def test_between_check_out_of_range(self):
        """between(1, 5, 6) fails."""
        mod = Module("test")
        goal = CallGoal(func=LoadName(name="Between"), args=[1, 5, 6], kwargs=[])
        assert once(goal, mod) is None

    def test_abs(self):
        x = Var()
        assert _call_var("Abs", -5, x) == [5]

    def test_max(self):
        x = Var()
        assert _call_var("Max", 3, 7, x) == [7]

    def test_min(self):
        x = Var()
        assert _call_var("Min", 3, 7, x) == [3]
