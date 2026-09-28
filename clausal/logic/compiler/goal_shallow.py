"""Shallow / short-stack goal-and-body compilation.

This is the ``compile_predicate_shallow`` strategy (Python ``for``
loops over sub-predicate generators; stack grows with recursion
depth; safe for bounded-depth predicates).  The trampoline counterpart
lives in ``.goal_trampoline``.

The two compilers are independent — neither strategy calls into the
other.  Cross-module helpers (control constructs, ITE, tabled NAF,
star-segments) are imported directly from their canonical owner
submodules.
"""

from __future__ import annotations

import ast
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref, unify  # noqa: F401
from clausal.logic.trampoline import StepGenerator  # noqa: F401
from clausal.terms import (
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
)
from clausal.logic.database import Clause, Database
from clausal.terms import PyThunk
from clausal.pythonic_ast.nodes import Keyword as KWNode

from ._ast_helpers import (
    _name, _attr, _call, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt, _in_iter_expr,
    _MARK_PREFIX, _TRAIL_PARAM_NAME, _K_PARAM_NAME,
    _THIS_GEN_NAME,
    _EXTRA_FUNCDEF,
)
from ._vars import _var_python_name, _collect_vars, _collect_bound_vars
from .terms_to_ast import (
    term_to_ast_expr, arith_to_ast_expr, call_arg_context, construction_context,
    _is_star_list, _dotted_name_from_loadattr,
)
from .compile_ctx import CompilationContext
from .star_segments import _compile_star_is
from .globals_env import _disp_key, _preallocate_body_vars

# Cross-module helpers — pulled explicitly from real owners.
from .tabled_naf import _is_tabled_naf, _compile_tabled_naf_simple
from .control_constructs import (
    _compile_arith_cmp, _deref_cmp,
    _compile_once, _compile_call_nth, _compile_count_all,
    _compile_setup_call_cleanup, _compile_freeze, _compile_when,
    _compile_find_all_core,
    _compile_throw, _compile_catch,
    _compile_goal_lambda, _flatten_conjunction, _hoist_lambda_args,
)

def _dispatch_call_iter(
    ctx: CompilationContext,
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
) -> ast.expr:
    """Generate: _tramp_call($dispatch_at(fname, N), (arg0, …, argN), trail)

    Bridges simple-mode callers to trampoline-mode dispatch functions.
    ``fname`` is resolved from the compiled function's globals, where it
    refers to a predicate handle or a _DbDispatchAdapter shim.

    Phase 7: if the predicate is locked (its dispatch fn pre-cached in
    ``base_globals`` under ``_disp_Foo_N``), emits that direct name
    reference instead of the slower ``$dispatch_at(fname, N)`` call.
    Locked keys live on ``ctx.locked_dispatch_keys``.
    """
    dk = _disp_key(fname, arity)
    if dk in ctx.locked_dispatch_keys:
        dispatch_expr: ast.expr = _name(dk)
    else:
        # The arity is the call site's, not the callee's: passing it is what
        # lets the callee refuse a call no clause could match, instead of
        # handing back a dispatch function that runs out of arguments and
        # blames `trail`.  It goes through $dispatch_at rather than straight
        # into ``fname._get_dispatch(N)`` because ``fname`` may be a foreign
        # single-argument implementor — see _dispatch_at in logic/predicate.py.
        dispatch_expr = ast.Call(
            func=_name("$dispatch_at"),
            args=[_name(fname), ast.Constant(value=arity)],
            keywords=[],
        )
    args_tuple = ast.Tuple(elts=arg_exprs, ctx=ast.Load())
    return ast.Call(
        func=_name("$tramp_call"),
        args=[dispatch_expr, args_tuple, _name(ctx.trail_name)],
        keywords=[],
    )




# moved to .star_segments
from .star_segments import (  # noqa: E402,F401
    _compile_star_is, _compile_single_star_is, _compile_multi_star_is,
)


# ── WFS: tabled NAF helpers (moved to .tabled_naf) ───────────────────────────
from .tabled_naf import (  # noqa: E402,F401
    _is_tabled_naf, _compile_tabled_naf_simple,
)


