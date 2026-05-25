"""Probe F017: SegString.__hash__ violates the Python eq/hash invariant.

terms.py:589-591 returns ``hash(walked)`` when the SegString is ground
but ``id(self)`` when non-ground. Two non-ground SegStrings with
structurally equal `_segments` lists compare equal via `__eq__`
(terms.py:582-583) but hash to distinct values, violating the Python
data-model contract `a == b -> hash(a) == hash(b)`. Concrete effect:
they become distinct keys in a `dict` / `set`.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F017.py
"""
from clausal.logic.variables import Var
from clausal.terms import SegString, VarSeg


def main() -> None:
    print("Probe F017: SegString.__hash__ vs __eq__ invariant")

    X = Var()
    ss1 = SegString(["a", VarSeg(X), "c"])
    ss2 = SegString(["a", VarSeg(X), "c"])

    print(f"  ss1 == ss2: {ss1 == ss2}")
    print(f"  hash(ss1) = {hash(ss1)}")
    print(f"  hash(ss2) = {hash(ss2)}")
    print(f"  hash(ss1) == hash(ss2): {hash(ss1) == hash(ss2)}")
    print(f"  len({{ss1: 1, ss2: 2}}) = {len({ss1: 1, ss2: 2})}  (expected 1)")
    print(f"  len({{ss1, ss2}}) = {len({ss1, ss2})}  (expected 1)")


if __name__ == "__main__":
    main()
