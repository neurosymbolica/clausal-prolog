"""SI unit names are lowercase identifiers: ``metre``, ``second``, ``newton``.

The TitleCase spellings (``Metre``, ``Second``, ``Newton``, …) are superseded:
still accepted everywhere the lowercase name is, but they warn — once per
file from a ``-import_from(py.units, [...])`` list, once per process per
name from Python attribute access — and nothing in the library emits them
any more.  See ``todo/remove-deprecated-TitleCase-unit-names-after-migration-2026-09-09.md``.
"""

from __future__ import annotations

import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.modules import units
from clausal.terms import Quantity, UnitsMismatch
from clausal.templating.term_rewriting import ClausalDeprecatedSpellingWarning


def _load(name, src_text, tmp_path):
    path = tmp_path / f"{name}.clausal"
    path.write_text(src_text)
    return _load_module(name, str(path)).__dict__["$module"]


def _load_recording(name, src_text, tmp_path):
    """Load and return ``(module, deprecation warnings raised by the load)``."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = _load(name, src_text, tmp_path)
    return mod, [w for w in caught
                 if issubclass(w.category, ClausalDeprecatedSpellingWarning)]


def _one(mod, pred, *args):
    out = Var()
    got = [deref(out) for _ in call(pred, *args, out, module=mod)]
    assert len(got) == 1, got
    return got[0]


@pytest.fixture
def fresh_python_warnings():
    """Reset the once-per-process memo so each test observes its own warning."""
    units._warned_deprecated_unit_names.clear()
    yield
    units._warned_deprecated_unit_names.clear()


# ── The canonical spelling ───────────────────────────────────────────────────


class TestLowercaseNames:
    def test_python_constructor(self):
        """# nv"""
        assert units.metre(5) == Quantity(5, {units.metre: 1})
        assert units.newton(9.8) == Quantity(
            9.8, {units.kilogram: 1, units.metre: 1, units.second: -2})

    def test_every_unit_is_lowercase(self):
        """No TitleCase unit predicate or unit-vector constant is defined.

        The physical constants (``SpeedOfLight``, …) and the ``SI_*`` unit
        vectors are Quantity values too, but they are not unit names; their
        spelling is a separate question and they are pinned here as-is so
        this test shrinks, not grows, when that is settled.
        """
        # nv
        parked = {
            "SpeedOfLight", "PlanckConstant", "ReducedPlanck",
            "BoltzmannConstant", "AvogadroConstant", "ElementaryCharge",
            "StandardGravity", "GravitationalConstant", "AtomicMassUnit",
            "ElectronMass", "ProtonMass", "VacuumPermeability",
            "VacuumPermittivity", "StefanBoltzmann",
        }
        titlecase = {
            n for n, v in vars(units).items()
            if isinstance(v, (units._UnitsPredicate, Quantity))
            and n[:1].isupper() and not n.startswith("SI_")
        }
        assert titlecase == parked

    def test_sugar_builds_the_same_quantity(self, tmp_path):
        """5(metre) is the Quantity Metre(5) used to build."""
        # nv
        mod = _load("lc_sugar", (
            "-import_from(py.units, [metre])\n"
            "q(D) <- eval_(5(metre), D)\n"), tmp_path)
        assert _one(mod, "q") == Quantity(5, {units.metre: 1})

    def test_compound_sugar_and_has_units(self, tmp_path):
        """# nv"""
        mod = _load("lc_compound", (
            "-import_from(py.units, [metre, second, kilogram, newton])\n"
            "q(F) <- (F is 9.8(kilogram*metre/second**2), has_units(F, newton))\n"
        ), tmp_path)
        assert _one(mod, "q") == units.newton(9.8)

    def test_does_not_warn(self, tmp_path):
        """# nv"""
        _, warned = _load_recording("lc_quiet", (
            "-import_from(py.units, [metre, second, byte, kilometer])\n"
            "q(D) <- eval_(5(metre), D)\n"), tmp_path)
        assert warned == []

    def test_dimension_arithmetic(self):
        """# nv"""
        derived = units.kilogram * units.metre / units.second ** 2
        assert derived._dims == units.newton._dims
        assert (units.joule / units.second)._dims == units.watt._dims

    def test_symbol_aliases_are_the_lowercase_objects(self):
        """# nv"""
        assert units.m is units.metre
        assert units.kg is units.kilogram
        assert units.s is units.second
        assert units.km is units.kilometer
        assert units.min is units.minute
        assert units.hr is units.hour

    def test_star_import_module_exports_lowercase(self):
        """# nv"""
        from clausal.modules.py import units as py_units
        assert py_units.metre is units.metre
        assert py_units.newton is units.newton


# ── Printing: the label follows the identifier ───────────────────────────────


