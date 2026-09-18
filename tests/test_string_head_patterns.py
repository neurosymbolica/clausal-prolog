"""Tests for compiler head pattern matching against strings.

Compiled clause heads with list patterns accept strings as input, because
a string IS the list of its char atoms (spec §6.2). String slicing
preserves string type through recursion: ``[H, *T]`` on ``"hello"`` gives
``H = ('h',)`` (a char atom) and ``T = "ello"`` (a str slice, R-S2).

Every test here feeds a STRING and asserts the solutions it produced, so a
head pattern that stopped matching strings would empty the result list and
fail the assertion rather than pass vacuously.
"""

import pytest
from clausal.logic.atoms import char_atom, mint
from clausal.logic.cells import chars, is_chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.import_hook import _load_module
import os


@pytest.fixture(scope="module")
def edge_mod():
    fixture = os.path.join(
        os.path.dirname(__file__), "clausal_modules", "list_edge_cases.clausal"
    )
    return _load_module("lec_head_str", fixture).__dict__["$module"]


@pytest.fixture(scope="module")
def lists_mod():
    fixture = os.path.join(
        os.path.dirname(__file__), "clausal_modules", "lists.clausal"
    )
    return _load_module("lists_head_str", fixture).__dict__["$module"]


# ── Single-star patterns ───────────────────────────────────────────────────


class TestHeadTailString:
    def test_head_tail(self, edge_mod):
        # nv
        H, T = Var(), Var()
        results = []
        for _ in call("head_tail", chars("abc"), H, T, module=edge_mod):
            results.append((deref(H), deref(T)))
        # THE FLIP (spec §6.2): the head is a CHAR ATOM, the tail a str slice.
        assert results == [(char_atom("a"), chars("bc"))]

    def test_head_tail_single_char(self, edge_mod):
        # nv
        H, T = Var(), Var()
        results = []
        for _ in call("head_tail", chars("a"), H, T, module=edge_mod):
            results.append((deref(H), deref(T)))
        assert results == [(char_atom("a"), chars(""))]

    def test_head_tail_empty_fails(self, edge_mod):
        """Empty string has no head — should fail."""
        # nv
        H, T = Var(), Var()
        assert list(call("head_tail", chars(""), H, T, module=edge_mod)) == []


class TestCaptureAllString:
    def test_capture_all(self, edge_mod):
        # nv
        A = Var()
        results = []
        for _ in call("capture_all", chars("hello"), A, module=edge_mod):
            results.append(deref(A))
        # THE FLIP (spec §6.2): a star over a string captures a str slice.
        assert results == [chars("hello")]

    def test_capture_all_empty(self, edge_mod):
        # nv
        A = Var()
        results = []
        for _ in call("capture_all", chars(""), A, module=edge_mod):
            results.append(deref(A))
        assert results == [chars("")]


class TestThreeAndRestString:
    def test_three_and_rest(self, edge_mod):
        # nv
        A, B, C, R = Var(), Var(), Var(), Var()
        results = []
        for _ in call("three_and_rest", chars("abcde"), A, B, C, R, module=edge_mod):
            results.append((deref(A), deref(B), deref(C), deref(R)))
        # THE FLIP (spec §6.2): fixed elements are CHAR ATOMS, the rest a str.
        assert results == [
            (char_atom("a"), char_atom("b"), char_atom("c"), chars("de"))
        ]

    def test_three_exact(self, edge_mod):
        # nv
        A, B, C, R = Var(), Var(), Var(), Var()
        results = []
        for _ in call("three_and_rest", chars("abc"), A, B, C, R, module=edge_mod):
            results.append((deref(A), deref(B), deref(C), deref(R)))
        assert results == [(char_atom("a"), char_atom("b"), char_atom("c"), chars(""))]

    def test_too_short_fails(self, edge_mod):
        # nv
        A, B, C, R = Var(), Var(), Var(), Var()
        assert list(call("three_and_rest", chars("ab"), A, B, C, R, module=edge_mod)) == []


