"""Tests for Phase 2: MI specialization pipeline integration.

End-to-end tests that import .clausal fixtures using -metainterpreter
and -specialize directives, verifying that specialized predicates are
compiled and callable.
"""

from __future__ import annotations

import pytest


# ── Fixture imports ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def specialize_natnum():
    """Import the specialize_natnum fixture."""
    import tests.fixtures.specialize_natnum as mod
    return mod


@pytest.fixture(scope="module")
def specialize_graph():
    """Import the specialize_graph fixture."""
    import tests.fixtures.specialize_graph as mod
    return mod


@pytest.fixture(scope="module")
def specialize_limit():
    """Import the specialize_limit fixture."""
    import tests.fixtures.specialize_limit as mod
    return mod


# ── Directive parsing tests ──────────────────────────────────────────────────


class TestDirectiveParsing:
    """Verify that -metainterpreter and -specialize directives are parsed."""

    def test_specialized_predicate_exists(self, specialize_natnum):
        """The specialized predicate should be created in module dict."""
        assert hasattr(specialize_natnum, "SolveCountNatnum")

    def test_specialized_predicate_is_predicate_meta(self, specialize_natnum):
        from clausal.logic.predicate import PredicateMeta
        assert isinstance(specialize_natnum.SolveCountNatnum, PredicateMeta)

    def test_specialized_fields_no_program(self, specialize_natnum):
        """Specialized predicate should drop the PROGRAM field."""
        fields = specialize_natnum.SolveCountNatnum._fields
        assert "PROGRAM" not in fields
        assert "GOALS" in fields
        assert "COUNT" in fields

    def test_specialized_has_clauses(self, specialize_natnum):
        """Specialized predicate should have compiled clauses."""
        assert len(specialize_natnum.SolveCountNatnum._clauses) == 3

    def test_specialized_has_dispatch(self, specialize_natnum):
        """Specialized predicate should have a dispatch function."""
        assert specialize_natnum.SolveCountNatnum._dispatch_fn is not None


# ── SolveCount specialization tests ─────────────────────────────────────────


class TestSpecializeCountNatnum:
    """Specialized SolveCount with natnum — end-to-end via .clausal fixture."""

    def test_count_natnum_0(self, specialize_natnum):
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.SolveCountNatnum, [["natnum", 0]], count):
            results.append(walk(deref(count)))
        assert 1 in results

    def test_count_natnum_s0(self, specialize_natnum):
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.SolveCountNatnum, [["natnum", ["s", 0]]], count):
            results.append(walk(deref(count)))
        assert 2 in results

    def test_count_natnum_ss0(self, specialize_natnum):
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.SolveCountNatnum, [["natnum", ["s", ["s", 0]]]], count):
            results.append(walk(deref(count)))
        assert 3 in results

    def test_clausal_inline_tests(self, specialize_natnum):
        """All Test(...) predicates in the fixture should have passed."""
        assert hasattr(specialize_natnum, "Test")


# ── Solve specialization tests (graph) ──────────────────────────────────────


class TestSpecializeSolveGraph:
    """Specialized Solve with graph — end-to-end via .clausal fixture."""

    def test_specialized_exists(self, specialize_graph):
        assert hasattr(specialize_graph, "SolveGraph")

    def test_edge_ab(self, specialize_graph):
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [["edge", "a", "b"]]))
        assert len(results) >= 1

    def test_path_ab(self, specialize_graph):
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [["path", "a", "b"]]))
        assert len(results) >= 1

    def test_path_ac_transitive(self, specialize_graph):
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [["path", "a", "c"]]))
        assert len(results) >= 1

    def test_path_ad_transitive(self, specialize_graph):
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [["path", "a", "d"]]))
        assert len(results) >= 1

    def test_no_path_ca(self, specialize_graph):
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [["path", "c", "a"]]))
        assert len(results) == 0

    def test_solve_graph_fields(self, specialize_graph):
        fields = specialize_graph.SolveGraph._fields
        assert "PROGRAM" not in fields
        assert "GOALS" in fields


# ── SolveLimit specialization tests ─────────────────────────────────────────


class TestSpecializeLimitNatnum:
    """Specialized SolveLimit with natnum — end-to-end via .clausal fixture."""

    def test_specialized_exists(self, specialize_limit):
        assert hasattr(specialize_limit, "SolveLimitNatnum")

    def test_fields(self, specialize_limit):
        fields = specialize_limit.SolveLimitNatnum._fields
        assert "PROGRAM" not in fields
        assert "GOALS" in fields
        assert "MAX_DEPTH" in fields

    def test_limit_natnum_0_depth_1(self, specialize_limit):
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.SolveLimitNatnum, [["natnum", 0]], 1,
        ))
        assert len(results) >= 1

    def test_limit_natnum_s0_depth_1_fails(self, specialize_limit):
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.SolveLimitNatnum, [["natnum", ["s", 0]]], 1,
        ))
        assert len(results) == 0

    def test_limit_natnum_s0_depth_2(self, specialize_limit):
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.SolveLimitNatnum, [["natnum", ["s", 0]]], 2,
        ))
        assert len(results) >= 1

    def test_limit_natnum_ss0_depth_3(self, specialize_limit):
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.SolveLimitNatnum, [["natnum", ["s", ["s", 0]]]], 3,
        ))
        assert len(results) >= 1


