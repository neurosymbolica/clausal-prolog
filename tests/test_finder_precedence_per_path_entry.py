"""Source-module resolution is per ``sys.path`` ENTRY, in path order.

Python's contract: the first path entry that holds the module wins.  The
suffix priority (``.clausal``/``.seam`` before ``.pl``) decides only between
files in the SAME entry.  Before the fix, ``.clausal``/``.seam`` and ``.pl``
were found by two finders that each scanned the whole path, so a
``.clausal`` module anywhere on ``sys.path`` beat a ``.pl`` module of the same
dotted name in an EARLIER entry -- including a ``.pl`` package's own
submodule, which then silently answered from the other tree.

Every case runs under both ``.pl`` front ends (``CLAUSAL_PL_FRONTEND``).
Trees are synthetic, built in ``tmp_path``.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import sys
import textwrap
import types
import warnings

import pytest

import clausal
from clausal import import_hook as ih
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk

FRONTENDS = ("native", "translator")
PL_LOADER = {"native": ih.NativePrologLoader, "translator": ih.PrologLoader}

# Every top-level name a test here creates; evicted before and after.
_NAMES = ("d49top", "d49ns", "d49pkg", "d49same", "leakdom", "d49py",
          "d49bogus")


def _evict():
    for name in list(sys.modules):
        if name.split(".", 1)[0] in _NAMES:
            del sys.modules[name]


@pytest.fixture(params=FRONTENDS)
def frontend(request, monkeypatch):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, request.param)
    return request.param


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """``roots(*names)`` makes ``tmp_path/<name>`` dirs and puts them on
    ``sys.path`` in the given order, ahead of everything else."""
    _evict()
    saved = list(sys.path)

    def make(*names):
        dirs = []
        for n in names:
            d = tmp_path / n
            d.mkdir(exist_ok=True)
            dirs.append(d)
        sys.path[:] = [str(d) for d in dirs] + saved
        importlib.invalidate_caches()
        return dirs

    yield make
    sys.path[:] = saved
    _evict()
    for p in tmp_path.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    importlib.invalidate_caches()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _answers(mod, name):
    x = Var()
    return [walk(deref(x)) for _ in call(name, x, module=mod)]


def _under(spec_or_mod, root):
    # A module's __file__, a spec's origin.  Not getattr(x, "origin", None):
    # on a .pl module that is the atom 'origin' (ruling 2026-10-01).
    if isinstance(spec_or_mod, types.ModuleType):
        origin = spec_or_mod.__file__
    else:
        origin = spec_or_mod.origin
    return os.path.commonpath([origin, str(root)]) == str(root)


def test_probe_runs_this_engine():
    # Positive control that the finder under test is this tree's.
    assert os.path.dirname(ih.__file__) == os.path.dirname(clausal.__file__)
    kinds = [type(f).__name__ for f in sys.meta_path]
    assert kinds.count("PredicateFinder") == 1, kinds
    assert "PrologFinder" not in kinds, kinds


# ── .pl vs .clausal across entries ──────────────────────────────────────────


def _pl_and_clausal_trees(a, b):
    # Top-level package, and a subpackage of a namespace package that spans
    # both roots (so the submodule lookup's ``path`` is [a/d49ns, b/d49ns]).
    _write(a / "d49top" / "__init__.pl", "which(1).\n")
    _write(b / "d49top" / "__init__.clausal", "which(2),\n")
    _write(a / "d49ns" / "sub" / "__init__.pl", "which(1).\n")
    _write(b / "d49ns" / "sub" / "__init__.clausal", "which(2),\n")


@pytest.mark.parametrize("order", ["AB", "BA"])
def test_pl_vs_clausal_across_entries_find_spec(roots, frontend, order):
    a, b = roots("A", "B") if order == "AB" else roots("B", "A")[::-1]
    _pl_and_clausal_trees(a, b)
    first = a if order == "AB" else b
    for name in ("d49top", "d49ns.sub"):
        if name == "d49ns.sub":
            importlib.import_module("d49ns")
        spec = importlib.util.find_spec(name)
        assert _under(spec, first), (name, spec.origin)
        want = PL_LOADER[frontend] if first is a else ih.PredicateLoader
        assert type(spec.loader) is want


@pytest.mark.parametrize("order", ["AB", "BA"])
def test_pl_vs_clausal_across_entries_import(roots, frontend, order):
    a, b = roots("A", "B") if order == "AB" else roots("B", "A")[::-1]
    _pl_and_clausal_trees(a, b)
    first = a if order == "AB" else b
    for name in ("d49top", "d49ns.sub"):
        mod = importlib.import_module(name)
        assert _under(mod, first), (name, mod.__file__)
        assert _answers(mod, "which") == ([1] if first is a else [2])


@pytest.mark.parametrize("order", ["AB", "BA"])
def test_pl_package_importing_its_own_submodule(roots, frontend, order):
    """A's ``.pl`` package imports ``helper``, which exists only in A; B has
    a ``.clausal`` package of the same dotted name without it."""
    a, b = roots("A", "B") if order == "AB" else roots("B", "A")[::-1]
    _write(a / "d49pkg" / "sub" / "helper.pl", """\
        :- module(helper, [helper_fact/1]).
        helper_fact(7).
        """)
    _write(a / "d49pkg" / "sub" / "__init__.pl", """\
        :- use_module(d49pkg/sub/helper, [helper_fact/1]).
        viahelper(X) :- helper_fact(X).
        """)
    _write(b / "d49pkg" / "sub" / "__init__.clausal", "viahelper(1),\n")
    mod = importlib.import_module("d49pkg.sub")
    if order == "AB":
        assert _under(mod, a), mod.__file__
        assert _answers(mod, "viahelper") == [7]
        assert _under(sys.modules["d49pkg.sub.helper"], a)
    else:
        assert _under(mod, b), mod.__file__
        assert _answers(mod, "viahelper") == [1]
        assert "d49pkg.sub.helper" not in sys.modules


_GOLD_SIB = """\
    -module(sib, [answer(X)])
    answer("GOLD")
    """
_FRESH_SIB = """\
    :- module(sib, [answer/1]).
    answer(fresh).
    """


@pytest.mark.parametrize("shape", ["package", "flat_sibling", "gold_facade"])
def test_pl_facade_is_not_answered_by_a_later_clausal(roots, frontend, shape):
    """The silent wrong answer: a ``.pl`` facade in an earlier entry whose
    sibling module ``sib`` is ``.pl`` there and ``.clausal`` in a LATER entry
    must answer from its own tree.

    ``package``: fresh/leakdom/{__init__,sib}.pl, gold/leakdom/sib.clausal.
    The facade is a regular package, so its ``__path__`` already confined
    ``leakdom.sib`` to fresh -- this shape answered correctly before the fix
    too and is kept as a guard.
    ``flat_sibling``: fresh/{leakdom,sib}.pl, gold/sib.clausal -- the
    sibling is a top-level module found by walking ``sys.path``; before the
    fix it loaded gold's and the facade answered "GOLD".
    ``gold_facade``: the ``package`` shape plus gold/leakdom/__init__.clausal
    -- before the fix gold's whole package won and answered "GOLD".
    """
    fresh, gold = roots("fresh", "gold")
    if shape == "flat_sibling":
        _write(fresh / "leakdom.pl", """\
            :- module(leakdom, [answer/1]).
            :- use_module(sib, [answer/1]).
            """)
        _write(fresh / "sib.pl", _FRESH_SIB)
        _write(gold / "sib.clausal", _GOLD_SIB)
        sib_name = "sib"
    else:
        _write(fresh / "leakdom" / "__init__.pl", """\
            :- module(leakdom, [answer/1]).
            :- use_module(leakdom/sib, [answer/1]).
            """)
        _write(fresh / "leakdom" / "sib.pl", _FRESH_SIB)
        _write(gold / "leakdom" / "sib.clausal", _GOLD_SIB)
        if shape == "gold_facade":
            _write(gold / "leakdom" / "__init__.clausal", """\
                -module(leakdom, [answer(X)])
                -import_from(leakdom.sib, [answer])
                """)
        sib_name = "leakdom.sib"
    sys.modules.pop(sib_name, None)
    try:
        facade = importlib.import_module("leakdom")
        assert _under(facade, fresh), facade.__file__
        assert _answers(facade, "answer") == ["fresh"]
        sib = sys.modules[sib_name]
        assert _under(sib, fresh), sib.__file__
    finally:
        sys.modules.pop("sib", None)


@pytest.mark.parametrize("order", ["AD", "DA"])
def test_seam_vs_pl_across_entries(roots, frontend, order):
    a, d = roots("A", "D") if order == "AD" else roots("D", "A")[::-1]
    _write(a / "d49top.pl", "which(1).\n")
    _write(d / "d49top.seam", "which(4),\n")
    first = a if order == "AD" else d
    spec = importlib.util.find_spec("d49top")
    assert _under(spec, first), spec.origin
    mod = importlib.import_module("d49top")
    assert _answers(mod, "which") == ([1] if first is a else [4])


# ── same-entry priority: unchanged ──────────────────────────────────────────


def test_same_entry_priority_unchanged(roots, frontend):
    (d,) = roots("S")
    # Flat files: .clausal > .seam > .pl.
    _write(d / "d49same.clausal", "which(0),\n")
    _write(d / "d49same.seam", "which(0),\n")
    _write(d / "d49same.pl", "which(0).\n")
    assert importlib.util.find_spec("d49same").origin.endswith(".clausal")
    (d / "d49same.clausal").unlink()
    importlib.invalidate_caches()
    assert importlib.util.find_spec("d49same").origin.endswith(".seam")
    (d / "d49same.seam").unlink()
    importlib.invalidate_caches()
    spec = importlib.util.find_spec("d49same")
    assert spec.origin.endswith(".pl")
    assert type(spec.loader) is PL_LOADER[frontend]
    # A .clausal PACKAGE beats a flat .pl in the same entry (the .clausal
    # group, flat then package, is asked before the .pl group).
    _write(d / "d49same" / "__init__.clausal", "which(0),\n")
    importlib.invalidate_caches()
    spec = importlib.util.find_spec("d49same")
    assert spec.origin.endswith(os.path.join("d49same", "__init__.clausal"))
    assert spec.submodule_search_locations == [str(d / "d49same")]
    # Within the .pl group a flat file beats a package.
    (d / "d49same" / "__init__.clausal").unlink()
    _write(d / "d49same" / "__init__.pl", "which(0).\n")
    importlib.invalidate_caches()
    assert importlib.util.find_spec("d49same").origin == str(d / "d49same.pl")


# ── namespace packages and .py: unchanged ───────────────────────────────────


def test_namespace_package_spanning_entries_unchanged(roots, frontend):
    a, b = roots("A", "B")
    _write(a / "d49ns" / "x.pl", "which(1).\n")
    _write(b / "d49ns" / "y.clausal", "which(2),\n")
    spec = importlib.util.find_spec("d49ns")
    assert spec.origin is None  # PEP 420, left to PathFinder
    assert list(spec.submodule_search_locations) == [
        str(a / "d49ns"), str(b / "d49ns")]
    assert _answers(importlib.import_module("d49ns.x"), "which") == [1]
    assert _answers(importlib.import_module("d49ns.y"), "which") == [2]


def test_py_package_earlier_still_loses_to_clausal_later(roots, frontend):
    """Pins today's behaviour, NOT Python's contract: the source finder sits
    ahead of PathFinder on ``sys.meta_path``, so a ``.clausal`` module in any
    entry beats a ``.py`` module in an earlier one.  Out of scope here."""
    c, b = roots("C", "B")
    _write(c / "d49py" / "__init__.py", "")
    _write(b / "d49py" / "__init__.clausal", "which(2),\n")
    assert _under(importlib.util.find_spec("d49py"), b)


def test_invalid_frontend_breaks_only_pl_imports(roots, monkeypatch):
    """The .pl loader is chosen only once a .pl file is found, so a bad
    ``CLAUSAL_PL_FRONTEND`` cannot break a .clausal or plain import."""
    (d,) = roots("S")
    _write(d / "d49top.clausal", "which(3),\n")
    _write(d / "d49bogus.pl", "which(5).\n")
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, "bogus")
    assert importlib.util.find_spec("d49top").origin.endswith(".clausal")
    assert importlib.util.find_spec("json") is not None
    with pytest.raises(ImportError, match="not a .pl front end"):
        importlib.util.find_spec("d49bogus")


def test_stdlib_named_source_still_defers(roots, frontend):
    (d,) = roots("S")
    _write(d / "json.pl", "x(1).\n")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        spec = ih.PredicateFinder().find_spec("json", path=[str(d)])
    assert spec is None
    assert any("standard-library" in str(x.message) for x in w)
