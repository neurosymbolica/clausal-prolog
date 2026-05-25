"""Probe F041: _body_multi_star_unify has no non-ground SegString branch.

body_star_unify.py:234-262 — the non-list/str dispatch has an
``isinstance(d, SegList)`` branch (235-248) that walks and, when the
walked value is still a SegList, constructs a SegList from the pattern
and binds (deferred-constraint flavour). There is no parallel
``isinstance(d, SegString)`` branch — a non-ground SegString-bound
target hits the catch-all ``else: return`` and silently drops the goal.

The SegList branch itself is currently broken in a separate way: it
unifies the target (which is already a Var bound to a SegList) with a
fresh SegList(segs), which is the SegList-vs-SegList unification that
is deferred per F030 / Phase 6. That gap is independent: F041 is the
*structural* missing branch for SegString.

Severity: bug — silent no-solutions on a logically-satisfiable
body-position pattern match against a partial SegString. Parallel to
F031 (head-position input). The fix is to add a SegString branch
symmetric to the SegList one at 235-248, and to translate the pattern
``segments`` into ``[str | VarSeg]`` for SegString rather than
``[ConcreteSeg | VarSeg]``.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F041.py
"""
from clausal.logic.variables import Var, unify, Trail
from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
from clausal.terms import SegString, SegList, VarSeg, ConcreteSeg


def main() -> None:
    print("Probe F041: _body_multi_star_unify missing non-ground SegString branch")

    # Direct non-ground SegString target
    X = Var()
    ss = SegString(["a", VarSeg(X), "c"])
    print(f"  ss.is_ground() = {ss.is_ground()}")
    H, S, R = Var(), Var(), Var()
    segments = [("fixed", [H]), ("star", S), ("fixed", [R])]
    solutions = list(_body_multi_star_unify(ss, segments, Trail()))
    print(f"  direct non-ground SegString: solutions={solutions!r}")

    # Var-wrapped non-ground SegString
    X2 = Var()
    Y2 = Var()
    unify(X2, SegString(["a", VarSeg(Y2), "c"]), Trail())
    H2, S2, R2 = Var(), Var(), Var()
    segments2 = [("fixed", [H2]), ("star", S2), ("fixed", [R2])]
    solutions2 = list(_body_multi_star_unify(X2, segments2, Trail()))
    print(f"  Var->non-ground SegString:   solutions={solutions2!r}")

    # Compare: Var-wrapped non-ground SegList — has a branch (which is in turn
    # blocked on the deferred SegList-vs-SegList unification, F030, but the
    # *structural* branch exists at body_star_unify.py:235-248).
    X3 = Var()
    Y3 = Var()
    unify(X3, SegList([ConcreteSeg([1]), VarSeg(Y3), ConcreteSeg([3])]), Trail())
    H3, S3, R3 = Var(), Var(), Var()
    segments3 = [("fixed", [H3]), ("star", S3), ("fixed", [R3])]
    solutions3 = list(_body_multi_star_unify(X3, segments3, Trail()))
    print(f"  Var->non-ground SegList:     solutions={solutions3!r}")
    print(f"    (gated on F030 SegList-vs-SegList unify — but the branch exists)")

    print()
    print("  Expected (SegString): a structural branch symmetric to 235-248,")
    print("            building a SegString from the pattern and unifying.")
    print("  Actual:   No branch — falls through to silent 'else: return'.")


if __name__ == "__main__":
    main()
