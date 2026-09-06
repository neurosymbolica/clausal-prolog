"""Tests for Phase 1: string ↔ list unification at the C level.

P3-1 Task 5 (§1b/R2), 2026-09-04: the Phase 1 rule this file was written
to pin — a bare str unifies element-wise with a char list — is RETIRED.
str unifies with str by equality; lists unify with lists; SegString
remains the char-list optimisation (unaffected, see test_segstring.py).
``TestStringUnifiesWithCharList`` and the var-binding half of
``TestStringListVarBinding`` are inverted below to pin the retirement;
the mismatch/failure-case classes (which already asserted ``not unify``)
are unaffected — they still fail, just via a different code path now
(the generic list/tuple-mismatch guard in ``_variables.c`` rather than
the deleted str↔list cons-rule block).
"""

import pytest
from clausal.logic.atoms import char_atom, mint
from clausal.logic.variables import Var, Trail, unify, deref, is_var


class TestStringUnifiesWithCharList:
    """RETIRED (P3-1 §1b): str vs char-list element-wise unification.

    (Formerly "Core: str = [char, char, ...] element-wise unification" —
    every case here now fails.)
    """

    def test_basic(self):
        # nv
        assert not unify("abc", ["a", "b", "c"], Trail())

    def test_symmetric(self):
        # nv
        assert not unify(["a", "b", "c"], "abc", Trail())

    def test_empty(self):
        # nv — empty str vs empty list: no cross-type exception either.
        assert not unify("", [], Trail())

    def test_single_char(self):
        # nv
        assert not unify("a", ["a"], Trail())

    def test_unicode(self):
        # nv
        assert not unify("日本語", ["日", "本", "語"], Trail())

    def test_emoji(self):
        # nv
        assert not unify("👋🌍", ["👋", "🌍"], Trail())


class TestStringListMismatch:
    """Unification fails when content or length doesn't match."""

    def test_length_str_longer(self):
        # nv
        assert not unify("abc", ["a", "b"], Trail())

    def test_length_list_longer(self):
        # nv
        assert not unify("ab", ["a", "b", "c"], Trail())

    def test_content_mismatch(self):
        # nv
        assert not unify("abc", ["a", "x", "c"], Trail())

    def test_str_vs_int_list(self):
        # nv
        assert not unify("abc", [1, 2, 3], Trail())

    def test_str_vs_multi_char_elements(self):
        """'abc' = ['ab', 'c'] fails — length 3 vs 2."""
        # nv
        assert not unify("abc", ["ab", "c"], Trail())

    def test_str_vs_mixed_type_list(self):
        # nv
        assert not unify("abc", ["a", 2, "c"], Trail())

    def test_str_vs_none_in_list(self):
        # nv
        assert not unify("abc", ["a", None, "c"], Trail())


class TestStringListVarBinding:
    """RETIRED (P3-1 §1b): a Var inside a char-list target no longer binds
    against a str's char — the whole unify fails before any element is
    visited (str is not list-shaped any more), so no partial bindings
    leak either.

    (Formerly "Variables in the list get bound to single-character
    strings".)
    """

    def test_all_vars(self):
        # nv
        trail = Trail()
        X, Y, Z = Var(), Var(), Var()
        assert not unify("abc", [X, Y, Z], trail)
        assert is_var(deref(X)) and is_var(deref(Y)) and is_var(deref(Z))

    def test_partial_vars(self):
        # nv
        trail = Trail()
        X = Var()
        assert not unify("abc", ["a", X, "c"], trail)
        assert is_var(deref(X))

    def test_var_at_start(self):
        # nv
        trail = Trail()
        X = Var()
        assert not unify("abc", [X, "b", "c"], trail)
        assert is_var(deref(X))

    def test_var_at_end(self):
        # nv
        trail = Trail()
        X = Var()
        assert not unify("abc", ["a", "b", X], trail)
        assert is_var(deref(X))

    def test_var_mismatch_other_position(self):
        """'abc' = ['a', X, 'z'] still fails — unaffected (was already a
        failure case, now for the retirement's reason rather than a
        content mismatch)."""
        # nv
        trail = Trail()
        X = Var()
        assert not unify("abc", ["a", X, "z"], trail)

    def test_symmetric_var_binding(self):
        """[X, 'b', 'c'] = 'abc' no longer binds X — retired."""
        # nv
        trail = Trail()
        X = Var()
        assert not unify([X, "b", "c"], "abc", trail)
        assert is_var(deref(X))

    def test_unicode_var_binding(self):
        # nv
        trail = Trail()
        X, Y = Var(), Var()
        assert not unify("日本語", [X, "本", Y], trail)
        assert is_var(deref(X)) and is_var(deref(Y))


