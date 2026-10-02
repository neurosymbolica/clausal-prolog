"""Arithmetic operator rulings of 2026-09-28, pinned against Scryer.

* A QUOTED or cell spelling follows Scryer Prolog: ``'//'`` truncates toward
  zero, ``div`` floors, ``'**'`` is always a float, ``'^'`` is the integer
  power, and ``//``, ``div``, ``mod`` take integers only (Q1, Q2).
* A zero divisor is ``evaluation_error(zero_divisor)`` naming the operator,
  on every spelling (Q4).
* A non-arithmetic term in a CLP(FD) post is clpz's
  ``domain_error(clpz_expression, T)`` (Q3).

(A BARE operator in today's source syntax keeps Python's meaning; those rows
are in tests/test_arith_operator_rulings.py -- Scryer is not their oracle.)

Each ROW runs the goal in the engine and (ORACLE half) in Scryer; both must
print the same.  The engine's explanatory prose is not compared.
"""

from __future__ import annotations

import os
import re
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref

from .conftest import SCRYER, run_scryer
from tests._suffix import SEAM

#: (evaluable cell as written in the engine, the same in Scryer, what both print)
ROWS = [
    ("'//'(-7, 2)", "-7 // 2", "-3"),
    # Q15: the quoted / is Scryer's float division; rdiv is exact
    ("'/'(7, 2)", "7 / 2", "3.5"),
    ("'/'(6, 2)", "6 / 2", "3.0"),
    ("'/'(rdiv(7, 2), 2)", "(7 rdiv 2) / 2", "1.75"),
    ("'//'(7, -2)", "7 // -2", "-3"),
    ("'//'(7, 2)", "7 // 2", "3"),
    ("div(-7, 2)", "-7 div 2", "-4"),
    ("div(7, -2)", "7 div -2", "-4"),
    ("mod(-7, 2)", "-7 mod 2", "1"),
    ("mod(7, -2)", "7 mod -2", "-1"),
    ("'**'(2, 3)", "2 ** 3", "8.0"),
    ("'**'(2, -1)", "2 ** -1", "0.5"),
    ("'**'(0, 0)", "0 ** 0", "1.0"),
    ("'**'(2.0, 3)", "2.0 ** 3", "8.0"),
    ("'^'(2, 3)", "2 ^ 3", "8"),
    ("'^'(0, 0)", "0 ^ 0", "1"),
    ("'^'(1, -5)", "1 ^ (-5)", "1"),
    ("'^'(-1, -3)", "(-1) ^ (-3)", "-1"),
    ("'^'(-1, -2)", "(-1) ^ (-2)", "1"),
    ("'^'(2.0, 3)", "2.0 ^ 3", "8.0"),
    ("'^'(2, 3.0)", "2 ^ 3.0", "8.0"),
    ("'^'(2, -1)", "2 ^ (-1)", "error(type_error(float,2),(^)/2)"),
    ("'^'(3, -2)", "3 ^ (-2)", "error(type_error(float,3),(^)/2)"),
    ("'//'(7.0, 2)", "7.0 // 2", "error(type_error(integer,7.0),(//)/2)"),
    ("'//'(7, 2.0)", "7 // 2.0", "error(type_error(integer,2.0),(//)/2)"),
    ("mod(1.5, 1)", "1.5 mod 1", "error(type_error(integer,1.5),(mod)/2)"),
    ("'/'(1, 0)", "1 / 0", "error(evaluation_error(zero_divisor),(/)/2)"),
    ("'/'(0, 0)", "0 / 0", "error(evaluation_error(zero_divisor),(/)/2)"),
    ("'/'(1.0, 0)", "1.0 / 0", "error(evaluation_error(zero_divisor),(/)/2)"),
    ("'/'(1, 0.0)", "1 / 0.0", "error(evaluation_error(zero_divisor),(/)/2)"),
    ("'//'(1, 0)", "1 // 0", "error(evaluation_error(zero_divisor),(//)/2)"),
    ("mod(1, 0)", "1 mod 0", "error(evaluation_error(zero_divisor),(mod)/2)"),
    ("'**'(10.0, 400)", "10.0 ** 400",
     "error(evaluation_error(float_overflow),(**)/2)"),
    ("'**'(10, 400)", "10 ** 400",
     "error(evaluation_error(float_overflow),(**)/2)"),
    ("'**'(-8.0, 0.5)", "(-8.0) ** 0.5",
     "error(evaluation_error(undefined),(**)/2)"),
    ("'^'(-2, 0.5)", "(-2) ^ 0.5", "error(evaluation_error(undefined),(^)/2)"),
    # abs/1 (ISO 9.1.7), min/2 and max/2 (ISO Cor.2): the operand's own kind;
    # beside a float the operands compare as floats and a tie is a float
    ("abs(-3)", "abs(-3)", "3"),
    ("abs(3)", "abs(3)", "3"),
    ("abs(-3.5)", "abs(-3.5)", "3.5"),
    ("abs(-9223372036854775808)", "abs(-9223372036854775808)",
     "9223372036854775808"),
    ("max(2, 5)", "max(2, 5)", "5"),
    ("min(2, 5)", "min(2, 5)", "2"),
    ("max(1, 2.0)", "max(1, 2.0)", "2.0"),
    ("min(1, 2.0)", "min(1, 2.0)", "1"),
    ("min(2, 1.0)", "min(2, 1.0)", "1.0"),
    ("max(1, 1.0)", "max(1, 1.0)", "1.0"),
    ("max(1.0, 1)", "max(1.0, 1)", "1.0"),
    ("min(1, 1.0)", "min(1, 1.0)", "1.0"),
    ("max(-3, abs(-7))", "max(-3, abs(-7))", "7"),
    ("abs('foo')", "abs(foo)", "error(type_error(evaluable,foo/0),(is)/2)"),
    ("max(1, 'foo')", "max(1, foo)", "error(type_error(evaluable,foo/0),(is)/2)"),
]

