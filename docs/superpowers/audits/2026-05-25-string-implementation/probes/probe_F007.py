"""Probe F007: surrogate halves in str (constructable, invalid unicode).

Python permits constructing str containing lone surrogate halves (U+D800-U+DFFF).
PyUnicode_GET_LENGTH counts them as 1 codepoint each. Confirm the str<->list
path treats them the same way: 1 lone-surrogate codepoint == 1 list element
that is a 1-codepoint str containing the surrogate.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F007.py
"""
from clausal.logic.variables import Trail, unify


def main() -> None:
    print("Probe F007: lone surrogate halves")
    # Lone high surrogate
    s = "\ud83d"
    print(f"  s = {s!r}, len = {len(s)}")

    t = Trail()
    print(f"  unify(s, [s]): {unify(s, [s], t)}  (expected True)")

    # Astral codepoint U+1F600 ('😀') is ONE codepoint in Python str
    # (Python 3 always uses code-points, never UTF-16 surrogate pairs).
    smile = "\U0001f600"
    print(f"  smile = {smile!r}, len = {len(smile)}")
    t = Trail()
    print(f"  unify(smile, [smile]): {unify(smile, [smile], t)}  (expected True)")

    # Lone surrogate halves form a different sequence than the combined codepoint.
    t = Trail()
    res = unify(smile, ['\ud83d', '\ude00'], t)
    print(f"  unify(smile, ['\\ud83d', '\\ude00']): {res}  (expected False — codepoint != surrogate-pair)")


if __name__ == "__main__":
    main()
