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

from clausal.logic.atoms import mint
from clausal.import_hook import (
    EmbedTransformer,
    PredicateLoader,
    _load_module,
    _fact_to_predicate_node,
    predicate_builtins,
    runtime_builtins,
)
from clausal.logic.compiler_v2 import compile_module, mark_import_placeholder
from clausal.logic.database import Module as LogicModule, head_key
from clausal.logic.predicate import (
    is_declared_predicate, resolve_predicate_row,
)
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
    # Marked as the import hook's exec-time PLACEHOLDER, exactly as
    # ``import_hook._run_v2_pipeline`` does: ``compile_module`` swaps the real
    # module in for it before step 0 (``_install_real_module``).  Unmarked,
    # the placeholder's empty store stays ``$module`` for the whole compile,
    # and once a predicate binding is a HANDLE (the W4b-2d flip) a handle to
    # this module resolves to nothing mid-compile.
    dummy_lm = mark_import_placeholder(
        LogicModule(mod_name, module_dict=module_dict))
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
        """edge graph fixture: basic facts + rules."""
        # nv
        path = os.path.join(FIXTURES_DIR, "edge_graph.clausal")
        md = _load_via_v2(path, "_v2_edge_graph")
        lm = md["$module"]

        x = Var()
        vals = sorted(_call_collect("edge", 1, x, module=lm))
        assert vals == [2, 3]

    def test_fibonacci(self):
        """Fibonacci fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "fibonacci.clausal")
        md = _load_via_v2(path, "_v2_fibonacci")
        lm = md["$module"]

        f = Var()
        results = _call_collect("fib", 5, f, module=lm)
        assert len(results) >= 1
        assert results[0] == 5

    def test_dynamic_pred(self):
        """Dynamic predicate fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "dynamic_pred.clausal")
        md = _load_via_v2(path, "_v2_dynamic_pred")
        lm = md["$module"]
        assert lm.db.is_dynamic("color", 2)

    def test_facts_only(self):
        """Facts-only fixture (edge_graph has facts + rules)."""
        # nv
        path = os.path.join(FIXTURES_DIR, "edge_graph.clausal")
        md = _load_via_v2(path, "_v2_edge_graph2")
        lm = md["$module"]
        a, b = Var(), Var()
        count = sum(1 for _ in call("edge", a, b, module=lm))
        assert count == 3

    def test_tabled_fib(self):
        """Tabled fibonacci fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "tabled_fib.clausal")
        md = _load_via_v2(path, "_v2_tabled_fib")
        lm = md["$module"]
        assert lm.db.is_tabled("fib", 2)

        f = Var()
        results = _call_collect("fib", 10, f, module=lm)
        assert len(results) >= 1
        assert results[0] == 55

    def test_shallow_pred(self):
        """Shallow predicate fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "shallow_pred.clausal")
        md = _load_via_v2(path, "_v2_shallow_pred")
        lm = md["$module"]
        assert lm.db.is_shallow("color", 2)

    def test_dcg_grammar(self):
        """DCG grammar fixture."""
        # nv
        path = os.path.join(FIXTURES_DIR, "dcg_grammar.clausal")
        md = _load_via_v2(path, "_v2_dcg_grammar")
        lm = md["$module"]
        greeting_cls = md.get("greeting")
        assert greeting_cls is not None
        count = sum(1 for _ in call("greeting", [mint("hello"), mint("world")], [], module=lm))
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
        """A non-dynamic predicate THIS Database holds is locked after
        compile_module -- and a class it holds no row for is left alone.

        This used to re-walk step 7's OWN condition and assert the walk had
        happened, so it passed on ``BoolEq/2`` -- a CLP(B) constraint TERM
        class, present in every module dict and a predicate of no Database.
        Locking one of those minted a DETACHED row as a side effect and wrote
        the lock into a private single-predicate Database nobody else can
        reach, so it had no enforcement effect: the refusal reads
        ``row.locked`` off the REAL row (``database.write_refusal``).  A test
        that mirrors the implementation cannot see that.
        """
        # nv
        path = os.path.join(FIXTURES_DIR, "static_pred.clausal")
        md = _load_via_v2(path, "_v2_static_pred")
        db = md["$module"].db

        # THE REQUIREMENT: held by this Database, not dynamic => locked.
        # The population is the module dict's predicate HANDLES (after the
        # W4b-2d flip a binding is a mangled atom, not a class), each read
        # at every arity this Database knows its name at -- deliberately NOT
        # step 7's own ``db.owned_keys()``, so the test does not mirror the
        # implementation.
        from clausal.logic.atoms import demangle, is_mangled
        population = 0
        checked = []
        for obj in list(md.values()):
            if not isinstance(obj, str) or not is_mangled(obj):
                continue
            _owner, name = demangle(obj)
            for arity in sorted(db.arities_for(name)):
                if not is_declared_predicate(obj, arity=arity, db=db):
                    continue
                row = resolve_predicate_row(obj, arity=arity, db=db)
                if row is None or row.db is not db:
                    continue
                population += 1
                if not db.is_dynamic(name, arity):
                    assert row.locked, (name, arity)
                    checked.append((name, arity))
        print(f"locking population: {population} handle rows, "
              f"{len(checked)} static checked: {checked}")
        assert population, "the selector found no predicate handle at all"
        assert checked, "fixture exercised no non-dynamic predicate at all"
        assert ("fact", 2) in checked, checked


    def test_dynamic_not_locked(self):
        """Dynamic predicates are NOT locked after compile_module."""
        # nv
        path = os.path.join(FIXTURES_DIR, "dynamic_pred.clausal")
        md = _load_via_v2(path, "_v2_dynamic_pred2")
        Color = md.get("color")
        db = md["$module"].db
        assert Color is not None
        assert is_declared_predicate(Color, arity=2, db=db), Color
        row = resolve_predicate_row(Color, arity=2, db=db)
        assert row is not None and row is db.row("color", 2)
        assert db.is_dynamic("color", 2)
        assert not row.locked
