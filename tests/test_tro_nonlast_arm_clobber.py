"""Regression: signal-mode TRO flag must survive re-entrancy from a sibling
goal while a NON-last tail-recursive clause has a pending tail call.

todo/tro-signal-flag-clobbered-by-later-match-arms.md — a signal-mode TRO
clause sets the shared ``$tro_state`` flag and falls through; a later match
arm that yields a solution suspends the bucket generator while the flag is
still pending.  Any re-entry into the same predicate during that suspension
(here, the sibling ``prc("w", 0, _)`` conjunct) resets ``$tro_state[0]`` at
its dispatch-loop entry, destroying the pending tail call — the enclosing
loop then sees ``False`` and drops the tail, silently losing solutions.

Before the fix ``drv(X)`` returned 1 solution instead of 3.
"""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


@pytest.fixture(scope="module")
def prc_mod():
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "tro_nonlast_arm_clobber.seam"
    )
    return _load_module("tests.fixtures.tro_nonlast_arm_clobber", path)


def _prc_solutions(mod, k, n):
    lm = mod.__dict__["$module"]
    x = Var()
    return sorted((deref(x) for _ in call("prc", k, n, x, module=lm)), key=repr)


def _drv_solutions(mod):
    lm = mod.__dict__["$module"]
    x = Var()
    return sorted((deref(x) for _ in call("drv", x, module=lm)), key=repr)


class TestTroNonLastArmClobber:
    def test_tro_is_active(self, prc_mod):
        """Guard against a vacuous pass: the fixture must actually compile the
        recursive clause in signal-mode TRO (bucket carries ``$tro_state``)."""
        prc_row = prc_mod.__dict__["$module"].db.row("prc", 3)
        assert prc_row is not None and prc_row.clauses
        for idx_dict in prc_row.index_plans.values():
            for wrapper in idx_dict.values():
                for cell in wrapper.__closure__ or ():
                    g = getattr(cell.cell_contents, "__globals__", None)
                    if isinstance(g, dict) and "$tro_state" in g:
                        return
        pytest.fail("no compiled bucket carries $tro_state — TRO not active")

    def test_recursion_alone(self, prc_mod):
        """Baseline: the tail recursion yields all three solutions on its own."""
        assert len(_prc_solutions(prc_mod, mint("k"), 2)) == 3

    def test_sibling_reentry_preserves_solutions(self, prc_mod):
        """THE regression: a deterministic sibling goal after the recursive
        call must not drop any solutions.  drv(X) := prc("k",2,X), prc("w",0,_)
        — the sibling re-enters dispatch while the tail flag is pending."""
        alone = _prc_solutions(prc_mod, mint("k"), 2)
        drv = _drv_solutions(prc_mod)
        assert drv == alone
        assert len(drv) == 3


def test_nonlast_tro_arm_answers_in_clause_order(prc_mod):
    """todo/done/tro-nonlast-arm-solution-order.md: signal-mode TRO on a
    NON-last clause used to yield the later arm's answers before the tail
    recursion's (2, 1, 0).  Clause order is the recursion's deepest answer
    first: N - 1 - 1 (0), then N - 1 (1), then N (2).  No longer reproduces
    on f01790d2; this pins the order (the tests above sort)."""
    lm = prc_mod.__dict__["$module"]
    x = Var()
    got = [str(deref(x)) for _ in call("prc", mint("k"), 2, x, module=lm)]
    assert got == ["2 - 1 - 1", "2 - 1", "2"]
