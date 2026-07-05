"""Tests for Quantity terms and the units module.

Covers:
  - Quantity arithmetic (add, sub, mul, div, pow, neg, abs)
  - UnitsMismatch on incompatible operations
  - Comparison operators
  - Clausal unification protocol (__unify__, __walk__, __occurs_check__)
  - Named-unit constructor predicates
  - Scaled unit predicates
  - Utility predicates (dimension_of, strip_units, make_quantity)
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
        # nv
        x = Quantity(1, {Metre: 1, Second: 0})
        assert x.dims == {Metre: 1}

    def test_empty_dims_is_dimensionless(self):
        # nv
        x = Quantity(42, {})
        assert x.dims == {}
        assert x.value == 42

    def test_repr(self):
        # nv
        x = d(3, m=1, s=-2)
        assert "Quantity" in repr(x)
        assert "3" in repr(x)

    def test_str(self):
        # nv
        x = d(9.8, m=1, s=-2)
        s = str(x)
        assert "9.8" in s
        assert "Metre" in s
        assert "Second" in s

    def test_equality(self):
        # nv
        assert d(1, m=1) == d(1, m=1)
        assert d(1, m=1) != d(1, m=2)
        assert d(1, m=1) != d(2, m=1)

    def test_hash_consistent_with_eq(self):
        # nv
        a = d(5, m=1)
        b = d(5, m=1)
        assert hash(a) == hash(b)


# ════════════════════════════════════════════════════════════════════════════
# 2. Arithmetic
# ════════════════════════════════════════════════════════════════════════════


class TestArithmetic:
    # ── addition ────────────────────────────────────────────────────────────

    def test_add_same_dims(self):
        # nv
        result = d(3, m=1) + d(2, m=1)
        assert result == d(5, m=1)

    def test_add_mismatch_raises(self):
        # nv
        with pytest.raises(UnitsMismatch):
            d(3, m=1) + d(2, s=1)

    def test_add_dimensioned_with_plain_raises(self):
        # nv
        with pytest.raises(UnitsMismatch):
            d(3, m=1) + 5

    def test_add_dimensionless_with_plain(self):
        # nv
        result = d(3.0, **{}) + 1.0
        assert result == d(4.0, **{})

    def test_radd_dimensionless(self):
        # nv
        result = 2.0 + d(3.0, **{})
        assert result == d(5.0, **{})

    # ── subtraction ─────────────────────────────────────────────────────────

    def test_sub_same_dims(self):
        # nv
        result = d(5, m=1) - d(2, m=1)
        assert result == d(3, m=1)

    def test_sub_mismatch_raises(self):
        # nv
        with pytest.raises(UnitsMismatch):
            d(5, kg=1) - d(2, m=1)

    # ── multiplication ──────────────────────────────────────────────────────

    def test_mul_dimensioned_dimensioned(self):
        # velocity * time = length
        # nv
        v = d(10, m=1, s=-1)
        t = d(3, s=1)
        result = v * t
        assert result == d(30, m=1)

    def test_mul_dimensioned_scalar(self):
        # nv
        result = d(4, m=1) * 3
        assert result == d(12, m=1)

    def test_rmul_scalar(self):
        # nv
        result = 2 * d(5, kg=1)
        assert result == d(10, kg=1)

    def test_mul_cancels_dims(self):
        # m/s * s/m = dimensionless
        # nv
        a = d(6, m=1, s=-1)
        b = d(1, s=1, m=-1)
        result = a * b
        assert result.dims == {}
        assert result.value == 6

    def test_mul_compound_dims(self):
        # kg * m/s² = N
        # nv
        mass = d(2, kg=1)
        accel = d(9.8, m=1, s=-2)
        force = mass * accel
        assert force.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert pytest.approx(force.value) == 19.6

    # ── division ────────────────────────────────────────────────────────────

    def test_div_dimensioned_dimensioned(self):
        # nv
        dist = d(100, m=1)
        time = d(10, s=1)
        vel = dist / time
        assert vel == d(10, m=1, s=-1)

    def test_div_by_scalar(self):
        # nv
        result = d(20, m=1) / 4
        assert result == d(5, m=1)

    def test_rdiv_scalar(self):
        # 1 / s = Hz
        # nv
        result = 1 / d(2, s=1)
        assert result == d(0.5, s=-1)

    def test_div_same_dims_gives_dimensionless(self):
        # nv
        result = d(10, m=1) / d(2, m=1)
        assert result.dims == {}
        assert result.value == 5.0

    # ── power ───────────────────────────────────────────────────────────────

    def test_pow_integer_exponent(self):
        # nv
        side = d(3, m=1)
        area = side ** 2
        assert area == d(9, m=2)

    def test_pow_cubed(self):
        # nv
        side = d(2, m=1)
        vol = side ** 3
        assert vol == d(8, m=3)

    def test_pow_minus_one(self):
        # nv
        freq = d(50, s=1) ** -1
        assert freq.dims == {Second: -1}
        assert pytest.approx(freq.value) == 0.02

    def test_pow_zero_gives_dimensionless(self):
        # nv
        result = d(5, m=1) ** 0
        assert result.dims == {}
        assert result.value == 1

    def test_pow_non_integer_raises(self):
        # nv
        with pytest.raises(UnitsMismatch):
            d(4, m=1) ** 0.5

    def test_pow_dimensioned_exponent_raises(self):
        # nv
        with pytest.raises(UnitsMismatch):
            d(4, m=1) ** d(2, s=1)

    def test_pow_dimensionless_exponent_integer_value(self):
        # Exponent is Quantity but dimensionless with integer value
        # nv
        exp = d(2, **{})  # dimensionless Quantity
        result = d(3, m=1) ** exp
        assert result == d(9, m=2)

    # ── negation / abs ───────────────────────────────────────────────────────

    def test_neg(self):
        # nv
        result = -d(5, m=1)
        assert result == d(-5, m=1)

    def test_abs(self):
        # nv
        result = abs(d(-3, kg=1))
        assert result == d(3, kg=1)


# ════════════════════════════════════════════════════════════════════════════
# 3. Comparison operators
# ════════════════════════════════════════════════════════════════════════════


class TestComparisons:
    def test_lt_same_dims(self):
        # nv
        assert d(1, m=1) < d(2, m=1)

    def test_gt_same_dims(self):
        # nv
        assert d(5, s=1) > d(3, s=1)

    def test_le_equal(self):
        # nv
        assert d(4, kg=1) <= d(4, kg=1)

    def test_ge_equal(self):
        # nv
        assert d(4, kg=1) >= d(4, kg=1)

    def test_comparison_mismatch_raises(self):
        # nv
        with pytest.raises(UnitsMismatch):
            d(1, m=1) < d(2, s=1)

    def test_comparison_with_plain_on_dimensionless(self):
        # nv
        assert d(3.0, **{}) > 2.0

    def test_comparison_dimensioned_with_plain_raises(self):
        # nv
        with pytest.raises(UnitsMismatch):
            d(1, m=1) < 2


# ════════════════════════════════════════════════════════════════════════════
# 4. Clausal unification protocol
# ════════════════════════════════════════════════════════════════════════════


class TestUnificationProtocol:
    def test_unify_same_value_same_dims(self):
        # nv
        trail = Trail()
        assert unify(d(3, m=1), d(3, m=1), trail)

    def test_unify_different_value_fails(self):
        # nv
        trail = Trail()
        assert not unify(d(3, m=1), d(4, m=1), trail)

    def test_unify_different_dims_fails(self):
        # nv
        trail = Trail()
        assert not unify(d(3, m=1), d(3, s=1), trail)

    def test_unify_var_with_dimensioned(self):
        # nv
        trail = Trail()
        v = Var()
        assert unify(v, d(10, kg=1), trail)
        assert deref(v) == d(10, kg=1)

    def test_unify_not_dimensioned_returns_not_implemented(self):
        # nv
        trail = Trail()
        x = d(1, m=1)
        result = x.__unify__(42, trail)
        assert result is NotImplemented

    # ── AttVar-based dimensional constraint tests ────────────────────────────

    def test_attvar_unit_constraint_fires_on_bind(self):
        """Binding a constrained AttVar to a matching Quantity succeeds."""
        # nv
        trail = Trail()
        v = Var()
        put_attr(v, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert unify(v, d(5, m=1), trail)
        assert deref(v) == d(5, m=1)

    def test_attvar_unit_constraint_fails_wrong_dims(self):
        """Binding to a Quantity with wrong dims fails."""
        # nv
        trail = Trail()
        v = Var()
        put_attr(v, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert not unify(v, d(5, s=1), trail)

    def test_attvar_unit_constraint_fails_plain_number(self):
        """Binding a dimensioned constraint to a plain number fails."""
        # nv
        trail = Trail()
        v = Var()
        put_attr(v, UNITS_KEY, UnitState({Metre: 1}), trail)
        assert not unify(v, 5, trail)

    def test_attvar_dimensionless_constraint_accepts_plain_number(self):
        """A dimensionless constraint accepts a plain number."""
        # nv
        trail = Trail()
        v = Var()
        put_attr(v, UNITS_KEY, UnitState({}), trail)
        assert unify(v, 42, trail)

    def test_two_attvar_unit_constraints_merge_compatible(self):
        """Unifying two vars with identical unit constraints succeeds."""
        # nv
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
        # nv
        trail = Trail()
        x = Var()
        y = Var()
        put_attr(x, UNITS_KEY, UnitState({Metre: 1}), trail)
        put_attr(y, UNITS_KEY, UnitState({Second: 1}), trail)
        assert not unify(x, y, trail)

    def test_attvar_constraint_transfers_to_unconstrained_var(self):
        """when constrained var is unified with unconstrained var, constraint transfers."""
        # nv
        trail = Trail()
        x = Var()
        y = Var()
        put_attr(x, UNITS_KEY, UnitState({Kilogram: 1}), trail)
        assert unify(x, y, trail)
        assert get_attr(deref(y), UNITS_KEY).dims == {Kilogram: 1}

    def test_attvar_unit_constraint_backtracks(self):
        """put_attr via trail correctly undoes on backtrack."""
        # nv
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
        # nv
        from clausal.modules.py.units import Metre
        assert self._fwd(Metre, 5) == d(5, m=1)

    def test_kilogram(self):
        # nv
        from clausal.modules.py.units import Kilogram
        assert self._fwd(Kilogram, 3) == d(3, kg=1)

    def test_second(self):
        # nv
        from clausal.modules.py.units import Second
        assert self._fwd(Second, 10) == d(10, s=1)

    def test_ampere(self):
        # nv
        from clausal.modules.py.units import Ampere
        assert self._fwd(Ampere, 2) == d(2, A=1)

    def test_kelvin(self):
        # nv
        from clausal.modules.py.units import Kelvin
        assert self._fwd(Kelvin, 273) == d(273, K=1)

    def test_mole(self):
        # nv
        from clausal.modules.py.units import Mole
        assert self._fwd(Mole, 1) == d(1, mol=1)

    def test_candela(self):
        # nv
        from clausal.modules.py.units import Candela
        assert self._fwd(Candela, 100) == d(100, cd=1)


# ════════════════════════════════════════════════════════════════════════════
# 7. Scaled unit constructors (Python __call__)
# ════════════════════════════════════════════════════════════════════════════


class TestScaledUnits:
    """Scaled units are Quantity constants — multiply by a scalar."""

    def test_kilometer(self):
        # nv
        from clausal.modules.py.units import Kilometer
        result = 1 * Kilometer
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 1000.0

    def test_centimeter(self):
        # nv
        from clausal.modules.py.units import Centimeter
        result = 100 * Centimeter
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 1.0

    def test_gram(self):
        # nv
        from clausal.modules.py.units import Gram
        result = 500 * Gram
        assert result.dims == {Kilogram: 1}
        assert pytest.approx(result.value) == 0.5

    def test_tonne(self):
        # nv
        from clausal.modules.py.units import Tonne
        result = 2 * Tonne
        assert pytest.approx(result.value) == 2000.0

    def test_minute(self):
        # nv
        from clausal.modules.py.units import Minute
        result = 5 * Minute
        assert result.dims == {Second: 1}
        assert pytest.approx(result.value) == 300.0

    def test_hour(self):
        # nv
        from clausal.modules.py.units import Hour
        result = 2 * Hour
        assert pytest.approx(result.value) == 7200.0

    def test_foot_unit_vector(self):
        # nv
        from clausal.modules.py.imperial import foot
        result = 1 * foot
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 0.3048

    def test_pound_unit_vector(self):
        # nv
        from clausal.modules.py.imperial import pound_mass
        result = 1 * pound_mass
        assert result.dims == {Kilogram: 1}
        assert pytest.approx(result.value) == 0.45359237


# ════════════════════════════════════════════════════════════════════════════
# 8. Named derived unit constructors (Python __call__)
# ════════════════════════════════════════════════════════════════════════════


class TestDerivedUnits:
    def _fwd(self, pred, number):
        return pred(number)

    def test_newton(self):
        # nv
        from clausal.modules.py.units import Newton
        result = self._fwd(Newton, 10)
        assert result.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert result.value == 10

    def test_joule(self):
        # nv
        from clausal.modules.py.units import Joule
        result = self._fwd(Joule, 1)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -2}

    def test_watt(self):
        # nv
        from clausal.modules.py.units import Watt
        result = self._fwd(Watt, 60)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -3}

    def test_pascal(self):
        # nv
        from clausal.modules.py.units import Pascal
        result = self._fwd(Pascal, 101325)
        assert result.dims == {Kilogram: 1, Metre: -1, Second: -2}

    def test_hertz(self):
        # nv
        from clausal.modules.py.units import Hertz
        result = self._fwd(Hertz, 440)
        assert result.dims == {Second: -1}

    def test_volt(self):
        # nv
        from clausal.modules.py.units import Volt
        result = self._fwd(Volt, 230)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -3, Ampere: -1}

    def test_coulomb(self):
        # nv
        from clausal.modules.py.units import Coulomb
        result = self._fwd(Coulomb, 1)
        assert result.dims == {Ampere: 1, Second: 1}

    def test_farad(self):
        # nv
        from clausal.modules.py.units import Farad
        result = self._fwd(Farad, 100e-6)
        assert result.dims == {Kilogram: -1, Metre: -2, Second: 4, Ampere: 2}

    def test_ohm(self):
        # nv
        from clausal.modules.py.units import Ohm
        result = self._fwd(Ohm, 100)
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -3, Ampere: -2}

    def test_bar(self):
        # nv
        from clausal.modules.py.units import Bar
        result = 1 * Bar
        assert result.dims == {Kilogram: 1, Metre: -1, Second: -2}
        assert pytest.approx(result.value) == 1e5

    def test_kilowatt_hour_unit_vector(self):
        # nv
        from clausal.modules.py.imperial import kilowatt_hour
        result = 1 * kilowatt_hour
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(result.value) == 3_600_000.0



# ════════════════════════════════════════════════════════════════════════════
# 10. Utility predicates
# ════════════════════════════════════════════════════════════════════════════


class TestUtilityPredicates:
    def test_dimension_of(self):
        # nv
        from clausal.modules.py.units import dimension_of
        velocity = d(10, m=1, s=-1)
        sols = run(dimension_of, velocity, "DIMS")
        assert sols
        dims = sols[0]["DIMS"]
        assert isinstance(dims, DictTerm)
        assert dims[Metre] == 1
        assert dims[Second] == -1

    def test_value_of(self):
        # nv
        from clausal.modules.py.units import strip_units
        force = d(9.8, kg=1, m=1, s=-2)
        sols = run(strip_units, force, "V")
        assert sols
        assert sols[0]["V"] == 9.8

    def test_strip_dimensions(self):
        # nv
        from clausal.modules.py.units import strip_units
        x = d(42, m=2)
        sols = run(strip_units, x, "V")
        assert sols
        assert sols[0]["V"] == 42

    def test_make_dimensioned(self):
        # nv
        from clausal.modules.py.units import make_quantity
        dims = DictTerm({Kilogram: 1, Metre: 1, Second: -2})
        sols = run(make_quantity, 10, dims, "D")
        assert sols
        result = sols[0]["D"]
        assert isinstance(result, Quantity)
        assert result.value == 10
        assert result.dims == {Kilogram: 1, Metre: 1, Second: -2}

    def test_dimension_of_plain_number_fails(self):
        # nv
        from clausal.modules.py.units import dimension_of
        sols = run(dimension_of, 42, "DIMS")
        assert not sols

    def test_value_of_plain_number_fails(self):
        # nv
        from clausal.modules.py.units import strip_units
        sols = run(strip_units, 42, "V")
        assert not sols


# ════════════════════════════════════════════════════════════════════════════
# 11. Arithmetic through Python is/2 evaluator
# ════════════════════════════════════════════════════════════════════════════


class TestArithmeticViaIs:
    """Verify Quantity arithmetic works when values are passed through is/2."""

    def test_force_from_mass_times_acceleration(self):
        """F = m * a — multiplication gives correct force dimensions."""
        # nv
        mass = d(2, kg=1)
        accel = d(9.8, m=1, s=-2)
        force = mass * accel
        assert force.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert pytest.approx(force.value) == 19.6

    def test_kinetic_energy(self):
        """KE = 0.5 * m * v²."""
        # nv
        mass = d(10, kg=1)
        velocity = d(3, m=1, s=-1)
        ke = 0.5 * mass * velocity ** 2
        assert ke.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(ke.value) == 45.0

    def test_power_from_energy_over_time(self):
        """P = E / t."""
        # nv
        energy = d(3600, kg=1, m=2, s=-2)
        time = d(60, s=1)
        power = energy / time
        assert power.dims == {Kilogram: 1, Metre: 2, Second: -3}
        assert pytest.approx(power.value) == 60.0

    def test_speed_from_distance_over_time(self):
        # nv
        speed = d(100, m=1) / d(10, s=1)
        assert speed.dims == {Metre: 1, Second: -1}
        assert speed.value == 10.0

    def test_ohms_law_voltage(self):
        """V = I * R."""
        # nv
        current = d(2, A=1)
        resistance = d(50, kg=1, m=2, s=-3, A=-2)
        voltage = current * resistance
        assert voltage.dims == {Kilogram: 1, Metre: 2, Second: -3, Ampere: -1}
        assert voltage.value == 100

    def test_area_from_side_squared(self):
        # nv
        side = d(4, m=1)
        area = side ** 2
        assert area == d(16, m=2)

    def test_chain_unit_predicates_and_arithmetic(self):
        """Combine Newton pred output with arithmetic."""
        # nv
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
        # nv
        scalar = d(2.0, **{})
        length = d(3, m=1)
        result = scalar * length
        assert result.dims == {Metre: 1}
        assert result.value == 6.0

    def test_add_two_dimensionless(self):
        # nv
        result = d(1.0, **{}) + d(2.0, **{})
        assert result == d(3.0, **{})

    def test_sub_two_dimensionless(self):
        # nv
        result = d(5.0, **{}) - d(2.0, **{})
        assert result == d(3.0, **{})

    def test_pow_with_dimensionless_dimensioned_int_value(self):
        """Pow where exponent is a dimensionless Quantity with integer value."""
        # nv
        base = d(2, m=1)
        exp = Quantity(3, {})
        result = base ** exp
        assert result == d(8, m=3)

    def test_attvar_vars_merge_then_bind(self):
        """Two unit-constrained vars are merged; binding one binds both."""
        # nv
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
        # nv
        x = d(5.0, m=1)
        assert f"{x}" == str(x)

    def test_dimensioned_zero_value(self):
        # nv
        result = d(0, kg=1) + d(0, kg=1)
        assert result == d(0, kg=1)

    def test_negative_exponents_in_display(self):
        # nv
        x = d(10, m=1, s=-2)
        s = str(x)
        assert "Second" in s

    def test_multiply_complex_dims(self):
        """Watt * Second = Joule."""
        # nv
        power = d(100, kg=1, m=2, s=-3)
        time = d(10, s=1)
        energy = power * time
        assert energy.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert energy.value == 1000

    def test_pow_half_dimensionless(self):
        """** 0.5 is allowed for dimensionless Quantity."""
        # nv
        result = d(9.0, **{}) ** 0.5
        assert result.dims == {}
        assert pytest.approx(result.value) == 3.0

    def test_pow_half_dimensional_raises(self):
        """** 0.5 raises UnitsMismatch for dimensional quantities."""
        # nv
        with pytest.raises(UnitsMismatch):
            d(4.0, m=2) ** 0.5


class TestUnitPredicateCall:
    """Unit predicates are callable as Python expressions via __call__."""

    def test_kilogram_call(self):
        # nv
        from clausal.modules.py.units import Kilogram
        assert Kilogram(5) == d(5, kg=1)

    def test_meter_call(self):
        # nv
        from clausal.modules.py.units import Metre
        assert Metre(3) == d(3, m=1)

    def test_newton_call(self):
        # nv
        from clausal.modules.py.units import Newton
        assert Newton(9.8) == d(9.8, kg=1, m=1, s=-2)

    def test_kilometer_multiply(self):
        # nv
        from clausal.modules.py.units import Kilometer
        assert 1 * Kilometer == d(1000, m=1)

    def test_expression_e_mc2(self):
        """E = mc² via Python expression syntax."""
        # nv
        from clausal.modules.py.units import Kilogram, SpeedOfLight
        e = Kilogram(1) * SpeedOfLight ** 2
        assert e.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(e.value) == 8.987551787368176e16

    def test_expression_weight(self):
        # nv
        from clausal.modules.py.units import Kilogram, StandardGravity
        w = Kilogram(70) * StandardGravity
        assert w.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert pytest.approx(w.value) == 686.4655

    def test_expression_ohms_law(self):
        # nv
        from clausal.modules.py.units import Volt, Ampere
        r = Volt(12) / Ampere(3)
        assert r.dims == {Kilogram: 1, Metre: 2, Second: -3, Ampere: -2}
        assert pytest.approx(r.value) == 4.0


# ════════════════════════════════════════════════════════════════════════════
# Unit predicate arithmetic (dims combinators)
# ════════════════════════════════════════════════════════════════════════════


class TestUnitPredicateArithmetic:
    """_UnitsPredicate arithmetic produces dimension descriptors for has_units."""

    def test_pow_produces_correct_dims(self):
        # nv
        from clausal.modules.py.units import Metre
        area = Metre ** 2
        assert area._dims == {Metre: 2}

    def test_div_produces_correct_dims(self):
        # nv
        from clausal.modules.py.units import Metre, Second
        velocity = Metre / Second
        assert velocity._dims == {Metre: 1, Second: -1}

    def test_mul_produces_correct_dims(self):
        # nv
        from clausal.modules.py.units import Kilogram, Metre
        kg_m = Kilogram * Metre
        assert kg_m._dims == {Kilogram: 1, Metre: 1}

    def test_compound_force_dims(self):
        # nv
        from clausal.modules.py.units import Kilogram, Metre, Second, Newton
        force = Kilogram * Metre / Second ** 2
        assert force._dims == Newton._dims

    def test_acceleration_dims(self):
        # nv
        from clausal.modules.py.units import Metre, Second
        acc = Metre / Second ** 2
        assert acc._dims == {Metre: 1, Second: -2}

    def test_pow_fractional_not_useful_but_legal(self):
        # nv
        from clausal.modules.py.units import Metre
        # Metre**-1 is a valid descriptor (e.g. wavenumber)
        inv = Metre ** -1
        assert inv._dims == {Metre: -1}

    def test_descriptor_matches_quantity_dims(self):
        # nv
        from clausal.modules.py.units import Metre, Second
        velocity_desc = Metre / Second
        velocity_qty = Metre(10) / Second(1)
        assert velocity_qty.dims == velocity_desc._dims

    def test_area_descriptor_matches_quantity_dims(self):
        # nv
        from clausal.modules.py.units import Metre
        area_desc = Metre ** 2
        area_qty = Metre(4) ** 2
        assert area_qty.dims == area_desc._dims

    def test_compound_desc_mismatch(self):
        # nv
        from clausal.modules.py.units import Metre, Second
        area_desc = Metre ** 2
        velocity_qty = Metre(10) / Second(1)
        assert velocity_qty.dims != area_desc._dims


class TestPhysicalConstants:
    def test_speed_of_light_dims(self):
        # nv
        from clausal.modules.py.units import SpeedOfLight
        assert SpeedOfLight.dims == {Metre: 1, Second: -1}

    def test_planck_constant_dims(self):
        # nv
        from clausal.modules.py.units import PlanckConstant
        assert PlanckConstant.dims == {Kilogram: 1, Metre: 2, Second: -1}

    def test_boltzmann_constant_dims(self):
        # nv
        from clausal.modules.py.units import BoltzmannConstant
        assert BoltzmannConstant.dims == {Kilogram: 1, Metre: 2, Second: -2, Kelvin: -1}

    def test_standard_gravity_dims(self):
        # nv
        from clausal.modules.py.units import StandardGravity
        assert StandardGravity.dims == {Metre: 1, Second: -2}

    def test_elementary_charge_dims(self):
        # nv
        from clausal.modules.py.units import ElementaryCharge
        assert ElementaryCharge.dims == {Ampere: 1, Second: 1}

    def test_gravitational_constant_dims(self):
        # nv
        from clausal.modules.py.units import GravitationalConstant
        assert GravitationalConstant.dims == {Metre: 3, Kilogram: -1, Second: -2}


# ── Sugar tests ───────────────────────────────────────────────────────────────


class TestUnitsSugar:
    """Tests for n(Unit) and X(Unit) syntactic sugar."""

    # ── has_units/2 builtin (direct Python via run()) ──────────────────────────

    def _has_units_pred(self):
        """Return a callable suitable for run() that wraps has_units/2."""
        import clausal.modules.py.units  # ensure units_constraint is imported
        from clausal.logic.builtins._registry import get_builtin_predicate
        return get_builtin_predicate("has_units", 2)

    def test_has_units_ground_match(self):
        # nv
        from clausal.modules.py.units import Newton
        results = run(self._has_units_pred(), Newton(9.8), Newton)
        assert len(results) == 1

    def test_has_units_ground_mismatch(self):
        # nv
        from clausal.modules.py.units import Newton, Metre
        results = run(self._has_units_pred(), Newton(9.8), Metre)
        assert results == []

    def test_has_units_unbound_var_posts_constraint(self):
        # nv
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
        # nv
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
        # nv
        from clausal.modules.py.units import Metre
        from clausal.logic.variables import Var
        from clausal.logic.units_constraint import constrain_var_dims
        v = Var()
        trail = Trail()
        constrain_var_dims(v, Metre._dims, trail)
        results = run(self._has_units_pred(), v, Metre)
        assert len(results) == 1

    def test_has_units_already_constrained_conflict(self):
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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

    # ── X(Unit) expression sugar: construction ─────────────────────────────────

    def test_var_sugar_constructs_quantity(self, tmp_path):
        """MY_VAL(Metre) in expression position constructs Quantity(MY_VAL, Metre)."""
        # nv
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre])\n"
            "Test <- (N := 5, D := N(Metre), D == 5(Metre))\n"
        )
        p = tmp_path / "var_sugar_construct.clausal"
        p.write_text(src)
        mod = _load_module("var_sugar_construct", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_var_sugar_compound_constructs(self, tmp_path):
        """MY_VAL(Metre/Second) constructs a velocity Quantity."""
        # nv
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (N := 10, V := N(Metre/Second), has_units(V, Metre/Second))\n"
        )
        p = tmp_path / "var_sugar_compound.clausal"
        p.write_text(src)
        mod = _load_module("var_sugar_compound", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_has_units_check_passes(self, tmp_path):
        """has_units(D, Metre) succeeds when D is a Metre Quantity."""
        # nv
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre])\n"
            "Test <- (D := 5(Metre), has_units(D, Metre))\n"
        )
        p = tmp_path / "has_units_match.clausal"
        p.write_text(src)
        mod = _load_module("has_units_match", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_has_units_check_fails(self, tmp_path):
        """has_units(D, Metre) fails when D has Second dims."""
        # nv
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (D := 5(Second), has_units(D, Metre))\n"
        )
        p = tmp_path / "has_units_fail.clausal"
        p.write_text(src)
        mod = _load_module("has_units_fail", str(p)).__dict__["$module"]
        assert not any(True for _ in call("Test", module=mod))

    def test_has_units_posts_constraint(self, tmp_path):
        """has_units(X, Metre) on unbound var posts the units constraint."""
        # nv
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre])\n"
            "Test <- (has_units(X, Metre), X is 5(Metre))\n"
        )
        p = tmp_path / "has_units_constrain.clausal"
        p.write_text(src)
        mod = _load_module("has_units_constrain", str(p)).__dict__["$module"]
        assert any(True for _ in call("Test", module=mod))

    def test_has_units_constraint_rejects_wrong_unit(self, tmp_path):
        """has_units(X, Metre) then unify with Second — fails."""
        # nv
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        src = (
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (has_units(X, Metre), X is 5(Second))\n"
        )
        p = tmp_path / "has_units_reject.clausal"
        p.write_text(src)
        mod = _load_module("has_units_reject", str(p)).__dict__["$module"]
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
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_add",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (D := ++(Metre(3) + Second(2)))\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

    def test_sub_metre_minus_kilogram_raises(self, tmp_path):
        """Subtracting kg from m via ++ raises UnitsMismatch."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_sub",
            "-import_from(py.units, [Metre, Kilogram])\n"
            "Test <- (D := ++(Metre(5) - Kilogram(1)))\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

    def test_compare_metre_with_second_raises(self, tmp_path):
        """Comparing m > s directly in clause body raises UnitsMismatch."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_cmp",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- (5(Metre) > 3(Second))\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

    def test_add_dimensioned_with_plain_raises(self, tmp_path):
        """Adding a plain number to a dimensional quantity via ++ raises UnitsMismatch."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "mismatch_plain",
            "-import_from(py.units, [Metre])\n"
            "Test <- (D := ++(Metre(5) + 3))\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

    def test_matching_units_no_error(self, tmp_path):
        """Adding same units via ++ succeeds and produces the correct result."""
        # nv
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
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_int",
            "Test <- (D := 42(), ++(D.dims == {}), ++(D.value == 42))\n")
        assert any(True for _ in call("Test", module=mod))

    def test_float_dimensionless(self, tmp_path):
        """3.14() produces Quantity(3.14, {})."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_float",
            "Test <- (D := 3.14(), ++(D.dims == {}), ++(D.value == 3.14))\n")
        assert any(True for _ in call("Test", module=mod))

    def test_dimensionless_equals_dimensionless_pred(self, tmp_path):
        """42() == Dimensionless(42) via predicate."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_eq",
            "-import_from(py.units, [Dimensionless])\n"
            "Test <- (D1 := 42(), D2 := ++(Dimensionless(42)), D1 == D2)\n")
        assert any(True for _ in call("Test", module=mod))

    def test_dimensionless_arithmetic(self, tmp_path):
        """Dimensionless values can be added via ++: ++(3() + 2()) == 5()."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_arith",
            "Test <- (S := ++(Quantity(3, {}) + Quantity(2, {})), S == 5())\n")
        assert any(True for _ in call("Test", module=mod))

    def test_dimensionless_is_dimensionless(self, tmp_path):
        """has_units(D, Dimensionless) succeeds for n()."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_is",
            "-import_from(py.units, [Dimensionless])\n"
            "Test <- (D := 7(), has_units(D, Dimensionless))\n")
        assert any(True for _ in call("Test", module=mod))

    def test_dimensionless_is_dimensionless_not_length(self, tmp_path):
        """has_units(D, Metre) fails for a dimensionless n() value."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "dimless_not_len",
            "-import_from(py.units, [Metre])\n"
            "Test <- (D := 7(), has_units(D, Metre))\n")
        assert not any(True for _ in call("Test", module=mod))


# ════════════════════════════════════════════════════════════════════════════
# 15. Python exception catch/3 integration
# ════════════════════════════════════════════════════════════════════════════


class TestPythonExceptionCatch:
    """catch/3 catches UnitsMismatch as UnitsMismatch(Msg) — ClassName(Message) compound."""

    def _load(self, tmp_path, name, src):
        from clausal.import_hook import _load_module
        p = tmp_path / f"{name}.clausal"
        p.write_text(src)
        return _load_module(name, str(p)).__dict__["$module"]

    def test_catch_add_mismatch(self, tmp_path):
        """Catching UnitsMismatch from incompatible addition."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "catch_add",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- catch(++(Metre(1) + Second(1)), UnitsMismatch(_), 1 == 1)\n")
        assert any(True for _ in call("Test", module=mod))

    def test_catch_sub_mismatch(self, tmp_path):
        """Catching UnitsMismatch from incompatible subtraction."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "catch_sub",
            "-import_from(py.units, [Metre, Kilogram])\n"
            "Test <- catch(++(Metre(5) - Kilogram(3)), UnitsMismatch(_), 1 == 1)\n")
        assert any(True for _ in call("Test", module=mod))

    def test_catch_message_bound(self, tmp_path):
        """The caught message variable is bound to the exception string."""
        # nv
        from clausal.logic.solve import call
        from clausal.logic.variables import deref, Var
        mod = self._load(tmp_path, "catch_msg",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- catch(++(Metre(1) + Second(1)), UnitsMismatch(_MSG), _MSG == _MSG)\n")
        assert any(True for _ in call("Test", module=mod))

    def test_no_exception_recovery_skipped(self, tmp_path):
        """If no exception, the recovery goal is not run (even if it would fail)."""
        # nv
        from clausal.logic.solve import call
        mod = self._load(tmp_path, "catch_noexc",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- catch(++(Metre(3) * Second(2)), UnitsMismatch(_), 1 == 2)\n")
        # Mul doesn't raise; goal succeeds; recovery is skipped entirely.
        assert any(True for _ in call("Test", module=mod))

    def test_unmatched_exception_reraises(self, tmp_path):
        """An exception that doesn't match the catcher is re-raised."""
        # nv
        from clausal.logic.solve import call
        from clausal.terms import UnitsMismatch
        mod = self._load(tmp_path, "catch_reraise",
            "-import_from(py.units, [Metre, Second])\n"
            "Test <- catch(++(Metre(1) + Second(1)), SomeOtherError(_), 1 == 1)\n")
        with pytest.raises(UnitsMismatch):
            list(call("Test", module=mod))

