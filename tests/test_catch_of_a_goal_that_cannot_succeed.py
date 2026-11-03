"""catch/3 of a goal that lowers to no statements loads, and fails.

``fail`` (and ``false``) drops its continuation, so it lowers to an empty
statement list.  The trampoline's inline catch put that list straight into
the body of an ``ast.Try``, and loading the module raised
``ValueError: empty body on Try``.  The catch's try body is ``pass`` then
(``_compile_catch_impl``).  Scryer simply fails the goal: ``t(X)`` below
answers only its second clause, ``X = 2``; under ``\\+`` it succeeds.

Every surface and both compilation strategies: Clausal Prolog
(``.clausal``), ISO Prolog (``.pl``), and the seam (``.seam``), trampoline
and ``-shallow``.
"""
from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

#: (label, ISO body, seam body, answers of t/1).  t(X) :- Body, X = 1.
#: t(2).
_CASES = [
    ("catch_fail", "catch(fail, _, true)", "catch(fail, _, True)", [2]),
    ("catch_false", "catch(false, _, true)", "catch(false, _, True)", [2]),
    ("catch_error_fail", None, "catch_error(fail, _)", [2]),
    ("catch_recover_fail", None, "catch_recover(fail, _, True)", [2]),
    ("not_catch_fail", "\\+ catch(fail, _, true)",
     "not catch(fail, _, True)", [1, 2]),
    ("catch_recovery_fail", "catch(throw(x), _, fail)",
     "catch(throw(x), _, fail)", [2]),
    ("nested", "catch(catch(fail, _, true), _, true)",
     "catch(catch(fail, _, True), _, True)", [2]),
    ("in_findall", "findall(Z, catch(fail, _, true), [])",
     "findall(Z, catch(fail, _, True), [])", [1, 2]),
]


def _write(tmp_path, name, ext, src):
    path = tmp_path / f"{name}{ext}"
    path.write_text(src)
    return path


def _answers(mod):
    y = Var()
    return [deref(y) for _ in solve(("t", y), mod)]


def _every_case(surface, tmp_path):
    """(label, answers or the error) for every case on *surface*."""
    out = []
    for label, iso, seam, expected in _CASES:
        if surface == "seam" or surface == "seam_shallow":
            head = "-private([x])\n"
            if surface == "seam_shallow":
                head += "-shallow([t/1])\n"
            src = f"{head}t(X) <- ({seam}, X is 1)\nt(2),\n"
            ext = ".seam"
        else:
            if iso is None:
                continue
            src = f"t(X) :- {iso}, X = 1.\nt(2).\n"
            ext = ".pl" if surface == "pl" else ".clausal"
        try:
            got = _answers(load_clausal_module(
                _write(tmp_path, f"{surface}_{label}", ext, src)))
        except Exception as exc:  # noqa: BLE001 -- named in the report
            got = f"{type(exc).__name__}: {exc}"
        out.append((label, got, expected))
    return out


@pytest.mark.filterwarnings("ignore")
@pytest.mark.parametrize("surface", ["clausal", "pl", "seam", "seam_shallow"])
def test_a_catch_of_a_failing_goal_loads_and_fails(surface, tmp_path):
    wrong = [f"{label}: got {got!r}, expected {expected!r}"
             for label, got, expected in _every_case(surface, tmp_path)
             if got != expected]
    assert not wrong, "\n".join(wrong)
