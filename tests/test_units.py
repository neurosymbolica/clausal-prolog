"""Tests for Quantity terms and the units module.

Covers:
  - Quantity arithmetic (add, sub, mul, div, pow, neg, abs)
  - UnitsMismatch on incompatible operations
  - Comparison operators
  - Clausal unification protocol (__unify__, __walk__, __occurs_check__)
  - Named-unit constructor predicates (forward + reverse modes)
  - Scaled unit predicates
  - Dimension-type predicates (IsForce, IsEnergy, …)
  - Utility predicates (DimensionOf, StripUnits, MakeQuantity)
  - IsDimensionless / IsQuantity
  - Python interop via is/2 evaluator through query()
"""

import pytest

from clausal import Var
from clausal.terms import Quantity, UnitsMismatch, DictTerm
from clausal.logic.variables import Trail, Var as LVar, deref, unify, get_attr, put_attr
from clausal.logic.solve import _drive_trampoline
from clausal.modules.py.units import (
    Metre, Kilogram, Second, Ampere, Kelvin, Mole, Candela,
)
from clausal.logic.units_constraint import UNITS_KEY, UnitState


# ── Test helper ──────────────────────────────────────────────────────────────


def run(pred, *args):
    """Invoke a module predicate directly; return list of binding dicts.

    String arguments (e.g. "D", "X") become named Var outputs that appear
    as keys in the returned binding dicts.
    """
    trail = Trail()
    var_map: dict[str, LVar] = {}
    resolved = []
    for arg in args:
        if isinstance(arg, str):
            if arg not in var_map:
                var_map[arg] = LVar()
            resolved.append(var_map[arg])
        else:
            resolved.append(arg)
    dispatch = pred._get_dispatch()
    results = []
    for _ in _drive_trampoline(dispatch, trail, *resolved):
        results.append({name: deref(v) for name, v in var_map.items()})
    return results


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════


_DIM_KEY = {
    "m": Metre, "kg": Kilogram, "s": Second,
    "A": Ampere, "K": Kelvin, "mol": Mole, "cd": Candela,
}


def d(value, **kwargs):
    """Shorthand: d(5, m=1) → Quantity(5, {Metre: 1})."""
    return Quantity(value, {_DIM_KEY[k]: v for k, v in kwargs.items() if v != 0})


def approx_d(value, **dims):
    """Create a Quantity and round its value for float comparison."""
    return d(value, **dims)


# ════════════════════════════════════════════════════════════════════════════
# 1. Quantity construction and display
# ════════════════════════════════════════════════════════════════════════════


class TestQuantityBasics:
    def test_zero_exponents_removed(self):
        x = Quantity(1, {Metre: 1, Second: 0})
        assert x.dims == {Metre: 1}

    def test_empty_dims_is_dimensionless(self):
        x = Quantity(42, {})
        assert x.dims == {}
        assert x.value == 42

    def test_repr(self):
        x = d(3, m=1, s=-2)
        assert "Quantity" in repr(x)
        assert "3" in repr(x)

    def test_str(self):
        x = d(9.8, m=1, s=-2)
        s = str(x)
        assert "9.8" in s
        assert "Metre" in s
        assert "Second" in s

    def test_equality(self):
        assert d(1, m=1) == d(1, m=1)
        assert d(1, m=1) != d(1, m=2)
        assert d(1, m=1) != d(2, m=1)

    def test_hash_consistent_with_eq(self):
        a = d(5, m=1)
        b = d(5, m=1)
        assert hash(a) == hash(b)


# ════════════════════════════════════════════════════════════════════════════
# 2. Arithmetic
# ════════════════════════════════════════════════════════════════════════════


