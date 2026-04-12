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
from . import _monolith as _m


def _is_deterministic_goal(goal):
    # Lazy accessor — _is_deterministic_goal lives in TRO (still in _monolith
    # until phase 16) and is defined after destructive_reuse is imported.
    return _m._is_deterministic_goal(goal)


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



