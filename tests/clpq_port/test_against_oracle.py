# tests/clpq_port/test_against_oracle.py
"""The port against the oracle (Scryer's library(clpq)).

Task 10 (ruling R16): the solver switch that clausal_answers(solver=
"holzbaur") needs is wired in Task 14, so the Clausal side here is a
Python-API driver.  It reads each query with Clausal's own reader
(iso_l3.read_iso), builds the operator nodes the `{}` lowering builds from
the same tables (iso_l3._CLPQ_COMPARISONS, _CLPQ_BINARY), posts them through
normal_form.post_constraint, and enumerates the answers with its own trail
mark and undo for `;`.  An answer is compared on the bindings of the shown
variables, for each its inf and sup (`none` where unbounded), and the
residual constraints (Task 12): the port's residual_constraints.
residual_strings against Scryer's dump/3, equal when z3 proves them
equivalent (tests/clpq_oracle.py same_solution_sets).

Delayed non-linear goals: Scryer's dump/3 drops them (ruling R8), so the
port's are split off before the comparison and checked against the text
the 1.3.3 source gives (_DELAYED).  Residual text and order: the port's
residuals are also compared as text with Scryer's; an order difference
would be recorded in DEVIATIONS.md D4/D8 and listed in
_KNOWN_TEXT_DIFFERENCES.

A binding `A = B` is the engine's unify, so it reaches the store through
the CLPQ_KEY hook (itf3.pl's verify_attributes/3, Task 11).
"""
import ast
import re
from fractions import Fraction

import pytest

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq.normal_form import post_constraint
from clausal.logic.clpq.residual_constraints import residual_strings
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.pythonic_ast import nodes
from clausal.tools.iso_l3 import _CLPQ_BINARY, _CLPQ_COMPARISONS, read_iso
from clausal.tools.prolog_reader import VarRef
from tests.clpq_oracle import (
    Answer, _equivalent, _marked_negative, _parse, _sides, oracle_answers,
    same_solution_sets)

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


def shown_residual(query, shown, trail):
    """The residual on the unbound *shown* variables, as the oracle helper
    prints it: an equality `R=N` for each shown variable that is the same
    variable as an earlier one R, then residual_strings over one
    representative of each; other variables are `_I1`, `_I2`, ..."""
    table = {}
    free = []
    aliases = []
    for name in shown:
        variable = deref(query.variable(name))
        if not is_var(variable):
            continue
        if variable._id in table:
            aliases.append(f"{table[variable._id]}={name}")
            continue
        table[variable._id] = name
        free.append(variable)
    internal = [0]

    def name_of(variable):
        if variable._id not in table:
            internal[0] += 1
            table[variable._id] = f"_I{internal[0]}"
        return table[variable._id]

    return aliases + residual_strings(free, trail, name_of)


def port_answers(text, shown, bounds=True):
    """Every answer of the query *text* on the port, as Answers over the
    *shown* variables, their `_inf`/`_sup` companions (unless *bounds* is
    False) and the residual constraints."""
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
            if bounds:
                low, high = _bounds(variable, trail)
                bindings[name + "_inf"] = low
                bindings[name + "_sup"] = high
        answers.append(Answer(bindings, shown_residual(query, shown, trail)))

    _solve(query, [query.body], trail, found)
    return answers


def scryer_answers(text, shown, bounds=True):
    """The same on the oracle, with Scryer's dump/3 as the residual."""
    companions = []
    probes = ""
    if bounds:
        for name in shown:
            companions += [name + "_inf", name + "_sup"]
        probes = ", " + ", ".join(f"'$bounds'({n}, {n}_inf, {n}_sup)"
                                  for n in shown)
    head = ", ".join(shown + companions)
    program = (":- use_module(library(clpq)).\n" + _BOUNDS
               + f"p({head}) :- {text}{probes}.\n")
    return oracle_answers(program, f"p({head})", shown + companions)


# ---------------------------------------------------------------- residuals

def _is_linear(constraint):
    """A constraint Scryer's dump/3 would show: an alias `R=N`, or `{C}`
    with no product of two terms holding variables, no variable divisor
    and no power or function of one."""
    constraint = constraint.strip()
    if not constraint.startswith("{"):
        return re.fullmatch(r"\w+=\w+", constraint) is not None
    stack = []
    for side in _sides(constraint)[0::2]:
        stack.append(_parse(side))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Mult) and _has_name(node.left) \
                    and _has_name(node.right):
                return False
            if isinstance(node.op, ast.Div) and _has_name(node.right):
                return False
            if isinstance(node.op, ast.Pow) and (_has_name(node.left)
                                                 or _has_name(node.right)):
                return False
            stack += [node.left, node.right]
        elif isinstance(node, ast.UnaryOp):
            stack.append(node.operand)
        elif not isinstance(node, (ast.Name, ast.Constant)):
            return False
    return True


def _has_name(node):
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and _marked_negative(child.id) is None:
            return True
    return False


