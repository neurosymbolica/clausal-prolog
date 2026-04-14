"""Strategy-agnostic :class:`~clausal.logic.compiler.ir.GoalOp` lowering.

The ops in this module emit identical AST under both shallow and
trampoline strategies (see the legacy ``_compile_deterministic_goal``
/ ``_compile_shared_membership_goal`` helpers and the ``Or`` arm —
all strategy-invariant).  Both strategy-specific lowerings delegate
here after handling their own divergent ops.

The ``recurse`` parameter is the strategy-specific top-level ``lower``
function.  :class:`Sequence` and :class:`Alternate` dispatch their
children through *recurse* so the strategy's divergent ops (e.g.
``Negate``) lower in the correct dialect even when they appear nested
inside a shared op.
"""

from __future__ import annotations

import ast
from typing import Callable, Union

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
    PyThunkOp,
    ReifiedKind,
    Sequence,
    StructuralEq,
    SubCall,
    Unify,
)
from clausal.logic.compiler.ite_reified import _three_way_reif_branch
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler._ast_helpers import (
    _MARK_PREFIX,
    _assign,
    _assign_mark,
    _call,
    _if,
    _in_iter_expr,
    _name,
    _undo_stmt,
)
from clausal.logic.compiler.terms_to_ast import (
    arith_to_ast_expr,
    term_to_ast_expr,
)


_FD_RUNTIME: dict[FDOp, str] = {
    "eq": "_fd_eq",
    "ne": "_fd_ne",
    "lt": "_fd_lt",
    "le": "_fd_le",
    "gt": "_fd_gt",
    "ge": "_fd_ge",
}


# (op_name, fd_true_name, fd_false_name) — the same triple the legacy
# ``_FD_REIFY_INFO`` carries, keyed here by :data:`ReifiedKind` literal
# rather than ``clausal.terms`` type so the IR has no term-level dep.
_FD_REIFY: dict[str, tuple[str, str, str]] = {
    "fd_eq": ("eq", "_fd_eq", "_fd_ne"),
    "fd_ne": ("ne", "_fd_ne", "_fd_eq"),
    "fd_lt": ("lt", "_fd_lt", "_fd_ge"),
    "fd_le": ("le", "_fd_le", "_fd_gt"),
    "fd_gt": ("gt", "_fd_gt", "_fd_le"),
    "fd_ge": ("ge", "_fd_ge", "_fd_lt"),
}


