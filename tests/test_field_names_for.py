"""W4b-1: one accessor for a declared functor's field names (spec
docs/superpowers/specs/2026-09-22-w4b1-term-shape-rehome-design.md).

The contract that matters is the DECLAREDNESS one: ``None`` means the value
names nothing declared, ``()`` means declared with zero fields, and the
length of the tuple is the arity.  Arm 3 (a NAME) is the point of the
change: at W4b-2 a module attribute becomes a mangled atom, and arm 3
already answers for it."""
import dataclasses

import pytest

from clausal.logic.atoms import mangle
from clausal.logic.database import Database
from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY
from clausal.logic.predicate import (
    field_names_for, make_predicate, term_field_names_of_class,
)


@dataclasses.dataclass
class Point:
    x: int
    y: int


def test_arm1_dataclass_class_yields_declared_fields():
    assert field_names_for(Point) == ("x", "y")


def test_arm2_predicate_class_yields_its_fields():
    Pt = make_predicate("Pt", ["x", "y"])
    assert field_names_for(Pt) == ("x", "y")


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


def test_arm4_a_non_class_non_name_value_is_None():
    assert field_names_for(42) is None
    assert field_names_for(object()) is None


def test_zero_field_declaration_is_empty_tuple_not_None():
    """The contract's sharp edge: ``p()`` is DECLARED with no fields, and
    that is not the same answer as 'nothing declared'."""
    P = make_predicate("P0", [])
    assert field_names_for(P) == ()
    assert field_names_for("never_declared", arity=0, db=Database()) is None


def test_two_arities_exact_read_beats_the_by_name_fallback():
    db = Database()
    db.declare_functor("p", ("a",))
    db.declare_functor("p", ("a", "b"))
    assert field_names_for("p", arity=1, db=db) == ("a",)
    assert field_names_for("p", arity=2, db=db) == ("a", "b")
    # No arity: the by-name read, which answers the LAST declaration.  Pinned
    # so the documented lossiness is a recorded property, not a surprise.
    assert field_names_for("p", db=db) == ("a", "b")


def test_term_field_names_of_class_still_answers_for_its_callers():
    Pt = make_predicate("PtAlias", ["x"])
    assert term_field_names_of_class(Pt) == ("x",)
    assert term_field_names_of_class(Point) == ("x", "y")
    assert term_field_names_of_class(42) is None