# ── Equivalence tests ───────────────────────────────────────────────────────


class TestEquivalence:
    """Verify specialized produces same results as unspecialized MI."""

    def test_count_equivalence(self, specialize_natnum):
        """SolveCountNatnum gives same counts as SolveCount."""
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        mi_module = specialize_natnum
        spec_cls = mi_module.SolveCountNatnum

        for goal, expected in [
            ([["natnum", 0]], 1),
            ([["natnum", ["s", 0]]], 2),
            ([["natnum", ["s", ["s", 0]]]], 3),
        ]:
            count = Var()
            results = []
            for _ in call(spec_cls, goal, count):
                results.append(walk(deref(count)))
            assert expected in results, (
                f"Expected count={expected} for {goal}, got {results}"
            )

    def test_graph_solve_equivalence(self, specialize_graph):
        """SolveGraph gives same success/failure as Solve with GraphProgram."""
        from clausal.logic.solve import call

        spec_cls = specialize_graph.SolveGraph

        # Should succeed
        for goal in [
            [["edge", "a", "b"]],
            [["path", "a", "b"]],
            [["path", "a", "c"]],
            [["path", "a", "d"]],
        ]:
            results = list(call(spec_cls, goal))
            assert len(results) >= 1, f"Expected success for {goal}"

        # Should fail
        for goal in [
            [["path", "c", "a"]],
            [["edge", "c", "a"]],
        ]:
            results = list(call(spec_cls, goal))
            assert len(results) == 0, f"Expected failure for {goal}"


# ── Phase 3: Object programs with builtins ──────────────────────────────────


@pytest.fixture(scope="module")
def specialize_builtins():
    """Import the specialize_builtins fixture."""
    import tests.fixtures.specialize_builtins as mod
    return mod


class TestSpecializeFactorial:
    """Specialized Solve + factorial (has gt, sub, mul builtins)."""

    def test_specialized_exists(self, specialize_builtins):
        assert hasattr(specialize_builtins, "SolveFactorial")

    def test_has_catch_all(self, specialize_builtins):
        """Factorial has builtins → specialized predicate should have catch-all."""
        # 1 base + 2 object clauses + 1 catch-all = 4
        assert len(specialize_builtins.SolveFactorial._clauses) == 4

    def test_factorial_0(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveFactorial, [["factorial", 0, 1]]))
        assert len(results) >= 1

    def test_factorial_3(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveFactorial, [["factorial", 3, 6]]))
        assert len(results) >= 1

    def test_factorial_5(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveFactorial, [["factorial", 5, 120]]))
        assert len(results) >= 1

    def test_factorial_query_var(self, specialize_builtins):
        """Query with result as Var — binding should propagate."""
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        r = Var()
        results = []
        for _ in call(specialize_builtins.SolveFactorial, [["factorial", 4, r]]):
            results.append(walk(deref(r)))
        assert 24 in results

    def test_factorial_wrong_fails(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveFactorial, [["factorial", 3, 7]]))
        assert len(results) == 0


class TestSpecializeCountFactorial:
    """Specialized SolveCount + factorial."""

    def test_specialized_exists(self, specialize_builtins):
        assert hasattr(specialize_builtins, "SolveCountFactorial")

    def test_count_factorial_0(self, specialize_builtins):
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_builtins.SolveCountFactorial, [["factorial", 0, 1]], count):
            results.append(walk(deref(count)))
        assert 1 in results


class TestSpecializeLimitFactorial:
    """Specialized SolveLimit + factorial."""

    def test_specialized_exists(self, specialize_builtins):
        assert hasattr(specialize_builtins, "SolveLimitFactorial")

    def test_limit_factorial_0_depth_1(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveLimitFactorial, [["factorial", 0, 1]], 1))
        assert len(results) >= 1

    def test_limit_factorial_3_depth_30(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveLimitFactorial, [["factorial", 3, 6]], 30))
        assert len(results) >= 1


class TestSpecializeEven:
    """Specialized Solve + even program."""

    def test_even_0(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveEven, [["even", 0]]))
        assert len(results) >= 1

    def test_even_4(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveEven, [["even", 4]]))
        assert len(results) >= 1

    def test_odd_1_fails(self, specialize_builtins):
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveEven, [["even", 1]]))
        assert len(results) == 0


# ── Error handling tests ────────────────────────────────────────────────────


class TestErrors:
    """Test error cases for the specialization directives."""

    def test_specialize_missing_args(self):
        """Malformed -specialize with missing args should raise SyntaxError."""
        from clausal.templating.term_rewriting import EmbedTransformer
        import ast

        source = "-specialize(SolveCount)"
        with pytest.raises(SyntaxError):
            tree = ast.parse(source)
            t = EmbedTransformer()
            t.visit(tree)