# ── Control constructs (moved to .control_constructs) ───────────────────────
from .control_constructs import (  # noqa: E402,F401
    _compile_arith_cmp, _deref_cmp,
    _compile_once, _compile_call_nth, _compile_count_all,
    _compile_setup_call_cleanup, _compile_freeze, _compile_when,
    _compile_find_all_core,
    _catcher_to_structural, _compile_throw,
    _compile_catch,
    _compile_goal_lambda, _flatten_conjunction, _hoist_lambda_args,
)

# ── compile_goal ───────────────────────────────────────────────────────────────


def compile_goal(
    goal: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    *,
    ctx: CompilationContext | None = None,
) -> list[ast.stmt]:
    """Public entry point — compile a single shallow-strategy goal.

    The legacy tuple signature is preserved for external callers
    (``solve.py``, tests).  Slice D7c-β3 replaced the term-walking
    ``_dispatch_goal`` with a straight pass through the IR pipeline:
    wrap the goal in a singleton :func:`terms_to_goalop` call to
    produce a :class:`Sequence`, then lower through
    :mod:`.lower_python_shallow`.  Byte-identical to the pre-β3
    dispatcher at every shape the compiler accepts (``_compile_body_impl``
    has driven the same pipeline as source of truth since D7b).
    """
    from .strategy import ShallowStrategy
    from .terms_to_goalop import terms_to_goalop
    from . import lower_python_shallow
    if ctx is None:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            strategy=ShallowStrategy(),
        )
    elif ctx.strategy is None:
        ctx = ctx.replace(strategy=ShallowStrategy())
    ir = terms_to_goalop([goal], ctx.db)
    return lower_python_shallow.lower(ir, ctx, k_stmts)


def _compile_predicate_call_impl(
    ctx: CompilationContext,
    fname: str,
    call_args: list,
    call_kwargs: list,
    k_stmts: list[ast.stmt],
    *,
    direct_bucket_ref: str | None = None,
    direct_joint_bucket_ref: str | None = None,
    tail_position: bool = False,
) -> list[ast.stmt]:
    """Shared predicate-call compilation: arg normalisation + lambda hoist.

    Both shallow and trampoline predicate-call sites share identical
    front-ends:

    1. WK-4 keyword normalisation — reorder kwargs into positional order
       using the predicate's signature.  Raises RuntimeError if kwargs
       are present but no signature is registered, or if a required
       kwarg is missing.
    2. Hoist Lambda arguments to FunctionDef statements.
    3. Compile each ordered arg to an AST expression.

    The strategy-specific tail — shallow's ``for`` loop over a generator
    vs trampoline's ``_gen_N`` + ``_st_N`` while loop — is produced by
    ``ctx.strategy.emit_sub_call(ctx, fname, arity, arg_exprs, k_stmts)``.
    The returned statements are prepended with the hoisted lambda defs.
    """
    db = ctx.db
    var_context = ctx.var_context
    n_pos = len(call_args)
    arity = n_pos + len(call_kwargs)

    ordered_args: list = list(call_args)
    if call_kwargs:
        sig = db.signature_for(fname, arity)
        if sig is None:
            raise RuntimeError(
                f"No signature registered for {fname}/{arity}; "
                "cannot compile keyword call without a signature"
            )
        kw_dict = {kw.name: kw.value for kw in call_kwargs if isinstance(kw, KWNode)}
        for param_name in sig[n_pos:]:
            if param_name not in kw_dict:
                raise RuntimeError(
                    f"Missing argument {param_name!r} in keyword call to {fname}/{arity}"
                )
            ordered_args.append(kw_dict[param_name])

    # Hoist any Lambda arguments to FunctionDef statements
    ordered_args, lambda_defs = _hoist_lambda_args(ctx, ordered_args)

    arg_exprs = []
    for index, a in enumerate(ordered_args):
        # An evaluable argument of an ISO arithmetic builtin, or the clause
        # of an assert, fixes the ISO term an UNDECLARED functor built there
        # raises (``terms_to_ast.construction_context``).
        where = call_arg_context(fname, index)
        with construction_context(*(where or (None,))):
            arg_exprs.append(term_to_ast_expr(a, var_context, eval_arith=False))
    return lambda_defs + ctx.strategy.emit_sub_call(
        ctx, fname, arity, arg_exprs, k_stmts,
        direct_bucket_ref=direct_bucket_ref,
        direct_joint_bucket_ref=direct_joint_bucket_ref,
        tail_position=tail_position,
    )


