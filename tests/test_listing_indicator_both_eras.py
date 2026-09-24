"""F1 row 60: ``listing(Name/Arity)`` resolves the same predicate in both
eras -- a ``PredicateMeta`` binding today, a module-qualified HANDLE (mangled
atom) after the flip -- with the owner loaded and popped from ``sys.modules``.

Also pins the pre-existing twin bug
(``todo/done/listing-an-imported-dynamic-predicate-shows-the-importers-twin-2026-09-24.md``):
``gate_dyn_user`` imports ``gd_p`` and re-declares it ``-dynamic``, so its
database holds an EMPTY local twin under the same key; listing the import
used to print the twin's "no clauses".
"""

from __future__ import annotations

import os
import sys

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.solve import call
from clausal.terms import Div

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_OWNER = "tests.fixtures.gate_dyn_owner"
_USER = "_row60_gate_dyn_user"
_ALIAS = "_row60_alias_user"
_HIDE = "hide_owner"


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


@pytest.fixture
def hide():
    saved = sys.modules.pop(_HIDE, None)
    mod = _load_module(_HIDE, os.path.join(FIXTURES, "hide_owner.clausal"))
    yield mod
    sys.modules.pop(_HIDE, None)
    if saved is not None:
        sys.modules[_HIDE] = saved


def _flip(user):
    md = user.__dict__
    assert isinstance(md["gd_p"], PredicateMeta), "fixture no longer binds a class"
    md["gd_p"] = mangle(_OWNER, "gd_p")


def _listing(indicator, module, capsys):
    capsys.readouterr()
    next(call("listing", indicator, module=module), None)
    return capsys.readouterr().out


def _existence_culprit(indicator, module):
    with pytest.raises(LogicException) as exc:
        next(call("listing", indicator, module=module), None)
    err = exc.value.term.args[0]
    assert err.functor == "existence_error", err
    return err.args[1].args


def _prime(owner, user):
    """Put a second clause on the OWNER's row through the import; positive
    control that the owner/twin population compared below is non-empty."""
    lm = user.__dict__["$module"]
    next(call("gd_add", 42, module=lm), None)
    owner_row = owner.__dict__["$module"].db.row("gd_p", 1)
    twin = lm.db.row("gd_p", 1)
    assert twin is not None and twin.db is lm.db, "no local twin: no hazard"
    assert len(owner_row.clauses) == 2, "owner population empty"
    assert twin.clauses == [], "twin is not empty: the test cannot tell them apart"
    return lm


_ERAS = [pytest.param(f, p, id=f"{'flipped' if f else 'class'}-"
                              f"{'popped' if p else 'loaded'}")
         for f in (False, True) for p in (False, True)]


@pytest.mark.parametrize("flipped,owner_popped", _ERAS)
def test_the_atom_indicator_lists_the_owner_not_the_importer_twin(
        pair, capsys, flipped, owner_popped):
    owner, user = pair
    lm = _prime(owner, user)
    if flipped:
        _flip(user)
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    out = _listing(("/", "gd_p", 1), lm, capsys)
    assert "% gd_p/1 — 2 clause(s)" in out, out


@pytest.mark.parametrize("flipped,owner_popped", _ERAS)
def test_the_binding_indicator_lists_the_owner(
        pair, capsys, flipped, owner_popped):
    """``listing(gd_p/1)`` as source compiles it: a Div whose left operand is
    the module's binding for ``gd_p`` -- the class, or after the flip the
    owner's handle (ruling D1)."""
    owner, user = pair
    lm = _prime(owner, user)
    if flipped:
        _flip(user)
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    binding = user.__dict__["gd_p"]
    assert isinstance(binding, str) is flipped
    out = _listing(Div(left=binding, right=1), lm, capsys)
    assert "% gd_p/1 — 2 clause(s)" in out, out


@pytest.mark.parametrize("flipped,owner_popped", _ERAS)
def test_a_module_still_lists_its_own_predicates(
        pair, capsys, flipped, owner_popped):
    """Popped, the owner's own handle resolves only through the caller's
    ``db`` (ruling Q0's local short-circuit)."""
    owner, user = pair
    lm = _prime(owner, user)
    if flipped:
        _flip(user)
    assert "% gd_add/1 — 1 clause(s)" in _listing(("/", "gd_add", 1), lm, capsys)
    om = owner.__dict__["$module"]
    if flipped:
        owner.__dict__["gd_p"] = mangle(_OWNER, "gd_p")
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    for ind in (("/", "gd_p", 1), Div(left=owner.__dict__["gd_p"], right=1)):
        assert "% gd_p/1 — 2 clause(s)" in _listing(ind, om, capsys), ind


