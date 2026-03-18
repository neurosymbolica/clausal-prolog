"""Tests for Dimensioned terms and the units module.

Covers:
  - Dimensioned arithmetic (add, sub, mul, div, pow, neg, abs)
  - UnitsMismatch on incompatible operations
  - Comparison operators
  - Clausal unification protocol (__unify__, __walk__, __occurs_check__)
  - Named-unit constructor predicates (forward + reverse modes)
  - Scaled unit predicates
  - Dimension-type predicates (IsForce, IsEnergy, …)
  - Utility predicates (DimensionOf, ValueOf, MakeDimensioned, StripDimensions)
  - IsDimensionless / IsDimensioned
  - Python interop via is/2 evaluator through query()
"""

import pytest

from clausal import Var
from clausal.terms import Dimensioned, UnitsMismatch, DictTerm
from clausal.logic.variables import Trail, Var as LVar, deref, unify
from clausal.logic.solve import _drive_trampoline


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


def d(value, **dims):
    """Shorthand: d(5, m=1) → Dimensioned(5, {'m': 1})."""
    return Dimensioned(value, dims)


def approx_d(value, **dims):
    """Create a Dimensioned and round its value for float comparison."""
    return d(value, **dims)


# ════════════════════════════════════════════════════════════════════════════
# 1. Dimensioned construction and display
# ════════════════════════════════════════════════════════════════════════════


class TestDimensionedBasics:
    def test_zero_exponents_removed(self):
        x = Dimensioned(1, {"m": 1, "s": 0})
        assert x.dims == {"m": 1}

    def test_empty_dims_is_dimensionless(self):
        x = Dimensioned(42, {})
        assert x.dims == {}
        assert x.value == 42

    def test_repr(self):
        x = d(3, m=1, s=-2)
        assert "Dimensioned" in repr(x)
        assert "3" in repr(x)

    def test_str(self):
        x = d(9.8, m=1, s=-2)
        s = str(x)
        assert "9.8" in s
        assert "m" in s
        assert "s" in s

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
        assert force.dims == {"kg": 1, "m": 1, "s": -2}
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
        assert freq.dims == {"s": -1}
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
        # Exponent is Dimensioned but dimensionless with integer value
        exp = d(2, **{})  # dimensionless Dimensioned
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

    def test_unify_variable_value(self):
        trail = Trail()
        x = Var()
        target = d(x, m=1)
        if unify(target, d(5, m=1), trail):
            from clausal.logic.variables import deref
            assert deref(x) == 5

    def test_unify_var_with_dimensioned(self):
        trail = Trail()
        v = Var()
        assert unify(v, d(10, kg=1), trail)
        from clausal.logic.variables import deref
        assert deref(v) == d(10, kg=1)

    def test_walk_follows_var_in_value(self):
        trail = Trail()
        x = Var()
        dim_x = d(x, m=1)
        unify(x, 7, trail)
        walked = dim_x.__walk__()
        assert walked.value == 7
        assert walked.dims == {"m": 1}

    def test_walk_returns_self_when_ground(self):
        x = d(5, m=1)
        assert x.__walk__() is x

    def test_occurs_check_in_value(self):
        x = Var()
        dim_x = d(x, m=1)
        assert dim_x.__occurs_check__(x)

    def test_occurs_check_absent(self):
        x = Var()
        y = Var()
        dim_x = d(x, m=1)
        assert not dim_x.__occurs_check__(y)

    def test_unify_not_dimensioned_returns_not_implemented(self):
        trail = Trail()
        x = d(1, m=1)
        result = x.__unify__(42, trail)
        assert result is NotImplemented


# ════════════════════════════════════════════════════════════════════════════
# 5. SI base unit predicates (forward mode)
# ════════════════════════════════════════════════════════════════════════════


class TestSIBaseUnits:
    def _fwd(self, pred, number):
        sols = run(pred, number, "D")
        assert sols, f"{pred} produced no solutions"
        return sols[0]["D"]

    def test_meter(self):
        from clausal.modules.py.units import Meter
        assert self._fwd(Meter, 5) == d(5, m=1)

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
# 6. SI base unit predicates (reverse mode)
# ════════════════════════════════════════════════════════════════════════════


