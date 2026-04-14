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
    _name, _attr, _call, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt, _in_iter_expr,
    _MARK_PREFIX, _TRAIL_PARAM_NAME, _K_PARAM_NAME,
    _TRAMP_PARENT_NAME, _THIS_GEN_NAME,
    _EXTRA_FUNCDEF,
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
from .arg_index import _static_call_key, _bucket_key, _joint_bucket_key

from .tabled_naf import _is_tabled_naf, _compile_tabled_naf_simple
from .ite_reified import (
    _is_reifiable,
    _compile_reified_ite,
    _compile_general_ite,
)
from .control_constructs import (
    _compile_arith_cmp, _deref_cmp,
    _compile_once, _compile_call_nth, _compile_count_all,
    _compile_setup_call_cleanup, _compile_freeze, _compile_when,
    _compile_find_all_core,
    _compile_throw, _compile_catch,
    _compile_goal_lambda, _flatten_conjunction, _hoist_lambda_args,
)

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

    # Snapshot existing keys so the cross-check sees only the entries
    # *this* call adds.  ``ctx`` lives across multiple
    # ``_inject_bucket_refs_trampoline`` invocations within a single
    # predicate compilation; without the snapshot we'd repeatedly
    # rediscover the same legacy entries and the strict-equality check
    # on flat-body subsets would still pass, but the missing-entries
    # check would compare against an ever-growing baseline.
    br_before = dict(brmap)
    jbr_before = dict(jbrmap)

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

    legacy_br_diff = {k: v for k, v in brmap.items() if k not in br_before}
    legacy_jbr_diff = {k: v for k, v in jbrmap.items() if k not in jbr_before}
    _maybe_cross_check_bucket_refs(
        legacy_br_diff, legacy_jbr_diff, clauses, base_globals,
    )


# ── IR-side parallel analysis (Slice D6c) ────────────────────────────────────
#
# ``analyse_ir_bucket_refs`` mirrors :func:`_inject_bucket_refs_trampoline`
# over IR :class:`Sequence` ops produced by ``terms_to_goalop``.
# Verification-only shadow today (D6 option-1): the entries it would
# inject are compared to the entries legacy actually injects
# (``_maybe_cross_check_bucket_refs`` below) and any divergence is
# stop-the-line.  D7 promotes the IR walk to primary and writes
# ``SubCall.direct_bucket_ref`` hints directly.
#
# IR walks ``ir.ops`` (the flat post-``terms_to_goalop`` :class:`Sequence`)
# rather than ``clause.body`` (the unflattened source).  ``terms_to_goalop``
# flattens ``And`` / list / ``TupleLiteral`` conjunctions, so the IR walker
# inspects every :class:`SubCall` reachable as a top-level conjunction
# member.  Legacy's ``for goal in clause.body`` only sees the
# unflattened items — calls nested inside ``And`` are silently skipped
# (a latent legacy limitation).  The cross-check tolerates the
# resulting "IR ⊇ legacy" relationship by demanding strict equality
# only on flat bodies.


def analyse_ir_bucket_refs(
    clauses: list,
    base_globals: dict,
) -> tuple[dict, dict]:
    """Return the bucket-ref entries the IR walker would inject.

    Result mirrors ``_inject_bucket_refs_trampoline`` mutations: a pair
    ``(brmap_entries, jbrmap_entries)`` of dicts keyed exactly the same
    way as ``ctx.bucket_ref_map`` / ``ctx.joint_bucket_ref_map``.

    ``base_globals`` is read-only here — the IR walker does not inject
    new globals, only computes which entries *would* be added.  The
    cross-check compares against legacy's actual mutations.

    Bodies that ``terms_to_goalop`` cannot convert (``NotImplementedError``)
    are silently skipped, matching the D4/D6a/D6b fallback contract.
    """
    from .terms_to_goalop import terms_to_goalop
    from . import ir as _ir

    brmap: dict = {}
    jbrmap: dict = {}

    for clause in clauses:
        try:
            body_ir = terms_to_goalop(clause.body, db=None)
        except NotImplementedError:
            continue
        if not isinstance(body_ir, _ir.Sequence):
            continue
        for op in body_ir.ops:
            if not isinstance(op, _ir.SubCall):
                continue
            fname = op.fname
            arity = op.arity

            pred_obj = base_globals.get(fname)
            if not isinstance(pred_obj, PredicateMeta):
                continue
            if not getattr(pred_obj, "_locked", False):
                continue
            if not hasattr(pred_obj, "_index_plans"):
                continue

            # ``SubCall.args`` carries the same positional terms legacy
            # reads off ``Call.args``; kwarg normalisation by
            # ``terms_to_goalop`` only reorders, never alters values.
            arg_exprs = [term_to_ast_expr(a, {}) for a in op.args]

            for pos, idx_dict in pred_obj._index_plans.items():
                if pos >= len(arg_exprs):
                    continue
                key = _static_call_key(arg_exprs[pos])
                if key is None or key not in idx_dict:
                    continue
                gkey = _bucket_key(fname, pos, key)
                brmap[(fname, arity, pos, key)] = gkey

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
                    jbrmap[(fname, arity, pi, pj, ki, kj)] = gkey
    return brmap, jbrmap


