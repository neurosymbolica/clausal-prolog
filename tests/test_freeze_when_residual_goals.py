"""A pending freeze/2 or when/2 keeps its goal TERM (operator ruling
2026-10-26), read back with ``clausal.logic.coroutining.pending_goals`` (the
answer printers' helper) and ``frozen/2``.

The command-line and Scryer rows are in
``tests/iso/test_freeze_when_residuals_scryer.py``; these are the Python
entry and the seam surface, plus the edges the printer rows do not reach:
a when/2 whose goal ran through one branch of a disjunction, a ground/1
re-check, a nested special form and a call/1 of a variable goal.
"""
from __future__ import annotations

import itertools
import re

import pytest

from clausal.import_hook import _load_module
from clausal.logic.coroutining import pending_goals, residual_of
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Trail, Var
from clausal.terms import term_writeq

from tests._suffix import SEAM

_N = itertools.count()

PL = """\
g. h.
p1(X) :- freeze(X, g).
p2(X) :- freeze(X, g), freeze(X, h).
p3(X, Y) :- when((nonvar(X) ; nonvar(Y)), g).
p4(X, Y) :- when((nonvar(X) ; nonvar(Y)), g), Y = 1.
p5(X, Y) :- when(ground(f(X, Y)), g), X = 1.
p6(X, G) :- freeze(X, G).
p7(X, L) :- freeze(X, (findall(Z, member(Z, [1]), L), \\+ h)).
p8(X) :- freeze(X, (g -> h ; true)).
p9(X, Y) :- when(((nonvar(X) ; nonvar(Y)), ground(Y)), g), X = 1.
"""


def _module(tmp_path, text, suffix):
    name = f"_fz_residual_{next(_N)}"
    p = tmp_path / f"{name}{suffix}"
    p.write_text(text)
    return _load_module(name, str(p))


@pytest.fixture
def mod(tmp_path):
    return _module(tmp_path, PL, ".pl")


def _goals(mod, name, *args):
    out = []
    for _ in solve((name, *args), mod):
        free = [a for a in args if isinstance(_deref_walk(a), Var)]
        out.append([term_writeq(_deref_walk(g)) for g in pending_goals(free)])
    return out


def test_freeze_goals(mod):
    x = Var()
    assert _goals(mod, "p1", x) == [[f"freeze({term_writeq(x)},g)"]]
    x = Var()
    assert _goals(mod, "p2", x) == [[f"freeze({term_writeq(x)},(g,h))"]]


def test_a_disjunction_prints_once_and_is_gone_once_it_ran(mod):
    x, y = Var(), Var()
    [[only]] = _goals(mod, "p3", x, y)
    assert only == f"when((nonvar({term_writeq(x)});nonvar({term_writeq(y)})),g)"
    x, y = Var(), Var()
    assert _goals(mod, "p4", x, y) == [[]]


def test_a_ground_recheck_keeps_the_whole_condition(mod):
    x, y = Var(), Var()
    assert _goals(mod, "p5", x, y) == [[f"when(ground(f(1,{term_writeq(y)})),g)"]]


def test_a_conjunction_of_a_fired_disjunction_is_still_pending(mod):
    x, y = Var(), Var()
    assert _goals(mod, "p9", x, y) == [
        [f"when(((nonvar(1);nonvar({term_writeq(y)})),ground({term_writeq(y)})),g)"]]


def test_a_variable_goal_is_the_term_it_is_bound_to(mod):
    x = Var()
    assert _goals(mod, "p6", x, ("write", "hi")) == [
        [f"freeze({term_writeq(x)},write(hi))"]]


def test_goal_positions_are_goals(mod):
    x, l = Var(), Var()
    [[g]] = _goals(mod, "p7", x, l)
    z = re.search(r"findall\((_\w+),", g).group(1)
    assert g == (f"freeze({term_writeq(x)},(findall({z},member({z},[1]),"
                 f"{term_writeq(l)}),\\+h))")
    x = Var()
    assert _goals(mod, "p8", x) == [[f"freeze({term_writeq(x)},(g->h;true))"]]


SEAM_PROGRAM = """\
s(X) <- freeze(X, write('hi'))
s_or(X, Y) <- when(nonvar(X) or nonvar(Y), write('hi'))
s_and(X, Y) <- when((nonvar(X), nonvar(Y)), write('hi'))
s_ground(X, Y) <- when(ground([X, Y]), write('hi'))
s_nonvar(X) <- when(nonvar(X), write('hi'))
s_escape(X) <- freeze(X, ++print('SIDE EFFECT', X))
s_escape_arg(X, L) <- freeze(X, L is ++len([X]))
"""


def test_the_seam_surface(tmp_path):
    m = _module(tmp_path, SEAM_PROGRAM, SEAM)
    x, y = Var(), Var()
    X, Y = term_writeq(x), term_writeq(y)
    assert _goals(m, "s", x) == [[f"freeze({X},write(hi))"]]
    assert _goals(m, "s_or", x, y) == [[f"when((nonvar({X});nonvar({Y})),write(hi))"]]
    assert _goals(m, "s_and", x, y) == [[f"when((nonvar({X}),nonvar({Y})),write(hi))"]]
    assert _goals(m, "s_ground", x, y) == [[f"when(ground([{X},{Y}]),write(hi))"]]
    assert _goals(m, "s_nonvar", x) == [[f"when(nonvar({X}),write(hi))"]]


def test_printing_a_residual_runs_no_python_escape(tmp_path, capsys):
    """A Python escape in a delayed goal is shown as ``++Vars`` (the
    variables it reads), never evaluated: printing must not run code."""
    m = _module(tmp_path, SEAM_PROGRAM, SEAM)
    x, l = Var(), Var()
    X = term_writeq(x)
    assert _goals(m, "s_escape", x) == [[f"freeze({X},++([{X}]))"]]
    assert _goals(m, "s_escape_arg", x, l) == [
        [f"freeze({X},{term_writeq(l)} is ++([{X}]))"]]
    assert "SIDE EFFECT" not in capsys.readouterr().out


def test_a_thunk_built_outside_the_engine_answers_nothing():
    def thunk():
        yield None
    assert residual_of(thunk) is None
    from clausal.logic.coroutining import _freeze_var
    v, t = Var(), Trail()
    _freeze_var(v, thunk, t)
    assert pending_goals([v]) == []


def test_frozen_2_from_python(mod):
    x, g = Var(), Var()
    out = [term_writeq(_deref_walk(g))
           for _ in solve((",", ("p2", x), ("frozen", x, g)), mod)]
    assert out == [f"freeze({term_writeq(x)},(g,h))"]
