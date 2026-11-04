"""Evaluating a CYCLIC arithmetic term, row by row against Scryer.

There is no occurs check, so ``X = X+1`` builds a rational tree, and asking
``Y is X`` evaluates an infinite expression.  The evaluator used to recurse
until Python's recursion limit and answer ``resource_error(stack)``; Scryer
answers ``type_error(evaluable, (+)/2)``.  Operator ruling 2026-11-04: "type_error
if Scryer gives one" -- for the ARITHMETIC EVALUATOR (ISO ``is/2`` and the
comparisons in ``.pl``/``.clausal``, the seam's ``eval_/2``), not the seam's
``is``, which is unification.

Scryer's rule, read off the rows: the culprit is the term at which a
left-to-right descent first RE-ENTERS a term it is already inside -- the
term the cycle closes on -- named ``Name/Arity``.  ``X = 1+X, Y is X*2``
names ``(+)/2`` (the cycle closes on X's value, below the root ``*``);
``X = X+1, Y is X`` names the root.  A non-evaluable compound that holds a
cycle (``X = 1+f(X)``, ``Y = Y+1, X = f(Y)``) is descended into before it is
refused, so the cycle is reported, not ``f/1``.

Scryer gives those answers for goals in a consulted CLAUSE, which is what
these rows run.  Put to its TOPLEVEL, a term whose cycle closes below the
root of the expression answers ``instantiation_error`` instead (though no
variable is unbound): ``test_scryer_toplevel_differs`` pins that
inconsistency, which looks like a Scryer bug.

Errors met BEFORE the cycle are unchanged: an unbound variable or a
non-evaluable atom to its left is reported as for an acyclic term
(``X = Z+X`` -- instantiation_error; ``X = a+X`` -- ``a/0``).  The context is
``(is)/2`` for the comparisons too, as Scryer reports it and as the engine
already did for every other arithmetic error (``iso_compare._arith_cmp``).

Each row is one clause run under the native ``.pl`` front end, under the
``.clausal`` front end (the same text: the helper is cut-free), and -- the
oracle half -- under Scryer.  The seam rows put the same shapes to
``eval_/2`` (built with the seam's ``is``, which unifies).
"""
from __future__ import annotations

import os
import re

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from clausal.terms import term_writeq

from tests._oracles import run_scryer
from tests._suffix import SEAM

_TE = "type_error(evaluable,{})-(is)/2"
_INST = "instantiation_error-(is)/2"

