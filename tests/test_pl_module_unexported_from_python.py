"""Operator ruling 2026-10-01: "In Python code, Python semantics apply" --
no export privacy from Python.  Python code reaches a ``.pl`` module's
UNEXPORTED predicates the way it reaches any Python module attribute:
``getattr(m, 'name')``, ``m.name`` and ``from m import name`` all give the
predicate's handle, and the predicate runs through ``solve(..., module=m)``.

Possible but NOT supported long-term and not advisable (documented in
docs/importing_prolog.md and docs/public-api.md; no runtime warning):
Python callers should use exported predicates.

This already held on 841b6b24 under both front ends; these tests pin it.
"""
import importlib
import sys
import textwrap
import warnings

import pytest

import clausal
from clausal import Var, deref, solve

FRONT_ENDS = ("translator", "native")

PRIV = """\
    :- module(MOD, [rate/1]).
    rate(X) :- helper(X).
    helper(5).
    secret(a, b).
    secret(c, d).
"""


@pytest.fixture
def plmod(tmp_path, monkeypatch):
    made = []

    def _make(fe, stem):
        tag = f"{stem}_{fe}"
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", fe)
        monkeypatch.syspath_prepend(str(tmp_path))
        (tmp_path / f"{tag}.pl").write_text(
            textwrap.dedent(PRIV).replace("MOD", tag))
        made.append(tag)
        importlib.invalidate_caches()
        return importlib.import_module(tag), tag

    yield _make
    for tag in made:
        sys.modules.pop(tag, None)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_attribute_access_reaches_an_unexported_predicate(plmod, fe):
    m, _tag = plmod(fe, "ux_attr")
    with warnings.catch_warnings():
        warnings.simplefilter("error")        # no runtime warning
        for name in ("helper", "secret"):
            handle = getattr(m, name)
            assert clausal.module_binds(m, name)
            assert handle == vars(m)[name]
            assert handle != name               # the handle, not the atom
        assert m.helper == getattr(m, "helper")
    assert clausal.has_predicate(m, "helper", 1)
    assert clausal.has_predicate(m, "secret", 2)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_from_import_reaches_an_unexported_predicate(plmod, fe):
    m, tag = plmod(fe, "ux_from")
    ns = {}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        exec(f"from {tag} import helper, secret, rate", ns)
    assert ns["helper"] == m.helper and ns["secret"] == m.secret
    assert ns["rate"] == m.rate


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_an_unexported_predicate_runs_from_python(plmod, fe):
    m, _tag = plmod(fe, "ux_run")
    x = Var()
    assert [deref(x) for _ in solve(("helper", x), module=m)] == [5]
    a, b = Var(), Var()
    assert [(deref(a), deref(b)) for _ in solve(("secret", a, b), module=m)] \
        == [("a", "b"), ("c", "d")]
