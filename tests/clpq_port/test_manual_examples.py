"""The CLP(Q) port against the answers the SICStus 3.7.1 clp(Q,R) manual
chapter documents: the independent reference.

The oracle (tests/clpq_oracle.py) is the LOCAL clpq.pl port of 1.3.3 on
Scryer, so agreeing with it is two ports of one source agreeing.  The
manual's printed answers come from neither port, and that is the point of
this file.  Each documented query that runs cut-free is asserted against
the manual, and against the oracle where the oracle applies.

Sources.  The example programs are extracted at test time from the
chapter's text, ``sicstus-3.7.1-clpqr-manual.txt`` in
``CLAUSAL_CLPQ_EXAMPLES_DIR`` (tests/clpq_example_files.py): each block after
a ``% from file: library('clpqr/examples/...')`` marker.  The Monash
mortgage, which the chapter only queries, comes from ``test_examples_clpq.pl``
(the 1.3.3 distribution's examples) in the same directory.  Neither file is
copied into this repository (the licence acceptance for the 1.3.3 sources
does not cover them); the tests skip where one is absent, and fail when
CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1.  The queries below are this test's own.

Exact or within a tolerance.  The manual's answers are mostly clp(r)
output, floats; the port computes clp(Q), exact rationals.  Where the true
value is evidently exact (an integer optimum, the integral vertex, 1/4,
a coefficient printed as 49.5) the rational is compared exactly.  Otherwise
the rational is compared with the documented float to within a relative
``REL = 1e-12``; each test says which.  The manual itself warns that its
printed answer constraints may differ syntactically from a run's while
meaning the same, so residuals are compared by z3 equivalence
(tests/clpq_oracle.py), never as text.

Adaptations, on the port's copy only:
- floats in a program or query (``0.01``, ``0.9``) are kept: the port
  coerces them to the decimal rational (1/100, 9/10), as the chapter says
  clp(Q) does.  The oracle reads them as binary floats and converts those
  exactly (its flugpl infimum is 5013024519777045/2^32 and its bb_inf
  fails), so the oracle's copy spells them 1/100 and 9/10.
- ``maximize(Z)`` becomes ``maximize(Z, _)`` (DEVIATIONS.md D20) in
  test_maximize; test_maximize_1_as_documented runs the /1 form as written.
- the Monash mortgage's ``<=`` becomes ``=<``, as in test_examples.py.
- clp(q)'s ``C = rat(10,1)`` is ``C = 10``: rat/2 is SICStus 3's internal
  spelling of a rational (the chapter's "Rationals" section).

Where the port disagrees with the manual the test asserts the manual and
is ``xfail(strict=True)`` with the reason (``raises`` is set, so a missing
example file still fails under CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1).  Two of
the manual's printed answers are not the answers their own queries have;
see test_dump_3 and test_monash_go4_as_documented.
"""
import functools
import os
import re
import subprocess
import sys
import time
from fractions import Fraction

import pytest
import z3

from tests.clpq_example_files import example_file
from tests.clpq_oracle import (Answer, _equivalent, _expression, _sides, _value,
                               clausal_answers, oracle_answers,
                               same_solution_sets)

MANUAL = "sicstus-3.7.1-clpqr-manual.txt"
EXAMPLES = "test_examples_clpq.pl"

#: Relative tolerance between an exact rational and the manual's clp(r) float.
REL = 1e-12

_HEAD = ":- use_module(library(clpq)).\n"
_ORACLE_HEAD = ":- use_module(library(lists)).\n:- use_module(library(between)).\n"


def _disagrees(reason, error=None):
    """A strict xfail that holds only for the stated disagreement.

    *error* is a regex the port's RuntimeError (its error text) must match;
    None means the disagreement is a wrong answer, an AssertionError.  Any
    other failure (a crash, an AssertionError where an error is expected,
    another error text) is a real failure, so a crash cannot satisfy the
    xfail.  A missing example file fails too (pytest.fail is not in
    ``raises``)."""
    def decorate(test):
        @functools.wraps(test)
        def run(*args, **kwargs):
            try:
                test(*args, **kwargs)
            except RuntimeError as exc:
                if error is None or not re.search(error, str(exc)):
                    pytest.fail(f"not the stated disagreement ({reason}):\n{exc}",
                                pytrace=False)
                raise
            except AssertionError as exc:
                if error is not None:
                    pytest.fail(f"expected the error {error!r} ({reason}), "
                                f"got a wrong answer:\n{exc}", pytrace=False)
                raise
        return pytest.mark.xfail(strict=True, raises=(AssertionError, RuntimeError),
                                 reason=reason)(run)
    return decorate


# ---- the programs, from the manual's text ----------------------------------

_MARK = re.compile(r"^% from file: library\('clpqr/examples/([a-z_/]+)'\)\s*$")
_CLAUSE_START = re.compile(r"[a-z][A-Za-z0-9_]*\(")


@functools.cache
def _blocks(text):
    """{example file: [block, ...]}: the lines after each marker up to the
    first line of prose (one at column 0 that does not start a clause)."""
    blocks, lines, i = {}, text.splitlines(), 0
    while i < len(lines):
        found = _MARK.match(lines[i])
        i += 1
        if not found:
            continue
        if i < len(lines) and lines[i].strip() == "%":
            i += 1
        block = []
        while i < len(lines):
            line = lines[i]
            if line and not line[0].isspace() and not _CLAUSE_START.match(line):
                break
            block.append(line)
            i += 1
        blocks.setdefault(found.group(1), []).append("\n".join(block).strip() + "\n")
    return blocks


def _manual_program(*files, cut_free=True):
    blocks = _blocks(example_file(MANUAL).read_text())
    body = "".join(block for name in files for block in blocks[name])
    if cut_free:
        assert "!" not in body and "->" not in body, files
    return body