def lower_shared(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
    recurse: Callable[[GoalOp, CompilationContext, list[ast.stmt]], list[ast.stmt]],
) -> Union[list[ast.stmt], None]:
    """Lower a strategy-agnostic op, or return ``None`` if *ir* is
    strategy-specific and must be handled by the caller."""
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    match ir:

        case Sequence(ops=ops):
            k = list(k_stmts)
            for op in reversed(ops):
                k = recurse(op, ctx, k)
            return k

        # ── Constant failure (legacy ``goal is False``) — drops the
        # continuation entirely.  In a Sequence right-to-left fold this
        # truncates everything to its left, byte-identical to legacy.
        case Fail():
            return []

        # ── PyThunk as a body goal — evaluate the embedded callable
        # for side effects, then continue.  Identical between shallow
        # and trampoline (legacy fast-path in both ``_dispatch_goal``s).
        case PyThunkOp(thunk=thunk):
            call_expr = term_to_ast_expr(thunk, var_context, eval_arith=False)
            return [ast.Expr(value=call_expr)] + list(k_stmts)

        # ── Reified Branch (D5d-i) — three-way ITE.
        # General Branch (``reified_test is None``) is deferred to
        # D5d-ii; returning ``None`` lets the caller fall back to
        # legacy via the harness.
        case Branch(test=t_op, then=th_op, else_=el_op, reified_test=kind) \
                if kind is not None:
            return _lower_reified_branch(
                ctx, kind, t_op, th_op, el_op, k_stmts, recurse,
            )

        case Alternate(ops=ops):
            mark = ctx.fresh(_MARK_PREFIX)
            out: list[ast.stmt] = [_assign_mark(mark, trail_name)]
            for op in ops:
                out.extend(recurse(op, ctx, k_stmts))
                out.append(_undo_stmt(mark, trail_name))
            return out

        case Unify(l=l, r=r):
            mark = ctx.fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        case ArithEval(target=l, expr=r):
            mark = ctx.fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = arith_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        case Dif(l=l, r=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_dif"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        case StructuralEq(l=l, r=r, negate=False):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [_if(_call(_name("_structural_eq"), l_expr, r_expr), k_stmts)]

        case StructuralEq(l=l, r=r, negate=True):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [_if(_call(_name("_structural_neq"), l_expr, r_expr), k_stmts)]

        case FDCompare(op=op, l=l, r=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(
                    _call(_name(_FD_RUNTIME[op]), l_expr, r_expr, _name(trail_name)),
                    k_stmts,
                ),
            ]

        # ── Body-side star-list unification — delegate to the
        # ``_compile_star_is`` helper in ``.star_segments``.  Single
        # vs multi-star routing happens inside that helper; the IR
        # carries only the raw pair (see ``ir.py::ListPatternUnify``).
        case ListPatternUnify(star_side=ss, other_side=os):
            from .star_segments import _compile_star_is
            return _compile_star_is(ctx, ss, os, k_stmts)

        # ── Meta-predicate calls — delegate to the legacy helpers.
        # Each ``MetaCall`` kind corresponds to a specific legacy
        # ``_compile_*`` helper in :mod:`.control_constructs`.  The
        # helpers use the shallow ``_dispatch_goal`` for inner goals
        # regardless of outer strategy (inner meta-call bodies are
        # always compiled shallow); this matches legacy behaviour.
        # ``args`` carries raw terms — see ``terms_to_goalop`` for the
        # rationale.  Function-local imports break the shared ↔
        # control_constructs / goal_shallow cycle.
        case MetaCall(kind=kind, args=margs):
            return _lower_meta_call(ctx, kind, margs, k_stmts)

        # ── Predicate call — delegate to the shared legacy front-end.
        # ``_compile_predicate_call_impl`` already performs the exact
        # sequence the legacy ``Call(LoadName | LoadAttr)`` arms do:
        # lambda-hoist (advances ``ctx.fresh``), ``term_to_ast_expr`` per
        # arg, then ``ctx.strategy.emit_sub_call``.  Keyword normalisation
        # was done by ``terms_to_goalop`` (WK-4) so we pass ``kwargs=[]``
        # here.  Function-local import breaks the shared ↔ goal_shallow
        # cycle (ratified B4/B6 idiom).
        case SubCall(fname=fname, arity=_arity, args=args):
            # Slice E4c: tail_recursive hint — emit the TRO tail
            # (``_compile_tro_tail``) and drop *k_stmts*.  ``ctx.tro_mode``
            # carries the per-clause-compile mode (``"loop"`` /
            # ``"signal"``); it must be set by the caller that wrote the
            # hint, otherwise refuse to lower (guards against a stray
            # hint reaching ``_compile_body_impl``).
            if ir.tail_recursive:
                if ctx.tro_mode is None:
                    raise AssertionError(
                        "SubCall.tail_recursive set but ctx.tro_mode is None — "
                        "TRO hint reached non-TRO compilation context."
                    )
                from clausal.terms import Call, LoadName
                from clausal.logic.compiler.tro import _compile_tro_tail
                fake_tail_call = Call(
                    func=LoadName(name=fname), args=list(args), kwargs=[],
                )
                return _compile_tro_tail(
                    ctx, fake_tail_call, ir.arity, ctx.var_context,
                    ctx.db, ctx.trail_name,
                    tro_mode=ctx.tro_mode,
                    check_indices=ir.tro_check_indices or None,
                )
            from clausal.logic.compiler.goal_shallow import (
                _compile_predicate_call_impl,
            )
            # Slice E4b: destructive-reuse hint — rewrite fname to the
            # ``_dr_<name>__<arity>`` variant so dispatch emission picks
            # the in-place bucket function.  The DR variants are
            # unconditionally registered in ``base_globals`` by
            # ``predicate.py`` (they're builtin dispatch entries), so
            # the rename is always resolvable.
            if ir.destructive_reuse:
                _DR_NAME_MAP = {
                    "append": "_dr_append__3",
                    "dict_put": "_dr_dict_put__4",
                    "set_union": "_dr_set_union__3",
                }
                fname = _DR_NAME_MAP.get(fname, fname)
            return _compile_predicate_call_impl(
                ctx, fname, args, [], k_stmts,
                direct_bucket_ref=ir.direct_bucket_ref,
            )

        case MemberIn(elem=elem, collection=collection, negate=False):
            loop_var = ctx.fresh("_el")
            mark = ctx.fresh(_MARK_PREFIX)
            elem_expr = term_to_ast_expr(elem, var_context, eval_arith=False)
            coll_expr = term_to_ast_expr(collection, var_context, eval_arith=False)
            return [
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_in_iter_expr(elem, coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        _if(
                            _call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            k_stmts,
                        ),
                        _undo_stmt(mark, trail_name),
                    ],
                    orelse=[],
                )
            ]

        case MemberIn(elem=elem, collection=collection, negate=True):
            found_flag = ctx.fresh("_found")
            loop_var = ctx.fresh("_el")
            mark = ctx.fresh(_MARK_PREFIX)
            elem_expr = term_to_ast_expr(elem, var_context, eval_arith=False)
            coll_expr = term_to_ast_expr(collection, var_context, eval_arith=False)
            return [
                _assign(found_flag, ast.Constant(value=False)),
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_in_iter_expr(elem, coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        ast.If(
                            test=_call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            body=[
                                _assign(found_flag, ast.Constant(value=True)),
                                _undo_stmt(mark, trail_name),
                                ast.Break(),
                            ],
                            orelse=[_undo_stmt(mark, trail_name)],
                        ),
                    ],
                    orelse=[],
                ),
                _if(ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)), k_stmts),
            ]

    return None


