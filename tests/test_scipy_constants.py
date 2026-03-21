"""Tests for clausal.modules.py.scipy_constants — physical constants.

Named constants are plain Quantity values; tests check value and dims directly.
CODATA lookup predicates (Value, Unit, Precision, Lookup, Find, AllNames) are
tested separately via their predicate interface.
"""

import math
import os
import pytest

pytest.importorskip("scipy", reason="scipy not installed")

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.logic.solve import call
from clausal.import_hook import _load_module
from clausal.terms import Quantity
from clausal.modules.py import units as _u
from clausal.modules.py.scipy_constants import (
    SpeedOfLight, PlanckConstant, ReducedPlanckConstant,
    GravitationalConstant, AvogadroConstant, BoltzmannConstant,
    ElementaryCharge, ElectronMass, ProtonMass,
    ElectronVolt, StandardAtmosphere,
    Kilo, Mega, Giga,
    Value, Unit, Precision, Lookup, Find, AllNames,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _val(q):
    assert isinstance(q, Quantity), f"expected Quantity, got {type(q)}"
    return float(q.value)

def _dims(q):
    assert isinstance(q, Quantity)
    return q.dims

def _drive_pred(pred, *args):
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, *args, result, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


# ── Physical constants — type and value ───────────────────────────────────

class TestSpeedOfLight:
    def test_is_quantity(self):       assert isinstance(SpeedOfLight, Quantity)
    def test_value(self):             assert _val(SpeedOfLight) == pytest.approx(299792458.0)
    def test_dims(self):
        assert _dims(SpeedOfLight) == {_u.Metre: 1, _u.Second: -1}


class TestPlanckConstant:
    def test_is_quantity(self):       assert isinstance(PlanckConstant, Quantity)
    def test_value(self):             assert _val(PlanckConstant) == pytest.approx(6.62607015e-34)
    def test_dims(self):
        assert _dims(PlanckConstant) == {_u.Kilogram: 1, _u.Metre: 2, _u.Second: -1}


class TestReducedPlanckConstant:
    def test_is_quantity(self):       assert isinstance(ReducedPlanckConstant, Quantity)
    def test_value(self):
        assert _val(ReducedPlanckConstant) == pytest.approx(_val(PlanckConstant) / (2 * math.pi))
    def test_dims(self):
        assert _dims(ReducedPlanckConstant) == _dims(PlanckConstant)


class TestGravitationalConstant:
    def test_is_quantity(self):       assert isinstance(GravitationalConstant, Quantity)
    def test_value(self):             assert _val(GravitationalConstant) == pytest.approx(6.6743e-11)
    def test_dims(self):
        assert _dims(GravitationalConstant) == {_u.Metre: 3, _u.Kilogram: -1, _u.Second: -2}


class TestAvogadroConstant:
    def test_is_quantity(self):       assert isinstance(AvogadroConstant, Quantity)
    def test_value(self):             assert _val(AvogadroConstant) == pytest.approx(6.02214076e23)
    def test_dims(self):
        assert _dims(AvogadroConstant) == {_u.Mole: -1}


class TestBoltzmannConstant:
    def test_is_quantity(self):       assert isinstance(BoltzmannConstant, Quantity)
    def test_value(self):             assert _val(BoltzmannConstant) == pytest.approx(1.380649e-23)
    def test_dims(self):
        assert _dims(BoltzmannConstant) == {
            _u.Kilogram: 1, _u.Metre: 2, _u.Second: -2, _u.Kelvin: -1}


class TestElementaryCharge:
    def test_is_quantity(self):       assert isinstance(ElementaryCharge, Quantity)
    def test_value(self):             assert _val(ElementaryCharge) == pytest.approx(1.602176634e-19)
    def test_dims(self):
        assert _dims(ElementaryCharge) == {_u.Ampere: 1, _u.Second: 1}


class TestElectronMass:
    def test_is_quantity(self):       assert isinstance(ElectronMass, Quantity)
    def test_value(self):             assert _val(ElectronMass) == pytest.approx(9.1093837139e-31)
    def test_dims(self):
        assert _dims(ElectronMass) == {_u.Kilogram: 1}


class TestProtonMass:
    def test_is_quantity(self):       assert isinstance(ProtonMass, Quantity)
    def test_value(self):             assert _val(ProtonMass) == pytest.approx(1.67262192595e-27)
    def test_dims(self):
        assert _dims(ProtonMass) == {_u.Kilogram: 1}
    def test_heavier_than_electron(self):
        assert _val(ProtonMass) > _val(ElectronMass)


class TestElectronVolt:
    def test_is_quantity(self):       assert isinstance(ElectronVolt, Quantity)
    def test_value(self):             assert _val(ElectronVolt) == pytest.approx(1.602176634e-19)
    def test_dims_are_energy(self):
        assert _dims(ElectronVolt) == {_u.Kilogram: 1, _u.Metre: 2, _u.Second: -2}
    def test_matches_elementary_charge_value(self):
        assert _val(ElectronVolt) == pytest.approx(_val(ElementaryCharge))


class TestStandardAtmosphere:
    def test_is_quantity(self):       assert isinstance(StandardAtmosphere, Quantity)
    def test_value(self):             assert _val(StandardAtmosphere) == pytest.approx(101325.0)
    def test_dims_are_pressure(self):
        assert _dims(StandardAtmosphere) == {_u.Kilogram: 1, _u.Metre: -1, _u.Second: -2}


# ── SI prefix factors ─────────────────────────────────────────────────────

class TestPrefixes:
    def test_kilo(self):  assert Kilo  == pytest.approx(1e3)
    def test_mega(self):  assert Mega  == pytest.approx(1e6)
    def test_giga(self):  assert Giga  == pytest.approx(1e9)
    def test_are_floats(self):
        assert isinstance(Kilo, float)
        assert isinstance(Mega, float)
        assert isinstance(Giga, float)


# ── CODATA lookup predicates ──────────────────────────────────────────────

class TestValuePredicate:
    def test_speed_of_light(self):
        assert _drive_pred(Value, "speed of light in vacuum") == pytest.approx(299792458.0)
    def test_unknown_fails(self):
        assert _drive_pred(Value, "not a real constant xyz") is None


class TestUnitPredicate:
    def test_speed_of_light_unit(self):
        u = _drive_pred(Unit, "speed of light in vacuum")
        assert isinstance(u, str) and "m" in u


class TestPrecisionPredicate:
    def test_c_is_exact(self):
        assert _drive_pred(Precision, "speed of light in vacuum") == pytest.approx(0.0)
    def test_G_has_uncertainty(self):
        assert _drive_pred(Precision, "Newtonian constant of gravitation") > 0


class TestLookupPredicate:
    def test_returns_all_three(self):
        v, u_str, unc = Var(), Var(), Var()
        dispatch = Lookup._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, "electron mass", v, u_str, unc, trail)
        for parent, sentinel in gen:
            if sentinel is None:
                assert deref(v) == pytest.approx(9.1093837139e-31)
                assert isinstance(deref(u_str), str)
                assert deref(unc) >= 0
                break

    def test_unknown_fails(self):
        v, u_str, unc = Var(), Var(), Var()
        dispatch = Lookup._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, "not real xyz", v, u_str, unc, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


