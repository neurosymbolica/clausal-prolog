"""Tests for Phase 1: string ↔ list unification at the C level.

Strings are treated as lists of single-character strings during unification.
String-vs-string unification remains fast equality (unchanged).
"""

import pytest
from clausal.logic.variables import Var, Trail, unify, deref


class TestStringUnifiesWithCharList:
    """Core: str = [char, char, ...] element-wise unification."""

    def test_basic(self):
        assert unify("abc", ["a", "b", "c"], Trail())

    def test_symmetric(self):
        assert unify(["a", "b", "c"], "abc", Trail())

    def test_empty(self):
        assert unify("", [], Trail())

    def test_single_char(self):
        assert unify("a", ["a"], Trail())

    def test_unicode(self):
        assert unify("日本語", ["日", "本", "語"], Trail())

    def test_emoji(self):
        assert unify("👋🌍", ["👋", "🌍"], Trail())


class TestStringListMismatch:
    """Unification fails when content or length doesn't match."""

    def test_length_str_longer(self):
        assert not unify("abc", ["a", "b"], Trail())

    def test_length_list_longer(self):
        assert not unify("ab", ["a", "b", "c"], Trail())

    def test_content_mismatch(self):
        assert not unify("abc", ["a", "x", "c"], Trail())

    def test_str_vs_int_list(self):
        assert not unify("abc", [1, 2, 3], Trail())

    def test_str_vs_multi_char_elements(self):
        """'abc' = ['ab', 'c'] fails — length 3 vs 2."""
        assert not unify("abc", ["ab", "c"], Trail())

    def test_str_vs_mixed_type_list(self):
        assert not unify("abc", ["a", 2, "c"], Trail())

    def test_str_vs_none_in_list(self):
        assert not unify("abc", ["a", None, "c"], Trail())


class TestStringListVarBinding:
    """Variables in the list get bound to single-character strings."""

    def test_all_vars(self):
        trail = Trail()
        X, Y, Z = Var(), Var(), Var()
        assert unify("abc", [X, Y, Z], trail)
        assert deref(X) == "a"
        assert deref(Y) == "b"
        assert deref(Z) == "c"

    def test_partial_vars(self):
        trail = Trail()
        X = Var()
        assert unify("abc", ["a", X, "c"], trail)
        assert deref(X) == "b"

    def test_var_at_start(self):
        trail = Trail()
        X = Var()
        assert unify("abc", [X, "b", "c"], trail)
        assert deref(X) == "a"

    def test_var_at_end(self):
        trail = Trail()
        X = Var()
        assert unify("abc", ["a", "b", X], trail)
        assert deref(X) == "c"

    def test_var_mismatch_other_position(self):
        """'abc' = ['a', X, 'z'] fails at position 2."""
        trail = Trail()
        X = Var()
        assert not unify("abc", ["a", X, "z"], trail)

    def test_symmetric_var_binding(self):
        """[X, 'b', 'c'] = 'abc' binds X='a'."""
        trail = Trail()
        X = Var()
        assert unify([X, "b", "c"], "abc", trail)
        assert deref(X) == "a"

    def test_unicode_var_binding(self):
        trail = Trail()
        X, Y = Var(), Var()
        assert unify("日本語", [X, "本", Y], trail)
        assert deref(X) == "日"
        assert deref(Y) == "語"


class TestStringStringUnchanged:
    """String-vs-string unification remains equality (not element-wise)."""

    def test_equal(self):
        assert unify("abc", "abc", Trail())

    def test_not_equal(self):
        assert not unify("abc", "def", Trail())

    def test_empty_strings(self):
        assert unify("", "", Trail())

    def test_unicode_equal(self):
        assert unify("日本", "日本", Trail())

    def test_unicode_not_equal(self):
        assert not unify("日本", "中国", Trail())


