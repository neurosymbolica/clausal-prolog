"""``clausal.declared_atoms(module_or_package)`` -- the atoms a module's or a
package's OWN files declare.

The answer is the union of each file's ``-module``/``-private`` atom record
(``cells.DECLARED_ATOMS_KEY``) over the module and, for a package, its loaded
submodules.  It must not include an ``-import_from``ed atom, and it must not
depend on the order the files were imported in (the module NAMESPACE does).
"""

from __future__ import annotations

import importlib
import sys
import uuid

import pytest

import clausal
import clausal.import_hook  # noqa: F401 -- a directory package needs the real finder
from clausal.logic.exceptions import LogicException
from tests._suffix import SEAM


VOCAB = "-module(da_vocab, [foreign_atom])\n"
INIT = (
    "-import_from(da_pkg.alpha, [red, green])\n"
    "-import_from(da_pkg.beta, [circle])\n"
    "-module(da_pkg, [red, green, circle, pkg_own])\n"
)
ALPHA = (
    "-module(alpha, [red, green, colour/1])\n"
    "-private([hidden_a])\n"
    "colour(red),\n"
    "colour(green),\n"
)
BETA = (
    "-import_from(da_vocab, [foreign_atom])\n"
    "-module(beta, [circle, shape/1])\n"
    "shape(circle),\n"
    "shape(foreign_atom),\n"
)

PKG_ATOMS = frozenset({"red", "green", "hidden_a", "circle", "pkg_own"})


@pytest.fixture
def tree(tmp_path, request):
    (tmp_path / f"da_vocab{SEAM}").write_text(VOCAB)
    pkg = tmp_path / "da_pkg"
    pkg.mkdir()
    (pkg / f"__init__{SEAM}").write_text(INIT)
    (pkg / f"alpha{SEAM}").write_text(ALPHA)
    (pkg / f"beta{SEAM}").write_text(BETA)

    def load(order):
        """Import *order* on a clean slate; returns an evict() callable."""
        before = set(sys.modules)
        done = []

        def evict():
            if done:
                return
            done.append(True)
            for name in list(sys.modules):
                if name not in before:
                    sys.modules.pop(name, None)
            if str(tmp_path) in sys.path:
                sys.path.remove(str(tmp_path))
            importlib.invalidate_caches()

        # Registered before importing, so a failed import still cleans up.
        request.addfinalizer(evict)
        sys.path.insert(0, str(tmp_path))
        importlib.invalidate_caches()
        for name in order:
            importlib.import_module(name)
        return evict

    return load


def test_package_union_excludes_imported_atom(tree):
    evict = tree(["da_pkg"])
    try:
        got = clausal.declared_atoms("da_pkg")
        assert isinstance(got, frozenset)
        assert got == PKG_ATOMS
        # The imported atom is bound in beta's namespace but beta did not
        # declare it.
        assert "foreign_atom" in vars(sys.modules["da_pkg.beta"])
        assert "foreign_atom" not in got
        # Predicates are not atoms.
        assert "colour" not in got and "shape" not in got
    finally:
        evict()


def test_single_module_and_designator_forms(tree):
    evict = tree(["da_pkg"])
    try:
        beta = sys.modules["da_pkg.beta"]
        assert clausal.declared_atoms(beta) == {"circle"}
        assert clausal.declared_atoms("da_pkg.alpha") == {
            "red", "green", "hidden_a"}
        # A clausal Module answers like the Python module it came from.
        pkg = sys.modules["da_pkg"]
        assert clausal.declared_atoms(pkg.__clausal_module__) == PKG_ATOMS
        assert clausal.declared_atoms(pkg) == PKG_ATOMS
        # The owner of the imported atom declares it.
        assert clausal.declared_atoms("da_vocab") == {"foreign_atom"}
    finally:
        evict()


@pytest.mark.parametrize("order", [
    ["da_pkg"],
    ["da_pkg.beta", "da_pkg.alpha", "da_pkg"],
    ["da_vocab", "da_pkg.alpha", "da_pkg.beta", "da_pkg"],
])
def test_answer_does_not_depend_on_load_order(tree, order):
    evict = tree(order)
    try:
        assert clausal.declared_atoms("da_pkg") == PKG_ATOMS
    finally:
        evict()


def test_only_loaded_submodules_count(tmp_path):
    """Lookup-only: a submodule that was never imported is not counted, and
    asking does not import it."""
    pkg = tmp_path / "da_lazy"
    pkg.mkdir()
    (pkg / f"__init__{SEAM}").write_text("-module(da_lazy, [top])\n")
    (pkg / f"later{SEAM}").write_text("-module(later, [deep])\n")
    before = set(sys.modules)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        importlib.import_module("da_lazy")
        assert clausal.declared_atoms("da_lazy") == {"top"}
        assert "da_lazy.later" not in sys.modules
        importlib.import_module("da_lazy.later")
        assert clausal.declared_atoms("da_lazy") == {"top", "deep"}
    finally:
        for name in list(sys.modules):
            if name not in before:
                sys.modules.pop(name, None)
        sys.path.remove(str(tmp_path))
        importlib.invalidate_caches()


def test_unloaded_name_raises_existence_error():
    with pytest.raises(LogicException) as ei:
        clausal.declared_atoms("da_no_such_module.anywhere")
    assert "existence_error" in str(ei.value)


def test_rejects_non_module():
    with pytest.raises(TypeError):
        clausal.declared_atoms(42)


def test_exported_from_clausal():
    assert "declared_atoms" in clausal.__all__



def test_package_answer_is_a_vocabulary_not_the_root_attributes(tmp_path):
    """For a package, ``declared_atoms`` is the union over its own files
    (its atom vocabulary), NOT the names bound on the package root: an atom
    declared only in a submodule is listed, yet the root has no such
    attribute.  The spellings are unique to this test, so no earlier load
    has put them in the process-wide atom pool."""
    tag = uuid.uuid4().hex[:8]
    name, sub_atom, root_atom = f"da_voc_{tag}", f"only_in_sub_{tag}", f"in_root_{tag}"
    pkg_dir = tmp_path / name
    pkg_dir.mkdir()
    (pkg_dir / f"__init__{SEAM}").write_text(
        f"-import_from({name}.sub, [s/1])\n-private([{root_atom}])\n")
    (pkg_dir / f"sub{SEAM}").write_text(
        f"-private([{sub_atom}])\ns({sub_atom}),\n")
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        pkg = importlib.import_module(name)
        assert f"{name}.sub" in sys.modules
        got = clausal.declared_atoms(pkg)
        assert got == {sub_atom, root_atom}
        assert not hasattr(pkg, sub_atom)
        assert sub_atom in vars(sys.modules[f"{name}.sub"])
        assert hasattr(pkg, root_atom)
    finally:
        for m in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
            sys.modules.pop(m, None)
        sys.path.remove(str(tmp_path))
        importlib.invalidate_caches()
