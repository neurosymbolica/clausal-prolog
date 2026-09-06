"""Tests for clausal.terms — Step 9.

Covers:
  - Compound construction and repr
  - Python literals as terms (direct — no wrappers)
  - list_to_cons / cons_to_list helpers
  - term_str for all term types
  - KWTerm term_str (WK-3)
"""

from __future__ import annotations

import dataclasses
import pytest

from clausal.logic.atoms import mint
from clausal.terms import (
    Compound,
    KWTerm,
    list_to_cons,
    cons_to_list,
    term_str,
    term_pformat,
    Var,
    # goal/operator nodes used in term_str tests
    Unify as Is, And, Or, Not,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Lt, LtE, Gt, GtE, ArithEq, ArithNeq, in_, NotIn,
    Call, LoadName, LoadAttr,
    Predicate,
    Negate, Invert,
    BitAnd, BitOr, BitXor, LShift, RShift,
)


# ── Synthetic functor dataclass ────────────────────────────────────────────────


@dataclasses.dataclass
class point:
    x: object = None
    y: object = None


# ── TestCompound ───────────────────────────────────────────────────────────────


class TestCompound:
    def test_construction(self):
        # nv
        c = Compound("foo", (1, 2, 3))
        assert c.functor == "foo"
        assert c.args == (1, 2, 3)

    def test_arity_zero(self):
        # nv
        c = Compound("nil", ())
        assert c.functor == "nil"
        assert c.args == ()

    def test_var_functor(self):
        # nv
        v = Var()
        c = Compound(v, (1,))
        assert c.functor is v

    def test_equality_same(self):
        # nv
        assert Compound("f", (1, 2)) == Compound("f", (1, 2))

    def test_equality_different_functor(self):
        # nv
        assert Compound("f", (1,)) != Compound("g", (1,))

    def test_equality_different_args(self):
        # nv
        assert Compound("f", (1,)) != Compound("f", (2,))

    def test_equality_different_arity(self):
        # nv
        assert Compound("f", (1,)) != Compound("f", (1, 2))

    def test_str_no_args(self):
        # nv
        assert str(Compound("nil", ())) == "nil()"

    def test_str_with_args(self):
        # nv
        assert str(Compound("foo", (1, "x"))) == 'foo(1, "x")'

    def test_nested_str(self):
        # nv
        inner = Compound("g", (2,))
        outer = Compound("f", (inner,))
        assert str(outer) == "f(g(2))"

    def test_repr_is_dataclass_repr(self):
        # nv
        c = Compound("foo", (1,))
        r = repr(c)
        assert "Compound" in r
        assert "foo" in r


# ── TestPythonLiteralsAreTerms ─────────────────────────────────────────────────


class TestPythonLiteralsAreTerms:
    """Python built-in types are terms directly — no wrapper needed."""

    def test_int_is_term(self):
        # nv
        t = 42
        assert isinstance(t, int)
        assert term_str(t) == "42"

    def test_float_is_term(self):
        # nv
        t = 3.14
        assert term_str(t) == "3.14"

    def test_str_is_term(self):
        # nv
        t = "hello"
        assert term_str(t) == '"hello"'

    def test_bool_true_is_term(self):
        # nv
        assert term_str(True) == "True"

    def test_bool_false_is_term(self):
        # nv
        assert term_str(False) == "False"

    def test_none_is_term(self):
        # nv
        assert term_str(None) == "None"

    def test_list_is_term(self):
        # nv
        assert term_str([1, 2, 3]) == "[1, 2, 3]"

    def test_empty_list_is_term(self):
        # nv
        assert term_str([]) == "[]"

    def test_bytes_is_term(self):
        # nv
        assert term_str(b"hi") == "b'hi'"

    def test_ellipsis_is_term(self):
        # nv
        assert term_str(...) == "..."



# ── TestConsHelpers ────────────────────────────────────────────────────────────