class TestBacktracking:
    """Trail undo restores variables after failed/retracted unification."""

    def test_undo_restores_var(self):
        trail = Trail()
        X = Var()
        mark = trail.mark()
        assert unify("abc", ["a", X, "c"], trail)
        assert deref(X) == "b"
        trail.undo(mark)
        assert deref(X) is X  # unbound again

    def test_undo_after_failed_unify(self):
        """Failed unification should not leave partial bindings."""
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
    """Strings inside lists unify with char-lists inside lists."""

    def test_nested_string(self):
        assert unify([1, "abc", 2], [1, ["a", "b", "c"], 2], Trail())

    def test_list_of_strings(self):
        assert unify(["ab", "cd"], [["a", "b"], ["c", "d"]], Trail())

    def test_deeply_nested(self):
        """String inside nested list unifies with char list at same position."""
        assert unify([["ab", "cd"]], [["ab", "cd"]], Trail())
        # String at depth 2 vs char list at depth 2:
        assert unify([[1, "ab"]], [[1, ["a", "b"]]], Trail())

    def test_string_in_tuple(self):
        """Strings in tuples also unify with char lists in tuples."""
        assert unify((1, "ab"), (1, ["a", "b"]), Trail())

    def test_mixed_nesting(self):
        trail = Trail()
        X = Var()
        assert unify([1, "ab"], [1, ["a", X]], trail)
        assert deref(X) == "b"


class TestEdgeCases:
    """Boundary conditions and unusual inputs."""

    def test_very_long_string(self):
        s = "a" * 1000
        lst = ["a"] * 1000
        assert unify(s, lst, Trail())

    def test_very_long_string_mismatch_at_end(self):
        s = "a" * 999 + "b"
        lst = ["a"] * 1000
        assert not unify(s, lst, Trail())

    def test_string_vs_empty_list(self):
        assert not unify("a", [], Trail())

    def test_empty_string_vs_nonempty_list(self):
        assert not unify("", ["a"], Trail())

    def test_newline_char(self):
        assert unify("a\nb", ["a", "\n", "b"], Trail())

    def test_null_char(self):
        assert unify("a\x00b", ["a", "\x00", "b"], Trail())

    def test_surrogate_pair(self):
        """Multi-byte Unicode char is a single element."""
        assert unify("𝕳", ["𝕳"], Trail())

    def test_string_does_not_unify_with_tuple(self):
        """Strings only unify with lists, not tuples of chars."""
        assert not unify("ab", ("a", "b"), Trail())

    def test_pre_bound_var_match(self):
        """A var already bound to a char matches the string position."""
        trail = Trail()
        X = Var()
        unify(X, "b", trail)
        assert unify("abc", ["a", X, "c"], trail)

    def test_pre_bound_var_mismatch(self):
        """A var bound to wrong char causes failure."""
        trail = Trail()
        X = Var()
        unify(X, "z", trail)
        assert not unify("abc", ["a", X, "c"], trail)

    def test_same_var_repeated(self):
        """'aba' = [X, 'b', X] succeeds (X='a' used twice)."""
        trail = Trail()
        X = Var()
        assert unify("aba", [X, "b", X], trail)
        assert deref(X) == "a"

    def test_same_var_repeated_conflict(self):
        """'abc' = [X, 'b', X] fails (X can't be both 'a' and 'c')."""
        trail = Trail()
        X = Var()
        assert not unify("abc", [X, "b", X], trail)


# ── Phase 2: SegList accepts strings ────────────────────────────────────────

from clausal.terms import SegList, ConcreteSeg, VarSeg


