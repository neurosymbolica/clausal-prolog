"""Operator ruling 2026-10-01: the ``.pl`` data-import ruling extends to
ATTRIBUTE ACCESS.  ``getattr(mod, 'name')`` / ``mod.name`` on a module loaded
from ``.pl`` (either front end, a package's ``__init__.pl`` included), for an
atom-shaped name the module neither defines as a predicate (any arity) nor
binds, is the ATOM ``'name'`` instead of ``AttributeError``.

On 53bf70df reading a root atom off a ``.pl`` package root raised
``AttributeError: module 'x' has no attribute 'employment'``.

Atom-shaped is ``iso_l3_directives._is_declarable`` (a lowercase
identifier, no keyword, no reserved name): no dunder, private, TitleCase,
keyword or non-identifier name is answered.  ``from M import name`` in
Python code is getattr (operator ruling 2026-10-01); in Clausal code it is a
seam ``-import_from`` and keeps its own path.  ``.clausal``/``.seam`` and
Python modules are unchanged.  Absence is asked through ``clausal.defines_predicate`` /
``clausal.module_binds``.
"""
import importlib
import inspect
import sys
import textwrap
import warnings

import pytest

import clausal
from clausal.lint_warnings import ClausalImportedDataNameWarning

FRONT_ENDS = ("translator", "native")

FACADE = """\
    :- module(PKG, [citation/2, helper/1]).
    :- use_module(PKG/sub, [helper/1]).
    citation(k1, x).
"""

SUB = """\
    :- module(sub, [helper/1]).
    helper(sub_data).
"""

LATER = """\
    :- module(later, [l/1]).
    l(1).
"""


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    made = []

    def _make(fe, stem):
        tag = f"{stem}_{fe}"
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", fe)
        monkeypatch.syspath_prepend(str(tmp_path))
        root = tmp_path / tag
        root.mkdir()
        (root / "__init__.pl").write_text(
            textwrap.dedent(FACADE).replace("PKG", tag))
        (root / "sub.pl").write_text(textwrap.dedent(SUB))
        (root / "later.pl").write_text(textwrap.dedent(LATER))
        (root / "cl.clausal").write_text("-module(cl, [go(X)])\ngo(1),\n")
        (root / "py_side.py").write_text("x = 1\n")
        made.append(tag)
        importlib.invalidate_caches()
        return importlib.import_module(tag), tag

    yield _make
    for tag in made:
        for key in [k for k in sys.modules
                    if k == tag or k.startswith(tag + ".")]:
            sys.modules.pop(key, None)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_package_root_answers_a_data_name_with_its_atom(pkg, fe):
    root, _tag = pkg(fe, "ga_root")
    assert getattr(root, "employment") == "employment"
    assert root.employment == "employment"
    assert type(root.employment) is str
    assert hasattr(root, "employment")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_plain_pl_module_answers_too(pkg, fe):
    _root, tag = pkg(fe, "ga_sub")
    sub = importlib.import_module(f"{tag}.sub")
    assert sub.employment == "employment"
    assert getattr(sub, "cite") == "cite"


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_absence_is_asked_through_the_public_api(pkg, fe):
    root, _tag = pkg(fe, "ga_api")
    assert root.employment == "employment"
    assert not clausal.has_predicate(root, "employment")
    assert not clausal.defines_predicate(root, "employment")
    assert not clausal.module_binds(root, "employment")
    assert clausal.has_predicate(root, "citation", 2)
    assert clausal.defines_predicate(root, "citation", 2)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_bound_names_are_unchanged(pkg, fe):
    root, _tag = pkg(fe, "ga_bound")
    assert root.citation != "citation"          # the predicate's handle
    assert clausal.defines_predicate(root, "citation", 2)
    assert root.sub.__name__.endswith(".sub")   # a loaded submodule


