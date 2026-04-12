"""Reified if-then-else compilation (shallow + trampoline variants).

A "reifiable" test (unify/disunify, arithmetic/FD comparison) compiles
to a three-way branch driven by ``_reify_eq`` / ``_reify_fd``:

- returned value ``True``  → run ``then``
- returned value ``False`` → run ``else_``
- returned value ``None``  → explore both with appropriate constraints

Non-reifiable tests fall through to ``_compile_general_ite`` which
uses a single-evaluation ``_found`` flag (plus ``_naf_tabled`` for
WFS-sound tabled negation).

Each variant has a shallow and a trampoline counterpart — intentionally
co-located so a future de-duplication refactor is a single-file diff.

Cycle handling: ``compile_goal`` / ``compile_goal_trampoline`` /
``_yield_step_stmt`` / ``_EXTRA_FUNCDEF`` still live in ``_monolith``
at this split stage.  We reference them through the ``_m`` alias so
the attribute lookup happens at call time, sidestepping the
module-load-order cycle.
"""

from __future__ import annotations

import ast

from clausal.terms import (
    Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE,
)

from ._ast_helpers import (
    _name, _call, _fresh, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt,
    _MARK_PREFIX,
)
from .terms_to_ast import term_to_ast_expr
from . import _monolith as _m


_REIFIABLE_TYPES = (Unify, DoesNotUnify, ArithEq, ArithNeq, Lt, LtE, Gt, GtE)


def _is_reifiable(test) -> bool:
    """Return True if *test* can be compiled as a reified three-way branch."""
    return isinstance(test, _REIFIABLE_TYPES)


# ── Mapping from CmpOp node types to their FD reify ops and negated fd_ names ──

_FD_REIFY_INFO: dict[type, tuple[str, str, str]] = {
    ArithEq:  ("eq", "_fd_eq", "_fd_ne"),
    ArithNeq: ("ne", "_fd_ne", "_fd_eq"),
    Lt:            ("lt", "_fd_lt", "_fd_ge"),
    LtE:           ("le", "_fd_le", "_fd_gt"),
    Gt:            ("gt", "_fd_gt", "_fd_le"),
    GtE:           ("ge", "_fd_ge", "_fd_lt"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Shallow variants
# ─────────────────────────────────────────────────────────────────────────────


def _compile_reified_ite(test, then, else_, db, var_context, trail_name, k_stmts):
    """Compile a reified if-then-else for a reifiable condition.

    Generates a three-way branch:
    - True (ground-satisfied): run then
    - False (ground-violated): run else
    - None (undetermined): explore both with appropriate constraints
    """
    match test:
        case Unify(left=l, right=r):
            return _compile_reified_ite_eq(
                l, r, then, else_, db, var_context, trail_name, k_stmts, swap=False
            )
        case DoesNotUnify(left=l, right=r):
            return _compile_reified_ite_eq(
                l, r, then, else_, db, var_context, trail_name, k_stmts, swap=True
            )
        case _:
            # CLP(FD) comparison
            return _compile_reified_ite_fd(
                test, then, else_, db, var_context, trail_name, k_stmts
            )


def _compile_reified_ite_eq(l, r, then, else_, db, var_context, trail_name, k_stmts, swap=False):
    """Compile reified ITE for equality/disequality conditions.

    when swap=False (Unify):   True→then, False→else
    when swap=True  (DoesNot): True→else, False→then  (inverted reify_eq)
    """
    reif_var = _fresh("_reif")
    l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
    r_expr = term_to_ast_expr(r, var_context, eval_arith=False)

    then_stmts = _m.compile_goal(then, db, var_context, trail_name, k_stmts)
    else_stmts = _m.compile_goal(else_, db, var_context, trail_name, k_stmts)

    if swap:
        true_stmts, false_stmts = else_stmts, then_stmts
    else:
        true_stmts, false_stmts = then_stmts, else_stmts

    # Undetermined branch: explore both (unify for "true", dif for "false")
    mark = _fresh(_MARK_PREFIX)
    # "unify" path → then (or else if swapped)
    unify_branch_stmts = _m.compile_goal(then, db, var_context, trail_name, k_stmts) if not swap else _m.compile_goal(else_, db, var_context, trail_name, k_stmts)
    # "dif" path → else (or then if swapped)
    dif_branch_stmts = _m.compile_goal(else_, db, var_context, trail_name, k_stmts) if not swap else _m.compile_goal(then, db, var_context, trail_name, k_stmts)

    undetermined = [
        _assign_mark(mark, trail_name),
        _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), unify_branch_stmts),
        _undo_stmt(mark, trail_name),
        _if(_call(_name("_dif"), l_expr, r_expr, _name(trail_name)), dif_branch_stmts),
    ]

    # _reif_N = _reify_eq(l, r, trail)
    reif_assign = _assign(reif_var,
        _call(_name("_reify_eq"), l_expr, r_expr, _name(trail_name)))

    # if _reif_N is True: <true_stmts>
    # elif _reif_N is False: <false_stmts>
    # else: <undetermined>
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


