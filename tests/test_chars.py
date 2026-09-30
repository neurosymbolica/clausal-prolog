"""Tests for Phase 2 character/string builtins: char_type/2, char_code/2,
upcase_atom/2, downcase_atom/2, atom_length/2, atom_chars/2, atom_codes/2,
atom_concat/3, sub_atom/5.
"""

from __future__ import annotations

import pytest

from clausal import cell_args, cell_functor
from clausal.logic.atoms import char_atom, mint, spelling
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
        assert _run("char_type", 2, char_atom("a"), mint("alpha")) > 0

    def test_both_bound_mismatch(self):
        # nv
        assert _run("char_type", 2, char_atom("a"), mint("digit")) == 0

    def test_digit_match(self):
        # nv
        assert _run("char_type", 2, char_atom("1"), mint("digit")) > 0

    def test_upper_match(self):
        # nv
        assert _run("char_type", 2, char_atom("A"), mint("upper")) > 0

    def test_space_match(self):
        # nv
        assert _run("char_type", 2, char_atom(" "), mint("space")) > 0

    def test_punct_match(self):
        # nv
        assert _run("char_type", 2, char_atom("!"), mint("punct")) > 0

    def test_not_single_char_fails(self):
        # nv
        assert _run("char_type", 2, mint("ab"), mint("alpha")) == 0

    def test_enum_types_for_char(self):
        """char_type('a', TYPE) → enumerate matching types."""
        # nv
        TYPE = Var()
        results = _run_collect("char_type", 2, char_atom("a"), TYPE,
                               snap=lambda: deref(TYPE))
        assert mint("alpha") in results
        assert mint("alnum") in results
        assert mint("lower") in results
        assert mint("ascii") in results
        assert mint("print") in results
        assert mint("digit") not in results

    def test_enum_chars_for_digit(self):
        """char_type(C, 'digit') → enumerate every Unicode digit.

        A09-F013: digit is Unicode-aware in test-mode (``char_type('٣',
        digit)`` succeeds via ``str.isdigit``), so the enumeration must be
        too — it includes the ASCII digits and Unicode digits like the
        Arabic-Indic three.
        """
        # nv
        C = Var()
        results = _run_collect("char_type", 2, C, mint("digit"),
                               snap=lambda: deref(C))
        assert set(char_atom(str(i)) for i in range(10)) <= set(results)
        assert char_atom("٣") in results  # ARABIC-INDIC THREE
        assert all(spelling(c).isdigit() for c in results)

    def test_both_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("char_type", 2, Var(), Var())

    def test_control_char(self):
        # nv
        assert _run("char_type", 2, char_atom(chr(0)), mint("control")) > 0

    def test_ascii_char(self):
        # nv
        assert _run("char_type", 2, char_atom("z"), mint("ascii")) > 0


# ── char_code/2 ───────────────────────────────────────────────────────────────

class TestCharCode:
    def test_char_to_code(self):
        # nv
        N = Var()
        results = _run_collect("char_code", 2, char_atom("A"), N,
                               snap=lambda: deref(N))
        assert results == [65]

    def test_code_to_char(self):
        # nv
        C = Var()
        results = _run_collect("char_code", 2, C, 65, snap=lambda: deref(C))
        assert results == [char_atom("A")]

    def test_both_bound_match(self):
        # nv
        assert _run("char_code", 2, char_atom("A"), 65) > 0

    def test_both_bound_mismatch(self):
        # nv
        assert _run("char_code", 2, char_atom("A"), 66) == 0

    def test_both_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("char_code", 2, Var(), Var())

    def test_non_char_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("char_code", 2, mint("AB"), Var())


# ── upcase_atom/2, downcase_atom/2 ────────────────────────────────────────────

