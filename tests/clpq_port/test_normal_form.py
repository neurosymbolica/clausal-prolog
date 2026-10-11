# tests/clpq_port/test_normal_form.py
"""Task 10: nf.pl and nfq.pl (normal_form.py), the normal form and {}/1.

Until Task 11 registers the unification hook, binding a constrained
variable does not wake anything; tests that need a wake run the delayed
goals themselves (_bind), as geler.pl's hook would.
"""
import pathlib
import random
import sys
from fractions import Fraction

import pytest

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq import normal_form as nf
from clausal.logic.clpq.arithmetic import ONE, ZERO, make_rational
from clausal.logic.clpq.attributes import state_of
from clausal.logic.clpq.delayed_goals import (
    attribute_goal, collect_nonlinear, project_nonlinear, run)
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.pythonic_ast.nodes import (
    Add, ArithEq, ArithNeq, CompareChain, Div, Gt, GtE, IsoIntPow, Lt, LtE,
    Mult, Negate, Sub, UnaryPlus)


def q(numerator, denominator=1):
    return make_rational(numerator, denominator)


def _value(term):
    term = deref(term)
    assert not is_var(term), "unbound"
    return Fraction(term)


def _sup(x, trail):
    s = Var()
    if not bv.sup(x, s, trail):
        return None
    return _value(s)


def _inf(x, trail):
    i = Var()
    if not bv.inf(x, i, trail):
        return None
    return _value(i)


def _bind(variable, value, trail):
    """Bind *variable* and run its delayed goals, as geler.pl's hook would
    (Task 11 wires the hook)."""
    state = state_of(variable)
    goals = () if state is None or state.delayed_goals is None \
        else state.delayed_goals
    assert unify(variable, value, trail)
    for goal in goals:
        if not run(goal, trail):
            return False
    return True


def _depth():
    frame, depth = sys._getframe(), 0
    while frame is not None:
        frame, depth = frame.f_back, depth + 1
    return depth


# ---------------------------------------------------------------- a reference

def _reference(term):
    """The polynomial of *term* as {((var_id, exponent), ...): Fraction}."""
    if isinstance(term, Var):
        return {((term._id, 1),): Fraction(1)}
    if isinstance(term, (int, Fraction)):
        return {(): Fraction(term)} if term else {}
    kind = type(term)
    if kind is Negate:
        return {k: -v for k, v in _reference(term.operand).items()}
    left, right = _reference(term.left), _reference(term.right)
    if kind is Add or kind is Sub:
        sign = 1 if kind is Add else -1
        result = dict(left)
        for k, v in right.items():
            result[k] = result.get(k, 0) + sign * v
        return {k: v for k, v in result.items() if v}
    if kind is Mult:
        result = {}
        for ka, va in left.items():
            for kb, vb in right.items():
                powers = {}
                for var, e in ka + kb:
                    powers[var] = powers.get(var, 0) + e
                key = tuple(sorted((v, e) for v, e in powers.items() if e))
                result[key] = result.get(key, 0) + va * vb
        return {k: v for k, v in result.items() if v}
    if kind is Div:
        (key, value), = right.items()
        assert key == ()
        return {k: v / value for k, v in left.items()}
    raise AssertionError(term)


def _as_dict(norm):
    result = {}
    for monomial in norm:
        key = tuple((deref(base)._id, e) for base, e in monomial.powers)
        result[key] = Fraction(*monomial.coefficient)
    return result


def _random_term(rng, variables, depth):
    if depth == 0 or rng.random() < 0.3:
        if rng.random() < 0.5:
            return rng.choice(variables)
        return Fraction(rng.randint(-5, 5), rng.randint(1, 3))
    kind = rng.choice([Add, Sub, Mult, Mult, Div, Negate])
    if kind is Negate:
        return Negate(operand=_random_term(rng, variables, depth - 1))
    if kind is Div:
        return Div(left=_random_term(rng, variables, depth - 1),
                   right=rng.choice([2, 3, Fraction(-1, 2)]))
    return kind(left=_random_term(rng, variables, depth - 1),
                right=_random_term(rng, variables, depth - 1))