def _compile_reified_ite_fd(test, then, else_, db, var_context, trail_name, k_stmts):
    """Compile reified ITE for CLP(FD) comparison conditions."""
    test_type = type(test)
    op_name, fd_true_name, fd_false_name = _FD_REIFY_INFO[test_type]

    reif_var = _fresh("_reif")
    l_expr = term_to_ast_expr(test.left, var_context, eval_arith=False)
    r_expr = term_to_ast_expr(test.right, var_context, eval_arith=False)

    then_stmts = _m.compile_goal(then, db, var_context, trail_name, k_stmts)
    else_stmts = _m.compile_goal(else_, db, var_context, trail_name, k_stmts)

    # Undetermined: post FD constraint for then path, negated for else path
    mark = _fresh(_MARK_PREFIX)
    fd_then_stmts = _m.compile_goal(then, db, var_context, trail_name, k_stmts)
    fd_else_stmts = _m.compile_goal(else_, db, var_context, trail_name, k_stmts)

    undetermined = [
        _assign_mark(mark, trail_name),
        _if(_call(_name(fd_true_name), l_expr, r_expr, _name(trail_name)), fd_then_stmts),
        _undo_stmt(mark, trail_name),
        _assign_mark(mark, trail_name),
        _if(_call(_name(fd_false_name), l_expr, r_expr, _name(trail_name)), fd_else_stmts),
        _undo_stmt(mark, trail_name),
    ]

    # _reif_N = _reify_fd("op", l, r, trail)
    reif_assign = _assign(reif_var,
        _call(_name("_reify_fd"), ast.Constant(op_name), l_expr, r_expr, _name(trail_name)))

    branch = ast.If(
        test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(True)]),
        body=then_stmts or [ast.Pass()],
        orelse=[
            ast.If(
                test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(False)]),
                body=else_stmts or [ast.Pass()],
                orelse=undetermined,
            ),
        ],
    )

    return [reif_assign, branch]


