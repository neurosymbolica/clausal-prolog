"""Reified if-then-else compilation — strategy-driven via ``ctx.strategy``.

A "reifiable" test (unify/disunify, arithmetic/FD comparison) compiles
to a three-way branch driven by ``_reify_eq`` / ``_reify_fd``:

- returned value ``True``  → run ``then``
- returned value ``False`` → run ``else_``
- returned value ``None``  → explore both with appropriate constraints

Non-reifiable tests fall through to ``_compile_general_ite`` which uses
a single-evaluation ``_found`` flag (plus ``_naf_tabled`` for WFS-sound
tabled negation).

Shallow and trampoline previously shipped separate twin helpers
(``*_trampoline``).  Slice C collapsed them: the reified branches route
goal-compilation through ``ctx.strategy.compile_goal`` and are
strategy-agnostic; the general-ITE scaffold (sub-generator + driver
loop) is the one place where shallow vs trampoline structurally
differs, so ``_compile_general_ite`` branches on the strategy class.

Cycle handling: the module is imported by ``goal_shallow`` and
``goal_trampoline``.  Back-references into those modules are
function-local imports (the ratified B4/B6 idiom).
"""

from __future__ import annotations

import ast

from clausal.terms import (
    Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE,
)

from ._ast_helpers import (
    _name, _call, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt,
    _MARK_PREFIX,
    _EXTRA_FUNCDEF,
)
from .terms_to_ast import term_to_ast_expr
from .compile_ctx import CompilationContext
from .tabled_naf import _is_tabled_naf


_REIFIABLE_TYPES = (Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE)


def _is_reifiable(test) -> bool:
    """Return True if *test* can be compiled as a reified three-way branch."""
    return isinstance(test, _REIFIABLE_TYPES)


_FD_REIFY_INFO: dict[type, tuple[str, str, str]] = {
    ArithEq:  ("eq", "_fd_eq", "_fd_ne"),
    ArithNeq: ("ne", "_fd_ne", "_fd_eq"),
    Lt:       ("lt", "_fd_lt", "_fd_ge"),
    LtE:      ("le", "_fd_le", "_fd_gt"),
    Gt:       ("gt", "_fd_gt", "_fd_le"),
    GtE:      ("ge", "_fd_ge", "_fd_lt"),
}


def _three_way_reif_branch(
    reif_var: str,
    reif_call: ast.expr,
    true_stmts: list[ast.stmt],
    false_stmts: list[ast.stmt],
    undetermined: list[ast.stmt],
) -> list[ast.stmt]:
    """Assemble the three-way branch."""
    reif_assign = _assign(reif_var, reif_call)
    branch = ast.If(
        test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(True)]),
        body=true_stmts or [ast.Pass()],
        orelse=[
            ast.If(
                test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(False)]),
                body=false_stmts or [ast.Pass()],
                orelse=undetermined,
            ),
        ],
    )
    return [reif_assign, branch]


def _compile_reified_ite_eq(
    ctx: CompilationContext, l, r, then, else_, k_stmts, *, swap: bool,
) -> list[ast.stmt]:
    """Reified ITE for equality / disequality — strategy-agnostic.

    Recursive goal compilation goes through ``ctx.strategy.compile_goal``,
    so shallow and trampoline share the same function.
    """
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    reif_var = ctx.fresh("_reif")
    l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
    r_expr = term_to_ast_expr(r, var_context, eval_arith=False)

    then_stmts = ctx.strategy.compile_goal(ctx, then, k_stmts)
    else_stmts = ctx.strategy.compile_goal(ctx, else_, k_stmts)

    if swap:
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


def _compile_reified_ite_fd(
    ctx: CompilationContext, test, then, else_, k_stmts,
) -> list[ast.stmt]:
    """Reified ITE for CLP(FD) comparison — strategy-agnostic."""
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    test_type = type(test)
    op_name, fd_true_name, fd_false_name = _FD_REIFY_INFO[test_type]

    reif_var = ctx.fresh("_reif")
    l_expr = term_to_ast_expr(test.left, var_context, eval_arith=False)
    r_expr = term_to_ast_expr(test.right, var_context, eval_arith=False)

    then_stmts = ctx.strategy.compile_goal(ctx, then, k_stmts)
    else_stmts = ctx.strategy.compile_goal(ctx, else_, k_stmts)

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


