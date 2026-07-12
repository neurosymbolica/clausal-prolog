"""Regression: ground-argument calls to IMPORTED indexed predicates.

todo/call-site-imported-ground-arg-4plus-clauses-runtime-error.md — a call
site inside a compiled clause, targeting an imported predicate that is
already locked with >= _INDEX_THRESHOLD clauses and head constants, compiles
to a direct bucket reference.  Before the fix the raw SIGNAL-mode bucket was
bound, which violates the trampoline contract and raised

    RuntimeError: StepGenerator inner generator returned unexpectedly
    (no final yield)

(pre-A04 it manifested as a silent 0-solutions wrong answer).
"""

from __future__ import annotations

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call


@pytest.fixture(scope="module")
def use_mod():
    # Loaded once per module — atoms and functor classes are module-scoped,
    # so tests must not mix objects across separate loads.
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "callsite_bucket_use.clausal"
    )
    mod = _load_module("tests.fixtures.callsite_bucket_use", path)
    return mod.__dict__["$module"]


class TestImportedGroundCallSite:
    def test_first_clause(self, use_mod):
        # nv
        assert len(list(call("GroundFirst", module=use_mod))) == 1

    def test_middle_clause(self, use_mod):
        # nv
        assert len(list(call("GroundMiddle", module=use_mod))) == 1

    def test_last_clause(self, use_mod):
        # nv
        assert len(list(call("GroundLast", module=use_mod))) == 1

    def test_ground_miss_terminates_with_no_solutions(self, use_mod):
        # nv
        assert list(call("GroundMiss", module=use_mod)) == []

    def test_tail_call_redispatches(self, use_mod):
        """The bucket's TRO tail call must re-dispatch, not be dropped."""
        # nv
        assert len(list(call("GroundTail", 6, module=use_mod))) == 1

    def test_tail_call_redispatch_failure_terminates(self, use_mod):
        # 7 → 5 → 3 → 1, and BucketSteps(1, "even") has no solution.
        # nv
        assert list(call("GroundTail", 7, module=use_mod)) == []
