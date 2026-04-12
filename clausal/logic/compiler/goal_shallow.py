"""Shallow / short-stack goal-and-body compilation.

This is the ``compile_predicate_shallow`` strategy (Python ``for``
loops over sub-predicate generators; stack grows with recursion
depth; safe for bounded-depth predicates).  The trampoline counterpart
lives in ``.goal_trampoline``.

The two compilers are independent — neither strategy calls into the
other.  Cross-module helpers (control constructs, ITE, tabled NAF,
star-segments, head-list unify runtime) are pulled from ``_monolith``
which re-exports them, so this submodule stays agnostic of the exact
location of each helper.
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
from . import _monolith as _m

# Cross-module helpers re-exported by _monolith — pulled explicitly so the
# goal compiler code doesn't need to be rewritten with ``_m.`` prefixes.
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

# Thread-local context for locked-predicate dispatch caching.
# Lives in _monolith; referenced lazily by _dispatch_call_iter.
_compile_context_local = _m._compile_context_local


def _dispatch_call_iter(
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
    trail_name: str,
) -> ast.expr:
    """Generate: _tramp_call(fname._get_dispatch(), (arg0, …, argN), trail)

    Bridges simple-mode callers to trampoline-mode dispatch functions.
    ``fname`` is resolved from the compiled function's globals, where it
    refers to either a PredicateMeta class or a _DbDispatchAdapter shim.

    Phase 7: if the predicate is locked, emits ``_disp_fname_N`` (a pre-captured
    dispatch function in base_globals) instead of ``fname._get_dispatch()``.
    """
    # Phase 7: use cached dispatch name for locked predicates
    dk = _disp_key(fname, arity)
    locked_keys = getattr(_compile_context_local, "locked_dispatch_keys", frozenset())
    if dk in locked_keys:
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
        args=[dispatch_expr, args_tuple, _name(trail_name)],
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
    _compile_catch, _compile_catch_trampoline,
    _compile_goal_lambda, _flatten_conjunction, _hoist_lambda_args,
)

# ── compile_goal ───────────────────────────────────────────────────────────────


def compile_goal(
    goal: Any,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a goal term into Python statements.

    On success, executes k_stmts (the inlined continuation).
    On failure, does nothing (falls through without executing k_stmts).

    Parameters
    ----------
    goal       : goal term (Is, And, Or, Call, True, False, …)
    db         : live database — used for predicate dispatch and signature lookup
    var_context: mutable Var._id → python_name dict; extended for body-only Vars
    trail_name : name of the trail parameter in the enclosing compiled function
    k_stmts    : continuation statements to inline on success
    """
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

    match goal:

        # ── Unification ─────────────────────────────────────────────────────
        case Unify(left=l, right=r):
            # Phase 5: detect star-list patterns in body Unify goals
            if _is_star_list(l):
                return _compile_star_is(l, r, var_context, trail_name, k_stmts)
            if _is_star_list(r):
                return _compile_star_is(r, l, var_context, trail_name, k_stmts)
            mark = _fresh(_MARK_PREFIX)
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _assign_mark(mark, trail_name),
                _if(_call(_name("unify"), l_expr, r_expr, _name(trail_name)), k_stmts),
                _undo_stmt(mark, trail_name),
            ]

        # ── Arithmetic evaluate-and-bind ─────────────────────────────────────
        case Evaluate(left=l, right=r):
            mark = _fresh(_MARK_PREFIX)
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

        # ── Conjunction ──────────────────────────────────────────────────────
        case And(left=l, right=r):
            # Build right-to-left: r's stmts become k for l
            inner_k = compile_goal(r, db, var_context, trail_name, k_stmts)
            return compile_goal(l, db, var_context, trail_name, inner_k)

        # ── Tuple-as-conjunction ─────────────────────────────────────────────
        # (A, B, C) in goal position → treat as conjunction (same as A and B and C)
        case TupleLiteral(elements=elems) if elems:
            k = k_stmts
            for goal in reversed(elems):
                k = compile_goal(goal, db, var_context, trail_name, k)
            return k

        # ── Disjunction ──────────────────────────────────────────────────────
        case Or(left=l, right=r):
            mark = _fresh(_MARK_PREFIX)
            left_stmts = compile_goal(l, db, var_context, trail_name, k_stmts)
            right_stmts = compile_goal(r, db, var_context, trail_name, k_stmts)
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
                return _compile_tabled_naf_simple(inner, db, var_context, trail_name, k_stmts)

            # Run inner as a sub-generator; succeed iff it yields no solutions.
            # Bindings from the inner goal do not escape (the nested function
            # closes over trail, and we use a fresh mark to undo any accidental
            # bindings that the sub-generator leaves before failing).
            naf_gen = _fresh("_naf_gen")
            naf_flag = _fresh("_naf")
            inner_stmts = compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
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
                **_m._EXTRA_FUNCDEF,
            )
            naf_mark = _fresh(_MARK_PREFIX)
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
                return _compile_reified_ite(test, then, else_, db, var_context, trail_name, k_stmts)
            else:
                return _compile_general_ite(test, then, else_, db, var_context, trail_name, k_stmts)

        # ── Membership / enumeration ─────────────────────────────────────────
        case in_(left=elem, right=collection):
            loop_var = _fresh("_el")
            mark = _fresh(_MARK_PREFIX)
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
            found_flag = _fresh("_found")
            loop_var = _fresh("_el")
            mark = _fresh(_MARK_PREFIX)
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

        # ── throw(Term) — raise LogicException ────────────────────────────
        case Call(func=LoadName(name="throw"), args=[term_arg], kwargs=[]):
            return _compile_throw(term_arg, var_context)

        # ── catch(Goal, Catcher, Recovery) — exception handling ──────────
        case Call(func=LoadName(name="catch"), args=[goal_arg, catcher, recovery], kwargs=[]):
            return _compile_catch(
                goal_arg, catcher, recovery, db, var_context, trail_name, k_stmts,
            )

        # ── catch_error(Goal, Error) — catch any exception, bind Error ──────────
        case Call(func=LoadName(name="catch_error"), args=[goal_arg, error_var], kwargs=[]):
            return _compile_catch(
                goal_arg, error_var, True, db, var_context, trail_name, k_stmts,
                always_catch=True,
            )

        # ── catch_recover(Goal, Error, Recovery) — catch, bind, recover ───
        case Call(func=LoadName(name="catch_recover"), args=[goal_arg, error_var, recovery], kwargs=[]):
            return _compile_catch(
                goal_arg, error_var, recovery, db, var_context, trail_name, k_stmts,
                always_catch=True,
            )

        # ── halt/0, halt/1 — exit ────────────────────────────────────────
        case Call(func=LoadName(name="halt"), args=[], kwargs=[]):
            return [ast.Raise(exc=_call(_name("SystemExit"), ast.Constant(0)))]

        case Call(func=LoadName(name="halt"), args=[code_arg], kwargs=[]):
            code_expr = term_to_ast_expr(code_arg, var_context, eval_arith=True)
            return [ast.Raise(exc=_call(_name("SystemExit"), code_expr))]

        # ── once(goal) — commit to first solution ──────────────────────────
        case Call(func=LoadName(name="once"), args=[inner], kwargs=[]):
            return _compile_once(inner, db, var_context, trail_name, k_stmts)

        # ── call_nth/2 — succeed on Nth solution only ─────────────────────
        case Call(func=LoadName(name="call_nth"), args=[inner, n_arg], kwargs=[]):
            return _compile_call_nth(inner, n_arg, db, var_context, trail_name, k_stmts)

        # ── count_all/2 — count solutions without collecting ──────────────
        case Call(func=LoadName(name="count_all"), args=[inner, count_arg], kwargs=[]):
            return _compile_count_all(inner, count_arg, db, var_context, trail_name, k_stmts)

        # ── setup_call_cleanup/3 — deterministic cleanup ───────────────────
        case Call(func=LoadName(name="setup_call_cleanup"), args=[setup, call_g, cleanup], kwargs=[]):
            return _compile_setup_call_cleanup(
                setup, call_g, cleanup, db, var_context, trail_name, k_stmts,
            )

        # ── call_cleanup/2 — sugar for setup_call_cleanup(true, Call, Cleanup)
        case Call(func=LoadName(name="call_cleanup"), args=[call_g, cleanup], kwargs=[]):
            return _compile_setup_call_cleanup(
                True, call_g, cleanup, db, var_context, trail_name, k_stmts,
            )

        # ── freeze/2 — delay goal until variable is bound ───────────────
        case Call(func=LoadName(name="freeze"), args=[x_arg, goal_arg], kwargs=[]):
            return _compile_freeze(x_arg, goal_arg, db, var_context, trail_name, k_stmts)

        # ── when/2 — generalized coroutining ────────────────────────────────
        case Call(func=LoadName(name="when"), args=[cond_arg, goal_arg], kwargs=[]):
            return _compile_when(cond_arg, goal_arg, db, var_context, trail_name, k_stmts)

        # ── findall/3 — collect all solutions ───────────────────────────────
        case Call(func=LoadName(name="findall"), args=[template, inner_goal, bag], kwargs=[]):
            return _compile_find_all_core(
                template, inner_goal, bag, db, var_context, trail_name, k_stmts,
                fail_on_empty=False, dedup=False,
            )

        # ── bagof/3 — findall that fails on empty ─────────────────────────
        case Call(func=LoadName(name="bagof"), args=[template, inner_goal, bag], kwargs=[]):
            return _compile_find_all_core(
                template, inner_goal, bag, db, var_context, trail_name, k_stmts,
                fail_on_empty=True, dedup=False,
            )

        # ── setof/3 — bagof + dedup ───────────────────────────────────────
        case Call(func=LoadName(name="setof"), args=[template, inner_goal, bag], kwargs=[]):
            return _compile_find_all_core(
                template, inner_goal, bag, db, var_context, trail_name, k_stmts,
                fail_on_empty=True, dedup=True,
            )

        # ── forall/2 — \+( Cond, \+ Action ) ───────────────────────────────
        case Call(func=LoadName(name="forall"), args=[cond, action], kwargs=[]):
            rewritten = Not(operand=And(left=cond, right=Not(operand=action)))
            return compile_goal(rewritten, db, var_context, trail_name, k_stmts)

        # ── Compile-time-known predicate call ────────────────────────────────
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            return _compile_predicate_call(
                fname, call_args, call_kwargs, db, var_context, trail_name, k_stmts
            )

        # ── Qualified predicate call (mod.Pred(X_)) ──────────────────────────
        case Call(func=LoadAttr() as attr, args=call_args, kwargs=call_kwargs):
            fname = _dotted_name_from_loadattr(attr)
            return _compile_predicate_call(
                fname, call_args, call_kwargs, db, var_context, trail_name, k_stmts
            )

        case Call():
            raise NotImplementedError(
                f"compile_goal: cannot compile Call with non-LoadName func: {goal.func!r}"
            )

        case _:
            raise NotImplementedError(
                f"compile_goal: unsupported goal type {type(goal).__name__}: {goal!r}"
            )