# (row, goal, Scryer's answer, the engine's answer when it differs)
ROWS = [
    # -- the cycle closes on the root: Scryer's type_error, matched --
    ("r1", "X = X+1, _ is X", _TE.format("(+)/2"), None),
    ("r2", "X = X+1, X =:= 1", _TE.format("(+)/2"), None),
    ("r3", "X = X+1, X < 1", _TE.format("(+)/2"), None),
    ("r4", "X = f(X), _ is X", _TE.format("f/1"), None),
    ("r5", "X = -(X), _ is X", _TE.format("(-)/1"), None),
    ("r6", "X = max(X,1), _ is X", _TE.format("max/2"), None),
    ("r7", "X = 1+X, _ is X", _TE.format("(+)/2"), None),
    ("r8", "X = X*2, _ is X", _TE.format("(*)/2"), None),
    ("r9", "X = 2*X, _ is X", _TE.format("(*)/2"), None),
    ("r10", "X = X/2, _ is X", _TE.format("(/)/2"), None),
    ("r11", "X = 2/X, _ is X", _TE.format("(/)/2"), None),
    ("r12", "X = X**2, _ is X", _TE.format("(**)/2"), None),
    ("r13", "X = 2**X, _ is X", _TE.format("(**)/2"), None),
    ("r14", "X = X^2, _ is X", _TE.format("(^)/2"), None),
    ("r15", "X = 2^X, _ is X", _TE.format("(^)/2"), None),
    ("r16", "X = X mod 2, _ is X", _TE.format("(mod)/2"), None),
    ("r17", "X = 2 mod X, _ is X", _TE.format("(mod)/2"), None),
    ("r18", "X = min(X,1), _ is X", _TE.format("min/2"), None),
    ("r19", "X = min(1,X), _ is X", _TE.format("min/2"), None),
    ("r20", "X = abs(X), _ is X", _TE.format("abs/1"), None),
    ("r21", "X = sin(X), _ is X", _TE.format("sin/1"), None),
    ("r22", "X = -(1,X), _ is X", _TE.format("(-)/2"), None),
    ("r23", "X = f(g(X)), _ is X", _TE.format("f/1"), None),
    ("r24", "X = f(1,X), _ is X", _TE.format("f/2"), None),
    ("r25", "X = f(X,X), _ is X", _TE.format("f/2"), None),
    ("r26", "X = 1+(X*2), _ is X", _TE.format("(+)/2"), None),
    ("r27", "X = (X*2)+1, _ is X", _TE.format("(+)/2"), None),
    ("r28", "X = 1+(2+(3+X)), _ is X", _TE.format("(+)/2"), None),
    ("r29", "X = max(1, min(X, 2)), _ is X", _TE.format("max/2"), None),
    # a non-evaluable compound ON the cycle: the root, not f/1
    ("r30", "X = 1+f(X), _ is X", _TE.format("(+)/2"), None),
    ("r31", "X = f(X)+1, _ is X", _TE.format("(+)/2"), None),
    # a cycle through two variables
    ("r32", "X = Y+1, Y = X*2, _ is X", _TE.format("(+)/2"), None),
    ("r33", "X = 1+Y, Y = 2*X, _ is X", _TE.format("(+)/2"), None),
    ("r34", "X = Y+1, Y = X+1, _ is Y", _TE.format("(+)/2"), None),
    ("r35", "X = X+Y, Y = Y*2, _ is X", _TE.format("(+)/2"), None),
    # both sides of a comparison cyclic: the left one is evaluated first
    ("r36", "X = X+1, X =:= X", _TE.format("(+)/2"), None),
    ("r37", "X = X+1, Z = Z*2, X =:= Z", _TE.format("(+)/2"), None),
    ("r38", "X = 1+X, Z = Z*2, Z =:= X", _TE.format("(*)/2"), None),
    ("r39", "X = 1+X, Z = 1+Z, X =:= Z", _TE.format("(+)/2"), None),
    ("r40", "X = X+1, 1 =:= X", _TE.format("(+)/2"), None),
    ("r41", "X = X+1, X =\\= 1", _TE.format("(+)/2"), None),
    ("r42", "X = X+1, X >= 1", _TE.format("(+)/2"), None),
    ("r43", "X = X+1, X > 1", _TE.format("(+)/2"), None),
    ("r44", "X = X+1, X =< 1", _TE.format("(+)/2"), None),
    ("r45", "X = X+1, X =:= X+1", _TE.format("(+)/2"), None),
    # -- an error to the LEFT of the cycle comes first, as for any term --
    ("r46", "X = a+X, _ is X", _TE.format("a/0"), None),
    ("r47", "X = X+a, _ is X", _TE.format("(+)/2"), None),
    ("r48", "X = X+_, _ is X", _TE.format("(+)/2"), None),
    ("r49", "X = _+X, _ is X", _INST, None),
    ("r50", "X = 1+(_+X), _ is X", _INST, None),
    # -- the cycle closes BELOW the root: the term it closes on --
    ("b1", "X = 1+X, _ is X*2", _TE.format("(+)/2"), None),
    ("b2", "X = X+1, _ is X*2", _TE.format("(+)/2"), None),
    ("b3", "X = X+1, _ is 2*X", _TE.format("(+)/2"), None),
    ("b4", "X = X+1, _ is X+X", _TE.format("(+)/2"), None),
    ("b5", "X = 1+X, _ is 1+X", _TE.format("(+)/2"), None),
    ("b6", "X = X+1, _ is -X", _TE.format("(+)/2"), None),
    ("b7", "X = X+1, _ is abs(X)", _TE.format("(+)/2"), None),
    ("b8", "X = X+1, _ is truncate(X)", _TE.format("(+)/2"), None),
    ("b9", "X = X+1, _ is X + 0.5", _TE.format("(+)/2"), None),
    ("b10", "X = 1+(2+(3+X)), _ is X+0", _TE.format("(+)/2"), None),
    ("b11", "Y = Y*2, X = 1+Y, _ is X", _TE.format("(*)/2"), None),
    ("b12", "X = X+1, X+1 =:= 1", _TE.format("(+)/2"), None),
    ("b13", "X = X+1, Z = Z*2, X+0 =:= Z", _TE.format("(+)/2"), None),
    ("b14", "X = g(X), _ is X+1", _TE.format("g/1"), None),
    ("b15", "X = f(X), _ is 1+X", _TE.format("f/1"), None),
    ("b16", "X = g(1, X), _ is X+1", _TE.format("g/2"), None),
    # a non-evaluable compound that merely HOLDS a cycle: the cycle
    ("b17", "Y = Y+1, X = f(Y), _ is X", _TE.format("(+)/2"), None),
    # -- the one divergence: a LIST.  Scryer evaluates ``[E]`` as ``E``
    #    (and so reaches the cycle, then names ``[]/0``); the engine
    #    refuses a list as such, cyclic or not --
    ("x1", "X = [X], _ is X", _TE.format("[]/0"), _TE.format("'.'/2")),
]

