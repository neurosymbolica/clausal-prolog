"""Probe F004: list element that is itself a multi-char string is rejected.

Confirms the documented (and currently implemented) rule that a list element
must be a single code point. The C path at _variables.c:1144 / 1171 checks
PyUnicode_GET_LENGTH(elem) == 1; multi-char strings inside the list cause
the unification to fail even when the concatenation matches.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F004.py
"""
from clausal.logic.variables import Trail, unify


def main() -> None:
    print("Probe F004: list element that is a multi-char string")

    # Concatenation would equal "abc" but elements are not 1-codepoint.
    cases = [
        ("abc", ["ab", "c"]),
        ("abc", ["a", "bc"]),
        ("abc", ["abc"]),
    ]
    for left, right in cases:
        t = Trail()
        actual = unify(left, right, t)
        print(f"  unify({left!r}, {right!r}): {actual}  (expected False)")


if __name__ == "__main__":
    main()
