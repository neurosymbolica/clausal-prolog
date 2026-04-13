"""Control-construct and meta-predicate goal compilation.

Compiles goals that wrap or transform other goals: once, call_nth,
count_all, setup_call_cleanup, freeze, when, find_all_core, throw,
catch (shallow + trampoline twins), goal lambdas, arithmetic /
structural comparisons, and the small helpers ``_flatten_conjunction``
and ``_hoist_lambda_args``.

Cycle handling: every control construct calls back into
``compile_goal`` / ``compile_goal_trampoline`` (still in ``_monolith``
at this split stage).  We reference them through the ``_m`` alias on
the ``_monolith`` module so the attribute lookup happens at call time,
avoiding the load-order cycle.  Future phase 12 moves the goal
compilers themselves; this module's call sites remain valid because
``_monolith`` re-exports the goal compilers.
"""

from __future__ import annotations

import ast
from typing import Any

from clausal.logic.variables import Var, is_var, deref, unify  # noqa: F401
from clausal.logic.trampoline import Step, DONE, StepGenerator  # noqa: F401
from clausal.terms import (
    Compound,
    And, Or, Not,
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq, StructuralEq, StructuralNeq,
    Lt, LtE, Gt, GtE,
    Call, LoadName, LoadAttr,
)
from clausal.pythonic_ast.nodes import IfExpr, Lambda
from clausal.logic.database import Clause, Database

from ._ast_helpers import (
    _name, _attr, _call, _fresh, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt, _in_iter_expr,
    _MARK_PREFIX, _TRAIL_PARAM_NAME, _K_PARAM_NAME,
    _TRAMP_PARENT_NAME, _THIS_GEN_NAME,
)
from ._vars import _var_python_name, _collect_vars, _collect_bound_vars
from .globals_env import _preallocate_body_vars
from .terms_to_ast import term_to_ast_expr, arith_to_ast_expr
from .compile_ctx import CompilationContext
from . import _monolith as _m
from clausal.pythonic_ast.nodes import Keyword as KWNode  # noqa: E402

# Aliases preserved from the pre-split monolith (Call/LoadName from the AST).
AstCall = Call
AstLoadName = LoadName


def _compile_arith_cmp(
    ctx: CompilationContext,
    l: Any,
    r: Any,
    ast_op: ast.cmpop,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    var_context = ctx.var_context
    l_expr = arith_to_ast_expr(l, var_context)
    r_expr = arith_to_ast_expr(r, var_context)
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]


