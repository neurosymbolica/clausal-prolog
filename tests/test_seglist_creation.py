"""Phase 4 tests: SegList *creation* — compiler produces SegLists when a star
var is unbound instead of failing or raising.

Sub-steps tested:
  4a. _head_list_unify_output with unbound star → SegList
  4b. _body_star_unify with unbound target → SegList (via 4a)
  4c. _body_multi_star_unify with unbound target → SegList
  4d. _build_star_list with unbound star → SegList
  4e. multi-star body expression builds SegList via _build_multi_star_list
"""

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.compiler import (
    _body_multi_star_unify,
    _body_star_unify,
    _build_multi_star_list,
    _build_star_list,
    _head_list_unify_output,
)
from clausal.logic.database import Module
from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, deref, unify, walk
from clausal.terms import SegList, ConcreteSeg, VarSeg


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_clausal_module(filename: str) -> Module:
    path = os.path.join(os.path.dirname(__file__), "clausal_modules", filename)
    name = f"_test_seglist_cr_{filename.replace('.', '_')}"
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def solutions_of(pred_name, *args, module):
    return list(call(pred_name, *args, module=module))


# ── 4a. _head_list_unify_output ────────────────────────────────────────────────


class TestOutputUnboundStar:
    """_head_list_unify_output builds a SegList when the star var is unbound."""

    def test_star_only(self):
        """[*T] with T unbound → SegList([VarSeg(T)]) bound to target."""
        trail = Trail()
        target = Var()
        star = Var()
        result = _head_list_unify_output(target, [], star, [], trail)
        assert result is True
        sl = deref(target)
        assert isinstance(sl, SegList)
        assert len(sl.segments) == 1
        assert isinstance(sl.segments[0], VarSeg)

    def test_before_and_unbound_star(self):
        """[1, *T] with T unbound → SegList([ConcreteSeg([1]), VarSeg(T)])."""
        trail = Trail()
        target = Var()
        h = Var()
        star = Var()
        unify(h, 1, trail)
        result = _head_list_unify_output(target, [h], star, [], trail)
        assert result is True
        sl = deref(target)
        assert isinstance(sl, SegList)
        assert sl.segments[0] == ConcreteSeg([1])
        assert isinstance(sl.segments[1], VarSeg)

    def test_before_unbound_star_after(self):
        """[1, *T, 2] with T unbound → SegList([ConcreteSeg([1]), VarSeg(T), ConcreteSeg([2])])."""
        trail = Trail()
        target = Var()
        h = Var()
        star = Var()
        tail_elem = Var()
        unify(h, 1, trail)
        unify(tail_elem, 2, trail)
        result = _head_list_unify_output(target, [h], star, [tail_elem], trail)
        assert result is True
        sl = deref(target)
        assert isinstance(sl, SegList)
        assert len(sl.segments) == 3
        assert sl.segments[0] == ConcreteSeg([1])
        assert isinstance(sl.segments[1], VarSeg)
        assert sl.segments[2] == ConcreteSeg([2])

    def test_seglist_later_unified(self):
        """After building a SegList, unifying the star var resolves it."""
        trail = Trail()
        target = Var()
        star = Var()
        h = Var()
        unify(h, 1, trail)
        _head_list_unify_output(target, [h], star, [], trail)
        # Now unify star → [2, 3]
        unify(star, [2, 3], trail)
        walked = walk(target)
        assert walked == [1, 2, 3]

    def test_target_already_bound_uses_input_mode(self):
        """If target was bound by body, output switches to input mode."""
        trail = Trail()
        target = Var()
        unify(target, [1, 2, 3], trail)
        h = Var()
        t = Var()
        result = _head_list_unify_output(target, [h], t, [], trail)
        assert result is True
        assert deref(h) == 1
        assert deref(t) == [2, 3]


# ── 4b. _body_star_unify with unbound target ──────────────────────────────────


class TestBodyStarUnifyUnbound:
    """_body_star_unify produces a SegList for unbound target."""

    def test_unbound_target_unbound_star(self):
        """Is([1, *T], R) with T and R unbound → R = SegList."""
        trail = Trail()
        target = Var()
        star = Var()
        h = Var()
        unify(h, 1, trail)
        result = _body_star_unify(target, [h], star, [], trail)
        assert result is True
        sl = deref(target)
        assert isinstance(sl, SegList)

    def test_unbound_target_bound_star(self):
        """Is([1, *T], R) with T=[2] → R = [1, 2] (plain list, not SegList)."""
        trail = Trail()
        target = Var()
        star = Var()
        h = Var()
        unify(h, 1, trail)
        unify(star, [2], trail)
        result = _body_star_unify(target, [h], star, [], trail)
        assert result is True
        assert deref(target) == [1, 2]

    def test_then_unify_against_ground(self):
        """After R = SegList, unify R against [1, 2] → T = [2]."""
        trail = Trail()
        target = Var()
        star = Var()
        h = Var()
        unify(h, 1, trail)
        _body_star_unify(target, [h], star, [], trail)
        sl = deref(target)
        assert isinstance(sl, SegList)
        # Unify the SegList against [1, 2]
        result = unify(sl, [1, 2], trail)
        assert result
        assert deref(star) == [2]


