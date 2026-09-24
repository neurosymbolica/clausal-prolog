"""F7 (ruled 2026-09-24): ``_dispatch_at``'s arity-aware ``PredicateMeta`` arm
is deleted, and the wrong-arity-vs-existence-error distinction that arm used
to make moves into the ``type(obj) is str`` (mangled-handle) arm, ahead of
``Database.get_dispatch``'s builtin-registry fallback.

The hazard this guards: ``Database.get_dispatch`` falls back to a same-named
builtin keyed ``(functor, arity)`` when the handle's own module has no
dispatch entry at the CALL arity.  A user predicate called at the wrong
arity is exactly that shape, so without a check ahead of the fallback, a
wrong-arity call on ``foo/2`` could silently resolve to a builtin ``foo/3``
instead of refusing.  ``numlist`` is a real, dual-arity builtin
(``numlist/2`` and ``numlist/3``, ``clausal/logic/builtins/lists.py``), which
makes it the concrete population this module's shadowing test exercises.
"""
import sys
import textwrap

import pytest

from clausal.logic.atoms import mangle
from clausal.logic.predicate import _dispatch_at
from clausal.predicate_diagnostics import PredicateArityMismatchError
from clausal.logic.exceptions import LogicException


def _load(tmp_path, monkeypatch, name, body):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}.clausal"
    p.write_text(textwrap.dedent(body).lstrip())
    mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    return mod


def test_wrong_arity_call_on_a_user_predicate_is_the_arity_refusal(tmp_path, monkeypatch):
    """Not an existence error, and not a raw AttributeError/TypeError: the
    same ``PredicateArityMismatchError`` the class-object arm always gave."""
    mod = _load(tmp_path, monkeypatch, "f7_wrongarity", """
        -module(f7_wrongarity, [pred(A)])
        pred(1),
        pred(2),
    """)
    with pytest.raises(PredicateArityMismatchError) as info:
        _dispatch_at(mangle("f7_wrongarity", "pred"), 2)
    assert "pred" in str(info.value)
    assert "1 argument" in str(info.value) or "takes 1" in str(info.value)


def test_correct_arity_call_is_unchanged(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "f7_rightarity", """
        -module(f7_rightarity, [pred(A)])
        pred(1),
        pred(2),
    """)
    fn = _dispatch_at(mangle("f7_rightarity", "pred"), 1)
    assert callable(fn)


def test_wrong_arity_does_not_silently_resolve_to_a_builtin_at_the_other_arity(tmp_path, monkeypatch):
    """The shadowing hazard, concretely: a local ``numlist/1`` shares its name
    with the builtin ``numlist/2`` (and ``numlist/3``).  Calling it at arity 2
    must refuse -- never silently hand back the builtin's ``numlist/2``."""
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS
    mod = _load(tmp_path, monkeypatch, "f7_shadow", """
        -module(f7_shadow, [numlist(A)])
        numlist(1),
    """)
    with pytest.raises(PredicateArityMismatchError):
        fn = _dispatch_at(mangle("f7_shadow", "numlist"), 2)
        builtin_fn = (_BUILTINS.get(("numlist", 2))
                      or _DB_BUILTINS.get(("numlist", 2)))
        assert fn is not builtin_fn, (
            "silently resolved the local numlist/1's wrong-arity call to "
            "the numlist/2 builtin instead of refusing"
        )
    # the arity-1 call is untouched and still reaches the LOCAL predicate,
    # not the builtin.
    fn1 = _dispatch_at(mangle("f7_shadow", "numlist"), 1)
    builtin_fn1 = _BUILTINS.get(("numlist", 1)) or _DB_BUILTINS.get(("numlist", 1))
    assert builtin_fn1 is None, "sanity: there is no numlist/1 builtin to confuse this with"
    assert callable(fn1)


def test_a_foreign_duck_typed_implementor_is_still_called_bare():
    """The frozen, arity-free protocol: a plain class with no ``PredicateMeta``
    in its MRO, whose whole contract is ``def _get_dispatch(self)``, must
    still be called with no ``arity`` argument -- unaffected by F7."""

    class _ForeignPredicate:
        def __init__(self):
            self.calls = []

        def _get_dispatch(self):
            self.calls.append(())
            return lambda *a: iter(())

    obj = _ForeignPredicate()
    fn = _dispatch_at(obj, 3)
    assert callable(fn)
    assert obj.calls == [()], "must be called with no arity argument"
