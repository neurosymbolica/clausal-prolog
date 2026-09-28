"""clausal.logic.constraints — constraint solvers for attributed variables.

Implements dif/2 (disequality constraint) using the AttVar infrastructure
from the C extension.  when ``dif(x, y, trail)`` is called on two terms that
*could* become equal (neither structurally incompatible nor already identical),
a constraint pair ``(x, y)`` is attached to every free variable in both terms.
when any of those variables is later bound, the ``_dif_hook`` re-evaluates the
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
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import (
    SegList,
    SegString,
    SegBytes,
    DictTerm,
    SetTerm,
    Quantity,
    ConcreteSeg,
    VarSeg,
)


DIF_KEY = "dif"


# ── Structural equality (Prolog ==/2) ────────────────────────────────────────


def structural_eq(left: Any, right: Any) -> bool:
    """True iff *left* and *right* are identical after dereferencing.

    No variables are bound and no arithmetic evaluation is performed.
    Corresponds to Prolog's ``==/2``.

    Defined so the invariant

        ``structural_eq(x, y) ⟺ reify_eq(x, y) is True``

    holds by construction: two terms are structurally equal exactly when
    they unify with no bindings.  Deferring the structured cases to
    ``reify_eq`` (rather than maintaining a third, hand-written structural
    walker) keeps ``==/2`` symmetric and consistent with unify / dif / setof
    across every container the unifier understands — including the Liskov
    str↔char-list contract, ground SegList↔list, DictTerm↔dict, and
    SetTerm↔set equivalences (A05-F003).  A fast path short-circuits the
    common identity / var / atomic cases without allocating a scratch Trail.
    """
    left = deref(left)
    right = deref(right)

    # Identical objects (covers same Var, same int, etc.)
    if left is right:
        return True

    # Two distinct unbound Vars → not structurally equal (unify would bind).
    if is_var(left) or is_var(right):
        return False

    # Atomic fast path: when BOTH sides are atomic, value equality settles it
    # without the reify_eq machinery.  A mixed atomic/structured pair (e.g.
    # str vs char-list) deliberately falls through so the unify contract is
    # honoured symmetrically.
    _ATOMIC = (bool, int, float, str, bytes, complex, type(None))
    if isinstance(left, _ATOMIC) and isinstance(right, _ATOMIC):
        return left == right

    # General case: structurally equal iff unifiable with zero bindings.
    return reify_eq(left, right, Trail()) is True


def structural_neq(left: Any, right: Any) -> bool:
    """True iff *left* and *right* are NOT identical after dereferencing.

    Corresponds to Prolog's ``\\==/2``.
    """
    return not structural_eq(left, right)


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
        # Containers the unifier can bind through via their __unify__ hook.
        # Kept in lockstep with what unify() descends into: a var reachable
        # only through one of these must still receive the dif constraint,
        # else dif silently drops it (A05-F001).  SetTerm is intentionally
        # absent — the unifier refuses var-element set unification, so a var
        # inside a SetTerm cannot become equal and needs no constraint.
        if isinstance(t, DictTerm):
            for elem in t.data.values():
                _walk(elem)
            return
        if isinstance(t, dict):
            for elem in t.values():
                _walk(elem)
            return
        if isinstance(t, (SegList, SegString, SegBytes)):
            for seg in t.segments:
                if isinstance(seg, VarSeg):
                    _walk(seg.var)
                elif isinstance(seg, ConcreteSeg):
                    for elem in seg.elements:
                        _walk(elem)
                # plain str/bytes segments are ground — nothing to collect
            return
        if isinstance(t, Quantity):
            _walk(t.value)
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

    Handles term (dataclass) instances that the C extension's
    ``unify_with_occurs_check`` does not (it falls through to ``==``).
    """
    t1 = deref(t1)
    t2 = deref(t2)

    # Let the C extension handle Var, tuple, list, scalars.
    # But if both are term instances, recurse.

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
            # Replace the list via put_attr (trailed) rather than mutating it in
            # place — an untrailed append survives backtracking and leaves a
            # stale constraint that wrongly blocks later unifications.
            put_attr(v, DIF_KEY, existing + [pair], trail)

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
                    # Trailed replacement, not an in-place append (see dif()).
                    put_attr(v, DIF_KEY, existing + [pair], trail)

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


# ── C extension replacement ──────────────────────────────────────────────────

# If the C extension is available, its versions silently replace the Python ones.

_USE_C_DIF = False
try:
    from clausal.logic._constraints_dif import (
        _collect_free_vars as _c_collect_free_vars,
        _structural_unify_oc as _c_structural_unify_oc,
        dif as _c_dif,
        _dif_hook as _c_dif_hook,
        reify_eq as _c_reify_eq,
    )
    _USE_C_DIF = True
except ImportError:
    pass

if _USE_C_DIF:
    _collect_free_vars = _c_collect_free_vars
    _structural_unify_oc = _c_structural_unify_oc
    dif = _c_dif
    _dif_hook = _c_dif_hook
    reify_eq = _c_reify_eq
    # Re-register the C dif_hook
    register_attr_hook(DIF_KEY, _c_dif_hook)
