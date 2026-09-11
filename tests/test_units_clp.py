"""Units side channel around CLP: dimension analysis, shadows, reattachment.

Spec: docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md
"""
from decimal import (Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN,
                     ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR)
from fractions import Fraction

import pytest

from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException
from clausal.terms import Compound, Quantity
from clausal.modules.countries.european_union import euro
from clausal.modules.countries.japan import yen
from clausal.modules.countries.kuwait import kwd


def _assert_system_error(ei, code):
    term = ei.value.term
    assert isinstance(term, Compound) and term.functor == "error"
    inner = term.args[0]
    assert isinstance(inner, Compound) and inner.functor == "system_error"
    assert inner.args[0] == mint(code)


class TestSystemErrorHelper:
    def test_builds_iso_shape(self):
        from clausal.logic.exceptions import system_error
        term = system_error("units_mismatch", "(==)/2: metre vs second")
        assert term.functor == "error"
        assert term.args[0].functor == "system_error"
        assert term.args[0].args == (mint("units_mismatch"),)
        assert term.args[1] == "(==)/2: metre vs second"


_MODES = [ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN, ROUND_UP,
          ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR]


class TestExactNumberCurrency:
    def test_currency_quantity_keeps_fraction(self):
        q = Quantity(Fraction(1, 3), {euro: 1})
        assert type(q.value) is Fraction and q.value == Fraction(1, 3)

    def test_decimal_and_fraction_quantities_compare_equal(self):
        assert Quantity(Decimal("1500.00"), {euro: 1}) == Quantity(Fraction(1500), {euro: 1})
        assert hash(Quantity(Decimal("1500.00"), {euro: 1})) == hash(Quantity(Fraction(1500), {euro: 1}))

    def test_tagging_terminating_fraction_passes_precision_check(self):
        q = Quantity(Fraction(3, 2), euro)          # 1.50, within scale 2
        assert q.value == Fraction(3, 2)

    def test_tagging_non_terminating_fraction_fails_precision_check(self):
        from clausal.terms import CurrencyPrecisionError
        with pytest.raises(CurrencyPrecisionError):
            Quantity(Fraction(1, 3), euro)

    @pytest.mark.parametrize("mode", _MODES)
    @pytest.mark.parametrize("num", [-27, -25, -23, -5, -1, 0, 1, 5, 23, 25, 27, 125, 135])
    def test_fraction_rounding_agrees_with_decimal_rounding(self, mode, num):
        """Positive control: on terminating fractions the Fraction rounder and
        Decimal.quantize must give the same integer for every mode."""
        from clausal.terms import _round_fraction_to_int
        fr = Fraction(num, 10)                       # x.5 ties and non-ties, both signs
        expected = int(Decimal(num).scaleb(-1).quantize(Decimal(1), rounding=mode))
        assert _round_fraction_to_int(fr, mode) == expected

    def test_quantize_fraction_third_of_a_yen(self):
        from clausal.terms import _quantize_to_scale
        assert _quantize_to_scale(Fraction(1000, 3), 0, "half_even") == Decimal("333")
        assert _quantize_to_scale(Fraction(1, 3), 3, "half_even") == Decimal("0.333")

    def test_money_round_on_fraction_quantity(self):
        from clausal.logic.variables import Trail, Var, deref
        from clausal.modules.currency import _money_round_impl
        q = Quantity(Fraction(1000, 3), {yen: 1})
        out = Var()
        assert list(_money_round_impl(q, "half_even", out, Trail())) == [None]
        assert deref(out) == Quantity(Decimal("333"), {yen: 1})


import random

from clausal.logic.variables import Trail, Var, deref, get_attr, put_attr, unify
from clausal.logic.units_constraint import UNITS_KEY, UnitState
from clausal.modules.py.units import metre, second, ampere, volt, ohm, watt, kilogram
from clausal.terms import Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate, UnitsMismatch

M = {metre: 1}


def _bin(cls, left, right):
    """Nodes carry a leading ``position`` field: operands go by keyword."""
    return cls(left=left, right=right)


def _neg(operand):
    return Negate(operand=operand)

S = {second: 1}


def _dims_of_value(v):
    return dict(v.dims) if isinstance(v, Quantity) else {}


def _eval_with_quantity_arithmetic(t):
    """Fold a ground tree with Quantity's own operators — the oracle."""
    if isinstance(t, Add):
        return _eval_with_quantity_arithmetic(t.left) + _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Sub):
        return _eval_with_quantity_arithmetic(t.left) - _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Mult):
        return _eval_with_quantity_arithmetic(t.left) * _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Div):
        return _eval_with_quantity_arithmetic(t.left) / _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Pow):
        return _eval_with_quantity_arithmetic(t.left) ** _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Negate):
        return -_eval_with_quantity_arithmetic(t.operand)
    return t


_LEAVES = [2, 3, Quantity(3, M), Quantity(5, M), Quantity(4, S), Quantity(7, {}),
           Quantity(2, {kilogram: 1})]


