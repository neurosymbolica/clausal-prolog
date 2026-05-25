"""Probe F001: empty string unifies with empty list at C level.

Confirms the n==0 fast path on both branches of the str<->list block
(_variables.c lines 1130 and 1158).

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F001.py
"""
from clausal.logic.variables import Trail, unify


def main() -> None:
    cases = [
        ("", []),
        ([], ""),
    ]
    for left, right in cases:
        t = Trail()
        actual = unify(left, right, t)
        expected = True
        print(f"Probe F001: unify({left!r}, {right!r})")
        print(f"  Expected: {expected!r}")
        print(f"  Actual:   {actual!r}")
        print(f"  Match:    {expected == actual}")


if __name__ == "__main__":
    main()