def _compile_reified_ite(
    ctx: CompilationContext, test, then, else_, k_stmts,
) -> list[ast.stmt]:
    """Three-way-branch dispatcher for reified ITE — strategy-agnostic."""
    match test:
        case Unify(left=l, right=r):
            return _compile_reified_ite_eq(ctx, l, r, then, else_, k_stmts, swap=False)
        case DoesNotUnify(left=l, right=r):
            return _compile_reified_ite_eq(ctx, l, r, then, else_, k_stmts, swap=True)
        case _:
            return _compile_reified_ite_fd(ctx, test, then, else_, k_stmts)


def _compile_general_ite(
    ctx: CompilationContext, test, then, else_, k_stmts,
) -> list[ast.stmt]:
    """Compile ITE for non-reifiable conditions.

    Structural: the strategy determines how the condition's sub-generator
    is wrapped and driven.  Shallow uses a plain ``def`` + ``for`` loop
    over a bare yield-None generator; trampoline uses a ``StepGenerator``
    + send-loop, and compiles the condition with trampoline yields.
    """
    from .strategy import TrampolineStrategy
    if isinstance(ctx.strategy, TrampolineStrategy):
        return _compile_general_ite_trampoline(ctx, test, then, else_, k_stmts)
    return _compile_general_ite_shallow(ctx, test, then, else_, k_stmts)


def _compile_general_ite_shallow(
    ctx: CompilationContext, test, then, else_, k_stmts,
) -> list[ast.stmt]:
    from .goal_shallow import _dispatch_goal
    db = ctx.db
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    use_tabled_naf = _is_tabled_naf(test, db)

    cond_gen = ctx.fresh("_ite_cond")
    cond_stmts = _dispatch_goal(ctx, test, [_yield_none_stmt()])
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

    then_stmts = _dispatch_goal(ctx, then, k_stmts)
    else_stmts = _dispatch_goal(ctx, else_, k_stmts)

    if use_tabled_naf:
        true_mark = ctx.fresh(_MARK_PREFIX)
        true_block = [
            _assign_mark(true_mark, trail_name),
            ast.For(
                target=_name("_", ast.Store()),
                iter=_call(_name(cond_gen)),
                body=then_stmts,
                orelse=[],
            ),
            _undo_stmt(true_mark, trail_name),
        ]
        fname = test.func.name
        call_arity = len(test.args) + len(test.kwargs)
        arg_exprs = [term_to_ast_expr(a, var_context, eval_arith=False) for a in test.args]
        naf_call = _call(
            _name("_naf_tabled"),
            ast.Constant(fname),
            ast.Constant(call_arity),
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
        return [cond_fn] + true_block + false_block

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


def _compile_general_ite_trampoline(
    ctx: CompilationContext, test, then, else_, k_stmts,
) -> list[ast.stmt]:
    from .goal_trampoline import _dispatch_goal_trampoline, _yield_step_stmt
    db = ctx.db
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    use_tabled_naf = _is_tabled_naf(test, db)

    cond_fn_name = ctx.fresh("_ite_cond_fn")
    cond_self = "_ite_self"
    cond_parent = "_ite_parent"
    cond_k = [_yield_step_stmt(_name(cond_parent), ast.Constant(None))]
    cond_ctx = ctx.replace(self_name=cond_self, parent_name=cond_parent)
    cond_stmts = _dispatch_goal_trampoline(cond_ctx, test, cond_k)
    cond_body = cond_stmts + [
        _yield_step_stmt(_name(cond_parent), _name("_DONE")),
    ]
    cond_fn_def = ast.FunctionDef(
        name=cond_fn_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=cond_self), ast.arg(arg=cond_parent),
                  ast.arg(arg=trail_name)],
            vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=cond_body,
        decorator_list=[], returns=None, type_comment=None,
        **_EXTRA_FUNCDEF,
    )

    then_stmts = _dispatch_goal_trampoline(ctx, then, k_stmts)
    else_stmts = _dispatch_goal_trampoline(ctx, else_, k_stmts)

    sg_name = ctx.fresh("_ite_sg")
    g_name = ctx.fresh("_ite_g")
    v_name = ctx.fresh("_ite_v")
    true_mark = ctx.fresh(_MARK_PREFIX)
    found_flag = ctx.fresh("_found")

    sg_create = _assign(sg_name,
        _call(_name("StepGenerator"), _name(cond_fn_name),
              ast.Constant(None), _name(trail_name)))
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
                    _name("_DONE")),
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
                    comparators=[_name("_DONE")],
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

    if use_tabled_naf:
        fname = test.func.name
        call_arity = len(test.args) + len(test.kwargs)
        arg_exprs = [term_to_ast_expr(a, var_context, eval_arith=False) for a in test.args]
        naf_call = _call(
            _name("_naf_tabled"),
            ast.Constant(fname),
            ast.Constant(call_arity),
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
