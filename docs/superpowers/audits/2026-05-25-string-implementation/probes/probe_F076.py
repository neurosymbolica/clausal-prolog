"""Probe F076: sub_atom/5 and atom_concat/3 split at codepoint boundaries.

Both predicates index into the str via codepoint offsets:
  * ``sub_atom`` uses ``va[b:b+l]`` (``chars.py:483``) and
    ``PyUnicode_Substring(atom_str, b, b+l)`` (``_chars_core.c:450``).
  * ``atom_concat`` enumerates splits ``sc[:i], sc[i:]`` for
    ``i ∈ [0, len(sc)]`` (``chars.py:386-390`` and
    ``_chars_core.c:272-298``).

A user-perceived grapheme that spans multiple codepoints (thumbs-up +
skin-tone modifier; NFD ``é`` = e + combining acute; family emoji
sequences) is *split in the middle* by these enumerations.  The
resulting substrings contain isolated modifier codepoints with no base
character — visually broken on rendering, semantically meaningless.

Severity: doc-only.  This is the same contract as [[F002]] / [[F004]]:
codepoint-level indexing, no grapheme awareness.  Internally consistent;
the gap is documentation.  Worth flagging that for ISO-Prolog
applications targeting human-readable text the user must normalise to
NFC and avoid emoji sequences when relying on positional predicates.
"""
from __future__ import annotations

from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions


def _collect(name, arity, *args, snap):
    disp = get_builtin_dispatch(name, arity, None)
    return solutions(StepGenerator(disp, None, None, None, *args, Trail()),
                     snapshot=snap)


def main() -> None:
    print("Probe F076: sub_atom and atom_concat split graphemes")

    # Thumbs-up + skin-tone modifier — 2 codepoints, 1 grapheme.
    g = "\U0001f44d\U0001f3fd"
    print(f"  Input: '{g}' (len={len(g)} codepoints, 1 grapheme)")
    print()

    # atom_concat enumerates 3 splits, one of which breaks the grapheme.
    A, B = Var(), Var()
    splits = _collect("atom_concat", 3, A, B, g,
                      snap=lambda: (deref(A), deref(B)))
    print(f"  atom_concat(A, B, <grapheme>):")
    for a, b in splits:
        marker = "  <-- broken grapheme" if 0 < len(a) < len(g) else ""
        print(f"    A={a!r:12s}  B={b!r:12s}{marker}")
    assert len(splits) == 3

    # sub_atom of length 1 — yields each codepoint, not the grapheme.
    print()
    A, S = Var(), Var()
    one_cp = _collect("sub_atom", 5, g, 0, 1, A, S,
                      snap=lambda: (deref(A), deref(S)))
    print(f"  sub_atom(<grapheme>, 0, 1, A, S): {one_cp}")
    # Expected one element if 'sub' indexed graphemes; got 1 element that
    # is the first codepoint alone (no skin-tone modifier).
    assert one_cp == [(1, "\U0001f44d")]

    # NFD 'é' = e + combining acute (2 codepoints).
    nfd = "é"
    print()
    print(f"  NFD 'é' = e + combining acute (len={len(nfd)})")
    A, B = Var(), Var()
    splits = _collect("atom_concat", 3, A, B, nfd,
                      snap=lambda: (deref(A), deref(B)))
    print(f"  atom_concat(A, B, NFD-é):")
    for a, b in splits:
        marker = "  <-- combining mark left dangling" if a == "e" else ""
        print(f"    A={a!r:8s}  B={b!r:8s}{marker}")

    print()
    print("  Verdict: positional predicates split at codepoint boundaries.")
    print("  Document this alongside [[F002]] / [[F004]] / [[F007]] — the")
    print("  whole codepoint-vs-grapheme story is one paragraph in the user")
    print("  docs.  No code change recommended.")


if __name__ == "__main__":
    main()
