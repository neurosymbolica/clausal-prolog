"""A GENERIC walk over reified-vocabulary cells needs two things ``is_v`` and
``vfield`` cannot give, because both make the caller NAME the class or the
field: which of the nine a cell is, and what its fields are called.  A
downstream gate's ``_attrs(node)`` -- "this node's fields, without knowing
its type" -- read ``__dict__`` / ``_fields`` off an instance and went
silently inert on cells (it returned nothing and the walk descended into
nothing).  ``vkind``, ``vfields`` and ``vitems`` are the public answers, and
they are exported alongside ``is_v`` / ``vfield``, which were public in use
but never in ``__all__``.
"""
import pytest

from clausal import reflection
from clausal.reflection import (
    Clause, Goal, Variable, is_v, vfield, vfields, vitems, vkind,
)


def test_vkind_names_the_vocabulary_of_a_cell():
    assert vkind(Clause("h", [], None)) == "Clause"
    assert vkind(Goal("g", (), {})) == "Goal"
    assert vkind(Variable("X")) == "Variable"


def test_vkind_is_none_for_anything_that_is_not_one_of_the_nine():
    assert vkind(("Unify", "a", "b")) is None      # a body cell, not vocabulary
    assert vkind("an_atom") is None
    assert vkind(42) is None
    assert vkind(None) is None
    assert vkind(("x",)) is None                    # the reserved 1-tuple: no raise


def test_vfields_is_the_declaration_in_order():
    assert vfields(Clause("h", [], None)) == ("head", "goals", "position")
    assert vfields(Goal("g", (), {})) == ("name", "args", "kwargs")
    assert vfields(("Unify", "a", "b")) is None


def test_vitems_pairs_every_field_with_its_value_in_order():
    c = Clause("h", ["g1"], (3, 4))
    assert vitems(c) == {"head": "h", "goals": ["g1"], "position": (3, 4)}
    assert list(vitems(c)) == list(vfields(c))
    assert vitems(("Unify", "a", "b")) is None


def test_the_accessors_agree_with_each_other_and_with_vfield():
    c = Goal("g", (1, 2), {"k": 3})
    for name in vfields(c):
        assert vitems(c)[name] == vfield(c, name)
    assert is_v(c, Goal) and vkind(c) == "Goal"


def test_every_vocabulary_name_has_a_kind_and_fields():
    """The accessors are generated off the declaration table, so every one of
    the nine answers, and the field tuple is the constructor's own order."""
    for name in ("Atom", "Clause", "Escape", "FormatString", "Goal",
                 "IfThenElse", "ModuleDirective", "PythonCode", "Variable"):
        ctor = getattr(reflection, name)
        cell = ctor(*([None] * len(reflection._VOCAB_FIELDS[name])))
        assert vkind(cell) == name
        assert vfields(cell) == reflection._VOCAB_FIELDS[name]


def test_the_public_names_are_exported():
    for name in ("is_v", "vfield", "vkind", "vfields", "vitems"):
        assert name in reflection.__all__, name
