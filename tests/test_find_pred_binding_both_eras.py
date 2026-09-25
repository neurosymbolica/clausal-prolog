"""F1 rows 58/59: runtime writes and call/N resolve an IMPORTED predicate to
its owner's row whatever the importer's binding looks like.

The F1 review measured the hazard on ``gate_dyn_user`` with the importer's
binding flipped to the owner's handle: ``gd_add(42)`` put the clause on the
importer's DEAD TWIN row (owner +0, twin +1) with no error, and ``call/N`` on
the import failed silently.  These tests flip the binding the way the flip
will (ruling D1: an imported name binds the OWNER's handle), both with the
owner loaded and with it popped from ``sys.modules`` as the ``.clausal``
runner pops what it loads.

Handle era (W4b-2d flip): the LOAD binds the owner's handle now, so the
stand-in ``_flip`` (which re-bound a class the load no longer leaves) and the
``flipped=False`` class arm are gone.  ``_the_load_bound_the_owner_handle``
asserts the binding each test depends on, so no arm runs on a class by
accident or on a binding nothing set.
"""

from __future__ import annotations

import os
import sys

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.builtins.database_ops import _find_pred_cls, _home_db
from clausal.logic.builtins.higher_order import _namespace_dispatch
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_OWNER = "tests.fixtures.gate_dyn_owner"
_USER = "_rows5859_gate_dyn_user"


@pytest.fixture
def pair():
    """Owner and importer, loaded fresh; sys.modules restored afterwards."""
    saved = sys.modules.get(_OWNER)
    sys.modules.pop(_OWNER, None)
    sys.modules.pop(_USER, None)
    owner = _load_module(_OWNER, os.path.join(FIXTURES, "gate_dyn_owner.clausal"))
    user = _load_module(_USER, os.path.join(FIXTURES, "gate_dyn_user.clausal"))
    yield owner, user
    sys.modules.pop(_USER, None)
    if saved is not None:
        sys.modules[_OWNER] = saved
    else:
        sys.modules.pop(_OWNER, None)


def _the_load_bound_the_owner_handle(user):
    """Ruling D1, done by the load: the imported name binds the OWNER's
    handle."""
    assert user.__dict__["gd_p"] == mangle(_OWNER, "gd_p"), (
        "the load did not bind the owner's handle")


def _owner_answers(owner):
    x = Var()
    return sorted(deref(x) for _ in call("gd_p", x,
                                         module=owner.__dict__["$module"]))


@pytest.mark.parametrize("owner_popped", [False, True])
def test_an_assert_through_the_import_lands_on_the_owner(pair, owner_popped):
    owner, user = pair
    odb = owner.__dict__["$module"].db
    udb = user.__dict__["$module"].db
    twin = udb.row("gd_p", 1)
    assert twin is not None and twin.db is udb, "no dual record: no hazard"
    before_owner, before_twin = len(odb.row("gd_p", 1).clauses), len(twin.clauses)
    _the_load_bound_the_owner_handle(user)
    if owner_popped:
        sys.modules.pop(_OWNER, None)

    next(call("gd_add", 42, module=user.__dict__["$module"]), None)

    assert len(odb.row("gd_p", 1).clauses) == before_owner + 1, "not on the owner"
    assert len(twin.clauses) == before_twin, "landed on the importer's dead twin"
    assert 42 in _owner_answers(owner)


@pytest.mark.parametrize("owner_popped", [False, True])
def test_call_n_reaches_the_imported_predicate(pair, owner_popped):
    owner, user = pair
    udb = user.__dict__["$module"].db
    _the_load_bound_the_owner_handle(user)
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    binding = _find_pred_cls("gd_p", 1, user.__dict__)
    assert binding is not None
    assert _home_db(udb, binding, "gd_p", 1) is owner.__dict__["$module"].db
    assert _namespace_dispatch(udb, "gd_p", 1) is not None


def test_a_mangled_data_atom_is_not_taken_for_a_predicate(tmp_path):
    """A -hide atom whose owner does not resolve is data, not a lost handle:
    without an adopted row it does not answer."""
    hide = _load_module("hide_owner", os.path.join(FIXTURES, "hide_owner.clausal"))
    try:
        md = dict(hide.__dict__)
        md["hide_secret"] = mangle("_rows5859_not_loaded", "hide_secret")
        assert _find_pred_cls("hide_secret", 1, md) is None
    finally:
        sys.modules.pop("hide_owner", None)


def test_a_resolvable_handle_is_found_without_any_adopted_row(pair, tmp_path):
    """No -import_from, so no adopted row: only the era-agnostic predicate
    test can recognise the handle."""
    owner, _user = pair
    plain = _load_module("_rows5859_plain",
                         os.path.join(FIXTURES, "gate_dyn_owner.clausal"))
    try:
        md = dict(plain.__dict__)
        db = md["$module"].db
        md["gd_q"] = mangle(_OWNER, "gd_p")
        assert db.adopted_row("gd_q", 1) is None
        assert _find_pred_cls("gd_q", 1, md) == md["gd_q"]
        assert _home_db(db, md["gd_q"], "gd_q", 1) is owner.__dict__["$module"].db
    finally:
        sys.modules.pop("_rows5859_plain", None)


def test_only_the_import_s_own_handle_takes_the_lost_route(pair):
    """With an adopted row present, an unrelated mangled atom rebound under
    the imported name is NOT the import: neither a handle to another module
    nor one naming another functor routes the write to the owner."""
    owner, user = pair
    udb = user.__dict__["$module"].db
    sys.modules.pop(_OWNER, None)
    md = dict(user.__dict__)
    assert udb.adopted_row("gd_p", 1) is not None
    for impostor in (mangle("_rows5859_elsewhere", "gd_p"),
                     mangle(_OWNER, "gd_other")):
        md["gd_p"] = impostor
        assert _find_pred_cls("gd_p", 1, md) is None, impostor
        assert _home_db(udb, impostor, "gd_p", 1) is udb, impostor


@pytest.mark.parametrize("owner_popped", [False, True])
def test_retract_follows_the_handle_to_the_owner(pair, owner_popped):
    owner, user = pair
    odb = owner.__dict__["$module"].db
    lm = user.__dict__["$module"]
    _the_load_bound_the_owner_handle(user)
    next(call("gd_add", 7, module=lm), None)          # on the owner
    assert 7 in _owner_answers(owner)
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    # (listing/_indicator_row, F1 row 60, now resolves through the binding
    # before the importer's -dynamic twin: tests/test_listing_indicator_both_eras.py)
    next(call("retract", ("gd_p", 7), module=lm), None)
    assert 7 not in _owner_answers(owner), "retract missed the owner's row"
