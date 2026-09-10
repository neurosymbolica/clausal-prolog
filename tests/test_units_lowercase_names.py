"""SI unit names are lowercase identifiers: ``metre``, ``second``, ``newton``.

The TitleCase spellings (``Metre``, ``Second``, ``Newton``, ``SpeedOfLight``)
and the American length family (``kilometer``) are superseded:
still accepted everywhere the lowercase name is, but they warn — once per
file from a ``-import_from(py.units, [...])`` list, once per process per
name from Python attribute access — and nothing in the library emits them
any more.  See ``todo/remove-deprecated-TitleCase-unit-names-after-migration-2026-09-09.md``.
"""

from __future__ import annotations

import subprocess
import sys
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.modules import units
from clausal.terms import Quantity, UnitsMismatch
from clausal.lint_warnings import ClausalDeprecatedSpellingWarning


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

    def test_no_titlecase_exports(self):
        """No TitleCase unit predicate, unit vector or physical constant."""
        # nv
        titlecase = {
            n for n, v in vars(units).items()
            if isinstance(v, (units._UnitsPredicate, Quantity))
            and n[:1].isupper() and not n.startswith("SI_")
        }
        assert titlecase == set()

    def test_no_american_metre_exports(self):
        """The length family is spelled like ``metre``: ``kilometre``."""
        # nv
        american = {n for n in vars(units) if n.endswith("meter")}
        assert american == set()

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
            "-import_from(py.units, [metre, second, byte, kilometre])\n"
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
        assert units.km is units.kilometre
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
    def test_bare_titlecase_unit_name_is_a_variable_and_only_fails_at_query(
            self):
        """The deprecation-window witness, and the one DIAGNOSTIC LOSS of the
        2026-09-10 TitleCase-is-a-variable change -- asserted here so it
        cannot change unnoticed, and so the cost is visible if anyone wants
        it back.

        A TitleCase unit name used BARE (outside an ``-import_from`` list,
        where the alias still resolves) sits in a unit-annotation ARGUMENT.
        That is a TERM position, so it now reads as a logic variable: the
        file LOADS, and the retired spelling surfaces only when the clause
        runs, as a plain ``NameError`` out of the Python the unit sugar
        embeds -- naming neither the rename nor the deprecation.  It used to
        be a located load-time SyntaxError saying
        ``Rename `Metre` -> `metre```.

        Restoring the old diagnostic would mean teaching the lint to read
        unit-annotation arguments specifically; nothing rules that today, so
        the behaviour is pinned rather than special-cased.

        Fixture: tests/fixtures/titlecase_unit_spelling_witness.clausal."""
        import pathlib
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        from clausal.logic.variables import Var
        p = (pathlib.Path(__file__).parent / "fixtures"
             / "titlecase_unit_spelling_witness.clausal")
        mod = _load_module("_titlecase_unit_witness", str(p))  # loads now
        with pytest.raises(NameError) as ei:
            list(call("speed", Var(), module=mod.__dict__["$module"]))
        assert "Metre" in str(ei.value)

    def test_the_supported_import_list_spelling_still_resolves_and_warns(
            self, tmp_path):
        """The other half, and the one that matters for real files: the
        retired spelling in an ``-import_from`` list is untouched -- it still
        binds, still resolves at the use site, and still names the rename."""
        import textwrap
        from clausal.import_hook import _load_module
        path = tmp_path / "tc_unit_ok.clausal"
        path.write_text(textwrap.dedent("""
            -import_from(py.units, [Metre])
            -module(tc_unit_ok, [speed(X)])
            speed(X) <- (X is 5.0(Metre))
        """).lstrip())
        with warnings.catch_warnings(record=True) as rec:
            warnings.simplefilter("always")
            _load_module("_titlecase_unit_import_ok", str(path))
        assert any("Metre" in str(w.message) and "metre" in str(w.message)
                   for w in rec), [str(w.message) for w in rec]

    def test_alias_table_is_complete(self):
        """Every entry names a real lowercase unit; every unit has an entry."""
        # nv
        table = units._DEPRECATED_UNIT_NAMES
        for old, new in table.items():
            assert old != new and new == new.lower(), (old, new)
            assert old not in vars(units), old      # resolved only by alias
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
            assert units.Kilometer is units.kilometre
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

    @pytest.mark.parametrize("module_path", [
        "units", "py.units", "clausal.modules.units", "clausal.modules.py.units",
    ])
    def test_warns_once_per_file_under_every_module_path(self, tmp_path,
                                                          module_path):
        """Each spelling of the units module path is linted the same way."""
        # nv
        name = "tc_path_" + module_path.replace(".", "_")
        mod, warned = _load_recording(name, (
            f"-import_from({module_path}, [Metre])\n"
            "q(D) <- eval_(5(Metre), D)\n"), tmp_path)
        assert len(warned) == 1, module_path
        assert "`Metre` -> `metre`" in str(warned[0].message)
        assert _one(mod, "q") == Quantity(5, {units.metre: 1})

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


