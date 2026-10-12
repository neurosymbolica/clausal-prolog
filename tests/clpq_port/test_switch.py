# tests/clpq_port/test_switch.py
"""Task 14: CLAUSAL_CLPQ=holzbaur selects the port behind the legacy API.

The adapter (clausal/logic/clpq/holzbaur.py) is tested here in process,
through its own functions, whatever CLAUSAL_CLPQ says.  What needs the
package to export the port (clpfd's dispatch, the builtins, the CLI) runs
in a subprocess with CLAUSAL_CLPQ=holzbaur: the legacy suites, and
test_switch_engine.py, which is skipped unless the port is selected.
"""
import os
import pathlib
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.clpq import holzbaur as h
from clausal.logic.clpq import legacy
from clausal.logic.clpq.attributes import CLPQ_KEY
from clausal.logic.pending import drain
from clausal.logic.variables import (
    Trail, Var, deref, get_attr, is_var, put_attr, register_attr_hook, unify)
from clausal.pythonic_ast.nodes import (
    Add, ArithEq, CompareChain, Gt, GtE, Lt, LtE, Mult, Sub)

ROOT = pathlib.Path(__file__).resolve().parents[2]

LEGACY_SUITES = ["tests/test_clpq.py", "tests/test_clpq_box_bounded_optimum.py",
                 "tests/test_clpq_undo_on_backtracking.py",
                 "tests/test_dump_q_projection.py", "tests/test_units_clp.py",
                 "tests/test_seam_set_goal_clpq.py", "tests/test_cli.py"]


def _under(solver, argv, timeout=1800):
    env = dict(os.environ, CLAUSAL_CLPQ=solver, PYTHONPATH=str(ROOT))
    return subprocess.run([sys.executable, *argv], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout)


@pytest.mark.parametrize("suite", LEGACY_SUITES)
def test_the_suite_passes_under_the_port(suite):          # Review Focus 4
    r = _under("holzbaur", ["-m", "pytest", "-q", "-p", "no:cacheprovider",
                            suite])
    assert r.returncode == 0, r.stdout[-3000:]


