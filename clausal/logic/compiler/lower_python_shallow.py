"""Lower a :class:`~clausal.logic.compiler.ir.GoalOp` tree to Python
``ast.stmt`` list — shallow strategy.

Covers the D2 subset plus ``Alternate`` (D5b) and ``Negate`` (D5c).
Output is byte-for-byte identical to what ``compile_goal`` would emit
today for the same input; the D4 parallel-implementation harness in
``_compile_body_impl`` enforces this via ``ast.dump`` diff on every
body compilation.

Everything outside the supported set raises ``NotImplementedError``
via ``_not_yet`` so the D4 harness can fall back cleanly.  Coverage
grows one construct at a time through Slice D5.

Strategy-agnostic cases live in ``_lower_goalop_shared.lower_shared``
and are shared with ``lower_python_trampoline``.  Strategy-specific
cases (``Negate`` today; later ``SubCall``, catch-family, meta-call
arms that differ) live here.
"""

from __future__ import annotations

import ast
from typing import NoReturn

from clausal.logic.compiler.ir import Branch, GoalOp, Negate
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.compiler._ast_helpers import (
    _EXTRA_FUNCDEF,
    _MARK_PREFIX,
    _assign,
    _assign_mark,
    _call,
    _if,
    _name,
    _undo_stmt,
    _yield_none_stmt,
)
from clausal.logic.compiler._lower_goalop_shared import lower_shared


def lower(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Lower *ir* (shallow strategy), threading *k_stmts* as continuation."""
    match ir:

        # ── General ITE — shallow form.  (Reified Branch is handled
        # by ``lower_shared``.)  Mirrors legacy ``_compile_general_ite_shallow``
        # byte-for-byte.  Tabled-NAF handling is not needed here until
        # D5e lands Call → SubCall; see D5d-ii commit.
        case Branch(test=t_op, then=th_op, else_=el_op, reified_test=None):
            trail_name = ctx.trail_name
            cond_gen = ctx.fresh("_ite_cond")
            cond_stmts = lower(t_op, ctx, [_yield_none_stmt()])
            cond_body = cond_stmts + [
                ast.Return(value=ast.Constant(value=None)),
                ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
            ]
            cond_fn = ast.FunctionDef(
                name=cond_gen,
                args=ast.arguments(
                    posonlyargs=[], args=[], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=cond_body,
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            then_stmts = lower(th_op, ctx, k_stmts)
            else_stmts = lower(el_op, ctx, k_stmts)
            found_flag = ctx.fresh("_found")
            mark = ctx.fresh(_MARK_PREFIX)
            return [
                cond_fn,
                _assign(found_flag, ast.Constant(value=False)),
                _assign_mark(mark, trail_name),
                ast.For(
                    target=_name("_", ast.Store()),
                    iter=_call(_name(cond_gen)),
                    body=[_assign(found_flag, ast.Constant(value=True))] + then_stmts,
                    orelse=[],
                ),
                _undo_stmt(mark, trail_name),
                _if(
                    ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)),
                    else_stmts,
                ),
            ]

        # ── Negation-as-failure — shallow form.
        # Inline sub-generator function + ``for`` loop over its first
        # solution; flag gates the continuation.  Mirrors the legacy
        # ``_dispatch_goal`` ``Not`` arm byte-for-byte.
        case Negate(op=inner):
            trail_name = ctx.trail_name
            naf_gen = ctx.fresh("_naf_gen")
            naf_flag = ctx.fresh("_naf")
            inner_stmts = lower(inner, ctx, [_yield_none_stmt()])
            naf_body = inner_stmts + [
                ast.Return(value=ast.Constant(value=None)),
                ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
            ]
            naf_fn = ast.FunctionDef(
                name=naf_gen,
                args=ast.arguments(
                    posonlyargs=[], args=[], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=naf_body,
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            naf_mark = ctx.fresh(_MARK_PREFIX)
            return [
                naf_fn,
                _assign(naf_flag, ast.Constant(value=True)),
                _assign_mark(naf_mark, trail_name),
                ast.For(
                    target=_name("_", ast.Store()),
                    iter=_call(_name(naf_gen)),
                    body=[
                        _assign(naf_flag, ast.Constant(value=False)),
                        ast.Break(),
                    ],
                    orelse=[],
                ),
                _undo_stmt(naf_mark, trail_name),
                _if(_name(naf_flag), k_stmts),
            ]

    shared = lower_shared(ir, ctx, k_stmts, lower)
    if shared is not None:
        return shared
    _not_yet(ir)


def _not_yet(ir: GoalOp) -> NoReturn:
    raise NotImplementedError(
        f"lower_python_shallow: IR op not yet supported: {type(ir).__name__}"
    )


__all__ = ["lower"]
