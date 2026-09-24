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


def _bind_imports_as_owner_handles(monkeypatch, owner):
    """Emulate the handle era for ``-import_from`` (D1: an import binds the
    OWNER's handle): after ``_process_imports`` runs, every name it bound to
    one of *owner*'s predicate classes is re-bound to ``mangle(owner, name)``
    -- dotted key and local (possibly aliased) name alike."""
    import clausal.logic.compiler_v2 as cv
    from clausal.logic.predicate import PredicateMeta
    orig = cv._process_imports
    seen = []

    def flipped(items, module_dict, db=None):
        orig(items, module_dict, db)
        for k, v in list(module_dict.items()):
            if (isinstance(v, PredicateMeta) and v._row is not None
                    and v._row._db is owner.db):
                module_dict[k] = mangle(owner.name, v._row._key[0])
                seen.append(k)

    monkeypatch.setattr(cv, "_process_imports", flipped)
    return seen


@pytest.mark.parametrize("era", ["class", "handle"])
def test_an_unqualified_call_at_another_arity_resolves_only_under_the_name_used(
        tmp_path, monkeypatch, era):
    """Operator ruling 2026-09-24 (closing the aliased-import leak): an
    other-arity call resolves in the namespace the caller NAMED, under the
    name the caller USED.

    ``alim`` does ``-import_from(alow, [alias(numlist, nl)])``; ``alow``
    defines ``numlist/1``.

    * UNQUALIFIED ``nl(3, L)`` in ``alim``: ``alim`` has no ``nl/2`` and no
      builtin is called ``nl`` -> ``PredicateArityMismatchError`` naming
      ``nl``, in compiled code AND through ``solve.call``.  Importing
      ``numlist/1`` as ``nl`` grants no other arity and no other name.
      (Before the ruling this test pinned the opposite -- the class-arm
      fallback answered with ``alow``'s builtin ``numlist/2``.)
    * QUALIFIED ``alow.numlist(3, L)`` (and the class / owner handle held
      directly): the qualifier's module under that name -> the builtin
      ``numlist/2`` answers (F7's reversed pin).
    * the imported arity ``nl(1)`` is untouched.

    Both eras: the handle era binds the import to the OWNER handle (D1)."""
    from clausal.logic.predicate import PredicateMeta, is_declared_predicate_name
    from clausal.logic.solve import _drive_trampoline, call as _call
    from clausal.logic.variables import Trail, Var, deref
    ow = _load(tmp_path, monkeypatch, f"f7_alow_{era}", """
        -module(f7_alow_ERA, [numlist(A)])
        numlist(1),
    """.replace("ERA", era))
    O = ow.__dict__["$module"]
    flipped = (_bind_imports_as_owner_handles(monkeypatch, O)
               if era == "handle" else None)
    imp = _load(tmp_path, monkeypatch, f"f7_alim_{era}", """
        -module(f7_alim_ERA, [])
        -import_from(f7_alow_ERA, [alias(numlist, nl)])
        use(L) <- nl(3, L)
        use1 <- nl(1)
        q(L) <- f7_alow_ERA.numlist(3, L)
    """.replace("ERA", era))
    I = imp.__dict__["$module"]
    b = I.module_dict["nl"]
    if era == "class":
        assert isinstance(b, PredicateMeta) and b._row._key == ("numlist", 1)
    else:
        assert "nl" in flipped, "the handle era must really be exercised"
        assert b == mangle(f"f7_alow_{era}", "numlist")
        assert is_declared_predicate_name(b)

    def _sols(goal, *args):
        return [[deref(a) for a in args if isinstance(a, Var)]
                for _ in _call(goal, *args, module=I)]

    # unqualified, compiled
    with pytest.raises(PredicateArityMismatchError, match=r"\bnl\b"):
        _sols("use", Var())
    # unqualified, solve.call
    with pytest.raises(PredicateArityMismatchError, match=r"\bnl\b"):
        _sols("nl", 3, Var())
    # the imported arity is untouched
    assert len(_sols("use1")) == 1
    assert len(_sols("nl", 1)) == 1
    assert len(_sols("nl", 2)) == 0
    # qualified: the qualifier's module, under that name -> builtin numlist/2
    assert _sols("q", Var()) == [[[1, 2, 3]]]
    # held directly: the class and the owner handle resolve in the owner
    for t in (O.module_dict["numlist"], mangle(f"f7_alow_{era}", "numlist")):
        out = Var()
        got = [deref(out) for _ in
               _drive_trampoline(_dispatch_at(t, 2), Trail(), 3, out)]
        assert got == [[1, 2, 3]]


