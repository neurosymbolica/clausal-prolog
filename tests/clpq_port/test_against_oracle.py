# tests/clpq_port/test_against_oracle.py
"""The port against the oracle (Scryer's library(clpq)).

Task 10 (ruling R16): the solver switch that clausal_answers(solver=
"holzbaur") needs is wired in Task 14, so the Clausal side here is a
Python-API driver.  It reads each query with Clausal's own reader
(iso_l3.read_iso), builds the operator nodes the `{}` lowering builds from
the same tables (iso_l3._CLPQ_COMPARISONS, _CLPQ_BINARY), posts them through
normal_form.post_constraint, and enumerates the answers with its own trail
mark and undo for `;`.  An answer is compared on the bindings of the shown
variables and, for each, its inf and sup (`none` where unbounded): the
residual constraints come with dump/3 in Task 12.

A binding `A = B` is the engine's unify, so it reaches the store through
the CLPQ_KEY hook (itf3.pl's verify_attributes/3, Task 11).
"""
from fractions import Fraction

import pytest

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq.normal_form import post_constraint
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.pythonic_ast import nodes
from clausal.tools.iso_l3 import _CLPQ_BINARY, _CLPQ_COMPARISONS, read_iso
from clausal.tools.prolog_reader import VarRef
from tests.clpq_oracle import Answer, oracle_answers, same_solution_sets

_BOUNDS = """\
'$bounds'(V, I, S) :-
    ( inf(V, I0) -> I = I0 ; I = none ),
    ( sup(V, S0) -> S = S0 ; S = none ).
"""


# ---------------------------------------------------------------- the driver

class _Query:
    """A query read with Clausal's reader; its variables are engine Vars."""

    def __init__(self, text):
        (clause,) = read_iso(f"'$query' :- {text}.\n")
        self.names = clause.var_names
        self.variables = {index: Var() for index in clause.var_names}
        self.body = clause.term[2]

    def variable(self, name):
        for index, known in self.names.items():
            if known == name:
                return self.variables[index]
        raise KeyError(name)

    def expression(self, term):
        """A reader term as the `{}` lowering's arithmetic nodes."""
        if type(term) is VarRef:
            return self.variables[term.i]
        if type(term) in (int, float):
            return term
        if type(term) is tuple and len(term) == 3 and term[0] in _CLPQ_BINARY:
            node = getattr(nodes, _CLPQ_BINARY[term[0]])
            return node(left=self.expression(term[1]), right=self.expression(term[2]))
        if type(term) is tuple and len(term) == 2 and term[0] == "-":
            return nodes.Negate(operand=self.expression(term[1]))
        if type(term) is tuple and len(term) == 2 and term[0] == "+":
            return self.expression(term[1])
        raise ValueError(f"not an expression the lowering accepts: {term!r}")

    def constraints(self, term):
        """`{C}`'s argument as the lowering's comparison nodes."""
        parts = []
        while type(term) is tuple and len(term) == 3 and term[0] == ",":
            parts.append(term[1])
            term = term[2]
        parts.append(term)
        result = []
        for part in parts:
            node = getattr(nodes, _CLPQ_COMPARISONS[part[0]])
            result.append(node(left=self.expression(part[1]),
                               right=self.expression(part[2])))
        return result[0] if len(result) == 1 else tuple(result)


def _term(query, term):
    """A reader term as an engine term: variables become the query's Vars,
    a compound a tuple cell."""
    if type(term) is VarRef:
        return query.variables[term.i]
    if type(term) is tuple:
        return (term[0],) + tuple(_term(query, argument) for argument in term[1:])
    return term


