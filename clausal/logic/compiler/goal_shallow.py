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
)
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import PredicateMeta
from clausal.terms import PyThunk
from clausal.pythonic_ast.nodes import Keyword as KWNode

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
from .compile_ctx import CompilationContext
from .star_segments import _compile_star_is
from .globals_env import _disp_key, _preallocate_body_vars

# Cross-module helpers — pulled explicitly from real owners.
from .tabled_naf import _is_tabled_naf, _compile_tabled_naf_simple
from .ite_reified import (
    _is_reifiable, _compile_reified_ite, _compile_general_ite,
)
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
    """Generate: _tramp_call(fname._get_dispatch(), (arg0, …, argN), trail)

    Bridges simple-mode callers to trampoline-mode dispatch functions.
    ``fname`` is resolved from the compiled function's globals, where it
    refers to either a PredicateMeta class or a _DbDispatchAdapter shim.

    Phase 7: if the predicate is locked (its dispatch fn pre-cached in
    ``base_globals`` under ``_disp_Foo_N``), emits that direct name
    reference instead of the slower ``fname._get_dispatch()`` call.
    Locked keys live on ``ctx.locked_dispatch_keys``.
    """
    dk = _disp_key(fname, arity)
    if dk in ctx.locked_dispatch_keys:
        dispatch_expr: ast.expr = _name(dk)
    else:
        dispatch_expr = ast.Call(
            func=ast.Attribute(value=_name(fname), attr="_get_dispatch"),
            args=[],
            keywords=[],
        )
    args_tuple = ast.Tuple(elts=arg_exprs, ctx=ast.Load())
    return ast.Call(
        func=_name("_tramp_call"),
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
    """Public entry point — construct ctx if needed, delegate to _dispatch_goal.

    This legacy tuple signature is preserved for external callers
    (``solve.py``, tests).  All internal compilation threads ctx
    directly via ``_dispatch_goal``.
    """
    from .strategy import ShallowStrategy
    if ctx is None:
        ctx = CompilationContext(
            db=db, var_context=var_context, trail_name=trail_name,
            strategy=ShallowStrategy(),
        )
    elif ctx.strategy is None:
        ctx = ctx.replace(strategy=ShallowStrategy())
    return _dispatch_goal(ctx, goal, k_stmts)


def _dispatch_goal(
    ctx: CompilationContext,
    goal: Any,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Internal ctx-native goal dispatcher.

    Shallow-strategy counterpart to ``_dispatch_goal_trampoline``.  On
    success, emit statements that execute *k_stmts* (the inlined
    continuation); on failure, emit statements that fall through.

    Strategy is forced to :class:`ShallowStrategy` on entry — callers
    like ``_compile_find_all_core`` / ``_compile_once`` embed a shallow
    sub-generator inside an outer (possibly trampoline-mode) predicate,
    and reach here with the outer ctx.  The dispatcher you call
    determines the strategy; the ``ctx.strategy`` field controls only
    the outer predicate's body compilation.
    """
    from .strategy import ShallowStrategy
    if not isinstance(ctx.strategy, ShallowStrategy):
        ctx = ctx.replace(strategy=ShallowStrategy())
    db = ctx.db
    var_context = ctx.var_context
    trail_name = ctx.trail_name

    goal = deref(goal)

    # Booleans — must be tested before isinstance(term, int) in the general path
    if goal is True:
        return list(k_stmts)
    if goal is False:
        return []

    # PyThunk as a goal — evaluate for side effects, then continue.
    if isinstance(goal, PyThunk):
        call_expr = term_to_ast_expr(goal, var_context, eval_arith=False)
        return [ast.Expr(value=call_expr)] + list(k_stmts)

    # Strategy-agnostic deterministic cases (unify, evaluate, dif, FD
    # comparisons, structural comparisons) are identical between shallow
    # and trampoline — handle them in the shared helpers first.
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
            # Build right-to-left: r's stmts become k for l
            inner_k = _dispatch_goal(ctx, r, k_stmts)
            return _dispatch_goal(ctx, l, inner_k)

        # ── Tuple-as-conjunction ─────────────────────────────────────────────
        # (A, B, C) in goal position → treat as conjunction (same as A and B and C)
        case TupleLiteral(elements=elems) if elems:
            k = k_stmts
            for goal in reversed(elems):
                k = _dispatch_goal(ctx, goal, k)
            return k

        # ── Disjunction ──────────────────────────────────────────────────────
        case Or(left=l, right=r):
            mark = ctx.fresh(_MARK_PREFIX)
            left_stmts = _dispatch_goal(ctx, l, k_stmts)
            right_stmts = _dispatch_goal(ctx, r, k_stmts)
            # Note: both branches share var_context; body-only vars in Or
            # branches that differ between branches are a known POC limitation.
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
        case Not(operand=inner):
            # WFS: if inner is a call to a tabled predicate, use _naf_tabled
            # instead of inline NAF (handles cycles through negation).
            if _is_tabled_naf(inner, db):
                return _compile_tabled_naf_simple(ctx, inner, k_stmts)

            # Run inner as a sub-generator; succeed iff it yields no solutions.
            # Bindings from the inner goal do not escape (the nested function
            # closes over trail, and we use a fresh mark to undo any accidental
            # bindings that the sub-generator leaves before failing).
            naf_gen = ctx.fresh("_naf_gen")
            naf_flag = ctx.fresh("_naf")
            inner_stmts = _dispatch_goal(ctx, inner, [_yield_none_stmt()])
            # Always append ``return; yield`` so the NAF function is a generator
            # type even when inner_stmts is empty (e.g. inner goal is False).
            # The dead ``yield`` after ``return`` is the standard Python trick.
            naf_body = inner_stmts + [
                ast.Return(value=ast.Constant(value=None)),
                ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
            ]
            naf_fn = ast.FunctionDef(
                name=naf_gen,
                args=ast.arguments(
                    posonlyargs=[], args=[], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=naf_body,
                decorator_list=[], returns=None, type_comment=None,
                **_EXTRA_FUNCDEF,
            )
            naf_mark = ctx.fresh(_MARK_PREFIX)
            return [
                naf_fn,
                _assign(naf_flag, ast.Constant(value=True)),
                _assign_mark(naf_mark, trail_name),
                ast.For(
                    target=_name("_", ast.Store()),
                    iter=_call(_name(naf_gen)),
                    body=[
                        _assign(naf_flag, ast.Constant(value=False)),
                        ast.Break(),
                    ],
                    orelse=[],
                ),
                _undo_stmt(naf_mark, trail_name),
                _if(_name(naf_flag), k_stmts),
            ]

        # ── Reified if-then-else ───────────────────────────────────────────
        case IfExpr(test=test, body=then, orelse=else_):
            if _is_reifiable(test):
                return _compile_reified_ite(ctx, test, then, else_, k_stmts)
            else:
                return _compile_general_ite(ctx, test, then, else_, k_stmts)

        # ── Membership / enumeration ─────────────────────────────────────────
        # ── catch(Goal, Catcher, Recovery) — exception handling ──────────
        case Call(func=LoadName(name="catch"), args=[goal_arg, catcher, recovery], kwargs=[]):
            return _compile_catch(ctx, goal_arg, catcher, recovery, k_stmts)

        # ── catch_error(Goal, Error) — catch any exception, bind Error ──────────
        case Call(func=LoadName(name="catch_error"), args=[goal_arg, error_var], kwargs=[]):
            return _compile_catch(
                ctx, goal_arg, error_var, True, k_stmts,
                always_catch=True,
            )

        # ── catch_recover(Goal, Error, Recovery) — catch, bind, recover ───
        case Call(func=LoadName(name="catch_recover"), args=[goal_arg, error_var, recovery], kwargs=[]):
            return _compile_catch(
                ctx, goal_arg, error_var, recovery, k_stmts,
                always_catch=True,
            )

        # ── forall/2 — \+( Cond, \+ Action ) ───────────────────────────────
        case Call(func=LoadName(name="forall"), args=[cond, action], kwargs=[]):
            rewritten = Not(operand=And(left=cond, right=Not(operand=action)))
            return _dispatch_goal(ctx, rewritten, k_stmts)


        # ── Compile-time-known predicate call ────────────────────────────────
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            return _compile_predicate_call(ctx, fname, call_args, call_kwargs, k_stmts)

        # ── Qualified predicate call (mod.Pred(X_)) ──────────────────────────
        case Call(func=LoadAttr() as attr, args=call_args, kwargs=call_kwargs):
            fname = _dotted_name_from_loadattr(attr)
            return _compile_predicate_call(ctx, fname, call_args, call_kwargs, k_stmts)

        case Call():
            raise NotImplementedError(
                f"compile_goal: cannot compile Call with non-LoadName func: {goal.func!r}"
            )

        case _:
            raise NotImplementedError(
                f"compile_goal: unsupported goal type {type(goal).__name__}: {goal!r}"
            )




def _compile_predicate_call_impl(
    ctx: CompilationContext,
    fname: str,
    call_args: list,
    call_kwargs: list,
    k_stmts: list[ast.stmt],
    *,
    direct_bucket_ref: str | None = None,
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

    arg_exprs = [term_to_ast_expr(a, var_context, eval_arith=False) for a in ordered_args]
    return lambda_defs + ctx.strategy.emit_sub_call(
        ctx, fname, arity, arg_exprs, k_stmts,
        direct_bucket_ref=direct_bucket_ref,
    )


def _compile_predicate_call(
    ctx: CompilationContext,
    fname: str,
    call_args: list,
    call_kwargs: list,   # list of Keyword nodes from the term
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a call to a named predicate.

    Thin wrapper around ``_compile_predicate_call_impl`` — the strategy-
    specific call site (``for`` loop vs StepGenerator while-loop) is
    emitted via ``ctx.strategy.emit_sub_call``.
    """
    return _compile_predicate_call_impl(
        ctx, fname, call_args, call_kwargs, k_stmts,
    )


# ── compile_body ───────────────────────────────────────────────────────────────


def _compile_deterministic_goal(
    ctx: CompilationContext,
    goal,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt] | None:
    """Try to compile *goal* as one of the strategy-agnostic deterministic
    goal types (Unify, Evaluate, dif, arithmetic/structural comparisons,
    FD constraints).  Return the compiled statements, or ``None`` if the
    goal is of a kind handled differently by shallow vs trampoline.

    These twelve cases are byte-identical between ``compile_goal`` and
    ``compile_goal_trampoline`` — they emit unify/dif/fd_eq/... runtime
    calls wrapped in mark/undo (where appropriate), all producing at
    most one solution and therefore the same AST under both strategies.
    """
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    match goal:
        # ── Unification ─────────────────────────────────────────────────────
        case Unify(left=l, right=r):
            # Phase 5: detect star-list patterns in body Unify goals
            if _is_star_list(l) or _is_star_list(r):
                if _is_star_list(l):
                    return _compile_star_is(ctx, l, r, k_stmts)
                return _compile_star_is(ctx, r, l, k_stmts)
            mark = ctx.fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        # ── Arithmetic evaluate-and-bind ─────────────────────────────────────
        case Evaluate(left=l, right=r):
            mark = ctx.fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context)
            r_expr = arith_to_ast_expr(r, var_context)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        # ── dif (disequality constraint) ──────────────────────────────────
        case DoesNotUnify(left=l, right=r):
            # dif/2 semantics: post constraint, succeed if terms can stay different.
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_dif"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        # ── CLP(FD) arithmetic equality ─────────────────────────────────────
        case ArithEq(left=l, right=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_fd_eq"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        case ArithNeq(left=l, right=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_fd_ne"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        # ── Structural equality (Prolog ==/2, \==/2) ───────────────────────
        case StructuralEq(left=l, right=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_structural_eq"), l_expr, r_expr), k_stmts),
            ]

        case StructuralNeq(left=l, right=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_structural_neq"), l_expr, r_expr), k_stmts),
            ]

        # ── CLP(FD) arithmetic comparisons ──────────────────────────────────
        case Lt(left=l, right=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_fd_lt"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        case LtE(left=l, right=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_fd_le"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        case Gt(left=l, right=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_fd_gt"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

        case GtE(left=l, right=r):
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_fd_ge"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

    return None


def _compile_shared_membership_goal(
    ctx: CompilationContext,
    goal,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt] | None:
    """Compile ``in_`` / ``NotIn`` membership goals — strategy-agnostic.

    These produce multiple / single solutions respectively, but the AST
    they emit (a ``for`` loop over ``_in_iter(...)`` with unify + mark/undo)
    is identical in shallow and trampoline mode, so both strategies'
    ``match`` dispatchers delegate here.
    """
    var_context = ctx.var_context
    trail_name = ctx.trail_name
    match goal:
        # ── Membership ───────────────────────────────────────────────────────
        case in_(left=elem, right=collection):
            loop_var = ctx.fresh("_el")
            mark = ctx.fresh(_MARK_PREFIX)
            elem_expr = term_to_ast_expr(elem, var_context, eval_arith=False)
            coll_expr = term_to_ast_expr(collection, var_context, eval_arith=False)
            return [
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_in_iter_expr(elem, coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        _if(
                            _call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            k_stmts,
                        ),
                        _undo_stmt(mark, trail_name),
                    ],
                    orelse=[],
                )
            ]

        # ── Non-membership ───────────────────────────────────────────────────
        case NotIn(left=elem, right=collection):
            found_flag = ctx.fresh("_found")
            loop_var = ctx.fresh("_el")
            mark = ctx.fresh(_MARK_PREFIX)
            elem_expr = term_to_ast_expr(elem, var_context, eval_arith=False)
            coll_expr = term_to_ast_expr(collection, var_context, eval_arith=False)
            return [
                _assign(found_flag, ast.Constant(value=False)),
                ast.For(
                    target=_name(loop_var, ast.Store()),
                    iter=_in_iter_expr(elem, coll_expr),
                    body=[
                        _assign_mark(mark, trail_name),
                        ast.If(
                            test=_call(_name("unify"), elem_expr, _name(loop_var), _name(trail_name)),
                            body=[
                                _assign(found_flag, ast.Constant(value=True)),
                                _undo_stmt(mark, trail_name),
                                ast.Break(),
                            ],
                            orelse=[_undo_stmt(mark, trail_name)],
                        ),
                    ],
                    orelse=[],
                ),
                _if(ast.UnaryOp(op=ast.Not(), operand=_name(found_flag)), k_stmts),
            ]

    return None


def _compile_shared_meta_call(
    ctx: CompilationContext,
    goal,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt] | None:
    """Try to compile *goal* as one of the meta-predicate calls that share
    an implementation between shallow and trampoline (they all dispatch to
    the strategy-agnostic ``_compile_*`` helpers in ``control_constructs``).

    Returns the compiled stmts, or ``None`` if *goal* is not one of these
    arms.  The caller can then fall through to its own ``match`` for
    strategy-specific cases (And, Or, Not, IfExpr, catch-family, predicate
    calls, …).

    Covered arms (all identical in shallow vs trampoline):

    - ``throw(Term)``                        → ``_compile_throw``
    - ``halt/0``, ``halt/1``                 → ``raise SystemExit``
    - ``once(G)``                            → ``_compile_once``
    - ``call_nth(G, N)``                     → ``_compile_call_nth``
    - ``count_all(G, N)``                    → ``_compile_count_all``
    - ``setup_call_cleanup(S, C, Cl)``       → ``_compile_setup_call_cleanup``
    - ``call_cleanup(C, Cl)``                → sugar for setup_call_cleanup(true, C, Cl)
    - ``freeze(X, G)``                       → ``_compile_freeze``
    - ``when(Cond, G)``                      → ``_compile_when``
    - ``findall/bagof/setof(T, G, Bag)``     → ``_compile_find_all_core`` with flags
    """
    var_context = ctx.var_context
    match goal:
        # ── throw(Term) — raise a logic exception ────────────────────────
        case Call(func=LoadName(name="throw"), args=[term_arg], kwargs=[]):
            return _compile_throw(ctx, term_arg)

        # ── halt/0, halt/1 — exit ────────────────────────────────────────
        case Call(func=LoadName(name="halt"), args=[], kwargs=[]):
            return [ast.Raise(exc=_call(_name("SystemExit"), ast.Constant(0)))]

        case Call(func=LoadName(name="halt"), args=[code_arg], kwargs=[]):
            code_expr = term_to_ast_expr(code_arg, var_context, eval_arith=True)
            return [ast.Raise(exc=_call(_name("SystemExit"), code_expr))]

        # ── once(goal) — commit to first solution ──────────────────────────
        case Call(func=LoadName(name="once"), args=[inner], kwargs=[]):
            return _compile_once(ctx, inner, k_stmts)

        # ── call_nth/2 — succeed on Nth solution only ─────────────────────
        case Call(func=LoadName(name="call_nth"), args=[inner, n_arg], kwargs=[]):
            return _compile_call_nth(ctx, inner, n_arg, k_stmts)

        # ── count_all/2 — count solutions without collecting ──────────────
        case Call(func=LoadName(name="count_all"), args=[inner, count_arg], kwargs=[]):
            return _compile_count_all(ctx, inner, count_arg, k_stmts)

        # ── setup_call_cleanup/3 — deterministic cleanup ───────────────────
        case Call(func=LoadName(name="setup_call_cleanup"), args=[setup, call_g, cleanup], kwargs=[]):
            return _compile_setup_call_cleanup(ctx, setup, call_g, cleanup, k_stmts)

        # ── call_cleanup/2 — sugar for setup_call_cleanup(true, Call, Cleanup)
        case Call(func=LoadName(name="call_cleanup"), args=[call_g, cleanup], kwargs=[]):
            return _compile_setup_call_cleanup(ctx, True, call_g, cleanup, k_stmts)

        # ── freeze/2 — delay goal until variable is bound ───────────────
        case Call(func=LoadName(name="freeze"), args=[x_arg, goal_arg], kwargs=[]):
            return _compile_freeze(ctx, x_arg, goal_arg, k_stmts)

        # ── when/2 — generalized coroutining ────────────────────────────────
        case Call(func=LoadName(name="when"), args=[cond_arg, goal_arg], kwargs=[]):
            return _compile_when(ctx, cond_arg, goal_arg, k_stmts)

        # ── findall/3 — collect all solutions ───────────────────────────────
        case Call(func=LoadName(name="findall"), args=[template, inner_goal, bag], kwargs=[]):
            return _compile_find_all_core(
                ctx, template, inner_goal, bag, k_stmts,
                fail_on_empty=False, dedup=False,
            )

        # ── bagof/3 — findall that fails on empty ─────────────────────────
        case Call(func=LoadName(name="bagof"), args=[template, inner_goal, bag], kwargs=[]):
            return _compile_find_all_core(
                ctx, template, inner_goal, bag, k_stmts,
                fail_on_empty=True, dedup=False,
            )

        # ── setof/3 — bagof + dedup ───────────────────────────────────────
        case Call(func=LoadName(name="setof"), args=[template, inner_goal, bag], kwargs=[]):
            return _compile_find_all_core(
                ctx, template, inner_goal, bag, k_stmts,
                fail_on_empty=True, dedup=True,
            )

    return None


def _compile_body_impl(
    goals: list,
    ctx: CompilationContext,
    *,
    original_goals: list | None = None,
    head: Any = None,
) -> list[ast.stmt]:
    """Shared conjunction compilation, parameterised on ``ctx.strategy``.

    Takes a :class:`CompilationContext` bundling ``db``, ``var_context``,
    ``trail_name`` (and, trampoline-only, ``self_name``/``parent_name``)
    plus the compilation strategy.

    Both ``compile_body`` (shallow) and ``compile_body_trampoline`` reduce
    to this helper — they differ only via ``ctx.strategy``:

    - ``ctx.strategy.emit_leaf_yield(ctx)`` produces the solution-surfacing
      statement at the innermost continuation (``yield None`` for shallow,
      ``yield (parent, None)`` for trampoline).
    - ``ctx.strategy.compile_goal(ctx, goal, k_stmts)`` dispatches to the
      strategy-specific recursive goal compiler.

    Body-only Vars (variables that appear in the body but not the head) are
    pre-allocated via ``_preallocate_body_vars`` so that they are registered
    in ``ctx.var_context`` as named locals before right-to-left compilation
    begins.  This prevents UnboundLocalError when an outer goal references a
    Var that would otherwise only be walrus-introduced inside a later (inner)
    goal.
    """
    strategy = ctx.strategy
    alloc_stmts = _preallocate_body_vars(goals, ctx.var_context)
    # Slice F1: Phase 5 entry gate — README §10 invariant 1.  Lock in
    # the contract that ``_preallocate_body_vars`` covers every Var
    # reachable from a body goal so the right-to-left fold below
    # cannot reference an unregistered Var (which would generate a
    # walrus-introduced local that earlier-emitted goals try to read).
    from .invariants import assert_body_vars_preallocated
    assert_body_vars_preallocated(ctx, goals)
    leaf: list[ast.stmt] = [strategy.emit_leaf_yield(ctx)]

    # Legacy right-to-left fold.  This advances ``ctx.fresh`` — the IR
    # parallel run below re-uses the same starting counter via a cloned
    # FreshNames so the two emissions pick identical fresh names.
    fresh_before = ctx.fresh._n
    legacy_k: list[ast.stmt] = list(leaf)
    for goal in reversed(goals):
        legacy_k = strategy.compile_goal(ctx, goal, legacy_k)

    # **D7b**: when the IR path is enabled and succeeds, *its* output
    # is what we return — the IR path is now source-of-truth, the
    # legacy fold runs alongside as a verification gate.  IR fallback
    # (``terms_to_goalop`` raises ``NotImplementedError`` on a body
    # shape outside the D5 subset) returns ``None`` and we use the
    # legacy result; this keeps any never-yet-seen pathological body
    # building cleanly until D7c retires legacy outright.
    chosen_k = legacy_k
    if _ir_path_enabled(ctx):
        ir_k = _run_ir_parallel(
            goals, ctx, leaf, legacy_k, fresh_before,
            original_goals=original_goals if original_goals is not None else goals,
            head=head,
        )
        if ir_k is not None:
            chosen_k = ir_k

    return alloc_stmts + chosen_k


# ── Slice D4 harness observability ───────────────────────────────────────────
#
# Counters let tests assert the IR path isn't silently falling back on
# every compile (e.g. if a module scrub caused ``nodes.Not`` captured in
# ``terms_to_goalop`` to miss new ``Not`` instances).  ``reset()`` and
# the raw dict are module-private — tests import them by name.
_IR_PATH_STATS: dict[str, int] = {"runs": 0, "fallbacks": 0, "matches": 0}


def _ir_path_stats_reset() -> None:
    _IR_PATH_STATS["runs"] = 0
    _IR_PATH_STATS["fallbacks"] = 0
    _IR_PATH_STATS["matches"] = 0


def _ir_path_enabled(ctx: CompilationContext) -> bool:
    """Slice D4 feature flag.

    Enabled per-context via ``ctx.use_ir_path`` or globally via the
    ``CLAUSAL_IR_PATH=1`` env var (the CI fallback).  D7 flips the
    default to ``True``; until then the legacy fold remains the
    source of truth and the IR path is a verification-only shadow.
    """
    import os
    if ctx.use_ir_path:
        return True
    return os.environ.get("CLAUSAL_IR_PATH") == "1"


def _run_ir_parallel(
    goals: list,
    ctx: CompilationContext,
    leaf: list[ast.stmt],
    legacy_k: list[ast.stmt],
    fresh_before: int,
    *,
    original_goals: list | None = None,
    head: Any = None,
) -> list[ast.stmt] | None:
    """Slice D4 parallel-implementation harness, promoted by D7b.

    Run the GoalOp IR path alongside the just-completed legacy fold and
    assert ``ast.dump`` equality.  Any drift is stop-the-line — this
    routine raises ``AssertionError`` rather than silently papering
    over a lowering bug.  On success returns the IR-produced
    statements (which D7b made source-of-truth); on
    ``NotImplementedError`` from ``terms_to_goalop`` (body shape
    outside the D5 subset) returns ``None`` so the caller falls back
    to the legacy result.

    The IR run uses a cloned :class:`FreshNames` starting at
    *fresh_before* (the legacy run's pre-fold counter value) so the
    two emissions pick identical fresh names.  ``ctx.fresh`` itself
    is not touched — callers see only the legacy advance, which is
    what downstream compilation relies on for further fresh-name
    monotonicity.
    """
    import logging
    from ._ast_helpers import FreshNames
    from .strategy import ShallowStrategy
    from .terms_to_goalop import terms_to_goalop
    from . import lower_python_shallow, lower_python_trampoline
    from .strategy import TrampolineStrategy
    _IR_PATH_STATS["runs"] += 1
    # Slice E4b: build IR from the *original* (un-DR-rewritten) goal
    # list so ``destructive_reuse.analyse`` can flag eligible SubCalls
    # under their original fname; the lowering reads the hint and
    # emits the ``_dr_<name>__<arity>`` variant.  Legacy still runs
    # the preprocess-time rewrite (its output drives ``goals``), so
    # when the caller didn't supply ``original_goals`` we treat
    # ``goals`` itself as original — byte-parity holds because both
    # legacy-fold and IR-lowering then emit the same DR-variant name.
    ir_source = original_goals if original_goals is not None else goals
    try:
        ir = terms_to_goalop(ir_source, ctx.db)
    except NotImplementedError as exc:
        # Legitimate fallback — D2 subset is still growing.  Logging here
        # lets D5 development see which body shapes still drop to legacy
        # without instrumenting individual sub-slices; turn on with
        # ``pytest --log-cli-level=DEBUG`` or ``logging.basicConfig``.
        _IR_PATH_STATS["fallbacks"] += 1
        logging.getLogger(__name__).debug("ir-path fallback: %s", exc)
        return None
    # Slice E4b: apply destructive-reuse hints from E1's analyse pass
    # so IR lowering emits the ``_dr_<name>__<arity>`` variant when
    # the hint is set.  Gated on strategy support — shallow has no
    # DR variants.  Running on the original (un-rewritten) IR lets
    # the analyse see the original fnames ("append", …) before the
    # SubCall arm in lowering rewrites to the DR name.
    if (
        isinstance(ctx.strategy, TrampolineStrategy)
        and ctx.strategy.supports_destructive_reuse
        and head is not None
        and "destructive_reuse" in ctx.enabled_optimisations
    ):
        from .optimisations import destructive_reuse as _dr
        _dr_plan = _dr.analyse(ir, head, db=ctx.db)
        ir = _dr.apply(ir, _dr_plan)
    # Slice E4a: apply call-site bucket-ref hints from E3's analyse pass
    # so IR lowering can emit the direct bucket reference straight off
    # the :class:`SubCall`.  Legacy's ``_inject_bucket_refs_trampoline``
    # still populates ``ctx.bucket_ref_map`` (its retirement waits for
    # E6); both paths produce byte-identical AST because the E3
    # analyser's gkeys are guaranteed identical to the legacy map's.
    if (
        ctx.base_globals is not None
        and isinstance(ctx.strategy, TrampolineStrategy)
        and "call_site" in ctx.enabled_optimisations
    ):
        from .optimisations import call_site as _call_site
        _plan = _call_site.analyse(ir, None, ctx.base_globals, db=ctx.db)
        ir = _call_site.apply(ir, _plan)
    lower_fn = (
        lower_python_shallow.lower
        if isinstance(ctx.strategy, ShallowStrategy)
        else lower_python_trampoline.lower
    )
    ir_ctx = ctx.replace(fresh=FreshNames(starting_at=fresh_before))
    new_k = lower_fn(ir, ir_ctx, list(leaf))
    legacy_dump = [ast.dump(s) for s in legacy_k]
    new_dump = [ast.dump(s) for s in new_k]
    if new_dump != legacy_dump:
        raise AssertionError(
            "Slice D4 IR-path AST diff from legacy path — stop the line.\n"
            f"  legacy: {legacy_dump}\n"
            f"  ir:     {new_dump}"
        )
    _IR_PATH_STATS["matches"] += 1
    return new_k


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
        # Slice E5b: when ``destructive_reuse`` is disabled, skip the
        # legacy DR preprocess so legacy and IR fold both see the
        # original (un-renamed) body — neither path emits a
        # ``_dr_<name>__<arity>`` call.
        _dr_enabled = (
            ctx_template.strategy.supports_destructive_reuse
            and "destructive_reuse" in ctx_template.enabled_optimisations
        )
        if _dr_enabled:
            goals = ctx_template.strategy.preprocess_clause(clause, db=db)
        else:
            from .destructive_reuse import _flatten_and_goals
            goals = _flatten_and_goals(clause.body)
        # Slice E4b: keep the un-DR-rewritten body around for the IR
        # path.  Legacy fold consumes the rewritten ``goals`` (SubCall
        # fname already ``_dr_…``); IR lowering consumes the flattened
        # original body + hints and renames in the SubCall arm.  Both
        # emit the same AST under the D4/D7b harness.
        original_goals: list | None = None
        if _dr_enabled:
            from .destructive_reuse import _flatten_and_goals
            original_goals = _flatten_and_goals(clause.body)
        ctx = ctx_template.replace(
            db=db, var_context=var_context, trail_name=_TRAIL_PARAM_NAME,
        )
        return _compile_body_impl(
            goals, ctx,
            original_goals=original_goals,
            head=clause.head,
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


