"""Public atom API (spec §6.1). Representation-agnostic: these tests hold
before and after the Stage B flip; only the ``_repr_probe`` tests pin the
current representation and are rewritten by Stage B."""
import pytest
from clausal.logic.atoms import mint, is_atom, spelling, char_atom, is_char_atom
from clausal.logic.predicate import make_atom, is_atom_value


def test_mint_roundtrips_spelling():
    a = mint("foo")
    assert is_atom(a)
    assert spelling(a) == "foo"


def test_mint_is_equal_for_equal_spellings():
    assert mint("foo") == mint("foo")
    assert mint("foo") != mint("bar")


def test_mint_rejects_non_str():
    with pytest.raises(TypeError):
        mint(3)


def test_spelling_rejects_non_atom():
    with pytest.raises(TypeError):
        spelling(3)


def test_char_atom_is_a_one_char_atom():
    c = char_atom("x")
    assert is_atom(c) and is_char_atom(c) and spelling(c) == "x"
    assert not is_char_atom(mint("xy"))
    with pytest.raises(ValueError):
        char_atom("xy")


def test_make_atom_delegates_to_mint():
    assert make_atom("foo") == mint("foo")


def test_is_atom_value_accepts_minted_atom():
    assert is_atom_value(mint("foo"))


def test_repr_probe_plan0_str():
    # Plan 0: today's representation. Stage B replaces this test with the
    # cell probe (see Task 12).
    assert mint("foo") == "foo"
