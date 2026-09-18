"""Stage 2 of the atoms-as-str flip (spec 2026-09-18 §1, §4, Q2, Q3): an
atom is a Python str; the arity-0 cell is RESERVED and refused; a string
stays the ``('$chars', s)`` carrier stage 1 built."""
import pytest

from clausal.logic.atoms import (mint, key_of, is_atom, spelling, char_atom,
                                 is_char_atom, NIL_KEY)
from clausal.logic.cells import (chars, is_chars, refuse_reserved_1tuple,
                                 is_reserved_1tuple, compound_cell_shape, _cell_shape)


def test_an_atom_is_the_interned_str():
    a = mint("foo")
    assert a == "foo" and type(a) is str and is_atom(a) and spelling(a) == "foo"
    assert mint("foo") is mint("foo")            # interned: identity fast path on slot 0 stays


def test_nil_spellings_are_one_atom():
    assert mint("[]") == [] and key_of("[]") is NIL_KEY and spelling([]) == "[]"
    assert spelling("") == "" and mint("") == "" and spelling(chars("")) == "[]"   # '' is an atom; "" (chars) is nil


def test_a_char_atom_is_a_one_char_str():
    assert char_atom("a") == "a" and is_char_atom("a") and not is_char_atom("ab") and not is_char_atom(chars("a"))


def test_a_string_is_not_an_atom_and_an_atom_is_not_text():
    assert not is_atom(chars("foo")) and is_chars(chars("foo"))
    assert not is_chars("foo")


def test_the_1_tuple_is_reserved():
    assert is_reserved_1tuple(("x",)) and not is_reserved_1tuple(("f", 1)) and not is_reserved_1tuple(chars("x"))
    with pytest.raises(TypeError, match="reserved"):
        refuse_reserved_1tuple(("x",))
    with pytest.raises(TypeError, match="reserved"):
        _cell_shape(("x",))
    assert compound_cell_shape("x") == (False, None)
    assert compound_cell_shape(("f", 1)) == (True, "f")


# ── Task 2: the reader and the head compiler ────────────────────────────────

def _mod(tmp_path, body, hdr="-double_quotes(chars)\n-private([yes, no, a, b, foo])\n"):
    from clausal.testing import load_clausal_module
    p = tmp_path / "s2.clausal"; p.write_text(hdr + body)
    return load_clausal_module(p)


def _first(mod, name, *args):
    from clausal.logic.solve import call
    from clausal.logic.variables import deref
    for _ in call(name, *args, module=mod):
        return [deref(x) for x in args]
    return None


def test_an_atom_literal_compiles_to_the_str(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, "p(X) <- (X is foo)\nq(X) <- (X is 'foo')\nr(X) <- (X is \"foo\")\n")
    assert _first(mod, "p", Var()) == ["foo"] and _first(mod, "q", Var()) == ["foo"]
    assert _first(mod, "r", Var()) == [chars("foo")]


def test_an_atom_head_literal_matches_the_str_and_binds_output_mode(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, "p(foo, R) <- (R is yes)\np(bar, R) <- (R is no)\n", hdr="-private([yes, no, foo, bar])\n")
    assert _first(mod, "p", "foo", Var())[1] == "yes" and _first(mod, "p", mint("bar"), Var())[1] == "no"
    x = Var(); assert _first(mod, "p", x, Var())[0] == "foo"
    assert _first(mod, "p", chars("foo"), Var()) is None     # a STRING is not the atom


def test_an_atom_and_a_predicate_of_the_same_name_coexist(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, "foo,\np(X) <- (X is foo)\nq <- foo()\n", hdr="")
    assert _first(mod, "p", Var()) == ["foo"] and _first(mod, "q") is not None


def test_first_arg_indexing_keys_an_atom_by_the_str(tmp_path):
    from clausal.logic.variables import Var
    body = "".join(f"c({a}, {i}),\n" for i, a in enumerate(["a", "b", "foo", "yes", "no"]))
    mod = _mod(tmp_path, body)
    assert _first(mod, "c", "foo", Var())[1] == 2 and _first(mod, "c", chars("foo"), Var()) is None