#: Rows where the engine DELIBERATELY differs from Scryer (engine column only;
#: the Scryer answer is in the comment).  Scryer names the CALLER for these
#: evaluation errors, or -- for ``div`` -- the ``mod`` it is implemented by;
#: the engine names the operator, as it does for every other evaluation error.
DEVIATIONS = [
    ("div(1, 0)", "error(evaluation_error(zero_divisor),(div)/2)"),     # Scryer: (mod)/2
    ("'**'(0, -1)", "error(evaluation_error(undefined),(**)/2)"),       # Scryer: (is)/2
    ("'^'(0, -1)", "error(evaluation_error(undefined),(^)/2)"),         # Scryer: (is)/2
    ("'^'(0.0, -1)", "error(evaluation_error(undefined),(^)/2)"),       # Scryer: (is)/2
    # exact arithmetic (RULED 2026-09-17): a rational base stays exact;
    # Scryer answers the float 0.25
    ("'^'(rdiv(1, 2), 2)", "1/4"),
    # an exact rational stays exact (Scryer: the rational 1 rdiv 4 too, but
    # it prints it in its own spelling)
    ("abs(rdiv(-1, 4))", "1/4"),
    ("max(rdiv(1, 3), rdiv(1, 4))", "1/3"),
]

_ALL = [(cell, want) for cell, _, want in ROWS] + DEVIATIONS

# A STRICT module: the evaluable functors are in scope everywhere, with no
# declaration (ruling Q16, 2026-09-28: "they are builtins really").
_SRC = "-allow_singletons\n" + "".join(
    f"g{i}(X) <- 'is'(X, {cell}),\n" for i, (cell, _) in enumerate(_ALL))


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=SEAM, mode="w",
                                     delete=False) as f:
        f.write(_SRC)
        path = f.name
    try:
        return _load_module("_arith_rulings_scryer", path)
    finally:
        os.unlink(path)


