"""entailed/1 reads a relation written as a compound cell.

A .clausal (and .pl) program hands ``entailed(X =< 5)`` its argument as the
cell ``('=<', X, 5)``; the builtin used to match only the seam's comparison
nodes, so every such call failed silently, on both CLP(Q) solvers.  See
todo/clausal-surface-gaps-found-moving-the-docs-2026-10-17.md (engine bugs,
item 2).

The in-process tests run under the solver CLAUSAL_CLPQ selects (run the file
under both); ``test_clausal_program_under_each_solver`` runs the .clausal
program under each solver in a subprocess, so the default run pins both.
"""
import os
import pathlib
import subprocess
import sys

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module
from tests._suffix import SEAM

ROOT = pathlib.Path(__file__).resolve().parents[1]

CLAUSAL_PROGRAM = r"""
:- use_module(library(clpq)).

implied :- in_q(X, 0, 100), {X =< 4}, entailed(X =< 5).
implied_strict :- {X > 2}, entailed(X > 2).
implied_through_another_variable :- {X >= 2, Y =:= X + 1}, entailed(Y >= 3).
implied_equality :- {X + Y =:= 10, X - Y =:= 4}, entailed(X =:= 7).
implied_disequality :- {X >= 2}, entailed(X =\= 1).
implied_disequality_unbounded_below :- {A =< 4}, entailed(A =\= 5).
implied_built_at_run_time :- {X =< 4}, C = (X =< 5), entailed(C).
implied_module_form :- {X =< 4}, clpq:entailed(X =< 5).

% Consistent with the store but not implied by it: X could be 4.
not_implied :- in_q(X, 0, 100), {X =< 4}, entailed(X =< 3).
not_implied_strict :- {X >= 2}, entailed(X > 2).
% Inconsistent with the store.
disentailed :- in_q(X, 0, 100), {X =< 4}, entailed(X > 10).

store_unchanged(S) :- {X =< 4}, entailed(X =< 5), \+ entailed(X =< 3), sup(X, S).

all_cases :-
    implied, implied_through_another_variable, implied_equality,
    implied_disequality, implied_disequality_unbounded_below,
    implied_built_at_run_time, implied_module_form,
    \+ not_implied, \+ not_implied_strict, \+ disentailed,
    store_unchanged(S), S =:= 4.
"""

SEAM_PROGRAM = """
implied() <- (in_q(X, 0, 100), X <= 4, entailed(X <= 5))
not_implied() <- (in_q(X, 0, 100), X <= 4, entailed(X <= 3))
disentailed() <- (in_q(X, 0, 100), X <= 4, entailed(X > 10))
module_implied() <- (in_q(X, 0, 100), X <= 4, clpq.entailed(X <= 5))
bounded_holds(X, C) <- (in_q(X, 0, 100), X <= 4, entailed(C))
bounded_module_holds(X, C) <- (in_q(X, 0, 100), X <= 4, clpq.entailed(C))
"""


def _succeeds(name, *args, module):
    return any(True for _ in call(name, *args, module=module))


@pytest.fixture(scope="module")
def clausal_module(tmp_path_factory):
    path = tmp_path_factory.mktemp("entailed") / "entailed_cells.clausal"
    path.write_text(CLAUSAL_PROGRAM)
    return load_clausal_module(path)


@pytest.fixture(scope="module")
def seam_module(tmp_path_factory):
    path = tmp_path_factory.mktemp("entailed") / f"entailed_seam{SEAM}"
    path.write_text(SEAM_PROGRAM)
    return load_clausal_module(path)


@pytest.mark.parametrize("goal", [
    "implied", "implied_through_another_variable", "implied_equality",
    "implied_disequality", "implied_disequality_unbounded_below",
    "implied_built_at_run_time", "implied_module_form"])
def test_clausal_entailed_relation_holds(clausal_module, goal):
    assert _succeeds(goal, module=clausal_module)


def test_clausal_entailed_strict_relation_holds(clausal_module):
    assert _succeeds("implied_strict", module=clausal_module)


@pytest.mark.parametrize("goal", ["not_implied", "not_implied_strict",
                                  "disentailed"])
def test_clausal_entailed_relation_not_implied(clausal_module, goal):
    assert not _succeeds(goal, module=clausal_module)


def test_clausal_entailed_leaves_the_store_as_it_was(clausal_module):
    s = Var()
    answers = [deref(s) for _ in call("store_unchanged", s,
                                      module=clausal_module)]
    assert answers == [4]


def test_clausal_all_cases(clausal_module):
    assert _succeeds("all_cases", module=clausal_module)


@pytest.mark.parametrize("goal, expected", [
    ("implied", True), ("not_implied", False), ("disentailed", False),
    ("module_implied", True)])
def test_seam_entailed_comparison_node(seam_module, goal, expected):
    assert _succeeds(goal, module=seam_module) is expected


@pytest.mark.parametrize("predicate", ["bounded_holds", "bounded_module_holds"])
@pytest.mark.parametrize("relation, bound, expected", [
    ("=<", 5, True), ("=<", 3, False), (">", 10, False), ("<", 5, True),
    (">=", 0, True), ("=\\=", 7, True), ("=:=", 4, False)])
def test_seam_entailed_relation_cell(seam_module, predicate, relation, bound,
                                     expected):
    # A relation cell reaches seam code from Clausal Prolog or from Python.
    x = Var()
    cell = (relation, x, bound)
    assert _succeeds(predicate, x, cell, module=seam_module) is expected


@pytest.mark.parametrize("solver", ["legacy", "holzbaur"])
def test_clausal_program_under_each_solver(solver, tmp_path):
    path = tmp_path / "entailed_cells.clausal"
    path.write_text(CLAUSAL_PROGRAM)
    env = dict(os.environ, CLAUSAL_CLPQ=solver, PYTHONPATH=str(ROOT))
    result = subprocess.run(
        [sys.executable, "-m", "clausal", str(path), "-g", "all_cases"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert result.stdout.strip().splitlines()[-1:] == ["true."], (
        result.stdout + result.stderr)


PROLOG_PROGRAM = r"""
:- use_module(library(clpq)).
implied :- {A =< 4}, entailed(A =< 5).
implied_disequality :- {A =< 4}, entailed(A =\= 5).
not_implied :- {A =< 4}, entailed(A =\= 3).
"""


@pytest.mark.parametrize("goal, expected", [
    ("implied", True), ("implied_disequality", True), ("not_implied", False)])
def test_prolog_entailed_relation(tmp_path, goal, expected):
    # The .pl front end passes the relation as a cell too
    # (todo/clpq-prolog-surface-gaps-entailed-dump-tabling-2026-10-12.md, 1).
    path = tmp_path / "entailed_cells.pl"
    path.write_text(PROLOG_PROGRAM)
    module = load_clausal_module(path)
    assert _succeeds(goal, module=module) is expected
