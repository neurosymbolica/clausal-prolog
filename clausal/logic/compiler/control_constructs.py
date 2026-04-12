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
from . import _monolith as _m
from clausal.pythonic_ast.nodes import Keyword as KWNode  # noqa: E402

# Aliases preserved from the pre-split monolith (Call/LoadName from the AST).
AstCall = Call
AstLoadName = LoadName


def _compile_arith_cmp(
    l: Any,
    r: Any,
    ast_op: ast.cmpop,
    var_context: dict[int, str],
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    l_expr = arith_to_ast_expr(l, var_context)
    r_expr = arith_to_ast_expr(r, var_context)
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]


def _deref_cmp(
    l: Any,
    r: Any,
    ast_op: ast.cmpop,
    var_context: dict[int, str],
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a structural comparison using deref on both sides."""
    l_expr = _call(_name("deref"), term_to_ast_expr(l, var_context, eval_arith=False))
    r_expr = _call(_name("deref"), term_to_ast_expr(r, var_context, eval_arith=False))
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]
def _compile_once(inner, db, var_context, trail_name, k_stmts):
    """Compile once(goal) — take first solution of inner goal, then continue."""
    once_gen = _fresh("_once_gen")
    inner_stmts = _m.compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
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


def _compile_call_nth(inner, n_arg, db, var_context, trail_name, k_stmts):
    """Compile call_nth(Goal, N) — succeed on the Nth solution of Goal only.

    Generates::

        _cn_count_N = 0
        _cn_n_N = deref(<n_expr>)
        if not isinstance(_cn_n_N, int) or _cn_n_N < 1:
            raise _LogicException(_type_error("positive_integer", _cn_n_N, "call_nth/2"))
        _cn_m_N = trail.mark()
        def _cn_gen_N():
            <compiled inner goal with k = [yield None]>
            return; yield
        for _ in _cn_gen_N():
            _cn_count_N += 1
            if _cn_count_N == _cn_n_N:
                <k_stmts>
                break
        trail.undo(_cn_m_N)
    """
    count_var = _fresh("_cn_count")
    n_var = _fresh("_cn_n")
    mark_var = _fresh("_cn_m")
    gen_name = _fresh("_cn_gen")

    n_expr = term_to_ast_expr(n_arg, var_context, eval_arith=True)

    inner_stmts = _m.compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
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

    # for loop: count solutions, break at Nth
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


def _compile_count_all(inner, count_arg, db, var_context, trail_name, k_stmts):
    """Compile count_all(Goal, Count) — count solutions without collecting.

    Generates::

        _ca_n_N = 0
        _ca_m_N = trail.mark()
        def _ca_gen_N():
            <compiled inner goal with k = [yield None]>
            return; yield
        for _ in _ca_gen_N():
            _ca_n_N += 1
        trail.undo(_ca_m_N)
        _ca_um_N = trail.mark()
        if unify(<count_expr>, _ca_n_N, trail):
            <k_stmts>
        trail.undo(_ca_um_N)
    """
    n_var = _fresh("_ca_n")
    mark_var = _fresh("_ca_m")
    gen_name = _fresh("_ca_gen")
    unify_mark = _fresh("_ca_um")

    count_expr = term_to_ast_expr(count_arg, var_context, eval_arith=False)

    inner_stmts = _m.compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
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


def _compile_setup_call_cleanup(setup, call, cleanup, db, var_context, trail_name, k_stmts):
    """Compile setup_call_cleanup(Setup, Call, Cleanup) — deterministic cleanup.

    Generates::

        _scc_m_N = trail.mark()
        def _scc_setup_N():
            <compiled Setup with k = [yield None]>
            return; yield
        _scc_ok_N = False
        for _ in _scc_setup_N():
            _scc_ok_N = True
            break
        if _scc_ok_N:
            _scc_exc_N = None
            def _scc_call_N():
                <compiled Call with k = [yield None]>
                return; yield
            try:
                for _ in _scc_call_N():
                    <k_stmts>
            except Exception as _scc_e_N:
                _scc_exc_N = _scc_e_N
            finally:
                def _scc_cleanup_N():
                    <compiled Cleanup with k = [yield None]>
                    return; yield
                for _ in _scc_cleanup_N():
                    break
                if _scc_exc_N is not None:
                    raise _scc_exc_N
    """
    mark_var = _fresh("_scc_m")
    setup_gen = _fresh("_scc_setup")
    ok_var = _fresh("_scc_ok")
    call_gen = _fresh("_scc_call")
    exc_var = _fresh("_scc_exc")
    exc_e = _fresh("_scc_e")
    cleanup_gen = _fresh("_scc_cleanup")

    def _make_sub_gen(name, goal):
        stmts = _m.compile_goal(goal, db, var_context, trail_name, [_yield_none_stmt()])
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

    # Setup loop — run once, set ok flag
    setup_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(setup_gen)),
        body=[
            _assign(ok_var, ast.Constant(value=True)),
            ast.Break(),
        ],
        orelse=[],
    )

    # Call loop
    call_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(call_gen)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )

    # Cleanup loop — run once
    cleanup_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(cleanup_gen)),
        body=[ast.Break()],
        orelse=[],
    )

    # Exception handler
    handler = ast.ExceptHandler(
        type=_name("Exception"),
        name=exc_e,
        body=[_assign(exc_var, _name(exc_e))],
    )

    # Re-raise if exception
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

    # if ok: try/finally
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


def _compile_freeze(x_arg, goal, db, var_context, trail_name, k_stmts):
    """Compile freeze(X, Goal) — delay Goal until X is bound.

    Generates::

        _fz_x_N = deref(<x_expr>)
        if not is_var(_fz_x_N):
            # Already bound — run Goal immediately
            <compiled Goal with k = k_stmts>
        else:
            def _fz_thunk_N():
                <compiled Goal with k = [yield None]>
                return; yield
            _fz_old_N = _get_attr(_fz_x_N, "freeze")
            _fz_goals_N = list(_fz_old_N) if _fz_old_N else []
            _fz_goals_N.append(_fz_thunk_N)
            _put_attr(_fz_x_N, "freeze", _fz_goals_N, trail)
            <k_stmts>
    """
    x_var = _fresh("_fz_x")
    thunk_name = _fresh("_fz_thunk")
    old_var = _fresh("_fz_old")
    goals_var = _fresh("_fz_goals")

    x_expr = term_to_ast_expr(x_arg, var_context, eval_arith=False)

    # Compile goal for the "already bound" branch (inline with k_stmts)
    bound_stmts = _m.compile_goal(goal, db, var_context, trail_name, k_stmts)

    # Compile goal as a thunk (closure) for the "deferred" branch
    deferred_stmts = _m.compile_goal(goal, db, var_context, trail_name, [_yield_none_stmt()])
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

    # _fz_old_N = _get_attr(_fz_x_N, "freeze")
    get_old = _assign(
        old_var,
        _call(_name("_get_attr"), _name(x_var), ast.Constant(value="freeze")),
    )

    # _fz_goals_N = list(_fz_old_N) if _fz_old_N else []
    make_goals = _assign(
        goals_var,
        ast.IfExp(
            test=_name(old_var),
            body=_call(_name("list"), _name(old_var)),
            orelse=ast.List(elts=[], ctx=ast.Load()),
        ),
    )

    # _fz_goals_N.append(_fz_thunk_N)
    append_thunk = ast.Expr(
        value=_call(
            _attr(goals_var, "append"),
            _name(thunk_name),
        ),
    )

    # _put_attr(_fz_x_N, "freeze", _fz_goals_N, trail)
    put_attr_stmt = ast.Expr(
        value=_call(
            _name("_put_attr"),
            _name(x_var),
            ast.Constant(value="freeze"),
            _name(goals_var),
            _name(trail_name),
        ),
    )

    # if not is_var(...): <bound> else: <deferred>
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


def _compile_when(cond, goal, db, var_context, trail_name, k_stmts):
    """Compile when(Cond, Goal) — delay Goal until Cond is satisfied.

    Handles common conditions at compile time:
    - ``when(nonvar(X), Goal)`` → compiles as ``freeze(X, Goal)``
    - ``when(And(C1, C2), Goal)`` → ``when(C1, when(C2, Goal))``
    - ``when(ground(X), Goal)`` → runtime ``_install_when_ground``
    - ``when(Or(C1, C2), Goal)`` → runtime ``_install_when_disjunction``
    """

    # when(nonvar(X), Goal) → freeze(X, Goal)
    if (isinstance(cond, AstCall)
            and isinstance(cond.func, AstLoadName)
            and cond.func.name == "nonvar"
            and len(cond.args) == 1):
        return _compile_freeze(cond.args[0], goal, db, var_context, trail_name, k_stmts)

    # when((C1, C2), Goal) → when(C1, when(C2, Goal)) [conjunction]
    if isinstance(cond, And):
        inner_when = AstCall(
            func=AstLoadName(name="when"),
            args=[cond.right, goal],
            kwargs=[],
        )
        return _compile_when(cond.left, inner_when, db, var_context, trail_name, k_stmts)

    # For ground and Or conditions, use runtime dispatch.
    # Compile goal as thunk, emit runtime _install_when_condition call.
    thunk_name = _fresh("_when_thunk")
    deferred_stmts = _m.compile_goal(goal, db, var_context, trail_name, [_yield_none_stmt()])
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

    # when(ground(X), Goal)
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

    # when((C1; C2), Goal) [disjunction]
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

    # Fallback: runtime condition dispatch
    install_call = ast.Expr(value=_call(
        _name("_install_when_condition"),
        cond_expr,
        _name(thunk_name),
        _name(trail_name),
    ))
    return [thunk_fn, install_call] + (k_stmts or [])


def _compile_find_all_core(
    template: Any,
    inner_goal: Any,
    bag: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    *,
    fail_on_empty: bool = False,
    dedup: bool = False,
) -> list[ast.stmt]:
    """Compile find_all/3, bag_of/3, set_of/3 as special forms.

    Generates::

        _fa_results_N = []
        _fa_m_N = trail.mark()
        def _fa_gen_N():
            <compiled inner_goal with k = [yield None]>
            return; yield
        for _ in _fa_gen_N():
            _fa_results_N.append(_deref_walk(<template_expr>))
        trail.undo(_fa_m_N)
        # optional dedup: _fa_results_N = _set_of_dedup(_fa_results_N)
        # optional empty check: if _fa_results_N:
        _fa_um_N = trail.mark()
        if unify(<bag_expr>, _fa_results_N, trail):
            <k_stmts>
        trail.undo(_fa_um_N)
    """
    results_var = _fresh("_fa_results")
    mark_var = _fresh("_fa_m")
    gen_name = _fresh("_fa_gen")
    unify_mark = _fresh("_fa_um")

    template_expr = term_to_ast_expr(template, var_context, eval_arith=False)
    bag_expr = term_to_ast_expr(bag, var_context, eval_arith=False)

    # Compile inner goal as sub-generator (simple mode, like once/NAF)
    inner_stmts = _m.compile_goal(inner_goal, db, var_context, trail_name, [_yield_none_stmt()])
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

    # Build the for-loop that collects results
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

    # Unify bag with results + k_stmts
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

    # Optional dedup (set_of)
    if dedup:
        stmts.append(_assign(
            results_var,
            _call(_name("_set_of_dedup"), _name(results_var)),
        ))

    # Optional empty check (bag_of, set_of)
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
    """Recursively convert Call nodes to Compound in a catcher term.

    ``catch/3`` catcher patterns and ``Catch/2`` error patterns appear in
    *term* position, not goal position. ``Call(LoadName("Foo"), [arg])``
    should construct ``Compound("Foo", (arg,))`` at runtime, not call the
    dispatch function for ``Foo``. This avoids collisions with
    ``_inject_call_targets`` which replaces functor names with
    ``_DbDispatchAdapter`` objects that are not callable as constructors.
    """
    if isinstance(term, Call) and isinstance(term.func, LoadName) and not term.kwargs:
        new_args = [_catcher_to_structural(a) for a in term.args]
        return Compound(term.func.name, tuple(new_args))
    return term


def _compile_throw(
    term_arg: Any,
    var_context: dict[int, str],
) -> list[ast.stmt]:
    """Compile throw(Term) — raise LogicException(term_expr).

    Same in both simple and trampoline modes — Python raise propagates naturally.
    """
    term_expr = term_to_ast_expr(term_arg, var_context, eval_arith=False)
    return [
        ast.Raise(exc=_call(_name("_LogicException"), term_expr)),
    ]


def _compile_catch(
    goal_arg: Any,
    catcher: Any,
    recovery: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    always_catch: bool = False,
) -> list[ast.stmt]:
    """Compile catch(Goal, Catcher, Recovery) in simple mode.

    Catches both ``throw/1`` (LogicException) and plain Python exceptions.
    Python exceptions are wrapped as ``ClassName(Message)`` so that Clausal
    code can match them the same way as logic terms::

        catch(Goal, UnitsMismatch(_), Recovery)
        catch_error(Goal, Error)                # always_catch=True, recovery=True
        catch_recover(Goal, Error, Recovery)  # always_catch=True

    Generates::

        _catch_mark_N = trail.mark()
        def _catch_gen_N():
            <compiled goal with k = [yield None]>
            return; yield
        try:
            for _ in _catch_gen_N():
                <k_stmts>
        except Exception as _exc_N:
            _term_N = _exc_N.term if isinstance(_exc_N, _LogicException) \\
                      else _python_error_term(_exc_N)
            trail.undo(_catch_mark_N)
            _catch_um_N = trail.mark()
            if unify(<catcher_expr>, _term_N, trail):
                def _catch_rec_N():
                    <compiled recovery with k = [yield None]>
                    return; yield
                for _ in _catch_rec_N():
                    <k_stmts>
            else:
                trail.undo(_catch_um_N)
                raise
            trail.undo(_catch_um_N)
    """
    catch_mark = _fresh("_catch_m")
    gen_name = _fresh("_catch_gen")
    exc_name = _fresh("_exc")
    term_name = _fresh("_term")
    unify_mark = _fresh("_catch_um")
    rec_gen_name = _fresh("_catch_rec")

    catcher_expr = term_to_ast_expr(_catcher_to_structural(catcher), var_context, eval_arith=False)

    # Compile inner goal as sub-generator (simple mode)
    inner_stmts = _m.compile_goal(goal_arg, db, var_context, trail_name, [_yield_none_stmt()])
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

    # for loop over goal generator
    goal_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(gen_name)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )

    # Compile recovery as sub-generator (simple mode)
    recovery_stmts = _m.compile_goal(recovery, db, var_context, trail_name, [_yield_none_stmt()])
    rec_body = recovery_stmts + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]
    rec_fn = ast.FunctionDef(
        name=rec_gen_name,
        args=ast.arguments(
            posonlyargs=[], args=[], vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=rec_body,
        decorator_list=[], returns=None, type_comment=None,
        **_m._EXTRA_FUNCDEF,
    )

    # Recovery for loop
    rec_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(rec_gen_name)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )

    # term extraction: _LogicException carries .term; Python exceptions are wrapped
    term_extract = _assign(
        term_name,
        ast.IfExp(
            test=_call(_name("isinstance"), _name(exc_name), _name("_LogicException")),
            body=ast.Attribute(value=_name(exc_name), attr="term", ctx=ast.Load()),
            orelse=_call(_name("_python_error_term"), _name(exc_name)),
        ),
    )

    # except block: extract term, undo trail, match catcher, run recovery
    # always_catch=True (catch_error/2, catch_recover/3): never re-raise on mismatch
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
                _name("unify"),
                catcher_expr,
                _name(term_name),
                _name(trail_name),
            ),
            body=[rec_fn, rec_loop],
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
        body=[goal_loop],
        handlers=[handler],
        orelse=[],
        finalbody=[],
    )

    return [
        _assign_mark(catch_mark, trail_name),
        gen_fn,
        try_block,
    ]


def _compile_catch_trampoline(
    goal_arg: Any,
    catcher: Any,
    recovery: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    self_name: str,
    always_catch: bool = False,
) -> list[ast.stmt]:
    """Compile catch(Goal, Catcher, Recovery) in trampoline mode.

    Catches both ``throw/1`` (LogicException) and plain Python exceptions.
    Python exceptions are wrapped as ``ClassName(Message)``.

    Generates::

        _catch_mark_N = trail.mark()
        try:
            _gen_N = StepGenerator(goal_dispatch, this_generator, ..., trail)
            _st_N = (yield (_gen_N, None))
            while _st_N is not _DONE:
                <k_stmts>
                _st_N = (yield (_gen_N, None))
        except Exception as _exc_N:
            _term_N = _exc_N.term if isinstance(_exc_N, _LogicException) \\
                      else _python_error_term(_exc_N)
            trail.undo(_catch_mark_N)
            _catch_um_N = trail.mark()
            if unify(<catcher_expr>, _term_N, trail):
                _gen_rec_N = StepGenerator(rec_dispatch, this_generator, ..., trail)
                _st_rec_N = (yield (_gen_rec_N, None))
                while _st_rec_N is not _DONE:
                    <k_stmts>
                    _st_rec_N = (yield (_gen_rec_N, None))
            else:
                trail.undo(_catch_um_N)
                raise
            trail.undo(_catch_um_N)
    """
    catch_mark = _fresh("_catch_m")
    exc_name = _fresh("_exc")
    term_name = _fresh("_term")
    unify_mark = _fresh("_catch_um")

    catcher_expr = term_to_ast_expr(_catcher_to_structural(catcher), var_context, eval_arith=False)

    # Compile goal as trampoline call
    goal_stmts = _m.compile_goal_trampoline(
        goal_arg, db, var_context, trail_name, k_stmts, self_name,
    )

    # Compile recovery as trampoline call
    recovery_stmts = _m.compile_goal_trampoline(
        recovery, db, var_context, trail_name, k_stmts, self_name,
    )

    # term extraction: _LogicException carries .term; Python exceptions are wrapped
    term_extract = _assign(
        term_name,
        ast.IfExp(
            test=_call(_name("isinstance"), _name(exc_name), _name("_LogicException")),
            body=ast.Attribute(value=_name(exc_name), attr="term", ctx=ast.Load()),
            orelse=_call(_name("_python_error_term"), _name(exc_name)),
        ),
    )

    # except block: extract term, undo trail, match catcher, run recovery
    # always_catch=True (catch_error/2, catch_recover/3): never re-raise on mismatch
    orelse_stmts_t: list[ast.stmt] = (
        [] if always_catch
        else [_undo_stmt(unify_mark, trail_name), ast.Raise()]
    )
    except_body: list[ast.stmt] = [
        term_extract,
        _undo_stmt(catch_mark, trail_name),
        _assign_mark(unify_mark, trail_name),
        ast.If(
            test=_call(
                _name("unify"),
                catcher_expr,
                _name(term_name),
                _name(trail_name),
            ),
            body=recovery_stmts or [ast.Pass()],
            orelse=orelse_stmts_t or [ast.Pass()],
        ),
        _undo_stmt(unify_mark, trail_name),
    ]

    handler = ast.ExceptHandler(
        type=_name("Exception"),
        name=exc_name,
        body=except_body,
    )

    try_block = ast.Try(
        body=goal_stmts,
        handlers=[handler],
        orelse=[],
        finalbody=[],
    )

    return [
        _assign_mark(catch_mark, trail_name),
        try_block,
    ]


# ── Goal lambda compilation ──────────────────────────────────────────────────


def _compile_goal_lambda(
    lambda_node: Lambda,
    enclosing_var_context: dict[int, str],
    db: Database,
    trail_name: str,
) -> tuple[str, ast.FunctionDef]:
    """Compile a Lambda node to a simple-mode dispatch function.

    Returns ``(func_name, func_def)`` — a FunctionDef statement that should be
    emitted before the enclosing call, and the name to reference it by.

    The generated function has signature::

        def _lambda_N(X_, Y_, trail, k):
            # body-only Var allocations
            # compiled goal body with k_stmts = [yield None]
            return; yield  # ensure generator

    Lambda params are direct function arguments (not Var + unify).
    Param references in the body are LoadName nodes — term_to_ast_expr
    maps them to the function arg names directly.
    Captured variables from the enclosing scope are Python closure references.
    """
    func_name = _fresh("_lambda")

    # Inherit captured vars from enclosing scope.
    # Param references are LoadName nodes (not Vars), so they don't need
    # entries in var_context — term_to_ast_expr handles them directly.
    body_vc: dict[int, str] = dict(enclosing_var_context)
    param_arg_names: list[str] = [param.name for param in lambda_node.params.params]

    # Compile the lambda body goals
    body_goals = _flatten_conjunction(lambda_node.body)
    alloc_stmts = _preallocate_body_vars(body_goals, body_vc)

    k: list[ast.stmt] = [_yield_none_stmt()]
    for goal in reversed(body_goals):
        k = _m.compile_goal(goal, db, body_vc, trail_name, k)

    body_stmts = alloc_stmts + k + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]

    # Build the function arguments: X_, Y_, ..., trail, k
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
    ordered_args: list,
    enclosing_var_context: dict[int, str],
    db: Database,
    trail_name: str,
) -> tuple[list, list[ast.stmt]]:
    """Scan call args for Lambda nodes; compile them and replace with name refs.

    Returns ``(processed_args, lambda_defs)`` where processed_args has Lambda
    nodes replaced with LoadName references to the generated functions, and
    lambda_defs is the list of FunctionDef statements to emit before the call.
    """
    lambda_defs: list[ast.stmt] = []
    processed: list = []
    for a in ordered_args:
        if isinstance(a, Lambda):
            func_name, func_def = _compile_goal_lambda(
                a, enclosing_var_context, db, trail_name,
            )
            lambda_defs.append(func_def)
            processed.append(LoadName(name=func_name))
        else:
            processed.append(a)
    return processed, lambda_defs
