"""Probe F031: head [H, *T] against non-ground SegString silently fails.

list_unify.py:111-117 — the input path walks SegList but has no
SegString twin. A clause head ``foo([H, *T])`` matched against a
non-ground ``SegString(["a", VarSeg(X), "c"])`` returns ``False``
without binding anything, even though the unification is logically
satisfiable (H="a", T = SegString([VarSeg(X), "c"]) or analogous).

The C version (`_list_unify.c:139-149`) mirrors the same blind spot:
it has a SegListType TypeCheck branch but no SegStringType branch,
so the behaviour is identical regardless of whether the C extension
was built.

Symmetric to F012 (C-side unify str↔list rejects SegString-as-elem)
and F023 (`SegString.__unify__(list)` silent-fail on non-ground).

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F031.py
"""
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString, VarSeg
from clausal.logic.runtime.list_unify import (
    _head_list_unify_input,
    _head_list_unify_input_py,
)


def main() -> None:
    print("Probe F031: head [H, *T] against non-ground SegString")

    # C version
    H, T = Var(), Var()
    X = Var()
    seg = SegString(["a", VarSeg(X), "c"])
    t = Trail()
    r_c = _head_list_unify_input(seg, [H], T, [], t)
    print(f"  C  _head_list_unify_input(non-ground SegString, [H], T, [], t)"
          f" -> {r_c!r}")
    print(f"     H = {deref(H)!r}, T = {deref(T)!r}")

    # Python fallback
    H2, T2 = Var(), Var()
    X2 = Var()
    seg2 = SegString(["a", VarSeg(X2), "c"])
    t2 = Trail()
    r_py = _head_list_unify_input_py(seg2, [H2], T2, [], t2)
    print(f"  Py _head_list_unify_input_py(non-ground SegString, ...)"
          f" -> {r_py!r}")
    print(f"     H = {deref(H2)!r}, T = {deref(T2)!r}")

    print(f"  Expected: deferred (None) or constrained binding.")
    print(f"  Actual:   silent False — no SegString-walking branch exists.")


if __name__ == "__main__":
    main()
