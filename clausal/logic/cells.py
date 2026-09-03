"""Tagged cells: the Phase 2 bridge's plain-tuple term representation.

Spec: ``implementation_plans/tagged-tuple-term-representation.md`` (design
§1, optimisations §3c); this module is Task 1 of
``docs/superpowers/plans/2026-09-03-phase2-bridge.md``.

A *cell* is a plain Python ``tuple`` whose slot 0 identifies its shape:

  - a ``str`` functor   -> ``("point", x, y)``   a compound term ``point/2``.
  - the ``tuple`` TYPE OBJECT (``TUPLE_TAG``) -> ``(tuple, e1, e2, ...)``
    tuple-DATA, not a compound -- this is how a cell represents a bare
    Python tuple as term data without slot 0 colliding with a real user
    value (a plain data tuple's own slot 0 could be anything; tagging with
    the ``tuple`` type itself sidesteps that).
  - an unbound ``Var`` -> ``(X, a, b)``   a higher-order / not-yet-resolved
    functor slot; unifies against a same-shape cell and binds ``X`` to the
    other cell's functor (see ``tests/test_cells.py``, and the
    higher-order guard test in particular).

Nothing else may occupy slot 0 -- ``make_cell`` enforces this; ``is_cell``
recognizes it.

BRIDGE-ENTRY RULING (ledgered in the Phase 2 bridge plan's Global
Constraints): ``is_cell`` does NOT require ``sys.intern``'d functors --
equality is the semantics of functor comparison everywhere a cell is
compared (the existing C tuple-unify branch this module deliberately rides
compares slot 0 with ``==``, never ``is``; see ``do_unify``'s
``PyTuple_Check(t1) && PyTuple_Check(t2)`` branch in
``clausal/logic/variables/_variables.c``). ``make_cell`` interns as a
convenience only (fewer distinct string objects, marginally faster
compares in practice) -- ``is_cell`` and every accessor here accept ANY
``str`` in slot 0, interned or not.

KNOWN AMBIGUITY (accepted, not solved, per the same ruling): a plain user
tuple whose slot 0 happens to be a ``str`` -- e.g. ``("hello", 1)`` meant
as ordinary tuple data, not a cell -- is indistinguishable from a cell by
shape alone. This bridge stage accepts that ambiguity rather than solving
it: ``is_cell`` answers ``True`` for such a tuple, and the funnel
accessors in ``clausal/logic/builtins/_helpers.py`` therefore treat it as
a cell too. Callers that need a real disambiguation between "cell" and
"plain tuple that happens to start with a str" must gate on something
other than shape -- a flagged module (Task 2's ``-tagged_terms``
directive), or an explicit call site -- not on ``is_cell`` alone.

Cells ride the *existing* C unify/walk tuple branches unchanged (they are
just tuples): this module adds no C code and no new representation
machinery, only Python-level construction/inspection helpers, per the
Phase 2 bridge plan's Global Constraints ("Cells are plain tuples ...
They already unify/walk/key through the existing C tuple branches -- do
not add representation machinery the engine already has.").
"""

from __future__ import annotations

import sys
from typing import Any

from clausal.logic.variables import deref, is_var

__all__ = [
    "TAGGED_TERMS_FLAG",
    "TUPLE_TAG",
    "make_cell",
    "make_tuple_cell",
    "is_cell",
    "cell_functor",
    "cell_args",
    "cell_arity",
]
# NOTE: `_cell_shape` is intentionally NOT in __all__ (internal helper) but
# IS imported directly by clausal/logic/builtins/_helpers.py -- the same
# "leading-underscore, cross-module funnel helper" convention that module
# already uses for _functor_name/_arity/etc. See _cell_shape's docstring.


# The tag used in slot 0 for a "tuple as term data" cell: ``(tuple, e1,
# ...)``. This is the ``tuple`` TYPE OBJECT itself, not the string
# ``"tuple"`` -- see ``is_cell``/``make_tuple_cell``.
TUPLE_TAG = tuple


# The module-namespace key a ``-tagged_terms`` module carries.  The directive
# (clausal/templating/term_rewriting.py, ``_handle_tagged_terms_directive``)
# compiles to a plain module-level ``__clausal_tagged_terms__ = True``
# assignment, and the compiler entrypoints
# (clausal/logic/compiler/predicate.py) read it back off the ``globals_`` they
# are handed -- which for a ``.clausal`` module IS that module's ``__dict__``.
#
# A module-namespace flag rather than a ``module_items`` entry, deliberately:
# module items are recovered separately when a module loads from its ``.pyc``
# cache, whereas an assignment is part of the cached bytecode and therefore
# cannot go missing on the cached path.
TAGGED_TERMS_FLAG = "__clausal_tagged_terms__"