def _monash_mortgage():
    """monash_mg/5, the Monash mortgage, from the 1.3.3 examples file: the
    port's copy (``<=`` as ``=<``) and the oracle's (``<=`` an operator)."""
    text = example_file(EXAMPLES).read_text()
    clauses = re.findall(r"^monash_mg\(.*\.[ \t]*$", text, re.M)
    assert len(clauses) == 2, clauses
    clauses = "\n".join(clauses) + "\n"
    return (re.sub(r"(?<![=<>])<=", "=<", clauses),
            ":- op(700, xfx, <=).\n" + clauses)


# ---- running a query ---------------------------------------------------------

def _goal(query, variables):
    return f"{query}({', '.join(variables)})" if variables else query


def port(program, query, variables):
    return clausal_answers(_HEAD + program, _goal(query, variables), variables,
                           "holzbaur")


def oracle(program, query, variables, timeout=120):
    return oracle_answers(_ORACLE_HEAD + _HEAD + program, _goal(query, variables),
                          variables, timeout=timeout)


def _one(answers):
    """The one answer; an AssertionError (not a ValueError) otherwise, so a
    disagreement's xfail catches it."""
    assert len(answers) == 1, answers
    return answers[0]


def _agree(got, want):
    assert same_solution_sets(got, want) == (True, ""), (got, want)


def _is(answer, bindings, residual):
    """*answer* has exactly *bindings* and a residual z3-equivalent to *residual*."""
    _agree([answer], [Answer(bindings, residual)])


def _exact(value):
    assert type(value) in (int, Fraction), value
    return Fraction(value)


def _close(value, documented):
    """An exact rational within REL of the manual's float."""
    assert abs(float(_exact(value)) - documented) <= REL * abs(documented), \
        (value, float(value), documented)


def _list(text):
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


def _linear(constraint):
    """``L = R`` as its coefficients ({name: Fraction}) and constant, of L - R."""
    left, relation, right = _sides(constraint)
    assert relation in ("=", "=:="), constraint
    names = {}
    form = _expression(left, names) - _expression(right, names)

    def at(values):
        pairs = [(names[n], z3.RealVal(values.get(n, 0))) for n in names]
        return Fraction(z3.simplify(z3.substitute(form, *pairs)).as_fraction())
    constant = at({})
    return {n: at({n: 1}) - constant for n in names}, constant


def _solved_for(constraint, variable):
    """The equality *constraint* as ``variable = sum(c * v) + k``: ({v: c}, k)."""
    coefficients, constant = _linear(constraint)
    pivot = coefficients.pop(variable)
    return ({n: -c / pivot for n, c in coefficients.items() if c},
            -constant / pivot)


# ---- Solver Predicates -------------------------------------------------------

_SOLVER = """
q_entailed(A) :- {A =< 4}, entailed(A =\\= 5).
q_not_entailed(A) :- {A =< 4}, entailed(A =\\= 3).
q_sup(X, Y, Z, Sup) :-
    { 2*X+Y =< 16, X+2*Y =< 11, X+3*Y =< 15, Z = 30*X+50*Y }, sup(Z, Sup).
q_maximize(X, Y, Z) :-
    { 2*X+Y =< 16, X+2*Y =< 11, X+3*Y =< 15, Z = 30*X+50*Y }, maximize(Z, _).
q_maximize_1(X, Y, Z) :-
    { 2*X+Y =< 16, X+2*Y =< 11, X+3*Y =< 15, Z = 30*X+50*Y }, maximize(Z).
q_bb_inf(X, Y, Z, Inf) :- {X >= Y+Z, Y > 1, Z > 1}, bb_inf([Y,Z], X, Inf).
q_dump(A, B, Vs, Cs, Bp, Cb) :-
    {A+B =< 10, A >= 4}, dump([A,B], Vs, Cs), dump([B], Bp, Cb).
"""
_SOLVER_ORACLE = _SOLVER.replace("maximize(Z, _)", "maximize(Z)")


@_disagrees("entailed/1 fails on every constraint written as a Prolog term: "
            "builtins/constraints.py _entailed__1 matches only the seam's "
            "comparison nodes, so ('=\\\\=', A, 5) falls through and fails "
            "silently (entailed(A =< 5) fails too); the oracle answers yes")
def test_entailed():
    # {A =< 4}, entailed(A =\= 5): yes, with {A =< 4} left.
    answer = _one(port(_SOLVER, "q_entailed", ["A"]))
    _is(answer, {}, ["A=<4"])


def test_entailed_on_the_oracle():
    [answer] = oracle(_SOLVER_ORACLE, "q_entailed", ["A"])
    _is(answer, {}, ["A=<4"])


@_disagrees("entailed/1 fails on every constraint written as a Prolog term "
            "(see test_entailed), so a `no` from the port means nothing until "
            "the positive control, {A =< 4}, entailed(A =\\= 5), answers yes")
def test_not_entailed():
    # {A =< 4}, entailed(A =\= 3): no.  The port's `no` counts only once
    # its entailed/1 can say yes: the positive control comes first.  When
    # entailed/1 is fixed this flips to XPASS and fails, forcing a revisit.
    assert len(port(_SOLVER, "q_entailed", ["A"])) == 1
    assert port(_SOLVER, "q_not_entailed", ["A"]) == []


def test_not_entailed_on_the_oracle():
    assert len(oracle(_SOLVER_ORACLE, "q_entailed", ["A"])) == 1
    assert oracle(_SOLVER_ORACLE, "q_not_entailed", ["A"]) == []


def test_sup():
    # Exact: Sup = 310, and the residual the manual prints.
    variables = ["X", "Y", "Z", "Sup"]
    answer = _one(port(_SOLVER, "q_sup", variables))
    _is(answer, {"Sup": 310}, ["Z=30*X+50*Y", "X+1/2*Y=<8", "X+3*Y=<15",
                               "X+2*Y=<11"])
    _agree([answer], oracle(_SOLVER_ORACLE, "q_sup", variables))


