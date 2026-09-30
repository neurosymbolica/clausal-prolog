r"""The rest of ISO's evaluables (2026-09-28), pinned against Scryer.

sign/1, +/1, rem/2, gcd/2, truncate/1, round/1, ceiling/1, floor/1, float/1,
float_integer_part/1, float_fractional_part/1, sqrt/1, sin/1, cos/1, tan/1,
asin/1, acos/1, atan/1, atan2/2, atan/2, exp/1, log/1, pi/0, e/0, and the
bitwise >>/2, <</2, /\/2, \//2, \/1, xor/2 -- as QUOTED/cell spellings (a
bare seam operator keeps Python's meaning and is not tested here).

Each ROW runs ``'is'(X, Cell)`` in the engine and (ORACLE half) ``X is G`` in
Scryer; both must print the same.  DEVIATIONS are engine-only, with Scryer's
answer in the comment.  NOT_EVALUABLE pins what Scryer does not evaluate
(integer/1, log/2).
"""

from __future__ import annotations

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref

from .conftest import SCRYER, run_scryer

#: (cell as written in the engine, the same in Scryer, what both print)
ROWS = [
    # sign/1: the operand's kind; an exact rational's sign is an integer
    ("sign(-3)", "sign(-3)", "-1"),
    ("sign(0)", "sign(0)", "0"),
    ("sign(3)", "sign(3)", "1"),
    ("sign(-2.5)", "sign(-2.5)", "-1.0"),
    ("sign(0.0)", "sign(0.0)", "0.0"),
    ("sign(rdiv(1, 3))", "sign(1 rdiv 3)", "1"),
    ("sign(rdiv(-1, 3))", "sign((-1) rdiv 3)", "-1"),
    # +/1
    ("'+'(3)", "+ 3", "3"),
    ("'+'(-3.5)", "+ (-3.5)", "-3.5"),
    # rem/2: the sign of the dividend; integers only
    ("rem(7, 2)", "7 rem 2", "1"),
    ("rem(-7, 2)", "-7 rem 2", "-1"),
    ("rem(7, -2)", "7 rem -2", "1"),
    ("rem(-7, -2)", "-7 rem -2", "-1"),
    ("rem(7, 0)", "7 rem 0", "error(evaluation_error(zero_divisor),(rem)/2)"),
    ("rem(7.0, 2)", "7.0 rem 2", "error(type_error(integer,7.0),(rem)/2)"),
    ("rem(9, 3.0)", "9 rem 3.0", "error(type_error(integer,3.0),(rem)/2)"),
    # truncate/round/ceiling/floor: an integer from any number
    ("truncate(3.7)", "truncate(3.7)", "3"),
    ("truncate(-3.7)", "truncate(-3.7)", "-3"),
    ("truncate(3)", "truncate(3)", "3"),
    ("truncate(-0.5)", "truncate(-0.5)", "0"),
    ("truncate(rdiv(7, 2))", "truncate(7 rdiv 2)", "3"),
    ("truncate(1.0e20)", "truncate(1.0e20)", "100000000000000000000"),
    ("round(2.5)", "round(2.5)", "3"),
    ("round(-2.5)", "round(-2.5)", "-3"),
    ("round(0.5)", "round(0.5)", "1"),
    ("round(-0.5)", "round(-0.5)", "-1"),
    ("round(0.49999999999999994)", "round(0.49999999999999994)", "0"),
    ("round(3)", "round(3)", "3"),
    ("round(rdiv(7, 2))", "round(7 rdiv 2)", "4"),
    ("round(rdiv(-7, 2))", "round((-7) rdiv 2)", "-4"),
    ("ceiling(2.1)", "ceiling(2.1)", "3"),
    ("ceiling(-2.1)", "ceiling(-2.1)", "-2"),
    ("ceiling(-0.5)", "ceiling(-0.5)", "0"),
    ("ceiling(3)", "ceiling(3)", "3"),
    ("ceiling(rdiv(7, 2))", "ceiling(7 rdiv 2)", "4"),
    ("floor(2.9)", "floor(2.9)", "2"),
    ("floor(-2.1)", "floor(-2.1)", "-3"),
    ("floor(3)", "floor(3)", "3"),
    ("floor(rdiv(7, 2))", "floor(7 rdiv 2)", "3"),
    ("floor(rdiv(-7, 2))", "floor((-7) rdiv 2)", "-4"),
    # float/1 and the float parts: a float
    ("float(3)", "float(3)", "3.0"),
    ("float(3.5)", "float(3.5)", "3.5"),
    ("float(rdiv(7, 2))", "float(7 rdiv 2)", "3.5"),
    ("float_integer_part(3.7)", "float_integer_part(3.7)", "3.0"),
    ("float_integer_part(-3.7)", "float_integer_part(-3.7)", "-3.0"),
    ("float_integer_part(-0.5)", "float_integer_part(-0.5)", "0.0"),
    ("float_integer_part(3)", "float_integer_part(3)", "3.0"),
    ("float_integer_part(rdiv(1, 3))", "float_integer_part(1 rdiv 3)", "0.0"),
    ("float_fractional_part(3.75)", "float_fractional_part(3.75)", "0.75"),
    ("float_fractional_part(-3.75)", "float_fractional_part(-3.75)", "-0.75"),
    ("float_fractional_part(-0.5)", "float_fractional_part(-0.5)", "-0.5"),
    ("float_fractional_part(3)", "float_fractional_part(3)", "0.0"),
    ("float_fractional_part(rdiv(1, 3))", "float_fractional_part(1 rdiv 3)",
     "0.3333333333333333"),
    # gcd/2: integers only, non-negative
    ("gcd(12, 18)", "gcd(12, 18)", "6"),
    ("gcd(-12, 18)", "gcd(-12, 18)", "6"),
    ("gcd(-4, -6)", "gcd(-4, -6)", "2"),
    ("gcd(0, 0)", "gcd(0, 0)", "0"),
    ("gcd(0, 5)", "gcd(0, 5)", "5"),
    ("gcd(12, 0)", "gcd(12, 0)", "12"),
    ("gcd(12, 1.5)", "gcd(12, 1.5)", "error(type_error(integer,1.5),gcd/2)"),
    ("gcd(12.0, 18)", "gcd(12.0, 18)", "error(type_error(integer,12.0),gcd/2)"),
    # the float functions
    ("sqrt(4)", "sqrt(4)", "2.0"),
    ("sqrt(2)", "sqrt(2)", "1.4142135623730951"),
    ("sqrt(4.0)", "sqrt(4.0)", "2.0"),
    ("sqrt(0)", "sqrt(0)", "0.0"),
    ("sqrt(rdiv(1, 4))", "sqrt(1 rdiv 4)", "0.5"),
    ("sin(0)", "sin(0)", "0.0"),
    ("sin(1)", "sin(1)", "0.8414709848078965"),
    ("sin(rdiv(1, 2))", "sin(1 rdiv 2)", "0.479425538604203"),
    ("cos(0)", "cos(0)", "1.0"),
    ("cos(rdiv(1, 3))", "cos(1 rdiv 3)", "0.9449569463147377"),
    ("tan(1)", "tan(1)", "1.5574077246549023"),
    ("asin(1)", "asin(1)", "1.5707963267948966"),
    ("asin(rdiv(1, 2))", "asin(1 rdiv 2)", "0.5235987755982989"),
    ("acos(1)", "acos(1)", "0.0"),
    ("acos(-1)", "acos(-1)", "3.141592653589793"),
    ("atan(1)", "atan(1)", "0.7853981633974483"),
    ("atan(rdiv(1, 2))", "atan(1 rdiv 2)", "0.4636476090008061"),
    ("atan2(1, 1)", "atan2(1, 1)", "0.7853981633974483"),
    ("atan2(1, 0)", "atan2(1, 0)", "1.5707963267948966"),
    ("atan2(1, -1)", "atan2(1, -1)", "2.356194490192345"),
    ("atan2(1.0, 0)", "atan2(1.0, 0)", "1.5707963267948966"),
    ("exp(0)", "exp(0)", "1.0"),
    ("exp(1)", "exp(1)", "2.718281828459045"),
    ("exp(rdiv(1, 2))", "exp(1 rdiv 2)", "1.6487212707001282"),
    ("exp(-1000)", "exp(-1000)", "0.0"),
    ("log(1)", "log(1)", "0.0"),
    ("log(2.718281828459045)", "log(2.718281828459045)", "1.0"),
    ("log(rdiv(1, 2))", "log(1 rdiv 2)", "-0.6931471805599453"),
    ("log(1.0e-320)", "log(1.0e-320)", "-736.8272408909739"),
    # pi/0, e/0
    ("pi", "pi", "3.141592653589793"),
    ("e", "e", "2.718281828459045"),
    ("'**'(e, 2)", "e ** 2", "7.3890560989306495"),
    ("'-'(pi)", "- pi", "-3.141592653589793"),
    # bitwise: integers only; a negative shift count shifts the other way
    ("'>>'(8, 1)", "8 >> 1", "4"),
    ("'>>'(-8, 1)", "-8 >> 1", "-4"),
    ("'>>'(-7, 1)", "-7 >> 1", "-4"),
    ("'>>'(-1, 1)", "-1 >> 1", "-1"),
    ("'>>'(1, 100)", "1 >> 100", "0"),
    ("'>>'(8, -1)", "8 >> -1", "16"),
    ("'<<'(1, 3)", "1 << 3", "8"),
    ("'<<'(-1, 2)", "-1 << 2", "-4"),
    ("'<<'(1, -1)", "1 << -1", "0"),
    ("'<<'(1, 100)", "1 << 100", "1267650600228229401496703205376"),
    ("'>>'(8.0, 1)", "8.0 >> 1", "error(type_error(integer,8.0),(>>)/2)"),
    ("'>>'(8, 1.0)", "8 >> 1.0", "error(type_error(integer,1.0),(>>)/2)"),
    ("'<<'(1, 1.0)", "1 << 1.0", "error(type_error(integer,1.0),(<<)/2)"),
    ("'/\\\\'(12, 10)", "12 /\\ 10", "8"),
    ("'/\\\\'(5, -2)", "5 /\\ -2", "4"),
    ("'/\\\\'(12, 1.0)", "12 /\\ 1.0", "error(type_error(integer,1.0),(/\\)/2)"),
    ("'\\\\/'(12, 10)", "12 \\/ 10", "14"),
    ("'\\\\/'(5, -8)", "5 \\/ -8", "-3"),
    ("'\\\\'(5)", "\\ 5", "-6"),
    ("'\\\\'(-1)", "\\ (-1)", "0"),
    ("xor(12, 10)", "xor(12, 10)", "6"),
    ("xor(-1, 5)", "xor(-1, 5)", "-6"),
    ("xor(12, 1.0)", "xor(12, 1.0)", "error(type_error(integer,1.0),xor/2)"),
    # a non-number operand
    ("sin('foo')", "sin(foo)", "error(type_error(evaluable,foo/0),(is)/2)"),
    ("truncate('foo')", "truncate(foo)", "error(type_error(evaluable,foo/0),(is)/2)"),
    # NOT evaluable in Scryer (nor ISO): integer/1, log/2
    ("integer(2.5)", "integer(2.5)", "error(type_error(evaluable,integer/1),(is)/2)"),
    ("log(2, 8)", "log(2, 8)", "error(type_error(evaluable,log/2),(is)/2)"),
]

