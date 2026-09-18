"""Tests for Phase 7: SegString and string-preserving pattern matching.

Tests cover:
1. SegString core: construction, walk, unification, occurs check
2. String-preserving VarSeg binding in SegList (star vars → substrings)
3. Body multi-star on strings (compiler path)
4. _build_star_list / _build_multi_star_list string support
"""

from clausal.logic.atoms import char_atom
from clausal.logic.cells import chars, is_chars
from clausal.logic.variables import Var, Trail, unify, deref
from clausal.terms import (
    SegBytes, SegString, SegList, ConcreteSeg, VarSeg,
    _segstring_unify_gen, _seglist_unify_gen,
)


# ── SegString core ──────────────────────────────────────────────────────────


class TestSegStringConstruction:
    """SegString creation and basic properties."""

    def test_create(self):
        # nv
        seg = SegString(["hel", VarSeg(Var()), "ld"])
        assert len(seg.segments) == 3
        assert seg.segments[0] == "hel"
        assert isinstance(seg.segments[1], VarSeg)
        assert seg.segments[2] == "ld"

    def test_repr(self):
        # nv
        ss = SegString(["abc"])
        assert "SegString" in repr(ss)


class TestSegStringWalk:
    """SegString __walk__ normalisation."""

    def test_ground_returns_str(self):
        """Fully ground SegString walks to a plain str."""
        # nv
        ss = SegString(["hello"])
        assert ss.__walk__() == chars("hello")

    def test_bound_varseg_collapses(self):
        """VarSeg bound to a string is inlined."""
        # nv
        trail = Trail()
        X = Var()
        unify(X, "lo wor", trail)
        ss = SegString(["hel", VarSeg(X), "ld"])
        assert ss.__walk__() == chars("hello world")

    def test_unbound_returns_segstring(self):
        """Unbound VarSeg keeps SegString non-ground."""
        # nv
        X = Var()
        ss = SegString(["hel", VarSeg(X), "ld"])
        walked = ss.__walk__()
        assert isinstance(walked, SegString)

    def test_empty_segments(self):
        """Empty SegString walks to empty str."""
        # nv
        assert SegString([]).__walk__() == chars("")
        assert SegString([""]).__walk__() == chars("")

    def test_adjacent_strings_merge(self):
        """Adjacent str segments merge during walk."""
        # nv
        ss = SegString(["hel", "lo"])
        assert ss.__walk__() == chars("hello")

    def test_varseg_bound_to_list_joins(self):
        """VarSeg bound to a char list is joined into string during walk."""
        # nv
        trail = Trail()
        X = Var()
        unify(X, [char_atom("l"), char_atom("o")], trail)
        ss = SegString(["hel", VarSeg(X)])
        assert ss.__walk__() == chars("hello")

    def test_nested_segstring(self):
        """VarSeg bound to another SegString is inlined."""
        # nv
        trail = Trail()
        X = Var()
        inner = SegString(["lo wor"])
        unify(X, inner, trail)
        ss = SegString(["hel", VarSeg(X), "ld"])
        assert ss.__walk__() == chars("hello world")

    def test_is_ground(self):
        # nv
        X = Var()
        ss = SegString(["abc"])
        assert ss.is_ground()
        ss2 = SegString(["a", VarSeg(X)])
        assert not ss2.is_ground()

    def test_to_str(self):
        # nv
        ss = SegString(["hello"])
        assert ss.to_str() == "hello"

    def test_to_str_raises_when_not_ground(self):
        # nv
        import pytest
        X = Var()
        ss = SegString(["a", VarSeg(X)])
        with pytest.raises(TypeError):
            ss.to_str()


