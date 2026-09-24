"""``assertz``/``retract`` through an ALIASED ``-import_from`` land on the
owner's row, in both eras, owner loaded or popped.

``todo/done/assertz-through-an-aliased-import-raises-existence-error-2026-09-24.md``:
``row60_alias_user`` imports ``alias(gd_p, gd_loc)``; its body's
``gd_loc(X)`` is a CELL spelled with the OWNER's name (``("gd_p", X)`` --
``terms_to_ast._functor_spelling``, so the owner's clauses can match it), and
the assert looked ``gd_p/1`` up in the importer, where only ``gd_loc`` is
bound and adopted: ``existence_error(procedure, gd_p/1)``.
"""
from __future__ import annotations

import os
import sys

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import PredicateMeta, mint_predicate_handle
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_OWNER = "tests.fixtures.gate_dyn_owner"
_ALIAS = "_alias_assert_user"

_SRC = """\
-dynamic(gd_loc/1)
-module(_alias_assert_user, [gd_loc_add(X), gd_loc_del(X), gd_loc_call(X)])
-import_from(tests.fixtures.gate_dyn_owner, [alias(gd_p, gd_loc)])

gd_loc_add(X) <- assertz(gd_loc(X))
gd_loc_del(X) <- retract(gd_loc(X))
gd_loc_call(X) <- call(gd_loc(X))
"""


@pytest.fixture
def aliased(tmp_path):
    saved = sys.modules.pop(_OWNER, None)
    sys.modules.pop(_ALIAS, None)
    owner = _load_module(_OWNER, os.path.join(FIXTURES, "gate_dyn_owner.clausal"))
    src = tmp_path / f"{_ALIAS}.clausal"
    src.write_text(_SRC)
    user = _load_module(_ALIAS, str(src))
    yield owner, user
    sys.modules.pop(_ALIAS, None)
    if saved is not None:
        sys.modules[_OWNER] = saved
    else:
        sys.modules.pop(_OWNER, None)


_ERAS = [pytest.param(f, p, id=f"{'flipped' if f else 'class'}-"
                              f"{'popped' if p else 'loaded'}")
         for f in (False, True) for p in (False, True)]


def _owner_answers(owner):
    x = Var()
    return sorted(deref(x) for _ in call("gd_p", x,
                                         module=owner.__dict__["$module"]))


def _setup(owner, user, flipped, owner_popped):
    lm = user.__dict__["$module"]
    assert lm.db.adopted_row("gd_loc", 1) is not None
    assert lm.db.adopted_row("gd_p", 1) is None, "keyed by the importer's name"
    if flipped:
        md = user.__dict__
        assert isinstance(md["gd_loc"], PredicateMeta)
        # Ruling D1: an imported name binds the OWNER's handle.
        md["gd_loc"] = mint_predicate_handle(owner.__dict__["$module"].db, "gd_p")
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    return lm


@pytest.mark.parametrize("flipped,owner_popped", _ERAS)
def test_assertz_through_the_alias_lands_on_the_owner(
        aliased, flipped, owner_popped):
    owner, user = aliased
    lm = _setup(owner, user, flipped, owner_popped)
    assert next(call("gd_loc_add", 42, module=lm), None) is not None
    assert _owner_answers(owner) == [1, 42]
    assert lm.db.row("gd_loc", 1).clauses == [], "wrote the importer's twin"


@pytest.mark.parametrize("flipped,owner_popped", _ERAS)
def test_retract_through_the_alias_removes_from_the_owner(
        aliased, flipped, owner_popped):
    owner, user = aliased
    lm = _setup(owner, user, flipped, owner_popped)
    assert next(call("gd_loc_add", 42, module=lm), None) is not None
    assert next(call("gd_loc_del", 1, module=lm), None) is not None
    assert _owner_answers(owner) == [42]


@pytest.mark.parametrize("flipped,owner_popped", _ERAS)
def test_call_of_the_alias_cell_answers_from_the_owner(
        aliased, flipped, owner_popped):
    """``call(gd_loc(X))`` hands call/1 the same owner-spelled cell; it used
    to answer NOTHING, silently (higher_order resolves through the same
    ``_find_pred_cls``)."""
    owner, user = aliased
    lm = _setup(owner, user, flipped, owner_popped)
    x = Var()
    assert [deref(x) for _ in call("gd_loc_call", x, module=lm)] == [1]


def test_an_unrelated_cell_is_still_refused(aliased):
    """The reverse lookup is by the adopted row's OWN key, so a cell naming
    something nobody imported still gets the existence error."""
    _owner, user = aliased
    lm = user.__dict__["$module"]
    with pytest.raises(LogicException) as exc:
        next(call("assertz", ("gd_nothing", 1), module=lm), None)
    assert exc.value.term.args[0].functor == "existence_error"


def test_the_reverse_spelling_refuses_to_guess_between_two_owners():
    from clausal.logic.database import Database

    a, b, imp = Database(), Database(), Database()
    row_a, row_b = a.row("p", 1, create=True), b.row("p", 1, create=True)
    assert imp.adopt_row("pa", 1, row_a)
    assert imp.adopted_spelling("p", 1) == "pa"
    assert imp.adopt_row("pa2", 1, row_a)          # same row twice: still one
    assert imp.adopted_spelling("p", 1) in ("pa", "pa2")
    assert imp.adopt_row("pb", 1, row_b)            # a second owner's p/1
    assert imp.adopted_spelling("p", 1) is None
    assert imp.adopted_spelling("p", 2) is None