def split_delayed(answers):
    """(answers with only their linear residual, each answer's delayed
    goals with blanks removed)."""
    linear, delayed = [], []
    for answer in answers:
        kept = [r for r in answer.residual if _is_linear(r)]
        delayed.append([re.sub(r"\s+", "", r) for r in answer.residual
                        if not _is_linear(r)])
        linear.append(Answer(answer.bindings, kept))
    return linear, delayed


def residual_text(answers):
    """Each answer's residual as text: braces, blanks and `rdiv` spelt
    out the same way for both systems."""
    result = []
    for answer in answers:
        texts = []
        for constraint in answer.residual:
            constraint = constraint.strip()
            if constraint.startswith("{") and constraint.endswith("}"):
                constraint = constraint[1:-1]
            texts.append(re.sub(r"\s+", "", constraint.replace(" rdiv ", "/")))
        result.append(texts)
    return result


#: Delayed goals the port shows, as the 1.3.3 source gives them (ruling R8:
#: nfq.pl translate_goal//1 gives clpq:{Term=0}, nf2term writes the
#: constant first and p2term([X^1, Y^1]) is Y*X; dump.pl strips clpq:).
_DELAYED = {"{X * Y = 6}": [["{-6+Y*X=0}"]]}

#: Cases whose residual text or order differs from Scryer's while z3 proves
#: them equivalent (DEVIATIONS.md D4/D8 list each one).
_KNOWN_TEXT_DIFFERENCES = {}


def check_against_oracle(text, shown, got, want):
    """same_solution_sets on bindings and linear residuals; the delayed
    goals against _DELAYED; the residual text against Scryer's."""
    got_linear, delayed = split_delayed(got)
    ok, why = same_solution_sets(got_linear, want)
    assert ok, f"{text}\n{why}\nport:   {got}\noracle: {want}"
    assert delayed == _DELAYED.get(text, [[] for _ in got]), (text, delayed)
    if text not in _KNOWN_TEXT_DIFFERENCES:
        assert residual_text(got_linear) == residual_text(want), \
            f"{text}\nport:   {residual_text(got_linear)}\noracle: {residual_text(want)}"


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
    check_against_oracle(text, shown, got, want)


def _chain(steps):
    links = ", ".join(f"{{X{i + 1} = 7/13*X{i} + 1/3}}" for i in range(steps))
    return f"{{X0 >= 0, X0 =< 1}}, {links}, sup(X{steps}, S), inf(X{steps}, I)"


def test_review_focus_3_the_chain_through_nf_against_the_oracle():
    # 60 steps of X_{i+1} = 7/13*X_i + 1/3: numerators past 10**60, exact.
    want = scryer_answers(_chain(60), ["S", "I"])
    got = port_answers(_chain(60), ["S", "I"])
    assert want[0].bindings["S"].numerator > 10**60
    check_against_oracle(_chain(60), ["S", "I"], got, want)


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
    check_against_oracle(text, shown, got, want)


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
    check_against_oracle(text, shown, got, want)


# ---------------------------------------------------------------- the brief's residual cases

def test_two_multiples_of_one_equation_answer_one_equation():
    text = "{X + Y = 3, 2*X + 2*Y = 6}"
    (answer,) = port_answers(text, ["X", "Y"], bounds=False)
    assert len(answer.residual) == 1
    assert _equivalent(answer.residual, ["X+Y=3"]) == (True, "")


def test_two_strict_bounds_stay_strict():
    (answer,) = port_answers("{X > 1, X < 3}", ["X"], bounds=False)
    assert answer.residual == ["{X > 1}", "{X < 3}"]


def test_a_strict_bound_projects_strict_onto_x():
    # The legacy solver answered X =< 3.
    text = "{X < Y, Y =< 3}"
    got = port_answers(text, ["X"], bounds=False)
    assert [a.residual for a in got] == [["{X < 3}"]]
    check_against_oracle(text, ["X"], got, scryer_answers(text, ["X"], bounds=False))


@pytest.mark.parametrize("text, expected", [
    ("{Y >= 2, X - Y >= 0, X > 0, X < 5}", ["{X >= 2}", "{X < 5}"]),
    ("{Y =< 2, X - Y =< 0, X < 9, X > -5}", ["{X =< 2}", "{X > -5}"]),
])
def test_the_bound_that_stays_keeps_its_strictness(text, expected):
    # redund.pl strictness_parts/3: the redundant bound goes, the other
    # keeps its own strictness bit (X > 0 and X < 9 go).
    got = port_answers(text, ["X"], bounds=False)
    assert [a.residual for a in got] == [expected]
    check_against_oracle(text, ["X"], got, scryer_answers(text, ["X"], bounds=False))


# ---------------------------------------------------------------- the projection fuzz

