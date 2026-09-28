"""An ISO ``name/N`` export entry whose arity the module neither defines nor
declares, while the module HAS clauses for ``name`` at another arity, warns
at load: ``-module(m, [base/9])`` over ``base/2`` clauses is almost always a
typo.  A warning, not a refusal (operator ruling 2026-09-29): an exported
``name/N`` with no clauses here is a legal procedure (calling it raises
``existence_error``), so the module still loads.
"""

from __future__ import annotations

import sys
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.lint_warnings import (
    ClausalExportArityMismatchWarning, ClausalLintWarning,
)
from clausal.logic.compiler_v2 import _warn_export_arity_mismatches
from clausal.pythonic_ast.nodes import Directive, ModuleDeclaration


@pytest.fixture
def load(tmp_path):
    names = []

    def _load(name, src):
        path = tmp_path / f"{name}.clausal"
        path.write_text(src)
        sys.modules.pop(name, None)
        names.append(name)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            mod = _load_module(name, str(path))
        return mod, path, [w for w in caught
                           if issubclass(w.category,
                                         ClausalExportArityMismatchWarning)]

    yield _load
    for name in names:
        sys.modules.pop(name, None)


def test_the_warning_is_a_lint_warning():
    assert issubclass(ClausalExportArityMismatchWarning, ClausalLintWarning)


def test_export_at_an_arity_with_no_clauses_warns(load):
    mod, path, caught = load(
        "eam_typo", "-module(eam_typo, [base/9])\nbase(1, 2),\n")
    assert len(caught) == 1
    message = str(caught[0].message)
    # Located at the export entry, names both arities, suggests the fix.
    assert message.startswith(f"{path}:1: ")
    assert "eam_typo lists base/9" in message
    assert "its clauses are for base/2" in message
    assert "did you mean base/2?" in message
    assert "-dynamic(base/9)" in message
    # Only a warning: the module loaded.
    assert mod.__clausal_module__ is not None


def test_a_private_entry_warns_at_its_own_line(load):
    _mod, path, caught = load(
        "eam_priv",
        "-module(eam_priv, [base/2])\n-private([base/4])\nbase(1, 2),\n")
    assert [str(w.message).split(": ", 1)[0] for w in caught] == [f"{path}:2"]
    assert "base/4" in str(caught[0].message)


def test_export_at_the_clause_arity_is_silent(load):
    _mod, _path, caught = load(
        "eam_ok", "-module(eam_ok, [base/2])\nbase(1, 2),\n")
    assert caught == []


def test_export_of_a_name_with_no_clauses_is_silent(load):
    # Ruling 2026-09-25: a clause-less exported name/N is a procedure.
    _mod, _path, caught = load("eam_none", "-module(eam_none, [nothing/3])\n")
    assert caught == []


def test_export_declared_dynamic_at_its_arity_is_silent(load):
    _mod, _path, caught = load(
        "eam_dyn",
        "-module(eam_dyn, [base/3])\n-dynamic(base/3)\nbase(1, 2),\n")
    assert caught == []


def test_warns_once_per_entry_on_a_cached_reload(load):
    src = "-module(eam_twice, [base/9])\nbase(1, 2),\n"
    _mod, _path, first = load("eam_twice", src)
    _mod, _path, second = load("eam_twice", src)
    assert len(first) == 1 and len(second) == 1


# A .clausal/.pl file gives a name one arity (the rewriter refuses base/2
# beside base/3 in one file), so "clauses at the exported arity AND at
# another" is exercised on the check itself, with cell heads.

class _Clause:
    def __init__(self, head):
        self.head = head
        self.body = True


def _run(exports, heads, extra_items=()):
    items = [ModuleDeclaration(module_name="m", exports=[]),
             *extra_items,
             *(Directive(name="predicate_export", specs=[spec])
               for spec in exports)]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _warn_export_arity_mismatches(
            items, [_Clause(h) for h in heads], "m", {})
    return [w for w in caught
            if issubclass(w.category, ClausalExportArityMismatchWarning)]


def test_export_with_clauses_at_its_arity_and_another_is_silent():
    assert _run([("base", 2)], [("base", 1, 2), ("base", 1, 2, 3)]) == []


def test_check_names_every_defined_arity():
    caught = _run([("base", 9)], [("base", 1, 2), ("base", 1, 2, 3)])
    assert len(caught) == 1
    message = str(caught[0].message)
    assert "its clauses are for base/2, base/3" in message
    assert "did you mean one of base/2, base/3?" in message


def test_meta_predicate_declaration_at_the_arity_is_silent():
    meta = Directive(name="meta_predicate", specs=[("base", 3, ("0", "?", "?"))])
    assert _run([("base", 3)], [("base", 1, 2)], [meta]) == []