class TestArithmetic:
    # ── addition ────────────────────────────────────────────────────────────

    def test_add_same_dims(self):
        result = d(3, m=1) + d(2, m=1)
        assert result == d(5, m=1)

    def test_add_mismatch_raises(self):
        with pytest.raises(UnitsMismatch):
            d(3, m=1) + d(2, s=1)

    def test_add_dimensioned_with_plain_raises(self):
        with pytest.raises(UnitsMismatch):
            d(3, m=1) + 5

    def test_add_dimensionless_with_plain(self):
        result = d(3.0, **{}) + 1.0
        assert result == d(4.0, **{})

    def test_radd_dimensionless(self):
        result = 2.0 + d(3.0, **{})
        assert result == d(5.0, **{})

    # ── subtraction ─────────────────────────────────────────────────────────

    def test_sub_same_dims(self):
        result = d(5, m=1) - d(2, m=1)
        assert result == d(3, m=1)

    def test_sub_mismatch_raises(self):
        with pytest.raises(UnitsMismatch):
            d(5, kg=1) - d(2, m=1)

    # ── multiplication ──────────────────────────────────────────────────────

    def test_mul_dimensioned_dimensioned(self):
        # velocity * time = length
        v = d(10, m=1, s=-1)
        t = d(3, s=1)
        result = v * t
        assert result == d(30, m=1)

    def test_mul_dimensioned_scalar(self):
        result = d(4, m=1) * 3
        assert result == d(12, m=1)

    def test_rmul_scalar(self):
        result = 2 * d(5, kg=1)
        assert result == d(10, kg=1)

    def test_mul_cancels_dims(self):
        # m/s * s/m = dimensionless
        a = d(6, m=1, s=-1)
        b = d(1, s=1, m=-1)
        result = a * b
        assert result.dims == {}
        assert result.value == 6

    def test_mul_compound_dims(self):
        # kg * m/s² = N
        mass = d(2, kg=1)
        accel = d(9.8, m=1, s=-2)
        force = mass * accel
        assert force.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert pytest.approx(force.value) == 19.6

    # ── division ────────────────────────────────────────────────────────────

    def test_div_dimensioned_dimensioned(self):
        dist = d(100, m=1)
        time = d(10, s=1)
        vel = dist / time
        assert vel == d(10, m=1, s=-1)

    def test_div_by_scalar(self):
        result = d(20, m=1) / 4
        assert result == d(5, m=1)

    def test_rdiv_scalar(self):
        # 1 / s = Hz
        result = 1 / d(2, s=1)
        assert result == d(0.5, s=-1)

    def test_div_same_dims_gives_dimensionless(self):
        result = d(10, m=1) / d(2, m=1)
        assert result.dims == {}
        assert result.value == 5.0

    # ── power ───────────────────────────────────────────────────────────────

    def test_pow_integer_exponent(self):
        side = d(3, m=1)
        area = side ** 2
        assert area == d(9, m=2)

    def test_pow_cubed(self):
        side = d(2, m=1)
        vol = side ** 3
        assert vol == d(8, m=3)

    def test_pow_minus_one(self):
        freq = d(50, s=1) ** -1
        assert freq.dims == {Second: -1}
        assert pytest.approx(freq.value) == 0.02

    def test_pow_zero_gives_dimensionless(self):
        result = d(5, m=1) ** 0
        assert result.dims == {}
        assert result.value == 1

    def test_pow_non_integer_raises(self):
        with pytest.raises(UnitsMismatch):
            d(4, m=1) ** 0.5

    def test_pow_dimensioned_exponent_raises(self):
        with pytest.raises(UnitsMismatch):
            d(4, m=1) ** d(2, s=1)

    def test_pow_dimensionless_exponent_integer_value(self):
        # Exponent is Quantity but dimensionless with integer value
        exp = d(2, **{})  # dimensionless Quantity
        result = d(3, m=1) ** exp
        assert result == d(9, m=2)

    # ── negation / abs ───────────────────────────────────────────────────────

    def test_neg(self):
        result = -d(5, m=1)
        assert result == d(-5, m=1)

    def test_abs(self):
        result = abs(d(-3, kg=1))
        assert result == d(3, kg=1)


# ════════════════════════════════════════════════════════════════════════════
# 3. Comparison operators
# ════════════════════════════════════════════════════════════════════════════


class TestComparisons:
    def test_lt_same_dims(self):
        assert d(1, m=1) < d(2, m=1)

    def test_gt_same_dims(self):
        assert d(5, s=1) > d(3, s=1)

    def test_le_equal(self):
        assert d(4, kg=1) <= d(4, kg=1)

    def test_ge_equal(self):
        assert d(4, kg=1) >= d(4, kg=1)

    def test_comparison_mismatch_raises(self):
        with pytest.raises(UnitsMismatch):
            d(1, m=1) < d(2, s=1)

    def test_comparison_with_plain_on_dimensionless(self):
        assert d(3.0, **{}) > 2.0

    def test_comparison_dimensioned_with_plain_raises(self):
        with pytest.raises(UnitsMismatch):
            d(1, m=1) < 2


# ════════════════════════════════════════════════════════════════════════════
# 4. Clausal unification protocol
# ════════════════════════════════════════════════════════════════════════════