@pytest.fixture
def aliased(pair):
    """``alias(gd_p, gd_loc)``: the adopted row is keyed by the importer's
    spelling ``gd_loc``, the owner's row by ``gd_p``."""
    owner, _user = pair
    sys.modules.pop(_ALIAS, None)
    mod = _load_module(_ALIAS, os.path.join(FIXTURES, "row60_alias_user.clausal"))
    yield owner, mod
    sys.modules.pop(_ALIAS, None)


@pytest.mark.parametrize("flipped,owner_popped", _ERAS)
def test_an_aliased_import_lists_the_owner(
        aliased, capsys, flipped, owner_popped):
    owner, user = aliased
    lm = user.__dict__["$module"]
    # Primed through the OWNER, so this test does not depend on the alias
    # write path (tests/test_assert_through_aliased_import_both_eras.py).
    next(call("assertz", ("gd_p", 42), module=owner.__dict__["$module"]), None)
    assert len(owner.__dict__["$module"].db.row("gd_p", 1).clauses) == 2
    twin = lm.db.row("gd_loc", 1)
    assert twin is not None and twin.db is lm.db and twin.clauses == []
    assert lm.db.adopted_row("gd_loc", 1) is not None
    assert lm.db.adopted_row("gd_p", 1) is None, "keyed by the owner's name"
    if flipped:
        md = user.__dict__
        assert isinstance(md["gd_loc"], PredicateMeta)
        md["gd_loc"] = mangle(_OWNER, "gd_p")
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    for ind in (("/", "gd_loc", 1), Div(left=user.__dict__["gd_loc"], right=1)):
        out = _listing(ind, lm, capsys)
        assert "— 2 clause(s)" in out, (ind, out)


@pytest.mark.parametrize("detached", [False, True])
def test_a_standalone_class_bound_under_another_name_does_not_redirect(
        pair, capsys, detached):
    """The namespace leg is taken only when the binding reads a REAL row.  A
    standalone class named ``gd_p`` bound under ``gd_add`` has no row (or a
    private detached one); it must not send ``listing(gd_add/1)`` to the
    local ``gd_p`` twin."""
    owner, user = pair
    lm = _prime(owner, user)
    stray = make_predicate("gd_p", ["x"])
    if detached:
        assert stray._state_row().detached
    user.__dict__["gd_add"] = stray
    assert "% gd_add/1 — 1 clause(s)" in _listing(("/", "gd_add", 1), lm, capsys)


def test_a_mangled_predicate_handle_lists_its_predicate(hide, capsys):
    lm = hide.__dict__["$module"]
    handle = mangle(_HIDE, "holds")
    for ind in (("/", handle, 1), Div(left=handle, right=1)):
        assert "% holds/1 — 1 clause(s)" in _listing(ind, lm, capsys), ind


def test_a_mangled_predicate_handle_is_authoritative_at_its_arity(
        hide, tmp_path, capsys):
    """Ruling QE: a handle at an arity its owner does not define raises,
    naming the PLAIN name -- no fall-through to the caller's same-named
    predicate at that arity (which the caller DOES define here, so a
    fall-through would list it)."""
    src = tmp_path / "row60_local_holds.clausal"
    src.write_text("holds(1, 2),\n")
    name = "_row60_local_holds"
    sys.modules.pop(name, None)
    local = _load_module(name, str(src))
    try:
        lm = local.__dict__["$module"]
        assert "% holds/2 — 1 clause(s)" in _listing(("/", "holds", 2), lm, capsys)
        assert _existence_culprit(("/", mangle(_HIDE, "holds"), 2), lm) == (
            "holds", 2)
        assert "% holds/1 — 1 clause(s)" in _listing(
            ("/", mangle(_HIDE, "holds"), 1), lm, capsys)
    finally:
        sys.modules.pop(name, None)


def test_a_hide_atom_indicator_is_not_a_predicate(hide):
    """A -hide DATA atom is mangled in the handle's shape; it keeps today's
    treatment: its mangled spelling names no predicate."""
    lm = hide.__dict__["$module"]
    secret = mangle(_HIDE, "hide_secret")
    assert _existence_culprit(("/", secret, 1), lm) == (secret, 1)
    orphan = mangle("_row60_not_loaded", "hide_secret")
    assert _existence_culprit(("/", orphan, 1), lm) == (orphan, 1)
