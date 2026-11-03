"""CLP(Q) on deep terms (clpq DEVIATIONS.md D24, deep terms; D23).

A sum nested 100,000 deep (``lsum(N, X, T) :- ..., lsum(N1, X + 1, T)``,
then ``{Y >= T}``) raised RecursionError from clpfd's cell walk
(``_arith_cells_to_nodes``) before either solver was reached, then from
legacy's ``_ensure_q_for_expr`` and ``_linearize`` and from CLP(R)'s
``_collect_vars_from`` (inf/2 and sup/2 ask it first).  Those walks now run
on an explicit stack past a shallow depth, so the post answers at any depth.

How the tests stay fast and still mean something: the depth is 20,000, and
the ``pinned_limit`` fixture pins Python's recursion limit at 1,000 for the
test, so the walks the fix replaced cannot reach the bottom of these terms
(``test_the_depth_is_past_the_recursive_walk`` checks that against the
recursive walk itself).  Both solvers are called through their modules,
whatever CLAUSAL_CLPQ says; the engine tests run under the solver it says.
"""
import itertools
import random
import sys
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic import clpfd, clpr
from clausal.logic.clpq import holzbaur, legacy
from clausal.logic.exceptions import LogicException, render_error_term, type_error
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.pythonic_ast.nodes import Add, Mult, Negate, Sub

DEPTH = 20_000
SOLVERS = [pytest.param(holzbaur, id="port"), pytest.param(legacy, id="legacy")]
_N = itertools.count()


@pytest.fixture
def pinned_limit():
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        yield
    finally:
        sys.setrecursionlimit(old)


def _left_sum(depth, leaf=0):
    """``((leaf + 1) + 1) + ...`` as cells, what ``lsum/3`` builds."""
    term = leaf
    for _ in range(depth):
        term = ("+", term, 1)
    return term


def _right_sum(depth):
    term = 0
    for _ in range(depth):
        term = ("+", 1, term)
    return term


def _negations(depth, x):
    """``-(-(...(X)))``, *depth* even, as nodes."""
    term = x
    for _ in range(depth):
        term = Negate(operand=term)
    return term


def _raised(call):
    with pytest.raises(LogicException) as caught:
        call()
    return caught.value.term


def test_the_depth_is_past_the_recursive_walk(pinned_limit, monkeypatch):
    # The recursive cell walk the fix keeps for shallow terms, never handed
    # on: at DEPTH under the pinned limit it overflows, as it did before.
    monkeypatch.setattr(clpfd, "_SHALLOW_CELL_WALK", 10 ** 9)
    with pytest.raises(RecursionError):
        clpfd._arith_cells_to_nodes(_left_sum(DEPTH), "(>=)/2")


@pytest.mark.parametrize("solver", SOLVERS)
def test_a_deep_sum_posts_and_answers(pinned_limit, solver):
    t, y, i = Trail(), Var(), Var()
    assert solver.q_ge(y, _left_sum(DEPTH), t)
    assert solver.inf(y, i, t)
    assert deref(i) == DEPTH


@pytest.mark.parametrize("solver", SOLVERS)
def test_a_deep_sum_in_a_block_posts(pinned_limit, solver):
    t, y, i = Trail(), Var(), Var()
    assert solver.clpq_constraint_block(("=<", _right_sum(DEPTH), y), t)
    assert solver.sup(Negate(operand=y), i, t)
    assert deref(i) == -DEPTH


@pytest.mark.parametrize("solver", SOLVERS)
def test_a_deep_objective_answers(pinned_limit, solver):
    t, y, i = Trail(), Var(), Var()
    assert solver.q_ge(y, 0, t)
    assert solver.inf(Add(left=_left_sum(DEPTH), right=y), i, t)
    assert deref(i) == DEPTH
    j = Var()
    assert solver.bb_inf([y], ("+", y, _left_sum(DEPTH)), j, t)
    assert deref(j) == DEPTH
    assert solver.entailed(">=", _left_sum(DEPTH), DEPTH, t)


