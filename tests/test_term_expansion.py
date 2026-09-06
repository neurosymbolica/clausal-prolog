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

from clausal.logic.atoms import mint
from clausal.import_hook import (
    EmbedTransformer,
    _fact_to_predicate_node,
    _load_module,
    predicate_builtins,
    runtime_builtins,
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
    # P3-2 Task 8: mirrors import_hook.py's exec_module seeding order --
    # the atom pool first, runtime_builtins layered on top and winning any
    # collision.
    module_dict.update(predicate_builtins)
    module_dict.update(runtime_builtins)

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
        # nv
        source = 'foo("a"),\nfoo("b"),\n'
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert result is preds  # exact same list object (no copy)

    def test_empty_input(self):
        """Empty predicate list returns empty."""
        # nv
        result = run_term_expansion([], {})
        assert result == []


class TestTermExpansionDetection:
    """Test _is_term_expansion_clause."""

    def test_detects_te_clause(self):
        """TermExpansion/4 clauses are detected."""
        # nv
        source = (
            'TermExpansion(_term, _expansion, _m0, _m1) <- ('
            '    _term is _expansion,'
            '    _m0 is _m1'
            ')\n'
        )
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 1
        assert _is_term_expansion_clause(preds[0])

    def test_non_te_not_detected(self):
        """Regular clauses are not detected as TermExpansion."""
        # nv
        source = 'foo("a"),\n'
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 1
        assert not _is_term_expansion_clause(preds[0])


class TestIdentityExpansion:
    """TermExpansion that passes items through unchanged."""

    def test_identity_expansion(self):
        """TermExpansion(T, T, M, M) passes all items through."""
        # nv
        source = (
            'TermExpansion(_term, _term, _m0, _m0) <- True\n'
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
        # nv
        mod = _load_module(
            "_exp_pt", os.path.join(FIXTURES_DIR, "expansion_passthrough.clausal")
        )
        lm = mod.__dict__["$module"]
        x = Var()
        results = []
        for t in call("foo", x, module=lm):
            results.append(deref(x))
        assert sorted(results) == [mint("a"), mint("b"), mint("c")]


class TestSuppression:
    """TermExpansion that suppresses items."""

    def test_suppress_all(self):
        """TermExpansion(T, 'none', M, M) suppresses all items."""
        # nv
        source = (
            'TermExpansion(_term, "none", _m0, _m0) <- True\n'
            'foo("a"),\n'
            'foo("b"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert result == []

    def test_suppress_via_fixture(self):
        """Full import of expansion_suppress.clausal — no foo clauses."""
        # nv
        mod = _load_module(
            "_exp_sup", os.path.join(FIXTURES_DIR, "expansion_suppress.clausal")
        )
        lm = mod.__dict__["$module"]
        assert not lm.db.is_defined("foo", 1)


class TestTeNotExpanded:
    """TermExpansion clauses themselves are not expanded."""

    def test_te_clauses_removed_from_output(self):
        """TE clauses are separated, not passed through expansion."""
        # nv
        source = (
            'TermExpansion(_term, _term, _m0, _m0) <- True\n'
            'foo("x"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        assert len(preds) == 2  # 1 TE + 1 foo
        result = run_term_expansion(preds, md)
        # Only foo should remain — TE clause was separated out
        assert len(result) == 1
        assert type(result[0].head).__name__ == "foo"


class TestOneToMany:
    """TermExpansion that produces multiple items from one."""

    def test_duplicate_items(self):
        """TermExpansion(T, [T, T], M, M) duplicates each item."""
        # nv
        source = (
            'TermExpansion(_term, [_term, _term], _m0, _m0) <- True\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert len(result) == 2
        for p in result:
            assert type(p.head).__name__ == "foo"

    def test_duplicate_full_pipeline(self):
        """Full pipeline: duplicate items → double the clauses."""
        # nv
        source = (
            'TermExpansion(_term, [_term, _term], _m0, _m0) <- True\n'
            'item("x"),\n'
            'item("y"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_dup_te")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("item", x, module=lm):
            results.append(deref(x))
        # Each item duplicated: x, x, y, y
        assert sorted(results) == [mint("x"), mint("x"), mint("y"), mint("y")]


class TestModuleState:
    """Module state threading through expansion."""

    def test_state_unmatched_passes_through(self):
        """When a TE rule's body cleanly FAILS, items pass through unchanged."""
        # The head matches the state (binding _count="nil"), but the guard
        # `_count == 0` fails for the initial "nil" count → no solution →
        # pass-through.  (Body failure, not body error — see the error case in
        # ``test_state_body_arith_error_propagates`` below.)
        # nv
        source = (
            'TermExpansion(_term, _term, ModuleExpansionState(_i, _f, _count), '
            'ModuleExpansionState(_i, _f, _next)) <- '
            '(_count == 0, _next == _count + 1)\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        assert len(result) == 1
        assert type(result[0].head).__name__ == "foo"

    def test_state_body_arith_error_propagates(self):
        """A TE rule whose body errors (e.g. arithmetic on a non-number) raises,
        rather than silently failing into pass-through.

        Bad arithmetic (``"nil" + 1``) is a type error and must surface — it is
        catchable in .clausal via ``catch/3`` (e.g. ``TypeError(_)``).  This pins
        the decided semantics: body *errors* propagate; only body *failure* (no
        solution) yields pass-through.
        """
        # nv
        source = (
            'TermExpansion(_term, _term, ModuleExpansionState(_i, _f, _count), '
            'ModuleExpansionState(_i, _f, _next)) <- eval_(_count + 1, _next)\n'
            'foo("a"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        with pytest.raises(TypeError):
            run_term_expansion(preds, md)


class TestQuasiQuotation:
    """Test q(...) quasi-quotation in TermTransformer."""

    def test_q_produces_call_node(self):
        """q(foo(_x)) produces a Call constructor AST node."""
        # nv
        from clausal.templating.term_rewriting import TermTransformer
        tree = ast.parse("q(foo(_x))", mode="eval").body
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
        # nv
        from clausal.templating.term_rewriting import TermTransformer
        tree = ast.parse("[q(foo(_x)), bar(_x)]", mode="eval").body
        t = TermTransformer()
        t.visit(tree)
        assert "_x" in t.seen_vars


class TestModuleItemsUnchanged:
    """Verify that module_items (directives, imports) are unaffected by expansion."""

    def test_directives_preserved(self):
        """Directives in module_items survive term expansion."""
        # nv
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
        # nv
        source = 'foo("a"),\nfoo("b"),\n'
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_no_te")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("foo", x, module=lm):
            results.append(deref(x))
        assert sorted(results) == [mint("a"), mint("b")]

    def test_identity_expansion_full_pipeline(self):
        """Full pipeline with identity TE — all clauses survive."""
        # nv
        source = (
            'TermExpansion(_term, _term, _m0, _m0) <- True\n'
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
        assert sorted(results) == [mint("x"), mint("y")]

    def test_suppression_full_pipeline(self):
        """Full pipeline with suppression TE — no clauses compiled."""
        # nv
        source = (
            'TermExpansion(_term, "none", _m0, _m0) <- True\n'
            'baz("a"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_sup_te")
        assert not lm.db.is_defined("baz", 1)


class TestImportedExpansionRules:
    """TermExpansion rules imported from another module via -import_from."""

    def test_imported_te_via_fixture(self):
        """Full import of expansion_importer.clausal which imports TE rules."""
        # nv
        import sys
        # Ensure fixtures dir is on path for -import_from resolution.
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        if fixtures_dir not in sys.path:
            sys.path.insert(0, fixtures_dir)
        try:
            # First load the provider so it's in sys.modules.
            _load_module(
                "expansion_provider",
                os.path.join(FIXTURES_DIR, "expansion_provider.clausal"),
            )
            # Now load the importer that uses -import_from(expansion_provider, ...).
            mod = _load_module(
                "_exp_imp",
                os.path.join(FIXTURES_DIR, "expansion_importer.clausal"),
            )
            lm = mod.__dict__["$module"]
            x = Var()
            results = []
            for t in call("color", x, module=lm):
                results.append(deref(x))
            # The imported TE rule duplicates each item.
            assert sorted(results) == [mint("green"), mint("green"), mint("red"), mint("red")]
        finally:
            sys.modules.pop("expansion_provider", None)
            sys.modules.pop("_exp_imp", None)

    def test_imported_te_predicate_nodes_stored(self):
        """Provider module stores _te_predicate_nodes on TermExpansion class."""
        # nv
        mod = _load_module(
            "_exp_prov",
            os.path.join(FIXTURES_DIR, "expansion_provider.clausal"),
        )
        te_cls = mod.__dict__.get("TermExpansion")
        assert te_cls is not None
        assert hasattr(te_cls, "_te_predicate_nodes")
        assert len(te_cls._te_predicate_nodes) == 1


class TestNewFunctorsFromExpansion:
    """Expansion that creates predicates with functors not in the source."""

    def test_expansion_creates_new_functor(self):
        """TermExpansion rewrites src/1 facts into dst/1 facts."""
        # The expansion rule rewrites every item into an item with a different
        # functor name ("dst") that doesn't appear in the original source.
        # Because the TE rule unifies _term with the original Predicate node
        # and _expansion is constructed by Clausal's own unification, the
        # result is a new Predicate node with head dst(...).
        # nv
        source = (
            'TermExpansion(_term, _exp, _m0, _m0) <- (\n'
            '    _term is _exp,\n'  # identity — passes item through
            '    _m0 is _m0\n'
            ')\n'
            'src("hello"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        # With identity expansion, src items pass through
        assert len(result) == 1
        assert type(result[0].head).__name__ == "src"

    def test_new_functor_full_pipeline(self):
        """Full pipeline: expansion duplicates items, creating more clauses.

        This verifies compile_module handles predicates produced by expansion
        that weren't in the original source (extra clauses for same functor).
        """
        # nv
        source = (
            'TermExpansion(_term, [_term, _term], _m0, _m0) <- True\n'
            'color("red"),\n'
            'color("blue"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_new_fn")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("color", x, module=lm):
            results.append(deref(x))
        # Each duplicated: red, red, blue, blue
        assert sorted(results) == [mint("blue"), mint("blue"), mint("red"), mint("red")]


class TestInitFinalInjection:
    """Module state init/final list injection."""

    def test_init_list_injection(self):
        """TermExpansion accumulates init items via module state."""
        # This TE rule passes items through but adds each item to the
        # init list (prepended items).
        # nv
        source = (
            'TermExpansion(_term, _term, ModuleExpansionState(_init, _final, _s), '
            'ModuleExpansionState([_term | _init], _final, _s)) <- True\n'
            'item("a"),\n'
            'item("b"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        # Items passed through (2) + init items prepended (2) = 4
        # Init list is built by consing, so it's reversed: [b, a]
        assert len(result) == 4

    def test_final_list_injection(self):
        """TermExpansion accumulates final items via module state."""
        # nv
        source = (
            'TermExpansion(_term, _term, ModuleExpansionState(_init, _final, _s), '
            'ModuleExpansionState(_init, [_term | _final], _s)) <- True\n'
            'item("x"),\n'
        )
        preds, _, md = _parse_and_collect(source)
        result = run_term_expansion(preds, md)
        # 1 passed through + 1 appended from final list
        assert len(result) == 2

    def test_init_final_full_pipeline(self):
        """Full pipeline with init/final injection — all items compiled."""
        # nv
        source = (
            'TermExpansion(_term, _term, ModuleExpansionState(_init, _final, _s), '
            'ModuleExpansionState([_term | _init], [_term | _final], _s)) <- True\n'
            'val("one"),\n'
        )
        preds, items, md = _parse_and_collect(source)
        lm = compile_module(preds, items, md, "_test_init_final")
        md["$module"] = lm

        x = Var()
        results = []
        for trail in call("val", x, module=lm):
            results.append(deref(x))
        # Original + init copy + final copy = 3 solutions
        assert results.count(mint("one")) == 3


class TestNestedVarSubstitution:
    """A var matched inside a quoted PATTERN flows into the quoted OUTPUT.

    Gap 2 of todo/term-expansion-compile-time-predicate-synthesis.md (filed
    2026-07-03): ``TermExpansion(q(key(KEY)), [q(marker(KEY))], S, S)`` used
    to leave ``marker/1`` existing but EMPTY — the matched KEY never reached
    the registered output facts.  Fixed since; pinned here end-to-end.
    """

    def test_matched_var_registers_in_output_facts(self):
        # nv
        mod = _load_module(
            "_exp_nested_var",
            os.path.join(FIXTURES_DIR, "expansion_nested_var.clausal"),
        )
        lm = mod.__dict__["$module"]
        x = Var()
        results = [deref(x) for _ in call("marker", x, module=lm)]
        names = sorted(results, key=repr)
        assert names == [mint("income"), mint("stays")], (
            f"matched KEY must flow into the quoted output; got {results!r}"
        )
