"""The engine-level half of D35: ``True``/``False``/``Undefined`` ARE the atoms
``true``/``false``/``undefined`` to every layer that decides -- unify (C),
``structural_eq``, the standard-order key, the index keys, ``mint``, the
evaluators and the renderers -- while the OBJECTS stay Python's.

The front-end table is tests/iso_l3/test_l3_truth_atoms.py; this file pins
the primitives those answers are built from, so a regression names its layer.
"""
from __future__ import annotations

import pytest

from clausal.logic.atoms import (
    is_atom, is_truth_atom, mint, spelling, truth_atom, truth_spelling,
)
from clausal.logic.builtins._helpers import term_key, _ORD_ATOM, _ORD_NUM
from clausal.logic.compiler.arg_index import (
    _arg_to_index_key, _runtime_arg_key, _INDEX_VAR,
)
from clausal.logic.constraints import structural_eq
from clausal.logic.exact_arith import evaluate
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, unify
from clausal.terms import Undefined, term_str, term_canonical

TRUTH = [(True, "true"), (False, "false"), (Undefined, "undefined")]


# ── the one definition ───────────────────────────────────────────────────────

@pytest.mark.parametrize("obj, spell", TRUTH)
def test_the_truth_atoms_are_atoms_with_their_spelling(obj, spell):
    assert is_truth_atom(obj)
    assert is_atom(obj)
    assert spelling(obj) == spell
    assert truth_spelling(obj) == spell
    assert truth_atom(spell) is obj
    assert mint(spell) is obj                 # a runtime-built atom IS the object


def test_nothing_else_is_a_truth_atom():
    for x in (1, 0, 1.0, "true", ("true",), None, [], Var()):
        assert not is_truth_atom(x)
    assert truth_atom("foo") is None
    assert mint("foo") == "foo"


# ── unification (C) ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("a, b", [
    (True, 1), (False, 0), (1, True), (0, False), (True, 1.0),
    (("f", True), ("f", 1)), ([True], [1]), (True, False),
    ([True], b"\x01"), (b"\x00", [False]),          # a bool is not a code
    (True, ("$chars", "true")),                     # a STRING is not the atom
    (Undefined, 1), (Undefined, "undefine"),
])
def test_a_truth_atom_never_unifies_with_a_number(a, b):
    assert not unify(a, b, Trail())
    assert not unify(b, a, Trail())


@pytest.mark.parametrize("obj, spell", TRUTH)
def test_a_truth_atom_unifies_with_itself_and_with_its_spelling(obj, spell):
    assert unify(obj, obj, Trail())
    assert unify(obj, spell, Trail())      # the same atom in its other spelling
    assert unify(spell, obj, Trail())
    v = Var()
    assert unify(v, obj, Trail())
    assert unify(v, obj, Trail()) and not unify(v, 1, Trail())


# ── ==/2 ─────────────────────────────────────────────────────────────────────

def test_structural_eq_reads_the_atom():
    assert not structural_eq(True, 1)
    assert not structural_eq(False, 0)
    assert not structural_eq(1, True)
    assert structural_eq(True, "true")
    assert structural_eq("undefined", Undefined)
    assert not structural_eq(True, "false")


# ── standard order ───────────────────────────────────────────────────────────

def test_the_truth_atoms_key_in_the_atom_band():
    for obj, spell in TRUTH:
        assert term_key(obj) == (_ORD_ATOM, spell) == term_key(spell)
    assert term_key(1)[0] == _ORD_NUM
    assert sorted([True, "z", 1, "a", False, 1.5, Undefined], key=term_key) == \
        [1, 1.5, "a", False, True, Undefined, "z"]


# ── indexing ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("obj, spell", TRUTH)
def test_the_index_key_is_the_atoms_bucket_never_the_ints(obj, spell):
    assert _arg_to_index_key(obj) == (spell, 0) == _runtime_arg_key(obj)
    assert _arg_to_index_key(spell) == (spell, 0)
    assert _arg_to_index_key(1) == 1 and _arg_to_index_key(0) == 0
    assert _arg_to_index_key(obj) != _arg_to_index_key(1)
    assert _INDEX_VAR not in (_arg_to_index_key(obj),)


# ── arithmetic ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("obj", [True, False, Undefined])
def test_a_truth_atom_is_not_evaluable(obj):
    with pytest.raises(LogicException) as ei:
        evaluate(obj, "is/2")
    assert ei.value.term[1][:2] == ("type_error", "evaluable")
    assert ei.value.term[1][2] == ("/", obj, 0)


# ── rendering ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("obj, spell", TRUTH)
def test_the_renderers_print_the_spelling(obj, spell):
    assert term_str(obj) == spell
    assert term_canonical(obj) == spell
    assert term_str(("g", obj, [obj])) == f"g({spell}, [{spell}])"
