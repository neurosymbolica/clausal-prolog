"""Tests for the Prolog operator table."""
import pytest
from clausal.tools.prolog_operators import OperatorTable, OpEntry


class TestOperatorTable:
    def test_iso_default_has_comma(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(",")
        assert e is not None
        assert e.precedence == 1000
        assert e.specifier == "xfy"

    def test_iso_default_has_plus(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("+")
        assert e is not None
        assert e.precedence == 500
        assert e.specifier == "yfx"

    def test_iso_default_has_negation(self):
        t = OperatorTable.iso_default()
        e = t.lookup_prefix("\\+")
        assert e is not None
        assert e.precedence == 900
        assert e.specifier == "fy"

    def test_iso_default_has_unify(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("=")
        assert e is not None
        assert e.precedence == 700
        assert e.specifier == "xfx"

    def test_iso_default_has_is(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("is")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_clause_arrow(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(":-")
        assert e is not None
        assert e.precedence == 1200
        assert e.specifier == "xfx"

    def test_iso_default_has_dcg_arrow(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("-->")
        assert e is not None
        assert e.precedence == 1200

    def test_iso_default_has_semicolon(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(";")
        assert e is not None
        assert e.precedence == 1100
        assert e.specifier == "xfy"

    def test_iso_default_has_arrow(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("->")
        assert e is not None
        assert e.precedence == 1050
        assert e.specifier == "xfy"

    def test_iso_default_has_not_equal(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("\\=")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_struct_eq(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("==")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_arith_eq(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("=:=")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_univ(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("=..")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_multiply(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("*")
        assert e is not None
        assert e.precedence == 400
        assert e.specifier == "yfx"

    def test_iso_default_has_divide(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("/")
        assert e is not None
        assert e.precedence == 400

    def test_iso_default_has_integer_divide(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("//")
        assert e is not None
        assert e.precedence == 400

    def test_iso_default_has_mod(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("mod")
        assert e is not None
        assert e.precedence == 400

    def test_iso_default_has_rem(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("rem")
        assert e is not None
        assert e.precedence == 400

    def test_iso_default_has_power(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("**")
        assert e is not None
        assert e.precedence == 200
        assert e.specifier == "xfx"

    def test_iso_default_has_less_than(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("<")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_greater_than(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(">")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_less_equal(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("=<")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_greater_equal(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(">=")
        assert e is not None
        assert e.precedence == 700

    def test_iso_default_has_colon(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(":")
        assert e is not None
        assert e.precedence == 600
        assert e.specifier == "xfy"

    def test_iso_default_has_bitwise_and(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("/\\")
        assert e is not None
        assert e.precedence == 500

    def test_iso_default_has_bitwise_or(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("\\/")
        assert e is not None
        assert e.precedence == 500

    def test_iso_default_has_left_shift(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix("<<")
        assert e is not None
        assert e.precedence == 400

    def test_iso_default_has_right_shift(self):
        t = OperatorTable.iso_default()
        e = t.lookup_infix(">>")
        assert e is not None
        assert e.precedence == 400

    def test_prefix_minus(self):
        t = OperatorTable.iso_default()
        e = t.lookup_prefix("-")
        assert e is not None
        assert e.precedence == 200
        assert e.specifier == "fy"

    def test_prefix_backslash(self):
        t = OperatorTable.iso_default()
        e = t.lookup_prefix("\\")
        assert e is not None
        assert e.precedence == 200
        assert e.specifier == "fy"

    def test_prefix_directive(self):
        t = OperatorTable.iso_default()
        e = t.lookup_prefix(":-")
        assert e is not None
        assert e.precedence == 1200
        assert e.specifier == "fx"

    def test_prefix_query(self):
        t = OperatorTable.iso_default()
        e = t.lookup_prefix("?-")
        assert e is not None
        assert e.precedence == 1200
        assert e.specifier == "fx"

    def test_same_name_prefix_and_infix(self):
        """'-' is both prefix (fy 200) and infix (yfx 500)."""
        t = OperatorTable.iso_default()
        pre = t.lookup_prefix("-")
        inf = t.lookup_infix("-")
        assert pre is not None
        assert inf is not None
        assert pre.specifier == "fy"
        assert inf.specifier == "yfx"

    def test_define_user_op(self):
        t = OperatorTable.iso_default()
        t.define(700, "xfx", "<>")
        e = t.lookup_infix("<>")
        assert e is not None
        assert e.precedence == 700

    def test_user_defined_list(self):
        t = OperatorTable.iso_default()
        assert t.user_defined() == []
        t.define(700, "xfx", "<>")
        ud = t.user_defined()
        assert len(ud) == 1
        assert ud[0].name == "<>"

    def test_define_replaces_same_kind(self):
        t = OperatorTable.iso_default()
        t.define(300, "xfx", "+")  # replace infix +
        e = t.lookup_infix("+")
        assert e is not None
        assert e.precedence == 300

    def test_is_operator(self):
        t = OperatorTable.iso_default()
        assert t.is_operator("+")
        assert t.is_operator(",")
        assert not t.is_operator("foobar")

    def test_lookup_nonexistent(self):
        t = OperatorTable.iso_default()
        assert t.lookup_infix("foobar") is None
        assert t.lookup_prefix("foobar") is None
        assert t.lookup_postfix("foobar") is None


class TestSWIDefaults:
    def test_swi_default_has_xor(self):
        t = OperatorTable.swi_default()
        e = t.lookup_infix("xor")
        assert e is not None
        assert e.precedence == 500

    def test_swi_default_has_rdiv(self):
        t = OperatorTable.swi_default()
        e = t.lookup_infix("rdiv")
        assert e is not None
        assert e.precedence == 400

    def test_swi_default_has_prefix_plus(self):
        t = OperatorTable.swi_default()
        e = t.lookup_prefix("+")
        assert e is not None
        assert e.precedence == 200

    def test_swi_default_has_dict_ops(self):
        t = OperatorTable.swi_default()
        assert t.lookup_infix(">:<") is not None
        assert t.lookup_infix(":<") is not None

    def test_swi_inherits_iso(self):
        t = OperatorTable.swi_default()
        assert t.lookup_infix("=") is not None
        assert t.lookup_infix(",") is not None


class TestScryerDefaults:
    def test_scryer_default_is_iso_base(self):
        t = OperatorTable.scryer_default()
        e = t.lookup_infix("=")
        assert e is not None

    def test_scryer_has_clpz_ops(self):
        t = OperatorTable.scryer_default()
        assert t.lookup_infix("#=") is not None
        assert t.lookup_infix("#\\=") is not None
        assert t.lookup_infix("#<") is not None
        assert t.lookup_infix("#>") is not None
        assert t.lookup_infix("#=<") is not None
        assert t.lookup_infix("#>=") is not None

    def test_scryer_clpz_ops_precedence(self):
        t = OperatorTable.scryer_default()
        for op_name in ("#=", "#\\=", "#<", "#>", "#=<", "#>="):
            e = t.lookup_infix(op_name)
            assert e is not None
            assert e.precedence == 700
            assert e.specifier == "xfx"
