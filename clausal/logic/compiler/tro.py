"""Tail Recursion Optimization (TRO) — compile-time analysis + rewrite.

When the last goal in a clause body is a self-recursive Call preceded
only by deterministic goals (at most one solution, no StepGenerator),
the recursive call can be replaced by argument reassignment + loop
restart.  This avoids allocating a new StepGenerator + generator
object per recursion depth.

The generated pattern wraps the clause match arms in ``while True:``
and uses a ``_tro`` flag + ``continue`` to restart when a TRO-eligible
clause fires.
"""

from __future__ import annotations

import ast
from typing import Any

from clausal.logic.variables import is_var, deref  # noqa: F401
from clausal.logic.meta_predicate import MetaArg as _MetaArg
from clausal.terms import (
    And, Or, Not,
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq, StructuralEq, StructuralNeq,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    Call, LoadName,
)
from clausal.pythonic_ast.nodes import StarUnpack, IfExpr, Lambda
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.cells import _cell_shape, cell_args
from clausal.logic.database import Clause, Database
from clausal.terms import PyThunk, DictTerm, SetTerm

from ._ast_helpers import (
    _name, _call, _attr, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt,
    _MARK_PREFIX, _TRAIL_PARAM_NAME,
    _PROCEED_PARAM_NAME, _FAIL_PARAM_NAME, _CATCHER_PARAM_NAME,
    _THIS_GEN_NAME,
)
from .compile_ctx import CompilationContext
from ._vars import _collect_var_ids, _collect_bound_vars
from .terms_to_ast import term_to_ast_expr
from .globals_env import _preallocate_body_vars
from .control_constructs import _hoist_lambda_args
from .goal_shallow import _compile_predicate_call_impl
from .goal_trampoline import (
    _step_expr, _yield_step_stmt, _assign_yield_step,
    _dispatch_call_trampoline,
)


# ── IR-side parallel analysis (Slice D6a) ────────────────────────────────────
#
# The IR module is imported function-locally inside the analysis helpers
# below.  ``tests/test_runtime_compiler_boundary`` deliberately scrubs
# ``sys.modules['clausal.logic.compiler.*']`` and re-imports to verify
# import-discipline; a module-level ``from . import ir as _ir`` would
# leave us holding stale class references after that scrub, while
# ``terms_to_goalop`` (imported lazily under ``_maybe_cross_check_ir``)
# would produce instances of the *new* IR classes — every ``isinstance``
# check would silently fall through.  The function-local pattern keeps
# both producer and consumer pinned to the current IR module instance.
#
# ``analyse_ir`` mirrors ``_detect_tro_clause`` + ``_get_tro_check_indices``
# but operates on a :class:`GoalOp` tree.  This is a verification-only
# shadow today (D6 option-1): the result is asserted equal to the legacy
# detector's by ``tests/test_tro_ir_parallel.py`` and is not yet wired
# into the compile pipeline.  When D7 promotes the IR path to primary,
# the SubCall hint write becomes the source of truth and the legacy
# term-walking detectors retire.
#
# The analysis does NOT re-derive the head/arg-safety logic — it reuses
# the existing ``_tro_args_safe`` and ``_head_has_unifying_list_pattern``
# helpers.  Those operate on raw ``head`` / argument terms; ``SubCall.args``
# carries the same terms (already normalised for kwargs by
# ``terms_to_goalop``), so the checks port over unchanged.


