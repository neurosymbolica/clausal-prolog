"""The standard order of numbers, ISO 7.2.1: every float precedes every
integer, whatever their values (operator ruling 2026-11-03, "as with ISO";
Cor.2 8.4.3.4).  Arithmetic comparison (``<``, ``=:=``, ``max``, ``min``)
stays numeric, by value.  Pinned against the engine and Scryer."""

from __future__ import annotations

import importlib
import sys

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers

#: (row name, body binding R, what both print)
ROWS = [
    ("1 against 2.0", "compare(R, 1, 2.0)", [">"]),
    ("2.0 against 1", "compare(R, 2.0, 1)", ["<"]),
    ("1 against 1.0", "compare(R, 1, 1.0)", [">"]),
    ("-5 against 100.0", "compare(R, -5, 100.0)", [">"]),
    ("floats by value", "compare(R, 1.5, 2.5)", ["<"]),
    ("integers by value", "compare(R, 3, 2)", [">"]),
    ("@< across the kinds", "( 2.0 @< 1 -> R = y ; R = n )", ["y"]),
    # Cor.2 8.4.3.4's example with two-letter atoms: Scryer v0.10.0-137
    # raises type_error(list, [a, 1]) on sort([a, 1], R) -- a one-character
    # atom followed by a non-atom (a Scryer defect)
    ("sort", "sort([1, zz, aa, 1, 7.0, 8.0, 2, 8.0, -aa, aa], R)",
     ["[7.0,8.0,1,2,aa,zz,-aa]"]),
]

# Term order is not numeric order (Mike, 2026-11-03: "there's a difference
# between term order and numeric order"): arithmetic compares by value.
ROWS += [
    ("1 < 2.0 by value", "( 1 < 2.0 -> R = y ; R = n )", ["y"]),
    ("2.0 > 1 by value", "( 2.0 > 1 -> R = y ; R = n )", ["y"]),
    ("1 =:= 1.0", "( 1 =:= 1.0 -> R = y ; R = n )", ["y"]),
    ("1 =< 0.5 is false", "( 1 =< 0.5 -> R = y ; R = n )", ["n"]),
    ("max by value", "R is max(1, 2.0)", ["2.0"]),
    ("min by value", "R is min(2.0, 1)", ["1"]),
    # the same pair in term order: 2.0 first
    ("the same pair in term order", "compare(R, 2.0, 1)", ["<"]),
]

PROGRAM = "".join(f"r{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(ROWS))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("number_order")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_iso_number_order_1103"
    (d / f"{name}.pl").write_text(PROGRAM)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 3) == ROWS[i][2]


def test_oracle(scryer):
    del scryer   # the fixture only asserts the binary is there
    got = _scryer_answers(PROGRAM, [(f"r{i}(R)", 3) for i in range(len(ROWS))])
    assert got == [r[2] for r in ROWS]
