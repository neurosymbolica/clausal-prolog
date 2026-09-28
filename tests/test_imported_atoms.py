"""``clausal.imported_atoms(module_or_package)`` -- the atoms a module's or a
package's own files bring in via ``-import_from`` WITHOUT declaring them.

The companion of ``declared_atoms`` (tests/test_declared_atoms.py): the two
answers are disjoint, so ``declared_atoms(m) | imported_atoms(m).keys()`` is
every atom the files can name.  The motivating shape is a package
``__init__.clausal`` with no ``-module`` list whose atoms all arrive by
``-import_from`` -- ``declared_atoms`` rightly refuses them, and before this
accessor a consumer had to read the compiler's internal dotted
``"<exporter>.<name>"`` namespace keys.

Fixtures: tests/fixtures/ia_vocab.clausal, ia_vocab2.clausal,
ia_plain_importer.clausal and the ia_pkg/ package.
"""

from __future__ import annotations

import importlib
import sys

import pytest

import clausal
import clausal.import_hook  # noqa: F401 -- a directory package needs the real finder
from clausal.logic.exceptions import LogicException


VOCAB = "tests.fixtures.ia_vocab"
VOCAB2 = "tests.fixtures.ia_vocab2"
PKG = "tests.fixtures.ia_pkg"
REDECL = "tests.fixtures.ia_pkg.redecl"
PLAIN = "tests.fixtures.ia_plain_importer"

# Only the package __init__ loaded.  restricted_procedure is imported and not
# declared by any LOADED file of the package yet (see the loaded-submodule
# test).  shared_kind is imported from both exporters; the later directive
# wins, as the name's binding does.  open_procedure is also listed from
# ia_vocab2, which merely imports it, so ia_vocab (the owner) is the answer.
# aliased_src is imported under a local alias; the ATOM is the exporter's
# spelling.  vocab_rel is a predicate.
INIT_ONLY = {
    "open_procedure": VOCAB,
    "shared_kind": VOCAB2,
    "restricted_procedure": VOCAB,
    "aliased_src": VOCAB,
}


@pytest.fixture
def load():
    """Import modules on a clean slate; evict every new module afterwards."""
    before = set(sys.modules)

    def _load(*names):
        for name in names:
            importlib.import_module(name)

    yield _load
    for name in list(sys.modules):
        if name not in before and name.startswith("tests.fixtures.ia_"):
            sys.modules.pop(name, None)


def test_moduleless_package_init_reports_its_imported_atoms(load):
    load(PKG)
    got = clausal.imported_atoms(PKG)
    assert isinstance(got, dict)
    assert got == INIT_ONLY
    # The motivating gap: declared_atoms refuses every one of them.
    assert clausal.declared_atoms(PKG) == frozenset()


def test_imported_predicate_is_not_an_atom(load):
    load(PKG, PLAIN)
    assert "vocab_rel" not in clausal.imported_atoms(PKG)
    assert "vocab_rel" not in clausal.imported_atoms(PLAIN)


def test_alias_reports_the_atom_spelling_not_the_local_name(load):
    load(PKG)
    got = clausal.imported_atoms(PKG)
    assert got["aliased_src"] == VOCAB
    assert "aliased_local" not in got
    # The alias binds the exporter's atom.
    assert vars(sys.modules[PKG])["aliased_local"] == "aliased_src"


def test_redeclared_import_is_declared_not_imported(load):
    load(REDECL)
    got = clausal.imported_atoms(REDECL)
    assert got == {"second_only": VOCAB2, "shared_kind": VOCAB}
    assert clausal.declared_atoms(REDECL) == {"restricted_procedure"}


def test_package_union_is_disjoint_from_declared_atoms(load):
    load(PKG, REDECL)
    got = clausal.imported_atoms(PKG)
    # restricted_procedure: redecl (a file of the package) declares it, so
    # the package declares it and it is not reported as imported.
    # shared_kind: __init__ says ia_vocab2, redecl says ia_vocab -- the
    # package's own file is asked first.
    assert got == {
        "open_procedure": VOCAB,
        "shared_kind": VOCAB2,
        "aliased_src": VOCAB,
        "second_only": VOCAB2,
    }
    assert not set(got) & clausal.declared_atoms(PKG)


def test_only_the_exporters_own_declarations_count(load):
    """One level: ia_vocab2 imports open_procedure but does not declare it,
    so importing it from ia_vocab2 alone does not make it an imported atom
    of ia_vocab2's importer -- and ia_vocab2 itself does not report it as
    imported either, since ia_vocab declares it."""
    load(VOCAB2)
    assert clausal.imported_atoms(VOCAB2) == {"open_procedure": VOCAB}
    assert "open_procedure" not in clausal.declared_atoms(VOCAB2)


def test_plain_module_clash_later_directive_wins(load):
    load(PLAIN)
    assert clausal.imported_atoms(PLAIN) == {
        "second_only": VOCAB2,
        "shared_kind": VOCAB,  # listed from ia_vocab2 first, ia_vocab later
    }
    # The bare name is bound by the later directive too.
    assert "local_one" in clausal.declared_atoms(PLAIN)


def test_designator_forms_agree(load):
    load(PKG)
    mod = sys.modules[PKG]
    assert clausal.imported_atoms(mod) == INIT_ONLY
    assert clausal.imported_atoms(mod.__clausal_module__) == INIT_ONLY
    assert clausal.imported_atoms(PKG) == INIT_ONLY


def test_result_is_a_fresh_sorted_dict(load):
    load(PKG, REDECL)
    first = clausal.imported_atoms(PKG)
    assert list(first) == sorted(first)
    first["mutated"] = "x"
    assert "mutated" not in clausal.imported_atoms(PKG)


def test_module_without_imports_answers_empty(load):
    load(VOCAB)
    assert clausal.imported_atoms(VOCAB) == {}


def test_unloaded_name_raises_existence_error():
    with pytest.raises(LogicException) as ei:
        clausal.imported_atoms("ia_no_such_module.anywhere")
    assert "existence_error" in str(ei.value)


def test_rejects_non_module():
    with pytest.raises(TypeError):
        clausal.imported_atoms(42)


def test_exported_from_clausal():
    assert "imported_atoms" in clausal.__all__
