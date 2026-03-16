"""Tests for term expansion — TermExpansion/4 predicate.

Verifies:
1. No TermExpansion → pass-through, zero overhead
2. Identity expansion (pass-through with TE rule)
3. Clause suppression (``"none"``)
4. TermExpansion clauses are NOT themselves expanded
5. q(...) quasi-quotation produces correct AST nodes
6. Variables shared between q(...) and clause body
7. Full pipeline integration: .clausal fixtures with TermExpansion
"""

from __future__ import annotations

import ast
import os
import sys
import warnings

import pytest

from clausal.import_hook import (
    EmbedTransformer,
    _fact_to_predicate_node,
    _load_module,
    predicate_builtins,
)
from clausal.logic.compiler_v2 import compile_module
from clausal.logic.database import Module as LogicModule, head_key
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.solve import call
from clausal.logic.term_expansion import (
    run_term_expansion,
    _is_term_expansion_clause,
)
from clausal.logic.variables import Var, Trail, deref


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _parse_and_collect(source: str):
    """Parse source, run EmbedTransformer, collect predicate nodes."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        tree = ast.parse(source)
        transformer = EmbedTransformer()
        tree = transformer.visit(tree)
        ast.fix_missing_locations(tree)

    module_items = transformer._module_items
    module_dict = {"__name__": "_test_expansion"}
    module_dict.update(predicate_builtins)

    predicate_nodes = []
    dummy_lm = LogicModule("_test_expansion_", module_dict=module_dict)
    module_dict["$module"] = dummy_lm
    module_dict["$define_predicate"] = lambda pred, lm: predicate_nodes.append(pred)
    module_dict["$assert_fact"] = lambda term: predicate_nodes.append(
        _fact_to_predicate_node(term)
    )
    code = compile(tree, filename="<test>", mode="exec")
    exec(code, module_dict)

    return predicate_nodes, module_items, module_dict


class TestPassThrough:
    """No TermExpansion → zero overhead pass-through."""

    def test_no_expansion_returns_same(self):
        """Without TermExpansion clauses, items pass through unchanged."""
        source = 'foo("a"),\nfoo("b"),\n'
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert result is preds  # exact same list object (no copy)

    def test_empty_input(self):
        """Empty predicate list returns empty."""
        result = run_term_expansion([], {})
        assert result == []


class TestTermExpansionDetection:
    """Test _is_term_expansion_clause."""

    def test_detects_te_clause(self):
        """TermExpansion/4 clauses are detected."""
        source = (
            'TermExpansion(Term_, Expansion_, M0_, M1_) <- ('
            '    Term_ is Expansion_,'
            '    M0_ is M1_'
            ')\n'
        )
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 1
        assert _is_term_expansion_clause(preds[0])

    def test_non_te_not_detected(self):
        """Regular clauses are not detected as TermExpansion."""
        source = 'foo("a"),\n'
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 1
        assert not _is_term_expansion_clause(preds[0])


class TestIdentityExpansion:
    """TermExpansion that passes items through unchanged."""

    def test_identity_expansion(self):
        """TermExpansion(T, T, M, M) passes all items through."""
        source = (
            'TermExpansion(Term_, Term_, M0_, M0_) <- True\n'
            'foo("a"),\n'
            'foo("b"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        # TE clause removed, two foo items remain
        assert len(result) == 2
        for p in result:
            assert type(p.head).__name__ == "foo"

    def test_identity_via_fixture(self):
        """Full import of expansion_passthrough.clausal."""
        mod = _load_module(
            "_exp_pt", os.path.join(FIXTURES_DIR, "expansion_passthrough.clausal")
        )
        lm = mod.__dict__["$module"]
        x = Var()
        results = []
        for t in call("foo", x, module=lm):
            results.append(deref(x))
        assert sorted(results) == ["a", "b", "c"]


class TestSuppression:
    """TermExpansion that suppresses items."""

    def test_suppress_all(self):
        """TermExpansion(T, 'none', M, M) suppresses all items."""
        source = (
            'TermExpansion(Term_, "none", M0_, M0_) <- True\n'
            'foo("a"),\n'
            'foo("b"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert result == []

    def test_suppress_via_fixture(self):
        """Full import of expansion_suppress.clausal — no foo clauses."""
        mod = _load_module(
            "_exp_sup", os.path.join(FIXTURES_DIR, "expansion_suppress.clausal")
        )
        lm = mod.__dict__["$module"]
        assert not lm.db.is_defined("foo", 1)


class TestTeNotExpanded:
    """TermExpansion clauses themselves are not expanded."""

    def test_te_clauses_removed_from_output(self):
        """TE clauses are separated, not passed through expansion."""
        source = (
            'TermExpansion(Term_, Term_, M0_, M0_) <- True\n'
            'foo("x"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 2  # 1 TE + 1 foo
        result = run_term_expansion(preds, md)
        # Only foo should remain — TE clause was separated out
        assert len(result) == 1
        assert type(result[0].head).__name__ == "foo"


class TestQuasiQuotation:
    """Test q(...) quasi-quotation in TermTransformer."""

    def test_q_produces_call_node(self):
        """q(foo(X_)) produces a Call constructor AST node."""
        from clausal.templating.term_rewriting import TermTransformer
        tree = ast.parse("q(foo(X_))", mode="eval").body
        t = TermTransformer()
        result = t.visit(tree)

        # Result should be a Python AST Call that constructs simple_ast.Call
        assert isinstance(result, ast.Call)
        assert isinstance(result.func, ast.Name)
        assert result.func.id == "Call"
        kw_names = {kw.arg for kw in result.keywords}
        assert "func" in kw_names
        assert "args" in kw_names

    def test_q_shares_vars(self):
        """Variables inside q() are shared with the enclosing context."""
        from clausal.templating.term_rewriting import TermTransformer
        tree = ast.parse("[q(foo(X_)), bar(X_)]", mode="eval").body
        t = TermTransformer()
        t.visit(tree)
        assert "X_" in t.seen_vars


class TestModuleItemsUnchanged:
    """Verify that module_items (directives, imports) are unaffected by expansion."""

    def test_directives_preserved(self):
        """Directives in module_items survive term expansion."""
        from clausal.pythonic_ast.nodes import Directive
        source = '-dynamic(color/2)\ncolor("sky", "blue"),\n'
        preds, items, md = _parse_and_collect(source)
        directives = [i for i in items if isinstance(i, Directive)]
        assert len(directives) == 1
        assert directives[0].specs == [("color", 2)]


class TestIntegrationWithCompileModule:
    """Test term expansion integrated with compile_module."""

    def test_no_expansion_full_pipeline(self):
        """Full pipeline with no TermExpansion clauses works normally."""
        source = 'foo("a"),\nfoo("b"),\n'
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_no_te")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("foo", x, module=lm):
            results.append(deref(x))
        assert sorted(results) == ["a", "b"]

    def test_identity_expansion_full_pipeline(self):
        """Full pipeline with identity TE — all clauses survive."""
        source = (
            'TermExpansion(Term_, Term_, M0_, M0_) <- True\n'
            'bar("x"),\n'
            'bar("y"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_id_te")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("bar", x, module=lm):
            results.append(deref(x))
        assert sorted(results) == ["x", "y"]

    def test_suppression_full_pipeline(self):
        """Full pipeline with suppression TE — no clauses compiled."""
        source = (
            'TermExpansion(Term_, "none", M0_, M0_) <- True\n'
            'baz("a"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_sup_te")
        assert not lm.db.is_defined("baz", 1)