@pytest.mark.parametrize("era", ["class", "handle"])
def test_a_meta_call_through_an_unqualified_name_resolves_under_that_name(
        tmp_path, monkeypatch, capsys, era):
    """Roborev MEDIUM on the aliased-import ruling (2026-09-24): a META-call
    whose goal arrived as an unqualified name of the calling module resolves
    under THAT name in the calling module -- ``call/N``, ``maplist`` and
    ``phrase`` all refuse ``nl`` at arity 2 (``alim`` has no ``nl/2``, no
    builtin is ``nl/2``); before the fix each handed alow's binding to
    ``_dispatch_at``, which answered alow's builtin ``numlist/2``.

    Also pinned: the imported arity still answers through each; ``time_goal
    (nl)`` calls ``nl/0``, and under the name used that is the BUILTIN
    ``nl/0`` (newline) -- the name, not the owner, decides; and the
    QUALIFIED meta-call ``call(alow:numlist, 3, L)`` still resolves in the
    qualifier under its name (the builtin ``numlist/2``).  Both eras."""
    from clausal.logic.solve import call as _call
    from clausal.logic.variables import Var, deref
    ow = _load(tmp_path, monkeypatch, f"f7_mc_ow_{era}", """
        -module(f7_mc_ow_ERA, [numlist(A)])
        numlist(1),
    """.replace("ERA", era))
    O = ow.__dict__["$module"]
    if era == "handle":
        _bind_imports_as_owner_handles(monkeypatch, O)
    imp = _load(tmp_path, monkeypatch, f"f7_mc_im_{era}", """
        -module(f7_mc_im_ERA, [])
        -import_from(f7_mc_ow_ERA, [alias(numlist, nl)])
        m(L) <- call(nl, 3, L)
        mm(L) <- maplist(nl, [3], [L])
        ph(R) <- phrase(nl, 3, R)
        tg <- time_goal(nl)
        m1 <- call(nl, 1)
        mm1 <- maplist(nl, [1])
    """.replace("ERA", era))
    I = imp.__dict__["$module"]
    if era == "handle":
        assert I.module_dict["nl"] == mangle(f"f7_mc_ow_{era}", "numlist")
    for goal in ("m", "mm", "ph"):
        with pytest.raises(PredicateArityMismatchError, match=r"\bnl\b"):
            list(_call(goal, Var(), module=I))
    assert len(list(_call("m1", module=I))) == 1
    assert len(list(_call("mm1", module=I))) == 1
    assert len(list(_call("tg", module=I))) == 1         # builtin nl/0
    capsys.readouterr()
    out = Var()
    got = [deref(out) for _ in _call(
        "call", (":", f"f7_mc_ow_{era}", "numlist"), 3, out, module=I)]
    assert got == [[1, 2, 3]]


@pytest.mark.parametrize("era", ["class", "handle"])
def test_an_owner_arity_added_after_the_import_is_not_imported(
        tmp_path, monkeypatch, era):
    """Roborev LOW 1: the import binds ONE predicate.  ``alow`` gains a
    ``numlist/2`` row by ``assertz`` after ``alim`` imported ``numlist/1``
    as ``nl``; ``nl(3, L)`` in ``alim`` still refuses in BOTH eras (the
    handle's owner would call itself a predicate at 2; the import record --
    the adopted rows -- says only 1 was imported).  Direct and through
    ``solve.call`` and a meta-call; the qualified reference sees the new
    row."""
    from clausal.logic.solve import _drive_trampoline, call as _call
    from clausal.logic.variables import Trail, Var, deref
    from clausal.terms import Compound
    ow = _load(tmp_path, monkeypatch, f"f7_late_ow_{era}", """
        -module(f7_late_ow_ERA, [numlist(A)])
        numlist(1),
    """.replace("ERA", era))
    O = ow.__dict__["$module"]
    if era == "handle":
        _bind_imports_as_owner_handles(monkeypatch, O)
    imp = _load(tmp_path, monkeypatch, f"f7_late_im_{era}", """
        -module(f7_late_im_ERA, [])
        -import_from(f7_late_ow_ERA, [alias(numlist, nl)])
        use(L) <- nl(3, L)
        m(L) <- call(nl, 3, L)
    """.replace("ERA", era))
    I = imp.__dict__["$module"]
    assert len(list(_call("assertz", Compound("numlist", (3, "own")),
                          module=O))) == 1
    assert O.db.row("numlist", 2) is not None
    for goal in ("use", "m"):
        with pytest.raises(PredicateArityMismatchError, match=r"\bnl\b"):
            list(_call(goal, Var(), module=I))
    with pytest.raises(PredicateArityMismatchError, match=r"\bnl\b"):
        list(_call("nl", 3, Var(), module=I))
    # the qualified reference -- the owner, under its name -- sees the row
    out = Var()
    got = [deref(out) for _ in _drive_trampoline(
        _dispatch_at(mangle(f"f7_late_ow_{era}", "numlist"), 2), Trail(), 3, out)]
    assert got == ["own"]