def _maybe_cross_check_bucket_refs(
    legacy_brmap_diff: dict,
    legacy_jbrmap_diff: dict,
    clauses: list,
    base_globals: dict,
) -> None:
    """Slice D6c parallel-implementation gate.

    Under ``CLAUSAL_IR_PATH=1``, run :func:`analyse_ir_bucket_refs`
    against the same clauses + ``base_globals`` and assert the entries
    it would inject equal what legacy actually injected.

    Bodies whose top-level shape contains ``And`` / nested-list
    conjunctions cause ``terms_to_goalop`` to flatten and surface
    additional :class:`SubCall` ops the legacy walker never sees — for
    those clauses the IR result is a strict superset of legacy's.  We
    assert ``ir ⊇ legacy`` always, plus ``ir == legacy`` when the
    clause shape is flat (no ``And`` / list / ``TupleLiteral`` conjunction
    at top level).
    """
    import os
    if os.environ.get("CLAUSAL_IR_PATH") != "1":
        return
    ir_br, ir_jbr = analyse_ir_bucket_refs(clauses, base_globals)

    # ``ir ⊇ legacy`` always — IR must catch every entry legacy did.
    missing_br = {k: v for k, v in legacy_brmap_diff.items() if ir_br.get(k) != v}
    missing_jbr = {k: v for k, v in legacy_jbrmap_diff.items() if ir_jbr.get(k) != v}
    if missing_br or missing_jbr:
        raise AssertionError(
            "Slice D6c bucket-ref IR-analysis missed legacy entries — "
            "stop the line.\n"
            f"  missing single: {missing_br}\n"
            f"  missing joint:  {missing_jbr}"
        )

    # Strict equality on flat bodies (no top-level conjunction node).
    # An ``And`` / list / ``TupleLiteral`` at top level is legitimately
    # observed only by IR after ``terms_to_goalop`` flattens — that's
    # an additive optimisation, not a divergence.
    if all(_is_flat_body(c.body) for c in clauses):
        if ir_br != legacy_brmap_diff or ir_jbr != legacy_jbrmap_diff:
            raise AssertionError(
                "Slice D6c bucket-ref IR-analysis disagreement on flat "
                "body — stop the line.\n"
                f"  legacy single: {legacy_brmap_diff}\n"
                f"  ir     single: {ir_br}\n"
                f"  legacy joint:  {legacy_jbrmap_diff}\n"
                f"  ir     joint:  {ir_jbr}"
            )