def _deref_cmp(
    ctx: CompilationContext,
    l: Any,
    r: Any,
    ast_op: ast.cmpop,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a structural comparison using deref on both sides."""
    var_context = ctx.var_context
    l_expr = _call(_name("deref"), term_to_ast_expr(l, var_context, eval_arith=False))
    r_expr = _call(_name("deref"), term_to_ast_expr(r, var_context, eval_arith=False))
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]


def _compile_once(ctx: CompilationContext, inner, k_stmts):
    """Compile once(goal) — take first solution of inner goal, then continue."""
    from .goal_shallow import _dispatch_goal
    trail_name = ctx.trail_name
    once_gen = _fresh("_once_gen")
    inner_stmts = _dispatch_goal(ctx, inner, [_yield_none_stmt()])
    once_body = inner_stmts + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]
    once_fn = ast.FunctionDef(
        name=once_gen,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=once_body,
        decorator_list=[], returns=None, type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )
    once_mark = _fresh(_MARK_PREFIX)
    return [
        once_fn,
        _assign_mark(once_mark, trail_name),
        ast.For(
            target=_name("_", ast.Store()),
            iter=_call(_name(once_gen)),
            body=k_stmts + [ast.Break()],
            orelse=[],
        ),
        _undo_stmt(once_mark, trail_name),
    ]


def _compile_call_nth(ctx: CompilationContext, inner, n_arg, k_stmts):
    """Compile call_nth(Goal, N) — succeed on the Nth solution of Goal only."""
    from .goal_shallow import _dispatch_goal
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    count_var = _fresh("_cn_count")
    n_var = _fresh("_cn_n")
    mark_var = _fresh("_cn_m")
    gen_name = _fresh("_cn_gen")

    n_expr = term_to_ast_expr(n_arg, var_context, eval_arith=True)

    inner_stmts = _dispatch_goal(ctx, inner, [_yield_none_stmt()])
    gen_body = inner_stmts + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]
    gen_fn = ast.FunctionDef(
        name=gen_name,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=gen_body,
        decorator_list=[], returns=None, type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )

    # Type check: n must be a positive integer
    type_check = ast.If(
        test=ast.BoolOp(
            op=ast.Or(),
            values=[
                ast.UnaryOp(
                    op=ast.Not(),
                    operand=_call(_name("isinstance"), _name(n_var), _name("int")),
                ),
                ast.Compare(
                    left=_name(n_var),
                    ops=[ast.Lt()],
                    comparators=[ast.Constant(value=1)],
                ),
            ],
        ),
        body=[
            ast.Raise(exc=_call(
                _name("_LogicException"),
                _call(_name("_type_error"), ast.Constant(value="positive_integer"),
                      _name(n_var), ast.Constant(value="call_nth/2")),
            )),
        ],
        orelse=[],
    )

    count_incr = ast.AugAssign(
        target=_name(count_var, ast.Store()),
        op=ast.Add(),
        value=ast.Constant(value=1),
    )
    nth_check = ast.If(
        test=ast.Compare(
            left=_name(count_var),
            ops=[ast.Eq()],
            comparators=[_name(n_var)],
        ),
        body=k_stmts + [ast.Break()],
        orelse=[],
    )
    goal_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(gen_name)),
        body=[count_incr, nth_check],
        orelse=[],
    )

    return [
        _assign(count_var, ast.Constant(value=0)),
        _assign(n_var, _call(_name("deref"), n_expr)),
        type_check,
        _assign_mark(mark_var, trail_name),
        gen_fn,
        goal_loop,
        _undo_stmt(mark_var, trail_name),
    ]


def _compile_count_all(ctx: CompilationContext, inner, count_arg, k_stmts):
    """Compile count_all(Goal, Count) — count solutions without collecting."""
    from .goal_shallow import _dispatch_goal
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    n_var = _fresh("_ca_n")
    mark_var = _fresh("_ca_m")
    gen_name = _fresh("_ca_gen")
    unify_mark = _fresh("_ca_um")

    count_expr = term_to_ast_expr(count_arg, var_context, eval_arith=False)

    inner_stmts = _dispatch_goal(ctx, inner, [_yield_none_stmt()])
    gen_body = inner_stmts + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]
    gen_fn = ast.FunctionDef(
        name=gen_name,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=gen_body,
        decorator_list=[], returns=None, type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )

    count_incr = ast.AugAssign(
        target=_name(n_var, ast.Store()),
        op=ast.Add(),
        value=ast.Constant(value=1),
    )
    goal_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(gen_name)),
        body=[count_incr],
        orelse=[],
    )

    unify_check = ast.If(
        test=_call(_name("unify"), count_expr, _name(n_var), _name(trail_name)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )

    return [
        _assign(n_var, ast.Constant(value=0)),
        _assign_mark(mark_var, trail_name),
        gen_fn,
        goal_loop,
        _undo_stmt(mark_var, trail_name),
        _assign_mark(unify_mark, trail_name),
        unify_check,
        _undo_stmt(unify_mark, trail_name),
    ]


def _compile_setup_call_cleanup(ctx: CompilationContext, setup, call, cleanup, k_stmts):
    """Compile setup_call_cleanup(Setup, Call, Cleanup) — deterministic cleanup."""
    from .goal_shallow import _dispatch_goal
    trail_name = ctx.trail_name
    mark_var = _fresh("_scc_m")
    setup_gen = _fresh("_scc_setup")
    ok_var = _fresh("_scc_ok")
    call_gen = _fresh("_scc_call")
    exc_var = _fresh("_scc_exc")
    exc_e = _fresh("_scc_e")
    cleanup_gen = _fresh("_scc_cleanup")

    def _make_sub_gen(name, goal):
        stmts = _dispatch_goal(ctx, goal, [_yield_none_stmt()])
        body = stmts + [
            ast.Return(value=ast.Constant(value=None)),
            ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
        ]
        return ast.FunctionDef(
            name=name,
            args=ast.arguments(
                posonlyargs=[], args=[], vararg=None,
                kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=body,
            decorator_list=[], returns=None, type_comment=None,
            **_m._EXTRA_FUNCDEF,
        )

    setup_fn = _make_sub_gen(setup_gen, setup)
    call_fn = _make_sub_gen(call_gen, call)
    cleanup_fn = _make_sub_gen(cleanup_gen, cleanup)

    setup_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(setup_gen)),
        body=[
            _assign(ok_var, ast.Constant(value=True)),
            ast.Break(),
        ],
        orelse=[],
    )

    call_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(call_gen)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )

    cleanup_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(cleanup_gen)),
        body=[ast.Break()],
        orelse=[],
    )

    handler = ast.ExceptHandler(
        type=_name("Exception"),
        name=exc_e,
        body=[_assign(exc_var, _name(exc_e))],
    )

    reraise = ast.If(
        test=ast.Compare(
            left=_name(exc_var),
            ops=[ast.IsNot()],
            comparators=[ast.Constant(value=None)],
        ),
        body=[ast.Raise(exc=_name(exc_var))],
        orelse=[],
    )

    try_block = ast.Try(
        body=[call_loop],
        handlers=[handler],
        orelse=[],
        finalbody=[cleanup_fn, cleanup_loop, reraise],
    )

    if_ok = ast.If(
        test=_name(ok_var),
        body=[_assign(exc_var, ast.Constant(value=None)), call_fn, try_block],
        orelse=[],
    )

    return [
        _assign_mark(mark_var, trail_name),
        setup_fn,
        _assign(ok_var, ast.Constant(value=False)),
        setup_loop,
        if_ok,
    ]


def _compile_freeze(ctx: CompilationContext, x_arg, goal, k_stmts):
    """Compile freeze(X, Goal) — delay Goal until X is bound."""
    from .goal_shallow import _dispatch_goal
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    x_var = _fresh("_fz_x")
    thunk_name = _fresh("_fz_thunk")
    old_var = _fresh("_fz_old")
    goals_var = _fresh("_fz_goals")

    x_expr = term_to_ast_expr(x_arg, var_context, eval_arith=False)

    bound_stmts = _dispatch_goal(ctx, goal, k_stmts)

    deferred_stmts = _dispatch_goal(ctx, goal, [_yield_none_stmt()])
    thunk_body = deferred_stmts + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]
    thunk_fn = ast.FunctionDef(
        name=thunk_name,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=thunk_body,
        decorator_list=[], returns=None, type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )

    get_old = _assign(
        old_var,
        _call(_name("_get_attr"), _name(x_var), ast.Constant(value="freeze")),
    )

    make_goals = _assign(
        goals_var,
        ast.IfExp(
            test=_name(old_var),
            body=_call(_name("list"), _name(old_var)),
            orelse=ast.List(elts=[], ctx=ast.Load()),
        ),
    )

    append_thunk = ast.Expr(
        value=_call(
            _attr(goals_var, "append"),
            _name(thunk_name),
        ),
    )

    put_attr_stmt = ast.Expr(
        value=_call(
            _name("_put_attr"),
            _name(x_var),
            ast.Constant(value="freeze"),
            _name(goals_var),
            _name(trail_name),
        ),
    )

    check = ast.If(
        test=ast.UnaryOp(
            op=ast.Not(),
            operand=_call(_name("is_var"), _name(x_var)),
        ),
        body=bound_stmts or [ast.Pass()],
        orelse=[
            thunk_fn,
            get_old,
            make_goals,
            append_thunk,
            put_attr_stmt,
        ] + (k_stmts or [ast.Pass()]),
    )

    return [
        _assign(x_var, _call(_name("deref"), x_expr)),
        check,
    ]


def _compile_when(ctx: CompilationContext, cond, goal, k_stmts):
    """Compile when(Cond, Goal) — delay Goal until Cond is satisfied."""
    from .goal_shallow import _dispatch_goal
    var_context = ctx.var_context
    trail_name = ctx.trail_name

    # when(nonvar(X), Goal) → freeze(X, Goal)
    if (isinstance(cond, AstCall)
            and isinstance(cond.func, AstLoadName)
            and cond.func.name == "nonvar"
            and len(cond.args) == 1):
        return _compile_freeze(ctx, cond.args[0], goal, k_stmts)

    # when((C1, C2), Goal) → when(C1, when(C2, Goal))
    if isinstance(cond, And):
        inner_when = AstCall(
            func=AstLoadName(name="when"),
            args=[cond.right, goal],
            kwargs=[],
        )
        return _compile_when(ctx, cond.left, inner_when, k_stmts)

    thunk_name = _fresh("_when_thunk")
    deferred_stmts = _dispatch_goal(ctx, goal, [_yield_none_stmt()])
    thunk_body = deferred_stmts + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]
    thunk_fn = ast.FunctionDef(
        name=thunk_name,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=thunk_body,
        decorator_list=[], returns=None, type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )

    cond_expr = term_to_ast_expr(cond, var_context, eval_arith=False)

    if (isinstance(cond, AstCall)
            and isinstance(cond.func, AstLoadName)
            and cond.func.name == "ground"
            and len(cond.args) == 1):
        install_call = ast.Expr(value=_call(
            _name("_install_when_ground"),
            term_to_ast_expr(cond.args[0], var_context, eval_arith=False),
            _name(thunk_name),
            _name(trail_name),
        ))
        return [thunk_fn, install_call] + (k_stmts or [])

    if isinstance(cond, Or):
        c1_expr = term_to_ast_expr(cond.left, var_context, eval_arith=False)
        c2_expr = term_to_ast_expr(cond.right, var_context, eval_arith=False)
        install_call = ast.Expr(value=_call(
            _name("_install_when_disjunction"),
            c1_expr,
            c2_expr,
            _name(thunk_name),
            _name(trail_name),
        ))
        return [thunk_fn, install_call] + (k_stmts or [])

    install_call = ast.Expr(value=_call(
        _name("_install_when_condition"),
        cond_expr,
        _name(thunk_name),
        _name(trail_name),
    ))
    return [thunk_fn, install_call] + (k_stmts or [])


def _compile_find_all_core(
    ctx: CompilationContext,
    template: Any,
    inner_goal: Any,
    bag: Any,
    k_stmts: list[ast.stmt],
    *,
    fail_on_empty: bool = False,
    dedup: bool = False,
) -> list[ast.stmt]:
    """Compile find_all/3, bag_of/3, set_of/3 as special forms."""
    from .goal_shallow import _dispatch_goal
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    results_var = _fresh("_fa_results")
    mark_var = _fresh("_fa_m")
    gen_name = _fresh("_fa_gen")
    unify_mark = _fresh("_fa_um")

    template_expr = term_to_ast_expr(template, var_context, eval_arith=False)
    bag_expr = term_to_ast_expr(bag, var_context, eval_arith=False)

    inner_stmts = _dispatch_goal(ctx, inner_goal, [_yield_none_stmt()])
    gen_body = inner_stmts + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]
    gen_fn = ast.FunctionDef(
        name=gen_name,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=gen_body,
        decorator_list=[], returns=None, type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )

    append_call = ast.Expr(value=_call(
        _attr(results_var, "append"),
        _call(_name("_deref_walk"), template_expr),
    ))
    collect_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(gen_name)),
        body=[append_call],
        orelse=[],
    )

    unify_block = [
        _assign_mark(unify_mark, trail_name),
        ast.If(
            test=_call(_name("unify"), bag_expr, _name(results_var), _name(trail_name)),
            body=k_stmts or [ast.Pass()],
            orelse=[],
        ),
        _undo_stmt(unify_mark, trail_name),
    ]

    stmts: list[ast.stmt] = [
        _assign(results_var, ast.List(elts=[], ctx=ast.Load())),
        _assign_mark(mark_var, trail_name),
        gen_fn,
        collect_loop,
        _undo_stmt(mark_var, trail_name),
    ]

    if dedup:
        stmts.append(_assign(
            results_var,
            _call(_name("_set_of_dedup"), _name(results_var)),
        ))

    if fail_on_empty:
        stmts.append(ast.If(
            test=_name(results_var),
            body=unify_block,
            orelse=[],
        ))
    else:
        stmts.extend(unify_block)

    return stmts


# ── throw/catch compilation (V2-14) ─────────────────────────────────────────


def _catcher_to_structural(term: Any) -> Any:
    """Recursively convert Call nodes to Compound in a catcher term."""
    if isinstance(term, Call) and isinstance(term.func, LoadName) and not term.kwargs:
        new_args = [_catcher_to_structural(a) for a in term.args]
        return Compound(term.func.name, tuple(new_args))
    return term


def _compile_throw(
    ctx: CompilationContext,
    term_arg: Any,
) -> list[ast.stmt]:
    """Compile throw(Term) — raise LogicException(term_expr)."""
    var_context = ctx.var_context
    term_expr = term_to_ast_expr(term_arg, var_context, eval_arith=False)
    return [
        ast.Raise(exc=_call(_name("_LogicException"), term_expr)),
    ]


def _compile_catch_impl(
    ctx: CompilationContext,
    catcher: Any,
    *,
    goal_body_stmts: list[ast.stmt],
    recovery_body_stmts: list[ast.stmt],
    always_catch: bool,
) -> list[ast.stmt]:
    """Shared catch-block assembly."""
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    catch_mark = _fresh("_catch_m")
    exc_name = _fresh("_exc")
    term_name = _fresh("_term")
    unify_mark = _fresh("_catch_um")

    catcher_expr = term_to_ast_expr(_catcher_to_structural(catcher), var_context, eval_arith=False)

    term_extract = _assign(
        term_name,
        ast.IfExp(
            test=_call(_name("isinstance"), _name(exc_name), _name("_LogicException")),
            body=ast.Attribute(value=_name(exc_name), attr="term", ctx=ast.Load()),
            orelse=_call(_name("_python_error_term"), _name(exc_name)),
        ),
    )

    orelse_stmts: list[ast.stmt] = (
        [] if always_catch
        else [_undo_stmt(unify_mark, trail_name), ast.Raise()]
    )
    except_body: list[ast.stmt] = [
        term_extract,
        _undo_stmt(catch_mark, trail_name),
        _assign_mark(unify_mark, trail_name),
        ast.If(
            test=_call(
                _name("unify"), catcher_expr, _name(term_name), _name(trail_name),
            ),
            body=recovery_body_stmts or [ast.Pass()],
            orelse=orelse_stmts or [ast.Pass()],
        ),
        _undo_stmt(unify_mark, trail_name),
    ]

    handler = ast.ExceptHandler(
        type=_name("Exception"),
        name=exc_name,
        body=except_body,
    )

    try_block = ast.Try(
        body=goal_body_stmts,
        handlers=[handler],
        orelse=[],
        finalbody=[],
    )

    return [_assign_mark(catch_mark, trail_name), try_block]


def _make_catch_subgen_fn_and_loop(
    name_prefix: str,
    compiled_stmts: list[ast.stmt],
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Wrap shallow-compiled *compiled_stmts* as a sub-generator ``def`` + ``for`` loop."""
    gen_name = _fresh(name_prefix)
    gen_body = compiled_stmts + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]
    gen_fn = ast.FunctionDef(
        name=gen_name,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=gen_body,
        decorator_list=[], returns=None, type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )
    loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(gen_name)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )
    return [gen_fn, loop]


