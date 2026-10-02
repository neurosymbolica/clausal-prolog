"""Tests for clausal.modules.py.random — float_0_to_1 predicates."""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.random import (
    float_0_to_1, float_between, integer_between, choice,
    permutation, sample, set_seed, maybe,
    _random_1, _random_float_3, _random_integer_3,
    _random_member_2, _random_permutation_2, _random_sample_3,
    _random_seed_1, _maybe_0, _maybe_1, _rng,
)
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def raised(fn, *args):
    """The error term a simple-mode builtin raises.  RULED 2026-10-02: an
    argument of the wrong type raises type_error, an unbound required one
    instantiation_error -- neither fails the goal."""
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── float_0_to_1/1 ─────────────────────────────────────────────────────────────


class TestRandom:
    def test_binds_float(self):
        # nv
        x = Var()
        sols, trail = simple_solutions(_random_1, x)
        assert len(sols) == 1
        val = deref(x)
        assert isinstance(val, float)
        assert 0.0 <= val < 1.0

    def test_trampoline(self):
        # nv
        x = Var()
        sols, trail = trampoline_solutions(float_0_to_1, x)
        assert len(sols) == 1
        val = deref(x)
        assert isinstance(val, float)
        assert 0.0 <= val < 1.0


# ── float_between/3 ───────────────────────────────────────────────────────


class TestRandomFloat:
    def test_in_range(self):
        # nv
        x = Var()
        sols, trail = simple_solutions(_random_float_3, 1.0, 5.0, x)
        assert len(sols) == 1
        val = deref(x)
        assert 1.0 <= val < 5.0

    def test_low_equals_high_fails(self):
        # nv
        x = Var()
        sols, _ = simple_solutions(_random_float_3, 3.0, 3.0, x)
        assert len(sols) == 0

    def test_low_greater_than_high_fails(self):
        # nv
        x = Var()
        sols, _ = simple_solutions(_random_float_3, 5.0, 1.0, x)
        assert len(sols) == 0

    def test_unbound_low_raises(self):
        # nv
        term = raised(_random_float_3, Var(), 5.0, Var())
        assert term == ('error', 'instantiation_error', ('/', 'float_between', 3))

    def test_unbound_high_raises(self):
        # nv
        term = raised(_random_float_3, 1.0, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'float_between', 3))


# ── integer_between/3 ─────────────────────────────────────────────────────


class TestRandomInteger:
    def test_in_range(self):
        # nv
        x = Var()
        sols, trail = simple_solutions(_random_integer_3, 1, 6, x)
        assert len(sols) == 1
        val = deref(x)
        assert isinstance(val, int)
        assert 1 <= val <= 6

    def test_boundaries_inclusive(self):
        """Seed and verify both endpoints are reachable."""
        # nv
        _rng.seed(42)
        values = set()
        for _ in range(200):
            x = Var()
            trail = Trail()
            list(_random_integer_3(1, 3, x, trail, None))
            values.add(deref(x))
        assert 1 in values
        assert 3 in values

    def test_low_greater_than_high_fails(self):
        # nv
        sols, _ = simple_solutions(_random_integer_3, 6, 1, Var())
        assert len(sols) == 0

    def test_unbound_args_raise(self):
        # nv
        term = raised(_random_integer_3, Var(), 6, Var())
        assert term == ('error', 'instantiation_error', ('/', 'integer_between', 3))


# ── choice/2 ──────────────────────────────────────────────────────


class TestRandomMember:
    def test_picks_element(self):
        # nv
        x = Var()
        lst = ["a", "b", "c"]
        sols, trail = simple_solutions(_random_member_2, lst, x)
        assert len(sols) == 1
        assert deref(x) in lst

    def test_empty_list_fails(self):
        # nv
        sols, _ = simple_solutions(_random_member_2, [], Var())
        assert len(sols) == 0

    def test_unbound_list_raises(self):
        # nv
        term = raised(_random_member_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'choice', 2))

    def test_trampoline(self):
        # nv
        x = Var()
        sols, trail = trampoline_solutions(choice, ["x", "y"], x)
        assert len(sols) == 1
        assert deref(x) in ["x", "y"]


# ── permutation/2 ────────────────────────────────────────────────