# ── Physical constants: snake_case ───────────────────────────────────────────


class TestPhysicalConstants:
    def test_snake_case_names(self):
        """# nv"""
        assert units.speed_of_light.value == 299_792_458
        assert units.speed_of_light.dims == units.SI_Velocity.dims
        assert units.planck_constant.dims == (units.SI_Energy * units.second(1)).dims
        for name in ("reduced_planck", "boltzmann_constant", "avogadro_constant",
                     "elementary_charge", "standard_gravity",
                     "gravitational_constant", "atomic_mass_unit",
                     "electron_mass", "proton_mass", "vacuum_permeability",
                     "vacuum_permittivity", "stefan_boltzmann"):
            assert isinstance(getattr(units, name), Quantity), name

    def test_python_alias_warns_once(self, fresh_python_warnings):
        """# nv"""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            first = units.SpeedOfLight
            second = units.SpeedOfLight
        assert first is units.speed_of_light and second is units.speed_of_light
        hits = [w for w in caught
                if issubclass(w.category, ClausalDeprecatedSpellingWarning)]
        assert len(hits) == 1
        assert "`SpeedOfLight` -> `speed_of_light`" in str(hits[0].message)

    def test_clausal_import_new_name(self, tmp_path):
        """# nv"""
        mod, warned = _load_recording("pc_new", (
            "-import_from(py.units, [speed_of_light, standard_gravity])\n"
            "q(V) <- (V is ++(speed_of_light))\n"
            "g(A) <- (A is ++(2 * standard_gravity))\n"), tmp_path)
        assert warned == []
        assert _one(mod, "q") == units.speed_of_light
        assert _one(mod, "g") == 2 * units.standard_gravity

    def test_clausal_import_old_name_warns_once(self, tmp_path):
        """# nv"""
        mod, warned = _load_recording("pc_old", (
            "-import_from(py.units, [SpeedOfLight, StandardGravity])\n"
            "q(V) <- (V is ++(SpeedOfLight))\n"
            "g(A) <- (A is ++(StandardGravity))\n"), tmp_path)
        assert len(warned) == 1
        msg = str(warned[0].message)
        assert "`SpeedOfLight` -> `speed_of_light`" in msg
        assert "`StandardGravity` -> `standard_gravity`" in msg
        assert _one(mod, "q") == units.speed_of_light
        assert _one(mod, "g") == units.standard_gravity


# ── The length family is spelled like metre ──────────────────────────────────


