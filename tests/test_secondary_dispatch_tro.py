"""Regression: secondary (hierarchical) dispatch must re-dispatch TRO tail calls.

todo/call-site-specialisation-protocol-questions.md Q2 — the Phase 9c
secondary dispatch's level-0/level-1 buckets are compiled without TRO, but
its fallback is the shared ``{functor}__all``, compiled in SIGNAL mode
(``tro_indices`` set, ``emit_done=False``). Before the fix the secondary
dispatch had no ``tro_state`` loop, so a tail call signalled from the
fallback (unbound indexed arg → fallback route) was silently dropped: the
query returned 0 solutions instead of recursing. Ground-key calls were
unaffected (bucket clauses recurse normally), which is why nothing caught it.
"""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import term_str


@pytest.fixture(scope="module")
def hop_mod():
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "secondary_dispatch_tro.clausal"
    )
    mod = _load_module("tests.fixtures.secondary_dispatch_tro", path)
    return mod


def _solutions(mod, *args):
    lm = mod.__dict__["$module"]
    vals = [Var() if a is None else a for a in args]
    return sorted(term_str(deref(vals[-1]), quoted=False)
                  for _ in call("Hop", *vals, module=lm))


BASE_SOLUTIONS = ["[a1]", "[a2]", "[b1]", "[b2]", "[c1]", "[c2]"]


class TestSecondaryDispatchTro:
    def test_strategy_is_hierarchical(self, hop_mod):
        """Pin the fixture to the secondary-dispatch strategy — if index
        analysis changes and this stops holding, the TRO coverage below
        silently stops exercising the secondary path."""
        # nv
        hop = hop_mod.__dict__["Hop"]
        assert getattr(hop, "_index_plans_hierarchical", None)

    def test_tro_is_active(self, hop_mod):
        """Pin TRO eligibility of the tail-recursive clause — the compiled
        predicate's base_globals carry $tro_state only when the sweep
        selected it. Guards against the test passing vacuously."""
        # nv
        hop = hop_mod.__dict__["Hop"]
        for idx_dict in hop._index_plans.values():
            for wrapper in idx_dict.values():
                for cell in wrapper.__closure__ or ():
                    g = getattr(cell.cell_contents, "__globals__", None)
                    if isinstance(g, dict) and "$tro_state" in g:
                        return
        pytest.fail("no compiled bucket carries $tro_state — TRO not active")

    def test_base_case_unbound_keys(self, hop_mod):
        # nv
        assert _solutions(hop_mod, None, None, 0, None) == BASE_SOLUTIONS

    def test_ground_key_recursion(self, hop_mod):
        """Control: bucket-routed recursion (compiled without TRO) works."""
        # nv
        assert _solutions(hop_mod, mint("a"), 1, 2, None) == ["[a1]"]

    def test_unbound_key_recursion_via_fallback(self, hop_mod):
        """THE regression: unbound K routes to the SIGNAL-mode fallback;
        its TRO tail call must be re-dispatched, not dropped."""
        # nv
        assert _solutions(hop_mod, None, None, 2, None) == BASE_SOLUTIONS

    def test_unbound_key_deep_recursion(self, hop_mod):
        # nv
        assert _solutions(hop_mod, None, None, 7, None) == BASE_SOLUTIONS

    def test_unbound_key_negative_terminates(self, hop_mod):
        # nv
        assert _solutions(hop_mod, None, None, -1, None) == ["[neg]"]


def _solutions2(mod, *args):
    lm = mod.__dict__["$module"]
    vals = [Var() if a is None else a for a in args]
    return sorted(term_str(deref(vals[-1]), quoted=False)
                  for _ in call("Hop2", *vals, module=lm))


class TestSecondaryDispatchTroBucketLanding:
    """Hop2's recursive clause binds the level-0 key, so the re-dispatched
    tail call must land in a level-0 bucket — the other branch of the
    secondary TRO loop (Hop only re-enters the fallback)."""

    def test_strategy_is_hierarchical(self, hop_mod):
        # nv
        hop2 = hop_mod.__dict__["Hop2"]
        assert getattr(hop2, "_index_plans_hierarchical", None)

    def test_redispatch_lands_in_bucket(self, hop_mod):
        """Unbound start signals from the fallback; the updated args are
        ground ("a", 1) and must route into that level-0/level-1 bucket."""
        # nv
        assert _solutions2(hop_mod, None, None, 3, None) == ["[a1]"]

    def test_ground_other_bucket_start(self, hop_mod):
        # nv
        assert _solutions2(hop_mod, mint("b"), 2, 2, None) == ["[a1]"]