def _is_flat_body(body: list) -> bool:
    """True iff *body* contains no top-level conjunction node.

    ``And`` / Python list / ``TupleLiteral`` at the top level get
    flattened by ``terms_to_goalop``, surfacing nested calls the
    legacy walker doesn't see.  On flat bodies the two walkers
    observe identical call sequences and the cross-check can demand
    strict equality.
    """
    for goal in body:
        g = deref(goal)
        if isinstance(g, And):
            return False
        if isinstance(g, list):
            return False
        if isinstance(g, TupleLiteral):
            return False
    return True


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
    from .strategy import TrampolineStrategy
    if ctx is None:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name, parent_name=parent_name,
            strategy=TrampolineStrategy(),
        )
    elif ctx.strategy is None:
        ctx = ctx.replace(strategy=TrampolineStrategy())
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

    Strategy is forced to :class:`TrampolineStrategy` on entry — matches
    the mirror-image contract of ``_dispatch_goal`` (the dispatcher you
    call determines the strategy).
    """
    from .strategy import TrampolineStrategy
    if not isinstance(ctx.strategy, TrampolineStrategy):
        ctx = ctx.replace(strategy=TrampolineStrategy())
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
            mark = ctx.fresh(_MARK_PREFIX)
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

            naf_gen_fn = ctx.fresh("_naf_gen_fn")
            naf_flag = ctx.fresh("_naf")
            naf_sg = ctx.fresh("_naf_sg")
            naf_g = ctx.fresh("_naf_g")
            naf_v = ctx.fresh("_naf_v")
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
                **_EXTRA_FUNCDEF,
            )
            naf_mark = ctx.fresh(_MARK_PREFIX)
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
                return _compile_reified_ite(ctx, test, then, else_, k_stmts)
            else:
                return _compile_general_ite(ctx, test, then, else_, k_stmts)

        # ── catch(Goal, Catcher, Recovery) — exception handling ──────────
        case Call(func=LoadName(name="catch"), args=[goal_arg, catcher, recovery], kwargs=[]):
            return _compile_catch(ctx, goal_arg, catcher, recovery, k_stmts)

        # ── catch_error(Goal, Error) — catch any exception, bind Error ──────────
        case Call(func=LoadName(name="catch_error"), args=[goal_arg, error_var], kwargs=[]):
            return _compile_catch(
                ctx, goal_arg, error_var, True, k_stmts, always_catch=True,
            )

        # ── catch_recover(Goal, Error, Recovery) — catch, bind, recover ───
        case Call(func=LoadName(name="catch_recover"), args=[goal_arg, error_var, recovery], kwargs=[]):
            return _compile_catch(
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

    The strategy-specific StepGenerator + while-loop emission is handled
    by ``TrampolineStrategy.emit_sub_call``; see
    ``_compile_predicate_call_impl`` in ``goal_shallow`` for the shared
    front-end (arg ordering + lambda hoist + arg_expr lowering).
    """
    return _compile_predicate_call_impl(
        ctx, fname, call_args, call_kwargs, k_stmts,
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
    from .strategy import TrampolineStrategy
    if ctx is not None:
        # Caller supplied per-predicate ctx; use it but overlay the
        # per-clause trail/var_context/self_name/parent_name.
        ctx = ctx.replace(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name, parent_name=parent_name,
        )
        if ctx.strategy is None:
            ctx = ctx.replace(strategy=TrampolineStrategy())
    else:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name, parent_name=parent_name,
            strategy=TrampolineStrategy(),
        )

    return _compile_body_impl(goals, ctx)


def _make_body_compiler_trampoline(
    db: Database,
    *,
    ctx_template: CompilationContext | None = None,
) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a trampoline body_compiler callable bound to db.

    Destructive-reuse rewriting is applied by
    ``TrampolineStrategy.preprocess_clause``; see ``compiler/strategy.py``.
    DR is trampoline-only because the ``_dr_*__N`` dispatch functions live
    in ``clausal.logic.builtins.{lists,dict_set}`` and only exist in
    trampoline form.

    ``ctx_template`` (when supplied) is captured by reference and
    forwarded on every per-clause invocation, so later mutations to its
    ``locked_dispatch_keys`` / ``bucket_ref_map`` / ``joint_bucket_ref_map``
    fields are visible at compile time.  When omitted (``_ast`` variants,
    tests), a minimal ctx_template carrying ``TrampolineStrategy`` is
    constructed.
    """
    from .strategy import TrampolineStrategy
    if ctx_template is None:
        ctx_template = CompilationContext(
            db=db, var_context={}, trail_name=_TRAIL_PARAM_NAME,
            strategy=TrampolineStrategy(),
        )
    elif ctx_template.strategy is None:
        ctx_template = ctx_template.replace(strategy=TrampolineStrategy())
    return _make_body_compiler_impl(db, ctx_template=ctx_template)
