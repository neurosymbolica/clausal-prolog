"""`-` followed by a numeric literal, layout or not, is the negative numeric
literal: ``- 1`` reads as the integer -1, exactly as ``-1`` does.

Ruled against Ulrich Neumerkel's syntax conformity suite
(https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing,
fetched 2026-10-13), first ISO then Scryer:

* #56 ``integer(- 1).`` succeeds, and so do #57-#59 and #61: the quoted
  name ``'-'`` and a comment as the layout count too.  #60
  ``integer(-/*.*/1).`` is a syntax error only because ``-/*.*/`` lexes as
  ONE symbol-char atom.
* #286-#288 (marked as recent finds for WDCor4): ``(- (1)) = -(1)`` -- a
  ``(`` is not a number, so ``- (1)`` stays the compound; ``(- -1) =
  -(-1)``; and ``(- 1^2) = ^(-1,2)`` -- the literal is formed before the
  operators are.
* #63/#180/#64: the literal is a term in its own right, not the prefix
  operator, so it survives ``op(0, fy, -)``.

The adjacency rule this replaces (a spaced ``- 1`` read as the compound
-(1), F037) dated from an older reading of ISO 6.3.1.2; WDCor4 supersedes
it.  F037's real concern -- writeq/1 output must read back -- still holds:
the compound is written ``- (1)`` (#135), and an infix operand of ``-`` is
bracketed as well (#183 ``- (1^2)``, #327 ``- ((1*2)^3)``), since ``-1^2``
reads as ``(-1)^2``.

Every row runs through BOTH ``.pl`` front ends (the translator and the native
reader) and, unchanged, through the Scryer oracle.
"""

from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from clausal import import_hook as ih
from tests import _oracles

from .conftest import run_scryer
from .test_iso_answers_scryer import _engine_answers, _scryer_answers

FRONTENDS = ("translator", "native")

#: (row, goal) -- every goal must succeed.  Ulrich's rows verbatim where the
#: row is a goal; ``#236`` is a write_canonical/1 row, checked here as the
#: term it reads as.
READ_OK = [
    ("#286 - (1) is the compound", "(- (1)) = -(1)"),
    ("#287 - -1", "(- -1) = -(-1)"),
    ("#288 - 1^2 is (-1)^2", "(- 1^2) = ^(-1,2)"),
    ("#56 integer(- 1)", "integer(- 1)"),
    ("#57 integer('-'1)", "integer('-'1)"),
    ("#58 integer('-' 1)", "integer('-' 1)"),
    ("#59 integer(- /*.*/1)", "integer(- /*.*/1)"),
    ("#61 integer('-'/*.*/1)", "integer('-'/*.*/1)"),
    ("#62 atom(-/*.*/-)", "atom(-/*.*/-)"),
    ("#174 -1 = -0x1", "-1 = -0x1"),
    ("#81 {- - c}", "{- - c}={-(-(c))}"),
    ("#236 a- - -b", "X = (a- - -b), X == -(a,-(-(b)))"),
    ("#173 10.0** -323", "1.0e-323=:=10.0** -323"),
    # Not rows of the suite: the other shapes the ruling names, pinned
    # against Scryer.
    ("- 1.0e10 is a float", "X = - 1.0e10, X == -10000000000.0"),
    ("- 1.5 is a float", "X = - 1.5, float(X)"),
    ("-0'a", "X = -0'a, X == -97"),
    ("- 0'a", "X = - 0'a, X == -97"),
    ("a newline is layout", "X = -\n1, integer(X)"),
    ("a- 1 is infix", "X = (a- 1), X == -(a,1)"),
    ("1 - 1 is infix", "X = (1 - 1), X == -(1,1)"),
    ("-(1) is the compound", "X = -(1), compound(X), \\+ integer(X)"),
    ("- (1) is the compound", "X = - (1), compound(X)"),
    ("-(-(1))", "X = -(-(1)), X = -(Y), compound(Y)"),
    ("-(1) = -(Y)", "-(1) = -(Y), Y == 1"),
    ("- - 1 is -(-1)", "X = - - 1, X == -(-1)"),
    ("-(a)", "X = -(a), X == -a, compound(X)"),
    ("- 1 + 2", "X = (- 1 + 2), X == +(-1,2)"),
    ("[- 1]", "X = [- 1], X == [-1]"),
    ("f(- 1)", "X = f(- 1), X == f(-1)"),
    ("2 ** - 1: the literal fits a 199 slot", "X = (2 ** - 1), X == **(2,-1)"),
]