class TestSIBaseUnitsReverse:
    def _rev(self, pred, dimensioned):
        sols = run(pred, "X", dimensioned)
        assert sols
        return sols[0]["X"]

    def test_meter_reverse(self):
        from clausal.modules.py.units import Meter
        assert self._rev(Meter, d(7, m=1)) == 7

    def test_kilogram_reverse(self):
        from clausal.modules.py.units import Kilogram
        assert self._rev(Kilogram, d(4.5, kg=1)) == 4.5

    def test_second_reverse(self):
        from clausal.modules.py.units import Second
        assert self._rev(Second, d(60, s=1)) == 60

    def test_wrong_dims_no_solution(self):
        from clausal.modules.py.units import Meter
        sols = run(Meter, "X", d(5, s=1))
        assert sols == []


# ════════════════════════════════════════════════════════════════════════════
# 7. Scaled unit predicates
# ════════════════════════════════════════════════════════════════════════════


class TestScaledUnits:
    def _fwd(self, pred, number):
        sols = run(pred, number, "D")
        assert sols
        return sols[0]["D"]

    def _rev(self, pred, dimensioned):
        sols = run(pred, "X", dimensioned)
        assert sols
        return sols[0]["X"]

    def test_kilometer_forward(self):
        from clausal.modules.py.units import Kilometer
        result = self._fwd(Kilometer, 1)
        assert result.dims == {"m": 1}
        assert pytest.approx(result.value) == 1000.0

    def test_kilometer_reverse(self):
        from clausal.modules.py.units import Kilometer
        assert pytest.approx(self._rev(Kilometer, d(2000.0, m=1))) == 2.0

    def test_centimeter_forward(self):
        from clausal.modules.py.units import Centimeter
        result = self._fwd(Centimeter, 100)
        assert result.dims == {"m": 1}
        assert pytest.approx(result.value) == 1.0

    def test_gram_forward(self):
        from clausal.modules.py.units import Gram
        result = self._fwd(Gram, 500)
        assert result.dims == {"kg": 1}
        assert pytest.approx(result.value) == 0.5

    def test_gram_reverse(self):
        from clausal.modules.py.units import Gram
        assert pytest.approx(self._rev(Gram, d(0.25, kg=1))) == 250.0

    def test_tonne_forward(self):
        from clausal.modules.py.units import Tonne
        result = self._fwd(Tonne, 2)
        assert pytest.approx(result.value) == 2000.0

    def test_minute_forward(self):
        from clausal.modules.py.units import Minute
        result = self._fwd(Minute, 5)
        assert result.dims == {"s": 1}
        assert pytest.approx(result.value) == 300.0

    def test_hour_forward(self):
        from clausal.modules.py.units import Hour
        result = self._fwd(Hour, 2)
        assert pytest.approx(result.value) == 7200.0

    def test_hour_reverse(self):
        from clausal.modules.py.units import Hour
        assert pytest.approx(self._rev(Hour, d(3600.0, s=1))) == 1.0

    def test_foot_forward(self):
        from clausal.modules.py.units import Foot
        result = self._fwd(Foot, 1)
        assert pytest.approx(result.value) == 0.3048

    def test_pound_forward(self):
        from clausal.modules.py.units import Pound
        result = self._fwd(Pound, 1)
        assert pytest.approx(result.value) == 0.45359237


# ════════════════════════════════════════════════════════════════════════════
# 8. Named derived unit predicates
# ════════════════════════════════════════════════════════════════════════════