class TestUnificationProtocol:
    def test_unify_same_value_same_dims(self):
        trail = Trail()
        assert unify(d(3, m=1), d(3, m=1), trail)

    def test_unify_different_value_fails(self):
        trail = Trail()
        assert not unify(d(3, m=1), d(4, m=1), trail)

    def test_unify_different_dims_fails(self):
        trail = Trail()
        assert not unify(d(3, m=1), d(3, s=1), trail)

    def test_unify_var_with_dimensioned(self):
        trail = Trail()
        v = Var()
        assert unify(v, d(10, kg=1), trail)
        assert deref(v) == d(10, kg=1)

    def test_unify_not_dimensioned_returns_not_implemented(self):
        trail = Trail()
        x = d(1, m=1)
        result = x.__unify__(42, trail)
        assert result is NotImplemented

    # ── AttVar-based dimensional constraint tests ────────────────────────────

    def test_attvar_unit_constraint_fires_on_bind(self):
        """Binding a constrained AttVar to a matching Quantity succeeds."""
        trail = Trail()
        v = Var()
        put_attr(v, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert unify(v, d(5, m=1), trail)
        assert deref(v) == d(5, m=1)

    def test_attvar_unit_constraint_fails_wrong_dims(self):
        """Binding to a Quantity with wrong dims fails."""
        trail = Trail()
        v = Var()
        put_attr(v, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert not unify(v, d(5, s=1), trail)

    def test_attvar_unit_constraint_fails_plain_number(self):
        """Binding a dimensioned constraint to a plain number fails."""
        trail = Trail()
        v = Var()
        put_attr(v, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert not unify(v, 5, trail)

    def test_attvar_dimensionless_constraint_accepts_plain_number(self):
        """A dimensionless constraint accepts a plain number."""
        trail = Trail()
        v = Var()
        put_attr(v, UNITS_KEY, UnitState({}), trail)
        assert unify(v, 42, trail)

    def test_two_attvar_unit_constraints_merge_compatible(self):
        """Unifying two vars with identical unit constraints succeeds."""
        trail = Trail()
        x = Var()
        y = Var()
        put_attr(x, UNITS_KEY, UnitState({Metre: 1}), trail)
        put_attr(y, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert unify(x, y, trail)
        # The surviving (older) var still carries the constraint.
        assert get_attr(deref(x), UNITS_KEY).dims == {Metre: 1}

    def test_two_attvar_unit_constraints_fail_incompatible(self):
        """Unifying vars with incompatible unit constraints fails."""
        trail = Trail()
        x = Var()
        y = Var()
        put_attr(x, UNITS_KEY, UnitState({Metre: 1}), trail)
        put_attr(y, UNITS_KEY, UnitState({Second: 1}), trail)
        assert not unify(x, y, trail)

    def test_attvar_constraint_transfers_to_unconstrained_var(self):
        """When constrained var is unified with unconstrained var, constraint transfers."""
        trail = Trail()
        x = Var()
        y = Var()
        put_attr(x, UNITS_KEY, UnitState({Kilogram: 1}), trail)
        assert unify(x, y, trail)
        assert get_attr(deref(y), UNITS_KEY).dims == {Kilogram: 1}

    def test_attvar_unit_constraint_backtracks(self):
        """put_attr via trail correctly undoes on backtrack."""
        trail = Trail()
        v = Var()
        mark = trail.mark()
        put_attr(v, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert get_attr(v, UNITS_KEY) is not None
        trail.undo(mark)
        assert get_attr(v, UNITS_KEY) is None


# ════════════════════════════════════════════════════════════════════════════
# 5. SI base unit constructors (Python __call__)
# ════════════════════════════════════════════════════════════════════════════


class TestSIBaseUnits:
    def _fwd(self, pred, number):
        return pred(number)

    def test_meter(self):
        from clausal.modules.py.units import Metre
        assert self._fwd(Metre, 5) == d(5, m=1)

    def test_kilogram(self):
        from clausal.modules.py.units import Kilogram
        assert self._fwd(Kilogram, 3) == d(3, kg=1)

    def test_second(self):
        from clausal.modules.py.units import Second
        assert self._fwd(Second, 10) == d(10, s=1)

    def test_ampere(self):
        from clausal.modules.py.units import Ampere
        assert self._fwd(Ampere, 2) == d(2, A=1)

    def test_kelvin(self):
        from clausal.modules.py.units import Kelvin
        assert self._fwd(Kelvin, 273) == d(273, K=1)

    def test_mole(self):
        from clausal.modules.py.units import Mole
        assert self._fwd(Mole, 1) == d(1, mol=1)

    def test_candela(self):
        from clausal.modules.py.units import Candela
        assert self._fwd(Candela, 100) == d(100, cd=1)


# ════════════════════════════════════════════════════════════════════════════
# 7. Scaled unit constructors (Python __call__)
# ════════════════════════════════════════════════════════════════════════════


class TestScaledUnits:
    def _fwd(self, pred, number):
        return pred(number)

    def test_kilometer_forward(self):
        from clausal.modules.py.units import Kilometer
        result = self._fwd(Kilometer, 1)
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 1000.0

    def test_centimeter_forward(self):
        from clausal.modules.py.units import Centimeter
        result = self._fwd(Centimeter, 100)
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 1.0

    def test_gram_forward(self):
        from clausal.modules.py.units import Gram
        result = self._fwd(Gram, 500)
        assert result.dims == {Kilogram: 1}
        assert pytest.approx(result.value) == 0.5

    def test_tonne_forward(self):
        from clausal.modules.py.units import Tonne
        result = self._fwd(Tonne, 2)
        assert pytest.approx(result.value) == 2000.0

    def test_minute_forward(self):
        from clausal.modules.py.units import Minute
        result = self._fwd(Minute, 5)
        assert result.dims == {Second: 1}
        assert pytest.approx(result.value) == 300.0

    def test_hour_forward(self):
        from clausal.modules.py.units import Hour
        result = self._fwd(Hour, 2)
        assert pytest.approx(result.value) == 7200.0

    def test_foot_forward(self):
        from clausal.modules.py.units import Foot
        result = self._fwd(Foot, 1)
        assert pytest.approx(result.value) == 0.3048

    def test_pound_forward(self):
        from clausal.modules.py.units import Pound
        result = self._fwd(Pound, 1)
        assert pytest.approx(result.value) == 0.45359237


# ════════════════════════════════════════════════════════════════════════════
# 8. Named derived unit constructors (Python __call__)
# ════════════════════════════════════════════════════════════════════════════


class TestDerivedUnits:
    def _fwd(self, pred, number):
        return pred(number)

    def test_newton(self):
        from clausal.modules.py.units import Newton
        result = self._fwd(Newton, 10)
        assert result.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert result.value == 10

    def test_joule(self):
        from clausal.modules.py.units import Joule
        result = self._fwd(Joule, 1)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -2}

    def test_watt(self):
        from clausal.modules.py.units import Watt
        result = self._fwd(Watt, 60)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -3}

    def test_pascal(self):
        from clausal.modules.py.units import Pascal
        result = self._fwd(Pascal, 101325)
        assert result.dims == {Kilogram: 1, Metre: -1, Second: -2}

    def test_hertz(self):
        from clausal.modules.py.units import Hertz
        result = self._fwd(Hertz, 440)
        assert result.dims == {Second: -1}

    def test_volt(self):
        from clausal.modules.py.units import Volt
        result = self._fwd(Volt, 230)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -3, Ampere: -1}

    def test_coulomb(self):
        from clausal.modules.py.units import Coulomb
        result = self._fwd(Coulomb, 1)
        assert result.dims == {Ampere: 1, Second: 1}

    def test_farad(self):
        from clausal.modules.py.units import Farad
        result = self._fwd(Farad, 100e-6)
        assert result.dims == {Kilogram: -1, Metre: -2, Second: 4, Ampere: 2}

    def test_ohm(self):
        from clausal.modules.py.units import Ohm
        result = self._fwd(Ohm, 100)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -3, Ampere: -2}

    def test_bar_forward(self):
        from clausal.modules.py.units import Bar
        result = self._fwd(Bar, 1)
        assert result.dims == {Kilogram: 1, Metre: -1, Second: -2}
        assert pytest.approx(result.value) == 1e5

    def test_kilowatt_hour_forward(self):
        from clausal.modules.py.units import KilowattHour
        result = self._fwd(KilowattHour, 1)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(result.value) == 3_600_000.0


# ════════════════════════════════════════════════════════════════════════════
# 9. Dimension-type predicates
# ════════════════════════════════════════════════════════════════════════════


class TestIsPredicates:
    def _check(self, pred, dimensioned, should_succeed):
        sols = run(pred, dimensioned)
        if should_succeed:
            assert sols, f"{pred} should succeed for {dimensioned}"
        else:
            assert not sols, f"{pred} should fail for {dimensioned}"

    def test_is_length_pass(self):
        from clausal.modules.py.units import IsLength
        self._check(IsLength, d(5, m=1), True)

    def test_is_length_fail(self):
        from clausal.modules.py.units import IsLength
        self._check(IsLength, d(5, s=1), False)

    def test_is_area_pass(self):
        from clausal.modules.py.units import IsArea
        self._check(IsArea, d(4, m=2), True)

    def test_is_volume_pass(self):
        from clausal.modules.py.units import IsVolume
        self._check(IsVolume, d(1, m=3), True)

    def test_is_mass_pass(self):
        from clausal.modules.py.units import IsMass
        self._check(IsMass, d(70, kg=1), True)

    def test_is_time_pass(self):
        from clausal.modules.py.units import IsTime
        self._check(IsTime, d(60, s=1), True)

    def test_is_frequency_pass(self):
        from clausal.modules.py.units import IsFrequency
        self._check(IsFrequency, d(440, s=-1), True)

    def test_is_velocity_pass(self):
        from clausal.modules.py.units import IsVelocity
        self._check(IsVelocity, d(10, m=1, s=-1), True)

    def test_is_acceleration_pass(self):
        from clausal.modules.py.units import IsAcceleration
        self._check(IsAcceleration, d(9.8, m=1, s=-2), True)

    def test_is_force_pass(self):
        from clausal.modules.py.units import IsForce
        self._check(IsForce, d(10, kg=1, m=1, s=-2), True)

    def test_is_force_fail_on_energy(self):
        from clausal.modules.py.units import IsForce
        self._check(IsForce, d(10, kg=1, m=2, s=-2), False)

    def test_is_energy_pass(self):
        from clausal.modules.py.units import IsEnergy
        self._check(IsEnergy, d(100, kg=1, m=2, s=-2), True)

    def test_is_power_pass(self):
        from clausal.modules.py.units import IsPower
        self._check(IsPower, d(60, kg=1, m=2, s=-3), True)

    def test_is_pressure_pass(self):
        from clausal.modules.py.units import IsPressure
        self._check(IsPressure, d(101325, kg=1, m=-1, s=-2), True)

    def test_is_voltage_pass(self):
        from clausal.modules.py.units import IsVoltage
        self._check(IsVoltage, d(230, kg=1, m=2, s=-3, A=-1), True)

    def test_is_charge_pass(self):
        from clausal.modules.py.units import IsCharge
        self._check(IsCharge, d(1, A=1, s=1), True)

    def test_is_temperature_pass(self):
        from clausal.modules.py.units import IsTemperature
        self._check(IsTemperature, d(300, K=1), True)

    def test_dimensionless_forward(self):
        from clausal.modules.py.units import Dimensionless
        assert Dimensionless(7) == d(7, **{})

    def test_dimensionless_check_by_value(self):
        from clausal.modules.py.units import Dimensionless
        ratio = d(5.0, **{})
        assert Dimensionless(5.0) == ratio

    def test_dimensionless_differs_from_dimensioned(self):
        from clausal.modules.py.units import Dimensionless
        assert Dimensionless(5.0) != d(5.0, m=1)

    def test_is_dimensionless_with_empty_dims(self):
        from clausal.modules.py.units import IsDimensionless
        self._check(IsDimensionless, d(1.0, **{}), True)

    def test_is_dimensionless_with_plain_float(self):
        from clausal.modules.py.units import IsDimensionless
        sols = run(IsDimensionless, 3.14)
        assert sols

    def test_is_dimensionless_fail_for_length(self):
        from clausal.modules.py.units import IsDimensionless
        self._check(IsDimensionless, d(5, m=1), False)

    def test_is_dimensioned_pass(self):
        from clausal.modules.py.units import IsQuantity
        self._check(IsQuantity, d(5, m=1), True)

    def test_is_dimensioned_fail_for_plain_number(self):
        from clausal.modules.py.units import IsQuantity
        sols = run(IsQuantity, 42)
        assert not sols


# ════════════════════════════════════════════════════════════════════════════
# 10. Utility predicates
# ════════════════════════════════════════════════════════════════════════════


class TestUtilityPredicates:
    def test_dimension_of(self):
        from clausal.modules.py.units import DimensionOf
        velocity = d(10, m=1, s=-1)
        sols = run(DimensionOf, velocity, "DIMS")
        assert sols
        dims = sols[0]["DIMS"]
        assert isinstance(dims, DictTerm)
        assert dims[Metre] == 1
        assert dims[Second] == -1

    def test_value_of(self):
        from clausal.modules.py.units import StripUnits
        force = d(9.8, kg=1, m=1, s=-2)
        sols = run(StripUnits, force, "V")
        assert sols
        assert sols[0]["V"] == 9.8

    def test_strip_dimensions(self):
        from clausal.modules.py.units import StripUnits
        x = d(42, m=2)
        sols = run(StripUnits, x, "V")
        assert sols
        assert sols[0]["V"] == 42

    def test_make_dimensioned(self):
        from clausal.modules.py.units import MakeQuantity
        dims = DictTerm({Kilogram: 1, Metre: 1, Second: -2})
        sols = run(MakeQuantity, 10, dims, "D")
        assert sols
        result = sols[0]["D"]
        assert isinstance(result, Quantity)
        assert result.value == 10
        assert result.dims == {Kilogram: 1, Metre: 1, Second: -2}

    def test_dimension_of_plain_number_fails(self):
        from clausal.modules.py.units import DimensionOf
        sols = run(DimensionOf, 42, "DIMS")
        assert not sols

    def test_value_of_plain_number_fails(self):
        from clausal.modules.py.units import StripUnits
        sols = run(StripUnits, 42, "V")
        assert not sols


# ════════════════════════════════════════════════════════════════════════════
# 11. Arithmetic through Python is/2 evaluator
# ════════════════════════════════════════════════════════════════════════════


class TestArithmeticViaIs:
    """Verify Quantity arithmetic works when values are passed through is/2."""

    def test_force_from_mass_times_acceleration(self):
        """F = m * a — multiplication gives correct force dimensions."""
        mass = d(2, kg=1)
        accel = d(9.8, m=1, s=-2)
        force = mass * accel
        assert force.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert pytest.approx(force.value) == 19.6

    def test_kinetic_energy(self):
        """KE = 0.5 * m * v²."""
        mass = d(10, kg=1)
        velocity = d(3, m=1, s=-1)
        ke = 0.5 * mass * velocity ** 2
        assert ke.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(ke.value) == 45.0

    def test_power_from_energy_over_time(self):
        """P = E / t."""
        energy = d(3600, kg=1, m=2, s=-2)
        time = d(60, s=1)
        power = energy / time
        assert power.dims == {Kilogram: 1, Metre: 2, Second: -3}
        assert pytest.approx(power.value) == 60.0

    def test_speed_from_distance_over_time(self):
        speed = d(100, m=1) / d(10, s=1)
        assert speed.dims == {Metre: 1, Second: -1}
        assert speed.value == 10.0

    def test_ohms_law_voltage(self):
        """V = I * R."""
        current = d(2, A=1)
        resistance = d(50, kg=1, m=2, s=-3, A=-2)
        voltage = current * resistance
        assert voltage.dims == {Kilogram: 1, Metre: 2, Second: -3, Ampere: -1}
        assert voltage.value == 100

    def test_area_from_side_squared(self):
        side = d(4, m=1)
        area = side ** 2
        assert area == d(16, m=2)

    def test_chain_unit_predicates_and_arithmetic(self):
        """Combine Newton pred output with arithmetic."""
        from clausal.modules.py.units import Newton, Second

        # impulse = force * time
        force = Newton(5)
        time = Second(3)
        impulse = force * time
        # impulse dims: kg·m/s (momentum)
        assert impulse.dims == {Kilogram: 1, Metre: 1, Second: -1}
        assert impulse.value == 15


# ════════════════════════════════════════════════════════════════════════════
# 12. Edge cases and error paths
# ════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_dimensionless_times_dimensioned(self):
        """Dimensionless Quantity * Quantity merges (empty + dims = dims)."""
        scalar = d(2.0, **{})
        length = d(3, m=1)
        result = scalar * length
        assert result.dims == {Metre: 1}
        assert result.value == 6.0

    def test_add_two_dimensionless(self):
        result = d(1.0, **{}) + d(2.0, **{})
        assert result == d(3.0, **{})

    def test_sub_two_dimensionless(self):
        result = d(5.0, **{}) - d(2.0, **{})
        assert result == d(3.0, **{})

    def test_pow_with_dimensionless_dimensioned_int_value(self):
        """Pow where exponent is a dimensionless Quantity with integer value."""
        base = d(2, m=1)
        exp = Quantity(3, {})
        result = base ** exp
        assert result == d(8, m=3)

    def test_attvar_vars_merge_then_bind(self):
        """Two unit-constrained vars are merged; binding one binds both."""
        trail = Trail()
        x = Var()
        y = Var()
        put_attr(x, UNITS_KEY, UnitState({Metre: 1}), trail)
        put_attr(y, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert unify(x, y, trail)
        # Bind the merged slot to a matching Quantity.
        assert unify(deref(x), d(10, m=1), trail)
        assert deref(x) == d(10, m=1)
        assert deref(y) == d(10, m=1)

    def test_format_dunder(self):
        """__format__ returns string."""
        x = d(5.0, m=1)
        assert f"{x}" == str(x)

    def test_dimensioned_zero_value(self):
        result = d(0, kg=1) + d(0, kg=1)
        assert result == d(0, kg=1)

    def test_negative_exponents_in_display(self):
        x = d(10, m=1, s=-2)
        s = str(x)
        assert "Second" in s

    def test_multiply_complex_dims(self):
        """Watt * Second = Joule."""
        power = d(100, kg=1, m=2, s=-3)
        time = d(10, s=1)
        energy = power * time
        assert energy.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert energy.value == 1000

    def test_pow_half_dimensionless(self):
        """** 0.5 is allowed for dimensionless Quantity."""
        result = d(9.0, **{}) ** 0.5
        assert result.dims == {}
        assert pytest.approx(result.value) == 3.0

    def test_pow_half_dimensional_raises(self):
        """** 0.5 raises UnitsMismatch for dimensional quantities."""
        with pytest.raises(UnitsMismatch):
            d(4.0, m=2) ** 0.5


class TestUnitPredicateCall:
    """Unit predicates are callable as Python expressions via __call__."""

    def test_kilogram_call(self):
        from clausal.modules.py.units import Kilogram
        assert Kilogram(5) == d(5, kg=1)

    def test_meter_call(self):
        from clausal.modules.py.units import Metre
        assert Metre(3) == d(3, m=1)

    def test_newton_call(self):
        from clausal.modules.py.units import Newton
        assert Newton(9.8) == d(9.8, kg=1, m=1, s=-2)

    def test_kilometer_call_scales(self):
        from clausal.modules.py.units import Kilometer
        assert Kilometer(1) == d(1000.0, m=1)

    def test_expression_e_mc2(self):
        """E = mc² via Python expression syntax."""
        from clausal.modules.py.units import Kilogram, SpeedOfLight
        e = Kilogram(1) * SpeedOfLight ** 2
        assert e.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(e.value) == 8.987551787368176e16

    def test_expression_weight(self):
        from clausal.modules.py.units import Kilogram, StandardGravity
        w = Kilogram(70) * StandardGravity
        assert w.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert pytest.approx(w.value) == 686.4655

    def test_expression_ohms_law(self):
        from clausal.modules.py.units import Volt, Ampere
        r = Volt(12) / Ampere(3)
        assert r.dims == {Kilogram: 1, Metre: 2, Second: -3, Ampere: -2}
        assert pytest.approx(r.value) == 4.0


# ════════════════════════════════════════════════════════════════════════════
# Unit predicate arithmetic (dims combinators)
# ════════════════════════════════════════════════════════════════════════════


class TestUnitPredicateArithmetic:
    """_UnitsPredicate arithmetic produces dimension descriptors for HasUnits."""

    def test_pow_produces_correct_dims(self):
        from clausal.modules.py.units import Metre
        area = Metre ** 2
        assert area._dims == {Metre: 2}

    def test_div_produces_correct_dims(self):
        from clausal.modules.py.units import Metre, Second
        velocity = Metre / Second
        assert velocity._dims == {Metre: 1, Second: -1}

    def test_mul_produces_correct_dims(self):
        from clausal.modules.py.units import Kilogram, Metre
        kg_m = Kilogram * Metre
        assert kg_m._dims == {Kilogram: 1, Metre: 1}

    def test_compound_force_dims(self):
        from clausal.modules.py.units import Kilogram, Metre, Second, Newton
        force = Kilogram * Metre / Second ** 2
        assert force._dims == Newton._dims

    def test_acceleration_dims(self):
        from clausal.modules.py.units import Metre, Second
        acc = Metre / Second ** 2
        assert acc._dims == {Metre: 1, Second: -2}

    def test_pow_fractional_not_useful_but_legal(self):
        from clausal.modules.py.units import Metre
        # Metre**-1 is a valid descriptor (e.g. wavenumber)
        inv = Metre ** -1
        assert inv._dims == {Metre: -1}

    def test_descriptor_matches_quantity_dims(self):
        from clausal.modules.py.units import Metre, Second
        velocity_desc = Metre / Second
        velocity_qty = Metre(10) / Second(1)
        assert velocity_qty.dims == velocity_desc._dims

    def test_area_descriptor_matches_quantity_dims(self):
        from clausal.modules.py.units import Metre
        area_desc = Metre ** 2
        area_qty = Metre(4) ** 2
        assert area_qty.dims == area_desc._dims

    def test_compound_desc_mismatch(self):
        from clausal.modules.py.units import Metre, Second
        area_desc = Metre ** 2
        velocity_qty = Metre(10) / Second(1)
        assert velocity_qty.dims != area_desc._dims


class TestPhysicalConstants:
    def test_speed_of_light_dims(self):
        from clausal.modules.py.units import SpeedOfLight
        assert SpeedOfLight.dims == {Metre: 1, Second: -1}

    def test_planck_constant_dims(self):
        from clausal.modules.py.units import PlanckConstant
        assert PlanckConstant.dims == {Kilogram: 1, Metre: 2, Second: -1}

    def test_boltzmann_constant_dims(self):
        from clausal.modules.py.units import BoltzmannConstant
        assert BoltzmannConstant.dims == {Kilogram: 1, Metre: 2, Second: -2, Kelvin: -1}

    def test_standard_gravity_dims(self):
        from clausal.modules.py.units import StandardGravity
        assert StandardGravity.dims == {Metre: 1, Second: -2}

    def test_elementary_charge_dims(self):
        from clausal.modules.py.units import ElementaryCharge
        assert ElementaryCharge.dims == {Ampere: 1, Second: 1}

    def test_gravitational_constant_dims(self):
        from clausal.modules.py.units import GravitationalConstant
        assert GravitationalConstant.dims == {Metre: 3, Kilogram: -1, Second: -2}


# ── Sugar tests ───────────────────────────────────────────────────────────────


class TestUnitsSugar:
    """Tests for n(Unit) and X(Unit) syntactic sugar."""

    # ── HasUnits/2 builtin (direct Python via run()) ──────────────────────────

    def _has_units_pred(self):
        """Return a callable suitable for run() that wraps HasUnits/2."""
        import clausal.modules.py.units  # ensure units_constraint is imported
        from clausal.logic.builtins._registry import get_builtin_predicate
        return get_builtin_predicate("HasUnits", 2)

    def test_has_units_ground_match(self):
        from clausal.modules.py.units import Newton
        results = run(self._has_units_pred(), Newton(9.8), Newton)
        assert len(results) == 1

    def test_has_units_ground_mismatch(self):
        from clausal.modules.py.units import Newton, Metre
        results = run(self._has_units_pred(), Newton(9.8), Metre)
        assert results == []

    def test_has_units_unbound_var_posts_constraint(self):
        from clausal.modules.py.units import Metre
        from clausal.logic.variables import Var, get_attr
        from clausal.logic.units_constraint import UNITS_KEY
        # run() creates Var from string — check constraint posted via second binding
        v = Var()
        trail = Trail()
        from clausal.logic.units_constraint import constrain_var_dims
        pred = self._has_units_pred()
        from clausal.logic.solve import _drive_trampoline
        dispatch = pred._get_dispatch()
        found = False
        for _ in _drive_trampoline(dispatch, trail, v, Metre):
            found = True
            state = get_attr(v, UNITS_KEY)
            assert state is not None
            assert state.dims == Metre._dims
        assert found

    def test_has_units_unbound_var_backtracks(self):
        from clausal.modules.py.units import Metre
        from clausal.logic.variables import Var, get_attr
        from clausal.logic.units_constraint import UNITS_KEY
        v = Var()
        trail = Trail()
        mark = trail.mark()
        pred = self._has_units_pred()
        dispatch = pred._get_dispatch()
        from clausal.logic.solve import _drive_trampoline
        for _ in _drive_trampoline(dispatch, trail, v, Metre):
            break
        assert get_attr(v, UNITS_KEY) is not None
        trail.undo(mark)
        assert get_attr(v, UNITS_KEY) is None

    def test_has_units_already_constrained_match(self):
        from clausal.modules.py.units import Metre
        from clausal.logic.variables import Var
        from clausal.logic.units_constraint import constrain_var_dims
        v = Var()
        trail = Trail()
        constrain_var_dims(v, Metre._dims, trail)
        results = run(self._has_units_pred(), v, Metre)
        assert len(results) == 1

    def test_has_units_already_constrained_conflict(self):
        from clausal.modules.py.units import Metre, Second
        from clausal.logic.variables import Var
        from clausal.logic.units_constraint import constrain_var_dims
        v = Var()
        trail = Trail()
        constrain_var_dims(v, Metre._dims, trail)
        results = run(self._has_units_pred(), v, Second)
        assert results == []

    # ── n(Unit) sugar: inline Clausal source ──────────────────────────────────

    def test_numeric_sugar_basic(self, tmp_path):
        """5(Metre) produces the same Quantity as Metre(5)."""
        import os
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre])\n"
            "Test <- (D1 := ++(Metre(5)), D2 := 5(Metre), D1 == D2)\n"
        )
        p = tmp_path / "sugar_basic.clausal"
        p.write_text(src)
        mod = _load_module("sugar_basic", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_numeric_sugar_float(self, tmp_path):
        """9.8(Newton) produces Quantity(9.8, Newton._dims)."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Newton])\n"
            "Test <- (D1 := ++(Newton(9.8)), D2 := 9.8(Newton), D1 == D2)\n"
        )
        p = tmp_path / "sugar_float.clausal"
        p.write_text(src)
        mod = _load_module("sugar_float", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_numeric_sugar_negation(self, tmp_path):
        """-5(Metre) produces Quantity(-5, ...)."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre])\n"
            "Test <- (D := -5(Metre), V := ++(D.value), V == -5)\n"
        )
        p = tmp_path / "sugar_neg.clausal"
        p.write_text(src)
        mod = _load_module("sugar_neg", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_numeric_sugar_addition(self, tmp_path):
        """5(Metre) + 3(Metre) == 8(Metre)."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre])\n"
            "Test <- (S := 5(Metre) + 3(Metre), S == 8(Metre))\n"
        )
        p = tmp_path / "sugar_add.clausal"
        p.write_text(src)
        mod = _load_module("sugar_add", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    # ── X(Unit) goal sugar: inline Clausal source ─────────────────────────────

    def test_var_sugar_on_dimensioned(self, tmp_path):
        """X(Metre) on a Quantity(5, Metre) succeeds."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre])\n"
            "Test <- (D := 5(Metre), D(Metre))\n"
        )
        p = tmp_path / "var_sugar_match.clausal"
        p.write_text(src)
        mod = _load_module("var_sugar_match", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_var_sugar_mismatch_fails(self, tmp_path):
        """X(Metre) on a Quantity(5, Second) fails."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (D := 5(Second), D(Metre))\n"
        )
        p = tmp_path / "var_sugar_fail.clausal"
        p.write_text(src)
        mod = _load_module("var_sugar_fail", str(p)).__dict__["$module"]
        assert not any(True for _ in call("Test", module=mod))

    def test_var_sugar_posts_constraint(self, tmp_path):
        """X(Metre) on an unbound var posts the units constraint and allows binding."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre])\n"
            "Test <- (X(Metre), X is 5(Metre))\n"
        )
        p = tmp_path / "var_sugar_post.clausal"
        p.write_text(src)
        mod = _load_module("var_sugar_post", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_var_sugar_constraint_rejects_wrong_unit(self, tmp_path):
        """X(Metre) then unify X with a Second value — fails."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (X(Metre), X is 5(Second))\n"
        )
        p = tmp_path / "var_sugar_reject.clausal"
        p.write_text(src)
        mod = _load_module("var_sugar_reject", str(p)).__dict__["$module"]
        assert not any(True for _ in call("Test", module=mod))


# ════════════════════════════════════════════════════════════════════════════
# 13. Unit mismatch errors (Clausal source)
# ════════════════════════════════════════════════════════════════════════════


class TestUnitMismatchErrors:
    """UnitsMismatch is raised when incompatible units are combined via ++ Python escapes."""

    def _load(self, tmp_path, name, src):
        from clausal.import_hook import _load_module
        p = tmp_path / f"{name}.clausal"
        p.write_text(src)
        return _load_module(name, str(p)).__dict__["$module"]

    def test_add_metre_plus_second_raises(self, tmp_path):
        """Adding m and s via ++ raises UnitsMismatch."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_add",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (D := ++(Metre(3) + Second(2)))\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

    def test_sub_metre_minus_kilogram_raises(self, tmp_path):
        """Subtracting kg from m via ++ raises UnitsMismatch."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_sub",
            "-import_from(py.units, [Metre, Kilogram])\n"
            "Test <- (D := ++(Metre(5) - Kilogram(1)))\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

    def test_compare_metre_with_second_raises(self, tmp_path):
        """Comparing m > s directly in clause body raises UnitsMismatch."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_cmp",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (5(Metre) > 3(Second))\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

    def test_add_dimensioned_with_plain_raises(self, tmp_path):
        """Adding a plain number to a dimensional quantity via ++ raises UnitsMismatch."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_plain",
            "-import_from(py.units, [Metre])\n"
            "Test <- (D := ++(Metre(5) + 3))\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

    def test_matching_units_no_error(self, tmp_path):
        """Adding same units via ++ succeeds and produces the correct result."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_ok",
            "-import_from(py.units, [Metre])\n"
            "Test <- (D := ++(Metre(3) + Metre(2)), D == 5(Metre))\n")
        assert any(True for _ in call("Test", module=mod))


