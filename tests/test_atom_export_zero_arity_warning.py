"""A bare name exported as an ATOM and also made a PREDICATE of any arity in
the same module warns at load (operator ruling 2026-09-26; widened to any
arity and to clause-free declarations by roborev 228, after measuring: no
corpus module and no on-disk in-repo module is added by the widening).

ISO allows an atom ``foo`` and a predicate ``foo/0`` side by side, so this is
a warning, not a refusal.  The harm is at the binding: with ``foo,`` (or
``foo <- ...``) in the file, the module attribute ``foo`` -- in the module
and in every importer -- is the predicate's HANDLE, not the atom ``'foo'``,
so data keyed by the atom that is read through ``module.foo`` silently stops
matching (measured 2026-09-26: ``hm.foo == 'hm\\x1ffoo'``).
"""

from __future__ import annotations

import sys
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.lint_warnings import (
    ClausalAtomExportDefinedAsPredicateWarning, ClausalLintWarning,
)
from tests._suffix import SEAM


@pytest.fixture
def load(tmp_path):
    names = []

    def _load(name, src):
        path = tmp_path / f"{name}{SEAM}"
        path.write_text(src)
        sys.modules.pop(name, None)
        names.append(name)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            mod = _load_module(name, str(path))
        return mod, [w for w in caught
                     if issubclass(w.category,
                                   ClausalAtomExportDefinedAsPredicateWarning)]

    yield _load
    for name in names:
        sys.modules.pop(name, None)


def test_the_warning_is_a_lint_warning():
    assert issubclass(ClausalAtomExportDefinedAsPredicateWarning,
                      ClausalLintWarning)


def test_an_exported_atom_with_a_zero_arity_fact_warns(load):
    mod, caught = load("aw_fact", "-module(aw_fact, [foo, kind(X)])\n"
                       "foo,\nkind(foo),\n")
    assert len(caught) == 1
    message = str(caught[0].message)
    assert "aw_fact exports `foo` as an ATOM" in message
    assert "defines the predicate foo/0" in message
    assert "a fact `foo,`" in message
    assert "Drop the foo/0 definition if it is only there for conformance" in message
    assert "rename" in message
    # The harm it names is real: the attribute is the handle, not the atom.
    assert mod.foo != "foo"


def test_an_exported_atom_with_a_zero_arity_rule_warns(load):
    _mod, caught = load("aw_rule", "-module(aw_rule, [foo, kind(X)])\n"
                        "foo <- kind(1)\nkind(1),\n")
    assert len(caught) == 1
    assert "a rule `foo <- ...`" in str(caught[0].message)


def test_several_clauses_warn_once_per_name(load):
    _mod, caught = load("aw_once", "-module(aw_once, [foo, bar, kind(X)])\n"
                        "foo,\nfoo <- kind(1)\nbar,\nkind(1),\n")
    assert sorted(str(w.message).split("`")[1] for w in caught) == ["bar", "foo"]


def test_a_plain_atom_export_does_not_warn(load):
    mod, caught = load("aw_plain", "-module(aw_plain, [foo, kind(X)])\n"
                       "kind(foo),\n")
    assert caught == []
    assert mod.foo == "foo"


def test_an_atom_export_beside_foo_1_warns(load):
    """The hazard is binding by NAME, not arity: the module attribute ``foo``
    is the handle of ``foo/1`` too (roborev 228)."""
    mod, caught = load("aw_arity", "-module(aw_arity, [foo, kind(X)])\n"
                       "foo(1),\nkind(foo),\n")
    assert len(caught) == 1
    message = str(caught[0].message)
    assert "defines the predicate foo/1 (clauses for foo/1)" in message
    assert "write foo/1 in the export list" in message
    assert mod.foo != "foo"


@pytest.mark.parametrize("decl, shown", [
    ("-dynamic(foo/0)\n", "-dynamic(foo/0)"),
    ("-dynamic(foo/2)\n", "-dynamic(foo/2)"),
])
def test_a_clause_free_declaration_warns(load, decl, shown):
    mod, caught = load("aw_decl", "-module(aw_decl, [foo, kind(X)])\n"
                       + decl + "kind(foo),\n")
    assert len(caught) == 1
    assert f"({shown})" in str(caught[0].message)
    assert mod.foo != "foo"


def test_an_iso_foo_0_export_does_not_warn(load):
    _mod, caught = load("aw_iso", "-module(aw_iso, [foo/0])\nfoo,\n")
    assert caught == []


def test_a_specialize_alias_warns(load):
    src = ("-import_from(clausal.examples.metainterpreters, [solve])\n"
           "-module(aw_spec, [solve_graph, graph_program(P)])\n"
           "graph_program(PROGRAM) <- (PROGRAM is [[[\"edge\", \"a\", \"b\"], []]])\n"
           "-specialize(solve, graph_program, alias=solve_graph)\n")
    _mod, caught = load("aw_spec", src)
    assert len(caught) == 1
    assert "(-specialize(..., alias=solve_graph))" in str(caught[0].message)
