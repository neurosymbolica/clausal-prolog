"""``terms_to_goalop`` — convert a clause body (term/AST-node list) into
a :class:`~clausal.logic.compiler.ir.GoalOp` tree.

Slice D2 prototype: handles the binding / constraint / membership subset
plus list-body and ``TupleLiteral`` conjunction.  Everything else raises
``NotImplementedError`` via :func:`_not_yet` so the D4 parallel-implementation
harness can fall back to the legacy path cleanly.

Subset covered:

- ``nodes.Unify`` / ``nodes.DoesNotUnify`` → :class:`Unify` / :class:`Dif`
- ``nodes.Evaluate`` (``LHS := RHS``) → :class:`ArithEval`
- ``nodes.Lt`` / ``LtE`` / ``Gt`` / ``GtE`` / ``ArithEq`` / ``ArithNeq``
  → :class:`FDCompare`
- ``nodes.StructuralEq`` / ``StructuralNeq`` → :class:`StructuralEq`
- ``nodes.in_`` / ``NotIn`` → :class:`MemberIn`
- ``list`` body / ``TupleLiteral`` in goal position → flattened
  :class:`Sequence`

Coverage expands one construct at a time through Slice D5 (see
``todo/slice_d_goalop_ir.md``).
"""

from __future__ import annotations

from typing import Any, NoReturn

from clausal.pythonic_ast import nodes
from clausal.logic.compiler.terms_to_ast import _is_star_list
from clausal.logic.compiler.ir import (
    Alternate,
    ArithEval,
    Dif,
    FDCompare,
    FDOp,
    GoalOp,
    MemberIn,
    Sequence,
    StructuralEq,
    Unify,
)


def terms_to_goalop(body: list[Any]) -> GoalOp:
    """Convert a clause body (list of goals) to a :class:`Sequence`.

    Each element is converted recursively; nested list / ``TupleLiteral``
    conjunctions flatten into the outer :class:`Sequence`.
    """
    ops: list[GoalOp] = []
    _extend(ops, body)
    return Sequence(ops=ops)


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────


_FD_OP: dict[type, FDOp] = {
    nodes.ArithEq: "eq",
    nodes.ArithNeq: "ne",
    nodes.Lt: "lt",
    nodes.LtE: "le",
    nodes.Gt: "gt",
    nodes.GtE: "ge",
}


def _extend(ops: list[GoalOp], body: Any) -> None:
    """Flatten list / ``TupleLiteral`` conjunctions; convert each goal."""
    if isinstance(body, list):
        for goal in body:
            _extend(ops, goal)
        return
    if isinstance(body, nodes.TupleLiteral):
        for goal in body.elements:
            _extend(ops, goal)
        return
    if isinstance(body, nodes.And):
        # ``And`` is a conjunction node; flatten arbitrarily-nested
        # ``And(And(a, b), c)`` into ``[a, b, c]``.  Sequence's
        # right-to-left fold is identical to the legacy ``_dispatch_goal``
        # ``And`` arm (``dispatch(l, dispatch(r, k))``) so flattening
        # preserves byte-for-byte AST output.
        _extend(ops, body.left)
        _extend(ops, body.right)
        return
    ops.append(_convert(body))


def _convert(goal: Any) -> GoalOp:
    match goal:
        # ``Or`` stays binary — nested ``Or(Or(a, b), c)`` must round-trip
        # to nested ``Alternate`` so the lowering emits the same nested
        # mark/undo pattern as the legacy dispatcher.  Flattening would
        # change the number of trail marks and break byte-for-byte
        # AST equivalence.
        case nodes.Or(left=l, right=r):
            return Alternate(ops=[_convert(l), _convert(r)])
        case nodes.Unify(left=l, right=r):
            # Star-list unification (e.g. ``X is [*T, Last]``) routes
            # through ``_compile_star_is`` in the legacy path and maps to
            # ``ListPatternUnify`` in the IR — both belong to Slice D5g,
            # not D2.  Defer so the D4 harness falls back cleanly.
            if _is_star_list(l) or _is_star_list(r):
                _not_yet(goal)
            return Unify(l=l, r=r)
        case nodes.DoesNotUnify(left=l, right=r):
            return Dif(l=l, r=r)
        case nodes.Evaluate(left=l, right=r):
            return ArithEval(target=l, expr=r)
        case nodes.StructuralEq(left=l, right=r):
            return StructuralEq(l=l, r=r, negate=False)
        case nodes.StructuralNeq(left=l, right=r):
            return StructuralEq(l=l, r=r, negate=True)
        case nodes.in_(left=l, right=r):
            return MemberIn(elem=l, collection=r, negate=False)
        case nodes.NotIn(left=l, right=r):
            return MemberIn(elem=l, collection=r, negate=True)
        case nodes.ArithEq() | nodes.ArithNeq() | nodes.Lt() | nodes.LtE() \
                | nodes.Gt() | nodes.GtE():
            return FDCompare(op=_FD_OP[type(goal)], l=goal.left, r=goal.right)
    _not_yet(goal)


def _not_yet(goal: Any) -> NoReturn:
    """Signal that the D2 subset does not yet cover this goal shape.

    The D4 parallel-implementation harness catches this and falls back
    to the legacy compilation path; Slice D5 flips each of these to a
    real conversion.
    """
    raise NotImplementedError(
        f"terms_to_goalop: goal shape not yet supported "
        f"({type(goal).__name__}): {goal!r}"
    )


__all__ = ["terms_to_goalop"]
