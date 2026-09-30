"""``clausal.defines_predicate`` and ``clausal.module_binds``: asking a module
about a name WITHOUT going through ``getattr``.

Operator ruling 2026-10-01 makes ``getattr`` on a ``.pl`` module answer a
name the module does not bind with the atom of that name, so the probe
``getattr(mod, name, None) is None`` stops seeing absence there.  These two
functions are the public replacement:

- ``defines_predicate(mod, name, arity=None)``: the module defines, or
  imports and exports, the predicate (any arity when ``arity`` is None);
- ``module_binds(mod, name)``: the name is a REAL attribute of the module
  (in its ``__dict__``: defined, imported, declared or auto-declared).

Both are new on 53bf70df (``clausal`` has neither attribute there).
"""
import importlib
import sys
import textwrap

import pytest

import clausal

FRONT_ENDS = ("translator", "native")

SUB = """\
    :- module(sub, [helper/1]).
    helper(X) :- X = sub_data.
"""

FACADE = """\
    :- module(PKG, [top/1, helper/1]).
    :- use_module(PKG/sub, [helper/1]).
    top(X) :- helper(X).
    top(root_data).
    private_pred(1).
"""

SEAM = """\
    -module(sm, [go(X), cite_data])
    go(1),
    hidden(2),
"""


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    made = []

    def _make(fe):
        tag = f"dpmb_{fe}"
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", fe)
        monkeypatch.syspath_prepend(str(tmp_path))
        root = tmp_path / tag
        root.mkdir()
        (root / "__init__.pl").write_text(
            textwrap.dedent(FACADE).replace("PKG", tag))
        (root / "sub.pl").write_text(textwrap.dedent(SUB))
        (root / "sm.seam").write_text(textwrap.dedent(SEAM))
        made.append(tag)
        importlib.invalidate_caches()
        return importlib.import_module(tag), tag

    yield _make
    for tag in made:
        for key in [k for k in sys.modules
                    if k == tag or k.startswith(tag + ".")]:
            sys.modules.pop(key, None)


def test_both_are_exported_from_clausal():
    assert "has_predicate" in clausal.__all__
    assert "defines_predicate" in clausal.__all__
    assert "module_binds" in clausal.__all__


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_pl_package_root_answers_its_predicates(pkg, fe):
    root, _tag = pkg(fe)
    assert clausal.defines_predicate(root, "top")
    assert clausal.defines_predicate(root, "top", 1)
    assert not clausal.defines_predicate(root, "top", 2)
    # imported AND exported (the facade's re-export)
    assert clausal.defines_predicate(root, "helper", 1)
    # defined, not exported: still its own predicate
    assert clausal.defines_predicate(root, "private_pred", 1)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_pl_submodule_answers_its_predicates(pkg, fe):
    _root, tag = pkg(fe)
    sub = importlib.import_module(f"{tag}.sub")
    assert clausal.defines_predicate(sub, "helper", 1)
    assert not clausal.defines_predicate(sub, "top")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_missing_name_is_false_for_both(pkg, fe):
    root, tag = pkg(fe)
    sub = importlib.import_module(f"{tag}.sub")
    for mod in (root, sub):
        assert not clausal.defines_predicate(mod, "employment")
        assert not clausal.defines_predicate(mod, "employment", 0)
        assert not clausal.module_binds(mod, "employment")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_predicate_is_not_data(pkg, fe):
    root, _tag = pkg(fe)
    assert clausal.defines_predicate(root, "top", 1)
    assert not clausal.defines_predicate(root, "root_data")


def test_native_auto_declared_data_is_bound(pkg):
    """The native front end binds a data atom its file uses; the name is a
    real attribute of the module, not a predicate."""
    root, _tag = pkg("native")
    assert clausal.module_binds(root, "root_data")
    assert root.root_data == "root_data"
    assert not clausal.defines_predicate(root, "root_data")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_seam_module(pkg, fe):
    _root, tag = pkg(fe)
    sm = importlib.import_module(f"{tag}.sm")
    assert clausal.defines_predicate(sm, "go", 1)
    assert clausal.defines_predicate(sm, "hidden", 1)
    assert not clausal.defines_predicate(sm, "go", 2)
    assert not clausal.defines_predicate(sm, "cite_data")
    assert clausal.module_binds(sm, "cite_data")      # declared in -module
    assert clausal.module_binds(sm, "go")
    assert not clausal.module_binds(sm, "employment")
    assert not clausal.defines_predicate(sm, "employment")