#: Rows the TRANSLATOR front end still gets wrong, for reasons other than the
#: literal (each reproduces at the base commit): `{...}` over a `-` term
#: builds a Python set of operator nodes (TypeError: unhashable), a `(a,b)`
#: data term is emitted as a call, and the seam's `-Y` is an operator node
#: that does not unify with the ISO compound '-'(1).  Strict, so a fix
#: flips them.
TRANSLATOR_OPEN = {"#81 {- - c}", "#139", "-(1) = -(Y)"}

#: Rows Scryer gets wrong: in a CONSULTED clause
#: `1.0e-323 =:= 10.0** -323` fails, while the same goal at its toplevel
#: succeeds, as Ulrich's table says.  Nothing to do with the literal --
#: `-323` is adjacent.
SCRYER_WRONG_IN_CLAUSE = {"#173 10.0** -323"}

#: (row, goal) -- every goal is a syntax error.
READ_ERR = [
    ("#46 float(- .0)", "float(- .0)"),
    ("#60 integer(-/*.*/1)", "integer(-/*.*/1)"),
    ("#350 -[]1", "writeq(-[]1)"),
    ("#351 -{}1", "writeq(-{}1)"),
    # Not the literal: an infix operator atom (``=``) is a term of priority
    # 1201, so it is not the operand of prefix ``-`` (ISO 6.3.1.3; see
    # test_operator_operand_priority_ulrich.py).
    ("#86 {- = - 1}", "{- = - 1}={(-(=)) - 1}"),
    ("#87 (- = - 1)", "write_canonical((- = - 1))"),
    ("#88 (- = -1)", "write_canonical((- = -1))"),
]

#: After ``op(0, fy, -)``: #180 and #64.
OP0_OK = [
    ("#180 integer(-1)", "integer(-1)"),
    ("#64 integer(- 1)", "integer(- 1)"),
]

#: (row, term, writeq/1 output).
WRITE = [
    ("#135", "-(1)", "- (1)"),
    ("scryer", "-(0)", "- (0)"),
    ("scryer", "-(0.0)", "- (0.0)"),
    ("#182", "-(-1)", "- -1"),
    ("#183", "-(1^2)", "- (1^2)"),
    ("#216", "-(-(1))", "- - (1)"),
    ("#218", "-(1*2)", "- (1*2)"),
    ("#327", "-((1*2)^3)", "- ((1*2)^3)"),
    ("#338", "-'-'2", "- -2"),
    ("#260", "-(a^2)", "- (a^2)"),
    ("#139", "-((a,b))", "- (a,b)"),
    ("#137", "- (a*b)", "- (a*b)"),
    ("#140", "-a", "-a"),
    ("#191", "-(-a)", "- -a"),
    ("#192", "-(-(-a))", "- - -a"),
    ("#184", "-(-)", "- (-)"),
    # Not rows of the suite, pinned against Scryer.
    ("float", "-(1.0)", "- (1.0)"),
    ("spaced float", "- (1.0e10)", "- (10000000000.0)"),
    ("char code", "-(0'a)", "- (97)"),
    ("infix then literal", "1 - -1", "1- -1"),
    ("infix then compound", "1-(-(1))", "1- - (1)"),
    ("nested float", "-(-(1.5))", "- - (1.5)"),
    ("nested infix", "-(-(a^2))", "- - (a^2)"),
    ("compound as left operand", "-(1)^2", "(- (1))^2"),
    ("compound under an infix", "-((-(1))^2)", "- ((- (1))^2)"),
]


def _program(goals) -> str:
    return "".join(f"r{i}(R) :- {g}, R = true.\n" for i, (_, g) in enumerate(goals))


def _write_program() -> str:
    return "".join(f"w{i}(R) :- R = {t}.\n" for i, (_, t, _) in enumerate(WRITE))


class _Loads:
    def __init__(self, tmp, monkeypatch):
        self.tmp, self.mp, self.names = tmp, monkeypatch, []

    def load(self, name: str, text: str, frontend: str):
        """Import *text* as a fresh ``.pl`` under *frontend*, and assert that
        front end is the one that ran."""
        path = self.tmp / f"{name}.pl"
        path.write_text(text, encoding="utf-8")
        self.mp.setenv(ih.PL_FRONTEND_ENV, frontend)
        for p in self.tmp.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        sys.modules.pop(name, None)
        self.names.append(name)
        importlib.invalidate_caches()
        want = ih._prolog_loader_class_for(str(path))
        assert (want is ih.NativePrologLoader) == (frontend == "native"), want
        mod = importlib.import_module(name)
        assert type(mod.__loader__) is want, type(mod.__loader__)
        return mod


