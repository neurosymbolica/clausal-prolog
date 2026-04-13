"""Trampoline / stack-safe goal-and-body compilation.

This is the ``compile_predicate_trampoline`` strategy.  Every
generated function participates in the ``clausal.logic.trampoline``
tuple protocol: sub-predicate calls use ``StepGenerator(dispatch,
this_generator, …)`` so the Python call stack does not grow.

The shallow counterpart lives in ``.goal_shallow``.  Neither strategy
calls into the other at compile time.
"""

from __future__ import annotations

import ast
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref, unify  # noqa: F401
from clausal.logic.trampoline import Step, DONE, StepGenerator  # noqa: F401
from clausal.terms import (
    Compound,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    And, Or, Not,
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq, StructuralEq, StructuralNeq,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    Call, LoadName, LoadAttr,
)
from clausal.pythonic_ast.nodes import (
    IfExpr, Lambda, StarUnpack, TupleLiteral,
    Keyword as KWNode,
)
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import PredicateMeta
from clausal.terms import PyThunk

from ._ast_helpers import (
    _name, _attr, _call, _fresh, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt, _in_iter_expr,
    _MARK_PREFIX, _TRAIL_PARAM_NAME, _K_PARAM_NAME,
    _TRAMP_PARENT_NAME, _THIS_GEN_NAME,
)
from ._vars import _var_python_name, _collect_vars, _collect_bound_vars
from .terms_to_ast import (
    term_to_ast_expr, arith_to_ast_expr,
    _is_star_list, _dotted_name_from_loadattr,
)
from .star_segments import _compile_star_is
from .globals_env import _disp_key, _preallocate_body_vars
from .goal_shallow import (
    _compile_body_impl, _make_body_compiler_impl,
    _compile_predicate_call_impl,
    _compile_deterministic_goal,
    _compile_shared_membership_goal,
    _compile_shared_meta_call,
    _dispatch_goal,
)
from .compile_ctx import CompilationContext
from . import _monolith as _m

from .tabled_naf import _is_tabled_naf, _compile_tabled_naf_simple
from .ite_reified import (
    _is_reifiable,
    _compile_reified_ite_trampoline,
    _compile_general_ite_trampoline,
)
from .control_constructs import (
    _compile_arith_cmp, _deref_cmp,
    _compile_once, _compile_call_nth, _compile_count_all,
    _compile_setup_call_cleanup, _compile_freeze, _compile_when,
    _compile_find_all_core,
    _compile_throw, _compile_catch_trampoline,
    _compile_goal_lambda, _flatten_conjunction, _hoist_lambda_args,
)

# Destructive-reuse helpers used by _make_body_compiler_trampoline — still
# in _monolith until their own phase extraction.
from ._monolith import (
    _flatten_and_goals, _find_destructive_reuse_goals, _apply_destructive_reuse,
)

# Argument-indexing helpers still in _monolith until phase 14 — resolved
# lazily at call time via _m.* since they are defined in _monolith AFTER
# this submodule is imported.
def _static_call_key(*a, **kw): return _m._static_call_key(*a, **kw)
def _bucket_key(*a, **kw): return _m._bucket_key(*a, **kw)
def _joint_bucket_key(*a, **kw): return _m._joint_bucket_key(*a, **kw)

# ── Trampoline tuple-protocol compilation ──────────────────────────────────────
#
# DONE sentinel: yielded as (parent, DONE) when a predicate generator has
# exhausted all clauses.  The calling generator receives DONE as the value of
# its ``_st = (yield (_gen, None))`` expression and exits its while loop.
#
# DONE is imported from clausal.logic.trampoline (which prefers the C extension).


# ── AST helpers for tuple yields ───────────────────────────────────────────────


def _step_expr(gen_expr: ast.expr, value_expr: ast.expr) -> ast.expr:
    """Generate AST for: (gen_expr, value_expr) tuple"""
    return ast.Tuple(elts=[gen_expr, value_expr], ctx=ast.Load())


def _yield_step_stmt(gen_expr: ast.expr, value_expr: ast.expr) -> ast.stmt:
    """Generate AST for statement: yield (gen_expr, value_expr)"""
    return ast.Expr(value=ast.Yield(value=_step_expr(gen_expr, value_expr)))