def _is_deterministic_op_ir(op: Any) -> bool:
    """IR equivalent of ``_is_deterministic_goal`` — pattern-match on
    :class:`GoalOp` rather than terms.  Mirrors the legacy decision
    table arm-for-arm so ``analyse_ir`` agrees with ``_detect_tro_clause``
    on every prefix-determinism judgement.

    Notes on parity:

    - ``True`` (identity) becomes an empty :class:`Sequence` (D5j); the
      ``Sequence`` arm below treats empty as deterministic.
    - ``False`` becomes :class:`Fail` (D5j) — deterministic.
    - ``PyThunk`` becomes :class:`PyThunkOp` (D5j) — deterministic.
    - ``Call(once|findall|throw|halt, ...)`` becomes a
      :class:`MetaCall` with the matching ``kind`` — the explicit set
      below mirrors the legacy ``name in {...}`` arm.
    - Other ``MetaCall`` kinds (``catch``, ``forall``, ``freeze``,
      ``when``, ``setup_call_cleanup``, ``call_cleanup``, ``call_nth``,
      ``count_all``) are non-deterministic in legacy and stay so here.
    - ``SubCall`` (general predicate call) is non-deterministic unless
      its ``(fname, arity)`` is in :data:`_DETERMINISTIC_BUILTINS` — same
      table the legacy arm consults.
    - :class:`ListPatternUnify` is the IR shape for star-list ``Unify``
      bodies; legacy treats ``Unify(...)`` as deterministic regardless
      of operand shape, so we do too.
    """
    from . import ir as _ir
    match op:
        case _ir.Unify() | _ir.Dif() | _ir.ArithEval() | _ir.FDCompare() \
                | _ir.StructuralEq() | _ir.ListPatternUnify() \
                | _ir.Fail() | _ir.PyThunkOp():
            return True
        case _ir.MemberIn(negate=neg):
            # A03-F001: positive membership (``X in L``) is NONdeterministic —
            # it generates members / succeeds once per matching occurrence
            # (even a ground list with duplicates). Only not_in (negate=True)
            # is semidet. Preceding a TRO tail call, a nondet prefix drops all
            # but the last prefix solution.
            return neg
        case _ir.Negate():
            return True
        case _ir.Branch():
            # A03-F001: a reified ``If`` explores BOTH arms when the condition
            # is undetermined at runtime — not statically provable as
            # single-solution, so the safe classification is nondeterministic.
            return False
        case _ir.Sequence(ops=ops):
            return all(_is_deterministic_op_ir(c) for c in ops)
        case _ir.Alternate():
            return False
        case _ir.MetaCall(kind=kind):
            return kind in _DETERMINISTIC_META_KINDS
        case _ir.SubCall(fname=fname, arity=arity):
            return (fname, arity) in _DETERMINISTIC_BUILTINS
    return False


# Subset of ``MetaKind`` that the legacy ``_is_deterministic_goal``
# treats as at-most-one-solution.  The remaining kinds (``catch``,
# ``forall``, ``freeze``, ``when``, ``setup_call_cleanup``,
# ``call_cleanup``, ``call_nth``, ``count_all``) are non-deterministic.
_DETERMINISTIC_META_KINDS: frozenset[str] = frozenset({
    # (not bagof/setof: they backtrack over the free-variable bags)
    "once", "findall", "throw", "halt",
})


def analyse_ir(
    ir: Any,
    head: Any,
    functor: str,
    arity: int,
) -> tuple[bool, frozenset[int]]:
    """IR-side TRO eligibility analysis.

    Returns ``(eligible, check_indices)`` where the first element matches
    ``_detect_tro_clause(functor, arity, clause)`` and the second matches
    ``_get_tro_check_indices(functor, arity, clause)`` (empty when not
    eligible, or when no prefix goals exist).

    Expects *ir* to be the body :class:`Sequence` produced by
    ``terms_to_goalop``.  An empty Sequence (no body — facts) returns
    ``(False, frozenset())``.
    """
    from . import ir as _ir
    if not isinstance(ir, _ir.Sequence) or not ir.ops:
        return (False, frozenset())

    last = ir.ops[-1]
    if not isinstance(last, _ir.SubCall):
        return (False, frozenset())
    if last.fname != functor or last.arity != arity:
        return (False, frozenset())

    prefix_ops = ir.ops[:-1]
    if not all(_is_deterministic_op_ir(op) for op in prefix_ops):
        return (False, frozenset())

    # Star-unpack guard (mirrors legacy ``_contains_star_unpack`` over
    # ``call_args``).  ``SubCall.args`` retains the original positional
    # term shape; kwarg normalisation by ``terms_to_goalop`` only
    # reorders, never wraps.
    if any(_contains_star_unpack(a) for a in last.args):
        return (False, frozenset())

    if _head_has_unifying_list_pattern(head):
        return (False, frozenset())

    # ``_tro_args_safe`` walks raw goal terms to find vars bound by
    # prefix ``Evaluate`` / ``Unify`` / ``And``.  We don't have those
    # raw terms on the IR side without a reverse map, so reconstruct
    # the bound-var set directly from the IR prefix using the matching
    # ``ArithEval`` / ``Unify`` arms.  The semantics are identical to
    # the legacy helper's per-goal scan.
    if not prefix_ops:
        safe, check = _tro_args_safe_ir(head, [], last.args, arity)
    else:
        safe, check = _tro_args_safe_ir(
            head, prefix_ops, last.args, arity, allow_head_vars=True,
        )
    if not safe:
        return (False, frozenset())
    return (True, check)


