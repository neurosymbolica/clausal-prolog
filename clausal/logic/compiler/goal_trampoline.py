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
    _PROCEED_PARAM_NAME, _FAIL_PARAM_NAME, _CATCHER_PARAM_NAME,
    _THIS_GEN_NAME,
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
)
from .compile_ctx import CompilationContext
from .arg_index import _static_call_key, _bucket_key, _joint_bucket_key

from .tabled_naf import _is_tabled_naf, _compile_tabled_naf_simple
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
        legacy_br_diff, legacy_jbr_diff, clauses, base_globals, ctx.db,
    )


# Process-wide audit log for D6c: each entry is a ``(extra_br,
# extra_jbr)`` pair recording bucket-ref entries the IR walker found
# that the legacy walker missed (always due to ``terms_to_goalop``
# flattening a top-level ``And`` / nested-list conjunction).  Empty in
# normal operation; consulted by the D6 post-audit and by
# ``tests/test_bucket_refs_ir_extras_audit.py``.
_IR_EXTRA_BUCKET_REFS: list[tuple[dict, dict]] = []


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
    db: Any = None,
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
            body_ir = terms_to_goalop(clause.body, db=db)
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
    db: Any = None,
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
    ir_br, ir_jbr = analyse_ir_bucket_refs(clauses, base_globals, db=db)

    # Audit instrumentation: when the IR walker discovers entries the
    # legacy walker missed (legitimate when a top-level ``And`` /
    # nested-list conjunction surfaces a hidden Call), record them on
    # a process-wide counter so the post-D6 audit can verify that the
    # "IR ⊇ legacy" leniency isn't masking something unexpected.
    extra_br = {k: v for k, v in ir_br.items() if k not in legacy_brmap_diff}
    extra_jbr = {k: v for k, v in ir_jbr.items()
                 if k not in legacy_jbrmap_diff}
    if extra_br or extra_jbr:
        _IR_EXTRA_BUCKET_REFS.append((extra_br, extra_jbr))

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
    *,
    direct_bucket_ref: str | None = None,
    direct_joint_bucket_ref: str | None = None,
    tail_position: bool = False,
) -> ast.expr:
    """Generate: ``StepGenerator(fname._get_dispatch(), <proceed>, <fail>,
    <catcher>, arg0, …, trail)``.

    ``fname`` is resolved from the compiled function's globals.  Non-TCO
    calls pass ``this_generator`` for all three continuation slots — the
    child routes solutions, exhaustion, and exceptions all back through
    this frame.  When ``tail_position`` is set, the child's ``proceed``
    slot becomes the caller's own ``_proceed`` so solutions bypass this
    frame one hop sooner; ``fail`` and ``catcher`` stay pointed at
    ``this_generator`` so our frame still wakes on child exhaustion
    (next clause / enclosing loop / trail undo) and on thrown
    exceptions (``try/except`` wrapping the child).

    Phase 7: if the predicate is locked, emits ``_disp_fname_N`` (a
    pre-captured dispatch function in base_globals) instead of
    ``fname._get_dispatch()``.

    Phase 10: if a statically-known argument matches an indexed
    position of the callee, emits a direct bucket-function reference
    (bypassing the dispatch closure entirely).
    """
    brmap = ctx.bucket_ref_map
    jbrmap = ctx.joint_bucket_ref_map
    trail_name = ctx.trail_name
    self_name = ctx.self_name

    proceed_expr = _name(ctx.proceed_name) if tail_position else _name(self_name)
    fail_expr = _name(self_name)
    catcher_expr = _name(self_name)

    def _sg(dispatch_expr: ast.expr) -> ast.Call:
        return ast.Call(
            func=_name("StepGenerator"),
            args=[dispatch_expr, proceed_expr, fail_expr, catcher_expr]
                + arg_exprs + [_name(trail_name)],
            keywords=[],
        )

    # Slice E6a: prefer the IR-path joint hint over the legacy
    # ``ctx.joint_bucket_ref_map`` lookup.  Joint entries win over
    # single-position entries — both hint and map — matching legacy's
    # joint-first preference.
    if direct_joint_bucket_ref is not None:
        return _sg(ast.Name(id=direct_joint_bucket_ref, ctx=ast.Load()))

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
                return _sg(ast.Name(id=gkey, ctx=ast.Load()))

    # Prefer the IR-path hint (``SubCall.direct_bucket_ref``) over the
    # ``ctx.bucket_ref_map`` lookup for the single-position case.
    if direct_bucket_ref is not None:
        return _sg(ast.Name(id=direct_bucket_ref, ctx=ast.Load()))

    # Try single-position bucket
    for pos, arg_expr in enumerate(arg_exprs):
        key = _static_call_key(arg_expr)
        if key is None:
            continue
        gkey = brmap.get((fname, arity, pos, key))
        if gkey is not None:
            return _sg(ast.Name(id=gkey, ctx=ast.Load()))

    # Phase 7: use cached dispatch name for locked predicates
    dk = _disp_key(fname, arity)
    locked_keys = ctx.locked_dispatch_keys
    if dk in locked_keys:
        dispatch_expr: ast.expr = _name(dk)
    else:
        # The arity is the call site's, not the callee's — see
        # PredicateMeta._get_dispatch and
        # todo/arity-mismatch-reports-a-missing-trail-argument.md.
        dispatch_expr = ast.Call(
            func=ast.Attribute(value=_name(fname), attr="_get_dispatch"),
            args=[ast.Constant(value=arity)],
            keywords=[],
        )
    return _sg(dispatch_expr)


