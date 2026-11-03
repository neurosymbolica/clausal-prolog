"""Tabled CLP(Q) answers are kept modulo entailment, and every read of a
table sees the caller's store.

A table stores an answer that carries CLP(Q) state with its residue
(tests/test_clpq_tabled_answers.py).  Keyed on the residue's text, a
recursion that derives ever tighter constraints never completed:
``p(X) :- {X >= 0}.  p(X) :- p(Y), {X >= Y + 1}.`` derived X >= 1, X >= 2,
... -- each already covered by X >= 0 -- and the same constraints in
another order or basis were two answers.  A new answer whose constraints
entail the constraints of a stored answer of the same shape is no new
answer: the stored one already covers it (answer subsumption).  The solver
decides the entailment, under a trail mark it undoes.

The negation scan of a complete table read its rows on a scratch trail,
which under the default solver is a separate store: the caller's
constraints were not seen.  It reads them on the caller's trail now.

An answer whose only constraints are CLP(Q) ones is stored whole, so it no
longer bypasses the table (the D68 live hand-over is for constraints the
table cannot store).

Runs under the solver ``CLAUSAL_CLPQ`` selects; run the file under both.
"""
import signal

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _query_cache, call
from clausal.logic.variables import Var, deref

GROW = """\
:- use_module(library(clpq)).
:- table(p/1).
p(X) :- {X >= 0}.
p(X) :- p(Y), {X >= Y + 1}.
all(L) :- findall(I, (p(X), inf(X, I)), L).

edge(a, b). edge(b, c). edge(c, a).
:- table(cost/3).
cost(X, Y, C) :- edge(X, Y), {C >= 1}.
cost(X, Y, C) :- cost(X, Z, C0), edge(Z, Y), {C >= C0 + 1}.
costs(L) :- findall(Y-I, (cost(a, Y, C), inf(C, I)), L).

:- table(r5/2).
r5(X, Y) :- {X >= 1}, {Y >= 2}.
r5(X, Y) :- {Y >= 2}, {X >= 1}.
:- table(r6/2).
r6(X, Y) :- {X >= 1, X =< 5, Y = X + 1}.
r6(X, Y) :- {Y >= 2, Y =< 6, X = Y - 1}.
:- table(s/1).
s(X) :- {X >= 2}.
s(X) :- {X >= 1}.
s(X) :- {X >= 3}.
infs_s(L) :- findall(I, (s(X), inf(X, I)), L).
:- table(t/2).
t(X, Y) :- {X >= 1, Y >= 1}.
t(X, X) :- {X >= 2}.
:- table(c/1).
c(X) :- {X >= 1}.
c(1).
c(2).
pairs(N) :- findall(X-Y, (c(X), c(Y)), L), length(L, N).

:- table(q/1).
q(X) :- {X >= 1, X =< 5}.
prime :- q(_).
neg_far :- {X >= 10}, \\+ q(X).
neg_near :- {X >= 4}, \\+ q(X).
"""

SEAM = """\
-table(q/1)

q(X) <- in_q(X, 1, 5)

prime <- q(_)
neg_far(X) <- (in_q(X, 10, 20), not q(X))
neg_near(X) <- (in_q(X, 4, 20), not q(X))
"""

_count = [0]


class _Hang(Exception):
    pass


def _alarm(signum, frame):
    raise _Hang()


@pytest.fixture(autouse=True)
def _guard():
    _query_cache.clear()
    previous = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(30)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)
    _query_cache.clear()


def _load(tmp_path, text, suffix):
    _count[0] += 1
    path = tmp_path / f"tabled_sub_{_count[0]}{suffix}"
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


@pytest.fixture(params=SURFACES)
def program(request, tmp_path):
    return _load(tmp_path, GROW, request.param)


def test_a_recursion_that_tightens_its_constraints_completes(program):
    """X >= 1, X >= 2, ... are each entailed by X >= 0: one answer.  It
    never completed (each pass added one)."""
    assert _answers(program, "all") == [([0],)]
    assert _answers(program, "all") == [([0],)]


