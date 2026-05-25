"""Probe F002: multi-codepoint emoji vs char list (code-point level match).

Tests whether the C-level str<->list path treats multi-codepoint emoji
("thumbs up + skin-tone modifier") as a sequence of code points, with each
list element being a single code point.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F002.py
"""
from clausal.logic.variables import Trail, unify


def main() -> None:
    # U+1F44D THUMBS UP SIGN, then U+1F3FD EMOJI MODIFIER FITZPATRICK TYPE-4
    s = "\U0001f44d\U0001f3fd"
    chars_correct = ["\U0001f44d", "\U0001f3fd"]
    chars_wrong = ["\U0001f44d\U0001f3fd"]  # the whole grapheme as one element

    print(f"Probe F002: multi-codepoint emoji unification")
    print(f"  s = {s!r}, len(s) = {len(s)}")

    t = Trail()
    actual_correct = unify(s, chars_correct, t)
    print(f"  unify(s, [cp0, cp1])")
    print(f"    Expected: True   Actual: {actual_correct}   Match: {actual_correct is True}")

    t2 = Trail()
    actual_wrong = unify(s, chars_wrong, t2)
    print(f"  unify(s, [whole_grapheme])  (1 list element of length 2)")
    print(f"    Expected: False  Actual: {actual_wrong}   Match: {actual_wrong is False}")


if __name__ == "__main__":
    main()
