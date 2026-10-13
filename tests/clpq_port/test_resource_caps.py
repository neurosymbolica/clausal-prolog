# tests/clpq_port/test_resource_caps.py
"""DEVIATIONS.md D24, ruling D51: the port's resource caps.

1.3.3 has no limit on three kinds of work: the nodes of a bb_inf search
(a store with no integer point branches for ever), the rows a projection
writes (Fourier-Motzkin is exponential) and the terms of an integer
power's expansion (`(Y + 1)^N` costs about N^3).  The port caps each and
raises `error(resource_error(R), _)` past the cap, never failing or
answering in part.  For each cap: the D24 repro raises within seconds, a
case at its cap answers, the same case one under its cap raises, and
raising the cap lets it through.

The in-process tests call the adapter whatever CLAUSAL_CLPQ says and set
the caps through clausal.logic.clpq.limits.  The flags and catch/3 run in
a `clausal` subprocess under CLAUSAL_CLPQ=holzbaur, where the flags exist.
"""
import os
import pathlib
import signal
import subprocess
import sys

import pytest

import clausal.logic.clpq as clpq
from clausal.logic.clpq import holzbaur as h
from clausal.logic.clpq import limits
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref, is_var, walk
from clausal.pythonic_ast.nodes import Add, ArithEq, IsoIntPow, Mult

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def caps():
    """limits.set_limit, every cap put back after the test."""
    saved = {resource: limits.limit(resource) for resource in limits.DEFAULTS}
    yield limits.set_limit
    for resource, value in saved.items():
        limits.set_limit(resource, value)


@pytest.fixture
def used(monkeypatch):
    """The most of each resource a test used: resource -> count."""
    most = {}
    check = limits.check

    def recording(resource, count, what):
        most[resource] = max(most.get(resource, 0), count)
        return check(resource, count, what)
    monkeypatch.setattr(limits, "check", recording)
    return most


class _Hang(BaseException):
    pass


def _within(seconds, call):
    """*call*, or _Hang after *seconds*."""
    def alarm(*_):
        raise _Hang()
    previous = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(seconds)
    try:
        return call()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _raised(call):
    with pytest.raises(LogicException) as caught:
        call()
    return caught.value.term


def _is_resource_error(term, resource):
    """`error(resource_error(R), _)`, Scryer's shape: the context is a
    variable."""
    return (type(term) is tuple and len(term) == 3 and term[0] == "error"
            and term[1] == ("resource_error", resource)
            and type(deref(term[2])).__name__.endswith("Var"))


def _sum(coefficients, variables):
    result = None
    for coefficient, variable in zip(coefficients, variables):
        if coefficient:
            term = Mult(left=coefficient, right=variable)
            result = term if result is None else Add(left=result, right=term)
    return result


# ---------------------------------------------------------------- nodes

def _no_integer_point():
    """D24 High 1: `{X >= 0, Y >= 0, 2*X - 2*Y =:= 1}, bb_inf([X, Y], X, I)`."""
    trail, x, y = Trail(), Var(), Var()
    assert h.q_ge(x, 0, trail) and h.q_ge(y, 0, trail)
    assert h.q_eq(_sum([2, -2], [x, y]), 1, trail)
    return h.bb_inf([x, y], x, Var(), trail)


def _integer_optimum():
    """min X + Y with 3X + 5Y >= 17 and 7X - 4Y =< 9 over the integers:
    a search of a few nodes; the infimum."""
    trail, x, y, infimum = Trail(), Var(), Var(), Var()
    assert h.q_ge(x, 0, trail) and h.q_ge(y, 0, trail)
    assert h.q_ge(_sum([3, 5], [x, y]), 17, trail)
    assert h.q_le(_sum([7, -4], [x, y]), 9, trail)
    assert h.bb_inf([x, y], _sum([1, 1], [x, y]), infimum, trail)
    return deref(infimum)


def test_bb_inf_without_an_integer_point_raises_clpq_nodes(caps):
    caps("clpq_nodes", 2000)
    term = _within(60, lambda: _raised(_no_integer_point))
    assert _is_resource_error(term, "clpq_nodes")


def test_bb_inf_without_an_integer_point_raises_at_the_default_cap():
    assert limits.limit("clpq_nodes") == limits.DEFAULTS["clpq_nodes"]
    term = _within(120, lambda: _raised(_no_integer_point))
    assert _is_resource_error(term, "clpq_nodes")


