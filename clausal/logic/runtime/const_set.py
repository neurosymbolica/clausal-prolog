"""Constant-list membership — the frozenset fast path for ``X in [c1, c2, …]``.

A membership goal compiles to a linear scan that ``unify()``s the left
operand against every element of the collection (see
``_lower_goalop_shared.MemberIn``).  That scan is O(n) with a large
constant: a *failing* ``unify()`` between two ground terms costs ~640 ns
because the C fast paths fall through to a ``__unify__`` attribute probe
on both operands, so a four-element ``ACTION in [acquire, dispose,
amend, cancel]`` costs ~2.5 µs per call.

When the collection is a list of compile-time constants the compiler
emits a guarded frozenset lookup instead.  The set is built **once**, on
first execution, by :func:`_const_set`, and memoised in a one-slot cell
in the compiled predicate's globals.  Building it at first execution
rather than at compile time matters: the emitted list expression and the
set are then evaluated in the same namespace at (almost) the same time,
so an atom can never be captured as a different object than the fallback
scan would see.

Substituting set membership for a unify scan is only sound when nothing
observable distinguishes them.  :func:`_const_set` refuses — returning
``False``, which pins the callsite to the scan forever — unless all of
the following hold.

**Every element's type is on the whitelist.**  ``x in frozenset`` answers
``hash``/``__eq__``; the scan answers ``unify()``.  For the types in
:data:`_CONST_SET_TYPES` those coincide:

* ``int``/``float``/``bool``/``complex``/``Fraction`` — ``unify()`` on two
  ground non-container terms bottoms out in ``PyObject_RichCompareBool(…,
  Py_EQ)``, i.e. exactly Python ``==``; and Python's numeric tower
  guarantees ``x == y ⇒ hash(x) == hash(y)`` across those types.  So
  ``unify(1, 1.0)`` succeeds *and* ``1 in {1.0}`` is True — the two
  agree, including on the cross-type cases.  ``hash()`` is total on all
  of them (``float('nan')`` included — CPython ≥3.10 hashes it by
  identity, which keeps ``nan`` out of a set that holds a *different*
  ``nan``, matching ``unify``'s ``==``-based failure).
* ``str``/``bytes``/``NoneType`` — value equality, hash total.
* ``PredicateMeta`` — an atom is a class, so ``==`` and ``hash`` are
  ``type``'s identity ones, and ``unify()`` on two atoms is likewise
  identity.

``Decimal`` is deliberately *absent*: ``hash(Decimal('nan'))`` raises
``ValueError``, so it could turn a membership test into an exception.
``Quantity`` is absent because it carries a ``__unify__`` hook (and may
contain a Var), so its unification is not its ``==``.  Both simply take
the scan.

**No duplicates.**  Membership is a choice point, so ``a in [a, a, b]``
succeeds *twice* today — verified by execution, not assumed.  A set
collapses that to one solution and would silently drop a solution from
the enclosing conjunction, so a list with any hash-equal pair (``[1,
1.0]`` counts) is refused.

**Nothing unhashable.**  Caught both by the type whitelist and by a
``try``/``except TypeError`` around the ``frozenset`` build, so a list
holding a compound term or a nested list falls back instead of raising.

Note what is *not* handled here: solution **order**.  ``X in [c, a, b]``
with ``X`` unbound enumerates ``c, a, b`` — list order, observable in
first-solution order and in ``findall`` results.  A set reorders it.  The
compiler therefore only takes the frozenset branch when the left operand
derefs to a ground whitelisted term, where there is at most one solution
and no order to observe; an unbound Var falls to the scan at runtime.
"""

from __future__ import annotations

from fractions import Fraction

from clausal.logic.predicate import PredicateMeta

__all__ = ["_CONST_SET_TYPES", "_const_set"]


#: Types for which ``hash``/``__eq__`` provably answer the same question as
#: ``unify()``, and for which ``hash()`` cannot raise.  Used twice: to vet
#: the list elements when the set is built, and — from generated code — to
#: vet the left operand on every call.
_CONST_SET_TYPES: frozenset[type] = frozenset({
    int,
    float,
    bool,
    complex,
    str,
    bytes,
    type(None),
    Fraction,
    PredicateMeta,
})


def _const_set(elements):
    """Return a frozenset equivalent to scanning *elements*, else ``False``.

    ``False`` means "this callsite is not eligible" and is memoised by the
    caller, so the check runs once per callsite rather than once per call.
    """
    if type(elements) is not list or len(elements) < 2:
        return False
    for element in elements:
        if element.__class__ not in _CONST_SET_TYPES:
            return False
    try:
        as_set = frozenset(elements)
    except TypeError:
        return False
    # Duplicates would each yield their own solution under the scan.
    if len(as_set) != len(elements):
        return False
    return as_set
