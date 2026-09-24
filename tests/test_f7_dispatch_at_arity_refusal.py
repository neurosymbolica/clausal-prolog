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

REVERSED IN PART by the name + ARITY ruling (operator, 2026-09-24): a
predicate name is name + ARITY, so a same-named builtin (or the module's own
row) AT THE CALL ARITY is the call's normal answer, not a silent shadow --
``get_dispatch`` is now asked BEFORE the refusal, in both eras.  What F7
keeps is the refusal where nothing answers at the call arity.
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


def _numlist_answers(fn, *args):
    from clausal.logic.solve import _drive_trampoline
    from clausal.logic.variables import Trail, Var, deref
    out = Var()
    return [deref(out) for _ in _drive_trampoline(fn, Trail(), *args, out)]


@pytest.mark.parametrize("era", ["class", "handle"])
def test_wrong_arity_resolves_normally_to_the_builtin_at_the_call_arity(
        tmp_path, monkeypatch, era):
    """REVERSED by the name + ARITY ruling (operator, 2026-09-24).

    This test used to be ``test_wrong_arity_does_not_silently_resolve_to_a_
    builtin_at_the_other_arity`` and pinned the opposite: a local
    ``numlist/1`` called at arity 2 had to REFUSE rather than answer with the
    builtin ``numlist/2``.  The ruling: a predicate name is name + ARITY, so
    ``numlist/1`` is not the target of a ``numlist/2`` call at all, and the
    call resolves normally -- here to the builtin ``numlist/2``.  The old
    refusal was an artefact of ``PredicateMeta`` being a class, not
    behaviour to preserve.  The refusal survives only where NOTHING answers
    at the call arity (``test_wrong_arity_call_on_a_user_predicate_is_the_
    arity_refusal`` above).  Both eras -- the class binding and the
    module-qualified handle -- must agree."""
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS
    from clausal.logic.predicate import PredicateMeta
    assert ("numlist", 2) in _BUILTINS or ("numlist", 2) in _DB_BUILTINS
    mod = _load(tmp_path, monkeypatch, f"f7_shadow_{era}", """
        -module(f7_shadow_ERA, [numlist(A)])
        numlist(1),
    """.replace("ERA", era))
    cls = mod.__dict__["$module"].module_dict["numlist"]
    assert isinstance(cls, PredicateMeta)
    target = cls if era == "class" else mangle(f"f7_shadow_{era}", "numlist")
    fn = _dispatch_at(target, 2)
    # the builtin numlist(High, List): numlist(3, L) gives L = [1, 2, 3]
    assert _numlist_answers(fn, 3) == [[1, 2, 3]]
    # the arity-1 call is untouched and still reaches the LOCAL predicate,
    # not a builtin (there is no numlist/1 builtin to confuse it with).
    assert ("numlist", 1) not in _BUILTINS and ("numlist", 1) not in _DB_BUILTINS
    fn1 = _dispatch_at(target, 1)
    from clausal.logic.solve import _drive_trampoline
    from clausal.logic.variables import Trail
    assert len(list(_drive_trampoline(fn1, Trail(), 1))) == 1
    assert len(list(_drive_trampoline(fn1, Trail(), 2))) == 0


@pytest.mark.parametrize("era", ["class", "handle"])
def test_wrong_arity_with_nothing_else_answering_still_refuses(
        tmp_path, monkeypatch, era):
    """The half of F7 the ruling keeps: ``pred/1`` called at 2, with no
    ``pred/2`` row and no ``pred/2`` builtin, is the arity refusal in both
    eras -- not an existence error and not a raw TypeError."""
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS
    from clausal.logic.predicate import PredicateMeta
    mod = _load(tmp_path, monkeypatch, f"f7_nothing_{era}", """
        -module(f7_nothing_ERA, [pred(A)])
        pred(1),
    """.replace("ERA", era))
    assert ("pred", 2) not in _BUILTINS and ("pred", 2) not in _DB_BUILTINS
    cls = mod.__dict__["$module"].module_dict["pred"]
    assert isinstance(cls, PredicateMeta)
    target = cls if era == "class" else mangle(f"f7_nothing_{era}", "pred")
    with pytest.raises(PredicateArityMismatchError, match="takes 1 argument"):
        _dispatch_at(target, 2)


@pytest.mark.parametrize("era", ["class", "handle"])
def test_wrong_arity_reaches_the_modules_own_row_at_the_call_arity(
        tmp_path, monkeypatch, era):
    """Name + ARITY ruling: the module's own ``ping/2`` answers a ``ping/2``
    call made through its ``ping/0`` binding.  Before the ruling the eras
    DISAGREED here: the handle arm answered (``get_dispatch`` found the row)
    while the class arm refused off the ``ping/0`` clause heads.

    One file cannot define both ``ping/0`` and ``ping/2`` (one name, one
    arity, refused at load), so the ``ping/2`` row is installed on the
    owner's db with ``set_dispatch``, borrowing a compiled ``ping/2`` from a
    second module."""
    from clausal.logic.predicate import PredicateMeta
    from clausal.logic.solve import _drive_trampoline, call as _call
    from clausal.logic.variables import Trail, Var
    name = f"f7_ownrow_{era}"
    mod = _load(tmp_path, monkeypatch, name, """
        -module(NAME, [])
        ping <- (1 > 0)
    """.replace("NAME", name))
    donor = _load(tmp_path, monkeypatch, f"{name}_donor", """
        -module(NAME_donor, [])
        ping(1, 2),
    """.replace("NAME", name))
    M, D = mod.__dict__["$module"], donor.__dict__["$module"]
    list(_call("ping", 1, Var(), module=D))              # compile it
    M.db.set_dispatch("ping", 2, D.db.get_dispatch("ping", 2))
    cls = M.module_dict["ping"]
    assert isinstance(cls, PredicateMeta) and cls._fields == ()
    assert cls._row is not None and cls._row._key == ("ping", 0)
    target = cls if era == "class" else mangle(name, "ping")
    fn = _dispatch_at(target, 2)
    assert len(list(_drive_trampoline(fn, Trail(), 1, 2))) == 1
    assert len(list(_drive_trampoline(fn, Trail(), 1, 3))) == 0
    # and ping/0 is still ping/0
    assert len(list(_drive_trampoline(_dispatch_at(target, 0), Trail()))) == 1


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
