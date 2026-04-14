"""Slice E1: destructive-reuse pass as ``analyse → apply``.

Per the migration plan §7, each optimisation pass has:

- a **round-trip** test: ``apply(ir, analyse(ir))`` applied twice
  yields the same result as applied once (idempotence);
- a **no-op** test: on bodies where the optimisation doesn't
  apply, ``apply`` returns the IR unchanged;
- a **correctness** test: compiling with the pass on and off
  produces equivalent solutions — this one requires the
  lowering-reads-hints step (later E sub-slice) to be meaningful
  in isolation, so the existing end-to-end ``test_destructive_reuse.py``
  serves that role today.

This file covers round-trip + no-op.
"""

from __future__ import annotations

from clausal.logic.database import Clause
from clausal.logic.variables import Var
from clausal.terms import (
    Compound,
    Evaluate,
    Call, LoadName,
)


def _body_dr_eligible():
    Temp, Extra, Out = Var(), Var(), Var()
    head = Compound("process", (Out,))
    body = [
        Evaluate(left=Temp, right=[1, 2, 3]),
        Call(func=LoadName(name="append"),
             args=[Temp, Extra, Out], kwargs=[]),
    ]
    return head, body


def _body_dr_ineligible():
    """No DR-candidate Call — append(HeadVar, ...) where source is head-var."""
    Old, Extra, Out = Var(), Var(), Var()
    head = Compound("process", (Old, Out))
    body = [Call(func=LoadName(name="append"),
                 args=[Old, Extra, Out], kwargs=[])]
    return head, body


def _body_no_dr_calls_at_all():
    """Body with no DR-candidate calls (not append/dict_put/set_union)."""
    x, y = Var(), Var()
    head = Compound("other", (x, y))
    body = [Call(func=LoadName(name="Helper"), args=[x, y], kwargs=[])]
    return head, body


def test_dr_pass_analyse_returns_plan():
    from clausal.logic.compiler.optimisations import destructive_reuse as dr
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    head, body = _body_dr_eligible()
    ir = terms_to_goalop(body, db=None)
    plan = dr.analyse(ir, head)
    assert isinstance(plan, dr.DRPlan)
    assert plan.eligible  # the append call is eligible
    assert len(plan.eligible) == 1


def test_dr_pass_apply_sets_hint_on_eligible_subcall():
    from clausal.logic.compiler.optimisations import destructive_reuse as dr
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.logic.compiler.ir import SubCall
    head, body = _body_dr_eligible()
    ir = terms_to_goalop(body, db=None)
    plan = dr.analyse(ir, head)
    new_ir = dr.apply(ir, plan)
    # The eligible SubCall should have destructive_reuse=True set.
    marked = [op for op in new_ir.ops
              if isinstance(op, SubCall) and op.destructive_reuse]
    assert len(marked) == 1
    assert marked[0].fname == "append"


def test_dr_pass_apply_is_idempotent():
    """Round-trip: applying twice ≡ applying once."""
    from clausal.logic.compiler.optimisations import destructive_reuse as dr
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    head, body = _body_dr_eligible()
    ir = terms_to_goalop(body, db=None)
    plan = dr.analyse(ir, head)
    once = dr.apply(ir, plan)
    twice_plan = dr.analyse(once, head)
    twice = dr.apply(once, twice_plan)
    # Structural equality is good enough here — dataclass __eq__
    # checks ops list element-by-element.
    assert once == twice


def test_dr_pass_apply_empty_plan_is_noop():
    """No-op: empty plan returns ir unchanged (reference equality)."""
    from clausal.logic.compiler.optimisations import destructive_reuse as dr
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    head, body = _body_no_dr_calls_at_all()
    ir = terms_to_goalop(body, db=None)
    plan = dr.analyse(ir, head)
    assert not plan.eligible
    new_ir = dr.apply(ir, plan)
    assert new_ir is ir  # reference equality — contract documents this


def test_dr_pass_ineligible_body_produces_empty_plan():
    """Head-aliased source means ineligible — plan is empty."""
    from clausal.logic.compiler.optimisations import destructive_reuse as dr
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    head, body = _body_dr_ineligible()
    ir = terms_to_goalop(body, db=None)
    plan = dr.analyse(ir, head)
    assert not plan.eligible


def test_dr_plan_is_hashable():
    """Frozen dataclass contract — plans can go into sets / dict keys."""
    from clausal.logic.compiler.optimisations import destructive_reuse as dr
    p1 = dr.DRPlan(eligible=frozenset({1, 3}))
    p2 = dr.DRPlan(eligible=frozenset({1, 3}))
    assert p1 == p2
    assert hash(p1) == hash(p2)
    assert {p1, p2} == {p1}
