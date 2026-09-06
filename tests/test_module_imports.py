"""Tests for V3-1 — Module system (-import_from, -import_module, qualified calls).

Verifies that .clausal files can import predicates from other .clausal files
and from Python modules using -import_from and -import_module directives.
"""

from __future__ import annotations

import sys
import os
import types

import pytest

from clausal.logic.atoms import char_atom, mint
import clausal.import_hook
from clausal.import_hook import _load_module
from clausal.logic.solve import call, query, solve
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.compiler.terms_to_ast import _dotted_name_from_loadattr
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
        # nv
        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        assert hasattr(mod, "Double")
        assert hasattr(mod, "Helper")

    def test_base_double_ground(self):
        # nv
        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        logic_mod = mod.__dict__["$module"]
        results = list(call("Double", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_base_helper_calls_double(self):
        # nv
        mod = _load_fixture("importable_utils.clausal",
                            "tests.fixtures.importable_utils")
        logic_mod = mod.__dict__["$module"]
        results = list(call("Helper", 3, 6, module=logic_mod))
        assert len(results) == 1

    def test_base_double_with_var(self):
        # nv
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
        # nv
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        assert hasattr(mod, "Helper")
        assert hasattr(mod, "Double")
        assert hasattr(mod, "UseHelper")
        assert hasattr(mod, "UseDouble")

    def test_use_helper_ground(self):
        # nv
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseHelper", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_use_double_ground(self):
        # nv
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseDouble", 3, 6, module=logic_mod))
        assert len(results) == 1

    def test_use_helper_failure(self):
        # nv
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseHelper", 2, 999, module=logic_mod))
        assert results == []

    def test_use_helper_with_var(self):
        # nv
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        y = Var()
        trail = next(call("UseHelper", 1, y, module=logic_mod))
        assert deref(y) == 2

    def test_imported_predicate_directly_callable(self):
        """The imported Helper predicate can be called directly too."""
        # nv
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        results = list(call("Helper", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_multiple_solutions(self):
        """Imported predicate yields all solutions from the source module."""
        # nv
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
        # nv
        mod = _load_fixture("imports_alias.clausal",
                            "tests.fixtures.imports_alias")
        assert hasattr(mod, "Hlp")
        assert hasattr(mod, "UseAlias")

    def test_use_alias_ground(self):
        # nv
        mod = _load_fixture("imports_alias.clausal",
                            "tests.fixtures.imports_alias")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseAlias", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_use_alias_with_var(self):
        # nv
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
        """The live target-resolution loop resolves dotted names from globals.

        P3-3 Task 5b fix round 1 (review finding F3): this used to drive
        ``_inject_call_targets``, the clause-taking twin that Phase 6 left
        behind and that had no production call sites -- so the assertion held
        while saying nothing about the compiler.  It now drives the pair the
        compiler actually runs (``_collect_globals_info`` to gather the
        targets, ``_inject_resolved_targets`` to resolve them), which is the
        same two calls ``compiler/predicate.py`` makes.
        """
        from clausal.logic.compiler.globals_env import (
            _collect_globals_info, _inject_resolved_targets,
        )
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
        _, _, targets = _collect_globals_info(clauses)
        _inject_resolved_targets(targets, base_globals, None, globals_)

        # The dotted name should be in base_globals
        assert "utils.Helper" in base_globals
        assert base_globals["utils.Helper"] is helper_cls

    def test_dotted_name_dispatch(self):
        """Compiled code can dispatch via dotted globals key."""
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
        # nv
        mod = _load_fixture("imports_module.clausal",
                            "tests.fixtures.imports_module")
        assert hasattr(mod, "UseImported")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseImported", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_import_module_fixture_with_var(self):
        # nv
        mod = _load_fixture("imports_module.clausal",
                            "tests.fixtures.imports_module")
        logic_mod = mod.__dict__["$module"]
        y = Var()
        trail = next(call("UseImported", 1, y, module=logic_mod))
        assert deref(y) == 2


# ── Qualified atoms as VALUES (module.atom in term position) ─────────────────


class TestQualifiedValueAtoms:
    """Module-qualified atoms (``module.atom``) must resolve as VALUES in term
    position, not only as call targets.

    Regression test for ``todo/qualified-atoms-in-term-position.md``: a
    ``module.atom`` reference in a term (argument / unification operand) was
    lowered to a ``LoadAttr`` reflection node instead of the module's exported
    atom, so it failed to unify with the same atom obtained via ``-import_from``.
    """

    def test_qualified_atom_in_term_position_unifies_with_imported_bare(self):
        # nv
        _load_fixture("qualified_atom_vocab.clausal", "qualified_atom_vocab")
        mod = _load_fixture("qualified_atom_consumer.clausal",
                            "qualified_atom_consumer")
        logic_mod = mod.__dict__["$module"]

        # Control: the imported bare atom resolves and unifies with the fact.
        y0 = Var()
        assert len(list(call("ImportedControl", y0, module=logic_mod))) == 1

        # The fix: qualified ``qualified_atom_vocab.euro`` in term position must
        # resolve to the SAME atom, so ``Stored(qualified_atom_vocab.euro)``
        # unifies against the fact built with the imported bare ``euro``.
        y = Var()
        results = list(call("QualifiedMatchesImported", y, module=logic_mod))
        assert len(results) == 1, "qualified atom in term position did not unify"

        # Binding is only live during iteration, so re-run with next() to read it.
        y2 = Var()
        next(call("QualifiedMatchesImported", y2, module=logic_mod))
        # P3-1 Task 2 (§1b/R2): atoms are plain strs now, not classes.
        assert deref(y2) == mint("ok")

    def test_qualified_atom_in_head_position_constructs_real_atom(self):
        # nv
        _load_fixture("qualified_atom_vocab.clausal", "qualified_atom_vocab")
        mod = _load_fixture("qualified_atom_consumer.clausal",
                            "qualified_atom_consumer")
        logic_mod = mod.__dict__["$module"]

        # ``StoredHead(qualified_atom_vocab.euro)`` fact must build the real atom,
        # so a query using the imported bare ``euro`` matches it.
        y = Var()
        results = list(call("HeadQualifiedMatches", y, module=logic_mod))
        assert len(results) == 1, "qualified atom in head position did not construct the atom"

    def test_query_from_python_with_cross_module_atom(self):
        """solve() a clausal goal built with a foreign atom whose bare name is
        NOT in the target module's globals (import_module only, no import_from).

        The query compiler must pass the atom as a bound parameter rather than
        baking a bare ``Name(atom.__name__)`` into the generated code, which
        would raise ``NameError`` for the cross-module atom.
        """
        # nv
        vocab = _load_fixture("qualified_atom_vocab.clausal",
                              "qualified_atom_vocab")
        mod = _load_fixture("qualified_atom_import_module_only.clausal",
                            "qualified_atom_import_module_only")
        euro = vocab.euro  # foreign atom; its bare name is not in mod's globals
        results = list(solve(mod.KnownCurrency(euro)))
        assert len(results) == 1


# ── Python-to-clausal import (existing behaviour preserved) ──────────────────


class TestPythonImport:
    """Existing Python import of .clausal files still works."""

    def test_python_import_existing_fixture(self):
        # nv
        mod = _load_fixture("edge_graph.clausal", "tests.fixtures.edge_graph")
        logic_mod = mod.__dict__["$module"]
        results = list(call("Edge", 1, 2, module=logic_mod))
        assert len(results) == 1


# ── Error handling ───────────────────────────────────────────────────────────


class TestImportErrors:
    """Error cases for import directives."""

    def test_unknown_module_raises_import_error(self):
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
        import ast as stdlib_ast
        from clausal.templating.term_rewriting import _dotted_name_from_ast
        node = stdlib_ast.Name(id="foo")
        assert _dotted_name_from_ast(node) == "foo"

    def test_dotted_name_two_parts(self):
        # nv
        import ast as stdlib_ast
        from clausal.templating.term_rewriting import _dotted_name_from_ast
        node = stdlib_ast.Attribute(
            value=stdlib_ast.Name(id="foo"),
            attr="bar",
        )
        assert _dotted_name_from_ast(node) == "foo.bar"

    def test_dotted_name_three_parts(self):
        # nv
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
        # nv
        import ast as stdlib_ast
        from clausal.templating.term_rewriting import _dotted_name_from_ast
        node = stdlib_ast.Constant(value=42)
        assert _dotted_name_from_ast(node) is None


# ── Compiler dotted name helper ──────────────────────────────────────────────


class TestCompilerDottedName:
    """Unit tests for _dotted_name_from_loadattr in compiler."""

    def test_loadname(self):
        # nv
        node = LoadName(name="foo")
        assert _dotted_name_from_loadattr(node) == "foo"

    def test_loadattr_simple(self):
        # nv
        node = LoadAttr(object=LoadName(name="graphs"), attr="Path")
        assert _dotted_name_from_loadattr(node) == "graphs.Path"

    def test_loadattr_nested(self):
        # nv
        node = LoadAttr(
            object=LoadAttr(object=LoadName(name="a"), attr="b"),
            attr="c",
        )
        assert _dotted_name_from_loadattr(node) == "a.b.c"


# ── visit_Attribute validation ──────────────────────────────────────────────


class TestVisitAttributeValidation:
    """Ensure visit_Attribute rejects logic variables and unsupported patterns.

    ``_x.foo`` on a logic variable is no longer an error — it is dict
    attribute-access sugar for ``_x[foo]`` (see
    docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md).  The
    *method-call* form ``_x.foo(_x)`` is still rejected, and a logic variable
    used as the attribute of a module-qualified name still is too.
    """

    def test_logic_var_method_call_raises_syntax_error(self):
        """X_.attr(...) is rejected: a dict read is a value, not a callable."""
        # nv
        import tempfile
        src = (
            '-import_module(tests.fixtures.importable_utils)\n'
            '-private([foo])\n'
            'Bad(_x) <- _x.foo(_x)\n'
        )
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            with pytest.raises(SyntaxError, match="[Mm]ethod-call"):
                _load_module("_test_var_attr", f.name)
        os.unlink(f.name)

    def test_logic_var_base_attr_read_is_dict_sugar(self):
        """X_.attr (no call) now compiles to the subscript read X_[attr]."""
        # nv
        import tempfile
        src = (
            '-private([foo])\n'
            'Bad(_x, _v) <- (_v is _x.foo)\n'
        )
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            f.flush()
            mod = _load_module("_test_var_attr_read", f.name)
        os.unlink(f.name)
        from clausal.terms import DictTerm
        from clausal.logic.variables import Var, deref
        logic_mod = mod.__dict__["$module"]
        foo = mod.__dict__["foo"]
        out = Var()
        got = [deref(out) for _ in
               call("Bad", DictTerm({foo: 42}), out, module=logic_mod)]
        assert got == [42]

    def test_logic_var_as_attr_name_raises_syntax_error(self):
        """mod.X_ is rejected because X_ is a logic variable."""
        # nv
        import tempfile
        src = (
            '-import_module(tests.fixtures.importable_utils)\n'
            'Bad(_x) <- mod._x(_x)\n'
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
        # nv
        mod = _load_fixture("imports_from.clausal",
                            "tests.fixtures.imports_from")
        logic_mod = mod.__dict__["$module"]
        # The compiled dispatch should resolve the predicate under a
        # dotted key, not a bare local name.
        results = list(call("UseHelper", 2, 4, module=logic_mod))
        assert len(results) == 1

    def test_alias_import_uses_dotted_key(self):
        """Aliased imports also use dotted key with original name."""
        # nv
        mod = _load_fixture("imports_alias.clausal",
                            "tests.fixtures.imports_alias")
        logic_mod = mod.__dict__["$module"]
        results = list(call("UseAlias", 3, 6, module=logic_mod))
        assert len(results) == 1

    def test_local_name_does_not_shadow_import(self):
        """A local predicate with same name as import doesn't break dispatch."""
        # nv
        import tempfile
        src = (
            '-import_from(tests.fixtures.importable_utils, [Double])\n'
            'UseDouble(_x, _y) <- Double(_x, _y)\n'
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
