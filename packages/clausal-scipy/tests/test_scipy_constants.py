"""Tests for clausal.modules.py.scipy_constants — physical constants.

Named constants are plain Quantity values; tests check value and dims directly.
CODATA lookup predicates (value, unit, precision, lookup, find, all_names) are
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
    value, unit, precision, lookup, find, all_names,
)
from clausal._suffixes import SEAM_SUFFIX
from clausal.logic.cells import chars


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
    gen = dispatch(None, None, None, None, *args, result, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


# ── Physical constants — type and value ───────────────────────────────────

class TestSpeedOfLight:
                                      # nv
    def test_is_quantity(self):       assert isinstance(SpeedOfLight, Quantity)
                                      # nv
    def test_value(self):             assert _val(SpeedOfLight) == pytest.approx(299792458.0)
    def test_dims(self):
        # nv
        assert _dims(SpeedOfLight) == {"metre": 1, "second": -1}


class TestPlanckConstant:
                                      # nv
    def test_is_quantity(self):       assert isinstance(PlanckConstant, Quantity)
                                      # nv
    def test_value(self):             assert _val(PlanckConstant) == pytest.approx(6.62607015e-34)
    def test_dims(self):
        # nv
        assert _dims(PlanckConstant) == {"kilogram": 1, "metre": 2, "second": -1}


class TestReducedPlanckConstant:
                                      # nv
    def test_is_quantity(self):       assert isinstance(ReducedPlanckConstant, Quantity)
    def test_value(self):
        # nv
        assert _val(ReducedPlanckConstant) == pytest.approx(_val(PlanckConstant) / (2 * math.pi))
    def test_dims(self):
        # nv
        assert _dims(ReducedPlanckConstant) == _dims(PlanckConstant)


class TestGravitationalConstant:
                                      # nv
    def test_is_quantity(self):       assert isinstance(GravitationalConstant, Quantity)
                                      # nv
    def test_value(self):             assert _val(GravitationalConstant) == pytest.approx(6.6743e-11)
    def test_dims(self):
        # nv
        assert _dims(GravitationalConstant) == {"metre": 3, "kilogram": -1, "second": -2}


class TestAvogadroConstant:
                                      # nv
    def test_is_quantity(self):       assert isinstance(AvogadroConstant, Quantity)
                                      # nv
    def test_value(self):             assert _val(AvogadroConstant) == pytest.approx(6.02214076e23)
    def test_dims(self):
        # nv
        assert _dims(AvogadroConstant) == {"mole": -1}


class TestBoltzmannConstant:
                                      # nv
    def test_is_quantity(self):       assert isinstance(BoltzmannConstant, Quantity)
                                      # nv
    def test_value(self):             assert _val(BoltzmannConstant) == pytest.approx(1.380649e-23)
    def test_dims(self):
        # nv
        assert _dims(BoltzmannConstant) == {
            "kilogram": 1, "metre": 2, "second": -2, "kelvin": -1}


class TestElementaryCharge:
                                      # nv
    def test_is_quantity(self):       assert isinstance(ElementaryCharge, Quantity)
                                      # nv
    def test_value(self):             assert _val(ElementaryCharge) == pytest.approx(1.602176634e-19)
    def test_dims(self):
        # nv
        assert _dims(ElementaryCharge) == {"ampere": 1, "second": 1}


class TestElectronMass:
                                      # nv
    def test_is_quantity(self):       assert isinstance(ElectronMass, Quantity)
                                      # nv
    def test_value(self):             assert _val(ElectronMass) == pytest.approx(9.1093837139e-31)
    def test_dims(self):
        # nv
        assert _dims(ElectronMass) == {"kilogram": 1}


class TestProtonMass:
                                      # nv
    def test_is_quantity(self):       assert isinstance(ProtonMass, Quantity)
                                      # nv
    def test_value(self):             assert _val(ProtonMass) == pytest.approx(1.67262192595e-27)
    def test_dims(self):
        # nv
        assert _dims(ProtonMass) == {"kilogram": 1}
    def test_heavier_than_electron(self):
        # nv
        assert _val(ProtonMass) > _val(ElectronMass)


class TestElectronVolt:
                                      # nv
    def test_is_quantity(self):       assert isinstance(ElectronVolt, Quantity)
                                      # nv
    def test_value(self):             assert _val(ElectronVolt) == pytest.approx(1.602176634e-19)
    def test_dims_are_energy(self):
        # nv
        assert _dims(ElectronVolt) == {"kilogram": 1, "metre": 2, "second": -2}
    def test_matches_elementary_charge_value(self):
        # nv
        assert _val(ElectronVolt) == pytest.approx(_val(ElementaryCharge))


class TestStandardAtmosphere:
                                      # nv
    def test_is_quantity(self):       assert isinstance(StandardAtmosphere, Quantity)
                                      # nv
    def test_value(self):             assert _val(StandardAtmosphere) == pytest.approx(101325.0)
    def test_dims_are_pressure(self):
        # nv
        assert _dims(StandardAtmosphere) == {"kilogram": 1, "metre": -1, "second": -2}


# ── SI prefix factors ─────────────────────────────────────────────────────

class TestPrefixes:
                          # nv
    def test_kilo(self):  assert Kilo  == pytest.approx(1e3)
                          # nv
    def test_mega(self):  assert Mega  == pytest.approx(1e6)
                          # nv
    def test_giga(self):  assert Giga  == pytest.approx(1e9)
    def test_are_floats(self):
        # nv
        assert isinstance(Kilo, float)
        assert isinstance(Mega, float)
        assert isinstance(Giga, float)


# ── CODATA lookup predicates ──────────────────────────────────────────────

class TestValuePredicate:
    def test_speed_of_light(self):
        # nv
        assert _drive_pred(value, "speed of light in vacuum") == pytest.approx(299792458.0)
    def test_unknown_fails(self):
        # nv
        assert _drive_pred(value, "not a real constant xyz") is None


class TestUnitPredicate:
    def test_speed_of_light_unit(self):
        # nv
        u = _drive_pred(unit, "speed of light in vacuum")
        assert u == chars("m s^-1")   # a unit is free-form text: a STRING


class TestPrecisionPredicate:
    def test_c_is_exact(self):
        # nv
        assert _drive_pred(precision, "speed of light in vacuum") == pytest.approx(0.0)
    def test_G_has_uncertainty(self):
        # nv
        assert _drive_pred(precision, "Newtonian constant of gravitation") > 0


class TestLookupPredicate:
    def test_returns_all_three(self):
        # nv
        v, u_str, unc = Var(), Var(), Var()
        dispatch = lookup._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, "electron mass", v, u_str, unc, trail)
        for parent, sentinel in gen:
            if sentinel is None:
                assert deref(v) == pytest.approx(9.1093837139e-31)
                assert deref(u_str) == chars("kg")   # the unit: a STRING
                assert deref(unc) >= 0
                break

    def test_unknown_fails(self):
        # nv
        v, u_str, unc = Var(), Var(), Var()
        dispatch = lookup._get_dispatch()
        trail = Trail()
        gen = dispatch(None, None, None, None, "not real xyz", v, u_str, unc, trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


class TestFindPredicate:
    def test_finds_electron_mass(self):
        # nv
        names = _drive_pred(find, "electron mass")
        assert "electron mass" in names

    def test_no_match_is_empty(self):
        # nv
        names = _drive_pred(find, "zzznomatch")
        assert names == []


class TestAllNamesPredicate:
    def test_returns_many(self):
        # nv
        names = _drive_pred(all_names)
        assert len(names) >= 300
    def test_contains_known(self):
        # nv
        names = _drive_pred(all_names)
        assert "Planck constant" in names


# ── .clausal fixture integration ──────────────────────────────────────────

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}{SEAM_SUFFIX}")
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
        # nv
        assert _succeeds("test", name, module=self.mod), f"Test({name!r}) failed"