class TestSegStringUnification:
    """SegString __unify__ against strings."""

    def test_ground_match(self):
        # nv
        ss = SegString(["hello"])
        assert unify(ss, chars("hello"), Trail())

    def test_ground_mismatch(self):
        # nv
        ss = SegString(["hello"])
        assert not unify(ss, "world", Trail())

    def test_varseg_binds_to_substring(self):
        # nv
        trail = Trail()
        X = Var()
        ss = SegString(["hel", VarSeg(X)])
        assert unify(ss, chars("hello"), trail)
        assert deref(X) == chars("lo")

    def test_two_varseg(self):
        # nv
        trail = Trail()
        A, B = Var(), Var()
        ss = SegString([VarSeg(A), ",", VarSeg(B)])
        assert unify(ss, chars("hello,world"), trail)
        assert deref(A) == chars("hello")
        assert deref(B) == chars("world")

    def test_empty_match(self):
        # nv
        assert unify(SegString([""]), chars(""), Trail())
        assert unify(SegString([]), chars(""), Trail())

    def test_varseg_empty_binding(self):
        # nv
        trail = Trail()
        X = Var()
        ss = SegString([VarSeg(X), "abc"])
        assert unify(ss, chars("abc"), trail)
        assert deref(X) == chars("")

    def test_string_vs_segstring_symmetric(self):
        """String on left, SegString on right — C tries __unify__."""
        # nv
        trail = Trail()
        X = Var()
        ss = SegString(["hel", VarSeg(X)])
        assert unify(chars("hello"), ss, trail)
        assert deref(X) == chars("lo")

    def test_segstring_vs_char_list(self):
        """Ground SegString unifies with a character list via C str↔list."""
        # nv
        trail = Trail()
        ss = SegString(["hello"])
        assert unify(ss, [char_atom('h'), char_atom('e'), char_atom('l'), char_atom('l'), char_atom('o')], trail)

    def test_segstring_vs_char_list_with_var(self):
        """SegString with bound VarSeg unifies with char list."""
        # nv
        trail = Trail()
        X = Var()
        unify(X, "lo", trail)
        ss = SegString(["hel", VarSeg(X)])
        assert unify(ss, [char_atom('h'), char_atom('e'), char_atom('l'), char_atom('l'), char_atom('o')], trail)

    def test_segstring_vs_wrong_list_fails(self):
        """SegString 'hello' does NOT unify with [1, 2, 3]."""
        # nv
        assert not unify(SegString(["hello"]), [1, 2, 3], Trail())


class TestAnEmptySegIsTheEmptyList:
    """Task 15 fix round 4, item 5.

    Nil is ONE term with several spellings — ``[]``, ``""``, ``b""``, ``()``
    — and every top-level pair of them unifies.  A ``Seg*`` that WALKS to
    nothing is that same term, so it must unify with (and compare equal to)
    every spelling, not only the one its own arm accepts.  Fix round 3 gave
    the three empty ``Seg*`` the ``()`` and ``[]`` spellings; the str/bytes
    CROSS pairs (``SegString([""])`` vs ``b""``, ``SegBytes([b""])`` vs
    ``""``) and ``SegList`` vs ``b""`` under ``==`` were left False —
    a residual non-transitivity, since ``""`` and ``b""`` unify with each
    other directly.
    """

    NIL_SPELLINGS = ([], chars(""), b"", ())

    def _empties(self):
        return (SegList([ConcreteSeg([])]), SegString([""]), SegBytes([b""]))

    def test_every_empty_seg_unifies_with_every_nil_spelling(self):
        # nv
        for seg in self._empties():
            for nil in self.NIL_SPELLINGS:
                assert unify(seg, nil, Trail()), (seg, nil)

    def test_the_nil_spelling_on_the_LEFT_unifies_too(self):
        """Symmetry: the C top level dispatches on either operand."""
        # nv
        for seg in self._empties():
            for nil in self.NIL_SPELLINGS:
                assert unify(nil, seg, Trail()), (nil, seg)

    def test_every_empty_seg_compares_equal_to_every_nil_spelling(self):
        # nv
        for seg in self._empties():
            for nil in self.NIL_SPELLINGS:
                assert seg == nil, (seg, nil)
                assert nil == seg, (nil, seg)

    def test_a_seg_whose_varsegs_are_bound_to_nothing_is_empty_too(self):
        """Emptiness is a property of the WALKED term, not of the segment
        list: a ``VarSeg`` bound to ``""`` walks away."""
        # nv
        trail = Trail()
        A = Var()
        ss = SegString([VarSeg(A)])
        assert unify(A, chars(""), trail)
        for nil in self.NIL_SPELLINGS:
            assert unify(ss, nil, Trail()), nil

    def test_a_nonempty_seg_is_unaffected(self):
        # nv
        for seg in (SegList([ConcreteSeg([char_atom("a")])]),
                    SegString(["ab"]), SegBytes([b"ab"])):
            for nil in self.NIL_SPELLINGS:
                assert not unify(seg, nil, Trail()), (seg, nil)
                assert not (seg == nil), (seg, nil)

    def test_the_varseg_pin_is_untouched(self):
        """The round-3 narrowing exists because rewriting ``""``/``b""`` at
        the top of the arms moved a same-type target off its own arm and
        changed what a ``VarSeg`` binds to.  An OPEN ``Seg*`` does not walk
        to nothing, so the new branch never sees it: ``[*A] = ""`` still
        binds ``A = ""`` (and the list form still binds ``[]``)."""
        # nv
        trail = Trail()
        A = Var()
        assert unify(SegList([VarSeg(A)]), chars(""), trail)
        assert deref(A) == chars("")
        assert not isinstance(deref(A), list)
        trail2 = Trail()
        B = Var()
        assert unify(SegList([VarSeg(B)]), [], trail2)
        assert deref(B) == []
        trail3 = Trail()
        C = Var()
        assert unify(SegBytes([VarSeg(C)]), b"", trail3)
        assert deref(C) == b""


