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

from clausal.logic.variables import is_var

__all__ = [
    "TUPLE_TAG",
    "make_cell",
    "make_tuple_cell",
    "is_cell",
    "cell_functor",
    "cell_args",
    "cell_arity",
]


# The tag used in slot 0 for a "tuple as term data" cell: ``(tuple, e1,
# ...)``. This is the ``tuple`` TYPE OBJECT itself, not the string
# ``"tuple"`` -- see ``is_cell``/``make_tuple_cell``.
TUPLE_TAG = tuple


def _valid_functor_slot(slot0: Any) -> bool:
    """True if *slot0* is a legal cell slot-0 value (the bridge-entry ruling)."""
    return isinstance(slot0, str) or slot0 is TUPLE_TAG or is_var(slot0)


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
    never tuple subclasses, so this cannot collide with them) whose slot 0
    is a ``str``, the ``tuple`` type object, or an unbound ``Var``.

    This is a SHAPE-only test -- see the module docstring's KNOWN
    AMBIGUITY note: a plain user tuple like ``("hello", 1)`` also answers
    ``True`` here. That is accepted for this bridge stage, not a bug.
    """
    return type(x) is tuple and len(x) >= 1 and _valid_functor_slot(x[0])


def cell_functor(c: tuple) -> Any:
    """Return the functor slot (slot 0) of cell *c*.

    No validation -- callers that don't already know *c* is cell-shaped
    should check ``is_cell(c)`` first.
    """
    return c[0]


def cell_args(c: tuple) -> tuple:
    """Return the argument slice (slots 1..) of cell *c*, as a tuple."""
    return c[1:]


def cell_arity(c: tuple) -> int:
    """Return the arity (argument count) of cell *c*."""
    return len(c) - 1
