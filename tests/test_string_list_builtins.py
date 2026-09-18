"""Tests for Phase 4: polymorphic list builtins accept strings.

All list builtins now accept strings as character sequences. when all
sequence inputs are strings and the result is a valid char sequence,
the result is returned as a string.
"""

import pytest
from clausal.logic.atoms import char_atom, mint
from clausal.logic.cells import chars, is_chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.import_hook import _load_module
import tempfile
import os


@pytest.fixture(scope="module")
def mod():
    """Minimal module for calling builtins."""
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write("-module(tmod, [])\n")
        f.flush()
        m = _load_module("tmod_phase4", f.name).__dict__["$module"]
    yield m
    os.unlink(f.name)


def _first(functor, *args, module):
    """Return the first result for a builtin call, or None."""
    for _ in call(functor, *args, module=module):
        return True
    return False


def _collect(var, functor, *args, module):
    """Collect all bindings of *var* across backtracking."""
    results = []
    for _ in call(functor, *args, module=module):
        results.append(deref(var))
    return results


# ── in_/2 ────────────────────────────────────────────────────────────────────


class TestInString:
    def test_enumerate_chars(self, mod):
        # nv
        V = Var()
        assert _collect(V, "in_", V, chars("abc"), module=mod) == [mint("a"), mint("b"), mint("c")]

    def test_member_check(self, mod):
        # nv
        assert _first("in_", mint("b"), chars("abc"), module=mod)

    def test_member_miss(self, mod):
        # nv — a char atom that is genuinely absent from "abc".
        assert not _first("in_", char_atom("z"), chars("abc"), module=mod)

    def test_a_one_element_string_is_not_an_element(self, mod):
        """``"z"`` is the LIST ``[('z',)]``, not the char ``('z',)``.

        THE FLIP (spec §6.2): the elements of a string are char atoms, so a
        one-character STRING never matches one — the old ``in_("z", "abc")``
        spelling passed for this reason, not because ``z`` was absent.
        """
        # nv
        assert not _first("in_", chars("a"), chars("abc"), module=mod)   # "a" IS in "abc"…
        assert _first("in_", char_atom("a"), chars("abc"), module=mod)  # …as an atom

    def test_empty_string(self, mod):
        # nv
        V = Var()
        assert _collect(V, "in_", V, chars(""), module=mod) == []

    def test_list_still_works(self, mod):
        # nv
        V = Var()
        assert _collect(V, "in_", V, [1, 2], module=mod) == [1, 2]


class TestInCheckString:
    def test_memberchk_hit(self, mod):
        # nv
        assert _first("in_check", char_atom("l"), chars("hello"), module=mod)

    def test_memberchk_miss(self, mod):
        # nv
        assert not _first("in_check", char_atom("z"), chars("hello"), module=mod)


# ── append/3 ────────────────────────────────────────────────────────────────


class TestAppendString:
    def test_concat_two_strings(self, mod):
        # nv
        X = Var()
        r = _collect(X, "append", chars("hel"), chars("lo"), X, module=mod)
        assert r == [chars("hello")]

    def test_prefix_match(self, mod):
        # nv
        X = Var()
        r = _collect(X, "append", chars("hel"), X, chars("hello"), module=mod)
        assert r == [chars("lo")]

    def test_suffix_match(self, mod):
        # nv
        X = Var()
        r = _collect(X, "append", X, chars("lo"), chars("hello"), module=mod)
        assert r == [chars("hel")]

    def test_enumerate_splits(self, mod):
        # nv
        X, Y = Var(), Var()
        pairs = []
        for _ in call("append", X, Y, chars("abc"), module=mod):
            pairs.append((deref(X), deref(Y)))
        assert pairs == [
            (chars(""), chars("abc")),
            (chars("a"), chars("bc")),
            (chars("ab"), chars("c")),
            (chars("abc"), chars("")),
        ]

    def test_concat_string_with_list(self, mod):
        """Mixed types: string + list → list result."""
        # nv
        X = Var()
        r = _collect(X, "append", chars("ab"), [1, 2], X, module=mod)
        assert r == [[mint("a"), mint("b"), 1, 2]]

    def test_empty_strings(self, mod):
        # nv
        X = Var()
        r = _collect(X, "append", chars(""), chars(""), X, module=mod)
        assert r == [chars("")]

    def test_list_still_works(self, mod):
        # nv
        X = Var()
        r = _collect(X, "append", [1, 2], [3], X, module=mod)
        assert r == [[1, 2, 3]]