def _compile_predicate_call(
    fname: str,
    call_args: list,
    call_kwargs: list,   # list of Keyword nodes from the term
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
) -> list[ast.stmt]:
    """Compile a call to a named predicate.

    WK-4: when kwargs are present, look up the predicate's signature in the
    database and reorder keyword args to positional order.  Raises RuntimeError
    if no signature is registered.
    """

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
    ordered_args, lambda_defs = _hoist_lambda_args(
        ordered_args, var_context, db, trail_name,
    )

    arg_exprs = [term_to_ast_expr(a, var_context, eval_arith=False) for a in ordered_args]
    iter_expr = _dispatch_call_iter(fname, arity, arg_exprs, trail_name)
    return lambda_defs + [
        ast.For(
            target=_name("_", ast.Store()),
            iter=iter_expr,
            body=k_stmts or [ast.Pass()],
            orelse=[],
        )
    ]


# ── compile_body ───────────────────────────────────────────────────────────────


def _compile_body_impl(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    *,
    leaf_yield: ast.stmt,
    compile_goal_fn,
) -> list[ast.stmt]:
    """Shared conjunction compilation, parameterised on strategy.

    Both ``compile_body`` (shallow) and ``compile_body_trampoline`` reduce
    to this helper — they only differ in:

    - ``leaf_yield``: the statement emitted at the innermost continuation
      to surface a solution (``yield None`` for shallow, ``yield (parent, None)``
      for trampoline).
    - ``compile_goal_fn``: the goal-compiler callable that wraps each outer
      goal around the accumulating continuation.  ``compile_goal`` for
      shallow; a closure around ``compile_goal_trampoline`` for trampoline
      (bound to ``self_name``/``parent_name``).

    Body-only Vars (variables that appear in the body but not the head) are
    pre-allocated via ``_preallocate_body_vars`` so that they are registered
    in ``var_context`` as named locals before right-to-left compilation begins.
    This prevents UnboundLocalError when an outer goal references a Var that
    would otherwise only be walrus-introduced inside a later (inner) goal.
    """
    alloc_stmts = _preallocate_body_vars(goals, var_context)
    k: list[ast.stmt] = [leaf_yield]
    for goal in reversed(goals):
        k = compile_goal_fn(goal, db, var_context, trail_name, k)
    return alloc_stmts + k


def compile_body(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction (shallow strategy).

    The leaf continuation is ``yield None`` (one solution).  See
    ``_compile_body_impl`` for the shared right-to-left reduction.
    """
    return _compile_body_impl(
        goals, db, var_context, trail_name,
        leaf_yield=_yield_none_stmt(),
        compile_goal_fn=compile_goal,
    )


def _make_body_compiler(db: Database) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a body_compiler callable bound to db."""
    def _body_compiler(clause: Clause, var_context: dict[int, str]) -> list[ast.stmt]:
        return compile_body(clause.body, db, var_context, _TRAIL_PARAM_NAME)
    return _body_compiler


