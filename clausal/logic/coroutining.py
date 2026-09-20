"""Coroutining primitives: freeze/2, when/2.

freeze/2 delays a goal until a variable is bound. The goal is stored as an
attributed variable attribute under the key ``"freeze"``. when the variable
is unified (bound), the hook fires and drives the frozen goal generator
synchronously — if the goal succeeds, the unification succeeds; if the
goal fails, the unification fails.

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

FREEZE_KEY = "freeze"


def _freeze_hook(goals, bound_to, trail):
    """Fire all frozen goals when a variable is bound.

    Each goal is a zero-arg generator factory (closure capturing trail and
    variables from the compilation context). The hook drives each generator
    to its first solution. If any goal fails (no solutions), the hook
    returns False, causing the unification to fail.
    """
    for goal_fn in goals:
        found = False
        for _ in goal_fn():
            found = True
            break  # one solution suffices
        if not found:
            return False
    return True


register_attr_hook(FREEZE_KEY, _freeze_hook)


# ── when/2 runtime helpers ───────────────────────────────────────────────────


def _freeze_var(var, goal_thunk, trail):
    """Attach a freeze goal to an unbound variable."""
    existing = get_attr(var, FREEZE_KEY)
    goals = list(existing) if existing else []
    goals.append(goal_thunk)
    put_attr(var, FREEZE_KEY, goals, trail)


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
        for _ in goal_thunk():
            return True
        return False

    free_vars = _collect_free_vars(term_d)
    if not free_vars:
        # No free vars but _is_ground returned False? Shouldn't happen.
        for _ in goal_thunk():
            return True
        return False

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


def _install_when_disjunction(cond_left, cond_right, goal_thunk, trail):
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

    _install_when_condition(cond_left, _guarded_thunk, trail)
    _install_when_condition(cond_right, _guarded_thunk, trail)


def _install_when_condition(condition, goal_thunk, trail):
    """Dispatch a when condition at runtime.

    Handles nonvar(X), ground(X), conjunction, disjunction.

    Parameters
    ----------
    condition : the condition to check (a term or AST-like structure)
    goal_thunk : zero-arg generator factory to fire when condition is met
    trail : the current Trail
    """
    from clausal.logic.predicate import is_term_instance, term_field_names
    from clausal.logic.cells import compound_cell_shape, cell_args  # noqa: PLC0415

    cond = deref(condition)

    def _shape(c):
        """``(functor, args)`` for a condition, or ``(None, ())``.

        P2: a condition is the functor-first CELL ``('nonvar', X)``; before it
        it was a class instance whose CLASS NAME was the functor.  Both are
        read here, positionally, and the instance arm goes with the class in
        P4.  The order matters -- see the conjunction arm below.
        """
        is_cell, functor = compound_cell_shape(c)
        if is_cell:
            return functor, tuple(cell_args(c))
        if is_term_instance(c):
            return type(c).__name__, tuple(getattr(c, f) for f in term_field_names(c))
        return None, ()

    cond_functor, cond_args = _shape(cond)

    # nonvar(X)
    if cond_functor == "nonvar":
        if cond_args:
            x = deref(cond_args[0])
            if is_var(x):
                _freeze_var(x, goal_thunk, trail)
            else:
                # Already bound — check immediately
                for _ in goal_thunk():
                    break
        return

    # ground(X)
    if cond_functor == "ground":
        if cond_args:
            _install_when_ground(cond_args[0], goal_thunk, trail)
        return

    # Conjunction: (C1, C2) as a bare 2-tuple or list of conditions.
    #
    # ``cond_functor is None`` is load-bearing, not defensive.  A CELL is a
    # tuple, so ``('nonvar', X)`` has length 2 and this arm used to swallow it
    # — destructuring a condition into c1='nonvar', c2=X and then failing on
    # the bare atom, reported as "Unsupported when condition: 'nonvar'".  A
    # cell is never a conjunction; only a functor-less pair is.
    if cond_functor is None and isinstance(cond, (tuple, list)) and len(cond) == 2:
        c1, c2 = cond
        # when(C1, when(C2, Goal))
        def _inner_thunk():
            _install_when_condition(c2, goal_thunk, trail)
            yield None
        _install_when_condition(c1, _inner_thunk, trail)
        return

    raise ValueError(f"Unsupported when condition: {cond!r}")
