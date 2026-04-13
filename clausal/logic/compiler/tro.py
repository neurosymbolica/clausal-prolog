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
from clausal.terms import (
    Compound,
    And, Or, Not,
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq, StructuralEq, StructuralNeq,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    Call, LoadName,
)
from clausal.pythonic_ast.nodes import StarUnpack, IfExpr, Lambda
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.database import Clause, Database
from clausal.terms import PyThunk, DictTerm, SetTerm

from ._ast_helpers import (
    _name, _call, _assign, _assign_mark, _undo_stmt, _if,
    _yield_none_stmt,
    _MARK_PREFIX, _TRAIL_PARAM_NAME,
    _TRAMP_PARENT_NAME, _THIS_GEN_NAME,
)
from .compile_ctx import CompilationContext
from ._vars import _collect_var_ids, _collect_bound_vars
from .terms_to_ast import term_to_ast_expr
from .globals_env import _preallocate_body_vars
from .control_constructs import _hoist_lambda_args
from .goal_trampoline import (
    _compile_predicate_call_trampoline,
    _step_expr, _yield_step_stmt, _assign_yield_step,
    _dispatch_call_trampoline,
    _dispatch_goal_trampoline,
)


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
    ctx: CompilationContext,
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

    # Hoist any lambda arguments (reuse existing helper).  Overlay the
    # caller's ctx with this TRO tail's var_context / names — the shared
    # ``ctx.fresh`` generator is preserved by ``replace()``.
    _hoist_ctx = ctx.replace(
        db=db, var_context=var_context, trail_name=trail_name,
        self_name=self_name, parent_name=parent_name,
    )
    ordered_args, lambda_defs = _hoist_lambda_args(_hoist_ctx, ordered_args)

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
        _fallback_ctx = ctx.replace(
            db=db, var_context=var_context, trail_name=trail_name,
            self_name=self_name, parent_name=parent_name,
        )
        fallback_stmts = _compile_predicate_call_trampoline(
            _fallback_ctx, fname, [None] * arity, [],
            [_yield_step_stmt(_name(parent_name), ast.Constant(None))],
        )
        # Patch the arg expressions in the StepGenerator call to use _tro_arg values.
        # The simplest approach: build the call directly.
        call_expr = _dispatch_call_trampoline(_fallback_ctx, fname, arity, arg_exprs)
        gen_name = ctx.fresh("_gen")
        status_name = ctx.fresh("_st")
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

def _compile_tro_body(
    ctx: CompilationContext,
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
    # _dispatch_goal_trampoline find all Var names in var_context.
    alloc_stmts = _preallocate_body_vars(goals, var_context)

    # Compute runtime ground-check indices for head-decomposition vars.
    check_indices = _get_tro_check_indices(functor, arity, clause)

    # The innermost continuation is the TRO tail code (instead of yield solution).
    k = _compile_tro_tail(
        ctx, tail_call, arity, var_context, db, trail_name,
        tro_mode=tro_mode, check_indices=check_indices or None,
    )

    # Build prefix goals right-to-left, wrapping around the TRO tail.
    # Overlay ctx with this clause's var_context; the shared ``ctx.fresh``
    # is preserved so generated names stay monotonic within the compilation.
    prefix_ctx = ctx.replace(
        db=db, var_context=var_context, trail_name=trail_name,
        self_name=_THIS_GEN_NAME, parent_name=_TRAMP_PARENT_NAME,
    )
    for goal in reversed(prefix_goals):
        k = _dispatch_goal_trampoline(prefix_ctx, goal, k)
    return alloc_stmts + k


