"""Probe F005: list element that is a nested list is rejected.

The str<->list path strictly expects single-codepoint string elements.
A list element that is itself a list (e.g. [['a'], 'b']) cannot match a
str character. Confirms behaviour and direction symmetry.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F005.py
"""
from clausal.logic.variables import Trail, unify


def main() -> None:
    print("Probe F005: list element that is itself a list")
    cases = [
        ("ab", [["a"], "b"]),
        ("ab", ["a", ["b"]]),
        ("ab", [["a"], ["b"]]),
    ]
    for left, right in cases:
        t = Trail()
        print(f"  unify({left!r}, {right!r}): {unify(left, right, t)}  (expected False)")


if __name__ == "__main__":
    main()