# ---------------------------------------------------------------- normal_form/2

@pytest.mark.parametrize("seed", range(60))
def test_normal_form_agrees_with_a_polynomial_reference(seed):
    rng = random.Random(seed)
    variables = [Var() for _ in range(3)]
    term = _random_term(rng, variables, 4)
    norm = nf.normal_form(term)
    assert _as_dict(norm) == _reference(term)
    # sorted by the standard order of the power products, no zero coefficient
    for a, b in zip(norm, norm[1:]):
        assert nf.compare_power_products(a.powers, b.powers) < 0
    assert all(m.coefficient != ZERO for m in norm)


def test_the_constant_comes_first_then_variables_in_creation_order():
    x, y = Var(), Var()
    norm = nf.normal_form(Sub(left=Add(left=Mult(left=2, right=y), right=x),
                              right=3))
    assert [m.coefficient for m in norm] == [q(-3), ONE, q(2)]
    assert [m.powers for m in norm] == [[], [(x, 1)], [(y, 1)]]
    assert nf.split(norm) == (norm[1:], q(-3))
    assert nf.split(norm[1:]) == (norm[1:], ZERO)
    assert nf.split([]) == ([], ZERO)


def test_power_products_follow_the_standard_order():
    x, y = Var(), Var()
    order = [[], [(x, 1)], [(x, 1), (y, 1)], [(x, 2)], [(y, -1)], [(y, 1)]]
    for i, a in enumerate(order):
        for j, b in enumerate(order):
            assert nf.compare_power_products(a, b) == (i > j) - (i < j)
    base = nf.NonlinearBase("sin", ([nf.Monomial(ONE, [(x, 1)])],))
    assert nf.compare_bases(x, base) < 0     # a variable before a compound
    exp_base = nf.NonlinearBase("exp", ([], []))
    assert nf.compare_bases(base, exp_base) < 0   # arity before name


def test_numbers_are_exact_and_a_float_is_its_short_convergent():
    assert nf.normal_form(Fraction(1, 3))[0].coefficient == q(1, 3)
    from decimal import Decimal
    assert nf.normal_form(Decimal("2.50"))[0].coefficient == q(5, 2)
    # 1.3.3 reads a float through float_rat: 0.1 is 1/10 (Scryer's own
    # library(clpq) gives the float's exact binary value instead).
    assert nf.normal_form(0.1)[0].coefficient == q(1, 10)
    assert nf.normal_form(0) == []
    assert nf.normal_form(("rat", 3, 6))[0].coefficient == q(1, 2)


def test_monash_constants():
    assert nf.normal_form(("#", "zero")) == []
    pi = nf.normal_form(("#", "pi"))[0].coefficient
    assert abs(Fraction(*pi) - Fraction(3.141592653589793)) < Fraction(1, 10**15)
    assert nf.normal_form(("#", "p"))[0].coefficient == pi
    with pytest.raises(LogicException):
        nf.normal_form(("#", "tau"))


def test_division_by_a_constant_by_a_monomial_and_by_a_sum():
    x, y = Var(), Var()
    assert _as_dict(nf.normal_form(Div(left=x, right=4))) == {((x._id, 1),): Fraction(1, 4)}
    inverse = nf.normal_form(Div(left=3, right=Mult(left=2, right=x)))
    assert [(m.coefficient, m.powers) for m in inverse] == [(q(3, 2), [(x, -1)])]
    quotient = nf.normal_form(Div(left=x, right=Add(left=x, right=y)))
    (monomial,) = quotient
    (base, exponent), = monomial.powers
    assert exponent == 1 and base.name == "/"
    assert _as_dict(base.arguments[0]) == {((x._id, 1),): 1}
    assert _as_dict(base.arguments[1]) == {((x._id, 1),): 1, ((y._id, 1),): 1}


