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
from clausal.logic.compiler.terms_to_ast import (
    _is_star_list,
    _dotted_name_from_loadattr,
)
from clausal.logic.compiler.ite_reified import _is_reifiable
from clausal.logic.compiler.tabled_naf import _is_tabled_naf
from clausal.logic.compiler.ir import (
    Alternate,
    ArithEval,
    Branch,
    Dif,
    FDCompare,
    FDOp,
    GoalOp,
    MemberIn,
    Negate,
    ReifiedKind,
    Sequence,
    StructuralEq,
    SubCall,
    Unify,
)


# Meta-predicate names that the legacy dispatcher routes to dedicated
# ``_compile_*`` helpers (``_compile_catch``, ``_compile_once``, …).
# Until D5f lands ``MetaCall`` coverage, a ``Call`` to one of these must
# fall back to the legacy path rather than being converted to a plain
# :class:`SubCall` (which would invoke it as an ordinary predicate and
# diverge from the legacy AST).
_META_NAMES: frozenset[str] = frozenset({
    "catch", "catch_error", "catch_recover", "forall",
    "throw", "halt",
    "once", "call_nth", "count_all",
    "setup_call_cleanup", "call_cleanup",
    "freeze", "when",
    "findall", "bagof", "setof",
})


def terms_to_goalop(body: list[Any], db: Any = None) -> GoalOp:
    """Convert a clause body (list of goals) to a :class:`Sequence`.

    Each element is converted recursively; nested list / ``TupleLiteral``
    conjunctions flatten into the outer :class:`Sequence`.

    ``db`` (when provided) is consulted for two D5e-era decisions:

    - WK-4 keyword normalisation on :class:`SubCall` — calls with
      ``kwargs`` need a predicate signature to reorder them.
    - Tabled-NAF detection — ``Not(Call(tabled_pred))`` must stay on
      the legacy path until :class:`MetaCall` support lands in D5f;
      without ``db`` we cannot tell, so such calls fall back.
    """
    ops: list[GoalOp] = []
    _extend(ops, body, db)
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


_REIFIED_KIND: dict[type, ReifiedKind] = {
    nodes.Unify: "unify",
    nodes.DoesNotUnify: "dif",
    nodes.ArithEq: "fd_eq",
    nodes.ArithNeq: "fd_ne",
    nodes.Lt: "fd_lt",
    nodes.LtE: "fd_le",
    nodes.Gt: "fd_gt",
    nodes.GtE: "fd_ge",
}


def _extend(ops: list[GoalOp], body: Any, db: Any) -> None:
    """Flatten list / ``TupleLiteral`` conjunctions; convert each goal."""
    if isinstance(body, list):
        for goal in body:
            _extend(ops, goal, db)
        return
    if isinstance(body, nodes.TupleLiteral):
        for goal in body.elements:
            _extend(ops, goal, db)
        return
    if isinstance(body, nodes.And):
        # ``And`` is a conjunction node; flatten arbitrarily-nested
        # ``And(And(a, b), c)`` into ``[a, b, c]``.  Sequence's
        # right-to-left fold is identical to the legacy ``_dispatch_goal``
        # ``And`` arm (``dispatch(l, dispatch(r, k))``) so flattening
        # preserves byte-for-byte AST output.
        _extend(ops, body.left, db)
        _extend(ops, body.right, db)
        return
    ops.append(_convert(body, db))


def _convert(goal: Any, db: Any) -> GoalOp:
    match goal:
        # ``Or`` stays binary — nested ``Or(Or(a, b), c)`` must round-trip
        # to nested ``Alternate`` so the lowering emits the same nested
        # mark/undo pattern as the legacy dispatcher.  Flattening would
        # change the number of trail marks and break byte-for-byte
        # AST equivalence.
        case nodes.Or(left=l, right=r):
            return Alternate(ops=[_convert(l, db), _convert(r, db)])

        # ``Not(op)`` → ``Negate(op)``.  Tabled NAF (``Not`` of a call to
        # a tabled predicate) routes through
        # ``_compile_tabled_naf_simple`` in the legacy path rather than
        # the inline NAF that ``lower(Negate)`` emits, so defer those
        # cases to D5f's ``MetaCall`` coverage.  Non-tabled ``Not(Call)``
        # is fine — ``SubCall`` lowering + ``Negate`` lowering compose
        # to the same inline-NAF AST the legacy dispatcher emits.
        case nodes.Not(operand=op):
            if isinstance(op, nodes.Call) and _is_tabled_naf(op, db):
                _not_yet(goal)
            return Negate(op=_convert(op, db))

        # ``IfExpr(test, body, orelse)`` → ``Branch``.  ``reified_test``
        # is populated for the legacy reifiable test types
        # (unify/dif/FD comparisons); otherwise ``None`` — the general
        # single-eval ITE shape that each strategy lowers in its own
        # dialect.  An ``IfExpr`` whose test is a tabled-predicate call
        # exercises a bespoke ``_naf_tabled`` branch in the legacy
        # general-ITE compiler; defer those to D5f.
        case nodes.IfExpr(test=test, body=then, orelse=else_):
            if isinstance(test, nodes.Call) and _is_tabled_naf(test, db):
                _not_yet(goal)
            kind = _REIFIED_KIND[type(test)] if _is_reifiable(test) else None
            return Branch(
                test=_convert(test, db),
                then=_convert(then, db),
                else_=_convert(else_, db),
                reified_test=kind,
            )

        # ``Call(LoadName | LoadAttr)`` → ``SubCall``.  Meta-predicate
        # names (``once``, ``catch``, ``findall``, …) are deferred to
        # D5f so the legacy ``_compile_shared_meta_call`` arms keep
        # owning those bodies.  Keyword arguments are normalised here
        # (WK-4) using the predicate signature on ``db`` — when no
        # signature is registered we fall back rather than guessing
        # argument order.  Lambda hoisting stays in the lowering, so
        # :class:`SubCall.args` carries the terms unchanged.
        case nodes.Call(func=func, args=call_args, kwargs=call_kwargs) \
                if isinstance(func, (nodes.LoadName, nodes.LoadAttr)):
            if isinstance(func, nodes.LoadName):
                fname = func.name
            else:
                fname = _dotted_name_from_loadattr(func)
                if fname is None:
                    _not_yet(goal)
            if fname in _META_NAMES:
                _not_yet(goal)
            n_pos = len(call_args)
            arity = n_pos + len(call_kwargs or [])
            ordered_args: list = list(call_args)
            if call_kwargs:
                if db is None:
                    _not_yet(goal)
                sig = db.signature_for(fname, arity)
                if sig is None:
                    _not_yet(goal)
                kw_dict = {
                    kw.name: kw.value for kw in call_kwargs
                    if isinstance(kw, nodes.Keyword)
                }
                for param_name in sig[n_pos:]:
                    if param_name not in kw_dict:
                        _not_yet(goal)
                    ordered_args.append(kw_dict[param_name])
            return SubCall(fname=fname, arity=arity, args=ordered_args)

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
