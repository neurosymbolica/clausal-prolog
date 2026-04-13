"""Lower a :class:`~clausal.logic.compiler.ir.GoalOp` tree to Python
``ast.stmt`` list — shallow strategy.

Slice D3 prototype: covers the D2 subset (Unify, Dif, ArithEval,
FDCompare, StructuralEq, MemberIn, Sequence).  Output must be
byte-for-byte identical to what ``compile_goal`` would emit today for
the same input; the D4 parallel-implementation harness will enforce
this via ``ast.dump`` diff.

Everything outside the D2 subset raises ``NotImplementedError`` via
``_not_yet`` so the D4 harness can fall back cleanly.  Coverage grows
one construct at a time through Slice D5.

The shallow and trampoline variants (see ``lower_python_trampoline``)
emit identical AST for the entire D2 subset — those twelve ops are
strategy-agnostic at the legacy dispatcher level (see
``_compile_deterministic_goal`` / ``_compile_shared_membership_goal``).
The modules are kept separate so they can diverge naturally as D5
expands into strategy-specific constructs (And, Or, Not, IfExpr, Call).
"""

from __future__ import annotations

import ast
from typing import NoReturn

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


def lower(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Lower *ir* (shallow strategy), threading *k_stmts* as continuation."""
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    match ir:

        # ── Sequence — right-to-left fold threading k_stmts. ────────────────
        case Sequence(ops=ops):
            k = list(k_stmts)
            for op in reversed(ops):
                k = lower(op, ctx, k)
            return k

        # ── Alternate — disjunction.  ``terms_to_goalop`` keeps ``Or``
        # binary (no flattening) so nested ``Or`` produces nested
        # ``Alternate`` and this lowering recurses, emitting the same
        # nested mark/undo pattern as the legacy ``Or`` arm.
        case Alternate(ops=ops):
            mark = ctx.fresh(_MARK_PREFIX)
            out: list[ast.stmt] = [_assign_mark(mark, trail_name)]
            for op in ops:
                out.extend(lower(op, ctx, k_stmts))
                out.append(_undo_stmt(mark, trail_name))
            return out

        # ── Unify ──────────────────────────────────────────────────────────
        case Unify(l=l, r=r):
            mark = ctx.fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        # ── ArithEval (target := expr) ─────────────────────────────────────
        case ArithEval(target=l, expr=r):
            mark = ctx.fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = arith_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        # ── Dif (disequality constraint) ───────────────────────────────────
        case Dif(l=l, r=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_dif"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        # ── Structural equality (==/2, \\==/2) ─────────────────────────────
        case StructuralEq(l=l, r=r, negate=False):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [_if(_call(_name("_structural_eq"), l_expr, r_expr), k_stmts)]

        case StructuralEq(l=l, r=r, negate=True):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [_if(_call(_name("_structural_neq"), l_expr, r_expr), k_stmts)]

        # ── CLP(FD) comparisons ────────────────────────────────────────────
        case FDCompare(op=op, l=l, r=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(
                    _call(_name(_FD_RUNTIME[op]), l_expr, r_expr, _name(trail_name)),
                    k_stmts,
                ),
            ]

        # ── Membership ─────────────────────────────────────────────────────
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

    _not_yet(ir)


def _not_yet(ir: GoalOp) -> NoReturn:
    raise NotImplementedError(
        f"lower_python_shallow: IR op not yet supported: {type(ir).__name__}"
    )


__all__ = ["lower"]
