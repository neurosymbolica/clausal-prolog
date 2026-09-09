from decimal import Decimal

import pytest

from clausal.terms import term_str, Compound, Quantity


class TestDecimalRendering:
    def test_bare_decimal_renders_plainly(self):
        assert term_str(Decimal("7.89")) == "7.89"

    def test_decimal_no_trailing_zeros_lost(self):
        # str(Decimal) preserves scale; repr would wrap it in Decimal('...').
        assert term_str(Decimal("7.90")) == "7.90"

    def test_decimal_nested_in_compound(self):
        s = term_str(Compound("price", (Decimal("1.50"),)))
        assert "1.50" in s
        assert "Decimal(" not in s


class TestDecimalArithmeticCoercion:
    def test_decimal_quantity_times_float_scalar(self):
        # Decimal * float would raise TypeError without coercion.
        q = Quantity(Decimal("100.00"), {})  # dimensionless
        r = q * 0.2
        assert isinstance(r.value, Decimal)
        assert r.value == Decimal("20.000")

    def test_float_scalar_times_decimal_quantity(self):
        q = Quantity(Decimal("100.00"), {})
        r = 0.2 * q
        assert r.value == Decimal("20.000")

    def test_decimal_quantity_divided_by_float(self):
        q = Quantity(Decimal("10.00"), {})
        r = q / 4.0
        assert r.value == Decimal("2.5")

    def test_decimal_quantity_divided_by_int_still_exact(self):
        q = Quantity(Decimal("10.00"), {})
        r = q / 4
        assert r.value == Decimal("2.5")

    def test_dimensionless_decimal_plus_float(self):
        q = Quantity(Decimal("1.50"), {})
        r = q + 0.25
        assert r.value == Decimal("1.75")

    def test_coercion_uses_str_not_binary_expansion(self):
        # The load-bearing rule: Decimal(str(0.2)) == 0.2, NOT Decimal(0.2).
        q = Quantity(Decimal("1"), {})
        r = q * 0.2
        assert r.value == Decimal("0.2")

    def test_mixed_value_quantities_same_dims_add(self):
        from clausal.modules.py.units import metre
        a = Quantity(Decimal("1.5"), {metre: 1})
        b = Quantity(0.25, {metre: 1})  # float-valued, same dims
        r = a + b
        assert r.value == Decimal("1.75")


class TestNoRegressionFloatQuantities:
    def test_float_quantity_arithmetic_unchanged(self):
        from clausal.modules.py.units import metre, second
        d = Quantity(20.0, {metre: 1})
        t = Quantity(2.0, {second: 1})
        v = d / t
        assert v.value == 10.0
        assert v.dims == {metre: 1, second: -1}

    def test_dimension_mismatch_still_raises(self):
        from clausal.terms import UnitsMismatch
        from clausal.modules.py.units import metre, second
        with pytest.raises(UnitsMismatch):
            _ = Quantity(1.0, {metre: 1}) + Quantity(1.0, {second: 1})

    def test_dimensioned_plus_plain_number_still_raises(self):
        from clausal.terms import UnitsMismatch
        from clausal.modules.py.units import metre
        with pytest.raises(UnitsMismatch):
            _ = Quantity(1.0, {metre: 1}) + 5


class TestDecimalScalarConsistency:
    def test_dimensionless_decimal_plus_bare_decimal(self):
        q = Quantity(Decimal("1.50"), {})
        assert (q + Decimal("0.25")).value == Decimal("1.75")

    def test_bare_decimal_plus_dimensionless_via_radd(self):
        q = Quantity(Decimal("1.50"), {})
        assert (Decimal("0.25") + q).value == Decimal("1.75")

    def test_dimensionless_decimal_minus_bare_decimal(self):
        q = Quantity(Decimal("1.50"), {})
        assert (q - Decimal("0.25")).value == Decimal("1.25")

    def test_bare_decimal_minus_dimensionless_via_rsub(self):
        q = Quantity(Decimal("0.50"), {})
        assert (Decimal("2.00") - q).value == Decimal("1.50")

    def test_dimensioned_plus_bare_decimal_still_raises(self):
        from clausal.terms import UnitsMismatch
        from clausal.modules.py.units import metre
        with pytest.raises(UnitsMismatch):
            _ = Quantity(Decimal("1"), {metre: 1}) + Decimal("1")

    def test_constructor_scaled_unit_with_decimal_magnitude(self):
        from clausal.modules.py.units import centimeter, metre
        q = Quantity(Decimal("5"), centimeter)  # centimeter == Quantity(1e-2, {metre:1})
        assert q.value == Decimal("0.05")
        assert q.dims == {metre: 1}