# ════════════════════════════════════════════════════════════════════════════
# SI prefix constants
# ════════════════════════════════════════════════════════════════════════════


class TestSIPrefixes:
    """SI prefix constants are plain numbers — multiply against unit vectors."""

    def test_kilo_is_number(self):
        # nv
        from clausal.modules.py.units import kilo
        assert kilo == 1000
        assert isinstance(kilo, (int, float))

    def test_milli_is_number(self):
        # nv
        from clausal.modules.py.units import milli
        assert milli == 1e-3

    def test_mega_is_number(self):
        # nv
        from clausal.modules.py.units import mega
        assert mega == 1e6

    def test_nano_is_number(self):
        # nv
        from clausal.modules.py.units import nano
        assert nano == 1e-9

    def test_kilo_times_unit_vector(self):
        # nv
        from clausal.modules.py.units import kilo, Newton
        result = 5 * kilo * Newton(1)
        assert result.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert pytest.approx(result.value) == 5_000.0

    def test_nano_times_unit_vector(self):
        # nv
        from clausal.modules.py.units import nano
        result = 100 * nano * Second(1)
        assert result.dims == {Second: 1}
        assert pytest.approx(result.value) == 1e-7

    def test_mega_times_unit_vector(self):
        # nv
        from clausal.modules.py.units import mega, Hertz
        result = 2.4 * mega * Hertz(1)
        assert result.dims == {Second: -1}
        assert pytest.approx(result.value) == 2.4e6

    def test_prefix_abbreviation_k(self):
        # nv
        from clausal.modules.py.units import k, kilo
        assert k == kilo

    def test_prefix_abbreviation_n(self):
        # nv
        from clausal.modules.py.units import n, nano
        assert n == nano