def test_division_by_zero_fails():
    x = Var()
    assert nf.normal_form(Div(left=x, right=0)) is None
    assert nf.post_constraint(ArithEq(left=x, right=Div(left=1, right=Sub(left=x, right=x))),
                              Trail()) is False


def test_x_times_one_over_x_is_one():
    x = Var()
    norm = nf.normal_form(Mult(left=x, right=Div(left=1, right=x)))
    assert [(m.coefficient, m.powers) for m in norm] == [(ONE, [])]


def test_integer_powers_expand_binomially():
    x, y = Var(), Var()
    cube = nf.normal_form(IsoIntPow(left=Add(left=x, right=Add(left=y, right=1)), right=3))
    product = nf.normal_form(Mult(left=Add(left=x, right=Add(left=y, right=1)),
                                  right=Mult(left=Add(left=x, right=Add(left=y, right=1)),
                                             right=Add(left=x, right=Add(left=y, right=1)))))
    assert _as_dict(cube) == _as_dict(product)
    assert len(cube) == 10
    assert _as_dict(nf.normal_form(("^", Mult(left=2, right=x), 3))) == {((x._id, 3),): 8}
    assert nf.normal_form(("^", x, 0))[0].powers == []
    # a negative power of a sum is 1 over the expanded sum
    (monomial,) = nf.normal_form(("^", Add(left=x, right=1), -2))
    (base, _), = monomial.powers
    assert base.name == "/" and len(base.arguments[1]) == 3
    assert nf.normal_form(("^", Sub(left=x, right=x), -1)) is None


def test_constant_non_linear_functions_evaluate():
    assert nf.normal_form(("abs", -3))[0].coefficient == q(3)
    assert nf.normal_form(("min", 2, Fraction(1, 2)))[0].coefficient == q(1, 2)
    assert nf.normal_form(("max", 2, Fraction(1, 2)))[0].coefficient == q(2)
    assert nf.normal_form(("exp", 2, 10))[0].coefficient == q(1024)
    assert nf.normal_form(("pow", 2, -2))[0].coefficient == q(1, 4)
    assert nf.normal_form(("sin", 0)) == []
    assert nf.normal_form(("exp", 4, Fraction(1, 2)))[0].coefficient == q(2)


def test_non_linear_functions_of_variables_are_bases():
    x = Var()
    (monomial,) = nf.normal_form(("sin", Mult(left=2, right=x)))
    (base, exponent), = monomial.powers
    assert (base.name, exponent) == ("sin", 1)
    assert _as_dict(base.arguments[0]) == {((x._id, 1),): 2}
    (monomial,) = nf.normal_form(("exp", 2, x))
    (base, _), = monomial.powers
    assert base.name == "exp" and nf.normal_form_constant(base.arguments[0]) == q(2)


def test_an_expression_of_the_wrong_type_raises_type_error():
    x = Var()
    with pytest.raises(LogicException) as caught:
        nf.normal_form(Add(left=x, right="foo"))
    assert "type_error" in str(caught.value.term) and "expression" in str(caught.value.term)


def test_long_products_and_repairs_recurse_only_to_log_depth():
    # normal_form_multiply_balanced, normal_form_multiply_factor_balanced and
    # repair_balanced halve their count: 4,000 monomials under a recursion
    # limit of 100 frames above this test.
    trail = Trail()
    variables = [Var() for _ in range(4_000)]
    long_form = [nf.Monomial(ONE, [(v, 1)]) for v in variables]
    y = Var()
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 100)
    try:
        product = nf.normal_form_multiply(long_form, nf.normal_form(Add(left=y, right=1)))
        assert len(product) == 8_000
        assert unify(y, 2, trail)
        assert _as_dict(nf.repair(product)) == {((v._id, 1),): 3 for v in variables}
    finally:
        sys.setrecursionlimit(limit)