def test_maximize():
    # Exact: X = 7, Y = 2, Z = 310 (maximize(Z) as maximize(Z, _), D20).
    variables = ["X", "Y", "Z"]
    answer = _one(port(_SOLVER, "q_maximize", variables))
    _is(answer, {"X": 7, "Y": 2, "Z": 310}, [])
    _agree([answer], oracle(_SOLVER_ORACLE, "q_maximize", variables))


@_disagrees("maximize/1 is not a .pl builtin: existence_error(procedure, "
            "maximize/1); only Clausal's maximize/2 exists (DEVIATIONS.md D20)",
            error=r"existence_error\(procedure,maximize/1\)")
def test_maximize_1_as_documented():
    answer = _one(port(_SOLVER, "q_maximize_1", ["X", "Y", "Z"]))
    _is(answer, {"X": 7, "Y": 2, "Z": 310}, [])


def test_bb_inf_3():
    # Exact: Inf = 4, the store unchanged.
    variables = ["X", "Y", "Z", "Inf"]
    answer = _one(port(_SOLVER, "q_bb_inf", variables))
    _is(answer, {"Inf": 4}, ["Y>1", "Z>1", "X-Y-Z>=0"])
    _agree([answer], oracle(_SOLVER_ORACLE, "q_bb_inf", variables))


def _dumped(answer, new_vars, coded, targets):
    """The constraints of a dump/3 answer over *targets*: the CodedAnswer
    list with each NewVars variable renamed to its target."""
    names = _list(answer.bindings[new_vars])
    assert len(names) == len(targets), names
    constraints = _list(answer.bindings[coded])
    for name, target in zip(names, targets):
        constraints = [re.sub(rf"(?<![\w]){re.escape(name)}(?![\w])", target, c)
                       for c in constraints]
    return constraints


def _check_dump(answer):
    # Cs over Vs = [A', B'] is {A' >= 4, A' + B' =< 10}; Cb over Bp is
    # {B' =< 6}.  The manual prints Cs = [_B>=4, _C+_B=<10] with
    # Vs = [_C, _B], which puts the bound on B: a misprint, since its own
    # top-level answer in the same reply is {A>=4}, {A+B=<10}.  The test
    # takes the reading the definition of dump/3 and that top-level answer
    # give (the oracle's).
    _is(answer, {"Vs": answer.bindings["Vs"], "Cs": answer.bindings["Cs"],
                 "Bp": answer.bindings["Bp"], "Cb": answer.bindings["Cb"]},
        ["A>=4", "A+B=<10"])
    assert _equivalent(_dumped(answer, "Vs", "Cs", ["A", "B"]),
                       ["A>=4", "A+B=<10"]) == (True, "")
    assert _equivalent(_dumped(answer, "Bp", "Cb", ["B"]), ["B=<6"]) == (True, "")


@_disagrees("dump/3 raises type_error(callable, <function dump>) in a .pl "
            "program: the name resolves to a Python function, not a builtin",
            error=r"type_error\(callable,<function dump")
def test_dump_3():
    answer = _one(port(_SOLVER, "q_dump", ["A", "B", "Vs", "Cs", "Bp", "Cb"]))
    _check_dump(answer)


def test_dump_3_on_the_oracle():
    [answer] = oracle(_SOLVER_ORACLE, "q_dump", ["A", "B", "Vs", "Cs", "Bp", "Cb"])
    _check_dump(answer)


_DUMP_NONLINEAR = "q_dump_nonlinear(X, V, C) :- {X >= 10}, {sin(Z) > 3}, dump([X], V, C).\n"


def _check_dump_nonlinear(answer):
    # Exact: C = [_A >= 10] (clp(r) prints 10.0), and {X >= 10} stays.
    assert "X" not in answer.bindings
    assert _equivalent(_dumped(answer, "V", "C", ["X"]), ["X>=10"]) == (True, "")


@_disagrees("sin/1 in {}: the .pl front end lowers only + - * / "
            "(iso_l3.py _clpq_expr) and refuses the program at load",
            error=r"is not a linear arithmetic expression")
def test_dump_3_of_a_nonlinear_store():
    answer = _one(port(_DUMP_NONLINEAR, "q_dump_nonlinear", ["X", "V", "C"]))
    _check_dump_nonlinear(answer)


def test_dump_3_of_a_nonlinear_store_on_the_oracle():
    [answer] = oracle(_DUMP_NONLINEAR, "q_dump_nonlinear", ["X", "V", "C"])
    _check_dump_nonlinear(answer)


# ---- Unification, Feedback and Bindings --------------------------------------

_UNIFICATION = """
q_two_solvers(Aq, Bq) :- {Aq+Bq = 10}, Aq = Bq.
q_bound_after(A, B, C) :- {2*A+3*B = C/2}, C = 10, A = B.
q_bound_inside(A, B, C) :- {2*A+3*B = C/2, C = 10, A = B}.
q_feedback(A, B, C) :- {A-B+C = 10, C = 5+5}.
q_unification(Aq, Bq, A1, B1, C1, A2, B2, C2) :-
    q_two_solvers(Aq, Bq), q_bound_after(A1, B1, C1),
    q_bound_inside(A2, B2, C2), \\+ (X = 3.0+1.0, X = 4.0).
q_float_binding(A, B, C) :- {2*A+3*B = C/2}, C = 10.0, A = B.
"""


def test_unification():
    # Exact.  The clp(q) half of `clpr:{Ar+Br=10}, Ar=Br, clpq:{Aq+Bq=10},
    # Aq=Bq`: Aq = Bq = 5.  `{2*A+3*B=C/2}, C=rat(10,1), A=B` and the same
    # inside the braces: A = B = 1, C = 10 (clp(r)'s 0.9999999999999999 is
    # rounding; the value is 1).  `X=3.0+1.0, X=4.0`: no.
    variables = ["Aq", "Bq", "A1", "B1", "C1", "A2", "B2", "C2"]
    answer = _one(port(_UNIFICATION, "q_unification", variables))
    _is(answer, {"Aq": 5, "Bq": 5, "A1": 1, "B1": 1, "C1": 10,
                 "A2": 1, "B2": 1, "C2": 10}, [])
    _agree([answer], oracle(_UNIFICATION, "q_unification", variables))


