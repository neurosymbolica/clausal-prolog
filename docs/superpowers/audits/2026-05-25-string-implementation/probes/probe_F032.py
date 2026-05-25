"""Probe F032: head [H, *T] against GROUND SegString also fails.

list_unify.py:111-117 — even a fully ground ``SegString(["abc"])``,
whose ``__walk__()`` returns the plain str ``"abc"``, is rejected by
the input path: the function never walks SegString, so it falls
through to the final ``else: return False``.

The C version (`_list_unify.c:139-149, 213-214`) mirrors the same
behaviour.

This is the stronger half of [[F031]]: even when no logical
ambiguity exists (the SegString trivially walks to a str), the
input path still silently fails.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F032.py
"""
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString
from clausal.logic.runtime.list_unify import (
    _head_list_unify_input,
    _head_list_unify_input_py,
)


def main() -> None:
    print("Probe F032: head [H, *T] against ground SegString")

    ss = SegString(["abc"])
    print(f"  SegString.is_ground() = {ss.is_ground()}")
    print(f"  SegString.__walk__() = {ss.__walk__()!r}  (would unify cleanly)")

    H, T = Var(), Var()
    t = Trail()
    r_c = _head_list_unify_input(ss, [H], T, [], t)
    print(f"  C  result: {r_c!r}  H={deref(H)!r}  T={deref(T)!r}")

    H2, T2 = Var(), Var()
    ss2 = SegString(["abc"])
    t2 = Trail()
    r_py = _head_list_unify_input_py(ss2, [H2], T2, [], t2)
    print(f"  Py result: {r_py!r}  H={deref(H2)!r}  T={deref(T2)!r}")

    print(f"  Expected: True with H='a', T='bc'.")
    print(f"  Actual:   False (SegString never walked).")

    # Also via a Var bound to a ground SegString
    X = Var()
    unify(X, SegString(["abc"]), Trail())
    H3, T3 = Var(), Var()
    t3 = Trail()
    r3 = _head_list_unify_input(X, [H3], T3, [], t3)
    print(f"  Var bound to ground SegString: result={r3!r} "
          f"H={deref(H3)!r} T={deref(T3)!r}")


if __name__ == "__main__":
    main()
