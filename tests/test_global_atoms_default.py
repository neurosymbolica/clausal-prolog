"""Tests for Phase 2 and Phase 3 of GLOBAL_ATOMS_DEFAULT.

Phase 2 covers the bare-atom auto-mint hook — undeclared bare atom
references in .clausal files auto-mint into the process-wide
``predicate_builtins`` dict so that two modules each referencing the
same bare atom share its PredicateMeta class identity.

Phase 3 covers the ``-strict_atoms`` directive — a per-file opt-in that
disables the auto-mint default.  Bare references in a strict file must
be reachable via ``-module``, ``-private``, ``-import_from``, qualified
reference, or ``global_atom/2``; any other bare reference is a
compile-time ``NameError``.

The four cases in Phase 2 cover the precedence layering of resolution
rule 1 (private > module-decl > import > global fallthrough), per the
spec at ``implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md``.

Atom names used here are deliberately unique to this test file
(``phase2*`` and ``phase3strict_*`` prefixes) so that cross-test
pollution of the process-wide global dict does not perturb assertions.
"""

from __future__ import annotations

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module, predicate_builtins
from clausal.logic.predicate import PredicateMeta


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def _load_fixture(filename: str, mod_name: str) -> object:
    return _load_module(mod_name, _fixture_path(filename))


# ── Case 1: two modules, both reference bare atom undeclared ────────────────


def test_bare_atoms_share_identity_across_modules():
    """Two modules referencing bare ``phase2red`` without declaring it
    must see the same global PredicateMeta class."""
    mod_a = _load_fixture(
        "global_atoms_a.clausal",
        "tests.fixtures.global_atoms_a",
    )
    mod_b = _load_fixture(
        "global_atoms_b.clausal",
        "tests.fixtures.global_atoms_b",
    )
    assert isinstance(mod_a.phase2red, PredicateMeta)
    assert mod_a.phase2red is mod_b.phase2red
    assert mod_a.phase2red is predicate_builtins["phase2red"]


# ── Case 2: -private shadows the global ─────────────────────────────────────


def test_private_shadows_global():
    """A module that declares ``-private([phase2priv_orange])`` owns a
    distinct private class; a sibling that bare-references the same name
    must auto-mint the global, separate from the private class."""
    mod_a = _load_fixture(
        "global_atoms_priv_a.clausal",
        "tests.fixtures.global_atoms_priv_a",
    )
    mod_b = _load_fixture(
        "global_atoms_priv_b.clausal",
        "tests.fixtures.global_atoms_priv_b",
    )
    assert isinstance(mod_a.phase2priv_orange, PredicateMeta)
    assert isinstance(mod_b.phase2priv_orange, PredicateMeta)
    assert mod_a.phase2priv_orange is not mod_b.phase2priv_orange
    assert mod_b.phase2priv_orange is predicate_builtins["phase2priv_orange"]


# ── Case 3: import wins over global ─────────────────────────────────────────


def test_import_wins_over_global():
    """If a module ``-import_from(M, [phase2import_yellow])`` and also
    bare-references the same name, the bare reference resolves to the
    imported class — not the global fallthrough."""
    mod_owner = _load_fixture(
        "global_atoms_owner.clausal",
        "tests.fixtures.global_atoms_owner",
    )
    mod_importer = _load_fixture(
        "global_atoms_importer.clausal",
        "tests.fixtures.global_atoms_importer",
    )
    assert isinstance(mod_owner.phase2import_yellow, PredicateMeta)
    assert mod_importer.phase2import_yellow is mod_owner.phase2import_yellow


# ── Case 4: module-decl atom does NOT become global ─────────────────────────


def test_module_decl_atom_is_not_global():
    """A module that declares ``-module(M, [phase2declonly_green])`` keeps
    a local class.  Another module that bare-references the same name
    without importing must auto-mint a separate global class."""
    mod_a = _load_fixture(
        "global_atoms_decl_only_a.clausal",
        "tests.fixtures.global_atoms_decl_only_a",
    )
    mod_b = _load_fixture(
        "global_atoms_decl_only_b.clausal",
        "tests.fixtures.global_atoms_decl_only_b",
    )
    assert isinstance(mod_a.phase2declonly_green, PredicateMeta)
    assert isinstance(mod_b.phase2declonly_green, PredicateMeta)
    assert mod_a.phase2declonly_green is not mod_b.phase2declonly_green
    assert mod_b.phase2declonly_green is predicate_builtins["phase2declonly_green"]


# ── Phase 3: -strict_atoms directive ────────────────────────────────────────