class TestStringStringUnchanged:
    """String-vs-string unification remains equality (not element-wise)."""

    def test_equal(self):
        # nv
        assert unify("abc", "abc", Trail())

    def test_not_equal(self):
        # nv
        assert not unify("abc", "def", Trail())

    def test_empty_strings(self):
        # nv
        assert unify("", "", Trail())

    def test_unicode_equal(self):
        # nv
        assert unify("日本", "日本", Trail())

    def test_unicode_not_equal(self):
        # nv
        assert not unify("日本", "中国", Trail())


class TestBacktracking:
    """Trail undo restores variables after failed/retracted unification."""

    def test_undo_restores_var(self):
        # nv — P3-1 §1b: retired, str-vs-list unify fails outright now, so
        # X is never bound in the first place (nothing to undo).
        trail = Trail()
        X = Var()
        mark = trail.mark()
        assert not unify("abc", ["a", X, "c"], trail)
        assert is_var(deref(X))
        trail.undo(mark)
        assert deref(X) is X  # still unbound

    def test_undo_after_failed_unify(self):
        """Failed unification should not leave partial bindings."""
        # nv
        trail = Trail()
        X, Y = Var(), Var()
        # This should fail at position 2 ('c' != 'z')
        assert not unify("abc", [X, Y, "z"], trail)
        # X and Y should remain unbound (no partial bindings leaked)
        # Note: the C unifier may or may not trail partial bindings before
        # discovering the mismatch. The important thing is that after a failed
        # unify call, no NEW bindings persist on the trail that the caller
        # didn't mark/undo.


class TestNestedStringList:
    """RETIRED (P3-1 §1b): a str nested inside a list/tuple no longer
    unifies with an equivalent char-list nested at the same position —
    the retirement applies recursively, same as at the top level.

    (Formerly "Strings inside lists unify with char-lists inside lists".)
    """

    def test_nested_string(self):
        # nv
        assert not unify([1, "abc", 2], [1, ["a", "b", "c"], 2], Trail())

    def test_list_of_strings(self):
        # nv
        assert not unify(["ab", "cd"], [["a", "b"], ["c", "d"]], Trail())

    def test_deeply_nested(self):
        """String inside nested list no longer unifies with char list at
        the same position; ground-list-vs-ground-list (no str involved)
        is unaffected."""
        # nv
        assert unify([["ab", "cd"]], [["ab", "cd"]], Trail())  # unaffected: no str~list crossing
        # String at depth 2 vs char list at depth 2 — retired:
        assert not unify([[1, "ab"]], [[1, ["a", "b"]]], Trail())

    def test_string_in_tuple(self):
        """Strings in tuples no longer unify with char lists in tuples."""
        # nv
        assert not unify((1, "ab"), (1, ["a", "b"]), Trail())

    def test_mixed_nesting(self):
        # nv
        trail = Trail()
        X = Var()
        assert not unify([1, "ab"], [1, ["a", X]], trail)
        assert is_var(deref(X))


