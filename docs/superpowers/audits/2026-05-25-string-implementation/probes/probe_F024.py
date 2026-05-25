"""Probe F024: SegString.__walk__ raises TypeError on non-str list binding.

terms.py:493-499 — the `isinstance(v, list)` branch in
`SegString.__walk__` joins the list via ``"".join(v)``. This works
when every element is a 1-char (or multi-char) str — i.e. when the
list satisfies the char-list contract. If a VarSeg's var was unified
with a list of non-strs (e.g. ints), the walk raises TypeError from
inside ``str.join``.

This is a partial-term short-circuit (C8) of a different flavour:
instead of returning False / NotImplemented, the code blows up. The
TypeError surfaces wherever `__walk__` is called — print, repr, eq,
hash — making the SegString effectively unusable.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F024.py
"""
from clausal.logic.variables import Var, unify, Trail
from clausal.terms import SegString, VarSeg


def main() -> None:
    print("Probe F024: SegString.__walk__ TypeError on non-str list binding")

    # Char list (correct contract) — works
    X = Var()
    t = Trail()
    unify(X, ["h", "i"], t)
    ss_ok = SegString(["a", VarSeg(X), "b"])
    print(f"  X bound to ['h','i']:  walk -> {ss_ok.__walk__()!r}")

    # Multi-char strings — also joins (smell, but no crash)
    Y = Var()
    t = Trail()
    unify(Y, ["ab", "cd"], t)
    ss_multi = SegString(["x", VarSeg(Y), "z"])
    print(f"  Y bound to ['ab','cd']: walk -> {ss_multi.__walk__()!r}")

    # Non-str list — crashes
    Z = Var()
    t = Trail()
    unify(Z, [1, 2, 3], t)
    ss_bad = SegString(["x", VarSeg(Z), "z"])
    try:
        w = ss_bad.__walk__()
        print(f"  Z bound to [1,2,3]:    walk -> {w!r}")
    except TypeError as e:
        print(f"  Z bound to [1,2,3]:    TypeError: {e}")


if __name__ == "__main__":
    main()