def test_the_engine_tests_pass_under_the_port():
    r = _under("holzbaur", ["-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "tests/clpq_port/test_switch_engine.py"])
    assert r.returncode == 0, r.stdout[-3000:]
    assert "skipped" not in r.stdout.splitlines()[-1], r.stdout[-500:]


def test_the_subprocess_imports_this_tree():
    r = _under("holzbaur", ["-c", "import clausal.logic.clpq as c; "
                                  "print(c.__file__, c.SOLVER, c.Q_KEY)"])
    path, solver, key = r.stdout.split()
    assert pathlib.Path(path).is_relative_to(ROOT)
    assert (solver, key) == ("holzbaur", CLPQ_KEY)


def test_an_unknown_solver_name_stops_the_import():
    r = _under("simplex", ["-c", "import clausal.logic.clpq"])
    assert r.returncode != 0
    assert "CLAUSAL_CLPQ must be legacy or holzbaur, not 'simplex'" in r.stderr


# ---------------------------------------------------------------- sandbox

def test_the_key_each_solver_puts_is_an_engine_key():
    # sandbox.py reads ENGINE_ATTR_KEYS from source: legacy's Q_KEY row and
    # the port's CLPQ_KEY row.  holzbaur.Q_KEY is CLPQ_KEY.
    from clausal.sandbox import _engine_attr_keys
    keys = _engine_attr_keys()
    assert legacy.Q_KEY in keys
    assert h.Q_KEY == CLPQ_KEY and h.Q_KEY in keys


# ---------------------------------------------------------------- posting

def test_a_decimal_keeps_its_scale_through_an_equation():
    # Task 4's carry: legacy's present_number keeps Decimal('2.50') as it
    # is (ruled 2026-09-17); through nf.pl it would be the rational 5/2.
    for solver in (legacy, h):
        t, x = Trail(), Var()
        assert solver.in_q(x, 0, 10, t)
        assert solver.q_eq(x, Decimal("2.50"), t)
        assert type(deref(x)) is Decimal and str(deref(x)) == "2.50", solver
    t, x = Trail(), Var()
    assert h.clpq_constraint_block(ArithEq(left=x, right=Decimal("2.0")), t)
    assert str(deref(x)) == "2.0"


def test_a_non_linear_constraint_waits_as_in_1_3_3():
    # Legacy raises TypeError; nf.pl delays {X*Y = 6} until it is linear.
    t, x, y = Trail(), Var(), Var()
    assert h.q_eq(Mult(left=x, right=y), 6, t)
    assert is_var(deref(x)) and is_var(deref(y))
    assert unify(x, 2, t)
    assert deref(y) == 3


def test_an_fd_variable_is_promoted_with_its_bounds():
    from clausal.logic.clpfd import FD_KEY, in_domain
    t, x = Trail(), Var()
    in_domain(x, 1, 5, t)
    assert h.q_le(x, Fraction(7, 2), t)
    assert get_attr(x, FD_KEY) is not None and get_attr(x, CLPQ_KEY) is not None
    low, high = Var(), Var()
    assert h.inf(x, low, t) and h.sup(x, high, t)
    assert (deref(low), deref(high)) == (1, Fraction(7, 2))


def test_in_q_without_bounds_makes_a_constrained_variable():
    t, x = Trail(), Var()
    assert h.in_q(x, trail=t)
    assert get_attr(x, CLPQ_KEY) is not None
    assert not h.sup(x, Var(), t) and not h.inf(x, Var(), t)


def test_in_q_with_crossed_bounds_fails():
    t, x = Trail(), Var()
    assert not h.in_q(x, 10, 0, t)


# ---------------------------------------------------------------- {A ; B}

def test_a_block_with_a_disjunction_gives_every_answer():
    # Ruling R18: {X + Y = 4, (X = 1 ; X = 3)} answers twice; the second
    # answer still has the conjunct before the `;` (D12's precondition).
    t, x, y = Trail(), Var(), Var()
    block = (ArithEq(left=Add(left=x, right=y), right=4),
             (";", ArithEq(left=x, right=1), ArithEq(left=x, right=3)))
    answers = [(deref(x), deref(y))
               for _ in h.clpq_constraint_answers(block, t)]
    assert answers == [(1, 3), (3, 1)]
    assert is_var(deref(x)) and is_var(deref(y))      # undone at the end


def test_the_bool_block_refuses_a_disjunction():
    t, x = Trail(), Var()
    with pytest.raises(TypeError, match="clpq_constraint_answers"):
        h.clpq_constraint_block((";", LtE(left=x, right=1),
                                 GtE(left=x, right=3)), t)


def test_legacy_s_block_answers_once():
    t, x = Trail(), Var()
    answers = list(legacy.clpq_constraint_answers(
        (GtE(left=x, right=0), LtE(left=x, right=3)), t))
    assert answers == [None]


def test_a_compare_chain_and_a_conjunction_cell_post():
    t, x, y = Trail(), Var(), Var()
    chain = CompareChain(comparisons=[LtE(left=0, right=x),
                                      LtE(left=x, right=10)])
    assert h.clpq_constraint_block([chain, (",", GtE(left=y, right=x),
                                            LtE(left=y, right=3))], t)
    high = Var()
    assert h.sup(x, high, t) and deref(high) == 3


# ---------------------------------------------------------------- results

def test_dump_q_names_targets_with_name_of_and_the_rest_q1_q2():
    t, x = Trail(), Var()
    assert h.q_ne(x, 2, t)
    asked = []

    def name_of(v):
        asked.append(v)
        return "X"
    assert h.dump_q([x], t, name_of) == ["{X = 2 + _Q1}", "{_Q1 =\\= 0}"]
    assert asked and all(v is x for v in asked)


def test_residual_q_is_empty_without_a_store():
    t, x = Trail(), Var()
    assert h.residual_q([x], t, str) == []


def test_maximize_posts_the_optimum_and_binds_what_it_implies():
    t, x, y = Trail(), Var(), Var()
    assert h.q_ge(x, 0, t) and h.q_le(x, 2, t)
    assert h.q_ge(y, 0, t) and h.q_le(y, 3, t)
    best = Var()
    assert h.maximize(x, best, t)
    assert deref(best) == 2 and deref(x) == 2 and is_var(deref(y))


def test_an_unbounded_objective_fails():
    t, x = Trail(), Var()
    assert h.q_ge(x, 0, t)
    assert not h.sup(x, Var(), t)
    assert not h.maximize(x, Var(), t)


def test_bb_inf_binds_inf_and_leaves_the_store():
    t, x = Trail(), Var()
    assert h.q_ge(x, Fraction(3, 2), t) and h.q_le(x, 10, t)
    result = Var()
    assert h.bb_inf([x], x, result, t)
    assert deref(result) == 2 and is_var(deref(x))


class _Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return (None,)


@pytest.mark.parametrize("call", [
    lambda t, x: h.bb_inf([x], x, Var(), t),
    lambda t, x: h.inf(x, Var(), t),
    lambda t, x: h.sup(x, Var(), t),
    lambda t, x: h.entailed(">=", x, 1, t),
    lambda t, x: h.dump_q([x], t),
], ids=["bb_inf", "inf", "sup", "entailed", "dump_q"])
def test_a_goal_queued_before_an_entry_point_stays_queued(call):
    # Task 13c: outside a driver the port's own drain would run a goal
    # queued before it, and its owner would run it again.  The adapter
    # takes the queue first and puts it back.
    t, x = Trail(), Var()
    assert h.q_ge(x, Fraction(3, 2), t) and h.q_le(x, 10, t)
    counter = _Counter()
    t.push_pending(counter)
    assert call(t, x) is not False
    assert counter.calls == 0
    assert t.take_pending() == (counter,)


def test_ordering_takes_an_operator_node():
    t, x, y = Trail(), Var(), Var()
    assert h.q_le(Add(left=x, right=y), 3, t)
    assert h.ordering(Lt(left=y, right=x), t)
    assert h.ordering(Gt(left=x, right=y), t)
    assert h.ordering([x, y], t)


# ---------------------------------------------------------------- R28

_PROBE_KEY = "clpq_test_switch_probe"


def _probe_hook(state, other, trail):
    return state(trail)


register_attr_hook(_PROBE_KEY, _probe_hook)


def _store():
    """{X + Q = 3, W >= Q + 1/2, W =< 20}: X, Q and W in one component."""
    t = Trail()
    x, q, w = Var(), Var(), Var()
    assert h.clpq_constraint_block(
        (ArithEq(left=Add(left=x, right=q), right=3),
         GtE(left=w, right=Add(left=q, right=Fraction(1, 2))),
         LtE(left=w, right=20)), t)
    return t, x, q, w


@pytest.mark.parametrize("driver", [False, True])
def test_a_comparison_from_clpfd_inside_a_hook_is_queued(driver):
    # Ruling R28: a hook body (Z's, first in the unification) posts
    # {Q =< 1} through q_le while X is bound with its CLPQ_KEY hook still
    # to come.  In place it read rows holding X and left Q unbound with
    # sup 1 (DEVIATIONS.md D3, ruling R27); queued, it runs after X's hook
    # bound Q = 1.
    t, x, q, w = _store()
    seen = {}

    def body(trail):
        seen["window"] = h._reads_unhooked_bindings(q)
        before = trail.pending
        ok = h.q_le(q, 1, trail)
        seen["queued"] = trail.pending is not before
        return ok
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    if driver:
        t.defer = True
    assert unify(("f", z, x), ("f", 1, 2), t)
    if driver:
        assert [None for _ in drain(t)][:1] == [None]
        t.defer = False
    assert seen == {"window": True, "queued": True}
    assert deref(q) == 1
    low = Var()
    assert h.inf(w, low, t) and deref(low) == Fraction(3, 2)


def test_a_comparison_from_clpfd_at_a_goal_is_posted_in_place():
    # Under a driver trail.defer is True at every goal.  A compiled
    # comparison is not followed by a goal boundary, so a queued post would
    # be missed by the next goal: the post is made in place when no
    # component it reads holds an unhooked binding.
    t, x, q, w = _store()
    t.defer = True
    assert h.q_le(q, 1, t)
    assert t.pending is None
    high = Var()
    assert h.sup(q, high, t) and deref(high) == 1
    assert h.sync_fd_bounds(w, 2, 5, t) and t.pending is None
    low = Var()
    assert h.inf(w, low, t) and deref(low) == 2


@pytest.mark.parametrize("seed", range(100))
def test_no_component_holds_an_unhooked_binding_at_a_goal(seed):
    # The window check never fires between goals, so a post from clpfd at a
    # goal is made in place: random posts, implied bindings and unifications
    # (16,000 checks over 400 seeds gave none).
    import random
    rng = random.Random(seed)
    t = Trail()
    variables = [Var() for _ in range(5)]
    for _ in range(8):
        kind = rng.random()
        a, b = rng.sample(variables, 2)
        if kind < 0.3:
            h.q_eq(Add(left=Mult(left=rng.randint(-2, 2), right=a), right=b),
                   rng.randint(-3, 3), t)
        elif kind < 0.6:
            h.q_le(Sub(left=a, right=b), rng.randint(-3, 3), t)
        elif kind < 0.8:
            h.q_ge(a, rng.randint(-3, 3), t)
        elif kind < 0.9:
            unify(a, b, t)
        else:
            unify(a, rng.randint(-3, 3), t)
        assert not any(h._reads_unhooked_bindings(v) for v in variables)


def test_sync_fd_bounds_inside_a_hook_is_queued():
    t, x, q, w = _store()
    seen = {}

    def body(trail):
        before = trail.pending
        ok = h.sync_fd_bounds(w, 2, 5, trail)
        seen["queued"] = trail.pending is not before
        return ok
    z = Var()
    put_attr(z, _PROBE_KEY, body, t)
    assert unify(("f", z, x), ("f", 1, 2), t)
    assert seen == {"queued": True}
    low, high = Var(), Var()
    assert h.inf(w, low, t) and h.sup(w, high, t)
    assert (deref(low), deref(high)) == (2, 5)


def test_an_infinite_fd_end_is_left_open():
    t, x, q, w = _store()
    assert h.sync_fd_bounds(q, float("-inf"), 7, t)
    assert not h.inf(q, Var(), t)
    high = Var()
    assert h.sup(q, high, t) and deref(high) == 7


# ---------------------------------------------------------------- FD and Q

_FD_TO_Q = r'''
import json, sys
if sys.argv[1] == "python":         # clpfd's Python twin: no C extension
    sys.modules["clausal.logic._clpfd_propagate"] = None
from fractions import Fraction as F
import clausal.logic.clpq as clpq
from clausal.logic.clpfd import in_domain, zcompare
from clausal.logic.pending import drain
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.terms import Sub

queued = []
sync = clpq.sync_fd_bounds
def spy(variable, lower, upper, trail):
    before = trail.pending
    result = sync(variable, lower, upper, trail)
    queued.append(trail.pending is not before)
    return result
clpq.sync_fd_bounds = spy

def narrowed(driver):
    # zcompare(O, X, Y) over FD X, Y in 0..10; X joins W in CLP(Q).
    # f(O, W) = f(<, 20): O's hook narrows X to 0..9 (clpfd's _narrow, then
    # sync_fd_bounds) while W is bound with its CLP(Q) hook still to come.
    t = Trail()
    o, x, y, w = Var(), Var(), Var(), Var()
    in_domain(x, 0, 10, t)
    in_domain(y, 0, 10, t)
    assert zcompare(o, x, y, t)
    assert clpq.q_ge(x, F(1, 2), t)
    assert clpq.q_le(Sub(left=x, right=w), 0, t)
    if driver:
        t.defer = True
    ok = unify(("f", o, w), ("f", "<", 20), t)
    if driver:
        ok = ok and any(True for _ in drain(t))
        t.defer = False
    s, i = Var(), Var()
    return [ok, str(deref(s)) if clpq.sup(x, s, t) else None,
            str(deref(i)) if clpq.inf(x, i, t) else None]

def promoted():
    t = Trail()
    a, b = Var(), Var()
    in_domain(a, 0, 10, t)
    assert clpq.q_ge(a, F(1, 2), t)
    assert clpq.q_le(Sub(left=a, right=b), 0, t)
    assert clpq.q_le(b, 3, t)
    s = Var()
    return str(deref(s)) if clpq.sup(a, s, t) else None

print(json.dumps([narrowed(False), narrowed(True), promoted(), queued]))
'''


@pytest.mark.parametrize("twin", ["python", "c"])
def test_fd_to_q_bare_and_under_a_driver_against_legacy_and_the_oracle(twin):
    # Ruling R28's interplay check.  The oracle has no clpfd beside clpq,
    # so its programs are the store clpfd leaves, in clpq alone: Scryer
    # answers sup 9 and inf 1/2 for {X >= 1/2, X >= 0, X =< 9, X - W =< 0},
    # W = 20, and sup 3 for {A >= 0, A =< 10, A >= 1/2, A - B =< 0, B =< 3}.
    import json
    from tests.clpq_oracle import oracle_answers
    program = (":- use_module(library(clpq)).\n"
               "narrowed(S, I) :- {X >= 1/2, X >= 0, X =< 9, X - W =< 0},"
               " W = 20, sup(X, S), inf(X, I).\n"
               "promoted(S) :- {A >= 0, A =< 10, A >= 1/2, A - B =< 0,"
               " B =< 3}, sup(A, S).\n")
    assert [a.bindings for a in oracle_answers(
        program, "narrowed(S, I)", ["S", "I"])] == [{"S": 9, "I": Fraction(1, 2)}]
    assert [a.bindings for a in oracle_answers(program, "promoted(S)", ["S"])] \
        == [{"S": 3}]
    answers = {}
    for solver in ("legacy", "holzbaur"):
        r = _under(solver, ["-c", _FD_TO_Q, twin], timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        answers[solver] = json.loads(r.stdout)
    port = answers["holzbaur"]
    assert port[2] == answers["legacy"][2] == "3"
    if twin == "python":
        # The narrowing reaches the port's store (queued inside the hook,
        # run after W's hook), bare and under a driver.
        assert port[:2] == [[True, "9", "1/2"], [True, "9", "1/2"]]
        assert port[3] == [True, True]
        # Legacy-only answer: legacy's sync writes the QVar record and
        # not its tableau, so its sup/2 still says 10.
        assert answers["legacy"][:2] == [[True, "10", "1/2"]] * 2
    else:
        # The C twin narrows without a CLP(Q) sync (c_narrow syncs CLP(R)
        # only), under either solver: the store keeps X =< 10.
        assert port[3] == [] and answers["legacy"][3] == []
        assert port[:2] == answers["legacy"][:2] == [[True, "10", "1/2"]] * 2


# ---------------------------------------------------------------- oracle

def test_the_disjunction_answers_are_the_oracle_s():
    # The answers test_switch_engine.py gets through the engine.
    from tests.clpq_oracle import oracle_answers
    program = (":- use_module(library(clpq)).\n"
               "one(X, Y) :- {X + Y = 4, (X = 1 ; X = 3)}.\n"
               "two(S) :- {X >= 0, (X =< 1 ; X >= 3), X =< 5}, sup(X, S).\n")
    assert [a.bindings for a in oracle_answers(program, "one(X, Y)",
                                               ["X", "Y"])] == [
        {"X": 1, "Y": 3}, {"X": 3, "Y": 1}]
    assert [a.bindings for a in oracle_answers(program, "two(S)", ["S"])] \
        == [{"S": 1}, {"S": 5}]
    t, x = Trail(), Var()
    s = Var()
    block = (GtE(left=x, right=0),
             (";", LtE(left=x, right=1), GtE(left=x, right=3)),
             LtE(left=x, right=5))
    sups = []
    for _ in h.clpq_constraint_answers(block, t):
        mark = t.mark()
        assert h.sup(x, s, t)
        sups.append(deref(s))
        t.undo(mark)
    assert sups == [1, 5]


_CLI_PROGRAM = """\
:- use_module(library(clpq)).
dependent(X, Y) :- {X + Y = 3, 2*X + 2*Y = 6}.
between_1_3(X) :- {X > 1, X < 3}.
not_two(X) :- {X =\\= 2}.
two_bounds(X, Y) :- {X >= 2}, {Y >= 2}.
halves(X, Y) :- {2*X = 1, 3*Y = 1}.
bound_later(X, Y) :- {X + Y = 3, X >= 1}, X = Y.
strict_closed(X, Y) :- {X < Y, X >= 3, Y =< 3}.
optimum(X, Y, S) :- {X >= 0, X =< 2, Y >= 0, Y =< 3, X + 2*Y =< 6},
    sup(X + 3*Y, S).
int_optimum(I) :- {X >= 3/2, X =< 10}, bb_inf([X], X, I).
"""


@pytest.mark.parametrize("goal, variables", [
    ("dependent(X, Y)", ["X", "Y"]),
    ("between_1_3(X)", ["X"]),
    ("not_two(X)", ["X"]),
    ("two_bounds(X, Y)", ["X", "Y"]),
    ("halves(X, Y)", ["X", "Y"]),
    ("bound_later(X, Y)", ["X", "Y"]),
    ("strict_closed(X, Y)", ["X", "Y"]),
    ("optimum(X, Y, S)", ["X", "Y", "S"]),
    ("int_optimum(I)", ["I"]),
])
def test_the_cli_answers_as_the_oracle(goal, variables):
    # Ruling R16: the oracle through the CLI with CLAUSAL_CLPQ=holzbaur.
    from tests.clpq_oracle import (
        clausal_answers, oracle_answers, same_solution_sets)
    oracle = oracle_answers(_CLI_PROGRAM, goal, variables)
    port = clausal_answers(_CLI_PROGRAM, goal, variables, solver="holzbaur")
    ok, why = same_solution_sets(oracle, port)
    assert ok, why


# ---------------------------------------------------------------- R29

_FROZEN = "frozen(X, Y) <- (freeze(X, Y is 1), X == 3, var(Y))\n"


@pytest.mark.xfail(strict=True,
                   reason="engine: no pending boundary after inline goals (R29)")
def test_a_goal_woken_by_an_inline_comparison_runs_before_the_next_goal(
        tmp_path):
    # Not CLP(Q): freeze/2 under either solver.  Scryer runs a woken goal
    # before the next call, so var(Y) fails.
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from tests._suffix import SEAM
    path = tmp_path / f"r29_frozen{SEAM}"
    path.write_text(f"-module(r29_frozen, [frozen/2])\n-allow_singletons\n"
                    f"{_FROZEN}")
    module = _load_module("r29_frozen", str(path)).__dict__["$module"]
    assert list(call("frozen", Var(), Var(), module=module)) == []


def test_the_inline_goal_cases_answer_as_the_oracle():
    # The answers test_switch_engine.py's R29 tests expect, on Scryer's {}.
    from tests.clpq_oracle import oracle_answers
    program = (":- use_module(library(clpq)).\n"
               ":- use_module(library(freeze)).\n"
               "var_y(X, Y) :- {X*Y = 4}, {X =< 2}, {X >= 2}, var(Y).\n"
               "nonvar_y(X, Y) :- {X*Y = 4}, {X =< 2}, {X >= 2}, nonvar(Y).\n"
               "found_y(L) :- {X*Y = 4}, {X =< 2}, {X >= 2}, findall(Y, true, L).\n"
               "inf_y(L) :- {X*Y = 4}, {X =< 2}, {X >= 2}, inf(Y, L).\n"
               "entailed_y(X, Y) :- {X*Y = 4, Y >= 1}, {X =< 2}, {X >= 2},"
               " entailed(Y >= 2).\n"
               "bb_inf_y(I) :- {X*Y = 4}, {X =< 2}, {X >= 2}, bb_inf([Y], Y, I).\n"
               "equal_var_y(X, Y) :- {X*Y = 4, X >= 1}, {X = 2}, var(Y).\n"
               "frozen(Y) :- freeze(X, Y = 1), X = 3, var(Y).\n"
               "dump_y(E) :- {X*Y = 4}, {X =< 2}, {X >= 2},"
               " catch((dump([Y], [y], _), E = none), error(E, _), true).\n")
    def bindings(goal, shown):
        return [a.bindings for a in oracle_answers(program, goal, shown)]
    assert bindings("var_y(X, Y)", ["X", "Y"]) == []
    assert bindings("nonvar_y(X, Y)", ["X", "Y"]) == [{"X": 2, "Y": 2}]
    assert bindings("found_y(L)", ["L"]) == [{"L": "[2]"}]   # a list stays text
    assert bindings("inf_y(L)", ["L"]) == [{"L": 2}]
    assert bindings("entailed_y(X, Y)", ["X", "Y"]) == [{"X": 2, "Y": 2}]
    assert bindings("bb_inf_y(I)", ["I"]) == [{"I": 2}]
    assert bindings("equal_var_y(X, Y)", ["X", "Y"]) == []
    assert bindings("frozen(Y)", ["Y"]) == []
    (error,) = [a.bindings["E"] for a in oracle_answers(program, "dump_y(E)",
                                                         ["E"])]
    assert "uninstantiation_error" in str(error)
