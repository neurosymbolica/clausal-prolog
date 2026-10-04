"""Run the optional packages' suites against THIS checkout, uninstalled.

The packages contribute modules into the engine's namespaces --
``clausal.modules.py.<x>`` (most), ``clausal.modules.<x>`` (provenance) and
``clausal.<x>`` (the gprolog / scryer / trealla backends) -- which an install
normally wires up through site-packages or an editable finder.  This conftest
does the same for the source tree instead: each ``packages/<pkg>/clausal/...``
directory is spliced onto the matching package ``__path__`` right after the
engine's own entry, ahead of anything an interpreter's site-packages or a
stale editable install contributed.  Nothing is installed.

Run from the repository root, in its OWN session (the splice is
process-wide; keep it out of the engine's ``tests/`` run)::

    python -m pytest packages -p no:cacheprovider

A package whose REQUIRED third-party dependency (``[project] dependencies``
in its ``pyproject.toml``) is not importable here is SKIPPED, every test
module of it, with the missing distribution named in the reason -- it is
neither failed nor silently passed -- except a test module named
``*_stubbed.py``, which stands in for the dependency itself and always
runs.  An optional dependency
(``optional-dependencies``) is the package's own tests' business; a test
module whose import raises ``ModuleNotFoundError`` for one is skipped the
same way.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tomllib

import pytest

_PACKAGES = pathlib.Path(__file__).resolve().parent
_ROOT = _PACKAGES.parent

#: Distribution name -> top-level import name, where they differ.  A
#: distribution missing here maps to its normalised name; a wrong guess
#: makes the dependency look absent and SKIPS the package with that name in
#: the reason, so it is visible, never a silent pass.
_IMPORT_NAME_OF_DIST = {
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "scikit-learn": "sklearn",
    "pyyaml": "yaml",
}


def _engine_first():
    """The engine this session imports must be this checkout's."""
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    import clausal  # noqa: PLC0415
    got = os.path.realpath(clausal.__file__)
    if not got.startswith(os.path.join(os.path.realpath(_ROOT), "")):
        raise pytest.UsageError(
            f"packages/conftest.py: imported the engine from {got}, not from "
            f"{_ROOT}; run pytest from the repository root")
    return clausal


def _splice():
    """Put every package's source directories on the engine's namespaces."""
    clausal = _engine_first()
    import clausal.modules as cm  # noqa: PLC0415
    import clausal.modules.py as cmp  # noqa: PLC0415
    for pkg in sorted(_PACKAGES.glob("*/clausal"), reverse=True):
        for ns, sub in ((clausal, pkg),
                        (cm, pkg / "modules"),
                        (cmp, pkg / "modules" / "py")):
            if sub.is_dir() and str(sub) not in ns.__path__:
                ns.__path__.insert(1, str(sub))


_splice()


def _dist_name(spec: str) -> str:
    for sep in "<>=!~[; ":
        spec = spec.split(sep, 1)[0]
    return spec.strip().lower()


def _import_name(dist: str) -> str:
    return _IMPORT_NAME_OF_DIST.get(dist, dist.replace("-", "_"))


def _declared(pkg_dir: pathlib.Path) -> tuple[list[str], list[str]]:
    """(required, optional) third-party distribution names of a package."""
    pyproject = pkg_dir / "pyproject.toml"
    if not pyproject.is_file():
        return [], []
    project = tomllib.loads(pyproject.read_text()).get("project", {})
    required = [_dist_name(s) for s in project.get("dependencies", [])]
    optional = [_dist_name(s)
                for group in project.get("optional-dependencies", {}).values()
                for s in group]
    keep = lambda names: sorted({n for n in names  # noqa: E731
                                 if n and not n.startswith("clausal")})
    return keep(required), keep(optional)


_MISSING_CACHE: dict[pathlib.Path, list[str]] = {}


def _missing_required(pkg_dir: pathlib.Path) -> list[str]:
    if pkg_dir not in _MISSING_CACHE:
        required, _ = _declared(pkg_dir)
        _MISSING_CACHE[pkg_dir] = [
            f"{dist} (import {_import_name(dist)})" for dist in required
            if _absent(_import_name(dist))]
    return _MISSING_CACHE[pkg_dir]


def _package_of(path: pathlib.Path) -> pathlib.Path | None:
    try:
        rel = path.resolve().relative_to(_PACKAGES)
    except ValueError:
        return None
    return _PACKAGES / rel.parts[0] if len(rel.parts) > 1 else None


class _MissingDependencyModule(pytest.Module):
    """A test module of a package whose required dependency is absent."""

    def collect(self):
        pkg = _package_of(self.path)
        pytest.skip(f"{pkg.name}: required dependency not installed in this "
                    f"interpreter: {', '.join(_missing_required(pkg))}",
                    allow_module_level=True)