def test_unary_plus():
    x = Var()
    assert _as_dict(nf.normal_form(UnaryPlus(operand=x))) == {((x._id, 1),): 1}
    assert _as_dict(nf.normal_form(("+", x))) == {((x._id, 1),): 1}


def test_a_long_sum_needs_no_recursion():
    # A left-deep sum of 3,000 variables under a recursion limit of 150
    # frames above this test.  Each step merges into the growing sum, which
    # is quadratic, as nf.pl's normal_form/2 is.
    variables = [Var() for _ in range(3_000)]
    term = variables[0]
    for v in variables[1:]:
        term = Add(left=term, right=v)
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 150)
    try:
        norm = nf.normal_form(term)
        assert len(norm) == 3_000
        trail = Trail()
        assert nf.post_constraint(LtE(left=term, right=1), trail)
    finally:
        sys.setrecursionlimit(limit)


# ---------------------------------------------------------------- normal_form_to_term/2

def test_normal_form_to_term_builds_the_left_associative_sum():
    x, y, z = Var(), Var(), Var()
    norm = nf.normal_form(Sub(left=Add(left=Sub(left=Mult(left=3, right=x), right=y),
                                       right=Mult(left=-2, right=z)),
                              right=Fraction(-1, 2)))
    assert nf.normal_form_to_term(norm) == \
        ("-", ("-", ("+", Fraction(1, 2), ("*", 3, x)), y), ("*", 2, z))
    assert nf.normal_form_to_term([]) == 0
    assert nf.normal_form_to_term(nf.normal_form(Negate(operand=x))) == ("-", x)
    assert nf.normal_form_to_term(nf.normal_form(Mult(left=x, right=Mult(left=y, right=y)))) == \
        ("*", ("^", y, 2), x)
    assert nf.normal_form_to_term(nf.normal_form(Div(left=1, right=x))) == ("/", 1, x)
    assert nf.normal_form_to_term(nf.normal_form(("sin", Add(left=x, right=1)))) == \
        ("sin", ("+", 1, x))


def test_normal_form_to_term_round_trips_through_normal_form():
    rng = random.Random(7)
    variables = [Var() for _ in range(3)]
    for _ in range(40):
        norm = nf.normal_form(_random_term(rng, variables, 4))
        again = nf.normal_form(nf.normal_form_to_term(norm))
        assert _as_dict(again) == _as_dict(norm)


# ---------------------------------------------------------------- repair/2

def test_repair_folds_bound_variables_in():
    trail = Trail()
    x, y = Var(), Var()
    norm = nf.normal_form(Add(left=Mult(left=x, right=y), right=x))
    assert not nf.linear(norm)
    assert unify(x, 2, trail)
    repaired = nf.repair(norm)
    assert nf.linear(repaired)
    assert _as_dict(repaired) == {(): 2, ((y._id, 1),): 2}


def test_repair_of_a_variable_bound_to_another_merges_the_powers():
    trail = Trail()
    x, y = Var(), Var()
    norm = nf.normal_form(Mult(left=x, right=y))
    assert unify(y, x, trail)
    (monomial,) = nf.repair(norm)
    assert monomial.powers == [(deref(x), 2)]


def test_repair_of_a_skeleton_evaluates_it_once_constant():
    trail = Trail()
    x = Var()
    norm = nf.normal_form(Add(left=Div(left=1, right=Add(left=x, right=1)), right=("abs", x)))
    assert unify(x, -3, trail)
    assert _as_dict(nf.repair(norm)) == {(): Fraction(-1, 2) + 3}


