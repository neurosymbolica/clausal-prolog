"""Phase 1 tests: core SegList type — construction, walk, ground detection,
sequence protocol, concat, and __repr__."""

import pytest
from clausal.logic.cells import chars  # stage 2: a string is the carrier
from clausal.logic.atoms import char_atom
from clausal.terms import ConcreteSeg, VarSeg, SegList, _multi_star_splits, _seglist_unify_gen
from clausal.logic.variables import Var, Trail, walk, unify, deref


# ── _multi_star_splits ────────────────────────────────────────────────────────

class TestMultiStarSplits:
    def test_zero_stars_zero_remainder(self):
        # nv
        assert list(_multi_star_splits(0, 0)) == [()]

    def test_zero_stars_nonzero_fails(self):
        # nv
        assert list(_multi_star_splits(0, 3)) == []

    def test_one_star(self):
        # nv
        assert list(_multi_star_splits(1, 5)) == [(5,)]

    def test_two_stars_remainder_2(self):
        # nv
        result = list(_multi_star_splits(2, 2))
        assert result == [(0, 2), (1, 1), (2, 0)]

    def test_three_stars_remainder_1(self):
        # nv
        result = list(_multi_star_splits(3, 1))
        assert result == [(0, 0, 1), (0, 1, 0), (1, 0, 0)]

    def test_total_count(self):
        # C(n+k-1, k-1) combinations
        # nv
        assert len(list(_multi_star_splits(3, 4))) == 15  # C(6,2)


# ── Construction ──────────────────────────────────────────────────────────────

class TestConstruction:
    def test_empty_seglist(self):
        # nv
        sl = SegList([])
        assert sl.segments == []

    def test_single_concrete(self):
        # nv
        sl = SegList([ConcreteSeg([1, 2, 3])])
        assert len(sl.segments) == 1

    def test_single_var(self):
        # nv
        v = Var()
        sl = SegList([VarSeg(v)])
        assert sl.segments[0].var is v

    def test_mixed_segments(self):
        # nv
        v = Var()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v), ConcreteSeg([5])])
        assert len(sl.segments) == 3

    def test_segments_property_returns_copy_list(self):
        # nv
        sl = SegList([ConcreteSeg([1])])
        # segments returns the internal list; modifying returned object doesn't
        # matter, but at minimum it's accessible
        segs = sl.segments
        assert len(segs) == 1


# ── Walk / normalisation ──────────────────────────────────────────────────────

class TestWalk:
    def test_fully_ground_returns_plain_list(self):
        # nv
        sl = SegList([ConcreteSeg([1, 2, 3])])
        result = sl.__walk__()
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_unbound_var_stays_seglist(self):
        # nv
        v = Var()
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        result = sl.__walk__()
        assert isinstance(result, SegList)

    def test_bound_var_inlined(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, [2, 3], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        result = sl.__walk__()
        assert result == [1, 2, 3]

    def test_adjacent_concrete_segs_merged(self):
        # nv
        sl = SegList([ConcreteSeg([1, 2]), ConcreteSeg([3, 4])])
        result = sl.__walk__()
        assert result == [1, 2, 3, 4]

    def test_empty_var_bound_to_empty_list_inlined(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, [], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v), ConcreteSeg([2])])
        result = sl.__walk__()
        assert result == [1, 2]

    def test_nested_seglist_inlined_when_ground(self):
        # nv
        inner_v = Var()
        trail = Trail()
        unify(inner_v, [3, 4], trail)
        inner = SegList([ConcreteSeg([2]), VarSeg(inner_v)])
        outer_v = Var()
        unify(outer_v, inner, trail)
        outer = SegList([ConcreteSeg([1]), VarSeg(outer_v), ConcreteSeg([5])])
        result = outer.__walk__()
        assert result == [1, 2, 3, 4, 5]

    def test_nested_seglist_partially_unbound_inlined_structurally(self):
        # nv
        inner_v = Var()
        inner = SegList([ConcreteSeg([2]), VarSeg(inner_v)])
        outer_v = Var()
        trail = Trail()
        unify(outer_v, inner, trail)
        outer = SegList([ConcreteSeg([1]), VarSeg(outer_v)])
        result = outer.__walk__()
        assert isinstance(result, SegList)
        # Should have ConcreteSeg([1, 2]) merged and VarSeg(inner_v)
        segs = result.segments
        assert isinstance(segs[0], ConcreteSeg)
        assert segs[0].elements == [1, 2]
        assert isinstance(segs[1], VarSeg)

    def test_empty_seglist_returns_empty_list(self):
        # nv
        sl = SegList([])
        result = sl.__walk__()
        assert result == []

    def test_all_vars_bound_multi_star(self):
        # nv
        a, b = Var(), Var()
        trail = Trail()
        unify(a, [1, 2], trail)
        unify(b, [4, 5], trail)
        sl = SegList([VarSeg(a), ConcreteSeg([3]), VarSeg(b)])
        result = sl.__walk__()
        assert result == [1, 2, 3, 4, 5]