_PRELUDE = "ev(G, R) :- catch((G, R = yes), error(E, C), R = E-C).\n"
_PROGRAM = _PRELUDE + "".join(f"{n}(R) :- ev(({g}), R).\n" for n, g, _s, _e in ROWS)

_EXPECTED = {n: (e if e is not None else s) for n, _g, s, e in ROWS}
_SCRYER = {n: s for n, _g, s, _e in ROWS}
DIVERGES = sorted(n for n, _g, _s, e in ROWS if e is not None)


def _load(tmp_path_factory, suffix, text, frontend=None):
    path = tmp_path_factory.mktemp("cyclic_eval") / f"cyclic_eval_rows{suffix}"
    path.write_text(text, encoding="utf-8")
    saved = os.environ.get("CLAUSAL_PL_FRONTEND")
    if frontend:
        os.environ["CLAUSAL_PL_FRONTEND"] = frontend
    try:
        return _load_module(f"_cyclic_eval_rows_{suffix.lstrip('.')}", str(path))
    finally:
        if saved is None:
            os.environ.pop("CLAUSAL_PL_FRONTEND", None)
        else:
            os.environ["CLAUSAL_PL_FRONTEND"] = saved


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    return _load(tmp_path_factory, ".pl", _PROGRAM, frontend="native")


@pytest.fixture(scope="module")
def clausal_mod(tmp_path_factory):
    return _load(tmp_path_factory, ".clausal", _PROGRAM)


def _answer(mod, name) -> str:
    r = Var()
    try:
        answers = [term_writeq(_deref_walk(r)) for _ in solve((name, r), mod)]
    except LogicException as exc:
        pytest.fail(f"{name}: uncaught {exc}")
    assert len(answers) == 1, (name, answers)
    return answers[0]


_IDS = [r[0] for r in ROWS]


@pytest.mark.parametrize("name", _IDS)
def test_cyclic_eval_pl(pl_mod, name):
    assert _answer(pl_mod, name) == _EXPECTED[name]


@pytest.mark.parametrize("name", _IDS)
def test_cyclic_eval_clausal(clausal_mod, name):
    assert _answer(clausal_mod, name) == _EXPECTED[name]


@pytest.fixture(scope="module")
def scryer_answers(tmp_path_factory):
    path = tmp_path_factory.mktemp("cyclic_eval_scryer") / "rows.pl"
    path.write_text(_PROGRAM + "row_in(X, [X|_]).\nrow_in(X, [_|T]) :- row_in(X, T).\n",
                    encoding="utf-8")
    names = ", ".join(_IDS)
    goal = (f"( row_in(N, [{names}]), call(N, R), writeq(N = R), nl, fail "
            "; true ), halt.")
    proc = run_scryer(str(path), [goal], timeout=120)
    out = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"\s*(\w+)\s*=\s*(.*)$", line)
        if m and m.group(1) in _SCRYER:
            out[m.group(1)] = m.group(2)
    assert out, (proc.stdout[-500:], proc.stderr[-500:])
    return out


@pytest.mark.parametrize("name", _IDS)
def test_cyclic_eval_scryer(scryer, scryer_answers, name):
    """Scryer's own answer, so a Scryer change shows up as a failing row."""
    del scryer
    assert scryer_answers.get(name) == _SCRYER[name]


def test_the_rows_that_diverge_from_scryer_are_the_listed_ones():
    """The engine departs from Scryer (in a clause) only on a list."""
    assert DIVERGES == ["x1"]


# Scryer's TOPLEVEL answers instantiation_error where its clauses answer
# the type_error above: the same goal, built at the toplevel.
_TOPLEVEL_ROWS = [
    ("b1", "X = 1+X, catch(_ is X*2, E, true), writeq(E), nl.",
     "error(instantiation_error,(is)/2)"),
    ("b1_built", "X = 1+X, Y = X*2, catch(_ is Y, E, true), writeq(E), nl.",
     "error(instantiation_error,(is)/2)"),
    ("r1", "X = X+1, catch(_ is X, E, true), writeq(E), nl.",
     "error(type_error(evaluable,(+)/2),(is)/2)"),
]