class TestFindPredicate:
    def test_finds_electron_mass(self):
        names = _drive_pred(Find, "electron mass")
        assert "electron mass" in names

    def test_no_match_is_empty(self):
        names = _drive_pred(Find, "zzznomatch")
        assert names == []


class TestAllNamesPredicate:
    def test_returns_many(self):
        names = _drive_pred(AllNames)
        assert len(names) >= 300
    def test_contains_known(self):
        names = _drive_pred(AllNames)
        assert "Planck constant" in names


# ── .clausal fixture integration ──────────────────────────────────────────

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestClausalFixture:
    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_constants_tests")

    @pytest.mark.parametrize("name", [
        "speed of light exact value",
        "speed of light units",
        "planck constant units",
        "planck constant magnitude",
        "reduced planck constant units",
        "hbar equals h over two pi",
        "gravitational constant units",
        "gravitational constant magnitude",
        "avogadro constant units",
        "avogadro constant magnitude",
        "boltzmann constant units",
        "boltzmann constant magnitude",
        "elementary charge units",
        "elementary charge magnitude",
        "electron mass units",
        "electron mass magnitude",
        "proton mass units",
        "proton heavier than electron",
        "electron volt units",
        "electron volt magnitude",
        "standard atmosphere units",
        "standard atmosphere exact value",
        "si kilo",
        "si mega",
        "si giga",
        "si prefixes consistent",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"
