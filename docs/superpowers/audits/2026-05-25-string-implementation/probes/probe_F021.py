"""Probe F021: SegList sequence protocol crashes on non-ground.

terms.py:334-351 — `__len__`, `__iter__`, `__getitem__` all call
`to_list()` (terms.py:285-292) which raises `TypeError` when the
SegList is not ground. A caller using duck-typed sequence operations
on a non-ground SegList gets an unexpected crash rather than a
logically-incomplete answer or a deferred constraint.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F021.py
"""
from clausal.logic.variables import Var
from clausal.terms import SegList, VarSeg, ConcreteSeg


def main() -> None:
    print("Probe F021: SegList sequence ops on non-ground")

    X = Var()
    sl = SegList([ConcreteSeg([1, 2]), VarSeg(X)])
    print(f"  is_ground: {sl.is_ground()}")

    for op_name, op in (
        ("len(sl)",        lambda: len(sl)),
        ("list(sl)",       lambda: list(sl)),
        ("sl[0]",          lambda: sl[0]),
    ):
        try:
            print(f"  {op_name} -> {op()!r}")
        except TypeError as e:
            print(f"  {op_name} -> TypeError: {e}")


if __name__ == "__main__":
    main()