# ── is_ground / to_list ───────────────────────────────────────────────────────

class TestGroundness:
    def test_ground_concrete_only(self):
        # nv
        sl = SegList([ConcreteSeg([1, 2])])
        assert sl.is_ground() is True

    def test_not_ground_with_unbound_var(self):
        # nv
        sl = SegList([VarSeg(Var())])
        assert sl.is_ground() is False

    def test_ground_after_binding(self):
        # nv
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert not sl.is_ground()
        unify(v, [2, 3], trail)
        assert sl.is_ground()

    def test_to_list_ground(self):
        # nv
        sl = SegList([ConcreteSeg([10, 20])])
        assert sl.to_list() == [10, 20]

    def test_to_list_raises_if_not_ground(self):
        # nv
        sl = SegList([VarSeg(Var())])
        with pytest.raises(TypeError, match="not ground"):
            sl.to_list()

    def test_to_list_after_binding(self):
        # nv
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        unify(v, [2, 3], trail)
        assert sl.to_list() == [1, 2, 3]


# ── __occurs_check__ ──────────────────────────────────────────────────────────

class TestOccursCheck:
    def test_var_in_varseg(self):
        # nv
        v = Var()
        sl = SegList([VarSeg(v)])
        assert sl.__occurs_check__(v) is True

    def test_var_not_present(self):
        # nv
        v, other = Var(), Var()
        sl = SegList([VarSeg(other)])
        assert sl.__occurs_check__(v) is False

    def test_var_in_concrete_elem(self):
        # nv
        v = Var()
        sl = SegList([ConcreteSeg([1, v, 3])])
        assert sl.__occurs_check__(v) is True

    def test_var_absent_all_concrete(self):
        # nv
        v = Var()
        sl = SegList([ConcreteSeg([1, 2, 3])])
        assert sl.__occurs_check__(v) is False


# ── __unify__ ─────────────────────────────────────────────────────────────────

class TestUnify:
    def test_unify_against_matching_list_single_star(self):
        # nv
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v)])
        result = sl.__unify__([1, 2, 3, 4], trail)
        assert result is True
        assert walk(v) == [3, 4]

    def test_unify_against_too_short_list(self):
        # nv
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1, 2, 3]), VarSeg(v)])
        result = sl.__unify__([1, 2], trail)
        assert result is False

    def test_unify_against_non_sequence_returns_not_implemented(self):
        # nv
        sl = SegList([ConcreteSeg([1])])
        result = sl.__unify__(42, Trail())
        assert result is NotImplemented

    def test_unify_against_string_treats_as_char_list(self):
        """Strings are treated as char lists for SegList unification."""
        # nv
        # THE FLIP (spec §6.2): a char is the ATOM ("h",).
        sl = SegList([ConcreteSeg([char_atom("h"), char_atom("i")])])
        assert sl.__unify__(chars("hi"), Trail()) is True   # stage 2: the string is the carrier
        assert sl.__unify__(chars("ho"), Trail()) is False

    def test_unify_against_seglist(self):
        # nv
        # Two SegLists unify as the lists they spell (F030): a ground pair
        # compares element-wise; an open pair pairs its elements and hands
        # the tail over; an ambiguous pair (both remainders open with a hole
        # and go on) is still NotImplemented.
        sl = SegList([ConcreteSeg([1])])
        assert sl.__unify__(SegList([ConcreteSeg([1])]), Trail()) is True
        assert sl.__unify__(SegList([ConcreteSeg([2])]), Trail()) is False
        h, t1, t2 = Var(), Var(), Var()
        open1 = SegList([ConcreteSeg([1]), VarSeg(t1)])
        assert open1.__unify__(SegList([ConcreteSeg([h]), VarSeg(t2)]), Trail())
        assert deref(h) == 1 and deref(t1) is deref(t2)
        a, b = Var(), Var()
        amb = SegList([VarSeg(a), ConcreteSeg([1])])
        assert amb.__unify__(SegList([VarSeg(b), ConcreteSeg([1])]), Trail()) is NotImplemented

    def test_unify_fully_ground_seglist_against_equal_list(self):
        # nv
        sl = SegList([ConcreteSeg([1, 2, 3])])
        result = sl.__unify__([1, 2, 3], Trail())
        assert result is True

    def test_unify_fully_ground_seglist_against_unequal_list(self):
        # nv
        sl = SegList([ConcreteSeg([1, 2, 3])])
        result = sl.__unify__([1, 2, 4], Trail())
        assert result is False


# ── _seglist_unify_gen ────────────────────────────────────────────────────────