# ── 4c. _body_multi_star_unify with unbound target ────────────────────────────


class TestBodyMultiStarUnifyUnbound:
    """_body_multi_star_unify builds a SegList for unbound targets."""

    def test_two_stars_unbound_target(self):
        """[*A, *B] against unbound L → L = SegList([VarSeg(A), VarSeg(B)]).
        Binding is live inside the generator loop."""
        trail = Trail()
        target = Var()
        a, b = Var(), Var()
        segments = [("star", a), ("star", b)]
        found = []
        for _ in _body_multi_star_unify(target, segments, trail):
            sl = deref(target)
            assert isinstance(sl, SegList)
            assert len(sl.segments) == 2
            assert all(isinstance(s, VarSeg) for s in sl.segments)
            found.append(True)
        assert len(found) == 1

    def test_star_fixed_star_unbound_target(self):
        """[*A, 5, *B] against unbound L → L = SegList([VarSeg(A), ConcreteSeg([5]), VarSeg(B)]).
        Binding is live inside the generator loop."""
        trail = Trail()
        target = Var()
        a, b, mid = Var(), Var(), Var()
        unify(mid, 5, trail)
        segments = [("star", a), ("fixed", [mid]), ("star", b)]
        found = []
        for _ in _body_multi_star_unify(target, segments, trail):
            sl = deref(target)
            assert isinstance(sl, SegList)
            assert len(sl.segments) == 3
            assert isinstance(sl.segments[0], VarSeg)
            assert sl.segments[1] == ConcreteSeg([5])
            assert isinstance(sl.segments[2], VarSeg)
            found.append(True)
        assert len(found) == 1

    def test_seglist_then_unified_against_ground(self):
        """[*A, *B] unbound L; inside loop unify L against [1,2,3] gives all splits."""
        trail = Trail()
        target = Var()
        a, b = Var(), Var()
        segments = [("star", a), ("star", b)]
        splits = []
        for _ in _body_multi_star_unify(target, segments, trail):
            sl = deref(target)
            assert isinstance(sl, SegList)
            # Enumerate all splits of [1, 2, 3]
            for _ in _seglist_unify_gen(sl, [1, 2, 3], trail):
                splits.append((list(deref(a)), list(deref(b))))
        assert splits == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]


# Import missing helper
from clausal.terms import _seglist_unify_gen


# ── 4d. _build_star_list with unbound star ────────────────────────────────────


class TestBuildStarListUnbound:
    """_build_star_list returns a SegList when the star element is unbound."""

    def test_star_only_unbound(self):
        """_build_star_list([], T, []) with T unbound → SegList([VarSeg(T)])."""
        t = Var()
        result = _build_star_list([], t, [])
        assert isinstance(result, SegList)
        assert len(result.segments) == 1
        assert isinstance(result.segments[0], VarSeg)
        assert result.segments[0].var is t

    def test_before_and_unbound_star(self):
        """_build_star_list([1], T, []) → SegList([ConcreteSeg([1]), VarSeg(T)])."""
        t = Var()
        result = _build_star_list([1], t, [])
        assert isinstance(result, SegList)
        assert result.segments[0] == ConcreteSeg([1])
        assert isinstance(result.segments[1], VarSeg)

    def test_before_unbound_star_after(self):
        """_build_star_list([1], T, [2]) → 3-segment SegList."""
        t = Var()
        result = _build_star_list([1], t, [2])
        assert isinstance(result, SegList)
        assert len(result.segments) == 3
        assert result.segments[0] == ConcreteSeg([1])
        assert isinstance(result.segments[1], VarSeg)
        assert result.segments[2] == ConcreteSeg([2])

    def test_bound_star_returns_plain_list(self):
        """_build_star_list([1], [2, 3], []) → plain list [1, 2, 3]."""
        result = _build_star_list([1], [2, 3], [])
        assert result == [1, 2, 3]

    def test_seglist_becomes_ground_on_bind(self):
        """After building SegList, binding the star var resolves to a plain list."""
        trail = Trail()
        t = Var()
        sl = _build_star_list([1], t, [4])
        assert isinstance(sl, SegList)
        unify(t, [2, 3], trail)
        walked = walk(sl)
        assert walked == [1, 2, 3, 4]


# ── 4e. _build_multi_star_list ────────────────────────────────────────────────