class TestExactlyTwoString:
    def test_exactly_two(self, edge_mod):
        # nv
        X, Y = Var(), Var()
        results = []
        for _ in call("exactly_two", chars("ab"), X, Y, module=edge_mod):
            results.append((deref(X), deref(Y)))
        assert results == [(char_atom("a"), char_atom("b"))]

    def test_wrong_length_fails(self, edge_mod):
        # nv
        X, Y = Var(), Var()
        assert list(call("exactly_two", chars("abc"), X, Y, module=edge_mod)) == []
        assert list(call("exactly_two", chars("a"), X, Y, module=edge_mod)) == []


class TestIsEmptyString:
    def test_empty_string_matches_empty_list_head(self, edge_mod):
        # nv — THE FLIP (spec §6.2): `""` unifies with `[]`, so IsEmpty's
        # literal `[]` fact head matches the empty STRING. (Under P3-1 a
        # `str` was an atom and this failed; the inversion is deliberate.)
        assert len(list(call("is_empty", chars(""), module=edge_mod))) == 1

    def test_nonempty_string_fails(self, edge_mod):
        # nv — "x" is the one-element list [('x',)], not [].
        assert list(call("is_empty", chars("x"), module=edge_mod)) == []

    def test_atom_does_not_match_empty_list_head(self, edge_mod):
        # nv — the ATOM `''` is a cell, not a list; it never matches `[]`.
        assert list(call("is_empty", mint(""), module=edge_mod)) == []


# ── Recursive predicates on strings ────────────────────────────────────────


class TestRecursiveOnString:
    def test_length(self, lists_mod):
        # nv
        N = Var()
        results = []
        for _ in call("length", chars("hello"), N, module=lists_mod):
            results.append(deref(N))
        assert results == [5]

    def test_length_empty(self, lists_mod):
        # nv
        N = Var()
        results = []
        for _ in call("length", chars(""), N, module=lists_mod):
            results.append(deref(N))
        assert results == [0]

    def test_last(self, lists_mod):
        # nv
        L = Var()
        results = []
        for _ in call("last", chars("hello"), L, module=lists_mod):
            results.append(deref(L))
        # THE FLIP (spec §6.2): an element of a string is a CHAR ATOM.
        assert results == [char_atom("o")]

    def test_last_single(self, lists_mod):
        # nv
        L = Var()
        results = []
        for _ in call("last", chars("x"), L, module=lists_mod):
            results.append(deref(L))
        assert results == [char_atom("x")]


# ── String type preservation through recursion ─────────────────────────────


class TestStringPreservation:
    """Verify that [H, *T] on a string gives T as a string, not a list."""

    def test_tail_is_string(self, edge_mod):
        # nv
        H, T = Var(), Var()
        results = []
        for _ in call("head_tail", chars("abc"), H, T, module=edge_mod):
            results.append(deref(T))
        assert results == [chars("bc")]
        assert is_chars(results[0]), f"T should be chars, got {type(results[0])}"

    def test_star_capture_is_string(self, edge_mod):
        # nv
        A = Var()
        results = []
        for _ in call("capture_all", chars("hello"), A, module=edge_mod):
            results.append(deref(A))
        assert results == [chars("hello")]
        assert is_chars(results[0])

    def test_rest_is_string(self, edge_mod):
        # nv
        A, B, C, R = Var(), Var(), Var(), Var()
        results = []
        for _ in call("three_and_rest", chars("abcde"), A, B, C, R, module=edge_mod):
            results.append(deref(R))
        assert results == [chars("de")]
        assert is_chars(results[0])

    def test_list_input_still_gives_list(self, edge_mod):
        """List input is unchanged — tail is still a list."""
        # nv
        H, T = Var(), Var()
        results = []
        for _ in call(
            "head_tail", [mint("a"), mint("b"), mint("c")], H, T, module=edge_mod
        ):
            results.append((deref(H), deref(T)))
        assert results == [(mint("a"), [mint("b"), mint("c")])]
        assert isinstance(results[0][1], list)
