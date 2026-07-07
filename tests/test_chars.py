"""Tests for Phase 2 character/string builtins: char_type/2, char_code/2,
upcase_atom/2, downcase_atom/2, atom_length/2, atom_chars/2, atom_codes/2,
atom_concat/3, sub_atom/5.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.exceptions import LogicException


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(name, arity, *args, trail=None):
    """Run a builtin and return the number of solutions."""
    if trail is None:
        trail = Trail()
    dispatch = get_builtin_dispatch(name, arity, None)
    return len(solutions(StepGenerator(dispatch, None, None, None, *args, trail)))


def _run_collect(name, arity, *args, trail=None, snap=None):
    """Run a builtin and collect snapshot values per solution."""
    if trail is None:
        trail = Trail()
    dispatch = get_builtin_dispatch(name, arity, None)
    return solutions(StepGenerator(dispatch, None, None, None, *args, trail),
                     snapshot=snap)


# ── char_type/2 ───────────────────────────────────────────────────────────────

class TestCharType:
    def test_both_bound_match(self):
        # nv
        assert _run("char_type", 2, "a", "alpha") > 0

    def test_both_bound_mismatch(self):
        # nv
        assert _run("char_type", 2, "a", "digit") == 0

    def test_digit_match(self):
        # nv
        assert _run("char_type", 2, "1", "digit") > 0

    def test_upper_match(self):
        # nv
        assert _run("char_type", 2, "A", "upper") > 0

    def test_space_match(self):
        # nv
        assert _run("char_type", 2, " ", "space") > 0

    def test_punct_match(self):
        # nv
        assert _run("char_type", 2, "!", "punct") > 0

    def test_not_single_char_fails(self):
        # nv
        assert _run("char_type", 2, "ab", "alpha") == 0

    def test_enum_types_for_char(self):
        """char_type('a', TYPE) → enumerate matching types."""
        # nv
        TYPE = Var()
        results = _run_collect("char_type", 2, "a", TYPE,
                               snap=lambda: deref(TYPE))
        assert "alpha" in results
        assert "alnum" in results
        assert "lower" in results
        assert "ascii" in results
        assert "print" in results
        assert "digit" not in results

    def test_enum_chars_for_digit(self):
        """char_type(C, 'digit') → enumerate every Unicode digit.

        A09-F013: digit is Unicode-aware in test-mode (``char_type('٣',
        digit)`` succeeds via ``str.isdigit``), so the enumeration must be
        too — it includes the ASCII digits and Unicode digits like the
        Arabic-Indic three.
        """
        # nv
        C = Var()
        results = _run_collect("char_type", 2, C, "digit",
                               snap=lambda: deref(C))
        assert set(str(i) for i in range(10)) <= set(results)
        assert "٣" in results  # ARABIC-INDIC THREE
        assert all(c.isdigit() for c in results)

    def test_both_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("char_type", 2, Var(), Var())

    def test_control_char(self):
        # nv
        assert _run("char_type", 2, chr(0), "control") > 0

    def test_ascii_char(self):
        # nv
        assert _run("char_type", 2, "z", "ascii") > 0


# ── char_code/2 ───────────────────────────────────────────────────────────────

class TestCharCode:
    def test_char_to_code(self):
        # nv
        N = Var()
        results = _run_collect("char_code", 2, "A", N, snap=lambda: deref(N))
        assert results == [65]

    def test_code_to_char(self):
        # nv
        C = Var()
        results = _run_collect("char_code", 2, C, 65, snap=lambda: deref(C))
        assert results == ["A"]

    def test_both_bound_match(self):
        # nv
        assert _run("char_code", 2, "A", 65) > 0

    def test_both_bound_mismatch(self):
        # nv
        assert _run("char_code", 2, "A", 66) == 0

    def test_both_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("char_code", 2, Var(), Var())

    def test_non_char_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("char_code", 2, "AB", Var())


# ── upcase_atom/2, downcase_atom/2 ────────────────────────────────────────────

class TestCaseConversion:
    def test_upcase(self):
        # nv
        S = Var()
        results = _run_collect("upcase_atom", 2, "hello", S,
                               snap=lambda: deref(S))
        assert results == ["HELLO"]

    def test_upcase_mixed(self):
        # nv
        S = Var()
        results = _run_collect("upcase_atom", 2, "Hello World", S,
                               snap=lambda: deref(S))
        assert results == ["HELLO WORLD"]

    def test_downcase(self):
        # nv
        S = Var()
        results = _run_collect("downcase_atom", 2, "HELLO", S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_upcase_empty(self):
        # nv
        S = Var()
        results = _run_collect("upcase_atom", 2, "", S, snap=lambda: deref(S))
        assert results == [""]

    def test_upcase_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("upcase_atom", 2, Var(), Var())

    def test_upcase_non_string_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("upcase_atom", 2, 42, Var())


# ── atom_length/2 ─────────────────────────────────────────────────────────────

class TestAtomLength:
    def test_length(self):
        # nv
        N = Var()
        results = _run_collect("atom_length", 2, "hello", N,
                               snap=lambda: deref(N))
        assert results == [5]

    def test_empty(self):
        # nv
        N = Var()
        results = _run_collect("atom_length", 2, "", N, snap=lambda: deref(N))
        assert results == [0]

    def test_both_bound_match(self):
        # nv
        assert _run("atom_length", 2, "hello", 5) > 0

    def test_both_bound_mismatch(self):
        # nv
        assert _run("atom_length", 2, "hello", 3) == 0

    def test_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_length", 2, Var(), Var())


# ── atom_chars/2 ──────────────────────────────────────────────────────────────

class TestAtomChars:
    def test_atom_to_chars(self):
        # nv
        L = Var()
        results = _run_collect("atom_chars", 2, "hi", L, snap=lambda: deref(L))
        assert results == [["h", "i"]]

    def test_chars_to_atom(self):
        # nv
        A = Var()
        results = _run_collect("atom_chars", 2, A, ["h", "i"],
                               snap=lambda: deref(A))
        assert results == ["hi"]

    def test_both_bound_match(self):
        # nv
        assert _run("atom_chars", 2, "hi", ["h", "i"]) > 0

    def test_empty(self):
        # nv
        L = Var()
        results = _run_collect("atom_chars", 2, "", L, snap=lambda: deref(L))
        assert results == [[]]

    def test_both_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_chars", 2, Var(), Var())


# ── atom_codes/2 ──────────────────────────────────────────────────────────────

class TestAtomCodes:
    def test_atom_to_codes(self):
        # nv
        L = Var()
        results = _run_collect("atom_codes", 2, "hi", L, snap=lambda: deref(L))
        assert results == [[104, 105]]

    def test_codes_to_atom(self):
        # nv
        A = Var()
        results = _run_collect("atom_codes", 2, A, [104, 105],
                               snap=lambda: deref(A))
        assert results == ["hi"]

    def test_both_bound_match(self):
        # nv
        assert _run("atom_codes", 2, "hi", [104, 105]) > 0

    def test_both_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_codes", 2, Var(), Var())


# ── atom_concat/3 ─────────────────────────────────────────────────────────────

class TestAtomConcat:
    def test_forward(self):
        # nv
        S = Var()
        results = _run_collect("atom_concat", 3, "hel", "lo", S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_forward_empty_left(self):
        # nv
        S = Var()
        results = _run_collect("atom_concat", 3, "", "hello", S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_forward_empty_right(self):
        # nv
        S = Var()
        results = _run_collect("atom_concat", 3, "hello", "", S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_reverse_enumerate_splits(self):
        """atom_concat(A, B, 'abc') → 4 solutions."""
        # nv
        A = Var()
        B = Var()
        results = _run_collect("atom_concat", 3, A, B, "abc",
                               snap=lambda: (deref(A), deref(B)))
        assert results == [("", "abc"), ("a", "bc"), ("ab", "c"), ("abc", "")]

    def test_prefix_bound(self):
        # nv
        B = Var()
        results = _run_collect("atom_concat", 3, "a", B, "abc",
                               snap=lambda: deref(B))
        assert results == ["bc"]

    def test_suffix_bound(self):
        # nv
        A = Var()
        results = _run_collect("atom_concat", 3, A, "bc", "abc",
                               snap=lambda: deref(A))
        assert results == ["a"]

    def test_all_bound_match(self):
        # nv
        assert _run("atom_concat", 3, "a", "bc", "abc") > 0

    def test_all_bound_mismatch(self):
        # nv
        assert _run("atom_concat", 3, "x", "bc", "abc") == 0

    def test_all_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_concat", 3, Var(), Var(), Var())

    def test_c_unbound_a_bound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_concat", 3, "abc", Var(), Var())


# ── sub_atom/5 ────────────────────────────────────────────────────────────────

class TestSubAtom:
    def test_all_bound_extract(self):
        # nv
        S = Var()
        results = _run_collect("sub_atom", 5, "hello", 1, 3, 1, S,
                               snap=lambda: deref(S))
        assert results == ["ell"]

    def test_whole_string(self):
        # nv
        S = Var()
        results = _run_collect("sub_atom", 5, "hello", 0, 5, 0, S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_empty_prefix(self):
        # nv
        S = Var()
        results = _run_collect("sub_atom", 5, "hello", 0, 0, 5, S,
                               snap=lambda: deref(S))
        assert results == [""]

    def test_sub_bound_find(self):
        # nv
        B = Var()
        results = _run_collect("sub_atom", 5, "hello", B, Var(), Var(), "ell",
                               snap=lambda: deref(B))
        assert results == [1]

    def test_sub_bound_multiple_occurrences(self):
        """sub_atom('abcabc', B, _, _, 'bc') → B=1 and B=4."""
        # nv
        B = Var()
        results = _run_collect("sub_atom", 5, "abcabc", B, Var(), Var(), "bc",
                               snap=lambda: deref(B))
        assert results == [1, 4]

    def test_length_bound_enumerate(self):
        """sub_atom('abc', B, 1, A, S) → 3 solutions."""
        # nv
        B = Var()
        A = Var()
        S = Var()
        results = _run_collect("sub_atom", 5, "abc", B, 1, A, S,
                               snap=lambda: (deref(B), deref(A), deref(S)))
        assert results == [(0, 2, "a"), (1, 1, "b"), (2, 0, "c")]

    def test_all_unbound_enumerate(self):
        """sub_atom('abc', B, L, A, S) → 10 solutions (all substrings)."""
        # nv
        assert _run("sub_atom", 5, "abc", Var(), Var(), Var(), Var()) == 10

    def test_inconsistent_fails(self):
        """sub_atom('hello', 1, 3, 2, 'ell') → fails (After should be 1)."""
        # nv
        assert _run("sub_atom", 5, "hello", 1, 3, 2, "ell") == 0

    def test_consistent_succeeds(self):
        # nv
        assert _run("sub_atom", 5, "hello", 1, 3, 1, "ell") > 0

    def test_unbound_atom_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("sub_atom", 5, Var(), 0, 1, Var(), Var())

    def test_empty_string(self):
        """sub_atom('', B, L, A, S) → 1 solution: (0,0,0,'')."""
        # nv
        B = Var()
        L = Var()
        A = Var()
        S = Var()
        results = _run_collect("sub_atom", 5, "", B, L, A, S,
                               snap=lambda: (deref(B), deref(L),
                                             deref(A), deref(S)))
        assert results == [(0, 0, 0, "")]

    def test_before_bound_enumerate(self):
        """sub_atom('abc', 0, L, A, S) → 4 solutions (all prefixes)."""
        # nv
        L = Var()
        A = Var()
        S = Var()
        results = _run_collect("sub_atom", 5, "abc", 0, L, A, S,
                               snap=lambda: (deref(L), deref(A), deref(S)))
        assert results == [(0, 3, ""), (1, 2, "a"), (2, 1, "ab"), (3, 0, "abc")]


# ── number_chars/2 ──────────────────────────────────────────────────────────────


class TestNumberChars:

    def test_int_forward(self):
        """number_chars(42, C) → ["4", "2"]."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, 42, v,
                               snap=lambda: deref(v))
        assert results == [["4", "2"]]

    def test_int_reverse(self):
        """number_chars(N, ["4", "2"]) → N = 42."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, v, ["4", "2"],
                               snap=lambda: deref(v))
        assert results == [42]

    def test_float_forward(self):
        """number_chars(3.14, C) → ["3", ".", "1", "4"]."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, 3.14, v,
                               snap=lambda: deref(v))
        assert results == [["3", ".", "1", "4"]]

    def test_float_reverse(self):
        """number_chars(N, ["3", ".", "1", "4"]) → N = 3.14."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, v, ["3", ".", "1", "4"],
                               snap=lambda: deref(v))
        assert results == [3.14]

    def test_negative(self):
        """number_chars(-5, C) → ["-", "5"]."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, -5, v,
                               snap=lambda: deref(v))
        assert results == [["-", "5"]]

    def test_invalid_chars_fails(self):
        """number_chars(N, ["a", "b"]) → no solutions."""
        # nv
        v = Var()
        assert _run("number_chars", 2, v, ["a", "b"]) == 0

    def test_both_bound_consistent(self):
        """number_chars(42, ["4", "2"]) → succeeds."""
        # nv
        assert _run("number_chars", 2, 42, ["4", "2"]) == 1

    def test_both_bound_inconsistent(self):
        """number_chars(42, ["4", "3"]) → fails."""
        # nv
        assert _run("number_chars", 2, 42, ["4", "3"]) == 0

    def test_both_unbound_raises(self):
        """number_chars(N, C) with both unbound → instantiation error."""
        # nv
        with pytest.raises(LogicException):
            _run("number_chars", 2, Var(), Var())

    def test_bool_raises(self):
        """number_chars(True, C) → type error (bool is not a number)."""
        # nv
        with pytest.raises(LogicException):
            _run("number_chars", 2, True, Var())


