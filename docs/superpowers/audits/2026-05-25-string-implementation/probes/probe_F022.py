"""Probe F022: SegList.__contains__ silently incomplete on VarSegs.

terms.py:340-348 — when the SegList is non-ground, `__contains__`
walks the segments and only checks `ConcreteSeg.elements`; it never
checks whether a `VarSeg`'s bound value contains the item. Effect:
``3 in SegList([ConcreteSeg([1,2]), VarSeg(X), ConcreteSeg([4])])``
returns False even when X could be bound to a list containing 3.

This is silent logical incompleteness (C8): no error, just a wrong
answer for unbound vars. Compared with the sequence-op crash in F021
this gives the *wrong* answer rather than an exception.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F022.py
"""
from clausal.logic.variables import Var
from clausal.terms import SegList, VarSeg, ConcreteSeg


def main() -> None:
    print("Probe F022: SegList.__contains__ silent incompleteness")

    X = Var()
    sl = SegList([ConcreteSeg([1, 2]), VarSeg(X), ConcreteSeg([4])])
    print(f"  1 in sl: {1 in sl}  (ConcreteSeg hit)")
    print(f"  4 in sl: {4 in sl}  (ConcreteSeg hit)")
    print(f"  3 in sl: {3 in sl}  (could be in X; reported False)")
    print(f"  999 in sl: {999 in sl}  (definitely not)")


if __name__ == "__main__":
    main()