def test_feedback():
    # Exact: B = A, C = 10.
    variables = ["A", "B", "C"]
    answer = _one(port(_UNIFICATION, "q_feedback", variables))
    _is(answer, {"C": 10}, ["A=B"])
    _agree([answer], oracle(_UNIFICATION, "q_feedback", variables))


def test_a_float_binding_is_a_type_error():
    # clp(q): {TYPE ERROR: _=10.0 - arg 2: expected 'a rational number',
    # found 10.0}.  (The oracle computes with the float instead: A = B =
    # 0.9999999999999999, C = 10.0.)
    with pytest.raises(RuntimeError, match=r"type_error\(rational,10\.0\)"):
        port(_UNIFICATION, "q_float_binding", ["A", "B", "C"])


# ---- Linearity and Nonlinear Residues ------------------------------------------

def test_a_nonlinear_equation_that_is_linear():
    # Exact: {(X+Y)*(Y+X)/X = Y*Y/X+99} is {Y = 49.5 - 0.5*X}.
    program = "q_nonlinear(X, Y) :- {(X+Y)*(Y+X)/X = Y*Y/X+99}.\n"
    answer = _one(port(program, "q_nonlinear", ["X", "Y"]))
    _is(answer, {}, ["Y=99/2-1/2*X"])
    _agree([answer], oracle(program, "q_nonlinear", ["X", "Y"]))


def _unbound(*names):
    def check(answer, side):
        assert not set(names) & set(answer.bindings), answer
    return check


def _residuates(*names):
    """Unbound, and (on the port) a residual is shown; the oracle's dump
    drops the nonlinear residue, so it shows none."""
    def check(answer, side):
        _unbound(*names)(answer, side)
        if side == "port":
            assert answer.residual, answer
    return check


def _near(name, documented):
    def check(answer, side):
        _close(answer.bindings[name], documented)
    return check


def _equal(**values):
    def check(answer, side):
        for name, value in values.items():
            assert _exact(answer.bindings[name]) == value, (name, answer)
    return check


def _both(*checks):
    def check(answer, side):
        for each in checks:
            each(answer, side)
    return check


def _square_residue(answer, side):
    # {exp(X+Y+1,2) = 3*X*X+Y*Y} residuates as
    # {Y*2 - X^2*2 + Y*X*2 + X*2 + 1 = 0}, exact.
    _unbound("X", "Y")(answer, side)
    if side == "port":
        assert _equivalent(answer.residual,
                           ["Y*2-X^2*2+Y*X*2+X*2+1=0"]) == (True, "")


#: (id, goal, shown variables, check): the chapter's nonlinear queries.
#: Floats are clp(r)'s and compared within REL; 1, 1/4 are exact.
_NONLINEAR = [
    ("sin_equals_cos", "{sin(X) = cos(X)}", ["X"], _residuates("X")),
    ("sin_cos_equation", "{sin(cos(X)) = 1/2}", ["X"],
     _near("X", 1.0197267436954502)),
    ("sin_cos_inequation", "{sin(cos(X)) < 1/2}", ["X"], _residuates("X")),
    ("sin_quotient", "{sin(X+2+2)/sin(4+X) = Y}", ["X", "Y"],
     _both(_unbound("X"), _equal(Y=1))),
    ("square_residue", "{exp(X+Y+1,2) = 3*X*X+Y*Y}", ["X", "Y"], _square_residue),
    ("square_collapses", "{exp(X+Y+1,2) = 3*X*X+Y*Y}, X = Y", ["X", "Y"],
     _equal(X=Fraction(-1, 4), Y=Fraction(-1, 4))),
    ("pow_exponent", "{12 = pow(2,X)}", ["X"], _near("X", 3.5849625007211565)),
    ("pow_base", "{12 = pow(X,3.585)}", ["X"], _near("X", 1.9999854993443926)),
    ("pow_value", "{X = pow(2,3.585)}", ["X"], _near("X", 12.000311914286545)),
    ("sin_inverse", "{1/2 = sin(X)}", ["X"], _near("X", 0.5235987755982989)),
]


def _nonlinear_program(goal, variables):
    return f"q_nonlinear({', '.join(variables)}) :- {goal}.\n"


@pytest.mark.parametrize(
    "goal, variables, check",
    [pytest.param(goal, variables, check, id=name) for name, goal, variables, check
     in _NONLINEAR])
@_disagrees("sin/cos/pow/exp in {}: the .pl front end lowers only + - * / "
            "(iso_l3.py _clpq_expr) and refuses the program at load; the "
            "oracle answers each",
            error=r"is not a linear arithmetic expression")
def test_nonlinear(goal, variables, check):
    answer = _one(port(_nonlinear_program(goal, variables), "q_nonlinear", variables))
    check(answer, "port")


@pytest.mark.parametrize(
    "goal, variables, check",
    [pytest.param(goal, variables, check, id=name) for name, goal, variables, check
     in _NONLINEAR])
def test_nonlinear_on_the_oracle(goal, variables, check):
    [answer] = oracle(_nonlinear_program(goal, variables), "q_nonlinear", variables)
    check(answer, "oracle")


# ---- Numerical Precision and Rationals: root and e ---------------------------

@pytest.mark.parametrize("program, predicate", [
    pytest.param(0, "root(0, S, R) :- !", id="root"),
    pytest.param(1, "inv_e_series", id="e"),
])
def test_root_and_e_need_cut(program, predicate):
    # root/3 (Newton's sqrt(2): root(3..7, R) and print_decimal/2) and
    # inv_e_series/5 (e(1000, E)) commit with a cut.
    block = _blocks(example_file(MANUAL).read_text())["root"][program]
    assert predicate in block and "!" in block
    pytest.skip("its clauses use cut (!): Clausal is cut-free, so this "
                "waits for the cut series")


