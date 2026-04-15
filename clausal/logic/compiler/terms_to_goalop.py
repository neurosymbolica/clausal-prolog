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
from clausal.terms import PyThunk
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
    Fail,
    FDCompare,
    FDOp,
    GoalOp,
    ListPatternUnify,
    MemberIn,
    MetaCall,
    Negate,
    PyThunkOp,
    ReifiedKind,
    Sequence,
    StructuralEq,
    SubCall,
    Unify,
)


# Meta-predicate names that must never be converted to a plain
# :class:`SubCall` — the legacy dispatcher routes them to dedicated
# ``_compile_*`` helpers and we mirror that via explicit :class:`MetaCall`
# arms below.  Pre-D7c-β1 this list also gated a legacy-fallback deferral
# for meta-name calls with unexpected arity/kwargs (e.g. ``findall/4``);
# that deferral is gone — such calls now convert to :class:`SubCall` and
# resolve against the database like any other user predicate, which is
# what the legacy path did at those arities too.


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
    # ``True`` is conjunction identity — emit no ops.  ``False`` lowers
    # to :class:`Fail`, whose lowering returns ``[]`` and in a
    # right-to-left :class:`Sequence` fold truncates everything to its
    # left.
    if body is True:
        return
    if body is False:
        ops.append(Fail())
        return
    if isinstance(body, list):
        for goal in body:
            _extend(ops, goal, db)
        return
    if isinstance(body, nodes.TupleLiteral):
        for goal in body.elements:
            _extend(ops, goal, db)
        return
    if isinstance(body, nodes.And):
        # Flatten arbitrarily-nested ``And(And(a, b), c)`` into
        # ``[a, b, c]``; the right-to-left :class:`Sequence` fold
        # produces the same AST as the nested-dispatch form.  The
        # :class:`And`'s own ``position`` is the outermost conjunction
        # span — useful as a fallback for child ops whose own position
        # is missing, but we don't stamp it onto a wrapper here because
        # the flattened ops carry their own.
        _extend(ops, body.left, db)
        _extend(ops, body.right, db)
        return
    ops.append(_convert(body, db))


def _convert(goal: Any, db: Any) -> GoalOp:
    """Convert one goal term to a :class:`GoalOp`, stamping its source
    position from the originating term.

    Slice G threads :attr:`pythonic_ast.nodes.Node.position` (and the
    matching attribute now carried by ``terms.Compound`` /
    ``DictTerm`` / etc.) onto the produced op.  When the goal is a
    Python literal that carries no position (e.g. bare ``True`` /
    ``False``), the op's ``position`` stays ``None`` — call sites that
    care must scope the surrounding term's position.
    """
    op = _convert_inner(goal, db)
    pos = getattr(goal, "position", None)
    if pos is not None and op.position is None:
        op.position = pos
    return op


