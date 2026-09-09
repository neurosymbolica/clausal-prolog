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

from fractions import Fraction as _Fraction

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
    UnboundVarCoercionError,
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


def present_number(x):
    """The number a binder hands to ``unify``: an integral ``Fraction`` as int.

    THE one spelling of the rule. ``int/int`` is exact (``3/2`` is
    ``Fraction(3, 2)``, never 1.5), but ``Fraction(2, 1)`` is not the term
    ``2``: the standard order (``'=='``, ``compare/3``) tags every numeric
    type as its own kind while ``unify`` compares by ``==``, so an integral
    Fraction reaching a variable made ``'is'(X, 4/2), '=='(X, 2)`` false and
    ``'='(X, 2)`` true at once. Every producer — the interpreted evaluator,
    the compiled ``$present``/``$exact_div``, CLP(Q)'s binders, the Z3
    converter, ``between/3`` — calls this.

    The predicate is ``type(x) is Fraction``, deliberately not
    ``isinstance``: this sits on arithmetic hot paths and an exact type
    check is one pointer compare. A ``Fraction`` SUBCLASS is therefore
    passed through untouched — none exists in the engine, and a subclass
    that wanted presenting would have to say so here.
    """
    if type(x) is _Fraction and x.denominator == 1:
        return x.numerator
    return x


__all__ = [
    "present_number",
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
    "UnboundVarCoercionError",
]