# ---- Projection: mg and ordering/1 -------------------------------------------

_MG_QUERIES = """
q_mg(P, B, Mp) :- mg(P, 12, 0.01, B, Mp).
q_ordering_mp(Mp, P, B) :- mg(P, 12, 0.01, B, Mp), ordering([Mp]).
q_ordering_mp_p(Mp, P, B) :- mg(P, 12, 0.01, B, Mp), ordering([Mp, P]).
q_ordering_b_mp(B, Mp, P) :- ordering(B < Mp), mg(P, 12, 0.01, B, Mp).
q_ordering_p_mp(P, B, Mp) :-
    ordering(B < Mp), mg(P, 12, 0.01, B, Mp), ordering(P < Mp).
"""


def _mg(oracle_copy=False):
    queries = _MG_QUERIES.replace("0.01", "1/100") if oracle_copy else _MG_QUERIES
    return _manual_program("mg") + queries


def _check_mg_relation(answer, defined, documented):
    """One equality over P, B, Mp; solved for *defined*, each coefficient
    within REL of the manual's (clp(r) floats)."""
    assert answer.bindings == {}
    [constraint] = answer.residual
    coefficients, constant = _solved_for(constraint, defined)
    assert constant == 0
    assert set(coefficients) == set(documented), (coefficients, documented)
    for name, value in documented.items():
        _close(coefficients[name], value)


def test_mg():
    # mg(P,12,0.01,B,Mp): {B = 1.1268250301319698*P - 12.682503013196973*Mp},
    # within REL.  Exactly, from the program: B = 1.01^12*P - (1.01^12-1)/0.01*Mp.
    answer = _one(port(_mg(), "q_mg", ["P", "B", "Mp"]))
    _check_mg_relation(answer, "B", {"P": 1.1268250301319698,
                                     "Mp": -12.682503013196973})
    growth = Fraction(101, 100) ** 12
    assert _solved_for(answer.residual[0], "B") == \
        ({"P": growth, "Mp": -(growth - 1) * 100}, 0)
    _agree([answer], oracle(_mg(oracle_copy=True), "q_mg", ["P", "B", "Mp"]))


#: The ordering/1 queries: the variable the manual's answer defines, and its
#: coefficients (clp(r) floats, within REL).
#: The shown variables (the query's head) are listed in the order of the
#: manual's answer: the oracle's dump/3 orders its targets as listed, so
#: [P, B, Mp] with ordering([Mp, P]) would raise
#: system_error(unsatisfiable_ordering) there.
_ORDERINGS = [
    ("q_ordering_mp", ["Mp", "P", "B"], "Mp",
     {"B": -0.0788487886783417, "P": 0.08884878867834171}),
    ("q_ordering_mp_p", ["Mp", "P", "B"], "Mp",
     {"P": 0.08884878867834171, "B": -0.0788487886783417}),
    ("q_ordering_b_mp", ["B", "Mp", "P"], "B",
     {"Mp": -12.682503013196973, "P": 1.1268250301319698}),
    ("q_ordering_p_mp", ["P", "B", "Mp"], "P",
     {"B": 0.8874492252651537, "Mp": 11.255077473484631}),
]


@pytest.mark.parametrize("query, variables, defined, documented",
                         [pytest.param(*row, id=row[0][2:]) for row in _ORDERINGS])
@_disagrees("ordering/1 is not a .pl builtin: existence_error(procedure, "
            "ordering/1) (holzbaur.ordering exists, unregistered)",
            error=r"existence_error\(procedure,ordering/1\)")
def test_ordering(query, variables, defined, documented):
    # The relation, and which variable it defines: ordering/1's effect.
    answer = _one(port(_mg(), query, variables))
    _check_mg_relation(answer, defined, documented)
    assert _sides(answer.residual[0])[0] == defined, answer


@pytest.mark.parametrize("query, variables, defined, documented",
                         [pytest.param(*row, id=row[0][2:]) for row in _ORDERINGS])
def test_ordering_on_the_oracle(query, variables, defined, documented):
    # The relation and the variable it defines.  The oracle's target order
    # (the listed variables) is an ordering too, so the defined variable is
    # not ordering/1's alone here; the port test is the one that tells.
    [answer] = oracle(_mg(oracle_copy=True), query, variables)
    _check_mg_relation(answer, defined, documented)
    assert _sides(answer.residual[0])[0] == defined, answer


# ---- Turning Answers into Terms -------------------------------------------------

_TERMS = """
q_store(A, B, C, D, E) :- {2*A+B+C = 10, C-D = E, A < 10}.
q_dump_names(A, B, C, D, E, Cs) :-
    {2*A+B+C = 10, C-D = E, A < 10}, dump([A,B,C,D,E], [a,b,c,d,e], Cs).
q_call_residue(A, B, C, D, E, Cs) :-
    call_residue({2*A+B+C = 10, C-D = E, A < 10}, Cs).
"""
#: The top-level answer the manual prints for the store (exact).
_STORE = ["C=10-2*A-B", "E=10-2*A-B-D", "A<10"]


def test_the_store():
    variables = ["A", "B", "C", "D", "E"]
    answer = _one(port(_TERMS, "q_store", variables))
    _is(answer, {}, _STORE)
    _agree([answer], oracle(_TERMS, "q_store", variables))


def _check_dump_names(answer):
    # Cs over the names a..e is the store.  The manual prints
    # [e<10.0, a=10.0-c-d-2.0*e, b=c+d], which is the store under the
    # renaming a->B, b->C, c->E, e->A, not under a->A ... e->E: a misprint
    # (its top-level answer in the same reply is the store as named).  The
    # test takes the definition's reading (the oracle's).
    _is(answer, {"Cs": answer.bindings["Cs"]}, _STORE)
    assert _equivalent(_list(answer.bindings["Cs"]),
                       [c.lower() for c in _STORE]) == (True, "")


