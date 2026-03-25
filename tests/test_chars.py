"""Tests for Phase 2 character/string builtins: CharType/2, CharCode/2,
UpcaseAtom/2, DowncaseAtom/2, AtomLength/2, AtomChars/2, AtomCodes/2,
AtomConcat/3, SubAtom/5.
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
    return len(solutions(StepGenerator(dispatch, None, *args, trail)))


def _run_collect(name, arity, *args, trail=None, snap=None):
    """Run a builtin and collect snapshot values per solution."""
    if trail is None:
        trail = Trail()
    dispatch = get_builtin_dispatch(name, arity, None)
    return solutions(StepGenerator(dispatch, None, *args, trail),
                     snapshot=snap)


# ── CharType/2 ───────────────────────────────────────────────────────────────

class TestCharType:
    def test_both_bound_match(self):
        assert _run("CharType", 2, "a", "alpha") > 0

    def test_both_bound_mismatch(self):
        assert _run("CharType", 2, "a", "digit") == 0

    def test_digit_match(self):
        assert _run("CharType", 2, "1", "digit") > 0

    def test_upper_match(self):
        assert _run("CharType", 2, "A", "upper") > 0

    def test_space_match(self):
        assert _run("CharType", 2, " ", "space") > 0

    def test_punct_match(self):
        assert _run("CharType", 2, "!", "punct") > 0

    def test_not_single_char_fails(self):
        assert _run("CharType", 2, "ab", "alpha") == 0

    def test_enum_types_for_char(self):
        """CharType('a', TYPE) → enumerate matching types."""
        TYPE = Var()
        results = _run_collect("CharType", 2, "a", TYPE,
                               snap=lambda: deref(TYPE))
        assert "alpha" in results
        assert "alnum" in results
        assert "lower" in results
        assert "ascii" in results
        assert "print" in results
        assert "digit" not in results

    def test_enum_chars_for_digit(self):
        """CharType(C, 'digit') → enumerate '0'..'9' (10 solutions)."""
        C = Var()
        results = _run_collect("CharType", 2, C, "digit",
                               snap=lambda: deref(C))
        assert sorted(results) == [str(i) for i in range(10)]

    def test_both_unbound_error(self):
        with pytest.raises(LogicException):
            _run("CharType", 2, Var(), Var())

    def test_control_char(self):
        assert _run("CharType", 2, chr(0), "control") > 0

    def test_ascii_char(self):
        assert _run("CharType", 2, "z", "ascii") > 0


# ── CharCode/2 ───────────────────────────────────────────────────────────────

class TestCharCode:
    def test_char_to_code(self):
        N = Var()
        results = _run_collect("CharCode", 2, "A", N, snap=lambda: deref(N))
        assert results == [65]

    def test_code_to_char(self):
        C = Var()
        results = _run_collect("CharCode", 2, C, 65, snap=lambda: deref(C))
        assert results == ["A"]

    def test_both_bound_match(self):
        assert _run("CharCode", 2, "A", 65) > 0

    def test_both_bound_mismatch(self):
        assert _run("CharCode", 2, "A", 66) == 0

    def test_both_unbound_error(self):
        with pytest.raises(LogicException):
            _run("CharCode", 2, Var(), Var())

    def test_non_char_error(self):
        with pytest.raises(LogicException):
            _run("CharCode", 2, "AB", Var())


# ── UpcaseAtom/2, DowncaseAtom/2 ────────────────────────────────────────────

class TestCaseConversion:
    def test_upcase(self):
        S = Var()
        results = _run_collect("UpcaseAtom", 2, "hello", S,
                               snap=lambda: deref(S))
        assert results == ["HELLO"]

    def test_upcase_mixed(self):
        S = Var()
        results = _run_collect("UpcaseAtom", 2, "Hello World", S,
                               snap=lambda: deref(S))
        assert results == ["HELLO WORLD"]

    def test_downcase(self):
        S = Var()
        results = _run_collect("DowncaseAtom", 2, "HELLO", S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_upcase_empty(self):
        S = Var()
        results = _run_collect("UpcaseAtom", 2, "", S, snap=lambda: deref(S))
        assert results == [""]

    def test_upcase_unbound_error(self):
        with pytest.raises(LogicException):
            _run("UpcaseAtom", 2, Var(), Var())

    def test_upcase_non_string_error(self):
        with pytest.raises(LogicException):
            _run("UpcaseAtom", 2, 42, Var())


# ── AtomLength/2 ─────────────────────────────────────────────────────────────

class TestAtomLength:
    def test_length(self):
        N = Var()
        results = _run_collect("AtomLength", 2, "hello", N,
                               snap=lambda: deref(N))
        assert results == [5]

    def test_empty(self):
        N = Var()
        results = _run_collect("AtomLength", 2, "", N, snap=lambda: deref(N))
        assert results == [0]

    def test_both_bound_match(self):
        assert _run("AtomLength", 2, "hello", 5) > 0

    def test_both_bound_mismatch(self):
        assert _run("AtomLength", 2, "hello", 3) == 0

    def test_unbound_error(self):
        with pytest.raises(LogicException):
            _run("AtomLength", 2, Var(), Var())


# ── AtomChars/2 ──────────────────────────────────────────────────────────────

class TestAtomChars:
    def test_atom_to_chars(self):
        L = Var()
        results = _run_collect("AtomChars", 2, "hi", L, snap=lambda: deref(L))
        assert results == [["h", "i"]]

    def test_chars_to_atom(self):
        A = Var()
        results = _run_collect("AtomChars", 2, A, ["h", "i"],
                               snap=lambda: deref(A))
        assert results == ["hi"]

    def test_both_bound_match(self):
        assert _run("AtomChars", 2, "hi", ["h", "i"]) > 0

    def test_empty(self):
        L = Var()
        results = _run_collect("AtomChars", 2, "", L, snap=lambda: deref(L))
        assert results == [[]]

    def test_both_unbound_error(self):
        with pytest.raises(LogicException):
            _run("AtomChars", 2, Var(), Var())


# ── AtomCodes/2 ──────────────────────────────────────────────────────────────

class TestAtomCodes:
    def test_atom_to_codes(self):
        L = Var()
        results = _run_collect("AtomCodes", 2, "hi", L, snap=lambda: deref(L))
        assert results == [[104, 105]]

    def test_codes_to_atom(self):
        A = Var()
        results = _run_collect("AtomCodes", 2, A, [104, 105],
                               snap=lambda: deref(A))
        assert results == ["hi"]

    def test_both_bound_match(self):
        assert _run("AtomCodes", 2, "hi", [104, 105]) > 0

    def test_both_unbound_error(self):
        with pytest.raises(LogicException):
            _run("AtomCodes", 2, Var(), Var())


# ── AtomConcat/3 ─────────────────────────────────────────────────────────────

class TestAtomConcat:
    def test_forward(self):
        S = Var()
        results = _run_collect("AtomConcat", 3, "hel", "lo", S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_forward_empty_left(self):
        S = Var()
        results = _run_collect("AtomConcat", 3, "", "hello", S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_forward_empty_right(self):
        S = Var()
        results = _run_collect("AtomConcat", 3, "hello", "", S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_reverse_enumerate_splits(self):
        """AtomConcat(A, B, 'abc') → 4 solutions."""
        A = Var()
        B = Var()
        results = _run_collect("AtomConcat", 3, A, B, "abc",
                               snap=lambda: (deref(A), deref(B)))
        assert results == [("", "abc"), ("a", "bc"), ("ab", "c"), ("abc", "")]

    def test_prefix_bound(self):
        B = Var()
        results = _run_collect("AtomConcat", 3, "a", B, "abc",
                               snap=lambda: deref(B))
        assert results == ["bc"]

    def test_suffix_bound(self):
        A = Var()
        results = _run_collect("AtomConcat", 3, A, "bc", "abc",
                               snap=lambda: deref(A))
        assert results == ["a"]

    def test_all_bound_match(self):
        assert _run("AtomConcat", 3, "a", "bc", "abc") > 0

    def test_all_bound_mismatch(self):
        assert _run("AtomConcat", 3, "x", "bc", "abc") == 0

    def test_all_unbound_error(self):
        with pytest.raises(LogicException):
            _run("AtomConcat", 3, Var(), Var(), Var())

    def test_c_unbound_a_bound_error(self):
        with pytest.raises(LogicException):
            _run("AtomConcat", 3, "abc", Var(), Var())


# ── SubAtom/5 ────────────────────────────────────────────────────────────────

class TestSubAtom:
    def test_all_bound_extract(self):
        S = Var()
        results = _run_collect("SubAtom", 5, "hello", 1, 3, 1, S,
                               snap=lambda: deref(S))
        assert results == ["ell"]

    def test_whole_string(self):
        S = Var()
        results = _run_collect("SubAtom", 5, "hello", 0, 5, 0, S,
                               snap=lambda: deref(S))
        assert results == ["hello"]

    def test_empty_prefix(self):
        S = Var()
        results = _run_collect("SubAtom", 5, "hello", 0, 0, 5, S,
                               snap=lambda: deref(S))
        assert results == [""]

    def test_sub_bound_find(self):
        B = Var()
        results = _run_collect("SubAtom", 5, "hello", B, Var(), Var(), "ell",
                               snap=lambda: deref(B))
        assert results == [1]

    def test_sub_bound_multiple_occurrences(self):
        """SubAtom('abcabc', B, _, _, 'bc') → B=1 and B=4."""
        B = Var()
        results = _run_collect("SubAtom", 5, "abcabc", B, Var(), Var(), "bc",
                               snap=lambda: deref(B))
        assert results == [1, 4]

    def test_length_bound_enumerate(self):
        """SubAtom('abc', B, 1, A, S) → 3 solutions."""
        B = Var()
        A = Var()
        S = Var()
        results = _run_collect("SubAtom", 5, "abc", B, 1, A, S,
                               snap=lambda: (deref(B), deref(A), deref(S)))
        assert results == [(0, 2, "a"), (1, 1, "b"), (2, 0, "c")]

    def test_all_unbound_enumerate(self):
        """SubAtom('abc', B, L, A, S) → 10 solutions (all substrings)."""
        assert _run("SubAtom", 5, "abc", Var(), Var(), Var(), Var()) == 10

    def test_inconsistent_fails(self):
        """SubAtom('hello', 1, 3, 2, 'ell') → fails (After should be 1)."""
        assert _run("SubAtom", 5, "hello", 1, 3, 2, "ell") == 0

    def test_consistent_succeeds(self):
        assert _run("SubAtom", 5, "hello", 1, 3, 1, "ell") > 0

    def test_unbound_atom_error(self):
        with pytest.raises(LogicException):
            _run("SubAtom", 5, Var(), 0, 1, Var(), Var())

    def test_empty_string(self):
        """SubAtom('', B, L, A, S) → 1 solution: (0,0,0,'')."""
        B = Var()
        L = Var()
        A = Var()
        S = Var()
        results = _run_collect("SubAtom", 5, "", B, L, A, S,
                               snap=lambda: (deref(B), deref(L),
                                             deref(A), deref(S)))
        assert results == [(0, 0, 0, "")]

    def test_before_bound_enumerate(self):
        """SubAtom('abc', 0, L, A, S) → 4 solutions (all prefixes)."""
        L = Var()
        A = Var()
        S = Var()
        results = _run_collect("SubAtom", 5, "abc", 0, L, A, S,
                               snap=lambda: (deref(L), deref(A), deref(S)))
        assert results == [(0, 3, ""), (1, 2, "a"), (2, 1, "ab"), (3, 0, "abc")]