def _random_tree(rng, depth):
    if depth == 0 or rng.random() < 0.3:
        return rng.choice(_LEAVES)
    op = rng.choice(["add", "sub", "mult", "div", "pow", "neg"])
    if op == "neg":
        return _neg(_random_tree(rng, depth - 1))
    if op == "pow":
        return _bin(Pow, _random_tree(rng, depth - 1), rng.choice([2, 3]))
    cls = {"add": Add, "sub": Sub, "mult": Mult, "div": Div}[op]
    return _bin(cls, _random_tree(rng, depth - 1), _random_tree(rng, depth - 1))


class TestRuleTablePositiveControl:
    def test_ground_dims_agree_with_quantity_arithmetic(self):
        from clausal.logic.units_clp import ground_dims
        rng = random.Random(20260912)
        seen_ok = seen_err = 0
        for _ in range(3000):
            tree = _random_tree(rng, 3)
            try:
                expected = _dims_of_value(_eval_with_quantity_arithmetic(tree))
            except UnitsMismatch:
                with pytest.raises(LogicException) as ei:
                    ground_dims(tree)
                _assert_system_error(ei, "units_mismatch")
                seen_err += 1
                continue
            except (ZeroDivisionError, TypeError, OverflowError):
                continue          # arithmetic accident, not a units question
            assert ground_dims(tree) == expected, tree
            seen_ok += 1
        assert seen_ok > 500 and seen_err > 100   # the control actually exercised both arms

    def test_floordiv_and_mod_follow_divmod_rules(self):
        from clausal.logic.units_clp import ground_dims
        assert ground_dims(_bin(FloorDiv, Quantity(7, M), Quantity(2, M))) == {}
        assert ground_dims(_bin(Mod, Quantity(7, M), Quantity(2, M))) == M
        with pytest.raises(LogicException) as ei:
            ground_dims(_bin(FloorDiv, Quantity(7, M), 2))
        _assert_system_error(ei, "units_mismatch")


class TestInference:
    def test_fresh_var_beside_metre_in_sub_is_metre(self):
        from clausal.logic.units_clp import analyse
        x, y = Var(), Var()
        dl, dr, env = analyse(x, _bin(Sub, Quantity(3, M), y), "(==)/2")
        assert dl == M and dr == M
        assert env[x._id] == M and env[y._id] == M

    def test_product_with_one_unknown_factor_defaults_the_factor(self):
        from clausal.logic.units_clp import analyse
        total, qty = Var(), Var()
        dl, dr, env = analyse(total, _bin(Mult, Quantity(Decimal("2.00"), {euro: 1}), qty), "(==)/2")
        assert env[total._id] == {euro: 1} and env[qty._id] == {}

    def test_ohms_law_infers_volt(self):
        from clausal.logic.units_clp import analyse
        v = Var()
        _, _, env = analyse(v, _bin(Mult, Quantity(2, {ampere: 1}), Quantity(3, ohm)), "(==)/2")
        assert env[v._id] == dict(volt._dims)

    def test_product_with_two_unknown_factors_is_undetermined(self):
        from clausal.logic.units_clp import analyse
        x, y, z = Var(), Var(), Var()
        put_attr(x, UNITS_KEY, UnitState(M), Trail())
        with pytest.raises(LogicException) as ei:
            analyse(x, _bin(Mult, y, z), "(==)/2")
        _assert_system_error(ei, "units_undetermined")

    def test_plain_number_beside_dimensioned_in_add_mismatches(self):
        from clausal.logic.units_clp import analyse
        with pytest.raises(LogicException) as ei:
            analyse(Var(), _bin(Add, Quantity(3, M), 1), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_mixed_currencies_mismatch_and_name_both(self):
        from clausal.logic.units_clp import analyse
        from clausal.modules.countries.united_states import usd
        with pytest.raises(LogicException) as ei:
            analyse(Var(), _bin(Add, Quantity(Decimal("1.00"), {euro: 1}), Quantity(Decimal("1.00"), {usd: 1})), "(==)/2")
        _assert_system_error(ei, "units_mismatch")
        assert "euro" in ei.value.term.args[1] and "dollar" in ei.value.term.args[1]

    def test_declared_units_var_disagreeing_with_operand_mismatches(self):
        from clausal.logic.units_clp import analyse
        x = Var()
        put_attr(x, UNITS_KEY, UnitState(S), Trail())
        with pytest.raises(LogicException) as ei:
            analyse(x, Quantity(3, M), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_solver_var_without_units_is_a_bare_number(self):
        from clausal.logic.units_clp import analyse
        from clausal.logic.clpfd import in_domain
        y = Var()
        assert in_domain(y, 1, 5, Trail())
        with pytest.raises(LogicException) as ei:
            analyse(Var(), _bin(Sub, Quantity(3, M), y), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_dimensionless_result_is_bare(self):
        from clausal.logic.units_clp import analyse
        r = Var()
        _, _, env = analyse(r, _bin(Div, Quantity(6, M), Quantity(3, M)), "(==)/2")
        assert env[r._id] == {}

    def test_no_material_is_not_engaged(self):
        from clausal.logic.units_clp import has_units_material
        assert not has_units_material(_bin(Add, Var(), 3))
        assert has_units_material(_bin(Add, Var(), Quantity(3, M)))

    def test_non_numeric_leaf_is_not_engaged(self):
        from clausal.logic.units_clp import has_units_material
        assert not has_units_material(_bin(Add, Quantity(3, M), "banana"))