class TestConsRuleRetirementLockstep:
    """P3-1 Task 5 (§1b): the C str~char-list cons rule is retired —
    ``do_unify``'s ``PyUnicode_Check``/``PyList_Check`` cross-type branches
    in ``_variables.c`` are deleted. SegString is the ONE place a str-shaped
    value still unifies element-wise against a list: it remains the
    char-LIST optimization (unifies with plain ``list`` / ``SegList``
    element-wise, both directions), but a BARE ``str`` — no SegString
    wrapper — must no longer unify against a char list, in either
    direction. These tests pin both halves side by side.
    """

    # ── still works: SegString vs list/SegList, both directions ──────────

    def test_segstring_still_unifies_with_list_ground(self):
        # nv — restates test_segstring_vs_char_list as an explicit
        # lockstep pin: SegString stays the char-list optimization.
        assert unify(SegString(["hi"]), [char_atom('h'), char_atom('i')], Trail())

    def test_segstring_still_unifies_with_list_containing_var(self):
        # nv — the list side may hold an unbound Var; SegString unify
        # still binds it element-wise (goes through the C list-vs-list
        # path after this task's fix, not the retired str~list path).
        trail = Trail()
        X = Var()
        assert unify(SegString(["hi"]), [char_atom('h'), X], trail)
        assert deref(X) == char_atom('i')

    def test_list_still_unifies_with_segstring_symmetric(self):
        # nv — list on the left, SegString on the right: do_unify's
        # __unify__-protocol probe tries SegString.__unify__(list, trail),
        # the symmetric call shape to test_segstring_vs_char_list.
        assert unify([char_atom('h'), char_atom('i')], SegString(["hi"]), Trail())

    def test_segstring_still_unifies_with_seglist_ground(self):
        # nv — a ground SegList is walked to a plain list; must still
        # match a SegString element-wise.
        from clausal.terms import ConcreteSeg
        sl = SegList([ConcreteSeg([char_atom('h'), char_atom('i')])])
        assert unify(SegString(["hi"]), sl, Trail())

    # ── a BARE str (no SegString) vs a char list ─────────────────────────

    def test_bare_str_unifies_with_its_char_list(self):
        # nv — THE FLIP (2026-09-06-atoms-as-cells-strings §6.2) reinstated
        # the str↔list arm P3-1 retired: a plain ``str`` IS the list of its
        # char atoms, so it unifies with one directly, not only through
        # SegString.  (The retirement was right while a str was an ATOM; it
        # is a STRING now.)
        assert unify(chars("hi"), [char_atom('h'), char_atom('i')], Trail())

    def test_char_list_unifies_with_a_bare_str(self):
        # nv — symmetric direction.
        assert unify([char_atom('h'), char_atom('i')], chars("hi"), Trail())

    def test_a_one_char_string_is_not_the_char(self):
        # nv — spec §6.2's row: ``"a"`` is the one-element LIST [a], not the
        # char atom, so the two do not unify.
        assert not unify(chars("a"), char_atom("a"), Trail())


class TestSegStringOccursCheck:
    """SegString __occurs_check__."""

    def test_var_in_varseg(self):
        # nv
        X = Var()
        ss = SegString(["abc", VarSeg(X)])
        assert ss.__occurs_check__(X)

    def test_var_not_in_segstring(self):
        # nv
        X, Y = Var(), Var()
        ss = SegString(["abc", VarSeg(Y)])
        assert not ss.__occurs_check__(X)