def _compile_general_ite(test, then, else_, db, var_context, trail_name, k_stmts):
    """Compile ITE for non-reifiable conditions.

    Uses single-evaluation with a _found flag instead of double-evaluation NAF.
    For tabled predicates, falls back to _naf_tabled for the false path (WFS
    requires separate tabled negation).
    """
    use_tabled_naf = _m._is_tabled_naf(test, db)

    # Build the condition sub-generator
    cond_gen = _fresh("_ite_cond")
    cond_stmts = _m.compile_goal(test, db, var_context, trail_name, [_yield_none_stmt()])
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
        **_m._EXTRA_FUNCDEF,
    )

    then_stmts = _m.compile_goal(then, db, var_context, trail_name, k_stmts)
    else_stmts = _m.compile_goal(else_, db, var_context, trail_name, k_stmts)

    if use_tabled_naf:
        # Tabled predicates: must use _naf_tabled for WFS soundness.
        # Still evaluate condition once for the true path, but use
        # _naf_tabled separately for the false path.
        true_mark = _fresh(_MARK_PREFIX)
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
        naf_mark = _fresh(_MARK_PREFIX)
        false_block = [
            _assign_mark(naf_mark, trail_name),
            _if(naf_call, else_stmts),
            _undo_stmt(naf_mark, trail_name),
        ]
        return [cond_fn] + true_block + false_block
    else:
        # Non-tabled: single evaluation with _found flag.
        # Run condition once; for each solution run then. After exhaustion,
        # if no solutions were found, run else.
        found_flag = _fresh("_found")
        mark = _fresh(_MARK_PREFIX)
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


# ─────────────────────────────────────────────────────────────────────────────
# Trampoline variants
# ─────────────────────────────────────────────────────────────────────────────


def _compile_reified_ite_trampoline(test, then, else_, db, var_context, trail_name,
                                     k_stmts, self_name, parent_name):
    """Trampoline variant of _compile_reified_ite."""
    match test:
        case Unify(left=l, right=r):
            return _compile_reified_ite_eq_trampoline(
                l, r, then, else_, db, var_context, trail_name,
                k_stmts, self_name, parent_name, swap=False,
            )
        case DoesNotUnify(left=l, right=r):
            return _compile_reified_ite_eq_trampoline(
                l, r, then, else_, db, var_context, trail_name,
                k_stmts, self_name, parent_name, swap=True,
            )
        case _:
            return _compile_reified_ite_fd_trampoline(
                test, then, else_, db, var_context, trail_name,
                k_stmts, self_name, parent_name,
            )


def _compile_reified_ite_eq_trampoline(l, r, then, else_, db, var_context, trail_name,
                                        k_stmts, self_name, parent_name, swap=False):
    """Trampoline variant of _compile_reified_ite_eq."""
    reif_var = _fresh("_reif")
    l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
    r_expr = term_to_ast_expr(r, var_context, eval_arith=False)

    _cgt = _m.compile_goal_trampoline  # shorthand
    then_stmts = _cgt(then, db, var_context, trail_name, k_stmts, self_name, parent_name)
    else_stmts = _cgt(else_, db, var_context, trail_name, k_stmts, self_name, parent_name)

    if swap:
        true_stmts, false_stmts = else_stmts, then_stmts
        unify_branch, dif_branch = else_stmts, then_stmts
    else:
        true_stmts, false_stmts = then_stmts, else_stmts
        unify_branch, dif_branch = then_stmts, else_stmts

    mark = _fresh(_MARK_PREFIX)

    undetermined = [
        _assign_mark(mark, trail_name),
        _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), unify_branch),
        _undo_stmt(mark, trail_name),
        _if(_call(_name("_dif"), l_expr, r_expr, _name(trail_name)), dif_branch),
    ]

    reif_assign = _assign(reif_var,
        _call(_name("_reify_eq"), l_expr, r_expr, _name(trail_name)))

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