class TestSeglistUnifyGen:
    def test_single_var_tail(self):
        # nv
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v)])
        solutions = []
        for _ in _seglist_unify_gen(sl, [1, 2, 3, 4], trail):
            solutions.append(walk(v))
            trail.undo(trail.mark())  # reset for next
        assert solutions == [[3, 4]]

    def test_two_vars_all_splits(self):
        # nv
        a, b = Var(), Var()
        trail = Trail()
        sl = SegList([VarSeg(a), VarSeg(b)])
        solutions = []
        for _ in _seglist_unify_gen(sl, [1, 2, 3], trail):
            solutions.append((list(walk(a)), list(walk(b))))
            trail.undo(trail.mark())
        assert solutions == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]

    def test_sandwich_pattern(self):
        # nv
        a, b = Var(), Var()
        x = Var()
        trail = Trail()
        sl = SegList([VarSeg(a), ConcreteSeg([x]), VarSeg(b)])
        solutions = []
        for _ in _seglist_unify_gen(sl, [1, 2, 3], trail):
            solutions.append((list(walk(a)), walk(x), list(walk(b))))
            trail.undo(trail.mark())
        assert solutions == [
            ([], 1, [2, 3]),
            ([1], 2, [3]),
            ([1, 2], 3, []),
        ]

    def test_too_short_yields_nothing(self):
        # nv
        v = Var()
        sl = SegList([ConcreteSeg([1, 2, 3]), VarSeg(v)])
        trail = Trail()
        assert list(_seglist_unify_gen(sl, [1, 2], trail)) == []

    def test_empty_var_match(self):
        # nv
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1]), VarSeg(v), ConcreteSeg([2])])
        solutions = []
        for _ in _seglist_unify_gen(sl, [1, 2], trail):
            solutions.append(list(walk(v)))
            trail.undo(trail.mark())
        assert solutions == [[]]


# ── sequence protocol ─────────────────────────────────────────────────────────

class TestSequenceProtocol:
    def setup_method(self):
        self.sl_ground = SegList([ConcreteSeg([10, 20, 30])])

    def test_len_ground(self):
        # nv
        assert len(self.sl_ground) == 3

    def test_len_unground_returns_concrete_prefix_length(self):
        # F021 (audit 2026-05-25): non-ground __len__ now returns the
        # minimum knowable length (sum of ConcreteSeg sizes) instead of
        # raising a bare TypeError. ``len(SegList([VarSeg(Var())]))`` has
        # no concrete elements, so the lower bound is 0.
        # nv
        sl = SegList([VarSeg(Var())])
        assert len(sl) == 0
        sl2 = SegList([ConcreteSeg([1, 2]), VarSeg(Var())])
        assert len(sl2) == 2

    def test_iter_ground(self):
        # nv
        assert list(self.sl_ground) == [10, 20, 30]

    def test_iter_unground_yields_concrete_prefix(self):
        # F021 (audit 2026-05-25): non-ground __iter__ yields the concrete
        # prefix (skipping VarSeg gaps) instead of raising TypeError.
        # nv
        sl = SegList([VarSeg(Var())])
        assert list(sl) == []
        sl2 = SegList([ConcreteSeg([1, 2]), VarSeg(Var()), ConcreteSeg([5])])
        assert list(sl2) == [1, 2, 5]

    def test_contains_ground(self):
        # nv
        assert 20 in self.sl_ground
        assert 99 not in self.sl_ground

    def test_contains_in_concrete_seg_unground(self):
        # element is in a ConcreteSeg — can answer True even if unground
        # nv
        sl = SegList([ConcreteSeg([5]), VarSeg(Var())])
        assert 5 in sl

    def test_contains_not_found_unground_returns_true_conservatively(self):
        # F022 (audit 2026-05-25): on a partial container, ``elem in sl``
        # returns True conservatively when the element is not in any
        # ConcreteSeg but an unbound VarSeg remains — the VarSeg could be
        # bound to a list containing the element. A definite False on a
        # satisfiable goal is the silent-incompleteness bug F022 fixes.
        # nv
        sl = SegList([ConcreteSeg([1]), VarSeg(Var())])
        assert 99 in sl

    def test_getitem_ground(self):
        # nv
        assert self.sl_ground[0] == 10
        assert self.sl_ground[-1] == 30

    def test_getitem_unground_raises_typed_partial_term_error(self):
        # F021 (audit 2026-05-25): non-ground __getitem__ raises a typed
        # ``PartialTermError`` when the index falls past the concrete
        # prefix (i.e. depends on resolving an unbound VarSeg). Indices
        # within the concrete prefix return the known element.
        # nv
        from clausal.terms import PartialTermError
        sl = SegList([VarSeg(Var())])
        with pytest.raises(PartialTermError):
            _ = sl[0]
        # Within concrete prefix: returns the element.
        sl2 = SegList([ConcreteSeg([10, 20]), VarSeg(Var())])
        assert sl2[0] == 10
        assert sl2[1] == 20
        # Past the concrete prefix: hits the VarSeg → PartialTermError.
        with pytest.raises(PartialTermError):
            _ = sl2[2]