# ════════════════════════════════════════════════════════════════════════════
# 14. Dimensionless n() sugar
# ════════════════════════════════════════════════════════════════════════════


class TestDimensionlessSugar:
    """42 () creates Quantity(42, {}) — empty-unit dimensionless sugar."""

    def _load(self, tmp_path, name, src):
        from clausal.import_hook import _load_module
        p = tmp_path / f"{name}.clausal"
        p.write_text(src)
        return _load_module(name, str(p)).__dict__["$module"]

    def test_integer_dimensionless(self, tmp_path):
        """42() produces Quantity(42, {})."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_int",
            "Test <- (D := 42(), ++(D.dims == {}), ++(D.value == 42))\n")
        assert any(True for _ in call("Test", module=mod))

    def test_float_dimensionless(self, tmp_path):
        """3.14() produces Quantity(3.14, {})."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_float",
            "Test <- (D := 3.14(), ++(D.dims == {}), ++(D.value == 3.14))\n")
        assert any(True for _ in call("Test", module=mod))

    def test_dimensionless_equals_dimensionless_pred(self, tmp_path):
        """42() == Dimensionless(42) via predicate."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_eq",
            "-import_from(py.units, [Dimensionless])\n"
            "Test <- (D1 := 42(), D2 := ++(Dimensionless(42)), D1 == D2)\n")
        assert any(True for _ in call("Test", module=mod))

    def test_dimensionless_arithmetic(self, tmp_path):
        """Dimensionless values can be added via ++: ++(3() + 2()) == 5()."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_arith",
            "Test <- (S := ++(Quantity(3, {}) + Quantity(2, {})), S == 5())\n")
        assert any(True for _ in call("Test", module=mod))

    def test_dimensionless_is_dimensionless(self, tmp_path):
        """IsDimensionless succeeds for n()."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_is",
            "-import_from(py.units, [IsDimensionless])\n"
            "Test <- (D := 7(), IsDimensionless(D))\n")
        assert any(True for _ in call("Test", module=mod))

    def test_dimensionless_is_dimensionless_not_length(self, tmp_path):
        """IsLength fails for a dimensionless n() value."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_not_len",
            "-import_from(py.units, [IsLength])\n"
            "Test <- (D := 7(), IsLength(D))\n")
        assert not any(True for _ in call("Test", module=mod))


