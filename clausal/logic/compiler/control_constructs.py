"""Control-construct and meta-predicate goal compilation.

Compiles goals that wrap or transform other goals: once, call_nth,
count_all, setup_call_cleanup, freeze, when, find_all_core, throw,
catch (shallow + trampoline twins), goal lambdas, arithmetic /
structural comparisons, and the small helpers ``_flatten_conjunction``
and ``_hoist_lambda_args``.

Inner goal compilation (Slice D7c-β2): each helper routes inner goals
through the IR pipeline (:func:`terms_to_goalop` + strategy-specific
``lower``), not the legacy ``_dispatch_goal[_trampoline]`` dispatchers
which β3 will delete.  The local :func:`_lower_inner` /
:func:`_lower_inner_trampoline` wrappers are byte-identical to the
corresponding legacy dispatch at the shapes these helpers accept.

Cycle handling: ``goal_shallow`` / ``goal_trampoline`` import this
module, so the back-imports of ``lower_python_shallow`` /
``lower_python_trampoline`` inside the wrappers stay function-local
(ratified B4/B6 idiom).  ``_EXTRA_FUNCDEF`` lives in ``_ast_helpers``
(leaf; no cycle).
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
from clausal.logic.meta_predicate import MetaArg as _MetaArg

from ._ast_helpers import (
    _name, _attr, _call, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt, _in_iter_expr,
    _MARK_PREFIX, _TRAIL_PARAM_NAME, _K_PARAM_NAME,
    _THIS_GEN_NAME,
    _EXTRA_FUNCDEF,
    maybe_assert_located,
    stamp_predicate_funcdef,
)
from ._vars import _var_python_name, _collect_vars, _collect_bound_vars
from .globals_env import _preallocate_body_vars
from .terms_to_ast import term_to_ast_expr, arith_to_ast_expr
from .compile_ctx import CompilationContext
from clausal.pythonic_ast.nodes import Keyword as KWNode  # noqa: E402

# Aliases preserved from the pre-split monolith (Call/LoadName from the AST).
AstCall = Call
AstLoadName = LoadName


def _lower_inner(
    ctx: CompilationContext,
    inner: Any,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Byte-identical replacement for the legacy shallow dispatcher
    ``_dispatch_goal(ctx, inner, k_stmts)`` via the IR pipeline.

    Forces :class:`ShallowStrategy` on entry to match legacy semantics
    (inner sub-generators in ``once`` / ``findall`` / ``catch`` /
    goal-lambda bodies etc. are always compiled shallow regardless of
    the outer clause's strategy).  Wrapping *inner* in a singleton
    :func:`terms_to_goalop` call produces a :class:`Sequence` whose
    fold lowers identically to a single ``_dispatch_goal`` call.
    """
    from .strategy import ShallowStrategy
    from .terms_to_goalop import terms_to_goalop
    from . import lower_python_shallow
    if not isinstance(ctx.strategy, ShallowStrategy):
        ctx = ctx.replace(strategy=ShallowStrategy())
    ir = terms_to_goalop([inner], ctx.db)
    return lower_python_shallow.lower(ir, ctx, k_stmts)


