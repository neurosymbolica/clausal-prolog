"""Probe F040: _body_multi_star_unify rejects ground SegString target.

body_star_unify.py:231-262 — the dispatch checks
``isinstance(d, (list, str))`` first (true → enumerate splits), then
``isinstance(d, SegList)`` (true → walk and either enumerate or
rebuild), then ``is_var(d)`` (true → construct + bind). A trivially
ground ``SegString(["abc"])`` whose ``__walk__()`` returns ``"abc"``
falls through all four branches and hits the catch-all
``else: return`` at :262, silently producing zero solutions.

This is the multi-star body-position twin of F032: even when no
logical ambiguity exists, the body path silently fails on SegString
targets.

Severity: bug — silent no-solutions on a logically-satisfiable goal.
Parallel to F032 (head-position) and F031 (non-ground SegString
input). See also F041 (non-ground SegString missing branch).

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F040.py
"""
from clausal.logic.variables import Var, unify, Trail
from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
from clausal.terms import SegString, SegList, ConcreteSeg


def main() -> None:
    print("Probe F040: _body_multi_star_unify silent-drops ground SegString")

    # Ground SegList target — works (walks via SegList branch)
    sl = SegList([ConcreteSeg([1, 2, 3])])
    H, S, R = Var(), Var(), Var()
    segments = [("fixed", [H]), ("star", S), ("fixed", [R])]
    solutions = list(_body_multi_star_unify(sl, segments, Trail()))
    print(f"  ground SegList target: solutions={solutions!r}")

    # Ground SegString target — silently drops
    ss = SegString(["abc"])
    print(f"  ground SegString.is_ground() = {ss.is_ground()}, "
          f"walks to {ss.__walk__()!r}")
    H2, S2, R2 = Var(), Var(), Var()
    segments2 = [("fixed", [H2]), ("star", S2), ("fixed", [R2])]
    solutions2 = list(_body_multi_star_unify(ss, segments2, Trail()))
    print(f"  ground SegString target: solutions={solutions2!r}")

    # Symmetric: Var bound to ground SegString
    X = Var()
    unify(X, SegString(["abc"]), Trail())
    H3, S3, R3 = Var(), Var(), Var()
    segments3 = [("fixed", [H3]), ("star", S3), ("fixed", [R3])]
    solutions3 = list(_body_multi_star_unify(X, segments3, Trail()))
    print(f"  Var->ground SegString:  solutions={solutions3!r}")

    print()
    print("  Expected: [True] with H='a', S='b', R='c' (analogous to SegList).")
    print("  Actual:   [] — falls through dispatch to silent 'else: return'.")


if __name__ == "__main__":
    main()