class TestSegStringGenerator:
    """_segstring_unify_gen multiple solutions."""

    def test_multiple_splits(self):
        """[*A, ',', *B] matches 'a,b,c' at multiple comma positions."""
        # nv
        trail = Trail()
        A, B = Var(), Var()
        ss = SegString([VarSeg(A), ",", VarSeg(B)])
        walked = ss.__walk__()
        solutions = []
        for _ in _segstring_unify_gen(walked, "a,b,c", trail):
            solutions.append((deref(A), deref(B)))
        assert len(solutions) == 2
        assert (chars("a"), chars("b,c")) in solutions
        assert (chars("a,b"), chars("c")) in solutions

    def test_no_match(self):
        # nv
        trail = Trail()
        A, B = Var(), Var()
        ss = SegString([VarSeg(A), "x", VarSeg(B)])
        walked = ss.__walk__()
        solutions = list(_segstring_unify_gen(walked, "abc", trail))
        assert len(solutions) == 0

    def test_single_varseg(self):
        # nv
        trail = Trail()
        X = Var()
        ss = SegString([VarSeg(X)])
        walked = ss.__walk__()
        solutions = []
        for _ in _segstring_unify_gen(walked, "hello", trail):
            solutions.append(deref(X))
        assert solutions == [chars("hello")]


# ── String-preserving SegList matching ──────────────────────────────────────


class TestSegListStringPreserving:
    """SegList VarSegs bind to substrings when matching strings."""

    def test_single_star_binds_substring(self):
        # nv
        trail = Trail()
        T = Var()
        sl = SegList([ConcreteSeg([char_atom("h")]), VarSeg(T)])
        assert unify(sl, chars("hello"), trail)
        assert deref(T) == chars("ello")
        assert is_chars(deref(T))

    def test_multi_star_binds_substrings(self):
        # nv
        trail = Trail()
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg([char_atom(",")]), VarSeg(B)])
        assert unify(sl, chars("hello,world"), trail)
        assert deref(A) == chars("hello")
        assert deref(B) == chars("world")

    def test_star_binds_empty_substring(self):
        # nv
        trail = Trail()
        A = Var()
        sl = SegList([VarSeg(A), ConcreteSeg([char_atom("x")])])
        assert unify(sl, chars("x"), trail)
        assert deref(A) == chars("")

    def test_walk_handles_string_bound_varseg(self):
        """SegList.__walk__ converts string-bound VarSegs to char lists,
        then promotes the all-1-char-str result to a plain ``str`` under
        the Phase 2 Task 13 Liskov rule (F018 fix)."""
        # nv
        trail = Trail()
        A = Var()
        unify(A, "hello", trail)
        sl = SegList([VarSeg(A)])
        walked = sl.__walk__()
        # F018 fix: all-1-char-str walked list promotes to str.
        assert is_chars(walked)
        assert walked == chars("hello")

    def test_seglist_still_works_with_lists(self):
        """SegList against list still returns list slices."""
        # nv
        trail = Trail()
        T = Var()
        sl = SegList([ConcreteSeg([1]), VarSeg(T)])
        assert unify(sl, [1, 2, 3], trail)
        assert deref(T) == [2, 3]
        assert isinstance(deref(T), list)

    def test_multi_star_string_generator(self):
        """_seglist_unify_gen with string target yields substring bindings."""
        # nv
        trail = Trail()
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg([char_atom("l")]), VarSeg(B)])
        walked = sl.__walk__()
        solutions = []
        for _ in _seglist_unify_gen(walked, "hello", trail):
            solutions.append((deref(A), deref(B)))
        assert len(solutions) == 2
        assert (chars("he"), chars("lo")) in solutions
        assert (chars("hel"), chars("o")) in solutions


# ── Body multi-star on strings (compiler path) ─────────────────────────────


class TestBodyMultiStarString:
    """_body_multi_star_unify preserves string type."""

    def test_star_vars_bind_to_substrings(self):
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [char_atom(",")]), ("star", B)]
        solutions = []
        for _ in _body_multi_star_unify(chars("hello,world"), segments, trail):
            solutions.append((deref(A), deref(B)))
        assert (chars("hello"), chars("world")) in solutions

    def test_fixed_elements_match_chars(self):
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [char_atom("l")]), ("star", B)]
        solutions = []
        for _ in _body_multi_star_unify(chars("hello"), segments, trail):
            solutions.append((deref(A), deref(B)))
        assert len(solutions) == 2
        assert (chars("he"), chars("lo")) in solutions
        assert (chars("hel"), chars("o")) in solutions

    def test_empty_string_target(self):
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A = Var()
        segments = [("star", A)]
        solutions = []
        for _ in _body_multi_star_unify(chars(""), segments, trail):
            solutions.append(deref(A))
        assert solutions == [chars("")]

    def test_no_match(self):
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [char_atom("x")]), ("star", B)]
        solutions = list(_body_multi_star_unify(chars("hello"), segments, trail))
        assert len(solutions) == 0


