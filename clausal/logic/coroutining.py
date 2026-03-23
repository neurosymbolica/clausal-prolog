"""Coroutining primitives: Freeze/2, When/2.

Freeze/2 delays a goal until a variable is bound. The goal is stored as an
attributed variable attribute under the key ``"freeze"``. When the variable
is unified (bound), the hook fires and drives the frozen goal generator
synchronously — if the goal succeeds, the unification succeeds; if the
goal fails, the unification fails.

Multiple freezes on the same variable accumulate in a list. All are fired
when the variable is bound.

When/2 generalizes Freeze by supporting compound conditions:
- ``IsBound(X)`` — equivalent to Freeze(X, Goal)
- ``IsGround(X)`` — delay until X is fully ground
- ``(C1, C2)`` — conjunction: both conditions must be satisfied
- ``(C1 ; C2)`` — disjunction: either condition suffices
"""

from __future__ import annotations

from clausal.logic.variables import (
    register_attr_hook, get_attr, put_attr, deref, is_var,
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


# ── When/2 runtime helpers ───────────────────────────────────────────────────


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
    """Install a When(IsGround(term), Goal) condition at runtime.

    Freezes on every unbound var in term. When any is bound, re-checks
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
    """Install a When((C1 ; C2), Goal) disjunction at runtime.

    Attaches to vars in both conditions. Whichever fires first runs Goal.
    Uses a shared flag to ensure Goal fires at most once.
    """
    fired = [False]

    def _guarded_thunk():
        if not fired[0]:
            fired[0] = True
            yield from goal_thunk()
        else:
            yield None  # already fired — succeed silently

    _install_when_condition(cond_left, _guarded_thunk, trail)
    _install_when_condition(cond_right, _guarded_thunk, trail)


def _install_when_condition(condition, goal_thunk, trail):
    """Dispatch a When condition at runtime.

    Handles IsBound(X), IsGround(X), conjunction, disjunction.

    Parameters
    ----------
    condition : the condition to check (a term or AST-like structure)
    goal_thunk : zero-arg generator factory to fire when condition is met
    trail : the current Trail
    """
    from clausal.logic.predicate import is_term_instance, term_field_names

    cond = deref(condition)

    # IsBound(X) — check if X is a term with one field named 'term'
    # and the class name is 'IsBound'
    if is_term_instance(cond) and type(cond).__name__ == "IsBound":
        fields = term_field_names(cond)
        if fields:
            x = deref(getattr(cond, fields[0]))
            if is_var(x):
                _freeze_var(x, goal_thunk, trail)
            else:
                # Already bound — check immediately
                for _ in goal_thunk():
                    break
        return

    # IsGround(X)
    if is_term_instance(cond) and type(cond).__name__ == "IsGround":
        fields = term_field_names(cond)
        if fields:
            _install_when_ground(getattr(cond, fields[0]), goal_thunk, trail)
        return

    # Conjunction: (C1, C2) represented as a tuple or list of conditions
    if isinstance(cond, (tuple, list)) and len(cond) == 2:
        c1, c2 = cond
        # When(C1, When(C2, Goal))
        def _inner_thunk():
            _install_when_condition(c2, goal_thunk, trail)
            yield None
        _install_when_condition(c1, _inner_thunk, trail)
        return

    raise ValueError(f"Unsupported When condition: {cond!r}")
