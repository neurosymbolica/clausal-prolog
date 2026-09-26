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

**An atom is eligible too, and is not a type test.**  After the
atoms-as-cells flip an atom is the arity-0 cell ``("bar",)`` — a ``tuple``,
and ``tuple`` is emphatically NOT on the whitelist: a cell of arity ≥ 1 may
hold a Var or a ``__unify__``-carrying element, so its ``==`` does not
answer ``unify()``.  Atoms specifically do coincide: two ground atoms unify
exactly when their spellings are equal, which is exactly 1-tuple ``==``, and
``hash`` on a 1-tuple of a ``str`` is total.  So eligibility is
``element.__class__ in _CONST_SET_TYPES`` **or** :func:`is_atom` — a shape
test, not a type test, which is why the generated guard
(``_lower_goalop_shared._const_set_guard``) ORs the injected ``$cset_atom``
onto the class test rather than growing the type set.  Without this an
``ACTION in [acquire, dispose, amend, cancel]`` over declared atoms — the
motivating shape for the whole optimisation — would pin itself to the scan
forever, which is what it did between the flip and this note.

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

from clausal.logic.atoms import is_atom as _term_is_atom
from clausal.logic.cells import is_chars

__all__ = [
    "_CONST_SET_TYPES", "_const_set", "_cset_atom", "_AtomSpellings",
]

#: The shape half of the eligibility test — see the module docstring.  Bound
#: into generated code as ``$cset_atom`` and ORed onto the class test, so a
#: non-tuple left operand never pays for the call.
_cset_atom = _term_is_atom


class _AtomSpellings(frozenset):
    """A const-set holding ATOMS only — which, since STAGE 2 of the
    atoms-as-str flip, are their spellings (an atom IS the ``str``).

    ``_const_set`` returns one of these when EVERY element of the constant
    list is an atom, which is the overwhelmingly common shape (``ACTION in
    [acquire, dispose, amend, cancel]``).  The subclass is the signal: the
    generated code asks ``set.__class__ is $ATOM_SET`` and, when it is,
    narrows its GUARD to ``elem.__class__ is $str`` (the lookup is ``elem in
    set`` in both modes; the slot-0 read of the cell era is gone).
    The measurements below are from the cell era and are kept for the record.

    How much this is worth, measured rather than assumed: the cached-str-hash
    argument that motivates it is **almost entirely wrong on CPython 3.13**.
    ``hash(("a0",))`` times at 28.9 ns against ``hash("a0")``'s 27.8 ns — a
    1-tuple's hash is a couple of arithmetic ops over the (cached) hash of
    slot 0, so there is no field-read-versus-recompute gap to win.  Nor is
    the lookup itself cheaper: ``spelling in _AtomSpellings`` measured 30.9 ns
    against ``cell in frozenset``'s 28.0 ns, the subclass costing a little on
    the set path.

    What the mode is actually worth is the GUARD it enables.  Knowing every
    element is an atom lets the guard collapse from "a whitelisted type or an
    atom" to "an atom", which the emitted code can then spell out inline
    (``_lower_goalop_shared._is_atom_inline``) instead of calling
    ``$cset_atom`` — and that Python-level call was 67 ns of a ~110 ns fast
    path.  Guard plus lookup: 108 ns keying on cells with the call, 90.9 ns
    keying on spellings with the test inlined.  The set contents are along
    for the ride; the call being gone is the win.

    Why it needs a distinct type rather than always storing spellings: a
    spelling is indistinguishable from a STRING, and after the flip a string
    is a term in its own right that must NOT unify with the atom of the same
    text.  A MIXED list — ``[a, "a", 1, None]`` — therefore keeps the plain
    ``frozenset`` holding atom cells, where the atom and the string sit in it
    as the two different terms they are.  Collapsing them would make
    ``"a" in [a, "a"]`` answer twice-over-one-element.

    In atom-spellings mode the generated guard narrows from "whitelisted type
    or an atom" to "an atom": a non-atom left operand cannot unify with any
    element of an all-atom list, so it takes the scan (which fails), and no
    ``str`` operand ever gets to test itself against a spelling.

    ``__contains__`` is deliberately NOT overridden — that would put back the
    Python-level call this exists to remove.  The unwrapping lives in the
    emitted code instead.
    """

    __slots__ = ()


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
})


def _const_set(elements):
    """Return a frozenset equivalent to scanning *elements*, else ``False``.

    ``False`` means "this callsite is not eligible" and is memoised by the
    caller, so the check runs once per callsite rather than once per call.
    """
    if type(elements) is not list or len(elements) < 2:
        return False
    all_atoms = True
    for element in elements:
        if _cset_atom(element):
            continue
        all_atoms = False
        if element.__class__ not in _CONST_SET_TYPES and not is_chars(element):
            return False              # the chars carrier is hashable and equal only to itself here; a char-list operand takes the scan
    if all_atoms:
        # Every element is an atom, so nothing in the set can collide with a
        # string of the same text — key on the spelling and let CPython's
        # cached str hash do the work.  Duplicate atoms are duplicate
        # spellings, so the count check below still catches them.
        as_set = _AtomSpellings(elements)   # STAGE 2: an atom IS its spelling
    else:
        try:
            as_set = frozenset(elements)
        except TypeError:
            return False
    # Duplicates would each yield their own solution under the scan.
    if len(as_set) != len(elements):
        return False
    return as_set
