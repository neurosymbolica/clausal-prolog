"""Tests for V3-5 — extended list predicates (list_util port)."""

from __future__ import annotations

import os

import pytest

from clausal.logic.cells import chars
from clausal.logic.builtins.lists import (
    _take__3, _drop__3, _split_at__4, _zip__3, _replicate__3, _split_with__3,
)
from clausal.logic.builtins.higher_order import (
    _take_while__3, _drop_while__3, _span__4,
    _group_by__3, _sort_by__3, _max_by__3, _min_by__3, _filter_map__3,
)
from clausal.logic.atoms import char_atom, mint
from clausal.logic.solve import call
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.import_hook import _load_module
from tests._suffix import seam_path


# ── Helpers ────────────────────────────────────────────────────────────────────


def run_trampoline(fn, *args):
    """Call a native trampoline builtin and return number of solutions."""
    trail = Trail()
    sg = StepGenerator(fn, None, None, None, *args, trail)
    gen, value = sg.send(None)
    count = 0
    while True:
        if gen is None:
            if value is DONE:
                return count
            count += 1
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


def run_trampoline_var(fn, *args_before_result):
    """Call a native trampoline builtin with trailing Var, return deref'd values."""
    trail = Trail()
    result = Var()
    sg = StepGenerator(fn, None, None, None, *args_before_result, result, trail)
    gen, value = sg.send(None)
    results = []
    while True:
        if gen is None:
            if value is DONE:
                return results
            results.append(deref(result))
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


def run_trampoline_2vars(fn, *args_before_results):
    """Call with two trailing Vars, return pairs of deref'd values."""
    trail = Trail()
    v1, v2 = Var(), Var()
    sg = StepGenerator(fn, None, None, None, *args_before_results, v1, v2, trail)
    gen, value = sg.send(None)
    results = []
    while True:
        if gen is None:
            if value is DONE:
                return results
            results.append((deref(v1), deref(v2)))
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


# ── Simple goal closures for testing ──────────────────────────────────────────


def _goal_positive(x, trail, k):
    if isinstance(deref(x), (int, float)) and deref(x) > 0:
        yield None


def _goal_even(x, trail, k):
    if isinstance(deref(x), int) and deref(x) % 2 == 0:
        yield None


def _goal_double(x, y, trail, k):
    val = deref(x)
    if isinstance(val, (int, float)):
        if unify(y, val * 2, trail):
            yield None


def _goal_negate(x, y, trail, k):
    val = deref(x)
    if isinstance(val, (int, float)):
        if unify(y, -val, trail):
            yield None


def _goal_identity(x, y, trail, k):
    if unify(y, deref(x), trail):
        yield None


def _goal_double_positive(x, y, trail, k):
    val = deref(x)
    if isinstance(val, (int, float)) and val > 0:
        if unify(y, val * 2, trail):
            yield None


def _goal_always_fail(*args):
    return; yield  # noqa: B901


# ══════════════════════════════════════════════════════════════════════════════
# CORE LIST PREDICATES
# ══════════════════════════════════════════════════════════════════════════════


class TestTake:
    def test_basic(self):
        # nv
        assert run_trampoline_var(_take__3, 2, [1, 2, 3, 4]) == [[1, 2]]

    def test_take_zero(self):
        # nv
        assert run_trampoline_var(_take__3, 0, [1, 2, 3]) == [[]]

    def test_take_more_than_length(self):
        # nv
        assert run_trampoline_var(_take__3, 10, [1, 2]) == [[1, 2]]

    def test_take_from_empty(self):
        # nv
        assert run_trampoline_var(_take__3, 3, []) == [[]]


class TestDrop:
    def test_basic(self):
        # nv
        assert run_trampoline_var(_drop__3, 2, [1, 2, 3, 4]) == [[3, 4]]

    def test_drop_zero(self):
        # nv
        assert run_trampoline_var(_drop__3, 0, [1, 2, 3]) == [[1, 2, 3]]

    def test_drop_all(self):
        # nv
        assert run_trampoline_var(_drop__3, 3, [1, 2, 3]) == [[]]

    def test_drop_more_than_length(self):
        # nv
        assert run_trampoline_var(_drop__3, 10, [1, 2]) == [[]]


