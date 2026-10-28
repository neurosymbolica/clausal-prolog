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

import threading as _threading
from typing import Any

from clausal.logic.variables import (
    Var,
    deref,
    is_var,
    unify,
    unify_with_occurs_check,
    put_attr,
    get_attr,
    register_attr_hook,
    Trail,
)
from clausal.logic.atoms import truth_spelling as _truth_spelling
from clausal.logic.number_kinds import same_number
from clausal.logic.rational_walk import (
    collect_free_vars_iterative as _collect_free_vars_iterative)
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
    Undefined as _Undefined,
    _partial_list_build,
    _partial_list_parts,
)

_ATOMIC = (bool, int, float, str, bytes, complex, type(None))


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
    # A truth atom (True/False/Undefined -- the atoms true/false/undefined,
    # ``atoms.is_truth_atom``) is identical to itself (the identity check
    # above) and to the str of its spelling, never to a number: Python's
    # ``True == 1`` must not reach ``==``.  The bool test sits INSIDE the
    # atomic branch (a bool is atomic) so the common int/str pair pays two
    # ``type`` compares, not two calls; ``Undefined`` is not atomic and is
    # tested only on the way to the general case.
    if isinstance(left, _ATOMIC) and isinstance(right, _ATOMIC):
        if type(left) is bool:
            return type(right) is str and _truth_spelling(left) == right
        if type(right) is bool:
            return type(left) is str and _truth_spelling(right) == left
        # Two numbers are one term only in one KIND (ISO 7.3: ``1`` is not
        # ``1.0``; a Decimal keeps its scale) -- the rule the unifier holds
        # since 2026-10-23, so this fast path answers what the general
        # ``reify_eq`` path below would.
        return left == right and same_number(left, right)
    if left is _Undefined:
        return type(right) is str and right == "undefined"
    if right is _Undefined:
        return type(left) is str and left == "undefined"

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

    Returns a list of unique Var objects (deduplicated by identity), in
    order of first appearance left to right.  The walk is iterative and
    cycle-aware (``rational_walk.collect_free_vars_iterative``): a cyclic
    term (``X = f(X)``) or one nested past any recursion limit is walked
    to the end, never a ``resource_error``.  The C twin is ``collect_root``
    in ``_constraints_dif.c``.
    """
    result: list = []
    _collect_free_vars_iterative(term, result, set())
    return result


# ── Structural unify with occurs check ───────────────────────────────────────


#: The depth past which ``_structural_unify_oc`` stops descending (twin of
#: ``STRUCTURAL_DEEP`` in ``_constraints_dif.c``): a cyclic term, or a list
#: nested deeper than any program's data.  The walk unwinds to its entry,
#: which hands the ROOT pair to the engine's unify, whose rational-tree
#: walk terminates on a cycle (``unify_rational`` in
#: ``variables/_variables.c``, 2026-10-24); deciding in place where the
#: depth was exceeded would be exponential on a branching cycle.
_STRUCTURAL_DEEP = 1000


class _StructuralDeep(Exception):
    """The walk reached ``_STRUCTURAL_DEEP``: the root pair goes to unify."""


def _structural_unify_oc(t1: Any, t2: Any, trail: Trail) -> bool:
    """Unify t1 and t2 structurally with occurs check (subsumes_term/2,
    unify_with_occurs_check/2).

    Handles term (dataclass) instances that the C extension's
    ``unify_with_occurs_check`` does not (it falls through to ``==``).
    """
    try:
        return _structural_unify_oc_walk(t1, t2, trail, 0, True)
    except (_StructuralDeep, RecursionError):
        # RecursionError: the Python stack ran out before the threshold
        # (the walk runs under the solver's own frames).
        return unify_with_occurs_check(t1, t2, trail)


def _structural_unify(t1: Any, t2: Any, trail: Trail) -> bool:
    """``_structural_unify_oc`` with no occurs check, as ``=/2`` unifies:
    the trial unify of ``dif/2``, its hook and ``reify_eq``.  A rational
    tree is a solution of ``X = f(X)`` (ISO 7.3.2), so ``dif(X, f(X))``
    must suspend (Scryer, SICStus), not succeed with nothing to wait on."""
    try:
        return _structural_unify_oc_walk(t1, t2, trail, 0, False)
    except (_StructuralDeep, RecursionError):
        return unify(t1, t2, trail)


def _structural_unify_oc_walk(t1: Any, t2: Any, trail: Trail, _depth: int,
                              oc: bool = True) -> bool:
    t1 = deref(t1)
    t2 = deref(t2)

    if _depth > _STRUCTURAL_DEEP:
        raise _StructuralDeep()

    # Let the C extension handle Var, tuple, list, scalars.
    # But if both are term instances, recurse.

    if is_term_instance(t1) and is_term_instance(t2):
        t1_type = type(t1)
        t2_type = type(t2)
        if t1_type is not t2_type:
            return False
        fields = term_field_names(t1)
        for fname in fields:
            if not _structural_unify_oc_walk(getattr(t1, fname), getattr(t2, fname),
                                             trail, _depth + 1, oc):
                return False
        return True

    if isinstance(t1, list) and isinstance(t2, list):
        if len(t1) != len(t2):
            return False
        for e1, e2 in zip(t1, t2):
            if not _structural_unify_oc_walk(e1, e2, trail, _depth + 1, oc):
                return False
        return True

    # A partial list ([a|T], the seam's [a, *T]) is read and paired here,
    # never handed to SegList.__unify__ (see _partial_list_parts).
    if ((type(t1) is SegList or type(t2) is SegList)
            and not is_var(t1) and not is_var(t2)):
        p1 = _partial_list_parts(t1)
        if p1 is not None:
            p2 = _partial_list_parts(t2)
            if p2 is not None:
                return _unify_partial_lists_oc(p1, p2, trail, _depth, oc)

    # Fall through to C extension for Var/scalar/tuple.
    if oc:
        return unify_with_occurs_check(t1, t2, trail)
    return unify(t1, t2, trail)


def _unify_partial_lists_oc(p1, p2, trail: Trail, _depth: int = 0,
                            oc: bool = True) -> bool:
    """Unify two lists read by ``_partial_list_parts`` (``(elements, tail)``,
    tail an unbound Var or None for ``[]``), as ISO unifies ``[E1..En|T]``:
    pair the elements, then the shorter side's tail takes the rest of the
    longer side.  Occurs-checked, like the rest of ``_structural_unify_oc``
    (the C ``unify_partial_lists_oc`` is its twin)."""
    (e1, t1), (e2, t2) = p1, p2
    n = min(len(e1), len(e2))
    for i in range(n):
        if not _structural_unify_oc_walk(e1[i], e2[i], trail, _depth + 1, oc):
            return False
    if len(e1) > n:
        if t2 is None:
            return False
        return _structural_unify_oc_walk(t2, _partial_list_build(e1[n:], t1), trail,
                                         _depth + 1, oc)
    if len(e2) > n:
        if t1 is None:
            return False
        return _structural_unify_oc_walk(t1, _partial_list_build(e2[n:], t2), trail,
                                         _depth + 1, oc)
    if t1 is None and t2 is None:
        return True
    return _structural_unify_oc_walk([] if t1 is None else t1,
                                     [] if t2 is None else t2, trail, _depth + 1, oc)


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
    unified = _structural_unify(x, y, trail)

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


#: The pairs whose trial unify is running on this thread, innermost last
#: (the C twin's ``dif_trial_pairs``).  The trial binds the pair's own
#: variables, so their dif hooks run inside it and meet the pair with its
#: two sides made one: the hypothesis under test, not a violation.
#: Answering "violated" there failed the trial, and the hook dropped the
#: pair as entailed (a copied ``dif(_A, E)`` bound to a plain variable lost
#: the constraint).  A nested hook skips a pair on this stack.
_TRIAL = _threading.local()


def _dif_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when an AttVar with dif constraints is unified.

    *attr_value* is the list of ``(x, y)`` constraint pairs.
    *bound_to* is the value the variable was bound to.

    Returns True if all constraints survive; False if any is violated.
    """
    constraints = attr_value
    stack = getattr(_TRIAL, "pairs", None)
    if stack is None:
        stack = _TRIAL.pairs = []
    for pair in constraints:
        if stack and any(p is pair for p in stack):
            continue            # this pair's own trial, further out
        x, y = pair
        x = deref(x)
        y = deref(y)

        mark = trail.mark()
        stack.append(pair)
        try:
            unified = _structural_unify(x, y, trail)
        finally:
            stack.pop()

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
    unified = _structural_unify(x, y, trail)
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
        _structural_unify as _c_structural_unify,
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
    _structural_unify = _c_structural_unify
    dif = _c_dif
    _dif_hook = _c_dif_hook
    reify_eq = _c_reify_eq
    # Re-register the C dif_hook
    register_attr_hook(DIF_KEY, _c_dif_hook)
