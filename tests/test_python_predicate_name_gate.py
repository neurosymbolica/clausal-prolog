"""Every predicate a PYTHON module registers has a valid Clausal name.

``test_titlecase_gate.py`` reads Clausal SOURCE.  A predicate registered from
Python -- ``ModulePredicate("Name")``, a module's ``_pred``/``_pred_bidir``
helper, a hand-rolled ``*Predicate`` adapter, ``X._register(n, ...)`` --
never passes through the transformer, so a TitleCase name there loads
silently and can then only be called as a quoted atom.  About 300 such names
sat in the optional packages until they were renamed by hand, because
nothing read them: the packages are not installed in the engine venv and
their own suites are not in the gate.

This gate reads the REGISTRY, not the text: ``tests/_predicate_name_census``
imports each module under ``clausal/modules/`` and
``packages/*/clausal/modules/`` from this checkout's source, in a child
process, and reports what ``module_signatures`` offers plus every adapter's
own ``_name``.  The rule is the engine's ``_is_logic_var_name``: a name the
variable rule claims (``Foo``, ``FOO``, ``_foo``) is no predicate name.

It fails CLOSED:

* a package module whose import fails for a missing DECLARED third-party
  dependency is AST-read instead, never skipped; any other import failure
  is a failure;
* an AST-read module with a computed registration name is a failure (the
  static reading cannot see it);
* on every module that DID import, the static reading must find every
  registry name -- the fallback's recall is measured where the truth is
  known, so it cannot quietly go blind;
* the census must see a minimum number of modules and names;
* the positive controls run the same child on synthetic packages.

It also reads the DATA names each module offers to ``-import_from`` (which
compiles to a Python ``from M import name``, so it offers every public
attribute: a ``Quantity`` constant, a number, a term constructor).  None may
be TitleCase -- the one spelling ``-import_from`` lets through silently,
which is how ``scipy_constants`` exported ``SpeedOfLight`` & co. unseen.
Read both on the loaded module and statically (with the same recall check,
and a computed module-global write in an AST-checked module failing), with
its own floors and controls.  The ENGINE's TitleCase data names awaiting a
ruling are listed in ``_ENGINE_DATA_PENDING_RULING``, exactly: a new one
fails, and so does a listed one that is gone.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

from tests._predicate_name_census import DISABLED_PACKAGES

_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Floors, measured 2026-10-03 at 277 modules, 65 naming a predicate, 1271
#: names.  An empty or truncated discovery falls far below them.
_MIN_MODULES = 250
_MIN_NAMING_MODULES = 55
_MIN_NAMES = 1000

#: Data-name floors, measured 2026-10-04 at 209 modules offering 572 data
#: names (engine + packages).
_MIN_DATA_MODULES = 180
_MIN_DATA_NAMES = 450

#: TitleCase data names the ENGINE exports, held for an operator ruling
#: (2026-10-04) rather than renamed: engine-side names are not this gate's
#: to change.  ``prolog.Rem/TruncDiv/TruncMod`` are the qualified operator
#: helpers the .pl translator emits; ``units.SI_*`` are the derived-unit
#: dimension templates ``clausal/library/units`` imports.  EXACT: a name
#: not listed fails, and so does a listed name that no longer exists.
_ENGINE_DATA_PENDING_RULING = {
    "clausal.modules.prolog": {"Rem", "TruncDiv", "TruncMod"},
    "clausal.modules.units": {
        "SI_Acceleration", "SI_Area", "SI_Capacitance", "SI_Charge",
        "SI_Conductance", "SI_Energy", "SI_Force", "SI_Frequency",
        "SI_Illuminance", "SI_Inductance", "SI_LuminousFlux",
        "SI_MagneticFlux", "SI_MagneticFluxDensity", "SI_Power",
        "SI_Pressure", "SI_Resistance", "SI_Velocity", "SI_Voltage",
        "SI_Volume"},
}


def _run_census(*extra: pathlib.Path, only_extra: bool = False) -> dict:
    env = dict(os.environ, PYTHONPATH=str(_ROOT), CLAUSAL_ROOT=str(_ROOT))
    argv = [sys.executable, "-m", "tests._predicate_name_census", str(_ROOT)]
    if only_extra:
        argv.append("--only-extra")
    argv.extend(str(p) for p in extra)
    proc = subprocess.run(argv, cwd=_ROOT, env=env, capture_output=True,
                          text=True, timeout=900)
    if proc.returncode < 0:
        pytest.fail(f"census child killed by signal {-proc.returncode} "
                    "(SIGKILL is usually the OOM killer); stderr tail:\n"
                    + proc.stderr[-2000:])
    assert proc.returncode == 0, proc.stderr[-4000:]
    census = json.loads(proc.stdout)
    engine = os.path.realpath(census["engine_file"])
    assert engine.startswith(os.path.join(os.path.realpath(_ROOT), "")), engine
    return census


def _problems(census: dict) -> list[str]:
    """Everything that keeps the census from being clean."""
    out = []
    for r in census["records"]:
        where = f"{r['module']} ({r['file']})"
        if r["mode"] == "failed":
            out.append(f"{where}: does not import -- {r['error']}")
            continue
        for name, why in r["bad"].items():
            out.append(f"{where}: registers {name!r}: {why}")
        if r["mode"] == "ast" and r["dynamic"]:
            out.append(f"{where}: AST-checked, but registers computed names "
                       f"at lines {r['dynamic']} the static read cannot see")
        if r["mode"] == "import" and r["origin"] in DISABLED_PACKAGES:
            out.append(f"{where}: {r['origin']} imports again -- remove it "
                       "from DISABLED_PACKAGES")
        if r["mode"] == "import" and r["origin"] != "engine":
            blind = sorted(set(r["names"]) - set(r["ast_names"]))
            if blind:
                out.append(f"{where}: the AST fallback misses registry "
                           f"names {blind}; teach ast_registrations the shape")
    return out


def _data_problems(census: dict, pending=None) -> list[str]:
    """Everything that keeps the DATA-name census from being clean."""
    pending = _ENGINE_DATA_PENDING_RULING if pending is None else pending
    out = []
    seen_pending: dict[str, set] = {}
    for r in census["records"]:
        where = f"{r['module']} ({r['file']})"
        if r["mode"] == "failed":
            continue                    # reported by _problems
        held = pending.get(r["module"], set()) if r["origin"] == "engine" else set()
        for name, why in r["data_bad"].items():
            if name in held:
                seen_pending.setdefault(r["module"], set()).add(name)
                continue
            out.append(f"{where}: exports the data name {name!r}: {why}")
        if r["mode"] == "ast" and r["data_dynamic"]:
            out.append(f"{where}: AST-checked, but writes computed module "
                       f"globals at lines {r['data_dynamic']} the static "
                       "read cannot see")
        if r["mode"] == "import" and r["origin"] != "engine":
            blind = sorted(set(r["data_names"]) - set(r["ast_data_names"]))
            if blind:
                out.append(f"{where}: the static data reading misses "
                           f"{blind}; teach ast_data_names the shape")
    for module, names in sorted(pending.items()):
        gone = sorted(names - seen_pending.get(module, set()))
        if gone:
            out.append(f"{module}: {gone} listed in "
                       "_ENGINE_DATA_PENDING_RULING but no longer exported "
                       "TitleCase -- drop them from the list")
    return out


@pytest.fixture(scope="module")
def census():
    return _run_census()


def test_every_python_registered_predicate_name_is_valid(census):
    problems = _problems(census)
    assert not problems, "\n".join(problems)


def test_the_census_saw_the_whole_tree(census):
    """Positive control on discovery: an empty census proves nothing."""
    records = census["records"]
    by_mode = {m: sum(r["mode"] == m for r in records)
               for m in ("import", "ast", "failed")}
    naming = [r for r in records if r["names"]]
    names = sum(len(r["names"]) for r in records)
    summary = (f"{len(records)} modules (import-checked {by_mode['import']}, "
               f"AST-checked {by_mode['ast']}, failed {by_mode['failed']}); "
               f"{len(naming)} name a predicate; {names} names")
    print(summary)
    assert len(records) >= _MIN_MODULES, summary
    assert len(naming) >= _MIN_NAMING_MODULES, summary
    assert names >= _MIN_NAMES, summary
    expected = {p.parent.parent.name
                for p in (_ROOT / "packages").glob("*/clausal/modules")}
    seen = {r["origin"] for r in records}
    assert expected and expected | {"engine"} == seen, (expected, seen)


def test_every_exported_data_name_is_valid(census):
    problems = _data_problems(census)
    assert not problems, "\n".join(problems)


def test_the_data_census_saw_the_whole_tree(census):
    """Positive control on the DATA reading: an empty one proves nothing."""
    records = census["records"]
    offering = [r for r in records if r["data"]]
    names = sum(len(r["data"]) for r in records)
    titlecase = sum(len(r["data_bad"]) for r in records)
    summary = (f"{len(offering)} modules offer {names} data names; "
               f"{titlecase} TitleCase (held for a ruling: "
               f"{sum(map(len, _ENGINE_DATA_PENDING_RULING.values()))})")
    print(summary)
    assert len(offering) >= _MIN_DATA_MODULES, summary
    assert names >= _MIN_DATA_NAMES, summary
    # Both readings were taken: some package module was read statically
    # AND some by import, and the units module's own constants are seen.
    by_module = {r["module"]: r for r in records}
    assert {"metre", "kilo", "speed_of_light"} <= set(
        by_module["clausal.modules.units"]["data"]), summary
    assert any(r["mode"] == "ast" and r["data"] for r in records), summary


# ── Positive controls: the same child on synthetic packages ──────────────────

_HEADER = ("from clausal.modules.py import ModulePredicate, "
           "simple_to_trampoline\n"
           "def _one(x, trail, k):\n"
           "    yield None\n")


def _probe_package(tmp_path, deps, modules: dict[str, str]) -> pathlib.Path:
    pkg = tmp_path / "clausal-nameprobe"
    py = pkg / "clausal" / "modules" / "py"
    py.mkdir(parents=True)
    dep_list = ", ".join(f'"{d}"' for d in ["clausal>=0.3.1", *deps])
    (pkg / "pyproject.toml").write_text(
        f'[project]\nname = "clausal-nameprobe"\n'
        f'dependencies = [{dep_list}]\n')
    for stem, body in modules.items():
        (py / f"{stem}.py").write_text(textwrap.dedent(body))
    return pkg


def _by_stem(census):
    return {r["module"].rsplit(".", 1)[-1]: r for r in census["records"]}


def test_control_titlecase_registry_name_fails(tmp_path):
    """``ModulePredicate("BadName")`` under a clean attribute: only the
    adapter's own ``_name`` shows it, and the gate must see it."""
    pkg = _probe_package(tmp_path, [], {
        "nameprobe_bad": _HEADER + (
            "bad = ModulePredicate('BadName')\n"
            "bad._register(1, simple_to_trampoline(_one))\n"),
        "nameprobe_good": _HEADER + (
            "good = ModulePredicate('good')\n"
            "good._register(1, simple_to_trampoline(_one))\n"),
    })
    census = _run_census(pkg, only_extra=True)
    recs = _by_stem(census)
    assert recs["nameprobe_bad"]["mode"] == "import"
    assert recs["nameprobe_good"]["names"] == ["good"]
    problems = _problems(census)
    assert len(problems) == 1 and "'BadName'" in problems[0], problems