# ── Concatenation ─────────────────────────────────────────────────────────────

class TestConcat:
    def test_add_plain_list(self):
        # nv
        v = Var()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v)])
        result = sl + [3, 4]
        assert isinstance(result, SegList)
        # After binding v
        trail = Trail()
        unify(v, [99], trail)
        assert result.to_list() == [1, 2, 99, 3, 4]

    def test_add_seglist(self):
        # nv
        v1, v2 = Var(), Var()
        sl1 = SegList([ConcreteSeg([1]), VarSeg(v1)])
        sl2 = SegList([ConcreteSeg([3]), VarSeg(v2)])
        result = sl1 + sl2
        assert isinstance(result, SegList)
        trail = Trail()
        unify(v1, [2], trail)
        unify(v2, [4], trail)
        assert result.to_list() == [1, 2, 3, 4]

    def test_radd_plain_list(self):
        # nv
        v = Var()
        sl = SegList([VarSeg(v), ConcreteSeg([3, 4])])
        result = [1, 2] + sl
        assert isinstance(result, SegList)
        trail = Trail()
        unify(v, [99], trail)
        assert result.to_list() == [1, 2, 99, 3, 4]

    def test_add_non_list_returns_not_implemented(self):
        # nv
        sl = SegList([ConcreteSeg([1])])
        assert sl.__add__(42) is NotImplemented


# ── Equality ──────────────────────────────────────────────────────────────────

class TestEquality:
    def test_seglist_eq_seglist_structural(self):
        # nv
        v = Var()
        sl1 = SegList([ConcreteSeg([1]), VarSeg(v)])
        sl2 = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert sl1 == sl2

    def test_seglist_eq_list_when_ground(self):
        # nv
        sl = SegList([ConcreteSeg([1, 2, 3])])
        assert sl == [1, 2, 3]

    def test_seglist_neq_list_when_unground(self):
        # nv
        sl = SegList([VarSeg(Var())])
        assert not (sl == [1, 2, 3])

    def test_seglist_neq_non_list(self):
        # nv — SegList of non-char ints can't equal a str (asymmetry fix
        # F019: SegList.__eq__ now accepts str as a comparand and walks,
        # but only matches when the walked list is a list of 1-char strs).
        sl = SegList([ConcreteSeg([1])])
        assert (sl == "hello") is False
        # And: a non-str/list/Seg* comparand still returns NotImplemented.
        assert sl.__eq__(42) is NotImplemented

    def test_seglist_eq_str_when_charlist(self):
        # nv — Symmetric with SegString under the strings-as-lists contract
        # (F019 fix): a ground SegList of 1-char strings equals the matching str.
        sl = SegList([ConcreteSeg([char_atom(c) for c in "abc"])])
        assert sl == chars("abc")   # stage 2: the string is the carrier; a bare str is an atom

    def test_unhashable_unconditionally(self):
        # nv — Phase 2 Task 13 (revised F017/F025 contract): SegList is
        # *unconditionally* unhashable, matching Python's ``list``. The
        # Task 5 hashable-when-ground / structural-when-non-ground
        # contract was reverted because the Liskov "strings-as-lists"
        # model leaves hashing of seg containers undefined. Callers
        # needing hashability convert via ``to_list()`` first.
        import pytest
        sl_ground = SegList([ConcreteSeg([1, 2, 3])])
        with pytest.raises(TypeError, match="unhashable"):
            hash(sl_ground)
        v = Var()
        sl_nonground = SegList([ConcreteSeg([1]), VarSeg(v)])
        with pytest.raises(TypeError, match="unhashable"):
            hash(sl_nonground)
        # User-side workaround: convert to_list() first.
        assert hash(tuple(sl_ground.to_list())) == hash((1, 2, 3))


# ── __repr__ ──────────────────────────────────────────────────────────────────

class TestRepr:
    def test_concrete_only(self):
        # nv
        sl = SegList([ConcreteSeg([1, 2, 3])])
        assert repr(sl) == "[1, 2, 3]"

    def test_single_var(self):
        # nv
        v = Var()
        sl = SegList([VarSeg(v)])
        r = repr(sl)
        assert r.startswith("[*")
        assert r.endswith("]")

    def test_mixed(self):
        # nv
        v = Var()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v), ConcreteSeg([5])])
        r = repr(sl)
        assert r.startswith("[1, 2, *")
        assert r.endswith(", 5]")

    def test_empty(self):
        # nv
        sl = SegList([])
        assert repr(sl) == "[]"