def _solve(query, goals, trail, found):
    """Run the goal list depth first, calling *found* at each answer.  A
    binding `A = B` is the engine's unify, through the CLPQ_KEY hook."""
    if not goals:
        found()
        return
    goal, rest = goals[0], goals[1:]
    if goal == "true":
        _solve(query, rest, trail, found)
        return
    if goal == "fail":
        return
    functor = goal[0]
    mark = trail.mark()
    if functor == ",":
        _solve(query, [goal[1], goal[2]] + rest, trail, found)
    elif functor == ";":
        _solve(query, [goal[1]] + rest, trail, found)
        trail.undo(mark)
        _solve(query, [goal[2]] + rest, trail, found)
    elif functor == "{}":
        if post_constraint(query.constraints(goal[1]), trail):
            _solve(query, rest, trail, found)
    elif functor == "=":
        if unify(_term(query, goal[1]), _term(query, goal[2]), trail):
            _solve(query, rest, trail, found)
    elif functor == "maximize":
        if bv.maximize(query.expression(goal[1]), trail):
            _solve(query, rest, trail, found)
    elif functor in ("sup", "inf"):
        optimum = bv.sup if functor == "sup" else bv.inf
        if optimum(query.expression(goal[1]), query.expression(goal[2]), trail):
            _solve(query, rest, trail, found)
    else:
        raise ValueError(f"the driver does not run {goal!r}")
    trail.undo(mark)


def _number(term):
    term = deref(term)
    return None if is_var(term) else Fraction(term)


def _bounds(variable, trail):
    """'$bounds'/3 on the port: inf and sup, or none."""
    values = []
    for optimum in (bv.inf, bv.sup):
        mark = trail.mark()
        result = Var()
        values.append(_number(result) if optimum(variable, result, trail) else "none")
        trail.undo(mark)
    return values


def port_answers(text, shown):
    """Every answer of the query *text* on the port, as Answers over the
    *shown* variables and their `_inf`/`_sup` companions."""
    query = _Query(text)
    trail = Trail()
    answers = []

    def found():
        bindings = {}
        for name in shown:
            variable = query.variable(name)
            value = _number(variable)
            if value is not None:
                bindings[name] = value
            low, high = _bounds(variable, trail)
            bindings[name + "_inf"] = low
            bindings[name + "_sup"] = high
        answers.append(Answer(bindings, []))

    _solve(query, [query.body], trail, found)
    return answers


def scryer_answers(text, shown):
    """The same on the oracle, residuals dropped (Task 12 adds them)."""
    companions = []
    for name in shown:
        companions += [name + "_inf", name + "_sup"]
    probes = ", ".join(f"'$bounds'({n}, {n}_inf, {n}_sup)" for n in shown)
    head = ", ".join(shown + companions)
    program = (":- use_module(library(clpq)).\n" + _BOUNDS
               + f"p({head}) :- {text}, {probes}.\n")
    answers = oracle_answers(program, f"p({head})", shown + companions)
    return [Answer(answer.bindings, []) for answer in answers]


# ---------------------------------------------------------------- the cases