def _compile_reified_ite_fd_trampoline(test, then, else_, db, var_context, trail_name,
                                        k_stmts, self_name, parent_name):
    """Trampoline variant of _compile_reified_ite_fd."""
    test_type = type(test)
    op_name, fd_true_name, fd_false_name = _FD_REIFY_INFO[test_type]

    reif_var = _fresh("_reif")
    l_expr = term_to_ast_expr(test.left, var_context, eval_arith=False)
    r_expr = term_to_ast_expr(test.right, var_context, eval_arith=False)

    _cgt = _m.compile_goal_trampoline
    then_stmts = _cgt(then, db, var_context, trail_name, k_stmts, self_name, parent_name)
    else_stmts = _cgt(else_, db, var_context, trail_name, k_stmts, self_name, parent_name)

    mark = _fresh(_MARK_PREFIX)

    undetermined = [
        _assign_mark(mark, trail_name),
        _if(_call(_name(fd_true_name), l_expr, r_expr, _name(trail_name)), then_stmts),
        _undo_stmt(mark, trail_name),
        _assign_mark(mark, trail_name),
        _if(_call(_name(fd_false_name), l_expr, r_expr, _name(trail_name)), else_stmts),
        _undo_stmt(mark, trail_name),
    ]

    reif_assign = _assign(reif_var,
        _call(_name("_reify_fd"), ast.Constant(op_name), l_expr, r_expr, _name(trail_name)))

    branch = ast.If(
        test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(True)]),
        body=then_stmts or [ast.Pass()],
        orelse=[
            ast.If(
                test=ast.Compare(left=_name(reif_var), ops=[ast.Is()], comparators=[ast.Constant(False)]),
                body=else_stmts or [ast.Pass()],
                orelse=undetermined,
            ),
        ],
    )

    return [reif_assign, branch]


def _compile_general_ite_trampoline(test, then, else_, db, var_context, trail_name,
                                     k_stmts, self_name, parent_name):
    """Trampoline variant of _compile_general_ite.

    Condition compiles in trampoline mode and is driven by a mini-trampoline.
    Then/else branches compile in trampoline mode with normal k_stmts.

    Non-tabled: single evaluation with _found flag (no double-evaluation).
    Tabled: uses _naf_tabled for WFS-sound false path.
    """
    use_tabled_naf = _m._is_tabled_naf(test, db)

    # ── Build the condition function in trampoline mode ──
    cond_fn_name = _fresh("_ite_cond_fn")
    cond_self = "_ite_self"
    cond_parent = "_ite_parent"
    cond_k = [_m._yield_step_stmt(_name(cond_parent), ast.Constant(None))]
    cond_stmts = _m.compile_goal_trampoline(
        test, db, var_context, trail_name, cond_k,
        self_name=cond_self, parent_name=cond_parent,
    )
    cond_body = cond_stmts + [
        _m._yield_step_stmt(_name(cond_parent), _name("_DONE")),
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
        **_m._EXTRA_FUNCDEF,
    )

    _cgt = _m.compile_goal_trampoline
    then_stmts = _cgt(then, db, var_context, trail_name, k_stmts, self_name, parent_name)
    else_stmts = _cgt(else_, db, var_context, trail_name, k_stmts, self_name, parent_name)

    # ── "True" path: mini-trampoline that runs then for each solution ──
    sg_name = _fresh("_ite_sg")
    g_name = _fresh("_ite_g")
    v_name = _fresh("_ite_v")
    true_mark = _fresh(_MARK_PREFIX)
    found_flag = _fresh("_found")

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
    # Continue send after running then_stmts
    continue_send = ast.Assign(
        targets=[ast.Tuple(
            elts=[_name(g_name, ast.Store()), _name(v_name, ast.Store())],
            ctx=ast.Store(),
        )],
        value=_call(ast.Attribute(value=_name(sg_name), attr="send", ctx=ast.Load()),
                    ast.Constant(None)),
    )
    # Step into child generator (with _TABLING_SUSPEND handling)
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
    # if _ite_v is _TABLING_SUSPEND: send DONE; else: send value
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
            # Got a solution — set found flag and run then branch
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

    # ── "False" path ──
    if use_tabled_naf:
        # Tabled: must use _naf_tabled for WFS soundness
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
        naf_mark = _fresh(_MARK_PREFIX)
        false_block = [
            _assign_mark(naf_mark, trail_name),
            _if(naf_call, else_stmts),
            _undo_stmt(naf_mark, trail_name),
        ]
    else:
        # Non-tabled: use _found flag from true path (no re-evaluation)
        false_block = [
            _if(
                ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)),
                else_stmts,
            ),
        ]

    return [cond_fn_def] + true_block + false_block
