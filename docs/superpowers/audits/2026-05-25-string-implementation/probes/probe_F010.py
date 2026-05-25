"""Probe F010: asymmetric arg order in the recursive do_unify call.

The str-on-left branch (line 1140) calls do_unify(ch, elem, ...) with the
allocated single-char str FIRST and the deref'd elem (a Var) SECOND.
The list-on-left branch (line 1167) calls do_unify(elem, ch, ...) with
the Var FIRST.

do_unify treats Var-Term and Term-Var symmetrically (both bind the Var),
so this should not matter for the result. Confirm both directions still
bind the Var to the same 1-char str.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F010.py
"""
from clausal.logic.variables import Trail, Var, deref, unify


def main() -> None:
    print("Probe F010: arg-order asymmetry between the two branches")

    # str on left
    v1 = Var()
    t = Trail()
    ok1 = unify("a", [v1], t)
    print(f"  unify('a', [v1]): {ok1}  v1 = {deref(v1)!r}")

    # list on left
    v2 = Var()
    t = Trail()
    ok2 = unify([v2], "a", t)
    print(f"  unify([v2], 'a'): {ok2}  v2 = {deref(v2)!r}")

    # Non-ASCII to ensure no interning shortcut hides anything
    v3 = Var()
    t = Trail()
    ok3 = unify("\U0001f600", [v3], t)
    print(f"  unify(smile, [v3]): {ok3}  v3 = {deref(v3)!r}")

    v4 = Var()
    t = Trail()
    ok4 = unify([v4], "\U0001f600", t)
    print(f"  unify([v4], smile): {ok4}  v4 = {deref(v4)!r}")


if __name__ == "__main__":
    main()
