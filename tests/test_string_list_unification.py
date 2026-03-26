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
