"""Probe F012: Var inside list bound to a SegString (not plain str).

If a list element is a Var bound to a SegString that resolves to a 1-char
string, the C path checks Var_Check(elem) after var_deref. var_deref
follows the Var chain, but SegString is not a Var — so elem ends up as
the SegString, which fails PyUnicode_Check and goes to the "else: return 0"
branch (1149/1175). Confirm behaviour.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F012.py
"""
from clausal.logic.variables import Trail, Var, unify

try:
    from clausal.terms import SegString
except Exception as e:
    print(f"Probe F012: SKIP — cannot import SegString: {e}")
    raise SystemExit(0)


def main() -> None:
    print("Probe F012: Var bound to SegString inside a list")

    v = Var()
    t = Trail()
    # Bind v to a SegString representing a single char
    seg_a = SegString("a")
    ok = unify(v, seg_a, t)
    print(f"  bind v to SegString('a'): {ok}")

    # Now try to unify "a" with [v]. Inside the C loop, var_deref(v)
    # returns the SegString. Since SegString is NOT PyUnicode_Check,
    # the else branch returns 0 — even though semantically the SegString
    # IS the 1-char string 'a'.
    ok2 = unify("a", [v], t)
    print(f"  unify('a', [v]) where v=SegString('a'): {ok2}")
    print(f"  Expected if exact str-check: False  (SegString != PyUnicode)")
    print(f"  Expected if semantic: True")


if __name__ == "__main__":
    main()
