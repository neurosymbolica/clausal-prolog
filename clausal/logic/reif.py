"""clausal.logic.reif — reified predicates (V2-8 Phase B).

User-callable reified builtins that produce truth values as data.
These implement Neumerkel & Kral's reified equality/disequality pattern
(arXiv:1607.01590) as simple-mode generator functions.

Reified predicates always succeed, binding their last argument to True/False.
when the relationship is undetermined, they explore both branches via
backtracking with appropriate constraints.

Built-ins implemented
---------------------
eq/3        — reified equality: eq(X, Y, T) — T is True if X=Y, False if dif(X,Y)
dif_t/3     — reified disequality: dif_t(X, Y, T) — T is True if dif(X,Y), False if X=Y
=/3, dif/3  — library(reif)'s names (Scryer's reif.pl): =/3 is eq/3; dif/3 is
              dif_t/3 in =/3's answer order (False first)
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.constraints import reify_eq, dif


def eq__3(x: Any, y: Any, t: Any, trail: Trail, k: Any):
    """Reified equality: eq(X, Y, T) — T is True if X=Y, False if dif(X,Y).

    Three-way decision:
    - Already identical → T = True (deterministic)
    - Structurally incompatible → T = False (deterministic)
    - Undetermined → explore both: (T=True, X=Y) and (T=False, dif(X,Y))
    """
    result = reify_eq(x, y, trail)
    if result is True:
        # Ground-equal or identical — deterministic
        mark = trail.mark()
        if unify(t, True, trail):
            yield None
        trail.undo(mark)
    elif result is False:
        # Structurally incompatible — deterministic
        mark = trail.mark()
        if unify(t, False, trail):
            yield None
        trail.undo(mark)
    else:
        # Undetermined — explore both branches
        # Branch 1: T = True, X = Y
        mark = trail.mark()
        if unify(t, True, trail) and unify(x, y, trail):
            yield None
        trail.undo(mark)
        # Branch 2: T = False, dif(X, Y)
        mark = trail.mark()
        if unify(t, False, trail) and dif(x, y, trail):
            yield None
        trail.undo(mark)
    return; yield  # noqa: B901 — ensure generator


def dif_t__3(x: Any, y: Any, t: Any, trail: Trail, k: Any):
    """Reified disequality: dif_t(X, Y, T) — T is True if dif(X,Y), False if X=Y.

    Inverse of eq/3: swaps True/False.
    """
    result = reify_eq(x, y, trail)
    if result is True:
        # Already identical → dif fails → T = False
        mark = trail.mark()
        if unify(t, False, trail):
            yield None
        trail.undo(mark)
    elif result is False:
        # Structurally incompatible → dif succeeds → T = True
        mark = trail.mark()
        if unify(t, True, trail):
            yield None
        trail.undo(mark)
    else:
        # Undetermined — explore both branches
        # Branch 1: T = True, dif(X, Y)
        mark = trail.mark()
        if unify(t, True, trail) and dif(x, y, trail):
            yield None
        trail.undo(mark)
        # Branch 2: T = False, X = Y
        mark = trail.mark()
        if unify(t, False, trail) and unify(x, y, trail):
            yield None
        trail.undo(mark)
    return; yield  # noqa: B901 — ensure generator


def reif_dif__3(x: Any, y: Any, t: Any, trail: Trail, k: Any):
    """Scryer's reif ``dif(X, Y, T) :- =(X, Y, NT), non(NT, T).``: dif_t/3's
    truth values, in =/3's answer order -- undetermined, (T = False, X = Y)
    comes before (T = True, dif(X, Y))."""
    for _ in eq__3(x, y, nt := Var(), trail, k):
        mark = trail.mark()
        if unify(t, deref(nt) is not True, trail):
            yield None
        trail.undo(mark)
