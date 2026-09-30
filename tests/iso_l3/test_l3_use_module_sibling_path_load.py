"""A bare ``use_module`` sibling resolves to the importer's FULL dotted
name whether the importer was imported by dotted name or LOADED BY PATH.

Scryer resolves a relative ``use_module`` path against the importing file's
own directory; both ``.pl`` front ends then name that file by its dotted
module.  ``package_root`` climbed one directory per dot of the importer's
module name (one more for ``__init__``), which is right only when that name
IS the file's dotted name.  ``clausal.testing.load_clausal_module`` loads a
file under the synthetic ``_clausal_test_<stem>``: from
``pkg/dom/__init__.pl`` the climb landed on ``pkg/`` and named the sibling
``dom.schema`` (native: "no module dom.schema on sys.path"; translator:
"No module named 'dom'").  The root is now trusted only when it
round-trips to the importer's own name; otherwise the most specific
``sys.path`` entry names the sibling -- ``pkg.dom.schema``, the name an
import finds it under.

Every case runs under both front ends.  Trees are synthetic, in
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
from clausal.testing import load_clausal_module

FRONTENDS = ("native", "translator")

_TOPS = ("sbp_pkg", "schema", "sub")


def _evict():
    for name in list(sys.modules):
        if name.split(".", 1)[0] in _TOPS:
            del sys.modules[name]


@pytest.fixture(params=FRONTENDS)
def frontend(request, monkeypatch):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, request.param)
    expected = (ih.NativePrologLoader if request.param == "native"
                else ih.PrologLoader)
    assert ih._pl_loader_class() is expected
    return request.param


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """``fresh/sbp_pkg/dom/`` holding a package ``__init__.pl``, a plain
    module ``rules.pl``, a slash-path importer ``nest.pl`` and the siblings
    they name; ``fresh`` is on ``sys.path``."""
    _evict()
    fresh = tmp_path / "fresh"
    dom = fresh / "sbp_pkg" / "dom"
    _write(dom / "schema.pl", ":- module(schema, [limit/1]).\nlimit(5).\n")
    _write(dom / "sub" / "leaf.pl",
           ":- module(leaf, [limit/1]).\nlimit(6).\n")
    _write(dom / "__init__.pl", """\
        :- module(dom, [answer/1]).
        :- use_module(schema, [limit/1]).
        answer(X) :- limit(X).
    """)
    _write(dom / "rules.pl", """\
        :- module(rules, [answer/1]).
        :- use_module(schema, [limit/1]).
        answer(X) :- limit(X).
    """)
    _write(dom / "nest.pl", """\
        :- module(nest, [answer/1]).
        :- use_module(sub/leaf, [limit/1]).
        answer(X) :- limit(X).
    """)
    monkeypatch.setattr(sys, "path", [str(fresh)] + sys.path)
    importlib.invalidate_caches()
    yield tmp_path, dom
    _evict()
    for p in tmp_path.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    importlib.invalidate_caches()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _answers(mod):
    x = Var()
    return [walk(deref(x)) for _ in call("answer", x, module=mod)]


def test_package_init_loaded_by_path(frontend, tree):
    _, dom = tree
    mod = load_clausal_module(str(dom / "__init__.pl"))
    assert _answers(mod) == [5]
    assert "sbp_pkg.dom.schema" in sys.modules
    assert "dom.schema" not in sys.modules


def test_package_init_imported_by_dotted_name(frontend, tree):
    assert _answers(importlib.import_module("sbp_pkg.dom")) == [5]
    assert "sbp_pkg.dom.schema" in sys.modules


def test_plain_module_in_the_package_loaded_by_path(frontend, tree):
    _, dom = tree
    assert _answers(load_clausal_module(str(dom / "rules.pl"))) == [5]
    assert "sbp_pkg.dom.schema" in sys.modules
    assert "schema" not in sys.modules


def test_slash_path_from_a_file_loaded_by_path(frontend, tree):
    _, dom = tree
    assert _answers(load_clausal_module(str(dom / "nest.pl"))) == [6]
    assert "sbp_pkg.dom.sub.leaf" in sys.modules
    assert "sub.leaf" not in sys.modules


def test_sibling_still_beats_a_top_level_module_when_loaded_by_path(
        frontend, tree, monkeypatch):
    tmp, dom = tree
    _write(tmp / "top" / "schema.pl",
           ":- module(schema, [limit/1]).\nlimit(top).\n")
    monkeypatch.setattr(sys, "path", sys.path + [str(tmp / "top")])
    importlib.invalidate_caches()
    assert _answers(load_clausal_module(str(dom / "__init__.pl"))) == [5]
    assert "schema" not in sys.modules


def test_path_load_with_the_file_directory_on_sys_path(frontend, tree,
                                                       monkeypatch):
    # The directory itself is the most specific entry: the sibling is the
    # top-level ``schema`` there, as it was before the fix.
    _, dom = tree
    monkeypatch.setattr(sys, "path", [str(dom)] + sys.path)
    importlib.invalidate_caches()
    assert _answers(load_clausal_module(str(dom / "rules.pl"))) == [5]
    assert "schema" in sys.modules


def test_no_sys_path_entry_holds_the_sibling_is_refused(frontend, tree,
                                                        monkeypatch):
    tmp, dom = tree
    monkeypatch.setattr(sys, "path",
                        [p for p in sys.path if p != str(tmp / "fresh")])
    importlib.invalidate_caches()
    with pytest.raises((SyntaxError, ImportError)) as ei:
        load_clausal_module(str(dom / "rules.pl"))
    assert "no sys.path entry" in str(ei.value)


def test_package_root_round_trips_or_declines(tmp_path):
    from clausal.tools.prolog_to_clausal import package_root
    init = str(tmp_path / "pkg" / "dom" / "__init__.pl")
    rules = str(tmp_path / "pkg" / "dom" / "rules.pl")
    assert package_root(init, "pkg.dom") == str(tmp_path)
    assert package_root(rules, "pkg.dom.rules") == str(tmp_path)
    assert package_root(init, "_clausal_test___init__") is None
    assert package_root(rules, "_clausal_test_rules") is None
    assert package_root(rules, "rules") == str(tmp_path / "pkg" / "dom")


@pytest.mark.parametrize("modname,fname", [
    ("sbp_pkg.dom", "__init__.clausal"),
    ("sbp_pkg.dom.rules", "rules.clausal"),
    ("_clausal_test___init__", "__init__.clausal"),
    ("_clausal_test_rules", "rules.clausal"),
])
def test_undefined_name_hint_names_the_full_dotted_sibling(
        tmp_path, monkeypatch, modname, fname):
    # The seam-side twin: the NameError hint that names the sibling which
    # exports the missing name qualifies it by the same package root.
    from clausal.predicate_diagnostics import UndefinedNameError
    dom = tmp_path / "fresh" / "sbp_pkg" / "dom"
    _write(tmp_path / "fresh" / "sbp_pkg" / "__init__.clausal", "")
    _write(dom / fname, "answer(X) <- cite(X)\n")
    _write(dom / "schema.clausal", "-module(schema, [cite(X)])\ncite(1)\n")
    monkeypatch.setattr(sys, "path", [str(tmp_path / "fresh")] + sys.path)
    exc = UndefinedNameError("name 'cite' is not defined", name="cite",
                             module_name=modname,
                             module_file=str(dom / fname))
    assert "-import_from(sbp_pkg.dom.schema, [cite])" in str(exc)
