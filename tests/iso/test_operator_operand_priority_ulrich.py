"""Operator atoms as operands.

Ruled against Ulrich Neumerkel's syntax conformity suite
(https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing,
fetched 2026-10-14), then against Scryer:

* ISO 6.3.1.3: a bare atom that is an operator is a term of priority 1201,
  so it cannot be the operand of an operator: #148 ``fy yf``, #161 ``f f``,
  #162 ``1 p p p 2`` (yfx), #235 ``1 = f``, #82-#84 ``(- -)``, #89 ``(-;)``,
  #92 ``[:- -c]``, #134 ``{- =xf1}``, #349 ``(-,(1))`` are syntax errors.
  As a whole argument (6.3.3.1, priority 999), a list element or tail, or
  in parentheses (6.3.4.1) it is fine: ``f(-)``, ``[-]``, ``(-)``.  Scryer
  also takes ``{-}``.

Every row runs in the engine (the native ``.pl`` front end) and, unchanged,
in Scryer.  A row of the suite that is a ``write_canonical/1`` goal is
checked here as the term it reads as.
"""

from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from clausal import import_hook as ih

from .conftest import run_scryer
from .test_iso_answers_scryer import _engine_answers, _scryer_answers

_FY_YF = (":- op(9, fy, fy).", ":- op(9, yf, yf).")
_F = (":- op(9, fy, f).", ":- op(9, yf, f).")
_P_YFX = (":- op(9, fy, p).", ":- op(9, yfx, p).")
_P_XFY = (":- op(9, fy, p).", ":- op(9, xfy, p).")
_P7_YFX = (":- op(7, fy, p).", ":- op(9, yfx, p).")
_FY_YFX = (":- op(9, fy, fy).", ":- op(9, yfx, yfx).")
_XF1 = (":- op(1, xf, xf1).",)
_F400 = (":- op(400, fx, f).",)

#: (row, op directives, goal) -- every goal must succeed.
READ_OK = [
    # A prefix operator applied, not a bare atom: these keep reading.
    ("#147 fy 1 yf", _FY_YF, "X = (fy 1 yf), X == fy(yf(1))"),
    ("#159 f f 0", _F, "X = (f f 0), X == f(f(0))"),
    ("#163 1 p p p 2 xfy", _P_XFY, "X = (1 p p p 2), X == p(1,p(p(2)))"),
    ("#164 1 p p p 2 fy 7", _P7_YFX, "X = (1 p p p 2), X == p(1,p(p(2)))"),
    ("#151 fy 1 yfx 2", _FY_YFX, "X = (fy 1 yfx 2), X == fy(yfx(1,2))"),
    ("#42 1xf1", _XF1, "1xf1 = xf1(1)"),
    ("#81 {- - c}", (), "{- - c}={-(-(c))}"),
    # An operator atom where ISO allows one.
    ("f(-)", (), "X = f(-), X =.. [f, Y], Y == (-)"),
    ("f(a, -)", (), "X = f(a, -), arg(2, X, Y), Y == (-)"),
    ("f(+, -, *)", (), "X = f(+, -, *), functor(X, f, 3)"),
    ("[-]", (), "X = [-], X = [Y], Y == (-)"),
    ("[a|-]", (), "X = [a|-], X = [_|T], T == (-)"),
    ("(-)", (), "X = (-), atom(X)"),
    ("(\\+)", (), "X = (\\+), atom(X)"),
    ("{-}", (), "X = {-}, X = {Y}, Y == (-)"),
    ("- - c", (), "X = (- - c), X == -(-(c))"),
    ("- (-)", (), "X = - (-), X == -(-)"),
]

#: (row, op directives, goal) -- every goal is a syntax error.
READ_ERR = [
    # An operator atom as the operand of an operator.
    ("#148 fy yf", _FY_YF, "write_canonical(fy yf)"),
    ("#161 f f", _F, "write_canonical(f f)"),
    ("#162 1 p p p 2 yfx", _P_YFX, "write_canonical(1 p p p 2)"),
    ("#235 1 = f", _F400, "writeq(1 = f)"),
    ("#82 (- -)", (), "(- -) = -(-)"),
    ("#83 (- - -)", (), "(- - -) = -(-(-))"),
    ("#84 (- - - -)", (), "(- - - -) = -(-(-(-)))"),
    ("#89 (-;)", (), "write_canonical((-;))"),
    ("#92 [:- -c]", (), "[:- -c] = [(:- -c)]"),
    ("#134 {- =xf1}", _XF1, "writeq({- =xf1})"),
    ("#349 (-,(1))", (), "write_canonical((-,(1)))"),
    ("X = -", (), "X = -"),
    ("X = '-'", (), "X = '-'"),
    ("X == -", (), "X == -"),
    ("(- , a)", (), "X = (- , a)"),
    ("(a :- -)", (), "X = (a :- -)"),
    ("X = - -", (), "X = - -"),
]

_PRELUDES = sorted({ops for _, ops, _ in READ_OK})


def _ok_program(ops) -> str:
    rows = [(i, g) for i, (_, o, g) in enumerate(READ_OK) if o == ops]
    return "\n".join(ops) + "\n" + "".join(
        f"r{i}(R) :- {g}, R = true.\n" for i, g in rows)


@pytest.fixture(scope="module")
def loads(tmp_path_factory):
    d = tmp_path_factory.mktemp("op_operand")
    mp = pytest.MonkeyPatch()
    mp.syspath_prepend(str(d))
    mp.setenv(ih.PL_FRONTEND_ENV, "native")
    names = []

    def load(name: str, text: str):
        path = d / f"{name}.pl"
        path.write_text(text, encoding="utf-8")
        for p in d.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        sys.modules.pop(name, None)
        names.append(name)
        importlib.invalidate_caches()
        assert ih._prolog_loader_class_for(str(path)) is ih.NativePrologLoader
        return importlib.import_module(name)
    try:
        yield load
    finally:
        for n in names:
            sys.modules.pop(n, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(READ_OK)), ids=[r[0] for r in READ_OK])
def test_read(loads, i):
    _, ops, goal = READ_OK[i]
    mod = loads(f"_op_operand_ok{i}", "\n".join(ops) + f"\nr(R) :- {goal}, R = true.\n")
    assert _engine_answers(mod, "r", 2) == ["true"]


@pytest.mark.parametrize("i", range(len(READ_ERR)), ids=[r[0] for r in READ_ERR])
def test_syntax_error(loads, i):
    _, ops, goal = READ_ERR[i]
    with pytest.raises(SyntaxError):
        loads(f"_op_operand_err{i}", "\n".join(ops) + f"\nr(R) :- {goal}, R = true.\n")


# ── The Scryer oracle: the same rows, unchanged ─────────────────────────────


def test_oracle_read(scryer):
    del scryer      # the fixture only asserts the binary is there
    for ops in _PRELUDES:
        idx = [i for i, (_, o, _) in enumerate(READ_OK) if o == ops]
        got = _scryer_answers(_ok_program(ops), [(f"r{i}(R)", 2) for i in idx])
        assert got == [["true"]] * len(idx), [READ_OK[i][0] for i in idx]


def test_oracle_syntax_errors(scryer, tmp_path):
    del scryer
    for i, (row, ops, goal) in enumerate(READ_ERR):
        pl = tmp_path / f"e{i}.pl"
        pl.write_text("\n".join(ops) + "\n")
        proc = run_scryer(str(pl), [goal + "."], timeout=60)
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        assert lines and "syntax_error" in lines[-1], (row, proc.stdout, proc.stderr)