def _engine(mod, i) -> str:
    x = Var()
    try:
        for _ in solve((f"g{i}", x), mod):
            v = deref(x)
            return str(v)
    except LogicException as exc:
        return render_error_term(exc.term)
    return "fails"


@pytest.mark.parametrize("i", range(len(_ALL)), ids=[r[0] for r in _ALL])
def test_engine(mod, i):
    assert _engine(mod, i) == _ALL[i][1]


def test_oracle_prints_the_expected_column(scryer):
    del scryer   # the fixture only asserts the binary is there
    goals = [f"r({goal})." for _, goal, _ in ROWS]
    with tempfile.NamedTemporaryFile(suffix=".pl", mode="w",
                                     delete=False) as f:
        f.write("r(G) :- catch((V is G, R = V), E, R = E),"
                " write('R '), writeq(R), nl.\n")
        prelude = f.name
    try:
        out = run_scryer(prelude, goals, timeout=60).stdout.splitlines()
    finally:
        os.unlink(prelude)
    got = [line[2:].strip() for line in out if line.startswith("R ")]
    want = [r[2] for r in ROWS]
    assert len(got) == len(want) == len(ROWS) > 0
    assert got == want


# ── Q3: a non-arithmetic term in a CLP(FD) post ─────────────────────────────

#: (engine body, Scryer goal, the FORMAL both raise).  The second argument of
#: error/2 differs by convention: Scryer's clpz puts ``unknown(T)-1`` there,
#: the engine the comparison's indicator or an unbound variable.
CLP_ROWS = [
    ("X == foo(1)", "X #= foo(1)", "domain_error(clpz_expression,foo(1))"),
    ("X != foo(1)", "X #\\= foo(1)", "domain_error(clpz_expression,foo(1))"),
    ("X < foo(1)", "X #< foo(1)", "domain_error(clpz_expression,foo(1))"),
    ("X == 2 + foo", "X #= 2 + foo", "domain_error(clpz_expression,foo)"),
    ("X == '**'(Y, 2)", "X #= Y ** 2", "domain_error(clpz_expression,_**2)"),
]


@pytest.fixture(scope="module")
def clp_mod():
    # ``foo`` is used both bare (row 4) and applied (rows 1-3), so it is
    # declared as the atom AND as the data functor foo/1.
    src = ("-allow_singletons\n-private([foo, foo(_)])\n-implicit_functors\n" + "".join(
        f"c{i}(X) <- ({body}),\n" for i, (body, _, _) in enumerate(CLP_ROWS)))
    with tempfile.NamedTemporaryFile(suffix=SEAM, mode="w",
                                     delete=False) as f:
        f.write(src)
        path = f.name
    try:
        return _load_module("_arith_rulings_clp", path)
    finally:
        os.unlink(path)


@pytest.mark.parametrize("i", range(len(CLP_ROWS)), ids=[r[1] for r in CLP_ROWS])
def test_clp_engine_formal(clp_mod, i):
    with pytest.raises(LogicException) as info:
        list(solve((f"c{i}", Var()), clp_mod))
    text = render_error_term(info.value.term)
    assert text.startswith(f"error({CLP_ROWS[i][2]},"), text


def test_clp_oracle_formal(scryer):
    del scryer
    goals = [f"catch(({goal}), error(F, _), (writeq(F), nl))."
             for _, goal, _ in CLP_ROWS]
    with tempfile.NamedTemporaryFile(suffix=".pl", mode="w",
                                     delete=False) as f:
        f.write(":- use_module(library(clpz)).\n")
        prelude = f.name
    try:
        out = run_scryer(prelude, goals, timeout=60).stdout.splitlines()
    finally:
        os.unlink(prelude)
    # a variable prints as _NNN in Scryer: compare it as ``_``
    got = [re.sub(r"_\d+", "_", line.strip())
           for line in out if line.startswith("domain_error(")]
    want = [r[2] for r in CLP_ROWS]
    assert len(got) == len(want) > 0
    assert got == want
