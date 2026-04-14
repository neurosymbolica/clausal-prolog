"""Slice E3: call-site bucket-ref as ``analyse → apply``.

Same three-property contract as E1 and E2.  Correctness coverage
(end-to-end bucket-ref dispatch behaviour) stays in the existing
`test_callsite_specialization.py`.
"""

from __future__ import annotations

from clausal.logic.database import Clause
from clausal.logic.variables import Var
from clausal.terms import Compound, Call, LoadName

# Re-use helpers from the legacy callsite test file.
from tests.test_callsite_specialization import _make_locked_pred_cls


def _case_eligible_literal_arg():
    callee_cls, _ = _make_locked_pred_cls("color_e3", [
        ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
    ])
    x = Var()
    body = [Call(func=LoadName(name="color_e3"), args=["red", x], kwargs=[])]
    clause = Clause(head=Compound("caller", (x,)), body=body)
    base_globals = {"color_e3": callee_cls}
    return clause, base_globals


def _case_ineligible_variable_arg():
    callee_cls, _ = _make_locked_pred_cls("color_e3v", [
        ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
    ])
    x, y = Var(), Var()
    body = [Call(func=LoadName(name="color_e3v"), args=[y, x], kwargs=[])]
    clause = Clause(head=Compound("caller", (x,)), body=body)
    base_globals = {"color_e3v": callee_cls}
    return clause, base_globals


def test_call_site_pass_analyse_eligible():
    from clausal.logic.compiler.optimisations import call_site
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    clause, base_globals = _case_eligible_literal_arg()
    ir = terms_to_goalop(clause.body, db=None)
    plan = call_site.analyse(ir, clause.head, base_globals)
    assert isinstance(plan, call_site.CallSitePlan)
    assert len(plan.hints) == 1
    op_idx, gkey = plan.hints[0]
    assert op_idx == 0
    assert "red" in gkey


def test_call_site_pass_apply_sets_direct_bucket_ref():
    from clausal.logic.compiler.optimisations import call_site
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.logic.compiler.ir import SubCall
    clause, base_globals = _case_eligible_literal_arg()
    ir = terms_to_goalop(clause.body, db=None)
    plan = call_site.analyse(ir, clause.head, base_globals)
    new_ir = call_site.apply(ir, plan)
    marked = [op for op in new_ir.ops
              if isinstance(op, SubCall) and op.direct_bucket_ref]
    assert len(marked) == 1
    assert "red" in marked[0].direct_bucket_ref


def test_call_site_pass_apply_is_idempotent():
    from clausal.logic.compiler.optimisations import call_site
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    clause, base_globals = _case_eligible_literal_arg()
    ir = terms_to_goalop(clause.body, db=None)
    plan = call_site.analyse(ir, clause.head, base_globals)
    once = call_site.apply(ir, plan)
    twice_plan = call_site.analyse(once, clause.head, base_globals)
    twice = call_site.apply(once, twice_plan)
    assert once == twice


def test_call_site_pass_ineligible_body_empty_plan():
    from clausal.logic.compiler.optimisations import call_site
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    clause, base_globals = _case_ineligible_variable_arg()
    ir = terms_to_goalop(clause.body, db=None)
    plan = call_site.analyse(ir, clause.head, base_globals)
    assert not plan.hints
    new_ir = call_site.apply(ir, plan)
    assert new_ir is ir


def test_call_site_plan_is_hashable():
    from clausal.logic.compiler.optimisations import call_site
    p1 = call_site.CallSitePlan(
        hints=((0, "_bucket_foo_0_red"),),
        joint_hints=(),
    )
    p2 = call_site.CallSitePlan(
        hints=((0, "_bucket_foo_0_red"),),
        joint_hints=(),
    )
    assert p1 == p2
    assert hash(p1) == hash(p2)


def test_call_site_pass_matches_legacy_gkey():
    """The IR-side plan's gkey must equal what legacy writes to
    ``ctx.bucket_ref_map`` (byte parity guarantee for D7c)."""
    from clausal.logic.compiler.optimisations import call_site
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.logic.compiler import _inject_bucket_refs_trampoline
    from clausal.logic.compiler.compile_ctx import CompilationContext

    clause, base_globals = _case_eligible_literal_arg()
    legacy_globals = dict(base_globals)
    ctx = CompilationContext(
        db=None, var_context={}, trail_name="trail",
    )
    _inject_bucket_refs_trampoline(ctx, [clause], legacy_globals)
    legacy_gkeys = set(ctx.bucket_ref_map.values())

    ir = terms_to_goalop(clause.body, db=None)
    plan = call_site.analyse(ir, clause.head, base_globals)
    ir_gkeys = {gkey for _, gkey in plan.hints}

    assert ir_gkeys == legacy_gkeys, (
        f"gkey mismatch — legacy={legacy_gkeys}, ir={ir_gkeys}"
    )