# ── compile_body ───────────────────────────────────────────────────────────────


def _head_has_deferred_pattern(head) -> bool:
    """True when the clause head contains a list pattern that will
    compile to deferred output-mode unification.

    Head args that are list patterns — bare lists (star-free or
    ``[H, *T]``-style) and :class:`~clausal.terms.SegList`\\s — compile
    to the two-phase list-guard machinery: ``_head_list_unify_input``
    returns ``None`` for an unbound caller arg (output mode) and
    :func:`clausal.logic.compiler.head_match._wrap_yields_with_output_guards`
    wraps every leaf yield with a per-solution
    ``_head_list_unify_output(...)`` check.  That check is essential —
    it's what binds the caller's output-position vars — and it must run
    on our side of each solution.  Continuation-TCO routes solutions
    past us, so it's unsafe in these clauses.  See
    ``implementation_plans/CONTINUATION_TCO_PLAN.md``.

    Star-free ground lists defer exactly like star-lists (the caller arg
    may still be an unbound Var at match time), so ANY list head field
    counts.  Missing that case let TCO skip the deferred output guard:
    the query succeeded through the callee's ``_proceed`` but handed the
    caller back an unbound Var.  See
    ``todo/head-list-of-local-atoms-never-binds.md``.
    """
    if head is None:
        return False
    from clausal.terms import SegList
    from clausal.pythonic_ast.nodes import StarUnpack
    try:
        from clausal.logic.predicate import term_field_names, is_term_instance
    except ImportError:  # pragma: no cover — defensive
        return False
    # Walk the head's fields.  Any list (or SegList / StarUnpack) is a
    # list pattern that gets deferred output-mode unification.
    def _walk(val) -> bool:
        if isinstance(val, SegList) or isinstance(val, StarUnpack):
            return True
        if isinstance(val, list):
            return True
        if isinstance(val, tuple):
            return any(_walk(x) for x in val)
        if is_term_instance(val):
            names = term_field_names(val)
            return any(_walk(getattr(val, n)) for n in names if hasattr(val, n))
        return False
    return _walk(head)


