"""Probe F026: _multi_star_splits combinatorial blowup.

terms.py:429-443 — `_multi_star_splits(n_stars, remainder)` yields
``C(remainder + n_stars - 1, n_stars - 1)`` tuples (stars-and-bars).
For ``n_stars=8, remainder=20`` that's 888 030 tuples. Both
`_seglist_unify_gen` and `_segstring_unify_gen` iterate this product
on every call, even though `SegList.__unify__` / `SegString.__unify__`
only consume the first split (see F015, F016).

When the unify hooks are later made non-deterministic (Phase 2 fix
for C2), this combinatorial cost becomes user-visible. For now it's
masked by the first-solution-only consumption but worth flagging.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F026.py
"""
import time

from clausal.terms import _multi_star_splits


def main() -> None:
    print("Probe F026: _multi_star_splits combinatorial cost")

    for n_stars, remainder, expected in (
        (1,  10, 1),
        (2,  10, 11),
        (4,  10, 286),
        (4,  50, 23_426),
        (8,  20, 888_030),
    ):
        t0 = time.perf_counter()
        count = sum(1 for _ in _multi_star_splits(n_stars, remainder))
        dt = time.perf_counter() - t0
        assert count == expected, (count, expected)
        print(f"  n_stars={n_stars:>2} remainder={remainder:>2}: "
              f"{count:>10,} splits in {dt:>6.3f}s")


if __name__ == "__main__":
    main()