# ── number_codes/2 ──────────────────────────────────────────────────────────────


class TestNumberCodes:

    def test_int_forward(self):
        """number_codes(42, C) → [52, 50]."""
        # nv
        v = Var()
        results = _run_collect("number_codes", 2, 42, v,
                               snap=lambda: deref(v))
        assert results == [[52, 50]]

    def test_int_reverse(self):
        """number_codes(N, [52, 50]) → N = 42."""
        # nv
        v = Var()
        results = _run_collect("number_codes", 2, v, [52, 50],
                               snap=lambda: deref(v))
        assert results == [42]

    def test_float_forward(self):
        """number_codes(3.14, C) → code points of "3.14"."""
        # nv
        v = Var()
        results = _run_collect("number_codes", 2, 3.14, v,
                               snap=lambda: deref(v))
        assert results == [[ord(c) for c in "3.14"]]

    def test_float_reverse(self):
        """number_codes(N, [ord(c) for c in "3.14"]) → N = 3.14."""
        # nv
        v = Var()
        codes = [ord(c) for c in "3.14"]
        results = _run_collect("number_codes", 2, v, codes,
                               snap=lambda: deref(v))
        assert results == [3.14]

    def test_negative(self):
        """number_codes(-5, C) → code points of "-5"."""
        # nv
        v = Var()
        results = _run_collect("number_codes", 2, -5, v,
                               snap=lambda: deref(v))
        assert results == [[ord("-"), ord("5")]]

    def test_invalid_codes_fails(self):
        """number_codes(N, [ord('a'), ord('b')]) → no solutions."""
        # nv
        v = Var()
        assert _run("number_codes", 2, v, [ord("a"), ord("b")]) == 0

    def test_both_unbound_raises(self):
        """number_codes(N, C) with both unbound → instantiation error."""
        # nv
        with pytest.raises(LogicException):
            _run("number_codes", 2, Var(), Var())

    def test_non_int_code_raises(self):
        """number_codes(N, ["4", "2"]) with string elements → type error."""
        # nv
        with pytest.raises(LogicException):
            _run("number_codes", 2, Var(), ["4", "2"])
