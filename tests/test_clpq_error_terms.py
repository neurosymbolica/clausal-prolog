"""CLP(Q) errors are ISO error terms, and the legacy solver answers as the
port does where it used to raise a Python exception.

Two groups:

- ``entailed/1`` (and ``clpq.entailed/1``) with an argument that is not a
  relation: an unbound argument raises ``instantiation_error`` and any other
  non-relation ``type_error(constraint, T)``, as nf.pl's negate/2 does in
  clp(q,r) 1.3.3 (and SICStus).  It used to fail silently on both solvers.
- The legacy solver raised bare Python exceptions (TypeError, ValueError)
  that ``catch/3`` saw as Python objects.  Each case now answers what the
  port (``CLAUSAL_CLPQ=holzbaur``) answers: a non-linear relation is not
  entailed, a zero divisor fails a post and an optimum and makes
  ``entailed`` hold (its negation cannot be posted), and in_q/3's bounds,
  a float binding and a block node that is no constraint raise the port's
  error terms.

The in-process tests run under the solver CLAUSAL_CLPQ selects (run the
file under both); ``test_clausal_program_under_each_solver`` runs the
Clausal Prolog program under each solver in a subprocess, and the Python
API tests call both solvers' modules directly.
"""
import os
import pathlib
import subprocess
import sys
from fractions import Fraction

import pytest

from clausal.logic.clpq import holzbaur as _holzbaur
from clausal.logic.clpq import legacy as _legacy
from clausal.logic.exceptions import (
    LogicException, instantiation_error, type_error)
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.pythonic_ast.nodes import LtE
from clausal.testing import load_clausal_module
from tests._suffix import SEAM

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: case name -> the outcome expected, as Clausal Prolog source: true, false
#: or caught(Error).  outcome/2 below computes each.
EXPECTED = {
    # entailed/1 of a term that is not a relation.
    "entailed_unbound": "caught(error(instantiation_error, _))",
    "entailed_unbound_built_at_run_time":
        "caught(error(instantiation_error, _))",
    "entailed_atom": "caught(error(type_error(constraint, foo), _))",
    "entailed_number": "caught(error(type_error(constraint, 1), _))",
    "entailed_compound": "caught(error(type_error(constraint, f(a, b)), _))",
    "entailed_three_argument_compound":
        "caught(error(type_error(constraint, f(a, b, c)), _))",
    "entailed_term_inequality":
        "caught(error(type_error(constraint, _ \\= 2), _))",
    "entailed_structural_equality":
        "caught(error(type_error(constraint, _ == 2), _))",
    "entailed_is": "caught(error(type_error(constraint, _ is 2), _))",
    "entailed_list": "caught(error(type_error(constraint, [_ =< 1]), _))",
    "module_entailed_unbound": "caught(error(instantiation_error, _))",
    "module_entailed_atom": "caught(error(type_error(constraint, foo), _))",
    # A relation is still read.
    "entailed_relation_holds": "true",
    "entailed_relation_built_at_run_time": "true",
    # A non-linear relation is not entailed.
    "entailed_nonlinear_disequality": "false",
    "entailed_nonlinear_le": "false",
    "entailed_nonlinear_lt": "false",
    "entailed_nonlinear_ge": "false",
    "entailed_nonlinear_gt": "false",
    "entailed_nonlinear_equality": "false",
    "entailed_nonlinear_unbound": "false",
    "entailed_division_by_a_variable": "false",
    "module_entailed_nonlinear": "false",
    # A zero divisor: the negation cannot be posted, so the relation holds.
    "entailed_zero_divisor_le": "true",
    "entailed_zero_divisor_equality": "true",
    "entailed_zero_divisor_disequality": "true",
    "entailed_zero_divisor_ground": "true",
    # A zero divisor fails a post and an optimum.
    "post_zero_divisor_equality": "false",
    "post_zero_divisor_le": "false",
    "post_zero_divisor_lt": "false",
    "post_zero_divisor_ge": "false",
    "post_zero_divisor_disequality": "false",
    "post_zero_divisor_nonlinear": "false",
    "sup_zero_divisor": "false",
    "inf_zero_divisor": "false",
    "maximize_zero_divisor": "false",
    "bb_inf_zero_divisor": "false",
    # in_q/3's bounds and a float binding.
    "in_q_atom_bound": "caught(error(type_error(rational, a), _))",
    "in_q_unbound_bound": "caught(error(instantiation_error, _))",
    "bind_a_float": "caught(error(type_error(rational, 1.5), _))",
}

