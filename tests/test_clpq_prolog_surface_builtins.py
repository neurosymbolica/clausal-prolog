"""The clp(Q,R) builtins the SICStus 3.7.1 manual documents, on the .pl
surface, under each CLP(Q) solver.

``maximize/1``, ``minimize/1``, ``bb_inf/5``, ``ordering/1`` and ``dump/3``
raised existence_error (dump/3 a type_error: the name resolved to a Python
function); see todo/clpq-port-vs-sicstus-manual-23-gaps-2026-10-16.md.  The manual's own
queries are in tests/clpq_port/test_manual_examples.py (they need the
example files); these run without them, under both solvers through the
CLI, which is where a .pl program's answer is printed.
"""
import re

import pytest

from tests.clpq_oracle import _equivalent, _sides, _value, clausal_answers

SOLVERS = ["legacy", "holzbaur"]

PROGRAM = r"""
:- use_module(library(clpq)).

q_maximize(X, Y, Z) :-
    { 2*X+Y =< 16, X+2*Y =< 11, X+3*Y =< 15, Z = 30*X+50*Y }, maximize(Z).
q_minimize(X, Y, Z) :-
    { 2*X+Y =< 16, X+2*Y =< 11, X+3*Y =< 15, X >= 0, Y >= 0, Z = 30*X+50*Y },
    minimize(Z).
q_unbounded(X) :- { X >= 1 }, maximize(X).
q_bb_inf_5(X, Y, Z, Inf, Vertex) :-
    {X >= Y+Z, Y >= 3/2, Z >= 3/2}, bb_inf([Y, Z], X, Inf, Vertex, 0.001).
q_bb_inf_5_strict(X, Y, Z, Inf, Vertex) :-
    {X >= Y+Z, Y > 1, Z > 1}, bb_inf([Y, Z], X, Inf, Vertex, 0.001).
q_bb_inf_5_one(X, Y, Inf, Vertex) :-
    {X >= Y, Y >= 3/2}, bb_inf([Y], X, Inf, Vertex, 1/1000).
q_bb_inf_5_eps_unbound(X, Y, Inf, Vertex, Eps) :-
    {X >= Y, Y >= 3/2}, bb_inf([Y], X, Inf, Vertex, Eps).
q_ordering_list(X, Y) :- {X + Y = 10}, ordering([X]).
q_ordering_lt(X, Y) :- ordering(X < Y), {X + Y = 10}.
q_dump_names(A, B, Cs) :- {A + B =< 10, A >= 4}, dump([A, B], [a, b], Cs).
q_dump_fresh(A, B, Vs, Cs) :- {A + B =< 10, A >= 4}, dump([A, B], Vs, Cs).
q_dump_none(A, Vs, Cs) :- dump([A], Vs, Cs).
"""


def _answers(solver, goal, variables):
    return clausal_answers(PROGRAM, goal, variables, solver)


def _one(solver, goal, variables):
    [answer] = _answers(solver, goal, variables)
    return answer


def _items(text):
    """A printed list (``[a, b]``) as its item texts."""
    text = text.strip()
    assert text.startswith("[") and text.endswith("]"), text
    items, depth, start = [], 0, 1
    for i, char in enumerate(text[1:-1], 1):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(text[start:i].strip())
            start = i + 1
    items.append(text[start:-1].strip())
    return [item for item in items if item]


def _renamed(constraints, names, targets):
    for name, target in zip(names, targets):
        constraints = [re.sub(rf"(?<![\w]){re.escape(name)}(?![\w])", target, c)
                       for c in constraints]
    return constraints


# ---- maximize/1 and minimize/1 ---------------------------------------------

@pytest.mark.parametrize("solver", SOLVERS)
def test_maximize_1_binds_the_optimum(solver):
    answer = _one(solver, "q_maximize(X, Y, Z)", ["X", "Y", "Z"])
    assert answer.bindings == {"X": 7, "Y": 2, "Z": 310}
    assert answer.residual == []


@pytest.mark.parametrize("solver", SOLVERS)
def test_minimize_1_binds_the_optimum(solver):
    answer = _one(solver, "q_minimize(X, Y, Z)", ["X", "Y", "Z"])
    assert answer.bindings == {"X": 0, "Y": 0, "Z": 0}
    assert answer.residual == []


@pytest.mark.parametrize("solver", SOLVERS)
def test_maximize_1_of_an_unbounded_objective_fails(solver):
    assert _answers(solver, "q_unbounded(X)", ["X"]) == []


# ---- bb_inf/5 -----------------------------------------------------------------