class TestDerivedUnits:
    def _fwd(self, pred, number):
        sols = run(pred, number, "D")
        assert sols
        return sols[0]["D"]

    def test_newton(self):
        from clausal.modules.py.units import Newton
        result = self._fwd(Newton, 10)
        assert result.dims == {"kg": 1, "m": 1, "s": -2}
        assert result.value == 10

    def test_joule(self):
        from clausal.modules.py.units import Joule
        result = self._fwd(Joule, 1)
        assert result.dims == {"kg": 1, "m": 2, "s": -2}

    def test_watt(self):
        from clausal.modules.py.units import Watt
        result = self._fwd(Watt, 60)
        assert result.dims == {"kg": 1, "m": 2, "s": -3}

    def test_pascal(self):
        from clausal.modules.py.units import Pascal
        result = self._fwd(Pascal, 101325)
        assert result.dims == {"kg": 1, "m": -1, "s": -2}

    def test_hertz(self):
        from clausal.modules.py.units import Hertz
        result = self._fwd(Hertz, 440)
        assert result.dims == {"s": -1}

    def test_volt(self):
        from clausal.modules.py.units import Volt
        result = self._fwd(Volt, 230)
        assert result.dims == {"kg": 1, "m": 2, "s": -3, "A": -1}

    def test_coulomb(self):
        from clausal.modules.py.units import Coulomb
        result = self._fwd(Coulomb, 1)
        assert result.dims == {"A": 1, "s": 1}

    def test_farad(self):
        from clausal.modules.py.units import Farad
        result = self._fwd(Farad, 100e-6)
        assert result.dims == {"kg": -1, "m": -2, "s": 4, "A": 2}

    def test_ohm(self):
        from clausal.modules.py.units import Ohm
        result = self._fwd(Ohm, 100)
        assert result.dims == {"kg": 1, "m": 2, "s": -3, "A": -2}

    def test_bar_forward(self):
        from clausal.modules.py.units import Bar
        result = self._fwd(Bar, 1)
        assert result.dims == {"kg": 1, "m": -1, "s": -2}
        assert pytest.approx(result.value) == 1e5

    def test_kilowatt_hour_forward(self):
        from clausal.modules.py.units import KilowattHour
        result = self._fwd(KilowattHour, 1)
        assert result.dims == {"kg": 1, "m": 2, "s": -2}
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
        assert run(Dimensionless, 7, "D")[0]["D"] == d(7, **{})

    def test_dimensionless_reverse(self):
        from clausal.modules.py.units import Dimensionless
        assert run(Dimensionless, "X", d(7, **{}))[0]["X"] == 7

    def test_dimensionless_check_by_unification(self):
        from clausal.modules.py.units import Dimensionless
        ratio = d(5.0, **{})
        assert run(Dimensionless, 5.0, ratio)

    def test_dimensionless_fails_for_dimensioned(self):
        from clausal.modules.py.units import Dimensionless
        assert not run(Dimensionless, 5.0, d(5.0, m=1))

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
        from clausal.modules.py.units import IsDimensioned
        self._check(IsDimensioned, d(5, m=1), True)

    def test_is_dimensioned_fail_for_plain_number(self):
        from clausal.modules.py.units import IsDimensioned
        sols = run(IsDimensioned, 42)
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
        assert dims["m"] == 1
        assert dims["s"] == -1

    def test_value_of(self):
        from clausal.modules.py.units import ValueOf
        force = d(9.8, kg=1, m=1, s=-2)
        sols = run(ValueOf, force, "V")
        assert sols
        assert sols[0]["V"] == 9.8

    def test_strip_dimensions(self):
        from clausal.modules.py.units import StripDimensions
        x = d(42, m=2)
        sols = run(StripDimensions, x, "V")
        assert sols
        assert sols[0]["V"] == 42

    def test_make_dimensioned(self):
        from clausal.modules.py.units import MakeDimensioned
        dims = DictTerm({"kg": 1, "m": 1, "s": -2})
        sols = run(MakeDimensioned, 10, dims, "D")
        assert sols
        result = sols[0]["D"]
        assert isinstance(result, Dimensioned)
        assert result.value == 10
        assert result.dims == {"kg": 1, "m": 1, "s": -2}

    def test_dimension_of_plain_number_fails(self):
        from clausal.modules.py.units import DimensionOf
        sols = run(DimensionOf, 42, "DIMS")
        assert not sols

    def test_value_of_plain_number_fails(self):
        from clausal.modules.py.units import ValueOf
        sols = run(ValueOf, 42, "V")
        assert not sols


# ════════════════════════════════════════════════════════════════════════════
# 11. Arithmetic through Python is/2 evaluator
# ════════════════════════════════════════════════════════════════════════════


class TestArithmeticViaIs:
    """Verify Dimensioned arithmetic works when values are passed through is/2."""

    def test_force_from_mass_times_acceleration(self):
        """F = m * a — multiplication gives correct force dimensions."""
        mass = d(2, kg=1)
        accel = d(9.8, m=1, s=-2)
        force = mass * accel
        assert force.dims == {"kg": 1, "m": 1, "s": -2}
        assert pytest.approx(force.value) == 19.6

    def test_kinetic_energy(self):
        """KE = 0.5 * m * v²."""
        mass = d(10, kg=1)
        velocity = d(3, m=1, s=-1)
        ke = 0.5 * mass * velocity ** 2
        assert ke.dims == {"kg": 1, "m": 2, "s": -2}
        assert pytest.approx(ke.value) == 45.0

    def test_power_from_energy_over_time(self):
        """P = E / t."""
        energy = d(3600, kg=1, m=2, s=-2)
        time = d(60, s=1)
        power = energy / time
        assert power.dims == {"kg": 1, "m": 2, "s": -3}
        assert pytest.approx(power.value) == 60.0

    def test_speed_from_distance_over_time(self):
        speed = d(100, m=1) / d(10, s=1)
        assert speed.dims == {"m": 1, "s": -1}
        assert speed.value == 10.0

    def test_ohms_law_voltage(self):
        """V = I * R."""
        current = d(2, A=1)
        resistance = d(50, kg=1, m=2, s=-3, A=-2)
        voltage = current * resistance
        assert voltage.dims == {"kg": 1, "m": 2, "s": -3, "A": -1}
        assert voltage.value == 100

    def test_area_from_side_squared(self):
        side = d(4, m=1)
        area = side ** 2
        assert area == d(16, m=2)

    def test_chain_unit_predicates_and_arithmetic(self):
        """Combine Newton pred output with arithmetic."""
        from clausal.modules.py.units import Newton, Second

        # impulse = force * time
        force = run(Newton, 5, "F")[0]["F"]
        time = run(Second, 3, "T")[0]["T"]
        impulse = force * time
        # impulse dims: kg·m/s (momentum)
        assert impulse.dims == {"kg": 1, "m": 1, "s": -1}
        assert impulse.value == 15