@pytest.fixture(scope="module")
def loads(tmp_path_factory):
    d = tmp_path_factory.mktemp("minus_literal")
    mp = pytest.MonkeyPatch()
    mp.syspath_prepend(str(d))
    lo = _Loads(d, mp)
    try:
        yield lo
    finally:
        for n in lo.names:
            sys.modules.pop(n, None)
        mp.undo()


_SOURCES = {
    "read": lambda: _program(READ_OK),
    "write": _write_program,
    "op0": lambda: ":- op(0, fy, -).\n" + _program(OP0_OK),
}


@pytest.fixture(scope="module")
def mods(loads):
    """``mods(kind, fe)``: the *kind* program loaded under front end *fe*,
    once per module (each load separate, so one failing load fails only its
    own rows)."""
    cache = {}

    def get(kind, fe):
        if (kind, fe) not in cache:
            cache[kind, fe] = loads.load(f"_minus_{kind}_{fe}", _SOURCES[kind](), fe)
        return cache[kind, fe]
    return get


def _params(rows):
    """(fe, i) pairs, the TRANSLATOR_OPEN rows strict-xfail under the
    translator."""
    out = []
    for fe in FRONTENDS:
        for i, row in enumerate(rows):
            marks = ()
            if fe == "translator" and row[0] in TRANSLATOR_OPEN:
                marks = pytest.mark.xfail(strict=True, reason="translator gap, "
                                          "not the literal; see TRANSLATOR_OPEN")
            out.append(pytest.param(fe, i, marks=marks, id=f"{row[0]}-{fe}"))
    return out


@pytest.mark.parametrize("fe, i", _params(READ_OK))
def test_read(mods, fe, i):
    assert _engine_answers(mods("read", fe), f"r{i}", 2) == ["true"]


@pytest.mark.parametrize("fe", FRONTENDS)
@pytest.mark.parametrize("i", range(len(OP0_OK)), ids=[r[0] for r in OP0_OK])
def test_read_after_op0(mods, fe, i):
    assert _engine_answers(mods("op0", fe), f"r{i}", 2) == ["true"]


@pytest.mark.parametrize("fe, i", _params(WRITE))
def test_write(mods, fe, i):
    assert _engine_answers(mods("write", fe), f"w{i}", 2) == [WRITE[i][2]]


def _assert_syntax_error(loads, name, goal, fe):
    with pytest.raises(SyntaxError):
        loads.load(name, f"r(R) :- {goal}, R = true.\n", fe)


@pytest.mark.parametrize("fe", FRONTENDS)
@pytest.mark.parametrize("i", range(len(READ_ERR)), ids=[r[0] for r in READ_ERR])
def test_syntax_error(loads, fe, i):
    _assert_syntax_error(loads, f"_minus_err{i}_{fe}", READ_ERR[i][1], fe)


# ── The Scryer oracle: the same rows, unchanged ─────────────────────────────


@pytest.fixture
def scryer_bin(scryer):
    """The oracle binary (``tests._oracles.SCRYER``; ``CLAUSAL_SCRYER``
    overrides it -- these rows answer the same on the plain build)."""
    del scryer      # the conftest fixture fails when the oracle is absent
    return _oracles.SCRYER


def test_oracle_read(scryer_bin):
    got = _scryer_answers(_program(READ_OK), [(f"r{i}(R)", 2) for i in range(len(READ_OK))])
    assert got == [[] if row in SCRYER_WRONG_IN_CLAUSE else ["true"]
                   for row, _ in READ_OK]


def test_oracle_toplevel_gets_the_scryer_wrong_rows_right(scryer_bin):
    rows = [(r, g) for r, g in READ_OK if r in SCRYER_WRONG_IN_CLAUSE]
    assert rows
    proc = run_scryer(None, [g + "." for _, g in rows], timeout=60, binary=scryer_bin)
    assert [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()] == ["true."] * len(rows)


def test_oracle_read_after_op0(scryer_bin):
    got = _scryer_answers(":- op(0, fy, -).\n" + _program(OP0_OK),
                          [(f"r{i}(R)", 2) for i in range(len(OP0_OK))])
    assert got == [["true"]] * len(OP0_OK)


def test_oracle_write(scryer_bin):
    got = _scryer_answers(_write_program(), [(f"w{i}(R)", 2) for i in range(len(WRITE))])
    assert got == [[w] for _, _, w in WRITE]


def test_oracle_syntax_errors(scryer_bin):
    rows = READ_ERR
    proc = run_scryer(None, [g + "." for _, g in rows], timeout=120, binary=scryer_bin)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == len(rows), proc.stdout + proc.stderr
    for (row, _), line in zip(rows, lines):
        assert "syntax_error" in line, (row, line)
