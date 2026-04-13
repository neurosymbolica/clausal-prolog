"""Lower a :class:`~clausal.logic.compiler.ir.GoalOp` tree to Python
``ast.stmt`` list — trampoline strategy.

Covers the D2 subset plus ``Alternate`` (D5b) and ``Negate`` (D5c).
Output is byte-for-byte identical to what ``compile_goal_trampoline``
would emit today for the same input; the D4 parallel-implementation
harness in ``_compile_body_impl`` enforces this via ``ast.dump`` diff
on every body compilation.

Strategy-agnostic cases delegate to ``_lower_goalop_shared``.  The
trampoline-specific arms (``Negate`` today — a mini-trampoline
``StepGenerator`` loop — and later ``SubCall``, catch-family, meta-call
arms that diverge from shallow) live in this module.

Before D5c, this module delegated entirely to ``lower_python_shallow``
because every covered op was strategy-agnostic.  ``Negate`` is the
first divergent op and forces the fork; see commit history for the
transition.
"""

from __future__ import annotations

import ast
from typing import NoReturn

from clausal.logic.compiler.ir import GoalOp, Negate
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
)
from clausal.logic.compiler._lower_goalop_shared import lower_shared


def lower(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Lower *ir* (trampoline strategy), threading *k_stmts* as continuation."""
    match ir:

        # ── Negation-as-failure — trampoline form.
        # Inner goal is compiled in trampoline mode with swapped
        # ``self_name`` / ``parent_name``; a mini-trampoline
        # ``StepGenerator`` loop checks if at least one solution exists.
        # Mirrors the legacy ``_dispatch_goal_trampoline`` ``Not`` arm
        # byte-for-byte.
        case Negate(op=inner):
            from clausal.logic.compiler.goal_trampoline import _yield_step_stmt
            trail_name = ctx.trail_name
            naf_gen_fn = ctx.fresh("_naf_gen_fn")
            naf_flag = ctx.fresh("_naf")
            naf_sg = ctx.fresh("_naf_sg")
            naf_g = ctx.fresh("_naf_g")
            naf_v = ctx.fresh("_naf_v")
            inner_k = [_yield_step_stmt(_name("_naf_parent"), ast.Constant(None))]
            inner_stmts = lower(
                inner,
                ctx.replace(self_name="_naf_self", parent_name="_naf_parent"),
                inner_k,
            )
            naf_body = inner_stmts + [
                _yield_step_stmt(_name("_naf_parent"), _name("_DONE")),
            ]
            naf_fn_def = ast.FunctionDef(
                name=naf_gen_fn,
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg="_naf_self"), ast.arg(arg="_naf_parent"),
                          ast.arg(arg=trail_name)],
                    vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=naf_body,
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            naf_mark = ctx.fresh(_MARK_PREFIX)
            sg_create = _assign(naf_sg,
                _call(_name("StepGenerator"), _name(naf_gen_fn),
                      ast.Constant(None), _name(trail_name)))
            first_send = ast.Assign(
                targets=[ast.Tuple(
                    elts=[_name(naf_g, ast.Store()), _name(naf_v, ast.Store())],
                    ctx=ast.Store(),
                )],
                value=_call(ast.Attribute(value=_name(naf_sg), attr="send", ctx=ast.Load()),
                            ast.Constant(None)),
            )
            inner_if = ast.If(
                test=ast.Compare(
                    left=_name(naf_g),
                    ops=[ast.Is()],
                    comparators=[ast.Constant(None)],
                ),
                body=[
                    ast.If(
                        test=ast.Compare(
                            left=_name(naf_v),
                            ops=[ast.Is()],
                            comparators=[_name("_DONE")],
                        ),
                        body=[ast.Break()],
                        orelse=[],
                    ),
                    _assign(naf_flag, ast.Constant(value=False)),
                    ast.Break(),
                ],
                orelse=[
                    ast.Assign(
                        targets=[ast.Tuple(
                            elts=[_name(naf_g, ast.Store()), _name(naf_v, ast.Store())],
                            ctx=ast.Store(),
                        )],
                        value=_call(ast.Attribute(value=_name(naf_g), attr="send", ctx=ast.Load()),
                                    _name(naf_v)),
                    ),
                ],
            )
            while_loop = ast.While(
                test=ast.Constant(value=True),
                body=[inner_if],
                orelse=[],
            )
            return [
                naf_fn_def,
                _assign(naf_flag, ast.Constant(value=True)),
                _assign_mark(naf_mark, trail_name),
                sg_create,
                first_send,
                while_loop,
                _undo_stmt(naf_mark, trail_name),
                _if(_name(naf_flag), k_stmts),
            ]

    shared = lower_shared(ir, ctx, k_stmts, lower)
    if shared is not None:
        return shared
    _not_yet(ir)


def _not_yet(ir: GoalOp) -> NoReturn:
    raise NotImplementedError(
        f"lower_python_trampoline: IR op not yet supported: {type(ir).__name__}"
    )


__all__ = ["lower"]
