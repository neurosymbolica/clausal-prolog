"""Phase 3 tests: SegList passthrough — ground and non-ground SegLists passed
to compiled predicates with single-star and multi-star head patterns.

These tests construct SegLists directly (not via compiler) and feed them into
compiled predicates.  They must continue to pass through Phases 4–6 as well.
"""

import os
import sys

import pytest

from clausal.import_hook import _load_module
from clausal.logic.database import Module
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, Trail, deref, unify, walk
from clausal.terms import SegList, ConcreteSeg, VarSeg, _seglist_unify_gen


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_clausal_module(filename: str) -> Module:
    path = os.path.join(os.path.dirname(__file__), "clausal_modules", filename)
    name = f"_test_seglist_pt_{filename.replace('.', '_')}"
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def solutions_of(pred_name, *args, module):
    return list(call(pred_name, *args, module=module))


# ── Single-star head patterns (_head_list_unify_input) ───────────────────────

class TestSingleStarPassthrough:
    """Compiled predicates with [HEAD, *TAIL] patterns receive ground SegLists."""

    def setup_method(self):
        self.mod = _load_clausal_module("lists.clausal")

    def test_append_first_arg_ground_seglist(self):
        """append([1, *V_BOUND], [3], R) where the SegList walks to [1, 2]."""
        # nv
        v = Var()
        trail = Trail()
        unify(v, [2], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert sl.is_ground()

        r = Var()
        results = [deref(r) for _ in call("append", sl, [3], r, module=self.mod)]
        assert results == [[1, 2, 3]]

    def test_append_third_arg_ground_seglist(self):
        """append(A, B, ground_seglist) deconstructing correctly."""
        # nv
        v = Var()
        trail = Trail()
        unify(v, [2], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert sl.is_ground()

        a, b = Var(), Var()
        results = [(deref(a), deref(b)) for _ in call("append", a, b, sl, module=self.mod)]
        assert results == [
            ([], [1, 2]),
            ([1], [2]),
            ([1, 2], []),
        ]

    def test_last_ground_seglist(self):
        """last(ground_seglist, X) finds the last element."""
        # nv
        v = Var()
        trail = Trail()
        unify(v, [2, 3], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert sl.is_ground()

        x = Var()
        results = [deref(x) for _ in call("last", sl, x, module=self.mod)]
        assert results == [3]


# ── Multi-star head patterns (_compile_multi_star_guard) ─────────────────────

class TestMultiStarPassthrough:
    """Compiled predicates with [*A, *B] patterns receive ground SegLists."""

    def setup_method(self):
        self.mod = _load_clausal_module("multistar.clausal")

    def _ground_seglist(self, elems):
        """Construct a ground SegList that walks to elems."""
        v = Var()
        trail = Trail()
        unify(v, elems, trail)
        sl = SegList([VarSeg(v)])
        assert sl.is_ground()
        return sl

    def test_split_ground_seglist(self):
        """split([*A, *B], A, B) with a ground SegList [1, 2, 3]."""
        # nv
        sl = self._ground_seglist([1, 2, 3])
        a, b = Var(), Var()
        results = [(deref(a), deref(b)) for _ in call("split", sl, a, b, module=self.mod)]
        assert results == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]

    def test_split3_ground_seglist(self):
        """split3([X, *A, *B], X, A, B) with a ground SegList [10, 20, 30]."""
        # nv
        sl = self._ground_seglist([10, 20, 30])
        x, a, b = Var(), Var(), Var()
        results = [(deref(x), deref(a), deref(b))
                   for _ in call("split3", sl, x, a, b, module=self.mod)]
        assert results == [
            (10, [], [20, 30]),
            (10, [20], [30]),
            (10, [20, 30], []),
        ]

    def test_around_ground_seglist(self):
        """around([*A, X, *B], X, [A, B]) with a ground SegList."""
        # nv
        sl = self._ground_seglist([1, 2, 3])
        x, p = Var(), Var()
        results = [(deref(x), deref(p))
                   for _ in call("around", sl, x, p, module=self.mod)]
        assert results == [
            (1, [[], [2, 3]]),
            (2, [[1], [3]]),
            (3, [[1, 2], []]),
        ]

    def test_split_concrete_seglist(self):
        """Ground SegList built purely from ConcreteSegs (no VarSeg)."""
        # nv
        sl = SegList([ConcreteSeg([1, 2]), ConcreteSeg([3])])
        assert sl.is_ground()
        a, b = Var(), Var()
        results = [(deref(a), deref(b)) for _ in call("split", sl, a, b, module=self.mod)]
        assert results == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]

    def test_non_ground_seglist_produces_no_solutions(self):
        """Non-ground SegList passed to multi-star predicate: graceful fail (Phase 6)."""
        # nv
        sl = SegList([VarSeg(Var()), VarSeg(Var())])
        assert not sl.is_ground()
        a, b = Var(), Var()
        results = list(call("split", sl, a, b, module=self.mod))
        # Phase 3: no solutions for non-ground SegList (no error)
        assert results == []


# ── Body-position star unification (_body_star_unify) ─────────────────────────

class TestBodyStarPassthrough:
    """Body Is goals with star patterns against SegList targets."""

    def setup_method(self):
        self.mod = _load_clausal_module("body_star.clausal")

    def test_head_tail_ground_seglist(self):
        """head_tail(ground_seglist, H, T) — body Is pattern against SegList."""
        # nv
        v = Var()
        trail = Trail()
        unify(v, [2, 3], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert sl.is_ground()

        h, t = Var(), Var()
        results = [(deref(h), deref(t))
                   for _ in call("head_tail", sl, h, t, module=self.mod)]
        assert results == [(1, [2, 3])]

    def test_init_last_ground_seglist(self):
        """init_last(ground_seglist, INIT, LAST) — trailing-star body pattern."""
        # nv
        v = Var()
        trail = Trail()
        unify(v, [2, 3], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        assert sl.is_ground()

        init, last = Var(), Var()
        results = [(deref(init), deref(last))
                   for _ in call("init_last", sl, init, last, module=self.mod)]
        assert results == [([1, 2], 3)]


# ── SegList concat passthrough ────────────────────────────────────────────────

class TestSegListConcatPassthrough:
    """SegList + list / list + SegList concatenation used as predicate args."""

    def setup_method(self):
        self.mod = _load_clausal_module("lists.clausal")

    def test_append_result_via_add(self):
        """Use sl + [3] as the third argument to append."""
        # nv
        v = Var()
        trail = Trail()
        unify(v, [2], trail)
        sl = SegList([ConcreteSeg([1]), VarSeg(v)])
        # sl is ground [1, 2]; sl + [3] is a new SegList that walks to [1, 2, 3]
        target = sl + [3]
        assert target.is_ground()

        a, b = Var(), Var()
        results = [(deref(a), deref(b)) for _ in call("append", a, b, target, module=self.mod)]
        assert results == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]