# ── length/2 ────────────────────────────────────────────────────────────────


class TestLengthString:
    def test_length(self, mod):
        # nv
        X = Var()
        assert _collect(X, "length", chars("hello"), X, module=mod) == [5]

    def test_empty(self, mod):
        # nv
        X = Var()
        assert _collect(X, "length", chars(""), X, module=mod) == [0]


# ── reverse/2 ──────────────────────────────────────────────────────────────


class TestReverseString:
    def test_reverse(self, mod):
        # nv
        X = Var()
        assert _collect(X, "reverse", chars("hello"), X, module=mod) == [chars("olleh")]

    def test_reverse_empty(self, mod):
        # nv
        X = Var()
        assert _collect(X, "reverse", chars(""), X, module=mod) == [chars("")]

    def test_reverse_single(self, mod):
        # nv
        X = Var()
        assert _collect(X, "reverse", chars("a"), X, module=mod) == [chars("a")]


# ── last/2 ──────────────────────────────────────────────────────────────────


class TestLastString:
    def test_last_char(self, mod):
        # nv
        X = Var()
        assert _collect(X, "last", chars("hello"), X, module=mod) == [mint("o")]

    def test_empty_fails(self, mod):
        # nv
        X = Var()
        assert _collect(X, "last", chars(""), X, module=mod) == []


# ── list_item/3 ─────────────────────────────────────────────────────────────


class TestListItemString:
    def test_index(self, mod):
        # nv
        X = Var()
        assert _collect(X, "list_item", 1, chars("hello"), X, module=mod) == [mint("e")]

    def test_enumerate(self, mod):
        # nv
        N, E = Var(), Var()
        pairs = []
        for _ in call("list_item", N, chars("ab"), E, module=mod):
            pairs.append((deref(N), deref(E)))
        assert pairs == [(0, mint("a")), (1, mint("b"))]


# ── take/3, drop/3, split_at/4 ─────────────────────────────────────────────


class TestTakeDropSplitAt:
    def test_take(self, mod):
        # nv
        X = Var()
        assert _collect(X, "take", 3, chars("hello"), X, module=mod) == [chars("hel")]

    def test_drop(self, mod):
        # nv
        X = Var()
        assert _collect(X, "drop", 3, chars("hello"), X, module=mod) == [chars("lo")]

    def test_split_at(self, mod):
        # nv
        L, R = Var(), Var()
        for _ in call("split_at", 3, chars("hello"), L, R, module=mod):
            assert deref(L) == chars("hel")
            assert deref(R) == chars("lo")

    def test_take_zero(self, mod):
        # nv
        X = Var()
        assert _collect(X, "take", 0, chars("hello"), X, module=mod) == [chars("")]

    def test_drop_all(self, mod):
        # nv
        X = Var()
        assert _collect(X, "drop", 5, chars("hello"), X, module=mod) == [chars("")]


# ── msort/2, sort/2 ───────────────────────────────────────────────────


class TestSortString:
    def test_msort(self, mod):
        # nv
        X = Var()
        r = _collect(X, "msort", chars("cba"), X, module=mod)
        assert r == [chars("abc")]

    def test_msort_duplicates(self, mod):
        # nv
        X = Var()
        r = _collect(X, "msort", chars("abba"), X, module=mod)
        assert r == [chars("aabb")]

    def test_sort_dedup(self, mod):
        # nv
        X = Var()
        r = _collect(X, "sort", chars("abba"), X, module=mod)
        assert r == [chars("ab")]


# ── list_to_set/2 ────────────────────────────────────────────────────────────────


class TestToSetString:
    def test_to_set(self, mod):
        # nv
        X = Var()
        r = _collect(X, "list_to_set", chars("abba"), X, module=mod)
        assert r == [chars("ab")]


# ── select/3 ──────────────────────────────────────────────────────────────


class TestSelectString:
    def test_select(self, mod):
        # nv
        E, R = Var(), Var()
        pairs = []
        for _ in call("select", E, chars("abc"), R, module=mod):
            pairs.append((deref(E), deref(R)))
        assert pairs == [
            (char_atom("a"), chars("bc")),
            (char_atom("b"), chars("ac")),
            (char_atom("c"), chars("ab")),
        ]