#: Engine-only rows: the engine deliberately differs from Scryer (Scryer's
#: answer in the comment).  An evaluation error names the evaluable, as for
#: the rest of the table, where Scryer names is/2.
DEVIATIONS = [
    ("sqrt(-1)", "error(evaluation_error(undefined),sqrt/1)"),       # Scryer: (is)/2
    ("asin(2)", "error(evaluation_error(undefined),asin/1)"),        # Scryer: (is)/2
    ("acos(2)", "error(evaluation_error(undefined),acos/1)"),        # Scryer: (is)/2
    ("atan2(0, 0)", "error(evaluation_error(undefined),atan2/2)"),   # Scryer: (is)/2
    ("atan2(0.0, 0.0)", "error(evaluation_error(undefined),atan2/2)"),  # Scryer: (is)/2
    ("log(-1)", "error(evaluation_error(undefined),log/1)"),         # Scryer: (is)/2
    # ISO 9.3.6: log of zero is undefined (Scryer: float_overflow, (is)/2)
    ("log(0)", "error(evaluation_error(undefined),log/1)"),
    ("log(0.0)", "error(evaluation_error(undefined),log/1)"),
    ("exp(1000)", "error(evaluation_error(float_overflow),exp/1)"),  # Scryer: (is)/2
    ("float('^'(10, 400))", "error(evaluation_error(float_overflow),float/1)"),  # (is)/2
    ("sqrt('^'(10, 400))", "error(evaluation_error(float_overflow),sqrt/1)"),    # (is)/2
    # ISO Cor.2 atan/2 is atan2/2 (Scryer: type_error(evaluable, atan/2))
    ("atan(1, 1)", "0.7853981633974483"),
    ("atan(0, 0)", "error(evaluation_error(undefined),atan/2)"),
    # an integral rational IS an integer here (RULED 2026-09-09); Scryer
    # keeps 12 rdiv 1 a rational: type_error(integer, 12)
    ("gcd(rdiv(12, 1), 18)", "6"),
    ("'>>'(rdiv(4, 2), 1)", "1"),
    # the context names the unary \/1 (Scryer names (\)/2)
    ("'\\\\'(5.0)", "error(type_error(integer,5.0),(\\)/1)"),
]

