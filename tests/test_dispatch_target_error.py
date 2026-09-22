"""W3 of the PredicateMeta retirement: a goal whose callee resolves to
something that is not a predicate at all -- a MODULE, most often, when a
dotted name lands on a package rather than on a predicate inside it -- raises
``DispatchTargetError`` from the one funnel every such callee passes through,
``_dispatch_at``.

Before W3 the funnel fell through to ``obj._get_dispatch()`` and the caller
saw CPython's own ``AttributeError: module 'x.y' has no attribute
'_get_dispatch'``.  Two downstream gates classify that failure by matching
that wording, and the wording is an interpreter detail nobody owns.  The
exception's CLASS NAME is the token they key on instead, so it appears in the
rendered text -- and it stays a ``LogicException``, so ``catch/3`` and every
existing ``except LogicException`` see it exactly as they see the atom case.
"""
import types

import pytest

from clausal.logic.exceptions import DispatchTargetError, LogicException
from clausal.logic.predicate import PredicateMeta, _dispatch_at, make_predicate


def test_a_module_target_raises_dispatch_target_error():
    mod = types.ModuleType("some.package")
    with pytest.raises(DispatchTargetError) as info:
        _dispatch_at(mod, 2)
    exc = info.value
    assert isinstance(exc, LogicException), "catch/3 must see it"
    term = exc.term
    assert term.functor == "error"
    inner = term.args[0]
    assert inner.functor == "type_error"
    assert inner.args[0] == "callable"
    rendered = str(exc)
    assert "DispatchTargetError" in rendered, "the token the downstream gates key on"
    assert "some.package" in rendered, "what the goal actually resolved to"
    assert "module" in rendered


def test_any_object_without_the_protocol_raises_the_same_class():
    """Not only modules: anything with no ``_get_dispatch`` is the same
    mistake, and it must never surface as a raw AttributeError again."""
    with pytest.raises(DispatchTargetError):
        _dispatch_at(object(), 1)
    with pytest.raises(DispatchTargetError):
        _dispatch_at(42, 0)


def test_a_foreign_implementor_is_still_called_bare():
    """The frozen protocol (ruled 2026-09-22): a plain class whose whole
    contract is ``def _get_dispatch(self)`` is called with NO arity, as it
    always was."""
    sentinel = object()

    class Foreign:
        def _get_dispatch(self):
            return sentinel

    assert _dispatch_at(Foreign(), 3) is sentinel


def test_a_predicate_class_is_still_arity_aware():
    cls = make_predicate("W3Pred", ["a", "b"])
    assert isinstance(cls, PredicateMeta)
    with pytest.raises(Exception) as info:
        _dispatch_at(cls, 5)          # wrong arity: the class refuses
    assert not isinstance(info.value, DispatchTargetError), (
        "a wrong-arity call on a real predicate is a different mistake")


def test_the_atom_case_keeps_its_own_shape():
    """An atom that is not callable stays ``existence_error(procedure, ...)``
    in a plain LogicException: the gates tell 'resolved to data' from
    'resolved to a module' by these two shapes, so they must not merge."""
    with pytest.raises(LogicException) as info:
        _dispatch_at("just_an_atom", 1)
    assert not isinstance(info.value, DispatchTargetError)
    assert info.value.term.args[0].functor == "existence_error"