def test_control_titlecase_attribute_fails(tmp_path):
    """A clean ``_name`` bound to a TitleCase ATTRIBUTE: what
    ``-import_from`` offers is the attribute, and the gate must see it."""
    pkg = _probe_package(tmp_path, [], {
        "nameprobe_attr": _HEADER + (
            "BadAttr = ModulePredicate('bad_attr')\n"
            "BadAttr._register(1, simple_to_trampoline(_one))\n"),
    })
    problems = _problems(_run_census(pkg, only_extra=True))
    assert len(problems) == 1 and "'BadAttr'" in problems[0], problems


def test_control_missing_declared_dependency_is_ast_checked(tmp_path):
    """A module whose declared dependency is absent is read statically --
    and a TitleCase name in it still fails."""
    pkg = _probe_package(tmp_path, ["nameprobe-absent-dep>=1"], {
        "nameprobe_needs_dep": _HEADER + (
            "import nameprobe_absent_dep\n"
            "bad = ModulePredicate('BadName')\n"
            "bad._register(1, simple_to_trampoline(_one))\n"),
    })
    census = _run_census(pkg, only_extra=True)
    rec = _by_stem(census)["nameprobe_needs_dep"]
    assert rec["mode"] == "ast" and rec["missing"] == "nameprobe_absent_dep"
    assert set(rec["names"]) == {"BadName", "bad"}
    problems = _problems(census)
    assert len(problems) == 1 and "'BadName'" in problems[0], problems