def _tro_args_safe_ir(
    head: Any,
    prefix_ops: list,
    tail_args: list,
    arity: int,
    allow_head_vars: bool = False,
) -> tuple[bool, frozenset[int]]:
    """IR equivalent of :func:`_tro_args_safe`.

    Same return contract; the only difference is how the bound-var set
    is collected — from :class:`Unify` / :class:`ArithEval` IR ops in
    *prefix_ops* (descending into :class:`Sequence` to mirror the legacy
    ``And`` recursion) rather than from raw ``Unify`` / ``Evaluate`` /
    ``And`` term nodes.
    """
    bound_var_ids: set[int] = set()
    for op in prefix_ops:
        _collect_bound_vars_ir(op, bound_var_ids)

    head_passthrough_ids: set[int] = set()
    all_head_var_ids: set[int] = set()
    for i, head_arg in enumerate(_head_args(head) or ()):
        _collect_var_ids(head_arg, all_head_var_ids)
        head_arg = deref(head_arg)
        if is_var(head_arg) and i < len(tail_args):
            tail_arg = deref(tail_args[i])
            if type(tail_arg) is _MetaArg:
                # A -meta_predicate position of a SELF-call: the head variable
                # passed through unchanged, wrapped for qualification.  The
                # qualification is idempotent -- the value was qualified when
                # the predicate was entered (every entry qualifies: compiled
                # call sites, call/N, solve.call), and an already-qualified
                # goal or a goal object is left as it is -- so for TRO it IS
                # the pass-through variable (roborev, 2026-09-25).
                tail_arg = deref(tail_arg.value)
            if is_var(tail_arg) and tail_arg._id == head_arg._id:
                head_passthrough_ids.add(head_arg._id)

    _check_positions: set[int] = set()
    for arg_idx, arg in enumerate(tail_args):
        arg_var_ids: set[int] = set()
        _collect_var_ids(arg, arg_var_ids)
        for vid in arg_var_ids:
            if vid in bound_var_ids:
                continue
            if vid in head_passthrough_ids:
                continue
            if allow_head_vars and vid in all_head_var_ids:
                _check_positions.add(arg_idx)
                continue
            return (False, frozenset())
    return (True, frozenset(_check_positions))


def _head_args(head):
    """The clause head's positional arguments, whatever shape it is.

    P2 (2026-09-19): a head is the functor-first CELL; the instance arm is
    the pre-flip shape and goes with the class in P4.  Returns None for a
    head this file has nothing to say about (a bare name, a ``Call``).
    """
    if _cell_shape(head)[0]:
        return list(cell_args(head))
    if is_term_instance(head):
        return [getattr(head, f) for f in term_field_names(head)]
    return None


