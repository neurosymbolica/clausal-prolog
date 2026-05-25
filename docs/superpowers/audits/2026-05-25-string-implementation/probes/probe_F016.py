"""Probe F016: SegString.__unify__ only consumes first split.

Mirror of F015 for SegString. terms.py:562 uses the same
``for _ in _segstring_unify_gen(...): return True`` pattern, returning on
the first split. For ``SegString([*A, *B]) = "abc"`` there are 4 valid
splits (A="", B="abc" / A="a", B="bc" / A="ab", B="c" / A="abc", B="");
the implementation surfaces only A="", B="abc".

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F016.py
"""
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString, VarSeg, _segstring_unify_gen


def main() -> None:
    print("Probe F016: SegString.__unify__ first-solution-only")

    A, B = Var(), Var()
    ss = SegString([VarSeg(A), VarSeg(B)])
    t = Trail()
    ok = unify(ss, "abc", t)
    print(f"  unify(SegString[*A,*B], 'abc') -> {ok}")
    print(f"  A = {deref(A)!r}, B = {deref(B)!r}")

    A2, B2 = Var(), Var()
    ss2 = SegString([VarSeg(A2), VarSeg(B2)])
    t2 = Trail()
    n = sum(1 for _ in _segstring_unify_gen(ss2, "abc", t2))
    print(f"  _segstring_unify_gen yields {n} splits (expected 4)")


if __name__ == "__main__":
    main()