class TestCaseConversion:
    def test_upcase(self):
        # nv
        S = Var()
        results = _run_collect("upcase_atom", 2, mint("hello"), S,
                               snap=lambda: deref(S))
        assert results == [mint("HELLO")]

    def test_upcase_mixed(self):
        # nv
        S = Var()
        results = _run_collect("upcase_atom", 2, mint("Hello World"), S,
                               snap=lambda: deref(S))
        assert results == [mint("HELLO WORLD")]

    def test_downcase(self):
        # nv
        S = Var()
        results = _run_collect("downcase_atom", 2, mint("HELLO"), S,
                               snap=lambda: deref(S))
        assert results == [mint("hello")]

    def test_upcase_empty(self):
        # nv
        S = Var()
        results = _run_collect("upcase_atom", 2, mint(""), S,
                               snap=lambda: deref(S))
        assert results == [mint("")]

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
        results = _run_collect("atom_length", 2, mint("hello"), N,
                               snap=lambda: deref(N))
        assert results == [5]

    def test_empty(self):
        # nv
        N = Var()
        results = _run_collect("atom_length", 2, mint(""), N,
                               snap=lambda: deref(N))
        assert results == [0]

    def test_both_bound_match(self):
        # nv
        assert _run("atom_length", 2, mint("hello"), 5) > 0

    def test_both_bound_mismatch(self):
        # nv
        assert _run("atom_length", 2, mint("hello"), 3) == 0

    def test_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_length", 2, Var(), Var())


# ── atom_chars/2 ──────────────────────────────────────────────────────────────

class TestAtomChars:
    def test_atom_to_chars(self):
        # nv
        L = Var()
        results = _run_collect("atom_chars", 2, mint("hi"), L,
                               snap=lambda: deref(L))
        assert results == [[char_atom("h"), char_atom("i")]]

    def test_chars_to_atom(self):
        # nv
        A = Var()
        results = _run_collect("atom_chars", 2, A,
                               [char_atom("h"), char_atom("i")],
                               snap=lambda: deref(A))
        assert results == [mint("hi")]

    def test_both_bound_match(self):
        # nv
        assert _run("atom_chars", 2, mint("hi"), [char_atom("h"), char_atom("i")]) > 0

    def test_empty(self):
        # nv
        L = Var()
        results = _run_collect("atom_chars", 2, mint(""), L,
                               snap=lambda: deref(L))
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
        results = _run_collect("atom_codes", 2, mint("hi"), L,
                               snap=lambda: deref(L))
        assert results == [[104, 105]]

    def test_codes_to_atom(self):
        # nv
        A = Var()
        results = _run_collect("atom_codes", 2, A, [104, 105],
                               snap=lambda: deref(A))
        assert results == [mint("hi")]

    def test_both_bound_match(self):
        # nv
        assert _run("atom_codes", 2, mint("hi"), [104, 105]) > 0

    def test_both_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_codes", 2, Var(), Var())


# ── atom_concat/3 ─────────────────────────────────────────────────────────────

class TestAtomConcat:
    def test_forward(self):
        # nv
        S = Var()
        results = _run_collect("atom_concat", 3, mint("hel"), mint("lo"), S,
                               snap=lambda: deref(S))
        assert results == [mint("hello")]

    def test_forward_empty_left(self):
        # nv
        S = Var()
        results = _run_collect("atom_concat", 3, mint(""), mint("hello"), S,
                               snap=lambda: deref(S))
        assert results == [mint("hello")]

    def test_forward_empty_right(self):
        # nv
        S = Var()
        results = _run_collect("atom_concat", 3, mint("hello"), mint(""), S,
                               snap=lambda: deref(S))
        assert results == [mint("hello")]

    def test_reverse_enumerate_splits(self):
        """atom_concat(A, B, 'abc') → 4 solutions."""
        # nv
        A = Var()
        B = Var()
        results = _run_collect("atom_concat", 3, A, B, mint("abc"),
                               snap=lambda: (deref(A), deref(B)))
        assert results == [(mint(""), mint("abc")),
                           (mint("a"), mint("bc")),
                           (mint("ab"), mint("c")),
                           (mint("abc"), mint(""))]

    def test_prefix_bound(self):
        # nv
        B = Var()
        results = _run_collect("atom_concat", 3, mint("a"), B, mint("abc"),
                               snap=lambda: deref(B))
        assert results == [mint("bc")]

    def test_suffix_bound(self):
        # nv
        A = Var()
        results = _run_collect("atom_concat", 3, A, mint("bc"), mint("abc"),
                               snap=lambda: deref(A))
        assert results == [mint("a")]

    def test_all_bound_match(self):
        # nv
        assert _run("atom_concat", 3, mint("a"), mint("bc"), mint("abc")) > 0

    def test_all_bound_mismatch(self):
        # nv
        assert _run("atom_concat", 3, mint("x"), mint("bc"), mint("abc")) == 0

    def test_all_unbound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_concat", 3, Var(), Var(), Var())

    def test_c_unbound_a_bound_error(self):
        # nv
        with pytest.raises(LogicException):
            _run("atom_concat", 3, mint("abc"), Var(), Var())

    def test_both_numbers_type_error(self):
        """atom_concat(1, 2, X) -> type_error(atom, 1).

        ISO 8.16.2 and Scryer 0.10 both reject a number in atom position;
        an earlier spec note ("numbers accepted as ISO allows") had this
        backwards.
        """
        with pytest.raises(LogicException) as exc:
            _run("atom_concat", 3, 1, 2, Var())
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom")
        assert cell_args(formal)[1] == 1

    def test_second_arg_number_type_error(self):
        """atom_concat(a, 1, X) -> type_error(atom, 1); the culprit is the
        offending number, not the whole call."""
        with pytest.raises(LogicException) as exc:
            _run("atom_concat", 3, mint("a"), 1, Var())
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom")
        assert cell_args(formal)[1] == 1

    def test_atoms_still_concat(self):
        """atom_concat(a, b, X) -> X = ab still works (regression guard next
        to the number-rejection tests above)."""
        S = Var()
        results = _run_collect("atom_concat", 3, mint("a"), mint("b"), S,
                               snap=lambda: deref(S))
        assert results == [mint("ab")]