CASES = [
    # the 2026-10-11 bug list (the plan's six)
    ("{X + Y = 3, 2*X + 2*Y = 6}", ["X", "Y"], 1),
    ("{X > 1, X < 3}", ["X"], 1),
    ("{X + Y >= 2}", ["X", "Y"], 1),
    ("{1 =< X, X =< 5, X = Y + 1}, Y = -10", ["X", "Y"], 0),
    ("{X < Y, Y =< 3}, X = 3", ["X", "Y"], 0),
    ("{X =< 3}, ({X >= 1}, fail ; true), X = 0", ["X"], 1),
    # the box LP: max X+3*Y is 9, at (0, 3)
    ("{0 =< X, X =< 2, 0 =< Y, Y =< 3, X + 2*Y =< 6}, sup(X + 3*Y, S)",
     ["X", "Y", "S"], 1),
    ("{0 =< X, X =< 2, 0 =< Y, Y =< 3, X + 2*Y =< 6}, sup(X + 3*Y, S),"
     " {X + 3*Y >= S}", ["X", "Y", "S"], 1),
    # non-linear: delays; linear once a factor is bound
    ("{X * Y = 6}", ["X", "Y"], 1),
    ("X = 2, {X * Y = 6}", ["X", "Y"], 1),
    # Review Focus 1: strict after backtracking
    ("{X < 3}, ({X =< 2}, fail ; true)", ["X"], 1),
    # Task 11: bindings through itf3.pl's hook
    ("{X >= 1}, {Y =< 0}, X = Y", ["X", "Y"], 0),
    ("{X >= 1}, {Y =< 5}, (X = Y, fail ; true)", ["X", "Y"], 1),
    ("{X >= 1}, {Y =< 5}, X = Y", ["X", "Y"], 1),
    ("{X + Y = 4}, X = Y", ["X", "Y"], 1),
    ("{X + Y =< 3}, {X = 1}", ["X", "Y"], 1),
    ("{X + Y =< 3}, X = 1", ["X", "Y"], 1),
    ("{X >= 1}, {X * X = 0}", ["X"], 0),
    ("{X < 3}, X = 3", ["X"], 0),
    ("{X >= 1, X =< 5}, X = 3", ["X"], 1),
    ("{X >= 1, X =< 5}, X = 7", ["X"], 0),
    ("{X =\\= 2}, {X + W = 3}, {W = 1}", ["X", "W"], 0),
    ("{X =\\= 2}, {X + W = 3}, {W = 2}", ["X", "W"], 1),
    ("{P * Q = 6}, {P + R = 3}, {R = 1}", ["P", "Q", "R"], 1),
    ("{Y = X + Z, X >= 1}, X = Y", ["X", "Y", "Z"], 1),
    ("{Y = X + Z, X >= 1}, Y = X", ["X", "Y", "Z"], 1),
    # Z, Y, X created in that order: X - Y has no X (itf3.pl's "deep shit")
    ("{0*Z + Y = X + Z, X >= 1}, X = Y", ["X", "Y", "Z"], 1),
    ("{X >= 1, X < 4}, X = Y", ["X", "Y"], 1),
    ("{X0 >= 0}, {X1 = X0 + 1, X2 = X1 + 1, X3 = X2 + 1}, X0 = 2",
     ["X0", "X1", "X2", "X3"], 1),
    ("{X0 >= 0}, {X1 = X0 + 1, X2 = X1 + 1, X3 = X2 + 1}, X3 = 2",
     ["X0", "X1", "X2", "X3"], 0),
    ("{X >= 1, X + Z =< 5}, X = 2", ["X", "Z"], 1),
    ("{X >= 1, X + Z =< 5}, {Y =< 3}, X = Y", ["X", "Y", "Z"], 1),
    ("{Y =< 3}, {X >= 1, X + Z =< 5}, X = Y", ["X", "Y", "Z"], 1),
    ("{X > 1, X + Z < 5}, {Y < 3}, X = Y", ["X", "Y", "Z"], 1),
    ("{X >= 1, X + Z =< 5, Z >= 2}, {Y >= 3}, X = Y", ["X", "Y", "Z"], 1),
    ("{X >= 1, X + Z =< 5, Z >= 2}, {Y >= 4}, X = Y", ["X", "Y", "Z"], 0),
    ("{X + Y + Z = 6, X - Y >= 0}, Z = 2, X = Y", ["X", "Y", "Z"], 1),
    ("{X =\\= 3}, {Y >= 3, Y =< 3}, X = Y", ["X", "Y"], 0),
    ("{X =\\= 3}, {Y >= 3, Y =< 4}, X = Y", ["X", "Y"], 1),
    # two answers through a disjunction
    ("({X >= 1} ; {X =< -1}), {X =< 4}", ["X"], 2),
]


@pytest.mark.parametrize("text, shown, count", CASES)
def test_the_port_answers_as_the_oracle(text, shown, count):
    want = scryer_answers(text, shown)
    assert len(want) == count, want
    got = port_answers(text, shown)
    ok, why = same_solution_sets(got, want)
    assert ok, f"{why}\nport:   {got}\noracle: {want}"


