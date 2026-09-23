"""F2b: the era-agnostic, ARITY-BLIND predicate-identity accessor.

Design authority: ``implementation_plans/w4b2-f2b-and-hard-families-2026-09-23.md``
Job 1, and ``implementation_plans/w4b1-site-classification-2026-09-22.md``
(the 12-row "predicate-name-as-atom coercion" family: rows 6, 12, 19, 21,
23, 38, 43, 44, 46, 49, 50, 52 -- row 20 excluded per Job 1's Q5, rows
30/31 excluded as F1-shaped and already migrated).

A bare reference to a predicate in term position denotes the ATOM of its
own name, regardless of the arity it happens to be declared at -- a bare
``p/3`` denotes the atom ``p`` exactly as a bare ``p/0`` would.  So unlike
``is_declared_predicate`` (F2, arity-EXACT), ``is_declared_predicate_name``
(F2b) takes no ``arity`` argument at all and is deliberately arity-BLIND.

This suite mirrors ``tests/test_w4b2b_binding_resolver.py``'s hazard
coverage (same six shapes, same "no monkeypatch on the real fixture" rule)
plus the ``arities_for``-trap probe (``Database.is_predicate_name`` must
see ``mark_predicate_export``-only and ``adopt_row``-only predicates that
``arities_for`` silently misses).
"""
from __future__ import annotations

import dataclasses
import os

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.database import Database
from clausal.logic.predicate import (
    is_declared_predicate_name, make_predicate,
)


def _fixture_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", name)


def _load_hide_owner():
    """Load the REAL ``-hide`` fixture under sys.modules key ``"hide_owner"``
    -- no monkeypatch anywhere in this file (hazard 4)."""
    return _load_module("hide_owner", _fixture_path("hide_owner.clausal"))


# ── Database.is_predicate_name: the arities_for trap, verified directly ───

def test_arities_for_trap_dynamic_predicate_is_seen_by_both():
    db = Database()
    db.mark_dynamic("p", 1)
    assert db.arities_for("p") == {1}
    assert db.is_predicate_name("p") is True


def test_arities_for_trap_predicate_export_only_is_missed_by_arities_for():
    """A bare ``name/arity`` -module/-private export entry
    (``mark_predicate_export``, e.g. ``gv_free/1`` in
    tests/fixtures/gate_vocab.clausal) has no row and no dispatch -- the
    ``arities_for`` trap this whole accessor exists to route around."""
    db = Database()
    db.mark_predicate_export("q", 3)
    assert db.arities_for("q") == set(), (
        "arities_for was expected to miss this -- if it no longer does, "
        "the trap this test guards has been fixed upstream and this "
        "assertion (not is_predicate_name) needs revisiting")
    assert db.declared_kind("q", 3) == "predicate"
    assert db.is_predicate_name("q") is True


def test_arities_for_trap_adopted_row_is_missed_by_arities_for():
    """An ``-import_from`` row (``adopt_row``) is a real, in-corpus way a
    name becomes a declared predicate with no entry in any container
    ``arities_for`` scans."""
    owner = Database()
    owner.mark_dynamic("r", 1)
    row = owner.row("r", 1, create=True)
    importer = Database()
    assert importer.adopt_row("r", 1, row) is True
    assert importer.arities_for("r") == set(), (
        "arities_for was expected to miss the adopted row too")
    assert importer.declared_kind("r", 1) == "predicate"
    assert importer.is_predicate_name("r") is True


def test_data_functor_is_not_a_predicate_name():
    db = Database()
    db.declare_functor("d", ("x", "y"))
    assert db.declared_kind("d", 2) == "data"
    assert db.is_predicate_name("d") is False


def test_undeclared_name_is_not_a_predicate_name():
    db = Database()
    assert db.is_predicate_name("nope") is False


def test_two_arities_both_seen_by_a_single_arity_blind_query():
    db = Database()
    db.mark_dynamic("p", 1)
    db.mark_dynamic("p", 2)
    assert db.is_predicate_name("p") is True


# ── Hazard 1: six shapes -- must not resolve ────────────────────────────────

@dataclasses.dataclass
class Point:
    x: int
    y: int


def test_1a_dataclass_class_is_not_a_predicate_name():
    assert is_declared_predicate_name(Point) is False


def test_1b_plain_nonmangled_string_is_not_a_predicate_name():
    """The sharp one: a bare string that merely SPELLS a declared/builtin
    name must not resolve."""
    assert is_declared_predicate_name("holds") is False


def test_1c_mangled_atom_unloaded_module_is_not_a_predicate_name():
    ghost = mangle("f2b_no_such_module_ever_loaded", "p")
    assert is_declared_predicate_name(ghost) is False


