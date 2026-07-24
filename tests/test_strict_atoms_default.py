"""Tests for strict-atoms-by-default (staged binary flip).

See docs/superpowers/specs/2026-07-24-strict-atoms-default-design.md.
Atom names are prefixed ``sad_`` (strict-atoms-default) and unique per
test so the process-wide predicate_builtins dict is not cross-polluted.
"""
from __future__ import annotations

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module, predicate_builtins
from clausal.logic.predicate import PredicateMeta


def _load_inline_clausal(name: str, source: str):
    """Write `source` to a temp .clausal file and load it (avoids the
    conftest .clausal collector that would surface persistent fixtures)."""
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


def test_implicit_atoms_mints_undeclared_bare_atom():
    """`-implicit_atoms` opts into loose auto-mint: an undeclared bare
    atom is minted into the global dict (today's default behavior)."""
    assert "sad_implicit_red" not in predicate_builtins
    source = (
        "-implicit_atoms\n"
        "\n"
        "ColorImplicit(sad_implicit_red),\n"
    )
    mod = _load_inline_clausal("_sad_implicit_mints", source)
    assert isinstance(predicate_builtins["sad_implicit_red"], PredicateMeta)
    assert mod.sad_implicit_red is predicate_builtins["sad_implicit_red"]


def test_implicit_atoms_parenthesised_form():
    """`-implicit_atoms()` is accepted, same as the bare form."""
    source = (
        "-implicit_atoms()\n"
        "\n"
        "ColorImplicitParen(sad_implicit_paren_blue),\n"
    )
    mod = _load_inline_clausal("_sad_implicit_paren", source)
    assert isinstance(mod.sad_implicit_paren_blue, PredicateMeta)


def test_implicit_atoms_rejects_arguments():
    """`-implicit_atoms(foo)` is a SyntaxError — the marker takes no args."""
    source = "-implicit_atoms(foo)\n\nX(y),\n"
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_sad_implicit_args", source)
    assert "-implicit_atoms takes no arguments" in str(exc_info.value)


def test_strict_and_implicit_mutually_exclusive():
    """A file carrying both directives is a SyntaxError."""
    source = (
        "-strict_atoms\n"
        "-implicit_atoms\n"
        "\n"
        "X(sad_both_atom),\n"
    )
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_sad_both", source)
    msg = str(exc_info.value)
    assert "mutually exclusive" in msg


import ast

from clausal.templating.term_rewriting import EmbedTransformer
from clausal.pythonic_ast.nodes import ImplicitAtomsDeclaration


def test_repl_transformer_injects_implicit_atoms():
    """A transformer in REPL mode seeds an ImplicitAtomsDeclaration so
    interactive cells auto-mint even under the strict file default."""
    tree = ast.parse("Color(sad_repl_undeclared),\n")
    t = EmbedTransformer(implicit_atoms_default=True)
    t.visit(tree)
    assert any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )


def test_file_transformer_does_not_inject_implicit_atoms():
    """The default (file) transformer does NOT seed implicit mode."""
    tree = ast.parse("Color(sad_file_undeclared),\n")
    t = EmbedTransformer()
    t.visit(tree)
    assert not any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )


def test_repl_transformer_respects_explicit_strict():
    """REPL mode must not override an explicit -strict_atoms in the cell."""
    tree = ast.parse("-strict_atoms\nColor(sad_repl_strict),\n")
    t = EmbedTransformer(implicit_atoms_default=True)
    t.visit(tree)
    assert not any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )
