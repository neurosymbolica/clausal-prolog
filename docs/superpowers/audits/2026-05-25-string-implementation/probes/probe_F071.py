"""Probe F071: ``char_type/2`` silently fails on multi-codepoint grapheme.

``char_type/2`` requires its Char argument to be a single-codepoint str
(``isinstance(vc, str) and len(vc) == 1``).  A user-perceived grapheme
that spans multiple codepoints (e.g. ``"👍🏽"`` = U+1F44D + U+1F3FD,
2 codepoints) is silently rejected at the ``len(vc) != 1`` gate at
``chars.py:105``.

Parallel to [[F002]] (the same multi-codepoint shape mismatch on the
str↔list unify path).  The contract is consistent — code-point
identity throughout — but the failure mode is silent (no error,
just zero solutions), which is harder to debug than a type_error.
"""
from __future__ import annotations

from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions


def _run(name, arity, *args):
    disp = get_builtin_dispatch(name, arity, None)
    return len(solutions(StepGenerator(disp, None, None, None, *args, Trail())))


def main() -> None:
    print("Probe F071: char_type/2 on multi-codepoint grapheme")

    # Single-codepoint emoji works.
    smile = "\U0001f600"
    n = _run("char_type", 2, smile, "print")
    print(f"  char_type('😀', print)                   = {n}  (expected 1)")
    assert n == 1

    # Multi-codepoint thumbs-up + skin-tone (2 codepoints) silently fails.
    grapheme = "\U0001f44d\U0001f3fd"
    print(f"  len(thumbs+modifier) = {len(grapheme)} codepoints")
    for type_name in ("print", "alpha", "alnum", "ascii", "punct"):
        n = _run("char_type", 2, grapheme, type_name)
        print(f"  char_type(<2cp grapheme>, {type_name})       = {n}  (silent fail)")
        assert n == 0

    # Same shape with NFC vs NFD precomposed/decomposed 'é'.
    nfc = "é"          # one codepoint
    nfd = "é"         # two codepoints
    n_nfc = _run("char_type", 2, nfc, "alpha")
    n_nfd = _run("char_type", 2, nfd, "alpha")
    print(f"  char_type(NFC 'é', alpha)                = {n_nfc}  (expected 1)")
    print(f"  char_type(NFD 'é', alpha)                = {n_nfd}  (silent fail; 2cp)")
    assert n_nfc == 1
    assert n_nfd == 0

    print()
    print("  Verdict: char_type/2 fails silently on graphemes that span")
    print("  more than one codepoint.  Codepoint-level contract is internally")
    print("  consistent (mirrors [[F002]]), but the silent-fail behaviour is")
    print("  worth a documentation note alongside the str-as-list rules.")


if __name__ == "__main__":
    main()