def test_1d_mangled_atom_naming_a_real_python_module_is_not_a_predicate_name():
    """Module validity is ``_db_for_module_name(...)``, NEVER
    ``sys.modules`` -- a mangled handle whose module half collides with an
    unrelated loaded Python module (``json``) must not resolve."""
    import json  # noqa: F401 -- make sure it is actually loaded
    handle = mangle("json", "loads")
    assert is_declared_predicate_name(handle) is False


def test_1e_none_is_not_a_predicate_name():
    assert is_declared_predicate_name(None) is False


def test_1f_arbitrary_object_is_not_a_predicate_name():
    assert is_declared_predicate_name(object()) is False
    assert is_declared_predicate_name(42) is False
    assert is_declared_predicate_name(("not", "a", "binding")) is False


# ── Class arm: today's era, a PredicateMeta binding, ARITY-BLIND ──────────

def test_kind_predicate_class_is_a_predicate_name_regardless_of_arity():
    P1 = make_predicate("F2bArity1", ["a"])
    P3 = make_predicate("F2bArity3", ["a", "b", "c"])
    P0 = make_predicate("F2bArity0", [])
    assert is_declared_predicate_name(P1) is True
    assert is_declared_predicate_name(P3) is True
    assert is_declared_predicate_name(P0) is True


def test_kind_predicate_class_is_true_unconditionally_row_bound_or_not():
    P = make_predicate("F2bUnbound", ["a", "b"])
    assert is_declared_predicate_name(P) is True
    P._state_row()
    assert is_declared_predicate_name(P) is True


def test_kind_bare_predicate_class_with_no_fields_of_its_own_is_still_true():
    from clausal.logic.predicate import PredicateMeta
    bare = PredicateMeta("F2bBareNoFields", (), {})
    assert not hasattr(bare, "_fields")
    assert is_declared_predicate_name(bare) is True


# ── Positive control ────────────────────────────────────────────────────────

def test_positive_control_hide_owner_declares_all_three():
    mod = _load_hide_owner()
    db = mod.__dict__["$module"].db
    assert db.declared_kind("holds", 1) == "predicate"
    assert db.declared_kind("label", 1) == "predicate"
    assert db.declared_kind("same", 2) == "predicate"
    assert db.declared_kind("hide_secret", 0) is None


# ── Hazard 4: a REAL loaded module, no monkeypatch anywhere ─────────────────

def test_mangled_predicate_is_a_predicate_name_through_a_real_loaded_module():
    _load_hide_owner()
    assert is_declared_predicate_name(mangle("hide_owner", "holds")) is True
    assert is_declared_predicate_name(mangle("hide_owner", "label")) is True
    assert is_declared_predicate_name(mangle("hide_owner", "same")) is True


def test_mangled_predicate_name_is_arity_blind_through_a_real_module():
    """``same/2`` is declared at arity 2 only -- unlike ``is_declared_predicate``,
    this accessor takes no arity and answers True for the mangled name
    regardless of what arity the caller happens to be looking at it from."""
    _load_hide_owner()
    handle = mangle("hide_owner", "same")
    assert is_declared_predicate_name(handle) is True


def test_mangled_hide_data_atom_is_not_a_predicate_name():
    """``-hide`` never calls ``declare_functor``/``mark_predicate_export`` --
    there is no row and no export entry for a hidden atom, ever."""
    _load_hide_owner()
    assert is_declared_predicate_name(mangle("hide_owner", "hide_secret")) is False


# ── mark_predicate_export / adopt_row through a mangled binding ────────────

def test_mangled_predicate_export_only_binding_resolves_true(monkeypatch):
    """The arities_for-trap population, reached through the FULL
    is_declared_predicate_name path (demangle -> owner db ->
    is_predicate_name), not just Database.is_predicate_name directly."""
    import clausal.logic.predicate as predmod

    owner_db = Database()
    owner_db.mark_predicate_export("gv_free", 1)
    monkeypatch.setattr(
        predmod, "_db_for_module_name", lambda name: owner_db, raising=False)
    assert is_declared_predicate_name(mangle("gate_vocab", "gv_free")) is True


def test_mangled_adopted_row_only_binding_resolves_true(monkeypatch):
    import clausal.logic.predicate as predmod

    real_owner = Database()
    real_owner.mark_dynamic("shared", 1)
    row = real_owner.row("shared", 1, create=True)
    importer_db = Database()
    importer_db.adopt_row("shared", 1, row)
    monkeypatch.setattr(
        predmod, "_db_for_module_name", lambda name: importer_db, raising=False)
    assert is_declared_predicate_name(mangle("importer_mod", "shared")) is True
