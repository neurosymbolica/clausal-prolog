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

from clausal import cell_args, cell_functor
from clausal.logic.exceptions import (
    DispatchTargetError, LogicException,
)
from clausal.logic.predicate import _dispatch_at
from tests._suffix import SEAM


def test_a_module_target_raises_dispatch_target_error():
    mod = types.ModuleType("some.package")
    with pytest.raises(DispatchTargetError) as info:
        _dispatch_at(mod, 2)
    exc = info.value
    assert isinstance(exc, LogicException), "catch/3 must see it"
    term = exc.term
    assert type(term) is tuple and cell_functor(term) == "error"
    inner = cell_args(term)[0]
    assert cell_functor(inner) == "type_error"
    assert cell_args(inner)[0] == "callable"
    rendered = str(exc)
    assert "DispatchTargetError" in rendered, "the token the downstream gates key on"
    assert "module 'some.package'" in exc.message, "what the goal actually resolved to"
    # The rendering is the term as Scryer writes it -- no indicator leads the
    # prose, so error/2's second argument is unbound -- then the prose.
    assert rendered == (
        "Uncaught logic exception: error(type_error(callable,'some.package'),_): "
        + exc.message)
    assert cell_args(inner)[1] == "some.package", "the culprit is the module's name"


def test_any_object_without_the_protocol_raises_the_same_class():
    """Not only modules: anything with no ``_get_dispatch`` is the same
    mistake, and it must never surface as a raw AttributeError again."""
    with pytest.raises(DispatchTargetError):
        _dispatch_at(object(), 1)
    with pytest.raises(DispatchTargetError) as info:
        _dispatch_at(42, 0)
    inner = cell_args(info.value.term)[0]
    assert cell_args(inner)[1] == 42, "the culprit is the offending VALUE, not its type"
    assert "a int value 42" in str(info.value)


def test_a_huge_or_hostile_repr_cannot_break_the_diagnostic():
    """Building an exception must never itself raise, and must not render a
    multi-megabyte message: the repr in the prose is bounded and guarded."""
    class Hostile:
        def __repr__(self):
            raise RuntimeError("repr exploded")

    with pytest.raises(DispatchTargetError) as info:
        _dispatch_at(Hostile(), 1)
    assert "Hostile" in str(info.value)
    assert cell_args(cell_args(info.value.term)[0])[1] == "Hostile", (
        "a value whose repr raises cannot be the culprit; its type stands in")
    with pytest.raises(DispatchTargetError) as info:
        _dispatch_at(list(range(100_000)), 1)
    assert "a list value [0, 1, 2, 3, 4, 5, ...]" in str(info.value), (
        "the message shows a BOUNDED repr")


def test_a_foreign_implementor_is_still_called_bare():
    """The frozen protocol (ruled 2026-09-22): a plain class whose whole
    contract is ``def _get_dispatch(self)`` is called with NO arity, as it
    always was."""
    sentinel = object()

    class Foreign:
        def _get_dispatch(self):
            return sentinel

    assert _dispatch_at(Foreign(), 3) is sentinel


def test_the_atom_case_keeps_its_own_shape():
    """An atom that is not callable stays ``existence_error(procedure, ...)``
    in a plain LogicException: the gates tell 'resolved to data' from
    'resolved to a module' by these two shapes, so they must not merge."""
    with pytest.raises(LogicException) as info:
        _dispatch_at("just_an_atom", 1)
    assert not isinstance(info.value, DispatchTargetError)
    assert cell_functor(cell_args(info.value.term)[0]) == "existence_error"


def _write(tmp_path, name, src):
    import textwrap
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


def test_a_compiled_dotted_goal_that_lands_on_a_submodule_raises_it(tmp_path, monkeypatch):
    """END TO END, the shape the downstream tooling actually meets: a
    ``.clausal`` body calls ``pkg.shadow(X)``, and ``pkg.shadow`` is a
    SUBMODULE of the imported package rather than a predicate inside it (a
    module-shadow collision).  The compiled goal goes through the runtime
    funnel ``$dispatch_at(pkg.shadow, 1)`` and must surface as
    ``DispatchTargetError`` -- a ``LogicException`` -- not as CPython's
    ``AttributeError: module ... has no attribute '_get_dispatch'``."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var

    monkeypatch.syspath_prepend(str(tmp_path))
    pkg = tmp_path / "w3shadowpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import shadow\n")
    (pkg / "shadow.py").write_text("VALUE = 1\n")
    use = _write(tmp_path, f"w3shadowuse{SEAM}", """
        -import_module(w3shadowpkg)

        w3_use(X) <- w3shadowpkg.shadow(X)
    """)
    mod = _load_module("_w3shadowuse", str(use))
    with pytest.raises(LogicException) as info:
        list(call("w3_use", Var(), module=mod.__dict__["$module"]))
    assert isinstance(info.value, DispatchTargetError)
    assert "module 'w3shadowpkg.shadow'" in info.value.message
    assert "module 'w3shadowpkg.shadow'" in str(info.value)
