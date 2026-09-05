"""Tests for compiler_v2 — pipeline split (ModuleAST-driven compilation).

Verifies that the v2 pipeline (EmbedTransformer → module_items → compile_module)
produces equivalent results to the v1 pipeline for all .clausal fixtures.
"""

from __future__ import annotations

import ast
import os
import sys
import warnings

import pytest

from clausal.import_hook import (
    EmbedTransformer,
    PredicateLoader,
    _load_module,
    _fact_to_predicate_node,
    predicate_builtins,
    runtime_builtins,
)
from clausal.logic.compiler_v2 import compile_module
from clausal.logic.database import Module as LogicModule, head_key
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, Trail, deref


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_via_v2(path: str, mod_name: str):
    """Load a .clausal file through the v2 pipeline and return the module dict."""
    with open(path) as f:
        source = f.read()

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="'str' object is not callable",
            category=SyntaxWarning,
        )
        tree = ast.parse(source, filename=path)
        transformer = EmbedTransformer()
        tree = transformer.visit(tree)
        ast.fix_missing_locations(tree)

    module_items = transformer._module_items
    module_dict = {"__name__": mod_name, "__file__": path}
    # P3-2 Task 8: mirrors import_hook.py's exec_module seeding order --
    # the atom pool first, runtime_builtins (compilation-support namespace)
    # layered on top and winning any collision (see import_hook.py's
    # pool-split comment for why).
    module_dict.update(predicate_builtins)
    module_dict.update(runtime_builtins)

    # Collect Predicate nodes by executing bytecode.
    predicate_nodes = []
    from clausal.pythonic_ast.nodes import Predicate, BoolLiteral
    dummy_lm = LogicModule(mod_name, module_dict=module_dict)
    module_dict["$module"] = dummy_lm
    module_dict["$define_predicate"] = lambda pred, lm: predicate_nodes.append(pred)
    module_dict["$assert_fact"] = lambda term: predicate_nodes.append(
        _fact_to_predicate_node(term)
    )
    code = compile(tree, filename=path, mode="exec")
    exec(code, module_dict)

    logic_module = compile_module(
        predicate_nodes, module_items, module_dict, mod_name,
    )
    module_dict["$module"] = logic_module
    return module_dict


class TestModuleItemAccumulation:
    """Test that EmbedTransformer correctly accumulates _module_items."""

    def test_empty_module(self):
        """Empty source produces no module items."""
        # nv
        tree = ast.parse("")
        t = EmbedTransformer()
        t.visit(tree)
        assert t._module_items == []

    def test_directive_items(self):
        """Directives produce DirectiveItem entries."""
        # nv
        from clausal.pythonic_ast.nodes import Directive
        source = "-dynamic(color/2)\n-table(fib/2)\n"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(source)
            t = EmbedTransformer()
            t.visit(tree)
        directives = [i for i in t._module_items if isinstance(i, Directive)]
        assert len(directives) == 2
        assert directives[0].name == "dynamic"
        assert directives[0].specs == [("color", 2)]
        assert directives[1].name == "table"
        assert directives[1].specs == [("fib", 2)]

    def test_import_from_item(self):
        """import_from directives produce ImportFromItem entries."""
        # nv
        from clausal.pythonic_ast.nodes import ImportFromDirective
        source = "-import_from(some.module, [Foo, alias(Bar, Baz)])\n"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(source)
            t = EmbedTransformer()
            t.visit(tree)
        imports = [i for i in t._module_items if isinstance(i, ImportFromDirective)]
        assert len(imports) == 1
        assert imports[0].module == "some.module"
        assert imports[0].names == ["Foo", ("Bar", "Baz")]

    def test_import_module_item(self):
        """import_module directives produce ImportModuleItem entries."""
        # nv
        from clausal.pythonic_ast.nodes import ImportModuleDirective
        source = "-import_module(some.module)\n"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(source)
            t = EmbedTransformer()
            t.visit(tree)
        imports = [i for i in t._module_items if isinstance(i, ImportModuleDirective)]
        assert len(imports) == 1
        assert imports[0].module == "some.module"

    def test_module_declaration_item(self):
        """Module declarations produce ModuleDeclItem entries."""
        # nv
        from clausal.pythonic_ast.nodes import ModuleDeclaration
        source = "-module(mymod, [fib(N_, F_), hello])\n"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(source)
            t = EmbedTransformer()
            t.visit(tree)
        decls = [i for i in t._module_items if isinstance(i, ModuleDeclaration)]
        assert len(decls) == 1
        assert decls[0].module_name == "mymod"
        # Should have fib with field names and "hello" as atom
        assert any(isinstance(e, tuple) and e[0] == "fib" for e in decls[0].exports)
        assert "hello" in decls[0].exports


