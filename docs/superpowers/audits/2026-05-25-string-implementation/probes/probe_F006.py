"""Probe F006: Var inside list binds to a 1-char str when unified with str.

When the list element is an unbound Var, the C path allocates a 1-codepoint
substring via PyUnicode_Substring and unifies the Var with it. Confirms the
binding happens and produces a 1-char str (not an int code).

Also covers the symmetric branch (list-on-left, str-on-right).

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F006.py
"""
from clausal.logic.variables import Trail, Var, deref, unify


def main() -> None:
    print("Probe F006: Var inside list binds to 1-char str")

    # str on left, list with Vars on right
    a, b, c = Var(), Var(), Var()
    t = Trail()
    ok = unify("abc", [a, b, c], t)
    print(f"  unify('abc', [a,b,c]) -> {ok}")
    for name, v in (("a", a), ("b", b), ("c", c)):
        r = deref(v)
        print(f"    {name} = {r!r}   type = {type(r).__name__}")

    # list on left, str on right
    x, y = Var(), Var()
    t = Trail()
    ok = unify([x, y], "12", t)
    print(f"  unify([x,y], '12') -> {ok}")
    print(f"    x = {deref(x)!r}   y = {deref(y)!r}")

    # Var bound to a multi-char string should NOT match a single code point
    z = Var()
    t = Trail()
    unify(z, "ab", t)
    ok = unify("ab", [z], t)
    print(f"  z=Var bound to 'ab'; unify('ab', [z]) -> {ok}  (expected False — len(str)!=len(list))")

    # 2-element list where one var was pre-bound to multi-char
    w = Var()
    t = Trail()
    unify(w, "xy", t)
    ok = unify("ab", [w, "b"], t)
    print(f"  w bound to 'xy'; unify('ab', [w, 'b']) -> {ok}  (expected False — w resolves to 2-char str, fails 1-char check)")


if __name__ == "__main__":
    main()