def _assign_yield_step(
    target: str, gen_expr: ast.expr, value_expr: ast.expr
) -> ast.stmt:
    """Generate AST for: target = (yield (gen_expr, value_expr))

    The yielded tuple tells the trampoline to (re)start gen_expr.  When
    gen_expr next yields (back_to_us, v), the trampoline sends v here
    and target is bound to v.
    """
    return _assign(target, ast.Yield(value=_step_expr(gen_expr, value_expr)))


def _inject_bucket_refs_trampoline(
    ctx: CompilationContext,
    clauses: list,
    base_globals: dict,
) -> None:
    """Phase 10d: pre-scan clause bodies for statically-known call-site args.

    For each Call in a clause body where the callee is a locked predicate with
    ``_index_plans`` and one (or two) arguments are statically known literals
    or compound constructors, injects the matching bucket function into
    ``base_globals`` and records the mapping in
    ``ctx.bucket_ref_map`` / ``ctx.joint_bucket_ref_map`` so that
    :func:`_dispatch_call_trampoline` can emit a direct bucket reference.

    Mutates ``ctx`` in place — the caller's ctx_template (captured by
    reference in the body_compiler closure) sees the new entries.
    """

    brmap = ctx.bucket_ref_map
    jbrmap = ctx.joint_bucket_ref_map

    for clause in clauses:
        for goal in clause.body:
            # Identify Call(LoadName | LoadAttr) nodes
            if not (isinstance(goal, Call) and isinstance(goal.func, (LoadName, LoadAttr))):
                continue
            if isinstance(goal.func, LoadName):
                fname = goal.func.name
            else:
                fname = _dotted_name_from_loadattr(goal.func)
                if fname is None:
                    continue

            n_kwargs = len(goal.kwargs) if goal.kwargs else 0
            arity = len(goal.args) + n_kwargs

            pred_obj = base_globals.get(fname)
            if not isinstance(pred_obj, PredicateMeta):
                continue
            if not getattr(pred_obj, "_locked", False):
                continue
            if not hasattr(pred_obj, "_index_plans"):
                continue

            # Convert term args to AST exprs (fresh var_context — we only care
            # about constants, not variable names)
            arg_exprs = [term_to_ast_expr(a, {}) for a in goal.args]

            # Single-position bucket specialisation
            for pos, idx_dict in pred_obj._index_plans.items():
                if pos >= len(arg_exprs):
                    continue
                key = _static_call_key(arg_exprs[pos])
                if key is None or key not in idx_dict:
                    continue
                gkey = _bucket_key(fname, pos, key)
                if gkey not in base_globals:
                    base_globals[gkey] = idx_dict[key]
                brmap[(fname, arity, pos, key)] = gkey

            # Joint bucket specialisation (Phase 9b)
            if hasattr(pred_obj, "_index_plans_joint"):
                for (pi, pj), jdict in pred_obj._index_plans_joint.items():
                    if pi >= len(arg_exprs) or pj >= len(arg_exprs):
                        continue
                    ki = _static_call_key(arg_exprs[pi])
                    kj = _static_call_key(arg_exprs[pj])
                    if ki is None or kj is None:
                        continue
                    jkey = (ki, kj)
                    if jkey not in jdict:
                        continue
                    gkey = _joint_bucket_key(fname, pi, pj, ki, kj)
                    if gkey not in base_globals:
                        base_globals[gkey] = jdict[jkey]
                    jbrmap[(fname, arity, pi, pj, ki, kj)] = gkey


