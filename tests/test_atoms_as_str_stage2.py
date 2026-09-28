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
    # the fact comes FIRST: a 0-arity predicate referenced as a value before
    # its first clause still loads the class (the value arm needs the
    # registration), and a class is no longer an atom -- an order-dependence
    # recorded in the handoff
    mod = _mod(tmp_path, 'foo,\np(R) <- if_(atom(foo), R is yes, R is no)\nq(R) <- if_(string(foo), R is yes, R is no)\n'
                         'r(R) <- if_(atom("foo"), R is yes, R is no)\ns <- call(foo)\nt(R) <- if_("ab" == [a, b], R is yes, R is no)\n'
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


# ── Task 6: the writers, the order, the legacy ──────────────────────────────

def test_write_and_order(tmp_path):
    from clausal.logic.variables import Var
    mod = _mod(tmp_path, "p(S) <- term_to_string('a b', S)\nq(S) <- write_to_string(\"ab\", S)\nw(S) <- term_to_string([a, \"b\"], S)\n"
                         "r(L) <- msort([\"b\", b, [a], a, 1], L)\n")
    assert _first(mod, "p", Var()) == [chars("'a b'")] and _first(mod, "q", Var()) == [chars("[a,b]")]
    assert _first(mod, "w", Var()) == [chars('[a, "b"]')]
    assert _first(mod, "r", Var()) == [[1, "a", "b", ["a"], chars("b")]]      # number < atoms < compounds; "b" == [b]


def test_no_class_is_an_atom_and_the_reserved_tuple_never_prints():
    from clausal.terms import term_str, term_canonical
    from clausal.logic.predicate import is_atom_value
    assert term_str("foo") == "foo" and term_str("a b") == "'a b'" and term_str("a b", quoted=False) == "a b"
    assert term_canonical("a b") == "'a b'" and term_canonical(chars("ab")) == "'.'(a,'.'(b,[]))"
    with pytest.raises(TypeError, match="reserved"):
        term_str(("foo",))
    assert not is_atom_value(type("Zero", (), {}))


class TestReviewRound1:
    """Rows from the roborev review of the stage-2 branch (2026-09-18)."""

    def test_must_be_callable_admits_an_atom_like_callable_1(self):
        from clausal.logic.builtins.type_checks import _check_type
        assert _check_type("callable", mint("foo")) is True
        assert _check_type("callable", chars("foo")) is True     # a non-empty string is the '.'/2 compound
        assert _check_type("callable", 3) is False

    def test_the_reader_spells_the_chars_tag_as_cells_does(self):
        from clausal.logic.cells import CHARS_TAG
        from clausal.logic.atoms import is_nil
        from clausal.tools.prolog_ast import PString
        from clausal.tools.prolog_reader import transform_term
        cell, _span, _names = transform_term(PString(""))
        assert cell == chars("") and cell[0] == CHARS_TAG and is_nil(cell)
        cell, _span, _names = transform_term(PString("ab"))
        assert cell == chars("ab") and not is_nil(cell)

    def test_call_of_a_control_construct_atom_reports_the_atom_not_a_1tuple(self, tmp_path):
        from clausal.logic.exceptions import LogicException
        mod = _mod(tmp_path, "")
        with pytest.raises(LogicException) as exc:
            _first(mod, "call", mint(","))
        # the diagnostic renders its culprit: with a reserved 1-tuple as the
        # culprit, str() of the error raised TypeError instead
        assert "control construct" in str(exc.value) and ",/0" in str(exc.value)


    def test_solve_refuses_a_control_construct_atom_like_call_does(self):
        from clausal.logic.exceptions import LogicException
        from clausal.logic.solve import _term_to_goal
        with pytest.raises(LogicException) as exc:
            _term_to_goal(mint(","))
        assert "control construct" in str(exc.value) and ",/0" in str(exc.value)
        # an ordinary atom still lowers to the 0-arity call of its name
        node = _term_to_goal(mint("foo"))
        assert node.func.name == "foo" and node.args == []

    def test_str_typed_node_fields_include_optional_str_names(self):
        from clausal.reflection import _str_typed_fields
        from clausal.pythonic_ast import nodes as simple_ast
        assert "name" in _str_typed_fields(simple_ast.PosOrKwParam)
        assert "name" in _str_typed_fields(simple_ast.MatchAs)       # declared Optional[str]
        assert "name" in _str_typed_fields(simple_ast.MatchStar)
        assert "rest" in _str_typed_fields(simple_ast.MatchMapping)
        assert _str_typed_fields(int) == frozenset()
        # a list[str] field is a LIST of names, not a name: it stays out
        assert "names" not in _str_typed_fields(simple_ast.Global)
        assert "kwd_attrs" not in _str_typed_fields(simple_ast.MatchClass)

    def test_raw_node_reads_a_name_field_raw_end_to_end(self):
        import ast
        from clausal.reflection import _ClauseReifier
        reifier = _ClauseReifier()
        param = reifier._raw_node("PosOrKwParam", {"name": ast.Constant("X")})
        assert param.name == "X" and type(param.name) is str
        star = reifier._raw_node("MatchStar", {"name": ast.Constant("rest")})   # Optional[str]
        assert star.name == "rest" and type(star.name) is str


class TestZeroArityValueBeforeFirstClause:
    """The order caveat of the 0-arity-predicate-as-value rule, closed: a
    reference BEFORE the predicate's first clause used to load the CLASS
    (prints like the atom, unequal to it, not a term).  ``p`` needs no atom
    declaration: the module's own 0-arity predicate makes the name known."""

    def test_reference_before_and_after_the_clause_is_the_same_atom(self, tmp_path):
        from clausal.logic.variables import Var
        mod = _mod(tmp_path, "before(V) <- (V is p)\np <- true\nafter(V) <- (V is p)\n",
                   hdr="")
        (b,) = _first(mod, "before", Var())
        (a,) = _first(mod, "after", Var())
        assert b == mint("p") and a == mint("p") and type(b) is str
        assert b == a

    def test_a_call_in_function_position_is_still_a_call(self, tmp_path):
        from clausal.logic.variables import Var
        mod = _mod(tmp_path, "p <- true\nt(R) <- (p, R is yes)\n", hdr="-private([yes])\n")
        (r,) = _first(mod, "t", Var())
        assert r == mint("yes")