class TestSplitAt:
    def test_middle(self):
        # nv
        assert run_trampoline_2vars(_split_at__4, 2, [1, 2, 3, 4]) == [([1, 2], [3, 4])]

    def test_at_zero(self):
        # nv
        assert run_trampoline_2vars(_split_at__4, 0, [1, 2, 3]) == [([], [1, 2, 3])]

    def test_at_end(self):
        # nv
        assert run_trampoline_2vars(_split_at__4, 3, [1, 2, 3]) == [([1, 2, 3], [])]

    def test_beyond_length(self):
        # nv
        assert run_trampoline_2vars(_split_at__4, 10, [1, 2]) == [([1, 2], [])]


class TestZip:
    def test_equal_length(self):
        # nv
        assert run_trampoline_var(_zip__3, [1, 2, 3], ["a", "b", "c"]) == [
            [("-", 1, "a"), ("-", 2, "b"), ("-", 3, "c")]
        ]

    def test_unequal_length(self):
        # nv
        assert run_trampoline_var(_zip__3, [1, 2], ["a", "b", "c"]) == [
            [("-", 1, "a"), ("-", 2, "b")]
        ]

    def test_empty(self):
        # nv
        assert run_trampoline_var(_zip__3, [], [1, 2]) == [[]]


class TestReplicate:
    def test_basic(self):
        # nv — F053 (C9 audit, option A): replicating a CHAR produces a str
        # (a list of char atoms IS a string, so the compact representation
        # is the right one to build).  THE FLIP
        # (2026-09-06-atoms-as-cells-strings): the element has to be the
        # char ATOM; a 1-char ``str`` is a one-element STRING and a list of
        # those is a list of strings, which does not promote.
        assert run_trampoline_var(_replicate__3, 3, char_atom("x")) == [chars("xxx")]

    def test_zero(self):
        # nv — F053: zero copies is the empty list, which is the empty str.
        assert run_trampoline_var(_replicate__3, 0, char_atom("x")) == [chars("")]

    def test_one(self):
        # nv
        assert run_trampoline_var(_replicate__3, 1, 42) == [[42]]


class TestSplitWith:
    def test_split_by_element(self):
        # nv
        assert run_trampoline_var(_split_with__3, 0, [1, 2, 0, 3, 4]) == [
            [[1, 2], [3, 4]]
        ]

    def test_no_separator(self):
        # nv
        assert run_trampoline_var(_split_with__3, 0, [1, 2, 3]) == [[[1, 2, 3]]]

    def test_consecutive_separators(self):
        # nv
        assert run_trampoline_var(_split_with__3, 0, [1, 0, 0, 2]) == [
            [[1], [], [2]]
        ]

    def test_join_mode(self):
        # nv
        trail = Trail()
        result = Var()
        sg = StepGenerator(_split_with__3, None, None, None, 0, result, [[1, 2], [3, 4]], trail)
        gen, value = sg.send(None)
        results = []
        while True:
            if gen is None:
                if value is DONE:
                    break
                results.append(deref(result))
                gen, value = sg.send(None)
            else:
                gen, value = gen.send(value)
        assert results == [[1, 2, 0, 3, 4]]


# ══════════════════════════════════════════════════════════════════════════════
# HIGHER-ORDER LIST PREDICATES
# ══════════════════════════════════════════════════════════════════════════════


class TestTakeWhile:
    def test_basic(self):
        # nv
        assert run_trampoline_var(_take_while__3, _goal_positive, [1, 2, -3, 4]) == [[1, 2]]

    def test_none_match(self):
        # nv
        assert run_trampoline_var(_take_while__3, _goal_positive, [-1, 2, 3]) == [[]]

    def test_all_match(self):
        # nv
        assert run_trampoline_var(_take_while__3, _goal_positive, [1, 2, 3]) == [[1, 2, 3]]


class TestDropWhile:
    def test_basic(self):
        # nv
        assert run_trampoline_var(_drop_while__3, _goal_positive, [1, 2, -3, 4]) == [[-3, 4]]

    def test_none_match(self):
        # nv
        assert run_trampoline_var(_drop_while__3, _goal_positive, [-1, 2, 3]) == [[-1, 2, 3]]

    def test_all_match(self):
        # nv
        assert run_trampoline_var(_drop_while__3, _goal_positive, [1, 2, 3]) == [[]]


