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


# ── Task 3: the C twins ─────────────────────────────────────────────────────

def test_c_unify_does_not_read_an_atom_as_a_list():
    from clausal.logic.variables import unify, Trail
    t = Trail()
    assert not unify("ab", ["a", "b"], t) and unify(chars("ab"), ["a", "b"], t)
    assert unify("ab", "ab", t) and not unify("ab", chars("ab"), t) and unify(chars("ab"), chars("ab"), t)
    assert unify(chars(""), [], t) and not unify("", [], t)      # '' is the atom '', not nil


def test_c_and_python_list_twins_agree_on_an_atom_target():
    from clausal.logic.runtime.list_unify import _head_list_unify_input_py
    from clausal.logic.runtime._list_unify import _head_list_unify_input
    from clausal.logic.variables import Var, Trail, deref
    for fn in (_head_list_unify_input_py, _head_list_unify_input):
        assert fn("ab", [Var()], Var(), [], Trail()) is False          # an atom is not a sequence
        h, tl, t = Var(), Var(), Trail()
        assert fn(chars("ab"), [h], tl, [], t) is True and deref(h) == "a" and deref(tl) == chars("b")


# ── Task 4: the entry points read a str as the atom ─────────────────────────

def test_an_atom_is_not_text_at_the_funnels():
    from clausal.logic.builtins.lists import _as_items
    from clausal.logic.runtime._seg_helpers import normalize_seg_input
    from clausal.modules.py import to_text
    from clausal.logic.builtins._helpers import _functor_name, _arity, _args_list, _standard_order_key
    assert _as_items("ab") is None and _as_items(chars("ab")) == ["a", "b"]
    assert normalize_seg_input("ab") == "ab" and normalize_seg_input(chars("ab")) == "ab"
    assert to_text("ab") == "ab" and to_text(chars("ab")) == "ab"
    assert (_functor_name("ab"), _arity("ab"), _args_list("ab")) == ("ab", 0, [])
    assert (_functor_name(chars("ab")), _arity(chars("ab"))) == (".", 2)
    assert _standard_order_key("ab") == _standard_order_key(mint("ab")) != _standard_order_key(chars("ab"))


def test_type_checks_and_goals(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, 'p(R) <- if_(atom(foo), R is yes, R is no)\nq(R) <- if_(string(foo), R is yes, R is no)\n'
                         'r(R) <- if_(atom("foo"), R is yes, R is no)\nfoo,\ns <- call(foo)\nt(R) <- if_("ab" == [a, b], R is yes, R is no)\n'
                         'u(R) <- if_(ab == [a, b], R is yes, R is no)\n', hdr="-double_quotes(chars)\n-private([yes, no, a, b, ab])\n")
    assert _first(mod, "p", Var()) == ["yes"] and _first(mod, "q", Var()) == ["no"] and _first(mod, "r", Var()) == ["no"]
    assert _first(mod, "s") is not None
    assert _first(mod, "t", Var()) == ["yes"] and _first(mod, "u", Var()) == ["no"]


# ── Task 5: the seam ────────────────────────────────────────────────────────

def test_a_python_str_crosses_in_as_the_atom_and_the_carrier_crosses_out_as_text():
    from clausal.logic.python_terms import to_term, from_term
    from clausal.logic.to_python import to_python, unwrap_atom, wrap_text
    assert to_term("ab") == "ab" and to_term({"k": "v"}) == {"k": "v"} and to_term(["ab"]) == ["ab"]
    assert from_term(chars("ab")) == "ab" and from_term("ab") == "ab"
    assert to_python("ab") == "ab" and to_python(chars("ab")) == "ab"
    assert unwrap_atom("ab") == "ab" and wrap_text("ab") == "ab"


def test_a_thunk_result_str_is_the_atom(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, 'p(R) <- (R is ++"foo".upper())\nq(R) <- if_(atom(++"x"), R is yes, R is no)\nr(R) <- if_(string(++"x"), R is yes, R is no)\n')
    assert _first(mod, "p", Var()) == ["FOO"] and _first(mod, "q", Var()) == ["yes"] and _first(mod, "r", Var()) == ["no"]
