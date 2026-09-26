"""Test support for W4b-3 slice 6: ``make_predicate`` is RETIRED (it raises
``MakePredicateRetiredError``).  Its test callers split two ways:

* :func:`term_ctor` -- for a test that used a ``make_predicate`` class only
  as a TERM BUILDER (a clause head, a fact, a pattern) to reach some other
  behaviour.  It is a plain callable, not a class: it builds the cell through
  ``build_term_cell``, the one home of construction against a signature that
  ``PredicateMeta.__call__`` and a handle's ``$head`` both use, so the cell,
  the arity check and the construction errors are the ones the class gave.

* :class:`RowPredicate` -- a HANDLE on a row of a named module Database, for
  a test that compiled into a class only to read back the row (W4b-3 slice
  7).  (``class_arm_predicate`` built a ``PredicateMeta`` class for the
  class-machinery tests; the class and those tests were retired together
  at W4b-3 slice 7.)
"""
from __future__ import annotations

from typing import Any

from clausal.logic.predicate import build_term_cell


class TermCtor:
    """A term constructor for *name* with the signature *fields*: calling it
    builds the cell ``(name, slot, ...)`` (the ATOM *name* for a zero-field
    one called with nothing) through ``build_term_cell`` -- the one home of
    construction against a signature, so its arity/field errors are the ones
    a module's clause heads raise.  It records where it was made, as the
    rewriter's declaration record does, so a construction error carries a
    "registered by:" site.  Not a class, so no class arm ever sees it."""

    __slots__ = ("__name__", "_fields", "_site")

    def __init__(self, name: str, fields, _depth: int = 1) -> None:
        from clausal.logic.predicate import _source_site
        self.__name__ = name
        self._fields = tuple(fields)
        self._site = _source_site(_depth + 1)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if not self._fields and not args and not kwargs:
            return self.__name__
        return build_term_cell(self.__name__, self._fields, args,
                               dict(kwargs), site=self._site)

    def __repr__(self) -> str:
        return f"TermCtor({self.__name__!r}, {self._fields!r})"


def term_ctor(name: str, fields) -> TermCtor:
    """See :class:`TermCtor` (its site is *term_ctor*'s caller)."""
    return TermCtor(name, fields, _depth=2)


def dispatch_solutions(dispatch, *args, trail=None) -> list:
    """Every answer of a compiled *dispatch* function for *args*, as tuples
    of the dereferenced arguments: the trampoline driven directly, as
    ``solve.call`` drives a class's ``_get_dispatch()`` -- for a compile with
    no Database and no class (``compile_predicate_trampoline`` returns the
    dispatch it installs)."""
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.logic.variables import Trail, deref
    trail = Trail() if trail is None else trail
    sg = StepGenerator(dispatch, None, None, None, *args, trail)
    return list(solutions(sg, lambda: tuple(deref(a) for a in args)))


class ForeignPredicate:
    """The FROZEN duck-typed protocol for a predicate supplied from Python:
    a plain object (not a class) whose ``_get_dispatch()`` returns the
    predicate's dispatch function (see ``import_diagnostics.
    describe_unowned_predicate_class``)."""

    __slots__ = ("_dispatch",)

    def __init__(self, dispatch) -> None:
        self._dispatch = dispatch

    def _get_dispatch(self):
        return self._dispatch


class RowPredicate:
    """A predicate as a loaded module holds it since the flip: a HANDLE
    naming a row of a module's Database.  For tests that used to compile
    into a ``PredicateMeta`` class (the retired class-era fixture) only to
    read back the row the compile wrote -- index plans, the lock, the
    dispatch.

    ONE convention: compile with ``compile_predicate_*(functor, arity,
    clauses, pred.db, pred_cls=pred.handle)`` -- the Database and the
    handle, exactly the arguments ``compiler_v2`` step 5 passes for a
    loaded module.  The compiler never sees this object.

    ``_state_row()`` (creating) / ``_row`` (or ``None``) answer that row, and
    calling the object builds a head cell (``build_term_cell``), so a test
    body written against the class reads the same state from the same
    place."""

    _serial = 0

    def __init__(self, name: str, fields, db=None) -> None:
        from clausal.logic.database import Module
        from clausal.logic.predicate import (
            mint_predicate_handle, register_handle_owner)
        if db is None:
            RowPredicate._serial += 1
            modname = f"_rowpred_{name}_{RowPredicate._serial}"
            db = Module(modname, module_dict={"__name__": modname}).db
        self.db = db
        self.__name__ = name
        self._fields = tuple(fields)
        register_handle_owner(db)
        self.handle = mint_predicate_handle(db, name)

    def _state_row(self):
        return self.db.row(self.__name__, len(self._fields), create=True)

    @property
    def _row(self):
        return self.db.row(self.__name__, len(self._fields))

    def __call__(self, *args, **kwargs):
        return build_term_cell(self.__name__, self._fields, args,
                               dict(kwargs))

    def _assertz(self, clause) -> None:
        """Append *clause* to the row (``Database.assertz``)."""
        self.db.assertz(clause)