def _compile_catch(
    ctx: CompilationContext,
    goal_arg: Any,
    catcher: Any,
    recovery: Any,
    k_stmts: list[ast.stmt],
    *,
    always_catch: bool = False,
) -> list[ast.stmt]:
    """Compile catch(Goal, Catcher, Recovery) in simple mode."""
    from .goal_shallow import _dispatch_goal
    goal_stmts = _dispatch_goal(ctx, goal_arg, [_yield_none_stmt()])
    recovery_stmts = _dispatch_goal(ctx, recovery, [_yield_none_stmt()])

    goal_gen_fn, goal_loop = _make_catch_subgen_fn_and_loop(
        "_catch_gen", goal_stmts, k_stmts,
    )
    rec_gen_fn, rec_loop = _make_catch_subgen_fn_and_loop(
        "_catch_rec", recovery_stmts, k_stmts,
    )

    body = _compile_catch_impl(
        ctx, catcher,
        goal_body_stmts=[goal_loop],
        recovery_body_stmts=[rec_gen_fn, rec_loop],
        always_catch=always_catch,
    )
    return [body[0], goal_gen_fn, body[1]]


def _compile_catch_trampoline(
    ctx: CompilationContext,
    goal_arg: Any,
    catcher: Any,
    recovery: Any,
    k_stmts: list[ast.stmt],
    *,
    always_catch: bool = False,
) -> list[ast.stmt]:
    """Compile catch(Goal, Catcher, Recovery) in trampoline mode."""
    from .goal_trampoline import _dispatch_goal_trampoline
    goal_stmts = _dispatch_goal_trampoline(ctx, goal_arg, k_stmts)
    recovery_stmts = _dispatch_goal_trampoline(ctx, recovery, k_stmts)
    return _compile_catch_impl(
        ctx, catcher,
        goal_body_stmts=goal_stmts,
        recovery_body_stmts=recovery_stmts,
        always_catch=always_catch,
    )


