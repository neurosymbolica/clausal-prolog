"""Probe F023: SegString.__unify__(list) returns NotImplemented when non-ground.

terms.py:565-573 — when `other` is a `list` and the SegString is not
ground, the branch returns `NotImplemented` and the C top-level
unify reads this as "no idea, try the next protocol" — eventually
giving `False`. Even when the unification is logically solvable
(``SegString(["a", *X, "c"]) = ['a','b','c']`` -> X = ['b'] or X =
'b'), the user sees a silent `False`.

Compare with the SegList<->str case (terms.py:316-327) which routes
non-ground SegList through `_seglist_unify_gen` against the string,
yielding solutions. The SegString side has no twin path against a
list — a design-gap matching spec C3 / C8.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F023.py
"""
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString, VarSeg


def main() -> None:
    print("Probe F023: SegString.__unify__(list) on non-ground")

    X = Var()
    ss = SegString(["a", VarSeg(X), "c"])
    t = Trail()

    direct = ss.__unify__(["a", "b", "c"], t)
    print(f"  ss.__unify__(['a','b','c']) -> {direct!r}")

    ok = unify(ss, ["a", "b", "c"], t)
    print(f"  unify(ss, ['a','b','c']) -> {ok}")
    print(f"  X = {deref(X)!r}  (expected 'b' or ['b']; got unbound)")

    # By contrast, SegList against a str does walk-driven non-det
    from clausal.terms import SegList, ConcreteSeg
    Y = Var()
    sl = SegList([ConcreteSeg(["a"]), VarSeg(Y), ConcreteSeg(["c"])])
    t2 = Trail()
    ok2 = unify(sl, "abc", t2)
    print(f"  unify(SegList[a,*Y,c], 'abc') -> {ok2}  (symmetric path works)")
    print(f"  Y = {deref(Y)!r}")


if __name__ == "__main__":
    main()