def test_other_argument_forms():
    import json
    assert clausal.module_binds(json, "dumps")
    assert not clausal.module_binds(json, "no_such_thing")
    assert clausal.module_binds("json", "dumps")
    assert not clausal.module_binds("dpmb_never_loaded_xyz", "x")
    with pytest.raises(TypeError):
        clausal.module_binds(42, "x")
    # a Python-backed predicate module, by its -import_from spelling
    assert clausal.defines_predicate("date_time", "date_add")
    assert not clausal.defines_predicate("date_time", "employment")


# ── has_predicate: "is n a predicate I can call through m" ─────────────────
#
# A THIN facade only imports its predicates, so defines_predicate ("does m
# itself define n") is False for them, and module_binds ("is n a real
# attribute") is True for a data atom too: neither answers the predicate
# question the old ``getattr(m, n, None) is not None`` probe asked.

THIN_PL = """\
    :- module(PKG, []).
    :- use_module(PKG/sub, [helper/1]).
    note(thin_data).
"""

THIN_CLAUSAL = """\
    -module(PKG, [thin_cdata])
    -import_from(PKG.csub, [p])
"""

CSUB = """\
    -module(csub, [p(X)])
    p(1),
"""


@pytest.fixture
def thin(tmp_path, monkeypatch):
    made = []

    def _make(fe, kind):
        tag = f"thin_{kind}_{fe}"
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", fe)
        monkeypatch.syspath_prepend(str(tmp_path))
        root = tmp_path / tag
        root.mkdir()
        (root / "sub.pl").write_text(textwrap.dedent(SUB))
        (root / "csub.clausal").write_text(textwrap.dedent(CSUB))
        if kind == "pl":
            (root / "__init__.pl").write_text(
                textwrap.dedent(THIN_PL).replace("PKG", tag))
        elif kind == "clausal":
            (root / "__init__.clausal").write_text(
                textwrap.dedent(THIN_CLAUSAL).replace("PKG", tag))
        else:
            (root / "__init__.py").write_text(
                f"from {tag}.sub import helper\n"
                f"from {tag}.csub import p\n")
        made.append(tag)
        importlib.invalidate_caches()
        return importlib.import_module(tag)

    yield _make
    for tag in made:
        for key in [k for k in sys.modules
                    if k == tag or k.startswith(tag + ".")]:
            sys.modules.pop(key, None)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_thin_pl_facade_can_call_what_it_imports(thin, fe):
    root = thin(fe, "pl")
    assert clausal.has_predicate(root, "helper")
    assert clausal.has_predicate(root, "helper", 1)
    assert not clausal.has_predicate(root, "helper", 2)
    assert not clausal.defines_predicate(root, "helper")
    assert clausal.module_binds(root, "helper")
    assert clausal.has_predicate(root, "note", 1)       # its own
    for fn in (clausal.has_predicate, clausal.defines_predicate,
               clausal.module_binds):
        assert not fn(root, "employment")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_thin_clausal_facade_can_call_what_it_imports(thin, fe):
    root = thin(fe, "clausal")
    assert clausal.has_predicate(root, "p", 1)
    assert not clausal.defines_predicate(root, "p")
    assert clausal.module_binds(root, "p")
    # a declared data atom: a real attribute, not a predicate
    assert clausal.module_binds(root, "thin_cdata")
    assert not clausal.has_predicate(root, "thin_cdata")
    for fn in (clausal.has_predicate, clausal.defines_predicate,
               clausal.module_binds):
        assert not fn(root, "employment")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_python_facade_can_call_what_it_imports(thin, fe):
    root = thin(fe, "py")
    assert clausal.has_predicate(root, "helper", 1)
    assert clausal.has_predicate(root, "p", 1)
    assert not clausal.defines_predicate(root, "helper")
    assert clausal.module_binds(root, "helper")
    assert not clausal.has_predicate(root, "employment")


def test_a_native_data_atom_is_bound_but_no_predicate(thin):
    root = thin("native", "pl")
    assert clausal.module_binds(root, "thin_data")
    assert not clausal.has_predicate(root, "thin_data")
    assert not clausal.defines_predicate(root, "thin_data")


def test_has_predicate_argument_forms():
    assert clausal.has_predicate("date_time", "date_add")
    assert not clausal.has_predicate("date_time", "employment")
    with pytest.raises(TypeError):
        clausal.has_predicate(42, "x")