def _lower_reified_branch(
    ctx: CompilationContext,
    kind: ReifiedKind,
    test_op: GoalOp,
    then_op: GoalOp,
    else_op: GoalOp,
    k_stmts: list[ast.stmt],
    recurse,
) -> list[ast.stmt]:
    """Emit the three-way reified ITE pattern, byte-identical to the
    legacy ``_compile_reified_ite_eq`` / ``_compile_reified_ite_fd``.

    The IR's ``reified_test`` literal carries enough information that
    operands can be read directly off ``test_op`` without re-deriving
    from a term — ``"unify"`` and ``"dif"`` come from a :class:`Unify`
    or :class:`Dif` IR op respectively, ``"fd_*"`` from :class:`FDCompare`.
    """
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    reif_var = ctx.fresh("_reif")
    l = test_op.l
    r = test_op.r
    l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
    r_expr = term_to_ast_expr(r, var_context, eval_arith=False)

    then_stmts = recurse(then_op, ctx, k_stmts)
    else_stmts = recurse(else_op, ctx, k_stmts)

    if kind == "unify" or kind == "dif":
        if kind == "dif":
            true_stmts, false_stmts = else_stmts, then_stmts
        else:
            true_stmts, false_stmts = then_stmts, else_stmts
        mark = ctx.fresh(_MARK_PREFIX)
        undetermined = [
            _assign_mark(mark, trail_name),
            _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), true_stmts),
            _undo_stmt(mark, trail_name),
            _if(_call(_name("_dif"), l_expr, r_expr, _name(trail_name)), false_stmts),
        ]
        reif_call = _call(_name("_reify_eq"), l_expr, r_expr, _name(trail_name))
        return _three_way_reif_branch(
            reif_var, reif_call, true_stmts, false_stmts, undetermined,
        )

    # FD reified.
    op_name, fd_true_name, fd_false_name = _FD_REIFY[kind]
    mark = ctx.fresh(_MARK_PREFIX)
    undetermined = [
        _assign_mark(mark, trail_name),
        _if(_call(_name(fd_true_name), l_expr, r_expr, _name(trail_name)), then_stmts),
        _undo_stmt(mark, trail_name),
        _assign_mark(mark, trail_name),
        _if(_call(_name(fd_false_name), l_expr, r_expr, _name(trail_name)), else_stmts),
        _undo_stmt(mark, trail_name),
    ]
    reif_call = _call(
        _name("_reify_fd"), ast.Constant(op_name), l_expr, r_expr, _name(trail_name),
    )
    return _three_way_reif_branch(
        reif_var, reif_call, then_stmts, else_stmts, undetermined,
    )