@pytest.mark.parametrize("solver", SOLVERS)
def test_deep_negations_of_a_variable(pinned_limit, solver):
    t, x, y, i = Trail(), Var(), Var(), Var()
    assert solver.q_eq(y, _negations(DEPTH, x), t)
    assert solver.q_ge(x, 3, t)
    assert solver.inf(y, i, t)
    assert deref(i) == 3


def test_the_variables_of_a_deep_expression_for_inf(pinned_limit):
    # inf/2 and sup/2 ask CLP(R) first: its variable walk recursed.
    xs = [Var() for _ in range(3)]
    term = xs[0]
    for k in range(DEPTH):
        term = Add(left=term, right=xs[k % 3] if k % 1000 == 0 else 1)
    found = []
    clpr._collect_vars_from(term, found)
    assert [v._id for v in found] == [xs[0]._id] + [
        xs[k % 3]._id for k in range(0, DEPTH, 1000)]


# ------------------------------------------------- the same answers as before

def _mixed(rng, xs, depth):
    """A random expression nested *depth* deep: cells and nodes, every
    operator the walks know, integer, rational and Decimal coefficients."""
    t = xs[0]
    for _ in range(depth):
        k = rng.randrange(8)
        x = rng.choice(xs)
        c = rng.choice([1, 2, -3, Fraction(1, 3), Decimal("0.5")])
        if k == 0:
            t = ("+", t, ("*", c, x))
        elif k == 1:
            t = ("-", t, x)
        elif k == 2:
            t = Add(left=t, right=Mult(left=x, right=c))
        elif k == 3:
            t = ("-", t)
        elif k == 4:
            t = ("*", 2, t)
        elif k == 5:
            t = ("/", t, 3)
        elif k == 6:
            t = ("+", c, t)
        else:
            t = Sub(left=t, right=Negate(operand=x))
    return t


def _store(solver, seed):
    """Post three constraints over deep mixed expressions; answer the
    residual, an optimum and how many variables the solver made."""
    rng = random.Random(seed)
    t = Trail()
    xs = [Var() for _ in range(6)]
    y, z = Var(), Var()
    names = {id(v): n for v, n in zip(xs + [y, z], "ABCDEFYZ")}
    first = Var()._id
    assert solver.q_ge(y, _mixed(rng, xs, 300), t)
    assert solver.q_le(_mixed(rng, xs, 300), ("+", z, 7), t)
    assert solver.q_eq(xs[0], _mixed(rng, xs[1:], 200), t)
    r = Var()
    found = solver.inf(("+", y, z), r, t)
    optimum = found, (deref(r) if found else None)
    residual = solver.dump_q(xs + [y, z], t,
                             lambda v: names.get(id(deref(v)), "?"))
    return residual, optimum, Var()._id - first


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("solver", SOLVERS)
def test_the_stack_walk_answers_as_the_recursive_one(solver, seed, monkeypatch):
    # Depth 300 under a raised limit, so the recursive cell walk reaches
    # the bottom too: the walk on the stack (from the root) and the
    # recursive one (never handed on) give the same residual, the same
    # optimum, and make the same number of variables in the same order (a
    # residual names the solver's own variables in the order made, D4/D11).
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(20_000)
    try:
        monkeypatch.setattr(clpfd, "_SHALLOW_CELL_WALK", 10 ** 9)
        recursive = _store(solver, seed)
        monkeypatch.setattr(clpfd, "_SHALLOW_CELL_WALK", -1)
        on_the_stack = _store(solver, seed)
    finally:
        sys.setrecursionlimit(old)
    assert on_the_stack == recursive


def _cell_terms():
    x, y = Var(), Var()
    t = Trail()
    bound = Var()
    unify(bound, ("+", 1, 2), t)
    return [
        ("+", x, 1), ("*", 2, ("-", y)), Add(left=("+", x, bound), right=3),
        ("abs", ("+", 1, 2)), ("abs", x), ("+", ("abs", x), ("min", 1, 2)),
        ("-", ("a", 1), 2), ("+", x, "atom"), ("+", x, [1]),
        ("+", ("rdiv", 1, 2), x), ("sin", ("cos", x)), ("+", ("sin", ("cos", x)), 1),
        Negate(operand=("*", x, y)), ("/", x, 0), 7, x, "atom",
    ]


