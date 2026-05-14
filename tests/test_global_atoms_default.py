"""Tests for Phase 2 of GLOBAL_ATOMS_DEFAULT — bare-atom auto-mint hook.

Verifies that undeclared bare atom references in .clausal files auto-mint
into the process-wide ``predicate_builtins`` dict so that two modules each
referencing the same bare atom share its PredicateMeta class identity.

The four cases cover the precedence layering of resolution rule 1
(private > module-decl > import > global fallthrough), per the spec at
``implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md``.

Atom names used here are deliberately unique to this test file (``phase2*``
prefix) so that cross-test pollution of the process-wide global dict does
not perturb assertions.
"""

from __future__ import annotations

import os

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