def test_bb_inf_answers_at_its_node_cap_and_raises_under_it(caps, used):
    expected = _integer_optimum()
    nodes = used["clpq_nodes"]
    assert nodes > 2                    # the search branches
    caps("clpq_nodes", nodes)
    assert _integer_optimum() == expected
    caps("clpq_nodes", nodes - 1)
    assert _is_resource_error(_raised(_integer_optimum), "clpq_nodes")
    caps("clpq_nodes", nodes)           # raising the cap lets it through
    assert _integer_optimum() == expected


# ---------------------------------------------------------------- projection

#: D24 Medium 3, the security review's probe `proj.py 101 5 1`: 15 random
#: `=<` constraints on 5 variables (random.Random(101)), projected onto
#: the first two.  1.3.3's answer has 13 constraints, after 7 to 13 s.
_SEED_101 = [
    ([1, 3, -2, 1, -1], 8), ([-3, 2, 1, -2, 1], 4), ([-1, 0, 2, 3, -2], 6),
    ([0, -3, -1, -2, -2], 2), ([0, 3, 1, -1, -2], 8), ([3, -1, -2, 2, 3], 7),
    ([0, -2, -3, 0, 0], 5), ([-2, -3, 2, 3, 1], 6), ([2, 3, -1, 0, 3], 7),
    ([-2, 0, -3, 0, 2], 7), ([-3, 3, 0, -2, 1], 2), ([-1, 3, -3, -1, 2], 6),
    ([-3, -1, 1, 3, -2], 1), ([0, -2, -1, -3, 3], 3), ([0, 2, 2, 3, -1], 8)]

#: A smaller projection: 6 of those constraints on 4 variables.
_SMALL = [(row[:4], bound) for row, bound in _SEED_101[:6]]


def _project(rows):
    trail = Trail()
    variables = [Var() for _ in rows[0][0]]
    for coefficients, bound in rows:
        assert h.q_le(_sum(coefficients, variables), bound, trail)
    names = {variables[0]._id: "X1", variables[1]._id: "X2"}
    return h.dump_q(variables[:2], trail, lambda v: names[v._id])


def test_the_d24_projection_raises_clpq_projection_at_the_default_cap():
    assert limits.limit("clpq_projection") \
        == limits.DEFAULTS["clpq_projection"]
    term = _within(60, lambda: _raised(lambda: _project(_SEED_101)))
    assert _is_resource_error(term, "clpq_projection")


def test_a_projection_answers_at_its_cap_and_raises_under_it(caps, used):
    expected = _project(_SMALL)
    assert expected
    rows = used["clpq_projection"]
    caps("clpq_projection", rows)
    assert _project(_SMALL) == expected
    caps("clpq_projection", rows - 1)
    assert _is_resource_error(_raised(lambda: _project(_SMALL)),
                              "clpq_projection")
    caps("clpq_projection", rows)       # raising the cap lets it through
    assert _project(_SMALL) == expected


def test_derived_constraints_are_charged_before_they_are_made(
        caps, monkeypatch):
    # Fourier-Motzkin charges an elimination's cross product before it
    # makes a row of it: a cap that the first charge passes raises from
    # that charge, not from a later pivot.
    charges = []
    charge = limits.charge_projection

    def recording(rows):
        charges.append((sys._getframe(1).f_code.co_name, rows,
                        (limits.projection_rows or 0) + rows))
        return charge(rows)
    monkeypatch.setattr(limits, "charge_projection", recording)
    _project(_SMALL)
    first = next(entry for entry in charges
                 if entry[0] == "fourier_motzkin_eliminate_internal"
                 and entry[1] > 0)
    caps("clpq_projection", first[2] - 1)
    with pytest.raises(LogicException) as caught:
        _project(_SMALL)
    assert _is_resource_error(caught.value.term, "clpq_projection")
    names = []
    frame = caught.tb
    while frame is not None:
        names.append(frame.tb_frame.f_code.co_name)
        frame = frame.tb_next
    assert names[-4:-1] == ["fourier_motzkin_eliminate_internal",
                            "recording", "charge_projection"], names


