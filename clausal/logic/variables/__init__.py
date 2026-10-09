"""Logic variables, unification, and trail-based backtracking.

Threading contract
------------------
This module is safe for use from multiple threads under free-threaded
Python (3.13t+).  The rules:

**Safe to share** between threads:
  - ``Var`` / ``AttVar`` objects (bindings are atomic; ``unify()`` uses
    per-object critical sections).
  - Ground terms (int, str, tuples/lists of ground values).
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
from decimal import Decimal as _Decimal
import math as _math

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
    pending_or_once,
    unify_iter,
    _set_pending_drain,
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
    if type(x) is _Decimal:
        # A Decimal with NO decimal places presents as an int -- the same
        # rule the transfer form applies (``_decimal_to_term``: scale <= 0 is
        # an int), applied at the binder so the engine and the wire agree
        # about which term ``Decimal('2')`` is.  ``Decimal('2.0')`` keeps its
        # scale: scale is information (RULED 2026-09-17 Q2).  A non-finite
        # Decimal has a str exponent and is left alone (the evaluator refuses
        # it as a leaf).
        exp = x.as_tuple().exponent
        if type(exp) is int and exp >= 0:
            return int(x)
    return x


def exact_cell_number(term):
    """The number a CANONICAL exact-number cell denotes, or ``None``.

    ``('decimal', M, S)`` is ``M x 10**-S`` with ``S > 0`` decimal places;
    ``('rdiv', N, D)`` is ``N/D`` in lowest terms with ``D > 1`` and the sign
    on ``N``.  These are the TRANSFER forms of ``Decimal`` and ``Fraction``
    (RULED 2026-09-17 Q1: numbers are Python number objects in the engine,
    the cells are transfer forms and source spellings) and they should never
    survive as compounds here -- but a leaked one must still ORDER and
    EVALUATE as the number it denotes, because the failure mode is silent:
    two decimal cells ``msort``ed by mantissa reverse a threshold test without
    raising (todo/decimal-term-form-orders-as-a-term-in-compare-and-msort-2026-09-16.md).

    ONLY the canonical spelling is a number.  A look-alike (``rdiv(2, 4)``,
    ``rdiv(3, 1)``, ``decimal(100, 0)``, a str component, a bool) is a
    compound and stays in the compound band: if two spellings of one value
    both keyed as that value, ``compare(=, X, Y)`` would hold for terms
    ``'=='`` calls different, and the identity ``compare(=) <=> ==`` that the
    standard order holds BY CONSTRUCTION would break.  The transfer layer's
    ``from_transfer`` draws the same line (``_fraction_from_term``).
    ``bool`` is excluded by exact-type tests, as everywhere in this vocabulary.
    """
    if type(term) is not tuple or len(term) != 3:
        return None
    head, a, b = term
    if type(a) is not int or type(b) is not int:
        return None
    if head == "decimal":
        return _Decimal(a).scaleb(-b) if b > 0 else None
    if head == "rdiv":
        return _Fraction(a, b) if b > 1 and _math.gcd(a, b) == 1 else None
    return None


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
    "pending_or_once",
    "unify_iter",
]

# Registers the drain that pending_or_once hands out (clausal.logic.pending).
from clausal.logic import pending as _pending  # noqa: E402,F401