# ── Goal lambda compilation ──────────────────────────────────────────────────


def _compile_goal_lambda(
    ctx: CompilationContext,
    lambda_node: Lambda,
) -> tuple[str, ast.FunctionDef]:
    """Compile a Lambda node to a simple-mode dispatch function."""
    from .goal_shallow import _dispatch_goal
    enclosing_var_context = ctx.var_context
    trail_name = ctx.trail_name
    func_name = _fresh("_lambda")

    body_vc: dict[int, str] = dict(enclosing_var_context)
    param_arg_names: list[str] = [param.name for param in lambda_node.params.params]

    body_goals = _flatten_conjunction(lambda_node.body)
    alloc_stmts = _preallocate_body_vars(body_goals, body_vc)

    body_ctx = ctx.replace(var_context=body_vc)
    k: list[ast.stmt] = [_yield_none_stmt()]
    for goal in reversed(body_goals):
        k = _dispatch_goal(body_ctx, goal, k)

    body_stmts = alloc_stmts + k + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]

    func_args = ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=n) for n in param_arg_names] + [
            ast.arg(arg=trail_name),
            ast.arg(arg=_K_PARAM_NAME),
        ],
        vararg=None,
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=None,
        defaults=[],
    )

    func_def = ast.FunctionDef(
        name=func_name,
        args=func_args,
        body=body_stmts,
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)

    return func_name, func_def


def _flatten_conjunction(goal) -> list:
    """flatten nested And nodes into a list of goals."""
    if isinstance(goal, And):
        return _flatten_conjunction(goal.left) + _flatten_conjunction(goal.right)
    return [goal]


def _hoist_lambda_args(
    ctx: CompilationContext,
    ordered_args: list,
) -> tuple[list, list[ast.stmt]]:
    """Scan call args for Lambda nodes; compile them and replace with name refs."""
    lambda_defs: list[ast.stmt] = []
    processed: list = []
    for a in ordered_args:
        if isinstance(a, Lambda):
            func_name, func_def = _compile_goal_lambda(ctx, a)
            lambda_defs.append(func_def)
            processed.append(LoadName(name=func_name))
        else:
            processed.append(a)
    return processed, lambda_defs
