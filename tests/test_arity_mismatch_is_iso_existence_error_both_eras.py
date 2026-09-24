"""A call at an arity the predicate lacks is ISO ``existence_error``, catchable.

Operator ruling 2026-09-25 ("do what Scryer does"; SWI is not a target).  A
predicate is name + arity, so with only ``pk/1`` defined ``pk/2`` does not
exist, and Scryer answers::

    ?- catch(call(pk(3), _), E, true).
    E = error(existence_error(procedure, pk/2), pk/2).

-- the indicator at the CALLED arity, for ``call/N``, a direct goal, and a
module-qualified goal alike.  Before 2026-09-25 Clausal raised
``PredicateArityMismatchError`` as a plain ``TypeError``: ``catch/3`` caught
it only as the transliterated ``PredicateArityMismatchError(Message)``
compound, which no ISO catcher matches.  The error is now BOTH a
``LogicException`` carrying the ISO term (the "takes 1 argument" diagnostic
is its context) and a ``TypeError`` (ADD, not replace: ``except TypeError``,
``except PredicateArityMismatchError`` and a ``++TypeError`` catcher keep
working).

Both eras: the class binding and the module-qualified handle (emulated the
way ``tests/test_f7_dispatch_at_arity_refusal.py`` does).
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.logic.atoms import mangle, mint
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import PredicateMeta, _dispatch_at
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk
from clausal.predicate_diagnostics import PredicateArityMismatchError
from clausal.terms import Compound


def _load(tmp_path, monkeypatch, name, body):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}.clausal"
    p.write_text(textwrap.dedent(body).lstrip())
    mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    return mod


def _bind_imports_as_owner_handles(monkeypatch, owner):
    """The handle era for ``-import_from`` (D1: an import binds the OWNER's
    handle) -- the same emulation as test_f7_dispatch_at_arity_refusal.py."""
    import clausal.logic.compiler_v2 as cv
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


def _assert_iso(term, name, arity):
    """``error(existence_error(procedure, Name/Arity), Context)``."""
    assert isinstance(term, Compound) and term.functor == "error", term
    formal = term.args[0]
    assert formal.functor == "existence_error"
    assert formal.args[0] == mint("procedure")
    pi = formal.args[1]
    assert isinstance(pi, Compound) and pi.functor == "/"
    assert tuple(pi.args) == (mint(name), arity)
    # the diagnostic survives as the context
    assert f"{name} takes 1 argument, but this call passes {arity}" in term.args[1]


@pytest.fixture(params=["class", "handle"])
def pair(request, tmp_path, monkeypatch):
    era = request.param
    ow = _load(tmp_path, monkeypatch, f"aie_ow_{era}", """
        -module(aie_ow_ERA, [pk(A), local_goal(PI), local_call(PI)])
        -private([procedure])
        pk(1),
        local_goal(PI) <- catch(pk(3, _X), error(existence_error(procedure, PI), _), True)
        local_call(PI) <- catch(call(pk(3), _X), error(existence_error(procedure, PI), _), True)
    """.replace("ERA", era))
    O = ow.__dict__["$module"]
    seen = (_bind_imports_as_owner_handles(monkeypatch, O)
            if era == "handle" else None)
    imp = _load(tmp_path, monkeypatch, f"aie_im_{era}", """
        -module(aie_im_ERA, [])
        -import_from(aie_ow_ERA, [pk])
        -import_module(aie_ow_ERA)
        -private([procedure, caught])
        by_call(PI) <- catch(call(pk(3), _X), error(existence_error(procedure, PI), _), True)
        by_goal(PI) <- catch(pk(3, _X), error(existence_error(procedure, PI), _), True)
        by_qual(PI) <- catch(aie_ow_ERA.pk(3, _X), error(existence_error(procedure, PI), _), True)
        by_type(E) <- catch(pk(3, _X), ++TypeError, E is caught)
    """.replace("ERA", era))
    I = imp.__dict__["$module"]
    if era == "handle":
        assert "pk" in seen, "the handle era must really be exercised"
        assert I.module_dict["pk"] == mangle(f"aie_ow_{era}", "pk")
    return era, O, I


def _pi(goal, module):
    pi = Var()
    answers = [walk(pi) for _ in call(goal, pi, module=module)]
    assert len(answers) == 1, answers
    return answers[0]


@pytest.mark.parametrize("goal", ["by_call", "by_goal", "by_qual"])
def test_catch_3_catches_the_iso_term_in_the_importer(pair, goal):
    """call/N, a direct wrong-arity goal, and a module-qualified goal all
    raise the ISO term, the indicator at the CALLED arity."""
    _era, _O, I = pair
    assert _pi(goal, I) == Compound("/", (mint("pk"), 2))


@pytest.mark.parametrize("goal", ["local_goal", "local_call"])
def test_catch_3_catches_the_iso_term_in_the_owner(pair, goal):
    _era, O, _I = pair
    assert _pi(goal, O) == Compound("/", (mint("pk"), 2))


def test_a_plus_plus_type_error_catcher_still_catches_it(pair):
    """ADD, not replace: the error is still a Python ``TypeError`` for a
    ``++TypeError`` catcher (``exceptions._dual_typed_match``)."""
    _era, _O, I = pair
    e = Var()
    assert [walk(e) for _ in call("by_type", e, module=I)] == [mint("caught")]


def test_python_except_type_error_still_catches_it(pair):
    """Uncaught, it reaches Python as all three: the named class, a
    ``TypeError``, and a ``LogicException`` whose ``.term`` is the ISO one;
    ``str()`` is the diagnostic alone, as before."""
    era, O, _I = pair
    target = (O.module_dict["pk"] if era == "class"
              else mangle(f"aie_ow_{era}", "pk"))
    with pytest.raises(TypeError) as info:
        _dispatch_at(target, 2)
    exc = info.value
    assert isinstance(exc, PredicateArityMismatchError)
    assert isinstance(exc, LogicException)
    _assert_iso(exc.term, "pk", 2)
    assert str(exc).startswith("pk takes 1 argument, but this call passes 2")
    assert "Uncaught logic exception" not in str(exc)


def test_a_message_only_construction_keeps_the_old_ball():
    """Out-of-tree code that builds the error from a message alone gets the
    ball ``catch/3`` bound before 2026-09-25, not a malformed ISO term."""
    exc = PredicateArityMismatchError("p takes 1 argument, but this call passes 2")
    assert isinstance(exc, TypeError) and isinstance(exc, LogicException)
    assert exc.term == Compound(
        "PredicateArityMismatchError",
        ("p takes 1 argument, but this call passes 2",))
    assert str(exc) == "p takes 1 argument, but this call passes 2"


def test_a_plus_plus_exception_catcher_still_never_catches_a_plain_logic_ball(
        tmp_path, monkeypatch):
    """The dual-typed arm is narrow: a class that is merely a BASE of
    LogicException (``++Exception``) still never matches a logic ball
    (roborev job 18), and a plain ``throw/1`` ball is not a TypeError."""
    from clausal.logic.exceptions import catch_match
    from clausal.logic.variables import Trail
    ball = LogicException(mint("boom"))
    for cls in (Exception, BaseException, TypeError):
        assert not catch_match(cls, ball.term, ball, Trail()), cls
    dual = PredicateArityMismatchError("m", "p", 2)
    assert catch_match(TypeError, dual.term, dual, Trail())
    assert not catch_match(Exception, dual.term, dual, Trail())
    assert catch_match(LogicException, dual.term, dual, Trail())
