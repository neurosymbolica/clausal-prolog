"""Logic variables, unification, and trail-based backtracking.

Threading contract
------------------
This module is safe for use from multiple threads under free-threaded
Python (3.13t+).  The rules:

**Safe to share** between threads:
  - ``Var`` / ``AttVar`` objects (bindings are atomic; ``unify()`` uses
    per-object critical sections).
  - Ground terms (int, str, tuples/lists of ground values, Compound).
  - The attribute hook registry (``register_attr_hook`` is synchronized).

**Must be per-thread** (enforced at runtime):
  - ``Trail`` objects.  Each thread must create its own Trail.  Passing a
    Trail created in one thread to another raises ``RuntimeError``.

**Caller responsibility:**
  - Each parallel search branch needs its own Trail and its own set of
    unbound query variables.  Shared variables are safe to *read* (deref)
    from any thread, but binding should happen from one thread at a time.
  - Constraint hooks re-enter the engine and must be re-entrant.
"""

from ._variables import (
    Var as PlainVar,
    AttVar,
    Trail,
    unify,
    unify_with_occurs_check,
    deref,
    walk,
    is_var,
    occurs_check,
    put_attr,
    get_attr,
    del_attr,
    register_attr_hook,
)

# All logic variables are AttVars so constraints (dif, etc.) can be attached.
# AttVar IS-A Var (C tp_base inheritance) — is_var/deref/unify all work unchanged.
# Only overhead: +8 bytes per variable for the attrs pointer (NULL until first put_attr).
Var = AttVar


def unregister_attr_hook(key: str) -> None:
    """Remove the attr hook for *key*.

    This is a convenience wrapper around ``register_attr_hook(key, None)``.
    Silently succeeds if no hook was registered for *key*.
    """
    register_attr_hook(key, None)


__all__ = [
    "Var",
    "PlainVar",
    "AttVar",
    "Trail",
    "unify",
    "unify_with_occurs_check",
    "deref",
    "walk",
    "is_var",
    "occurs_check",
    "put_attr",
    "get_attr",
    "del_attr",
    "register_attr_hook",
    "unregister_attr_hook",
]
