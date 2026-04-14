"""Defensive: the D4 IR-path harness is actually exercising the IR
lowering, not silently falling back on every compile.

The D4 AST-diff gate catches *drift* when both paths run but emit
different AST.  It does **not** catch the case where the IR path
silently falls back for every clause (e.g. because a module scrub
caused ``nodes.Not`` captured in ``terms_to_goalop`` to miss all
new ``Not`` instances).  That would look like "10463 passed" with
zero actual IR coverage.

These tests compile small bodies that are fully inside the current
IR subset and assert the IR path matched legacy — i.e. the harness
really ran and really agreed.
"""

from __future__ import annotations

import ast

import pytest

from clausal.pythonic_ast import nodes
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler.strategy import ShallowStrategy, TrampolineStrategy
from clausal.logic.compiler.goal_shallow import (
    _IR_PATH_STATS,
    _ir_path_stats_reset,
    _compile_body_impl,
)


def _b(cls, l, r):
    return cls(left=l, right=r)


def _ctx(strategy):
    return CompilationContext(
        db=None,
        var_context={},
        trail_name="trail",
        strategy=strategy,
        use_ir_path=True,
    )


@pytest.mark.parametrize("strategy_cls", [ShallowStrategy, TrampolineStrategy])
def test_ir_path_runs_and_matches_on_d_subset(strategy_cls):
    _ir_path_stats_reset()
    # A body built entirely from D2+D5a+D5b+D5c constructs so the IR
    # path must convert and lower successfully.
    body = [
        _b(nodes.And,
           _b(nodes.Unify, "X", "Y"),
           _b(nodes.Or,
              _b(nodes.Lt, "X", "Z"),
              nodes.Not(operand=_b(nodes.in_, "X", "L")))),
    ]
    _compile_body_impl(body, _ctx(strategy_cls()))
    assert _IR_PATH_STATS["runs"] == 1, _IR_PATH_STATS
    assert _IR_PATH_STATS["fallbacks"] == 0, (
        "IR path silently fell back — terms_to_goalop raised "
        "NotImplementedError on a body that is fully inside the "
        f"supported subset.  Stats: {_IR_PATH_STATS}"
    )
    assert _IR_PATH_STATS["matches"] == 1, _IR_PATH_STATS


def test_ir_path_fallback_is_counted_on_unsupported_op():
    _ir_path_stats_reset()
    # Star-list unification (``X is [*T]``) routes through
    # ``_compile_star_is`` in the legacy path and is deferred to
    # Slice D5g's :class:`ListPatternUnify` coverage, so this body
    # must fall back.  Legacy ``_compile_star_is`` requires the
    # surrounding term machinery so we exercise the fallback through
    # ``terms_to_goalop`` directly rather than the full harness.
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    with pytest.raises(NotImplementedError):
        terms_to_goalop([nodes.Unify(
            left=[nodes.StarUnpack(value="T")], right="X",
        )])