CASES = r"""
case(entailed_unbound) :- entailed(_).
case(entailed_unbound_built_at_run_time) :- C = _, entailed(C).
case(entailed_atom) :- entailed(foo).
case(entailed_number) :- entailed(1).
case(entailed_compound) :- entailed(f(a, b)).
case(entailed_three_argument_compound) :- entailed(f(a, b, c)).
case(entailed_term_inequality) :- {X =< 1}, entailed(X \= 2).
case(entailed_structural_equality) :- {X =< 1}, entailed(X == 2).
case(entailed_is) :- {X =< 1}, entailed(X is 2).
case(entailed_list) :- {X =< 1}, entailed([X =< 1]).
case(module_entailed_unbound) :- clpq:entailed(_).
case(module_entailed_atom) :- clpq:entailed(foo).
case(entailed_relation_holds) :- {X =< 1}, entailed(X =< 2).
case(entailed_relation_built_at_run_time) :- {X =< 1}, C = (X =< 2), entailed(C).
case(entailed_nonlinear_disequality) :- {A =< 4}, entailed(A*A =\= 5).
case(entailed_nonlinear_le) :- {A =< 4, A >= 0}, entailed(A*A =< 100).
case(entailed_nonlinear_lt) :- {A =< 4}, entailed(A*A < 100).
case(entailed_nonlinear_ge) :- {A =< 4}, entailed(A*A >= -1).
case(entailed_nonlinear_gt) :- {A =< 4}, entailed(A*A > -1).
case(entailed_nonlinear_equality) :- {A =< 4}, entailed(A*A =:= 4).
case(entailed_nonlinear_unbound) :- entailed(_A*_B =:= 4).
case(entailed_division_by_a_variable) :- {A =< 4, B >= 1}, entailed(A/B =< 100).
case(module_entailed_nonlinear) :- {A =< 4}, clpq:entailed(A*A =\= 5).
case(entailed_zero_divisor_le) :- {A =< 4}, Z = 0, entailed(A =< 1/Z).
case(entailed_zero_divisor_equality) :- {A =< 4}, Z = 0, entailed(A =:= 1/Z).
case(entailed_zero_divisor_disequality) :- {A =< 4}, Z = 0, entailed(A =\= 1/Z).
case(entailed_zero_divisor_ground) :- Z = 0, entailed(1 =< 1/Z).
case(post_zero_divisor_equality) :- Z = 0, {_X =:= 1/Z}.
case(post_zero_divisor_le) :- Z = 0, {_X =< 1/Z}.
case(post_zero_divisor_lt) :- Z = 0, {_X < 1/Z}.
case(post_zero_divisor_ge) :- Z = 0, {_X >= 1/Z}.
case(post_zero_divisor_disequality) :- Z = 0, {_X =\= 1/Z}.
case(post_zero_divisor_nonlinear) :- Z = 0, {X*X =< 1/Z}.
case(sup_zero_divisor) :- {X =< 4}, Z = 0, sup(X + 1/Z, _).
case(inf_zero_divisor) :- {X >= 4}, Z = 0, inf(X + 1/Z, _).
case(maximize_zero_divisor) :- {X =< 4}, Z = 0, maximize(X + 1/Z, _).
case(bb_inf_zero_divisor) :- {X >= 4}, Z = 0, bb_inf([X], X + 1/Z, _).
case(in_q_atom_bound) :- in_q(_, a, 3).
case(in_q_unbound_bound) :- in_q(_, _, 3).
case(bind_a_float) :- {X =< 4}, X = 1.5.
"""


def _clausal_program():
    expectations = "".join(
        f"expected({name}, {want}).\n" for name, want in EXPECTED.items())
    return (":- use_module(library(clpq)).\n" + CASES + expectations + r"""
outcome(N, R) :-
    catch((findall(x, once(case(N)), L),
           (L == [], R = false ; L \== [], R = true)),
          E, R = caught(E)).

check(N) :- expected(N, Want), outcome(N, Got), Got = Want.

all_cases :- forall(expected(N, _), check(N)).
""")


def _succeeds(name, *args, module):
    return any(True for _ in call(name, *args, module=module))


@pytest.fixture(scope="module")
def clausal_module(tmp_path_factory):
    path = tmp_path_factory.mktemp("clpq_errors") / "clpq_error_terms.clausal"
    path.write_text(_clausal_program())
    return load_clausal_module(path)


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_clausal_case(clausal_module, case):
    got = Var()
    outcomes = [deref(got) for _ in call("outcome", case, got,
                                         module=clausal_module)]
    assert _succeeds("check", case, module=clausal_module), (
        case, EXPECTED[case], outcomes)