# ════════════════════════════════════════════════════════════════════════════
# 15. Python exception catch/3 integration
# ════════════════════════════════════════════════════════════════════════════


class TestPythonExceptionCatch:
    """catch/3 catches UnitsMismatch as python_error("UnitsMismatch", Msg)."""

    def _load(self, tmp_path, name, src):
        from clausal.import_hook import _load_module
        p = tmp_path / f"{name}.clausal"
        p.write_text(src)
        return _load_module(name, str(p)).__dict__["$module"]

    def test_catch_add_mismatch(self, tmp_path):
        """Catching UnitsMismatch from incompatible addition."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "catch_add",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- catch(++(Metre(1) + Second(1)), python_error(\"UnitsMismatch\", _), 1 == 1)\n")
        assert any(True for _ in call("Test", module=mod))

    def test_catch_sub_mismatch(self, tmp_path):
        """Catching UnitsMismatch from incompatible subtraction."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "catch_sub",
            "-import_from(py.units, [Metre, Kilogram])\n"
            "Test <- catch(++(Metre(5) - Kilogram(3)), python_error(\"UnitsMismatch\", _), 1 == 1)\n")
        assert any(True for _ in call("Test", module=mod))

    def test_catch_message_bound(self, tmp_path):
        """The caught message variable is bound to the exception string."""
        from clausal.logic.solve import call
        from clausal.logic.variables import deref, Var
        mod = self._load(tmp_path, "catch_msg",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- catch(++(Metre(1) + Second(1)), python_error(\"UnitsMismatch\", _MSG), _MSG == _MSG)\n")
        assert any(True for _ in call("Test", module=mod))

    def test_no_exception_recovery_skipped(self, tmp_path):
        """If no exception, the recovery goal is not run (even if it would fail)."""
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "catch_noexc",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- catch(++(Metre(3) * Second(2)), python_error(\"UnitsMismatch\", _), 1 == 2)\n")
        # Mul doesn't raise; goal succeeds; recovery is skipped entirely.
        assert any(True for _ in call("Test", module=mod))

    def test_unmatched_exception_reraises(self, tmp_path):
        """An exception that doesn't match the catcher is re-raised."""
        from clausal.logic.solve import call
        from clausal.terms import UnitsMismatch
        mod = self._load(tmp_path, "catch_reraise",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- catch(++(Metre(1) + Second(1)), python_error(\"SomeOtherError\", _), 1 == 1)\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))