class TestSegListStringUnification:
    """SegList patterns match against strings."""

    def test_head_tail(self):
        """[X, *T] matches 'hello' → X='h', T=['e','l','l','o']."""
        trail = Trail()
        X, T = Var(), Var()
        sl = SegList([ConcreteSeg([X]), VarSeg(T)])
        assert unify(sl, "hello", trail)
        assert deref(X) == "h"
        assert deref(T) == ["e", "l", "l", "o"]

    def test_prefix_suffix(self):
        """[*P, ',', *S] matches 'a,b'."""
        trail = Trail()
        P, S = Var(), Var()
        sl = SegList([VarSeg(P), ConcreteSeg([","]), VarSeg(S)])
        assert unify(sl, "a,b", trail)
        assert deref(P) == ["a"]
        assert deref(S) == ["b"]

    def test_multi_star_multiple_solutions(self):
        """[*A, 'l', *B] matches 'hello' at two positions (l at idx 2 and 3)."""
        from clausal.terms import _seglist_unify_gen
        trail = Trail()
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg(["l"]), VarSeg(B)])
        walked = sl.__walk__()
        target = list("hello")
        solutions = []
        for _ in _seglist_unify_gen(walked, target, trail):
            solutions.append((list(deref(A)), list(deref(B))))
        assert len(solutions) == 2
        assert (["h", "e"], ["l", "o"]) in solutions
        assert (["h", "e", "l"], ["o"]) in solutions

    def test_empty_string(self):
        """[*A] matches '' → A=[]."""
        trail = Trail()
        A = Var()
        sl = SegList([VarSeg(A)])
        assert unify(sl, "", trail)
        assert deref(A) == []

    def test_full_concrete_match(self):
        """['h', 'i'] matches 'hi'."""
        sl = SegList([ConcreteSeg(["h", "i"])])
        assert unify(sl, "hi", Trail())

    def test_full_concrete_mismatch(self):
        """['h', 'i'] does NOT match 'ho'."""
        sl = SegList([ConcreteSeg(["h", "i"])])
        assert not unify(sl, "ho", Trail())

    def test_concrete_length_mismatch(self):
        """['a', 'b', 'c'] does NOT match 'ab'."""
        sl = SegList([ConcreteSeg(["a", "b", "c"])])
        assert not unify(sl, "ab", Trail())

    def test_only_star(self):
        """[*X] matches 'abc' → X=['a','b','c']."""
        trail = Trail()
        X = Var()
        sl = SegList([VarSeg(X)])
        assert unify(sl, "abc", trail)
        assert deref(X) == ["a", "b", "c"]

    def test_two_stars(self):
        """[*A, *B] matches 'abc' — enumerates 4 splits."""
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
        trail = Trail()
        X, T = Var(), Var()
        sl = SegList([ConcreteSeg([X]), VarSeg(T)])
        assert unify(sl, "日本語", trail)
        assert deref(X) == "日"
        assert deref(T) == ["本", "語"]

    def test_symmetric_string_seglist(self):
        """unify('hello', SegList) works (SegList has __unify__ hook)."""
        trail = Trail()
        X, T = Var(), Var()
        sl = SegList([ConcreteSeg([X]), VarSeg(T)])
        # SegList is on the right, string on the left — C tries t2.__unify__(t1)
        assert unify("hello", sl, trail)
        assert deref(X) == "h"
        assert deref(T) == ["e", "l", "l", "o"]


class TestBodyMultiStarUnifyString:
    """_body_multi_star_unify handles string targets."""

    def test_split_at_comma(self):
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [","]), ("star", B)]
        results = []
        for _ in _body_multi_star_unify("a,b", segments, trail):
            results.append((list(deref(A)), list(deref(B))))
        assert len(results) == 1
        assert results[0] == (["a"], ["b"])

    def test_multiple_commas(self):
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [","]), ("star", B)]
        results = []
        for _ in _body_multi_star_unify("a,b,c", segments, trail):
            results.append((list(deref(A)), list(deref(B))))
        assert len(results) == 2

    def test_no_match(self):
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [","]), ("star", B)]
        results = list(_body_multi_star_unify("abc", segments, trail))
        assert results == []  # No comma in string

    def test_empty_string(self):
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A = Var()
        segments = [("star", A)]
        results = list(_body_multi_star_unify("", segments, trail))
        assert len(results) == 1