class TestSpan:
    def test_basic(self):
        # nv
        assert run_trampoline_2vars(_span__4, _goal_positive, [1, 2, -3, 4]) == [
            ([1, 2], [-3, 4])
        ]


class TestGroupBy:
    def test_consecutive_equal(self):
        # nv
        assert run_trampoline_var(_group_by__3, _goal_identity, [1, 1, 2, 2, 2, 3]) == [
            [[1, 1], [2, 2, 2], [3]]
        ]

    def test_by_computed_key(self):
        # Group by even/odd: _goal_even as identity would need a key projector
        # Use _goal_negate as key: -1,-1 → group; -2,-2 → group
        # nv
        assert run_trampoline_var(_group_by__3, _goal_negate, [1, 2, 3]) == [
            [[1], [2], [3]]  # all different keys → singleton groups
        ]


class TestSortBy:
    def test_sort_by_key(self):
        # nv
        assert run_trampoline_var(_sort_by__3, _goal_negate, [1, 3, 2]) == [[3, 2, 1]]

    def test_already_sorted(self):
        # nv
        assert run_trampoline_var(_sort_by__3, _goal_identity, [1, 2, 3]) == [[1, 2, 3]]

    def test_empty(self):
        # nv
        assert run_trampoline_var(_sort_by__3, _goal_negate, []) == [[]]


class TestMaxBy:
    def test_basic(self):
        # max_by with negate key: max(-x) → element with smallest x → 1
        # nv
        assert run_trampoline_var(_max_by__3, _goal_negate, [3, 1, 2]) == [1]

    def test_single_element(self):
        # nv
        assert run_trampoline_var(_max_by__3, _goal_identity, [42]) == [42]

    def test_tie_breaking(self):
        # First max wins (stable)
        # nv
        assert run_trampoline_var(_max_by__3, _goal_identity, [3, 3, 1]) == [3]


class TestMinBy:
    def test_basic(self):
        # min_by with negate key: min(-x) → element with largest x → 3
        # nv
        assert run_trampoline_var(_min_by__3, _goal_negate, [3, 1, 2]) == [3]

    def test_single_element(self):
        # nv
        assert run_trampoline_var(_min_by__3, _goal_identity, [42]) == [42]


class TestFilterMap:
    def test_basic(self):
        # nv
        assert run_trampoline_var(_filter_map__3, _goal_double_positive, [1, -2, 3, -4]) == [
            [2, 6]
        ]

    def test_all_pass(self):
        # nv
        assert run_trampoline_var(_filter_map__3, _goal_double, [1, 2, 3]) == [
            [2, 4, 6]
        ]

    def test_none_pass(self):
        # nv
        assert run_trampoline_var(_filter_map__3, _goal_always_fail, [1, 2, 3]) == [[]]


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE INTEGRATION: Load .clausal file and run Test predicates
# ══════════════════════════════════════════════════════════════════════════════

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = seam_path(os.path.join(_FIXTURE_DIR, f"{name}.clausal"))
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestListUtilFixture:
    """Run Test predicates from tests/fixtures/list_util.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("list_util")

    @pytest.mark.parametrize("name", [
        # take
        "take basic",
        "take zero",
        "take more than length",
        "take from empty",
        # drop
        "drop basic",
        "drop zero",
        "drop all",
        "drop more than length",
        # split_at
        "split_at middle",
        "split_at zero",
        "split_at end",
        "split_at beyond",
        # zip_
        "zip equal",
        "zip unequal",
        "zip empty",
        # replicate
        "replicate basic",
        "replicate zero",
        "replicate one",
        # split_with
        "split_with basic",
        "split_with no sep",
        "split_with consecutive",
        # take_while
        "take_while basic",
        "take_while none match",
        "take_while all match",
        # drop_while
        "drop_while basic",
        "drop_while none match",
        "drop_while all match",
        # span
        "span basic",
        # group_by
        "group_by identity",
        # sort_by
        "sort_by negate",
        "sort_by empty",
        # max_by
        "max_by negate",
        "max_by single",
        # min_by
        "min_by negate",
        "min_by single",
        # filter_map
        "filter_map basic",
        "filter_map all pass",
        "filter_map none pass",
    ])
    def test_fixture(self, name):
        # nv — the fixture declares ``-double_quotes(atom)``, so a
        # ``test("...")`` description is an ATOM (THE FLIP).
        assert _succeeds("test", mint(name), module=self.mod)
