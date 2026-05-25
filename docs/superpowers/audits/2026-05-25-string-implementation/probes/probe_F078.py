"""Probe F078: ``_chars_core.c::py_char_type_find_chars`` has dead
non-ASCII branch.

At ``_chars_core.c:228-234`` the function checks
``(ch < 128) ? ascii_char_objs[ch] : NULL`` and, when the cached
ASCII singleton lookup misses, falls back to
``PyUnicode_FromKindAndData(PyUnicode_1BYTE_KIND, &ch, 1)`` with
``need_decref = 1``.

But ``type_to_chars`` is populated only for ``i ∈ [0, 128)`` at
``_chars_core.c:130-132`` — every codepoint in the table is ASCII.
So the ``!ch_obj`` branch is unreachable.  The dead branch is the
only place in this file that pairs an alloc with a conditional
DECREF; the rest of the file uses unconditional cleanup which is
easier to audit.

Severity: smell.  Two effects worth flagging:
  1. Static reviewers (and this audit!) have to walk an alloc/DECREF
     branch that never runs to convince themselves nothing leaks.
  2. If a future change widens ``type_to_chars`` to cover Unicode
     general categories (see [[F072]]), the existing code is *almost*
     right — but the ``PyUnicode_1BYTE_KIND`` kind is wrong for
     codepoints ≥ 0x100; the call would produce a corrupted string.

No correctness bug today; document the dead branch or remove it.
Static review only — no probe behaviour to demonstrate.
"""
from __future__ import annotations


def main() -> None:
    print("Probe F078: static-review note on _chars_core.c dead branch")
    print()
    print("  File: clausal/logic/builtins/_chars_core.c")
    print("  Lines: 226-234, 130-132")
    print()
    print("  Initialisation loop populates type_to_chars[t][i] from")
    print("  i = 0..127 only.  The runtime ``ch < 128`` test is therefore")
    print("  always True; the ``PyUnicode_FromKindAndData`` fallback is")
    print("  dead code.  Recommended: drop the branch (and the")
    print("  need_decref flag) or expand type_to_chars to actually cover")
    print("  the non-ASCII Unicode general categories — see [[F072]] for")
    print("  the motivating mode-matrix asymmetry.")
    print()
    print("  If the table is expanded, the PyUnicode_1BYTE_KIND argument")
    print("  to PyUnicode_FromKindAndData is wrong for codepoints ≥ 256")
    print("  (would silently produce a malformed string).  Use")
    print("  PyUnicode_FromOrdinal((int)ch) instead.")


if __name__ == "__main__":
    main()
