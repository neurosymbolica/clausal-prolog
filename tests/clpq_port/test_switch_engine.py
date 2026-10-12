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
    # with trail.defer set and no goal boundary after it (ruling R28's
    # adapter rule): inf/2 must see it.
    x, lo, hi = Var(), Var(), Var()
    assert [(walk(lo), walk(hi)) for _ in call("bounded", x, lo, hi,
                                               module=blocks)] == [(3, 10)]
