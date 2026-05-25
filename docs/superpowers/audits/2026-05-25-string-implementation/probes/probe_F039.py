"""Probe F039: _in_iter raises on non-ground SegList / SegString.

body_star_unify.py:208-217 — ``_in_iter`` calls ``iter(collection)``
which dispatches to ``SegList.__iter__`` → ``SegList.to_list()`` and
raises ``TypeError("SegList is not ground: ...")`` when any VarSeg is
unbound. SegString hits the no-``__iter__`` path (see F038) regardless
of ground state.

This is the body-position twin of F021 (SegList sequence-protocol crash
on partial terms). The body-position ``elem in coll`` goal has no way
to defer or partially enumerate — it just propagates the TypeError out
of the compiled body code.

A defensible alternative: enumerate the known ConcreteSeg / string
segments and surface the VarSeg holes as a marker so the caller can
defer. The current behaviour drops a satisfiable goal as an exception.

Severity: bug — TypeError on a logically-valid membership goal. The
prefix elements are knowable; the goal could succeed for any item in
the concrete prefix without committing on the VarSeg holes. Same C8
class as F021.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F039.py
"""
from clausal.logic.runtime.body_star_unify import _in_iter
from clausal.logic.variables import Var
from clausal.terms import SegList, SegString, VarSeg, ConcreteSeg


def main() -> None:
    print("Probe F039: _in_iter raises on non-ground Seg* terms")

    # Non-ground SegList
    sl = SegList([ConcreteSeg([1, 2]), VarSeg(Var()), ConcreteSeg([5])])
    try:
        items = list(_in_iter(sl, pair_mode=False))
        print(f"  non-ground SegList: {items!r}")
    except Exception as e:
        print(f"  non-ground SegList raised {type(e).__name__}: {e}")

    # Non-ground SegString
    ss = SegString(["a", VarSeg(Var()), "c"])
    try:
        items = list(_in_iter(ss, pair_mode=False))
        print(f"  non-ground SegString: {items!r}")
    except Exception as e:
        print(f"  non-ground SegString raised {type(e).__name__}: {e}")

    print()
    print("  Expected: enumerate the concrete prefix (1, 2, 5 / 'a', 'c') or")
    print("            a typed deferred-constraint signal.")
    print("  Actual:   TypeError propagates out of the body goal.")


if __name__ == "__main__":
    main()
