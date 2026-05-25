"""Probe F074: upcase_atom/downcase_atom can change string length.

``upcase_atom/2`` and ``downcase_atom/2`` call ``.upper()`` / ``.lower()``
on the underlying Python str (``chars.py:207``/``:222``).  Python's case
mappings follow the Unicode special-casing table — a few graphemes
expand or contract on case conversion.  Examples:

  * German sharp s ``"ß"`` (1 codepoint) → ``.upper() = "SS"`` (2 cps)
  * Greek small letter final sigma ``"ς"`` and small sigma ``"σ"`` both
    map to capital sigma ``"Σ"`` (round-trip is not the identity).
  * Title-cased ligatures: ``"ﬃ"`` → ``"FFI"`` (3 cps).

Consequence for the strings-as-lists contract:
  * ``atom_length(A, La), upcase_atom(A, B), atom_length(B, Lb)`` may
    have ``La != Lb`` — surprising under the "1 codepoint per char"
    rule, because the case-folding operation is *not* a per-character
    function.
  * Round-tripping ``downcase_atom(upcase_atom(A))`` is not guaranteed
    to return ``A`` even up to case (e.g. ``ß`` → ``SS`` → ``ss``).

Severity: doc-only.  Python's case folding is the right primitive;
the gap is purely documentation.  Classed under C7 (Unicode); related
to [[F003]] (NFC/NFD) and [[F071]] (multi-codepoint graphemes).
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
    print("Probe F074: upcase_atom / downcase_atom length changes")

    v = Var()
    r = _collect("upcase_atom", 2, "straße", v, snap=lambda: deref(v))
    print(f"  upcase_atom('straße', U):    U = {r[0]!r}   "
          f"(in_len=6, out_len={len(r[0])})")
    assert r == ["STRASSE"]

    # Round-trip not identity.
    v2 = Var()
    r2 = _collect("downcase_atom", 2, r[0], v2, snap=lambda: deref(v2))
    print(f"  downcase_atom('STRASSE', D): D = {r2[0]!r}   "
          f"(was 'straße' before upcase!)")
    assert r2 == ["strasse"]   # not 'straße'

    # Sigma round-trip: final ς and medial σ both → Σ → σ
    v3 = Var()
    r3 = _collect("upcase_atom", 2, "ς", v3, snap=lambda: deref(v3))
    print(f"  upcase_atom('ς', U):         U = {r3[0]!r}")
    v4 = Var()
    r4 = _collect("downcase_atom", 2, r3[0], v4, snap=lambda: deref(v4))
    print(f"  downcase_atom('Σ', D):       D = {r4[0]!r}   "
          f"(was 'ς' before upcase!)")
    assert r3 == ["Σ"]
    assert r4 == ["σ"]   # the *medial* form, not the original final

    # Ligature expansion: small ffi ﬃ → FFI
    v5 = Var()
    r5 = _collect("upcase_atom", 2, "ﬃ", v5, snap=lambda: deref(v5))
    print(f"  upcase_atom('ﬃ', U):         U = {r5[0]!r}   "
          f"(in_len=1, out_len={len(r5[0])})")
    assert r5 == ["FFI"]

    print()
    print("  Verdict: case conversion is locale-aware and not bijective on")
    print("  codepoint length.  Document that:")
    print("    - atom_length is not preserved by upcase/downcase.")
    print("    - upcase ∘ downcase is not the identity even up to case.")
    print("  No code change recommended; the underlying Python semantics")
    print("  are the standard.")


if __name__ == "__main__":
    main()
