"""scipy_constants exports its constants under lower_snake_case names.

The module exported ``SpeedOfLight``, ``PlanckConstant``, ... ``Pi``,
``Kilo``, ``Mega``, ``Giga`` -- TitleCase, which reads as a logic variable
and has no role in a Clausal position.  ``-import_from`` exempts a TitleCase
name from its variable check, so nothing caught it.  They are renamed to
``scipy_speed_of_light``, ... with NO aliases (docs/RENAMES.md); the
``scipy_`` prefix keeps every name apart from an engine name (``py.units``
has exact ``speed_of_light``, ``kilo``, ...; ``pi`` is an arithmetic
constant and a sympy name).
"""

from __future__ import annotations

import os
import pathlib
import re

import pytest

pytest.importorskip("scipy", reason="scipy not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.solve import call, module_signatures, _deref_walk
from clausal.logic.variables import Var
from clausal.modules import units as engine_units
from clausal.modules.py import scipy_constants as sc
from clausal.terms import Quantity

RENAMES = {
    "SpeedOfLight": "scipy_speed_of_light",
    "PlanckConstant": "scipy_planck_constant",
    "ReducedPlanckConstant": "scipy_reduced_planck_constant",
    "GravitationalConstant": "scipy_gravitational_constant",
    "AvogadroConstant": "scipy_avogadro_constant",
    "BoltzmannConstant": "scipy_boltzmann_constant",
    "ElementaryCharge": "scipy_elementary_charge",
    "ElectronMass": "scipy_electron_mass",
    "ProtonMass": "scipy_proton_mass",
    "ElectronVolt": "scipy_electron_volt",
    "StandardAtmosphere": "scipy_standard_atmosphere",
    "Pi": "scipy_pi",
    "Kilo": "scipy_kilo",
    "Mega": "scipy_mega",
    "Giga": "scipy_giga",
}

_FLOATS = {"scipy_pi", "scipy_kilo", "scipy_mega", "scipy_giga"}

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.mark.parametrize("old,new", sorted(RENAMES.items()))
def test_renamed_with_no_alias(old, new):
    value = getattr(sc, new)
    assert isinstance(value, float if new in _FLOATS else Quantity)
    assert not hasattr(sc, old), f"{old} is still exported (no aliases)"


def test_no_titlecase_constant_remains():
    # (TitleCase IMPORTS -- Callable, DONE, ModulePredicate -- are Python
    # names the module uses, not constants it offers)
    left = [n for n, v in vars(sc).items()
            if n[:1].isupper() and isinstance(v, (Quantity, float, int))]
    assert left == [], left


def test_new_names_collide_with_nothing():
    new = set(RENAMES.values())
    # the module's own predicates
    assert not new & set(module_signatures(sc))
    # the engine's units and constants (the units module's globals and the
    # retired spellings it still serves through __getattr__)
    assert not new & set(vars(engine_units))
    assert not new & set(engine_units._DEPRECATED_UNIT_NAMES)
    # the engine's builtin predicates
    from clausal.logic.builtins._registry import _BUILTINS
    assert not new & {name for (name, _arity) in _BUILTINS}


_SRC = """\
-import_from(scipy_constants, [scipy_speed_of_light, scipy_pi, scipy_kilo, value])

c_value(C) <- (C is scipy_speed_of_light)
c_escape(C) <- (C is ++scipy_speed_of_light)
pi_value(P) <- (P is scipy_pi)
kilo_value(K) <- (K is scipy_kilo)
c_matches_codata() <- (value('speed of light in vacuum', L), C is ++scipy_speed_of_light.value, C == L)
"""


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    src = tmp_path_factory.mktemp("scnames") / f"scipy_names_probe{SEAM_SUFFIX}"
    src.write_text(_SRC, encoding="utf-8")
    return _load_module("scipy_names_probe", str(src)).__dict__["$module"]


def _one(module, name):
    out = Var()
    [got] = [_deref_walk(out) for _ in call(name, out, module=module)]
    return got


def test_imported_by_the_new_names(probe):
    assert _one(probe, "c_value") is sc.scipy_speed_of_light
    assert _one(probe, "c_escape") is sc.scipy_speed_of_light
    assert _one(probe, "pi_value") == pytest.approx(3.141592653589793)
    assert _one(probe, "kilo_value") == pytest.approx(1000.0)
    assert any(True for _ in call("c_matches_codata", module=probe))


def _fixture_cases(rel):
    src = pathlib.Path(_FIXTURES, rel + SEAM_SUFFIX).read_text(encoding="utf-8")
    return re.findall(r'^test\("([^"]+)"\)', src, re.M)


@pytest.mark.parametrize("name", _fixture_cases(os.path.join("docs", "scipy_constants_sig_tests")))
def test_doc_sig_tests_fixture(name):
    mod = _load_module("scipy_constants_sig_tests_probe",
                       os.path.join(_FIXTURES, "docs", "scipy_constants_sig_tests" + SEAM_SUFFIX))
    assert any(True for _ in call("test", name, module=mod.__dict__["$module"])), name


def _example_block():
    text = pathlib.Path(_FIXTURES, "docs", "scipy_constants_sigs.txt").read_text(
        encoding="utf-8")
    return re.search(r"--8<-- \[start:example\]\n(.*?)--8<-- \[end:example\]",
                     text, re.S).group(1)


def test_doc_example_runs(tmp_path):
    src = tmp_path / f"scipy_constants_example{SEAM_SUFFIX}"
    src.write_text(_example_block(), encoding="utf-8")
    mod = _load_module("scipy_constants_example", str(src)).__dict__["$module"]
    kt = _one(mod, "thermal_energy")
    assert isinstance(kt, Quantity) and float(kt.value) == pytest.approx(4.14e-21, rel=1e-2)
    assert any(True for _ in call("check_c", module=mod))
    assert _one(mod, "planck_unit") == chars("J Hz^-1")
