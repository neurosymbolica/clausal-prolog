"""Slice D6c parallel-implementation harness for call-site bucket-ref analysis.

For each clause shape exercised by ``tests/test_callsite_specialization.py``'s
``TestInjectBucketRefs``, run both:

- legacy :func:`_inject_bucket_refs_trampoline` (mutates
  ``ctx.bucket_ref_map`` / ``ctx.joint_bucket_ref_map`` and ``base_globals``,
  walks ``clause.body`` directly), and
- IR-side :func:`analyse_ir_bucket_refs` (walks the
  :class:`Sequence` produced by ``terms_to_goalop``).

…and assert the entries the IR walker would inject equal what legacy
actually injected (on flat bodies — the wider cross-check inside
``_inject_bucket_refs_trampoline`` itself, gated by
``CLAUSAL_IR_PATH=1``, applies the same equality check across every
real predicate compilation in the suite, plus a "IR ⊇ legacy" check
on non-flat bodies).
"""

from __future__ import annotations

import pytest

from clausal.logic.database import Clause
from clausal.logic.predicate import PredicateMeta
from clausal.logic.variables import Var
from clausal.terms import Compound, Call, LoadName

# Re-use helpers from the legacy callsite test file.
from tests.test_callsite_specialization import (
    _make_locked_pred_cls, _mkctx, _make_pred_cls,
)


def _case_literal_arg():
    callee_cls, _ = _make_locked_pred_cls("color_lit", [
        ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
    ])
    x = Var()
    body = [Call(func=LoadName(name="color_lit"), args=["red", x], kwargs=[])]
    return ("literal_arg", callee_cls, "color_lit", Clause(
        head=Compound("caller", (x,)), body=body,
    ))


def _case_variable_arg():
    callee_cls, _ = _make_locked_pred_cls("color_var", [
        ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
    ])
    x, y = Var(), Var()
    body = [Call(func=LoadName(name="color_var"), args=[y, x], kwargs=[])]
    return ("variable_arg", callee_cls, "color_var", Clause(
        head=Compound("caller", (x,)), body=body,
    ))


def _case_unlocked_predicate():
    callee_cls, _ = _make_locked_pred_cls("color_unl", [
        ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
    ])
    callee_cls._locked = False
    x = Var()
    body = [Call(func=LoadName(name="color_unl"), args=["red", x], kwargs=[])]
    return ("unlocked_predicate", callee_cls, "color_unl", Clause(
        head=Compound("caller", (x,)), body=body,
    ))


def _case_unknown_key():
    callee_cls, _ = _make_locked_pred_cls("color_unk", [
        ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
    ])
    x = Var()
    body = [Call(func=LoadName(name="color_unk"), args=["orange", x], kwargs=[])]
    return ("unknown_key", callee_cls, "color_unk", Clause(
        head=Compound("caller", (x,)), body=body,
    ))


_CASES = [
    _case_literal_arg(),
    _case_variable_arg(),
    _case_unlocked_predicate(),
    _case_unknown_key(),
]


@pytest.mark.parametrize(
    "name,callee_cls,callee_name,clause",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_bucket_refs_analyse_ir_agrees_with_legacy(
    name, callee_cls, callee_name, clause,
):
    # Function-local imports survive the boundary-test sys.modules
    # scrub.  See Slice D6a commit message for the full hazard write-up.
    from clausal.logic.compiler import _inject_bucket_refs_trampoline
    from clausal.logic.compiler.goal_trampoline import analyse_ir_bucket_refs

    base_globals_legacy = {callee_name: callee_cls}
    ctx_legacy = _mkctx()
    _inject_bucket_refs_trampoline(ctx_legacy, [clause], base_globals_legacy)
    legacy_br = dict(ctx_legacy.bucket_ref_map)
    legacy_jbr = dict(ctx_legacy.joint_bucket_ref_map)

    base_globals_ir = {callee_name: callee_cls}
    ir_br, ir_jbr = analyse_ir_bucket_refs([clause], base_globals_ir)

    assert ir_br == legacy_br, (
        f"{name}: single-bucket disagreement — "
        f"legacy={legacy_br}, ir={ir_br}"
    )
    assert ir_jbr == legacy_jbr, (
        f"{name}: joint-bucket disagreement — "
        f"legacy={legacy_jbr}, ir={ir_jbr}"
    )