_ALL = [(cell, want) for cell, _, want in ROWS] + DEVIATIONS

# A STRICT module: the evaluable functors (and the atoms pi, e) are in scope
# everywhere with no declaration (ruling Q16, 2026-09-28).
_SRC = "-allow_singletons\n" + "".join(
    f"g{i}(X) <- 'is'(X, {cell}),\n" for i, (cell, _) in enumerate(_ALL))


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                     delete=False) as f:
        f.write(_SRC)
        path = f.name
    try:
        return _load_module("_iso_evaluables_scryer", path)
    finally:
        os.unlink(path)


def _engine(mod, i) -> str:
    x = Var()
    try:
        for _ in solve((f"g{i}", x), mod):
            return str(deref(x))
    except LogicException as exc:
        return render_error_term(exc.term)
    return "fails"


@pytest.mark.parametrize("i", range(len(_ALL)), ids=[r[0] for r in _ALL])
def test_engine(mod, i):
    assert _engine(mod, i) == _ALL[i][1]


def test_every_new_evaluable_has_a_row():
    """Positive control on the population: each added table key is exercised
    by at least one row (engine or deviation)."""
    from clausal.logic.exact_arith import EVALUABLE
    added = {("+", 1), ("sign", 1), ("rem", 2), ("gcd", 2), ("truncate", 1),
             ("round", 1), ("ceiling", 1), ("floor", 1), ("float", 1),
             ("float_integer_part", 1), ("float_fractional_part", 1),
             ("sqrt", 1), ("sin", 1), ("cos", 1), ("tan", 1), ("asin", 1),
             ("acos", 1), ("atan", 1), ("atan2", 2), ("atan", 2), ("exp", 1),
             ("log", 1), ("pi", 0), ("e", 0), (">>", 2), ("<<", 2),
             ("/\\", 2), ("\\/", 2), ("\\", 1), ("xor", 2)}
    assert len(added) == 30 and added <= set(EVALUABLE)
    cells = [cell for cell, _ in _ALL]
    for name, arity in added:
        if arity == 0:
            hit = name in cells
        else:
            quoted = "'" + name.replace("\\", "\\\\") + "'"
            hit = any(c.startswith((f"{name}(", f"{quoted}(")) for c in cells)
        assert hit, (name, arity)


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
