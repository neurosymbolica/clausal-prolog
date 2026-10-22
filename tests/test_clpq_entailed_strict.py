"""entailed/1 of a strict relation or a disequality the store implies.

The legacy solver keeps ``X < c`` as ``X =< c`` plus a passive disequality
``X =\\= c``; its ``entailed/4`` read only the closed polyhedron, so after
``{X < 5}`` neither ``entailed(X < 5)`` nor, after ``{X =\\= 5}``,
``entailed(X =\\= 5)`` held (SICStus, clp(q,r) 1.3.3 and the port all say
true).  Each case runs on both solvers, so the port pins the expected answer.

The fuzz that found the rest (legacy against the port, random small linear
systems) also found two in_q/3 bugs on legacy, pinned below: a bound on a
variable an equality had eliminated was never read by the simplex
(``{X + Y/2 = -4}, in_q(Y, 1, 2)`` left ``sup(X)`` unbounded), and a bound
that closed a strict one to a point was accepted (``{X > 0}, in_q(X, -1,
0)`` succeeded).

A non-finite float or decimal operand raises ``evaluation_error(undefined)``
(NaN) or ``evaluation_error(float_overflow)`` (an infinity) on the legacy
entry points pinned below, as the port does; legacy raised a bare Python
ValueError / OverflowError, or answered.  A number where in_q/3 or bb_inf/3
takes a variable is checked as the port checks it (in_q(0.5, 0, 1) holds,
bb_inf([0.5], X, I) fails).
"""
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.clpq import holzbaur as _holzbaur
from clausal.logic.clpq import legacy as _legacy
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref, unify

SOLVERS = pytest.mark.parametrize("solver", [_legacy, _holzbaur],
                                  ids=["legacy", "holzbaur"])


def _post(solver, posts, names, trail):
    rel = {"<": solver.q_lt, "=<": solver.q_le, ">": solver.q_gt,
           ">=": solver.q_ge, "=": solver.q_eq, "=\\=": solver.q_ne}
    for op, left, right in posts:
        assert rel[op](_term(left, names), _term(right, names), trail)


def _term(spec, names):
    """A tiny expression language: a str names a variable, a tuple
    ``(op, a, b)`` is an arithmetic cell over specs, anything else a
    number."""
    if isinstance(spec, str):
        return names.setdefault(spec, Var())
    if isinstance(spec, tuple):
        return (spec[0],) + tuple(_term(s, names) for s in spec[1:])
    return spec


def _entailed(solver, posts, query):
    trail, names = Trail(), {}
    _post(solver, posts, names, trail)
    op, left, right = query
    return solver.entailed(op, _term(left, names), _term(right, names), trail)


ENTAILED = [
    # The store's own strict relation and disequality.
    ([("<", "X", 5)], ("<", "X", 5)),
    ([(">", "X", 5)], (">", "X", 5)),
    ([(">", "X", 2)], (">", "X", 2)),
    ([("=\\=", "X", 5)], ("=\\=", "X", 5)),
    ([("=\\=", "X", 5)], ("=\\=", 5, "X")),
    # A strict bound implies the weaker strict and non-strict ones.
    ([("<", "X", 5)], ("<", "X", 6)),
    ([("<", "X", 5)], ("=<", "X", 5)),
    ([("<", "X", 5)], ("=\\=", "X", 5)),
    ([("<", "X", 5)], ("=\\=", "X", 7)),
    ([("<", "X", 5)], (">", 5, "X")),
    # Scaled and shifted forms of the stored relation.
    ([("<", "X", 0)], ("<", ("+", ("*", 3, "X"), 5), 5)),
    ([("<", "X", 5)], ("<", ("*", Fraction(1, 2), "X"), Fraction(5, 2))),
    # Variable-variable forms.
    ([("<", "X", "Y")], ("<", "X", "Y")),
    ([("<", "X", "Y")], (">", "Y", "X")),
    ([("<", "X", "Y")], ("=\\=", "X", "Y")),
    ([("<", "X", "Y"), ("<", "Y", "Z")], ("<", "X", "Z")),
    ([("<", "X", "Y"), ("=<", "Y", "Z")], ("<", "X", "Z")),
    ([("=<", "X", "Y"), ("<", "Y", "Z")], ("<", "X", "Z")),
    # Through an equality.
    ([("<", "X", 5), ("=", "Y", ("+", "X", 1))], ("<", "Y", 6)),
    ([("=\\=", "X", 5), ("=", "Y", ("*", 2, "X"))], ("=\\=", "Y", 10)),
    ([("<", "X", "Y"), ("=", "Z", ("-", "Y", "X"))], (">", "Z", 0)),
    # A strict bound and a bound that meet on a face the strict one
    # removes: X =< 3, X + Y < 5, Y >= 2 leaves X + Y in [?, 5).
    ([("=<", "X", 3), ("<", ("+", "X", "Y"), 5), (">=", "Y", 2)],
     ("<", "X", 3)),
    # The fuzzed cases (legacy answered false).
    ([("<", ("+", ("*", Fraction(-1, 3), "Y"), ("+", ("*", -1, "X"), 2)), 2)],
     ("=\\=", ("+", ("*", Fraction(1, 2), "Y"), ("*", Fraction(3, 2), "X")), 0)),
    ([("=\\=", "X", 5), (">", ("+", ("*", Fraction(1, 2), "X"),
                                  ("*", Fraction(1, 2), "Y")), 2)],
     (">", ("+", ("+", "X", "Y"), 1), 5)),
]