def test_a_zero_divisor_inside_a_repaired_quotient_raises():
    # x / (z + 1/(y+1)) with y = -1: the inner quotient fails after its cut,
    # so the outer repair_power_base/2 falls to its last clause, normal_form
    # of the digested skeleton, which raises on its list argument.
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    norm = nf.normal_form(Div(left=x, right=Add(left=z, right=Div(left=1, right=Add(left=y, right=1)))))
    assert unify(y, -1, trail)
    with pytest.raises(LogicException) as caught:
        nf.repair(norm)
    assert "type_error" in str(caught.value.term)


def test_repair_through_a_zero_divisor_fails():
    trail = Trail()
    x, y = Var(), Var()
    norm = nf.normal_form(Div(left=y, right=Add(left=x, right=1)))
    assert unify(x, -1, trail)
    assert nf.repair(norm) is None


# ---------------------------------------------------------------- submit_equal

def test_equal_binds_a_single_variable():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    assert nf.post_constraint(ArithEq(left=x, right=3), trail)
    assert deref(x) == 3
    assert nf.post_constraint(ArithEq(left=Add(left=Mult(left=2, right=y), right=4), right=0), trail)
    assert deref(y) == -2                                   # c11, P = 1
    assert nf.post_constraint(ArithEq(left=Div(left=1, right=z), right=2), trail)
    assert deref(z) == Fraction(1, 2)                       # c11, P = -1


def test_equal_of_a_power_to_zero_binds_zero():
    trail = Trail()
    x = Var()
    assert nf.post_constraint(ArithEq(left=Mult(left=5, right=IsoIntPow(left=x, right=3)), right=0), trail)
    assert deref(x) == 0                                    # b2, b3


def test_equal_of_constants():
    trail = Trail()
    assert nf.post_constraint(ArithEq(left=3, right=3), trail)       # a
    assert nf.post_constraint(ArithEq(left=3, right=4), trail) is False   # b1


def test_equal_of_two_variables_solves():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint((ArithEq(left=Add(left=x, right=y), right=3),
                               ArithEq(left=Add(left=Mult(left=2, right=x), right=Mult(left=2, right=y)), right=6)),
                              trail)
    assert is_var(deref(x)) and is_var(deref(y))
    mark = trail.mark()
    assert nf.post_constraint(ArithEq(left=Add(left=x, right=y), right=4), trail) is False
    trail.undo(mark)
    assert nf.post_constraint(ArithEq(left=Sub(left=x, right=y), right=1), trail)
    assert deref(x) == 2 and deref(y) == 1


def test_equal_through_the_solver_binds_the_implied_variable():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint(ArithEq(left=x, right=Add(left=y, right=1)), trail)
    assert nf.post_constraint(GtE(left=y, right=2), trail)
    assert nf.post_constraint(LtE(left=x, right=3), trail)
    assert deref(x) == 3 and deref(y) == 2


def test_a_non_linear_equation_delays_and_resubmits_once_linear():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint(ArithEq(left=Mult(left=x, right=y), right=6), trail)
    assert is_var(deref(x)) and is_var(deref(y))
    (goal,) = attribute_goal(x)
    assert goal[0] is nf.resubmit_equal
    assert attribute_goal(y) == [goal]
    assert _bind(x, 2, trail)
    assert deref(y) == 3
    assert attribute_goal(y) is None                        # the goal has run


def test_a_non_linear_equation_with_a_bound_factor_is_linear_at_once():
    trail = Trail()
    x, y = Var(), Var()
    assert unify(x, 2, trail)
    assert nf.post_constraint(ArithEq(left=Mult(left=x, right=y), right=6), trail)
    assert deref(y) == 3


def test_a_resubmitted_equation_that_is_false_fails():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint(ArithEq(left=Mult(left=x, right=x), right=Add(left=y, right=4)), trail)
    assert _bind(x, 3, trail)
    assert deref(y) == 5
    trail2 = Trail()
    a, b = Var(), Var()
    assert nf.post_constraint(ArithEq(left=Mult(left=a, right=b), right=6), trail2)
    assert _bind(a, 0, trail2) is False                        # 0 = 6


