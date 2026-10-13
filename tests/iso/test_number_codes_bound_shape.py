"""number_codes/2 with Number bound and Codes malformed raises Scryer's error.

The number_chars/2 analogue is tests/iso/test_number_chars_cont_ulrich.py.
``_refuse_bound_chars_shape`` takes an element kind, so the element error is
``type_error(integer, E)`` here, and the tail-shape check still comes first.
A non-ground partial term stays a partial list and never raises.
Every expected answer is Scryer's (``test_oracle`` re-measures them).
"""

from __future__ import annotations

import importlib
import sys

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers

ROWS = [
    ("Codes not a list",
     "catch(number_codes(1,1), error(F, C), R = [F, C])",
     ["[type_error(list,1),number_codes/2]"]),
    ("improper tail, good head",
     "catch(number_codes(1,[a|2]), error(F, C), R = [F, C])",
     ["[type_error(list,[a|2]),number_codes/2]"]),
    ("improper tail, unbound head",
     "catch(number_codes(1,[_|2]), error(F, C), R = [F, C])",
     ["[type_error(list,[_|2]),number_codes/2]"]),
    ("partial tail, bad head",
     "catch(number_codes(1,[[]|_]), error(F, C), R = [F, C])",
     ["[type_error(integer,[]),number_codes/2]"]),
    ("improper tail AND bad head: tail wins",
     "catch(number_codes(1,[[]|2]), error(F, C), R = [F, C])",
     ["[type_error(list,[[]|2]),number_codes/2]"]),
    ("proper list, bad 2nd element",
     "catch(number_codes(1,[_,[]]), error(F, C), R = [F, C])",
     ["[type_error(integer,[]),number_codes/2]"]),
    ("bind-order: hole bound after the list is built",
     "L = [_,[]|T], T = [], catch(number_codes(1,L), error(F, C), R = [F, C])",
     ["[type_error(integer,[]),number_codes/2]"]),
    # Must still just FAIL or succeed, never raise.
    ("partial list, mismatching well-typed head", "number_codes(1,[0'.|_]), R = true", []),
    ("self-referential [C|C]", "number_codes(1,[C|C]), R = C", []),
    ("partial list, matching head", "number_codes(12,[0'1|T]), T = [0'2], R = true", ["true"]),
    ("bare variable Codes", "number_codes(12, L), L = [0'1, 0'2], R = true", ["true"]),
]

PROGRAM = "".join(f"r{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(ROWS))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("nc_codes")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_nc_codes_bound_shape"
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
    del scryer
    got = _scryer_answers(PROGRAM, [(f"r{i}(R)", 3) for i in range(len(ROWS))])
    assert got == [r[2] for r in ROWS]