NOT_ENTAILED = [
    ([("=<", "X", 5)], ("<", "X", 5)),
    ([(">=", "X", 5)], (">", "X", 5)),
    ([("<", "X", 5)], ("<", "X", 4)),
    ([("=\\=", "X", 5)], ("<", "X", 5)),
    ([("=\\=", "X", 5)], ("=\\=", "X", 4)),
    ([("<", "X", "Y")], ("<", "X", ("-", "Y", 1))),
    ([("=<", "X", "Y"), ("<", "Y", "Z")], ("<", "Y", "X")),
    # The face X = 3 is not removed: X + Y < 5 with Y >= 1 allows X = 3.
    ([("=<", "X", 3), ("<", ("+", "X", "Y"), 5), (">=", "Y", 1)],
     ("<", "X", 3)),
    # A disequality on another expression does not cover the face.
    ([("=<", "X", 5), ("=\\=", "Y", 5)], ("<", "X", 5)),
    ([("=<", "X", 5), ("=\\=", ("+", "X", "Y"), 5)], ("<", "X", 5)),
]


@SOLVERS
@pytest.mark.parametrize("posts, query", ENTAILED)
def test_entailed(solver, posts, query):
    assert _entailed(solver, posts, query) is True


@SOLVERS
@pytest.mark.parametrize("posts, query", NOT_ENTAILED)
def test_not_entailed(solver, posts, query):
    assert _entailed(solver, posts, query) is False


@SOLVERS
def test_entailed_leaves_the_store_as_it_was(solver):
    trail, x, s = Trail(), Var(), Var()
    assert solver.q_lt(x, 5, trail)
    assert solver.entailed("<", x, 5, trail)
    assert solver.sup(x, s, trail)
    assert deref(s) == 5
    # The strict bound still holds: X = 5 fails, X = 4 succeeds.
    assert not solver.q_eq(x, 5, trail)


# ------------------------------------------- in_q/3 on an eliminated variable

@SOLVERS
def test_in_q_bounds_an_eliminated_variable(solver):
    trail, x, y, high, low = Trail(), Var(), Var(), Var(), Var()
    assert solver.q_eq(("+", x, ("*", Fraction(1, 2), y)), -4, trail)
    assert solver.in_q(y, 1, 6, trail)
    assert solver.in_q(y, 0, 2, trail)
    assert solver.sup(x, high, trail) and deref(high) == Fraction(-9, 2)
    assert solver.inf(x, low, trail) and deref(low) == -5
    assert solver.entailed("=\\=", x, 0, trail)


@SOLVERS
def test_in_q_on_an_eliminated_variable_can_fail(solver):
    trail, x, y = Trail(), Var(), Var()
    assert solver.q_eq(("+", x, ("*", Fraction(1, 2), y)), -4, trail)
    assert solver.in_q(x, -5, -4, trail)
    assert not solver.in_q(y, 3, 5, trail)   # X = -4 - Y/2 =< -11/2


@SOLVERS
@pytest.mark.parametrize("op", ["<", ">"])
def test_in_q_closing_a_strict_bound_fails(solver, op):
    trail, x = Trail(), Var()
    post = solver.q_lt if op == "<" else solver.q_gt
    assert post(x, 0, trail)
    low, high = (0, 1) if op == "<" else (-1, 0)
    assert not solver.in_q(x, low, high, trail)


@SOLVERS
def test_in_q_meeting_a_strict_bound_leaves_the_open_side(solver):
    trail, x, high = Trail(), Var(), Var()
    assert solver.q_lt(x, 1, trail)
    assert solver.in_q(x, 0, 1, trail)
    assert solver.sup(x, high, trail) and deref(high) == 1
    assert solver.entailed("<", x, 1, trail)
    assert not solver.q_eq(x, 1, trail)


# ------------------------------------------------- non-finite float operands

NON_FINITE = pytest.mark.parametrize("value, error", [
    (float("nan"), "undefined"),
    (float("inf"), "float_overflow"),
    (float("-inf"), "float_overflow")], ids=["nan", "inf", "-inf"])


def _evaluation_error(call_):
    with pytest.raises(LogicException) as caught:
        call_()
    term = caught.value.term
    assert term[0] == "error" and term[1][0] == "evaluation_error"
    return str(term[1][1])


