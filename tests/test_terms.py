"""Tests for clausal.terms — Step 9.

Covers:
  - Python literals as terms (direct — no wrappers)
  - term_str for all term types
"""

from __future__ import annotations

import dataclasses
import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.terms import (
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
        t = chars("hello")
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


# ── The cons helpers are gone ─────────────────────────────────────────────────


def test_cons_helpers_are_removed():
    """``list_to_cons`` / ``cons_to_list`` built and read a ``cons``/``nil``
    chain of ``Compound`` terms, ``nil`` being the non-term ``nil()``.  They
    were removed with no successor (Compound retirement slice 4, ruling R4):
    a list is a Python list."""
    import clausal.terms as T
    for name in ("list_to_cons", "cons_to_list"):
        assert not hasattr(T, name), name
        assert name not in T.__all__, name


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
        assert term_str(chars("abc")) == '"abc"'
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
        assert term_str(("foo", 1, 2)) == "foo(1, 2)"

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

    byte-parity requirement (the plan): ``term_str(("point", 1, 2))`` must
    equal the class-era rendering byte-for-byte with styling OFF -- the
    literal recorded string from ``TestTermStr::test_compound`` above,
    ``"foo(1, 2)"``'s sibling for a ``point`` functor.
    """

    def test_cell_matches_the_class_era_rendering_byte_for_byte(self):
        # The class-era anchor: term_str of the retired Compound("point",
        # (1, 2)) printed exactly this.
        assert term_str(("point", 1, 2)) == "point(1, 2)"

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
    got the indented multi-line form."""

    def test_short_cell_stays_flat(self):
        assert term_pformat(("pt", 1, 2), width=80) == "pt(1, 2)"

    def test_wide_cell_gets_the_multiline_form(self):
        wide = ("bigfunctor",) + tuple(range(1, 20))
        cell_result = term_pformat(wide, width=20)
        # byte-identical to what the retired Compound class printed (measured
        # on the last engine that had it)
        assert cell_result == (
            "bigfunctor(\n" + "".join(f"  {i},\n" for i in range(1, 19))
            + "  19\n)")

    def test_zero_arg_cell_stays_flat_like_zero_arg_compound(self):
        # A str-functor cell always has slot 0, so "zero args" means a
        # 1-tuple.
        # Spec §6.7: that flat form is the ATOM's bare name -- the 1-tuple
        # is an atom, not a zero-argument call (it printed ``atom_like()``
        # before atoms became cells).
        assert term_pformat("atom_like", width=1) == "atom_like"

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

