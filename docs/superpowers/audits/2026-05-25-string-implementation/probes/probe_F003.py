"""Probe F003: combining-character (NFD) string vs precomposed (NFC) list.

The C path compares code points. A precomposed e-acute (U+00E9) is one
code point; a decomposed e + combining acute (U+0065 U+0301) is two.
Confirm that these two visually identical strings do NOT unify even
though Python's == on the strings is False as well.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F003.py
"""
from clausal.logic.variables import Trail, unify


def main() -> None:
    nfc = "é"          # 1 codepoint
    nfd = "é"         # 2 codepoints

    print(f"Probe F003: NFC vs NFD code-point semantics")
    print(f"  nfc = {nfc!r}, len = {len(nfc)}")
    print(f"  nfd = {nfd!r}, len = {len(nfd)}")
    print(f"  Python str ==: {nfc == nfd}")

    # str-vs-str falls through to PyObject_RichCompareBool; same as Python ==
    t = Trail()
    print(f"  unify(nfc, nfd): {unify(nfc, nfd, t)}  (expected False)")

    # str-vs-list: precomposed unifies only with single-element list
    t = Trail()
    print(f"  unify(nfc, [nfc]):       {unify(nfc, [nfc], t)}  (expected True)")
    t = Trail()
    print(f"  unify(nfc, list(nfd)):   {unify(nfc, list(nfd), t)}  (expected False)")
    t = Trail()
    print(f"  unify(nfd, list(nfd)):   {unify(nfd, list(nfd), t)}  (expected True)")
    t = Trail()
    print(f"  unify(nfd, [nfc]):       {unify(nfd, [nfc], t)}  (expected False)")


if __name__ == "__main__":
    main()