@pytest.mark.parametrize("fe", FRONT_ENDS)
@pytest.mark.parametrize("name", [
    "__foo__", "__wrapped__", "__all__", "_x", "_private", "Employment",
    "true", "false", "undefined", "class", "a-b", "1x", "",
])
def test_names_that_are_not_atom_shaped_stay_missing(pkg, fe, name):
    root, _tag = pkg(fe, "ga_shape")
    with pytest.raises(AttributeError):
        getattr(root, name)
    assert not hasattr(root, name)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_an_unimported_submodule_is_not_data(pkg, fe):
    """``later`` is a submodule nobody imported yet: attribute access does
    not answer it with an atom, and ``from pkg import later`` (importlib's
    ``hasattr`` probe) still imports it."""
    root, tag = pkg(fe, "ga_later")
    assert f"{tag}.later" not in sys.modules
    with pytest.raises(AttributeError):
        getattr(root, "later")
    ns = {}
    exec(f"from {tag} import later", ns)
    assert ns["later"].__name__ == f"{tag}.later"


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_from_import_in_python_is_getattr(pkg, fe):
    """Operator ruling 2026-10-01 ("in Python code, Python semantics
    apply"): ``from M import name`` in Python behaves exactly like
    ``getattr(M, 'name')``, so an unbound atom-shaped name is its atom.
    On 841b6b24 the IMPORT_FROM opcode was excluded and this raised
    ``ImportError: cannot import name 'employment'``."""
    root, tag = pkg(fe, "ga_from")
    ns = {}
    exec(f"from {tag} import employment, citation", ns)
    assert ns["employment"] == "employment" == getattr(root, "employment")
    assert type(ns["employment"]) is str
    assert ns["citation"] == root.citation          # bound: unchanged


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_from_import_in_a_python_module_file(pkg, fe, tmp_path):
    """The same from a real ``.py`` module (not ``exec``)."""
    _root, tag = pkg(fe, "ga_fromfile")
    (tmp_path / f"user_{tag}.py").write_text(
        f"from {tag} import employment\n")
    importlib.invalidate_caches()
    try:
        user = importlib.import_module(f"user_{tag}")
        assert user.employment == "employment"
    finally:
        sys.modules.pop(f"user_{tag}", None)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_from_import_of_a_missing_submodule_name_is_the_atom(pkg, fe):
    """``from pkg import nosuchsub``: importlib's submodule probe finds no
    ``pkg.nosuchsub`` (and swallows that), then IMPORT_FROM reads the
    attribute, which -- like ``pkg.nosuchsub`` -- is the atom."""
    root, tag = pkg(fe, "ga_nosub")
    ns = {}
    exec(f"from {tag} import nosuchsub", ns)
    assert ns["nosuchsub"] == "nosuchsub" == root.nosuchsub
    assert f"{tag}.nosuchsub" not in sys.modules


@pytest.mark.parametrize("fe", FRONT_ENDS)
@pytest.mark.parametrize("name", ["Employment", "_employment", "__wrapped__"])
def test_from_import_of_a_name_that_is_not_atom_shaped_still_fails(
        pkg, fe, name):
    _root, tag = pkg(fe, "ga_fromshape")
    with pytest.raises(ImportError, match=f"cannot import name '{name}'"):
        exec(f"from {tag} import {name}", {})


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_near_miss_warns_once_per_module_and_name(pkg, fe):
    root, _tag = pkg(fe, "ga_typo")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert root.citaton == "citaton"
        assert getattr(root, "citaton") == "citaton"
        assert hasattr(root, "citaton")
        assert root.cite_far_away_name == "cite_far_away_name"
    hits = [w for w in caught
            if issubclass(w.category, ClausalImportedDataNameWarning)]
    assert len(hits) == 1, [str(w.message) for w in caught]
    msg = str(hits[0].message)
    assert "`citation`" in msg and "citaton" in msg
    assert hits[0].filename == __file__


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_tooling_probes_are_unaffected(pkg, fe):
    root, _tag = pkg(fe, "ga_tools")
    assert inspect.ismodule(root)
    assert inspect.getmodule(root) is root
    names = {n for n, _v in inspect.getmembers(root)}
    assert "employment" not in names
    assert not hasattr(root, "__path__") or isinstance(root.__path__, list)
    ns = {}
    exec(f"from {root.__name__} import *", ns)
    assert "employment" not in ns


def test_clausal_and_python_modules_are_unchanged(pkg):
    _root, tag = pkg("native", "ga_other")
    cl = importlib.import_module(f"{tag}.cl")
    py = importlib.import_module(f"{tag}.py_side")
    for mod in (cl, py):
        with pytest.raises(AttributeError):
            getattr(mod, "employment")
        assert "__getattr__" not in vars(mod)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_stdlib_hook_lookups_see_no_attribute(pkg, fe):
    """unittest's ``getattr(module, 'load_tests', None)`` must stay None,
    or the loader calls the str (review finding)."""
    import unittest
    root, _tag = pkg(fe, "ga_unittest")
    suite = unittest.TestLoader().loadTestsFromModule(root)
    assert suite.countTestCases() == 0
    assert root.load_tests == "load_tests"      # user code still gets it
