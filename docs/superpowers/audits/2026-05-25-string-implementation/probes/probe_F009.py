"""Probe F009: per-element PyUnicode_Substring allocation cost (perf smell).

The C path allocates a 1-codepoint PyUnicode for every list-element Var
that needs to be bound (lines 1138, 1165). For long strings unified
against a fresh var list, that is O(n) allocations of tiny 1-char strs.
Confirms that the binding works correctly even at scale, and prints
timing to document the cost.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F009.py
"""
import time
from clausal.logic.variables import Trail, Var, deref, unify


def main() -> None:
    print("Probe F009: per-element substring allocation under load")

    N = 10_000
    s = "a" * N
    vs = [Var() for _ in range(N)]

    t = Trail()
    t0 = time.perf_counter()
    ok = unify(s, vs, t)
    dt = time.perf_counter() - t0
    print(f"  unify str of len {N} with list of {N} Vars: {ok}  in {dt*1000:.2f} ms")
    # Spot check bindings are correct 1-char strs
    for i in (0, N // 2, N - 1):
        v = deref(vs[i])
        print(f"    vs[{i}] = {v!r}  (type {type(v).__name__})")


if __name__ == "__main__":
    main()
