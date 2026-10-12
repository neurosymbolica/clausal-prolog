# tests/clpq_port/test_switch_engine.py
"""Task 14: the port behind the engine (CLAUSAL_CLPQ=holzbaur).

These tests need the package to export the port, so the engine's builtins
and clpfd's dispatch reach it.  They are skipped under the default switch;
test_switch.py runs this file in a subprocess with CLAUSAL_CLPQ=holzbaur.
"""
import itertools
from fractions import Fraction

import pytest

import clausal.logic.clpq as clpq
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk
from clausal.pythonic_ast.nodes import Add, ArithEq, GtE, LtE
from tests._suffix import SEAM

pytestmark = pytest.mark.skipif(clpq.SOLVER != "holzbaur",
                                reason="needs CLAUSAL_CLPQ=holzbaur")

_N = itertools.count()


def _module(tmp_path, body, exports):
    name = f"_switch_engine_{next(_N)}"
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(f"-module({name}, [{', '.join(exports)}])\n"
                    f"-allow_singletons\n{body}\n")
    return _load_module(name, str(path)).__dict__["$module"]


_BLOCKS = """\
post(C) <- clpq.rational(C)
post_then_sup(C, X, S) <- (clpq.rational(C), sup(X, S))
bounded(X, Lo, Hi) <- (in_q(X, 0, 100), X <= 10, X >= 3, inf(X, Lo), sup(X, Hi))
"""


@pytest.fixture
def blocks(tmp_path):
    return _module(tmp_path, _BLOCKS,
                   ["post/1", "post_then_sup/3", "bounded/3"])


def test_the_package_exports_the_port():
    from clausal.logic.clpq import holzbaur
    assert clpq.q_eq is holzbaur.q_eq and clpq.Q_KEY == holzbaur.Q_KEY


def test_a_disjunction_in_a_block_answers_once_per_branch(blocks):
    # Ruling R18 through the clpq.rational builtin, under the engine's
    # driver.  Scryer: {X + Y = 4, (X = 1 ; X = 3)} gives X = 1, Y = 3 ;
    # X = 3, Y = 1 (test_switch.py checks the oracle).
    x, y = Var(), Var()
    block = (ArithEq(left=Add(left=x, right=y), right=4),
             (";", ArithEq(left=x, right=1), ArithEq(left=x, right=3)))
    assert [(walk(x), walk(y)) for _ in call("post", block, module=blocks)] \
        == [(1, 3), (3, 1)]


def test_the_goal_after_a_disjunction_sees_each_branch(blocks):
    # {X >= 0, (X =< 1 ; X >= 3), X =< 5}, sup(X, S): S = 1 ; S = 5.
    x, s = Var(), Var()
    block = (GtE(left=x, right=0),
             (";", LtE(left=x, right=1), GtE(left=x, right=3)),
             LtE(left=x, right=5))
    assert [walk(s) for _ in call("post_then_sup", block, x, s,
                                  module=blocks)] == [1, 5]


def test_compiled_comparisons_post_before_the_next_goal(blocks):
    # `X <= 10` in a seam clause is clpfd's fd_le, which dispatches to q_le
    # at a goal (trail.defer set, trail.hooks_running 0), so the adapter
    # posts it in place (ruling R28c): inf/2 must see it.
    x, lo, hi = Var(), Var(), Var()
    assert [(walk(lo), walk(hi)) for _ in call("bounded", x, lo, hi,
                                               module=blocks)] == [(3, 10)]


# ---------------------------------------------------------------- R29
#
# Fable's integration review (HIGH-1): a comparison compiled inline in a
# seam clause (`X <= 2`, clpfd's fd_le) was not followed by a goal
# boundary, so the delayed goal {X*Y == 4} that X = 2 wakes ran only at
# the next boundary, after the goals between had read Y.  The engine now
# runs woken goals after every inline comparison that can bind (ruling
# R29, a750f58c; docs/coroutining.md "Inside a hook or at a goal").  The
# expected answers are Scryer's on the {} form (test_switch.py,
# test_the_inline_goal_cases_answer_as_the_oracle), which the block-form
# controls below also give.

