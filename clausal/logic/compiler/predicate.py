"""Top-level predicate-compilation entrypoints.

This submodule owns the three public compile functions
(``compile_predicate_shallow``, ``compile_predicate_trampoline``,
``compile_predicate``) plus their ``_ast`` variants and the
``_build_predicate_*_funcdef`` helpers that assemble the final
``ast.FunctionDef`` for a predicate.

``_EXTRA_FUNCDEF`` lives in ``_ast_helpers`` so submodules can
reference it without depending on this entrypoint module.  Locked-
dispatch / bucket-ref state lives on ``CompilationContext``
(``ctx_template``) rather than a thread-local.
"""

from __future__ import annotations

import ast
import warnings
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref, unify  # noqa: F401
from clausal.logic.trampoline import Step, DONE, StepGenerator
from clausal.terms import (
    Compound,
    Call, LoadName, LoadAttr,
    SegList, ConcreteSeg, VarSeg,
    SegString,
    SegBytes,
    _seglist_unify_gen,
    Unknown,
)
from clausal.pythonic_ast.nodes import StarUnpack  # noqa: F401
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import (
    PredicateMeta, atom_by_id as _atom_by_id, _dispatch_at,
)
from clausal.codegen import functiondef_to_function
from clausal.logic.solve import _deref_walk as _deref_walk_fn
from clausal.logic.builtins import (  # noqa: F401
    get_builtin_predicate,
    BuiltinPredicate,
    _BUILTIN_CLASSES,
)
# Runtime helpers referenced by base_globals of compiled predicates.
# They live in clausal.logic.runtime; see clausal/logic/compiler/README.md
# §7 (runtime/compile-time boundary).  Importing them here binds them as
# module globals so base_globals[name] = <name> resolves at dict-
# construction time.  Generated code references them by name string only.
from clausal.logic.runtime.list_unify import (  # noqa: F401
    _head_list_unify_input,
    _head_list_unify_output,
    _head_multi_star_error,
)
from clausal.logic.runtime.body_star_unify import (  # noqa: F401
    _body_star_unify,
    _body_multi_star_unify,
    _build_star_list,
    _build_multi_star_list,
    _in_iter,
)
from clausal.logic.runtime.tramp_call import _tramp_call  # noqa: F401
from clausal.logic.runtime.dict_ops import _subscript, _splat_data, _dict_key  # noqa: F401

from ._ast_helpers import (
    _name, _call, _assign, _assign_mark, _undo_stmt, _if,
    _MARK_PREFIX, _TRAIL_PARAM_NAME, _K_PARAM_NAME,
    _THIS_GEN_NAME, _DISP_PREFIX,
    _EXTRA_FUNCDEF,
    maybe_assert_located,
    stamp_predicate_funcdef,
    _push_position,
    _pop_position,
)
from ._vars import _var_python_name, _collect_vars
from .terms_to_ast import term_to_ast_expr, _dotted_name_from_loadattr  # noqa: F401
from .terms_to_goalop import BareGoalVariableError, BareGoalUnknownError
from .globals_env import (
    _GlobalsDb, _DbDispatchAdapter, _set_of_dedup, _set_of_sort_dedup,
    _findall_copy_row, _disp_key,
    _merge_builtin, _inject_call_targets, _inject_resolved_targets,
    _collect_globals_info, _preallocate_body_vars,
)
from .head_match import (
    head_to_match_pattern, compile_head_to_match_case, _head_arg_patterns,
    _wrap_yields_with_output_guards,
)
from .list_dispatch import (
    _get_head_arg, _lift_clause_at_pos,
    _find_list_dispatch_pos, _build_list_dispatch_guard,
)
from .arg_index import (
    _INDEX_VAR, _INDEXABLE_TYPES, _INDEX_THRESHOLD, _JOINT_COVERAGE_THRESHOLD,
    _extract_arg_key, _extract_first_arg_key,
    _build_arg_index, _build_first_arg_index,
    _analyze_index_positions, _build_joint_arg_index,
    _analyze_joint_index_positions,
    _make_joint_dispatch_simple, _make_joint_dispatch_trampoline,
    _build_secondary_index,
    _make_secondary_dispatch_simple, _make_secondary_dispatch_trampoline,
    _make_indexed_dispatch_simple, _make_indexed_dispatch_trampoline,
    _make_groundness_dispatch_simple, _make_groundness_dispatch_trampoline,
    _make_call_site_bucket_trampoline,
)
from .compile_ctx import CompilationContext
from .strategy import ShallowStrategy, TrampolineStrategy
from .goal_shallow import (
    compile_body, _make_body_compiler,
)
from .goal_trampoline import (
    compile_body_trampoline, _make_body_compiler_trampoline,
    _inject_bucket_refs_trampoline,
    _yield_step_stmt,
)
# ── Phase 0.5a hoisted runtime-helper aliases ────────────────────────────────
# ``base_globals`` of compiled predicates references these runtime helpers by
# name.  The imports below bind each name as a module global in this file, so
# ``base_globals[name] = <name>`` picks them up at dict-construction time.
#
# Multiple aliases for the same symbol (e.g. ``_DictTerm_t`` vs ``_DictTerm_s``
# for trampoline vs shallow) are preserved verbatim — the trampoline and
# shallow ``base_globals`` dicts below bind different keys to the same
# underlying function, and downstream optimisations (per-strategy evolution
# of the bound function) could diverge the two aliases.  Keeping the aliases
# costs nothing and preserves optionality.
#
# History: these were previously bulk-copied out of ``_monolith`` via
# ``for _n in dir(_m): globals().setdefault(_n, getattr(_m, _n))``.  Slice B1a
# of the migration (see ``implementation_plans/SLICE_B_PROGRESS.md``) inlined
# them here so the bulk-copy hack could be retired.

from fractions import Fraction  # noqa: F401 — referenced as _Fraction
import sys as _sys  # noqa: F401
import warnings  # noqa: F401
from collections import defaultdict  # noqa: F401

from clausal.terms import DictTerm, SetTerm, KWTerm, PyThunk  # noqa: F401
_DictTerm = DictTerm
_SetTerm = SetTerm
_PyThunk = PyThunk
_KWTerm = KWTerm
_KWTerm_t = KWTerm
_DictTerm_t = DictTerm
_SetTerm_t = SetTerm
_DictTerm_s = DictTerm
_SetTerm_s = SetTerm

from clausal.pythonic_ast.nodes import (  # noqa: F401
    SetLiteral as _SetLiteral,
    Call as AstCall,
    LoadName as AstLoadName,
    Keyword as KWNode,
)
_SL = _SetLiteral
_SetLiteral_t = _SetLiteral