def _valid_functor_slot(resolved_slot0: Any) -> bool:
    """True if *resolved_slot0* is a legal cell slot-0 value (the
    bridge-entry ruling).

    *resolved_slot0* must already be dereferenced by the caller (see
    ``_cell_shape`` below) -- this function does not deref, so it can be
    reused without paying for a second deref of the same value.
    """
    return isinstance(resolved_slot0, str) or resolved_slot0 is TUPLE_TAG or is_var(resolved_slot0)


def _cell_shape(x: Any) -> tuple[bool, Any]:
    """Return ``(is_cell, resolved_slot0)`` for *x*.

    Dereferences slot 0 EXACTLY ONCE (review fix, finding #1: a cell's
    slot 0 must be inspected post-deref, not raw -- a cell built with an
    unbound Var functor that has since been bound by ``unify`` must not
    vanish from cell recognition just because its functor slot resolved).
    ``is_cell`` is defined in terms of this; the funnel accessors in
    ``clausal/logic/builtins/_helpers.py`` import this directly (rather
    than calling ``is_cell`` and then re-deref'ing slot 0 themselves) so a
    single top-level accessor call never dereferences slot 0 twice.

    For an unbound Var, ``deref`` is a no-op (returns the Var itself); for
    a bound Var, it returns the walked-to value. Either way this is one
    (cheap, C-implemented) call.
    """
    if type(x) is not tuple or len(x) < 1:
        return False, None
    resolved = deref(x[0])
    return _valid_functor_slot(resolved), resolved


def make_cell(functor: Any, *args: Any) -> tuple:
    """Construct a cell ``(functor, *args)``, enforcing the slot-0 ruling.

    *functor* must be one of:

      - a ``str`` -- interned via ``sys.intern`` as a convenience (see the
        module docstring's BRIDGE-ENTRY RULING: ``is_cell`` does not
        require this, ``make_cell`` does it only to make repeated
        same-functor cells cheaper to compare/store).
      - ``TUPLE_TAG`` (the ``tuple`` type object) -- for tuple-as-data cells.
      - an unbound ``Var`` -- a higher-order / not-yet-resolved functor slot.

    Anything else (``int``, a class other than ``tuple``, ``None``, ...)
    raises ``TypeError``.
    """
    if isinstance(functor, str):
        functor = sys.intern(functor)
    elif functor is TUPLE_TAG:
        pass
    elif is_var(functor):
        pass
    else:
        raise TypeError(
            "make_cell: functor must be a str, the `tuple` type object "
            f"(TUPLE_TAG), or an unbound Var; got {functor!r} "
            f"({type(functor).__name__})"
        )
    return (functor, *args)


def make_tuple_cell(*elems: Any) -> tuple:
    """Construct a tuple-DATA cell ``(tuple, e1, ..., en)``.

    Equivalent to ``make_cell(TUPLE_TAG, *elems)``, spelled out for callers
    building tuple-as-data cells (no functor validation to speak of --
    ``TUPLE_TAG`` is always valid).
    """
    return (TUPLE_TAG, *elems)


def is_cell(x: Any) -> bool:
    """True if *x* is shaped like a cell.

    A cell is a non-empty ``tuple`` (exactly ``type(x) is tuple`` -- a
    ``tuple`` subclass, e.g. a namedtuple, is deliberately excluded; term
    instances in this engine are dataclasses / ``PredicateMeta`` instances,
    never tuple subclasses, so this cannot collide with them) whose
    DEREFERENCED slot 0 is a ``str``, the ``tuple`` type object, or an
    unbound ``Var`` -- a cell built with an unbound Var functor that has
    since been bound (by ``unify``) is still a cell, recognized by its
    slot 0's current, walked-to value (review fix, finding #1).

    This is a SHAPE-only test -- see the module docstring's KNOWN
    AMBIGUITY note: a plain user tuple like ``("hello", 1)`` also answers
    ``True`` here. That is accepted for this bridge stage, not a bug.
    """
    return _cell_shape(x)[0]


def cell_functor(c: tuple) -> Any:
    """Return the functor slot (slot 0) of cell *c*, dereferenced.

    An unbound-Var functor slot derefs to itself (returned as the Var);
    a bound one derefs to its walked-to value (review fix, finding #1).
    No shape validation -- callers that don't already know *c* is
    cell-shaped should check ``is_cell(c)`` first.
    """
    return deref(c[0])


def cell_args(c: tuple) -> tuple:
    """Return the argument slice (slots 1..) of cell *c*, as a tuple."""
    return c[1:]


def cell_arity(c: tuple) -> int:
    """Return the arity (argument count) of cell *c*."""
    return len(c) - 1
