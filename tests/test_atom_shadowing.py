"""Atom shadowing is impossible after the P3-1 atom pivot (§1b/R2).

Pre-pivot, a module that both ``-import_from``'d an atom and locally
``-module``/``-private``-declared the same name got two distinct
``PredicateMeta`` classes, and unifying one against the other silently
failed — the "shadowing" this file used to test for, diagnosed by
``ClausalAtomShadowingWarning`` and acknowledged via an ``-overwrites([...])``
directive.

Under the pivot, atoms are global-by-spelling interned strs: a local
declaration and an import of the same name resolve to the identical str
object.  There is nothing left to shadow, so the whole detection apparatus
— ``ClausalAtomShadowingWarning``, ``ClausalUnusedOverwritesWarning``,
``_check_atom_shadowing``, and the ``-overwrites`` directive itself (its
only use was acknowledging atom shadowing; §1b Task 3 recon found no
predicate use) — is deleted rather than kept dark.  This file is inverted
to a compact suite pinning: the machinery is gone, the directive is gone,
and the "shadowing" scenario now just unifies.

See ``implementation_plans/phase3-decomposition-and-p31-atom-pivot.md``
Task 3.
"""

from __future__ import annotations

import ast
import warnings

import pytest

from clausal.import_hook import EmbedTransformer
from clausal.logic.compiler_v2 import _process_declarations


def _run_declarations(source: str, mod_name: str = "_atomshadow_test_mod"):
    """Parse ``source``, build ``module_items``, run ``_process_declarations`` alone.

    Avoids triggering Python's ``ImportFrom`` (which would require the
    foreign module to actually exist).
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        tree = ast.parse(source)
        t = EmbedTransformer()
        t.visit(tree)
    module_dict = {"__name__": mod_name, "__file__": f"<{mod_name}>"}
    _process_declarations(t._module_items, module_dict)
    return module_dict, t._module_items


class TestShadowingMachineryDeleted:
    """The identity/shadowing diagnostic classes and helper no longer exist."""

    def test_atom_shadowing_warning_class_is_gone(self):
        import clausal.logic.compiler_v2 as cv2
        assert not hasattr(cv2, "ClausalAtomShadowingWarning")

    def test_unused_overwrites_warning_class_is_gone(self):
        import clausal.logic.compiler_v2 as cv2
        assert not hasattr(cv2, "ClausalUnusedOverwritesWarning")

    def test_atom_identity_mismatch_warning_class_is_gone(self):
        import clausal.logic.compiler_v2 as cv2
        assert not hasattr(cv2, "ClausalAtomIdentityMismatchWarning")

    def test_check_atom_shadowing_helper_is_gone(self):
        import clausal.logic.compiler_v2 as cv2
        assert not hasattr(cv2, "_check_atom_shadowing")

    def test_overwrites_declaration_node_is_gone(self):
        import clausal.pythonic_ast.nodes as nodes
        assert not hasattr(nodes, "OverwritesDeclaration")


class TestOverwritesDirectiveRetired:
    """``-overwrites(...)`` is no longer a recognized directive."""

    def test_overwrites_directive_raises_unknown_directive(self):
        source = "-overwrites([atomshadow_foo, atomshadow_bar])\n"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(source)
            with pytest.raises(SyntaxError) as exc_info:
                t = EmbedTransformer()
                t.visit(tree)
        assert "Unknown directive" in str(exc_info.value)
        assert "overwrites" in str(exc_info.value)


class TestNoShadowingUnderGlobalAtoms:
    """A local declaration + an import of the same atom name is no longer
    distinguishable: both resolve to the identical global str, and no
    warning of any kind fires."""

    def test_atom_in_private_and_imported_share_identity_no_warning(self):
        """``-import_from(M, [red])`` + ``-private([red])`` used to warn and
        yield two distinct classes (§1b R2 inverts this): both bindings now
        collapse to the same interned str, with no warning."""
        source = (
            "-import_from(other.mod, [atomshadow_red])\n"
            "-private([atomshadow_red])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            module_dict, _ = _run_declarations(source, "_atomshadow_priv")
        assert not caught, [str(w.message) for w in caught]
        assert module_dict["atomshadow_red"] == "atomshadow_red"
        assert isinstance(module_dict["atomshadow_red"], str)

    def test_atom_in_module_decl_and_imported_share_identity_no_warning(self):
        source = (
            "-import_from(other.mod, [atomshadow_blue])\n"
            "-module(mymod, [atomshadow_blue])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            module_dict, _ = _run_declarations(source, "_atomshadow_mod")
        assert not caught, [str(w.message) for w in caught]
        assert module_dict["atomshadow_blue"] == "atomshadow_blue"

    def test_alias_import_and_local_decl_share_identity_no_warning(self):
        """``-import_from(M, [alias(Bar, red)])`` + ``-private([red])`` used
        to warn (the local binding from the alias is ``red``, colliding with
        the local declaration).  Now both simply name the same str."""
        source = (
            "-import_from(other.mod, [alias(atomshadow_orig_bar, "
            "atomshadow_aliased)])\n"
            "-private([atomshadow_aliased])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            module_dict, _ = _run_declarations(source, "_atomshadow_alias")
        assert not caught, [str(w.message) for w in caught]
        assert module_dict["atomshadow_aliased"] == "atomshadow_aliased"
