"""Probe F025: SegList.__hash__ unconditional vs SegString.__hash__ conditional.

terms.py:376-378 — `SegList.__hash__` raises ``TypeError("unhashable
type: 'SegList'")`` unconditionally, even when the SegList is ground.
By contrast, `SegString.__hash__` (terms.py:589-591) is hashable when
ground (returns ``hash(walked)``) and uses ``id(self)`` when non-ground.

A ground SegList ``SegList([ConcreteSeg(['a','b','c'])])`` has a
well-defined value (the list ['a','b','c']) but cannot be used as a
dict key. The asymmetry mirrors `list` (unhashable) vs `str`
(hashable) and is internally consistent with Python's mutable-vs-
immutable convention — but a ground SegList is conceptually immutable
(no VarSeg to mutate).

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F025.py
"""
from clausal.logic.variables import Var
from clausal.terms import SegList, SegString, ConcreteSeg, VarSeg


def main() -> None:
    print("Probe F025: SegList vs SegString hashability")

    sl_ground = SegList([ConcreteSeg(["a", "b", "c"])])
    print(f"  sl_ground.is_ground(): {sl_ground.is_ground()}")
    try:
        print(f"  hash(sl_ground) = {hash(sl_ground)}")
    except TypeError as e:
        print(f"  hash(sl_ground) -> TypeError: {e}")

    ss_ground = SegString(["abc"])
    print(f"  ss_ground.is_ground(): {ss_ground.is_ground()}")
    print(f"  hash(ss_ground) = {hash(ss_ground)}")

    X = Var()
    ss_nonground = SegString(["a", VarSeg(X), "c"])
    print(f"  ss_nonground.is_ground(): {ss_nonground.is_ground()}")
    print(f"  hash(ss_nonground) = {hash(ss_nonground)}  (== id(self))")


if __name__ == "__main__":
    main()