@pytest.mark.parametrize("strict", [None, "(>=)/2"])
def test_the_cell_walks_agree_term_by_term(strict, monkeypatch):
    # The two walks of _arith_cells_to_nodes, on every kind of argument the
    # recursive one distinguishes: the same node, or the same error.
    def walk(threshold):
        monkeypatch.setattr(clpfd, "_SHALLOW_CELL_WALK", threshold)
        out = []
        for term in terms:
            try:
                out.append(repr(clpfd._arith_cells_to_nodes(term, strict)))
            except LogicException as exc:
                out.append(("raised", repr(exc.term)))
        return out
    terms = _cell_terms()
    assert walk(-1) == walk(10 ** 9)


def _legacy_linearize_recursive(expr):
    """legacy._linearize as it was before it took an explicit stack."""
    from clausal.logic.clpq.legacy import ONE, ZERO, _exact_number
    from clausal.terms import Add as A, Div as D, Mult as M, Negate as N, Sub as S
    expr = deref(expr)
    if isinstance(expr, bool):
        return None
    if isinstance(expr, int):
        return {}, Fraction(expr)
    if isinstance(expr, Fraction):
        return {}, expr
    if isinstance(expr, (Decimal, float)):
        return {}, _exact_number(expr)
    if isinstance(expr, Var):
        return {expr._id: ONE}, ZERO
    if isinstance(expr, (A, S, M, D)):
        lc = _legacy_linearize_recursive(expr.left)
        rc = _legacy_linearize_recursive(expr.right)
        if lc is None or rc is None:
            return None
        (lk, lv), (rk, rv) = lc, rc
        if isinstance(expr, (A, S)):
            sign = 1 if isinstance(expr, A) else -1
            m = dict(lk)
            for v, c in rk.items():
                m[v] = m.get(v, ZERO) + sign * c
            return {v: c for v, c in m.items() if c != ZERO}, lv + sign * rv
        if isinstance(expr, M):
            if not lk:
                return {v: lv * c for v, c in rk.items()}, lv * rv
            if not rk:
                return {v: rv * c for v, c in lk.items()}, lv * rv
            return None
        if rk or rv == ZERO:
            return None
        return {v: c / rv for v, c in lk.items()}, lv / rv
    if isinstance(expr, N):
        inner = _legacy_linearize_recursive(expr.operand)
        if inner is None:
            return None
        return {x: -c for x, c in inner[0].items()}, -inner[1]
    return None


@pytest.mark.parametrize("seed", range(6))
def test_legacy_linear_forms_match_the_recursive_walk(seed):
    # The same coefficients, the same constant and the same variable order
    # (dict order: the order legacy's tableau meets the variables).
    rng = random.Random(seed)
    xs = [Var() for _ in range(5)]
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(20_000)
    try:
        node = clpfd._arith_cells_to_nodes(_mixed(rng, xs, 300), "x/0")
        expected = _legacy_linearize_recursive(node)
    finally:
        sys.setrecursionlimit(old)
    actual = legacy._linearize(node, None)
    assert actual == expected
    assert list(actual[0]) == list(expected[0])
    # A product of two variables is not linear, at any depth.
    assert legacy._linearize(Add(left=node, right=Mult(left=xs[0], right=xs[1])),
                             None) is None


# ------------------------------------------------------- errors, not overflows

def _cyclic(trail):
    x = Var()
    assert unify(x, ("+", 1, x), trail)
    return x


def test_a_cyclic_term_under_legacy_is_not_evaluable():
    # The recursive walk overflowed (RecursionError); legacy now raises what
    # the port raises (D23), with its own context.
    t = Trail()
    term = _raised(lambda: legacy.q_ge(Var(), _cyclic(t), t))
    assert term[1][:2] == ("type_error", "evaluable")
    assert term[1][2] == ("/", "+", 2)


def test_a_cyclic_term_outside_clp_q_has_no_finite_value():
    t = Trail()
    term = _raised(lambda: clpfd._arith_cells_to_nodes(_cyclic(t)))
    assert term[1] == ("resource_error", "finite_memory")


