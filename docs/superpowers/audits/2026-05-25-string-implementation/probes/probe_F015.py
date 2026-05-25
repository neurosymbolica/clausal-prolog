"""Probe F015: SegList.__unify__ only consumes first split.

`SegList.__unify__` at terms.py:325 uses
``for _ in _seglist_unify_gen(...): return True`` — it returns on the
first yielded split and never asks the generator for more solutions.
For `[*A, *B] = [1, 2, 3]` there are 4 valid splits (A=[], B=[1,2,3] /
A=[1], B=[2,3] / A=[1,2], B=[3] / A=[1,2,3], B=[]). The C2 contract
expects logic-level enumeration; this implementation collapses to the
first.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F015.py
"""
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegList, VarSeg, _seglist_unify_gen


def main() -> None:
    print("Probe F015: SegList.__unify__ first-solution-only")

    A, B = Var(), Var()
    sl = SegList([VarSeg(A), VarSeg(B)])
    t = Trail()
    ok = unify(sl, [1, 2, 3], t)
    print(f"  unify(SegList[*A,*B], [1,2,3]) -> {ok}")
    print(f"  A = {deref(A)!r}, B = {deref(B)!r}")

    # Count solutions via the generator
    A2, B2 = Var(), Var()
    sl2 = SegList([VarSeg(A2), VarSeg(B2)])
    t2 = Trail()
    n = sum(1 for _ in _seglist_unify_gen(sl2, [1, 2, 3], t2))
    print(f"  _seglist_unify_gen yields {n} splits (expected 4)")


if __name__ == "__main__":
    main()
