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

from clausal.logic.atoms import char_atom, mint
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
    assert _answers(mod.inner_catches) == [(mint("inner"),)]


def test_nested_catch_inner_declines_and_outer_catches(mod):
    """Exercises walking *past* a declining handler to the next catcher."""
    assert _answers(mod.outer_catches) == [(mint("outer"),)]


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
# once/findall/`not`/lambda bodies compile shallow and reach a trampoline-mode
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
    assert _answers(mod.catch_throw_via_once) == [(mint("boom"),)]


# ── the two remaining tramp_call drivers, and a raising recovery goal ────────
# Added 2026-08-26 after a review found the `not` lowering emitted its OWN copy
# of the drive loop as generated AST — the one copy with no routing at all.


def test_catch_inside_a_negated_goal_absorbs_the_exception(mod):
    """`not GOAL` is a drive loop of its own (the ``Negate`` lowering).

    The negated predicate's catch/3 absorbs the ValueError and its recovery
    then fails, so the negation succeeds.  Before the fix the exception
    escaped the negation entirely and the whole query raised.
    """
    assert _answers(mod.naf_over_catch) == [(mint("absorbed_then_failed"),)]


def test_catch_inside_a_goal_lambda_absorbs_the_exception(mod):
    """A goal lambda reaches a trampoline-mode callee through _tramp_call."""
    assert _answers(mod.catch_from_callee_via_lambda) == [
        (Compound("ValueError", (_INT_NOPE,)),)]


# ── the general-ITE condition driver (the seventh loop copy) ─────────────────


def test_catch_inside_an_ite_condition_absorbs_the_exception(mod):
    """A catch/3 inside a general-ITE *condition* absorbs; then-branch runs.

    The condition sub-generator is driven by the ITE's own mini-trampoline,
    which — emitted inline — had no exception routing, so the ValueError
    escaped the whole construct instead of reaching the handler.
    """
    assert _answers(mod.ite_cond_catch) == [(mint("then"),)]


def test_declining_catch_in_an_ite_condition_still_lets_the_error_escape(mod):
    """Control: routing must be invisible when no handler absorbs."""
    with pytest.raises(ValueError) as exc_info:
        _answers(mod.ite_cond_decline)
    assert str(exc_info.value) == _INT_NOPE


def test_uncaught_error_in_an_ite_condition_still_escapes(mod):
    """Control: no handler at all — the original exception surfaces."""
    with pytest.raises(ValueError) as exc_info:
        _answers(mod.ite_cond_raw)
    assert str(exc_info.value) == _INT_NOPE


def test_ite_then_branch_runs_once_per_condition_solution(mod):
    """Control: the general ITE enumerates ALL condition solutions."""
    assert _answers(mod.ite_multi) == [(1,), (2,), (3,)]


def test_an_exception_from_a_recovery_goal_reaches_the_outer_catch(mod):
    """The handler absorbs one exception and then raises a different one.

    ``unwind_to_catcher``'s "throw() raised a NEW routable exception" path:
    the walk continues from that frame's own catcher, so the outer catch/3
    binds the SECOND exception, not the first.
    """
    also_nope = "invalid literal for int() with base 10: 'also_nope'"
    assert _answers(mod.outer_catches_a_raising_recovery) == [
        (Compound("ValueError", (also_nope,)),)]


# ── the routing policy itself ────────────────────────────────────────────────


class TestWhatIsRoutable:
    """``_is_routable`` is the Python twin of C ``is_routable_exception``.

    Both are always live: the helper is defined above the C fast-path import,
    so ``tramp_call`` and the ``not`` lowering use exactly this function while
    the C drive loops use the twin.  What these tests do NOT cover is the
    pure-Python ``trampoline`` / ``solutions`` / ``_drive_until_yield``
    fallbacks, which the C extension shadows in any built tree; their routing
    is verified only by reading, and by this shared policy.
    """

    def test_ordinary_python_errors_are_routable(self):
        from clausal.logic.trampoline import _is_routable
        assert _is_routable(ValueError("x"))
        assert _is_routable(NameError("x"))

    def test_control_signals_are_not_routable(self):
        from clausal.logic.trampoline import _is_routable
        assert not _is_routable(StopIteration())
        assert not _is_routable(SystemExit(3))
        assert not _is_routable(GeneratorExit())
        assert not _is_routable(KeyboardInterrupt())

    def test_a_pep479_wrapper_is_not_routable(self):
        """A converted exhaustion must never be offered to catch/3 as an error."""
        from clausal.logic.trampoline import _is_routable
        wrapper = RuntimeError("generator raised StopIteration")
        wrapper.__cause__ = StopIteration()
        assert not _is_routable(wrapper)
        # A genuine RuntimeError from user code still is.
        assert _is_routable(RuntimeError("from a ++ escape"))

    def test_the_engine_protocol_error_is_not_routable(self):
        from clausal.logic.trampoline import _is_routable
        err = RuntimeError("StepGenerator inner generator returned unexpectedly")
        err.__clausal_engine_protocol__ = True
        assert not _is_routable(err)

    def test_the_c_protocol_error_carries_the_marker(self):
        """The C StepGen_send marks its protocol error so ``_is_routable`` can
        exclude it without matching on message text."""
        from clausal.logic.trampoline import StepGenerator

        def returns_without_yielding(_self, _proceed, _fail, _catcher, _trail):
            return
            yield  # pragma: no cover — makes this a generator function

        sg = StepGenerator(returns_without_yielding, None, None, None, None)
        with pytest.raises(RuntimeError) as exc_info:
            sg.send(None)
        assert getattr(exc_info.value, "__clausal_engine_protocol__", False)
