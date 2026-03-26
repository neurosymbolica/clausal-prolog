"""Tests for Phase 7: SegString and string-preserving pattern matching.

Tests cover:
1. SegString core: construction, walk, unification, occurs check
2. String-preserving VarSeg binding in SegList (star vars → substrings)
3. Body multi-star on strings (compiler path)
4. _build_star_list / _build_multi_star_list string support
"""

from clausal.logic.variables import Var, Trail, unify, deref
from clausal.terms import (
    SegString, SegList, ConcreteSeg, VarSeg,
    _segstring_unify_gen, _seglist_unify_gen,
)


# ── SegString core ──────────────────────────────────────────────────────────


class TestSegStringConstruction:
    """SegString creation and basic properties."""

    def test_create(self):
        seg = SegString(["hel", VarSeg(Var()), "ld"])
        assert len(seg.segments) == 3
        assert seg.segments[0] == "hel"
        assert isinstance(seg.segments[1], VarSeg)
        assert seg.segments[2] == "ld"

    def test_repr(self):
        ss = SegString(["abc"])
        assert "SegString" in repr(ss)


class TestSegStringWalk:
    """SegString __walk__ normalisation."""

    def test_ground_returns_str(self):
        """Fully ground SegString walks to a plain str."""
        ss = SegString(["hello"])
        assert ss.__walk__() == "hello"

    def test_bound_varseg_collapses(self):
        """VarSeg bound to a string is inlined."""
        trail = Trail()
        X = Var()
        unify(X, "lo wor", trail)
        ss = SegString(["hel", VarSeg(X), "ld"])
        assert ss.__walk__() == "hello world"

    def test_unbound_returns_segstring(self):
        """Unbound VarSeg keeps SegString non-ground."""
        X = Var()
        ss = SegString(["hel", VarSeg(X), "ld"])
        walked = ss.__walk__()
        assert isinstance(walked, SegString)

    def test_empty_segments(self):
        """Empty SegString walks to empty str."""
        assert SegString([]).__walk__() == ""
        assert SegString([""]).__walk__() == ""

    def test_adjacent_strings_merge(self):
        """Adjacent str segments merge during walk."""
        ss = SegString(["hel", "lo"])
        assert ss.__walk__() == "hello"

    def test_varseg_bound_to_list_joins(self):
        """VarSeg bound to a char list is joined into string during walk."""
        trail = Trail()
        X = Var()
        unify(X, ["l", "o"], trail)
        ss = SegString(["hel", VarSeg(X)])
        assert ss.__walk__() == "hello"

    def test_nested_segstring(self):
        """VarSeg bound to another SegString is inlined."""
        trail = Trail()
        X = Var()
        inner = SegString(["lo wor"])
        unify(X, inner, trail)
        ss = SegString(["hel", VarSeg(X), "ld"])
        assert ss.__walk__() == "hello world"

    def test_is_ground(self):
        X = Var()
        ss = SegString(["abc"])
        assert ss.is_ground()
        ss2 = SegString(["a", VarSeg(X)])
        assert not ss2.is_ground()

    def test_to_str(self):
        ss = SegString(["hello"])
        assert ss.to_str() == "hello"

    def test_to_str_raises_when_not_ground(self):
        import pytest
        X = Var()
        ss = SegString(["a", VarSeg(X)])
        with pytest.raises(TypeError):
            ss.to_str()


class TestSegStringUnification:
    """SegString __unify__ against strings."""

    def test_ground_match(self):
        ss = SegString(["hello"])
        assert unify(ss, "hello", Trail())

    def test_ground_mismatch(self):
        ss = SegString(["hello"])
        assert not unify(ss, "world", Trail())

    def test_varseg_binds_to_substring(self):
        trail = Trail()
        X = Var()
        ss = SegString(["hel", VarSeg(X)])
        assert unify(ss, "hello", trail)
        assert deref(X) == "lo"

    def test_two_varseg(self):
        trail = Trail()
        A, B = Var(), Var()
        ss = SegString([VarSeg(A), ",", VarSeg(B)])
        assert unify(ss, "hello,world", trail)
        assert deref(A) == "hello"
        assert deref(B) == "world"

    def test_empty_match(self):
        assert unify(SegString([""]), "", Trail())
        assert unify(SegString([]), "", Trail())

    def test_varseg_empty_binding(self):
        trail = Trail()
        X = Var()
        ss = SegString([VarSeg(X), "abc"])
        assert unify(ss, "abc", trail)
        assert deref(X) == ""

    def test_string_vs_segstring_symmetric(self):
        """String on left, SegString on right — C tries __unify__."""
        trail = Trail()
        X = Var()
        ss = SegString(["hel", VarSeg(X)])
        assert unify("hello", ss, trail)
        assert deref(X) == "lo"


