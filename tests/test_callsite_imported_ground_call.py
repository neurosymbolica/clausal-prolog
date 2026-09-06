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

from clausal.logic.atoms import char_atom, mint
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


@pytest.fixture(scope="module")
def tabled_use_mod():
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "callsite_tabled_use.clausal"
    )
    mod = _load_module("tests.fixtures.callsite_tabled_use", path)
    return mod.__dict__["$module"]


class TestImportedTabledCallSite:
    """A ground call site must NOT be bucket-specialised when the imported
    callee is tabled — a direct bucket ref bypasses the tabling wrapper
    (answer dedup, SLG suspension, WFS/NAF semantics)."""

    def _lib(self):
        import sys
        lib = sys.modules["tests.fixtures.callsite_tabled_lib"]
        return lib.__dict__["TCat"], lib.__dict__["$module"]

    def test_fixture_is_actually_tabled(self, tabled_use_mod):
        # Guard against the silent-no-op dangling -table directive.
        # nv
        _, lib_lm = self._lib()
        assert lib_lm.db.is_tabled("TCat", 2)

    def test_direct_call_dedups(self, tabled_use_mod):
        """Control: the wrapped dispatch dedups the two "a"-clause answers."""
        # nv
        assert len(list(call("TCat", 1, "a", module=tabled_use_mod))) == 1

    def test_ground_call_site_respects_tabling(self, tabled_use_mod):
        """The compiled ground call site must see the same deduped answers."""
        # nv
        assert len(list(call("TabledGround", module=tabled_use_mod))) == 1

    def test_tabled_callee_not_specialised(self, tabled_use_mod):
        """No bucket refs may exist for a tabled callee."""
        # nv
        tcat, _ = self._lib()
        assert getattr(tcat, "_index_plans", {}) == {}
        caller = tabled_use_mod.module_dict["TabledGround"]
        caller_globals = caller._dispatch_fn.__globals__
        assert not any("TCat.bucket(" in k for k in caller_globals)


class TestImportedGroundCallSiteMultiSolution:
    """A multi-clause caller distinguishes a missing terminal DONE under the
    pure-Python trampoline as well: its fallback driver converts a premature
    generator return into exhaustion, silently TRUNCATING later solutions —
    single-solution callers cannot observe that failure mode."""

    def test_multi_clause_caller_yields_all_solutions(self, use_mod):
        # nv
        from clausal.logic.variables import Var, deref
        r = Var()
        results = sorted(
            str(deref(r)) for _ in call("Multi", r, module=use_mod)
        )
        assert results == [mint("one"), mint("two")]


@pytest.fixture(scope="module")
def joint_use_mod():
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "callsite_joint_use.clausal"
    )
    mod = _load_module("tests.fixtures.callsite_joint_use", path)
    return mod.__dict__["$module"]


class TestImportedJointGroundCallSite:
    """Both-args-ground call sites against a flat-joint indexed import drive
    the wrapped JOINT bucket (direct_joint_bucket_ref / _joint_exposed)."""

    def test_joint_callee_is_specialised(self, joint_use_mod):
        """Pin the strategy: the caller must carry a joint bucket gkey —
        if joint exposure silently stops, this coverage evaporates."""
        # nv
        import sys
        lib = sys.modules["tests.fixtures.callsite_joint_lib"]
        assert getattr(lib.__dict__["JCat"], "_index_plans_joint", None)
        caller = joint_use_mod.module_dict["JBoth"]
        # The compiled clause must reference the JOINT gkey (joint hints are
        # preferred over single-position ones) — co_names pins the emission,
        # not just the globals injection.
        assert any(
            ".JCat.bucket(pos=(" in n
            for n in caller._dispatch_fn.__code__.co_names
        )

    def test_joint_ground_hit(self, joint_use_mod):
        # nv
        assert len(list(call("JBoth", module=joint_use_mod))) == 1

    def test_joint_ground_miss_terminates(self, joint_use_mod):
        # nv
        assert list(call("JMiss", module=joint_use_mod)) == []

    def test_joint_multi_clause_caller(self, joint_use_mod):
        # nv
        from clausal.logic.variables import Var, deref
        r = Var()
        results = sorted(
            str(deref(r)) for _ in call("JTwo", r, module=joint_use_mod)
        )
        assert results == [mint("one"), mint("two")]


@pytest.fixture(scope="module")
def throw_use_mod():
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "callsite_throw_use.clausal"
    )
    mod = _load_module("tests.fixtures.callsite_throw_use", path)
    return mod.__dict__["$module"]


class TestImportedCallSiteExceptions:
    """Exceptions thrown inside a directly-driven wrapped bucket must route
    through the catcher chain like any dispatch-driven call."""

    def test_throw_through_bucket_ref_is_catchable(self, throw_use_mod):
        # nv
        from clausal.logic.variables import Var, deref
        r = Var()
        results = [str(deref(r)) for _ in call("CatchIt", r, module=throw_use_mod)]
        assert results == [mint("caught")]

    def test_non_throwing_bucket_unaffected(self, throw_use_mod):
        # nv
        from clausal.logic.variables import Var, deref
        r = Var()
        results = [str(deref(r)) for _ in call("PassThru", r, module=throw_use_mod)]
        assert results == [mint("ok")]