@pytest.mark.parametrize("solver", SOLVERS)
def test_bb_inf_5_gives_the_infimum_and_the_integral_vertex(solver):
    answer = _one(solver, "q_bb_inf_5(X, Y, Z, Inf, Vertex)",
                  ["X", "Y", "Z", "Inf", "Vertex"])
    assert answer.bindings["Inf"] == 4
    assert [_value(v) for v in _items(answer.bindings["Vertex"])] == [2, 2]
    if solver == "holzbaur":
        # bb.pl's shape: the store is as it was, Inf alone is bound.
        assert set(answer.bindings) == {"Inf", "Vertex"}
        assert _equivalent(answer.residual,
                           ["Y>=3/2", "Z>=3/2", "X-Y-Z>=0"]) == (True, "")


def test_bb_inf_5_with_strict_bounds_on_the_port():
    # The manual's bb_inf example ({Y > 1, Z > 1}); the default solver's
    # bb_inf/3 fails on strict bounds, a limit it had before.
    answer = _one("holzbaur", "q_bb_inf_5_strict(X, Y, Z, Inf, Vertex)",
                  ["X", "Y", "Z", "Inf", "Vertex"])
    assert answer.bindings["Inf"] == 4
    assert [_value(v) for v in _items(answer.bindings["Vertex"])] == [2, 2]
    assert _equivalent(answer.residual, ["Y>1", "Z>1", "X-Y-Z>=0"]) == (True, "")


@pytest.mark.parametrize("solver", SOLVERS)
def test_bb_inf_5_with_one_integer_and_a_rational_eps(solver):
    answer = _one(solver, "q_bb_inf_5_one(X, Y, Inf, Vertex)",
                  ["X", "Y", "Inf", "Vertex"])
    assert answer.bindings["Inf"] == 2
    assert [_value(v) for v in _items(answer.bindings["Vertex"])] == [2]


@pytest.mark.parametrize("solver", SOLVERS)
def test_bb_inf_5_with_an_unbound_eps_fails(solver):
    # bb.pl: nf_constant/2 of Eps fails, so bb_inf/5 fails.
    assert _answers(solver, "q_bb_inf_5_eps_unbound(X, Y, Inf, Vertex, Eps)",
                    ["X", "Y", "Inf", "Vertex", "Eps"]) == []


# ---- ordering/1 ---------------------------------------------------------------

# The CLI prints a residual through dump/3 over the goal's variables in the
# order the goal lists them, which is an ordering too (X before Y here), so
# each ordering/1 below agrees with it; one that contradicts it raises
# system_error(unsatisfiable_ordering) from arrangement/2 on the port.

@pytest.mark.parametrize("solver", SOLVERS)
def test_ordering_1_with_a_list_is_accepted(solver):
    answer = _one(solver, "q_ordering_list(X, Y)", ["X", "Y"])
    assert answer.bindings == {}
    assert _equivalent(answer.residual, ["X+Y=10"]) == (True, "")
    if solver == "holzbaur":
        # ordering.pl: the listed variable is the one the answer defines.
        [constraint] = answer.residual
        assert _sides(constraint)[0] == "X", constraint


@pytest.mark.parametrize("solver", SOLVERS)
def test_ordering_1_with_a_relation_is_accepted(solver):
    answer = _one(solver, "q_ordering_lt(X, Y)", ["X", "Y"])
    assert answer.bindings == {}
    assert _equivalent(answer.residual, ["X+Y=10"]) == (True, "")
    if solver == "holzbaur":
        # ordering(A < B): the answer defines A in terms of B.
        [constraint] = answer.residual
        assert _sides(constraint)[0] == "X", constraint


# ---- dump/3 ---------------------------------------------------------------------

@pytest.mark.parametrize("solver", SOLVERS)
def test_dump_3_with_atoms_for_names(solver):
    answer = _one(solver, "q_dump_names(A, B, Cs)", ["A", "B", "Cs"])
    assert set(answer.bindings) == {"Cs"}
    # The store is as it was ...
    assert _equivalent(answer.residual, ["A>=4", "A+B=<10"]) == (True, "")
    # ... and CodedAnswer is its projection over the names.
    assert _equivalent(_items(answer.bindings["Cs"]),
                       ["a>=4", "a+b=<10"]) == (True, "")


@pytest.mark.parametrize("solver", SOLVERS)
def test_dump_3_with_fresh_variables(solver):
    answer = _one(solver, "q_dump_fresh(A, B, Vs, Cs)", ["A", "B", "Vs", "Cs"])
    assert set(answer.bindings) == {"Vs", "Cs"}
    names = _items(answer.bindings["Vs"])
    assert len(names) == 2 and all(n.startswith("_") for n in names), names
    assert _equivalent(_renamed(_items(answer.bindings["Cs"]), names, ["A", "B"]),
                       ["A>=4", "A+B=<10"]) == (True, "")
    assert _equivalent(answer.residual, ["A>=4", "A+B=<10"]) == (True, "")


@pytest.mark.parametrize("solver", SOLVERS)
def test_dump_3_without_a_store_is_empty(solver):
    answer = _one(solver, "q_dump_none(A, Vs, Cs)", ["A", "Vs", "Cs"])
    assert answer.bindings["Cs"] == "[]"
    assert answer.residual == []