def _compile_body_impl(
    goals: list,
    ctx: CompilationContext,
    *,
    head: Any = None,
    body_ir: Any = None,
) -> list[ast.stmt]:
    """Shared conjunction compilation — IR-only (Slice D7c-α).

    Builds a :class:`GoalOp` IR from *goals* via :func:`terms_to_goalop`,
    applies the active optimisation passes (TRO / destructive-reuse /
    call-site bucket-ref), and lowers via the strategy-specific lowering
    (:mod:`.lower_python_shallow` or :mod:`.lower_python_trampoline`).

    The pre-D7c legacy right-to-left fold (``strategy.compile_goal`` over
    raw terms) and its byte-parity verification harness retired in D7c-α;
    the IR path baked green under the D4/D7b harness through every E
    sub-slice, so it is now the only path.

    Body-only Vars (variables that appear in the body but not the head)
    are pre-allocated via :func:`_preallocate_body_vars` so the SubCall
    arm in lowering can reference them as named locals without relying
    on walrus introduction ordering.
    """
    from .invariants import assert_body_vars_preallocated
    from .strategy import ShallowStrategy, TrampolineStrategy
    from .terms_to_goalop import terms_to_goalop
    from . import lower_python_shallow, lower_python_trampoline

    strategy = ctx.strategy
    alloc_stmts = _preallocate_body_vars(goals, ctx.var_context)
    tro_active = (
        ctx.tro_plan is not None and bool(ctx.tro_plan.eligible)
    )
    if not tro_active:
        # Populate ``ctx.bucket_ref_map`` / ``joint_bucket_ref_map`` and
        # inject bucket functions into ``base_globals`` from the IR
        # call-site plan.  Meta-call helpers in :mod:`.control_constructs`
        # still run :func:`_dispatch_call_trampoline` on raw terms, and
        # it reads those maps for direct bucket refs — so we keep
        # populating them here for their benefit.  The main-body IR
        # lowering consumes the hints directly via the SubCall arm.
        _prepopulate_call_site_runtime(goals, ctx)
    assert_body_vars_preallocated(ctx, goals)

    # Slice E6d-β: predicate-trampoline sweep pre-builds the IR when
    # running the TRO eligibility check; reuse it here instead of
    # rebuilding.  ``body_ir`` is ``None`` for callers that bypass the
    # sweep (shallow path, meta-call recursion, test harnesses).
    # Slice D7c-β1 closed the last ``_convert`` gap (``And`` nested in
    # ``Or``/``Not``/``IfExpr``, plus meta-name arity-mismatch
    # deferral) so the IR-gap fallback to ``strategy.compile_goal`` is
    # gone — every body shape the compiler accepts is in the IR
    # subset.  ``terms_to_goalop`` now signals a genuine compiler bug
    # if it raises :class:`NotImplementedError`.
    ir = body_ir if body_ir is not None else terms_to_goalop(goals, ctx.db)

    if tro_active:
        from .optimisations import tro as _tro_pass
        ir = _tro_pass.apply(ir, ctx.tro_plan)
    else:
        if (
            isinstance(ctx.strategy, TrampolineStrategy)
            and ctx.strategy.supports_destructive_reuse
            and head is not None
            and "destructive_reuse" in ctx.enabled_optimisations
        ):
            from .optimisations import destructive_reuse as _dr
            _dr_plan = _dr.analyse(ir, head, db=ctx.db)
            ir = _dr.apply(ir, _dr_plan)
        if (
            ctx.base_globals is not None
            and isinstance(ctx.strategy, TrampolineStrategy)
            and "call_site" in ctx.enabled_optimisations
        ):
            from .optimisations import call_site as _call_site
            _plan = _call_site.analyse(ir, None, ctx.base_globals, db=ctx.db)
            ir = _call_site.apply(ir, _plan)
        if (
            isinstance(ctx.strategy, TrampolineStrategy)
            and "continuation_tco" in ctx.enabled_optimisations
            and not _head_has_deferred_pattern(head)
        ):
            # Continuation-TCO: only safe when nothing wraps the body's
            # leaf yield with per-solution work.  Head patterns with
            # star-lists (``[H, *T]``) emit a deferred output-mode
            # unification guard (``_head_list_unify_output``) around
            # every leaf yield in the clause — running that check is
            # essential for binding the caller's output vars, and it
            # must run on our side of each solution.  TCO would route
            # solutions past us before the guard fires.  Skip TCO for
            # such clauses.  See
            # ``implementation_plans/CONTINUATION_TCO_PLAN.md``.
            from .optimisations import continuation_tco as _ctco
            ir = _ctco.apply(ir, _ctco.analyse(ir))

    lower_fn = (
        lower_python_shallow.lower
        if isinstance(ctx.strategy, ShallowStrategy)
        else lower_python_trampoline.lower
    )
    leaf: list[ast.stmt] = [] if tro_active else [strategy.emit_leaf_yield(ctx)]
    body_k = lower_fn(ir, ctx, leaf)
    return alloc_stmts + body_k


def _prepopulate_call_site_runtime(
    ir_source: list, ctx: CompilationContext,
) -> None:
    """E6b: drive ``ctx.bucket_ref_map`` / ``joint_bucket_ref_map``
    population from the IR plan instead of the legacy per-predicate
    ``_inject_bucket_refs_trampoline`` pre-scan.

    Runs before the legacy fold so that ``_dispatch_call_trampoline``
    sees entries and emits direct bucket refs byte-identically to the
    pre-E6b shape.  No-op under a strategy without bucket-ref
    specialisation, when ``base_globals`` is unset, when the
    ``call_site`` optimisation flag is disabled.  Slice D7c-β1 closed
    the IR subset gap, so ``terms_to_goalop`` is no longer expected to
    raise :class:`NotImplementedError` on bodies the compiler accepts.
    """
    from .strategy import TrampolineStrategy
    if ctx.base_globals is None:
        return
    if not isinstance(ctx.strategy, TrampolineStrategy):
        return
    if "call_site" not in ctx.enabled_optimisations:
        return
    from .terms_to_goalop import terms_to_goalop
    from .optimisations import call_site as _call_site
    ir = terms_to_goalop(ir_source, ctx.db)
    plan = _call_site.analyse(ir, None, ctx.base_globals, db=ctx.db)
    _call_site.populate_runtime_from_plan(
        ir, plan, ctx, ctx.base_globals, db=ctx.db,
    )