def test_invertible_functions():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    assert nf.post_constraint(ArithEq(left=("sin", x), right=0), trail)   # b2
    assert deref(x) == 0
    assert nf.post_constraint(ArithEq(left=("exp", 2, y), right=8), trail)   # c12
    assert abs(_value(y) - 3) < Fraction(1, 10**12)
    assert nf.post_constraint(ArithEq(left=("exp", z, Fraction(1, 2)), right=3), trail)
    assert _value(z) == 9
    w = Var()
    assert nf.post_constraint(ArithEq(left=("abs", w), right=2), trail)   # not invertible: delays
    assert is_var(deref(w)) and attribute_goal(w)[0][0] is nf.resubmit_equal


# ---------------------------------------------------------------- inequalities

def test_less_than_of_constants_and_one_variable():
    trail = Trail()
    assert nf.post_constraint(Lt(left=2, right=3), trail)
    assert nf.post_constraint(Lt(left=3, right=3), trail) is False   # trivial failure
    assert nf.post_constraint(LtE(left=3, right=3), trail)
    x = Var()
    assert nf.post_constraint(Lt(left=x, right=0), trail)            # K*X < 0, K > 0
    assert _sup(x, trail) == 0 and state_of(x).upper_strict is True
    y = Var()
    assert nf.post_constraint(Gt(left=Mult(left=2, right=y), right=4), trail)  # ineq_one
    assert _inf(y, trail) == 2 and state_of(y).lower_strict is True
    z = Var()
    assert nf.post_constraint(GtE(left=z, right=0), trail)           # K < 0: X >= 0
    assert _inf(z, trail) == 0 and state_of(z).lower_strict is False


def test_less_than_of_several_variables():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint((GtE(left=x, right=0), GtE(left=y, right=0),
                               Lt(left=Add(left=x, right=y), right=3)), trail)
    assert _sup(Add(left=x, right=y), trail) == 3
    assert nf.post_constraint(GtE(left=x, right=3), trail) is False


def test_a_non_linear_inequality_delays_and_resubmits():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint(Lt(left=Mult(left=x, right=y), right=6), trail)
    assert attribute_goal(x)[0][0] is nf.resubmit_less_than
    assert _bind(x, 2, trail)
    assert _sup(y, trail) == 3 and state_of(deref(y)).upper_strict is True
    trail = Trail()
    a = Var()
    assert nf.post_constraint(LtE(left=Mult(left=a, right=a), right=-1), trail)
    assert attribute_goal(a)[0][0] is nf.resubmit_less_or_equal
    assert _bind(a, 1, trail) is False


def test_not_equal():
    trail = Trail()
    assert nf.post_constraint(ArithNeq(left=3, right=4), trail)
    assert nf.post_constraint(ArithNeq(left=3, right=3), trail) is False
    x = Var()
    assert nf.post_constraint(ArithNeq(left=x, right=3), trail)
    mark = trail.mark()
    assert nf.post_constraint(ArithEq(left=x, right=3), trail) is not None
    trail.undo(mark)
    y = Var()
    assert nf.post_constraint(ArithNeq(left=Mult(left=y, right=y), right=4), trail)
    assert attribute_goal(y)[0][0] is nf.resubmit_not_equal
    assert _bind(y, 2, trail) is False


def test_compare_chain_and_cells():
    trail = Trail()
    x = Var()
    chain = CompareChain(comparisons=[LtE(left=1, right=x), LtE(left=x, right=5)])
    assert nf.post_constraint(chain, trail)
    assert _inf(x, trail) == 1 and _sup(x, trail) == 5
    y = Var()
    assert nf.post_constraint((",", ("=<", 0, y), (">=", 2, y)), trail)
    assert _inf(y, trail) == 0 and _sup(y, trail) == 2
    assert nf.post_constraint(("<=", y, 1), trail)
    assert _sup(y, trail) == 1
    assert nf.post_constraint(("()", ("=:=", y, Fraction(1, 2)),), trail)
    assert deref(y) == Fraction(1, 2)


