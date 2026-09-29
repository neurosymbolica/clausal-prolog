"""C12 — Char representation drift.

1 bug finding. char_code/2 and atom_codes/2 leak raw Python ValueError
when given out-of-range code points (≥ 0x110000); a Prolog program
cannot catch the failure via catch/3.

Findings tested here:
- F073 (bug) chr() ValueError leak on out-of-range char codes
"""

import pytest

from clausal.logic.variables import Var, Trail, deref
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.exceptions import LogicException


def _run(name, arity, *args, trail=None):
    """Run a builtin and return the number of solutions."""
    if trail is None:
        trail = Trail()
    dispatch = get_builtin_dispatch(name, arity, None)
    return len(solutions(StepGenerator(dispatch, None, None, None, *args, trail)))


def test_F073_char_code_out_of_range_fails_logically():
    """char_code(V, 0x110000) should fail logically, not leak ValueError.

    char_code/2 calls chr(N) without guarding against out-of-range codes.
    Python's chr() raises ValueError for N < 0 or N >= 0x110000.

    The bug: the raw ValueError propagates through the trampoline as an
    uncaught Python exception — it is *not* a Prolog error/2 term, so
    catch/3 in Prolog cannot intercept it.

    Expected: either 0 solutions (logical failure) or a proper Prolog
    error term (type_error or representation_error).

    Actual (bug): raw ValueError leaks.
    """
    v = Var()

    # Should not raise ValueError; should either fail logically (0 solutions)
    # or raise LogicException.
    # 2026-09-30: ISO 8.16.6.3 / Scryer -- representation_error(character_code),
    # not a silent failure (todo/done/builtins-fail-silently-on-bad-arguments).
    with pytest.raises(LogicException) as info:
        _run("char_code", 2, v, 0x110000)
    assert info.value.term[1] == ("representation_error", "character_code")


def test_F073_char_code_negative_code_fails_logically():
    """char_code(V, -1) should fail logically, not leak ValueError.

    Symmetric case: negative out-of-range code.
    """
    v = Var()

    # 2026-09-30: ISO / Scryer -- representation_error(character_code).
    with pytest.raises(LogicException) as info:
        _run("char_code", 2, v, -1)
    assert info.value.term[1] == ("representation_error", "character_code")


def test_F073_atom_codes_negative_element_fails_logically():
    """atom_codes(V, [-1]) should fail logically, not leak ValueError.

    atom_codes/2 materialises characters via chr(e) for each element e
    in the codes list. No range check guards the call.

    Expected: 0 solutions (logical failure) or LogicException.
    Actual (bug): raw ValueError.
    """
    v = Var()

    try:
        n = _run("atom_codes", 2, v, [-1])
    except ValueError as e:
        pytest.fail(
            f"atom_codes(V, [-1]) leaked raw ValueError: {e}. "
            f"This is the bug F073 — catch/3 cannot intercept it."
        )

    assert n == 0, (
        f"expected logical failure (0 solutions) for atom_codes(V, [-1]), "
        f"got {n}"
    )


def test_F073_atom_codes_out_of_range_element_fails_logically():
    """atom_codes(V, [0x110000]) should fail logically, not leak ValueError.

    Symmetric case: code >= 0x110000.
    """
    v = Var()

    try:
        n = _run("atom_codes", 2, v, [0x110000])
    except ValueError as e:
        pytest.fail(
            f"atom_codes(V, [0x110000]) leaked raw ValueError: {e}. "
            f"This is the bug F073 — catch/3 cannot intercept it."
        )

    assert n == 0, (
        f"expected logical failure (0 solutions) for atom_codes(V, [0x110000]), "
        f"got {n}"
    )


def test_F073_number_codes_negative_element_fails_logically():
    """number_codes(V, [-1]) should fail logically, not leak ValueError.

    number_codes/2 has the same chr(e) call site as atom_codes/2.
    """
    v = Var()

    try:
        n = _run("number_codes", 2, v, [-1])
    except ValueError as e:
        pytest.fail(
            f"number_codes(V, [-1]) leaked raw ValueError: {e}. "
            f"This is the bug F073 — catch/3 cannot intercept it."
        )

    assert n == 0, (
        f"expected logical failure (0 solutions) for number_codes(V, [-1]), "
        f"got {n}"
    )


def test_F073_number_codes_out_of_range_element_fails_logically():
    """number_codes(V, [0x110000]) should fail logically, not leak ValueError.

    Symmetric case: code >= 0x110000 in number_codes.
    """
    v = Var()

    try:
        n = _run("number_codes", 2, v, [0x110000])
    except ValueError as e:
        pytest.fail(
            f"number_codes(V, [0x110000]) leaked raw ValueError: {e}. "
            f"This is the bug F073 — catch/3 cannot intercept it."
        )

    assert n == 0, (
        f"expected logical failure (0 solutions) for number_codes(V, [0x110000]), "
        f"got {n}"
    )