ENTRY_POINTS = {
    "entailed": lambda s, t, x, y, v: s.q_le(x, 4, t) and s.entailed("=<", x, v, t),
    "entailed_ground": lambda s, t, x, y, v: s.entailed("=\\=", 1, v, t),
    "q_eq": lambda s, t, x, y, v: s.q_eq(x, v, t),
    "q_ne": lambda s, t, x, y, v: s.q_ne(x, v, t),
    "q_le": lambda s, t, x, y, v: s.q_le(x, v, t),
    "q_lt": lambda s, t, x, y, v: s.q_lt(x, v, t),
    "q_le_ground": lambda s, t, x, y, v: s.q_le(1, v, t),
    "q_le_sum": lambda s, t, x, y, v: s.q_le(("+", x, v), 1, t),
    "in_q_high": lambda s, t, x, y, v: s.in_q(x, 0, v, t),
    "in_q_low": lambda s, t, x, y, v: s.in_q(x, v, None, t),
    "sup": lambda s, t, x, y, v: s.q_le(x, 4, t) and s.sup(("+", x, v), y, t),
    "inf": lambda s, t, x, y, v: s.q_ge(x, 4, t) and s.inf(("+", x, v), y, t),
    "maximize": lambda s, t, x, y, v: s.q_le(x, 4, t) and s.maximize(("+", x, v), y, t),
    "minimize": lambda s, t, x, y, v: s.q_ge(x, 4, t) and s.minimize(("+", x, v), y, t),
    "bb_inf": lambda s, t, x, y, v: s.q_ge(x, 4, t) and s.bb_inf([x], ("+", x, v), y, t),
    "bb_inf_integer_list": lambda s, t, x, y, v: s.q_ge(x, 4, t) and s.bb_inf([v], x, y, t),
    "in_q_target": lambda s, t, x, y, v: s.in_q(v, 0, 1, t),
    "in_q_target_in_list": lambda s, t, x, y, v: s.in_q([x, v], 0, 1, t),
}


@SOLVERS
@NON_FINITE
@pytest.mark.parametrize("entry", sorted(ENTRY_POINTS))
def test_non_finite_float_operand_raises_evaluation_error(solver, value, error,
                                                          entry):
    trail, x, y = Trail(), Var(), Var()
    raised = _evaluation_error(
        lambda: ENTRY_POINTS[entry](solver, trail, x, y, value))
    assert raised.lower() == error


DECIMAL_ENTRY_POINTS = {
    "bind": lambda s, t, x, v: s.q_ge(x, 1, t) and unify(x, v, t),
    "in_q_bound": lambda s, t, x, v: s.in_q(x, v, None, t),
    "in_q_target": lambda s, t, x, v: s.in_q(v, 0, 1, t),
    "q_eq_ground": lambda s, t, x, v: s.q_eq(1, v, t),
    "q_le": lambda s, t, x, v: s.q_le(x, v, t),
    "bb_inf_integer_list": lambda s, t, x, v: s.q_ge(x, 1, t) and s.bb_inf([v], x, Var(), t),
}


@SOLVERS
@pytest.mark.parametrize("value, error", [
    (Decimal("NaN"), "undefined"), (Decimal("Infinity"), "float_overflow")],
    ids=["nan", "inf"])
@pytest.mark.parametrize("entry", sorted(DECIMAL_ENTRY_POINTS))
def test_non_finite_decimal_operand_raises_evaluation_error(solver, value,
                                                            error, entry):
    trail, x = Trail(), Var()
    raised = _evaluation_error(
        lambda: DECIMAL_ENTRY_POINTS[entry](solver, trail, x, value))
    assert raised.lower() == error


# ---------------------------------------- a number where a variable may be

@SOLVERS
@pytest.mark.parametrize("value, expected", [
    (0.5, True), (1.5, False), (-0.25, False), (Decimal("0.5"), True),
    (Fraction(1, 2), True), (2, False)])
def test_in_q_of_a_number_checks_it(solver, value, expected):
    # in_q(0.5, 0, 1) failed on legacy: a float target was never compared.
    assert solver.in_q(value, 0, 1, Trail()) is expected
    assert solver.in_q([Var(), value], 0, 1, Trail()) is expected


@SOLVERS
@pytest.mark.parametrize("value, integral", [
    (0.5, False), (Decimal("0.5"), False), (Fraction(1, 2), False),
    (2, True), (2.0, True), (Fraction(4, 2), True)])
def test_bb_inf_of_a_number_requires_an_integer(solver, value, integral):
    # Legacy ignored a number in the integer list: bb_inf([0.5], X, I)
    # succeeded where the port fails.
    trail, x, low = Trail(), Var(), Var()
    assert solver.q_ge(x, 1, trail)
    assert bool(solver.bb_inf([value], x, low, trail)) is integral
