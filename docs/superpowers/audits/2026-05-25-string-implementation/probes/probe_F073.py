"""Probe F073: char_code/2 and atom_codes/2 raise raw Python
``ValueError`` for out-of-range code points instead of a Prolog error.

``char_code(C, N)`` and ``atom_codes(A, [..., N, ...])`` both materialise
characters via ``chr(N)``.  Python's ``chr`` raises ``ValueError`` for
``N < 0`` or ``N >= 0x110000``.  Neither builtin wraps the call in a
try/except — the raw ``ValueError`` propagates out of the trampoline as
an uncaught Python exception, which is *not* a Prolog ``error/2`` term.

Affected sites:
  * ``chars.py:190``  — ``unify(char, chr(vn), trail)`` in
    ``char_code/2`` (negative-int branch is type_error guarded at
    ``chars.py:187``, but ``vn >= 0x110000`` is not).
  * ``chars.py:323``  — ``elems.append(chr(e))`` in ``atom_codes/2``.
    No range check at all — ``[-1]`` and ``[0x110000]`` both crash.
  * ``chars.py:571``  — same pattern in ``number_codes/2``.

Each ought to raise a proper ``representation_error(character_code)``
(ISO-aligned) or ``type_error(integer, ...)``.  Classed as C12 (char
representation drift): the int-code domain is wider than the str
char domain, and the boundary is unguarded.

Severity: bug.  A user program that takes user-supplied codes via
``read``/``parse`` should be able to catch the failure, not see a
``ValueError`` leak.
"""
from __future__ import annotations

from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.exceptions import LogicException


def _run(name, arity, *args):
    disp = get_builtin_dispatch(name, arity, None)
    return solutions(StepGenerator(disp, None, None, None, *args, Trail()))


def main() -> None:
    print("Probe F073: out-of-range codes leak ValueError")

    # char_code/2 with N == 0x110000 (one past max).
    v = Var()
    try:
        _run("char_code", 2, v, 0x110000)
        print("  char_code(V, 0x110000)        OK (unexpected)")
    except LogicException as e:
        print(f"  char_code(V, 0x110000)        LogicException OK: {e}")
    except ValueError as e:
        print(f"  char_code(V, 0x110000)        BUG: raw ValueError: {e}")

    # atom_codes/2 with negative element.
    v = Var()
    try:
        _run("atom_codes", 2, v, [-1])
        print("  atom_codes(V, [-1])           OK (unexpected)")
    except LogicException as e:
        print(f"  atom_codes(V, [-1])           LogicException OK: {e}")
    except ValueError as e:
        print(f"  atom_codes(V, [-1])           BUG: raw ValueError: {e}")

    # atom_codes/2 with too-big element.
    v = Var()
    try:
        _run("atom_codes", 2, v, [0x110000])
        print("  atom_codes(V, [0x110000])     OK (unexpected)")
    except LogicException as e:
        print(f"  atom_codes(V, [0x110000])     LogicException OK: {e}")
    except ValueError as e:
        print(f"  atom_codes(V, [0x110000])     BUG: raw ValueError: {e}")

    # number_codes/2 — same path.
    v = Var()
    try:
        _run("number_codes", 2, v, [-1])
        print("  number_codes(V, [-1])         OK (unexpected)")
    except LogicException as e:
        print(f"  number_codes(V, [-1])         LogicException OK: {e}")
    except ValueError as e:
        print(f"  number_codes(V, [-1])         BUG: raw ValueError: {e}")

    print()
    print("  Verdict: a Prolog program cannot catch these failures with")
    print("  catch/3 — a raw ValueError leaks through the trampoline.  Fix")
    print("  is local: guard each ``chr(vn)`` / ``chr(e)`` with an explicit")
    print("  range check that raises ``representation_error(character_code)``.")


if __name__ == "__main__":
    main()
