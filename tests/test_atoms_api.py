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


def test_repr_probe_cell():
    # Stage B (THE FLIP): the representation is the arity-0 cell. The ``is``
    # pins the interned-spelling fast path -- the ONE place identity is
    # allowed to be observed (spec §5.2); the tuples themselves are fresh.
    assert mint("foo") == ("foo",)
    assert mint("foo")[0] is mint("foo")[0]


def test_the_cell_is_the_only_atom_shape():
    assert is_atom(("foo",)) and spelling(("foo",)) == "foo" and is_char_atom(("a",))
    assert not is_atom(("foo", 1)) and not is_atom(())
    # A plain str is a STRING, not an atom (spec §6.3).
    assert not is_atom("foo")
    assert not is_char_atom("a")
    with pytest.raises(TypeError):
        spelling("foo")