from clausal.logic.builtins.lists import (  # noqa: F401
    _append_dr__3 as _dr_append_fn,
)
from clausal.logic.builtins.dict_set import (  # noqa: F401
    _dict_put_dr__4 as _dr_dict_put_fn,
    _set_union_dr__3 as _dr_set_union_fn,
)

from clausal.logic.constraints import (  # noqa: F401
    dif as _dif_fn,
    reify_eq as _reify_eq_fn,
    structural_eq as _structural_eq_fn,
    structural_neq as _structural_neq_fn,
)
_dif_fn_s = _dif_fn
_reify_eq_fn_s = _reify_eq_fn

from clausal.logic.clpfd import (  # noqa: F401
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

from clausal.logic.exceptions import (  # noqa: F401
    LogicException as _LogicException_cls,
    python_error_term as _python_error_term_fn,
    type_error as _type_error_fn,
)
_python_error_term_fn_s = _python_error_term_fn
_type_error_fn_s = _type_error_fn

from clausal.logic.variables import (  # noqa: F401
    get_attr as _get_attr_fn,
    put_attr as _put_attr_fn,
)
_get_attr_fn_s = _get_attr_fn
_put_attr_fn_s = _put_attr_fn

from clausal.logic.coroutining import (  # noqa: F401
    _install_when_ground as _install_when_ground_fn,
    _install_when_disjunction as _install_when_disjunction_fn,
    _install_when_condition as _install_when_condition_fn,
)
_install_when_ground_fn_s = _install_when_ground_fn
_install_when_disjunction_fn_s = _install_when_disjunction_fn
_install_when_condition_fn_s = _install_when_condition_fn

from clausal.logic.tabling import (  # noqa: F401
    _naf_tabled as _naf_tabled_fn,
    _TABLING_SUSPEND,
)
_naf_tabled_fn_s = _naf_tabled_fn

# ── TRO (moved to .tro) ─────────────────────────────────────────────────────
from .tro import (  # noqa: E402,F401
    _is_deterministic_goal,
    _tro_args_safe,
    _head_has_unifying_list_pattern, _list_has_nonvar_constant,
    _contains_star_unpack,
    _compile_tro_tail,
)


# ── Injected runtime builtins (name-referenceable in compiled bodies) ────────
#
# ``term_to_ast_expr`` can emit a *bare Name* for a runtime value (not just a
# module-declared predicate): the term-constructor helpers ``Var``/``Compound``/
# ``DictTerm``/``SetTerm``/``KWTerm``, the Kleene ``Unknown`` singleton, and any
# ``is_term_instance`` runtime type referenced as ``Cls(...)`` — e.g. ``Quantity``,
# a ``PyThunk``/``FStringThunk`` wrapper, or a CLP(B) ``BoolEq``/``BoolImpl``.
# Inside a *module clause* these names resolve because the module namespace has
# been seeded with ``predicate_builtins`` (see clausal/import_hook.py).  A *bare
# query*, however, derives its compiled globals only from ``module.module_dict``
# (clausal/logic/solve.py::_compile_as_query), which need not carry those
# injections — so a name that compiles fine in a module clause could raise a
# ``NameError`` in a query.  Commit 999ed1cb papered over the one case that had
# surfaced (``Unknown``) by baking ``"Unknown": Unknown`` into both base_globals
# dicts; this dict is the generic fix — every base_globals below is seeded from
# it, so a future injected runtime binding cannot silently regress the query
# path.
#
# CRITERION — what belongs here (and why NOT the full ``predicate_builtins``):
# ``predicate_builtins`` also maps ALL of ``simple_ast.__all__`` (``Call``,
# ``Module``, ``If``, ``For``, ``Lt`` … plus ``assertz``/``dump``/``simplify`` …)
# under their PUBLIC names.  Seeding those into base_globals would *reserve* them,
# so a user predicate ``call/1`` or ``module/2`` etc. would be shadowed — the
# exact A12-F004 class of bug (see the walk/deref/unify note in import_hook.py),
# which is why base_globals is a curated dict rather than a union.  This dict is
# therefore restricted to the manually-injected runtime *value* bindings that the
# compiler can emit under a public name; the engine internals walk/deref/unify are
# injected ``$``-prefixed ONLY (below) so those public names stay free for users.
# ``globals_`` (the module/query dict) is still layered on top of base_globals at
# the call sites, so a module-declared name always wins on collision.
from clausal.logic.variables import Trail as _Trail, walk as _walk_fn  # noqa: E402
from clausal.terms import (  # noqa: E402
    Quantity as _Quantity,
    FStringThunk as _FStringThunk,
)
from clausal.logic.clpb import BoolEq as _BoolEq, BoolImpl as _BoolImpl  # noqa: E402

INJECTED_RUNTIME_BUILTINS: dict = {
    # Term-constructor helpers and runtime types emitted as bare Names by
    # term_to_ast_expr.  ``$``-prefixed engine internals below can never be
    # shadowed by user identifiers (``$`` is not a legal identifier char).
    "PredicateMeta": PredicateMeta,
    "Var": Var,
    "Compound": Compound,
    "DictTerm": _DictTerm,
    "SetTerm": _SetTerm,
    "KWTerm": _KWTerm,
    "Trail": _Trail,
    "PyThunk": _PyThunk,
    "FStringThunk": _FStringThunk,
    "Quantity": _Quantity,
    "Unknown": Unknown,
    "BoolEq": _BoolEq,
    "BoolImpl": _BoolImpl,
    # Engine internals — public names walk/deref/unify are deliberately NOT
    # bound (A12-F004); generated code references them ``$``-prefixed.
    "$walk": _walk_fn,
    "$deref": deref,
    "$unify": unify,
    "$ast": ast,
    # By-identity atom reference (``$atom(<token>)``): an atom that reached the
    # compiler as a live object must NOT be re-resolved by name in whatever
    # globals the generated code runs under.  See
    # ``terms_to_ast.atom_identity_expr``.
    "$atom": _atom_by_id,
}


def _sweep_tro_eligible(
    clauses: list,
    functor: str,
    arity: int,
    db,
    ctx_template: CompilationContext,
) -> frozenset[int]:
    """Slice E6d-β: TRO eligibility sweep via the uniform ``analyse`` pass.

    Builds each clause's body IR via :func:`terms_to_goalop` once, runs
    :func:`optimisations.tro.analyse`, and stashes both the IR and the
    resulting :class:`TROPlan` on *ctx_template* (keyed by ``id(clause)``)
    so later stages can reuse them:

    - :func:`_compile_body_impl` reads ``ctx.clause_ir_cache`` to skip a
      second :func:`terms_to_goalop` build.
    - The TRO-aware ``body_compiler`` wrapper in
      :func:`_build_predicate_trampoline_funcdef` reads
      ``ctx.clause_tro_plans`` instead of re-running analysis.

    Slice D7c-β1 closed the last IR subset gap, so every clause body
    the compiler accepts converts — a :class:`NotImplementedError`
    from :func:`terms_to_goalop` now signals a genuine compiler bug
    and propagates.

    Returns the frozenset of TRO-eligible clause indices.
    """
    from .terms_to_goalop import terms_to_goalop
    from .optimisations.tro import analyse as _tro_analyse
    if ctx_template.clause_ir_cache is None:
        ctx_template.clause_ir_cache = {}
    if ctx_template.clause_tro_plans is None:
        ctx_template.clause_tro_plans = {}
    eligible: list[int] = []
    for i, clause in enumerate(clauses):
        body_ir = terms_to_goalop(clause.body, db=db)
        ctx_template.clause_ir_cache[id(clause)] = body_ir
        plan = _tro_analyse(body_ir, clause.head, functor, arity, db=db)
        ctx_template.clause_tro_plans[id(clause)] = plan
        if plan.eligible:
            eligible.append(i)
    return frozenset(eligible)


def _node_has_own_yield(node: ast.AST) -> bool:
    """True if *node* contains a ``yield``/``yield from`` in its OWN scope
    (not inside a nested function/lambda, whose yields don't make the outer a
    generator)."""
    if isinstance(node, (ast.Yield, ast.YieldFrom)):
        return True
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return False  # nested scope — its yields belong to that function
    return any(_node_has_own_yield(c) for c in ast.iter_child_nodes(node))


def _stmts_force_generator(stmts: list[ast.stmt]) -> list[ast.stmt]:
    """Ensure *stmts* form a generator body (A03-F003).

    A funcdef with no top-level ``yield`` compiles to a plain function that
    returns ``None`` — an index bucket whose clauses are ALL signal-mode TRO
    clauses (prefix goals + _tro_state stores + early ``return``, no yield)
    then raises ``'NoneType' object is not iterable`` on first dispatch. Only
    the empty-body case was handled before. Append the unreachable
    ``return None; yield None`` tail whenever no own-scope yield is present."""
    if any(_node_has_own_yield(s) for s in stmts):
        return stmts
    return list(stmts) + [
        ast.Return(value=ast.Constant(value=None)),
        ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
    ]


def _empty_predicate_funcdef(
    functor: str,
    arity: int,
    db: "Database | None",
    strategy,
) -> ast.FunctionDef:
    """AST for a predicate that matches any args but never yields.

    Strategy-driven: parameter layout comes from
    ``strategy.function_params``; tail yield comes from
    ``strategy.emit_exhaustion_yield`` (trampoline's DONE yield) or the
    ``return; yield None`` idiom (shallow — needs it to make the
    function a generator type at all).
    """
    _params_ctx = CompilationContext(
        db=db, var_context={}, trail_name=_TRAIL_PARAM_NAME, strategy=strategy,
    )
    arg_names = [f"arg{i}" for i in range(arity)]
    params = strategy.function_params(_params_ctx, arg_names)
    exhaust = strategy.emit_exhaustion_yield(_params_ctx)
    if exhaust is not None:
        body: list[ast.stmt] = [exhaust]
    else:
        body = [
            ast.Return(value=ast.Constant(value=None)),
            ast.Expr(value=ast.Yield(value=ast.Constant(value=None))),
        ]
    func_def = ast.FunctionDef(
        name=f"{functor}__{arity}",
        args=ast.arguments(
            posonlyargs=[], args=[ast.arg(arg=p) for p in params],
            vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
        ),
        body=body,
        decorator_list=[], returns=None, type_comment=None,
        **_EXTRA_FUNCDEF,
    )
    stamp_predicate_funcdef(func_def, ())  # empty predicate — synthetic
    maybe_assert_located(func_def)
    return func_def


def _build_predicate_trampoline_funcdef(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
    emit_done: bool = True,
    tro_indices: frozenset[int] | None = None,
    skip_trail: bool = False,
    ctx_template: CompilationContext | None = None,
) -> ast.FunctionDef:
    """Build the ``ast.FunctionDef`` for a trampoline-protocol compiled predicate.

    Returns the fixed-up FunctionDef without executing it.  Used by both
    ``compile_predicate_trampoline`` and ``compile_predicate_trampoline_ast``.

    when *emit_done* is False the trailing ``yield (parent, DONE)`` is
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
    # ctx_template carries the per-compilation ``FreshNames``.  Callers
    # from ``compile_predicate_trampoline`` pass the outer template so
    # every TRO-tail helper draws from the same monotonic counter;
    # ``compile_predicate_trampoline_ast`` and tests that call this
    # builder directly get a fresh template.
    if ctx_template is None:
        ctx_template = CompilationContext(
            db=db, var_context={}, trail_name=_TRAIL_PARAM_NAME,
            strategy=TrampolineStrategy(),
        )
    arg_names = [f"arg{i}" for i in range(arity)]
    params = ctx_template.strategy.function_params(ctx_template, arg_names)

    # Statements that go inside the TRO while-loop (or directly in the func body).
    loop_stmts: list[ast.stmt] = []

    if clauses and arity > 0:
        # Deref each argument once into a local before the clause match arms.
        deref_names = [f"_d{i}" for i in range(arity)]
        for i, arg in enumerate(arg_names):
            loop_stmts.append(_assign(deref_names[i], _call(_name("$deref"), _name(arg))))
        subject = ast.Tuple(elts=[_name(n) for n in deref_names], ctx=ast.Load())
    else:
        subject = ast.Tuple(
            elts=[_call(_name("$deref"), _name(n)) for n in arg_names],
            ctx=ast.Load(),
        )

    if use_tro and tro_mode == "loop":
        # Initialise _tro flag at the top of each iteration.
        loop_stmts.append(_assign("_tro", ast.Constant(False)))

    # Slice E6c: TRO-aware body_compiler wrapper.  When the clause is
    # in ``tro_indices``, stash a :class:`TROPlan` and ``tro_mode`` on
    # ``ctx_template`` (captured by reference inside the underlying
    # closure) before invoking the real body_compiler; the
    # ``_compile_body_impl`` TRO branch then splits prefix/tail and
    # emits ``_compile_tro_tail`` as the leaf.  Replaces the legacy
    # ``_compile_tro_body`` bypass entirely.
    if use_tro:
        _tro_clause_set = {id(clauses[i]) for i in tro_indices}
        _orig_bc = body_compiler
        _tro_m = tro_mode
        _tro_ctx = ctx_template

        def _tro_aware_bc(clause, var_context,
                          _tset=_tro_clause_set, _tm=_tro_m, _ctx=_tro_ctx):
            if id(clause) in _tset:
                # Slice E6d-β: plan was built by ``_sweep_tro_eligible``;
                # ``id(clause) in _tset`` implies ``plan.eligible`` is True.
                _plan = _ctx.clause_tro_plans[id(clause)]
                _prev_plan = _ctx.tro_plan
                _prev_mode = _ctx.tro_mode
                _ctx.tro_plan = _plan
                _ctx.tro_mode = _tm
                try:
                    return _orig_bc(clause, var_context)
                finally:
                    _ctx.tro_plan = _prev_plan
                    _ctx.tro_mode = _prev_mode
            return _orig_bc(clause, var_context)
        body_compiler = _tro_aware_bc

    # Phase 5: structural dispatch for list-discriminating predicates.
    dispatch_pos = (
        _find_list_dispatch_pos(clauses, arity) if (clauses and arity > 0) else None
    )
    if dispatch_pos is not None:
        loop_stmts.extend(
            _build_list_dispatch_guard(
                clauses, dispatch_pos, arity, subject, body_compiler
            )
        )
    else:
        _head_globals = ctx_template.base_globals
        for ci, clause in enumerate(clauses):
            var_context: dict[int, str] = {}
            _head_arg_patterns(clause.head, var_context, arity, globals_=_head_globals)

            # Slice G5: scope head-match scaffolding (mark/undo, pattern
            # guards, unify calls) on the clause's own source position.
            # Without this the `_assign_mark`/`_undo_stmt` calls inside
            # ``compile_head_to_match_case`` emit at lineno=0.
            _push_position(getattr(clause, "position", None))
            try:
                body_stmts = body_compiler(clause, var_context)

                case_arm = compile_head_to_match_case(
                    head=clause.head,
                    body_stmts=body_stmts,
                    var_context=var_context,
                    arity=arity,
                    skip_trail=skip_trail,
                    globals_=_head_globals,
                )
            finally:
                _pop_position()
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
        # NOTE: _compile_tro_tail emits only the $tro_state stores — there is
        # NO per-arm early exit, so match arms AFTER a signalling TRO arm
        # still run with the flag set. If one of those arms re-enters the
        # same predicate, the nested dispatch resets the shared flag and the
        # pending tail call is dropped (lost solutions) — see
        # todo/tro-signal-flag-clobbered-by-later-match-arms.md.
        # The single flag check below runs after ALL match arms:
        loop_stmts.append(
            ast.If(
                test=ast.Subscript(
                    value=_name("$tro_state"), slice=ast.Constant(0), ctx=ast.Load(),
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
        exhaust = ctx_template.strategy.emit_exhaustion_yield(ctx_template)
        if exhaust is not None:
            all_stmts.append(exhaust)

    # A generator function needs at least one yield. Force it whenever the
    # body has no own-scope yield — empty body, or an all-signal-mode-TRO
    # bucket whose arm is prefix + tro-state stores + early return (A03-F003).
    all_stmts = _stmts_force_generator(all_stmts)

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
    # Slice F3+F4: Phase 6 post invariants — README §10 #3 and #4.
    # F3 (mark/undo paired) catches emitter regressions that allocate
    # a trail mark without consuming it, which would silently leak
    # trail entries on backtracking.  F4 (DONE yield) catches a
    # trampoline funcdef built with emit_done=True but missing the
    # terminal ``yield (parent, DONE)`` — without it the driver
    # loop never sees the termination signal and hangs.
    from .invariants import (
        assert_mark_undo_paired,
        assert_trampoline_done_yield_present,
    )
    assert_mark_undo_paired(func_def)
    if emit_done:
        assert_trampoline_done_yield_present(func_def)
    stamp_predicate_funcdef(func_def, clauses)
    maybe_assert_located(func_def)
    return func_def


def compile_predicate_trampoline(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: "Database | None" = None,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]] | None = None,
    globals_: dict | None = None,
    pred_cls: "PredicateMeta | None" = None,
    enabled_optimisations: "frozenset[str] | None" = None,
) -> Callable:
    """Compile all clauses into a trampoline tuple-protocol generator.

    Unlike ``compile_predicate`` (simple/short-stack), the generated function:

    - Takes ``this_generator, parent`` as first two arguments.
      ``StepGenerator`` wraps the function and passes itself as
      ``this_generator`` automatically.
    - At each solution: ``yield (parent, None)`` — suspends; the calling
      generator (via the trampoline) processes the solution, then resumes
      this generator to find more.
    - After all clauses exhausted: ``yield (parent, DONE)`` — signals
      end of search for this predicate.

    Sub-predicate calls within clause bodies use the coroutine-backtracking
    pattern::

        _gen  = StepGenerator(dispatch, this_generator, this_generator, this_generator, args, trail)
        _st   = (yield (_gen, None))
        while _st is not DONE:
            <continuation>
            _st = (yield (_gen, None))

    so the Python call stack does *not* grow with predicate recursion depth.

    Compiled function signature::

        def {functor}__{arity}(this_generator, parent, arg0, …, argN, trail):
            …              # clause match arms
            yield (parent, DONE)

    The trampoline (``clausal.logic.trampoline.trampoline``) drives execution
    via ``StepGenerator`` wrappers.
    """
    _effective_db = db if db is not None else _GlobalsDb(globals_ or {})

    # Ctx template: mutated below after base_globals analysis; captured
    # by reference inside body_compiler so mutations are visible at
    # per-clause compile time.
    ctx_template = CompilationContext(
        db=_effective_db, var_context={}, trail_name=_TRAIL_PARAM_NAME,
        strategy=TrampolineStrategy(),
    )
    # Slice E5b: per-optimisation toggle override.  ``None`` keeps the
    # ctx default (all-on); a frozenset narrows the enabled set so that
    # both the legacy bypasses (DR preprocess, ``_compile_tro_body``,
    # ``_inject_bucket_refs_trampoline``) and the IR-side analyses
    # short-circuit, surfacing un-optimised AST end-to-end.
    if enabled_optimisations is not None:
        ctx_template.enabled_optimisations = enabled_optimisations

    if body_compiler is None:
        body_compiler = _make_body_compiler_trampoline(
            _effective_db, ctx_template=ctx_template,
        )

    # Resolve pred_cls: explicit param > globals_ > auto-detect later.
    if pred_cls is None:
        pred_cls = (globals_ or {}).get(functor)
        if not isinstance(pred_cls, PredicateMeta):
            pred_cls = None

    if not clauses:
        fn = _compile_always_fail_trampoline(functor, arity)
        return _install(db, functor, arity, fn, pred_cls=pred_cls)

    base_globals: dict = {
        # Seed with the injected runtime builtins so every name term_to_ast_expr
        # can emit (Var/Compound/DictTerm/SetTerm/KWTerm, Unknown, Quantity,
        # PyThunk/FStringThunk, BoolEq/BoolImpl, plus $-prefixed engine helpers)
        # resolves even on the bare-query path — whose globals derive only from
        # the module dict, which need not carry the injections.  See
        # INJECTED_RUNTIME_BUILTINS above for the criterion.  ``globals_`` is
        # layered on top below, so a module-declared name still wins.
        **INJECTED_RUNTIME_BUILTINS,
        # A12-F004: generated bodies reference the engine helpers under the
        # reserved ``$``-prefix so a user predicate named unify/2 or deref/2
        # (which lands in the module dict and is merged in below) cannot shadow
        # them. The bare "unify"/"deref" keys are kept for backward compat with
        # any older cached bytecode but are not emitted by current codegen.
        "unify": unify,
        "deref": deref,
        "is_var": is_var,
        "StepGenerator": StepGenerator,
        "$DONE": DONE,
        "$dif": _dif_fn,
        "$reify_eq": _reify_eq_fn,
        "$structural_eq": _structural_eq_fn,
        "$structural_neq": _structural_neq_fn,
        "$reify_fd": _reify_fd_fn,
        "$fd_eq": _fd_eq_fn,
        "$fd_ne": _fd_ne_fn,
        "$fd_lt": _fd_lt_fn,
        "$fd_le": _fd_le_fn,
        "$fd_gt": _fd_gt_fn,
        "$fd_ge": _fd_ge_fn,
        "$head_list_unify_input": _head_list_unify_input,
        "$head_list_unify_output": _head_list_unify_output,
        "$head_multi_star_error": _head_multi_star_error,
        "$body_star_unify": _body_star_unify,
        "$body_multi_star_unify": _body_multi_star_unify,
        "$build_star_list": _build_star_list,
        "$build_multi_star_list": _build_multi_star_list,
        "$tramp_call": _tramp_call,
        "$dispatch_at": _dispatch_at,
        "$deref_walk": _deref_walk_fn,
        "$findall_copy": _findall_copy_row,
        "$set_of_dedup": _set_of_dedup,
        "$set_of_sort_dedup": _set_of_sort_dedup,
        "$LogicException": _LogicException_cls,
        "$python_error_term": _python_error_term_fn,
        "$in_iter": _in_iter,
        "$subscript": _subscript,
        "$splat_data": _splat_data,
        "$dict_key": _dict_key,
        "$type_error": _type_error_fn,
        "$get_attr": _get_attr_fn,
        "$put_attr": _put_attr_fn,
        "SegList": SegList,
        "SegString": SegString,
        "SegBytes": SegBytes,
        "ConcreteSeg": ConcreteSeg,
        "VarSeg": VarSeg,
        "$seglist_unify_gen": _seglist_unify_gen,
        "$Fraction": Fraction,
    }
    # Ensure freeze/when hooks are registered.
    base_globals["$install_when_ground"] = _install_when_ground_fn
    base_globals["$install_when_disjunction"] = _install_when_disjunction_fn
    base_globals["$install_when_condition"] = _install_when_condition_fn
    # WFS: inject $naf_tabled, $table_store, and $TABLING_SUSPEND for tabled NAF
    if db is not None:
        base_globals["$naf_tabled"] = _naf_tabled_fn
        base_globals["$table_store"] = db.table_store
        base_globals["$TABLING_SUSPEND"] = _TABLING_SUSPEND
    # Phase 6: single combined traversal replacing three separate walks.
    _head_types, _py_thunks, _call_targets = _collect_globals_info(clauses)
    base_globals.update(_head_types)
    base_globals.update(_py_thunks)
    if globals_:
        base_globals.update(globals_)
    # Phase 6+7: resolve targets and capture locked dispatch functions.
    _inject_resolved_targets(_call_targets, base_globals, db, globals_)
    # Slice F2: Phase 1 exit gate — README §10 invariant 2.  Lock in
    # the contract that every collected call target now has an entry
    # in base_globals (real predicate, BuiltinPredicate adapter,
    # _DbDispatchAdapter shim, or imported value).  Catches the
    # "db=None and no other resolution path" case where generated
    # code would NameError at runtime.
    from .invariants import assert_call_targets_resolved
    assert_call_targets_resolved(_call_targets, base_globals, db=db)
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
    base_globals[_disp_key("$dr_append__3", 3)] = _dr_append_fn
    base_globals[_disp_key("$dr_dict_put__4", 4)] = _dr_dict_put_fn
    base_globals[_disp_key("$dr_set_union__3", 3)] = _dr_set_union_fn


    # Phase 7: set compile context so _dispatch_call_trampoline can emit
    # cached dispatch names instead of fname._get_dispatch() for locked predicates.
    _locked_keys = frozenset(k for k in base_globals if k.startswith(_DISP_PREFIX))
    ctx_template.locked_dispatch_keys = _locked_keys
    ctx_template.base_globals = base_globals
    try:
        # Slice E6b: ``_inject_bucket_refs_trampoline`` retired.  The
        # IR-path per-body populator in ``goal_shallow.
        # _prepopulate_call_site_runtime`` now drives
        # ``ctx.bucket_ref_map`` / ``joint_bucket_ref_map`` and bucket
        # function injection into ``base_globals`` from
        # ``call_site.analyse`` output.  The legacy helper remains
        # importable for verification tests (``tests/
        # test_bucket_refs_ir_parallel.py``, D6c parity).
        pass
        # ── Groundness-keyed dispatch (V2-2, subsumes V2-1) ──────────────
        index_positions = _analyze_index_positions(clauses, arity)
        if index_positions:
            # TRO: detect tail-recursive clauses (same check as non-indexed path).
            # Gated on the strategy's ``supports_tro`` flag — see
            # ``compiler/strategy.py``.  Today only ``TrampolineStrategy``
            # supports TRO, which matches the reachable path here.
            _is_tabled = (
                db is not None and db.is_tabled(functor, arity)
            )
            _idx_tro_indices: frozenset[int] | None = None
            _tro_state_obj = None
            if (
                ctx_template.strategy.supports_tro and not _is_tabled
                and "tro" in ctx_template.enabled_optimisations
            ):
                _tro_set = _sweep_tro_eligible(
                    clauses, functor, arity, db, ctx_template,
                )
                if _tro_set:
                    _idx_tro_indices = _tro_set
                    # Shared mutable TRO state: [flag, arg0, arg1, ..., argN-1]
                    _tro_state_obj = [False] + [None] * arity
                    base_globals["$tro_state"] = _tro_state_obj

            # Compile fallback (all clauses, for when no arg is ground).
            # emit_done=False makes the fallback SIGNAL-mode TRO like the
            # buckets — the enclosing dispatch loop re-dispatches its tail
            # calls (arg_index.py groundness/joint/secondary TRO loops).
            fallback_def = _build_predicate_trampoline_funcdef(
                f"{functor}__all", arity, clauses,
                _effective_db, body_compiler, emit_done=False,
                tro_indices=_idx_tro_indices,
                ctx_template=ctx_template,
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
                ctx_template=ctx_template,
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
                ctx_template=ctx_template,
            )
                pos_default_fn = functiondef_to_function(ddef, globals_=base_globals)
                plans.append((pos, idx_dict, pos_default_fn))

            # Phase 10a: single-position bucket dicts are exposed on the
            # predicate class (as call-site-safe wrappers) AFTER the final
            # dispatch fn is built — see the _index_plans assignment below.
            _joint_exposed: tuple | None = None
            _hier_exposed: tuple | None = None

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
                ctx_template=ctx_template,
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
                ctx_template=ctx_template,
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
                ctx_template=ctx_template,
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
                ctx_template=ctx_template,
            )
                                level0_default_fn = functiondef_to_function(
                                    l0ddef, globals_=base_globals)
                            else:
                                level0_default_fn = _compile_always_fail_trampoline(
                                    functor, arity)
                            fn = _make_secondary_dispatch_trampoline(
                                sec, level0_compiled, level0_default_fn,
                                fallback_fn, DONE,
                                tro_state=_tro_state_obj, arity=arity)
                            # Phase 10a: hierarchical bucket dicts exposed
                            # at the single choke point below (with the
                            # tabled gate and staleness clearing).
                            _hier_exposed = ((pos_i, pos_j), level0_compiled)
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
                ctx_template=ctx_template,
            )
                            joint_dict[jk] = functiondef_to_function(
                                jbdef, globals_=base_globals)
                        # joint default (either arg var)
                        if joint_info["defaults"]:
                            jddef = _build_predicate_trampoline_funcdef(
                                f"{functor}__j{pos_i}_{pos_j}_dflt",
                                arity, joint_info["defaults"],
                                _effective_db, body_compiler, emit_done=False,
                ctx_template=ctx_template,
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
                        # Phase 10a: joint bucket dict exposed (wrapped)
                        # after the final dispatch fn is built, below.
                        _joint_exposed = ((pos_i, pos_j), joint_dict)
            if fn is None:
                fn = _make_groundness_dispatch_trampoline(
                    plans, fallback_fn, DONE,
                    tro_state=_tro_state_obj, arity=arity)

            # Phase 10a: expose bucket dicts on the predicate class so that
            # call-site specialisation can look up bucket functions for
            # statically-known argument values without invoking the dispatch
            # closure at runtime.  Call sites drive these DIRECTLY via
            # StepGenerator, so each SIGNAL-mode bucket is wrapped to
            # complete the trampoline contract (terminal DONE yield + TRO
            # re-dispatch through the full dispatch fn).
            #
            # Tabled predicates are NEVER exposed: their installed dispatch
            # is the tabling wrapper (make_tabled_wrapper_trampoline, added
            # after compilation), and a direct bucket ref would bypass it —
            # no answer dedup, no SLG suspension, wrong WFS/NAF semantics.
            # Empty plans here keep every bucket-ref walker (legacy inject,
            # call_site.analyse, the D6c shadow) consistently hint-free.
            if pred_cls is not None and _is_tabled:
                pred_cls._index_plans = {}
                pred_cls._index_plans_joint = {}
                pred_cls._index_plans_hierarchical = {}
            elif pred_cls is not None:
                pred_cls._index_plans = {
                    pos: {
                        key: _make_call_site_bucket_trampoline(
                            bfn, fn, DONE,
                            tro_state=_tro_state_obj, arity=arity)
                        for key, bfn in idx_dict.items()
                    }
                    for pos, idx_dict, _ in plans
                }
                # Joint/hierarchical always assigned — a recompile that no
                # longer selects the joint/secondary strategy must not leave
                # stale bucket dicts (wrapping the OLD clause set) behind.
                if _joint_exposed is not None:
                    _jpos, _jdict = _joint_exposed
                    pred_cls._index_plans_joint = {
                        _jpos: {
                            jk: _make_call_site_bucket_trampoline(
                                jfn, fn, DONE,
                                tro_state=_tro_state_obj, arity=arity)
                            for jk, jfn in _jdict.items()
                        }
                    }
                else:
                    pred_cls._index_plans_joint = {}
                # Hierarchical dicts stay RAW (level-0 entries are
                # (level1_fns, level1_default_fn) tuples, not drivable
                # bucket fns) — no walker consumes them for call-site
                # specialisation; exposure is informational only.
                if _hier_exposed is not None:
                    _hpos, _hdict = _hier_exposed
                    pred_cls._index_plans_hierarchical = {_hpos: _hdict}
                else:
                    pred_cls._index_plans_hierarchical = {}
        else:
            # Phase 10a: no indexing — clear any stale plan dicts from a
            # previous compilation (e.g. after retract reduced clause count
            # below the indexing threshold).
            if pred_cls is not None:
                pred_cls._index_plans = {}
                pred_cls._index_plans_joint = {}
                pred_cls._index_plans_hierarchical = {}

            # TRO: detect tail-recursive clauses with deterministic prefixes.
            # Disabled for tabled predicates (SLG has its own suspension
            # protocol) and gated on ``ctx_template.strategy.supports_tro``.
            _is_tabled = (
                db is not None and db.is_tabled(functor, arity)
            )
            tro_indices: frozenset[int] | None = None
            if (
                ctx_template.strategy.supports_tro and not _is_tabled
                and "tro" in ctx_template.enabled_optimisations
            ):
                _tro_set = _sweep_tro_eligible(
                    clauses, functor, arity, _effective_db, ctx_template,
                )
                if _tro_set:
                    tro_indices = _tro_set

            func_def = _build_predicate_trampoline_funcdef(
                functor, arity, clauses, _effective_db, body_compiler,
                tro_indices=tro_indices,
                ctx_template=ctx_template,
            )

            fn = functiondef_to_function(func_def, globals_=base_globals)
    except BareGoalVariableError as exc:
        # A clause body used a bare variable in goal position.  Re-raise
        # with the offending predicate's name so the load-time error
        # locates the clause for the author (todo/attvar-in-goal-position).
        if exc.predicate is None:
            raise BareGoalVariableError(
                exc.var, predicate=f"{functor}/{arity}"
            ) from None
        raise
    except BareGoalUnknownError as exc:
        # Bare ``Unknown`` in goal position — locate the clause by predicate
        # name (mirrors the BareGoalVariableError handling above).
        if exc.predicate is None:
            raise BareGoalUnknownError(predicate=f"{functor}/{arity}") from None
        raise
    finally:
        pass

    def _recompile_trampoline() -> Callable:
        if db is not None:
            next_clauses = db.clauses_for(functor, arity)
        else:
            next_clauses = pred_cls._clauses if pred_cls is not None else clauses
        return compile_predicate_trampoline(
            functor, arity, next_clauses, db,
            body_compiler=body_compiler, globals_=globals_, pred_cls=pred_cls,
        )

    # The installed function, not ``fn``: for a tabled predicate ``_install``
    # returns the SLG wrapper, and ``_recompile_trampoline``'s return value is
    # what ``_get_dispatch``/``db.get_dispatch`` put back on the class.
    return _install(
        db, functor, arity, fn,
        lazy_recompile=_recompile_trampoline, pred_cls=pred_cls,
    )


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
        return _empty_predicate_funcdef(functor, arity, db, TrampolineStrategy())
    return _build_predicate_trampoline_funcdef(functor, arity, clauses, db, body_compiler)


def _compile_always_fail_trampoline(functor: str, arity: int) -> Callable:
    """Trampoline variant: generator that immediately yields (_tramp_parent, DONE)."""
    func_def = _empty_predicate_funcdef(functor, arity, None, TrampolineStrategy())
    return functiondef_to_function(func_def, globals_={"$DONE": DONE})


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


# ── Argument indexing / dispatch builders (moved to .arg_index) ──────────────
from .arg_index import (  # noqa: E402,F401
    _INDEX_VAR, _INDEXABLE_TYPES, _INDEX_THRESHOLD, _JOINT_COVERAGE_THRESHOLD,
    _arg_to_index_key, _runtime_arg_key, _static_call_key,
    _bucket_key, _joint_bucket_key,
    _extract_arg_key, _extract_first_arg_key,
    _build_arg_index, _build_first_arg_index,
    _analyze_index_positions,
    _build_joint_arg_index, _analyze_joint_index_positions,
    _make_joint_dispatch_simple, _make_joint_dispatch_trampoline,
    _build_secondary_index,
    _make_secondary_dispatch_simple, _make_secondary_dispatch_trampoline,
    _make_indexed_dispatch_simple, _make_indexed_dispatch_trampoline,
    _make_groundness_dispatch_simple, _make_groundness_dispatch_trampoline,
)


# Shallow-path globals fallback.  ``compile_predicate_shallow`` builds a
# ``base_globals`` dict that head-pattern compilation needs to resolve
# imported-compound ``Call(LoadName(qualified))`` head terms to real
# classes.  Threading that dict through the ten ``_build_predicate_funcdef``
# call sites in compile_predicate_shallow would be noise; instead, the
# outer function stashes it here in a try/finally and the builder reads
# it as the default when no caller supplies an explicit override.  Module-
# level (not contextvar) is intentional — Python compilation runs on the
# importing thread, and the shallow compiler isn't reentrant from inside
# itself.  Re-entry from another module's compile would also be fine
# because both writes go through the same save/restore.
_CURRENT_SHALLOW_BASE_GLOBALS: "dict | None" = None


def _build_predicate_funcdef(
    functor: str,
    arity: int,
    clauses: list[Clause],
    db: Database,
    body_compiler: Callable[[Clause, dict[int, str]], list[ast.stmt]],
    skip_trail: bool = False,
    globals_: dict | None = None,
) -> ast.FunctionDef:
    """Build the ``ast.FunctionDef`` for a simple/short-stack compiled predicate.

    Returns the fixed-up FunctionDef without executing it.  Used by both
    ``compile_predicate`` (which then calls ``functiondef_to_function``) and
    ``compile_predicate_ast`` (which returns the FunctionDef directly).
    """
    if globals_ is None:
        globals_ = _CURRENT_SHALLOW_BASE_GLOBALS
    _shallow_strategy = ShallowStrategy()
    _params_ctx = CompilationContext(
        db=db, var_context={}, trail_name=_TRAIL_PARAM_NAME,
        strategy=_shallow_strategy,
    )
    arg_names = [f"arg{i}" for i in range(arity)]
    params = _shallow_strategy.function_params(_params_ctx, arg_names)

    all_stmts: list[ast.stmt] = []

    if clauses and arity > 0:
        # Deref each argument once into a local before the clause match arms.
        deref_names = [f"_d{i}" for i in range(arity)]
        for i, arg in enumerate(arg_names):
            all_stmts.append(_assign(deref_names[i], _call(_name("$deref"), _name(arg))))
        subject = ast.Tuple(elts=[_name(n) for n in deref_names], ctx=ast.Load())
    else:
        subject = ast.Tuple(
            elts=[_call(_name("$deref"), _name(n)) for n in arg_names],
            ctx=ast.Load(),
        )

    for clause in clauses:
        var_context: dict[int, str] = {}
        _head_arg_patterns(clause.head, var_context, arity, globals_=globals_)
        # Slice G5: scope head-match + body emission on clause position.
        _push_position(getattr(clause, "position", None))
        try:
            body_stmts = body_compiler(clause, var_context)
            case_arm = compile_head_to_match_case(
                head=clause.head,
                body_stmts=body_stmts,
                var_context=var_context,
                arity=arity,
                skip_trail=skip_trail,
                globals_=globals_,
            )
        finally:
            _pop_position()
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
    stamp_predicate_funcdef(func_def, clauses)
    maybe_assert_located(func_def)
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
    def _trampoline_wrapper(this_generator, _proceed, _fail, _catcher, *args):
        # args = (arg0, ..., argN, trail) in trampoline calling convention.
        for _ in shallow_fn(*args, None):   # k=None (shallow mode ignores k)
            yield (_proceed, None)
        yield (_fail, DONE)

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

    # Per-predicate ctx carrying shared state (locked_dispatch_keys etc.).
    # Populated below after base_globals analysis; body_compiler captures
    # this instance by reference and sees mutations at compile time.
    # (B1b: only locked_dispatch_keys migrates here for the shallow path.
    # bucket_ref_map / joint_bucket_ref_map still go through the thread-
    # local until B1c.)
    ctx_template = CompilationContext(
        db=_effective_db,
        var_context={},  # placeholder; per-clause dict is overlaid at compile time
        trail_name=_TRAIL_PARAM_NAME,
        strategy=ShallowStrategy(),
    )

    if body_compiler is None:
        body_compiler = _make_body_compiler(_effective_db, ctx_template=ctx_template)

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
        # See the trampoline base_globals above / INJECTED_RUNTIME_BUILTINS for
        # why these are seeded (name-referenceable injected runtime bindings that
        # must resolve on the bare-query path too).
        **INJECTED_RUNTIME_BUILTINS,
        # A12-F004: $-prefixed engine helpers for the shallow path (see the
        # trampoline base_globals above).
        "unify": unify,
        "deref": deref,
        "is_var": is_var,
        "$dif": _dif_fn_s,
        "$reify_eq": _reify_eq_fn_s,
        "$reify_fd": _reify_fd_fn_s,
        "$fd_eq": _fd_eq_fn_s,
        "$fd_ne": _fd_ne_fn_s,
        "$fd_lt": _fd_lt_fn_s,
        "$fd_le": _fd_le_fn_s,
        "$fd_gt": _fd_gt_fn_s,
        "$fd_ge": _fd_ge_fn_s,
        "$head_list_unify_input": _head_list_unify_input,
        "$head_list_unify_output": _head_list_unify_output,
        "$head_multi_star_error": _head_multi_star_error,
        "$body_star_unify": _body_star_unify,
        "$body_multi_star_unify": _body_multi_star_unify,
        "$build_star_list": _build_star_list,
        "$build_multi_star_list": _build_multi_star_list,
        "$tramp_call": _tramp_call,
        "$dispatch_at": _dispatch_at,
        "$deref_walk": _deref_walk_fn,
        "$findall_copy": _findall_copy_row,
        "$set_of_dedup": _set_of_dedup,
        "$set_of_sort_dedup": _set_of_sort_dedup,
        "$LogicException": _LogicException_cls,
        "$python_error_term": _python_error_term_fn_s,
        "$in_iter": _in_iter,
        "$subscript": _subscript,
        "$splat_data": _splat_data,
        "$dict_key": _dict_key,
        "$type_error": _type_error_fn_s,
        "$get_attr": _get_attr_fn_s,
        "$put_attr": _put_attr_fn_s,
        "SegList": SegList,
        "SegString": SegString,
        "SegBytes": SegBytes,
        "ConcreteSeg": ConcreteSeg,
        "VarSeg": VarSeg,
        "$seglist_unify_gen": _seglist_unify_gen,
        "$Fraction": Fraction,
    }
    # Ensure freeze/when hooks are registered.
    base_globals["$install_when_ground"] = _install_when_ground_fn_s
    base_globals["$install_when_disjunction"] = _install_when_disjunction_fn_s
    base_globals["$install_when_condition"] = _install_when_condition_fn_s
    # WFS: inject $naf_tabled and $table_store for tabled NAF
    if db is not None:
        base_globals["$naf_tabled"] = _naf_tabled_fn_s
        base_globals["$table_store"] = db.table_store
    # Phase 6: single combined traversal replacing three separate walks.
    _head_types, _py_thunks, _call_targets = _collect_globals_info(clauses)
    base_globals.update(_head_types)
    base_globals.update(_py_thunks)
    if globals_:
        base_globals.update(globals_)
    # Phase 6+7: resolve targets and capture locked dispatch functions.
    _inject_resolved_targets(_call_targets, base_globals, db, globals_)
    # Slice F2: Phase 1 exit gate — README §10 invariant 2.  Lock in
    # the contract that every collected call target now has an entry
    # in base_globals (real predicate, BuiltinPredicate adapter,
    # _DbDispatchAdapter shim, or imported value).  Catches the
    # "db=None and no other resolution path" case where generated
    # code would NameError at runtime.
    from .invariants import assert_call_targets_resolved
    assert_call_targets_resolved(_call_targets, base_globals, db=db)
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
    # ctx_template.locked_dispatch_keys is the single authoritative channel
    # — threaded via ctx through compile_body → compile_goal →
    # _compile_predicate_call → _dispatch_call_iter.
    _locked_keys = frozenset(k for k in base_globals if k.startswith(_DISP_PREFIX))
    ctx_template.locked_dispatch_keys = _locked_keys
    ctx_template.base_globals = base_globals
    global _CURRENT_SHALLOW_BASE_GLOBALS
    _saved_shallow_globals = _CURRENT_SHALLOW_BASE_GLOBALS
    _CURRENT_SHALLOW_BASE_GLOBALS = base_globals
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
    except BareGoalVariableError as exc:
        # Bare variable in goal position — locate the clause by predicate
        # name (mirrors compile_predicate_trampoline).
        if exc.predicate is None:
            raise BareGoalVariableError(
                exc.var, predicate=f"{functor}/{arity}"
            ) from None
        raise
    except BareGoalUnknownError as exc:
        if exc.predicate is None:
            raise BareGoalUnknownError(predicate=f"{functor}/{arity}") from None
        raise
    finally:
        _CURRENT_SHALLOW_BASE_GLOBALS = _saved_shallow_globals

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
        return _empty_predicate_funcdef(functor, arity, db, ShallowStrategy())
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
    func_def = _empty_predicate_funcdef(functor, arity, None, ShallowStrategy())
    return functiondef_to_function(func_def, globals_={})


def _install(
    db: "Database | None",
    functor: str,
    arity: int,
    fn: Callable,
    lazy_recompile: Callable | None = None,
    pred_cls: PredicateMeta | None = None,
) -> Callable:
    """Install fn as the compiled dispatch function.

    If ``db`` is provided, stores the dispatch fn via ``db.set_dispatch()``
    so that ``db.get_dispatch()`` works for test/non-PredicateMeta usage.

    If ``pred_cls`` is a PredicateMeta class, installs fn and lazy_recompile
    directly on the class so that ``pred_cls._get_dispatch()`` works.

    A ``-table``d predicate is installed *wrapped*, never raw.  This is the
    single choke point every recompile funnels through —
    ``assertz``/``asserta``/``retract`` in ``builtins/database_ops.py``, and the
    lazy recompile that ``_get_dispatch``/``db.get_dispatch`` trigger after
    those cleared the dispatch — and before this wrap lived here, each of them
    replaced the SLG wrapper with the raw compiled function.  A tabled
    predicate then lost answer dedup, and a *left-recursive* one lost
    termination outright: a program that answered before an ``assertz`` looped
    forever after it.  Load-time wrapping (import_hook / compiler_v2 step 6)
    still happens and is now a no-op, because ``ensure_tabled_wrapper`` is
    idempotent.

    ``fn`` is returned so that callers whose own return value feeds
    ``_dispatch_fn`` (the ``_recompile_*`` closures) propagate the wrapper
    rather than the raw function they compiled.
    """
    from clausal.logic.tabling import ensure_tabled_wrapper  # noqa: PLC0415
    wrapped = ensure_tabled_wrapper(db, functor, arity, fn)
    if wrapped is not fn:
        # Installing a freshly compiled dispatch for a tabled predicate means
        # the clause set its cached answers were derived from is gone, so the
        # table is stale by construction.  ``Database.assertz``/``retract``
        # abolish it themselves, but the ``retract/1`` builtin deletes straight
        # out of ``db._clauses`` and never calls them, and
        # ``PredicateMeta._assertz``/``_retract`` only clear the dispatch — both
        # then recompile through here.  Before the wrapper survived a recompile
        # this went unnoticed: the raw dispatch consulted no table, so a stale
        # entry could not be read back.
        db.abolish_table(functor, arity)
        fn = wrapped
    if db is not None:
        db.set_dispatch(functor, arity, fn, lazy_recompile=lazy_recompile)
    if pred_cls is not None and isinstance(pred_cls, PredicateMeta):
        pred_cls._dispatch_fn = fn
        if lazy_recompile is not None:
            pred_cls._lazy_recompile = lazy_recompile
    return fn

