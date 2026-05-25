"""Probe F042: unbound-target branch always builds SegList, never SegString.

body_star_unify.py:249-260 — when the dereffed target is an unbound
Var, the helper unconditionally constructs a SegList of
``[VarSeg | ConcreteSeg]`` segments from the pattern and binds the
target to it. There is no recording of whether the surrounding
*logical* context expects a str/SegString result.

So a goal ``X is [H, *S, T]`` where every var is unbound binds X to a
SegList. If the same X is later unified with a str (e.g. by another
arg of the head), the SegList-vs-str path takes over — fine — but
intermediate inspection of X (e.g. ``call/N``, term dump, hash
attempts) sees a SegList, never a SegString.

This is the multi-star body-position parallel of F033 (head-position
output mode always builds a list). Same root cause: the original
target type is genuinely absent at this site, so recovering it
requires upstream plumbing.

Severity: design-gap (matching F033's grading) — the type information
isn't present at the call site; defensible but inconsistent with the
"input type wins" strings-as-lists contract.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F042.py
"""
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
from clausal.terms import SegList, SegString


def main() -> None:
    print("Probe F042: unbound target binds to SegList unconditionally")

    target = Var()
    H, S, R = Var(), Var(), Var()
    segments = [("fixed", [H]), ("star", S), ("fixed", [R])]
    # Inspect the binding *inside* the yield — the generator's trail.undo
    # at body_star_unify.py:259 unbinds after each yield, so consuming the
    # full generator would lose the binding.
    bound = None
    for _ in _body_multi_star_unify(target, segments, Trail()):
        bound = deref(target)
        break
    print(f"  bound (during yield): {bound!r}")
    print(f"  type:                 {type(bound).__name__}")
    print(f"  isinstance(_, SegList):   {isinstance(bound, SegList)}")
    print(f"  isinstance(_, SegString): {isinstance(bound, SegString)}")
    print()
    print("  Expected (under 'input type wins'): a SegString when the surrounding")
    print("            logical context is string-typed; SegList otherwise.")
    print("  Actual:   Always SegList — the type-source information is absent")
    print("            at this site (same root cause as F033).")


if __name__ == "__main__":
    main()
