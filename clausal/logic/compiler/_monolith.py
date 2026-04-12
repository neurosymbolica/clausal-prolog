"""clausal.logic.compiler — predicate compiler (Steps 4 + 5).

Step 4 (head patterns): head_to_match_pattern, compile_head_to_match_case
Step 5 (body goals):    term_to_ast_expr, arith_to_ast_expr, compile_goal,
                        compile_body, _make_body_compiler

List patterns:  Bidirectional ``[HEAD, *TAIL]`` via _head_list_unify_input/output.
                Repeated head vars via dup_guards.  See block comment above
                ``_head_list_unify_input`` for the full design.

Two compilation strategies are provided:

**Shallow / short-stack** (``compile_predicate_shallow``)
    Each clause becomes a ``match`` arm.  The body ends with ``yield None``
    for each solution.  Sub-predicate calls use Python ``for`` loops so the
    Python call stack grows with recursion depth.  Safe only for predicates
    with bounded call depth (e.g., fact tables, leaf predicates).  Declared
    via the ``-shallow([pred/arity, ...])`` directive in ``.clausal`` files.

    Compiled function signature::

        def {functor}__{arity}(arg0, …, argN, trail, k):
            …
            yield None   # ← one solution

**Trampoline / stack-safe** (``compile_predicate_trampoline``)
    Every generated function participates in the
    ``clausal.logic.trampoline`` tuple protocol.  Sub-predicate calls use
    ``StepGenerator(dispatch, this_generator, …)`` so the Python call stack
    does *not* grow.  Solutions are surfaced via ``yield (parent, None)``;
    exhaustion via ``yield (parent, DONE)``.  The trampoline drives all
    generators.

    Compiled function signature::

        def {functor}__{arity}(this_generator, parent, arg0, …, argN, trail):
            …
            yield (parent, _DONE)   # ← search exhausted
"""

from __future__ import annotations

import ast
import dataclasses
import threading
from fractions import Fraction
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref, unify
from clausal.logic.trampoline import Step, DONE, StepGenerator
from clausal.terms import (
    Compound,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    And, Or, Not,
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq, StructuralEq, StructuralNeq,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    Call, LoadName, LoadAttr,
    SegList, ConcreteSeg, VarSeg, _seglist_unify_gen, _multi_star_splits,
    SegString,
)
from clausal.pythonic_ast.nodes import IfExpr, Lambda
from clausal.pythonic_ast.nodes import StarUnpack, TupleLiteral, DictLiteral, SetLiteral
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
from clausal.codegen import functiondef_to_function
from clausal.logic.solve import _deref_walk as _deref_walk_fn

# ── Hoisted formerly function-local imports (Phase 0.5a) ─────────────────────
# These were inner imports scattered through compile entrypoints.  Moved to
# module scope after verifying no import cycle results.  Multiple aliases for
# the same symbol are kept verbatim so call sites don't need editing.
import sys as _sys  # noqa: E402
import warnings  # noqa: E402
from collections import defaultdict  # noqa: E402

from clausal.terms import DictTerm, SetTerm, KWTerm, PyThunk  # noqa: E402
_DictTerm = DictTerm
_SetTerm = SetTerm
_PyThunk = PyThunk
_KWTerm = KWTerm
_KWTerm_t = KWTerm
_DictTerm_t = DictTerm
_SetTerm_t = SetTerm
_DictTerm_s = DictTerm
_SetTerm_s = SetTerm

from clausal.pythonic_ast.nodes import (  # noqa: E402
    SetLiteral as _SetLiteral,
    Call as AstCall,
    LoadName as AstLoadName,
    Keyword as KWNode,
)
_SL = _SetLiteral
_SetLiteral_t = _SetLiteral

from clausal.logic.builtins import (  # noqa: E402
    get_builtin_predicate,
    BuiltinPredicate,
    _BUILTIN_CLASSES,
)
from clausal.logic.builtins.lists import _append_dr__3 as _dr_append_fn  # noqa: E402
from clausal.logic.builtins.dict_set import (  # noqa: E402
    _dict_put_dr__4 as _dr_dict_put_fn,
    _set_union_dr__3 as _dr_set_union_fn,
)

from clausal.logic.constraints import (  # noqa: E402
    dif as _dif_fn,
    reify_eq as _reify_eq_fn,
    structural_eq as _structural_eq_fn,
    structural_neq as _structural_neq_fn,
)
_dif_fn_s = _dif_fn
_reify_eq_fn_s = _reify_eq_fn

from clausal.logic.clpfd import (  # noqa: E402
    fd_eq as _fd_eq_fn,
    fd_ne as _fd_ne_fn,
    fd_lt as _fd_lt_fn,
    fd_le as _fd_le_fn,
    fd_gt as _fd_gt_fn,
    fd_ge as _fd_ge_fn,
    reify_fd as _reify_fd_fn,
)
_fd_eq_fn_s = _fd_eq_fn
_fd_ne_fn_s = _fd_ne_fn
_fd_lt_fn_s = _fd_lt_fn
_fd_le_fn_s = _fd_le_fn
_fd_gt_fn_s = _fd_gt_fn
_fd_ge_fn_s = _fd_ge_fn
_reify_fd_fn_s = _reify_fd_fn

from clausal.logic.exceptions import (  # noqa: E402
    LogicException as _LogicException_cls,
    python_error_term as _python_error_term_fn,
    type_error as _type_error_fn,
)
_python_error_term_fn_s = _python_error_term_fn
_type_error_fn_s = _type_error_fn

from clausal.logic.variables import (  # noqa: E402
    get_attr as _get_attr_fn,
    put_attr as _put_attr_fn,
)
_get_attr_fn_s = _get_attr_fn
_put_attr_fn_s = _put_attr_fn

from clausal.logic.coroutining import (  # noqa: E402
    _install_when_ground as _install_when_ground_fn,
    _install_when_disjunction as _install_when_disjunction_fn,
    _install_when_condition as _install_when_condition_fn,
)
_install_when_ground_fn_s = _install_when_ground_fn
_install_when_disjunction_fn_s = _install_when_disjunction_fn
_install_when_condition_fn_s = _install_when_condition_fn

from clausal.logic.tabling import (  # noqa: E402
    _naf_tabled as _naf_tabled_fn,
    _TABLING_SUSPEND,
)
_naf_tabled_fn_s = _naf_tabled_fn

# ── Compiled-code naming constants (moved to ._ast_helpers) ──────────────────
from ._ast_helpers import (  # noqa: E402,F401
    _MARK_PREFIX, _TRAIL_PARAM_NAME, _K_PARAM_NAME, _DISP_PREFIX,
    _TRAMP_PARENT_NAME, _THIS_GEN_NAME,
)


# Phase 7: thread-local context for locked-predicate dispatch caching.
# Set during compile_predicate_trampoline / compile_predicate so that
# _dispatch_call_trampoline / _dispatch_call_iter can emit a direct name
# reference (_disp_Foo_2) instead of Foo._get_dispatch() for locked predicates.
_compile_context_local: threading.local = threading.local()


# ── ast helpers (moved to ._ast_helpers, re-imported here) ───────────────────
from ._ast_helpers import (  # noqa: E402,F401
    _name, _attr, _call, _fresh, _compile_counter,
)

# ── Bidirectional list pattern unification (moved to .head_list_unify) ───────
from .head_list_unify import (  # noqa: E402,F401
    _head_list_unify_input_py,
    _head_list_unify_output_py,
    _head_list_unify_input,
    _head_list_unify_output,
    _head_multi_star_error,
    _body_star_unify,
    _build_star_list,
    _build_multi_star_list,
    _in_iter,
    _body_multi_star_unify,
    _tramp_call,
)

# ── Variable naming (moved to ._vars) ─────────────────────────────────────────
from ._vars import _var_python_name, _collect_vars  # noqa: E402,F401

# ── Globals-environment construction (moved to .globals_env) ─────────────────
from .globals_env import (  # noqa: E402,F401
    _set_of_dedup,
    _DbDispatchAdapter,
    _GlobalsDb,
    _collect_head_types,
    _collect_py_thunks,
    _collect_types_from_term,
    _collect_call_targets,
    _collect_globals_info,
    _disp_key,
    _merge_builtin,
    _inject_call_targets,
    _inject_resolved_targets,
    _preallocate_body_vars,
)


# ── Term → AST expression (moved to .terms_to_ast) ───────────────────────────
from .terms_to_ast import (  # noqa: E402,F401
    term_to_ast_expr, arith_to_ast_expr,
    _is_star_list, _parse_star_segments, _count_stars,
    _dotted_name_from_loadattr,
)

# ── Misc AST-building helpers (moved to ._ast_helpers) ────────────────────────
from ._ast_helpers import (  # noqa: E402,F401
    _yield_none_stmt, _assign, _assign_mark, _undo_stmt, _if, _in_iter_expr,
)


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


# ── WFS: tabled NAF helpers ────────────────────────────────────────────────────


def _is_tabled_naf(inner_goal, db) -> bool:
    """Return True if inner_goal is a Call to a tabled predicate."""
    if not isinstance(inner_goal, Call):
        return False
    if not isinstance(inner_goal.func, LoadName):
        return False
    if db is None:
        return False
    fname = inner_goal.func.name
    call_arity = len(inner_goal.args) + len(inner_goal.kwargs)
    return db.is_tabled(fname, call_arity)


def _compile_tabled_naf_simple(inner_goal, db, var_context, trail_name, k_stmts):
    """Emit _naf_tabled(...) call for tabled NAF (both simple and trampoline modes).

    Generates:
        _m = trail.mark()
        if _naf_tabled("fname", arity, (arg0, ..., argN), trail, _table_store):
            k_stmts
        trail.undo(_m)
    """
    fname = inner_goal.func.name
    call_args = inner_goal.args
    call_kwargs = inner_goal.kwargs
    # Normalize kwargs into positional using signature
    if call_kwargs:
        sig = db.signature_for(fname, len(call_args) + len(call_kwargs))
        if sig is not None:
            kw_dict = {kw.arg: kw.value for kw in call_kwargs}
            all_args = []
            for i, field in enumerate(sig):
                if i < len(call_args):
                    all_args.append(call_args[i])
                elif field in kw_dict:
                    all_args.append(kw_dict[field])
            call_args = all_args

    arity = len(call_args)
    arg_exprs = [term_to_ast_expr(a, var_context, eval_arith=False) for a in call_args]
    args_tuple = ast.Tuple(elts=arg_exprs, ctx=ast.Load())
    mark = _fresh(_MARK_PREFIX)

    naf_call = _call(
        _name("_naf_tabled"),
        ast.Constant(value=fname),
        ast.Constant(value=arity),
        args_tuple,
        _name(trail_name),
        _name("_table_store"),
    )
    return [
        _assign_mark(mark, trail_name),
        _if(naf_call, k_stmts),
        _undo_stmt(mark, trail_name),
    ]


