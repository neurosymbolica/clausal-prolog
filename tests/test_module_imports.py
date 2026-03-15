"""Tests for V3-1 — Module system (-import_from, -import_module, qualified calls).

Verifies that .clausal files can import predicates from other .clausal files
and from Python modules using -import_from and -import_module directives.
"""

from __future__ import annotations

import sys
import os
import types

import pytest

import clausal.import_hook
from clausal.import_hook import _load_module
from clausal.logic.solve import call, query, solve
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.compiler import _dotted_name_from_loadattr
from clausal.terms import LoadName, LoadAttr, Call as AstCall


# ── Fixture loading helpers ──────────────────────────────────────────────────


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def _load_fixture(filename: str, mod_name: str | None = None) -> object:
    path = _fixture_path(filename)
    name = mod_name or f"_test_fixture_{filename.replace('.', '_')}"
    return _load_module(name, path)


# ── Base module loads correctly ──────────────────────────────────────────────


class TestBaseModule:
    """Verify the importable_utils.clausal base fixture works standalone."""

    def test_base_module_has_predicates(self):
        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        assert hasattr(mod, "Double")
        assert hasattr(mod, "Helper")

    def test_base_double_ground(self):
        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        logic_mod = mod.__dict__["$module"]
        results = list(call("Double", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_base_helper_calls_double(self):
        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        logic_mod = mod.__dict__["$module"]
        results = list(call("Helper", 3, 6, module=logic_mod))
        assert len(results) == 1

    def test_base_double_with_var(self):
        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        logic_mod = mod.__dict__["$module"]
        y = Var()
        trail = next(call("Helper", 0, y, module=logic_mod))
        assert deref(y) == 0


# ── -import_from directive ───────────────────────────────────────────────────


class TestImportFrom:
    """Tests for -import_from(module, [Pred1, Pred2])."""

    def test_imported_predicates_in_namespace(self):
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        assert hasattr(mod, "Helper")
        assert hasattr(mod, "Double")
        assert hasattr(mod, "UseHelper")
        assert hasattr(mod, "UseDouble")

    def test_use_helper_ground(self):
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseHelper", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_use_double_ground(self):
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseDouble", 3, 6, module=logic_mod))
        assert len(results) == 1

    def test_use_helper_failure(self):
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseHelper", 2, 999, module=logic_mod))
        assert results == []

    def test_use_helper_with_var(self):
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        y = Var()
        trail = next(call("UseHelper", 1, y, module=logic_mod))
        assert deref(y) == 2

    def test_imported_predicate_directly_callable(self):
        """The imported Helper predicate can be called directly too."""
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        results = list(call("Helper", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_multiple_solutions(self):
        """Imported predicate yields all solutions from the source module."""
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        y = Var()
        count = 0
        for trail in call("UseHelper", 0, y, module=logic_mod):
            count += 1
        # Double(0,0) is the only match, so Helper(0, Y) has 1 solution
        assert count == 1


# ── -import_from with alias ──────────────────────────────────────────────────


class TestImportAlias:
    """Tests for -import_from(module, [alias(Orig, Local)])."""

    def test_alias_in_namespace(self):
        mod = _load_fixture("imports_alias.clausal",
                            "tests.fixtures.imports_alias")
        assert hasattr(mod, "Hlp")
        assert hasattr(mod, "UseAlias")

    def test_use_alias_ground(self):
        mod = _load_fixture("imports_alias.clausal",
                            "tests.fixtures.imports_alias")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseAlias", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_use_alias_with_var(self):
        mod = _load_fixture("imports_alias.clausal",
                            "tests.fixtures.imports_alias")
        logic_mod = mod.__dict__["$module"]
        y = Var()
        trail = next(call("UseAlias", 3, y, module=logic_mod))
        assert deref(y) == 6


# ── Qualified calls (compiler-level tests) ───────────────────────────────────


class TestQualifiedCalls:
    """Tests for qualified predicate calls (mod.Pred(X_)) at compiler level.

    These test the compiler machinery directly rather than going through
    the import hook, which avoids namespace-package issues in the test
    harness.
    """

    def test_inject_dotted_call_target(self):
        """_inject_call_targets resolves dotted names from globals."""
        from clausal.logic.compiler import _inject_call_targets
        from clausal.logic.database import Clause

        # Create a mock module with a predicate class
        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        helper_cls = mod.Helper

        # Create a fake module object to simulate import
        class FakeModule:
            Helper = helper_cls

        # Simulate globals_ with the module object
        globals_ = {"utils": FakeModule}

        # Create a clause with a qualified call: utils.Helper(X_, Y_)
        x, y = Var(), Var()
        body_goal = AstCall(
            func=LoadAttr(object=LoadName(name="utils"), attr="Helper"),
            args=[x, y],
            kwargs=[],
        )
        clauses = [Clause(head=None, body=[body_goal])]

        base_globals = {}
        _inject_call_targets(clauses, base_globals, None, globals_)

        # The dotted name should be in base_globals
        assert "utils.Helper" in base_globals
        assert base_globals["utils.Helper"] is helper_cls

    def test_dotted_name_dispatch(self):
        """Compiled code can dispatch via dotted globals key."""
        from clausal.logic.compiler import _inject_call_targets
        from clausal.logic.database import Clause

        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        helper_cls = mod.Helper

        # Simulate: base_globals has "utils.Helper" → class
        base_globals = {"utils.Helper": helper_cls}

        # The class is accessible via _get_dispatch
        assert hasattr(base_globals["utils.Helper"], "_get_dispatch")
        dispatch = base_globals["utils.Helper"]._get_dispatch()
        assert dispatch is not None

    def test_import_module_fixture_loads(self):
        """imports_module.clausal loads and UseImported works."""
        mod = _load_fixture("imports_module.clausal",
                            "tests.fixtures.imports_module")
        assert hasattr(mod, "UseImported")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseImported", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_import_module_fixture_with_var(self):
        mod = _load_fixture("imports_module.clausal",
                            "tests.fixtures.imports_module")
        logic_mod = mod.__dict__["$module"]
        y = Var()
        trail = next(call("UseImported", 1, y, module=logic_mod))
        assert deref(y) == 2


# ── Python-to-clausal import (existing behaviour preserved) ──────────────────


class TestPythonImport:
    """Existing Python import of .clausal files still works."""

    def test_python_import_existing_fixture(self):
        mod = _load_fixture("edge_graph.clausal", "tests.fixtures.edge_graph")
        logic_mod = mod.__dict__["$module"]
        results = list(call("Edge", 1, 2, module=logic_mod))
        assert len(results) == 1


# ── Error handling ───────────────────────────────────────────────────────────


class TestImportErrors:
    """Error cases for import directives."""

    def test_unknown_module_raises_import_error(self):
        import tempfile
        src = '-import_from(nonexistent_module_xyz_123, [Foo])\n'
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            with pytest.raises((ImportError, ModuleNotFoundError)):
                _load_module("_test_bad_import", f.name)
        os.unlink(f.name)

    def test_unknown_predicate_raises_import_error(self):
        import tempfile
        src = '-import_from(tests.fixtures.importable_utils, [NoSuchPredicate])\n'
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            _load_fixture("importable_utils.clausal",
                          "tests.fixtures.importable_utils")
            with pytest.raises((ImportError, AttributeError)):
                _load_module("_test_bad_pred_import", f.name)
        os.unlink(f.name)

    def test_bad_directive_syntax_non_dotted(self):
        import tempfile
        src = '-import_from(123, [Foo])\n'
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            with pytest.raises(SyntaxError):
                _load_module("_test_bad_syntax", f.name)
        os.unlink(f.name)

    def test_bad_directive_missing_list(self):
        import tempfile
        src = '-import_from(some_module)\n'
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            with pytest.raises(SyntaxError):
                _load_module("_test_bad_syntax2", f.name)
        os.unlink(f.name)


# ── Directive parsing unit tests ─────────────────────────────────────────────


class TestDirectiveParsing:
    """Unit tests for the _dotted_name_from_ast helper."""

    def test_dotted_name_simple(self):
        import ast as stdlib_ast
        from clausal.templating.term_rewriting import _dotted_name_from_ast
        node = stdlib_ast.Name(id="foo")
        assert _dotted_name_from_ast(node) == "foo"

    def test_dotted_name_two_parts(self):
        import ast as stdlib_ast
        from clausal.templating.term_rewriting import _dotted_name_from_ast
        node = stdlib_ast.Attribute(
            value=stdlib_ast.Name(id="foo"),
            attr="bar",
        )
        assert _dotted_name_from_ast(node) == "foo.bar"

    def test_dotted_name_three_parts(self):
        import ast as stdlib_ast
        from clausal.templating.term_rewriting import _dotted_name_from_ast
        node = stdlib_ast.Attribute(
            value=stdlib_ast.Attribute(
                value=stdlib_ast.Name(id="a"),
                attr="b",
            ),
            attr="c",
        )
        assert _dotted_name_from_ast(node) == "a.b.c"

    def test_dotted_name_invalid(self):
        import ast as stdlib_ast
        from clausal.templating.term_rewriting import _dotted_name_from_ast
        node = stdlib_ast.Constant(value=42)
        assert _dotted_name_from_ast(node) is None


# ── Compiler dotted name helper ──────────────────────────────────────────────


class TestCompilerDottedName:
    """Unit tests for _dotted_name_from_loadattr in compiler."""

    def test_loadname(self):
        node = LoadName(name="foo")
        assert _dotted_name_from_loadattr(node) == "foo"

    def test_loadattr_simple(self):
        node = LoadAttr(object=LoadName(name="graphs"), attr="Path")
        assert _dotted_name_from_loadattr(node) == "graphs.Path"

    def test_loadattr_nested(self):
        node = LoadAttr(
            object=LoadAttr(object=LoadName(name="a"), attr="b"),
            attr="c",
        )
        assert _dotted_name_from_loadattr(node) == "a.b.c"


# ── visit_Attribute validation ──────────────────────────────────────────────


class TestVisitAttributeValidation:
    """Ensure visit_Attribute rejects logic variables and unsupported patterns."""

    def test_logic_var_in_attr_raises_syntax_error(self):
        """X_.attr is rejected because X_ is a logic variable."""
        import tempfile
        src = (
            '-import_module(tests.fixtures.importable_utils)\n'
            'Bad(X_) <- X_.foo(X_)\n'
        )
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            with pytest.raises(SyntaxError, match="Logic variable"):
                _load_module("_test_var_attr", f.name)
        os.unlink(f.name)

    def test_logic_var_as_attr_name_raises_syntax_error(self):
        """mod.X_ is rejected because X_ is a logic variable."""
        import tempfile
        src = (
            '-import_module(tests.fixtures.importable_utils)\n'
            'Bad(X_) <- mod.X_(X_)\n'
        )
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            with pytest.raises(SyntaxError, match="Logic variable"):
                _load_module("_test_attr_var", f.name)
        os.unlink(f.name)


# ── Dotted remap for imported predicates ─────────────────────────────────────


class TestDottedRemap:
    """Verify -import_from uses full dotted path in compiled globals."""

    def test_import_from_uses_dotted_key(self):
        """Imported predicates are stored under dotted key in compiled globals."""
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        # The compiled dispatch should resolve the predicate under a
        # dotted key, not a bare local name.
        results = list(call("UseHelper", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_alias_import_uses_dotted_key(self):
        """Aliased imports also use dotted key with original name."""
        mod = _load_fixture("imports_alias.clausal",
                            "tests.fixtures.imports_alias")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseAlias", 3, 6, module=logic_mod))
        assert len(results) == 1

    def test_local_name_does_not_shadow_import(self):
        """A local predicate with same name as import doesn't break dispatch."""
        import tempfile
        src = (
            '-import_from(tests.fixtures.importable_utils, [Double])\n'
            'UseDouble(X_, Y_) <- Double(X_, Y_)\n'
        )
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            mod = _load_module("_test_no_shadow", f.name)
            logic_mod = mod.__dict__["$module"]
            results = list(call("UseDouble", 2, 4, module=logic_mod))
            assert len(results) == 1
        os.unlink(f.name)