def test_the_projection_counter_stops_with_the_projection(caps):
    caps("clpq_projection", 1)
    _raised(lambda: _project(_SMALL))
    assert limits.projection_rows is None
    # Pivots outside a projection are not counted.
    trail, x, y = Trail(), Var(), Var()
    assert h.q_le(_sum([1, 1], [x, y]), 4, trail)
    assert h.q_ge(y, 0, trail)
    value = Var()
    assert h.sup(x, value, trail) and deref(value) == 4


# ---------------------------------------------------------------- power

def _power(base, exponent):
    trail, x = Trail(), Var()
    return h.q_eq(x, IsoIntPow(left=base, right=exponent), trail)


def test_a_huge_power_raises_clpq_power_at_once():
    # D24 Medium 4: {X = (Y + 1)^(10^7)} did not finish.
    term = _within(10, lambda: _raised(lambda: _power(Add(left=Var(), right=1),
                                                      10 ** 7)))
    assert _is_resource_error(term, "clpq_power")


def test_a_power_answers_at_its_cap_and_raises_under_it(caps):
    # (Y + 1)^N has N + 1 terms.
    caps("clpq_power", 201)
    assert _power(Add(left=Var(), right=1), 200)
    caps("clpq_power", 200)
    assert _is_resource_error(
        _raised(lambda: _power(Add(left=Var(), right=1), 200)), "clpq_power")
    # A negative exponent expands the same power first.
    assert _is_resource_error(
        _raised(lambda: _power(Add(left=Var(), right=1), -200)), "clpq_power")
    caps("clpq_power", 201)             # raising the cap lets it through
    assert _power(Add(left=Var(), right=1), -200)


def test_the_power_count_is_the_terms_of_the_expansion(caps):
    # (Y + Z + W)^N has binomial(N + 2, 2) terms: 66 at N = 10.
    def cube_sum():
        return _power(Add(left=Add(left=Var(), right=Var()), right=Var()), 10)
    caps("clpq_power", 66)
    assert cube_sum()
    caps("clpq_power", 65)
    assert _is_resource_error(_raised(cube_sum), "clpq_power")


def test_a_power_of_one_term_is_not_counted(caps):
    # A monomial's power is one term, whatever the exponent.
    caps("clpq_power", 1)
    assert _power(Mult(left=2, right=Var()), 50)


def test_set_limit_refuses_what_is_not_a_positive_int(caps):
    for value in (0, -1, 1.5, True, "10"):
        with pytest.raises(ValueError):
            caps("clpq_nodes", value)


# ---------------------------------------------------------------- Prolog

_PROGRAM = """\
:- module(caps_probe, [noint/1, project/1, big/2, post/1, caught/2]).
:- use_module(library(clpq)).
noint(I) :- {X >= 0, Y >= 0, 2*X - 2*Y =:= 1}, bb_inf([X, Y], X, I).
big(X1, X2) :-
    {X1 + 3*X2 - 2*X3 + X4 =< 8, -3*X1 + 2*X2 + X3 - 2*X4 =< 4,
     -X1 + 2*X3 + 3*X4 =< 6, -3*X2 - X3 - 2*X4 =< 2,
     3*X2 + X3 - X4 =< 8, 3*X1 - X2 - 2*X3 + 2*X4 =< 7}.
project(C) :- big(X1, X2), dump_q([X1, X2], C).
post(C) :- 'clpq.rational'(C).
caught(G, R) :- catch(G, error(resource_error(R), _), true).
"""


def _program(directory):
    path = directory / "caps_probe.pl"
    path.write_text(_PROGRAM)
    return path


def _clausal(tmp_path, goal, solver="holzbaur"):
    env = dict(os.environ, CLAUSAL_CLPQ=solver, CLAUSAL_PL_FRONTEND="native",
               PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "clausal", "-g", goal,
         str(_program(tmp_path))],
        cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, timeout=600)


_HOLZBAUR = pytest.mark.skipif(clpq.SOLVER != "holzbaur",
                               reason="needs CLAUSAL_CLPQ=holzbaur")


@pytest.fixture
def probe(tmp_path, monkeypatch, caps):
    """The program loaded in this process (the native .pl front end)."""
    from clausal.import_hook import _load_module
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    path = _program(tmp_path)
    return _load_module("caps_probe", str(path)).__dict__["$module"]


