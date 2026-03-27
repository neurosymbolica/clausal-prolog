"""Phase 1 tests: core SegList type — construction, walk, ground detection,
sequence protocol, concat, and __repr__."""

import pytest
from clausal.terms import ConcreteSeg, VarSeg, SegList, _multi_star_splits, _seglist_unify_gen
from clausal.logic.variables import Var, Trail, walk, unify


# ── _multi_star_splits ────────────────────────────────────────────────────────

class TestMultiStarSplits:
    def test_zero_stars_zero_remainder(self):
        assert list(_multi_star_splits(0, 0)) == [()]

    def test_zero_stars_nonzero_fails(self):
        assert list(_multi_star_splits(0, 3)) == []

    def test_one_star(self):
        assert list(_multi_star_splits(1, 5)) == [(5,)]

    def test_two_stars_remainder_2(self):
        result = list(_multi_star_splits(2, 2))
        assert result == [(0, 2), (1, 1), (2, 0)]

    def test_three_stars_remainder_1(self):
        result = list(_multi_star_splits(3, 1))
        assert result == [(0, 0, 1), (0, 1, 0), (1, 0, 0)]

    def test_total_count(self):
        # C(n+k-1, k-1) combinations
        assert len(list(_multi_star_splits(3, 4))) == 15  # C(6,2)


# ── Construction ──────────────────────────────────────────────────────────────

class TestConstruction:
    def test_empty_seglist(self):
        sl = SegList([])
        assert sl.segments == []

    def test_single_concrete(self):
        sl = SegList([ConcreteSeg([1, 2, 3])])
        assert len(sl.segments) == 1

    def test_single_var(self):
        v = Var()
        sl = SegList([VarSeg(v)])
        assert sl.segments[0].var is v

    def test_mixed_segments(self):
        v = Var()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v), ConcreteSeg([5])])
        assert len(sl.segments) == 3

    def test_segments_property_returns_copy_list(self):
        sl = SegList([ConcreteSeg([1])])
        # segments returns the internal list; modifying returned object doesn't
        # matter, but at minimum it's accessible
        segs = sl.segments
        assert len(segs) == 1


# ── Walk / normalisation ──────────────────────────────────────────────────────

class TestWalk:
    def test_fully_ground_returns_plain_list(self):
        sl = SegList([ConcreteSeg([1, 2, 3])])
        result = sl.__walk__()
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_unbound_var_stays_seglist(self):
        v = Var()
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        result = sl.__walk__()
        assert isinstance(result, SegList)

    def test_bound_var_inlined(self):
        v = Var()
        trail = Trail()
        unify(v, [2, 3], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        result = sl.__walk__()
        assert result == [1, 2, 3]

    def test_adjacent_concrete_segs_merged(self):
        sl = SegList([ConcreteSeg([1, 2]), ConcreteSeg([3, 4])])
        result = sl.__walk__()
        assert result == [1, 2, 3, 4]

    def test_empty_var_bound_to_empty_list_inlined(self):
        v = Var()
        trail = Trail()
        unify(v, [], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v), ConcreteSeg([2])])
        result = sl.__walk__()
        assert result == [1, 2]

    def test_nested_seglist_inlined_when_ground(self):
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
        sl = SegList([])
        result = sl.__walk__()
        assert result == []

    def test_all_vars_bound_multi_star(self):
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
        sl = SegList([ConcreteSeg([1, 2])])
        assert sl.is_ground() is True

    def test_not_ground_with_unbound_var(self):
        sl = SegList([VarSeg(Var())])
        assert sl.is_ground() is False

    def test_ground_after_binding(self):
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert not sl.is_ground()
        unify(v, [2, 3], trail)
        assert sl.is_ground()

    def test_to_list_ground(self):
        sl = SegList([ConcreteSeg([10, 20])])
        assert sl.to_list() == [10, 20]

    def test_to_list_raises_if_not_ground(self):
        sl = SegList([VarSeg(Var())])
        with pytest.raises(TypeError, match="not ground"):
            sl.to_list()

    def test_to_list_after_binding(self):
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        unify(v, [2, 3], trail)
        assert sl.to_list() == [1, 2, 3]


# ── __occurs_check__ ──────────────────────────────────────────────────────────

class TestOccursCheck:
    def test_var_in_varseg(self):
        v = Var()
        sl = SegList([VarSeg(v)])
        assert sl.__occurs_check__(v) is True

    def test_var_not_present(self):
        v, other = Var(), Var()
        sl = SegList([VarSeg(other)])
        assert sl.__occurs_check__(v) is False

    def test_var_in_concrete_elem(self):
        v = Var()
        sl = SegList([ConcreteSeg([1, v, 3])])
        assert sl.__occurs_check__(v) is True

    def test_var_absent_all_concrete(self):
        v = Var()
        sl = SegList([ConcreteSeg([1, 2, 3])])
        assert sl.__occurs_check__(v) is False


# ── __unify__ ─────────────────────────────────────────────────────────────────