def _dispatch_call_trampoline(
    ctx: CompilationContext,
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
) -> ast.expr:
    """Generate: StepGenerator(fname._get_dispatch(), this_generator, arg0, …, trail)

    ``fname`` is resolved from the compiled function's globals.
    ``this_generator`` is passed as ``parent`` so the child generator knows who to
    yield back to when it finds a solution.

    Phase 7: if the predicate is locked, emits ``_disp_fname_N`` (a pre-captured
    dispatch function in base_globals) instead of ``fname._get_dispatch()``.

    Phase 10: if a statically-known argument matches an indexed position of the
    callee, emits a direct bucket-function reference (bypassing the dispatch
    closure entirely).
    """
    # Phase 10: direct bucket ref for statically-known indexed argument
    brmap = ctx.bucket_ref_map
    jbrmap = ctx.joint_bucket_ref_map
    trail_name = ctx.trail_name
    self_name = ctx.self_name

    # Try joint first (more selective — two args constrain the bucket further)
    for pos_i in range(arity):
        for pos_j in range(arity):
            if pos_i == pos_j or pos_i >= len(arg_exprs) or pos_j >= len(arg_exprs):
                continue
            ki = _static_call_key(arg_exprs[pos_i])
            kj = _static_call_key(arg_exprs[pos_j])
            if ki is None or kj is None:
                continue
            gkey = jbrmap.get((fname, arity, pos_i, pos_j, ki, kj))
            if gkey is not None:
                return ast.Call(
                    func=_name("StepGenerator"),
                    args=[ast.Name(id=gkey, ctx=ast.Load()), _name(self_name)]
                        + arg_exprs + [_name(trail_name)],
                    keywords=[],
                )

    # Try single-position bucket
    for pos, arg_expr in enumerate(arg_exprs):
        key = _static_call_key(arg_expr)
        if key is None:
            continue
        gkey = brmap.get((fname, arity, pos, key))
        if gkey is not None:
            return ast.Call(
                func=_name("StepGenerator"),
                args=[ast.Name(id=gkey, ctx=ast.Load()), _name(self_name)]
                    + arg_exprs + [_name(trail_name)],
                keywords=[],
            )

    # Phase 7: use cached dispatch name for locked predicates
    dk = _disp_key(fname, arity)
    locked_keys = ctx.locked_dispatch_keys
    if dk in locked_keys:
        dispatch_expr: ast.expr = _name(dk)
    else:
        dispatch_expr = ast.Call(
            func=ast.Attribute(value=_name(fname), attr="_get_dispatch"),
            args=[],
            keywords=[],
        )
    return ast.Call(
        func=_name("StepGenerator"),
        args=[dispatch_expr, _name(self_name)] + arg_exprs + [_name(trail_name)],
        keywords=[],
    )


# ── compile_goal_trampoline ────────────────────────────────────────────────────


def compile_goal_trampoline(
    goal: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    self_name: str = _THIS_GEN_NAME,
    parent_name: str = _TRAMP_PARENT_NAME,
    *,
    ctx: CompilationContext | None = None,
) -> list[ast.stmt]:
    """Compile a goal using the trampoline tuple protocol.

    Identical to ``compile_goal`` for deterministic goals (Unify, ArithEq, comparisons,
    And, Or, Not, in_, NotIn).  Differs for predicate ``Call`` nodes: instead of

        for _ in dispatch(args, trail, k): k_stmts

    it generates the stack-safe coroutine pattern::

        _gen  = StepGenerator(dispatch, this_generator, args, trail)  # child
        _st   = (yield (_gen, None))           # start child; get solution or DONE
        while _st is not _DONE:
            <k_stmts>                          # continuation (ends with yield (parent,None))
            _st = (yield (_gen, None))         # ask child for next solution

    ``k_stmts`` for the innermost goal must be
    ``[yield (parent, None)]`` — use ``compile_body_trampoline`` to build
    these correctly from the inside out.

    Note: ``Not`` (NAF) compiles its inner goal with ``compile_goal`` (simple
    mode) so the inner check runs via a local for loop.  NAF inner goals must
    therefore be simple-compiled predicates or primitive goals.

    Public entry point: legacy tuple signature preserved for external
    callers.  All internal compilation threads ctx via
    ``_dispatch_goal_trampoline``.
    """
    if ctx is None:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name, parent_name=parent_name,
        )
    return _dispatch_goal_trampoline(ctx, goal, k_stmts)