class TestEdgeCases:
    """Boundary conditions and unusual inputs."""

    def test_very_long_string(self):
        # nv — P3-1 §1b: retired, regardless of length.
        s = "a" * 1000
        lst = ["a"] * 1000
        assert not unify(s, lst, Trail())

    def test_very_long_string_mismatch_at_end(self):
        # nv
        s = "a" * 999 + "b"
        lst = ["a"] * 1000
        assert not unify(s, lst, Trail())

    def test_string_vs_empty_list(self):
        # nv
        assert not unify("a", [], Trail())

    def test_empty_string_vs_nonempty_list(self):
        # nv
        assert not unify("", ["a"], Trail())

    def test_newline_char(self):
        # nv — P3-1 §1b: retired.
        assert not unify("a\nb", ["a", "\n", "b"], Trail())

    def test_null_char(self):
        # nv — P3-1 §1b: retired.
        assert not unify("a\x00b", ["a", "\x00", "b"], Trail())

    def test_surrogate_pair(self):
        """Multi-byte Unicode char no longer unifies as a single element
        — P3-1 §1b: retired."""
        # nv
        assert not unify("𝕳", ["𝕳"], Trail())

    def test_string_does_not_unify_with_tuple(self):
        """Strings only unify with lists, not tuples of chars."""
        # nv
        assert not unify("ab", ("a", "b"), Trail())

    def test_pre_bound_var_match(self):
        """A var already bound to a char no longer matches the string
        position — P3-1 §1b: retired regardless of the element's
        binding."""
        # nv
        trail = Trail()
        X = Var()
        unify(X, "b", trail)
        assert not unify("abc", ["a", X, "c"], trail)

    def test_pre_bound_var_mismatch(self):
        """A var bound to wrong char causes failure."""
        # nv
        trail = Trail()
        X = Var()
        unify(X, "z", trail)
        assert not unify("abc", ["a", X, "c"], trail)

    def test_same_var_repeated(self):
        """'aba' = [X, 'b', X] no longer succeeds — P3-1 §1b: retired."""
        # nv
        trail = Trail()
        X = Var()
        assert not unify("aba", [X, "b", X], trail)
        assert is_var(deref(X))

    def test_same_var_repeated_conflict(self):
        """'abc' = [X, 'b', X] fails (X can't be both 'a' and 'c')."""
        # nv
        trail = Trail()
        X = Var()
        assert not unify("abc", [X, "b", X], trail)


# ── Phase 2: SegList accepts strings ────────────────────────────────────────

from clausal.terms import SegList, ConcreteSeg, VarSeg


