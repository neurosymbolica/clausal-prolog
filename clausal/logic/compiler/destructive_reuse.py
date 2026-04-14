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


def _is_deterministic_goal(goal):
    # Function-local import to break the cycle:
    # tro -> goal_trampoline -> destructive_reuse -> tro
    from .tro import _is_deterministic_goal as _impl
    return _impl(goal)


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

    _maybe_cross_check_ir(clause, eligible)
    return eligible


# ── IR-side parallel analysis (Slice D6b) ────────────────────────────────────
#
# ``analyse_ir`` mirrors :func:`_find_destructive_reuse_goals` over a
# :class:`GoalOp` :class:`Sequence`.  This is a verification-only shadow
# today (D6 option-1): the result is asserted equivalent to the legacy
# detector's by ``_maybe_cross_check_ir`` (gated by ``CLAUSAL_IR_PATH=1``)
# and is not yet wired into the compile pipeline.  When D7 promotes the
# IR path, the SubCall hint write becomes the source of truth and the
# legacy term-walking detector retires.
#
# IR-module imports inside the analysis helpers are function-local for
# the same reason as ``tro.analyse_ir`` (D6a) — the boundary test
# scrubs ``sys.modules['clausal.logic.compiler.*']`` mid-session.


def analyse_ir(ir: Any, head: Any) -> set[int]:
    """Return indices into ``ir.ops`` of DR-eligible :class:`SubCall` ops.

    Mirrors :func:`_find_destructive_reuse_goals` arm-for-arm but
    operates on a :class:`GoalOp` :class:`Sequence`.  ``ir.ops`` is
    already flat (``terms_to_goalop`` flattens ``And`` / list /
    ``TupleLiteral``); no additional flattening pass is required.
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


def _maybe_cross_check_ir(clause: Clause, legacy_eligible: set[int]) -> None:
    """Slice D6b parallel-implementation gate.

    Under ``CLAUSAL_IR_PATH=1``, run :func:`analyse_ir` against the IR
    built from ``clause.body`` and assert the two detectors pick out
    the same set of eligible :class:`SubCall` calls.  Index sets aren't
    directly comparable — legacy returns indices into the post-flatten
    body, IR returns indices into ``Sequence.ops`` — so both are
    canonicalised to the set of ``(fname, arity, occurrence#)`` triples
    where ``occurrence#`` ranks calls of that ``(fname, arity)`` by body
    order.

    ``terms_to_goalop`` failures (body shape outside the D5 subset) are
    a legitimate fallback and are silently skipped, mirroring D4 / D6a.
    """
    import os
    if os.environ.get("CLAUSAL_IR_PATH") != "1":
        return
    from .terms_to_goalop import terms_to_goalop
    try:
        ir = terms_to_goalop(clause.body, db=None)
    except NotImplementedError:
        return

    legacy_canon = _canonicalise_legacy(clause.body, legacy_eligible)
    ir_eligible = analyse_ir(ir, clause.head)
    ir_canon = _canonicalise_ir(ir, ir_eligible)
    if legacy_canon != ir_canon:
        raise AssertionError(
            "Slice D6b destructive_reuse IR-analysis disagreement — stop the line.\n"
            f"  legacy (fname,arity,occurrence): {sorted(legacy_canon)}\n"
            f"  ir     (fname,arity,occurrence): {sorted(ir_canon)}"
        )


def _canonicalise_legacy(
    body: list, eligible: set[int],
) -> set[tuple[str, int, int]]:
    """Project legacy indices to ``(fname, arity, occurrence#)`` triples."""
    flat = _flatten_and_goals(body)
    return _project_calls(flat, eligible, _flat_call_signature)


def _canonicalise_ir(
    ir: Any, eligible: set[int],
) -> set[tuple[str, int, int]]:
    """Project IR indices to ``(fname, arity, occurrence#)`` triples."""
    return _project_calls(ir.ops, eligible, _subcall_signature)


def _project_calls(seq, eligible, sig_fn):
    counts: dict[tuple[str, int], int] = {}
    out: set[tuple[str, int, int]] = set()
    for i, op in enumerate(seq):
        sig = sig_fn(op)
        if sig is None:
            continue
        occ = counts.get(sig, 0)
        counts[sig] = occ + 1
        if i in eligible:
            out.add((sig[0], sig[1], occ))
    return out


def _flat_call_signature(goal: Any) -> tuple[str, int] | None:
    g = deref(goal)
    if not isinstance(g, Call):
        return None
    f = g.func
    if not isinstance(f, LoadName):
        return None
    if (f.name, len(g.args)) not in _DR_CANDIDATES:
        return None
    return (f.name, len(g.args))


def _subcall_signature(op: Any) -> tuple[str, int] | None:
    from . import ir as _ir
    if not isinstance(op, _ir.SubCall):
        return None
    if (op.fname, op.arity) not in _DR_CANDIDATES:
        return None
    return (op.fname, op.arity)


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