@pytest.mark.parametrize("solver", SOLVERS)
@pytest.mark.parametrize("make", [
    lambda: ("abs", _left_sum(DEPTH)),
    lambda: ("max", _left_sum(DEPTH, Var()), 0),
], ids=["ground", "unbound"])
def test_a_deep_argument_of_abs_is_a_stack_error(pinned_limit, solver, make):
    # abs/1, min/2 and max/2 have no operator node: the walk evaluates them
    # with is/2's evaluator, which recurses; past the stack it raises the
    # error is/2 raises, resource_error(stack).
    t = Trail()
    term = _raised(lambda: solver.q_ge(Var(), make(), t))
    assert term[1] == ("resource_error", "stack")


def test_an_error_on_a_deep_term_renders(pinned_limit):
    text = render_error_term(type_error("evaluable", _left_sum(DEPTH), "x/0"))
    assert isinstance(text, str)


def test_legacy_refuses_a_deep_non_linear_term(pinned_limit):
    t = Trail()
    term = _raised(lambda: legacy.q_ge(Var(), ("^", _left_sum(DEPTH, Var()), 2), t))
    assert term[1][0] == "domain_error"


# --------------------------------------------------------- through the engine

_PROGRAM = """\
:- use_module(library(clpq)).
lsum(0, X, X).
lsum(N, X, T) :- N > 0, N1 is N - 1, lsum(N1, X + 1, T).
deep(N, I) :- lsum(N, 0, T), {Y >= T}, inf(Y, I).
deep_objective(N, I) :- lsum(N, 0, T), {Y >= 0}, inf(T + Y, I).
cyclic_inf(I) :- X = 1 + X, inf(X, I).
cyclic_sup(I) :- X = 1 + X, sup(X, I).
"""


@pytest.fixture(scope="module")
def program(tmp_path_factory):
    from clausal.testing import load_clausal_module
    path = tmp_path_factory.mktemp("deep") / f"_deep_terms_{next(_N)}.clausal"
    path.write_text(_PROGRAM)
    return load_clausal_module(str(path))


@pytest.mark.parametrize("name", ["deep", "deep_objective"])
def test_a_deep_sum_through_the_engine(pinned_limit, program, name):
    from clausal.logic.solve import call
    i = Var()
    answers = [deref(i) for _ in call(name, DEPTH, i, module=program)]
    assert answers == [DEPTH]


@pytest.mark.parametrize("name, context", [("cyclic_inf", "inf"),
                                           ("cyclic_sup", "sup")])
def test_a_cyclic_objective_through_the_engine(program, name, context):
    # D23's case not covered before: inf/2 and sup/2 ask CLP(R) first,
    # whose cell walk overflowed.  Under both switches it is now the
    # error the port's normal_form/2 raises, named by inf/2 or sup/2.
    from clausal.logic.solve import call
    term = _raised(lambda: list(call(name, Var(), module=program)))
    assert term == type_error("evaluable", ("/", "+", 2), f"{context}/2")


# ------------------------------------------------- the units side channel

@pytest.mark.parametrize("solver", SOLVERS)
def test_a_deep_sum_posts_with_the_units_channel_on(pinned_limit, solver,
                                                    monkeypatch):
    # Once a process has built a Quantity, every post scans the tree for
    # units material first; that scan recursed.
    from clausal.logic import _units_flag
    monkeypatch.setattr(_units_flag, "active", True)
    t, y, i = Trail(), Var(), Var()
    assert solver.q_ge(y, _left_sum(DEPTH), t)
    assert solver.inf(y, i, t)
    assert deref(i) == DEPTH


@pytest.mark.parametrize("solver", SOLVERS)
def test_a_deep_sum_of_quantities_is_a_stack_error(pinned_limit, solver):
    # The dimension analysis and the strip recurse: a deep comparison that
    # holds units material raises resource_error(stack).
    from clausal.modules.countries.european_union import euro
    from clausal.terms import Quantity
    t = Trail()
    term = _raised(lambda: solver.q_ge(
        Var(), _left_sum(DEPTH, Quantity(Fraction(1), {euro: 1})), t))
    assert term[1] == ("resource_error", "stack")