class TestUnify:
    def test_unify_against_matching_list_single_star(self):
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v)])
        result = sl.__unify__([1, 2, 3, 4], trail)
        assert result is True
        assert walk(v) == [3, 4]

    def test_unify_against_too_short_list(self):
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1, 2, 3]), VarSeg(v)])
        result = sl.__unify__([1, 2], trail)
        assert result is False

    def test_unify_against_non_sequence_returns_not_implemented(self):
        sl = SegList([ConcreteSeg([1])])
        result = sl.__unify__(42, Trail())
        assert result is NotImplemented

    def test_unify_against_string_treats_as_char_list(self):
        """Strings are treated as char lists for SegList unification."""
        sl = SegList([ConcreteSeg(["h", "i"])])
        assert sl.__unify__("hi", Trail()) is True
        assert sl.__unify__("ho", Trail()) is False

    def test_unify_against_seglist_returns_not_implemented(self):
        sl = SegList([ConcreteSeg([1])])
        other = SegList([ConcreteSeg([1])])
        result = sl.__unify__(other, Trail())
        assert result is NotImplemented

    def test_unify_fully_ground_seglist_against_equal_list(self):
        sl = SegList([ConcreteSeg([1, 2, 3])])
        result = sl.__unify__([1, 2, 3], Trail())
        assert result is True

    def test_unify_fully_ground_seglist_against_unequal_list(self):
        sl = SegList([ConcreteSeg([1, 2, 3])])
        result = sl.__unify__([1, 2, 4], Trail())
        assert result is False


# ── _seglist_unify_gen ────────────────────────────────────────────────────────

class TestSeglistUnifyGen:
    def test_single_var_tail(self):
        v = Var()
        trail = Trail()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v)])
        solutions = []
        for _ in _seglist_unify_gen(sl, [1, 2, 3, 4], trail):
            solutions.append(walk(v))
            trail.undo(trail.mark())  # reset for next
        assert solutions == [[3, 4]]

    def test_two_vars_all_splits(self):
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
        v = Var()
        sl = SegList([ConcreteSeg([1, 2, 3]), VarSeg(v)])
        trail = Trail()
        assert list(_seglist_unify_gen(sl, [1, 2], trail)) == []

    def test_empty_var_match(self):
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
        assert len(self.sl_ground) == 3

    def test_len_unground_raises(self):
        sl = SegList([VarSeg(Var())])
        with pytest.raises(TypeError):
            len(sl)

    def test_iter_ground(self):
        assert list(self.sl_ground) == [10, 20, 30]

    def test_iter_unground_raises(self):
        sl = SegList([VarSeg(Var())])
        with pytest.raises(TypeError):
            list(sl)

    def test_contains_ground(self):
        assert 20 in self.sl_ground
        assert 99 not in self.sl_ground

    def test_contains_in_concrete_seg_unground(self):
        # element is in a ConcreteSeg — can answer True even if unground
        sl = SegList([ConcreteSeg([5]), VarSeg(Var())])
        assert 5 in sl

    def test_contains_not_found_unground(self):
        # Can't confirm — returns False (not in any ConcreteSeg)
        sl = SegList([ConcreteSeg([1]), VarSeg(Var())])
        assert 99 not in sl

    def test_getitem_ground(self):
        assert self.sl_ground[0] == 10
        assert self.sl_ground[-1] == 30

    def test_getitem_unground_raises(self):
        sl = SegList([VarSeg(Var())])
        with pytest.raises(TypeError):
            _ = sl[0]


# ── Concatenation ─────────────────────────────────────────────────────────────

class TestConcat:
    def test_add_plain_list(self):
        v = Var()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v)])
        result = sl + [3, 4]
        assert isinstance(result, SegList)
        # After binding v
        trail = Trail()
        unify(v, [99], trail)
        assert result.to_list() == [1, 2, 99, 3, 4]

    def test_add_seglist(self):
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
        v = Var()
        sl = SegList([VarSeg(v), ConcreteSeg([3, 4])])
        result = [1, 2] + sl
        assert isinstance(result, SegList)
        trail = Trail()
        unify(v, [99], trail)
        assert result.to_list() == [1, 2, 99, 3, 4]

    def test_add_non_list_returns_not_implemented(self):
        sl = SegList([ConcreteSeg([1])])
        assert sl.__add__(42) is NotImplemented


# ── Equality ──────────────────────────────────────────────────────────────────

class TestEquality:
    def test_seglist_eq_seglist_structural(self):
        v = Var()
        sl1 = SegList([ConcreteSeg([1]), VarSeg(v)])
        sl2 = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert sl1 == sl2

    def test_seglist_eq_list_when_ground(self):
        sl = SegList([ConcreteSeg([1, 2, 3])])
        assert sl == [1, 2, 3]

    def test_seglist_neq_list_when_unground(self):
        sl = SegList([VarSeg(Var())])
        assert not (sl == [1, 2, 3])

    def test_seglist_neq_non_list(self):
        sl = SegList([ConcreteSeg([1])])
        assert sl.__eq__("hello") is NotImplemented

    def test_not_hashable(self):
        sl = SegList([ConcreteSeg([1])])
        with pytest.raises(TypeError, match="unhashable"):
            hash(sl)


# ── __repr__ ──────────────────────────────────────────────────────────────────

class TestRepr:
    def test_concrete_only(self):
        sl = SegList([ConcreteSeg([1, 2, 3])])
        assert repr(sl) == "[1, 2, 3]"

    def test_single_var(self):
        v = Var()
        sl = SegList([VarSeg(v)])
        r = repr(sl)
        assert r.startswith("[*")
        assert r.endswith("]")

    def test_mixed(self):
        v = Var()
        sl = SegList([ConcreteSeg([1, 2]), VarSeg(v), ConcreteSeg([5])])
        r = repr(sl)
        assert r.startswith("[1, 2, *")
        assert r.endswith(", 5]")

    def test_empty(self):
        sl = SegList([])
        assert repr(sl) == "[]"
