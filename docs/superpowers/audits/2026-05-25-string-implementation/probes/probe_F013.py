"""Probe F013: Var inside list bound to another list (nested binding).

If a list element is a Var bound to a list, var_deref resolves the Var
to the inner list, which fails PyUnicode_Check and returns 0 — same as
the "list element is a list" rejection. This is consistent.

But what about a Var bound to a (1-char) tuple? Same — not PyUnicode_Check.
Document the rule: the C path requires the dereffed element to be either
an unbound Var (allocate substring & bind) or a PyUnicode of exactly 1
code point.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F013.py
"""
from clausal.logic.variables import Trail, Var, unify


def main() -> None:
    print("Probe F013: Var-bound-to-non-str-non-Var inside list")

    # Var bound to a 1-element list — should fail (not PyUnicode)
    v = Var()
    t = Trail()
    unify(v, ["a"], t)
    print(f"  v=['a']; unify('a', [v]): {unify('a', [v], t)}  (expected False)")

    # Var bound to a tuple containing 'a'
    w = Var()
    t = Trail()
    unify(w, ("a",), t)
    print(f"  w=('a',); unify('a', [w]): {unify('a', [w], t)}  (expected False)")

    # Var bound to an int
    x = Var()
    t = Trail()
    unify(x, 97, t)  # ASCII code for 'a'
    print(f"  x=97; unify('a', [x]): {unify('a', [x], t)}  (expected False — char != int code)")


if __name__ == "__main__":
    main()
