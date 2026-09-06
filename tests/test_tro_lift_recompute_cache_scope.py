"""F1 regression (P3-2 whole-branch final review): the TRO recompute cache
in ``_build_predicate_trampoline_funcdef``'s ``_tro_aware_bc`` closure
(clausal/logic/compiler/predicate.py) used to read/write
``ctx_template.clause_tro_plans`` / ``clause_ir_cache`` -- dicts owned by
``ctx_template`` and SHARED across every bucket/default/fallback call to
``_build_predicate_trampoline_funcdef`` for one predicate compile -- keyed
by ``id(clause)`` on the POST-lift clause object.

Each indexed bucket's ``lifted_bucket`` list (predicate.py's per-position
plan-building loop) is a fresh local rebound every iteration with no other
referent, so its ``Clause`` objects are freed as soon as that bucket's
funcdef is built. CPython recycles freed small-object addresses immediately,
so a LATER bucket's lift can mint a brand-new ``Clause`` at the SAME id as
an earlier, now-dead one. The old code read
``_ctx.clause_tro_plans.get(id(clause))`` BEFORE checking for a cache miss,
so a recycled id produced a false HIT: the stale plan (and stale body IR)
computed for the EARLIER, unrelated clause's body was silently reused for
the new one -- a miscompile the ``id(clause) in _tset`` guard cannot catch,
since colliding clauses are in ``_tset`` by construction (each bucket
builds its own ``_tset`` from its own ``clauses``).

Fixed by giving the recompute its own cache, LOCAL to each
``_build_predicate_trampoline_funcdef`` call -- see the fix's comment in
predicate.py.  Deterministic id-reuse is not reliably testable (CPython's
allocator behavior isn't a public contract), so this file pins two things
instead: (1) end-to-end correctness through the recompute path, and (2) the
STRUCTURAL property the chosen fix guarantees -- the shared
``ctx_template`` caches never grow past what the initial (pre-lift)
``_sweep_tro_eligible`` pass wrote, i.e. the bucket recompute never touches
them again.

Fixture: tests/fixtures/tro_lift_recompute_cache.clausal -- two
independent str-keyed buckets, "a" and "b", each indexed (first-arg str
literal, 7 clauses total > ``_INDEX_THRESHOLD``), TRO-eligible (tail
recursion), and -- since P3-2 Task 4/R8 retired the str half of the
lift-skip -- lift-eligible (the literal key is lifted straight into the
bucket's head pattern). "b"'s recursive clause carries one extra prefix
goal so a stale cross-bucket plan reuse would misplace the tail-call split
rather than silently agreeing with "a"'s.
"""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.import_hook import _load_module
from clausal.logic.compiler import predicate as predicate_mod
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import Sub

_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "tro_lift_recompute_cache.clausal"
)


def _reduce(term):
    """Fold a (possibly still-symbolic) ``Sub`` chain down to an int.

    ``is`` in this pipeline binds eagerly for a literal RHS but passes a
    bare-Var RHS through unreduced, so a solution can come back as e.g.
    ``Sub(left=Sub(left=4, right=1), right=1)`` instead of ``2`` -- reduce
    it ourselves rather than relying on incidental repr equality.
    """
    if isinstance(term, Sub):
        return _reduce(term.left) - _reduce(term.right)
    return term


@pytest.fixture()
def loaded():
    """Load the fixture with ``_sweep_tro_eligible`` spied on, drive both
    lift-eligible TRO buckets to completion, and hand back (answers,
    (ctx_template, original_clause_count))."""
    captured: list[tuple[object, int]] = []
    _orig_sweep = predicate_mod._sweep_tro_eligible

    def _spy(clauses_, functor, arity, db_, ctx_template):
        result = _orig_sweep(clauses_, functor, arity, db_, ctx_template)
        if functor == "Cnt" and arity == 3:
            captured.append((ctx_template, len(clauses_)))
        return result

    predicate_mod._sweep_tro_eligible = _spy
    try:
        mod = _load_module(
            "tests.fixtures.tro_lift_recompute_cache_scope_mod", _FIXTURE
        )
        lm = mod.__dict__["$module"]
        # Drive "a" then "b" back-to-back: "a"'s lifted bucket clauses are
        # freed right before "b"'s recompute runs -- the old bug's best
        # chance at an id collision.
        results = {}
        for key in ("a", "b"):
            k = Var()
            results[key] = [deref(k) for _ in call("Cnt", key, 4, k, module=lm)]
    finally:
        predicate_mod._sweep_tro_eligible = _orig_sweep

    assert captured, (
        "_sweep_tro_eligible never ran for Cnt/3 -- fixture isn't "
        "exercising TRO; this test can't pin anything until it does"
    )
    return results, captured[0]


class TestTroLiftRecomputeCacheScope:
    def test_correct_answers_for_both_lift_eligible_tro_buckets(self, loaded):
        """Both recursive buckets ("a": 2 prefix goals, "b": 3 prefix
        goals before the tail call) must independently count Cnt(key, 4, X)
        down to X=0. A cross-bucket plan mix-up would misplace the
        tail-call split and either crash the compile or bind the wrong
        value -- not merely disagree by coincidence."""
        results, _ctx_info = loaded
        for key in ("a", "b"):
            got = results[key]
            assert len(got) == 5, (key, got)
            # Deepest solution: 4 - 1 - 1 - 1 - 1 == 0 -- recursion ran
            # exactly 4 times regardless of "b"'s extra prefix goal.
            assert _reduce(got[0]) == 0, (key, got)
            # Shallowest solution: the top-level call's own N, untouched.
            assert _reduce(got[-1]) == 4, (key, got)

    def test_recompute_does_not_grow_the_shared_ctx_template_caches(self, loaded):
        """Structural pin for the chosen fix: the recompute inside
        ``_tro_aware_bc`` must use its OWN per-funcdef-call cache, never
        writing into ``ctx_template.clause_tro_plans`` /
        ``clause_ir_cache``. Those two dicts are populated exactly once,
        by the initial ``_sweep_tro_eligible`` pass over the PRE-lift
        clause list -- one entry per original clause. Under the old code
        the bucket recompute wrote POST-lift clause ids into these SAME
        shared dicts, so a predicate with lift-eligible TRO buckets (like
        this fixture's "a" and "b") would leave them larger than the
        original clause count. Post-fix they must stay exactly at that
        count no matter how many recompute-eligible buckets got compiled.
        """
        _results, (ctx_template, n_original) = loaded
        assert ctx_template.clause_tro_plans is not None
        assert ctx_template.clause_ir_cache is not None
        assert len(ctx_template.clause_tro_plans) == n_original, (
            "clause_tro_plans grew past the pre-lift sweep count "
            f"({n_original}) -- the bucket recompute is writing into the "
            "shared ctx_template cache again (id-recycling hazard reopened)"
        )
        assert len(ctx_template.clause_ir_cache) == n_original, (
            "clause_ir_cache grew past the pre-lift sweep count "
            f"({n_original}) -- the bucket recompute's temporary IR stash "
            "was not popped after use"
        )
