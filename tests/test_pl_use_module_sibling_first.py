"""A ``use_module`` path in a ``.pl`` file resolves against the IMPORTING
FILE'S OWN DIRECTORY first, then as a dotted module on ``sys.path``.

This is Scryer's rule (a relative path names a file beside the importer) and
the translator's (``prolog_to_clausal._resolve_module_path``).  Before the
fix the native front end read a bare ``use_module(sib, ...)`` inside a
``.pl`` package as the TOP-LEVEL module ``sib`` only: with a foreign ``sib``
later on ``sys.path`` it silently answered from that module, and without one
it refused "no module sib on sys.path".

Every case runs under both ``.pl`` front ends.  Trees are synthetic, built in
``tmp_path``.
"""
from __future__ import annotations

import importlib
import shutil
import sys
import textwrap

import pytest

from clausal import import_hook as ih
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from tests._suffix import SEAM

FRONTENDS = ("native", "translator")

_NAMES = ("sfq_pkg", "sfq_sib", "sfq_top", "sfq_n", "sfq_sub")


def _evict():
    for name in list(sys.modules):
        if name.split(".", 1)[0] in _NAMES:
            del sys.modules[name]


@pytest.fixture(params=FRONTENDS)
def frontend(request, monkeypatch):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, request.param)
    return request.param


@pytest.fixture
def roots(tmp_path):
    _evict()
    saved = list(sys.path)

    def make(*names):
        dirs = [tmp_path / n for n in names]
        for d in dirs:
            d.mkdir(exist_ok=True)
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


_PKG = """\
    :- module(sfq_pkg, [g/1]).
    :- use_module(sfq_sib, [f/1]).
    g(X) :- f(X).
"""


def test_sibling_beats_a_foreign_top_level_module(frontend, roots):
    ra, rb = roots("RA", "RB")
    _write(ra / "sfq_pkg" / "__init__.pl", _PKG)
    _write(ra / "sfq_pkg" / "sfq_sib.pl", ":- module(sfq_sib, [f/1]).\nf(inpkg).\n")
    _write(rb / f"sfq_sib{SEAM}", "-module(sfq_sib, [f(X)])\nf(7)\n")
    mod = importlib.import_module("sfq_pkg")
    assert _answers(mod, "g") == ["inpkg"]
    assert "sfq_pkg.sfq_sib" in sys.modules
    assert "sfq_sib" not in sys.modules


def test_sibling_loads_with_no_top_level_module(frontend, roots):
    (ra,) = roots("RA")
    _write(ra / "sfq_pkg" / "__init__.pl", _PKG)
    _write(ra / "sfq_pkg" / "sfq_sib.pl", ":- module(sfq_sib, [f/1]).\nf(inpkg).\n")
    assert _answers(importlib.import_module("sfq_pkg"), "g") == ["inpkg"]


def test_top_level_module_still_resolves_without_a_sibling(frontend, roots):
    ra, rb = roots("RA", "RB")
    _write(ra / "sfq_pkg" / "__init__.pl", """\
        :- module(sfq_pkg, [g/1]).
        :- use_module(sfq_top, [f/1]).
        g(X) :- f(X).
    """)
    _write(rb / "sfq_top.pl", ":- module(sfq_top, [f/1]).\nf(top).\n")
    assert _answers(importlib.import_module("sfq_pkg"), "g") == ["top"]
    assert "sfq_top" in sys.modules


def test_nested_package_bare_and_slash_paths(frontend, roots):
    (ra,) = roots("RA")
    _write(ra / "sfq_n" / "__init__.pl", ":- module(sfq_n, []).\n")
    _write(ra / "sfq_n" / "inner" / "__init__.pl", """\
        :- module(inner, [g/1]).
        :- use_module(sfq_sib, [f/1]).
        g(X) :- f(X).
    """)
    _write(ra / "sfq_n" / "inner" / "sfq_sib.pl",
           ":- module(sfq_sib, [f/1]).\nf(nested).\n")
    # A plain (non-package) module: a slash path a/b beside it.
    _write(ra / "sfq_n" / "inner" / "m.pl", """\
        :- module(m, [h/1]).
        :- use_module(sfq_sub/x, [k/1]).
        h(X) :- k(X).
    """)
    _write(ra / "sfq_n" / "inner" / "sfq_sub" / "x.pl",
           ":- module(x, [k/1]).\nk(beside).\n")
    # The same slash path read as a top-level dotted module: must NOT win.
    _write(ra / "sfq_sub" / "x.pl", ":- module(x, [k/1]).\nk(toplevel).\n")
    assert _answers(importlib.import_module("sfq_n.inner"), "g") == ["nested"]
    assert _answers(importlib.import_module("sfq_n.inner.m"), "h") == ["beside"]
    assert "sfq_n.inner.sfq_sub.x" in sys.modules
    assert "sfq_sub.x" not in sys.modules


def test_a_plain_directory_beside_the_importer_is_no_module(frontend, roots):
    # Scryer opens only sfq_top.pl beside the file; a data directory of the
    # same name must not stop the fallback to the top-level module.
    ra, rb = roots("RA", "RB")
    _write(ra / "sfq_pkg" / "__init__.pl", """\
        :- module(sfq_pkg, [g/1]).
        :- use_module(sfq_top, [f/1]).
        g(X) :- f(X).
    """)
    _write(ra / "sfq_pkg" / "sfq_top" / "readme.txt", "data\n")
    _write(rb / "sfq_top.pl", ":- module(sfq_top, [f/1]).\nf(top).\n")
    assert _answers(importlib.import_module("sfq_pkg"), "g") == ["top"]


def test_a_sibling_seam_module_is_imported_from_a_pl_file(frontend, roots):
    (ra,) = roots("RA")
    _write(ra / "sfq_pkg" / "__init__.pl", _PKG)
    _write(ra / "sfq_pkg" / f"sfq_sib{SEAM}",
           "-module(sfq_sib, [f(X)])\nf(8)\n")
    assert _answers(importlib.import_module("sfq_pkg"), "g") == [8]


def test_a_sibling_file_with_no_dotted_name_is_refused(frontend, roots):
    (ra,) = roots("RA")
    _write(ra / "sfq_pkg" / "__init__.pl", """\
        :- module(sfq_pkg, [g/1]).
        :- use_module('sfq-bad', [f/1]).
        g(X) :- f(X).
    """)
    _write(ra / "sfq_pkg" / "sfq-bad.pl", ":- module(sfq_bad, [f/1]).\nf(1).\n")
    with pytest.raises((SyntaxError, ImportError)) as ei:
        importlib.import_module("sfq_pkg")
    assert "sfq-bad" in str(ei.value)


def test_native_refuses_a_dot_dot_component_inside_a_path(monkeypatch, roots):
    # Ruling D10 (native): no relative file path, not even mid-path.
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, "native")
    (ra,) = roots("RA")
    _write(ra / "sfq_pkg" / "__init__.pl", """\
        :- module(sfq_pkg, [g/1]).
        :- use_module('sfq_sub/../sfq_sib', [f/1]).
        g(X) :- f(X).
    """)
    _write(ra / "sfq_pkg" / "sfq_sib.pl", ":- module(sfq_sib, [f/1]).\nf(1).\n")
    with pytest.raises(SyntaxError) as ei:
        importlib.import_module("sfq_pkg")
    assert "module path" in str(ei.value)
