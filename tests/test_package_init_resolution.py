"""Tests for ``__init__.clausal`` directory-as-package module resolution.

A directory ``foo/bar/`` that contains ``foo/bar/__init__.clausal`` must import
as the package module ``foo.bar`` (reusing Python's ``__init__`` package
mechanism), executing the init file's clauses into the package namespace.
Submodule files under it (``foo/bar/baz.clausal``) continue to resolve as
``foo.bar.baz``, both with and without an ``__init__.clausal`` present.

See ``todo/package-init-clausal-module-resolution.md``.
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings

import pytest

import clausal.import_hook
from clausal.import_hook import PredicateFinder
from clausal.logic.solve import call


# ── sys.path / sys.modules isolation ─────────────────────────────────────────


@pytest.fixture
def on_path(tmp_path):
    """Put ``tmp_path`` on ``sys.path`` and clean up any modules it introduced.

    Real import resolution (``import a.b`` / ``-import_from(a.b, …)``) goes
    through the meta-path finders, so the fixture root must be discoverable via
    ``sys.path``.  Every module imported from it is evicted afterwards so tests
    stay independent (see the double-load pitfalls note in the audit memory).
    """
    before = set(sys.modules)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        yield tmp_path
    finally:
        for name in list(sys.modules):
            if name not in before:
                sys.modules.pop(name, None)
        try:
            sys.path.remove(str(tmp_path))
        except ValueError:
            pass
        importlib.invalidate_caches()


# ── Finder directory branch (unit) ───────────────────────────────────────────


class TestFinderDirectoryBranch:
    """``PredicateFinder.find_spec`` resolves a directory-with-init to a package."""

    def test_directory_with_init_returns_package_spec(self, tmp_path):
        # nv
        pkg_b = tmp_path / "a" / "b"
        pkg_b.mkdir(parents=True)
        init = pkg_b / "__init__.clausal"
        init.write_text("-module(b, [ping])\nping(1),\n")

        spec = PredicateFinder().find_spec("a.b", path=[str(tmp_path / "a")])

        assert spec is not None
        assert spec.origin == str(init)
        # submodule_search_locations marks it a *package* so a.b.c resolves next.
        assert list(spec.submodule_search_locations) == [str(pkg_b)]

    def test_bare_directory_without_init_returns_none(self, tmp_path):
        """A directory with no ``__init__.clausal`` is left to PathFinder as a
        PEP-420 namespace package (no regression)."""
        # nv
        pkg_b = tmp_path / "a" / "b"
        pkg_b.mkdir(parents=True)
        (pkg_b / "c.clausal").write_text("-module(c, [Q])\nQ(1),\n")

        spec = PredicateFinder().find_spec("a.b", path=[str(tmp_path / "a")])

        assert spec is None

    def test_flat_file_takes_priority_over_package_dir(self, tmp_path):
        """When both ``b.clausal`` and ``b/__init__.clausal`` exist, the flat
        file wins so existing flat-module resolution is unchanged."""
        # nv
        (tmp_path / "b.clausal").write_text("-module(b, [ping])\nping(1),\n")
        pkg_b = tmp_path / "b"
        pkg_b.mkdir()
        (pkg_b / "__init__.clausal").write_text("-module(b, [ping])\nping(2),\n")

        spec = PredicateFinder().find_spec("b", path=[str(tmp_path)])

        assert spec.origin == str(tmp_path / "b.clausal")
        assert spec.submodule_search_locations is None

    def test_package_dir_named_after_stdlib_warns_and_defers(self, tmp_path):
        """A package dir named after a stdlib module must not silently shadow it."""
        # nv
        from clausal.templating.term_rewriting import ClausalLintWarning

        pkg = tmp_path / "json"
        pkg.mkdir()
        (pkg / "__init__.clausal").write_text("-module(json, [ping])\nping(1),\n")

        with pytest.warns(ClausalLintWarning, match="json"):
            spec = PredicateFinder().find_spec("json", path=[str(tmp_path)])
        assert spec is None


# ── End-to-end resolution through the import machinery ────────────────────────


class TestPackageInitEndToEnd:
    """Real ``import`` / ``-import_from`` resolution of directory packages."""

    def test_directory_as_module_loads_and_predicate_runs(self, on_path):
        # nv
        pkg = on_path / "a" / "b"
        pkg.mkdir(parents=True)
        (pkg / "__init__.clausal").write_text(
            "-module(b, [ping(X)])\nping(1),\nping(2),\n"
        )
        (on_path / "use_dir.clausal").write_text(
            "-import_from(a.b, [ping])\nuse_ping(X) <- ping(X)\n"
        )

        mod = importlib.import_module("use_dir")
        logic_mod = mod.__dict__["$module"]
        assert len(list(call("use_ping", 1, module=logic_mod))) == 1
        assert list(call("use_ping", 9, module=logic_mod)) == []

    def test_directory_package_executes_init_and_sets_dunder_path(self, on_path):
        """Importing the package directly executes the init's clauses (it is a
        real clausal module, not a bare PEP-420 namespace package) and sets
        ``__path__`` so submodules resolve under it."""
        # nv
        pkg = on_path / "a" / "b"
        pkg.mkdir(parents=True)
        (pkg / "__init__.clausal").write_text("-module(b, [ping(X)])\nping(1),\n")

        mod = importlib.import_module("a.b")
        # __path__ marks it a package (a namespace package would set this too)...
        assert list(mod.__path__) == [str(pkg)]
        # ...but only a real clausal load runs the init: a namespace package
        # would have neither ``$module`` nor the executed predicate.
        logic_mod = mod.__dict__["$module"]
        assert len(list(call("ping", 1, module=logic_mod))) == 1

    def test_reexport_through_init(self, on_path):
        """``a/b/__init__.clausal`` re-exports ``a.b.c``; a consumer importing
        ``a.b`` resolves the re-exported predicate (thin-package-init pattern)."""
        # nv
        pkg = on_path / "a" / "b"
        pkg.mkdir(parents=True)
        (pkg / "__init__.clausal").write_text("-import_from(a.b.c, [qux])\n")
        (pkg / "c.clausal").write_text("-module(c, [qux(X)])\nqux(7),\n")
        (on_path / "use_reexport.clausal").write_text(
            "-import_from(a.b, [qux])\nuse_q(X) <- qux(X)\n"
        )

        mod = importlib.import_module("use_reexport")
        logic_mod = mod.__dict__["$module"]
        assert len(list(call("use_q", 7, module=logic_mod))) == 1

    def test_submodule_resolves_with_init_present(self, on_path):
        """``a.b.c`` resolves directly even when ``a/b/`` has an ``__init__``."""
        # nv
        pkg = on_path / "a" / "b"
        pkg.mkdir(parents=True)
        (pkg / "__init__.clausal").write_text("-module(b, [marker(X)])\nmarker(1),\n")
        (pkg / "c.clausal").write_text("-module(c, [qux(X)])\nqux(3),\n")
        (on_path / "use_sub.clausal").write_text(
            "-import_from(a.b.c, [qux])\nuse_q(X) <- qux(X)\n"
        )

        mod = importlib.import_module("use_sub")
        logic_mod = mod.__dict__["$module"]
        assert len(list(call("use_q", 3, module=logic_mod))) == 1

    def test_submodule_resolves_without_init(self, on_path):
        """``ns.leaf.mod`` resolves as a namespace-package submodule with no
        ``__init__.clausal`` anywhere (no regression)."""
        # nv
        leaf = on_path / "ns" / "leaf"
        leaf.mkdir(parents=True)
        (leaf / "mod.clausal").write_text("-module(mod, [res(X)])\nres(5),\n")
        (on_path / "use_ns.clausal").write_text(
            "-import_from(ns.leaf.mod, [res])\nuse_r(X) <- res(X)\n"
        )

        mod = importlib.import_module("use_ns")
        logic_mod = mod.__dict__["$module"]
        assert len(list(call("use_r", 5, module=logic_mod))) == 1

    def test_flat_module_unchanged(self, on_path):
        """A flat ``snap.clausal`` still resolves as module ``snap``."""
        # nv
        (on_path / "snap.clausal").write_text("-module(snap, [ping(X)])\nping(1),\n")
        (on_path / "use_flat.clausal").write_text(
            "-import_from(snap, [ping])\nuse_ping(X) <- ping(X)\n"
        )

        mod = importlib.import_module("use_flat")
        logic_mod = mod.__dict__["$module"]
        assert len(list(call("use_ping", 1, module=logic_mod))) == 1