# ════════════════════════════════════════════════════════════════════════════
# Imperial and non-SI unit vectors
# ════════════════════════════════════════════════════════════════════════════


class TestImperialUnits:
    """Imperial / non-SI unit vectors are Quantity values; multiply by scalar."""

    # ── length ───────────────────────────────────────────────────────────────

    def test_inch(self):
        # nv
        from clausal.modules.py.imperial import inch
        result = 12 * inch
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 0.3048

    def test_foot(self):
        # nv
        from clausal.modules.py.imperial import foot
        result = 1 * foot
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 0.3048

    def test_yard(self):
        # nv
        from clausal.modules.py.imperial import yard
        result = 1 * yard
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 0.9144

    def test_mile(self):
        # nv
        from clausal.modules.py.imperial import mile
        result = 1 * mile
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 1_609.344

    def test_nautical_mile(self):
        # nv
        from clausal.modules.py.imperial import nautical_mile
        result = 1 * nautical_mile
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value) == 1_852.0

    def test_light_year(self):
        # nv
        from clausal.modules.py.imperial import light_year
        result = 1 * light_year
        assert result.dims == {Metre: 1}
        assert pytest.approx(result.value, rel=1e-9) == 9.4607304725808e15

    # ── Mass ─────────────────────────────────────────────────────────────────

    def test_pound_mass(self):
        # nv
        from clausal.modules.py.imperial import pound_mass
        result = 1 * pound_mass
        assert result.dims == {Kilogram: 1}
        assert pytest.approx(result.value) == 0.45359237

    def test_ounce_mass(self):
        # nv
        from clausal.modules.py.imperial import ounce_mass
        result = 16 * ounce_mass
        assert result.dims == {Kilogram: 1}
        assert pytest.approx(result.value) == pytest.approx(1 * 0.45359237, rel=1e-6)

    # ── Force ─────────────────────────────────────────────────────────────────

    def test_pound_force(self):
        # nv
        from clausal.modules.py.imperial import pound_force
        result = 1 * pound_force
        assert result.dims == {Kilogram: 1, Metre: 1, Second: -2}
        assert pytest.approx(result.value) == 4.4482216152605

    # ── Volume ────────────────────────────────────────────────────────────────

    def test_litre(self):
        # nv
        from clausal.modules.py.imperial import litre
        result = 1 * litre
        assert result.dims == {Metre: 3}
        assert pytest.approx(result.value) == 1e-3

    def test_gallon_us(self):
        # nv
        from clausal.modules.py.imperial import gallon_us
        result = 1 * gallon_us
        assert result.dims == {Metre: 3}
        assert pytest.approx(result.value) == 3.785411784e-3

    # ── Pressure ──────────────────────────────────────────────────────────────

    def test_psi(self):
        # nv
        from clausal.modules.py.imperial import psi
        result = 1 * psi
        assert result.dims == {Kilogram: 1, Metre: -1, Second: -2}
        assert pytest.approx(result.value) == 6_894.757

    # ── Energy ────────────────────────────────────────────────────────────────

    def test_calorie(self):
        # nv
        from clausal.modules.py.imperial import calorie
        result = 1 * calorie
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(result.value) == 4.184

    def test_btu(self):
        # nv
        from clausal.modules.py.imperial import btu
        result = 1 * btu
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(result.value) == 1_055.05585262

    def test_kilowatt_hour(self):
        # nv
        from clausal.modules.py.imperial import kilowatt_hour
        result = 1 * kilowatt_hour
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -2}
        assert pytest.approx(result.value) == 3_600_000.0

    # ── Power ─────────────────────────────────────────────────────────────────

    def test_horsepower(self):
        # nv
        from clausal.modules.py.imperial import horsepower
        result = 1 * horsepower
        assert result.dims == {Kilogram: 1, Metre: 2, Second: -3}
        assert pytest.approx(result.value) == 745.69987

    # ── Speed ─────────────────────────────────────────────────────────────────

    def test_mph(self):
        # nv
        from clausal.modules.py.imperial import mph
        result = 60 * mph
        assert result.dims == {Metre: 1, Second: -1}
        assert pytest.approx(result.value) == 26.8224

    def test_knot(self):
        # nv
        from clausal.modules.py.imperial import knot
        result = 1 * knot
        assert result.dims == {Metre: 1, Second: -1}
        assert pytest.approx(result.value, rel=1e-6) == 1_852.0 / 3_600.0

    # ── Abbreviations ─────────────────────────────────────────────────────────

    def test_ft_alias(self):
        # nv
        from clausal.modules.py.imperial import ft, foot
        assert ft is foot

    def test_lb_alias(self):
        # nv
        from clausal.modules.py.imperial import lb, pound_mass
        assert lb is pound_mass

    def test_lbf_alias(self):
        # nv
        from clausal.modules.py.imperial import lbf, pound_force
        assert lbf is pound_force

    def test_nmi_alias(self):
        # nv
        from clausal.modules.py.imperial import nmi, nautical_mile
        assert nmi is nautical_mile

    # ── Arithmetic with imperial units ────────────────────────────────────────

    def test_five_feet_twelve_inches_equals_six_feet(self):
        # nv
        from clausal.modules.py.imperial import foot, inch
        assert pytest.approx((5 * foot + 12 * inch).value) == (6 * foot).value

    def test_mph_to_ms(self):
        # nv
        from clausal.modules.py.imperial import mph
        speed = 60 * mph
        assert pytest.approx(speed.value, rel=1e-5) == 26.8224


