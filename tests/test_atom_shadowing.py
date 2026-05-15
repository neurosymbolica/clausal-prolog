"""Tests for Phase 4 of GLOBAL_ATOMS_DEFAULT.md — shadowing warning + ``-overwrites``.

Covers:

* ``ClausalAtomShadowingWarning`` — fires when ``-import_from(M, [red])`` and
  the same module locally declares ``red`` in ``-module`` or ``-private``.
  Two distinct ``PredicateMeta`` classes result, which is almost certainly
  unintentional.
* ``ClausalUnusedOverwritesWarning`` — fires when an ``-overwrites([foo])``
  entry does not actually shadow an imported name.
* ``OverwritesDeclaration`` AST node parsing via ``-overwrites([...])``.
* The **narrowed trigger** (atoms only): the warning fires for atom-name
  shadowing but **not** for predicate-functor shadowing, because Phase 2
  changes only the *atom* default to global and predicate functors were
  always module-local.
* Alias-form import: ``-import_from(M, [alias(Bar, red)])`` binds ``red``
  locally and therefore still triggers the warning when ``red`` is also
  declared locally.

Atom names used here are ``phase4_*`` to avoid pollution of the
process-wide ``predicate_builtins`` dict.

See ``implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md`` §"Phase
4: shadowing warning + ``-overwrites``" for the spec.
"""

from __future__ import annotations

import ast
import warnings

import pytest

from clausal.import_hook import EmbedTransformer
from clausal.logic.compiler_v2 import (
    ClausalAtomShadowingWarning,
    ClausalUnusedOverwritesWarning,
    _process_declarations,
)
from clausal.pythonic_ast.nodes import OverwritesDeclaration


# ── Helpers ────────────────────────────────────────────────────────────────