class TestSegStringOccursCheck:
    """SegString __occurs_check__."""

    def test_var_in_varseg(self):
        X = Var()
        ss = SegString(["abc", VarSeg(X)])
        assert ss.__occurs_check__(X)

    def test_var_not_in_segstring(self):
        X, Y = Var(), Var()
        ss = SegString(["abc", VarSeg(Y)])
        assert not ss.__occurs_check__(X)


class TestSegStringGenerator:
    """_segstring_unify_gen multiple solutions."""

    def test_multiple_splits(self):
        """[*A, ',', *B] matches 'a,b,c' at multiple comma positions."""
        trail = Trail()
        A, B = Var(), Var()
        ss = SegString([VarSeg(A), ",", VarSeg(B)])
        walked = ss.__walk__()
        solutions = []
        for _ in _segstring_unify_gen(walked, "a,b,c", trail):
            solutions.append((deref(A), deref(B)))
        assert len(solutions) == 2
        assert ("a", "b,c") in solutions
        assert ("a,b", "c") in solutions

    def test_no_match(self):
        trail = Trail()
        A, B = Var(), Var()
        ss = SegString([VarSeg(A), "x", VarSeg(B)])
        walked = ss.__walk__()
        solutions = list(_segstring_unify_gen(walked, "abc", trail))
        assert len(solutions) == 0

    def test_single_varseg(self):
        trail = Trail()
        X = Var()
        ss = SegString([VarSeg(X)])
        walked = ss.__walk__()
        solutions = []
        for _ in _segstring_unify_gen(walked, "hello", trail):
            solutions.append(deref(X))
        assert solutions == ["hello"]


# ── String-preserving SegList matching ──────────────────────────────────────


class TestSegListStringPreserving:
    """SegList VarSegs bind to substrings when matching strings."""

    def test_single_star_binds_substring(self):
        trail = Trail()
        T = Var()
        sl = SegList([ConcreteSeg(["h"]), VarSeg(T)])
        assert unify(sl, "hello", trail)
        assert deref(T) == "ello"
        assert isinstance(deref(T), str)

    def test_multi_star_binds_substrings(self):
        trail = Trail()
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg([","]), VarSeg(B)])
        assert unify(sl, "hello,world", trail)
        assert deref(A) == "hello"
        assert deref(B) == "world"

    def test_star_binds_empty_substring(self):
        trail = Trail()
        A = Var()
        sl = SegList([VarSeg(A), ConcreteSeg(["x"])])
        assert unify(sl, "x", trail)
        assert deref(A) == ""

    def test_walk_handles_string_bound_varseg(self):
        """SegList.__walk__ converts string-bound VarSegs to char lists."""
        trail = Trail()
        A = Var()
        unify(A, "hello", trail)
        sl = SegList([VarSeg(A)])
        walked = sl.__walk__()
        assert isinstance(walked, list)
        assert walked == ["h", "e", "l", "l", "o"]

    def test_seglist_still_works_with_lists(self):
        """SegList against list still returns list slices."""
        trail = Trail()
        T = Var()
        sl = SegList([ConcreteSeg([1]), VarSeg(T)])
        assert unify(sl, [1, 2, 3], trail)
        assert deref(T) == [2, 3]
        assert isinstance(deref(T), list)

    def test_multi_star_string_generator(self):
        """_seglist_unify_gen with string target yields substring bindings."""
        trail = Trail()
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg(["l"]), VarSeg(B)])
        walked = sl.__walk__()
        solutions = []
        for _ in _seglist_unify_gen(walked, "hello", trail):
            solutions.append((deref(A), deref(B)))
        assert len(solutions) == 2
        assert ("he", "lo") in solutions
        assert ("hel", "o") in solutions