def compile_body(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    *,
    ctx: CompilationContext | None = None,
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction (shallow strategy).

    The leaf continuation is ``yield None`` (one solution).  See
    ``_compile_body_impl`` for the shared right-to-left reduction.

    When the caller is internal (``_make_body_compiler``), it passes
    the shared per-predicate ctx so that ``locked_dispatch_keys`` etc.
    propagate to nested goal compilations.  External callers don't
    pass ctx; a plain CompilationContext with ``ShallowStrategy`` and
    empty locked-dispatch state is constructed.
    """
    from .strategy import ShallowStrategy
    if ctx is None:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            strategy=ShallowStrategy(),
        )
    else:
        # Caller-supplied ctx: var_context is this clause's fresh dict;
        # swap it in so compile_body's body-only-Var pre-allocation
        # populates the right context.
        ctx = ctx.replace(
            db=db, var_context=var_context, trail_name=trail_name,
        )
        if ctx.strategy is None:
            ctx = ctx.replace(strategy=ShallowStrategy())
    return _compile_body_impl(goals, ctx)


def _make_body_compiler_impl(
    db: Database,
    *,
    ctx_template: CompilationContext,
) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Shared factory for body-compiler closures — strategy lives on ctx.

    Returns a ``(clause, var_context) -> list[ast.stmt]`` callable that:

    1. Calls ``ctx_template.strategy.preprocess_clause(clause)`` to obtain
       the goal list.  ``ShallowStrategy`` returns ``list(clause.body)``
       unchanged; ``TrampolineStrategy`` applies the destructive-reuse
       rewrite (its ``_dr_*__N`` dispatch builtins only exist in trampoline
       form).
    2. Forks a per-clause ctx from ``ctx_template`` (swapping in the
       clause-specific ``var_context``) and delegates to
       ``_compile_body_impl`` — which reads the same strategy for leaf
       yield + goal dispatch.

    ``ctx_template`` carries per-predicate shared state
    (``locked_dispatch_keys``, ``bucket_ref_map``, ``joint_bucket_ref_map``,
    and most importantly ``strategy``).  The closure captures it by
    reference, so later mutations by the caller (e.g.
    ``_inject_bucket_refs_trampoline``) are visible at per-clause compile
    time.
    """
    def _body_compiler(clause: Clause, var_context: dict[int, str]) -> list[ast.stmt]:
        # Slice D7c-α: body is always the flattened raw clause body.
        # The pre-D7c DR preprocess retired with the legacy fold —
        # destructive-reuse rewriting now happens inside IR lowering
        # via the ``destructive_reuse`` SubCall hint.
        from .destructive_reuse import _flatten_and_goals
        goals = _flatten_and_goals(clause.body)
        ctx = ctx_template.replace(
            db=db, var_context=var_context, trail_name=_TRAIL_PARAM_NAME,
        )
        # Slice E6d-β: reuse the IR the predicate-trampoline TRO sweep
        # already built (see ``_build_predicate_trampoline_funcdef``).
        cached_ir = None
        if ctx_template.clause_ir_cache is not None:
            cached_ir = ctx_template.clause_ir_cache.get(id(clause))
        return _compile_body_impl(
            goals, ctx, head=clause.head, body_ir=cached_ir,
        )
    return _body_compiler


def _make_body_compiler(
    db: Database,
    *,
    ctx_template: CompilationContext | None = None,
) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a shallow body_compiler callable bound to db.

    If no ``ctx_template`` is supplied (``compile_predicate_shallow_ast``
    and test callers), constructs a minimal one carrying ``ShallowStrategy``.
    """
    from .strategy import ShallowStrategy
    if ctx_template is None:
        ctx_template = CompilationContext(
            db=db, var_context={}, trail_name=_TRAIL_PARAM_NAME,
            strategy=ShallowStrategy(),
        )
    elif ctx_template.strategy is None:
        ctx_template = ctx_template.replace(strategy=ShallowStrategy())
    return _make_body_compiler_impl(db, ctx_template=ctx_template)


