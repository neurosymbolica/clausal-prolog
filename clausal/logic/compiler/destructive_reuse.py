"""Destructive-reuse optimization for dead-source container args.

See the block comment below for the design rationale.  These helpers
are consumed by ``_make_body_compiler_trampoline`` (in ``.goal_trampoline``)
which flattens clause bodies, detects eligible goals, and rewrites them
in-place to call ``_dr_append__3`` / ``_dr_dict_put__4`` / ``_dr_set_union__3``
dispatch functions instead of the standard predicates.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import is_var, deref  # noqa: F401
from clausal.terms import (
    Compound,
    And, Or,
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq, StructuralEq, StructuralNeq,
    Lt, LtE, Gt, GtE,
    Call, LoadName,
)
from clausal.logic.database import Clause

from ._vars import _collect_var_ids


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


# ── IR-side eligibility analysis (source of truth since Slice E6d-β) ────────
#
# IR-module imports inside the analysis helpers are function-local because
# ``tests/test_runtime_compiler_boundary`` deliberately scrubs
# ``sys.modules['clausal.logic.compiler.*']`` mid-session; a module-level
# ``from . import ir as _ir`` would leave us holding stale class references
# after the scrub, while ``terms_to_goalop`` (re-imported on demand) would
# produce instances of the *new* IR classes — every ``isinstance`` check
# would silently fall through.


def analyse_ir(ir: Any, head: Any) -> set[int]:
    """Return indices into ``ir.ops`` of DR-eligible :class:`SubCall` ops.

    Walks the :class:`GoalOp` :class:`Sequence` produced by
    :func:`terms_to_goalop`; no pre-flattening is required since the IR
    builder already flattens ``And`` / list / ``TupleLiteral``.
    """
    from . import ir as _ir
    if not isinstance(ir, _ir.Sequence) or not ir.ops:
        return set()

    head_var_ids: set[int] = set()
    _collect_var_ids(head, head_var_ids)

    aliased_ids = _head_aliased_var_ids_ir(ir.ops, head_var_ids)

    from .tro import _is_deterministic_op_ir

    eligible: set[int] = set()
    ops = ir.ops
    for i, op in enumerate(ops):
        if not isinstance(op, _ir.SubCall):
            continue
        dr_info = _DR_CANDIDATES.get((op.fname, op.arity))
        if dr_info is None:
            continue
        source_idx = dr_info

        source_arg = deref(op.args[source_idx])
        if not is_var(source_arg):
            continue
        source_id = source_arg._id

        if source_id in aliased_ids:
            continue

        live_after: set[int] = set()
        for sop in ops[i + 1:]:
            _collect_op_var_ids(sop, live_after)
        if source_id in live_after:
            continue

        if not all(_is_deterministic_op_ir(ops[j]) for j in range(i)):
            continue

        eligible.add(i)
    return eligible


def _head_aliased_var_ids_ir(ops: list, head_var_ids: set[int]) -> set[int]:
    """IR equivalent of :func:`_head_aliased_var_ids`.

    Collects ``Var`` ↔ ``Var`` :class:`Unify` pairs from the top-level
    ops (descending into nested :class:`Sequence` to mirror the legacy
    ``And`` recursion in ``_collect_unify_pairs_from_and``), then takes
    the transitive closure with *head_var_ids* as seeds.  Other op
    kinds — including :class:`Alternate`, :class:`Branch`,
    :class:`Negate` arms — are not descended, matching the legacy
    helper which only handles ``Unify`` / ``And``.
    """
    aliased: set[int] = set(head_var_ids)
    pairs: list[tuple[int, int]] = []
    _collect_unify_pairs_ir(ops, pairs)
    changed = True
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


def _collect_unify_pairs_ir(ops: list, pairs: list[tuple[int, int]]) -> None:
    """Walk *ops* collecting ``Var`` ↔ ``Var`` :class:`Unify` pairs.

    Descends through nested :class:`Sequence` (post-D5 flattening
    leaves at most one level, but defensive recursion is cheap and
    matches legacy ``And`` recursion).
    """
    from . import ir as _ir
    for op in ops:
        match op:
            case _ir.Unify(l=l, r=r):
                l = deref(l)
                r = deref(r)
                if is_var(l) and is_var(r):
                    pairs.append((l._id, r._id))
            case _ir.Sequence(ops=child_ops):
                _collect_unify_pairs_ir(child_ops, pairs)


def _collect_op_var_ids(op: Any, ids: set[int]) -> None:
    """IR equivalent of ``_collect_var_ids`` invoked on a body goal.

    Walks every ``Term`` field carried by *op* and recurses into any
    child :class:`GoalOp` so the result captures all reachable
    variables — matching the legacy ``_collect_var_ids(subsequent_goal,
    live_after)`` call which descends through dataclass fields of the
    raw goal AST node.
    """
    from . import ir as _ir
    match op:
        case _ir.Unify(l=l, r=r) | _ir.Dif(l=l, r=r) \
                | _ir.FDCompare(l=l, r=r) | _ir.StructuralEq(l=l, r=r):
            _collect_var_ids(l, ids)
            _collect_var_ids(r, ids)
        case _ir.ArithEval(target=t, expr=e):
            _collect_var_ids(t, ids)
            _collect_var_ids(e, ids)
        case _ir.MemberIn(elem=e, collection=c):
            _collect_var_ids(e, ids)
            _collect_var_ids(c, ids)
        case _ir.SubCall(args=args):
            for a in args:
                _collect_var_ids(a, ids)
        case _ir.MetaCall(args=margs):
            for v in margs.values():
                if isinstance(v, _ir.GoalOp):
                    _collect_op_var_ids(v, ids)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, _ir.GoalOp):
                            _collect_op_var_ids(item, ids)
                        else:
                            _collect_var_ids(item, ids)
                elif v is not None:
                    _collect_var_ids(v, ids)
        case _ir.ListPatternUnify(star_side=ss, other_side=os):
            _collect_var_ids(ss, ids)
            _collect_var_ids(os, ids)
        case _ir.PyThunkOp(thunk=t):
            _collect_var_ids(t, ids)
        case _ir.Sequence(ops=child_ops) | _ir.Alternate(ops=child_ops):
            for child in child_ops:
                _collect_op_var_ids(child, ids)
        case _ir.Negate(op=child):
            _collect_op_var_ids(child, ids)
        case _ir.Branch(test=t, then=th, else_=e):
            _collect_op_var_ids(t, ids)
            _collect_op_var_ids(th, ids)
            _collect_op_var_ids(e, ids)
        case _ir.Fail():
            pass