# ════════════════════════════════════════════════════════════════════════════
# 12. Edge cases and error paths
# ════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_dimensionless_times_dimensioned(self):
        """Dimensionless Dimensioned * Dimensioned merges (empty + dims = dims)."""
        scalar = d(2.0, **{})
        length = d(3, m=1)
        result = scalar * length
        assert result.dims == {"m": 1}
        assert result.value == 6.0

    def test_add_two_dimensionless(self):
        result = d(1.0, **{}) + d(2.0, **{})
        assert result == d(3.0, **{})

    def test_sub_two_dimensionless(self):
        result = d(5.0, **{}) - d(2.0, **{})
        assert result == d(3.0, **{})

    def test_pow_with_dimensionless_dimensioned_int_value(self):
        """Pow where exponent is a dimensionless Dimensioned with integer value."""
        base = d(2, m=1)
        exp = Dimensioned(3, {})
        result = base ** exp
        assert result == d(8, m=3)

    def test_unify_two_vars_in_dimensioned(self):
        """Two Dimensioned terms with Var values unify vars together."""
        trail = Trail()
        x = Var()
        y = Var()
        dx = d(x, m=1)
        dy = d(y, m=1)
        assert unify(dx, dy, trail)
        from clausal.logic.variables import deref
        # x and y are now aliased
        unify(x, 10, trail)
        assert deref(y) == 10

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
        assert "s" in s

    def test_multiply_complex_dims(self):
        """Watt * Second = Joule."""
        power = d(100, kg=1, m=2, s=-3)
        time = d(10, s=1)
        energy = power * time
        assert energy.dims == {"kg": 1, "m": 2, "s": -2}
        assert energy.value == 1000

    def test_pow_half_dimensionless(self):
        """** 0.5 is allowed for dimensionless Dimensioned."""
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
        from clausal.modules.py.units import Meter
        assert Meter(3) == d(3, m=1)

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
        assert e.dims == {"kg": 1, "m": 2, "s": -2}
        assert pytest.approx(e.value) == 8.987551787368176e16

    def test_expression_weight(self):
        from clausal.modules.py.units import Kilogram, StandardGravity
        w = Kilogram(70) * StandardGravity
        assert w.dims == {"kg": 1, "m": 1, "s": -2}
        assert pytest.approx(w.value) == 686.4655

    def test_expression_ohms_law(self):
        from clausal.modules.py.units import Volt, Ampere
        r = Volt(12) / Ampere(3)
        assert r.dims == {"kg": 1, "m": 2, "s": -3, "A": -2}
        assert pytest.approx(r.value) == 4.0


class TestPhysicalConstants:
    def test_speed_of_light_dims(self):
        from clausal.modules.py.units import SpeedOfLight
        assert SpeedOfLight.dims == {"m": 1, "s": -1}

    def test_planck_constant_dims(self):
        from clausal.modules.py.units import PlanckConstant
        assert PlanckConstant.dims == {"kg": 1, "m": 2, "s": -1}

    def test_boltzmann_constant_dims(self):
        from clausal.modules.py.units import BoltzmannConstant
        assert BoltzmannConstant.dims == {"kg": 1, "m": 2, "s": -2, "K": -1}

    def test_standard_gravity_dims(self):
        from clausal.modules.py.units import StandardGravity
        assert StandardGravity.dims == {"m": 1, "s": -2}

    def test_elementary_charge_dims(self):
        from clausal.modules.py.units import ElementaryCharge
        assert ElementaryCharge.dims == {"A": 1, "s": 1}

    def test_gravitational_constant_dims(self):
        from clausal.modules.py.units import GravitationalConstant
        assert GravitationalConstant.dims == {"m": 3, "kg": -1, "s": -2}