def _run_declarations(source: str, mod_name: str = "_phase4_test_mod"):
    """Parse ``source``, build ``module_items``, run ``_process_declarations`` alone.

    Avoids triggering Python's ``ImportFrom`` (which would require the
    foreign module to actually exist).  The shadowing check only needs
    the ``module_items`` list, so we exercise the detection in isolation.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        tree = ast.parse(source)
        t = EmbedTransformer()
        t.visit(tree)
    module_dict = {"__name__": mod_name, "__file__": f"<{mod_name}>"}
    _process_declarations(t._module_items, module_dict)
    return module_dict, t._module_items


# ── OverwritesDeclaration AST node parsing ─────────────────────────────────


class TestOverwritesDirectiveParsing:
    """The ``-overwrites([...])`` directive parses to ``OverwritesDeclaration``."""

    def test_overwrites_directive_produces_item(self):
        source = "-overwrites([phase4_foo, phase4_bar])\n"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(source)
            t = EmbedTransformer()
            t.visit(tree)
        decls = [
            i for i in t._module_items
            if isinstance(i, OverwritesDeclaration)
        ]
        assert len(decls) == 1
        assert decls[0].items == ["phase4_foo", "phase4_bar"]

    def test_overwrites_empty_list_is_legal(self):
        source = "-overwrites([])\n"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(source)
            t = EmbedTransformer()
            t.visit(tree)
        decls = [
            i for i in t._module_items
            if isinstance(i, OverwritesDeclaration)
        ]
        assert len(decls) == 1
        assert decls[0].items == []

    def test_overwrites_non_name_element_raises(self):
        source = '-overwrites(["string_literal"])\n'
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(source)
            with pytest.raises(SyntaxError) as exc_info:
                t = EmbedTransformer()
                t.visit(tree)
        assert "overwrites" in str(exc_info.value)


# ── Shadowing detection ────────────────────────────────────────────────────


class TestAtomShadowingWarning:
    """``ClausalAtomShadowingWarning`` fires when a local atom shadows an import."""

    def test_atom_in_private_shadows_imported(self):
        """``-import_from(M, [red])`` + ``-private([red])`` → warning fires."""
        source = (
            "-import_from(other.mod, [phase4_red])\n"
            "-private([phase4_red])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_priv_shadow")
        shadow_warnings = [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]
        assert len(shadow_warnings) == 1, (
            f"expected exactly 1 ClausalAtomShadowingWarning, "
            f"got {[(w.category.__name__, str(w.message)) for w in caught]}"
        )
        msg = str(shadow_warnings[0].message)
        assert "phase4_red" in msg
        assert "other.mod" in msg

    def test_atom_in_module_decl_shadows_imported(self):
        """``-import_from(M, [red])`` + ``-module(N, [red])`` → warning fires."""
        source = (
            "-import_from(other.mod, [phase4_blue])\n"
            "-module(mymod, [phase4_blue])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_mod_shadow")
        shadow_warnings = [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]
        assert len(shadow_warnings) == 1
        msg = str(shadow_warnings[0].message)
        assert "phase4_blue" in msg
        assert "other.mod" in msg

    def test_no_warning_when_only_imported(self):
        source = "-import_from(other.mod, [phase4_only_imported])\n"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_only_imported")
        assert not [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]

    def test_no_warning_when_only_declared(self):
        source = "-private([phase4_only_declared])\n"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_only_declared")
        assert not [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]

    def test_alias_import_still_triggers_warning(self):
        """``-import_from(M, [alias(Bar, red)])`` + ``-private([red])`` →
        warning fires.  The local binding from the alias is ``red``, which
        is the same name the local declaration introduces."""
        source = (
            "-import_from(other.mod, [alias(phase4_orig_bar, phase4_aliased)])\n"
            "-private([phase4_aliased])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_alias_shadow")
        shadow_warnings = [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]
        assert len(shadow_warnings) == 1
        msg = str(shadow_warnings[0].message)
        assert "phase4_aliased" in msg
        # The source module is reported, not the original imported name.
        assert "other.mod" in msg

    def test_overwrites_suppresses_warning(self):
        """``-import_from(M, [red])`` + ``-private([red])`` +
        ``-overwrites([red])`` → no warning."""
        source = (
            "-import_from(other.mod, [phase4_green])\n"
            "-private([phase4_green])\n"
            "-overwrites([phase4_green])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_overwrites_suppress")
        # Neither warning should fire — shadowing is suppressed, and the
        # -overwrites entry actually corresponds to an import.
        assert not [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]
        assert not [
            w for w in caught
            if issubclass(w.category, ClausalUnusedOverwritesWarning)
        ]


class TestPredicateFunctorNotWarned:
    """The **narrowed** trigger excludes predicate-functor shadowing.

    Predicates with arity ≥ 1 stay module-local-by-default — they do not
    participate in the global-atom default introduced by Phase 2.  Shadowing
    a *predicate* name with an import is therefore the existing per-module
    convention, not the new atom-identity confusion the warning is meant to
    catch.  See GLOBAL_ATOMS_DEFAULT.md §"Predicates with arity"."""

    def test_predicate_functor_in_private_does_not_warn(self):
        """``-import_from(M, [Foo])`` + ``-private([Foo(X)])`` → no warning,
        because ``Foo`` here is a predicate functor with arity 1, not an atom."""
        source = (
            "-import_from(other.mod, [phase4_Foo])\n"
            "-private([phase4_Foo(X)])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_pred_no_warn")
        assert not [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]

    def test_predicate_functor_in_module_decl_does_not_warn(self):
        """``-import_from(M, [Foo])`` + ``-module(N, [Foo(X, Y)])`` → no warning."""
        source = (
            "-import_from(other.mod, [phase4_Bar])\n"
            "-module(mymod, [phase4_Bar(X, Y)])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_pred_mod_no_warn")
        assert not [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]


# ── Unused -overwrites detection ───────────────────────────────────────────


class TestUnusedOverwritesWarning:
    """``ClausalUnusedOverwritesWarning`` fires when an ``-overwrites`` entry
    does not correspond to an actual shadowing of an imported atom."""

    def test_overwrites_with_no_shadow_warns(self):
        """``-overwrites([foo])`` listed but ``foo`` is not imported anywhere
        → warning fires."""
        source = "-overwrites([phase4_unused_purple])\n"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_unused_overwrites")
        unused_warnings = [
            w for w in caught
            if issubclass(w.category, ClausalUnusedOverwritesWarning)
        ]
        assert len(unused_warnings) == 1
        msg = str(unused_warnings[0].message)
        assert "phase4_unused_purple" in msg

    def test_overwrites_with_import_but_no_local_decl_warns(self):
        """``-import_from(M, [foo])`` + ``-overwrites([foo])`` but no
        ``-private([foo])`` / ``-module(M, [foo])`` → unused warning fires
        (the entry suppresses a shadowing that never happened)."""
        source = (
            "-import_from(other.mod, [phase4_only_import])\n"
            "-overwrites([phase4_only_import])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_ow_no_local")
        unused_warnings = [
            w for w in caught
            if issubclass(w.category, ClausalUnusedOverwritesWarning)
        ]
        assert len(unused_warnings) == 1
        msg = str(unused_warnings[0].message)
        assert "phase4_only_import" in msg

    def test_overwrites_listing_predicate_functor_warns_unused(self):
        """A ``-overwrites([Foo])`` entry that names a predicate functor (not
        an atom) counts as unused under the narrowed interpretation: the
        warning never would have fired for a predicate functor in the first
        place, so the entry is suppressing nothing."""
        source = (
            "-import_from(other.mod, [phase4_Pred])\n"
            "-private([phase4_Pred(X)])\n"
            "-overwrites([phase4_Pred])\n"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _run_declarations(source, "_phase4_ow_pred_unused")
        # No shadowing warning (predicate-functor case is excluded).
        assert not [
            w for w in caught
            if issubclass(w.category, ClausalAtomShadowingWarning)
        ]
        # Unused-overwrites warning fires because phase4_Pred was never a
        # shadowed atom.
        unused_warnings = [
            w for w in caught
            if issubclass(w.category, ClausalUnusedOverwritesWarning)
        ]
        assert len(unused_warnings) == 1
        assert "phase4_Pred" in str(unused_warnings[0].message)