_WOKEN = """\
var_y(X, Y) <- ({X*Y == 4}, X <= 2, X >= 2, var(Y))
nonvar_y(X, Y) <- ({X*Y == 4}, X <= 2, X >= 2, nonvar(Y))
found_y(X, Y, L) <- ({X*Y == 4}, X <= 2, X >= 2, findall(Y, true, L))
inf_y(X, Y, L) <- ({X*Y == 4}, X <= 2, X >= 2, inf(Y, L))
entailed_y(X, Y) <- ({X*Y == 4, Y >= 1}, X <= 2, X >= 2, entailed(Y >= 2))
bb_inf_y(X, Y, I) <- ({X*Y == 4}, X <= 2, X >= 2, bb_inf([Y], Y, I))
dump_y(X, Y, C) <- ({X*Y == 4}, X <= 2, X >= 2, dump_q([Y], C))
equal_var_y(X, Y) <- ({X*Y == 4, X >= 1}, X == 2, var(Y))
block_var_y(X, Y) <- ({X*Y == 4}, {X <= 2}, {X >= 2}, var(Y))
block_nonvar_y(X, Y) <- ({X*Y == 4}, {X <= 2}, {X >= 2}, nonvar(Y))
block_equal_var_y(X, Y) <- ({X*Y == 4, X >= 1}, {X == 2}, var(Y))
"""
_WOKEN_EXPORTS = ["var_y/2", "nonvar_y/2", "found_y/3", "inf_y/3",
                  "entailed_y/2", "bb_inf_y/3", "dump_y/3", "equal_var_y/2",
                  "block_var_y/2", "block_nonvar_y/2", "block_equal_var_y/2"]


@pytest.fixture(scope="module")
def woken(tmp_path_factory):
    return _module(tmp_path_factory.mktemp("woken"), _WOKEN, _WOKEN_EXPORTS)


def _answers(module, name, arity):
    variables = [Var() for _ in range(arity)]
    return [tuple(walk(v) for v in variables)
            for _ in call(name, *variables, module=module)]


def test_var_after_inline_comparisons_fails(woken):
    assert _answers(woken, "var_y", 2) == []


def test_nonvar_after_inline_comparisons_sees_the_binding(woken):
    assert _answers(woken, "nonvar_y", 2) == [(2, 2)]


def test_findall_after_inline_comparisons_sees_the_binding(woken):
    assert [answer[2] for answer in _answers(woken, "found_y", 3)] == [[2]]


def test_inf_after_inline_comparisons_sees_the_binding(woken):
    assert [answer[2] for answer in _answers(woken, "inf_y", 3)] == [2]


def test_entailed_after_inline_comparisons_sees_the_binding(woken):
    assert _answers(woken, "entailed_y", 2) == [(2, 2)]


def test_bb_inf_after_inline_comparisons_sees_the_binding(woken):
    assert [answer[2] for answer in _answers(woken, "bb_inf_y", 3)] == [2]


def test_dump_q_after_inline_comparisons_sees_the_binding(woken):
    # Y is bound, so dump_q([Y], C) has nothing to project: C = [].
    # Scryer's dump/3 raises uninstantiation_error for a bound target, but
    # dump_q/2 is legacy's API, whose contract leaves a bound target out
    # (legacy's dump_q and the port's residual_strings both do), and the
    # -g printer relies on that; the adapter keeps the legacy contract.
    assert _answers(woken, "dump_y", 3) == [(2, 2, [])]


def test_var_after_an_inline_equation_fails(woken):
    assert _answers(woken, "equal_var_y", 2) == []


def test_block_form_controls_answer_as_the_oracle(woken):
    assert _answers(woken, "block_var_y", 2) == []
    assert _answers(woken, "block_nonvar_y", 2) == [(2, 2)]
    assert _answers(woken, "block_equal_var_y", 2) == []