def _load_inline_clausal(name: str, source: str):
    """Write `source` to a temp .clausal file and try to load it.

    Used for must-fail-to-load fixtures — keeping them as persistent files
    under ``tests/fixtures/`` would cause pytest's ``.clausal`` collector
    in ``conftest.py`` to surface them as <load> failures.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def test_strict_atoms_undeclared_atom_raises():
    """A file with ``-strict_atoms`` and a bare reference to an atom that is
    not declared, imported, or otherwise reached must fail to compile with
    a ``NameError`` naming the offending atom and the file."""
    # The auto-mint default for phase3strict_undeclared_red must NOT have
    # happened on a previous test run; assert that up front so the failure
    # is attributable to strict mode rather than a polluted dict.
    assert "phase3strict_undeclared_red" not in predicate_builtins
    source = (
        "-strict_atoms\n"
        "\n"
        "ColorStrictUndeclared(phase3strict_undeclared_red),\n"
    )
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_strict_atoms_undeclared_test", source)
    msg = str(exc_info.value)
    assert "strict_atoms" in msg
    assert "phase3strict_undeclared_red" in msg
    assert "_strict_atoms_undeclared_test" in msg
    # Diagnostic must point the author at the legitimate routes.
    assert "-module" in msg
    assert "-private" in msg
    assert "-import_from" in msg
    assert "global_atom" in msg
    # Strict mode must not have silently minted the undeclared atom.
    assert "phase3strict_undeclared_red" not in predicate_builtins


def test_strict_atoms_private_atom_compiles():
    """A file with ``-strict_atoms`` and a bare reference to an atom listed
    in ``-private([...])`` must compile successfully — the private listing
    satisfies strict mode and the resulting class is module-local."""
    mod = _load_fixture(
        "strict_atoms_private.clausal",
        "tests.fixtures.strict_atoms_private",
    )
    assert isinstance(mod.phase3strict_private_orange, PredicateMeta)
    # Private declaration installs a module-local class distinct from the
    # process-wide global dict.
    assert mod.phase3strict_private_orange is not predicate_builtins.get(
        "phase3strict_private_orange"
    )


def test_strict_atoms_module_decl_atom_compiles():
    """A file with ``-strict_atoms`` and a bare reference to an atom listed
    in ``-module(M, [...])`` must compile successfully."""
    mod = _load_fixture(
        "strict_atoms_module_decl.clausal",
        "tests.fixtures.strict_atoms_module_decl",
    )
    assert isinstance(mod.phase3strict_module_green, PredicateMeta)


def test_strict_atoms_imported_atom_compiles():
    """A file with ``-strict_atoms`` and a bare reference to an atom brought
    in via ``-import_from`` must compile successfully — the import binds
    the name in module_dict before the strict-mode check runs."""
    mod_owner = _load_fixture(
        "strict_atoms_import_owner.clausal",
        "tests.fixtures.strict_atoms_import_owner",
    )
    mod_importer = _load_fixture(
        "strict_atoms_import.clausal",
        "tests.fixtures.strict_atoms_import",
    )
    assert isinstance(mod_owner.phase3strict_import_yellow, PredicateMeta)
    # The importer's bare reference resolves to the same class as the
    # owner's declaration.
    assert (
        mod_importer.phase3strict_import_yellow
        is mod_owner.phase3strict_import_yellow
    )


def test_strict_atoms_global_atom_builtin_compiles():
    """A file with ``-strict_atoms`` that reaches a name via
    ``global_atom("name", X)`` must compile — the directive restricts bare
    atom references, not the reflection escape hatch.  The string literal
    in ``global_atom("phase3strict_global_red", _atom)`` is not a bare
    Name node, so strict mode never flags it."""
    mod = _load_fixture(
        "strict_atoms_global_atom.clausal",
        "tests.fixtures.strict_atoms_global_atom",
    )
    # Predicate compiled; LookupStrictGlobal must be a PredicateMeta.
    assert isinstance(mod.LookupStrictGlobal, PredicateMeta)


def test_strict_atoms_empty_file_compiles():
    """Edge case: a file with ``-strict_atoms`` and no clauses that bare-
    reference any atom must compile fine — strict mode has nothing to
    reject."""
    mod = _load_fixture(
        "strict_atoms_empty.clausal",
        "tests.fixtures.strict_atoms_empty",
    )
    assert isinstance(mod.Ok, PredicateMeta)


def test_strict_atoms_multiple_undeclared_reported_together():
    """When several undeclared atoms appear in a strict file, the diagnostic
    must enumerate them all in one message rather than failing at the
    first.  This makes the error easier to act on for the author."""
    # Names unique to this test to keep the global dict clean.
    for name in ("phase3strict_multi_alpha", "phase3strict_multi_beta"):
        assert name not in predicate_builtins
    source = (
        "-strict_atoms\n"
        "\n"
        "ColorMultiAlpha(phase3strict_multi_alpha),\n"
        "ColorMultiBeta(phase3strict_multi_beta),\n"
    )
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_strict_atoms_multi_test", source)
    msg = str(exc_info.value)
    assert "phase3strict_multi_alpha" in msg
    assert "phase3strict_multi_beta" in msg
    # Neither name should have been minted as a side effect.
    for name in ("phase3strict_multi_alpha", "phase3strict_multi_beta"):
        assert name not in predicate_builtins