class TestSegListStringUnification:
    """SegList patterns match against strings."""

    def test_head_tail(self):
        """[X, *T] matches 'hello' → X='h', T='ello' (substring preserved)."""
        # nv
        trail = Trail()
        X, T = Var(), Var()
        sl = SegList([ConcreteSeg([X]), VarSeg(T)])
        assert unify(sl, "hello", trail)
        assert deref(X) == mint("h")
        assert deref(T) == "ello"

    def test_prefix_suffix(self):
        """[*P, ',', *S] matches 'a,b' — star vars bind to substrings."""
        # nv
        trail = Trail()
        P, S = Var(), Var()
        sl = SegList([VarSeg(P), ConcreteSeg([","]), VarSeg(S)])
        assert unify(sl, "a,b", trail)
        assert deref(P) == "a"
        assert deref(S) == "b"

    def test_multi_star_multiple_solutions(self):
        """[*A, 'l', *B] matches 'hello' at two positions (l at idx 2 and 3)."""
        # nv
        from clausal.terms import _seglist_unify_gen
        trail = Trail()
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg(["l"]), VarSeg(B)])
        walked = sl.__walk__()
        # Pass string directly — VarSegs bind to substrings
        solutions = []
        for _ in _seglist_unify_gen(walked, "hello", trail):
            solutions.append((deref(A), deref(B)))
        assert len(solutions) == 2
        assert ("he", "lo") in solutions
        assert ("hel", "o") in solutions

    def test_empty_string(self):
        """[*A] matches '' → A='' (empty substring)."""
        # nv
        trail = Trail()
        A = Var()
        sl = SegList([VarSeg(A)])
        assert unify(sl, "", trail)
        assert deref(A) == ""

    def test_full_concrete_match(self):
        """['h', 'i'] matches 'hi'."""
        # nv
        sl = SegList([ConcreteSeg([mint("h"), "i"])])
        assert unify(sl, "hi", Trail())

    def test_full_concrete_mismatch(self):
        """['h', 'i'] does NOT match 'ho'."""
        # nv
        sl = SegList([ConcreteSeg([mint("h"), "i"])])
        assert not unify(sl, "ho", Trail())

    def test_concrete_length_mismatch(self):
        """['a', 'b', 'c'] does NOT match 'ab'."""
        # nv
        sl = SegList([ConcreteSeg(["a", "b", "c"])])
        assert not unify(sl, "ab", Trail())

    def test_only_star(self):
        """[*X] matches 'abc' → X='abc' (substring preserved)."""
        # nv
        trail = Trail()
        X = Var()
        sl = SegList([VarSeg(X)])
        assert unify(sl, "abc", trail)
        assert deref(X) == "abc"

    def test_two_stars(self):
        """[*A, *B] matches 'abc' — enumerates 4 splits."""
        # nv
        from clausal.terms import _seglist_unify_gen
        trail = Trail()
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), VarSeg(B)])
        walked = sl.__walk__()
        target = list("abc")
        solutions = []
        for _ in _seglist_unify_gen(walked, target, trail):
            solutions.append((list(deref(A)), list(deref(B))))
        assert len(solutions) == 4  # [], abc | [a], bc | ab, c | abc, []

    def test_var_in_concrete_binds(self):
        """[*_, X, *_] matching 'abc' with concrete var binds X to each char."""
        # nv
        from clausal.terms import _seglist_unify_gen
        trail = Trail()
        X = Var()
        Dummy1, Dummy2 = Var(), Var()
        sl = SegList([VarSeg(Dummy1), ConcreteSeg([X]), VarSeg(Dummy2)])
        walked = sl.__walk__()
        target = list("abc")
        chars = []
        for _ in _seglist_unify_gen(walked, target, trail):
            chars.append(deref(X))
        assert chars == ["a", "b", "c"]

    def test_unicode_string(self):
        """SegList matches unicode string."""
        # nv
        trail = Trail()
        X, T = Var(), Var()
        sl = SegList([ConcreteSeg([X]), VarSeg(T)])
        assert unify(sl, "日本語", trail)
        assert deref(X) == mint("日")
        assert deref(T) == "本語"

    def test_symmetric_string_seglist(self):
        """unify('hello', SegList) works (SegList has __unify__ hook)."""
        # nv
        trail = Trail()
        X, T = Var(), Var()
        sl = SegList([ConcreteSeg([X]), VarSeg(T)])
        # SegList is on the right, string on the left — C tries t2.__unify__(t1)
        assert unify("hello", sl, trail)
        assert deref(X) == mint("h")
        assert deref(T) == "ello"


class TestBodyMultiStarUnifyString:
    """_body_multi_star_unify handles string targets."""

    def test_split_at_comma(self):
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [","]), ("star", B)]
        results = []
        for _ in _body_multi_star_unify("a,b", segments, trail):
            results.append((list(deref(A)), list(deref(B))))
        assert len(results) == 1
        assert results[0] == (["a"], ["b"])

    def test_multiple_commas(self):
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [","]), ("star", B)]
        results = []
        for _ in _body_multi_star_unify("a,b,c", segments, trail):
            results.append((list(deref(A)), list(deref(B))))
        assert len(results) == 2

    def test_no_match(self):
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [","]), ("star", B)]
        results = list(_body_multi_star_unify("abc", segments, trail))
        assert results == []  # No comma in string

    def test_empty_string(self):
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A = Var()
        segments = [("star", A)]
        results = list(_body_multi_star_unify("", segments, trail))
        assert len(results) == 1