# ── subtract/3, intersection/3, union/3 ───────────────────────────────────


class TestSetOpsString:
    def test_subtract(self, mod):
        # nv
        X = Var()
        r = _collect(X, "subtract", chars("abcd"), chars("bd"), X, module=mod)
        assert r == [chars("ac")]

    def test_intersection(self, mod):
        # nv
        X = Var()
        r = _collect(X, "intersection", chars("abcd"), chars("bce"), X, module=mod)
        assert r == [chars("bc")]

    def test_union(self, mod):
        # nv
        X = Var()
        r = _collect(X, "union", chars("abc"), chars("cde"), X, module=mod)
        assert r == [chars("abcde")]


# ── max_list/2, min_list/2 ──────────────────────────────────────────────────


class TestMaxMinString:
    def test_max(self, mod):
        # nv
        X = Var()
        r = _collect(X, "max_list", chars("hello"), X, module=mod)
        assert r == [mint("o")]

    def test_min(self, mod):
        # nv
        X = Var()
        r = _collect(X, "min_list", chars("hello"), X, module=mod)
        assert r == [mint("e")]


# ── permutation/2 ─────────────────────────────────────────────────────────


class TestPermutationString:
    def test_permutations(self, mod):
        # nv
        P = Var()
        results = _collect(P, "permutation", chars("ab"), P, module=mod)
        assert set(results) == {chars("ab"), chars("ba")}
        assert all(is_chars(r) for r in results)


# ── zip_/3 ──────────────────────────────────────────────────────────────────


class TestZipString:
    def test_zip_strings(self, mod):
        # nv
        X = Var()
        r = _collect(X, "zip_", chars("ab"), chars("12"), X, module=mod)
        assert r == [[[char_atom("a"), char_atom("1")],
                      [char_atom("b"), char_atom("2")]]]

    def test_zip_string_list(self, mod):
        # nv
        X = Var()
        r = _collect(X, "zip_", chars("ab"), [1, 2], X, module=mod)
        assert r == [[[char_atom("a"), 1], [char_atom("b"), 2]]]


# ── split_with/3 ───────────────────────────────────────────────────────────


class TestSplitWithString:
    def test_split_by_comma(self, mod):
        # nv
        X = Var()
        # THE FLIP: the separator is an ELEMENT of the string, i.e. a CHAR
        # ATOM; the ``str`` "," is a one-element STRING and matches nothing.
        r = _collect(X, "split_with", char_atom(","), chars("a,b,c"), X, module=mod)
        assert r == [[chars("a"), chars("b"), chars("c")]]

    def test_split_no_sep(self, mod):
        # nv
        X = Var()
        r = _collect(X, "split_with", char_atom(","), chars("abc"), X, module=mod)
        assert r == [[chars("abc")]]


# ── same_length/2 ──────────────────────────────────────────────────────────


class TestSameLengthString:
    def test_same_length(self, mod):
        # nv
        assert _first("same_length", chars("abc"), chars("xyz"), module=mod)

    def test_different_length(self, mod):
        # nv
        assert not _first("same_length", chars("ab"), chars("xyz"), module=mod)

    def test_string_list_same_length(self, mod):
        # nv
        assert _first("same_length", chars("abc"), [1, 2, 3], module=mod)


# ── is_chars/1 ─────────────────────────────────────────────────────────────


class TestIsChars:
    def test_string(self, mod):
        # nv
        assert _first("is_chars", chars("hello"), module=mod)

    def test_list(self, mod):
        # nv
        assert _first("is_chars", [1, 2], module=mod)

    def test_int_fails(self, mod):
        # nv
        assert not _first("is_chars", 42, module=mod)

    def test_is_list_string_now_succeeds(self, mod):
        """is_list('hello') succeeds — strings-as-lists contract.

        Audit 2026-05-25 (Phase 2 Task 9, finding F080): the user
        selected option A — every list-flavoured builtin already
        treats ``str`` as a character sequence, so ``is_list/1`` is
        now polymorphic over ``list`` and ``str`` to match. The prior
        ``not _first(...)`` assertion has been inverted; see
        ``docs/superpowers/audits/2026-05-25-string-implementation``
        ledger entry F080 for the full rationale.
        """
        # nv
        assert _first("is_list", chars("hello"), module=mod)