# ── compile_goal_trampoline ────────────────────────────────────────────────────


def compile_goal_trampoline(
    goal: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    self_name: str = _THIS_GEN_NAME,
    proceed_name: str = _PROCEED_PARAM_NAME,
    fail_name: str = _FAIL_PARAM_NAME,
    catcher_name: str = _CATCHER_PARAM_NAME,
    *,
    ctx: CompilationContext | None = None,
) -> list[ast.stmt]:
    """Public entry point — compile a single trampoline-strategy goal.

    Slice D7c-β3 replaced the term-walking
    ``_dispatch_goal_trampoline`` with a straight pass through the IR
    pipeline: wrap the goal in a singleton :func:`terms_to_goalop`
    call to produce a :class:`Sequence`, then lower via
    :mod:`.lower_python_trampoline`.  Byte-identical to the pre-β3
    dispatcher at every shape the compiler accepts.
    """
    from .strategy import TrampolineStrategy
    from .terms_to_goalop import terms_to_goalop
    from . import lower_python_trampoline
    if ctx is None:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name,
            proceed_name=proceed_name, fail_name=fail_name, catcher_name=catcher_name,
            strategy=TrampolineStrategy(),
        )
    elif ctx.strategy is None:
        ctx = ctx.replace(strategy=TrampolineStrategy())
    ir = terms_to_goalop([goal], ctx.db)
    return lower_python_trampoline.lower(ir, ctx, k_stmts)




# ── compile_body_trampoline ────────────────────────────────────────────────────


def compile_body_trampoline(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    self_name: str = _THIS_GEN_NAME,
    proceed_name: str = _PROCEED_PARAM_NAME,
    fail_name: str = _FAIL_PARAM_NAME,
    catcher_name: str = _CATCHER_PARAM_NAME,
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
        # per-clause trail/var_context/self_name/continuation names.
        ctx = ctx.replace(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name,
            proceed_name=proceed_name, fail_name=fail_name,
            catcher_name=catcher_name,
        )
        if ctx.strategy is None:
            ctx = ctx.replace(strategy=TrampolineStrategy())
    else:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name,
            proceed_name=proceed_name, fail_name=fail_name,
            catcher_name=catcher_name,
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