class TestConsHelpers:
    def test_empty_list_to_cons(self):
        # nv
        c = list_to_cons([])
        assert isinstance(c, Compound)
        assert c.functor == "nil"
        assert c.args == ()

    def test_single_element(self):
        # nv
        c = list_to_cons([42])
        assert c.functor == "cons"
        assert c.args[0] == 42
        assert isinstance(c.args[1], Compound)
        assert c.args[1].functor == "nil"

    def test_three_elements(self):
        # nv
        c = list_to_cons([1, 2, 3])
        assert c.functor == "cons"
        assert c.args[0] == 1
        assert c.args[1].functor == "cons"
        assert c.args[1].args[0] == 2
        assert c.args[1].args[1].functor == "cons"
        assert c.args[1].args[1].args[0] == 3
        assert c.args[1].args[1].args[1].functor == "nil"

    def test_cons_to_list_empty(self):
        # nv
        nil = Compound("nil", ())
        assert cons_to_list(nil) == []

    def test_cons_to_list_single(self):
        # nv
        c = list_to_cons([99])
        assert cons_to_list(c) == [99]

    def test_roundtrip(self):
        # nv
        original = [1, "two", 3.0, None]
        assert cons_to_list(list_to_cons(original)) == original

    def test_roundtrip_empty(self):
        # nv
        assert cons_to_list(list_to_cons([])) == []

    def test_cons_to_list_improper_raises(self):
        # nv
        improper = Compound("cons", (1, 2))  # tail is 2, not nil
        with pytest.raises(ValueError):
            cons_to_list(improper)

    def test_cons_to_list_non_cons_raises(self):
        # nv
        with pytest.raises(ValueError):
            cons_to_list(Compound("foo", (1,)))

    def test_non_nil_tail_raises(self):
        # list_to_cons always produces proper lists, but cons_to_list
        # rejects improper ones
        # nv
        improper = Compound("cons", (1, Compound("cons", (2, 3))))
        with pytest.raises(ValueError):
            cons_to_list(improper)


# ── TestTermStr ────────────────────────────────────────────────────────────────