class TestBuildMultiStarList:
    """_build_multi_star_list builds SegLists for multi-star body expressions."""

    def test_two_unbound_stars(self):
        """[*A, *B] with both unbound → SegList([VarSeg(A), VarSeg(B)])."""
        a, b = Var(), Var()
        result = _build_multi_star_list([("star", a), ("star", b)])
        assert isinstance(result, SegList)
        segs = result.segments
        assert len(segs) == 2
        assert isinstance(segs[0], VarSeg)
        assert isinstance(segs[1], VarSeg)

    def test_fixed_star_unbound(self):
        """[1, 2, *T] with T unbound → SegList([ConcreteSeg([1,2]), VarSeg(T)])."""
        t = Var()
        result = _build_multi_star_list([("fixed", [1, 2]), ("star", t)])
        assert isinstance(result, SegList)
        assert result.segments[0] == ConcreteSeg([1, 2])
        assert isinstance(result.segments[1], VarSeg)

    def test_star_fixed_star_unbound(self):
        """[*A, 5, *B] → SegList with 3 segments."""
        a, b = Var(), Var()
        result = _build_multi_star_list([("star", a), ("fixed", [5]), ("star", b)])
        assert isinstance(result, SegList)
        assert len(result.segments) == 3
        assert isinstance(result.segments[0], VarSeg)
        assert result.segments[1] == ConcreteSeg([5])
        assert isinstance(result.segments[2], VarSeg)

    def test_all_bound_returns_plain_list(self):
        """[*A, *B] with A=[1,2], B=[3] → plain list [1,2,3]."""
        a, b = Var(), Var()
        trail = Trail()
        unify(a, [1, 2], trail)
        unify(b, [3], trail)
        result = _build_multi_star_list([("star", a), ("star", b)])
        assert result == [1, 2, 3]

    def test_fixed_and_bound_star(self):
        """[1, *T] with T=[2,3] → plain list [1, 2, 3]."""
        t = Var()
        trail = Trail()
        unify(t, [2, 3], trail)
        result = _build_multi_star_list([("fixed", [1]), ("star", t)])
        assert result == [1, 2, 3]


# ── Integration: compiled predicates produce SegLists ─────────────────────────


class TestCompiledPredicateCreation:
    """Compiled predicates produce SegLists when star vars are unbound."""

    def setup_method(self):
        self.mod = _load_clausal_module("lists.clausal")
        self.mstar = _load_clausal_module("multistar.clausal")

    def test_append_unbound_rhs(self):
        """append([1,2], Y, Z) with Y unbound → Z is a SegList inside the solution."""
        mod = self.mod
        y = Var()
        z = Var()
        # Capture binding while generator is live (bindings are active inside the loop)
        z_types = [type(deref(z)) for _ in call("append", [1, 2], y, z, module=mod)]
        assert z_types == [SegList]

    def test_append_unbound_rhs_then_unified(self):
        """Inside append([1,2], Y, Z) solution, unify Z=[1,2,3] → Y=[3]."""
        mod = self.mod
        y = Var()
        z = Var()
        y_vals = []
        for trail in call("append", [1, 2], y, z, module=mod):
            z_val = deref(z)
            assert isinstance(z_val, SegList)
            # Unify the SegList against [1, 2, 3]
            unify(z_val, [1, 2, 3], trail)
            y_vals.append(list(deref(y)))
        assert y_vals == [[3]]

    def test_last_forward_still_works(self):
        """last([1, 2, 3], X) → X = 3 (forward mode not broken by Phase 4 changes)."""
        mod = self.mod
        x = Var()
        solutions = [deref(x) for _ in call("last", [1, 2, 3], x, module=mod)]
        assert solutions == [3]
    # Note: last(L, X) with L unbound is inherently infinite — Clause 1 requires a
    # concrete list (no star), Clause 2 recurses with a fresh unbound TAIL forever.

    def test_split_unbound_list(self):
        """Split(L, A, B) with L unbound → L is a SegList inside the solution."""
        mod = self.mstar
        lst = Var()
        a, b = Var(), Var()
        lst_types = [type(deref(lst)) for _ in call("Split", lst, a, b, module=mod)]
        assert lst_types == [SegList]

    def test_split_unbound_list_then_ground(self):
        """Inside Split(L, A, B) solution, unify L=[1,2,3] enumerates splits."""
        mod = self.mstar
        lst = Var()
        a, b = Var(), Var()
        all_splits = []
        for trail in call("Split", lst, a, b, module=mod):
            sl = deref(lst)
            assert isinstance(sl, SegList)
            for _ in _seglist_unify_gen(sl, [1, 2, 3], trail):
                all_splits.append((list(deref(a)), list(deref(b))))
        assert all_splits == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]
