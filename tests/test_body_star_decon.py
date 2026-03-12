"""Tests for list patterns Phase 5 — star in body unification.

Currently body-position `[HEAD, *TAIL]` does NOT work in Is-goals because
`term_to_ast_expr` generates eager Python `[h, *t]` which fails when `t` is
an unbound Var (TypeError: Value after * must be an iterable).  Phase 5 must
make star-list patterns in body Is-goals work for both directions:

- **Deconstruction**: `[H, *T] is [1,2,3]` → H=1, T=[2,3]
- **Construction**: `R is [H, *T]` where H and T are already bound

Test categories:
  A. Is-goal deconstruction: [H, *T] is X where X is a ground list
  B. Is-goal construction: R is [H, *T] where H and T are bound
  C. Predicate-call regressions: head-pattern star (already works)
  D. Clausal file predicates using body-position star patterns
  E. Multi-star in body: [*A, *B]
  F. Bidirectional: same pattern for construct then deconstruct roundtrip
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

from clausal.logic.compiler import compile_predicate
from clausal.logic.database import Clause, Database, Module
from clausal.logic.solve import call, solve, query, once
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import (
    And, Or, Not,
    Unify as Is, Lt, LtE, Gt, GtE, NotEq, Eq,
    In, NotIn,
    Add, Sub, Mult, Negate,
    Call, LoadName,
    Compound,
)
from clausal.pythonic_ast.nodes import StarUnpack

import clausal.import_hook
from clausal.import_hook import _predicate_loader
from importlib.machinery import ModuleSpec


# ── Helpers ───────────────────────────────────────────────────────────────────

def fresh_module(name: str = "test") -> Module:
    return Module(name)


def _load_clausal_module(filename: str) -> Module:
    """Load a .clausal file from tests/clausal_modules/ and return its Module."""
    path = os.path.join(os.path.dirname(__file__), "clausal_modules", filename)
    name = f"_test_body_star_{filename.replace('.', '_')}"
    sys.modules.pop(name, None)
    spec = ModuleSpec(name, _predicate_loader, origin=path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod.__dict__["$module"]


# ══════════════════════════════════════════════════════════════════════════════
# A. Is-goal deconstruction — X is [H, *T] where X is a ground list
# ══════════════════════════════════════════════════════════════════════════════


class TestIsGoalDeconstruction:
    """Is-goal with body-position list pattern: deconstruct a ground list."""

    def test_head_tail_basic(self):
        """X is [1,2,3], [H, *T] is X → H=1, T=[2,3]."""
        mod = fresh_module()
        x, h, t = Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[1, 2, 3]),
            right=Is(left=[h, StarUnpack(value=t)], right=x),
        )
        results = [(deref(h), deref(t)) for _ in solve(goal, mod)]
        assert results == [(1, [2, 3])]

    def test_head_tail_singleton(self):
        """[H, *T] is [42] → H=42, T=[]."""
        mod = fresh_module()
        x, h, t = Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[42]),
            right=Is(left=[h, StarUnpack(value=t)], right=x),
        )
        results = [(deref(h), deref(t)) for _ in solve(goal, mod)]
        assert results == [(42, [])]

    def test_head_tail_empty_fails(self):
        """[H, *T] is [] → no solutions (empty list has no head)."""
        mod = fresh_module()
        x, h, t = Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[]),
            right=Is(left=[h, StarUnpack(value=t)], right=x),
        )
        assert list(solve(goal, mod)) == []

    def test_two_fixed_plus_star(self):
        """[A, B, *REST] is [10, 20, 30, 40] → A=10, B=20, REST=[30,40]."""
        mod = fresh_module()
        x, a, b, rest = Var(), Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[10, 20, 30, 40]),
            right=Is(left=[a, b, StarUnpack(value=rest)], right=x),
        )
        results = [(deref(a), deref(b), deref(rest)) for _ in solve(goal, mod)]
        assert results == [(10, 20, [30, 40])]

    def test_two_fixed_exact_match(self):
        """[A, B, *REST] is [1, 2] → A=1, B=2, REST=[]."""
        mod = fresh_module()
        x, a, b, rest = Var(), Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[1, 2]),
            right=Is(left=[a, b, StarUnpack(value=rest)], right=x),
        )
        results = [(deref(a), deref(b), deref(rest)) for _ in solve(goal, mod)]
        assert results == [(1, 2, [])]

    def test_two_fixed_too_short_fails(self):
        """[A, B, *REST] is [1] → no solutions (too few elements)."""
        mod = fresh_module()
        x, a, b, rest = Var(), Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[1]),
            right=Is(left=[a, b, StarUnpack(value=rest)], right=x),
        )
        assert list(solve(goal, mod)) == []

    def test_star_only(self):
        """[*ALL] is [1, 2, 3] → ALL=[1,2,3]."""
        mod = fresh_module()
        x, all_ = Var(), Var()
        goal = And(
            left=Is(left=x, right=[1, 2, 3]),
            right=Is(left=[StarUnpack(value=all_)], right=x),
        )
        results = [deref(all_) for _ in solve(goal, mod)]
        assert results == [[1, 2, 3]]

    def test_star_only_empty(self):
        """[*ALL] is [] → ALL=[]."""
        mod = fresh_module()
        x, all_ = Var(), Var()
        goal = And(
            left=Is(left=x, right=[]),
            right=Is(left=[StarUnpack(value=all_)], right=x),
        )
        results = [deref(all_) for _ in solve(goal, mod)]
        assert results == [[]]

    def test_sandwich_pattern(self):
        """[H, *MID, T] is [1, 2, 3, 4] → H=1, MID=[2,3], T=4."""
        mod = fresh_module()
        x, h, mid, t = Var(), Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[1, 2, 3, 4]),
            right=Is(left=[h, StarUnpack(value=mid), t], right=x),
        )
        results = [(deref(h), deref(mid), deref(t)) for _ in solve(goal, mod)]
        assert results == [(1, [2, 3], 4)]

    def test_sandwich_minimum(self):
        """[H, *MID, T] is [1, 2] → H=1, MID=[], T=2."""
        mod = fresh_module()
        x, h, mid, t = Var(), Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[1, 2]),
            right=Is(left=[h, StarUnpack(value=mid), t], right=x),
        )
        results = [(deref(h), deref(mid), deref(t)) for _ in solve(goal, mod)]
        assert results == [(1, [], 2)]

    def test_sandwich_too_short_fails(self):
        """[H, *MID, T] is [1] → no solutions (need at least 2 elements)."""
        mod = fresh_module()
        x, h, mid, t = Var(), Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[1]),
            right=Is(left=[h, StarUnpack(value=mid), t], right=x),
        )
        assert list(solve(goal, mod)) == []

    def test_trailing_star(self):
        """[*INIT, LAST] is [1, 2, 3] → INIT=[1,2], LAST=3."""
        mod = fresh_module()
        x, init, last = Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[1, 2, 3]),
            right=Is(left=[StarUnpack(value=init), last], right=x),
        )
        results = [(deref(init), deref(last)) for _ in solve(goal, mod)]
        assert results == [([1, 2], 3)]

    def test_nested_list_elements(self):
        """[H, *T] is [[1,2], [3,4], [5,6]] → H=[1,2], T=[[3,4],[5,6]]."""
        mod = fresh_module()
        x, h, t = Var(), Var(), Var()
        goal = And(
            left=Is(left=x, right=[[1, 2], [3, 4], [5, 6]]),
            right=Is(left=[h, StarUnpack(value=t)], right=x),
        )
        results = [(deref(h), deref(t)) for _ in solve(goal, mod)]
        assert results == [([1, 2], [[3, 4], [5, 6]])]


# ══════════════════════════════════════════════════════════════════════════════
# B. Construction regression — body [H, *T] with bound vars still works
# ══════════════════════════════════════════════════════════════════════════════


class TestIsGoalConstruction:
    """Body-position [H, *T] construction in Is-goals (new in Phase 5).

    These do NOT work pre-Phase 5 — `term_to_ast_expr` generates eager
    `[h, *t]` which fails when t is a Var.  Phase 5 must handle construction
    by deref'ing vars before star-expansion.
    """

    def test_construct_from_bound_vars(self):
        """H=1, T=[2,3] → [H, *T] constructs [1, 2, 3]."""
        mod = fresh_module()
        h, t, result = Var(), Var(), Var()
        goal = And(
            left=And(
                left=Is(left=h, right=1),
                right=Is(left=t, right=[2, 3]),
            ),
            right=Is(left=result, right=[h, StarUnpack(value=t)]),
        )
        results = [deref(result) for _ in solve(goal, mod)]
        assert results == [[1, 2, 3]]

    def test_construct_empty_tail(self):
        """H=42, T=[] → [H, *T] constructs [42]."""
        mod = fresh_module()
        h, t, result = Var(), Var(), Var()
        goal = And(
            left=And(
                left=Is(left=h, right=42),
                right=Is(left=t, right=[]),
            ),
            right=Is(left=result, right=[h, StarUnpack(value=t)]),
        )
        results = [deref(result) for _ in solve(goal, mod)]
        assert results == [[42]]

    def test_construct_star_only(self):
        """ALL=[1,2,3] → [*ALL] constructs [1,2,3]."""
        mod = fresh_module()
        all_, result = Var(), Var()
        goal = And(
            left=Is(left=all_, right=[1, 2, 3]),
            right=Is(left=result, right=[StarUnpack(value=all_)]),
        )
        results = [deref(result) for _ in solve(goal, mod)]
        assert results == [[1, 2, 3]]

    def test_construct_sandwich(self):
        """H=1, MID=[2,3], T=4 → [H, *MID, T] constructs [1,2,3,4]."""
        mod = fresh_module()
        h, mid, t, result = Var(), Var(), Var(), Var()
        goal = And(
            left=And(
                left=And(
                    left=Is(left=h, right=1),
                    right=Is(left=mid, right=[2, 3]),
                ),
                right=Is(left=t, right=4),
            ),
            right=Is(left=result, right=[h, StarUnpack(value=mid), t]),
        )
        results = [deref(result) for _ in solve(goal, mod)]
        assert results == [[1, 2, 3, 4]]


# ══════════════════════════════════════════════════════════════════════════════
# C. Predicate call body args — [H, *T] as argument to a body-position call
# ══════════════════════════════════════════════════════════════════════════════


class TestHeadPatternRegression:
    """Regression: star patterns in head positions still work after Phase 5.

    These test head-position [H, *T] which already works via MatchStar.
    Phase 5 changes must not break existing head-pattern deconstruction.
    """

    def test_append_forward(self):
        """append([1,2], [3,4], R) → R=[1,2,3,4] (head-pattern star)."""
        mod = _load_clausal_module("lists.clausal")
        r = Var()
        results = [deref(r) for _ in call("append", [1, 2], [3, 4], r, module=mod)]
        assert results == [[1, 2, 3, 4]]

    def test_append_reverse(self):
        """append(X, Y, [1,2,3]) → enumerates all splits (head-pattern star)."""
        mod = _load_clausal_module("lists.clausal")
        x, y = Var(), Var()
        results = [
            (deref(x), deref(y))
            for _ in call("append", x, y, [1, 2, 3], module=mod)
        ]
        assert results == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]

    def test_length(self):
        """length([10, 20, 30], N) → N=3 (head-pattern star)."""
        mod = _load_clausal_module("lists.clausal")
        n = Var()
        results = [deref(n) for _ in call("length", [10, 20, 30], n, module=mod)]
        assert results == [3]

    def test_length_empty(self):
        """length([], N) → N=0."""
        mod = _load_clausal_module("lists.clausal")
        n = Var()
        results = [deref(n) for _ in call("length", [], n, module=mod)]
        assert results == [0]


# ══════════════════════════════════════════════════════════════════════════════
# D. Clausal file predicates that use body-position star deconstruction
# ══════════════════════════════════════════════════════════════════════════════


class TestBodyStarInClausalFile:
    """Predicates defined in .clausal files that use [H, *T] in body goals."""

    def test_head_tail_body_decon(self):
        """head_tail(LIST, H, T) <- [H, *T] is LIST.

        Deconstructs LIST into head H and tail T in the body.
        """
        mod = _load_clausal_module("body_star.clausal")
        h, t = Var(), Var()
        results = [
            (deref(h), deref(t))
            for _ in call("head_tail", [1, 2, 3], h, t, module=mod)
        ]
        assert results == [(1, [2, 3])]

    def test_head_tail_singleton(self):
        """head_tail([42], H, T) → H=42, T=[]."""
        mod = _load_clausal_module("body_star.clausal")
        h, t = Var(), Var()
        results = [
            (deref(h), deref(t))
            for _ in call("head_tail", [42], h, t, module=mod)
        ]
        assert results == [(42, [])]

    def test_head_tail_empty_fails(self):
        """head_tail([], H, T) → no solutions."""
        mod = _load_clausal_module("body_star.clausal")
        h, t = Var(), Var()
        results = list(call("head_tail", [], h, t, module=mod))
        assert results == []

    def test_init_last_body_decon(self):
        """init_last(LIST, INIT, LAST) <- [*INIT, LAST] is LIST.

        Trailing star pattern in body — splits off the last element.
        """
        mod = _load_clausal_module("body_star.clausal")
        init, last = Var(), Var()
        results = [
            (deref(init), deref(last))
            for _ in call("init_last", [1, 2, 3], init, last, module=mod)
        ]
        assert results == [([1, 2], 3)]

    def test_init_last_singleton(self):
        """init_last([7], INIT, LAST) → INIT=[], LAST=7."""
        mod = _load_clausal_module("body_star.clausal")
        init, last = Var(), Var()
        results = [
            (deref(init), deref(last))
            for _ in call("init_last", [7], init, last, module=mod)
        ]
        assert results == [([], 7)]

    def test_init_last_empty_fails(self):
        """init_last([], INIT, LAST) → no solutions."""
        mod = _load_clausal_module("body_star.clausal")
        init, last = Var(), Var()
        results = list(call("init_last", [], init, last, module=mod))
        assert results == []

    def test_sandwich_body_decon(self):
        """sandwich(LIST, H, MID, T) <- [H, *MID, T] is LIST.

        Extracts first, middle, and last from a list in the body.
        """
        mod = _load_clausal_module("body_star.clausal")
        h, mid, t = Var(), Var(), Var()
        results = [
            (deref(h), deref(mid), deref(t))
            for _ in call("sandwich", [1, 2, 3, 4], h, mid, t, module=mod)
        ]
        assert results == [(1, [2, 3], 4)]

    def test_sandwich_minimum(self):
        """sandwich([1, 2], H, MID, T) → H=1, MID=[], T=2."""
        mod = _load_clausal_module("body_star.clausal")
        h, mid, t = Var(), Var(), Var()
        results = [
            (deref(h), deref(mid), deref(t))
            for _ in call("sandwich", [1, 2], h, mid, t, module=mod)
        ]
        assert results == [(1, [], 2)]

    def test_capture_all_body(self):
        """capture_body(LIST, ALL) <- [*ALL] is LIST.

        Star-only body deconstruction — just copies the list.
        """
        mod = _load_clausal_module("body_star.clausal")
        all_ = Var()
        results = [deref(all_) for _ in call("capture_body", [1, 2, 3], all_, module=mod)]
        assert results == [[1, 2, 3]]

    def test_capture_all_body_empty(self):
        """capture_body([], ALL) → ALL=[]."""
        mod = _load_clausal_module("body_star.clausal")
        all_ = Var()
        results = [deref(all_) for _ in call("capture_body", [], all_, module=mod)]
        assert results == [[]]

    def test_body_decon_then_use(self):
        """sum_tail(LIST, S) <- [_, *T] is LIST and length(T, S).

        Deconstruct in body, then use the result in a subsequent goal.
        """
        mod = _load_clausal_module("body_star.clausal")
        s = Var()
        results = [deref(s) for _ in call("sum_tail", [10, 20, 30, 40], s, module=mod)]
        assert results == [3]

    def test_body_decon_chain(self):
        """second(LIST, X) <- [_, *T] is LIST and [X, *_] is T.

        Two consecutive body deconstructions — extract the second element.
        """
        mod = _load_clausal_module("body_star.clausal")
        x = Var()
        results = [deref(x) for _ in call("second", [10, 20, 30], x, module=mod)]
        assert results == [20]

    def test_body_construct_and_decon(self):
        """wrap_unwrap(X, Y) <- L is [X, 99] and [Y, _] is L.

        First constructs a list from bound X, then deconstructs to get Y.
        Y should equal X.
        """
        mod = _load_clausal_module("body_star.clausal")
        y = Var()
        results = [deref(y) for _ in call("wrap_unwrap", 42, y, module=mod)]
        assert results == [42]


# ══════════════════════════════════════════════════════════════════════════════
# E. Multi-star in body deconstruction
# ══════════════════════════════════════════════════════════════════════════════


class TestBodyMultiStarDeconstruction:
    """Multi-star patterns [*A, *B] in body positions — combinatorial splits."""

    def test_body_split(self):
        """body_split(LIST, A, B) <- [*A, *B] is LIST.

        All 2-way splits enumerated via backtracking.
        """
        mod = _load_clausal_module("body_star.clausal")
        a, b = Var(), Var()
        results = [
            (deref(a), deref(b))
            for _ in call("body_split", [1, 2, 3], a, b, module=mod)
        ]
        assert results == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]

    def test_body_split_empty(self):
        """body_split([], A, B) → A=[], B=[]."""
        mod = _load_clausal_module("body_star.clausal")
        a, b = Var(), Var()
        results = [
            (deref(a), deref(b))
            for _ in call("body_split", [], a, b, module=mod)
        ]
        assert results == [([], [])]

    def test_body_split_singleton(self):
        """body_split([1], A, B) → two solutions."""
        mod = _load_clausal_module("body_star.clausal")
        a, b = Var(), Var()
        results = [
            (deref(a), deref(b))
            for _ in call("body_split", [1], a, b, module=mod)
        ]
        assert results == [([], [1]), ([1], [])]


# ══════════════════════════════════════════════════════════════════════════════
# F. Unification direction detection — same pattern works in both directions
# ══════════════════════════════════════════════════════════════════════════════


class TestBidirectionalBodyStar:
    """A single Is goal with a star list should work for both construct/decon."""

    def test_decon_then_construct_roundtrip(self):
        """Deconstruct a list, then reconstruct it — should get the original back.

        [H, *T] is [1,2,3]  then  R is [H, *T]  → R=[1,2,3].
        """
        mod = fresh_module()
        h, t, r = Var(), Var(), Var()
        goal = And(
            left=Is(left=[h, StarUnpack(value=t)], right=[1, 2, 3]),
            right=Is(left=r, right=[h, StarUnpack(value=t)]),
        )
        results = [deref(r) for _ in solve(goal, mod)]
        assert results == [[1, 2, 3]]

    def test_lhs_ground_rhs_pattern(self):
        """[1,2,3] is [H, *T] — ground list on left, pattern on right."""
        mod = fresh_module()
        h, t = Var(), Var()
        goal = Is(left=[1, 2, 3], right=[h, StarUnpack(value=t)])
        results = [(deref(h), deref(t)) for _ in solve(goal, mod)]
        assert results == [(1, [2, 3])]

    def test_rhs_ground_lhs_pattern(self):
        """[H, *T] is [1,2,3] — pattern on left, ground list on right."""
        mod = fresh_module()
        h, t = Var(), Var()
        goal = Is(left=[h, StarUnpack(value=t)], right=[1, 2, 3])
        results = [(deref(h), deref(t)) for _ in solve(goal, mod)]
        assert results == [(1, [2, 3])]