class TestTermStr:
    def test_none(self):
        # nv
        assert term_str(None) == "None"

    def test_ellipsis(self):
        # nv
        assert term_str(...) == "..."

    def test_true(self):
        # nv
        assert term_str(True) == "True"

    def test_false(self):
        # nv
        assert term_str(False) == "False"

    def test_int(self):
        # nv
        assert term_str(0) == "0"
        assert term_str(-5) == "-5"

    def test_float(self):
        # nv
        assert term_str(1.5) == "1.5"

    def test_complex(self):
        # nv
        result = term_str(1 + 2j)
        assert "1" in result and "2" in result

    def test_str(self):
        # nv — a STRING is double-quoted; the ATOM is what quotes with ''.
        assert term_str("abc") == '"abc"'
        assert term_str(mint("abc")) == "abc"

    def test_bytes(self):
        # nv
        assert term_str(b"x") == "b'x'"

    def test_list(self):
        # nv
        assert term_str([1, 2]) == "[1, 2]"

    def test_nested_list(self):
        # nv
        assert term_str([[1, 2], [3, 4]]) == "[[1, 2], [3, 4]]"

    def test_var_unbound(self):
        # nv
        v = Var()
        s = term_str(v)
        assert s == "_"

    def test_compound(self):
        # nv
        assert term_str(Compound("foo", (1, 2))) == "foo(1, 2)"


    def test_kwterm(self):
        # nv
        t = KWTerm("point", x=1, y=2)
        s = term_str(t)
        assert s.startswith("point(")
        assert "x=1" in s
        assert "y=2" in s

    def test_is_node(self):
        # nv
        v = Var()
        s = term_str(Is(left=v, right=42))
        assert "is" in s.lower() or "=" in s

    def test_and_node(self):
        # nv
        s = term_str(And(left=True, right=False))
        assert "and" in s.lower() or "&" in s

    def test_or_node(self):
        # nv
        s = term_str(Or(left=True, right=False))
        assert "or" in s.lower() or "|" in s

    def test_not_node(self):
        # nv
        s = term_str(Not(operand=True))
        assert "not" in s.lower() or "!" in s

    def test_add_node(self):
        # nv
        s = term_str(Add(left=1, right=2))
        assert "+" in s

    def test_lt_node(self):
        # nv
        s = term_str(Lt(left=1, right=2))
        assert "<" in s

    def test_eq_node(self):
        # nv
        s = term_str(ArithEq(left=1, right=1))
        assert "==" in s

    def test_call_node(self):
        # nv
        s = term_str(Call(func=LoadName(name="foo"), args=[1, 2], kwargs=[]))
        assert "foo" in s

    def test_loadname_node(self):
        # nv
        assert term_str(LoadName(name="bar")) == "bar"

    def test_predicate_node(self):
        # nv
        head = Call(func=LoadName(name="foo"), args=[], kwargs=[])
        s = term_str(Predicate(head=head, body=True))
        assert "<-" in s

    def test_dataclass_fallback(self):
        """A functor dataclass without special ops falls back to repr."""
        # nv
        p = point(x=1, y=2)
        s = term_str(p)
        # Should contain the type name or field info
        assert "point" in s or "1" in s

    def test_negate_node(self):
        # nv
        s = term_str(Negate(operand=5))
        assert "-" in s

    def test_invert_node(self):
        # nv
        s = term_str(Invert(operand=5))
        assert "~" in s

    def test_arithmetic_ops(self):
        # nv
        for NodeClass, expected_op in [
            (Sub, "-"), (Mult, "*"), (Div, "/"),
            (FloorDiv, "//"), (Mod, "%"), (Pow, "**"),
        ]:
            s = term_str(NodeClass(left=3, right=2))
            assert expected_op in s, f"{NodeClass.__name__}: expected {expected_op!r} in {s!r}"

    def test_bitwise_ops(self):
        # nv
        for NodeClass, expected in [
            (BitAnd, "&"), (BitOr, "|"), (BitXor, "^"),
            (LShift, "<<"), (RShift, ">>"),
        ]:
            s = term_str(NodeClass(left=3, right=1))
            assert expected in s, f"{NodeClass.__name__}: expected {expected!r} in {s!r}"

    def test_comparison_ops(self):
        # nv
        for NodeClass, expected in [
            (LtE, "<="), (Gt, ">"), (GtE, ">="),
            (ArithNeq, "!="), (in_, "in"), (NotIn, "not in"),
        ]:
            s = term_str(NodeClass(left=1, right=2))
            assert expected in s, f"{NodeClass.__name__}: expected {expected!r} in {s!r}"