# ── sub_atom/5 ────────────────────────────────────────────────────────────────

class TestSubAtom:
    def test_all_bound_extract(self):
        # nv
        S = Var()
        results = _run_collect("sub_atom", 5, mint("hello"), 1, 3, 1, S,
                               snap=lambda: deref(S))
        assert results == [mint("ell")]

    def test_whole_string(self):
        # nv
        S = Var()
        results = _run_collect("sub_atom", 5, mint("hello"), 0, 5, 0, S,
                               snap=lambda: deref(S))
        assert results == [mint("hello")]

    def test_empty_prefix(self):
        # nv
        S = Var()
        results = _run_collect("sub_atom", 5, mint("hello"), 0, 0, 5, S,
                               snap=lambda: deref(S))
        assert results == [mint("")]

    def test_sub_bound_find(self):
        # nv
        B = Var()
        results = _run_collect("sub_atom", 5, mint("hello"), B, Var(), Var(),
                               mint("ell"), snap=lambda: deref(B))
        assert results == [1]

    def test_sub_bound_multiple_occurrences(self):
        """sub_atom('abcabc', B, _, _, 'bc') → B=1 and B=4."""
        # nv
        B = Var()
        results = _run_collect("sub_atom", 5, mint("abcabc"), B, Var(), Var(),
                               mint("bc"), snap=lambda: deref(B))
        assert results == [1, 4]

    def test_length_bound_enumerate(self):
        """sub_atom('abc', B, 1, A, S) → 3 solutions."""
        # nv
        B = Var()
        A = Var()
        S = Var()
        results = _run_collect("sub_atom", 5, mint("abc"), B, 1, A, S,
                               snap=lambda: (deref(B), deref(A), deref(S)))
        assert results == [(0, 2, mint("a")), (1, 1, mint("b")),
                           (2, 0, mint("c"))]

    def test_all_unbound_enumerate(self):
        """sub_atom('abc', B, L, A, S) → 10 solutions (all substrings)."""
        # nv
        assert _run("sub_atom", 5, mint("abc"), Var(), Var(), Var(), Var()) == 10

    def test_inconsistent_fails(self):
        """sub_atom('hello', 1, 3, 2, 'ell') → fails (After should be 1)."""
        # nv
        assert _run("sub_atom", 5, mint("hello"), 1, 3, 2, mint("ell")) == 0

    def test_consistent_succeeds(self):
        # nv
        assert _run("sub_atom", 5, mint("hello"), 1, 3, 1, mint("ell")) > 0

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
        results = _run_collect("sub_atom", 5, mint(""), B, L, A, S,
                               snap=lambda: (deref(B), deref(L),
                                             deref(A), deref(S)))
        assert results == [(0, 0, 0, mint(""))]

    def test_before_bound_enumerate(self):
        """sub_atom('abc', 0, L, A, S) → 4 solutions (all prefixes)."""
        # nv
        L = Var()
        A = Var()
        S = Var()
        results = _run_collect("sub_atom", 5, mint("abc"), 0, L, A, S,
                               snap=lambda: (deref(L), deref(A), deref(S)))
        assert results == [(0, 3, mint("")), (1, 2, mint("a")),
                           (2, 1, mint("ab")), (3, 0, mint("abc"))]