def _lower_inner_trampoline(
    ctx: CompilationContext,
    inner: Any,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Trampoline counterpart to :func:`_lower_inner`.  Byte-identical
    replacement for ``_dispatch_goal_trampoline(ctx, inner, k_stmts)``
    via :mod:`.lower_python_trampoline`.
    """
    from .terms_to_goalop import terms_to_goalop
    from . import lower_python_trampoline
    ir = terms_to_goalop([inner], ctx.db)
    return lower_python_trampoline.lower(ir, ctx, k_stmts)


def _leader_stmt(leader_name: str) -> ast.stmt:
    """``leader = $current_leader()`` -- bind the condition target ONCE, at the
    collecting construct's entry.  Resolving it per solution would read the
    stack TOP, which is the streaming table's own entry while a tabled goal
    beneath is yielding, not the leader its conditions are credited to."""
    return _assign(leader_name, _call(_name("$current_leader")))


def _harvest_stmt(leader_name: str, bag_name: str) -> ast.stmt:
    """``$harvest_conditions(leader, bag)`` -- accumulate the WFS conditions
    this solution stands on, for a construct whose RESULT outlives it."""
    return ast.Expr(value=_call(
        _name("$harvest_conditions"), _name(leader_name), _name(bag_name)))


def _charge_stmt(trail_name: str, leader_name: str, bag_name: str) -> ast.stmt:
    """``$charge_conditions(trail, leader, bag)`` -- put the accumulated
    conditions back on that same leader once the construct has unwound its own
    mark, so they are retracted only by backtracking OVER the construct."""
    return ast.Expr(value=_call(
        _name("$charge_conditions"), _name(trail_name),
        _name(leader_name), _name(bag_name)))


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
    l_expr = _call(_name("$deref"), term_to_ast_expr(l, var_context, eval_arith=False))
    r_expr = _call(_name("$deref"), term_to_ast_expr(r, var_context, eval_arith=False))
    test = ast.Compare(left=l_expr, ops=[ast_op], comparators=[r_expr])
    return [_if(test, k_stmts)]


def _compile_once(ctx: CompilationContext, inner, k_stmts):
    """Compile once(goal) — take first solution of inner goal, then continue."""
    trail_name = ctx.trail_name
    once_gen = ctx.fresh("_once_gen")
    inner_stmts = _lower_inner(ctx, inner, [_yield_none_stmt()])
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
        **_EXTRA_FUNCDEF,
    )
    once_mark = ctx.fresh(_MARK_PREFIX)
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
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    count_var = ctx.fresh("_cn_count")
    n_var = ctx.fresh("_cn_n")
    mark_var = ctx.fresh("_cn_m")
    gen_name = ctx.fresh("_cn_gen")

    n_expr = term_to_ast_expr(n_arg, var_context, eval_arith=True)

    inner_stmts = _lower_inner(ctx, inner, [_yield_none_stmt()])
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
        **_EXTRA_FUNCDEF,
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
                _name("$LogicException"),
                _call(_name("$type_error"), ast.Constant(value="positive_integer"),
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
        _assign(n_var, _call(_name("$deref"), n_expr)),
        type_check,
        _assign_mark(mark_var, trail_name),
        gen_fn,
        goal_loop,
        _undo_stmt(mark_var, trail_name),
    ]


def _compile_count_all(ctx: CompilationContext, inner, count_arg, k_stmts):
    """Compile count_all(Goal, Count) — count solutions without collecting."""
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    n_var = ctx.fresh("_ca_n")
    mark_var = ctx.fresh("_ca_m")
    gen_name = ctx.fresh("_ca_gen")
    unify_mark = ctx.fresh("_ca_um")
    cond_bag = ctx.fresh("_ca_cond")
    cond_leader = ctx.fresh("_ca_cl")

    count_expr = term_to_ast_expr(count_arg, var_context, eval_arith=False)

    inner_stmts = _lower_inner(ctx, inner, [_yield_none_stmt()])
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
        **_EXTRA_FUNCDEF,
    )

    count_incr = ast.AugAssign(
        target=_name(n_var, ast.Store()),
        op=ast.Add(),
        value=ast.Constant(value=1),
    )
    goal_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(gen_name)),
        # A counted derivation may stand on WFS delays, and the count
        # survives the undo below: keep its conditions with it.
        body=[count_incr, _harvest_stmt(cond_leader, cond_bag)],
        orelse=[],
    )

    unify_check = ast.If(
        test=_call(_name("$unify"), count_expr, _name(n_var), _name(trail_name)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )

    return [
        _assign(n_var, ast.Constant(value=0)),
        _assign(cond_bag, ast.List(elts=[], ctx=ast.Load())),
        _leader_stmt(cond_leader),
        _assign_mark(mark_var, trail_name),
        gen_fn,
        goal_loop,
        _undo_stmt(mark_var, trail_name),
        _charge_stmt(trail_name, cond_leader, cond_bag),
        _assign_mark(unify_mark, trail_name),
        unify_check,
        _undo_stmt(unify_mark, trail_name),
    ]


def _compile_setup_call_cleanup(ctx: CompilationContext, setup, call, cleanup, k_stmts):
    """Compile setup_call_cleanup(Setup, Call, Cleanup) — deterministic cleanup."""
    trail_name = ctx.trail_name  # noqa: F841 — kept for symmetry with sibling helpers
    setup_gen = ctx.fresh("_scc_setup")
    ok_var = ctx.fresh("_scc_ok")
    call_gen = ctx.fresh("_scc_call")
    exc_var = ctx.fresh("_scc_exc")
    exc_e = ctx.fresh("_scc_e")
    cleanup_gen = ctx.fresh("_scc_cleanup")

    def _make_sub_gen(name, goal):
        stmts = _lower_inner(ctx, goal, [_yield_none_stmt()])
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
            **_EXTRA_FUNCDEF,
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

    # Note: an earlier emission allocated a ``_scc_m = trail.mark()``
    # snapshot here that was never consumed by any ``trail.undo``.
    # Slice F3's mark/undo invariant flagged it as dead (no observable
    # behaviour change from removal — the snapshot was written but
    # never read).  setup / call / cleanup do their own trail
    # management within their respective sub-generators.
    return [
        setup_fn,
        _assign(ok_var, ast.Constant(value=False)),
        setup_loop,
        if_ok,
    ]


def _compile_freeze(ctx: CompilationContext, x_arg, goal, k_stmts):
    """Compile freeze(X, Goal) — delay Goal until X is bound."""
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    x_var = ctx.fresh("_fz_x")
    thunk_name = ctx.fresh("_fz_thunk")
    old_var = ctx.fresh("_fz_old")
    goals_var = ctx.fresh("_fz_goals")

    x_expr = term_to_ast_expr(x_arg, var_context, eval_arith=False)

    bound_stmts = _lower_inner(ctx, goal, k_stmts)

    deferred_stmts = _lower_inner(ctx, goal, [_yield_none_stmt()])
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
        **_EXTRA_FUNCDEF,
    )

    get_old = _assign(
        old_var,
        _call(_name("$get_attr"), _name(x_var), ast.Constant(value="freeze")),
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
            _name("$put_attr"),
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
        _assign(x_var, _call(_name("$deref"), x_expr)),
        check,
    ]


def _compile_when(ctx: CompilationContext, cond, goal, k_stmts):
    """Compile when(Cond, Goal) — delay Goal until Cond is satisfied."""
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

    thunk_name = ctx.fresh("_when_thunk")
    deferred_stmts = _lower_inner(ctx, goal, [_yield_none_stmt()])
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
        **_EXTRA_FUNCDEF,
    )

    cond_expr = term_to_ast_expr(cond, var_context, eval_arith=False)

    if (isinstance(cond, AstCall)
            and isinstance(cond.func, AstLoadName)
            and cond.func.name == "ground"
            and len(cond.args) == 1):
        install_call = ast.Expr(value=_call(
            _name("$install_when_ground"),
            term_to_ast_expr(cond.args[0], var_context, eval_arith=False),
            _name(thunk_name),
            _name(trail_name),
        ))
        return [thunk_fn, install_call] + (k_stmts or [])

    if isinstance(cond, Or):
        c1_expr = term_to_ast_expr(cond.left, var_context, eval_arith=False)
        c2_expr = term_to_ast_expr(cond.right, var_context, eval_arith=False)
        install_call = ast.Expr(value=_call(
            _name("$install_when_disjunction"),
            c1_expr,
            c2_expr,
            _name(thunk_name),
            _name(trail_name),
        ))
        return [thunk_fn, install_call] + (k_stmts or [])

    install_call = ast.Expr(value=_call(
        _name("$install_when_condition"),
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
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    results_var = ctx.fresh("_fa_results")
    cond_bag = ctx.fresh("_fa_cond")
    cond_leader = ctx.fresh("_fa_cl")
    mark_var = ctx.fresh("_fa_m")
    gen_name = ctx.fresh("_fa_gen")
    unify_mark = ctx.fresh("_fa_um")

    template_expr = term_to_ast_expr(template, var_context, eval_arith=False)
    bag_expr = term_to_ast_expr(bag, var_context, eval_arith=False)

    inner_stmts = _lower_inner(ctx, inner_goal, [_yield_none_stmt()])
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
        **_EXTRA_FUNCDEF,
    )

    append_call = ast.Expr(value=_call(
        _attr(results_var, "append"),
        # A03-F006: collect a per-solution copy with fresh unbound vars (ISO
        # copy_term semantics) so rows don't share the caller's Var objects —
        # a later binding must not rewrite already-collected rows.
        _call(_name("$findall_copy"), template_expr),
    ))
    collect_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(gen_name)),
        # A collected row may stand on WFS delays, and the bag survives the
        # undo below: keep its conditions with it.
        body=[append_call, _harvest_stmt(cond_leader, cond_bag)],
        orelse=[],
    )

    unify_block = [
        _assign_mark(unify_mark, trail_name),
        ast.If(
            test=_call(_name("$unify"), bag_expr, _name(results_var), _name(trail_name)),
            body=k_stmts or [ast.Pass()],
            orelse=[],
        ),
        _undo_stmt(unify_mark, trail_name),
    ]

    # ISO 8.10.1.3 d / 8.10.2.3 c / 8.10.3.3 c: a bag that is neither a list
    # nor a partial list is type_error(list, Bag) -- checked BEFORE the goal
    # runs, as Scryer does (``findall(X, _, foo)`` is the type_error).
    who = "setof/3" if dedup else ("bagof/3" if fail_on_empty else "findall/3")
    stmts: list[ast.stmt] = [
        ast.Expr(value=_call(_name("$check_bag"), bag_expr,
                             ast.Constant(value=who))),
        _assign(results_var, ast.List(elts=[], ctx=ast.Load())),
        _assign(cond_bag, ast.List(elts=[], ctx=ast.Load())),
        _leader_stmt(cond_leader),
        _assign_mark(mark_var, trail_name),
        gen_fn,
        collect_loop,
        _undo_stmt(mark_var, trail_name),
        _charge_stmt(trail_name, cond_leader, cond_bag),
    ]

    if dedup:
        # setof/3 (the only dedup=True caller): sort into standard order AND
        # remove duplicates, per ISO / docs (A03-F005). findall/bagof are
        # dedup=False and keep insertion order + duplicates.
        stmts.append(_assign(
            results_var,
            _call(_name("$set_of_sort_dedup"), _name(results_var)),
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


def _lower_catcher(ctx: CompilationContext, catcher: Any) -> ast.expr:
    """Lower a catch/3 catcher so it matches the THROW form (A03-F004).

    A functor whose name the throw site lowers to a TERM — a class instance
    for a predicate/Python-minted functor, a CELL for a declared data functor
    (P3-2 Task 2) — must be lowered the same way here, or the catcher never
    matches what was thrown: ``unify(Compound('kab',(N,)), kab(7))`` is False,
    and so is ``unify(Compound('kab',(N,)), ('kab', 7))``.  Only names the
    throw site does NOT lower to a term (builtin ``error(...)`` terms, thrown
    as ``Compound``) fall back to ``_catcher_to_structural``.

    Both halves of the test are the throw site's own questions, asked in the
    throw site's own way: ``PredicateMeta`` binding -> class construction,
    ``cell_signature_for_name`` answers -> cell literal.  Either way the
    answer is produced by handing the catcher term to ``term_to_ast_expr``,
    which is literally the function the throw site uses.
    """
    from clausal.logic.predicate import is_declared_predicate_name  # noqa: PLC0415
    from .terms_to_ast import cell_signature_for_name  # noqa: PLC0415
    if (isinstance(catcher, Call) and isinstance(catcher.func, LoadName)
            and not catcher.kwargs):
        env = ctx.base_globals or {}
        resolved = env.get(catcher.func.name)
        if (is_declared_predicate_name(resolved, db=ctx.db)
                or cell_signature_for_name(catcher.func.name) is not None):
            # The throw site builds a term for this name → build the same
            # term here (term_to_ast_expr recurses into nested args too).
            return term_to_ast_expr(catcher, ctx.var_context, eval_arith=False)
    return term_to_ast_expr(
        _catcher_to_structural(catcher), ctx.var_context, eval_arith=False
    )


def _compile_throw(
    ctx: CompilationContext,
    term_arg: Any,
) -> list[ast.stmt]:
    """Compile throw(Term) -- raise ``$throw_ball(term_expr)``: a COPY of
    the ball, or instantiation_error for an unbound one (ISO 7.8.10; see
    ``globals_env._throw_ball``)."""
    var_context = ctx.var_context
    term_expr = term_to_ast_expr(term_arg, var_context, eval_arith=False)
    return [
        ast.Raise(exc=_call(_name("$throw_ball"), term_expr)),
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
    catch_mark = ctx.fresh("_catch_m")
    exc_name = ctx.fresh("_exc")
    term_name = ctx.fresh("_term")
    unify_mark = ctx.fresh("_catch_um")

    catcher_expr = _lower_catcher(ctx, catcher)

    term_extract = _assign(
        term_name,
        ast.IfExp(
            test=_call(_name("isinstance"), _name(exc_name), _name("$LogicException")),
            body=ast.Attribute(value=_name(exc_name), attr="term", ctx=ast.Load()),
            orelse=_call(_name("$python_error_term"), _name(exc_name)),
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
            # $catch_match: structural unify against the transliterated ball,
            # EXCEPT for a catcher that evaluated to a Python exception class
            # or instance (a ++ escape), which matches the ORIGINAL exception
            # object — see clausal.logic.exceptions.catch_match.
            test=_call(
                _name("$catch_match"), catcher_expr, _name(term_name),
                _name(exc_name), _name(trail_name),
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
    ctx: CompilationContext,
    name_prefix: str,
    compiled_stmts: list[ast.stmt],
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Wrap shallow-compiled *compiled_stmts* as a sub-generator ``def`` + ``for`` loop."""
    gen_name = ctx.fresh(name_prefix)
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
        **_EXTRA_FUNCDEF,
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
    """Compile catch(Goal, Catcher, Recovery) — strategy-driven.

    Shallow wraps *goal_arg* and *recovery* in sub-generators and drives
    them with ``for`` loops that execute *k_stmts* per solution; the
    try/except covers those loops.  Trampoline compiles *goal_arg* /
    *recovery* with *k_stmts* already embedded as the continuation; the
    try/except covers the yielding stmts directly.

    The structural split is captured here via ``ctx.strategy`` rather
    than in twin helpers — the shared ``_compile_catch_impl`` assembles
    the try/except/unify block given pre-compiled body statements.
    """
    from .strategy import TrampolineStrategy
    if isinstance(ctx.strategy, TrampolineStrategy):
        goal_stmts = _lower_inner_trampoline(ctx, goal_arg, k_stmts)
        recovery_stmts = _lower_inner_trampoline(ctx, recovery, k_stmts)
        return _compile_catch_impl(
            ctx, catcher,
            goal_body_stmts=goal_stmts,
            recovery_body_stmts=recovery_stmts,
            always_catch=always_catch,
        )

    goal_stmts = _lower_inner(ctx, goal_arg, [_yield_none_stmt()])
    recovery_stmts = _lower_inner(ctx, recovery, [_yield_none_stmt()])

    goal_gen_fn, goal_loop = _make_catch_subgen_fn_and_loop(
        ctx, "_catch_gen", goal_stmts, k_stmts,
    )
    rec_gen_fn, rec_loop = _make_catch_subgen_fn_and_loop(
        ctx, "_catch_rec", recovery_stmts, k_stmts,
    )

    body = _compile_catch_impl(
        ctx, catcher,
        goal_body_stmts=[goal_loop],
        recovery_body_stmts=[rec_gen_fn, rec_loop],
        always_catch=always_catch,
    )
    return [body[0], goal_gen_fn, body[1]]


# ── Goal lambda compilation ──────────────────────────────────────────────────


def _compile_goal_lambda(
    ctx: CompilationContext,
    lambda_node: Lambda,
) -> tuple[str, ast.FunctionDef]:
    """Compile a Lambda node to a simple-mode dispatch function."""
    from .strategy import ShallowStrategy
    from .terms_to_goalop import terms_to_goalop
    from . import lower_python_shallow
    enclosing_var_context = ctx.var_context
    trail_name = ctx.trail_name
    func_name = ctx.fresh("_lambda")

    body_vc: dict[int, str] = dict(enclosing_var_context)
    param_arg_names: list[str] = [param.name for param in lambda_node.params.params]

    body_goals = _flatten_conjunction(lambda_node.body)
    alloc_stmts = _preallocate_body_vars(body_goals, body_vc)

    body_ctx = ctx.replace(var_context=body_vc)
    if not isinstance(body_ctx.strategy, ShallowStrategy):
        body_ctx = body_ctx.replace(strategy=ShallowStrategy())
    body_ir = terms_to_goalop(body_goals, body_ctx.db)
    k = lower_python_shallow.lower(body_ir, body_ctx, [_yield_none_stmt()])

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
        **_EXTRA_FUNCDEF,
    )
    # Slice G5: meta-call sub-generator (once/findall/catch inner wrapper).
    # No clause list here — use the enclosing meta-call's position from
    # the active scope stack.  Falls back to SYNTHETIC_POSITION when the
    # caller didn't open a scope.
    from ._ast_helpers import _current_position, SYNTHETIC_POSITION
    pos = _current_position() or SYNTHETIC_POSITION
    func_def.lineno, func_def.col_offset, \
        func_def.end_lineno, func_def.end_col_offset = pos
    maybe_assert_located(func_def)

    return func_name, func_def