def fuzz_store(seed):
    """A store of 2 to 6 variables and 4 to 12 constraints mixing <, =< and
    =, as query text, and the variables it mentions."""
    import random
    rng = random.Random(seed)
    names = [f"X{i}" for i in range(rng.randint(2, 6))]
    constraints = []
    for _ in range(rng.randint(4, 12)):
        chosen = rng.sample(names, rng.randint(1, min(3, len(names))))
        terms = " + ".join(f"{rng.choice([-3, -2, -1, 1, 2, 3])}*{n}"
                           for n in chosen)
        relation = rng.choice(["<", "=<", "<", "=<", "="])
        constraints.append(f"{terms} {relation} {rng.randint(-6, 6)}")
    text = "{" + ", ".join(constraints) + "}"
    return text, [n for n in names if re.search(rf"\b{n}\b", text)]


def _rational_text(value):
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def own_interval(variable, name, trail):
    """The port's own inf and sup of *variable* with strictness: the inf I
    is attained where posting `{V =< I}` succeeds, the sup S where
    `{V >= S}` does.  As residual text over *name*.  (Posting `{V = I}`
    is no test: like Scryer's, the port can accept a binding that leaves
    strict constraints unsatisfiable;
    test_a_binding_can_leave_strict_constraints_unsatisfiable.)"""
    from clausal.logic.clpq.normal_form import post_constraint as post
    interval = []
    for optimum, closed, open_, probe in ((bv.inf, ">=", ">", "=<"),
                                          (bv.sup, "=<", "<", ">=")):
        mark = trail.mark()
        result = Var()
        found = optimum(variable, result, trail)
        value = _number(result) if found else None
        trail.undo(mark)
        if value is None:
            continue
        mark = trail.mark()
        attained = post((probe, variable, value), trail)
        trail.undo(mark)
        interval.append(f"{name}{closed if attained else open_}{_rational_text(value)}")
    return interval


def projection_fuzz(seed):
    """For each variable of the seed's store: (name, the dump projected onto
    it, the port's own interval), or (name, bound value, None)."""
    text, names = fuzz_store(seed)
    query = _Query(text)
    trail = Trail()
    results = []

    def found():
        for name in names:
            variable = deref(query.variable(name))
            if not is_var(variable):
                results.append((name, Fraction(variable), None))
                continue
            residual = shown_residual(query, [name], trail)
            results.append((name, residual, own_interval(variable, name, trail)))

    _solve(query, [query.body], trail, found)
    return text, names, results


def test_the_projected_dump_has_the_port_s_own_inf_and_sup():
    # 200 seeded stores: the dump projected onto each variable is exactly
    # the interval of the port's inf and sup, strictness included (z3
    # proves the two equivalent, the dump's other variables existential).
    feasible = checked = strict = 0
    for seed in range(200):
        text, _, results = projection_fuzz(seed)
        feasible += bool(results)
        for name, residual, interval in results:
            if interval is None:
                continue
            checked += 1
            strict += sum(1 for c in interval if re.search(r"[<>](?!=)", c))
            ok, why = _equivalent(residual, interval)
            assert ok, f"seed {seed}, {name}: {text}\n{residual} against {interval}: {why}"
    assert feasible >= 50 and checked >= 200 and strict >= 100, \
        (feasible, checked, strict)


@pytest.mark.parametrize("seed", range(30))
def test_the_projection_fuzz_against_the_oracle(seed):
    text, names = fuzz_store(seed)
    for name in names:
        got = port_answers(text, [name], bounds=False)
        want = scryer_answers(text, [name], bounds=False)
        check_against_oracle(text, [name], got, want)


def test_a_binding_can_leave_strict_constraints_unsatisfiable():
    # Found by the projection fuzz (seed 30): the store with X4 = -1 is
    # unsatisfiable (X0 - 1/3*X1 < -1 and X0 - X1 >= -1 give X0 < -1,
    # against X0 >= -1), yet the binding is accepted, by Scryer's clpq as by
    # the port; {X4 =< -1} fails on both.  The same answer on both, so the
    # port keeps it; whether SICStus 1.3.3 does too is not checked.
    store = ("{-1*X0 + -3*X4 + 1*X1 =< 4, -3*X0 =< 3, -3*X3 + 3*X4 < 4,"
             " -1*X0 + -2*X4 + -1*X3 < -2, 3*X0 + -1*X1 + -3*X4 < 0}")
    shown = ["X0", "X1", "X3", "X4"]
    for extra, count in ((", X4 = -1", 1), (", {X4 = -1}", 1), (", {X4 =< -1}", 0)):
        got = port_answers(store + extra, shown, bounds=False)
        want = scryer_answers(store + extra, shown, bounds=False)
        assert len(got) == len(want) == count
        check_against_oracle(store + extra, shown, got, want)
    (answer,) = port_answers(store + ", X4 = -1", shown, bounds=False)
    import z3
    from tests.clpq_oracle import _formula
    solver = z3.Solver()
    solver.add(_formula(answer.residual, {})[0])
    assert solver.check() == z3.unsat