def test_a_cost_over_a_cycle_completes(program):
    """cost(a, b, C >= 4) after a round of the 3-cycle is entailed by
    cost(a, b, C >= 1)."""
    [(costs,)] = _answers(program, "costs")
    assert sorted(costs) == [("-", "a", 3), ("-", "b", 1), ("-", "c", 2)]


@pytest.mark.parametrize("name", ["r5", "r6"])
def test_the_same_constraints_written_two_ways_are_one_answer(program, name):
    assert len(_answers(program, name, arity=2)) == 1
    assert len(_answers(program, name, arity=2)) == 1


def test_a_more_general_later_answer_is_kept_beside_the_earlier_one(program):
    """s/1 derives X >= 2, then X >= 1 (more general: kept, the earlier one
    stays too; replacing it is not done), then X >= 3 (entailed by both:
    not new)."""
    assert _answers(program, "infs_s") == [([2, 1],)]


def test_the_shape_of_the_answer_counts(program):
    """t(X, X) with X >= 2 is entailed by t(X, Y) with X >= 1, Y >= 1 only
    after unifying X with Y; the stored answers are of different shapes
    (variants are compared), so both stay."""
    assert len(_answers(program, "t", arity=2)) == 2


def test_an_answer_with_only_clpq_constraints_waits_for_the_table(program):
    """c(X) :- {X >= 1}. c(1). c(2): the second call in the first one's
    continuation sees every answer: 9 pairs (it saw 7 when the constrained
    answer was handed over live, before the table completed)."""
    assert _answers(program, "pairs") == [(9,)]
    assert _answers(program, "pairs") == [(9,)]


def test_negation_over_a_complete_table_sees_the_callers_store(program):
    """{X >= 10}, \\+ q(X): no answer of q/1 (1 =< X =< 5) is consistent
    with X >= 10, so the negation holds.  The default solver failed it:
    the scan posted the row on a scratch trail, a store without X >= 10."""
    assert len(_answers(program, "prime", arity=0)) == 1
    for _ in range(2):
        assert len(_answers(program, "neg_far", arity=0)) == 1
        assert _answers(program, "neg_near", arity=0) == []


def test_negation_in_the_seam_sees_the_callers_store(tmp_path):
    module = _load(tmp_path, SEAM, ".seam")
    assert len(_answers(module, "prime", arity=0)) == 1
    for _ in range(2):
        assert len(_answers(module, "neg_far")) == 1
        assert _answers(module, "neg_near") == []


WFS = """\
:- use_module(library(clpq)).
:- table(u/0).
u :- \\+ u.
:- table(w/1).
w(X) :- {X >= 1, X =< 5}, \\+ u.
"""


@pytest.mark.parametrize("suffix", SURFACES)
def test_a_judged_conditional_answer_keeps_its_constraints(tmp_path, suffix):
    """query_wfs/judged_answers delivers a conditional (Undefined) answer
    after the solve, from its own leader's row: X was unconstrained there
    (sup/2 failed).  The residue is taken when the answer is derived and
    the row is replayed through ``TableEntry.unify_row``."""
    from clausal.logic.clpq import sup
    from clausal.logic.seam import judged_answers
    from clausal.logic.solve import _resolved_goal_and_module
    from clausal.logic.variables import Trail
    from clausal.terms import Undefined
    module = _load(tmp_path, WFS, suffix)
    for _ in range(2):
        _query_cache.clear()
        x, trail = Var(), Trail()
        goal, resolved = _resolved_goal_and_module(("w", x), module,
                                                   "query_wfs/3")
        seen = []
        for truth, _delays in judged_answers(goal, resolved, [x], trail):
            bound = Var()
            seen.append((truth, sup(x, bound, trail) and deref(bound)))
        assert seen == [(Undefined, 5)]