class TestBritishSpelling:
    def test_metre_family(self):
        """# nv"""
        assert units.kilometre == Quantity(1_000, {units.metre: 1})
        assert units.centimetre == Quantity(1e-2, {units.metre: 1})
        assert units.millimetre == Quantity(1e-3, {units.metre: 1})
        assert units.micrometre == Quantity(1e-6, {units.metre: 1})
        assert units.nanometre == Quantity(1e-9, {units.metre: 1})
        assert units.km is units.kilometre
        assert units.cm is units.centimetre
        assert units.mm is units.millimetre
        assert units.um is units.micrometre
        assert units.nm is units.nanometre

    def test_printed_label_is_the_base_unit(self):
        """A scaled length carries no label of its own: it prints in metre."""
        # nv
        assert str(5 * units.kilometre) == "5000 metre"

    def test_american_python_alias_warns_once(self, fresh_python_warnings):
        """# nv"""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            a = units.kilometer
            b = units.kilometer
        assert a is units.kilometre and b is units.kilometre
        hits = [w for w in caught
                if issubclass(w.category, ClausalDeprecatedSpellingWarning)]
        assert len(hits) == 1
        assert "`kilometer` -> `kilometre`" in str(hits[0].message)

    def test_titlecase_american_resolves_to_british(self, fresh_python_warnings):
        """# nv"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ClausalDeprecatedSpellingWarning)
            assert units.Kilometer is units.kilometre
            assert units.Nanometer is units.nanometre

    def test_clausal_import_british(self, tmp_path):
        """# nv"""
        mod, warned = _load_recording("br_new", (
            "-import_from(py.units, [kilometre, centimetre])\n"
            "q(D) <- eval_(5(kilometre), D)\n"
            "c(D) <- eval_(200(centimetre), D)\n"), tmp_path)
        assert warned == []
        assert _one(mod, "q") == Quantity(5000, {units.metre: 1})
        assert _one(mod, "c") == 200 * units.centimetre

    def test_clausal_import_american_warns_once(self, tmp_path):
        """# nv"""
        mod, warned = _load_recording("br_old", (
            "-import_from(py.units, [kilometer, Centimeter])\n"
            "q(D) <- eval_(5(kilometer), D)\n"
            "c(D) <- eval_(200(Centimeter), D)\n"), tmp_path)
        assert len(warned) == 1
        msg = str(warned[0].message)
        assert "`kilometer` -> `kilometre`" in msg
        assert "`Centimeter` -> `centimetre`" in msg
        assert _one(mod, "q") == Quantity(5000, {units.metre: 1})
        assert _one(mod, "c") == 200 * units.centimetre


# ── The Python-side alias is cheap and points at the caller ──────────────────


class TestPythonAliasCost:
    def test_warning_class_is_shared_with_the_seam(self):
        """# nv"""
        from clausal.templating import term_rewriting  # noqa: PLC0415
        assert (term_rewriting.ClausalDeprecatedSpellingWarning
                is ClausalDeprecatedSpellingWarning)

    def test_alias_access_does_not_import_the_seam(self):
        """`units.Metre` from plain Python must not pull the rewriter in."""
        # nv
        code = (
            "import sys, warnings\n"
            "import clausal.modules.units as u\n"
            "with warnings.catch_warnings(record=True) as w:\n"
            "    warnings.simplefilter('always')\n"
            "    u.Metre\n"
            "from clausal.lint_warnings import ClausalDeprecatedSpellingWarning\n"
            "assert len(w) == 1 and w[0].category is ClausalDeprecatedSpellingWarning, w\n"
            "print('clausal.templating.term_rewriting' in sys.modules)\n"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, check=True)
        assert out.stdout.strip() == "False", out.stdout

    def test_warning_names_the_callers_line(self, fresh_python_warnings):
        """Direct access, the py.units forwarder and a from-import all
        report THIS file and the accessing line, not the forwarder or
        importlib."""
        # nv
        from clausal.modules.py import units as py_units  # noqa: PLC0415

        def _hits(caught):
            return [w for w in caught
                    if issubclass(w.category, ClausalDeprecatedSpellingWarning)]

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            units.Metre                                      # noqa: B018
            direct_line = _line()
        (hit,) = _hits(caught)
        assert (hit.filename, hit.lineno) == (__file__, direct_line)

        units._warned_deprecated_unit_names.clear()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            py_units.Metre                                   # noqa: B018
            fwd_line = _line()
        (hit,) = _hits(caught)
        assert (hit.filename, hit.lineno) == (__file__, fwd_line)

        units._warned_deprecated_unit_names.clear()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from clausal.modules.py.units import Newton  # noqa: PLC0415, F401
            imp_line = _line()
        (hit,) = _hits(caught)
        assert (hit.filename, hit.lineno) == (__file__, imp_line)


def _line():
    """Line number of the statement just above the call (same frame)."""
    import inspect  # noqa: PLC0415
    return inspect.currentframe().f_back.f_lineno - 1