@_disagrees("dump/3 raises type_error(callable, <function dump>) in a .pl "
            "program: the name resolves to a Python function, not a builtin",
            error=r"type_error\(callable,<function dump")
def test_dump_3_with_atoms_for_names():
    answer = _one(port(_TERMS, "q_dump_names", ["A", "B", "C", "D", "E", "Cs"]))
    _check_dump_names(answer)


def test_dump_3_with_atoms_for_names_on_the_oracle():
    [answer] = oracle(_TERMS, "q_dump_names", ["A", "B", "C", "D", "E", "Cs"])
    _check_dump_names(answer)


@_disagrees("call_residue/2 does not exist: existence_error(procedure, "
            "call_residue/2) (Scryer has no call_residue/2 either, so there is "
            "no oracle answer)",
            error=r"existence_error\(procedure,call_residue/2\)")
def test_call_residue():
    # [[A]-{A<10.0}, [B]-{B=10.0-2.0*A-C}, [D]-{D=C-E}]: together, the
    # store (exact).
    answer = _one(port(_TERMS, "q_call_residue", ["A", "B", "C", "D", "E", "Cs"]))
    groups = _list(answer.bindings["Cs"])
    assert len(groups) == 3, groups
    constraints = [c for group in groups
                   for inner in re.findall(r"\{([^{}]*)\}", group)
                   for c in _list(f"[{inner}]")]
    assert _equivalent(constraints, ["A<10", "B=10-2*A-C", "D=C-E"]) == (True, "")


# ---- Projecting Inequalities: eliminat and elimination ---------------------------

_ELIMINATION = """
q_eliminat(X0, X1, X2, X3, X4) :- example(2, [X0,X1,X2,X3,X4]).
q_shadow(X0, X1) :- example(2, [X0,X1|_]).
q_hull(X, Y) :- conv_hull([[1,1], [2,0], [3,0], [1,2], [2,2]], [X, Y]).
"""


def _elimination():
    return _manual_program("eliminat", "elimination") + _ELIMINATION


def test_eliminat_example_2():
    # Exact: the nine non-redundant inequalities of the eighteen.
    documented = [
        "X0-2/17*X1-35/68*X2-X3-35/68*X4>=5/4",
        "X0-73/93*X1+91/93*X2-1/93*X3+23/93*X4=< -29/31",
        "X0-29/25*X1+1/50*X2-57/50*X3-2/5*X4>= -3/25",
        "X0+7/39*X1+62/39*X2+18/13*X3-2/3*X4=< -9/13",
        "X0+2/19*X1-64/95*X2-4/5*X3+24/95*X4>= -33/95",
        "X0+2/3*X1-38/45*X2-53/90*X3+4/15*X4=< -34/45",
        "X0-23/49*X1-31/49*X2-76/49*X3+27/49*X4=<3/49",
        "X0+44/81*X1-19/81*X2+22/81*X3+73/81*X4>=17/81",
        "X0+9/43*X1-14/43*X2-27/43*X3-40/43*X4>= -39/43",
    ]
    variables = ["X0", "X1", "X2", "X3", "X4"]
    answer = _one(port(_elimination(), "q_eliminat", variables))
    _is(answer, {}, documented)
    assert len(answer.residual) == 9
    _agree([answer], oracle(_elimination(), "q_eliminat", variables))


def test_eliminat_projection_onto_x0_x1():
    # Exact: the shadow in the X0, X1 plane, five inequalities.
    documented = [
        "X0+2619277/17854273*X1>= -851123/17854273",
        "X0+6429953/16575801*X1=< -12749681/16575801",
        "X0+19130/1213083*X1>=795400/404361",
        "X0-1251619/3956679*X1>=21101146/3956679",
        "X0+601502/4257189*X1>=220850/473021",
    ]
    answer = _one(port(_elimination(), "q_shadow", ["X0", "X1"]))
    _is(answer, {}, documented)
    assert len(answer.residual) == 5
    _agree([answer], oracle(_elimination(), "q_shadow", ["X0", "X1"]))


def test_convex_hull():
    # Exact: the hull of the five points.
    answer = _one(port(_elimination(), "q_hull", ["X", "Y"]))
    _is(answer, {}, ["Y=<2", "X+1/2*Y=<3", "X>=1", "Y>=0", "X+Y>=2"])
    assert len(answer.residual) == 5
    _agree([answer], oracle(_elimination(), "q_hull", ["X", "Y"]))


# ---- Why Disequations: squares ----------------------------------------------------

_SQUARES = """
q_one_square(A, C1) :- filled_rectangle(A, [C1]).
q_nine_squares(A, C1, C2, C3, C4, C5, C6, C7, C8, C9) :-
    filled_rectangle(A, [C1, C2, C3, C4, C5, C6, C7, C8, C9]).
q_up_to_nine_squares(A, Squares) :-
    between(1, 9, N), length(Squares, N), filled_rectangle(A, Squares).
"""
_NINE = [f"C{i}" for i in range(1, 10)]
#: The answers the manual prints for filled_rectangle(A, Squares), in order
#: (exact).
_TILINGS = [
    (1, [1]),
    (Fraction(33, 32), [Fraction(n, 32) for n in (15, 18, 8, 7, 4, 14, 1, 10, 9)]),
    (Fraction(69, 61), [Fraction(n, 61) for n in (33, 36, 28, 5, 2, 9, 25, 7, 16)]),
]


def _squares():
    return _manual_program("squares") + _SQUARES


def test_filled_rectangle_first_answer():
    # filled_rectangle(A, Squares)'s first answer: A = 1, Squares = [1].
    answer = _one(port(_squares(), "q_one_square", ["A", "C1"]))
    _is(answer, {"A": 1, "C1": 1}, [])
    _agree([answer], oracle(_squares(), "q_one_square", ["A", "C1"]))