class TestPrintedLabel:
    def test_str_base(self):
        """# nv"""
        assert str(units.metre(5)) == "5 metre"

    def test_str_derived_lists_base_units(self):
        """# nv"""
        assert str(units.newton(9.8)) == "9.8 kilogram·metre·second^-2"

    def test_repr_uses_lowercase_key(self):
        """# nv"""
        assert repr(units.metre) == "units.metre/[]"

    def test_write_in_clausal(self, tmp_path):
        """# nv"""
        mod = _load("lc_write", (
            "-import_from(py.units, [metre, second])\n"
            "q(S) <- (V is 10(metre/second), S is ++(str(V)))\n"), tmp_path)
        got = _one(mod, "q")
        assert str(got) == "10 metre·second^-1"

    def test_mismatch_message_names_lowercase_units(self):
        """# nv"""
        with pytest.raises(UnitsMismatch) as exc:
            units.metre(1) + units.second(1)
        msg = str(exc.value)
        assert "metre" in msg and "second" in msg
        assert "Metre" not in msg and "Second" not in msg


# ── The superseded TitleCase spelling ────────────────────────────────────────


class TestTitleCaseAliases:
    def test_alias_table_is_complete(self):
        """Every entry names a real lowercase unit; every unit has an entry."""
        # nv
        table = units._DEPRECATED_UNIT_NAMES
        for old, new in table.items():
            assert old[:1].isupper(), old
            assert new == new.lower(), new
            assert getattr(units, new) is not None
        lower_units = {
            n for n, v in vars(units).items()
            if isinstance(v, (units._UnitsPredicate, Quantity))
            and n == n.lower() and len(n) > 3
            and not v is units.dimension_of
        }
        expected = {"dimension_of", "strip_units", "make_quantity", "has_units"}
        assert lower_units - set(table.values()) - expected == set()

    def test_python_attribute_still_works_and_warns_once(
            self, fresh_python_warnings):
        """# nv"""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            first = units.Metre
            second = units.Metre
        assert first is units.metre and second is units.metre
        hits = [w for w in caught
                if issubclass(w.category, ClausalDeprecatedSpellingWarning)]
        assert len(hits) == 1
        assert "`Metre` -> `metre`" in str(hits[0].message)

    def test_python_from_import_via_py_units(self, fresh_python_warnings):
        """# nv"""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from clausal.modules.py.units import Newton  # noqa: PLC0415
        assert Newton is units.newton
        assert any(issubclass(w.category, ClausalDeprecatedSpellingWarning)
                   for w in caught)

    def test_unknown_attribute_still_raises(self):
        """# nv"""
        with pytest.raises(AttributeError):
            units.NoSuchUnit  # noqa: B018

    def test_deprecated_alias_is_the_same_object(self, fresh_python_warnings):
        """A Quantity built through the old name is EQUAL to the new one."""
        # nv
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ClausalDeprecatedSpellingWarning)
            assert units.Metre(5) == units.metre(5)
            assert units.Kilometer is units.kilometer
            assert units.Byte is units.byte

    def test_sugar_still_works(self, tmp_path):
        """# nv"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ClausalDeprecatedSpellingWarning)
            mod = _load("tc_sugar", (
                "-import_from(py.units, [Metre, Second])\n"
                "q(D) <- eval_(5(Metre/Second), D)\n"), tmp_path)
        assert _one(mod, "q") == Quantity(5, {units.metre: 1, units.second: -1})

    def test_warns_exactly_once_per_file_naming_the_rename(self, tmp_path):
        """# nv"""
        _, warned = _load_recording("tc_warn", (
            "-import_from(py.units, [Metre, Second, strip_units])\n"
            "a(D) <- eval_(5(Metre), D)\n"
            "b(D) <- eval_(6(Metre), D)\n"
            "c(D) <- eval_(7(Second), D)\n"), tmp_path)
        assert len(warned) == 1
        msg = str(warned[0].message)
        assert "tc_warn.clausal:1" in msg
        assert "`Metre` -> `metre`" in msg
        assert "`Second` -> `second`" in msg
        assert "will be removed" in msg

    def test_warns_once_per_file_not_once_per_process(self, tmp_path):
        """A second file loading the same old name warns again."""
        # nv
        src = ("-import_from(py.units, [Metre])\n"
               "q(D) <- eval_(5(Metre), D)\n")
        _, first = _load_recording("tc_twice_a", src, tmp_path)
        _, second = _load_recording("tc_twice_b", src, tmp_path)
        assert len(first) == 1 and len(second) == 1

    def test_alias_form_warns(self, tmp_path):
        """# nv"""
        _, warned = _load_recording("tc_alias", (
            "-import_from(py.units, [alias(Metre, metres)])\n"
            "q(D) <- eval_(5(metres), D)\n"), tmp_path)
        assert len(warned) == 1
        assert "`Metre` -> `metre`" in str(warned[0].message)

    def test_only_the_units_module_is_linted(self, tmp_path, monkeypatch):
        """A same-named import from another module is not a unit rename."""
        # nv
        monkeypatch.syspath_prepend(str(tmp_path))
        (tmp_path / "otherunits.py").write_text("Metre = 1\n")
        _, warned = _load_recording("tc_other", (
            "-import_from(otherunits, [Metre])\n"
            "q(1),\n"), tmp_path)
        assert [w for w in warned if "metre" in str(w.message)] == []
