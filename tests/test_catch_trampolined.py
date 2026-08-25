"""catch/3 must see exceptions raised by a *trampolined* subgoal.

A trampoline-compiled predicate does not call its callees; it yields
``(child_step_generator, None)`` and the driver runs the child.  The child
therefore raises inside the driver's frame, not inside the ``try`` the compiled
``catch/3`` put in the caller.  The driver is the only place that can hand the
exception back, and it does so by throwing it into the failing generator's
``catcher`` chain — which historically only happened for ``LogicException``.
Every other Python exception walked straight past every enclosing ``catch/3``.

That is why the bug looked type-specific: ``throw/1`` and the typed builtin
errors are LogicExceptions and were routed; a ValueError out of a ``++`` escape,
or an UndefinedNameError from an unimported sibling predicate, was not.

The fixture puts each raising goal in its own predicate so the callee is always
driven through the trampoline seam.  See
``tests/fixtures/catch_trampolined.clausal``.
"""

from __future__ import annotations

import importlib

import pytest

from clausal.logic.solve import _deref_walk
from clausal.logic.variables import Var
from clausal.terms import Compound

_INT_NOPE = "invalid literal for int() with base 10: 'nope'"


@pytest.fixture(scope="module")
def mod():
    # conftest.py puts tests/fixtures on sys.path; the .clausal import hook
    # compiles the file on import.
    return importlib.import_module("catch_trampolined")


def _answers(pred, arity=1):
    """All solutions of *pred* as a list of fully-dereferenced arg tuples."""
    args = [Var() for _ in range(arity)]
    return [tuple(_deref_walk(a) for a in args) for _ in pred(*args)]


# ── the bug ──────────────────────────────────────────────────────────────────


def test_catch_catches_python_error_from_trampolined_callee(mod):
    """A plain ValueError raised by a trampolined callee reaches catch/3."""
    assert _answers(mod.catch_from_callee) == [(Compound("ValueError", (_INT_NOPE,)),)]


def test_catch_catches_undefined_name_from_trampolined_callee(mod):
    """The original repro: an unimported sibling predicate raises NameError.

    The functor is the *raw* ``NameError``, not the enriched
    ``UndefinedNameError``.  That enrichment lives at the outermost driver
    (``solve._drive_trampoline``), which is strictly above every catch/3 and
    only ever sees exceptions every handler declined — it is the message the
    author gets when nothing catches, not a term a handler is owed.  Routing
    must not let the trampoline rewrite an exception on its way to a live
    handler.
    """
    (term,), = _answers(mod.catch_undefined_name)
    assert isinstance(term, Compound)
    assert term.functor == "NameError"
    assert "cite" in term.args[0]


def test_uncaught_undefined_name_still_reaches_the_enrichment_seam(mod):
    """The other half of that: with no handler, the author still gets the hunt.

    ``_drive_trampoline`` enriches a NameError that escaped every catch/3 with
    the sibling-module search.  Routing must leave an unhandled exception
    untouched for it to find.
    """
    from clausal.predicate_diagnostics import UndefinedNameError

    with pytest.raises(UndefinedNameError) as exc_info:
        _answers(mod.undefined_in_callee)
    message = str(exc_info.value)
    assert "cite" in message
    assert "catch_tramp_sibling" in message


# ── the control: the already-working inline route must not regress ───────────


def test_catch_still_catches_the_same_error_raised_inline(mod):
    """The identical exception raised in the catch frame itself."""
    assert _answers(mod.catch_inline) == [(Compound("ValueError", (_INT_NOPE,)),)]


# ── a catcher that does not match must still propagate ───────────────────────


def test_non_matching_catcher_propagates_the_original_exception(mod):
    """The handler declines, so the ORIGINAL Python exception surfaces.

    Not a LogicException and not a re-wrapped anything: routing an exception
    through the catcher chain must leave an unhandled one exactly as it was, or
    the ``except NameError`` seam in ``_drive_trampoline`` (and every Python
    caller's ``except``) stops matching.
    """
    with pytest.raises(ValueError) as exc_info:
        _answers(mod.catch_wrong_catcher)
    assert str(exc_info.value) == _INT_NOPE


# ── nested catch across two predicates ───────────────────────────────────────


def test_nested_catch_inner_absorbs_and_outer_does_not_fire(mod):
    assert _answers(mod.inner_catches) == [("inner",)]


def test_nested_catch_inner_declines_and_outer_catches(mod):
    """Exercises walking *past* a declining handler to the next catcher."""
    assert _answers(mod.outer_catches) == [("outer",)]


# ── control-flow exceptions must not be stolen ───────────────────────────────


def test_system_exit_from_a_trampolined_callee_is_not_caught(mod):
    """halt/1 raises SystemExit — a BaseException, not catch/3's business."""
    with pytest.raises(SystemExit) as exc_info:
        _answers(mod.catch_halt)
    assert exc_info.value.code == 3


def test_generator_exit_still_closes_a_catch_wrapped_search(mod):
    """Abandoning the iterator mid-search must not be routed as an error."""
    n = Var()
    gen = iter(mod.catch_multi(n))
    next(gen)
    assert _deref_walk(n) == 1
    gen.close()          # raises GeneratorExit inside the driver
    with pytest.raises(StopIteration):
        next(gen)


def test_catch_around_a_many_solution_callee_yields_all(mod):
    assert _answers(mod.catch_multi) == [(1,), (2,), (3,)]


# ── the same seam under a shallow driver ─────────────────────────────────────
#
# once/findall/\+ /lambda bodies compile shallow and reach a trampoline-mode
# callee through ``runtime/tramp_call.py``'s mini-trampoline — a fourth copy of
# the drive loop, which had no catcher routing at all.  A catch/3 *inside* the
# trampolined predicate was therefore inert under any of them, for throw/1 as
# much as for a Python exception.


def test_catch_inside_a_predicate_called_through_once(mod):
    assert _answers(mod.catch_from_callee_via_once) == [
        (Compound("ValueError", (_INT_NOPE,)),)
    ]


def test_catch_inside_a_predicate_called_through_findall(mod):
    assert _answers(mod.catch_from_callee_via_findall) == [
        ([Compound("ValueError", (_INT_NOPE,))],)
    ]


def test_throw_caught_inside_a_predicate_called_through_once(mod):
    """The LogicException half of the same hole."""
    assert _answers(mod.catch_throw_via_once) == [("boom",)]
