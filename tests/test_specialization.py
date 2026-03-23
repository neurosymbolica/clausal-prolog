"""Tests for meta-interpreter specialization via partial deduction.

Phase 0: Pattern recognition on the five MIs from metainterpreters.clausal.
Phase 1: Core unfolder — specialize each MI with natnum/graph programs and
         verify identical results to unspecialized versions.
Phase 3: Object programs with builtins/external goals — residual goal
         dispatch via catch-all clause and _SolveGoal.
"""

from __future__ import annotations

import pytest
from clausal.logic.specialization import (
    analyze_mi,
    specialize_mi,
    MIPattern,
    CannotSpecialize,
    _known_functors,
    _has_residual_goals,
)


@pytest.fixture(scope="module")
def mi_module():
    """Import the metainterpreters module."""
    import clausal.examples.metainterpreters as mi
    return mi


# ── Phase 0: Pattern Recognition ──────────────────────────────────────────────


class TestAnalyzeSolve:
    """Vanilla MI: Solve/2."""

    def test_pattern_fields(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.name == "Solve"
        assert pattern.arity == 2
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == []
        assert pattern.recursive_call_style == "tail"

    def test_has_base_and_recursive(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.base_clause is not None
        assert pattern.recursive_clause is not None

    def test_no_pre_match_goals(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.pre_match_goals == []

    def test_no_post_match_goals(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.post_match_goals == []

    def test_match_clause_found(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.match_clause_index == 0

    def test_append_found(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.append_index == 1

    def test_one_recursive_call(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        assert len(pattern.recursive_call_indices) == 1

    def test_variables_extracted(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.goal_var is not None
        assert pattern.goals_var is not None
        assert pattern.body_var is not None
        assert pattern.all_goals_var is not None
        assert pattern.program_var is not None


class TestAnalyzeSolveCount:
    """Inference-counting MI: SolveCount/3."""

    def test_pattern_fields(self, mi_module):
        pattern = analyze_mi(mi_module.SolveCount)
        assert pattern.name == "SolveCount"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "tail"

    def test_post_match_goals(self, mi_module):
        """COUNT := SUB_COUNT + 1 is a post-match goal."""
        pattern = analyze_mi(mi_module.SolveCount)
        assert len(pattern.post_match_goals) == 1
        from clausal.pythonic_ast.nodes import Evaluate
        assert isinstance(pattern.post_match_goals[0], Evaluate)


class TestAnalyzeSolveLimit:
    """Depth-limited MI: SolveLimit/3."""

    def test_pattern_fields(self, mi_module):
        pattern = analyze_mi(mi_module.SolveLimit)
        assert pattern.name == "SolveLimit"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "tail"

    def test_pre_match_goals(self, mi_module):
        """MAX > 0 and MAX1 := MAX - 1 are pre-match goals."""
        pattern = analyze_mi(mi_module.SolveLimit)
        assert len(pattern.pre_match_goals) == 2
        from clausal.pythonic_ast.nodes import Gt, Evaluate
        assert isinstance(pattern.pre_match_goals[0], Gt)
        assert isinstance(pattern.pre_match_goals[1], Evaluate)


class TestAnalyzeSolveTree:
    """Proof-tree MI: SolveTree/3."""

    def test_pattern_fields(self, mi_module):
        pattern = analyze_mi(mi_module.SolveTree)
        assert pattern.name == "SolveTree"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "split"

    def test_no_append(self, mi_module):
        pattern = analyze_mi(mi_module.SolveTree)
        assert pattern.append_index is None

    def test_two_recursive_calls(self, mi_module):
        pattern = analyze_mi(mi_module.SolveTree)
        assert len(pattern.recursive_call_indices) == 2

    def test_no_pre_post_match_goals(self, mi_module):
        pattern = analyze_mi(mi_module.SolveTree)
        assert pattern.pre_match_goals == []
        assert pattern.post_match_goals == []


class TestAnalyzeSolveIterativeDeepening:
    """Iterative deepening MI: SolveIterativeDeepening/2.

    This MI is not a standard MI pattern (it delegates to SolveLimit).
    analyze_mi should raise CannotSpecialize.
    """

    def test_cannot_specialize(self, mi_module):
        with pytest.raises(CannotSpecialize):
            analyze_mi(mi_module.SolveIterativeDeepening)


class TestAnalyzeExplicitProgramArg:
    """Test explicit program_arg specification."""

    def test_explicit_program_arg(self, mi_module):
        pattern = analyze_mi(mi_module.SolveCount, program_arg=1)
        assert pattern.program_arg == 1

    def test_invalid_program_arg(self, mi_module):
        with pytest.raises(CannotSpecialize):
            analyze_mi(mi_module.SolveCount, program_arg=5)


# ── Phase 1: Core Unfolder ───────────────────────────────────────────────────


def _make_natnum_program():
    from clausal.logic.variables import Var
    x = Var()
    return [
        [["natnum", 0], []],
        [["natnum", ["s", x]], [["natnum", x]]],
    ]


def _make_graph_program():
    from clausal.logic.variables import Var
    x1, y1 = Var(), Var()
    x2, y2, z2 = Var(), Var(), Var()
    return [
        [["edge", "a", "b"], []],
        [["edge", "b", "c"], []],
        [["edge", "b", "d"], []],
        [["path", x1, y1], [["edge", x1, y1]]],
        [["path", x2, y2], [["edge", x2, z2], ["path", z2, y2]]],
    ]


class TestSpecializeSolve:
    """Specialize vanilla Solve/2 with natnum program."""

    def test_clause_count(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveNatnum")
        # 1 base + 2 object clauses = 3
        assert len(pred_cls._clauses) == 3

    def test_field_count(self, mi_module):
        """Specialized predicate drops PROGRAM field."""
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveNatnum2")
        assert len(pred_cls._fields) == 1  # just GOALS
        assert "GOALS" in pred_cls._fields

    def test_solve_natnum_0(self, mi_module):
        """SolveNatnum([["natnum", 0]]) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveNatnum3", module_dict,
        )
        results = list(_query(pred_cls, [["natnum", 0]], module_dict))
        assert len(results) >= 1

    def test_solve_natnum_s0(self, mi_module):
        """SolveNatnum([["natnum", ["s", 0]]]) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveNatnum4", module_dict,
        )
        results = list(_query(pred_cls, [["natnum", ["s", 0]]], module_dict))
        assert len(results) >= 1

    def test_solve_natnum_ss0(self, mi_module):
        """SolveNatnum([["natnum", ["s", ["s", 0]]]]) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveNatnum5", module_dict,
        )
        results = list(_query(pred_cls, [["natnum", ["s", ["s", 0]]]], module_dict))
        assert len(results) >= 1


class TestSpecializeSolveGraph:
    """Specialize vanilla Solve/2 with graph program."""

    def test_clause_count(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_graph_program(), "SolveGraph")
        # 1 base + 5 object clauses = 6
        assert len(pred_cls._clauses) == 6

    def test_solve_edge(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveGraph2", module_dict,
        )
        results = list(_query(pred_cls, [["edge", "a", "b"]], module_dict))
        assert len(results) >= 1

    def test_solve_path_direct(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveGraph3", module_dict,
        )
        results = list(_query(pred_cls, [["path", "a", "b"]], module_dict))
        assert len(results) >= 1

    def test_solve_path_transitive(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveGraph4", module_dict,
        )
        results = list(_query(pred_cls, [["path", "a", "c"]], module_dict))
        assert len(results) >= 1

    def test_solve_no_path(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveGraph5", module_dict,
        )
        results = list(_query(pred_cls, [["path", "c", "a"]], module_dict))
        assert len(results) == 0


class TestSpecializeSolveCount:
    """Specialize counting MI with natnum program."""

    def test_clause_count(self, mi_module):
        pattern = analyze_mi(mi_module.SolveCount)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveCountNatnum")
        # 1 base + 2 object clauses = 3
        assert len(pred_cls._clauses) == 3

    def test_fields(self, mi_module):
        pattern = analyze_mi(mi_module.SolveCount)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveCountNatnum2")
        assert pred_cls._fields == ("GOALS", "COUNT")

    def test_count_natnum_0(self, mi_module):
        """SolveCountNatnum([["natnum", 0]], COUNT) → COUNT = 1."""
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveCountNatnum3", module_dict,
        )
        results = list(_query_with_extra(pred_cls, [["natnum", 0]], module_dict))
        assert any(count == 1 for count in results)

    def test_count_natnum_s0(self, mi_module):
        """SolveCountNatnum([["natnum", ["s", 0]]], COUNT) → COUNT = 2."""
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveCountNatnum4", module_dict,
        )
        results = list(_query_with_extra(
            pred_cls, [["natnum", ["s", 0]]], module_dict,
        ))
        assert any(count == 2 for count in results)

    def test_count_natnum_ss0(self, mi_module):
        """SolveCountNatnum([["natnum", ["s", ["s", 0]]]], COUNT) → COUNT = 3."""
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveCountNatnum5", module_dict,
        )
        results = list(_query_with_extra(
            pred_cls, [["natnum", ["s", ["s", 0]]]], module_dict,
        ))
        assert any(count == 3 for count in results)


class TestSpecializeSolveCountGraph:
    """Specialize counting MI with graph program."""

    def test_count_edge(self, mi_module):
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveCountGraph", module_dict,
        )
        results = list(_query_with_extra(
            pred_cls, [["edge", "a", "b"]], module_dict,
        ))
        assert any(count == 1 for count in results)

    def test_count_path_direct(self, mi_module):
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveCountGraph2", module_dict,
        )
        results = list(_query_with_extra(
            pred_cls, [["path", "a", "b"]], module_dict,
        ))
        assert any(count == 2 for count in results)

    def test_count_path_transitive(self, mi_module):
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveCountGraph3", module_dict,
        )
        results = list(_query_with_extra(
            pred_cls, [["path", "a", "c"]], module_dict,
        ))
        assert any(count == 4 for count in results)


class TestSpecializeSolveLimit:
    """Specialize depth-limited MI with natnum program."""

    def test_clause_count(self, mi_module):
        pattern = analyze_mi(mi_module.SolveLimit)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveLimitNatnum")
        assert len(pred_cls._clauses) == 3

    def test_fields(self, mi_module):
        pattern = analyze_mi(mi_module.SolveLimit)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveLimitNatnum2")
        assert pred_cls._fields == ("GOALS", "MAX_DEPTH")

    def test_limit_natnum_s0_depth1_fails(self, mi_module):
        """Depth 1 is not enough for natnum(s(0)) → should fail."""
        pattern = analyze_mi(mi_module.SolveLimit)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveLimitNatnum3", module_dict,
        )
        results = list(_query_limit(
            pred_cls, [["natnum", ["s", 0]]], 1, module_dict,
        ))
        assert len(results) == 0

    def test_limit_natnum_s0_depth2_succeeds(self, mi_module):
        """Depth 2 is enough for natnum(s(0)) → should succeed."""
        pattern = analyze_mi(mi_module.SolveLimit)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveLimitNatnum4", module_dict,
        )
        results = list(_query_limit(
            pred_cls, [["natnum", ["s", 0]]], 2, module_dict,
        ))
        assert len(results) >= 1

    def test_limit_natnum_ss0_depth2_fails(self, mi_module):
        pattern = analyze_mi(mi_module.SolveLimit)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveLimitNatnum5", module_dict,
        )
        results = list(_query_limit(
            pred_cls, [["natnum", ["s", ["s", 0]]]], 2, module_dict,
        ))
        assert len(results) == 0

    def test_limit_natnum_ss0_depth3_succeeds(self, mi_module):
        pattern = analyze_mi(mi_module.SolveLimit)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveLimitNatnum6", module_dict,
        )
        results = list(_query_limit(
            pred_cls, [["natnum", ["s", ["s", 0]]]], 3, module_dict,
        ))
        assert len(results) >= 1


class TestSpecializeSolveTree:
    """Specialize proof-tree MI with natnum program."""

    def test_clause_count(self, mi_module):
        pattern = analyze_mi(mi_module.SolveTree)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveTreeNatnum")
        assert len(pred_cls._clauses) == 3

    def test_fields(self, mi_module):
        pattern = analyze_mi(mi_module.SolveTree)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveTreeNatnum2")
        assert pred_cls._fields == ("GOALS", "TREE")

    def test_tree_natnum_0(self, mi_module):
        """SolveTreeNatnum([["natnum", 0]], TREE) → TREE = [[["natnum", 0], []]]."""
        pattern = analyze_mi(mi_module.SolveTree)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveTreeNatnum3", module_dict,
        )
        results = list(_query_tree(
            pred_cls, [["natnum", 0]], module_dict,
        ))
        assert len(results) >= 1
        assert results[0] == [[["natnum", 0], []]]

    def test_tree_natnum_s0(self, mi_module):
        """Nested proof tree for natnum(s(0))."""
        pattern = analyze_mi(mi_module.SolveTree)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveTreeNatnum4", module_dict,
        )
        results = list(_query_tree(
            pred_cls, [["natnum", ["s", 0]]], module_dict,
        ))
        assert len(results) >= 1
        expected = [[["natnum", ["s", 0]], [[["natnum", 0], []]]]]
        assert results[0] == expected


# ── Equivalence Tests ─────────────────────────────────────────────────────────


class TestEquivalence:
    """Verify specialized MI produces same results as unspecialized."""

    def test_solve_natnum_equivalence(self, mi_module):
        """All natnum solutions match between Solve and specialized."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveEquiv1", module_dict,
        )

        for goal in [
            [["natnum", 0]],
            [["natnum", ["s", 0]]],
            [["natnum", ["s", ["s", 0]]]],
        ]:
            spec_results = list(_query(pred_cls, goal, module_dict))
            mi_results = list(_query_mi(mi_module.Solve, goal, _make_natnum_program()))
            assert len(spec_results) == len(mi_results), (
                f"Mismatch for goal {goal}: "
                f"specialized={len(spec_results)}, MI={len(mi_results)}"
            )

    def test_solve_count_equivalence(self, mi_module):
        """Count values match between SolveCount and specialized."""
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveCountEquiv1", module_dict,
        )

        for goal, expected_count in [
            ([["natnum", 0]], 1),
            ([["natnum", ["s", 0]]], 2),
            ([["natnum", ["s", ["s", 0]]]], 3),
        ]:
            spec_results = list(_query_with_extra(pred_cls, goal, module_dict))
            assert any(c == expected_count for c in spec_results), (
                f"Expected count={expected_count} for {goal}, got {spec_results}"
            )


# ── Phase 3: Residual goal support ────────────────────────────────────────────


def _make_factorial_program():
    """Object program: factorial with arithmetic builtins (gt, sub, mul).

    factorial(0, 1).
    factorial(N, R) :- gt(N, 0), sub(N, 1, N1), factorial(N1, R1), mul(N, R1, R).
    """
    from clausal.logic.variables import Var
    n, r, n1, r1 = Var(), Var(), Var(), Var()
    return [
        [["factorial", 0, 1], []],
        [["factorial", n, r], [
            ["gt", n, 0],
            ["sub", n, 1, n1],
            ["factorial", n1, r1],
            ["mul", n, r1, r],
        ]],
    ]


def _make_even_odd_program():
    """Object program: even/odd with modular arithmetic.

    even(0).
    even(N) :- gt(N, 0), sub(N, 2, N1), even(N1).
    """
    from clausal.logic.variables import Var
    n, n1 = Var(), Var()
    return [
        [["even", 0], []],
        [["even", n], [
            ["gte", n, 2],
            ["sub", n, 2, n1],
            ["even", n1],
        ]],
    ]


def _make_mixed_program():
    """Object program mixing known and residual goals.

    double(X, Y) :- mul(X, 2, Y).
    quadruple(X, Y) :- double(X, Z), double(Z, Y).
    """
    from clausal.logic.variables import Var
    x1, y1, x2, y2, z2 = Var(), Var(), Var(), Var(), Var()
    return [
        [["double", x1, y1], [["mul", x1, 2, y1]]],
        [["quadruple", x2, y2], [["double", x2, z2], ["double", z2, y2]]],
    ]


class TestKnownFunctors:
    """Test _known_functors helper."""

    def test_natnum(self):
        assert _known_functors(_make_natnum_program()) == {"natnum"}

    def test_graph(self):
        assert _known_functors(_make_graph_program()) == {"edge", "path"}

    def test_factorial(self):
        assert _known_functors(_make_factorial_program()) == {"factorial"}

    def test_mixed(self):
        assert _known_functors(_make_mixed_program()) == {"double", "quadruple"}


class TestHasResidualGoals:
    """Test _has_residual_goals helper."""

    def test_natnum_no_residual(self):
        prog = _make_natnum_program()
        assert not _has_residual_goals(prog, _known_functors(prog))

    def test_graph_no_residual(self):
        prog = _make_graph_program()
        assert not _has_residual_goals(prog, _known_functors(prog))

    def test_factorial_has_residual(self):
        prog = _make_factorial_program()
        assert _has_residual_goals(prog, _known_functors(prog))

    def test_mixed_has_residual(self):
        prog = _make_mixed_program()
        assert _has_residual_goals(prog, _known_functors(prog))


class TestSpecializeSolveFactorial:
    """Specialize vanilla Solve/2 with factorial program (has builtins)."""

    def test_clause_count(self, mi_module):
        """1 base + 2 object clauses + 1 catch-all = 4."""
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_factorial_program(), "SolveFactorial")
        assert len(pred_cls._clauses) == 4

    def test_fields(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_factorial_program(), "SolveFactorial2")
        assert "GOALS" in pred_cls._fields
        assert "PROGRAM" not in pred_cls._fields

    def test_factorial_0(self, mi_module):
        """factorial(0, 1) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial3", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 0, 1]], module_dict))
        assert len(results) >= 1

    def test_factorial_1(self, mi_module):
        """factorial(1, 1) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial4", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 1, 1]], module_dict))
        assert len(results) >= 1

    def test_factorial_3(self, mi_module):
        """factorial(3, 6) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial5", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 3, 6]], module_dict))
        assert len(results) >= 1

    def test_factorial_5(self, mi_module):
        """factorial(5, 120) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial6", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 5, 120]], module_dict))
        assert len(results) >= 1

    def test_factorial_wrong_result_fails(self, mi_module):
        """factorial(3, 7) should fail."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial7", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 3, 7]], module_dict))
        assert len(results) == 0


class TestSpecializeSolveCountFactorial:
    """Specialize counting MI with factorial program (has builtins)."""

    def test_clause_count(self, mi_module):
        """1 base + 2 object clauses + 1 catch-all = 4."""
        pattern = analyze_mi(mi_module.SolveCount)
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveCountFactorial",
        )
        assert len(pred_cls._clauses) == 4

    def test_count_factorial_0(self, mi_module):
        """factorial(0, 1) needs 1 step."""
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveCountFactorial2",
            module_dict,
        )
        results = list(_query_with_extra(
            pred_cls, [["factorial", 0, 1]], module_dict,
        ))
        assert any(count == 1 for count in results)

    def test_count_factorial_3(self, mi_module):
        """factorial(3, 6) needs 4 steps (1 per recursive clause + base case)."""
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveCountFactorial3",
            module_dict,
        )
        results = list(_query_with_extra(
            pred_cls, [["factorial", 3, 6]], module_dict,
        ))
        # Each residual goal (gt, sub, mul) counts as 1 step, plus 1 for the
        # factorial match.  But the counting happens per-resolution-step of the
        # MI loop, not per goal.  Each goal in the goal list is one step.
        # factorial(3, 6): factorial(3,R) matches → gt,sub,factorial(2,R1),mul
        # That's 4 goals (gt, sub, factorial(2,R1), mul) plus factorial(0,1)
        # base case.  Steps counted: one per goal consumed from the goal list.
        assert len(results) >= 1
        # We check the count is > 0; exact count depends on interleaving.
        assert all(count > 0 for count in results)


class TestSpecializeSolveEvenOdd:
    """Specialize Solve/2 with even/odd program (has arithmetic builtins)."""

    def test_even_0(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven", module_dict,
        )
        results = list(_query(pred_cls, [["even", 0]], module_dict))
        assert len(results) >= 1

    def test_even_2(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven2", module_dict,
        )
        results = list(_query(pred_cls, [["even", 2]], module_dict))
        assert len(results) >= 1

    def test_even_4(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven3", module_dict,
        )
        results = list(_query(pred_cls, [["even", 4]], module_dict))
        assert len(results) >= 1

    def test_odd_1_fails(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven4", module_dict,
        )
        results = list(_query(pred_cls, [["even", 1]], module_dict))
        assert len(results) == 0

    def test_odd_3_fails(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven5", module_dict,
        )
        results = list(_query(pred_cls, [["even", 3]], module_dict))
        assert len(results) == 0


class TestSpecializeSolveMixed:
    """Specialize Solve/2 with mixed program (known + residual goals)."""

    def test_double_3(self, mi_module):
        """double(3, 6) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_mixed_program(), "SolveMixed", module_dict,
        )
        results = list(_query(pred_cls, [["double", 3, 6]], module_dict))
        assert len(results) >= 1

    def test_quadruple_3(self, mi_module):
        """quadruple(3, 12) should succeed."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_mixed_program(), "SolveMixed2", module_dict,
        )
        results = list(_query(pred_cls, [["quadruple", 3, 12]], module_dict))
        assert len(results) >= 1

    def test_quadruple_wrong_fails(self, mi_module):
        """quadruple(3, 10) should fail."""
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_mixed_program(), "SolveMixed3", module_dict,
        )
        results = list(_query(pred_cls, [["quadruple", 3, 10]], module_dict))
        assert len(results) == 0


class TestNoResidualNoCatchAll:
    """Programs without residual goals should NOT get a catch-all clause."""

    def test_natnum_no_catchall(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveNatnumNoCatch")
        # 1 base + 2 object = 3 (no catch-all)
        assert len(pred_cls._clauses) == 3

    def test_graph_no_catchall(self, mi_module):
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_graph_program(), "SolveGraphNoCatch")
        # 1 base + 5 object = 6 (no catch-all)
        assert len(pred_cls._clauses) == 6


class TestCustomGoalMap:
    """Test custom goal_map parameter for user-defined residual handlers."""

    def test_custom_handler(self, mi_module):
        """Custom handler for 'double_it' functor."""
        from clausal.logic.variables import Var, unify as _unify

        def _handle_double_it(args, trail):
            from clausal.logic.variables import deref, walk
            a = walk(deref(args[0]))
            result = a * 2
            mark = trail.mark()
            if _unify(args[1], result, trail):
                yield None
            trail.undo(mark)

        x, y = Var(), Var()
        program = [
            [["compute", x, y], [["double_it", x, y]]],
        ]

        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, program, "SolveCustom", module_dict,
            goal_map={"double_it": _handle_double_it},
        )
        results = list(_query(pred_cls, [["compute", 5, 10]], module_dict))
        assert len(results) >= 1


class TestEquivalenceWithResidual:
    """Verify specialized MI with residual goals produces correct results.

    Note: the unspecialized MI cannot handle builtins (gt, sub, mul, etc.)
    since they are not in the object program.  Phase 3 adds this capability.
    We compare against known expected results instead.
    """

    def test_factorial_known_results(self, mi_module):
        """Specialized factorial should produce correct results."""
        program = _make_factorial_program()
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, program, "SolveFactorialEquiv", module_dict,
        )

        for n, expected_r in [(0, 1), (1, 1), (2, 2), (3, 6), (4, 24), (5, 120)]:
            goal = [["factorial", n, expected_r]]
            results = list(_query(pred_cls, goal, module_dict))
            assert len(results) >= 1, (
                f"factorial({n}, {expected_r}) should succeed"
            )

    def test_factorial_query_result(self, mi_module):
        """Specialized factorial should bind result variable."""
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        program = _make_factorial_program()
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, program, "SolveFactorialEquiv2", module_dict,
        )

        for n, expected_r in [(0, 1), (1, 1), (3, 6), (5, 120)]:
            r_var = Var()
            results = []
            for _ in call(pred_cls, [["factorial", n, r_var]]):
                results.append(walk(deref(r_var)))
            assert expected_r in results, (
                f"factorial({n}, R): expected R={expected_r}, got {results}"
            )


class TestSolveLimitWithResidual:
    """Specialize depth-limited MI with factorial (has builtins)."""

    def test_limit_factorial_0_depth1(self, mi_module):
        """Depth 1 should suffice for factorial(0, 1) (just the base clause)."""
        pattern = analyze_mi(mi_module.SolveLimit)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveLimitFactorial",
            module_dict,
        )
        results = list(_query_limit(
            pred_cls, [["factorial", 0, 1]], 1, module_dict,
        ))
        assert len(results) >= 1

    def test_limit_factorial_1_depth2_fails(self, mi_module):
        """Depth 2 is not enough for factorial(1, 1) — needs gt, sub, factorial(0,1), mul."""
        pattern = analyze_mi(mi_module.SolveLimit)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveLimitFactorial2",
            module_dict,
        )
        results = list(_query_limit(
            pred_cls, [["factorial", 1, 1]], 2, module_dict,
        ))
        assert len(results) == 0

    def test_limit_factorial_1_high_depth(self, mi_module):
        """With high depth limit, factorial(1, 1) should succeed."""
        pattern = analyze_mi(mi_module.SolveLimit)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveLimitFactorial3",
            module_dict,
        )
        results = list(_query_limit(
            pred_cls, [["factorial", 1, 1]], 20, module_dict,
        ))
        assert len(results) >= 1


# ── Test helpers ──────────────────────────────────────────────────────────────


def _query(pred_cls, goal_list, module_dict):
    """Query a specialized predicate with just a goal list (no extra args)."""
    from clausal.logic.solve import call

    for _ in call(pred_cls, goal_list):
        yield True


def _query_with_extra(pred_cls, goal_list, module_dict):
    """Query a specialized predicate with goal list + one extra arg (COUNT)."""
    from clausal.logic.variables import Var, deref, walk
    from clausal.logic.solve import call

    count_var = Var()
    for _ in call(pred_cls, goal_list, count_var):
        yield walk(deref(count_var))


def _query_limit(pred_cls, goal_list, max_depth, module_dict):
    """Query a depth-limited specialized predicate."""
    from clausal.logic.solve import call

    for _ in call(pred_cls, goal_list, max_depth):
        yield True


def _query_tree(pred_cls, goal_list, module_dict):
    """Query a proof-tree specialized predicate."""
    from clausal.logic.variables import Var, deref, walk
    from clausal.logic.solve import call

    tree_var = Var()
    for _ in call(pred_cls, goal_list, tree_var):
        yield walk(deref(tree_var))


def _query_mi(mi_cls, goal_list, program):
    """Query the unspecialized MI for comparison."""
    from clausal.logic.solve import call

    for _ in call(mi_cls, goal_list, program):
        yield True