def _collect_bound_vars_ir(op: Any, out: set[int]) -> None:
    """IR equivalent of the per-goal scan inside :func:`_tro_args_safe`.

    Mirrors the legacy ``Evaluate(left=lhs)`` / ``Unify(left, right)``
    arms.  :class:`Sequence` recurses (corresponds to the legacy
    ``And(left=l, right=r)`` arm calling ``_collect_bound_vars`` on each
    side).  Other op kinds bind nothing observable to TRO arg-safety.
    """
    from . import ir as _ir
    match op:
        case _ir.ArithEval(target=lhs):
            if is_var(lhs):
                out.add(lhs._id)
        case _ir.Unify(l=lhs, r=rhs):
            if is_var(lhs):
                out.add(lhs._id)
            if is_var(rhs):
                out.add(rhs._id)
        # Star-list unify (legacy ``Unify(left=[..,*x,..], right=acc2)``
        # or vice-versa).  ``terms_to_goalop`` normalises the star list
        # to ``star_side`` regardless of which side had the stars in
        # the source; ``other_side`` is then whatever was unified with
        # the pattern.  Legacy ``_tro_args_safe`` adds ``is_var(lhs)``
        # and ``is_var(rhs)`` at the top level — the star side is always
        # a list (never a top-level var), so only ``other_side`` is
        # relevant here.
        case _ir.ListPatternUnify(other_side=other):
            if is_var(other):
                out.add(other._id)
        case _ir.Sequence(ops=ops):
            for child in ops:
                _collect_bound_vars_ir(child, out)


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
        case NotIn():
            return True
        case in_():
            # A03-F001: positive membership is nondeterministic (mirror of the
            # IR-level MemberIn fix) — succeeds once per matching occurrence.
            return False
        # NAF — deterministic (succeeds or fails once)
        case Not():
            return True
        # Conjunction — deterministic if both sides are
        case And(left=l, right=r):
            return _is_deterministic_goal(l) and _is_deterministic_goal(r)
        # IfExpr — A03-F001: a reified If can explore both arms when the test
        # is undetermined; not guaranteed single-solution (mirror of Branch).
        case IfExpr():
            return False
        # once/findall — at most one result (bagof/setof backtrack over
        # the free-variable bags, so they are not here)
        case Call(func=LoadName(name=name)) if name in (
            "once", "findall",
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
    # (length/2 is not here: with an open list it enumerates.)
    ("last", 2), ("reverse", 2), ("flatten", 2),
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
    # A03-F001: atom_concat/3 (split mode enumerates all before/after splits)
    # and sub_atom/5 (enumerates matches) are NONdeterministic — removed. The
    # remaining entries are semidet in every mode.
    ("upcase_atom", 2), ("downcase_atom", 2),
})


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
    for i, head_arg in enumerate(_head_args(head) or ()):
        _collect_var_ids(head_arg, all_head_var_ids)
        head_arg = deref(head_arg)
        if is_var(head_arg) and i < len(tail_args):
            tail_arg = deref(tail_args[i])
            if type(tail_arg) is _MetaArg:
                # A -meta_predicate position of a SELF-call: the head variable
                # passed through unchanged, wrapped for qualification.  The
                # qualification is idempotent -- the value was qualified when
                # the predicate was entered (every entry qualifies: compiled
                # call sites, call/N, solve.call), and an already-qualified
                # goal or a goal object is left as it is -- so for TRO it IS
                # the pass-through variable (roborev, 2026-09-25).
                tail_arg = deref(tail_arg.value)
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
    for val in _head_args(head) or ():
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


# Locals set at the start of every activation (loop iteration / bucket call)
# of a predicate with a TRO clause: the trail length and the var-id floor
# there.  ``_compile_tro_tail`` hands them to ``trail.commit_fresh``.
_TRO_MARK_NAME = "_tro_mark"
_TRO_FLOOR_NAME = "_tro_floor"


