"""ISO 9.1.4.1: a float result that overflows is
evaluation_error(float_overflow) (Scryer too).  `X is 1.0e308 * 10`
answered inf; an integer too large to be a float beside one raised a raw
OverflowError.  A BARE seam operator keeps Python's meaning (inf), as the
2026-09-28 ruling has it."""
from __future__ import annotations
from tests._suffix import SEAM

SRC = """\
f1(E) :- catch(_ is 1.0e308 * 10, error(E, _), true).
f2(E) :- catch(_ is 1.0e308 + 1.0e308, error(E, _), true).
f3(E) :- catch(_ is -1.0e308 - 1.0e308, error(E, _), true).
f4(E) :- catch(_ is 10^400 + 1.0, error(E, _), true).
f5(X) :- X is 1.5 * 2.
f6(E) :- catch(_ is 10^400 - 1.0, error(E, _), true).
f7(E) :- catch(_ is 10^400 * 1.0, error(E, _), true).
f8(C) :- catch(_ is 1.0e308 * 10, error(_, C), true).
"""


def test_iso_float_overflow(native, ans):
    mod = native.load("l3_float_overflow", SRC)
    for name in ("f1", "f2", "f3", "f4", "f6", "f7"):
        assert ans(mod, name) == [("evaluation_error", "float_overflow")], name
    assert ans(mod, "f5") == [3.0]
    assert ans(mod, "f8") == [("/", "*", 2)]


def test_bare_seam_operator_keeps_python_inf(tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    p = tmp_path / f"_bare_overflow{SEAM}"
    p.write_text("-allow_singletons\ng(X) <- eval_(1.0e308 * 10, X)\n")
    m = _load_module("_bare_overflow", str(p))
    v = Var()
    assert [_deref_walk(v) for _ in solve(("g", v), m)] == [float("inf")]


def test_an_infinite_operand_passes_through():
    """Only an overflow from FINITE operands is the error: inf * 2 is inf."""
    from clausal.logic.exact_arith import EVALUABLE
    assert EVALUABLE[("*", 2)](float("inf"), 2) == float("inf")
    assert EVALUABLE[("+", 2)](float("-inf"), 1.0) == float("-inf")