def _call_collect(functor, *args, module):
    """Call a predicate and collect deref'd results for last arg."""
    results = []
    for trail in call(functor, *args, module=module):
        results.append(deref(args[-1]))
    return results


class TestV2PipelineEquivalence:
    """Test that v2 pipeline produces same query results as v1."""

    def test_edge_graph(self):
        """Edge graph fixture: basic facts + rules."""
        # nv
        path = os.path.join(FIXTURES_DIR, "edge_graph.clausal")
        md = _load_via_v2(path, "_v2_edge_graph")
        lm = md["$module"]

        x = Var()
        vals = sorted(_call_collect("Edge", 1, x, module=lm))
        assert vals == [2, 3]

    def test_fibonacci(self):
        """Fibonacci fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "fibonacci.clausal")
        md = _load_via_v2(path, "_v2_fibonacci")
        lm = md["$module"]

        f = Var()
        results = _call_collect("Fib", 5, f, module=lm)
        assert len(results) >= 1
        assert results[0] == 5

    def test_dynamic_pred(self):
        """Dynamic predicate fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "dynamic_pred.clausal")
        md = _load_via_v2(path, "_v2_dynamic_pred")
        lm = md["$module"]
        assert lm.db.is_dynamic("Color", 2)

    def test_facts_only(self):
        """Facts-only fixture (edge_graph has facts + rules)."""
        # nv
        path = os.path.join(FIXTURES_DIR, "edge_graph.clausal")
        md = _load_via_v2(path, "_v2_edge_graph2")
        lm = md["$module"]
        a, b = Var(), Var()
        count = sum(1 for _ in call("Edge", a, b, module=lm))
        assert count == 3

    def test_tabled_fib(self):
        """Tabled fibonacci fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "tabled_fib.clausal")
        md = _load_via_v2(path, "_v2_tabled_fib")
        lm = md["$module"]
        assert lm.db.is_tabled("Fib", 2)

        f = Var()
        results = _call_collect("Fib", 10, f, module=lm)
        assert len(results) >= 1
        assert results[0] == 55

    def test_shallow_pred(self):
        """Shallow predicate fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "shallow_pred.clausal")
        md = _load_via_v2(path, "_v2_shallow_pred")
        lm = md["$module"]
        assert lm.db.is_shallow("Color", 2)

    def test_dcg_grammar(self):
        """DCG grammar fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "dcg_grammar.clausal")
        md = _load_via_v2(path, "_v2_dcg_grammar")
        lm = md["$module"]
        greeting_cls = md.get("greeting")
        assert greeting_cls is not None
        count = sum(1 for _ in call("greeting", ["hello", "world"], [], module=lm))
        assert count >= 1


class TestV2CompileModule:
    """Test compile_module() directly."""

    def test_empty_module(self):
        """Empty predicate list produces empty module."""
        # nv
        module_dict = {"__name__": "empty"}
        lm = compile_module([], [], module_dict, "empty")
        assert isinstance(lm, LogicModule)

    def test_predicate_locking(self):
        """Non-dynamic predicates are locked after compile_module."""
        # nv
        path = os.path.join(FIXTURES_DIR, "static_pred.clausal")
        md = _load_via_v2(path, "_v2_static_pred")
        # All PredicateMeta classes should be locked
        for obj in md.values():
            if isinstance(obj, PredicateMeta) and hasattr(obj, '_fields'):
                key = (obj.__name__, len(obj._fields))
                if not md["$module"].db.is_dynamic(*key):
                    assert obj._locked

    def test_dynamic_not_locked(self):
        """Dynamic predicates are NOT locked after compile_module."""
        # nv
        path = os.path.join(FIXTURES_DIR, "dynamic_pred.clausal")
        md = _load_via_v2(path, "_v2_dynamic_pred2")
        Color = md.get("Color")
        assert Color is not None and isinstance(Color, PredicateMeta)
        assert not Color._locked