@pytest.mark.parametrize("solver", ["legacy", "holzbaur"])
def test_clausal_program_under_each_solver(solver, tmp_path):
    path = tmp_path / "clpq_error_terms.clausal"
    path.write_text(_clausal_program())
    env = dict(os.environ, CLAUSAL_CLPQ=solver, PYTHONPATH=str(ROOT))
    result = subprocess.run(
        [sys.executable, "-W", "ignore", "-m", "clausal", str(path),
         "-g", "all_cases"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert result.stdout.strip().splitlines()[-1:] == ["true."], (
        result.stdout + result.stderr)


# ---------------------------------------------------------------- the seam

SEAM_PROGRAM = """
holds(C) <- entailed(C)
module_holds(C) <- clpq.entailed(C)
nonlinear_holds() <- (in_q(X), X <= 4, entailed(X * X != 5))
block(C) <- clpq.rational(C)
bounded(L) <- in_q(X_UNUSED, L, 3)
"""


@pytest.fixture(scope="module")
def seam_module(tmp_path_factory):
    path = tmp_path_factory.mktemp("clpq_errors") / f"clpq_error_terms{SEAM}"
    path.write_text(SEAM_PROGRAM)
    return load_clausal_module(path)


def _raised(call_):
    with pytest.raises(LogicException) as caught:
        call_()
    return caught.value.term


@pytest.mark.parametrize("predicate", ["holds", "module_holds"])
def test_seam_entailed_of_an_unbound_argument_raises(seam_module, predicate):
    assert _raised(lambda: _succeeds(predicate, Var(), module=seam_module)) \
        == instantiation_error("entailed/1")


@pytest.mark.parametrize("predicate", ["holds", "module_holds"])
@pytest.mark.parametrize("term", ["foo", 1, ("f", "a", "b"),
                                  ("f", "a", "b", "c"), ("$chars", "abc")])
def test_seam_entailed_of_a_non_relation_raises(seam_module, predicate, term):
    assert _raised(lambda: _succeeds(predicate, term, module=seam_module)) \
        == type_error("constraint", term, "entailed/1")


def test_seam_entailed_of_a_nonlinear_relation_is_false(seam_module):
    assert not _succeeds("nonlinear_holds", module=seam_module)


@pytest.mark.parametrize("predicate", ["holds", "module_holds"])
def test_seam_entailed_of_a_nonlinear_relation_cell_is_false(seam_module,
                                                            predicate):
    y = Var()
    cell = ("=\\=", ("*", y, y), 5)
    assert not _succeeds(predicate, cell, module=seam_module)


def test_seam_block_of_an_unbound_term_raises(seam_module):
    assert _raised(lambda: _succeeds("block", Var(), module=seam_module)) \
        == instantiation_error("{}/1")


def test_seam_block_of_a_non_constraint_raises(seam_module):
    assert _raised(lambda: _succeeds("block", "foo", module=seam_module)) \
        == type_error("constraint", "foo", "{}/1")


def test_seam_in_q_bound_errors(seam_module):
    assert _raised(lambda: _succeeds("bounded", "a", module=seam_module)) \
        == type_error("rational", "a", "in_q/3")
    assert _raised(lambda: _succeeds("bounded", Var(), module=seam_module)) \
        == instantiation_error("in_q/3")


# ---------------------------------------------------------------- the API

SOLVERS = pytest.mark.parametrize("solver", [_legacy, _holzbaur],
                                  ids=["legacy", "holzbaur"])


@SOLVERS
def test_api_entailed_of_an_unknown_relation_raises(solver):
    t, x = Trail(), Var()
    term = _raised(lambda: solver.entailed("=>>", x, 1, t))
    assert term[0] == "error" and term[2] == ("/", "entailed", 1)
    assert term[1][:2] == ("type_error", "constraint")
    assert term[1][2][0] == "=>>" and deref(term[1][2][2]) == 1


@SOLVERS
def test_api_entailed_of_a_nonlinear_relation_is_false(solver):
    t, x = Trail(), Var()
    assert solver.q_le(x, 4, t)
    assert solver.entailed("=\\=", ("*", x, x), 5, t) is False


@SOLVERS
def test_api_zero_divisor(solver):
    t, x = Trail(), Var()
    assert solver.q_le(x, 4, t)
    assert solver.entailed("=<", x, ("/", 1, 0), t)
    assert not solver.q_le(Var(), ("/", 1, 0), t)
    assert not solver.sup(("+", x, ("/", 1, 0)), Var(), t)


@SOLVERS
def test_api_in_q_bound_errors(solver):
    t = Trail()
    assert _raised(lambda: solver.in_q(Var(), "a", None, t)) == \
        type_error("rational", "a", "in_q/3")
    assert _raised(lambda: solver.in_q(Var(), None, Var(), t)) == \
        instantiation_error("in_q/3")


@SOLVERS
def test_api_binding_a_float_raises(solver):
    t, x = Trail(), Var()
    assert solver.in_q(x, 0, 10, t)
    assert _raised(lambda: unify(x, 1.5, t)) == \
        type_error("rational", 1.5, "=/2")


@SOLVERS
@pytest.mark.parametrize("node", ["foo", ("not_a_constraint",)])
def test_api_block_of_a_non_constraint_raises(solver, node):
    t = Trail()
    assert _raised(lambda: solver.clpq_constraint_block(node, t)) == \
        type_error("constraint", node, "{}/1")


@SOLVERS
def test_api_block_of_an_unbound_term_raises(solver):
    assert _raised(lambda: solver.clpq_constraint_block(Var(), Trail())) == \
        instantiation_error("{}/1")


@SOLVERS
def test_api_block_of_a_conjunction_cell_posts_both(solver):
    t, x, s = Trail(), Var(), Var()
    block = (",", LtE(left=x, right=4), LtE(left=1, right=x))
    assert solver.clpq_constraint_block(block, t)
    assert solver.sup(x, s, t) and deref(s) == Fraction(4)
