"""A tabled answer keeps its CLP(Q) constraints.

With ``p(X) :- {X >= 1, X =< 5}`` tabled, an answer of p/1 is a variable
bounded by 1 and 5.  The table stored the answer as a fresh, attribute-free
copy, so every answer handed out FROM the table (a second call, a call in
the first one's continuation) was an unconstrained variable: ``(p(X),
sup(X, S))`` failed (unbounded) and ``(p(X), X = 6)`` succeeded
(todo/done/clpq-prolog-surface-gaps-entailed-dump-tabling-2026-10-12.md,
item 3).

The table now stores, beside each answer that carries CLP(Q) state, the
solver's dump/3 of the constraints projected onto the answer's variables
(its residue), and a replay re-posts the residue on the fresh copy, as
clp(q,r)'s projecting_assert/1 stores a clause with its constraints.  Two
answers that differ only in their constraints are two answers.

Runs under the solver ``CLAUSAL_CLPQ`` selects; run the file under both.
"""
from fractions import Fraction

import pytest

from clausal.import_hook import _load_module
from clausal.logic.clpq import SOLVER
from clausal.logic.solve import _query_cache, call
from clausal.logic.variables import Var, deref

PL = """\
:- use_module(library(clpq)).
:- table(p/1).
p(X) :- {X >= 1, X =< 5}.
:- table(r/1).
r(X) :- {X >= 1}.
r(X) :- {X >= 2}.
:- table(d/2).
d(X, Y) :- {X + Y = 3, X =\\= 1}.
:- table(e/2).
e(X, Y) :- {X >= Z, Z >= Y}.

sup_p(S) :- p(X), sup(X, S).
inf_p(S) :- p(X), inf(X, S).
p_is(V) :- p(X), X = V.
twice(S) :- p(_X), p(Y), sup(Y, S).
infs_r(L) :- findall(I, (r(X), inf(X, I)), L).
d_at(V, Y) :- d(X, Y), X = V.
e_sup(S) :- e(X, Y), Y = 2, inf(X, S).
not_p(V) :- \\+ p(V).
"""

SEAM = """\
-table(p/1)

p(X) <- in_q(X, 1, 5)

sup_p(S) <- (p(X), sup(X, S))
inf_p(S) <- (p(X), inf(X, S))
p_is(V) <- (p(X), X is V)
twice(S) <- (p(_), p(Y), sup(Y, S))
not_p(V) <- (not p(V))
"""

NONLINEAR = """\
:- use_module(library(clpq)).
:- table(n/2).
n(X, Y) :- {X * Y = 2}.
n_at(V) :- n(X, Y), X = 1, Y = V.
"""

_count = [0]


@pytest.fixture(autouse=True)
def _clear_query_cache():
    _query_cache.clear()
    yield
    _query_cache.clear()


def _load(tmp_path, text, suffix):
    _count[0] += 1
    path = tmp_path / f"tabled_q_{_count[0]}{suffix}"
    path.write_text(text, encoding="utf-8")
    return _load_module(path.stem, path)


def _answers(module, name, *fixed, arity=1):
    variables = [Var() for _ in range(arity - len(fixed))]
    out = []
    for _ in call(name, *fixed, *variables, module=module):
        out.append(tuple(deref(v) for v in variables))
        _query_cache.clear()
    return out


SURFACES = [".pl", ".clausal"]


@pytest.fixture(params=SURFACES + [".seam"])
def program(request, tmp_path):
    suffix = request.param
    return _load(tmp_path, SEAM if suffix == ".seam" else PL, suffix)


def test_the_first_call_and_a_replay_see_the_bounds(program):
    """The first query evaluates the table; the second replays it.  Both
    see X bounded by 1 and 5."""
    assert _answers(program, "sup_p") == [(5,)]
    assert _answers(program, "sup_p") == [(5,)]
    assert _answers(program, "inf_p") == [(1,)]


def test_a_replayed_answer_refuses_a_value_outside_the_bounds(program):
    _answers(program, "sup_p")                 # the table is complete now
    assert list(call("p_is", 6, module=program)) == []
    _query_cache.clear()
    assert len(list(call("p_is", 3, module=program))) == 1
    _query_cache.clear()
    assert list(call("p_is", Fraction(11, 2), module=program)) == []


def test_a_second_call_in_the_continuation_sees_the_bounds(program):
    """``(p(X), p(Y), sup(Y, S))``: the inner p(Y) is answered from the
    table.  It failed (Y unbounded)."""
    assert _answers(program, "twice") == [(5,)]


@pytest.mark.parametrize("suffix", SURFACES)
def test_answers_that_differ_only_in_constraints_are_two_answers(
        tmp_path, suffix):
    """r(X) :- {X >= 1}.  r(X) :- {X >= 2}.  Both answers are a bare
    variable; their constraints tell them apart."""
    module = _load(tmp_path, PL, suffix)
    assert _answers(module, "infs_r") == [([1, 2],)]
    assert _answers(module, "infs_r") == [([1, 2],)]


@pytest.mark.parametrize("suffix", SURFACES)
def test_a_disequation_survives_the_table(tmp_path, suffix):
    module = _load(tmp_path, PL, suffix)
    for _ in range(2):
        assert _answers(module, "d_at", 1, arity=2) == []
        assert _answers(module, "d_at", 0, arity=2) == [(3,)]


@pytest.mark.parametrize("suffix", SURFACES)
def test_a_constraint_through_a_variable_outside_the_answer(tmp_path, suffix):
    """e(X, Y) :- {X >= Z, Z >= Y}: Z is no part of the answer; the table
    keeps its projection, X >= Y."""
    module = _load(tmp_path, PL, suffix)
    for _ in range(2):
        assert _answers(module, "e_sup") == [(2,)]


@pytest.mark.skipif(SOLVER != "holzbaur",
                    reason="the default solver refuses a nonlinear equation")
@pytest.mark.parametrize("suffix", SURFACES)
def test_a_nonlinear_residue_survives_the_table(tmp_path, suffix):
    module = _load(tmp_path, NONLINEAR, suffix)
    for _ in range(2):
        assert _answers(module, "n_at") == [(2,)]


def test_negation_over_the_table_sees_the_bounds(program):
    """``\\+ p(6)`` holds, ``\\+ p(3)`` does not, before and after p(X)'s
    table is complete.  In the seam, ``not`` over a tabled call reads the
    rows of a complete table that subsumes it (``_scan_complete_answers``),
    with no constraint of the caller's to filter them."""
    module = program
    _answers(module, "sup_p")
    for _ in range(2):
        assert len(list(call("not_p", 6, module=module))) == 1
        _query_cache.clear()
        assert list(call("not_p", 3, module=module)) == []
        _query_cache.clear()