class TestRandomPermutation:
    def test_is_permutation(self):
        # nv
        p = Var()
        sols, trail = simple_solutions(_random_permutation_2, [1, 2, 3], p)
        assert len(sols) == 1
        result = deref(p)
        assert sorted(result) == [1, 2, 3]
        assert len(result) == 3

    def test_empty_list(self):
        # nv
        p = Var()
        sols, trail = simple_solutions(_random_permutation_2, [], p)
        assert len(sols) == 1
        assert deref(p) == []

    def test_unbound_list_raises(self):
        # nv
        term = raised(_random_permutation_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'permutation', 2))


# ── sample/3 ─────────────────────────────────────────────────────


class TestRandomSample:
    def test_correct_length(self):
        # nv
        s = Var()
        sols, trail = simple_solutions(_random_sample_3, [1, 2, 3, 4, 5], 3, s)
        assert len(sols) == 1
        result = deref(s)
        assert len(result) == 3
        assert all(x in [1, 2, 3, 4, 5] for x in result)

    def test_k_zero(self):
        # nv
        s = Var()
        sols, trail = simple_solutions(_random_sample_3, [1, 2, 3], 0, s)
        assert len(sols) == 1
        assert deref(s) == []

    def test_k_greater_than_length_fails(self):
        # nv
        sols, _ = simple_solutions(_random_sample_3, [1, 2], 5, Var())
        assert len(sols) == 0

    def test_unbound_k_raises(self):
        # nv
        term = raised(_random_sample_3, [1, 2, 3], Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'sample', 3))


# ── set_seed/1 ───────────────────────────────────────────────────────


class TestRandomSeed:
    def test_reproducible(self):
        """Seeding produces the same sequence."""
        # nv
        _rng.seed(123)
        x1 = Var()
        trail1 = Trail()
        list(_random_1(x1, trail1, None))
        val1 = deref(x1)

        _rng.seed(123)
        x2 = Var()
        trail2 = Trail()
        list(_random_1(x2, trail2, None))
        val2 = deref(x2)

        assert val1 == val2

    def test_via_predicate(self):
        """set_seed/1 followed by float_0_to_1/1 is reproducible."""
        # nv
        sols1, _ = simple_solutions(_random_seed_1, 42)
        assert len(sols1) == 1
        x1 = Var()
        simple_solutions(_random_1, x1)
        v1 = deref(x1)

        simple_solutions(_random_seed_1, 42)
        x2 = Var()
        simple_solutions(_random_1, x2)
        v2 = deref(x2)

        assert v1 == v2

    def test_unbound_seed_fails(self):
        # nv
        sols, _ = simple_solutions(_random_seed_1, Var())
        assert len(sols) == 0


# ── maybe/0, maybe/1 ───────────────────────────────────────────────────


class TestMaybe:
    def test_maybe_0_roughly_half(self):
        """Over many trials, maybe/0 succeeds ~50% of the time."""
        # nv
        _rng.seed(0)
        successes = 0
        trials = 1000
        for _ in range(trials):
            trail = Trail()
            sols = list(_maybe_0(trail, None))
            if len(sols) > 0:
                successes += 1
        ratio = successes / trials
        assert 0.4 < ratio < 0.6, f"ratio={ratio}"

    def test_maybe_1_always_succeeds(self):
        """maybe(1.0) always succeeds."""
        # nv
        for _ in range(20):
            sols, _ = simple_solutions(_maybe_1, 1.0)
            assert len(sols) == 1

    def test_maybe_1_always_fails(self):
        """maybe(0.0) always fails."""
        # nv
        for _ in range(20):
            sols, _ = simple_solutions(_maybe_1, 0.0)
            assert len(sols) == 0

    def test_maybe_1_unbound_raises(self):
        # nv
        term = raised(_maybe_1, Var())
        assert term == ('error', 'instantiation_error', ('/', 'maybe', 1))

    def test_maybe_trampoline_multi_arity(self):
        """maybe supports both arity 0 and 1 via multi-dispatch."""
        # Arity 0
        # nv
        _rng.seed(1)
        trail = Trail()
        dispatch = maybe._get_dispatch()
        gen = dispatch(None, None, None, None, trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append(value)
        # Just check it runs without error (result depends on seed)

        # Arity 1 — always succeed
        trail = Trail()
        gen = dispatch(None, None, None, None, 1.0, trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append(value)
        assert len(results) == 1