def _flatten_conjunction(goal) -> list:
    """flatten nested And nodes into a list of goals."""
    if isinstance(goal, And):
        return _flatten_conjunction(goal.left) + _flatten_conjunction(goal.right)
    return [goal]


def _hoist_lambdas_in_term(
    ctx: CompilationContext,
    term: Any,
    lambda_defs: list[ast.stmt],
):
    """Recursively replace every ``Lambda`` node *anywhere* in *term* with a
    ``LoadName`` reference to a freshly-compiled closure ``FunctionDef`` (appended
    to *lambda_defs*).

    A lambda only becomes a callable closure when it is compiled in its defining
    lexical context (so its free Vars and predicate names resolve).  Lambdas that
    appear directly as call arguments were always hoisted; this also hoists
    lambdas nested inside compound terms (``bundle((X <- ...))``) and any other
    value position, so a closure can be stored in a term or threaded through a
    variable and still be invoked by ``call_goal`` — standard higher-order use.
    Without this, a non-hoisted lambda reaches runtime as a raw ``Lambda`` AST
    node that ``call_goal`` cannot invoke.
    """
    if isinstance(term, Lambda):
        func_name, func_def = _compile_goal_lambda(ctx, term)
        lambda_defs.append(func_def)
        return LoadName(name=func_name)
    if type(term) is _MetaArg:
        # A -meta_predicate position (clausal.logic.meta_predicate): hoist
        # INSIDE the marker.  This walk used to stop at it, so a lambda
        # passed as a meta-argument reached ``term_to_ast_expr`` as a raw
        # ``Lambda`` node, compiled in the CALLER's scope, and its parameter
        # names were unbound there (``NameError: name 'U' is not defined``).
        inner = _hoist_lambdas_in_term(ctx, term.value, lambda_defs)
        return term if inner is term.value else _MetaArg(inner, term.spec)
    if isinstance(term, Compound):
        new_args = tuple(
            _hoist_lambdas_in_term(ctx, a, lambda_defs) for a in term.args
        )
        if new_args == term.args:
            return term
        return Compound(term.functor, new_args, term._position)
    if isinstance(term, Call):
        new_args = [
            _hoist_lambdas_in_term(ctx, a, lambda_defs) for a in term.args
        ]
        new_kwargs = [
            kw(value=_hoist_lambdas_in_term(ctx, kw.value, lambda_defs))
            if hasattr(kw, "value") else kw
            for kw in term.kwargs
        ]
        if new_args == term.args and new_kwargs == term.kwargs:
            return term
        # Call is a node_class node: field-replacement __call__ preserves position.
        return term(args=new_args, kwargs=new_kwargs)
    if isinstance(term, list):
        new_elts = [_hoist_lambdas_in_term(ctx, e, lambda_defs) for e in term]
        # No-op case (the overwhelming majority — a -constants list can
        # never contain a Lambda, since Lambdas aren't ground and would
        # already have failed the -constants groundness gate) returns the
        # ORIGINAL object, mirroring the Compound/Call branches above.
        # This matters beyond identity: a -constants list is a frozen
        # subclass (_FrozenList — clausal.logic.constants._freeze), and an
        # unconditional ``[... for e in term]`` rebuild silently downgrades
        # it to a plain, mutable list before terms_to_ast.term_to_ast_expr
        # ever sees it — defeating that function's frozen-reconstruction
        # branch, which can only preserve a type it still receives.
        # Identity check (not ==): cheaper, and correct regardless of
        # whether elements define a meaningful __eq__ (e.g. an unbound Var
        # comparing equal only to itself, by identity, is exactly what
        # "unchanged" means here).
        if all(a is b for a, b in zip(new_elts, term)):
            return term
        return new_elts
    return term


def _hoist_lambda_args(
    ctx: CompilationContext,
    ordered_args: list,
) -> tuple[list, list[ast.stmt]]:
    """Scan call args for Lambda nodes — including lambdas nested inside compound
    terms — compile them and replace with name refs."""
    lambda_defs: list[ast.stmt] = []
    processed = [_hoist_lambdas_in_term(ctx, a, lambda_defs) for a in ordered_args]
    return processed, lambda_defs
