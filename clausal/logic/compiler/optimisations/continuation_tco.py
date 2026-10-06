"""Continuation-level tail-call optimisation — analyse / apply pass.

Marks :attr:`~clausal.logic.compiler.ir.SubCall.tail_position` on every
:class:`SubCall` reached through tail-only paths from the clause body
root.  Trampoline lowering consumes the hint by emitting the child's
``StepGenerator`` with the caller's own ``_proceed`` in the solution
slot — solutions bypass the caller's frame while ``fail`` and
``catcher`` still route through it, so per-clause cleanup (``finally:
trail.undo(_mark)``) and backtracking (next clause / next ``for``
iteration / enclosing choice point) run correctly on exhaustion.

See ``implementation_plans/compiler/CONTINUATION_TCO_PLAN.md`` §5.1 for the
precise recursion.  Mutually exclusive with TRO
(``tail_recursive=True``); TRO wins and is a richer special case —
the pass skips any :class:`SubCall` TRO has already marked.

Trampoline-only.  ``ShallowStrategy`` doesn't emit ``StepGenerator``s
so the hint is unreachable; the pass is gated at the call site.

Contract (mirrors ``tro.py`` / ``destructive_reuse.py`` /
``call_site.py``):

- ``analyse(ir) -> ContinuationTCOPlan`` is pure; plan carries a
  frozenset of ``id(op)`` for the :class:`SubCall`\\s to mark.
- ``apply(ir, plan) -> ir`` is idempotent.  Empty plan returns *ir*
  unchanged (reference equality).  Non-empty plan returns a new IR
  tree with ``tail_position=True`` on every :class:`SubCall` whose
  ``id`` appears in ``plan.marks``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..ir import (
    Alternate,
    Branch,
    GoalOp,
    Sequence,
    SubCall,
)


@dataclasses.dataclass(frozen=True)
class ContinuationTCOPlan:
    """Ids of :class:`SubCall` ops to mark ``tail_position=True``."""
    marks: frozenset


def analyse(ir: Any) -> ContinuationTCOPlan:
    """Find every :class:`SubCall` in tail position within *ir*.

    Walks :class:`Sequence`\\'s last op, every arm of
    :class:`Alternate`, and both arms of :class:`Branch` (but not the
    test — its solutions are committed-choice).  :class:`Negate`,
    :class:`MetaCall`, and all leaf ops terminate the walk —
    solutions of their inner goals are observed, so the enclosing
    TCO would leak.
    """
    marks: set[int] = set()
    _walk(ir, marks)
    return ContinuationTCOPlan(marks=frozenset(marks))


def _walk(node: GoalOp, marks: set[int]) -> None:
    match node:
        case Sequence(ops=ops) if ops:
            _walk(ops[-1], marks)
        case Alternate(ops=ops):
            for op in ops:
                _walk(op, marks)
        case Branch(then=then, else_=else_):
            # test is NOT tail — solutions are committed-choice.
            # both arms inherit the outer continuation.
            _walk(then, marks)
            _walk(else_, marks)
        case SubCall() if not node.tail_recursive:
            marks.add(id(node))
        # Everything else — Negate, MetaCall, Unify, Dif,
        # StructuralEq, ArithEval, FDCompare, MemberIn,
        # ListPatternUnify, Fail, PyThunkOp, empty Sequence,
        # tail-recursive SubCall — terminates the walk.
        case _:
            return


def apply(ir: Any, plan: ContinuationTCOPlan) -> Any:
    """Rewrite *ir* by setting ``tail_position=True`` on each marked
    :class:`SubCall`.

    Empty plan → *ir* unchanged.  Non-empty plan returns a fresh tree
    (only the spine down to each mark is rebuilt; untouched subtrees
    share structure).
    """
    if not plan.marks:
        return ir
    return _rewrite(ir, plan.marks)


def _rewrite(node: GoalOp, marks: frozenset) -> GoalOp:
    if isinstance(node, Sequence):
        if not node.ops:
            return node
        new_ops = list(node.ops)
        new_ops[-1] = _rewrite(new_ops[-1], marks)
        return Sequence(ops=new_ops) if new_ops[-1] is not node.ops[-1] else node
    if isinstance(node, Alternate):
        new_ops = [_rewrite(op, marks) for op in node.ops]
        changed = any(a is not b for a, b in zip(new_ops, node.ops))
        return Alternate(ops=new_ops) if changed else node
    if isinstance(node, Branch):
        new_then = _rewrite(node.then, marks)
        new_else = _rewrite(node.else_, marks)
        if new_then is node.then and new_else is node.else_:
            return node
        return dataclasses.replace(node, then=new_then, else_=new_else)
    if isinstance(node, SubCall) and id(node) in marks:
        return dataclasses.replace(node, tail_position=True)
    return node


__all__ = ["ContinuationTCOPlan", "analyse", "apply"]