def _dispatch_goal_trampoline(
    ctx: CompilationContext,
    goal: Any,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Internal ctx-native trampoline goal dispatcher.

    Trampoline-strategy counterpart to ``_dispatch_goal``.  See the
    public ``compile_goal_trampoline`` docstring for the tuple-protocol
    details.
    """
    db = ctx.db
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    self_name = ctx.self_name
    parent_name = ctx.parent_name

    goal = deref(goal)

    if goal is True:
        return list(k_stmts)
    if goal is False:
        return []

    # PyThunk as a goal — evaluate for side effects, then continue.
    if isinstance(goal, PyThunk):
        call_expr = term_to_ast_expr(goal, var_context, eval_arith=False)
        return [ast.Expr(value=call_expr)] + list(k_stmts)

    # Strategy-agnostic cases (deterministic goals + shared meta-predicate
    # calls that delegate to control_constructs) — shared with shallow.
    det = _compile_deterministic_goal(ctx, goal, k_stmts)
    if det is not None:
        return det
    membership = _compile_shared_membership_goal(ctx, goal, k_stmts)
    if membership is not None:
        return membership
    meta = _compile_shared_meta_call(ctx, goal, k_stmts)
    if meta is not None:
        return meta

    match goal:

        # ── Conjunction ──────────────────────────────────────────────────────
        case And(left=l, right=r):
            inner_k = _dispatch_goal_trampoline(ctx, r, k_stmts)
            return _dispatch_goal_trampoline(ctx, l, inner_k)

        # ── Tuple-as-conjunction ─────────────────────────────────────────────
        case TupleLiteral(elements=elems) if elems:
            k = k_stmts
            for goal in reversed(elems):
                k = _dispatch_goal_trampoline(ctx, goal, k)
            return k

        # ── Disjunction ──────────────────────────────────────────────────────
        case Or(left=l, right=r):
            mark = _fresh(_MARK_PREFIX)
            left_stmts = _dispatch_goal_trampoline(ctx, l, k_stmts)
            right_stmts = _dispatch_goal_trampoline(ctx, r, k_stmts)
            # After trail.undo(mark) the trail is already back at mark, so the
            # second _assign_mark would be a no-op — omit it.
            return [
                _assign_mark(mark, trail_name),
                *left_stmts,
                _undo_stmt(mark, trail_name),
                *right_stmts,
                _undo_stmt(mark, trail_name),
            ]

        # ── Negation-as-failure ──────────────────────────────────────────────
        # Inner goal is compiled in trampoline mode.  A mini-trampoline loop
        # checks if at least one solution exists.  If not, the continuation
        # (k_stmts) is executed.
        case Not(operand=inner):
            # WFS: if inner is a call to a tabled predicate, use _naf_tabled
            if _is_tabled_naf(inner, db):
                return _compile_tabled_naf_simple(ctx, inner, k_stmts)

            naf_gen_fn = _fresh("_naf_gen_fn")
            naf_flag = _fresh("_naf")
            naf_sg = _fresh("_naf_sg")
            naf_g = _fresh("_naf_g")
            naf_v = _fresh("_naf_v")
            # Compile inner goal in trampoline mode with a solution yield
            inner_k = [_yield_step_stmt(_name("_naf_parent"), ast.Constant(None))]
            inner_stmts = _dispatch_goal_trampoline(
                ctx.replace(self_name="_naf_self", parent_name="_naf_parent"),
                inner, inner_k,
            )
            # Build the inner function: def _naf_gen_fn(_naf_self, _naf_parent, trail): ...
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
                **_m._EXTRA_FUNCDEF,
            )
            naf_mark = _fresh(_MARK_PREFIX)
            # Mini-trampoline: create StepGenerator, loop until solution or DONE.
            # _naf_sg = StepGenerator(_naf_gen_fn, None, trail)
            # _naf_g, _naf_v = _naf_sg.send(None)
            # while True:
            #     if _naf_g is None:
            #         if _naf_v is _DONE: break
            #         _naf_flag = False; break
            #     _naf_g, _naf_v = _naf_g.send(_naf_v)
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
            # while True body:
            inner_if = ast.If(
                test=ast.Compare(
                    left=_name(naf_g),
                    ops=[ast.Is()],
                    comparators=[ast.Constant(None)],
                ),
                body=[
                    # if _naf_v is _DONE: break
                    ast.If(
                        test=ast.Compare(
                            left=_name(naf_v),
                            ops=[ast.Is()],
                            comparators=[_name("_DONE")],
                        ),
                        body=[ast.Break()],
                        orelse=[],
                    ),
                    # Found a solution: _naf_flag = False; break
                    _assign(naf_flag, ast.Constant(value=False)),
                    ast.Break(),
                ],
                orelse=[
                    # Step into child: _naf_g, _naf_v = _naf_g.send(_naf_v)
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

        # ── Reified if-then-else ───────────────────────────────────────────
        case IfExpr(test=test, body=then, orelse=else_):
            if _is_reifiable(test):
                return _compile_reified_ite_trampoline(ctx, test, then, else_, k_stmts)
            else:
                return _compile_general_ite_trampoline(ctx, test, then, else_, k_stmts)

        # ── catch(Goal, Catcher, Recovery) — exception handling ──────────
        case Call(func=LoadName(name="catch"), args=[goal_arg, catcher, recovery], kwargs=[]):
            return _compile_catch_trampoline(ctx, goal_arg, catcher, recovery, k_stmts)

        # ── catch_error(Goal, Error) — catch any exception, bind Error ──────────
        case Call(func=LoadName(name="catch_error"), args=[goal_arg, error_var], kwargs=[]):
            return _compile_catch_trampoline(
                ctx, goal_arg, error_var, True, k_stmts, always_catch=True,
            )

        # ── catch_recover(Goal, Error, Recovery) — catch, bind, recover ───
        case Call(func=LoadName(name="catch_recover"), args=[goal_arg, error_var, recovery], kwargs=[]):
            return _compile_catch_trampoline(
                ctx, goal_arg, error_var, recovery, k_stmts, always_catch=True,
            )

        # ── forall/2 — \+( Cond, \+ Action ) ───────────────────────────────
        case Call(func=LoadName(name="forall"), args=[cond, action], kwargs=[]):
            rewritten = Not(operand=And(left=cond, right=Not(operand=action)))
            return _dispatch_goal(ctx, rewritten, k_stmts)

        # ── Stack-safe predicate call ─────────────────────────────────────────
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            return _compile_predicate_call_trampoline(
                ctx, fname, call_args, call_kwargs, k_stmts,
            )

        # ── Qualified predicate call (mod.Pred(X_)) ──────────────────────────
        case Call(func=LoadAttr() as attr, args=call_args, kwargs=call_kwargs):
            fname = _dotted_name_from_loadattr(attr)
            return _compile_predicate_call_trampoline(
                ctx, fname, call_args, call_kwargs, k_stmts,
            )

        case Call():
            raise NotImplementedError(
                f"compile_goal_trampoline: cannot compile Call with non-LoadName func: {goal.func!r}"
            )

        case _:
            raise NotImplementedError(
                f"compile_goal_trampoline: unsupported goal type {type(goal).__name__}: {goal!r}"
            )


def _compile_predicate_call_trampoline(
    ctx: CompilationContext,
    fname: str,
    call_args: list,
    call_kwargs: list,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Trampoline variant of _compile_predicate_call.

    Generates the coroutine-backtracking pattern::

        _gen_N  = StepGenerator(dispatch, this_generator, arg0, …, trail)
        _st_N   = (yield (_gen_N, None))
        while _st_N is not _DONE:
            <k_stmts>
            _st_N = (yield (_gen_N, None))

    when ``_gen_N`` yields ``(this_generator, None)`` (solution found), the
    trampoline sends ``None`` to ``this_generator`` so ``_st_N`` gets ``None``
    (not DONE) and the while body runs.  when ``_gen_N`` yields
    ``(this_generator, DONE)`` (exhausted), ``_st_N`` gets ``DONE`` and the
    while loop exits.

    WK-4 keyword normalisation is applied identically to the simple variant.
    See ``_compile_predicate_call_impl`` in ``goal_shallow`` for the shared
    front-end (arg ordering + lambda hoist + arg_expr lowering).
    """
    def _emit(arity, arg_exprs, k_stmts):
        gen_name = _fresh("_gen")
        status_name = _fresh("_st")

        call_expr = _dispatch_call_trampoline(
            ctx, fname, arity, arg_exprs,
        )

        # _gen_N = dispatch(self, arg0, …, trail)
        gen_assign = _assign(gen_name, call_expr)

        # _st_N = (yield Step(_gen_N, None))
        first_step = _assign_yield_step(status_name, _name(gen_name), ast.Constant(None))

        # while _st_N is not _DONE: k_stmts; _st_N = (yield Step(_gen_N, None))
        loop_body = (k_stmts or [ast.Pass()]) + [
            _assign_yield_step(status_name, _name(gen_name), ast.Constant(None))
        ]
        loop = ast.While(
            test=ast.Compare(
                left=_name(status_name),
                ops=[ast.IsNot()],
                comparators=[_name("_DONE")],
            ),
            body=loop_body,
            orelse=[],
        )
        return [gen_assign, first_step, loop]

    return _compile_predicate_call_impl(
        ctx, fname, call_args, call_kwargs, k_stmts,
        emit_dispatch=_emit,
    )



# ── compile_body_trampoline ────────────────────────────────────────────────────


def compile_body_trampoline(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    parent_name: str = _TRAMP_PARENT_NAME,
    self_name: str = _THIS_GEN_NAME,
    *,
    ctx: CompilationContext | None = None,
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction (trampoline strategy).

    The leaf continuation is ``yield (parent, None)`` — one solution
    surfaced to the calling generator.  See ``_compile_body_impl`` for
    the shared right-to-left reduction.

    ``ctx``, when supplied, carries the per-predicate
    ``locked_dispatch_keys`` / ``bucket_ref_map`` / ``joint_bucket_ref_map``
    forward to ``compile_goal_trampoline`` and onto
    ``_dispatch_call_trampoline``.  When omitted (legacy callers such as
    ``solve.py``), ctx is constructed with thread-local fallback values.
    """
    if ctx is not None:
        # Caller supplied per-predicate ctx; use it but overlay the
        # per-clause trail/var_context/self_name/parent_name.
        ctx = ctx.replace(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name, parent_name=parent_name,
        )
    else:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name, parent_name=parent_name,
        )

    return _compile_body_impl(
        goals, ctx,
        leaf_yield=_yield_step_stmt(_name(parent_name), ast.Constant(None)),
        compile_goal_fn=lambda goal, ctx_, k: _dispatch_goal_trampoline(ctx_, goal, k),
    )


def _dr_preprocess(clause: Clause) -> list:
    """Destructive-reuse preprocess: flatten And conjunctions, then rewrite.

    Flattening is safe because ``And(a, b)`` compiles identically to the
    sequential goal list ``[a, b]``.  The rewrite replaces eligible
    ``append``/``dict_put``/``set_union`` calls with their ``_dr_*``
    in-place variants when the source container is provably dead.

    Trampoline-only: the ``_dr_*__N`` dispatch functions live in
    ``clausal.logic.builtins.{lists,dict_set}`` and only exist in
    trampoline form; wiring this into shallow would require shallow
    equivalents that don't currently exist.
    """
    flat_body = _flatten_and_goals(clause.body)
    eligible = _find_destructive_reuse_goals(clause)
    return _apply_destructive_reuse(flat_body, eligible)


def _make_body_compiler_trampoline(
    db: Database,
    *,
    ctx_template: CompilationContext | None = None,
) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a trampoline body_compiler callable bound to db.

    Applies destructive-reuse rewriting as a preprocess step; see
    ``_dr_preprocess`` for why this is trampoline-only.

    ``ctx_template`` (when supplied) is captured by reference and
    forwarded on every per-clause invocation, so later mutations to its
    ``locked_dispatch_keys`` / ``bucket_ref_map`` / ``joint_bucket_ref_map``
    fields are visible at compile time.
    """
    return _make_body_compiler_impl(
        db,
        body_compile_fn=compile_body_trampoline,
        preprocess_clause=_dr_preprocess,
        ctx_template=ctx_template,
    )
