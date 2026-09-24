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
    """Name + ARITY ruling: a module's ``ping/0`` and its ``ping/2`` are two
    predicates, and each binding answers each arity.  Before the ruling the
    eras DISAGREED here: the handle arm answered while the class arm
    refused.

    The ``ping/2`` row is built by a real runtime ``assertz(ping(1, 2))``.
    (Not ``-dynamic(ping/2)`` in the file: that plus ``ping <- ...`` crashes
    at load on main too -- a separate defect the controller is filing.  One
    file cannot author both ``ping/0`` and ``ping(1, 2)`` either: one name,
    one arity per file.)  The assertz RE-BINDS the ``ping`` class to the
    ``ping/2`` row, so the class-era ``ping/0`` call is the one the class-arm
    fallback has to rescue."""
    from clausal.logic.predicate import PredicateMeta
    from clausal.logic.solve import _drive_trampoline, call as _call
    from clausal.logic.variables import Trail
    from clausal.terms import Compound
    name = f"f7_ownrow_{era}"
    mod = _load(tmp_path, monkeypatch, name, """
        -module(NAME, [])
        ping <- (1 > 0)
    """.replace("NAME", name))
    M = mod.__dict__["$module"]
    assert M.db.row("ping", 2) is None
    assert len(list(_call("assertz", Compound("ping", (1, 2)), module=M))) == 1
    assert len(M.db.row("ping", 2).clauses) == 1
    cls = M.module_dict["ping"]
    assert isinstance(cls, PredicateMeta) and cls._fields == ()
    target = cls if era == "class" else mangle(name, "ping")
    fn = _dispatch_at(target, 2)
    assert len(list(_drive_trampoline(fn, Trail(), 1, 2))) == 1
    assert len(list(_drive_trampoline(fn, Trail(), 1, 3))) == 0
    # and ping/0 is still ping/0
    assert len(list(_drive_trampoline(_dispatch_at(target, 0), Trail()))) == 1


def test_an_aliased_import_resolves_the_other_arity_in_the_OWNER_under_the_OWNER_name(
        tmp_path, monkeypatch):
    """Review round: pins WHICH module and WHICH name the class-arm fallback
    resolves in.  ``alim`` does ``-import_from(alow, [alias(numlist, nl)])``;
    ``alow``'s ``numlist/1`` is bound in ``alim`` as ``nl``.

    * The CLASS (the object ``alim`` binds) resolves ``/2`` in ``alow``,
      under ``alow``'s name ``numlist`` -- so it reaches the builtin
      ``numlist/2``.  The OWNER handle ``alow:numlist`` agrees.
    * The IMPORTER handle ``alim:nl`` does NOT: ``alim`` has no ``nl/2`` row
      and no builtin is called ``nl``, so it refuses.

    So the two eras agree only if the W4b-2d flip binds an import to the
    OWNER handle.  Parked for a ruling: todo/aliased-import-other-arity-
    resolves-in-the-owner-2026-09-24.md.  This test pins today's behaviour
    so a change to either side is seen."""
    from clausal.logic.predicate import PredicateMeta
    from clausal.logic.solve import _drive_trampoline, call as _call
    from clausal.logic.variables import Trail, Var, deref
    _load(tmp_path, monkeypatch, "f7_alow", """
        -module(f7_alow, [numlist(A)])
        numlist(1),
    """)
    imp = _load(tmp_path, monkeypatch, "f7_alim", """
        -module(f7_alim, [])
        -import_from(f7_alow, [alias(numlist, nl)])
    """)
    I = imp.__dict__["$module"]
    cls = I.module_dict["nl"]
    assert isinstance(cls, PredicateMeta)
    assert cls._row._key == ("numlist", 1)                 # the OWNER's row
    assert cls._row._db is sys.modules["f7_alow"].__dict__["$module"].db

    def _answers(target):
        out = Var()
        return [deref(out) for _ in
                _drive_trampoline(_dispatch_at(target, 2), Trail(), 3, out)]

    assert _answers(cls) == [[1, 2, 3]]
    assert _answers(mangle("f7_alow", "numlist")) == [[1, 2, 3]]
    with pytest.raises(PredicateArityMismatchError, match="nl"):
        _dispatch_at(mangle("f7_alim", "nl"), 2)
    # and through solve.call in the importer (class era): the last resort
    # hands the binding to _dispatch_at, so the owner answers here too.
    out = Var()
    assert [deref(out) for _ in _call("nl", 3, out, module=I)] == [[1, 2, 3]]
    # the imported arity is untouched in every shape
    for t in (cls, mangle("f7_alow", "numlist"), mangle("f7_alim", "nl")):
        assert len(list(_drive_trampoline(_dispatch_at(t, 1), Trail(), 1))) == 1


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