@pytest.mark.parametrize("name,goal,expected", _TOPLEVEL_ROWS,
                         ids=[r[0] for r in _TOPLEVEL_ROWS])
def test_scryer_toplevel_differs(scryer, name, goal, expected):
    """Pinned so a Scryer fix shows up here: then every row agrees."""
    del scryer
    proc = run_scryer(None, [goal], timeout=60)
    lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    assert lines and lines[0] == expected, (proc.stdout, proc.stderr[-300:])


# ── deep ACYCLIC terms are not mistaken for cycles ──────────────────────────

_DEEP_PROGRAM = _PRELUDE + """\
sum(0, T, T).
sum(N, T, S) :- N > 0, N1 is N-1, sum(N1, T+1, S).
vsum(0, T, T).
vsum(N, T, S) :- N > 0, N1 is N-1, V = T, vsum(N1, V+1, S).
dag(0, T, T).
dag(N, T, R+R) :- N > 0, N1 is N-1, dag(N1, T, R).
deep1(R) :- sum(200, 0, S), ev(R0 is S, R1), R = R0-R1.
deep2(R) :- vsum(200, 0, S), ev(R0 is S, R1), R = R0-R1.
shared(R) :- dag(20, 1, S), ev(R0 is S, R1), R = R0-R1.
shared_var(R) :- Y = 1+1, X = Y*Y, ev(R0 is X+Y, R1), R = R0-R1.
"""


@pytest.fixture(scope="module")
def deep_mod(tmp_path_factory):
    return _load(tmp_path_factory, ".pl", _DEEP_PROGRAM, frontend="native")


@pytest.mark.parametrize("name,expected", [
    ("deep1", "200-yes"), ("deep2", "200-yes"),
    # 2^20 leaves through 20 shared levels: the path set is per path, not
    # per term, so a shared (DAG) subterm is no cycle -- and is cheap
    ("shared", "1048576-yes"), ("shared_var", "6-yes"),
])
def test_acyclic_terms_still_evaluate(deep_mod, name, expected):
    assert _answer(deep_mod, name) == expected


# ── the seam: eval_/2, the seam's evaluator (its ``is`` unifies) ────────────

_SEAM_PROGRAM = """\
s1(R) <- catch((X is X + 1, eval_(X, Y_UNUSED), R is 'yes'), error(E, C), R is E - C)
s2(R) <- catch((X is X * 2, eval_(X, Y_UNUSED), R is 'yes'), error(E, C), R is E - C)
s3(R) <- catch((X is -X, eval_(X, Y_UNUSED), R is 'yes'), error(E, C), R is E - C)
s4(R) <- catch((X is 1 + X, eval_(X * 2 + 1, Y_UNUSED), R is 'yes'), error(E, C), R is E - C)
s5(R) <- catch((X is X + 1, eval_(X // 2, Y_UNUSED), R is 'yes'), error(E, C), R is E - C)
s6(R) <- catch((X is 'a' + X, eval_(X, Y_UNUSED), R is 'yes'), error(E, C), R is E - C)
s7(R) <- catch((X is Z_UNUSED + X, eval_(X, Y_UNUSED), R is 'yes'), error(E, C), R is E - C)
s8(R) <- catch((X is X + 1, eval_(X, Y_UNUSED), R is 'yes'), _, R is 'caught')
"""

SEAM_ROWS = [
    ("s1", "type_error(evaluable,(+)/2)-eval_/2"),
    ("s2", "type_error(evaluable,(*)/2)-eval_/2"),
    ("s3", "type_error(evaluable,(-)/1)-eval_/2"),
    # compiled operators ($mul/$add) meet the cyclic operand at runtime
    ("s4", "type_error(evaluable,(+)/2)-eval_/2"),
    # a native ``//`` evaluates its variable operand through $eval
    ("s5", "type_error(evaluable,(+)/2)-eval_/2"),
    ("s6", "type_error(evaluable,a/0)-eval_/2"),
    ("s7", "instantiation_error-eval_/2"),
    ("s8", "caught"),
]


@pytest.fixture(scope="module")
def seam_mod(tmp_path_factory):
    return _load(tmp_path_factory, SEAM, _SEAM_PROGRAM)


@pytest.mark.parametrize("name,expected", SEAM_ROWS, ids=[r[0] for r in SEAM_ROWS])
def test_cyclic_eval_seam(seam_mod, name, expected):
    assert _answer(seam_mod, name) == expected
