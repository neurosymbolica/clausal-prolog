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
    Dif,
    FDCompare,
    FDOp,
    GoalOp,
    MemberIn,
    Sequence,
    StructuralEq,
    Unify,
)
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


__all__ = ["lower_shared"]
