"""Test support for W4b-3 slice 6: ``make_predicate`` is RETIRED (it raises
``MakePredicateRetiredError``).  Its test callers split two ways:

* :func:`term_ctor` -- for a test that used a ``make_predicate`` class only
  as a TERM BUILDER (a clause head, a fact, a pattern) to reach some other
  behaviour.  It is a plain callable, not a class: it builds the cell through
  ``build_term_cell``, the one home of construction against a signature that
  ``PredicateMeta.__call__`` and a handle's ``$head`` both use, so the cell,
  the arity check and the construction errors are the ones the class gave.

* :func:`class_arm_predicate` -- for a test of the CLASS MACHINERY itself
  (``_bind_row``, detached rows, the class arm of an era-agnostic accessor,
  ``_refuse_call_at``, ...).  That code is still in the engine until the class
  is deleted (W4b-3 slice 7), which deletes these tests with it; until then
  they keep covering it.  It builds the class exactly as ``make_predicate``
  did (``PredicateMeta(name, (), {"_fields": ...})``).  Every caller is one
  grep away: ``class_arm_predicate``.
"""
from __future__ import annotations

from typing import Any

from clausal.logic.predicate import PredicateMeta, build_term_cell


def class_arm_predicate(name: str, fields) -> "PredicateMeta":
    """A ``PredicateMeta`` class, as the retired ``make_predicate`` built it.
    For tests of the class machinery only; see the module docstring."""
    from clausal.logic.predicate import _source_site
    cls = PredicateMeta(name, (), {"_fields": tuple(fields)})
    # ``make_predicate`` lived in the clausal package, so the class's
    # ``_registered_at`` (the "registered by:" line) skipped it and named its
    # CALLER; this helper is outside the package, so name the caller here.
    if "_registered_at" not in cls._fields:
        cls._registered_at = _source_site(2)
    return cls


class TermCtor:
    """A term constructor for *name* with the signature *fields*: calling it
    builds the cell ``(name, slot, ...)`` (the ATOM *name* for a zero-field
    one called with nothing).  Not a class, so no class arm ever sees it."""

    __slots__ = ("__name__", "_fields")

    def __init__(self, name: str, fields) -> None:
        self.__name__ = name
        self._fields = tuple(fields)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if not self._fields and not args and not kwargs:
            return self.__name__
        return build_term_cell(self.__name__, self._fields, args,
                               dict(kwargs))

    def __repr__(self) -> str:
        return f"TermCtor({self.__name__!r}, {self._fields!r})"


def term_ctor(name: str, fields) -> TermCtor:
    """See :class:`TermCtor`."""
    return TermCtor(name, fields)


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
