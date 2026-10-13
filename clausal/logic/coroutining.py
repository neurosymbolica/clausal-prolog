"""Coroutining primitives: freeze/2, when/2.

freeze/2 delays a goal until a variable is bound. The goal is stored as an
attributed variable attribute under the key ``"freeze"``. When the variable
is unified (bound), the hook wakes the goal: it is queued on the trail.
Under a driver it runs at the next goal boundary with every answer
(``clausal.logic.pending``); a bare unify from Python runs the queue itself
once every hook of the unification has run, to its first answer, and fails
when it has none.

Multiple freezes on the same variable accumulate in a list. All are fired
when the variable is bound.

when/2 generalizes freeze by supporting compound conditions:
- ``nonvar(X)`` — equivalent to freeze(X, Goal)
- ``ground(X)`` — delay until X is fully ground
- ``(C1, C2)`` — conjunction: both conditions must be satisfied
- ``(C1 ; C2)`` — disjunction: either condition suffices
"""

from __future__ import annotations

from clausal.logic.variables import (
    register_attr_hook, get_attr, put_attr, deref, is_var, Var, unify,
)
from clausal.logic.cells import compound_cell_shape, cell_args
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error)
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.pythonic_ast import nodes as _nodes
import clausal.logic.pending  # noqa: F401  -- registers the drain a bare unify runs

FREEZE_KEY = "freeze"


def _freeze_hook(goals, bound_to, trail):
    """Wake all frozen goals when a variable is bound: queue them.

    Each goal is a zero-arg generator factory (closure capturing trail and
    variables from the compilation context).  The goals never run inside
    the hook, where other variables of the same unification may not have
    had their hooks run yet: under a driver they run at the next goal
    boundary with every answer (``clausal.logic.pending``); a bare
    ``unify`` runs them after all its hooks, to their first answer.
    """
    for goal_fn in goals:
        trail.push_pending(goal_fn)
    return True


register_attr_hook(FREEZE_KEY, _freeze_hook)


# ── when/2 runtime helpers ───────────────────────────────────────────────────


def _freeze_var(var, goal_thunk, trail):
    """Attach a freeze goal to an unbound variable."""
    existing = get_attr(var, FREEZE_KEY)
    goals = list(existing) if existing else []
    goals.append(goal_thunk)
    put_attr(var, FREEZE_KEY, goals, trail)


def _run_now(goal_thunk, trail):
    """Run a goal whose condition already holds; False when it fails.

    While the trail is owned (``trail.defer``: a driver, or a bare unify
    firing its hooks and running its queue) it is queued like a woken goal:
    compiled when/2 puts a goal boundary right after the install, and a
    drain that ran the goal calling this runs what it queued after it.

    Otherwise nothing would ever run the queue for it -- a later bare unify
    drains only within its own unification, and leaving a goal there made
    every later unify on the trail run it (a failing one failed them all).
    So it runs here, to its first answer, as a bare unify runs its goals.
    """
    if trail.defer:
        trail.push_pending(goal_thunk)
        return True
    for _ in goal_thunk():
        return True
    return False


def _collect_free_vars(term):
    """Collect all unbound Vars reachable from *term*."""
    from clausal.logic.constraints import _collect_free_vars as _cfv
    return _cfv(term)


def _install_when_ground(term, goal_thunk, trail):
    """Install a when(ground(term), Goal) condition at runtime.

    Freezes on every unbound var in term. when any is bound, re-checks
    groundness. Fires goal_thunk when term is fully ground.
    """
    from clausal.logic.builtins._helpers import _is_ground

    term_d = deref(term)
    if _is_ground(term_d):
        # Already ground — run goal immediately
        return _run_now(goal_thunk, trail)

    free_vars = _collect_free_vars(term_d)
    if not free_vars:
        # No free vars but _is_ground returned False? Shouldn't happen.
        return _run_now(goal_thunk, trail)

    # Create a re-check thunk: when any var is bound, check if term
    # is now fully ground. If so, fire the goal.
    def _recheck_ground():
        if _is_ground(deref(term)):
            yield from goal_thunk()
        else:
            # Not fully ground yet — re-install on remaining free vars
            new_free = _collect_free_vars(deref(term))
            for v in new_free:
                _freeze_var(v, _recheck_ground, trail)
            yield None  # succeed (the when condition is still pending)

    for v in free_vars:
        _freeze_var(v, _recheck_ground, trail)
    return True


def _install_when_disjunction(cond_left, cond_right, goal_thunk, trail):
    """Install a when((C1 ; C2), Goal) disjunction at runtime (the entry the
    compiler's ``Or`` lowering calls); the condition is checked whole first."""
    tree = _parse_when_condition((";", cond_left, cond_right))
    return _install_when_disjunction_tree(tree[1], tree[2], goal_thunk, trail)


