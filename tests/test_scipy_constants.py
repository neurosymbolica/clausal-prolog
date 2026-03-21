"""Tests for clausal.modules.py.scipy_constants — scipy.constants predicates.

Tests cover:
- CODATA lookup predicates: Value, Unit, Precision
- Physical constant predicates (zero-input): SpeedOfLight, PlanckConstant,
  ReducedPlanckConstant, GravitationalConstant, AvogadroConstant,
  BoltzmannConstant, ElementaryCharge, ElectronMass, ProtonMass
- Conversion / SI prefix factors: ElectronVolt, StandardAtmosphere,
  Kilo, Mega, Giga
- Unification succeeds when RESULT is unbound
- Unification fails when RESULT is bound to an incorrect value
- .clausal fixture integration
"""

import math
import os
import pytest

pytest.importorskip("scipy", reason="scipy not installed")

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.logic.solve import call
from clausal.import_hook import _load_module
from clausal.modules.py.scipy_constants import (
    Value, Unit, Precision, Lookup, Find, AllNames,
    SpeedOfLight, PlanckConstant, ReducedPlanckConstant,
    GravitationalConstant, AvogadroConstant, BoltzmannConstant,
    ElementaryCharge, ElectronMass, ProtonMass,
    ElectronVolt, StandardAtmosphere,
    Kilo, Mega, Giga,
)


# ── Test drivers ──────────────────────────────────────────────────────────

def _drive(pred, *args):
    """Call predicate with a fresh Var as RESULT; return first solution value."""
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


def _fails_when_bound_wrong(pred, *inputs):
    """Return True when predicate yields no solutions for a wrong RESULT."""
    trail = Trail()
    wrong = object()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, *inputs, wrong, trail)
    solutions = [s for s in gen if s[1] is None]
    return len(solutions) == 0


# ── CODATA lookup — Value ─────────────────────────────────────────────────

class TestValue:
    def test_speed_of_light(self):
        v = _drive(Value, "speed of light in vacuum")
        assert v == pytest.approx(299792458.0)

    def test_planck_constant(self):
        v = _drive(Value, "Planck constant")
        assert v == pytest.approx(6.62607015e-34)

    def test_boltzmann_constant(self):
        v = _drive(Value, "Boltzmann constant")
        assert v == pytest.approx(1.380649e-23)

    def test_elementary_charge(self):
        v = _drive(Value, "elementary charge")
        assert v == pytest.approx(1.602176634e-19)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(Value, "speed of light in vacuum")

    def test_unknown_name_fails(self):
        # scipy raises KeyError for unknown names → predicate should fail
        result = _drive(Value, "not a real constant name xyz")
        assert result is None


# ── CODATA lookup — Unit ──────────────────────────────────────────────────

class TestUnit:
    def test_speed_of_light_unit(self):
        u = _drive(Unit, "speed of light in vacuum")
        assert isinstance(u, str)
        assert "m" in u

    def test_planck_constant_unit(self):
        u = _drive(Unit, "Planck constant")
        assert isinstance(u, str)
        assert "J" in u

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(Unit, "speed of light in vacuum")


# ── CODATA lookup — Precision ─────────────────────────────────────────────

class TestPrecision:
    def test_speed_of_light_precision(self):
        # c is exact in SI since 2019; uncertainty is 0
        p = _drive(Precision, "speed of light in vacuum")
        assert p == pytest.approx(0.0)

    def test_gravitational_constant_precision(self):
        # G has a small but non-zero uncertainty
        p = _drive(Precision, "Newtonian constant of gravitation")
        assert p > 0

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(Precision, "speed of light in vacuum")


# ── Lookup ────────────────────────────────────────────────────────────────

def _drive_lookup(name):
    """Call Lookup(NAME, VALUE, UNIT, UNCERTAINTY); return (value, unit, uncertainty)."""
    v, u, p = Var(), Var(), Var()
    dispatch = Lookup._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, name, v, u, p, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(v), deref(u), deref(p)
    return None