def _lower_meta_call(
    ctx: CompilationContext,
    kind: str,
    margs: dict,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Dispatch a :class:`MetaCall` to the matching legacy helper.

    One arm per closed :data:`~clausal.logic.compiler.ir.MetaKind`
    literal.  Each arm reads the fixed ``args`` schema documented on
    :class:`~clausal.logic.compiler.ir.MetaCall` and forwards to the
    corresponding ``_compile_*`` helper in :mod:`.control_constructs`.
    """
    from .control_constructs import (
        _compile_once, _compile_call_nth, _compile_count_all,
        _compile_setup_call_cleanup, _compile_freeze, _compile_when,
        _compile_find_all_core,
        _compile_throw, _compile_catch,
    )
    from .tabled_naf import _compile_tabled_naf_simple
    from ._ast_helpers import _name, _call
    from .terms_to_ast import term_to_ast_expr
    # ── WFS-sound NAF of a call to a tabled predicate.  The legacy
    # ``_compile_tabled_naf_simple`` takes the raw :class:`Call` term
    # and handles kwargs signature normalisation itself.
    if kind == "naf_tabled":
        return _compile_tabled_naf_simple(ctx, margs["call"], k_stmts)
    # ``forall`` rewrites to ``Not(And(cond, Not(action)))`` and
    # re-dispatches through the shallow goal compiler, matching the
    # legacy ``forall`` arm in both strategy dispatchers.
    if kind == "forall":
        from clausal.terms import And, Not
        from .goal_shallow import _dispatch_goal
        rewritten = Not(operand=And(
            left=margs["cond"],
            right=Not(operand=margs["action"]),
        ))
        return _dispatch_goal(ctx, rewritten, k_stmts)
    if kind == "throw":
        return _compile_throw(ctx, margs["term"])
    if kind == "halt":
        code_arg = margs["code"]
        if code_arg is None:
            return [ast.Raise(exc=_call(_name("SystemExit"), ast.Constant(0)))]
        code_expr = term_to_ast_expr(code_arg, ctx.var_context, eval_arith=True)
        return [ast.Raise(exc=_call(_name("SystemExit"), code_expr))]
    if kind == "once":
        return _compile_once(ctx, margs["inner"], k_stmts)
    if kind == "call_nth":
        return _compile_call_nth(ctx, margs["inner"], margs["n"], k_stmts)
    if kind == "count_all":
        return _compile_count_all(
            ctx, margs["inner"], margs["count"], k_stmts,
        )
    if kind == "setup_call_cleanup":
        return _compile_setup_call_cleanup(
            ctx, margs["setup"], margs["call"], margs["cleanup"], k_stmts,
        )
    if kind == "call_cleanup":
        # Legacy sugar: ``call_cleanup(C, Cl)`` → ``setup_call_cleanup(True, C, Cl)``.
        return _compile_setup_call_cleanup(
            ctx, True, margs["call"], margs["cleanup"], k_stmts,
        )
    if kind == "freeze":
        return _compile_freeze(ctx, margs["var"], margs["inner"], k_stmts)
    if kind == "when":
        return _compile_when(ctx, margs["cond"], margs["inner"], k_stmts)
    if kind == "findall":
        return _compile_find_all_core(
            ctx, margs["template"], margs["inner"], margs["bag"], k_stmts,
            fail_on_empty=False, dedup=False,
        )
    if kind == "bagof":
        return _compile_find_all_core(
            ctx, margs["template"], margs["inner"], margs["bag"], k_stmts,
            fail_on_empty=True, dedup=False,
        )
    if kind == "setof":
        return _compile_find_all_core(
            ctx, margs["template"], margs["inner"], margs["bag"], k_stmts,
            fail_on_empty=True, dedup=True,
        )
    if kind == "catch":
        return _compile_catch(
            ctx, margs["inner"], margs["catcher"], margs["recovery"], k_stmts,
        )
    if kind == "catch_error":
        return _compile_catch(
            ctx, margs["inner"], margs["error"], True, k_stmts,
            always_catch=True,
        )
    if kind == "catch_recover":
        return _compile_catch(
            ctx, margs["inner"], margs["error"], margs["recovery"], k_stmts,
            always_catch=True,
        )
    raise NotImplementedError(
        f"_lower_meta_call: unknown MetaCall kind {kind!r}"
    )


__all__ = ["lower_shared"]