@pytest.mark.skipif(os.environ.get("CLAUSAL_SLOW_TESTS") != "1",
                    reason="about 3 minutes (port and oracle), set CLAUSAL_SLOW_TESTS=1")
def test_filled_rectangle_with_nine_squares():
    # length(Squares, 9), filled_rectangle(A, Squares): eight solutions, the
    # first two as printed (exact).
    variables = ["A"] + _NINE
    start = time.perf_counter()
    got = port(_squares(), "q_nine_squares", variables)
    print(f"filled_rectangle, 9 squares, from the manual's program: port "
          f"{time.perf_counter() - start:.1f} s")
    assert len(got) == 8
    for answer, (width, squares) in zip(got, _TILINGS[1:]):
        assert answer.bindings["A"] == width
        assert [answer.bindings[c] for c in _NINE] == squares
    _agree(got, oracle(_squares(), "q_nine_squares", variables, timeout=600))


@pytest.mark.skipif(os.environ.get("CLAUSAL_SLOW_TESTS") != "1",
                    reason="about 80 s on the port, set CLAUSAL_SLOW_TESTS=1")
def test_filled_rectangle_first_three_answers():
    # filled_rectangle(A, Squares) with Squares unbound enumerates the lists
    # by length (distinct_squares/1 builds them), so its answers up to nine
    # squares are those of between(1, 9, N), length(Squares, N), ...: the
    # manual prints the first three (exact).
    start = time.perf_counter()
    got = port(_squares(), "q_up_to_nine_squares", ["A", "Squares"])
    print(f"filled_rectangle, 1 to 9 squares: port "
          f"{time.perf_counter() - start:.1f} s")
    assert len(got) == 9
    for answer, (width, squares) in zip(got, _TILINGS):
        assert answer.bindings["A"] == width
        assert [_exact(_value(s)) for s in _list(answer.bindings["Squares"])] \
            == squares


# ---- Monash Examples: the mortgage, go2 to go4 ------------------------------------

_MONASH = """
q_go2(P, MP) :- monash_mg(P, 120, 0.01, 0, MP).
q_go3(P, B, MP) :- monash_mg(P, 120, 0.01, B, MP).
q_go4(Int) :- monash_mg(999, 3, Int, 0, 400).
"""


def _monash(oracle_copy=False):
    port_clauses, oracle_clauses = _monash_mortgage()
    if oracle_copy:
        return oracle_clauses + _MONASH.replace("0.01", "1/100")
    return port_clauses + _MONASH


def test_monash_go2():
    # mg(P,120,0.01,0,MP), dump([P,MP]): {P = 69.7005220313972*MP}, within
    # REL.  dump/1 is the Monash compatibility package's printer; the
    # top-level answer is the same projection onto P, MP.
    answer = _one(port(_monash(), "q_go2", ["P", "MP"]))
    assert answer.bindings == {}
    [constraint] = answer.residual
    coefficients, constant = _solved_for(constraint, "P")
    assert constant == 0 and set(coefficients) == {"MP"}
    _close(coefficients["MP"], 69.7005220313972)
    _agree([answer], oracle(_monash(oracle_copy=True), "q_go2", ["P", "MP"]))


def test_monash_go3():
    # mg(P,120,0.01,B,MP), dump([P,B,MP]):
    # {P = 0.30299477968602706*B + 69.7005220313972*MP}, within REL.
    answer = _one(port(_monash(), "q_go3", ["P", "B", "MP"]))
    assert answer.bindings == {}
    [constraint] = answer.residual
    coefficients, constant = _solved_for(constraint, "P")
    assert constant == 0 and set(coefficients) == {"B", "MP"}
    _close(coefficients["B"], 0.30299477968602706)
    _close(coefficients["MP"], 69.7005220313972)
    _agree([answer], oracle(_monash(oracle_copy=True), "q_go3", ["P", "B", "MP"]))


#: What the manual prints for go4 (clp(r)'s 400.0, 599.0, 999.0 are the
#: program's integers), the internal _A, _B existential.
_GO4_DOCUMENTED = ["_B-_B*Int+_A+400=0", "_A-_A*Int+400=0", "_B=599+999*Int"]


@_disagrees("the manual's go4 residual is not the program's relation: z3 "
            "finds Int = -0.69649... satisfies it, while the port's (and the "
            "program's) 999*(1+Int)^3 - 400*(1+Int)^2 - 400*(1+Int) - 400 = 0 "
            "has the one real root 0.09757...; its _B = 599+999*Int is "
            "999*(1+Int)-400, but the next two signs of Int are flipped")
def test_monash_go4_as_documented():
    answer = _one(port(_monash(), "q_go4", ["Int"]))
    _is(answer, {}, _GO4_DOCUMENTED)


def test_monash_go4():
    # mg(999, 3, Int, 0, 400) with the interest unknown: a cubic in Int.
    # Exact, from the program (not the manual, see the test above):
    # P1 = 999*(1+Int) - 400, P2 = P1*(1+Int) - 400, 0 + 400 = P2*(1+Int).
    # The oracle answers once with Int unbound; its dump/3 drops the
    # nonlinear residue, so it has no residual to compare.
    answer = _one(port(_monash(), "q_go4", ["Int"]))
    _is(answer, {}, ["999*(1+Int)^3-400*(1+Int)^2-400*(1+Int)-400=0"])
    [answer] = oracle(_monash(oracle_copy=True), "q_go4", ["Int"])
    assert answer.bindings == {}


# ---- A Mixed Integer Linear Optimization Example: flugpl ---------------------------

_FLUGPL = """
q_relaxed(Inf) :- example(flugpl, Obj, _, _, _), inf(Obj, Inf).
q_bb_inf_3(Inf) :- example(flugpl, Obj, _, Ints, _), bb_inf(Ints, Obj, Inf).
q_bb_inf_5(Inf, Vertex) :-
    example(flugpl, Obj, _, Ints, _), bb_inf(Ints, Obj, Inf, Vertex, 0.001).
"""
_FLUGPL_INF = 1201500
_FLUGPL_VERTEX = [75, 70, 70, 60, 60, 0, 12, 7, 16, 6, 6]