def _caught(module, goal):
    """R where catch(Goal, error(resource_error(R), _), true) caught one;
    None where Goal answered."""
    from clausal.logic.solve import call
    resource = Var()
    answers = [walk(resource) for _ in call("caught", goal, resource,
                                             module=module)]
    assert len(answers) == 1
    return None if is_var(answers[0]) else answers[0]


@_HOLZBAUR
def test_catch_takes_each_resource_error(probe, caps):
    caps("clpq_nodes", 500)
    caps("clpq_projection", 10)
    caps("clpq_power", 10)
    x, y = Var(), Var()
    power = ArithEq(left=x, right=IsoIntPow(left=Add(left=y, right=1),
                                            right=10))
    assert _caught(probe, ("noint", Var())) == "clpq_nodes"
    assert _caught(probe, ("project", Var())) == "clpq_projection"
    assert _caught(probe, ("post", power)) == "clpq_power"
    x, y = Var(), Var()
    assert _caught(probe, ("post", ArithEq(
        left=x, right=IsoIntPow(left=Add(left=y, right=1), right=9)))) \
        is None


@_HOLZBAUR
def test_set_prolog_flag_sets_each_cap(probe, caps):
    from clausal.logic.solve import call
    for flag, resource in (("clpq_max_nodes", "clpq_nodes"),
                           ("clpq_max_projection", "clpq_projection"),
                           ("clpq_max_power", "clpq_power")):
        value = Var()
        assert [walk(value) for _ in call(
            "current_prolog_flag", flag, value, module=probe)] \
            == [limits.limit(resource)]
        assert len(list(call("set_prolog_flag", flag, 77, module=probe))) == 1
        assert limits.limit(resource) == 77


def test_the_flags_read_and_set_each_cap(tmp_path):
    result = _clausal(
        tmp_path,
        "current_prolog_flag(clpq_max_nodes, A), "
        "current_prolog_flag(clpq_max_projection, B), "
        "current_prolog_flag(clpq_max_power, C), "
        "set_prolog_flag(clpq_max_power, 7), "
        "current_prolog_flag(clpq_max_power, D)")
    assert result.stdout.strip() == (
        f"A = {limits.DEFAULTS['clpq_nodes']}, "
        f"B = {limits.DEFAULTS['clpq_projection']}, "
        f"C = {limits.DEFAULTS['clpq_power']}, D = 7."), result.stderr


def test_catch_takes_the_errors_in_a_program(tmp_path):
    result = _clausal(
        tmp_path,
        "set_prolog_flag(clpq_max_nodes, 500), "
        "set_prolog_flag(clpq_max_projection, 10), "
        "caught(noint(_), R1), caught(project(_), R2)")
    assert result.stdout.strip() == (
        "R1 = clpq_nodes, R2 = clpq_projection."), result.stderr


def test_a_cap_flag_takes_a_positive_integer_only(tmp_path):
    result = _clausal(
        tmp_path,
        "catch(set_prolog_flag(clpq_max_nodes, 0), E1, true), "
        "catch(set_prolog_flag(clpq_max_nodes, ten), E2, true)")
    assert result.stdout.strip() == (
        "E1 = error(domain_error(flag_value,clpq_max_nodes+0),"
        "set_prolog_flag/2), "
        "E2 = error(domain_error(flag_value,clpq_max_nodes+ten),"
        "set_prolog_flag/2)."), result.stderr


def test_the_answer_printer_reports_the_projection_cap(tmp_path):
    # The -g printer projects every answer: past the cap it reports the
    # error and prints no answer, partial or whole.
    whole = _clausal(tmp_path, "big(X1, X2)")
    assert whole.returncode == 0 and "{" in whole.stdout, whole.stderr
    result = _clausal(
        tmp_path, "set_prolog_flag(clpq_max_projection, 10), big(X1, X2)")
    assert result.returncode != 0
    assert "resource_error(clpq_projection)" in result.stderr
    assert "{" not in result.stdout


def test_the_legacy_switch_has_no_cap_flags(tmp_path):
    result = _clausal(
        tmp_path, "catch(current_prolog_flag(clpq_max_nodes, _), E, true)",
        solver="legacy")
    assert result.stdout.strip() == (
        "E = error(domain_error(prolog_flag,clpq_max_nodes),"
        "current_prolog_flag/2)."), result.stderr
