"""W4b-1: one accessor for a declared functor's field names (spec
docs/superpowers/specs/2026-09-22-w4b1-term-shape-rehome-design.md).

The contract that matters is the DECLAREDNESS one: ``None`` means the value
names nothing declared, ``()`` means declared with zero fields, and the
length of the tuple is the arity.  Arm 3 (a NAME) is the point of the
change: at W4b-2 a module attribute becomes a mangled atom, and arm 3
already answers for it."""
import dataclasses
import os

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.database import Database
from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY
from clausal.logic.predicate import (
    field_names_for, term_field_names_of_class,
)


@dataclasses.dataclass
class Point:
    x: int
    y: int


def test_arm1_dataclass_class_yields_declared_fields():
    assert field_names_for(Point) == ("x", "y")


def test_arm3_name_resolves_through_the_database():
    db = Database()
    db.declare_functor("edge", ("from_", "to"))
    assert field_names_for("edge", arity=2, db=db) == ("from_", "to")


def test_arm3_reads_register_signature_too():
    """signature_for chains _signatures BEFORE _declared, and -specialize
    registers through register_signature only."""
    db = Database()
    db.register_signature("spec_pred", 1, ("only",))
    assert field_names_for("spec_pred", arity=1, db=db) == ("only",)


def test_arm3_name_resolves_through_a_namespace_with_no_db():
    ns = {FUNCTOR_SIGNATURES_KEY: {"vec": ("x", "y")}}
    assert field_names_for("vec", namespace=ns) == ("x", "y")


def test_arm3_mangled_name_resolves_against_its_OWN_module_db(monkeypatch):
    """A handle carries its module.  The caller's db must not be consulted
    for a mangled name -- that would answer for the wrong predicate."""
    import clausal.logic.predicate as predmod

    owner_db = Database()
    owner_db.declare_functor("hidden", ("a",))
    caller_db = Database()
    caller_db.declare_functor("hidden", ("WRONG", "ALSO_WRONG"))

    monkeypatch.setattr(
        predmod, "_db_for_module_name", lambda name: owner_db, raising=False)
    assert field_names_for(mangle("owner", "hidden"), arity=1,
                           db=caller_db) == ("a",)


def test_arm3_mangled_owner_not_loaded_does_not_fall_through_to_namespace(
        monkeypatch):
    """Fix round 1: a mangled name is module-qualified by construction.  If
    the owner module isn't loaded, the caller's namespace must NOT answer
    for it under the bare name -- that would silently un-qualify the
    handle back onto the caller."""
    import clausal.logic.predicate as predmod

    monkeypatch.setattr(
        predmod, "_db_for_module_name", lambda name: None, raising=False)
    ns = {FUNCTOR_SIGNATURES_KEY: {"thing": ("CALLERS", "OWN", "FIELDS")}}
    assert field_names_for(mangle("no_such_module_xyz", "thing"), arity=3,
                           namespace=ns) is None


def test_arm3_mangled_owner_loaded_but_silent_does_not_fall_through_either(
        monkeypatch):
    """Same shape, but the owner db IS loaded and simply doesn't know the
    name -- the owner's registry is the SOLE authority for a mangled name,
    so this is still None, not a fallthrough to namespace."""
    import clausal.logic.predicate as predmod

    owner_db = Database()  # knows nothing about "thing"
    monkeypatch.setattr(
        predmod, "_db_for_module_name", lambda name: owner_db, raising=False)
    ns = {FUNCTOR_SIGNATURES_KEY: {"thing": ("CALLERS", "OWN", "FIELDS")}}
    assert field_names_for(mangle("owner", "thing"), arity=3,
                           namespace=ns) is None


def test_arm3_mangled_name_resolves_against_a_REAL_loaded_module_NO_monkeypatch():
    """CRITICAL 1 (final fix wave, 2026-09-23): the three ``arm3_mangled``
    tests above all monkeypatch ``_db_for_module_name`` itself, so the real
    lookup -- ``sys.modules.get(module_name)`` then ``getattr(mod, "db",
    None)`` -- had zero coverage.  A loaded ``.clausal`` module has no bare
    ``.db``; its Database lives at ``mod.__dict__["$module"].db`` (the same
    idiom ``testing.py`` and ``compiler_v2.py`` already use).  This test
    loads the real fixture and resolves through arm 3 with nothing faked,
    which is the coverage the branch's whole thesis rests on.
    """
    fixture = os.path.join(
        os.path.dirname(__file__), "fixtures", "hide_owner.clausal")
    _load_module("hide_owner", fixture)

    assert field_names_for(mangle("hide_owner", "same"), arity=2) == (
        "x", "y")
    assert field_names_for(mangle("hide_owner", "holds"), arity=1) is not None
    assert field_names_for(mangle("hide_owner", "label"), arity=1) is not None


def test_arm4_a_non_class_non_name_value_is_None():
    assert field_names_for(42) is None
    assert field_names_for(object()) is None


def test_two_arities_exact_read_beats_the_by_name_fallback():
    db = Database()
    db.declare_functor("p", ("a",))
    db.declare_functor("p", ("a", "b"))
    assert field_names_for("p", arity=1, db=db) == ("a",)
    assert field_names_for("p", arity=2, db=db) == ("a", "b")
    # No arity: by name alone, which of two declared arities is meant is not
    # the reader's to guess (per-arity ruling 2026-09-29: "-module(lib,
    # [q(X), q(X, Y)]): allow it").  It used to answer the LAST declaration.
    assert field_names_for("p", db=db) is None


def test_dynamic_only_declaration_has_no_field_names_but_IS_declared():
    """dynfix 2026-09-23 (todo/dynamic-declarations-are-invisible-to-arm-3-
    2026-09-22.md).  ``field_names_for`` is a field-NAMES reader, not a
    declaredness one: ``None`` here does not mean "not declared" for an
    arity-only ``-dynamic`` predicate (``dfact/3`` in
    tests/test_predicate_arity_mismatch_diagnostic.py:613 is the real-world
    case) -- it means no field names are known, which is simply true.
    ``db.declared_kind`` is the accessor for "is this declared", and it
    already answers correctly here via ``mark_dynamic``'s row."""
    db = Database()
    db.mark_dynamic("dfact", 3)
    assert field_names_for("dfact", arity=3, db=db) is None
    assert db.declared_kind("dfact", 3) == "predicate"


def test_bare_export_entry_has_no_field_names_but_IS_declared():
    """Same shape, the OTHER spelling the todo names: a bare ``name/arity``
    entry in a ``-module``/``-private`` export list (``gv_free/1`` in
    tests/fixtures/gate_vocab.clausal), reached through
    ``Database.mark_predicate_export``."""
    db = Database()
    db.mark_predicate_export("gv_free", 1)
    assert field_names_for("gv_free", arity=1, db=db) is None
    assert db.declared_kind("gv_free", 1) == "predicate"


def test_field_named_clause_free_declaration_is_unaffected():
    """Verification point 2: the ``-private([zonkish(X, Y)])`` shape --
    real field names, no row -- is a DIFFERENT mechanism from the
    arity-only one above and must not be swept up by this fix."""
    db = Database()
    db.declare_functor("zonkish", ("X", "Y"))
    assert field_names_for("zonkish", arity=2, db=db) == ("X", "Y")
    assert db.declared_kind("zonkish", 2) == "data"

