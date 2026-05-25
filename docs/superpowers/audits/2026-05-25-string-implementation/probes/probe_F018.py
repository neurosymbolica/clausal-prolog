"""Probe F018: SegList.__walk__ expands VarSeg-bound-str into char list.

terms.py:227-234 — when a VarSeg's var is bound to a `str`, the walk
expands it via ``list(v)`` and absorbs the chars into the preceding
ConcreteSeg. The string-ness of the binding is lost: the walked value
is a `list`, not a `str`. This is the C1 type-preservation candidate:
should the contract be "the segments dictate the container shape" or
"the bound value's type wins"?

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F018.py
"""
from clausal.logic.variables import Var, unify, Trail
from clausal.terms import SegList, VarSeg, ConcreteSeg


def main() -> None:
    print("Probe F018: SegList.__walk__ char expansion of str-bound VarSeg")

    X = Var()
    t = Trail()
    unify(X, "abc", t)
    sl = SegList([ConcreteSeg([1]), VarSeg(X), ConcreteSeg([2])])
    w = sl.__walk__()
    print(f"  X bound to 'abc'; sl = [1, *X, 2]")
    print(f"  sl.__walk__() = {w!r}")
    print(f"  type = {type(w).__name__}")
    print(f"  'abc' substring lost — chars expanded inline")


if __name__ == "__main__":
    main()