def _convert_inner(goal: Any, db: Any) -> GoalOp:
    # ``PyThunk`` as a body goal — wrap in :class:`PyThunkOp`; the
    # lowering reuses ``term_to_ast_expr`` to emit a single
    # ``ast.Expr(call)``.
    if isinstance(goal, PyThunk):
        return PyThunkOp(thunk=goal)
    # ``False`` reaching ``_convert`` (e.g. as an :class:`Or` arm or an
    # :class:`IfExpr` branch) — same :class:`Fail` op the conjunction
    # path emits.  ``True`` in the same position becomes an empty
    # :class:`Sequence` (the unit) so the surrounding op sees an
    # always-succeed leaf.
    if goal is False:
        return Fail()
    if goal is True:
        return Sequence(ops=[])
    # ``TupleLiteral`` reaching ``_convert`` (nested inside an
    # :class:`Or` arm, :class:`Not` operand, or :class:`IfExpr` branch
    # rather than at the conjunction top where ``_extend`` flattens
    # it) — flatten its elements into an inner :class:`Sequence`.
    if isinstance(goal, nodes.TupleLiteral) and goal.elements:
        inner_ops: list[GoalOp] = []
        _extend(inner_ops, list(goal.elements), db)
        return Sequence(ops=inner_ops)
    # ``And`` reaching ``_convert`` (nested inside an :class:`Or` arm,
    # :class:`Not` operand, or :class:`IfExpr` branch — at the
    # conjunction top :func:`_extend` flattens ``And`` directly).  Wrap
    # the flattened conjunction in an inner :class:`Sequence`.
    if isinstance(goal, nodes.And):
        inner_ops: list[GoalOp] = []
        _extend(inner_ops, goal.left, db)
        _extend(inner_ops, goal.right, db)
        return Sequence(ops=inner_ops)
    match goal:
        # ``Or`` stays binary — nested ``Or(Or(a, b), c)`` must round-trip
        # to nested ``Alternate`` so the lowering emits the same nested
        # mark/undo pattern as the legacy dispatcher.  Flattening would
        # change the number of trail marks and break byte-for-byte
        # AST equivalence.
        case nodes.Or(left=l, right=r):
            return Alternate(ops=[_convert(l, db), _convert(r, db)])

        # ``Not(op)`` → ``Negate(op)``.  Tabled NAF (``Not`` of a call
        # to a tabled predicate) routes through
        # ``_compile_tabled_naf_simple`` in the legacy path rather than
        # the inline NAF that ``lower(Negate)`` emits.  Slice D5h maps
        # those to :class:`MetaCall` with ``kind="naf_tabled"`` (Option
        # A from ``todo/slice_d_goalop_ir.md``) — semantically distinct
        # from standard NAF (WFS delay semantics), so a dedicated kind
        # rather than a hint on ``Negate``.  Non-tabled ``Not(Call)``
        # is fine — ``SubCall`` lowering + ``Negate`` lowering compose
        # to the same inline-NAF AST the legacy dispatcher emits.
        case nodes.Not(operand=op):
            if isinstance(op, nodes.Call) and _is_tabled_naf(op, db):
                return MetaCall(kind="naf_tabled", args={"call": op})
            return Negate(op=_convert(op, db))

        # ``IfExpr(test, body, orelse)`` → ``Branch``.  ``reified_test``
        # is populated for the legacy reifiable test types
        # (unify/dif/FD comparisons); otherwise ``None`` — the general
        # single-eval ITE shape that each strategy lowers in its own
        # dialect.  An ``IfExpr`` whose test is a tabled-predicate call
        # exercises a bespoke ``_naf_tabled`` branch in the legacy
        # general-ITE compiler; defer those to D5f.
        case nodes.IfExpr(test=test, body=then, orelse=else_):
            tabled = (
                isinstance(test, nodes.Call) and _is_tabled_naf(test, db)
            )
            kind = (
                None if tabled
                else (_REIFIED_KIND[type(test)] if _is_reifiable(test) else None)
            )
            return Branch(
                test=_convert(test, db),
                then=_convert(then, db),
                else_=_convert(else_, db),
                reified_test=kind,
                tabled_naf=tabled,
            )

        # ── Meta-predicate calls ─────────────────────────────────────
        # Inner goals are passed through as raw terms (not recursively
        # ``_convert``ed).  The ``_compile_*`` helpers in
        # :mod:`.control_constructs` consume them via the
        # ``_lower_inner`` / ``_lower_inner_trampoline`` wrappers, which
        # perform the conversion and the strategy-specific lowering in
        # one step — keeping raw terms here avoids a redundant
        # convert-at-analysis / rebuild-at-lowering round trip.  A
        # future cleanup may tighten ``MetaCall.args`` to carry
        # :class:`GoalOp` children directly (see
        # ``todo/slice_d_goalop_ir.md``).
        case nodes.Call(func=nodes.LoadName(name="throw"),
                        args=[term_arg], kwargs=[]):
            return MetaCall(kind="throw", args={"term": term_arg})
        case nodes.Call(func=nodes.LoadName(name="halt"),
                        args=[], kwargs=[]):
            return MetaCall(kind="halt", args={"code": None})
        case nodes.Call(func=nodes.LoadName(name="halt"),
                        args=[code_arg], kwargs=[]):
            return MetaCall(kind="halt", args={"code": code_arg})
        case nodes.Call(func=nodes.LoadName(name="once"),
                        args=[inner], kwargs=[]):
            return MetaCall(kind="once", args={"inner": inner})
        case nodes.Call(func=nodes.LoadName(name="call_nth"),
                        args=[inner, n_arg], kwargs=[]):
            return MetaCall(kind="call_nth",
                            args={"inner": inner, "n": n_arg})
        case nodes.Call(func=nodes.LoadName(name="count_all"),
                        args=[inner, count_arg], kwargs=[]):
            return MetaCall(kind="count_all",
                            args={"inner": inner, "count": count_arg})
        case nodes.Call(func=nodes.LoadName(name="setup_call_cleanup"),
                        args=[setup, call_g, cleanup], kwargs=[]):
            return MetaCall(kind="setup_call_cleanup", args={
                "setup": setup, "call": call_g, "cleanup": cleanup,
            })
        case nodes.Call(func=nodes.LoadName(name="call_cleanup"),
                        args=[call_g, cleanup], kwargs=[]):
            return MetaCall(kind="call_cleanup",
                            args={"call": call_g, "cleanup": cleanup})
        case nodes.Call(func=nodes.LoadName(name="freeze"),
                        args=[x_arg, inner], kwargs=[]):
            return MetaCall(kind="freeze",
                            args={"var": x_arg, "inner": inner})
        case nodes.Call(func=nodes.LoadName(name="when"),
                        args=[cond, inner], kwargs=[]):
            return MetaCall(kind="when",
                            args={"cond": cond, "inner": inner})
        case nodes.Call(func=nodes.LoadName(name="findall"),
                        args=[template, inner, bag], kwargs=[]):
            return MetaCall(kind="findall", args={
                "template": template, "inner": inner, "bag": bag,
            })
        case nodes.Call(func=nodes.LoadName(name="bagof"),
                        args=[template, inner, bag], kwargs=[]):
            return MetaCall(kind="bagof", args={
                "template": template, "inner": inner, "bag": bag,
            })
        case nodes.Call(func=nodes.LoadName(name="setof"),
                        args=[template, inner, bag], kwargs=[]):
            return MetaCall(kind="setof", args={
                "template": template, "inner": inner, "bag": bag,
            })
        case nodes.Call(func=nodes.LoadName(name="catch"),
                        args=[goal_arg, catcher, recovery], kwargs=[]):
            return MetaCall(kind="catch", args={
                "inner": goal_arg, "catcher": catcher, "recovery": recovery,
            })
        case nodes.Call(func=nodes.LoadName(name="catch_error"),
                        args=[goal_arg, error_var], kwargs=[]):
            return MetaCall(kind="catch_error", args={
                "inner": goal_arg, "error": error_var,
            })
        case nodes.Call(func=nodes.LoadName(name="catch_recover"),
                        args=[goal_arg, error_var, recovery], kwargs=[]):
            return MetaCall(kind="catch_recover", args={
                "inner": goal_arg, "error": error_var, "recovery": recovery,
            })
        case nodes.Call(func=nodes.LoadName(name="forall"),
                        args=[cond, action], kwargs=[]):
            return MetaCall(kind="forall",
                            args={"cond": cond, "action": action})

        # ``Call(LoadName | LoadAttr)`` → ``SubCall``.  Meta-predicate
        # names not captured by the explicit arms above (wrong arity,
        # unexpected kwargs) fall through here and resolve as ordinary
        # user predicate calls — the legacy dispatcher did the same at
        # those arities.  Keyword arguments on user predicates are
        # normalised here (WK-4) using the predicate signature on
        # ``db``; when no signature is registered we defer to legacy
        # rather than guessing argument order.  Lambda hoisting stays
        # in the lowering, so :class:`SubCall.args` carries the terms
        # unchanged.
        case nodes.Call(func=func, args=call_args, kwargs=call_kwargs) \
                if isinstance(func, (nodes.LoadName, nodes.LoadAttr)):
            if isinstance(func, nodes.LoadName):
                fname = func.name
            else:
                fname = _dotted_name_from_loadattr(func)
                if fname is None:
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
            # Star-list unification (e.g. ``X := [*T, Last]``) routes
            # through ``_compile_star_is`` in the legacy path.  Mirror
            # the legacy preference for putting the star side first:
            # when both sides carry stars the left side wins (legacy
            # shallow / trampoline dispatchers both test ``l`` first).
            if _is_star_list(l):
                return ListPatternUnify(star_side=l, other_side=r)
            if _is_star_list(r):
                return ListPatternUnify(star_side=r, other_side=l)
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