# ── number_chars/2 ──────────────────────────────────────────────────────────────


class TestNumberChars:

    def test_int_forward(self):
        """number_chars(42, C) → ["4", "2"]."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, 42, v,
                               snap=lambda: deref(v))
        assert results == [[char_atom("4"), char_atom("2")]]

    def test_int_reverse(self):
        """number_chars(N, ["4", "2"]) → N = 42."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, v,
                               [char_atom("4"), char_atom("2")],
                               snap=lambda: deref(v))
        assert results == [42]

    def test_float_forward(self):
        """number_chars(3.14, C) → ["3", ".", "1", "4"]."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, 3.14, v,
                               snap=lambda: deref(v))
        assert results == [[char_atom(c) for c in "3.14"]]

    def test_float_reverse(self):
        """number_chars(N, ["3", ".", "1", "4"]) → N = 3.14."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, v,
                               [char_atom(c) for c in "3.14"],
                               snap=lambda: deref(v))
        assert results == [3.14]

    def test_negative(self):
        """number_chars(-5, C) → ["-", "5"]."""
        # nv
        v = Var()
        results = _run_collect("number_chars", 2, -5, v,
                               snap=lambda: deref(v))
        assert results == [[char_atom("-"), char_atom("5")]]

    def test_invalid_chars_is_a_syntax_error(self):
        """number_chars(N, [a, b]) raises Scryer's
        error(syntax_error(unexpected_end_of_file), number_chars/2)
        (ISO 8.16.7.3 e); it used to FAIL (A09-F030, ruled 2026-09-30)."""
        # nv
        v = Var()
        with pytest.raises(LogicException) as ei:
            _run("number_chars", 2, v, [char_atom("a"), char_atom("b")])
        assert ei.value.term[1] == ("syntax_error", "unexpected_end_of_file")
        assert ei.value.term[2] == ("/", "number_chars", 2)

    def test_both_bound_consistent(self):
        """number_chars(42, ["4", "2"]) → succeeds."""
        # nv
        assert _run("number_chars", 2, 42, [char_atom("4"), char_atom("2")]) == 1

    def test_both_bound_inconsistent(self):
        """number_chars(42, ["4", "3"]) → fails."""
        # nv
        assert _run("number_chars", 2, 42, [char_atom("4"), char_atom("3")]) == 0

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

    def test_invalid_codes_is_a_syntax_error(self):
        """number_codes(N, "1a") raises Scryer's
        error(syntax_error(unexpected_char), number_codes/2:0); it used to
        FAIL (A09-F030, ruled 2026-09-30)."""
        # nv
        v = Var()
        with pytest.raises(LogicException) as ei:
            _run("number_codes", 2, v, [ord("1"), ord("a")])
        assert ei.value.term[1] == ("syntax_error", "unexpected_char")
        assert ei.value.term[2] == (":", ("/", "number_codes", 2), 0)

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


# ── Cell atoms (atoms-as-cells, Stage A) ─────────────────────────────────────