@pytest.mark.parametrize("era", ["class", "handle"])
def test_an_imported_stale_class_does_not_answer_from_its_owner(
        tmp_path, monkeypatch, era):
    """Roborev LOW 2: ``_refuse_unqualified_other_arity``'s stale-``_fields``
    exception is for a class LOCAL to the calling module.  Here the owner's
    ``ping`` class goes stale AFTER the import (a runtime ``assertz(ping(1,
    2))`` re-binds it to the owner's ``ping/2`` row, ``_fields == ()``); the
    importer imported ``ping/0`` only, so ``ping(1, 2)`` there refuses -- it
    must not answer from the owner's row.  Both eras."""
    from clausal.logic.predicate import PredicateMeta
    from clausal.logic.solve import call as _call
    from clausal.terms import Compound
    ow = _load(tmp_path, monkeypatch, f"f7_st_ow_{era}", """
        -module(f7_st_ow_ERA, [ping])
        ping <- (1 > 0)
    """.replace("ERA", era))
    O = ow.__dict__["$module"]
    if era == "handle":
        _bind_imports_as_owner_handles(monkeypatch, O)
    imp = _load(tmp_path, monkeypatch, f"f7_st_im_{era}", """
        -module(f7_st_im_ERA, [])
        -import_from(f7_st_ow_ERA, [ping])
    """.replace("ERA", era))
    I = imp.__dict__["$module"]
    assert len(list(_call("assertz", Compound("ping", (1, 2)), module=O))) == 1
    cls = O.module_dict["ping"]
    assert isinstance(cls, PredicateMeta)
    assert cls._fields == () and cls._row._key == ("ping", 2)   # STALE, owner's
    with pytest.raises(PredicateArityMismatchError, match="ping"):
        list(_call("ping", 1, 2, module=I))
    assert len(list(_call("ping", module=I))) == 1             # ping/0 intact
    assert len(list(_call("ping", 1, 2, module=O))) == 1        # owner's own


@pytest.mark.parametrize("era", ["class", "handle"])
def test_an_unaliased_import_at_another_arity_resolves_under_its_own_name(
        tmp_path, monkeypatch, era):
    """The ruling's unaliased check: ``-import_from(alow, [numlist])`` then
    ``numlist(3, L)`` resolves in the CALLING module under ``numlist`` --
    where the builtin ``numlist/2`` answers."""
    from clausal.logic.solve import call as _call
    from clausal.logic.variables import Var, deref
    ow = _load(tmp_path, monkeypatch, f"f7_unal_ow_{era}", """
        -module(f7_unal_ow_ERA, [numlist(A)])
        numlist(1),
    """.replace("ERA", era))
    if era == "handle":
        _bind_imports_as_owner_handles(monkeypatch, ow.__dict__["$module"])
    imp = _load(tmp_path, monkeypatch, f"f7_unal_im_{era}", """
        -module(f7_unal_im_ERA, [])
        -import_from(f7_unal_ow_ERA, [numlist])
        use(L) <- numlist(3, L)
        use1 <- numlist(1)
    """.replace("ERA", era))
    I = imp.__dict__["$module"]
    if era == "handle":
        assert I.module_dict["numlist"] == mangle(f"f7_unal_ow_{era}", "numlist")
    out = Var()
    assert [deref(out) for _ in _call("use", out, module=I)] == [[1, 2, 3]]
    out = Var()
    assert [deref(out) for _ in _call("numlist", 3, out, module=I)] == [[1, 2, 3]]
    assert len(list(_call("use1", module=I))) == 1


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