# ── Body multi-star on strings (compiler path) ─────────────────────────────


class TestBodyMultiStarString:
    """_body_multi_star_unify preserves string type."""

    def test_star_vars_bind_to_substrings(self):
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [","]), ("star", B)]
        solutions = []
        for _ in _body_multi_star_unify("hello,world", segments, trail):
            solutions.append((deref(A), deref(B)))
        assert ("hello", "world") in solutions

    def test_fixed_elements_match_chars(self):
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", ["l"]), ("star", B)]
        solutions = []
        for _ in _body_multi_star_unify("hello", segments, trail):
            solutions.append((deref(A), deref(B)))
        assert len(solutions) == 2
        assert ("he", "lo") in solutions
        assert ("hel", "o") in solutions

    def test_empty_string_target(self):
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A = Var()
        segments = [("star", A)]
        solutions = []
        for _ in _body_multi_star_unify("", segments, trail):
            solutions.append(deref(A))
        assert solutions == [""]

    def test_no_match(self):
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", ["x"]), ("star", B)]
        solutions = list(_body_multi_star_unify("hello", segments, trail))
        assert len(solutions) == 0


# ── _build_star_list / _build_multi_star_list string support ────────────────


class TestBuildStarListString:
    """_build_star_list returns strings when inputs are string-compatible."""

    def test_star_str_returns_str(self):
        from clausal.logic.compiler import _build_star_list
        trail = Trail()
        X = Var()
        unify(X, "ello", trail)
        result = _build_star_list(["h"], X, [])
        assert result == "hello"
        assert isinstance(result, str)

    def test_star_str_with_after(self):
        from clausal.logic.compiler import _build_star_list
        trail = Trail()
        X = Var()
        unify(X, "ell", trail)
        result = _build_star_list(["h"], X, ["o"])
        assert result == "hello"
        assert isinstance(result, str)

    def test_star_list_returns_list(self):
        """Non-string star still returns a list."""
        from clausal.logic.compiler import _build_star_list
        trail = Trail()
        X = Var()
        unify(X, [2, 3], trail)
        result = _build_star_list([1], X, [4])
        assert result == [1, 2, 3, 4]
        assert isinstance(result, list)


class TestBuildMultiStarListString:
    """_build_multi_star_list returns strings when all parts are chars."""

    def test_all_str_returns_str(self):
        from clausal.logic.compiler import _build_multi_star_list
        trail = Trail()
        A, B = Var(), Var()
        unify(A, "hel", trail)
        unify(B, "ld", trail)
        result = _build_multi_star_list([
            ("star", A), ("fixed", ["lo wor"]), ("star", B),
        ])
        # "lo wor" is not a single char — falls back to list
        # Only single-char strings qualify for str result
        assert isinstance(result, list)

    def test_single_char_fixed_returns_str(self):
        from clausal.logic.compiler import _build_multi_star_list
        trail = Trail()
        A, B = Var(), Var()
        unify(A, "he", trail)
        unify(B, "lo", trail)
        result = _build_multi_star_list([
            ("star", A), ("fixed", ["l"]), ("star", B),
        ])
        # All chars are single-char strings → str result
        assert result == "hello"
        assert isinstance(result, str)


# ── Integration: clause-level string pattern matching ───────────────────────


class TestClauseLevelStringPatterns:
    """End-to-end tests using existing clausal modules with string patterns."""

    def test_head_tail_string(self):
        """HeadTail from list_edge_cases works on strings (Phase 5b)."""
        import os
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        fixture = os.path.join(
            os.path.dirname(__file__), "clausal_modules", "list_edge_cases.clausal"
        )
        mod = _load_module("lec_segstr", fixture).__dict__["$module"]
        H, T = Var(), Var()
        for _ in call("HeadTail", "hello", H, T, module=mod):
            assert deref(H) == "h"
            assert deref(T) == "ello"
            break

    def test_body_multi_star_string_direct(self):
        """_body_multi_star_unify with string target — star vars are substrings."""
        from clausal.logic.compiler import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [","]), ("star", B)]
        found = False
        for _ in _body_multi_star_unify("hello,world", segments, trail):
            if deref(A) == "hello" and deref(B) == "world":
                found = True
                break
        assert found
