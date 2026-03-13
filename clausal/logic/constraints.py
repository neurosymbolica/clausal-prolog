"""clausal.logic.constraints — constraint solvers for attributed variables.

Implements dif/2 (disequality constraint) using the AttVar infrastructure
from the C extension.  When ``dif(x, y, trail)`` is called on two terms that
*could* become equal (neither structurally incompatible nor already identical),
a constraint pair ``(x, y)`` is attached to every free variable in both terms.
When any of those variables is later bound, the ``_dif_hook`` re-evaluates the
constraint and either drops it (satisfied), re-attaches it (still pending), or
fails (violated).
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import (
    Var,
    deref,
    is_var,
    unify_with_occurs_check,
    put_attr,
    get_attr,
    register_attr_hook,
    Trail,
)
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
from clausal.terms import Compound


DIF_KEY = "dif"


# ── Free-variable collector ──────────────────────────────────────────────────


def _collect_free_vars(term: Any) -> list:
    """Collect all unbound Vars reachable from *term*.

    Returns a list of unique Var objects (deduplicated by identity).
    """
    seen_ids: set[int] = set()
    result: list = []

    def _walk(t: Any) -> None:
        t = deref(t)
        if is_var(t):
            tid = id(t)
            if tid not in seen_ids:
                seen_ids.add(tid)
                result.append(t)
            return
        if isinstance(t, (tuple, list)):
            for elem in t:
                _walk(elem)
            return
        if isinstance(t, Compound):
            for arg in t.args:
                _walk(arg)
            return
        if is_term_instance(t):
            for fname in term_field_names(t):
                _walk(getattr(t, fname))
            return

    _walk(term)
    return result


# ── Structural unify with occurs check ───────────────────────────────────────


def _structural_unify_oc(t1: Any, t2: Any, trail: Trail) -> bool:
    """Unify t1 and t2 structurally with occurs check.

    Handles Compound and PredicateMeta instances that the C extension's
    ``unify_with_occurs_check`` does not (it falls through to ``==``).
    """
    t1 = deref(t1)
    t2 = deref(t2)

    # Let the C extension handle Var, tuple, list, scalars.
    # But if both are Compound or PredicateMeta, recurse.
    if isinstance(t1, Compound) and isinstance(t2, Compound):
        if t1.functor != t2.functor or len(t1.args) != len(t2.args):
            return False
        for a1, a2 in zip(t1.args, t2.args):
            if not _structural_unify_oc(a1, a2, trail):
                return False
        return True

    if is_term_instance(t1) and is_term_instance(t2):
        t1_type = type(t1)
        t2_type = type(t2)
        if t1_type is not t2_type:
            return False
        fields = term_field_names(t1)
        for fname in fields:
            if not _structural_unify_oc(getattr(t1, fname), getattr(t2, fname), trail):
                return False
        return True

    if isinstance(t1, list) and isinstance(t2, list):
        if len(t1) != len(t2):
            return False
        for e1, e2 in zip(t1, t2):
            if not _structural_unify_oc(e1, e2, trail):
                return False
        return True

    # Fall through to C extension for Var/scalar/tuple.
    return unify_with_occurs_check(t1, t2, trail)


# ── Core dif ─────────────────────────────────────────────────────────────────


def dif(x: Any, y: Any, trail: Trail) -> bool:
    """Disequality constraint: succeed iff *x* and *y* can remain different.

    - Ground & structurally incompatible → True (immediately satisfied).
    - Identical (same var, or ground-equal with no bindings) → False.
    - Otherwise → attach constraint to free vars and return True.
    """
    x = deref(x)
    y = deref(y)

    mark = trail.mark()
    unified = _structural_unify_oc(x, y, trail)

    if not unified:
        trail.undo(mark)
        return True

    trail_grew = (len(trail) != mark)

    if not trail_grew:
        # No bindings made → terms already identical (e.g. dif(X, X) or dif(1, 1)).
        return False

    trail.undo(mark)

    # Collect free vars and attach constraint.
    free_vars = _collect_free_vars(x) + _collect_free_vars(y)
    seen: set[int] = set()
    unique_vars: list = []
    for v in free_vars:
        vid = id(v)
        if vid not in seen:
            seen.add(vid)
            unique_vars.append(v)

    pair = (x, y)
    for v in unique_vars:
        existing = get_attr(v, DIF_KEY)
        if existing is None:
            put_attr(v, DIF_KEY, [pair], trail)
        else:
            existing.append(pair)

    return True


# ── Attribute hook ───────────────────────────────────────────────────────────


def _dif_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when an AttVar with dif constraints is unified.

    *attr_value* is the list of ``(x, y)`` constraint pairs.
    *bound_to* is the value the variable was bound to.

    Returns True if all constraints survive; False if any is violated.
    """
    constraints = attr_value
    for pair in constraints:
        x, y = pair
        x = deref(x)
        y = deref(y)

        mark = trail.mark()
        unified = _structural_unify_oc(x, y, trail)

        if not unified:
            trail.undo(mark)
            continue

        trail_grew = (len(trail) != mark)

        if not trail_grew:
            return False

        trail.undo(mark)

        remaining = _collect_free_vars(x) + _collect_free_vars(y)
        seen: set[int] = set()
        unique_remaining: list = []
        for v in remaining:
            vid = id(v)
            if vid not in seen:
                seen.add(vid)
                unique_remaining.append(v)

        for v in unique_remaining:
            existing = get_attr(v, DIF_KEY)
            if existing is None:
                put_attr(v, DIF_KEY, [pair], trail)
            else:
                if not any(p is pair for p in existing):
                    existing.append(pair)

    return True


register_attr_hook(DIF_KEY, _dif_hook)


# ── Reified equality ────────────────────────────────────────────────────────


def reify_eq(x: Any, y: Any, trail: Trail) -> bool | None:
    """Reified equality: three-valued decision procedure.

    Returns:
        True  — x and y are already identical (no bindings needed)
        False — x and y are structurally incompatible (cannot unify)
        None  — undetermined (unification possible but requires bindings)
    """
    x = deref(x)
    y = deref(y)

    # Fast path: identical objects (includes same Var)
    if x is y:
        return True

    mark = trail.mark()
    unified = _structural_unify_oc(x, y, trail)
    grew = (len(trail) != mark) if unified else False
    trail.undo(mark)

    if not unified:
        return False    # structurally incompatible
    if not grew:
        return True     # ground-equal, no bindings needed
    return None         # undetermined — needs exploration