def _flugpl(oracle_copy=False):
    program = _manual_program("mip")
    assert program.count("0.9*") == 5
    if oracle_copy:
        program = program.replace("0.9*", "9/10*")
    return program + _FLUGPL


def test_flugpl_relaxed_infimum():
    # inf(Obj, Inf): Inf = 1167185.7255923203, within REL.  The rational is
    # 11429082625/9792, the value the 1.3.3 examples file documents for its
    # copy of flugpl (test_examples.py, Z9).
    answer = _one(port(_flugpl(), "q_relaxed", ["Inf"]))
    _close(answer.bindings["Inf"], 1167185.7255923203)
    assert answer.bindings["Inf"] == Fraction(11429082625, 9792)
    _agree([answer], oracle(_flugpl(oracle_copy=True), "q_relaxed", ["Inf"]))


def test_flugpl_bb_inf_3():
    # The manual's bb_inf/5 infimum, through bb_inf/3 (which, the manual
    # says, is bb_inf/5 with Eps = 0.001): Inf = 1201500.0000000005 in
    # clp(r), exactly 1201500 (miplib's BEST SOLN).
    answer = _one(port(_flugpl(), "q_bb_inf_3", ["Inf"]))
    assert _exact(answer.bindings["Inf"]) == _FLUGPL_INF
    _agree([answer], oracle(_flugpl(oracle_copy=True), "q_bb_inf_3", ["Inf"]))


def _check_bb_inf_5(answer):
    # Exact: Inf = 1201500 and the integral Vertex for Ints, in order.
    assert _exact(answer.bindings["Inf"]) == _FLUGPL_INF
    assert [_exact(_value(v)) for v in _list(answer.bindings["Vertex"])] \
        == _FLUGPL_VERTEX


@_disagrees("bb_inf/5 is not a .pl builtin: existence_error(procedure, "
            "bb_inf/5); only bb_inf/3 is registered (builtins/constraints.py), "
            "though branch_and_bound.py implements the /5 form",
            error=r"existence_error\(procedure,bb_inf/5\)")
def test_flugpl_bb_inf_5():
    answer = _one(port(_flugpl(), "q_bb_inf_5", ["Inf", "Vertex"]))
    _check_bb_inf_5(answer)


def test_flugpl_bb_inf_5_on_the_oracle():
    [answer] = oracle(_flugpl(oracle_copy=True), "q_bb_inf_5", ["Inf", "Vertex"])
    _check_bb_inf_5(answer)


# ---- Asserting with Constraints ---------------------------------------------------

@_disagrees("an asserted clause loses the constraint on its variable: "
            "{A < 10}, assertz(p(A)), p(X) answers true with X unconstrained "
            "(Scryer's oracle does the same)")
def test_asserting_with_constraints():
    # {A < 10}, assert(p(A)), then p(X): {X < 10} (exact).
    program = ":- dynamic(p/1).\nq_assert(X) :- {A < 10}, assertz(p(A)), p(X).\n"
    answer = _one(port(program, "q_assert", ["X"]))
    _is(answer, {}, ["X<10"])


# ---- What the chapter shows that is not run ----------------------------------------

@pytest.mark.parametrize("reason", [
    pytest.param("needs clp(r) and clp(q) loaded side by side, and the port "
                 "is clp(Q) alone (the clp(q) half of `clpr:{Ar+Br=10}, Ar=Br, "
                 "clpq:{Aq+Bq=10}, Aq=Bq` is in test_unification)",
                 id="clpr_and_clpq_together"),
    pytest.param("the manual elides its answer (`polynomial continues for a "
                 "few pages`), so there is nothing to compare",
                 id="exp_15th_power"),
    pytest.param("mg's store before projection is an illustration, not a "
                 "query; the projected answer is test_mg", id="mg_unprojected"),
    pytest.param("library('clpqr/expand') (the eval-quote sugar, `2+2=X` "
                 "gives X = 4.0) is not among the 1.3.3 clp(q) sources the "
                 "port ports", id="expand"),
    pytest.param("rkf45's program is not in the chapter, and the manual says "
                 "clp(Q) runs out of memory on it", id="monash_rkf45"),
])
def test_not_run(reason):
    pytest.skip(reason)


# ---- CLAUSAL_REQUIRE_CLPQ_EXAMPLES -----------------------------------------------

def test_a_missing_example_file_fails_when_required(tmp_path):
    # One test from each of the three files that read the example files,
    # with CLAUSAL_CLPQ_EXAMPLES_DIR an empty directory: skipped, and with
    # CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1, failed.
    here = "tests/clpq_port/"
    tests = [here + "test_examples.py::test_the_cut_free_subset_is_found",
             here + "test_acceptance.py::test_one_square_is_the_trivial_rectangle",
             here + "test_manual_examples.py::test_mg"]
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def run(require):
        environment = dict(os.environ, CLAUSAL_CLPQ_EXAMPLES_DIR=str(tmp_path))
        environment.pop("CLAUSAL_REQUIRE_CLPQ_EXAMPLES", None)
        if require:
            environment["CLAUSAL_REQUIRE_CLPQ_EXAMPLES"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-rsf", "-p", "no:cacheprovider",
             *tests], cwd=root, env=environment, capture_output=True, text=True,
            timeout=300)

    skipped = run(require=False)
    assert skipped.returncode == 0, skipped.stdout
    assert "3 skipped" in skipped.stdout, skipped.stdout
    failed = run(require=True)
    assert failed.returncode == 1, failed.stdout
    assert "3 failed" in failed.stdout, failed.stdout
    assert failed.stdout.count("CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1 and") >= 3, \
        failed.stdout
