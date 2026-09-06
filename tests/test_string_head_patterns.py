"""Tests for compiler head pattern matching against strings.

Compiled clause heads with list patterns now accept strings as input.
String slicing preserves string type through recursion (e.g., [H, *T]
on "hello" gives H='h', T='ello').
"""

import pytest
from clausal.logic.atoms import char_atom, mint
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
        for _ in call("HeadTail", mint("abc"), H, T, module=edge_mod):
            results.append((deref(H), deref(T)))
        assert results == [("a", "bc")]

    def test_head_tail_single_char(self, edge_mod):
        # nv
        H, T = Var(), Var()
        results = []
        for _ in call("HeadTail", mint("a"), H, T, module=edge_mod):
            results.append((deref(H), deref(T)))
        assert results == [("a", "")]

    def test_head_tail_empty_fails(self, edge_mod):
        """Empty string has no head — should fail."""
        # nv
        H, T = Var(), Var()
        assert list(call("HeadTail", mint(""), H, T, module=edge_mod)) == []


class TestCaptureAllString:
    def test_capture_all(self, edge_mod):
        # nv
        A = Var()
        for _ in call("CaptureAll", mint("hello"), A, module=edge_mod):
            assert deref(A) == "hello"

    def test_capture_all_empty(self, edge_mod):
        # nv
        A = Var()
        for _ in call("CaptureAll", mint(""), A, module=edge_mod):
            assert deref(A) == ""


class TestThreeAndRestString:
    def test_three_and_rest(self, edge_mod):
        # nv
        A, B, C, R = Var(), Var(), Var(), Var()
        for _ in call("ThreeAndRest", mint("abcde"), A, B, C, R, module=edge_mod):
            assert deref(A) == "a"
            assert deref(B) == "b"
            assert deref(C) == "c"
            assert deref(R) == "de"

    def test_three_exact(self, edge_mod):
        # nv
        A, B, C, R = Var(), Var(), Var(), Var()
        for _ in call("ThreeAndRest", mint("abc"), A, B, C, R, module=edge_mod):
            assert deref(R) == ""

    def test_too_short_fails(self, edge_mod):
        # nv
        A, B, C, R = Var(), Var(), Var(), Var()
        assert list(call("ThreeAndRest", mint("ab"), A, B, C, R, module=edge_mod)) == []


class TestExactlyTwoString:
    def test_exactly_two(self, edge_mod):
        # nv
        X, Y = Var(), Var()
        for _ in call("ExactlyTwo", mint("ab"), X, Y, module=edge_mod):
            assert deref(X) == "a"
            assert deref(Y) == "b"

    def test_wrong_length_fails(self, edge_mod):
        # nv
        X, Y = Var(), Var()
        assert list(call("ExactlyTwo", mint("abc"), X, Y, module=edge_mod)) == []
        assert list(call("ExactlyTwo", mint("a"), X, Y, module=edge_mod)) == []


class TestIsEmptyString:
    def test_empty_string_no_longer_matches_empty_list_head(self, edge_mod):
        # nv — P3-1 Task 5 (§1b): IsEmpty's fact head is the literal empty
        # LIST `[]`, called here with the empty STR "". Empty str and
        # empty list are different types now too (no cross-type
        # exception for the empty case), so this no longer matches.
        # (Formerly ``test_empty_string``, asserting it DID match.)
        assert list(call("IsEmpty", mint(""), module=edge_mod)) == []

    def test_nonempty_string_fails(self, edge_mod):
        # nv
        assert list(call("IsEmpty", mint("x"), module=edge_mod)) == []


# ── Recursive predicates on strings ────────────────────────────────────────


class TestRecursiveOnString:
    def test_length(self, lists_mod):
        # nv
        N = Var()
        for _ in call("length", mint("hello"), N, module=lists_mod):
            assert deref(N) == 5

    def test_length_empty(self, lists_mod):
        # nv
        N = Var()
        for _ in call("length", mint(""), N, module=lists_mod):
            assert deref(N) == 0

    def test_last(self, lists_mod):
        # nv
        L = Var()
        for _ in call("last", mint("hello"), L, module=lists_mod):
            assert deref(L) == "o"

    def test_last_single(self, lists_mod):
        # nv
        L = Var()
        for _ in call("last", mint("x"), L, module=lists_mod):
            assert deref(L) == "x"


# ── String type preservation through recursion ─────────────────────────────


class TestStringPreservation:
    """Verify that [H, *T] on a string gives T as a string, not a list."""

    def test_tail_is_string(self, edge_mod):
        # nv
        H, T = Var(), Var()
        for _ in call("HeadTail", mint("abc"), H, T, module=edge_mod):
            assert isinstance(deref(T), str), f"T should be str, got {type(deref(T))}"

    def test_star_capture_is_string(self, edge_mod):
        # nv
        A = Var()
        for _ in call("CaptureAll", mint("hello"), A, module=edge_mod):
            assert isinstance(deref(A), str)

    def test_rest_is_string(self, edge_mod):
        # nv
        A, B, C, R = Var(), Var(), Var(), Var()
        for _ in call("ThreeAndRest", mint("abcde"), A, B, C, R, module=edge_mod):
            assert isinstance(deref(R), str)

    def test_list_input_still_gives_list(self, edge_mod):
        """List input is unchanged — tail is still a list."""
        # nv
        H, T = Var(), Var()
        for _ in call("HeadTail", [mint("a"), mint("b"), mint("c")], H, T, module=edge_mod):
            assert isinstance(deref(T), list)