class TestCellAtoms:
    """Spec §6.6 with a 1-tuple atom input (Stage A: outputs still str)."""

    def test_atom_length_accepts_cell_atom(self):
        # nv
        N = Var()
        answers = _run_collect("atom_length", 2, mint("abc"), N,
                               snap=lambda: deref(N))
        assert len(answers) == 1 and answers[0] == 3

    def test_atom_chars_accepts_cell_atom_and_char_atoms(self):
        # nv
        L = Var()
        answers = _run_collect("atom_chars", 2, mint("ab"), L,
                               snap=lambda: deref(L))
        assert answers == [[char_atom("a"), char_atom("b")]]
        A = Var()
        answers = _run_collect("atom_chars", 2, A,
                               [char_atom("a"), char_atom("b")],
                               snap=lambda: deref(A))
        assert answers == [mint("ab")]

    def test_atom_concat_cell_atoms(self):
        # nv
        X = Var()
        answers = _run_collect("atom_concat", 3, mint("a"), mint("b"), X,
                               snap=lambda: deref(X))
        assert answers == [mint("ab")]

    def test_sub_atom_cell_atom(self):
        # nv
        S = Var()
        answers = _run_collect("sub_atom", 5, mint("abc"), 1, 1, 1, S,
                               snap=lambda: deref(S))
        assert len(answers) == 1 and answers[0] == mint("b")

    def test_char_code_cell_char(self):
        # nv
        C = Var()
        answers = _run_collect("char_code", 2, mint("a"), C,
                               snap=lambda: deref(C))
        assert answers == [97]
        Ch = Var()
        answers = _run_collect("char_code", 2, Ch, 97,
                               snap=lambda: deref(Ch))
        assert answers == [char_atom("a")]

    def test_char_type_cell_char_and_cell_type(self):
        # nv
        assert _run("char_type", 2, mint("a"), mint("alpha")) == 1

    def test_number_chars_cell_char_atoms(self):
        """§6.6: number_chars(12, L) → L = ["1", "2"] and back."""
        # nv
        L = Var()
        answers = _run_collect("number_chars", 2, 12, L,
                               snap=lambda: deref(L))
        assert answers == [[char_atom("1"), char_atom("2")]]
        N = Var()
        answers = _run_collect("number_chars", 2, N, [mint("1"), mint("2")],
                               snap=lambda: deref(N))
        assert answers == [12]

    def test_atom_concat_split_enumeration_cell_atom(self):
        """Split mode: every enumerated half is an atom.

        Reaches ``_c_atom_concat_split_find`` (and its ``atom_from_str``
        wraps) on a build with the C extension.
        """
        # nv
        A, B = Var(), Var()
        answers = _run_collect("atom_concat", 3, A, B, mint("ab"),
                               snap=lambda: (deref(A), deref(B)))
        assert answers == [(mint(""), mint("ab")),
                           (mint("a"), mint("b")),
                           (mint("ab"), mint(""))]

    def test_char_type_char_enumeration_cell_type(self):
        """Type bound to a cell atom → every enumerated Char is a char atom.

        ``control`` is codepoint-bounded ASCII, so this reaches
        ``_c_char_type_find_chars`` and the ``ascii_char_objs`` table.
        """
        # nv
        C = Var()
        answers = _run_collect("char_type", 2, C, mint("control"),
                               snap=lambda: deref(C))
        assert answers == [char_atom(chr(i)) for i in range(32)] + \
            [char_atom(chr(127))]

    def test_char_type_type_enumeration_cell_char(self):
        """Char bound to a cell atom → every enumerated Type is an atom.

        Reaches ``_c_char_type_find_types`` and the ``type_name_objs`` table.
        """
        # nv
        T = Var()
        answers = _run_collect("char_type", 2, mint("a"), T,
                               snap=lambda: deref(T))
        assert answers == [mint("alpha"), mint("alnum"), mint("lower"),
                           mint("ascii"), mint("print")]


class TestCellAtomsPythonFallback(TestCellAtoms):
    """The same §6.6 rows with the C inner loops disabled.

    ``chars.py`` has no runtime switch for the C helpers (they are bound at
    import), so the twin-parity run nulls the module-level handles for the
    duration of each test — the Python fallback branches then run instead.

    Only four of the rows above have a C path in the mode they exercise:
    ``sub_atom/5``'s (Before, Length) enumeration, ``atom_concat/3``'s split
    enumeration and ``char_type/2``'s two enumerations.  The rest already run
    pure Python in the base class and are re-run here only as cheap
    regression cover.
    """

    @pytest.fixture(autouse=True)
    def _no_c(self, monkeypatch):
        from clausal.logic.builtins import chars as _chars
        for _name in ("_c_char_type_find_types", "_c_char_type_find_chars",
                      "_c_atom_concat_split_find", "_c_sub_atom_search",
                      "_c_sub_atom_enum", "_c_type_name_index"):
            monkeypatch.setattr(_chars, _name, None)
