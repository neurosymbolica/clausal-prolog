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

from clausal.logic.compiler.ir import Branch, GoalOp, Negate, SubCall
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
    with ctx.at_position(ir.position):
        return _lower_body(ir, ctx, k_stmts)


def _lower_body(
    ir: GoalOp,
    ctx: CompilationContext,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    match ir:

        # ── General ITE — trampoline form.  (Reified Branch is handled
        # by ``lower_shared``.)  Mirrors legacy
        # ``_compile_general_ite_trampoline`` byte-for-byte.  Tabled-NAF
        # handling isn't needed here until D5e lands Call → SubCall.
        case Branch(test=t_op, then=th_op, else_=el_op,
                    reified_test=None, tabled_naf=tnaf):
            from clausal.logic.compiler.goal_trampoline import _yield_step_stmt
            trail_name = ctx.trail_name
            cond_fn_name = ctx.fresh("_ite_cond_fn")
            cond_self = "_ite_self"
            cond_proceed = "_ite_proceed"
            cond_fail = "_ite_fail"
            cond_catcher = "_ite_catcher"
            cond_k = [_yield_step_stmt(_name(cond_proceed), ast.Constant(None))]
            cond_ctx = ctx.replace(
                self_name=cond_self,
                proceed_name=cond_proceed, fail_name=cond_fail,
                catcher_name=cond_catcher,
            )
            cond_stmts = lower(t_op, cond_ctx, cond_k)
            cond_body = cond_stmts + [
                _yield_step_stmt(_name(cond_fail), _name("$DONE")),
            ]
            cond_fn_def = ast.FunctionDef(
                name=cond_fn_name,
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg=cond_self),
                          ast.arg(arg=cond_proceed),
                          ast.arg(arg=cond_fail),
                          ast.arg(arg=cond_catcher),
                          ast.arg(arg=trail_name)],
                    vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=cond_body,
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            then_stmts = lower(th_op, ctx, k_stmts)
            else_stmts = lower(el_op, ctx, k_stmts)
            sg_name = ctx.fresh("_ite_sg")
            g_name = ctx.fresh("_ite_g")
            v_name = ctx.fresh("_ite_v")
            true_mark = ctx.fresh(_MARK_PREFIX)
            found_flag = ctx.fresh("_found")

            sg_create = _assign(sg_name,
                _call(_name("StepGenerator"), _name(cond_fn_name),
                      ast.Constant(None), ast.Constant(None), ast.Constant(None),
                      _name(trail_name)))
            first_send = ast.Assign(
                targets=[ast.Tuple(
                    elts=[_name(g_name, ast.Store()), _name(v_name, ast.Store())],
                    ctx=ast.Store(),
                )],
                value=_call(ast.Attribute(value=_name(sg_name), attr="send", ctx=ast.Load()),
                            ast.Constant(None)),
            )
            continue_send = ast.Assign(
                targets=[ast.Tuple(
                    elts=[_name(g_name, ast.Store()), _name(v_name, ast.Store())],
                    ctx=ast.Store(),
                )],
                value=_call(ast.Attribute(value=_name(sg_name), attr="send", ctx=ast.Load()),
                            ast.Constant(None)),
            )
            step_send_normal = ast.Assign(
                targets=[ast.Tuple(
                    elts=[_name(g_name, ast.Store()), _name(v_name, ast.Store())],
                    ctx=ast.Store(),
                )],
                value=_call(ast.Attribute(value=_name(g_name), attr="send", ctx=ast.Load()),
                            _name(v_name)),
            )
            step_send_done = ast.Assign(
                targets=[ast.Tuple(
                    elts=[_name(g_name, ast.Store()), _name(v_name, ast.Store())],
                    ctx=ast.Store(),
                )],
                value=_call(ast.Attribute(value=_name(g_name), attr="send", ctx=ast.Load()),
                            _name("$DONE")),
            )
            step_send = ast.If(
                test=ast.Compare(
                    left=_name(v_name),
                    ops=[ast.Is()],
                    comparators=[_name("_TABLING_SUSPEND")],
                ),
                body=[step_send_done],
                orelse=[step_send_normal],
            )
            true_loop_body = ast.If(
                test=ast.Compare(
                    left=_name(g_name),
                    ops=[ast.Is()],
                    comparators=[ast.Constant(None)],
                ),
                body=[
                    ast.If(
                        test=ast.Compare(
                            left=_name(v_name),
                            ops=[ast.Is()],
                            comparators=[_name("$DONE")],
                        ),
                        body=[ast.Break()],
                        orelse=[],
                    ),
                    _assign(found_flag, ast.Constant(value=True)),
                ] + then_stmts + [continue_send],
                orelse=[step_send],
            )
            true_block = [
                _assign(found_flag, ast.Constant(value=False)),
                _assign_mark(true_mark, trail_name),
                sg_create,
                first_send,
                ast.While(
                    test=ast.Constant(value=True),
                    body=[true_loop_body],
                    orelse=[],
                ),
                _undo_stmt(true_mark, trail_name),
            ]
            if tnaf:
                assert isinstance(t_op, SubCall)
                from clausal.logic.compiler.terms_to_ast import (
                    term_to_ast_expr,
                )
                arg_exprs = [
                    term_to_ast_expr(a, ctx.var_context, eval_arith=False)
                    for a in t_op.args
                ]
                naf_call = _call(
                    _name("_naf_tabled"),
                    ast.Constant(t_op.fname),
                    ast.Constant(t_op.arity),
                    ast.List(elts=arg_exprs, ctx=ast.Load()),
                    _name(trail_name),
                    _name("_table_store"),
                )
                naf_mark = ctx.fresh(_MARK_PREFIX)
                false_block = [
                    _assign_mark(naf_mark, trail_name),
                    _if(naf_call, else_stmts),
                    _undo_stmt(naf_mark, trail_name),
                ]
            else:
                false_block = [
                    _if(
                        ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)),
                        else_stmts,
                    ),
                ]
            return [cond_fn_def] + true_block + false_block

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
            inner_k = [_yield_step_stmt(_name("_naf_proceed"), ast.Constant(None))]
            inner_stmts = lower(
                inner,
                ctx.replace(
                    self_name="_naf_self",
                    proceed_name="_naf_proceed",
                    fail_name="_naf_fail",
                    catcher_name="_naf_catcher",
                ),
                inner_k,
            )
            naf_body = inner_stmts + [
                _yield_step_stmt(_name("_naf_fail"), _name("$DONE")),
            ]
            naf_fn_def = ast.FunctionDef(
                name=naf_gen_fn,
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg="_naf_self"),
                          ast.arg(arg="_naf_proceed"),
                          ast.arg(arg="_naf_fail"),
                          ast.arg(arg="_naf_catcher"),
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
                      ast.Constant(None), ast.Constant(None), ast.Constant(None),
                      _name(trail_name)))
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
                            comparators=[_name("$DONE")],
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