def _install_when_disjunction_tree(cond_left, cond_right, goal_thunk, trail):
    """Install a when((C1 ; C2), Goal) disjunction at runtime.

    Attaches to vars in both conditions. Whichever fires first runs Goal.
    Uses a shared flag to ensure Goal fires at most once.
    """
    # A04-F010: the at-most-once flag must be *backtrackable*. A plain closure
    # cell survives trail unwinding, so a branch that fires the goal and then
    # FAILS leaves the flag set — the surviving branch then skips the goal.
    # Bind an unbound Var via unify(): the trail undoes the "already fired"
    # state exactly when the firing branch is undone.
    fired = Var()

    def _guarded_thunk():
        if is_var(deref(fired)):
            unify(fired, True, trail)
            yield from goal_thunk()
        else:
            yield None  # already fired in this surviving world — succeed silently

    return (_install_tree(cond_left, _guarded_thunk, trail)
            and _install_tree(cond_right, _guarded_thunk, trail))


def _parse_when_condition(condition):
    """Parse a when/2 condition once into a tree, or raise Scryer's error.

    The tree is ``("nonvar", X)``, ``("ground", X)``, ``(",", L, R)`` or
    ``(";", L, R)``.  A condition is the functor-first CELL ``('nonvar', X)``
    (``(';', A, B)`` for a disjunction written in Prolog syntax); the seam
    ``Or``/``And`` nodes and a functor-less pair ``(C1, C2)`` read as ``;``
    and ``,``.  A CELL is a tuple, so the functor-less pair is tried LAST:
    ``('nonvar', X)`` has length 2 and would otherwise pass for a conjunction.

    An unbound condition (or sub-condition) is ``instantiation_error``; any
    other term that is not ``nonvar/1``, ``ground/1`` or a ``,``/``;`` of
    conditions is ``domain_error(when_condition, Condition)`` naming the WHOLE
    condition, as Scryer does.  The whole tree is parsed before anything is
    installed, so a bad branch leaves nothing half-installed.
    """
    def bad():
        raise LogicException(
            domain_error("when_condition", deref(condition), "when/2"))

    def walk(c):
        c = deref(c)
        if is_var(c):
            raise LogicException(instantiation_error("when_condition/1"))
        if type(c) is tuple:
            is_cell, functor = compound_cell_shape(c)
            if is_cell:
                args = cell_args(c)
                n = len(args)
                if n == 1 and (functor == "nonvar" or functor == "ground"):
                    return (functor, args[0])
                if n == 2 and (functor == "," or functor == ";"):
                    return (functor, walk(args[0]), walk(args[1]))
                bad()
        t = type(c)
        if t is _nodes.Or:
            return (";", walk(c.left), walk(c.right))
        if t is _nodes.And:
            return (",", walk(c.left), walk(c.right))
        if t is not tuple and is_term_instance(c):
            name = t.__name__
            args = tuple(getattr(c, f) for f in term_field_names(c))
            if len(args) == 1 and name in ("nonvar", "ground"):
                return (name, args[0])
            bad()
        if isinstance(c, (tuple, list)) and len(c) == 2:
            return (",", walk(c[0]), walk(c[1]))
        bad()

    return walk(condition)


def _install_when_condition(condition, goal_thunk, trail):
    """Dispatch a when condition at runtime.

    Handles nonvar(X), ground(X), conjunction and disjunction, the last two
    nested to any depth.  The condition is parsed whole first
    (:func:`_parse_when_condition`).
    """
    c = deref(condition)
    # Fast path: the common ``nonvar(X)`` cell, exactly as before the
    # dispatcher learned ``,`` and ``;``.
    if type(c) is tuple and len(c) == 2 and c[0] == "nonvar":
        x = deref(c[1])
        if is_var(x):
            _freeze_var(x, goal_thunk, trail)
            return True
        return _run_now(goal_thunk, trail)
    return _install_tree(_parse_when_condition(c), goal_thunk, trail)


def _install_tree(tree, goal_thunk, trail):
    kind = tree[0]

    if kind == "nonvar":
        x = deref(tree[1])
        if is_var(x):
            _freeze_var(x, goal_thunk, trail)
            return True
        return _run_now(goal_thunk, trail)

    if kind == "ground":
        return _install_when_ground(tree[1], goal_thunk, trail)

    if kind == ",":
        right = tree[2]

        # when(C1, when(C2, Goal))
        def _inner_thunk():
            if _install_tree(right, goal_thunk, trail):
                yield None
        return _install_tree(tree[1], _inner_thunk, trail)

    return _install_when_disjunction_tree(tree[1], tree[2], goal_thunk, trail)