def _chain(steps):
    links = ", ".join(f"{{X{i + 1} = 7/13*X{i} + 1/3}}" for i in range(steps))
    return f"{{X0 >= 0, X0 =< 1}}, {links}, sup(X{steps}, S), inf(X{steps}, I)"


def test_review_focus_3_the_chain_through_nf_against_the_oracle():
    # 60 steps of X_{i+1} = 7/13*X_i + 1/3: numerators past 10**60, exact.
    want = scryer_answers(_chain(60), ["S", "I"])
    got = port_answers(_chain(60), ["S", "I"])
    assert want[0].bindings["S"].numerator > 10**60
    ok, why = same_solution_sets(got, want)
    assert ok, why


def test_the_box_lp_vertex_is_0_3():
    (answer,) = port_answers(
        "{0 =< X, X =< 2, 0 =< Y, Y =< 3, X + 2*Y =< 6}, sup(X + 3*Y, S),"
        " {X + 3*Y >= S}", ["X", "Y", "S"])
    assert (answer.bindings["X"], answer.bindings["Y"], answer.bindings["S"]) == (0, 3, 9)


def test_strict_bounds_after_backtracking_stay_strict():
    # inf/sup cannot tell < from =<; read the port's strictness directly.
    from clausal.logic.clpq.attributes import state_of
    query = _Query("{X < 3}, ({X =< 2}, fail ; true)")
    trail = Trail()
    seen = []
    _solve(query, [query.body], trail,
           lambda: seen.append(state_of(query.variable("X")).upper_strict))
    assert seen == [True]


@pytest.mark.parametrize("text, shown", [
    ("{1 =< X, X =< 5, X = Y + 1}, Y = -10", ["X", "Y"]),
    ("{X < Y, Y =< 3}, X = 3", ["X", "Y"]),
    ("{X * Y = 6}, X = 2", ["X", "Y"]),
    ("{0 =< X, X =< 2, 0 =< Y, Y =< 3, X + 2*Y =< 6}, maximize(X + 3*Y)",
     ["X", "Y"]),
])
def test_a_binding_goes_through_the_hook(text, shown):
    want = scryer_answers(text, shown)
    got = port_answers(text, shown)
    ok, why = same_solution_sets(got, want)
    assert ok, f"{why}\nport:   {got}\noracle: {want}"


def _random_binding_query(seed):
    """A random store over X, Y, Z, W, then one binding: a variable to a
    small integer, or two variables to each other.  Returns the query and
    the variables it mentions.  (The oracle side answers [] or raises for a
    query variable named A; these names avoid it.)"""
    import random
    rng = random.Random(seed)
    names = ["X", "Y", "Z", "W"]
    constraints = []
    for _ in range(rng.randint(2, 5)):
        chosen = rng.sample(names, rng.randint(1, 3))
        terms = " + ".join(f"{rng.choice([-3, -2, -1, 1, 2, 3])}*{n}"
                           for n in chosen)
        relation = rng.choice(["=<", ">=", "<", ">", "=", "=<", ">="])
        constraints.append(f"{terms} {relation} {rng.randint(-5, 5)}")
    first, second = rng.sample(names, 2)
    if rng.random() < 0.5:
        binding = f"{first} = {rng.randint(-3, 3)}"
    else:
        binding = f"{first} = {second}"
    text = "{" + ", ".join(constraints) + "}, " + binding
    return text, [name for name in names if name in text]


@pytest.mark.parametrize("seed", range(40))
def test_random_stores_bound_through_the_hook_against_the_oracle(seed):
    text, shown = _random_binding_query(seed)
    want = scryer_answers(text, shown)
    got = port_answers(text, shown)
    ok, why = same_solution_sets(got, want)
    assert ok, f"{text}\n{why}\nport:   {got}\noracle: {want}"