def test_control_computed_name_in_an_ast_checked_module_fails(tmp_path):
    pkg = _probe_package(tmp_path, ["nameprobe-absent-dep"], {
        "nameprobe_dynamic": _HEADER + (
            "import nameprobe_absent_dep\n"
            "NAME = 'whatever'\n"
            "p = ModulePredicate(NAME)\n"
            # A function handed to an adapter is no computed NAME.
            "class WrapPredicate(ModulePredicate):\n"
            "    pass\n"
            "q = WrapPredicate(_one)\n"),
    })
    census = _run_census(pkg, only_extra=True)
    problems = _problems(census)
    assert len(problems) == 1 and "computed names" in problems[0], problems
    assert len(_by_stem(census)["nameprobe_dynamic"]["dynamic"]) == 1


@pytest.mark.parametrize("body, needle", [
    # A dependency the package never declared: not "optional", a bug.
    ("import nameprobe_undeclared_dep\n", "not a declared dependency"),
    # An engine import that does not resolve.
    ("import clausal.no_such_module_nameprobe\n",
     "an engine import that does not resolve"),
    # Anything else raised at import.
    ("raise RuntimeError('boom')\n", "RuntimeError: boom"),
])
def test_control_other_import_failures_fail(tmp_path, body, needle):
    pkg = _probe_package(tmp_path, [], {"nameprobe_broken": body})
    problems = _problems(_run_census(pkg, only_extra=True))
    assert len(problems) == 1 and needle in problems[0], problems