# ── Reified ITE helpers (moved to .ite_reified) ──────────────────────────────
from .ite_reified import (  # noqa: E402,F401
    _is_reifiable,
    _compile_reified_ite, _compile_reified_ite_eq, _compile_reified_ite_fd,
    _compile_general_ite,
    _compile_reified_ite_trampoline, _compile_reified_ite_eq_trampoline,
    _compile_reified_ite_fd_trampoline,
    _compile_general_ite_trampoline,
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
                **_EXTRA_FUNCDEF,
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


def _compile_once(inner, db, var_context, trail_name, k_stmts):
    """Compile once(goal) — take first solution of inner goal, then continue."""
    once_gen = _fresh("_once_gen")
    inner_stmts = compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
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

    inner_stmts = compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
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

    inner_stmts = compile_goal(inner, db, var_context, trail_name, [_yield_none_stmt()])
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
        stmts = compile_goal(goal, db, var_context, trail_name, [_yield_none_stmt()])
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
    bound_stmts = compile_goal(goal, db, var_context, trail_name, k_stmts)

    # Compile goal as a thunk (closure) for the "deferred" branch
    deferred_stmts = compile_goal(goal, db, var_context, trail_name, [_yield_none_stmt()])
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
    deferred_stmts = compile_goal(goal, db, var_context, trail_name, [_yield_none_stmt()])
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
    inner_stmts = compile_goal(inner_goal, db, var_context, trail_name, [_yield_none_stmt()])
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
    inner_stmts = compile_goal(goal_arg, db, var_context, trail_name, [_yield_none_stmt()])
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

    # for loop over goal generator
    goal_loop = ast.For(
        target=_name("_", ast.Store()),
        iter=_call(_name(gen_name)),
        body=k_stmts or [ast.Pass()],
        orelse=[],
    )

    # Compile recovery as sub-generator (simple mode)
    recovery_stmts = compile_goal(recovery, db, var_context, trail_name, [_yield_none_stmt()])
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
        **_EXTRA_FUNCDEF,
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
    goal_stmts = compile_goal_trampoline(
        goal_arg, db, var_context, trail_name, k_stmts, self_name,
    )

    # Compile recovery as trampoline call
    recovery_stmts = compile_goal_trampoline(
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
        k = compile_goal(goal, db, body_vc, trail_name, k)

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
        **_EXTRA_FUNCDEF,
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


def compile_body(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction.

    The leaf continuation is ``yield None`` (one solution).
    Goals are processed right-to-left so each wraps the next as its k_stmts.

    Body-only Vars (variables that appear in the body but not the head) are
    pre-allocated via ``_preallocate_body_vars`` so that they are registered
    in ``var_context`` as named locals before right-to-left compilation begins.
    This prevents UnboundLocalError when an outer goal references a Var that
    would otherwise only be walrus-introduced inside a later (inner) goal.
    """
    alloc_stmts = _preallocate_body_vars(goals, var_context)
    k: list[ast.stmt] = [_yield_none_stmt()]
    for goal in reversed(goals):
        k = compile_goal(goal, db, var_context, trail_name, k)
    return alloc_stmts + k


def _make_body_compiler(db: Database) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a body_compiler callable bound to db."""
    def _body_compiler(clause: Clause, var_context: dict[int, str]) -> list[ast.stmt]:
        return compile_body(clause.body, db, var_context, _TRAIL_PARAM_NAME)
    return _body_compiler


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
    clauses: list,
    base_globals: dict,
) -> None:
    """Phase 10d: pre-scan clause bodies for statically-known call-site args.

    For each Call in a clause body where the callee is a locked predicate with
    ``_index_plans`` and one (or two) arguments are statically known literals
    or compound constructors, injects the matching bucket function into
    ``base_globals`` and records the mapping in
    ``_compile_context_local.bucket_ref_map`` /
    ``_compile_context_local.joint_bucket_ref_map`` so that
    :func:`_dispatch_call_trampoline` can emit a direct bucket reference.
    """

    brmap: dict = {}
    jbrmap: dict = {}

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

    _compile_context_local.bucket_ref_map = brmap
    _compile_context_local.joint_bucket_ref_map = jbrmap


def _dispatch_call_trampoline(
    fname: str,
    arity: int,
    arg_exprs: list[ast.expr],
    trail_name: str,
    self_name: str,
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
    brmap = getattr(_compile_context_local, "bucket_ref_map", {})
    jbrmap = getattr(_compile_context_local, "joint_bucket_ref_map", {})

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
    locked_keys = getattr(_compile_context_local, "locked_dispatch_keys", frozenset())
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
    """
    goal = deref(goal)

    if goal is True:
        return list(k_stmts)
    if goal is False:
        return []

    # PyThunk as a goal — evaluate for side effects, then continue.
    if isinstance(goal, PyThunk):
        call_expr = term_to_ast_expr(goal, var_context, eval_arith=False)
        return [ast.Expr(value=call_expr)] + list(k_stmts)

    match goal:

        # ── Deterministic goals — identical to simple mode ───────────────────
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

        case DoesNotUnify(left=l, right=r):
            # dif/2 semantics: post constraint, succeed if terms can stay different.
            l_expr = term_to_ast_expr(l, var_context, eval_arith=False)
            r_expr = term_to_ast_expr(r, var_context, eval_arith=False)
            return [
                _if(_call(_name("_dif"), l_expr, r_expr, _name(trail_name)), k_stmts),
            ]

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
            inner_k = compile_goal_trampoline(
                r, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
            return compile_goal_trampoline(
                l, db, var_context, trail_name, inner_k, self_name, parent_name
            )

        # ── Tuple-as-conjunction ─────────────────────────────────────────────
        case TupleLiteral(elements=elems) if elems:
            k = k_stmts
            for goal in reversed(elems):
                k = compile_goal_trampoline(
                    goal, db, var_context, trail_name, k, self_name, parent_name
                )
            return k

        # ── Disjunction ──────────────────────────────────────────────────────
        case Or(left=l, right=r):
            mark = _fresh(_MARK_PREFIX)
            left_stmts = compile_goal_trampoline(
                l, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
            right_stmts = compile_goal_trampoline(
                r, db, var_context, trail_name, k_stmts, self_name, parent_name
            )
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
                return _compile_tabled_naf_simple(inner, db, var_context, trail_name, k_stmts)

            naf_gen_fn = _fresh("_naf_gen_fn")
            naf_flag = _fresh("_naf")
            naf_sg = _fresh("_naf_sg")
            naf_g = _fresh("_naf_g")
            naf_v = _fresh("_naf_v")
            # Compile inner goal in trampoline mode with a solution yield
            inner_k = [_yield_step_stmt(_name("_naf_parent"), ast.Constant(None))]
            inner_stmts = compile_goal_trampoline(
                inner, db, var_context, trail_name, inner_k,
                self_name="_naf_self", parent_name="_naf_parent",
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
                return _compile_reified_ite_trampoline(
                    test, then, else_, db, var_context, trail_name,
                    k_stmts, self_name, parent_name,
                )
            else:
                return _compile_general_ite_trampoline(
                    test, then, else_, db, var_context, trail_name,
                    k_stmts, self_name, parent_name,
                )

        # ── Membership / enumeration (Python for-loop, safe) ─────────────────
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
            return _compile_catch_trampoline(
                goal_arg, catcher, recovery, db, var_context,
                trail_name, k_stmts, self_name,
            )

        # ── catch_error(Goal, Error) — catch any exception, bind Error ──────────
        case Call(func=LoadName(name="catch_error"), args=[goal_arg, error_var], kwargs=[]):
            return _compile_catch_trampoline(
                goal_arg, error_var, True, db, var_context,
                trail_name, k_stmts, self_name, always_catch=True,
            )

        # ── catch_recover(Goal, Error, Recovery) — catch, bind, recover ───
        case Call(func=LoadName(name="catch_recover"), args=[goal_arg, error_var, recovery], kwargs=[]):
            return _compile_catch_trampoline(
                goal_arg, error_var, recovery, db, var_context,
                trail_name, k_stmts, self_name, always_catch=True,
            )

        # ── halt/0, halt/1 — exit ────────────────────────────────────────
        case Call(func=LoadName(name="halt"), args=[], kwargs=[]):
            return [ast.Raise(exc=_call(_name("SystemExit"), ast.Constant(0)))]

        case Call(func=LoadName(name="halt"), args=[code_arg], kwargs=[]):
            code_expr = term_to_ast_expr(code_arg, var_context, eval_arith=True)
            return [ast.Raise(exc=_call(_name("SystemExit"), code_expr))]

        # ── once(goal) — commit to first solution ──────────────────────────
        case Call(func=LoadName(name="once"), args=[inner], kwargs=[]):
            # Inner compiles in simple mode (sub-generator), same as NAF.
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

        # ── Stack-safe predicate call ─────────────────────────────────────────
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            return _compile_predicate_call_trampoline(
                fname, call_args, call_kwargs, db, var_context,
                trail_name, k_stmts, self_name,
            )

        # ── Qualified predicate call (mod.Pred(X_)) ──────────────────────────
        case Call(func=LoadAttr() as attr, args=call_args, kwargs=call_kwargs):
            fname = _dotted_name_from_loadattr(attr)
            return _compile_predicate_call_trampoline(
                fname, call_args, call_kwargs, db, var_context,
                trail_name, k_stmts, self_name,
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
    fname: str,
    call_args: list,
    call_kwargs: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    k_stmts: list[ast.stmt],
    self_name: str,
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
    gen_name = _fresh("_gen")
    status_name = _fresh("_st")

    call_expr = _dispatch_call_trampoline(fname, arity, arg_exprs, trail_name, self_name)

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
    return lambda_defs + [gen_assign, first_step, loop]



# ── compile_body_trampoline ────────────────────────────────────────────────────


def compile_body_trampoline(
    goals: list,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    parent_name: str = _TRAMP_PARENT_NAME,
    self_name: str = _THIS_GEN_NAME,
) -> list[ast.stmt]:
    """Compile a flat list of goals as a conjunction using the Step protocol.

    The leaf continuation is ``yield Step(parent, None)`` — one solution
    surfaced to the calling generator.

    Builds right-to-left: each goal wraps the next as its k_stmts, ending
    with the leaf.  Body-only Vars are pre-allocated (same fix as compile_body).
    """
    alloc_stmts = _preallocate_body_vars(goals, var_context)
    k: list[ast.stmt] = [_yield_step_stmt(_name(parent_name), ast.Constant(None))]
    for goal in reversed(goals):
        k = compile_goal_trampoline(goal, db, var_context, trail_name, k, self_name, parent_name)
    return alloc_stmts + k


# ── Destructive-reuse optimization ───────────────────────────────────────────
#
# When a builtin like append/3, dict_put/4, or set_union/3 consumes a
# container that is provably dead after the call, we can dispatch to a
# "destructive-reuse" variant that mutates the container in-place (guarded
# by a runtime sys.getrefcount check for safety).
#
# Eligibility criteria (compile-time):
#   1. Goal is a Call to one of the supported builtins.
#   2. The "source" argument is a Var (not a literal or compound term).
#   3. The source Var does NOT appear in the clause head (it wasn't passed
#      in by the caller, so no external alias exists).
#   4. The source Var is dead after the goal — it does not appear in any
#      subsequent body goal.
#   5. All preceding body goals are deterministic (no choice points that
#      could backtrack through the mutation).

# Maps builtin (functor, arity) → index of the "source" arg to try to reuse.
_DR_CANDIDATES: dict[tuple[str, int], int] = {
    ("append", 3): 0,       # append(Source, Extra, Result)
    ("dict_put", 4): 2,     # dict_put(Key, Value, Source, Result)
    ("set_union", 3): 0,    # set_union(Source, S2, Result)
}


def _head_aliased_var_ids(body: list, head_var_ids: set[int]) -> set[int]:
    """Return body-only var IDs that are transitively aliased to head vars.

    Scans deterministic prefix goals for ``Unify(left=A, right=B)`` where one
    side is (or is aliased to) a head var.  The other side is then also
    considered aliased.  Handles transitive chains like::

        Temp = In, Temp2 = Temp   →  Temp and Temp2 both alias In
    """
    aliased: set[int] = set(head_var_ids)
    changed = True
    # Collect all unify pairs first.
    pairs: list[tuple[int, int]] = []
    for goal in body:
        goal = deref(goal)
        match goal:
            case Unify(left=l, right=r):
                l = deref(l)
                r = deref(r)
                if is_var(l) and is_var(r):
                    pairs.append((l._id, r._id))
            case And():
                # Flatten And chains for unify scanning.
                _collect_unify_pairs_from_and(goal, pairs)
            case _:
                pass
    # Transitive closure.
    while changed:
        changed = False
        for a, b in pairs:
            if a in aliased and b not in aliased:
                aliased.add(b)
                changed = True
            elif b in aliased and a not in aliased:
                aliased.add(a)
                changed = True
    return aliased


def _collect_unify_pairs_from_and(goal: Any, pairs: list[tuple[int, int]]) -> None:
    """Recursively extract Var-Var Unify pairs from And nodes."""
    goal = deref(goal)
    match goal:
        case Unify(left=l, right=r):
            l = deref(l)
            r = deref(r)
            if is_var(l) and is_var(r):
                pairs.append((l._id, r._id))
        case And(left=left, right=right):
            _collect_unify_pairs_from_and(left, pairs)
            _collect_unify_pairs_from_and(right, pairs)


def _flatten_and_goals(goals: list) -> list:
    """Flatten nested ``And(a, And(b, c))`` into ``[a, b, c]``.

    And nodes in the body are semantically conjunctions — equivalent to a
    flat sequence of goals.  Flattening exposes the individual goals to the
    liveness analysis so that eligible calls inside And nodes can be detected.
    """
    flat: list = []
    for goal in goals:
        goal = deref(goal)
        _flatten_and_single(goal, flat)
    return flat


def _flatten_and_single(goal: Any, out: list) -> None:
    """Recursively flatten a single goal into *out*."""
    match goal:
        case And(left=l, right=r):
            _flatten_and_single(deref(l), out)
            _flatten_and_single(deref(r), out)
        case _:
            out.append(goal)


def _find_destructive_reuse_goals(clause: Clause) -> set[int]:
    """Return indices of body goals eligible for destructive-reuse dispatch.

    Only returns indices where all five compile-time criteria are satisfied.
    Analyses operate on a flattened copy of the body (And nodes expanded)
    so that eligible calls inside conjunctions are detected.
    """
    body = clause.body
    if not body:
        return set()

    # Flatten And conjunctions so individual goals are visible.
    flat_body = _flatten_and_goals(body)

    # Collect var IDs that appear in the clause head.
    head_var_ids: set[int] = set()
    _collect_var_ids(clause.head, head_var_ids)

    # Criterion 3 (extended): also exclude body vars aliased to head vars
    # through Unify chains (e.g. Temp = In where In is a head var).
    aliased_ids = _head_aliased_var_ids(flat_body, head_var_ids)

    eligible: set[int] = set()

    for i, goal in enumerate(flat_body):
        goal = deref(goal)
        # Criterion 1: must be a Call to a supported builtin.
        if not isinstance(goal, Call):
            continue
        func = goal.func
        if not isinstance(func, LoadName):
            continue
        dr_info = _DR_CANDIDATES.get((func.name, len(goal.args)))
        if dr_info is None:
            continue
        source_idx = dr_info

        # Criterion 2: source argument must be a Var.
        source_arg = deref(goal.args[source_idx])
        if not is_var(source_arg):
            continue
        source_id = source_arg._id

        # Criterion 3: source Var must NOT be (or alias) a head variable.
        if source_id in aliased_ids:
            continue

        # Criterion 4: source Var must be dead after this goal.
        live_after: set[int] = set()
        for subsequent_goal in flat_body[i + 1:]:
            _collect_var_ids(subsequent_goal, live_after)
        if source_id in live_after:
            continue

        # Criterion 5: all preceding goals must be deterministic.
        if not all(_is_deterministic_goal(flat_body[j]) for j in range(i)):
            continue

        eligible.add(i)

    return eligible


def _apply_destructive_reuse(goals: list, eligible: set[int]) -> list:
    """Return a copy of *goals* with eligible calls rewritten to use DR variants.

    Rewrites the Call's LoadName to a private name that the compiler resolves
    to the destructive-reuse dispatch function injected into base_globals.
    """
    if not eligible:
        return goals

    _DR_NAME_MAP: dict[str, str] = {
        "append": "_dr_append__3",
        "dict_put": "_dr_dict_put__4",
        "set_union": "_dr_set_union__3",
    }

    new_goals = list(goals)
    for i in eligible:
        goal = deref(new_goals[i])
        fname = goal.func.name
        dr_name = _DR_NAME_MAP[fname]
        new_goals[i] = Call(
            func=LoadName(name=dr_name),
            args=goal.args,
            kwargs=goal.kwargs,
        )
    return new_goals


def _make_body_compiler_trampoline(
    db: Database,
) -> Callable[[Clause, dict[int, str]], list[ast.stmt]]:
    """Return a trampoline body_compiler callable bound to db."""
    def _body_compiler(clause: Clause, var_context: dict[int, str]) -> list[ast.stmt]:
        # Destructive-reuse optimisation: flatten And conjunctions, then
        # rewrite eligible goals before compiling.  Flattening is safe
        # because And(a, b) compiles identically to sequential [a, b].
        flat_body = _flatten_and_goals(clause.body)
        eligible = _find_destructive_reuse_goals(clause)
        goals = _apply_destructive_reuse(flat_body, eligible)
        return compile_body_trampoline(goals, db, var_context, _TRAIL_PARAM_NAME)
    return _body_compiler


# ── Phase 5: deep structural indexing helpers ──────────────────────────────────


def _get_head_arg(clause: Clause, pos: int) -> Any:
    """Return the argument at position *pos* from the clause head (or None)."""
    head = clause.head
    if isinstance(head, Compound):
        return head.args[pos] if pos < len(head.args) else None
    if is_term_instance(head):
        fields = list(term_field_names(head))
        return getattr(head, fields[pos]) if pos < len(fields) else None
    return None


def _lift_clause_at_pos(clause: Clause, pos: int) -> Clause:
    """Phase 8: lift the body Unify for head position *pos* into the head.

    in_ bucket compilation contexts the indexed argument is already guaranteed
    ground by the dispatch layer.  Any leading body ``Unify(Var_at_pos, val)``
    is therefore redundant and can be absorbed into the head, letting
    ``head_to_match_pattern`` emit a ``MatchValue``/``MatchClass`` pattern
    rather than a wildcard capture.  This eliminates one ``trail.mark()`` +
    ``unify(...)`` + ``trail.undo()`` triple per clause per invocation.

    The transformation is a no-op when:
    - the head arg at *pos* is already a concrete term (not a Var), or
    - no matching ``Unify`` is found in the body's clean prefix (the
      contiguous run of ``Unify`` goals before the first non-``Unify`` goal).

    Only called from the indexed bucket path — the fallback function always
    uses the original unlifted clauses.
    """
    head = clause.head
    # Extract the head arg at pos
    if isinstance(head, Compound):
        if pos >= len(head.args):
            return clause
        head_arg = deref(head.args[pos])
    elif is_term_instance(head):
        fields = list(term_field_names(head))
        if pos >= len(fields):
            return clause
        head_arg = deref(getattr(head, fields[pos]))
    else:
        return clause

    # Only lift when the head arg is an unbound Var
    if not is_var(head_arg):
        return clause
    vid = head_arg._id

    # Scan the body clean prefix for Unify(Var_vid, term) or Unify(term, Var_vid)
    # Stop at the first non-Unify goal (that is the clean-prefix boundary).
    unify_idx = None
    lift_term = None
    for i, goal in enumerate(clause.body):
        if not isinstance(goal, Unify):
            break  # end of clean prefix
        left_d = deref(goal.left)
        right_d = deref(goal.right)
        if is_var(left_d) and left_d._id == vid and not is_var(right_d):
            unify_idx = i
            lift_term = goal.right   # use original (not deref'd) for nested Vars
            break
        if is_var(right_d) and right_d._id == vid and not is_var(left_d):
            unify_idx = i
            lift_term = goal.left
            break
        # Other Unify for a different var — keep scanning

    if unify_idx is None:
        return clause  # no liftable unification found

    # Rebuild head with lift_term at pos
    if isinstance(head, Compound):
        new_args = list(head.args)
        new_args[pos] = lift_term
        new_head = Compound(head.functor, tuple(new_args))
    else:  # is_term_instance
        fields = list(term_field_names(head))
        new_kwargs = {f: getattr(head, f) for f in fields}
        new_kwargs[fields[pos]] = lift_term
        new_head = type(head)(**new_kwargs)

    # Remove the matched Unify from the body
    new_body = clause.body[:unify_idx] + clause.body[unify_idx + 1:]
    return Clause(head=new_head, body=new_body)


def _classify_list_key(arg: Any) -> str:
    """Classify a head argument as ``"nil"``, ``"cons"``, ``"var"``, or ``"other"``.

    - ``"nil"``  — argument is the empty list ``[]``
    - ``"cons"`` — argument is a non-empty Python list (may contain Vars)
    - ``"var"``  — argument is an unbound Var (wildcard, matches anything)
    - ``"other"``— anything else (integer, string, Compound, …)
    """
    arg = deref(arg)
    if is_var(arg):
        return "var"
    if isinstance(arg, list):
        return "nil" if not arg else "cons"
    return "other"


def _find_list_dispatch_pos(clauses: list[Clause], arity: int) -> int | None:
    """Find the best argument position for list structural dispatch.

    Returns the position index when ALL clauses have nil/cons/var heads at that
    position (no scalars or compound terms) AND both ``"nil"`` and ``"cons"``
    appear in the clause set — guaranteeing the dispatch saves work.

    Returns ``None`` if no suitable position is found.
    """
    if arity == 0 or len(clauses) < 2:
        return None
    best_pos = None
    best_score = 0
    for pos in range(arity):
        keys = [_classify_list_key(_get_head_arg(c, pos)) for c in clauses]
        if "other" in keys:
            continue  # mixed list + non-list types at this position
        list_keys = {k for k in keys if k != "var"}
        score = len(list_keys)  # 0 (all var), 1 (only nil or only cons), or 2
        if score >= 2 and score > best_score:
            best_pos = pos
            best_score = score
    return best_pos


def _build_list_dispatch_guard(
    clauses: list[Clause],
    dispatch_pos: int,
    arity: int,
    subject: ast.expr,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
) -> list[ast.stmt]:
    """Build the isinstance/is_var structural dispatch guard for list predicates.

    Generates:

        if isinstance(_d_pos, list):
            if not _d_pos:          # nil branch
                <nil_clauses + var_clauses>
            else:                   # cons branch
                <cons_clauses + var_clauses>
        elif is_var(_d_pos):        # unbound — try all clauses
            <all clauses>
        # non-list, non-var → falls through to yield _DONE

    ``var_clauses`` (wildcard heads) appear in both the nil and cons branches
    because a wildcard matches any list.  They also appear in the is_var
    fallback because the variable might be bound to any list at call time.
    """
    nil_clauses: list[Clause] = []
    cons_clauses: list[Clause] = []
    var_clauses: list[Clause] = []
    for c in clauses:
        key = _classify_list_key(_get_head_arg(c, dispatch_pos))
        if key == "nil":
            nil_clauses.append(c)
        elif key == "cons":
            cons_clauses.append(c)
        else:  # "var"
            var_clauses.append(c)

    def _match_stmts(subset: list[Clause]) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []
        for clause in subset:
            vc: dict[int, str] = {}
            _head_arg_patterns(clause.head, vc, arity)
            body_stmts = body_compiler(clause, vc)
            case_arm = compile_head_to_match_case(
                head=clause.head,
                body_stmts=body_stmts,
                var_context=vc,
                arity=arity,
            )
            stmts.append(ast.Match(subject=subject, cases=[case_arm]))
        return stmts or [ast.Pass()]

    nil_body = _match_stmts(nil_clauses + var_clauses)
    cons_body = _match_stmts(cons_clauses + var_clauses)
    var_body = _match_stmts(nil_clauses + cons_clauses + var_clauses)

    deref_name = f"_d{dispatch_pos}"

    # if not _d_pos: <nil> else: <cons>
    nil_vs_cons = ast.If(
        test=ast.UnaryOp(op=ast.Not(), operand=_name(deref_name)),
        body=nil_body,
        orelse=cons_body,
    )

    # elif is_var(_d_pos): <all>
    is_var_branch = ast.If(
        test=_call(_name("is_var"), _name(deref_name)),
        body=var_body,
        orelse=[],
    )

    # if isinstance(_d_pos, (list, str)): <nil_vs_cons> elif is_var(_d_pos): <all>
    # Strings are treated as lists of characters for head pattern matching.
    _list_or_str = ast.Tuple(
        elts=[_name("list"), _name("str")], ctx=ast.Load(),
    )
    return [
        ast.If(
            test=_call(_name("isinstance"), _name(deref_name), _list_or_str),
            body=[nil_vs_cons],
            orelse=[is_var_branch],
        )
    ]


# ── Tail Recursion Optimization (TRO) ─────────────────────────────────────────
#
# when the last goal in a clause body is a self-recursive Call preceded only by
# deterministic goals (at most one solution, no StepGenerator), the recursive
# call can be replaced by argument reassignment + loop restart.  This avoids
# allocating a new StepGenerator + generator object per recursion depth.
#
# The generated pattern wraps the clause match arms in ``while True:`` and uses
# a ``_tro`` flag + ``continue`` to restart when a TRO-eligible clause fires.


def _is_deterministic_goal(goal: Any) -> bool:
    """Return True if *goal* compiles to at most one solution (no StepGenerator).

    Deterministic goals produce zero or one continuations and never create a
    ``StepGenerator`` child.  They are safe to precede a TRO tail call.
    """
    goal = deref(goal)

    if goal is True or goal is False:
        return True

    # PyThunk as goal (side effect) is deterministic.
    if isinstance(goal, PyThunk):
        return True

    match goal:
        # Unification / arithmetic / comparison — always deterministic
        case Unify() | Evaluate() | DoesNotUnify():
            return True
        case ArithEq() | ArithNeq():
            return True
        case StructuralEq() | StructuralNeq():
            return True
        case Lt() | LtE() | Gt() | GtE():
            return True
        case in_() | NotIn():
            return True
        # NAF — deterministic (succeeds or fails once)
        case Not():
            return True
        # Conjunction — deterministic if both sides are
        case And(left=l, right=r):
            return _is_deterministic_goal(l) and _is_deterministic_goal(r)
        # IfExpr — committed choice, one branch
        case IfExpr():
            return True
        # once/findall/bagof/setof — always produce exactly one result
        case Call(func=LoadName(name=name)) if name in (
            "once", "findall", "bagof", "setof",
            "throw", "halt",
        ):
            return True
        # Known-deterministic builtins: at most one solution, no backtracking.
        case Call(func=LoadName(name=name), args=args) if (name, len(args)) in _DETERMINISTIC_BUILTINS:
            return True
        case _:
            return False


# Builtins known to produce at most one solution (semidet / det).
_DETERMINISTIC_BUILTINS: frozenset[tuple[str, int]] = frozenset({
    # list builtins (lists.py)
    ("length", 2), ("last", 2), ("reverse", 2), ("flatten", 2),
    ("msort", 2), ("sort", 2), ("sum_list", 2), ("max_list", 2),
    ("min_list", 2), ("take", 3), ("drop", 3), ("split_at", 4),
    ("zip_", 3), ("replicate", 3),
    ("subtract", 3), ("intersection", 3), ("union", 3),
    ("list_to_set", 2),
    # dict builtins (dict_set.py)
    ("is_dict", 1), ("dict_size", 2), ("dict_keys", 2), ("dict_values", 2),
    ("dict_pairs", 2), ("dict_get", 3), ("dict_put", 4),
    ("dict_put_pairs", 3), ("dict_remove", 3), ("dict_merge", 3),
    # set builtins (dict_set.py)
    ("is_set", 1), ("set_size", 2), ("set_list", 2),
    ("set_union", 3), ("set_intersection", 3), ("set_subtract", 3),
    ("set_sym_diff", 3), ("set_add", 3), ("set_remove", 3),
    # type checks / inspection
    ("atom", 1), ("number", 1), ("integer", 1), ("float_", 1),
    ("is_list", 1), ("callable", 1), ("ground", 1),
    ("atom_length", 2), ("atom_chars", 2), ("atom_codes", 2),
    ("char_code", 2), ("number_chars", 2), ("number_codes", 2),
    ("atom_string", 2), ("term_string", 2),
    ("succ", 2), ("plus", 3),
    ("copy_term", 2),
    # string builtins
    ("atom_concat", 3), ("sub_atom", 5),
    ("upcase_atom", 2), ("downcase_atom", 2),
})


def _detect_tro_clause(functor: str, arity: int, clause: Clause) -> bool:
    """Return True if *clause* has a deterministic-prefix tail-recursive call.

    The last goal must be a ``Call`` to the same ``functor`` with ``arity``
    positional arguments, all preceding goals must be deterministic, and
    the tail call arguments must be TRO-safe.

    A tail call argument is TRO-safe when it will be a concrete value (not an
    unbound Var referencing a head-pattern variable) at the point of capture.
    This is true for:

    - Constants (int, str, list literals, etc.)
    - Variables that were bound by an ``Evaluate`` in a prefix goal
    - Variables that appear at the **same position** in both the head and the
      tail call (passthrough — the caller's original arg flows through
      unchanged).

    Variables introduced by head pattern decomposition (e.g. TAIL from
    ``[HEAD, *TAIL]``) are NOT safe because the corresponding head argument
    might be an unbound output Var from the caller.  After ``trail.undo``,
    the captured value would be an internal Var disconnected from the caller.
    """
    if not clause.body:
        return False

    last_goal = deref(clause.body[-1])
    match last_goal:
        case Call(func=LoadName(name=fname), args=call_args, kwargs=call_kwargs):
            if fname != functor:
                return False
            if len(call_args) + len(call_kwargs) != arity:
                return False
        case _:
            return False

    # All preceding goals must be deterministic.
    if not all(_is_deterministic_goal(g) for g in clause.body[:-1]):
        return False

    # Reject tail call args that contain StarUnpack — TRO code generation
    # cannot construct list-with-splat at runtime.
    if any(_contains_star_unpack(a) for a in call_args):
        return False

    # Reject clauses whose head list patterns contain non-variable constants.
    # The _head_list_unify_input call for such patterns creates caller-visible
    # bindings (e.g., unifying a query Var with a constant in the pattern).
    # TRO's trail.undo would undo these bindings prematurely.
    # This is common in specialized MI predicates whose heads embed
    # object-program clause heads like [["sum", 0, 0], *GOALS].
    if _head_has_unifying_list_pattern(clause.head):
        return False

    # Safety check: every variable in the tail call must be "grounded" by
    # the prefix goals, be a passthrough from the head, or come from head
    # list decomposition with at least one deterministic prefix goal
    # (implying the input is likely ground).
    if not clause.body[:-1]:
        return _tro_args_safe(clause.head, [], call_args, arity)[0]
    return _tro_args_safe(clause.head, clause.body[:-1], call_args, arity,
                          allow_head_vars=True)[0]


def _get_tro_check_indices(functor: str, arity: int, clause: Clause) -> frozenset[int]:
    """Return the set of tail-call arg positions needing runtime ground-check.

    Only meaningful for TRO-eligible clauses (call after ``_detect_tro_clause``
    returns True).
    """
    last_goal = deref(clause.body[-1])
    call_args = last_goal.args
    if not clause.body[:-1]:
        return frozenset()  # no prefix → no allow_head_vars → no checks needed
    _, check = _tro_args_safe(clause.head, clause.body[:-1], call_args, arity,
                              allow_head_vars=True)
    return check


def _tro_args_safe(
    head: Any,
    prefix_goals: list,
    tail_args: list,
    arity: int,
    allow_head_vars: bool = False,
) -> tuple[bool, frozenset[int]]:
    """Return ``(safe, check_indices)`` for TRO arg safety.

    *safe*: True if all tail call arguments are TRO-safe.
    *check_indices*: arg positions accepted via ``allow_head_vars`` that
    should be runtime-checked with ``is_var()`` for provable correctness.

    Safe categories:
    1. Constants (not a Var)
    2. Variables bound by ``Evaluate`` or ``Unify`` in prefix goals
    3. Variables that are passthrough — same Var appears at the same position
       in the head (the raw ``arg_i`` value, not a decomposed component)
    4. (when *allow_head_vars* is True) Any head variable — including those
       from list/compound decomposition.  These are safe when the head arg
       was ground, which is checked at runtime via ``is_var()`` on the
       captured value.  The positions are returned in *check_indices*.
    """
    # Collect Var IDs that are bound by Evaluate/Unify LHS in prefix goals.
    bound_var_ids: set[int] = set()
    for g in prefix_goals:
        g = deref(g)
        match g:
            case Evaluate(left=lhs):
                if is_var(lhs):
                    bound_var_ids.add(lhs._id)
            case Unify(left=lhs, right=rhs):
                if is_var(lhs):
                    bound_var_ids.add(lhs._id)
                if is_var(rhs):
                    bound_var_ids.add(rhs._id)
            case And(left=l, right=r):
                _collect_bound_vars(l, bound_var_ids)
                _collect_bound_vars(r, bound_var_ids)

    # Collect head arg Var IDs at each position (direct, not decomposed).
    head_passthrough_ids: set[int] = set()
    # Also collect ALL Var IDs that appear anywhere in the head.
    all_head_var_ids: set[int] = set()
    if is_term_instance(head):
        fields = list(term_field_names(head))
        for i, fname in enumerate(fields):
            head_arg = getattr(head, fname)
            _collect_var_ids(head_arg, all_head_var_ids)
            head_arg = deref(head_arg)
            if is_var(head_arg) and i < len(tail_args):
                tail_arg = deref(tail_args[i])
                if is_var(tail_arg) and tail_arg._id == head_arg._id:
                    head_passthrough_ids.add(head_arg._id)
    elif isinstance(head, Compound):
        for i, head_arg in enumerate(head.args):
            _collect_var_ids(head_arg, all_head_var_ids)
            head_arg = deref(head_arg)
            if is_var(head_arg) and i < len(tail_args):
                tail_arg = deref(tail_args[i])
                if is_var(tail_arg) and tail_arg._id == head_arg._id:
                    head_passthrough_ids.add(head_arg._id)

    # Check each tail call argument.  Collect ALL Var IDs within each arg
    # (not just top-level), since lists/compounds may embed unbound Vars.
    # Track which arg positions are accepted via allow_head_vars (need runtime check).
    _check_positions: set[int] = set()
    for arg_idx, arg in enumerate(tail_args):
        arg_var_ids: set[int] = set()
        _collect_var_ids(arg, arg_var_ids)
        for vid in arg_var_ids:
            if vid in bound_var_ids:
                continue  # bound by prefix goal — safe
            if vid in head_passthrough_ids:
                continue  # passthrough from head — safe
            if allow_head_vars and vid in all_head_var_ids:
                _check_positions.add(arg_idx)  # needs runtime ground-check
                continue
            return (False, frozenset())
    return (True, frozenset(_check_positions))


def _head_has_unifying_list_pattern(head: Any) -> bool:
    """Return True if any head field is a list containing non-variable constants.

    Such patterns cause ``_head_list_unify_input`` to create bindings on the
    caller's variables (by unifying the constant-bearing pattern with the input).
    TRO's ``trail.undo`` would undo these bindings prematurely, breaking the
    caller's view of the solution.

    Example: head field ``[["sum", 0, 0], StarUnpack(GOALS)]`` has the
    constant list ``["sum", 0, 0]`` — TRO is unsafe.
    """
    if is_term_instance(head):
        for fname in term_field_names(head):
            val = getattr(head, fname)
            if isinstance(val, list) and _list_has_nonvar_constant(val):
                return True
    return False


def _list_has_nonvar_constant(lst: list) -> bool:
    """Check if a list contains non-variable constants (not just Vars and StarUnpack)."""
    for elem in lst:
        if isinstance(elem, StarUnpack):
            continue
        elem = deref(elem)
        if is_var(elem):
            continue
        # This element is a constant or a list — it would require
        # unification that could bind caller variables.
        return True
    return False


def _contains_star_unpack(term: Any) -> bool:
    """Return True if *term* contains a StarUnpack node anywhere."""
    if isinstance(term, StarUnpack):
        return True
    if isinstance(term, (list, tuple)):
        return any(_contains_star_unpack(item) for item in term)
    return False


# moved to ._vars
from ._vars import _collect_var_ids, _collect_bound_vars  # noqa: E402,F401


def _compile_tro_tail(
    tail_call: Call,
    arity: int,
    var_context: dict[int, str],
    db: Database,
    trail_name: str,
    tro_mode: str = "loop",
    check_indices: frozenset[int] | None = None,
    self_name: str = _THIS_GEN_NAME,
    parent_name: str = _TRAMP_PARENT_NAME,
) -> list[ast.stmt]:
    """Compile TRO tail-call: snapshot new args, set TRO flag/state.

    The caller (``compile_head_to_match_case``) wraps this in
    ``try/finally: trail.undo(_mark)`` so trail cleanup is automatic.

    *tro_mode*:

    - ``"loop"`` (default): set local ``_tro = True``.  The enclosing
      ``while True`` loop in the funcdef will reassign args and ``continue``.
    - ``"signal"``: set shared ``_tro_state[0] = True`` and store new arg
      values in ``_tro_state[1..N]``.  The dispatch closure will check
      ``_tro_state`` after the bucket generator finishes and re-dispatch.

    *check_indices*: if not None, a set of arg positions that need a runtime
    ``is_var()`` check.  when any checked arg is an unbound Var, the TRO
    flag is NOT set and execution falls back to a normal ``StepGenerator``
    call (emitted inline).
    """

    call_args = list(tail_call.args)
    call_kwargs = tail_call.kwargs or []
    n_pos = len(call_args)

    ordered_args: list = list(call_args)
    if call_kwargs:
        fname = tail_call.func.name
        sig = db.signature_for(fname, arity)
        if sig is None:
            raise RuntimeError(
                f"TRO: no signature for {fname}/{arity}"
            )
        kw_dict = {kw.name: kw.value for kw in call_kwargs if isinstance(kw, KWNode)}
        for param_name in sig[n_pos:]:
            ordered_args.append(kw_dict[param_name])

    # Hoist any lambda arguments (reuse existing helper).
    ordered_args, lambda_defs = _hoist_lambda_args(
        ordered_args, var_context, db, trail_name,
    )

    stmts: list[ast.stmt] = list(lambda_defs)

    # Snapshot each new arg value via deref before trail.undo runs.
    for i, arg in enumerate(ordered_args):
        arg_expr = term_to_ast_expr(arg, var_context, eval_arith=False)
        tro_name = f"_tro_arg{i}"
        stmts.append(_assign(tro_name, _call(_name("deref"), arg_expr)))

    # Build the TRO-set statements.
    if tro_mode == "signal":
        # Signal mode: set _tro_state[0] = True, _tro_state[i+1] = _tro_arg_i
        tro_set_stmts: list[ast.stmt] = [
            ast.Assign(
                targets=[ast.Subscript(
                    value=_name("_tro_state"), slice=ast.Constant(0), ctx=ast.Store(),
                )],
                value=ast.Constant(True),
                lineno=0, col_offset=0,
            ),
        ]
        for i in range(arity):
            tro_set_stmts.append(ast.Assign(
                targets=[ast.Subscript(
                    value=_name("_tro_state"), slice=ast.Constant(i + 1), ctx=ast.Store(),
                )],
                value=_name(f"_tro_arg{i}"),
                lineno=0, col_offset=0,
            ))
    else:
        # Loop mode: set _tro = True
        tro_set_stmts = [_assign("_tro", ast.Constant(True))]

    # Runtime ground-check: if any checked arg is a Var, fall back to StepGenerator.
    if check_indices:
        checks = [
            ast.UnaryOp(op=ast.Not(), operand=_call(_name("is_var"), _name(f"_tro_arg{i}")))
            for i in sorted(check_indices)
        ]
        if len(checks) == 1:
            ground_cond = checks[0]
        else:
            ground_cond = ast.BoolOp(op=ast.And(), values=checks)

        # Fallback: normal StepGenerator call with captured _tro_arg values.
        arg_exprs = [_name(f"_tro_arg{i}") for i in range(arity)]
        fname = tail_call.func.name
        fallback_stmts = _compile_predicate_call_trampoline(
            fname, [None] * arity, [], db, var_context, trail_name,
            [_yield_step_stmt(_name(parent_name), ast.Constant(None))],
            self_name,
        )
        # Patch the arg expressions in the StepGenerator call to use _tro_arg values.
        # The simplest approach: build the call directly.
        call_expr = _dispatch_call_trampoline(fname, arity, arg_exprs, trail_name, self_name)
        gen_name = _fresh("_gen")
        status_name = _fresh("_st")
        gen_assign = _assign(gen_name, call_expr)
        first_step = _assign_yield_step(status_name, _name(gen_name), ast.Constant(None))
        loop_body = [
            _yield_step_stmt(_name(parent_name), ast.Constant(None)),
            _assign_yield_step(status_name, _name(gen_name), ast.Constant(None)),
        ]
        fallback_loop = ast.While(
            test=ast.Compare(
                left=_name(status_name),
                ops=[ast.IsNot()],
                comparators=[_name("_DONE")],
            ),
            body=loop_body,
            orelse=[],
        )
        fallback_stmts = [gen_assign, first_step, fallback_loop]

        stmts.append(ast.If(
            test=ground_cond,
            body=tro_set_stmts,
            orelse=fallback_stmts,
        ))
    else:
        stmts.extend(tro_set_stmts)

    return stmts


# ── compile_predicate_trampoline ───────────────────────────────────────────────


def _build_predicate_trampoline_funcdef(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
    emit_done: bool = True,
    tro_indices: frozenset[int] | None = None,
    skip_trail: bool = False,
) -> ast.FunctionDef:
    """Build the ``ast.FunctionDef`` for a trampoline-protocol compiled predicate.

    Returns the fixed-up FunctionDef without executing it.  Used by both
    ``compile_predicate_trampoline`` and ``compile_predicate_trampoline_ast``.

    when *emit_done* is False the trailing ``yield (parent, _DONE)`` is
    omitted — used for indexed-dispatch sub-functions that are consumed via
    ``yield from`` by an outer wrapper which emits its own DONE.

    when *tro_indices* is non-empty, tail-recursion optimization is applied.
    Two modes:

    - ``emit_done=True`` (or non-bucket): ``while True`` loop with ``continue``.
    - ``emit_done=False`` (bucket): signal mode — set ``_tro_state`` and return.
      The dispatch closure checks ``_tro_state`` after ``yield from`` completes.
    """
    use_tro = bool(tro_indices)
    # Bucket functions use "signal" mode (set _tro_state, return).
    # Full functions use "loop" mode (while True + continue).
    tro_mode = "signal" if (use_tro and not emit_done) else "loop"
    arg_names = [f"arg{i}" for i in range(arity)]
    params = [_THIS_GEN_NAME, _TRAMP_PARENT_NAME] + arg_names + [_TRAIL_PARAM_NAME]

    # Statements that go inside the TRO while-loop (or directly in the func body).
    loop_stmts: list[ast.stmt] = []

    if clauses and arity > 0:
        # Deref each argument once into a local before the clause match arms.
        deref_names = [f"_d{i}" for i in range(arity)]
        for i, arg in enumerate(arg_names):
            loop_stmts.append(_assign(deref_names[i], _call(_name("deref"), _name(arg))))
        subject = ast.Tuple(elts=[_name(n) for n in deref_names], ctx=ast.Load())
    else:
        subject = ast.Tuple(
            elts=[_call(_name("deref"), _name(n)) for n in arg_names],
            ctx=ast.Load(),
        )

    if use_tro and tro_mode == "loop":
        # Initialise _tro flag at the top of each iteration.
        loop_stmts.append(_assign("_tro", ast.Constant(False)))

    # Phase 5: structural dispatch for list-discriminating predicates.
    dispatch_pos = (
        _find_list_dispatch_pos(clauses, arity) if (clauses and arity > 0) else None
    )
    if dispatch_pos is not None:
        if use_tro:
            # TRO-aware body compiler: uses _compile_tro_body for eligible clauses.
            _tro_clause_set = {id(clauses[i]) for i in tro_indices}
            _orig_bc = body_compiler
            _tro_m = tro_mode
            def _tro_list_body_compiler(clause, var_context,
                                        _tset=_tro_clause_set, _fn=functor,
                                        _ar=arity, _db=db, _tm=_tro_m):
                if id(clause) in _tset:
                    return _compile_tro_body(clause, _fn, _ar, _db, var_context, _TRAIL_PARAM_NAME,
                                             tro_mode=_tm)
                return _orig_bc(clause, var_context)
            loop_stmts.extend(
                _build_list_dispatch_guard(
                    clauses, dispatch_pos, arity, subject, _tro_list_body_compiler
                )
            )
        else:
            loop_stmts.extend(
                _build_list_dispatch_guard(
                    clauses, dispatch_pos, arity, subject, body_compiler
                )
            )
    else:
        for ci, clause in enumerate(clauses):
            var_context: dict[int, str] = {}
            _head_arg_patterns(clause.head, var_context, arity)

            if use_tro and ci in tro_indices:
                # TRO clause: compile prefix goals normally, replace tail call.
                tro_body_stmts = _compile_tro_body(
                    clause, functor, arity, db, var_context, _TRAIL_PARAM_NAME,
                    tro_mode=tro_mode,
                )
                body_stmts = tro_body_stmts
            else:
                body_stmts = body_compiler(clause, var_context)

            case_arm = compile_head_to_match_case(
                head=clause.head,
                body_stmts=body_stmts,
                var_context=var_context,
                arity=arity,
                skip_trail=skip_trail,
            )
            loop_stmts.append(ast.Match(subject=subject, cases=[case_arm]))

    if use_tro and tro_mode == "loop":
        # After all match arms: if _tro was set, reassign args and continue.
        reassign_stmts: list[ast.stmt] = []
        for i in range(arity):
            reassign_stmts.append(
                _assign(f"arg{i}", _name(f"_tro_arg{i}"))
            )
        reassign_stmts.append(ast.Continue())
        loop_stmts.append(
            ast.If(
                test=_name("_tro"),
                body=reassign_stmts,
                orelse=[],
            )
        )
        loop_stmts.append(ast.Break())
    elif use_tro and tro_mode == "signal":
        # Signal mode (bucket): _tro_state was set by _compile_tro_tail.
        # Early exit via _tro_state[0] checks are emitted within the match
        # arms by _compile_tro_tail.  After all match arms, just fall through.
        # Add an early-exit check after the last TRO-eligible match arm:
        loop_stmts.append(
            ast.If(
                test=ast.Subscript(
                    value=_name("_tro_state"), slice=ast.Constant(0), ctx=ast.Load(),
                ),
                body=[ast.Return(value=ast.Constant(None))],
                orelse=[],
            )
        )

    # Build the function body.
    all_stmts: list[ast.stmt]
    if use_tro and tro_mode == "loop":
        # Wrap loop_stmts in while True: ...
        all_stmts = [
            ast.While(
                test=ast.Constant(value=True),
                body=loop_stmts,
                orelse=[],
            )
        ]
    else:
        all_stmts = loop_stmts

    if emit_done:
        all_stmts.append(_yield_step_stmt(_name(_TRAMP_PARENT_NAME), _name("_DONE")))

    # A generator function needs at least one yield or a return+yield pair.
    if not all_stmts:
        all_stmts = [
            ast.Return(value=ast.Constant(value=None)),
            ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
        ]

    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=all_stmts,
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return func_def


def _compile_tro_body(
    clause: Clause,
    functor: str,
    arity: int,
    db: Database,
    var_context: dict[int, str],
    trail_name: str,
    tro_mode: str = "loop",
) -> list[ast.stmt]:
    """Compile a TRO-eligible clause body.

    All goals except the last are compiled normally (right-to-left continuation
    building).  The last goal (the tail-recursive call) is replaced by
    ``_compile_tro_tail`` which snapshots new arg values and sets the TRO flag.

    *tro_mode*: ``"loop"`` for while-True internal restart, ``"signal"``
    for shared ``_tro_state`` bucket signalling.

    *check_indices*: arg positions needing runtime ``is_var()`` ground-check.
    """
    goals = clause.body
    if not goals:
        return []

    prefix_goals = goals[:-1]
    tail_call = deref(goals[-1])

    # Pre-allocate body-only Vars FIRST so _compile_tro_tail and
    # compile_goal_trampoline find all Var names in var_context.
    alloc_stmts = _preallocate_body_vars(goals, var_context)

    # Compute runtime ground-check indices for head-decomposition vars.
    check_indices = _get_tro_check_indices(functor, arity, clause)

    # The innermost continuation is the TRO tail code (instead of yield solution).
    k = _compile_tro_tail(
        tail_call, arity, var_context, db, trail_name,
        tro_mode=tro_mode, check_indices=check_indices or None,
    )

    # Build prefix goals right-to-left, wrapping around the TRO tail.
    for goal in reversed(prefix_goals):
        k = compile_goal_trampoline(
            goal, db, var_context, trail_name, k,
            _THIS_GEN_NAME, _TRAMP_PARENT_NAME,
        )
    return alloc_stmts + k


def compile_predicate_trampoline(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: "Database | None" = None,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
    pred_cls: "PredicateMeta | None" = None,
) -> Callable:
    """Compile all clauses into a trampoline tuple-protocol generator.

    Unlike ``compile_predicate`` (simple/short-stack), the generated function:

    - Takes ``this_generator, parent`` as first two arguments.
      ``StepGenerator`` wraps the function and passes itself as
      ``this_generator`` automatically.
    - At each solution: ``yield (parent, None)`` — suspends; the calling
      generator (via the trampoline) processes the solution, then resumes
      this generator to find more.
    - After all clauses exhausted: ``yield (parent, _DONE)`` — signals
      end of search for this predicate.

    Sub-predicate calls within clause bodies use the coroutine-backtracking
    pattern::

        _gen  = StepGenerator(dispatch, this_generator, args, trail)
        _st   = (yield (_gen, None))
        while _st is not _DONE:
            <continuation>
            _st = (yield (_gen, None))

    so the Python call stack does *not* grow with predicate recursion depth.

    Compiled function signature::

        def {functor}__{arity}(this_generator, parent, arg0, …, argN, trail):
            …              # clause match arms
            yield (parent, _DONE)

    The trampoline (``clausal.logic.trampoline.trampoline``) drives execution
    via ``StepGenerator`` wrappers.
    """
    _effective_db = db if db is not None else _GlobalsDb(globals_ or {})

    if body_compiler is None:
        body_compiler = _make_body_compiler_trampoline(_effective_db)

    # Resolve pred_cls: explicit param > globals_ > auto-detect later.
    if pred_cls is None:
        pred_cls = (globals_ or {}).get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    if not clauses:
        fn = _compile_always_fail_trampoline(functor, arity)
        _install(db, functor, arity, fn, pred_cls=pred_cls)
        return fn

    base_globals: dict = {
        "Compound": Compound,
        "KWTerm": _KWTerm_t,
        "DictTerm": _DictTerm_t,
        "SetTerm": _SetTerm_t,
        "Var": Var,
        "unify": unify,
        "deref": deref,
        "is_var": is_var,
        "StepGenerator": StepGenerator,
        "_DONE": DONE,
        "_dif": _dif_fn,
        "_reify_eq": _reify_eq_fn,
        "_structural_eq": _structural_eq_fn,
        "_structural_neq": _structural_neq_fn,
        "_reify_fd": _reify_fd_fn,
        "_fd_eq": _fd_eq_fn,
        "_fd_ne": _fd_ne_fn,
        "_fd_lt": _fd_lt_fn,
        "_fd_le": _fd_le_fn,
        "_fd_gt": _fd_gt_fn,
        "_fd_ge": _fd_ge_fn,
        "_head_list_unify_input": _head_list_unify_input,
        "_head_list_unify_output": _head_list_unify_output,
        "_head_multi_star_error": _head_multi_star_error,
        "_body_star_unify": _body_star_unify,
        "_body_multi_star_unify": _body_multi_star_unify,
        "_build_star_list": _build_star_list,
        "_build_multi_star_list": _build_multi_star_list,
        "_tramp_call": _tramp_call,
        "_deref_walk": _deref_walk_fn,
        "_set_of_dedup": _set_of_dedup,
        "_LogicException": _LogicException_cls,
        "_python_error_term": _python_error_term_fn,
        "_in_iter": _in_iter,
        "_type_error": _type_error_fn,
        "_get_attr": _get_attr_fn,
        "_put_attr": _put_attr_fn,
        "SegList": SegList,
        "ConcreteSeg": ConcreteSeg,
        "VarSeg": VarSeg,
        "_seglist_unify_gen": _seglist_unify_gen,
        "_Fraction": Fraction,
    }
    # Ensure freeze/when hooks are registered.
    base_globals["_install_when_ground"] = _install_when_ground_fn
    base_globals["_install_when_disjunction"] = _install_when_disjunction_fn
    base_globals["_install_when_condition"] = _install_when_condition_fn
    # WFS: inject _naf_tabled, _table_store, and _TABLING_SUSPEND for tabled NAF
    if db is not None:
        base_globals["_naf_tabled"] = _naf_tabled_fn
        base_globals["_table_store"] = db.table_store
        base_globals["_TABLING_SUSPEND"] = _TABLING_SUSPEND
    # Phase 6: single combined traversal replacing three separate walks.
    _head_types, _py_thunks, _call_targets = _collect_globals_info(clauses)
    base_globals.update(_head_types)
    base_globals.update(_py_thunks)
    if globals_:
        base_globals.update(globals_)
    # Phase 6+7: resolve targets and capture locked dispatch functions.
    _inject_resolved_targets(_call_targets, base_globals, db, globals_)
    # Inject builtin predicate classes so bare builtin names (e.g. Member
    # passed as an argument to maplist) resolve at runtime.  Injected after
    # _inject_resolved_targets so that BuiltinPredicate adapters for call
    # targets (which handle DB-dependent builtins correctly) are not
    # overwritten.  For stateless builtins (factory is None), prefer the
    # PredicateMeta/MultiArityBuiltin class: it is callable as a term
    # constructor (needed when a goal appears as an argument to a meta-predicate
    # such as time_goal) and also provides _get_dispatch().
    for _bc_name, _bc_val in _BUILTIN_CLASSES.items():
        existing = base_globals.get(_bc_name)
        if existing is None or (
            isinstance(existing, BuiltinPredicate) and existing._factory is None
        ):
            base_globals[_bc_name] = _bc_val
    if pred_cls is None:
        pred_cls = base_globals.get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    # Destructive-reuse: inject DR dispatch functions into base_globals so
    # that rewritten goal names (e.g. _dr_append__3) resolve at runtime via
    # the locked-dispatch fast path.
    base_globals[_disp_key("_dr_append__3", 3)] = _dr_append_fn
    base_globals[_disp_key("_dr_dict_put__4", 4)] = _dr_dict_put_fn
    base_globals[_disp_key("_dr_set_union__3", 3)] = _dr_set_union_fn

    # Phase 7: set compile context so _dispatch_call_trampoline can emit
    # cached dispatch names instead of fname._get_dispatch() for locked predicates.
    _locked_keys = frozenset(k for k in base_globals if k.startswith(_DISP_PREFIX))
    _prev_locked_keys = getattr(_compile_context_local, "locked_dispatch_keys", frozenset())
    _compile_context_local.locked_dispatch_keys = _locked_keys
    # Phase 10f: initialise bucket-ref maps for call-site specialisation.
    _prev_brmap = getattr(_compile_context_local, "bucket_ref_map", {})
    _prev_jbrmap = getattr(_compile_context_local, "joint_bucket_ref_map", {})
    _compile_context_local.bucket_ref_map = {}
    _compile_context_local.joint_bucket_ref_map = {}
    try:
        # Phase 10d: inject bucket refs for statically-known call-site args.
        # Must run after _inject_resolved_targets (which populates base_globals
        # with callee predicate classes) but before building funcdef ASTs.
        _inject_bucket_refs_trampoline(clauses, base_globals)
        # ── Groundness-keyed dispatch (V2-2, subsumes V2-1) ──────────────
        index_positions = _analyze_index_positions(clauses, arity)
        if index_positions:
            # TRO: detect tail-recursive clauses (same check as non-indexed path).
            _is_tabled = (
                db is not None and db.is_tabled(functor, arity)
            )
            _idx_tro_indices: frozenset[int] | None = None
            _tro_state_obj = None
            if not _is_tabled:
                _tro_set = frozenset(
                    i for i, cl in enumerate(clauses)
                    if _detect_tro_clause(functor, arity, cl)
                )
                if _tro_set:
                    _idx_tro_indices = _tro_set
                    # Shared mutable TRO state: [flag, arg0, arg1, ..., argN-1]
                    _tro_state_obj = [False] + [None] * arity
                    base_globals["_tro_state"] = _tro_state_obj

            # Compile fallback (all clauses, for when no arg is ground).
            # Fallback uses "loop" mode TRO (has all clauses, can restart internally).
            fallback_def = _build_predicate_trampoline_funcdef(
                f"{functor}__all", arity, clauses,
                _effective_db, body_compiler, emit_done=False,
                tro_indices=_idx_tro_indices,
            )

            fallback_fn = functiondef_to_function(fallback_def, globals_=base_globals)

            plans: list[tuple[int, dict, Callable]] = []
            for pos, index in index_positions:
                idx_dict: dict = {}
                for key, bucket_clauses in index["buckets"].items():
                    # Phase 8: lift the indexed-position body Unify into the
                    # head so that head_to_match_pattern emits a MatchValue/
                    # MatchClass pattern instead of a wildcard capture.
                    # The bucket function is only called when arg_pos is
                    # ground (guaranteed by dispatch), so the removed Unify
                    # would always succeed — lifting is semantically safe.
                    lifted_bucket = [
                        _lift_clause_at_pos(cl, pos) for cl in bucket_clauses
                    ]
                    # No extra globals update needed: any compound type that
                    # appears in the lifted head was already in the original
                    # clause body and collected by _collect_globals_info(clauses)
                    # above.  Calling it again on lifted_bucket would
                    # re-collect term-node classes (Unify, in_, …) and
                    # clobber predicate entries set by _inject_resolved_targets.
                    bname = f"{functor}__p{pos}_b{len(idx_dict)}"
                    # Map TRO indices from original clauses to this bucket's clauses.
                    _b_tro = None
                    if _idx_tro_indices is not None:
                        _orig_ids = {id(cl) for i, cl in enumerate(clauses) if i in _idx_tro_indices}
                        _b_tro_set = frozenset(
                            i for i, cl in enumerate(bucket_clauses) if id(cl) in _orig_ids
                        )
                        if _b_tro_set:
                            _b_tro = _b_tro_set
                    # Single-clause bucket: elide outer trail mark/undo
                    # since there is no sibling clause to backtrack to.
                    _skip_trail = len(lifted_bucket) == 1
                    bdef = _build_predicate_trampoline_funcdef(
                        bname, arity, lifted_bucket,
                        _effective_db, body_compiler, emit_done=False,
                        tro_indices=_b_tro,
                        skip_trail=_skip_trail,
                    )
                    idx_dict[key] = functiondef_to_function(bdef, globals_=base_globals)
                # Default bucket (clauses with Var at indexed position).
                _d_tro = None
                if _idx_tro_indices is not None:
                    _orig_ids = {id(cl) for i, cl in enumerate(clauses) if i in _idx_tro_indices}
                    _d_tro_set = frozenset(
                        i for i, cl in enumerate(index["defaults"]) if id(cl) in _orig_ids
                    )
                    if _d_tro_set:
                        _d_tro = _d_tro_set
                ddef = _build_predicate_trampoline_funcdef(
                    f"{functor}__p{pos}_dflt", arity, index["defaults"],
                    _effective_db, body_compiler, emit_done=False,
                    tro_indices=_d_tro,
                )
                pos_default_fn = functiondef_to_function(ddef, globals_=base_globals)
                plans.append((pos, idx_dict, pos_default_fn))

            # Phase 10a: expose single-position bucket dicts on the predicate
            # class so that call-site specialisation can look up bucket functions
            # for statically-known argument values without invoking the dispatch
            # closure at runtime.
            if pred_cls is not None:
                pred_cls._index_plans = {pos: idx_dict for pos, idx_dict, _ in plans}

            # Phase 9b/9c: attempt multi-argument indexing when arity ≥ 2.
            # Try secondary (hierarchical) dispatch first; fall back to joint
            # if secondary yields no improvement over the best single-arg plan.
            fn = None
            if arity >= 2:
                joint_result = _analyze_joint_index_positions(
                    clauses, arity, index_positions)
                if joint_result is not None:
                    pos_i, pos_j, joint_info = joint_result
                    coverage = joint_info["coverage"]
                    if coverage < _JOINT_COVERAGE_THRESHOLD:
                        # Phase 9c — secondary (hierarchical) dispatch.
                        sec = _build_secondary_index(
                            clauses, arity, pos_i, pos_j)
                        if sec is not None:
                            level0_compiled: dict = {}
                            for ki, (l1_buckets, l1_defaults) in \
                                    sec["level0"].items():
                                if l1_buckets is not None:
                                    l1_fns: dict = {}
                                    for kj, bkt in l1_buckets.items():
                                        lifted = [
                                            _lift_clause_at_pos(
                                                _lift_clause_at_pos(cl, pos_i),
                                                pos_j)
                                            for cl in bkt
                                        ]
                                        bname = (
                                            f"{functor}__s{pos_i}"
                                            f"_{pos_j}_l0b{len(level0_compiled)}"
                                            f"_l1b{len(l1_fns)}"
                                        )
                                        bdef = _build_predicate_trampoline_funcdef(
                                            bname, arity, lifted,
                                            _effective_db, body_compiler,
                                            emit_done=False,
                                        )
                                        l1_fns[kj] = functiondef_to_function(
                                            bdef, globals_=base_globals)
                                    # level-1 default: clauses with var at pos_j
                                    l1d_lifted = [
                                        _lift_clause_at_pos(cl, pos_i)
                                        for cl in l1_defaults
                                    ]
                                    l1dname = (
                                        f"{functor}__s{pos_i}_{pos_j}"
                                        f"_l0b{len(level0_compiled)}_l1dflt"
                                    )
                                    l1ddef = _build_predicate_trampoline_funcdef(
                                        l1dname, arity, l1d_lifted,
                                        _effective_db, body_compiler,
                                        emit_done=False,
                                    )
                                    level0_compiled[ki] = (
                                        l1_fns,
                                        functiondef_to_function(
                                            l1ddef, globals_=base_globals),
                                    )
                                else:
                                    # sub-bucket too small for level-1 index
                                    lifted = [
                                        _lift_clause_at_pos(cl, pos_i)
                                        for cl in l1_defaults
                                    ]
                                    bname = (
                                        f"{functor}__s{pos_i}_{pos_j}"
                                        f"_l0b{len(level0_compiled)}_flat"
                                    )
                                    bdef = _build_predicate_trampoline_funcdef(
                                        bname, arity, lifted,
                                        _effective_db, body_compiler,
                                        emit_done=False,
                                    )
                                    level0_compiled[ki] = (
                                        None,
                                        functiondef_to_function(
                                            bdef, globals_=base_globals),
                                    )
                            # level-0 default (var at pos_i)
                            if sec["level0_defaults"]:
                                l0ddef = _build_predicate_trampoline_funcdef(
                                    f"{functor}__s{pos_i}_{pos_j}_l0dflt",
                                    arity, sec["level0_defaults"],
                                    _effective_db, body_compiler,
                                    emit_done=False,
                                )
                                level0_default_fn = functiondef_to_function(
                                    l0ddef, globals_=base_globals)
                            else:
                                level0_default_fn = _compile_always_fail_trampoline(
                                    functor, arity)
                            fn = _make_secondary_dispatch_trampoline(
                                sec, level0_compiled, level0_default_fn,
                                fallback_fn, DONE)
                            # Phase 10a: expose hierarchical bucket dicts.
                            if pred_cls is not None:
                                pred_cls._index_plans_hierarchical = {
                                    (pos_i, pos_j): level0_compiled
                                }
                    else:
                        # Phase 9b — flat joint key dispatch (high coverage).
                        joint_dict: dict = {}
                        for jk, bkt in joint_info["buckets"].items():
                            lifted = [
                                _lift_clause_at_pos(
                                    _lift_clause_at_pos(cl, pos_i), pos_j)
                                for cl in bkt
                            ]
                            jbname = (
                                f"{functor}__j{pos_i}_{pos_j}"
                                f"_b{len(joint_dict)}"
                            )
                            jbdef = _build_predicate_trampoline_funcdef(
                                jbname, arity, lifted,
                                _effective_db, body_compiler, emit_done=False,
                            )
                            joint_dict[jk] = functiondef_to_function(
                                jbdef, globals_=base_globals)
                        # joint default (either arg var)
                        if joint_info["defaults"]:
                            jddef = _build_predicate_trampoline_funcdef(
                                f"{functor}__j{pos_i}_{pos_j}_dflt",
                                arity, joint_info["defaults"],
                                _effective_db, body_compiler, emit_done=False,
                            )
                            joint_default_fn = functiondef_to_function(
                                jddef, globals_=base_globals)
                        else:
                            joint_default_fn = _compile_always_fail_trampoline(
                                functor, arity)
                        # single-arg fallbacks for partial groundness
                        single_i = _make_groundness_dispatch_trampoline(
                            [p for p in plans if p[0] == pos_i],
                            fallback_fn, DONE,
                            tro_state=_tro_state_obj, arity=arity)
                        single_j_plans = [p for p in plans if p[0] == pos_j]
                        if single_j_plans:
                            single_j = _make_groundness_dispatch_trampoline(
                                single_j_plans, fallback_fn, DONE,
                                tro_state=_tro_state_obj, arity=arity)
                        else:
                            single_j = fallback_fn
                        fn = _make_joint_dispatch_trampoline(
                            pos_i, pos_j,
                            joint_dict, joint_default_fn,
                            single_i, single_j,
                            fallback_fn, DONE,
                            tro_state=_tro_state_obj, arity=arity)
                        # Phase 10a: expose joint bucket dict.
                        if pred_cls is not None:
                            pred_cls._index_plans_joint = {(pos_i, pos_j): joint_dict}
            if fn is None:
                fn = _make_groundness_dispatch_trampoline(
                    plans, fallback_fn, DONE,
                    tro_state=_tro_state_obj, arity=arity)
        else:
            # Phase 10a: no indexing — clear any stale _index_plans from a
            # previous compilation (e.g. after retract reduced clause count
            # below the indexing threshold).
            if pred_cls is not None:
                pred_cls._index_plans = {}

            # TRO: detect tail-recursive clauses with deterministic prefixes.
            # Disabled for tabled predicates (SLG has its own suspension protocol).
            _is_tabled = (
                db is not None and db.is_tabled(functor, arity)
            )
            tro_indices: frozenset[int] | None = None
            if not _is_tabled:
                _tro_set = frozenset(
                    i for i, cl in enumerate(clauses)
                    if _detect_tro_clause(functor, arity, cl)
                )
                if _tro_set:
                    tro_indices = _tro_set

            func_def = _build_predicate_trampoline_funcdef(
                functor, arity, clauses, _effective_db, body_compiler,
                tro_indices=tro_indices,
            )

            fn = functiondef_to_function(func_def, globals_=base_globals)
    finally:
        _compile_context_local.locked_dispatch_keys = _prev_locked_keys
        # Phase 10f: restore bucket-ref maps.
        _compile_context_local.bucket_ref_map = _prev_brmap
        _compile_context_local.joint_bucket_ref_map = _prev_jbrmap

    def _recompile_trampoline() -> Callable:
        if db is not None:
            next_clauses = db.clauses_for(functor, arity)
        else:
            next_clauses = pred_cls._clauses if pred_cls is not None else clauses
        return compile_predicate_trampoline(
            functor, arity, next_clauses, db,
            body_compiler=body_compiler, globals_=globals_, pred_cls=pred_cls,
        )

    _install(db, functor, arity, fn, lazy_recompile=_recompile_trampoline, pred_cls=pred_cls)
    return fn


def compile_predicate_trampoline_ast(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
) -> ast.FunctionDef:
    """Return the ``ast.FunctionDef`` for a trampoline-mode compiled predicate.

    Identical to ``compile_predicate_trampoline`` but returns the AST node
    instead of executing it.  Does *not* install anything in the database.
    """
    if body_compiler is None:
        body_compiler = _make_body_compiler_trampoline(db)
    if not clauses:
        arg_names = [f"arg{i}" for i in range(arity)]
        params = [_THIS_GEN_NAME, _TRAMP_PARENT_NAME] + arg_names + [_TRAIL_PARAM_NAME]
        func_def = ast.FunctionDef(
            name=f"{functor}__{arity}",
            args=ast.arguments(
                posonlyargs=[], args=[ast.arg(arg=p) for p in params],
                vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=[
                _yield_step_stmt(_name(_TRAMP_PARENT_NAME), _name("_DONE")),
            ],
            decorator_list=[], returns=None, type_comment=None, **_EXTRA_FUNCDEF,
        )
        ast.fix_missing_locations(func_def)
        return func_def
    return _build_predicate_trampoline_funcdef(functor, arity, clauses, db, body_compiler)


def _compile_always_fail_trampoline(functor: str, arity: int) -> Callable:
    """Trampoline variant: generator that immediately yields (_tramp_parent, DONE)."""
    arg_names = [f"arg{i}" for i in range(arity)]
    params = [_THIS_GEN_NAME, _TRAMP_PARENT_NAME] + arg_names + [_TRAIL_PARAM_NAME]
    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=[
            _yield_step_stmt(_name(_TRAMP_PARENT_NAME), _name("_DONE")),
        ],
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return functiondef_to_function(func_def, globals_={"_DONE": DONE})


# ── head_to_match_pattern et al (moved to .head_match) ───────────────────────
from .head_match import (  # noqa: E402,F401
    _wrap_yields_with_output_guards,
    head_to_match_pattern,
    _compile_multi_star_guard,
    compile_head_to_match_case,
    _head_arg_patterns,
)


# ── compile_predicate ─────────────────────────────────────────────────────────

# Python 3.12+ added type_params to FunctionDef
_EXTRA_FUNCDEF: dict = (
    {"type_params": []} if "type_params" in ast.FunctionDef._fields else {}
)


# ── First-argument indexing (V2-1) ────────────────────────────────────────────

_INDEX_VAR = object()  # sentinel: clause has variable/non-indexable first arg
_INDEXABLE_TYPES = (int, float, str, bytes, bool, type(None))
_INDEX_THRESHOLD = 4  # minimum clauses before indexing kicks in
_JOINT_COVERAGE_THRESHOLD = 0.8  # min fraction of clauses needing joint key for 9b


# ── Phase 9a: key helpers ────────────────────────────────────────────────────


def _arg_to_index_key(arg: Any) -> Any:
    """Compile-time: convert a head argument to its index key.

    Returns a hashable key for indexable terms:
    - Scalars (int, float, str, bytes, bool, None) → the value itself
    - Compound nodes → ``(functor, arity)`` tuple  (Phase 9a)
    - PredicateMeta instances → ``(class_name, field_count)`` tuple  (Phase 9a)
    - Anything else (Var, list, DictTerm, …) → ``_INDEX_VAR``
    """
    if isinstance(arg, _INDEXABLE_TYPES):
        return arg
    if isinstance(arg, Compound):
        return (arg.functor, len(arg.args))
    if is_term_instance(arg):
        cls = type(arg)
        return (cls.__name__, len(term_field_names(arg)))
    return _INDEX_VAR


def _runtime_arg_key(a: Any) -> Any:
    """Runtime: extract the index key from a deref'd argument value.

    Mirrors :func:`_arg_to_index_key` for the runtime dispatch path.
    All four dispatch closure factories use this so that compound-term
    buckets (Phase 9a) are reachable without special-casing.
    """
    t = type(a)
    if t is int or t is str:
        return a
    if isinstance(a, _INDEXABLE_TYPES):
        return a
    if isinstance(a, Compound):
        return (a.functor, len(a.args))
    if is_term_instance(a):
        cls = type(a)
        return (cls.__name__, len(term_field_names(a)))
    return _INDEX_VAR


def _static_call_key(arg_expr: ast.expr) -> Any | None:
    """Return the index key if *arg_expr* is statically known at compile time.

    Mirrors :func:`_runtime_arg_key` for the compile-time call-site analysis
    path.  Returns ``None`` if the argument is a variable or otherwise unknown.
    """
    if isinstance(arg_expr, ast.Constant):
        # scalar: int, str, float, bool, None — key is the value itself
        return arg_expr.value
    if isinstance(arg_expr, ast.Call):
        # compound term constructor: Dog(_v_name, _v_age) or mod.Dog(...)
        func = arg_expr.func
        if isinstance(func, ast.Name):
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            return (func.id, n_args)
        if isinstance(func, ast.Attribute):
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            return (func.attr, n_args)
    return None


def _bucket_key(fname: str, pos: int, key: Any) -> str:
    """Readable globals key for a single-position bucket function.

    The returned string is used as an ``ast.Name`` id and as a
    ``base_globals`` key.  It is not a valid Python identifier (it contains
    dots, brackets, and quotes) so generated code won't re-parse, but
    ``ast.unparse()`` renders it readably and ``compile(ast_tree, ...)``
    resolves it via a plain dict lookup.
    """
    return f"{fname}.bucket(pos={pos}, {key!r})"


def _joint_bucket_key(fname: str, pos_i: int, pos_j: int,
                      ki: Any, kj: Any) -> str:
    """Readable globals key for a joint (two-position) bucket function."""
    return f"{fname}.bucket(pos=({pos_i},{pos_j}), ({ki!r},{kj!r}))"


def _extract_arg_key(clause: Clause, pos: int, arity: int) -> Any:
    """Extract the indexing key for a clause's argument at position *pos*.

    Returns a hashable key (scalar or ``(functor, arity)`` tuple) for
    indexable clauses, or ``_INDEX_VAR`` for variable/non-indexable args.
    """
    if arity == 0 or pos >= arity:
        return _INDEX_VAR
    head = clause.head
    # Get arg at position pos from head
    if isinstance(head, Compound):
        if len(head.args) <= pos:
            return _INDEX_VAR
        arg = head.args[pos]
    elif isinstance(head, Call) and isinstance(head.func, LoadName):
        if len(head.args) <= pos:
            return _INDEX_VAR
        arg = head.args[pos]
    elif is_term_instance(head):
        fields = term_field_names(head)
        if len(fields) <= pos:
            return _INDEX_VAR
        arg = getattr(head, fields[pos])
    else:
        return _INDEX_VAR
    # Direct ground term (scalar or compound) — Phase 9a extends to compounds.
    key = _arg_to_index_key(arg)
    if key is not _INDEX_VAR:
        return key
    # Var + Unify pattern (from _normalize_dataclass_fact).
    # Phase 9a: also extract compound/predicate keys from Unify targets.
    if is_var(arg):
        for goal in clause.body:
            if isinstance(goal, Unify):
                if goal.left is arg:
                    k = _arg_to_index_key(goal.right)
                    if k is not _INDEX_VAR:
                        return k
                elif goal.right is arg:
                    k = _arg_to_index_key(goal.left)
                    if k is not _INDEX_VAR:
                        return k
        return _INDEX_VAR
    return _INDEX_VAR


def _extract_first_arg_key(clause: Clause, arity: int) -> Any:
    """Extract the indexing key for a clause's first argument.

    Convenience wrapper around :func:`_extract_arg_key` for position 0.
    """
    return _extract_arg_key(clause, 0, arity)


def _build_arg_index(
    clauses: list[Clause], arity: int, pos: int,
    threshold: int = _INDEX_THRESHOLD,
) -> dict | None:
    """partition clauses into buckets keyed on argument *pos*.

    Returns None if indexing is not beneficial (too few clauses, all defaults,
    or arity == 0).  Otherwise returns::

        {"buckets": {key: [Clause, ...]},  # merged with defaults
         "defaults": [Clause, ...],
         "all": [Clause, ...],
         "n_distinct": int}

    Each bucket's clause list includes the default (var-headed) clauses
    interleaved in their original order, preserving Prolog clause ordering.
    """
    if arity == 0 or pos >= arity or len(clauses) < threshold:
        return None
    keys = [_extract_arg_key(c, pos, arity) for c in clauses]
    default_indices = [i for i, k in enumerate(keys) if k is _INDEX_VAR]
    specific_indices = [i for i, k in enumerate(keys) if k is not _INDEX_VAR]
    if not specific_indices:
        return None  # all defaults — indexing won't help
    # Group specific clauses by key
    bucket_map: dict[Any, list[int]] = defaultdict(list)
    for i in specific_indices:
        bucket_map[keys[i]].append(i)
    # Each bucket = bucket-specific + default clauses, merged in original order
    merged_buckets: dict[Any, list[Clause]] = {}
    for key, b_indices in bucket_map.items():
        merged = sorted(b_indices + default_indices)
        merged_buckets[key] = [clauses[i] for i in merged]
    return {
        "buckets": merged_buckets,
        "defaults": [clauses[i] for i in default_indices],
        "all": clauses,
        "n_distinct": len(bucket_map),
    }


def _build_first_arg_index(
    clauses: list[Clause], arity: int, threshold: int = _INDEX_THRESHOLD,
) -> dict | None:
    """partition clauses into first-arg buckets.

    Convenience wrapper around :func:`_build_arg_index` for position 0.
    """
    return _build_arg_index(clauses, arity, 0, threshold)


def _analyze_index_positions(
    clauses: list[Clause], arity: int, threshold: int = _INDEX_THRESHOLD,
) -> list[tuple[int, dict]]:
    """Find argument positions suitable for indexing, sorted by selectivity.

    Returns a list of ``(pos, index_info)`` tuples where each *index_info*
    is the dict from :func:`_build_arg_index`.  Positions are sorted by
    number of distinct keys (most distinct first = most selective).
    """
    if arity == 0 or len(clauses) < threshold:
        return []
    results = []
    for pos in range(arity):
        idx = _build_arg_index(clauses, arity, pos, threshold)
        if idx is not None:
            results.append((pos, idx))
    # Sort by selectivity: most distinct keys first
    results.sort(key=lambda x: -x[1]["n_distinct"])
    return results


# ── Phase 9b: joint (argI, argJ) indexing ───────────────────────────────────


def _build_joint_arg_index(
    clauses: list[Clause], arity: int, pos_i: int, pos_j: int,
    threshold: int = _INDEX_THRESHOLD,
) -> dict | None:
    """Build a flat joint index keyed on ``(key_i, key_j)`` tuples.

    Returns ``None`` when fewer than *threshold* clauses have both args
    indexable.  Otherwise returns the same shape as :func:`_build_arg_index`
    but with tuple keys::

        {"buckets": {(ki, kj): [Clause, ...]},
         "defaults": [Clause, ...],
         "all": [Clause, ...],
         "n_distinct": int,
         "coverage": float}   # fraction of clauses with both args indexable
    """
    if arity < 2 or pos_i == pos_j or pos_i >= arity or pos_j >= arity:
        return None
    keys = []
    for c in clauses:
        ki = _extract_arg_key(c, pos_i, arity)
        kj = _extract_arg_key(c, pos_j, arity)
        if ki is not _INDEX_VAR and kj is not _INDEX_VAR:
            keys.append((ki, kj))
        else:
            keys.append(_INDEX_VAR)
    specific_indices = [i for i, k in enumerate(keys) if k is not _INDEX_VAR]
    if len(specific_indices) < threshold:
        return None
    default_indices = [i for i, k in enumerate(keys) if k is _INDEX_VAR]
    bucket_map: dict[Any, list[int]] = defaultdict(list)
    for i in specific_indices:
        bucket_map[keys[i]].append(i)
    merged_buckets: dict[Any, list[Clause]] = {}
    for key, b_indices in bucket_map.items():
        merged = sorted(b_indices + default_indices)
        merged_buckets[key] = [clauses[i] for i in merged]
    return {
        "buckets": merged_buckets,
        "defaults": [clauses[i] for i in default_indices],
        "all": clauses,
        "n_distinct": len(bucket_map),
        "coverage": len(specific_indices) / len(clauses),
    }


def _analyze_joint_index_positions(
    clauses: list[Clause], arity: int,
    single_indexes: list[tuple[int, dict]],
    min_gain: float = 1.5,
) -> tuple[int, int, dict] | None:
    """Find the best ``(pos_i, pos_j)`` pair for joint indexing.

    Considers pairs ``(best_single_pos, k)`` for all remaining positions *k*.
    Returns ``(pos_i, pos_j, joint_index_info)`` if the joint index offers at
    least *min_gain* × more distinct keys than the best single-arg index, else
    ``None``.
    """
    if not single_indexes or arity < 2:
        return None
    best_single_pos, best_single_idx = single_indexes[0]
    best_single_distinct = best_single_idx["n_distinct"]
    best_joint: tuple[int, int, dict] | None = None
    best_joint_distinct = 0
    for pos in range(arity):
        if pos == best_single_pos:
            continue
        joint = _build_joint_arg_index(clauses, arity, best_single_pos, pos)
        if joint is None:
            continue
        if joint["n_distinct"] > best_joint_distinct:
            best_joint_distinct = joint["n_distinct"]
            best_joint = (best_single_pos, pos, joint)
    if best_joint is None:
        return None
    pos_i, pos_j, joint = best_joint
    if joint["n_distinct"] > best_single_distinct * min_gain:
        return pos_i, pos_j, joint
    return None


def _make_joint_dispatch_simple(
    pos_i: int, pos_j: int,
    joint_dict: dict, joint_default_fn,
    single_i_dispatch, single_j_dispatch,
    fallback_fn,
) -> Callable:
    """Build a flat joint-key dispatch for simple/short-stack mode.

    Decision tree (Phase 9b):
    1. Both *pos_i* and *pos_j* ground → joint dict lookup (O(1))
    2. Only *pos_i* ground → single-arg dispatch on *pos_i*
    3. Only *pos_j* ground → single-arg dispatch on *pos_j*
    4. Neither ground → *fallback_fn* (linear scan)
    """
    def dispatch(*args):
        _ai = deref(args[pos_i])
        _aj = deref(args[pos_j])
        if not is_var(_ai) and not is_var(_aj):
            _jk = (_runtime_arg_key(_ai), _runtime_arg_key(_aj))
            try:
                _bfn = joint_dict.get(_jk)
            except TypeError:
                _bfn = None
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from joint_default_fn(*args)
        elif not is_var(_ai):
            yield from single_i_dispatch(*args)
        elif not is_var(_aj):
            yield from single_j_dispatch(*args)
        else:
            yield from fallback_fn(*args)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_joint_dispatch_trampoline(
    pos_i: int, pos_j: int,
    joint_dict: dict, joint_default_fn,
    single_i_dispatch, single_j_dispatch,
    fallback_fn, done,
    tro_state=None, arity=0,
) -> Callable:
    """Build a flat joint-key dispatch for trampoline mode.  (Phase 9b)"""
    offset_i = pos_i + 2
    offset_j = pos_j + 2

    if tro_state is not None:
        def dispatch(*args):
            parent = args[1]
            args_list = list(args)
            while True:
                tro_state[0] = False
                _ai = deref(args_list[offset_i])
                _aj = deref(args_list[offset_j])
                if not is_var(_ai) and not is_var(_aj):
                    _jk = (_runtime_arg_key(_ai), _runtime_arg_key(_aj))
                    try:
                        _bfn = joint_dict.get(_jk)
                    except TypeError:
                        _bfn = None
                    if _bfn is not None:
                        yield from _bfn(*args_list)
                    else:
                        yield from joint_default_fn(*args_list)
                elif not is_var(_ai):
                    yield from single_i_dispatch(*args_list)
                elif not is_var(_aj):
                    yield from single_j_dispatch(*args_list)
                else:
                    yield from fallback_fn(*args_list)
                    break  # fallback has internal TRO loop
                if tro_state[0]:
                    for _i in range(arity):
                        args_list[_i + 2] = tro_state[_i + 1]
                    continue
                break
            yield (parent, done)
    else:
        def dispatch(*args):
            parent = args[1]
            _ai = deref(args[offset_i])
            _aj = deref(args[offset_j])
            if not is_var(_ai) and not is_var(_aj):
                _jk = (_runtime_arg_key(_ai), _runtime_arg_key(_aj))
                try:
                    _bfn = joint_dict.get(_jk)
                except TypeError:
                    _bfn = None
                if _bfn is not None:
                    yield from _bfn(*args)
                else:
                    yield from joint_default_fn(*args)
            elif not is_var(_ai):
                yield from single_i_dispatch(*args)
            elif not is_var(_aj):
                yield from single_j_dispatch(*args)
            else:
                yield from fallback_fn(*args)
            yield (parent, done)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


# ── Phase 9c: secondary (hierarchical) dispatch ──────────────────────────────


def _build_secondary_index(
    clauses: list[Clause], arity: int, pos_i: int, pos_j: int,
    threshold: int = _INDEX_THRESHOLD,
    secondary_threshold: int = 2,
) -> dict | None:
    """Build a two-level hierarchical index: level-0 on *pos_i*, level-1 on *pos_j*.

    Level-0 partitions clauses by key at *pos_i* exactly as
    :func:`_build_arg_index` does.  Within each level-0 bucket a second
    :func:`_build_arg_index` on *pos_j* is attempted (using a lower threshold
    since the sub-buckets are smaller).

    Returns::

        {"level0": {ki: (level1_buckets or None, level1_default_clause_list)},
         "level0_defaults": [Clause, ...],
         "pos_i": pos_i,
         "pos_j": pos_j,
         "n_level0": int}

    or ``None`` if the primary index is not viable.
    """
    primary = _build_arg_index(clauses, arity, pos_i, threshold)
    if primary is None:
        return None
    level0: dict[Any, tuple] = {}
    for ki, bucket in primary["buckets"].items():
        secondary = _build_arg_index(bucket, arity, pos_j,
                                     threshold=secondary_threshold)
        if secondary is not None:
            # level-1 default: all clauses in this level-0 bucket.
            # Using bucket (= secondary["all"]) rather than secondary["defaults"]
            # ensures that unbound arg_j queries still scan every matching clause.
            level0[ki] = (secondary["buckets"], bucket)
        else:
            level0[ki] = (None, bucket)
    return {
        "level0": level0,
        "level0_defaults": primary["defaults"],
        "pos_i": pos_i,
        "pos_j": pos_j,
        "n_level0": primary["n_distinct"],
    }


def _make_secondary_dispatch_simple(
    sec_idx: dict,
    level0_compiled: dict,     # {ki: (level1_fn_dict or None, level1_default_fn)}
    level0_default_fn: Callable,
    fallback_fn: Callable,
) -> Callable:
    """Build a two-level hierarchical dispatch for simple mode.  (Phase 9c)

    Decision tree:
    - *pos_i* var → *fallback_fn*
    - *pos_i* ground, key unknown → *level0_default_fn*
    - *pos_i* ground, key found:
      - *pos_j* var or no level-1 index → level-1 default fn
      - *pos_j* ground, key found → level-1 bucket fn
      - *pos_j* ground, key unknown → level-1 default fn
    """
    pos_i = sec_idx["pos_i"]
    pos_j = sec_idx["pos_j"]

    def dispatch(*args):
        _ai = deref(args[pos_i])
        if is_var(_ai):
            yield from fallback_fn(*args)
            return
        _ki = _runtime_arg_key(_ai)
        try:
            _entry = level0_compiled.get(_ki)
        except TypeError:
            _entry = None
        if _entry is None:
            yield from level0_default_fn(*args)
            return
        level1_fns, level1_default_fn = _entry
        if level1_fns is None:
            yield from level1_default_fn(*args)
            return
        _aj = deref(args[pos_j])
        if is_var(_aj):
            yield from level1_default_fn(*args)
            return
        _kj = _runtime_arg_key(_aj)
        try:
            _bfn = level1_fns.get(_kj)
        except TypeError:
            _bfn = None
        if _bfn is not None:
            yield from _bfn(*args)
        else:
            yield from level1_default_fn(*args)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_secondary_dispatch_trampoline(
    sec_idx: dict,
    level0_compiled: dict,
    level0_default_fn: Callable,
    fallback_fn: Callable,
    done: Any,
) -> Callable:
    """Build a two-level hierarchical dispatch for trampoline mode.  (Phase 9c)"""
    pos_i = sec_idx["pos_i"]
    pos_j = sec_idx["pos_j"]
    offset_i = pos_i + 2
    offset_j = pos_j + 2

    def dispatch(*args):
        parent = args[1]
        _ai = deref(args[offset_i])
        if is_var(_ai):
            yield from fallback_fn(*args)
        else:
            _ki = _runtime_arg_key(_ai)
            try:
                _entry = level0_compiled.get(_ki)
            except TypeError:
                _entry = None
            if _entry is None:
                yield from level0_default_fn(*args)
            else:
                level1_fns, level1_default_fn = _entry
                if level1_fns is None:
                    yield from level1_default_fn(*args)
                else:
                    _aj = deref(args[offset_j])
                    if is_var(_aj):
                        yield from level1_default_fn(*args)
                    else:
                        _kj = _runtime_arg_key(_aj)
                        try:
                            _bfn = level1_fns.get(_kj)
                        except TypeError:
                            _bfn = None
                        if _bfn is not None:
                            yield from _bfn(*args)
                        else:
                            yield from level1_default_fn(*args)
        yield (parent, done)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_indexed_dispatch_simple(all_fn, idx_dict, default_fn):
    """Build an indexed dispatch wrapper for simple/short-stack mode.

    Legacy V2-1 wrapper — indexes only on the first argument.
    Superseded by :func:`_make_groundness_dispatch_simple` for V2-2.
    """
    def dispatch(*args):
        _a0 = deref(args[0])
        if is_var(_a0):
            yield from all_fn(*args)
            return
        _k = _runtime_arg_key(_a0)
        try:
            _bfn = idx_dict.get(_k)
        except TypeError:
            _bfn = None
        if _bfn is not None:
            yield from _bfn(*args)
        else:
            yield from default_fn(*args)
    dispatch.__name__ = all_fn.__name__
    dispatch.__qualname__ = all_fn.__qualname__
    return dispatch


def _make_indexed_dispatch_trampoline(all_fn, idx_dict, default_fn, done):
    """Build an indexed dispatch wrapper for trampoline mode.

    Legacy V2-1 wrapper — indexes only on the first argument.
    Superseded by :func:`_make_groundness_dispatch_trampoline` for V2-2.
    """
    def dispatch(*args):
        parent = args[1]
        _a0 = deref(args[2])  # first predicate arg is at index 2
        if is_var(_a0):
            yield from all_fn(*args)
        else:
            _k = _runtime_arg_key(_a0)
            try:
                _bfn = idx_dict.get(_k)
            except TypeError:
                _bfn = None
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from default_fn(*args)
        yield (parent, done)
    dispatch.__name__ = all_fn.__name__
    dispatch.__qualname__ = all_fn.__qualname__
    return dispatch


# ── V2-2: Groundness-keyed dispatch ─────────────────────────────────────────


def _make_groundness_dispatch_simple(plans, fallback_fn):
    """Build a groundness-keyed dispatch selector for simple/short-stack mode.

    *plans* is a list of ``(pos, idx_dict, default_fn)`` tuples, sorted by
    selectivity (most selective position first).  At call time the selector
    checks each position's argument; the first ground argument triggers
    index lookup on that position.  If no argument is ground, *fallback_fn*
    (all clauses, linear scan) is used.
    """
    if len(plans) == 1:
        # Single-position fast path — avoid the loop overhead.
        pos, idx_dict, dflt_fn = plans[0]
        def dispatch(*args):
            _a = deref(args[pos])
            if is_var(_a):
                yield from fallback_fn(*args)
                return
            _k = _runtime_arg_key(_a)
            try:
                _bfn = idx_dict.get(_k)
            except TypeError:
                _bfn = None
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from dflt_fn(*args)
        dispatch.__name__ = fallback_fn.__name__
        dispatch.__qualname__ = fallback_fn.__qualname__
        return dispatch

    # Multi-position selector — check positions in selectivity order.
    def dispatch(*args):
        for _pos, _idx_dict, _dflt_fn in plans:
            _a = deref(args[_pos])
            if not is_var(_a):
                _k = _runtime_arg_key(_a)
                try:
                    _bfn = _idx_dict.get(_k)
                except TypeError:
                    _bfn = None
                if _bfn is not None:
                    yield from _bfn(*args)
                else:
                    yield from _dflt_fn(*args)
                return
        yield from fallback_fn(*args)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_groundness_dispatch_trampoline(plans, fallback_fn, done,
                                         tro_state=None, arity=0):
    """Build a groundness-keyed dispatch selector for trampoline mode.

    Same logic as :func:`_make_groundness_dispatch_simple` but accounts for
    the trampoline arg layout ``(this_generator, parent, arg0, ..., trail)``
    and emits a trailing ``yield (parent, done)`` after search exhaustion.

    when *tro_state* is not None, the dispatch loops: after each bucket
    ``yield from`` completes, it checks ``tro_state[0]``.  If True, updates
    args from ``tro_state[1..N]`` and re-dispatches (potentially to a
    different bucket).
    """
    if len(plans) == 1:
        pos, idx_dict, dflt_fn = plans[0]
        offset = pos + 2  # skip this_generator, parent
        if tro_state is not None:
            def dispatch(*args):
                parent = args[1]
                args_list = None
                while True:
                    tro_state[0] = False
                    _current = args_list if args_list is not None else args
                    _a = deref(_current[offset])
                    if is_var(_a):
                        yield from fallback_fn(*_current)
                        break  # fallback has its own internal TRO loop
                    _k = _runtime_arg_key(_a)
                    try:
                        _bfn = idx_dict.get(_k)
                    except TypeError:
                        _bfn = None
                    if _bfn is not None:
                        yield from _bfn(*_current)
                    else:
                        yield from dflt_fn(*_current)
                    if tro_state[0]:
                        if args_list is None:
                            args_list = list(args)
                        for _i in range(arity):
                            args_list[_i + 2] = tro_state[_i + 1]
                        continue
                    break
                yield (parent, done)
        else:
            def dispatch(*args):
                parent = args[1]
                _a = deref(args[offset])
                if is_var(_a):
                    yield from fallback_fn(*args)
                else:
                    _k = _runtime_arg_key(_a)
                    try:
                        _bfn = idx_dict.get(_k)
                    except TypeError:
                        _bfn = None
                    if _bfn is not None:
                        yield from _bfn(*args)
                    else:
                        yield from dflt_fn(*args)
                yield (parent, done)
        dispatch.__name__ = fallback_fn.__name__
        dispatch.__qualname__ = fallback_fn.__qualname__
        return dispatch

    if tro_state is not None:
        def dispatch(*args):
            parent = args[1]
            args_list = None
            while True:
                tro_state[0] = False
                _current = args_list if args_list is not None else args
                _dispatched = False
                for _pos, _idx_dict, _dflt_fn in plans:
                    _a = deref(_current[_pos + 2])
                    if not is_var(_a):
                        _k = _runtime_arg_key(_a)
                        try:
                            _bfn = _idx_dict.get(_k)
                        except TypeError:
                            _bfn = None
                        if _bfn is not None:
                            yield from _bfn(*_current)
                        else:
                            yield from _dflt_fn(*_current)
                        _dispatched = True
                        break
                if not _dispatched:
                    yield from fallback_fn(*_current)
                    break  # fallback has its own internal TRO loop
                if tro_state[0]:
                    if args_list is None:
                        args_list = list(args)
                    for _i in range(arity):
                        args_list[_i + 2] = tro_state[_i + 1]
                    continue
                break
            yield (parent, done)
    else:
        def dispatch(*args):
            parent = args[1]
            for _pos, _idx_dict, _dflt_fn in plans:
                _a = deref(args[_pos + 2])
                if not is_var(_a):
                    _k = _runtime_arg_key(_a)
                    try:
                        _bfn = _idx_dict.get(_k)
                    except TypeError:
                        _bfn = None
                    if _bfn is not None:
                        yield from _bfn(*args)
                    else:
                        yield from _dflt_fn(*args)
                    yield (parent, done)
                    return
            yield from fallback_fn(*args)
            yield (parent, done)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _build_predicate_funcdef(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
    skip_trail: bool = False,
) -> ast.FunctionDef:
    """Build the ``ast.FunctionDef`` for a simple/short-stack compiled predicate.

    Returns the fixed-up FunctionDef without executing it.  Used by both
    ``compile_predicate`` (which then calls ``functiondef_to_function``) and
    ``compile_predicate_ast`` (which returns the FunctionDef directly).
    """
    arg_names = [f"arg{i}" for i in range(arity)]
    params = arg_names + [_TRAIL_PARAM_NAME, _K_PARAM_NAME]

    all_stmts: list[ast.stmt] = []

    if clauses and arity > 0:
        # Deref each argument once into a local before the clause match arms.
        deref_names = [f"_d{i}" for i in range(arity)]
        for i, arg in enumerate(arg_names):
            all_stmts.append(_assign(deref_names[i], _call(_name("deref"), _name(arg))))
        subject = ast.Tuple(elts=[_name(n) for n in deref_names], ctx=ast.Load())
    else:
        subject = ast.Tuple(
            elts=[_call(_name("deref"), _name(n)) for n in arg_names],
            ctx=ast.Load(),
        )

    for clause in clauses:
        var_context: dict[int, str] = {}
        _head_arg_patterns(clause.head, var_context, arity)
        body_stmts = body_compiler(clause, var_context)
        case_arm = compile_head_to_match_case(
            head=clause.head,
            body_stmts=body_stmts,
            var_context=var_context,
            arity=arity,
            skip_trail=skip_trail,
        )
        all_stmts.append(ast.Match(subject=subject, cases=[case_arm]))

    # Empty body is invalid Python; use return+yield to make a no-op generator.
    if not all_stmts:
        all_stmts = [
            ast.Return(value=ast.Constant(value=None)),
            ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
        ]

    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=all_stmts,
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return func_def


def _shallow_to_trampoline(shallow_fn: Callable, func_name: str) -> Callable:
    """Wrap a shallow-mode dispatch function in a trampoline-protocol adapter.

    Shallow functions have signature ``fn(arg0, …, argN, trail, k)`` and
    ``yield None`` per solution.  The trampoline solver calls predicates as
    ``fn(this_generator, parent, arg0, …, argN, trail)``.  This wrapper
    bridges the two protocols so the standard solver can drive shallow
    predicates without modification.

    The internal for-loop body of the shallow function is unchanged; the
    overhead is one extra generator frame at the call boundary.
    """
    def _trampoline_wrapper(this_generator, parent, *args):
        # args = (arg0, ..., argN, trail) in trampoline calling convention.
        for _ in shallow_fn(*args, None):   # k=None (shallow mode ignores k)
            yield (parent, None)
        yield (parent, DONE)

    _trampoline_wrapper.__name__ = func_name
    _trampoline_wrapper.__qualname__ = func_name
    return _trampoline_wrapper


def compile_predicate_shallow(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: "Database | None" = None,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
    pred_cls: "PredicateMeta | None" = None,
) -> Callable:
    """Compile a predicate in shallow / short-stack mode.

    Use this for predicates that are known to be bounded in call depth —
    fact tables, leaf predicates, and simple deterministic helpers.  Each
    sub-predicate call is a Python ``for`` loop, so the Python call stack
    grows with recursion depth.  For predicates with unbounded recursion use
    ``compile_predicate_trampoline`` instead.

    The compiled function signature is::

        def {functor}__{arity}(arg0, …, argN, trail, k):
            …
            yield None   # ← one solution

    Also installs on the PredicateMeta class (and ``db.set_dispatch()``) so
    subsequent ``_get_dispatch()`` / ``db.get_dispatch()`` calls work.
    """
    # Choose the effective db for body compilation (may be a no-db proxy).
    _effective_db = db if db is not None else _GlobalsDb(globals_ or {})

    if body_compiler is None:
        body_compiler = _make_body_compiler(_effective_db)

    # Resolve pred_cls: explicit param > globals_ > auto-detect later.
    if pred_cls is None:
        pred_cls = (globals_ or {}).get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    if not clauses:
        fn = _compile_always_fail(functor, arity)
        _install(db, functor, arity, fn, pred_cls=pred_cls)
        return fn

    base_globals: dict = {
        "Compound": Compound,
        "KWTerm": _KWTerm,
        "DictTerm": _DictTerm_s,
        "SetTerm": _SetTerm_s,
        "Var": Var,
        "unify": unify,
        "deref": deref,
        "is_var": is_var,
        "_dif": _dif_fn_s,
        "_reify_eq": _reify_eq_fn_s,
        "_reify_fd": _reify_fd_fn_s,
        "_fd_eq": _fd_eq_fn_s,
        "_fd_ne": _fd_ne_fn_s,
        "_fd_lt": _fd_lt_fn_s,
        "_fd_le": _fd_le_fn_s,
        "_fd_gt": _fd_gt_fn_s,
        "_fd_ge": _fd_ge_fn_s,
        "_head_list_unify_input": _head_list_unify_input,
        "_head_list_unify_output": _head_list_unify_output,
        "_head_multi_star_error": _head_multi_star_error,
        "_body_star_unify": _body_star_unify,
        "_body_multi_star_unify": _body_multi_star_unify,
        "_build_star_list": _build_star_list,
        "_build_multi_star_list": _build_multi_star_list,
        "_tramp_call": _tramp_call,
        "_deref_walk": _deref_walk_fn,
        "_set_of_dedup": _set_of_dedup,
        "_LogicException": _LogicException_cls,
        "_python_error_term": _python_error_term_fn_s,
        "_in_iter": _in_iter,
        "_type_error": _type_error_fn_s,
        "_get_attr": _get_attr_fn_s,
        "_put_attr": _put_attr_fn_s,
        "SegList": SegList,
        "ConcreteSeg": ConcreteSeg,
        "VarSeg": VarSeg,
        "_seglist_unify_gen": _seglist_unify_gen,
        "_Fraction": Fraction,
    }
    # Ensure freeze/when hooks are registered.
    base_globals["_install_when_ground"] = _install_when_ground_fn_s
    base_globals["_install_when_disjunction"] = _install_when_disjunction_fn_s
    base_globals["_install_when_condition"] = _install_when_condition_fn_s
    # WFS: inject _naf_tabled and _table_store for tabled NAF
    if db is not None:
        base_globals["_naf_tabled"] = _naf_tabled_fn_s
        base_globals["_table_store"] = db.table_store
    # Phase 6: single combined traversal replacing three separate walks.
    _head_types, _py_thunks, _call_targets = _collect_globals_info(clauses)
    base_globals.update(_head_types)
    base_globals.update(_py_thunks)
    if globals_:
        base_globals.update(globals_)
    # Phase 6+7: resolve targets and capture locked dispatch functions.
    _inject_resolved_targets(_call_targets, base_globals, db, globals_)
    # Inject builtin predicate classes so bare builtin names (e.g. Member
    # passed as an argument to maplist) resolve at runtime.  Injected after
    # _inject_resolved_targets so that BuiltinPredicate adapters for call
    # targets (which handle DB-dependent builtins correctly) are not
    # overwritten.  For stateless builtins (factory is None), prefer the
    # PredicateMeta/MultiArityBuiltin class: it is callable as a term
    # constructor (needed when a goal appears as an argument to a meta-predicate
    # such as time_goal) and also provides _get_dispatch().
    for _bc_name, _bc_val in _BUILTIN_CLASSES.items():
        existing = base_globals.get(_bc_name)
        if existing is None or (
            isinstance(existing, BuiltinPredicate) and existing._factory is None
        ):
            base_globals[_bc_name] = _bc_val
    # Resolve Predicate class — explicit param > globals_ > _collect_head_types.
    if pred_cls is None:
        pred_cls = base_globals.get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    # Phase 7: set compile context so _dispatch_call_iter can emit cached
    # dispatch names instead of fname._get_dispatch() for locked predicates.
    _locked_keys = frozenset(k for k in base_globals if k.startswith(_DISP_PREFIX))
    _prev_locked_keys = getattr(_compile_context_local, "locked_dispatch_keys", frozenset())
    _compile_context_local.locked_dispatch_keys = _locked_keys
    try:
        # ── Groundness-keyed dispatch (V2-2, subsumes V2-1) ──────────────
        index_positions = _analyze_index_positions(clauses, arity)
        if index_positions:
            # Compile fallback (all clauses, for when no arg is ground)
            fallback_def = _build_predicate_funcdef(
                f"{functor}__all", arity, clauses, _effective_db, body_compiler,
            )

            fallback_fn = functiondef_to_function(fallback_def, globals_=base_globals)

            plans: list[tuple[int, dict, Callable]] = []
            for pos, index in index_positions:
                idx_dict: dict = {}
                for key, bucket_clauses in index["buckets"].items():
                    bname = f"{functor}__p{pos}_b{len(idx_dict)}"
                    _skip_trail = len(bucket_clauses) == 1
                    bdef = _build_predicate_funcdef(
                        bname, arity, bucket_clauses, _effective_db, body_compiler,
                        skip_trail=_skip_trail,
                    )
                    idx_dict[key] = functiondef_to_function(bdef, globals_=base_globals)
                if index["defaults"]:
                    ddef = _build_predicate_funcdef(
                        f"{functor}__p{pos}_dflt", arity, index["defaults"],
                        _effective_db, body_compiler,
                    )
                    pos_default_fn = functiondef_to_function(ddef, globals_=base_globals)
                else:
                    pos_default_fn = _compile_always_fail(functor, arity)
                plans.append((pos, idx_dict, pos_default_fn))

            # Phase 9b/9c: attempt multi-argument indexing when arity ≥ 2.
            fn = None
            if arity >= 2:
                joint_result = _analyze_joint_index_positions(
                    clauses, arity, index_positions)
                if joint_result is not None:
                    pos_i, pos_j, joint_info = joint_result
                    coverage = joint_info["coverage"]
                    if coverage < _JOINT_COVERAGE_THRESHOLD:
                        # Phase 9c — secondary (hierarchical) dispatch.
                        sec = _build_secondary_index(
                            clauses, arity, pos_i, pos_j)
                        if sec is not None:
                            level0_compiled: dict = {}
                            for ki, (l1_buckets, l1_defaults) in \
                                    sec["level0"].items():
                                if l1_buckets is not None:
                                    l1_fns: dict = {}
                                    for kj, bkt in l1_buckets.items():
                                        bname = (
                                            f"{functor}__s{pos_i}"
                                            f"_{pos_j}_l0b{len(level0_compiled)}"
                                            f"_l1b{len(l1_fns)}"
                                        )
                                        bdef = _build_predicate_funcdef(
                                            bname, arity, bkt,
                                            _effective_db, body_compiler,
                                            skip_trail=len(bkt) == 1,
                                        )
                                        l1_fns[kj] = functiondef_to_function(
                                            bdef, globals_=base_globals)
                                    l1dname = (
                                        f"{functor}__s{pos_i}_{pos_j}"
                                        f"_l0b{len(level0_compiled)}_l1dflt"
                                    )
                                    l1ddef = _build_predicate_funcdef(
                                        l1dname, arity, l1_defaults,
                                        _effective_db, body_compiler,
                                    )
                                    level0_compiled[ki] = (
                                        l1_fns,
                                        functiondef_to_function(
                                            l1ddef, globals_=base_globals),
                                    )
                                else:
                                    bname = (
                                        f"{functor}__s{pos_i}_{pos_j}"
                                        f"_l0b{len(level0_compiled)}_flat"
                                    )
                                    bdef = _build_predicate_funcdef(
                                        bname, arity, l1_defaults,
                                        _effective_db, body_compiler,
                                    )
                                    level0_compiled[ki] = (
                                        None,
                                        functiondef_to_function(
                                            bdef, globals_=base_globals),
                                    )
                            if sec["level0_defaults"]:
                                l0ddef = _build_predicate_funcdef(
                                    f"{functor}__s{pos_i}_{pos_j}_l0dflt",
                                    arity, sec["level0_defaults"],
                                    _effective_db, body_compiler,
                                )
                                level0_default_fn = functiondef_to_function(
                                    l0ddef, globals_=base_globals)
                            else:
                                level0_default_fn = _compile_always_fail(
                                    functor, arity)
                            fn = _make_secondary_dispatch_simple(
                                sec, level0_compiled, level0_default_fn,
                                fallback_fn)
                    else:
                        # Phase 9b — flat joint key dispatch (high coverage).
                        joint_dict: dict = {}
                        for jk, bkt in joint_info["buckets"].items():
                            jbname = (
                                f"{functor}__j{pos_i}_{pos_j}"
                                f"_b{len(joint_dict)}"
                            )
                            jbdef = _build_predicate_funcdef(
                                jbname, arity, bkt,
                                _effective_db, body_compiler,
                                skip_trail=len(bkt) == 1,
                            )
                            joint_dict[jk] = functiondef_to_function(
                                jbdef, globals_=base_globals)
                        if joint_info["defaults"]:
                            jddef = _build_predicate_funcdef(
                                f"{functor}__j{pos_i}_{pos_j}_dflt",
                                arity, joint_info["defaults"],
                                _effective_db, body_compiler,
                            )
                            joint_default_fn = functiondef_to_function(
                                jddef, globals_=base_globals)
                        else:
                            joint_default_fn = _compile_always_fail(
                                functor, arity)
                        single_i = _make_groundness_dispatch_simple(
                            [p for p in plans if p[0] == pos_i], fallback_fn)
                        single_j_plans = [p for p in plans if p[0] == pos_j]
                        if single_j_plans:
                            single_j = _make_groundness_dispatch_simple(
                                single_j_plans, fallback_fn)
                        else:
                            single_j = fallback_fn
                        fn = _make_joint_dispatch_simple(
                            pos_i, pos_j,
                            joint_dict, joint_default_fn,
                            single_i, single_j, fallback_fn)
            if fn is None:
                fn = _make_groundness_dispatch_simple(plans, fallback_fn)
        else:
            func_def = _build_predicate_funcdef(
                functor, arity, clauses, _effective_db, body_compiler,
            )

            fn = functiondef_to_function(func_def, globals_=base_globals)
    finally:
        _compile_context_local.locked_dispatch_keys = _prev_locked_keys

    # Wrap the shallow function in a trampoline-protocol adapter so it can be
    # driven by the standard solver and called from compiled trampoline code.
    tramp_fn = _shallow_to_trampoline(fn, f"{functor}__{arity}")

    def _recompile_shallow() -> Callable:
        if db is not None:
            next_clauses = db.clauses_for(functor, arity)
        else:
            next_clauses = pred_cls._clauses if pred_cls is not None else clauses
        return compile_predicate_shallow(
            functor, arity, next_clauses, db,
            body_compiler=body_compiler, globals_=globals_, pred_cls=pred_cls,
        )

    _install(db, functor, arity, tramp_fn, lazy_recompile=_recompile_shallow, pred_cls=pred_cls)
    return fn


def compile_predicate(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: "Database | None" = None,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
    pred_cls: "PredicateMeta | None" = None,
) -> Callable:
    """Deprecated alias for ``compile_predicate_shallow``.

    Use ``compile_predicate_shallow`` for shallow/bounded predicates or
    ``compile_predicate_trampoline`` for the stack-safe production path.
    """
    warnings.warn(
        "compile_predicate() is deprecated — use compile_predicate_shallow() "
        "or compile_predicate_trampoline()",
        DeprecationWarning,
        stacklevel=2,
    )
    return compile_predicate_shallow(
        functor, arity, clauses, db,
        body_compiler=body_compiler, globals_=globals_, pred_cls=pred_cls,
    )


def compile_predicate_shallow_ast(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
) -> ast.FunctionDef:
    """Return the ``ast.FunctionDef`` for a shallow-mode compiled predicate.

    Identical to ``compile_predicate_shallow`` but returns the AST node
    instead of executing it.  Useful for inspecting or pretty-printing
    generated code.  Does *not* install anything in the database.
    """
    if body_compiler is None:
        body_compiler = _make_body_compiler(db)
    if not clauses:
        arg_names = [f"arg{i}" for i in range(arity)]
        params = arg_names + [_TRAIL_PARAM_NAME, _K_PARAM_NAME]
        return ast.FunctionDef(
            name=f"{functor}__{arity}",
            args=ast.arguments(
                posonlyargs=[], args=[ast.arg(arg=p) for p in params],
                vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=[ast.Return(value=ast.Constant(value=None)),
                  ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))],
            decorator_list=[], returns=None, type_comment=None, **_EXTRA_FUNCDEF,
        )
    return _build_predicate_funcdef(functor, arity, clauses, db, body_compiler)


def compile_predicate_ast(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
) -> ast.FunctionDef:
    """Deprecated alias for ``compile_predicate_shallow_ast``."""
    warnings.warn(
        "compile_predicate_ast() is deprecated — use compile_predicate_shallow_ast()",
        DeprecationWarning,
        stacklevel=2,
    )
    return compile_predicate_shallow_ast(functor, arity, clauses, db, body_compiler)


def _stub_body_stmts() -> list[ast.stmt]:
    """Placeholder body: succeed once by yielding None."""
    return [ast.Expr(value=ast.Yield(value=ast.Constant(value=None)))]


def _compile_always_fail(functor: str, arity: int) -> Callable:
    """Return a generator function that matches any args but never yields."""
    arg_names = [f"arg{i}" for i in range(arity)]
    params = arg_names + [_TRAIL_PARAM_NAME, _K_PARAM_NAME]
    func_name = f"{functor}__{arity}"
    func_def = ast.FunctionDef(
        name=func_name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=p) for p in params],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        # return; yield  →  generator that stops immediately
        body=[
            ast.Return(value=ast.Constant(value=None)),
            ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
        ],
        decorator_list=[],
        returns=None,
        type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    ast.fix_missing_locations(func_def)
    return functiondef_to_function(func_def, globals_={})


def _install(
    db: "Database | None",
    functor: str,
    arity: int,
    fn: Callable,
    lazy_recompile: Callable | None = None,
    pred_cls: PredicateMeta | None = None,
) -> None:
    """Install fn as the compiled dispatch function.

    If ``db`` is provided, stores the dispatch fn via ``db.set_dispatch()``
    so that ``db.get_dispatch()`` works for test/non-PredicateMeta usage.

    If ``pred_cls`` is a PredicateMeta class, installs fn and lazy_recompile
    directly on the class so that ``pred_cls._get_dispatch()`` works.
    """
    if db is not None:
        db.set_dispatch(functor, arity, fn, lazy_recompile=lazy_recompile)
    if pred_cls is not None and isinstance(pred_cls, PredicateMeta):
        pred_cls._dispatch_fn = fn
        if lazy_recompile is not None:
            pred_cls._lazy_recompile = lazy_recompile


__all__ = [
    # Shallow / short-stack compilation (bounded-depth predicates)
    "compile_predicate_shallow",
    "compile_predicate_shallow_ast",
    "compile_goal",
    "compile_body",
    # Trampoline / stack-safe compilation (production default)
    "compile_predicate_trampoline",
    "compile_predicate_trampoline_ast",
    "compile_goal_trampoline",
    "compile_body_trampoline",
    "DONE",
    # Shared utilities
    "head_to_match_pattern",
    "compile_head_to_match_case",
    "term_to_ast_expr",
    "arith_to_ast_expr",
    # Deprecated aliases
    "compile_predicate",
    "compile_predicate_ast",
]