def test_a_variable_or_a_non_constraint_raises():
    trail = Trail()
    with pytest.raises(LogicException) as caught:
        nf.post_constraint(Var(), trail)
    assert "instantiation_error" in str(caught.value.term)
    with pytest.raises(LogicException) as caught:
        nf.post_constraint(("foo", 1, 2), trail)
    assert "constraint" in str(caught.value.term)


# ---------------------------------------------------------------- disjunction, entailed

def test_a_disjunction_is_retried_when_a_later_constraint_fails():
    trail = Trail()
    x = Var()
    assert nf.post_constraint((",", (";", ("<", x, 0), (">", x, 5)), (">=", x, 1)), trail)
    assert _inf(x, trail) == 5 and state_of(x).lower_strict is True
    trail = Trail()
    y = Var()
    assert nf.post_constraint((";", ("<", y, 0), (">", y, 5)), trail)
    assert _sup(y, trail) == 0                              # the first branch is kept
    assert nf.post_constraint((",", (";", ("<", y, -9), ("<", y, -10)), (">", y, -9)),
                              trail) is False


def test_entailed_leaves_the_store_as_it_was():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint((GtE(left=x, right=1), LtE(left=Add(left=x, right=y), right=3)), trail)
    before = (state_of(x), state_of(y))
    assert nf.entailed(GtE(left=x, right=0), trail)
    assert not nf.entailed(GtE(left=x, right=2), trail)
    assert nf.entailed(LtE(left=y, right=2), trail)
    assert nf.entailed((",", (">=", x, 1), ("=<", y, 2)), trail)
    assert not nf.entailed((",", (">=", x, 1), ("=<", y, 1)), trail)
    assert nf.entailed((";", (">=", x, 5), ("=<", y, 2)), trail)
    assert not nf.entailed(ArithNeq(left=x, right=1), trail)
    assert (state_of(x), state_of(y)) == before


def test_negate():
    x = Var()
    assert nf.negate(Lt(left=x, right=1)) == (">=", x, 1)
    assert nf.negate((",", ("=", x, 1), ("=\\=", x, 2))) == (";", ("=\\=", x, 1), ("=:=", x, 2))
    assert nf.negate((ArithEq(left=x, right=1), Gt(left=x, right=0), LtE(left=x, right=2))) == \
        (";", ("=\\=", x, 1), (";", ("=<", x, 0), (">", x, 2)))
    with pytest.raises(LogicException):
        nf.negate(Var())
    with pytest.raises(LogicException):
        nf.negate(("foo", 1, 2))


def test_negate_of_a_long_conjunction_needs_no_recursion():
    x = Var()
    term = ("<", x, 0)
    for i in range(5_000):
        term = (",", ("<", x, i), term)
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 150)
    try:
        negation = nf.negate(term)
    finally:
        sys.setrecursionlimit(limit)
    assert negation[0] == ";" and negation[1] == (">=", x, 4_999)


# ---------------------------------------------------------------- wait_linear

def test_wait_linear_runs_at_once_on_a_linear_term():
    trail = Trail()
    x = Var()
    seen = []

    def goal(norm, argument, trail):
        seen.append((nf.normal_form_to_term(norm), argument))
        return True

    assert nf.wait_linear(Add(left=x, right=1), goal, "argument", trail)
    assert seen == [(("+", 1, x), "argument")]


def test_wait_linear_delays_until_linear():
    trail = Trail()
    x, y = Var(), Var()
    seen = []

    def goal(norm, argument, trail):
        seen.append(nf.normal_form_to_term(norm))
        return True

    assert nf.wait_linear(Mult(left=x, right=Mult(left=y, right=y)), goal, None, trail)
    assert seen == []
    (pending,) = attribute_goal(x)
    assert pending[0] is nf.wait_linear_retry
    assert _bind(y, 3, trail)
    assert seen == [("*", 9, x)]