# ── _build_star_list / _build_multi_star_list string support ────────────────


class TestBuildStarListString:
    """_build_star_list returns strings when inputs are string-compatible."""

    def test_star_str_returns_str(self):
        from clausal.logic.runtime.body_star_unify import _build_star_list
        trail = Trail()
        X = Var()
        unify(X, "ello", trail)
        result = _build_star_list([char_atom("h")], X, [])
        assert result == chars("hello")
        assert is_chars(result)

    def test_star_str_with_after(self):
        from clausal.logic.runtime.body_star_unify import _build_star_list
        trail = Trail()
        X = Var()
        unify(X, "ell", trail)
        result = _build_star_list([char_atom("h")], X, [char_atom("o")])
        assert result == chars("hello")
        assert is_chars(result)

    def test_star_list_returns_list(self):
        """Non-string star still returns a list."""
        from clausal.logic.runtime.body_star_unify import _build_star_list
        trail = Trail()
        X = Var()
        unify(X, [2, 3], trail)
        result = _build_star_list([1], X, [4])
        assert result == [1, 2, 3, 4]
        assert isinstance(result, list)

    def test_star_ground_segstring_mixed(self):
        """Ground SegString with mixed before/after returns a list."""
        from clausal.logic.runtime.body_star_unify import _build_star_list
        trail = Trail()
        X = Var()
        ss = SegString(["ello"])
        unify(X, ss, trail)
        # before has int, not single-char str → mixed types
        result = _build_star_list([1], X, [2])
        assert result == [1, char_atom('e'), char_atom('l'), char_atom('l'), char_atom('o'), 2]
        assert isinstance(result, list)

    def test_star_nonground_segstring_mixed(self):
        """Non-ground SegString with mixed before/after returns a SegList."""
        from clausal.logic.runtime.body_star_unify import _build_star_list
        Y = Var()
        ss = SegString([VarSeg(Y), "orld"])
        # before has int → mixed types, so can't return SegString
        result = _build_star_list([1], ss, [2])
        assert isinstance(result, SegList)

    def test_star_nonground_segstring_all_str(self):
        """Non-ground SegString with all-str before/after returns a SegString."""
        from clausal.logic.runtime.body_star_unify import _build_star_list
        Y = Var()
        ss = SegString([VarSeg(Y), "orld"])
        result = _build_star_list([char_atom("h")], ss, [char_atom("!")])
        assert isinstance(result, SegString)


class TestBuildMultiStarListString:
    """_build_multi_star_list returns strings when all parts are chars."""

    def test_all_str_returns_str(self):
        from clausal.logic.runtime.body_star_unify import _build_multi_star_list
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
        from clausal.logic.runtime.body_star_unify import _build_multi_star_list
        trail = Trail()
        A, B = Var(), Var()
        unify(A, "he", trail)
        unify(B, "lo", trail)
        result = _build_multi_star_list([
            ("star", A), ("fixed", [char_atom("l")]), ("star", B),
        ])
        # All chars are single-char strings → str result
        assert result == chars("hello")
        assert is_chars(result)


# ── Integration: clause-level string pattern matching ───────────────────────


class TestClauseLevelStringPatterns:
    """End-to-end tests using existing clausal modules with string patterns."""

    def test_head_tail_string(self):
        """head_tail from list_edge_cases works on strings (Phase 5b)."""
        # nv
        import os
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        fixture = os.path.join(
            os.path.dirname(__file__), "clausal_modules", "list_edge_cases.clausal"
        )
        mod = _load_module("lec_segstr", fixture).__dict__["$module"]
        H, T = Var(), Var()
        results = []
        for _ in call("head_tail", chars("hello"), H, T, module=mod):
            results.append((deref(H), deref(T)))
        # THE FLIP (spec §6.2): the head of a string is a CHAR ATOM, the
        # tail a str slice (R-S2).
        assert results == [(char_atom("h"), chars("ello"))]

    def test_body_multi_star_string_direct(self):
        """_body_multi_star_unify with string target — star vars are substrings."""
        from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
        trail = Trail()
        A, B = Var(), Var()
        segments = [("star", A), ("fixed", [char_atom(",")]), ("star", B)]
        found = False
        for _ in _body_multi_star_unify(chars("hello,world"), segments, trail):
            if deref(A) == chars("hello") and deref(B) == chars("world"):
                found = True
                break
        assert found