class TestLookup:
    def test_speed_of_light(self):
        result = _drive_lookup("speed of light in vacuum")
        assert result is not None
        val, unit, uncertainty = result
        assert val == pytest.approx(299792458.0)
        assert "m" in unit
        assert uncertainty == pytest.approx(0.0)

    def test_gravitational_constant(self):
        result = _drive_lookup("Newtonian constant of gravitation")
        assert result is not None
        val, unit, uncertainty = result
        assert val == pytest.approx(6.6743e-11)
        assert uncertainty > 0

    def test_matches_value_unit_precision(self):
        name = "Planck constant"
        result = _drive_lookup(name)
        assert result is not None
        val, unit, uncertainty = result
        assert val == pytest.approx(_drive(Value, name))
        assert unit == _drive(Unit, name)
        # precision is relative; uncertainty is absolute
        assert uncertainty >= 0

    def test_unknown_name_fails(self):
        result = _drive_lookup("not a real constant name xyz")
        assert result is None

    def test_wrong_value_binding_fails(self):
        trail = Trail()
        dispatch = Lookup._get_dispatch()
        gen = dispatch(None, None, "speed of light in vacuum",
                       object(), Var(), Var(), trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── Find ──────────────────────────────────────────────────────────────────

def _drive_find(substring):
    names = Var()
    dispatch = Find._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, substring, names, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(names)
    return None


class TestFind:
    def test_electron_mass_substring(self):
        names = _drive_find("electron mass")
        assert names is not None
        assert isinstance(names, list)
        assert "electron mass" in names
        assert len(names) > 1  # several entries contain this substring

    def test_proton_substring(self):
        names = _drive_find("proton mass")
        assert names is not None
        assert "proton mass" in names

    def test_empty_substring_returns_all(self):
        names = _drive_find("")
        assert names is not None
        assert len(names) >= 300  # all constants (count varies by scipy version)

    def test_no_match_returns_empty_list(self):
        names = _drive_find("zzznomatchzzz")
        assert names == []

    def test_wrong_result_fails(self):
        trail = Trail()
        dispatch = Find._get_dispatch()
        gen = dispatch(None, None, "electron mass", object(), trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── AllNames ──────────────────────────────────────────────────────────────

def _drive_all_names():
    names = Var()
    dispatch = AllNames._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, names, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(names)
    return None


class TestAllNames:
    def test_returns_list(self):
        names = _drive_all_names()
        assert isinstance(names, list)

    def test_count(self):
        names = _drive_all_names()
        # scipy 1.x ships 300–500 CODATA constants depending on version
        assert len(names) >= 300

    def test_known_names_present(self):
        names = _drive_all_names()
        assert "electron mass" in names
        assert "speed of light in vacuum" in names
        assert "Planck constant" in names
        assert "Boltzmann constant" in names

    def test_all_are_strings(self):
        names = _drive_all_names()
        assert all(isinstance(n, str) for n in names)

    def test_wrong_result_fails(self):
        trail = Trail()
        dispatch = AllNames._get_dispatch()
        gen = dispatch(None, None, object(), trail)
        solutions = [s for s in gen if s[1] is None]
        assert len(solutions) == 0


# ── Physical constants ────────────────────────────────────────────────────

class TestSpeedOfLight:
    def test_value(self):
        v = _drive(SpeedOfLight)
        assert v == pytest.approx(299792458.0)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(SpeedOfLight)


class TestPlanckConstant:
    def test_value(self):
        v = _drive(PlanckConstant)
        assert v == pytest.approx(6.62607015e-34)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(PlanckConstant)


class TestReducedPlanckConstant:
    def test_value(self):
        hbar = _drive(ReducedPlanckConstant)
        h = _drive(PlanckConstant)
        assert hbar == pytest.approx(h / (2 * math.pi))

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(ReducedPlanckConstant)


class TestGravitationalConstant:
    def test_value(self):
        v = _drive(GravitationalConstant)
        assert v == pytest.approx(6.6743e-11)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(GravitationalConstant)


class TestAvogadroConstant:
    def test_value(self):
        v = _drive(AvogadroConstant)
        assert v == pytest.approx(6.02214076e+23)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(AvogadroConstant)


class TestBoltzmannConstant:
    def test_value(self):
        v = _drive(BoltzmannConstant)
        assert v == pytest.approx(1.380649e-23)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(BoltzmannConstant)


class TestElementaryCharge:
    def test_value(self):
        v = _drive(ElementaryCharge)
        assert v == pytest.approx(1.602176634e-19)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(ElementaryCharge)


class TestElectronMass:
    def test_value(self):
        v = _drive(ElectronMass)
        assert v == pytest.approx(9.1093837139e-31)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(ElectronMass)


class TestProtonMass:
    def test_value(self):
        v = _drive(ProtonMass)
        assert v == pytest.approx(1.67262192595e-27)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(ProtonMass)


# ── Conversion / SI prefix factors ────────────────────────────────────────

class TestElectronVolt:
    def test_value(self):
        v = _drive(ElectronVolt)
        assert v == pytest.approx(1.602176634e-19)

    def test_matches_elementary_charge(self):
        # By definition, 1 eV = e * 1 V = elementary charge in joules
        ev = _drive(ElectronVolt)
        e = _drive(ElementaryCharge)
        assert ev == pytest.approx(e)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(ElectronVolt)


class TestStandardAtmosphere:
    def test_value(self):
        v = _drive(StandardAtmosphere)
        assert v == pytest.approx(101325.0)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(StandardAtmosphere)


class TestKilo:
    def test_value(self):
        assert _drive(Kilo) == pytest.approx(1e3)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(Kilo)


class TestMega:
    def test_value(self):
        assert _drive(Mega) == pytest.approx(1e6)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(Mega)


class TestGiga:
    def test_value(self):
        assert _drive(Giga) == pytest.approx(1e9)

    def test_wrong_result_fails(self):
        assert _fails_when_bound_wrong(Giga)


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
    """Run Test predicates from tests/fixtures/scipy_constants_tests.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_constants_tests")

    @pytest.mark.parametrize("name", [
        "value lookup matches direct constant",
        "unit string for speed of light",
        "precision of speed of light is zero",
        "hbar equals h over two pi",
        "boltzmann constant magnitude",
        "avogadro constant order of magnitude",
        "elementary charge equals electron volt",
        "standard atmosphere value",
        "si prefixes consistent",
        "gravitational constant is positive and small",
        "proton heavier than electron",
        "lookup value matches value predicate",
        "lookup unit matches unit predicate",
        "find electron mass substring",
        "all names has many entries",
        "all names contains planck constant",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod), f"Test({name!r}) failed"
