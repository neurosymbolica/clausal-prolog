"""Slice D3: byte-for-byte AST equivalence between legacy goal
compilation and the new GoalOp lowering pipeline.

For each goal in the D2 subset, assert that the AST emitted by:

    compile_goal(goal, ...)                         # legacy path
    lower(terms_to_goalop([goal]).ops[0], ctx, k)   # IR path

is identical under ``ast.dump``.  This is the guarantee the D4
parallel-implementation harness will rely on when it flips the IR
path on globally.

The legacy dispatcher uses strategy-agnostic helpers for the whole D2
subset, so both strategy lowerings are compared (shallow and
trampoline) against the same legacy function — both must match.
"""

from __future__ import annotations

import ast

import pytest

from clausal.pythonic_ast import nodes
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler.strategy import ShallowStrategy, TrampolineStrategy
from clausal.logic.compiler.goal_shallow import compile_goal
from clausal.logic.compiler.goal_trampoline import compile_goal_trampoline
from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
from clausal.logic.compiler.lower_python_shallow import lower as lower_shallow
from clausal.logic.compiler.lower_python_trampoline import lower as lower_trampoline


def _b(cls, l, r):
    return cls(left=l, right=r)


def _k_stmts():
    # A trivially-identifiable continuation so AST-dump diffs pinpoint
    # exactly the lowering output we care about, not the continuation.
    return [ast.Expr(value=ast.Constant(value="K"))]


def _fresh_ctx(strategy):
    return CompilationContext(
        db=None,
        var_context={},
        trail_name="trail",
        strategy=strategy,
    )


def _goalop(goal):
    ir = terms_to_goalop([goal])
    # Subset cases land as a single-op Sequence; unwrap for direct lowering.
    return ir.ops[0]


# ── Parametrised corpus — one goal per D2 case ─────────────────────────────
_CORPUS = [
    ("unify",        _b(nodes.Unify, "X", "Y")),
    ("does_not_unify", _b(nodes.DoesNotUnify, "X", "Y")),
    ("evaluate",     _b(nodes.Evaluate, "X", "Y")),
    ("arith_eq",     _b(nodes.ArithEq, "X", "Y")),
    ("arith_neq",    _b(nodes.ArithNeq, "X", "Y")),
    ("lt",           _b(nodes.Lt, "X", "Y")),
    ("lte",          _b(nodes.LtE, "X", "Y")),
    ("gt",           _b(nodes.Gt, "X", "Y")),
    ("gte",          _b(nodes.GtE, "X", "Y")),
    ("structural_eq",  _b(nodes.StructuralEq, "X", "Y")),
    ("structural_neq", _b(nodes.StructuralNeq, "X", "Y")),
    ("in_",          _b(nodes.in_, "X", "Y")),
    ("not_in",       _b(nodes.NotIn, "X", "Y")),
]


@pytest.mark.parametrize("label,goal", _CORPUS, ids=[c[0] for c in _CORPUS])
def test_lower_shallow_matches_legacy(label, goal):
    legacy_ctx = _fresh_ctx(ShallowStrategy())
    ir_ctx = _fresh_ctx(ShallowStrategy())

    legacy = compile_goal(goal, None, {}, "trail", _k_stmts(), ctx=legacy_ctx)
    new = lower_shallow(_goalop(goal), ir_ctx, _k_stmts())

    assert _dump(legacy) == _dump(new)


@pytest.mark.parametrize("label,goal", _CORPUS, ids=[c[0] for c in _CORPUS])
def test_lower_trampoline_matches_legacy(label, goal):
    legacy_ctx = _fresh_ctx(TrampolineStrategy())
    ir_ctx = _fresh_ctx(TrampolineStrategy())

    legacy = compile_goal_trampoline(goal, None, {}, "trail", _k_stmts(), ctx=legacy_ctx)
    new = lower_trampoline(_goalop(goal), ir_ctx, _k_stmts())

    assert _dump(legacy) == _dump(new)


def test_sequence_right_to_left_matches_legacy_body():
    # Three deterministic goals — legacy compile_body folds right-to-left
    # over ``_dispatch_goal``; IR pipeline wraps in ``Sequence`` and folds
    # identically.  Any drift between the two reductions shows here.
    goals = [
        _b(nodes.Unify, "X", "Y"),
        _b(nodes.Lt, "X", "Z"),
        _b(nodes.in_, "X", "L"),
    ]
    k = _k_stmts()

    legacy_ctx = _fresh_ctx(ShallowStrategy())
    legacy = list(k)
    for g in reversed(goals):
        legacy = compile_goal(g, None, {}, "trail", legacy, ctx=legacy_ctx)

    ir_ctx = _fresh_ctx(ShallowStrategy())
    new = lower_shallow(terms_to_goalop(goals), ir_ctx, k)

    assert _dump(legacy) == _dump(new)


def _dump(stmts):
    return [ast.dump(s) for s in stmts]