class TestCellTermStr:
    """P3-2 Task 7: cells (the tagged-tuple compound representation,
    ``clausal/logic/cells.py``) rendered by ``term_str``.

    Byte-parity requirement (the plan): ``term_str(("point", 1, 2))`` must
    equal the class-era rendering byte-for-byte with styling OFF -- the
    literal recorded string from ``TestTermStr::test_compound`` above,
    ``"foo(1, 2)"``'s sibling for a ``point`` functor.
    """

    def test_cell_matches_the_class_era_rendering_byte_for_byte(self):
        # The class-era anchor: term_str(Compound("point", (1, 2))) would
        # have printed exactly this (see TestTermStr.test_compound's
        # "foo(1, 2)" for the same shape with a different functor name).
        assert term_str(("point", 1, 2)) == "point(1, 2)"
        assert term_str(("point", 1, 2)) == term_str(Compound("point", (1, 2)))

    def test_nested_cells(self):
        assert term_str(("pt", 1, ("q", 2))) == "pt(1, q(2))"

    def test_tuple_data_cell_renders_as_a_plain_tuple(self):
        from clausal.logic.cells import TUPLE_TAG

        assert term_str((TUPLE_TAG, 1, 2)) == "(1, 2)"

    def test_tuple_data_cell_with_no_elements_renders_empty_parens(self):
        from clausal.logic.cells import TUPLE_TAG

        assert term_str((TUPLE_TAG,)) == "()"

    def test_hidden_atom_functor_renders_the_human_form(self):
        """A ``-hide``-mangled functor renders as ``module.name(...)`` --
        the same display substitution the plain-str branch already gives a
        mangled ATOM (P3-1 Task 6, design doc section 1b) -- reused here
        WITHOUT quoting, since a functor position is never quoted."""
        from clausal.logic.atoms import mangle

        mangled = mangle("mymod", "secret")
        assert term_str((mangled, 1, 2)) == "mymod.secret(1, 2)"

    def test_bound_var_functor_tuple_is_not_a_compound(self):
        """Task 5/Task 7 review ruling: cell recognition reads slot 0 RAW,
        never dereffed.  BEFORE this fix, ``term_str``'s cell branch tested
        ``isinstance(deref(t[0]), str)``, so a tuple whose slot 0 was a
        logic Var *bound* to a str rendered as a compound (``point(1, 2)``)
        -- disagreeing with ``_helpers._cell_functor``'s exact-type,
        raw-slot-0 recognition used everywhere else.  AFTER this fix, the
        same tuple is NOT a cell (a Var, bound or not, is never a legal
        slot 0 -- see ``clausal/logic/cells.py``'s module docstring) and
        keeps the ordinary (non-compound) tuple rendering."""
        from clausal.logic.variables import Trail, unify

        v = Var()
        trail = Trail()
        assert unify(v, "point", trail)
        t = (v, 1, 2)
        s = term_str(t)
        assert "point(1, 2)" not in s
        assert not s.startswith("point(")


class TestCellTermPformat:
    """P3-2 Task 7: ``term_pformat`` smoke tests -- a wide cell used to fall
    through every isinstance branch straight to ``return flat``, so it never
    got the indented multi-line form a wide ``Compound`` gets."""

    def test_short_cell_stays_flat(self):
        assert term_pformat(("pt", 1, 2), width=80) == "pt(1, 2)"

    def test_wide_cell_gets_the_compound_equivalent_multiline_form(self):
        wide = ("bigfunctor",) + tuple(range(1, 20))
        compound_equivalent = Compound("bigfunctor", tuple(range(1, 20)))
        cell_result = term_pformat(wide, width=20)
        compound_result = term_pformat(compound_equivalent, width=20)
        assert "\n" in cell_result
        assert cell_result.startswith("bigfunctor(\n")
        assert cell_result.rstrip().endswith(")")
        # identical multi-line shape to the Compound it replaced -- same
        # functor, same args, same indentation
        assert cell_result == compound_result

    def test_zero_arg_cell_stays_flat_like_zero_arg_compound(self):
        # A str-functor cell always has slot 0, so "zero args" means a
        # 1-tuple; matches Compound's `if not t.args: return flat` guard.
        # Spec §6.7: that flat form is the ATOM's bare name -- the 1-tuple
        # is an atom, not a zero-argument call (it printed ``atom_like()``
        # before atoms became cells).
        assert term_pformat(("atom_like",), width=1) == "atom_like"

    def test_wide_tuple_data_cell_gets_multiline_form(self):
        from clausal.logic.cells import TUPLE_TAG

        wide = (TUPLE_TAG,) + tuple(range(1, 20))
        result = term_pformat(wide, width=20)
        assert "\n" in result
        assert result.startswith("(\n")
        assert result.rstrip().endswith(")")

    def test_empty_tuple_data_cell_stays_flat(self):
        from clausal.logic.cells import TUPLE_TAG

        assert term_pformat((TUPLE_TAG,), width=1) == "()"