# ── Positive controls: exported DATA names ───────────────────────────────────

def test_control_titlecase_constant_fails(tmp_path):
    """A module exporting ``BadConstant`` fails; its lowercase constant, a
    TitleCase CLASS, a TitleCase IMPORT, a ``TypeVar``, an ALL-CAPS Python
    constant and a private name do not."""
    pkg = _probe_package(tmp_path, [], {
        "nameprobe_const": (
            "from typing import Callable, TypeVar\n"
            "BadConstant = 3\n"
            "good_constant = 4\n"
            "PYTHON_SIDE = 5\n"
            "_Private = 6\n"
            "T = TypeVar('T')\n"
            "class GoodClass:\n"
            "    pass\n"),
    })
    census = _run_census(pkg, only_extra=True)
    rec = _by_stem(census)["nameprobe_const"]
    assert rec["mode"] == "import"
    assert rec["data"] == ["BadConstant", "PYTHON_SIDE", "good_constant"]
    assert _problems(census) == []
    problems = _data_problems(census, pending={})
    assert len(problems) == 1 and "'BadConstant'" in problems[0], problems


def test_control_titlecase_constant_set_on_the_module_fails(tmp_path):
    """The scipy_constants shape: a helper writes the constant onto
    ``sys.modules[__name__]`` at import time.  Both readings see it."""
    body = ("import sys\n"
            "def _init():\n"
            "    mod = sys.modules[__name__]\n"
            "    mod.BadConstant = 1.0\n"
            "    setattr(mod, 'good_constant', 2.0)\n"
            "_init()\n")
    pkg = _probe_package(tmp_path, ["nameprobe-absent-dep"], {
        "nameprobe_setattr": body,
        "nameprobe_setattr_ast": "import nameprobe_absent_dep\n" + body,
    })
    census = _run_census(pkg, only_extra=True)
    recs = _by_stem(census)
    assert recs["nameprobe_setattr"]["mode"] == "import"
    assert recs["nameprobe_setattr_ast"]["mode"] == "ast"
    for stem in ("nameprobe_setattr", "nameprobe_setattr_ast"):
        assert {"BadConstant", "good_constant"} <= set(recs[stem]["data"])
    problems = _data_problems(census, pending={})
    assert len(problems) == 2, problems
    assert all("'BadConstant'" in p for p in problems), problems


def test_control_computed_module_global_in_an_ast_checked_module_fails(tmp_path):
    pkg = _probe_package(tmp_path, ["nameprobe-absent-dep"], {
        "nameprobe_dyn_data": (
            "import nameprobe_absent_dep\n"
            "for _n in ('a', 'b'):\n"
            "    globals()[_n] = 1\n"),
    })
    problems = _data_problems(_run_census(pkg, only_extra=True), pending={})
    assert len(problems) == 1 and "computed module globals" in problems[0], problems


def test_control_pending_ruling_list_is_exact(census):
    """A listed engine name that is no longer exported fails, so the list
    cannot outlive the names it holds."""
    stale = {m: set(n) for m, n in _ENGINE_DATA_PENDING_RULING.items()}
    stale["clausal.modules.units"].add("SI_NoSuchName")
    problems = _data_problems(census, pending=stale)
    assert len(problems) == 1 and "SI_NoSuchName" in problems[0], problems
    # and an engine name taken OFF the list fails
    short = {m: set(n) for m, n in _ENGINE_DATA_PENDING_RULING.items()}
    short["clausal.modules.prolog"].discard("Rem")
    problems = _data_problems(census, pending=short)
    assert len(problems) == 1 and "'Rem'" in problems[0], problems