class _OptionalDependencyModule(pytest.Module):
    """Skips the module when importing it raises ``ModuleNotFoundError``
    for one of the package's OPTIONAL dependencies; anything else raises."""

    def _getobj(self):
        try:
            return super()._getobj()
        except self.CollectError as err:
            cause = err.__cause__
            missing = (cause.name if isinstance(cause, ModuleNotFoundError)
                       else None)
            pkg = _package_of(self.path)
            _, optional = _declared(pkg)
            top = (missing or "").split(".")[0]
            if top and top in {_import_name(d) for d in optional}:
                pytest.skip(f"{pkg.name}: optional dependency {top!r} not "
                            "installed in this interpreter",
                            allow_module_level=True)
            raise


#: A test module whose name ends in this suffix supplies its own stand-in
#: for the package's third-party dependencies (a stub module in
#: ``sys.modules``, a fake installed on the adapter), so it runs whether or
#: not they are installed: the adapter-side code it pins is the package's
#: own Python, which imports the dependency lazily.
_STUBBED_SUFFIX = "_stubbed.py"


def _runs_without_dependencies(path: pathlib.Path) -> bool:
    return path.name.endswith(_STUBBED_SUFFIX)


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path, parent):
    pkg = _package_of(pathlib.Path(module_path))
    if pkg is None:
        return None
    if _missing_required(pkg) and not _runs_without_dependencies(
            pathlib.Path(module_path)):
        return _MissingDependencyModule.from_parent(parent, path=module_path)
    return _OptionalDependencyModule.from_parent(parent, path=module_path)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Skip every item -- ``.seam`` fixture tests included, which a plugin
    collects without importing a Python test module -- of a package whose
    required dependency is absent.  (A ``skip`` MARK would need a line
    number from the item's ``reportinfo``, which a ``.seam`` item lacks.)"""
    pkg = _package_of(pathlib.Path(str(item.path)))
    if (pkg is not None and _missing_required(pkg)
            and not _runs_without_dependencies(pathlib.Path(str(item.path)))):
        pytest.skip(f"{pkg.name}: required dependency not installed in this "
                    f"interpreter: {', '.join(_missing_required(pkg))}")


def _absent(import_name: str) -> bool:
    """True when *import_name* cannot be found by this interpreter.  A
    module whose ``__spec__`` is ``None`` (a stub in ``sys.modules``) makes
    ``find_spec`` raise ``ValueError``; it is present, not absent."""
    try:
        return importlib.util.find_spec(import_name) is None
    except ValueError:
        return False
    except ImportError:
        return True


def _absent_declared(pkg: pathlib.Path, exc: BaseException | None) -> str | None:
    """The top-level name of the first ``ModuleNotFoundError`` in *exc*'s
    chain (``__cause__`` / ``__context__``) that is a declared dependency of
    *pkg* (required or optional) and really is absent here.

    Only exception OBJECTS are read, never rendered text: a traceback's
    source lines, an assertion message or captured output that merely
    spells "No module named ..." must not turn a failure into a skip.  A
    ``.seam`` test's failure keeps the chain (``ClausalTestFailure`` is
    raised ``from`` the logic error, which a module predicate raises
    ``from`` the original exception), so it is read the same way."""
    required, optional = _declared(pkg)
    declared = {_import_name(d) for d in (*required, *optional)}
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, ModuleNotFoundError) and exc.name:
            top = exc.name.split(".")[0]
            if top in declared and _absent(top):
                return top
        exc = exc.__cause__ or exc.__context__
    return None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """A test that FAILS because a declared dependency of its package is
    absent -- imported lazily inside the test, or inside a predicate a
    ``.seam`` fixture calls -- is reported as SKIPPED, naming it.  Only a
    ``ModuleNotFoundError`` for an absent DECLARED dependency, found in the
    failure's exception chain, qualifies: an undeclared or installed module
    still fails, and so does a test that fails without raising one (a
    predicate that swallows the import error and answers "no")."""
    report = yield
    pkg = _package_of(pathlib.Path(str(item.path)))
    if pkg is None or not report.failed or call.excinfo is None:
        return report
    if _runs_without_dependencies(pathlib.Path(str(item.path))):
        return report     # its stub missed an import: that is a failure
    missing = _absent_declared(pkg, call.excinfo.value)
    if missing:
        report.outcome = "skipped"
        report.longrepr = (str(item.path), 0,
                           f"Skipped: {pkg.name}: dependency {missing!r} "
                           "not installed in this interpreter")
    return report


def pytest_collection_modifyitems(session, config, items):
    """The ``__path__`` splice above is process-wide, so the engine's own
    suite must never share this session: it would import package code it
    does not expect.  Refuse loudly rather than run it altered."""
    stray = [i.nodeid for i in items if _package_of(pathlib.Path(str(i.path))) is None]
    if stray:
        raise pytest.UsageError(
            "packages/conftest.py splices the package sources onto the "
            "engine's namespaces for the whole session; run `pytest "
            f"packages` on its own, not with {stray[0]!r} and "
            f"{len(stray) - 1} other item(s) outside packages/")