def _compile_tro_tail(
    ctx: CompilationContext,
    tail_call: Call,
    arity: int,
    var_context: dict[int, str],
    db: Database,
    trail_name: str,
    tro_mode: str = "loop",
    check_indices: frozenset[int] | None = None,
    self_name: str = _THIS_GEN_NAME,
    proceed_name: str = _PROCEED_PARAM_NAME,
    fail_name: str = _FAIL_PARAM_NAME,
    catcher_name: str = _CATCHER_PARAM_NAME,
) -> list[ast.stmt]:
    """Compile TRO tail-call: snapshot new args, set TRO flag/state.

    The caller (``compile_head_to_match_case``) wraps this in
    ``try/finally: trail.undo(_mark)`` so trail cleanup is automatic.
    The restart is taken only when ``trail.commit_fresh`` confirms every
    trail entry of this activation is on a variable created within it (and
    drops them, keeping their bindings); otherwise the ordinary
    ``StepGenerator`` call is emitted inline -- see the comment at
    ``commit_cond`` below.

    *tro_mode*:

    - ``"loop"`` (default): set local ``_tro = True``.  The enclosing
      ``while True`` loop in the funcdef will reassign args and ``continue``.
    - ``"signal"``: set shared ``_tro_state[0] = True`` and store new arg
      values in ``_tro_state[1..N]``.  The dispatch closure will check
      ``_tro_state`` after the bucket generator finishes and re-dispatch.

    *check_indices*: if not None, a set of arg positions that need a runtime
    ``is_var()`` check.  when any checked arg is an unbound Var, the TRO
    flag is NOT set and execution falls back to a normal ``StepGenerator``
    call (emitted inline) -- the same fallback ``commit_fresh`` refusing
    takes.
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

    # Hoist any lambda arguments (reuse existing helper).  Overlay the
    # caller's ctx with this TRO tail's var_context / names — the shared
    # ``ctx.fresh`` generator is preserved by ``replace()``.
    _hoist_ctx = ctx.replace(
        db=db, var_context=var_context, trail_name=trail_name,
        self_name=self_name,
        proceed_name=proceed_name, fail_name=fail_name, catcher_name=catcher_name,
    )
    ordered_args, lambda_defs = _hoist_lambda_args(_hoist_ctx, ordered_args)

    stmts: list[ast.stmt] = list(lambda_defs)

    # Snapshot each new arg value (the loop reassigns the args from these).
    for i, arg in enumerate(ordered_args):
        arg_expr = term_to_ast_expr(arg, var_context, eval_arith=False)
        tro_name = f"_tro_arg{i}"
        stmts.append(_assign(tro_name, _call(_name("$deref"), arg_expr)))

    # Build the TRO-set statements.
    if tro_mode == "signal":
        # Signal mode: set _tro_state[0] = True, _tro_state[i+1] = _tro_arg_i
        tro_set_stmts: list[ast.stmt] = [
            ast.Assign(
                targets=[ast.Subscript(
                    value=_name("$tro_state"), slice=ast.Constant(0), ctx=ast.Store(),
                )],
                value=ast.Constant(True),
            ),
        ]
        for i in range(arity):
            tro_set_stmts.append(ast.Assign(
                targets=[ast.Subscript(
                    value=_name("$tro_state"), slice=ast.Constant(i + 1), ctx=ast.Store(),
                )],
                value=_name(f"_tro_arg{i}"),
            ))
    else:
        # Loop mode: set _tro = True
        tro_set_stmts = [_assign("_tro", ast.Constant(True))]

    # The in-place restart discards this activation's trail segment, so it
    # is taken only when ``trail.commit_fresh`` finds every entry since the
    # activation began is on a variable created within it (it then drops
    # those entries WITHOUT undoing them, so a binding reachable from a
    # tail argument -- ``X is H, p(f(X), T)`` -- survives).  An effect on
    # anything older -- a caller variable bound (``K is foo``), a dif or
    # CLP constraint posted on one (``K is not H``, ``K != 3``, ``K > 3``)
    # -- must stay undoable and visible to the caller, so that iteration
    # takes the ordinary StepGenerator call below instead.  Undoing the
    # segment unconditionally (the pre-2026-09-29 behaviour) silently lost
    # all of these: the snapshot of the tail arguments preserves only
    # their top-level values.
    commit_cond = _call(
        _attr(trail_name, "commit_fresh"),
        _name(_TRO_MARK_NAME), _name(_TRO_FLOOR_NAME),
    )
    # Runtime ground-check: if any checked arg is a Var, fall back to StepGenerator.
    # The commit test goes LAST: it mutates the trail when it succeeds.
    checks = [
        ast.UnaryOp(op=ast.Not(), operand=_call(_name("is_var"), _name(f"_tro_arg{i}")))
        for i in sorted(check_indices or ())
    ]
    checks.append(commit_cond)
    if len(checks) == 1:
        ground_cond = checks[0]
    else:
        ground_cond = ast.BoolOp(op=ast.And(), values=checks)

    # Fallback: normal StepGenerator call with captured _tro_arg values.
    arg_exprs = [_name(f"_tro_arg{i}") for i in range(arity)]
    fname = tail_call.func.name
    _fallback_ctx = ctx.replace(
        db=db, var_context=var_context, trail_name=trail_name,
        self_name=self_name,
        proceed_name=proceed_name, fail_name=fail_name, catcher_name=catcher_name,
    )
    # A03-F001 (step 5): the StepGenerator call is built directly below;
    # the earlier _compile_predicate_call_impl() here was dead — its result
    # was unconditionally overwritten before use.
    call_expr = _dispatch_call_trampoline(_fallback_ctx, fname, arity, arg_exprs)
    gen_name = ctx.fresh("_gen")
    status_name = ctx.fresh("_st")
    gen_assign = _assign(gen_name, call_expr)
    first_step = _assign_yield_step(status_name, _name(gen_name), ast.Constant(None))
    loop_body = [
        _yield_step_stmt(_name(proceed_name), ast.Constant(None)),
        _assign_yield_step(status_name, _name(gen_name), ast.Constant(None)),
    ]
    fallback_loop = ast.While(
        test=ast.Compare(
            left=_name(status_name),
            ops=[ast.IsNot()],
            comparators=[_name("$DONE")],
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

    return stmts