def test_wait_linear_redelays_while_still_non_linear():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    seen = []
    assert nf.wait_linear(Mult(left=x, right=Mult(left=y, right=z)),
                          lambda norm, argument, trail: seen.append(norm) or True, None, trail)
    assert _bind(z, 2, trail)
    assert seen == []
    (pending,) = attribute_goal(x)
    assert pending[0] is nf.wait_linear_retry
    assert _bind(y, 5, trail)
    assert _as_dict(seen[0]) == {((x._id, 1),): 10}


def test_maximize_waits_for_a_linear_objective():
    # The goal runs once the objective is linear.  It ends in {Dep =:= Inf},
    # which binds Dep; carrying that to X is itf3.pl's hook (Task 11,
    # test_against_oracle.py test_a_binding_goes_through_the_hook).
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint((LtE(left=0, right=x), LtE(left=x, right=2)), trail)
    assert bv.maximize(Mult(left=x, right=y), trail)
    (pending,) = attribute_goal(x)
    assert pending[0] is nf.wait_linear_retry
    assert pending[1].procedure is bv.minimize_linear
    assert _bind(y, 1, trail)
    assert attribute_goal(x) is None


# ---------------------------------------------------------------- nfq.pl translate_goal//1

def test_translate_goal_of_resubmit_goals():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint(ArithEq(left=Mult(left=x, right=y), right=6), trail)
    assert nf.post_constraint(Lt(left=Mult(left=x, right=x), right=y), trail)
    assert nf.post_constraint(LtE(left=Mult(left=y, right=y), right=4), trail)
    assert nf.post_constraint(ArithNeq(left=Mult(left=x, right=y), right=1), trail)
    goals = collect_nonlinear([x, y], trail, nf.translate_goal)
    relations = sorted(goal[2][1][0] for goal in goals)
    assert relations == ["<", "=", "=<", "=\\="]
    for goal in goals:
        module, constraint = goal[1], goal[2]
        assert goal[0] == ":" and module == "clpq" and constraint[0] == "{}"
        assert constraint[1][2] == 0                        # Z = nf2term([])
    equal = next(goal for goal in goals if goal[2][1][0] == "=")
    assert equal[2][1][1] == ("+", -6, ("*", y, x))


def test_translate_goal_of_wait_linear_retry_reaches_res_and_the_goal():
    trail = Trail()
    x, y = Var(), Var()
    infimum = Var()
    assert bv.inf(Mult(left=x, right=y), infimum, trail)
    (pending,) = attribute_goal(x)
    record = pending[1]
    goals = nf.translate_goal(*pending)
    assert goals == [(":", "clpq", ("{}", ("=", ("*", y, x), record.result))),
                     (":", "clpq", ("infimum_linear", record.result, infimum, (), ()))]
    reachable = project_nonlinear([], [x], trail, nf.translate_goal)
    assert reachable == sorted([x, y, record.result, infimum], key=lambda v: v._id)


def test_translate_is_plugged_into_delayed_goals():
    trail = Trail()
    x, y = Var(), Var()
    assert nf.post_constraint(ArithEq(left=Mult(left=x, right=y), right=6), trail)
    assert collect_nonlinear([x], trail) == \
        [(":", "clpq", ("{}", ("=", ("+", -6, ("*", y, x)), 0)))]


def test_translate_goal_refuses_a_goal_nf_does_not_delay():
    with pytest.raises(ValueError):
        nf.translate_goal(print, None)


def test_the_module_has_its_provenance_header():
    text = pathlib.Path(nf.__file__).read_text()
    assert text.startswith("# Ported from clp(q,r) version 1.3.3, files nf.pl and nfq.pl\n"
                           "# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for\n")
