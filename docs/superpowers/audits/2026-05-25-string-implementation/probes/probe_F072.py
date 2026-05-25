"""Probe F072: char_type/2 mode asymmetry — Char-bound supports
non-ASCII, Type-bound enumeration is ASCII-only.

``char_type/2`` has two enumerative modes.  They disagree on which
characters the relation contains:

1.  Char bound, Type unbound (or both bound, test mode): for non-ASCII
    characters the C path falls back to ``Py_UNICODE_ISALPHA`` etc.
    (``_chars_core.c:165-179``) and the Python fallback uses
    ``_CHAR_TYPES`` dispatch (``chars.py:127``).  Greek ``α`` correctly
    classifies as ``alpha`` / ``alnum`` / ``lower`` / ``print``.
2.  Type bound, Char unbound: both the C path
    (``_chars_core.c:226-247``, iterates ``type_to_chars``) and the
    Python fallback (``chars.py:151``, iterates ``_TYPE_TO_CHARS``) only
    return ASCII chars [0..127].

Consequence: ``char_type('α', alpha)`` succeeds, but
``findall(C, char_type(C, alpha), L)`` returns only ASCII alpha
characters (52 entries).  ``α`` is *in* the relation under one mode and
*not* enumerated under the other — the relation isn't well-defined.

Classed as C9 (polymorphic builtin mode matrix).  Bug, not doc-only:
the test-mode and enum-mode answers contradict each other.
"""
from __future__ import annotations

from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions


def _run(name, arity, *args):
    disp = get_builtin_dispatch(name, arity, None)
    return len(solutions(StepGenerator(disp, None, None, None, *args, Trail())))


def _collect(name, arity, *args, snap):
    disp = get_builtin_dispatch(name, arity, None)
    return solutions(StepGenerator(disp, None, None, None, *args, Trail()),
                     snapshot=snap)


def main() -> None:
    print("Probe F072: char_type/2 Char-bound vs Type-bound mode mismatch")

    # Char-bound mode — non-ASCII works.
    n = _run("char_type", 2, "α", "alpha")
    print(f"  char_type('α', alpha)                   = {n}  (expected 1)")
    assert n == 1

    v = Var()
    types_for_alpha = _collect("char_type", 2, "α", v, snap=lambda: deref(v))
    print(f"  char_type('α', T) enumerates             = {types_for_alpha}")
    assert "alpha" in types_for_alpha

    # Type-bound mode — only ASCII enumerated.
    v = Var()
    chars_for_alpha = _collect("char_type", 2, v, "alpha", snap=lambda: deref(v))
    print(f"  findall(C, char_type(C, alpha)) count   = {len(chars_for_alpha)}")
    print(f"    first 4: {chars_for_alpha[:4]}    last 4: {chars_for_alpha[-4:]}")
    assert "α" not in chars_for_alpha
    assert len(chars_for_alpha) == 52  # ASCII A-Z + a-z

    print()
    print("  Verdict: the relation ``char_type/2`` is not consistent across")
    print("  modes — 'α' is in the relation when Char is bound, but not when")
    print("  Char is enumerated.  Either the Char-bound mode should be ASCII-")
    print("  only too (matching the enumeration), or the enumeration should")
    print("  cover the full Unicode general categories (impractical: ~155k")
    print("  codepoints).  Most ISO Prologs solve this by documenting that")
    print("  Type-bound mode enumerates only over a fixed alphabet.")


if __name__ == "__main__":
    main()
