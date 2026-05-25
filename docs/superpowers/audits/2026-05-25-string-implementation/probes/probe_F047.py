"""Probe F047: C3 — multi-star head pattern against a SegString target.

The multi-star head guard built by ``_compile_multi_star_guard``
(``clausal/logic/compiler/head_match.py:843-874``) emits this normalisation:

    _d = deref(_lcap)
    if isinstance(_d, SegList):
        _d = _d.__walk__()                # walk SegList → list / SegList
    if isinstance(_d, Var): defer …       # output mode
    if isinstance(_d, (list, str)):
        _len = len(_d); guarded body      # input mode

There is *no* ``isinstance(_d, SegString)`` normalisation, so a
SegString-typed target (whether ground or non-ground) walks past the
SegList branch, past the Var defer, and fails the ``(list, str)``
isinstance test — the multi-star arm is then skipped, the match falls
through, and the caller silently gets zero solutions.

This probe constructs both a ground ``SegString(["abc"])`` and a
non-ground ``SegString(["a", VarSeg(X), "c"])`` and feeds each to a
multi-star clause ``Bracket([*A, X, Y, *B], X, Y, A, B)`` (the existing
fixture in ``tests/clausal_modules/list_edge_cases.clausal``). For
reference it also calls the same predicate with the equivalent ``str``
``"abc"`` and plain ``list`` to confirm the normal path works.

If both SegString calls return 0 solutions while the str/list controls
return >0, C3-multi-star is confirmed.
"""
from __future__ import annotations

import os

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var
from clausal.terms import SegString, VarSeg


def _repo_root() -> str:
    # Walk up from this file until we find the tests/ directory.
    here = os.path.abspath(os.path.dirname(__file__))
    while here != "/" and not os.path.isdir(os.path.join(here, "tests")):
        here = os.path.dirname(here)
    return here


def _load_edge_mod():
    fixture = os.path.join(
        _repo_root(), "tests", "clausal_modules", "list_edge_cases.clausal"
    )
    return _load_module("probe_f047_edge", fixture).__dict__["$module"]


def main() -> None:
    print("Probe F047: C3 — multi-star head guard ignores SegString")
    mod = _load_edge_mod()

    # Control 1: ground str — multi-star walks the str via the (list, str)
    # isinstance arm. Bracket("abc", X, Y, A, B) should bind X='a', Y='b',
    # A='', B='c' for a single solution (or whatever the splits enumerate).
    X1, Y1, A1, B1 = Var(), Var(), Var(), Var()
    n_str = sum(1 for _ in call("Bracket", "abc", X1, Y1, A1, B1, module=mod))

    # Control 2: ground list — symmetric.
    X2, Y2, A2, B2 = Var(), Var(), Var(), Var()
    n_list = sum(1 for _ in call(
        "Bracket", ["a", "b", "c"], X2, Y2, A2, B2, module=mod
    ))

    # Probe target 1: ground SegString — walks to "abc"; if the guard
    # normalised SegString the way it normalises SegList, this would
    # return the same count as the str control.
    ss_ground = SegString(["abc"])
    assert ss_ground.is_ground() and ss_ground.__walk__() == "abc"
    X3, Y3, A3, B3 = Var(), Var(), Var(), Var()
    n_ss_ground = sum(1 for _ in call(
        "Bracket", ss_ground, X3, Y3, A3, B3, module=mod
    ))

    # Probe target 2: non-ground SegString — semantically equivalent to
    # "a" + ?X + "c". The multi-star pattern [*A, X, Y, *B] is logically
    # satisfiable (e.g. A="", X='a', Y='c', B="") for some bindings of
    # the inner Var, but at minimum the guard should NOT silently drop
    # the goal.
    XV = Var()
    ss_partial = SegString(["a", VarSeg(XV), "c"])
    X4, Y4, A4, B4 = Var(), Var(), Var(), Var()
    n_ss_partial = sum(1 for _ in call(
        "Bracket", ss_partial, X4, Y4, A4, B4, module=mod
    ))

    print(f"  Control Bracket(\"abc\")             solutions: {n_str}")
    print(f"  Control Bracket(['a','b','c'])       solutions: {n_list}")
    print(f"  Probe   Bracket(SegString(['abc']))  solutions: {n_ss_ground}")
    print(f"  Probe   Bracket(SegString(['a',*X,'c'])) solutions: {n_ss_partial}")

    str_ok = n_str > 0
    list_ok = n_list > 0
    ground_ss_silently_dropped = (n_ss_ground == 0 and str_ok)
    partial_ss_silently_dropped = (n_ss_partial == 0 and str_ok)

    if str_ok and list_ok and ground_ss_silently_dropped:
        print("  Verdict: C3-multi-star CONFIRMED for GROUND SegString")
        print("           (str/list control yields solutions; SegString yields 0)")
    elif not (str_ok and list_ok):
        print("  Verdict: UNCLEAR — controls did not yield solutions; "
              "review fixture")
    else:
        print("  Verdict: C3-multi-star NOT present for ground SegString")

    if partial_ss_silently_dropped:
        print("  Verdict: C3-multi-star CONFIRMED for NON-GROUND SegString")
    elif not str_ok:
        print("  (non-ground SegString verdict not meaningful without controls)")
    else:
        print("  Verdict: C3-multi-star NOT present for non-ground SegString")


if __name__ == "__main__":
    main()