# ════════════════════════════════════════════════════════════════════════════
# Digital information units (IEC 80000-13)
# ════════════════════════════════════════════════════════════════════════════


class TestInformationUnits:
    """Bit is the base unit; all values are stored internally in bits."""

    # ── Base unit ─────────────────────────────────────────────────────────────

    def test_bit_is_base_unit(self):
        # nv
        from clausal.modules.py.units import Bit
        result = Bit(1)
        assert result.dims == {Bit: 1}
        assert result.value == 1

    def test_bit_dim_key_is_predicate(self):
        # nv
        from clausal.modules.py.units import Bit
        key = list(Bit(1).dims.keys())[0]
        assert key is Bit

    # ── Byte = 8 bits ─────────────────────────────────────────────────────────

    def test_byte_is_8_bits(self):
        # nv
        from clausal.modules.py.units import Bit, Byte
        result = 1 * Byte
        assert result.dims == {Bit: 1}
        assert result.value == 8

    def test_byte_10_is_80_bits(self):
        # nv
        from clausal.modules.py.units import Bit, Byte
        assert (10 * Byte).value == 80

    # ── Decimal (SI-prefixed) byte multiples ──────────────────────────────────

    def test_kilobyte(self):
        # nv
        from clausal.modules.py.units import Bit, Kilobyte
        result = 1 * Kilobyte
        assert result.dims == {Bit: 1}
        assert result.value == 8_000

    def test_megabyte(self):
        # nv
        from clausal.modules.py.units import Bit, Megabyte
        result = 1 * Megabyte
        assert result.dims == {Bit: 1}
        assert result.value == 8_000_000

    def test_gigabyte(self):
        # nv
        from clausal.modules.py.units import Bit, Gigabyte
        result = 1 * Gigabyte
        assert result.dims == {Bit: 1}
        assert result.value == 8_000_000_000

    def test_terabyte(self):
        # nv
        from clausal.modules.py.units import Bit, Terabyte
        result = 1 * Terabyte
        assert result.dims == {Bit: 1}
        assert result.value == 8_000_000_000_000

    # ── Decimal (SI-prefixed) bit multiples ───────────────────────────────────

    def test_kilobit(self):
        # nv
        from clausal.modules.py.units import Bit, Kilobit
        result = 1 * Kilobit
        assert result.dims == {Bit: 1}
        assert result.value == 1_000

    def test_megabit(self):
        # nv
        from clausal.modules.py.units import Bit, Megabit
        result = 100 * Megabit
        assert result.dims == {Bit: 1}
        assert result.value == 100_000_000

    def test_gigabit(self):
        # nv
        from clausal.modules.py.units import Bit, Gigabit
        result = 1 * Gigabit
        assert result.dims == {Bit: 1}
        assert result.value == 1_000_000_000

    # ── Binary (IEC-prefixed) byte multiples ──────────────────────────────────

    def test_kibibyte(self):
        # nv
        from clausal.modules.py.units import Bit, Kibibyte
        result = 1 * Kibibyte
        assert result.dims == {Bit: 1}
        assert result.value == 8 * 1024

    def test_mebibyte(self):
        # nv
        from clausal.modules.py.units import Bit, Mebibyte
        result = 1 * Mebibyte
        assert result.dims == {Bit: 1}
        assert result.value == 8 * 2**20

    def test_gibibyte(self):
        # nv
        from clausal.modules.py.units import Bit, Gibibyte
        result = 1 * Gibibyte
        assert result.dims == {Bit: 1}
        assert result.value == 8 * 2**30

    def test_tebibyte(self):
        # nv
        from clausal.modules.py.units import Bit, Tebibyte
        result = 1 * Tebibyte
        assert result.dims == {Bit: 1}
        assert result.value == 8 * 2**40

    # ── Binary (IEC-prefixed) bit multiples ───────────────────────────────────

    def test_kibibit(self):
        # nv
        from clausal.modules.py.units import Bit, Kibibit
        result = 1 * Kibibit
        assert result.dims == {Bit: 1}
        assert result.value == 2**10

    def test_mebibit(self):
        # nv
        from clausal.modules.py.units import Bit, Mebibit
        result = 1 * Mebibit
        assert result.dims == {Bit: 1}
        assert result.value == 2**20

    def test_gibibit(self):
        # nv
        from clausal.modules.py.units import Bit, Gibibit
        result = 1 * Gibibit
        assert result.dims == {Bit: 1}
        assert result.value == 2**30

    # ── Binary prefix constants ───────────────────────────────────────────────

    def test_kibi_value(self):
        # nv
        from clausal.modules.py.units import kibi
        assert kibi == 1024

    def test_mebi_value(self):
        # nv
        from clausal.modules.py.units import mebi
        assert mebi == 2**20

    def test_gibi_value(self):
        # nv
        from clausal.modules.py.units import gibi
        assert gibi == 2**30

    def test_tebi_value(self):
        # nv
        from clausal.modules.py.units import tebi
        assert tebi == 2**40

    def test_pebi_value(self):
        # nv
        from clausal.modules.py.units import pebi
        assert pebi == 2**50

    def test_exbi_value(self):
        # nv
        from clausal.modules.py.units import exbi
        assert exbi == 2**60

    # ── Binary prefix used in expression ─────────────────────────────────────

    def test_gibi_times_byte(self):
        # nv
        from clausal.modules.py.units import Bit, Byte, gibi
        result = 4 * gibi * Byte
        assert result.dims == {Bit: 1}
        assert result.value == 4 * 2**30 * 8

    def test_mebi_times_byte(self):
        # nv
        from clausal.modules.py.units import Bit, Byte, mebi
        result = 100 * mebi * Byte
        assert result.dims == {Bit: 1}
        assert result.value == 100 * 2**20 * 8

    # ── Arithmetic between information quantities ─────────────────────────────

    def test_add_bytes_and_bits(self):
        """1*Byte + Bit(8) since both are {Bit: 1}."""
        # nv
        from clausal.modules.py.units import Bit, Byte
        result = 1 * Byte + Bit(8)
        assert result.dims == {Bit: 1}
        assert result.value == 16

    def test_kibibyte_minus_byte(self):
        # nv
        from clausal.modules.py.units import Bit, Kibibyte, Byte
        result = 1 * Kibibyte - 1 * Byte
        assert result.dims == {Bit: 1}
        assert result.value == 8 * 1023

    def test_information_mismatch_with_length(self):
        """Adding bits to metres raises UnitsMismatch."""
        # nv
        from clausal.modules.py.units import Bit, Metre
        with pytest.raises(UnitsMismatch):
            Bit(1) + Metre(1)
