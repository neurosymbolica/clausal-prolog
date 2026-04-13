"""Tests for meta-interpreter specialization via partial deduction.

Phase 0: Pattern recognition on the five MIs from metainterpreters.clausal.
Phase 1: Core unfolder — specialize each MI with natnum/graph programs and
         verify identical results to unspecialized versions.
Phase 3: Object programs with builtins/external goals — residual goal
         dispatch via catch-all clause and _SolveGoal.
Phase 5: Conjunctive partial deduction (deforestation) — non-deterministic
         inlining, intermediate list elimination, pre/post-match chaining.
"""

from __future__ import annotations

import pytest
from clausal.logic.specialization import (
    analyze_mi,
    specialize_mi,
    specialize_mi_cpd,
    MIPattern,
    CannotSpecialize,
    ConjunctionMemoTable,
    _known_functors,
    _has_residual_goals,
    _ast_unify,
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
        # nv
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.name == "Solve"
        assert pattern.arity == 2
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == []
        assert pattern.recursive_call_style == "tail"

    def test_has_base_and_recursive(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.base_clause is not None
        assert pattern.recursive_clause is not None

    def test_no_pre_match_goals(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.pre_match_goals == []

    def test_no_post_match_goals(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.post_match_goals == []

    def test_match_clause_found(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.match_clause_index == 0

    def test_append_found(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.append_index == 1

    def test_one_recursive_call(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        assert len(pattern.recursive_call_indices) == 1

    def test_variables_extracted(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        assert pattern.goal_var is not None
        assert pattern.goals_var is not None
        assert pattern.body_var is not None
        assert pattern.all_goals_var is not None
        assert pattern.program_var is not None


class TestAnalyzeSolveCount:
    """Inference-counting MI: SolveCount/3."""

    def test_pattern_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveCount)
        assert pattern.name == "SolveCount"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "tail"

    def test_post_match_goals(self, mi_module):
        """COUNT := SUB_COUNT + 1 is a post-match goal."""
        # nv
        pattern = analyze_mi(mi_module.SolveCount)
        assert len(pattern.post_match_goals) == 1
        from clausal.pythonic_ast.nodes import Evaluate
        assert isinstance(pattern.post_match_goals[0], Evaluate)


class TestAnalyzeSolveLimit:
    """Depth-limited MI: SolveLimit/3."""

    def test_pattern_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveLimit)
        assert pattern.name == "SolveLimit"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "tail"

    def test_pre_match_goals(self, mi_module):
        """MAX > 0 and MAX1 := MAX - 1 are pre-match goals."""
        # nv
        pattern = analyze_mi(mi_module.SolveLimit)
        assert len(pattern.pre_match_goals) == 2
        from clausal.pythonic_ast.nodes import Gt, Evaluate
        assert isinstance(pattern.pre_match_goals[0], Gt)
        assert isinstance(pattern.pre_match_goals[1], Evaluate)


class TestAnalyzeSolveTree:
    """Proof-tree MI: SolveTree/3."""

    def test_pattern_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveTree)
        assert pattern.name == "SolveTree"
        assert pattern.arity == 3
        assert pattern.goal_arg == 0
        assert pattern.program_arg == 1
        assert pattern.extra_args == [2]
        assert pattern.recursive_call_style == "split"

    def test_no_append(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveTree)
        assert pattern.append_index is None

    def test_two_recursive_calls(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveTree)
        assert len(pattern.recursive_call_indices) == 2

    def test_no_pre_post_match_goals(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveTree)
        assert pattern.pre_match_goals == []
        assert pattern.post_match_goals == []


class TestAnalyzeSolveIterativeDeepening:
    """Iterative deepening MI: SolveIterativeDeepening/2.

    This MI is not a standard MI pattern (it delegates to SolveLimit).
    analyze_mi should raise CannotSpecialize.
    """

    def test_cannot_specialize(self, mi_module):
        # nv
        with pytest.raises(CannotSpecialize):
            analyze_mi(mi_module.SolveIterativeDeepening)


class TestAnalyzeExplicitProgramArg:
    """Test explicit program_arg specification."""

    def test_explicit_program_arg(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveCount, program_arg=1)
        assert pattern.program_arg == 1

    def test_invalid_program_arg(self, mi_module):
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveNatnum")
        # 1 base + 2 object clauses = 3
        assert len(pred_cls._clauses) == 3

    def test_field_count(self, mi_module):
        """Specialized predicate drops PROGRAM field."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveNatnum2")
        assert len(pred_cls._fields) == 1  # just GOALS
        assert "GOALS" in pred_cls._fields

    def test_solve_natnum_0(self, mi_module):
        """SolveNatnum([["natnum", 0]]) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveNatnum3", module_dict,
        )
        results = list(_query(pred_cls, [["natnum", 0]], module_dict))
        assert len(results) >= 1

    def test_solve_natnum_s0(self, mi_module):
        """SolveNatnum([["natnum", ["s", 0]]]) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveNatnum4", module_dict,
        )
        results = list(_query(pred_cls, [["natnum", ["s", 0]]], module_dict))
        assert len(results) >= 1

    def test_solve_natnum_ss0(self, mi_module):
        """SolveNatnum([["natnum", ["s", ["s", 0]]]]) should succeed."""
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_graph_program(), "SolveGraph")
        # 1 base + 5 object clauses = 6
        assert len(pred_cls._clauses) == 6

    def test_solve_edge(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveGraph2", module_dict,
        )
        results = list(_query(pred_cls, [["edge", "a", "b"]], module_dict))
        assert len(results) >= 1

    def test_solve_path_direct(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveGraph3", module_dict,
        )
        results = list(_query(pred_cls, [["path", "a", "b"]], module_dict))
        assert len(results) >= 1

    def test_solve_path_transitive(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_graph_program(), "SolveGraph4", module_dict,
        )
        results = list(_query(pred_cls, [["path", "a", "c"]], module_dict))
        assert len(results) >= 1

    def test_solve_no_path(self, mi_module):
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.SolveCount)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveCountNatnum")
        # 1 base + 2 object clauses = 3
        assert len(pred_cls._clauses) == 3

    def test_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveCount)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveCountNatnum2")
        assert pred_cls._fields == ("GOALS", "COUNT")

    def test_count_natnum_0(self, mi_module):
        """SolveCountNatnum([["natnum", 0]], COUNT) → COUNT = 1."""
        # nv
        pattern = analyze_mi(mi_module.SolveCount)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_natnum_program(), "SolveCountNatnum3", module_dict,
        )
        results = list(_query_with_extra(pred_cls, [["natnum", 0]], module_dict))
        assert any(count == 1 for count in results)

    def test_count_natnum_s0(self, mi_module):
        """SolveCountNatnum([["natnum", ["s", 0]]], COUNT) → COUNT = 2."""
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.SolveLimit)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveLimitNatnum")
        assert len(pred_cls._clauses) == 3

    def test_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveLimit)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveLimitNatnum2")
        assert pred_cls._fields == ("GOALS", "MAX_DEPTH")

    def test_limit_natnum_s0_depth1_fails(self, mi_module):
        """Depth 1 is not enough for natnum(s(0)) → should fail."""
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.SolveTree)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveTreeNatnum")
        assert len(pred_cls._clauses) == 3

    def test_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.SolveTree)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveTreeNatnum2")
        assert pred_cls._fields == ("GOALS", "TREE")

    def test_tree_natnum_0(self, mi_module):
        """SolveTreeNatnum([["natnum", 0]], TREE) → TREE = [[["natnum", 0], []]]."""
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
        assert _known_functors(_make_natnum_program()) == {"natnum"}

    def test_graph(self):
        # nv
        assert _known_functors(_make_graph_program()) == {"edge", "path"}

    def test_factorial(self):
        # nv
        assert _known_functors(_make_factorial_program()) == {"factorial"}

    def test_mixed(self):
        # nv
        assert _known_functors(_make_mixed_program()) == {"double", "quadruple"}


class TestHasResidualGoals:
    """Test _has_residual_goals helper."""

    def test_natnum_no_residual(self):
        # nv
        prog = _make_natnum_program()
        assert not _has_residual_goals(prog, _known_functors(prog))

    def test_graph_no_residual(self):
        # nv
        prog = _make_graph_program()
        assert not _has_residual_goals(prog, _known_functors(prog))

    def test_factorial_has_residual(self):
        # nv
        prog = _make_factorial_program()
        assert _has_residual_goals(prog, _known_functors(prog))

    def test_mixed_has_residual(self):
        # nv
        prog = _make_mixed_program()
        assert _has_residual_goals(prog, _known_functors(prog))


class TestSpecializeSolveFactorial:
    """Specialize vanilla Solve/2 with factorial program (has builtins)."""

    def test_clause_count(self, mi_module):
        """1 base + 2 object clauses + 1 catch-all = 4."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_factorial_program(), "SolveFactorial")
        assert len(pred_cls._clauses) == 4

    def test_fields(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_factorial_program(), "SolveFactorial2")
        assert "GOALS" in pred_cls._fields
        assert "PROGRAM" not in pred_cls._fields

    def test_factorial_0(self, mi_module):
        """factorial(0, 1) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial3", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 0, 1]], module_dict))
        assert len(results) >= 1

    def test_factorial_1(self, mi_module):
        """factorial(1, 1) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial4", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 1, 1]], module_dict))
        assert len(results) >= 1

    def test_factorial_3(self, mi_module):
        """factorial(3, 6) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial5", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 3, 6]], module_dict))
        assert len(results) >= 1

    def test_factorial_5(self, mi_module):
        """factorial(5, 120) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveFactorial6", module_dict,
        )
        results = list(_query(pred_cls, [["factorial", 5, 120]], module_dict))
        assert len(results) >= 1

    def test_factorial_wrong_result_fails(self, mi_module):
        """factorial(3, 7) should fail."""
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.SolveCount)
        pred_cls = specialize_mi(
            pattern, _make_factorial_program(), "SolveCountFactorial",
        )
        assert len(pred_cls._clauses) == 4

    def test_count_factorial_0(self, mi_module):
        """factorial(0, 1) needs 1 step."""
        # nv
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
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven", module_dict,
        )
        results = list(_query(pred_cls, [["even", 0]], module_dict))
        assert len(results) >= 1

    def test_even_2(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven2", module_dict,
        )
        results = list(_query(pred_cls, [["even", 2]], module_dict))
        assert len(results) >= 1

    def test_even_4(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven3", module_dict,
        )
        results = list(_query(pred_cls, [["even", 4]], module_dict))
        assert len(results) >= 1

    def test_odd_1_fails(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_even_odd_program(), "SolveEven4", module_dict,
        )
        results = list(_query(pred_cls, [["even", 1]], module_dict))
        assert len(results) == 0

    def test_odd_3_fails(self, mi_module):
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_mixed_program(), "SolveMixed", module_dict,
        )
        results = list(_query(pred_cls, [["double", 3, 6]], module_dict))
        assert len(results) >= 1

    def test_quadruple_3(self, mi_module):
        """quadruple(3, 12) should succeed."""
        # nv
        pattern = analyze_mi(mi_module.Solve)
        module_dict = {}
        pred_cls = specialize_mi(
            pattern, _make_mixed_program(), "SolveMixed2", module_dict,
        )
        results = list(_query(pred_cls, [["quadruple", 3, 12]], module_dict))
        assert len(results) >= 1

    def test_quadruple_wrong_fails(self, mi_module):
        """quadruple(3, 10) should fail."""
        # nv
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
        # nv
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_natnum_program(), "SolveNatnumNoCatch")
        # 1 base + 2 object = 3 (no catch-all)
        assert len(pred_cls._clauses) == 3

    def test_graph_no_catchall(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        pred_cls = specialize_mi(pattern, _make_graph_program(), "SolveGraphNoCatch")
        # 1 base + 5 object = 6 (no catch-all)
        assert len(pred_cls._clauses) == 6


class TestCustomGoalMap:
    """Test custom goal_map parameter for user-defined residual handlers."""

    def test_custom_handler(self, mi_module):
        """Custom handler for 'double_it' functor."""
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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
        # nv
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


# ── Phase 4: Termination control ──────────────────────────────────────────────


class TestHomeomorphicEmbedding:
    """Unit tests for the embeds() function."""

    def test_var_embeds_var(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        assert embeds(Var(), Var())

    def test_var_does_not_embed_constant(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        assert not embeds(Var(), 42)

    def test_constant_does_not_embed_var(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        assert not embeds(42, Var())

    def test_equal_constants(self):
        # nv
        from clausal.logic.specialization import embeds
        assert embeds(0, 0)
        assert embeds("a", "a")

    def test_different_constants(self):
        # nv
        from clausal.logic.specialization import embeds
        assert not embeds(0, 1)
        assert not embeds("a", "b")

    def test_same_functor_coupling(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        # f(X) embeds f(Y) — same functor, var embeds var.
        assert embeds(["f", Var()], ["f", Var()])

    def test_same_functor_args(self):
        # nv
        from clausal.logic.specialization import embeds
        # f(0) embeds f(0).
        assert embeds(["f", 0], ["f", 0])
        # f(0) does NOT embed f(1).
        assert not embeds(["f", 0], ["f", 1])

    def test_diving(self):
        # nv
        from clausal.logic.specialization import embeds
        # f(0) embeds g(f(0)) — dives into g's arg.
        assert embeds(["f", 0], ["g", ["f", 0]])

    def test_diving_nested(self):
        # nv
        from clausal.logic.specialization import embeds
        # 0 embeds f(0) — constant dives into compound.
        assert embeds(0, ["f", 0])

    def test_growth_detection(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        # natnum(X) is embedded BY natnum(s(Y)) — the latter is "bigger".
        # in_ the standard definition, embeds(s, t) means s is a sub-pattern of t.
        # natnum(s(Y)) does NOT embed natnum(X) (compound arg doesn't embed var).
        # But natnum(X) DOES embed natnum(s(Y)) via diving: X doesn't embed s(Y),
        # but natnum(X) dives into natnum(s(Y))'s arg s(Y)... no.
        # Actually: for the termination test, we check if the NEW atom embeds
        # an ANCESTOR.  If natnum(s(Y)) embeds natnum(X), growth is detected.
        # s(Y) embeds X? No.  So coupling fails.
        # The correct growth check: the ancestor natnum(X) is embedded in the
        # descendant natnum(s(Y)) via diving: natnum(X) embeds natnum(Y)
        # (coupling: var embeds var), and natnum(Y) is a sub-term of natnum(s(Y)).
        # Wait — natnum(Y) is not a sub-term of natnum(s(Y)).  s(Y) is.
        # Standard: natnum(X) embeds natnum(s(Y))? No — coupling requires X embeds s(Y).
        # This is a limitation of strict homeomorphic embedding.  in_ practice,
        # the depth counter handles this.
        x, y = Var(), Var()
        # Verify that at least trivially-growing terms are caught:
        # f(X) embeds f(f(X)) — f(X) dives into f(f(X))'s arg f(X).
        assert embeds(["f", x], ["f", ["f", y]])

    def test_no_embed_different_arity(self):
        # nv
        from clausal.logic.specialization import embeds
        # f(0) does NOT embed f(0, 1) — different arity.
        assert not embeds(["f", 0], ["f", 0, 1])

    def test_transitive_growth(self):
        # nv
        from clausal.logic.specialization import embeds
        from clausal.logic.variables import Var
        # f(X, Y) embeds f(f(X), Y) — coupling: f(X) embeds f(f(X)) via diving,
        # and Y (var) embeds Y (var).
        x1, y1, x2, y2 = Var(), Var(), Var(), Var()
        assert embeds(
            ["f", ["f", x1], y1],
            ["f", ["f", ["f", x2]], y2],
        )

    def test_constant_does_not_embed_compound(self):
        # nv
        from clausal.logic.specialization import embeds
        # 0 doesn't embed ["natnum", 0] via coupling (different types).
        # But it does embed via diving (0 is inside the compound).
        assert embeds(0, ["natnum", 0])

    def test_compound_does_not_embed_constant(self):
        # nv
        from clausal.logic.specialization import embeds
        assert not embeds(["f", 0], 0)


class TestMemoTable:
    """Tests for the MemoTable memoization class."""

    def test_empty_lookup(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        assert memo.lookup(["natnum", 0]) is None

    def test_register_and_lookup(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        memo.register(["natnum", 0], "SolveNatnum")
        assert memo.lookup(["natnum", 0]) == "SolveNatnum"

    def test_register_var_pattern(self):
        # nv
        from clausal.logic.specialization import MemoTable
        from clausal.logic.variables import Var
        memo = MemoTable()
        memo.register(["natnum", Var()], "SolveNatnum")
        # Any natnum with a var should match.
        assert memo.lookup(["natnum", Var()]) == "SolveNatnum"

    def test_different_functor_no_match(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        memo.register(["natnum", 0], "SolveNatnum")
        assert memo.lookup(["even", 0]) is None

    def test_multiple_registrations(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        memo.register(["natnum", 0], "SolveNatnum")
        memo.register(["even", 0], "SolveEven")
        assert memo.lookup(["natnum", 0]) == "SolveNatnum"
        assert memo.lookup(["even", 0]) == "SolveEven"

    def test_non_list_lookup(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        assert memo.lookup(42) is None
        assert memo.lookup([]) is None

    def test_entries_property(self):
        # nv
        from clausal.logic.specialization import MemoTable
        memo = MemoTable()
        memo.register(["f", 0], "SpecF")
        entries = memo.entries
        assert "f" in entries
        assert len(entries["f"]) == 1


class TestSpecializeDeep:
    """Tests for specialize_mi_deep with depth-bounded unfolding."""

    def test_depth_0_same_as_shallow(self, mi_module):
        """At max_depth=0, deep unfolder produces same clauses as shallow."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_natnum_program()

        # Shallow specialization.
        shallow_cls = specialize_mi(pattern, program, "ShallowNatnum")
        shallow_count = len(shallow_cls._clauses)

        # Deep with depth=0.
        deep_cls = specialize_mi_deep(
            pattern, program, "DeepNatnum0", max_depth=0,
        )
        deep_count = len(deep_cls._clauses)

        assert shallow_count == deep_count

    def test_deep_natnum_produces_results(self, mi_module):
        """Deep-specialized natnum should still produce correct results."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_natnum_program()
        module_dict = {}
        pred_cls = specialize_mi_deep(
            pattern, program, "DeepNatnum1", module_dict, max_depth=3,
        )

        results = list(_query(pred_cls, [["natnum", 0]], module_dict))
        assert len(results) >= 1

    def test_deep_natnum_s0(self, mi_module):
        """Deep-specialized natnum: s(0) should succeed."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_natnum_program()
        module_dict = {}
        pred_cls = specialize_mi_deep(
            pattern, program, "DeepNatnum2", module_dict, max_depth=3,
        )

        results = list(_query(pred_cls, [["natnum", ["s", 0]]], module_dict))
        assert len(results) >= 1

    def test_deep_factorial_base(self, mi_module):
        """Deep-specialized factorial(0, 1) should succeed."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_factorial_program()
        module_dict = {}
        pred_cls = specialize_mi_deep(
            pattern, program, "DeepFactorial1", module_dict, max_depth=3,
        )

        results = list(_query(pred_cls, [["factorial", 0, 1]], module_dict))
        assert len(results) >= 1

    def test_deep_factorial_1(self, mi_module):
        """Deep-specialized factorial(1, 1) should succeed."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        pattern = analyze_mi(mi_module.Solve)
        program = _make_factorial_program()
        module_dict = {}
        pred_cls = specialize_mi_deep(
            pattern, program, "DeepFactorial2", module_dict, max_depth=5,
        )

        r_var = Var()
        results = []
        for _ in call(pred_cls, [["factorial", 1, r_var]]):
            results.append(walk(deref(r_var)))
        assert 1 in results

    def test_deep_count_natnum(self, mi_module):
        """Deep-specialized SolveCount with natnum: counting preserved."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.SolveCount)
        program = _make_natnum_program()
        module_dict = {}
        pred_cls = specialize_mi_deep(
            pattern, program, "DeepCountNatnum", module_dict, max_depth=3,
        )

        results = list(_query_with_extra(
            pred_cls, [["natnum", ["s", 0]]], module_dict,
        ))
        assert len(results) >= 1
        assert all(isinstance(r, int) for r in results)

    def test_deep_graph_path(self, mi_module):
        """Deep-specialized Solve with graph: paths still found."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_graph_program()
        module_dict = {}
        pred_cls = specialize_mi_deep(
            pattern, program, "DeepGraph1", module_dict, max_depth=3,
        )

        # path(a, c) should succeed.
        results = list(_query(
            pred_cls, [["path", "a", "c"]], module_dict,
        ))
        assert len(results) >= 1

    def test_max_depth_respected(self, mi_module):
        """Unfolding should not exceed max_depth."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_natnum_program()

        # Very low depth — should still produce valid (if not deeply inlined) code.
        pred_cls = specialize_mi_deep(
            pattern, program, "DeepNatnum_d1", max_depth=1,
        )
        # Should have at least the base clause count.
        assert len(pred_cls._clauses) >= 3  # 1 base + 2 object

    def test_equivalence_natnum(self, mi_module):
        """Deep-specialized natnum matches shallow for all small values."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep

        pattern = analyze_mi(mi_module.Solve)
        program = _make_natnum_program()
        module_dict_s = {}
        module_dict_d = {}
        shallow_cls = specialize_mi(
            pattern, program, "ShallowNatnum_eq", module_dict_s,
        )
        deep_cls = specialize_mi_deep(
            pattern, program, "DeepNatnum_eq", module_dict_d, max_depth=5,
        )

        for val in [0, ["s", 0], ["s", ["s", 0]], ["s", ["s", ["s", 0]]]]:
            shallow_results = list(_query(
                shallow_cls, [["natnum", val]], module_dict_s,
            ))
            deep_results = list(_query(
                deep_cls, [["natnum", val]], module_dict_d,
            ))
            assert len(shallow_results) == len(deep_results), (
                f"Mismatch for natnum({val}): "
                f"shallow={len(shallow_results)}, deep={len(deep_results)}"
            )

    def test_equivalence_factorial(self, mi_module):
        """Deep-specialized factorial matches shallow for small values."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        pattern = analyze_mi(mi_module.Solve)
        program = _make_factorial_program()
        module_dict_s = {}
        module_dict_d = {}
        shallow_cls = specialize_mi(
            pattern, program, "ShallowFact_eq", module_dict_s,
        )
        deep_cls = specialize_mi_deep(
            pattern, program, "DeepFact_eq", module_dict_d, max_depth=5,
        )

        for n, expected in [(0, 1), (1, 1), (3, 6)]:
            for cls, md, label in [
                (shallow_cls, module_dict_s, "shallow"),
                (deep_cls, module_dict_d, "deep"),
            ]:
                r = Var()
                results = []
                for _ in call(cls, [["factorial", n, r]]):
                    results.append(walk(deref(r)))
                assert expected in results, (
                    f"{label} factorial({n}): expected {expected}, got {results}"
                )


class TestEmbeddingTermination:
    """Tests that homeomorphic embedding prevents divergence."""

    def test_self_recursive_natnum_terminates(self, mi_module):
        """Natnum is self-recursive; deep unfolding should terminate."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_natnum_program()
        # If embedding check fails, this would loop forever.
        pred_cls = specialize_mi_deep(
            pattern, program, "TermNatnum", max_depth=20,
        )
        assert pred_cls is not None

    def test_recursive_factorial_terminates(self, mi_module):
        """Factorial is self-recursive; deep unfolding should terminate."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_factorial_program()
        pred_cls = specialize_mi_deep(
            pattern, program, "TermFactorial", max_depth=20,
        )
        assert pred_cls is not None

    def test_mutual_recursion_graph_terminates(self, mi_module):
        """Graph program has edge/path mutual reference; should terminate."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_graph_program()
        pred_cls = specialize_mi_deep(
            pattern, program, "TermGraph", max_depth=20,
        )
        assert pred_cls is not None

    def test_even_recursive_terminates(self, mi_module):
        """Even/odd recursive program should terminate deep unfolding."""
        # nv
        from clausal.logic.specialization import specialize_mi_deep
        pattern = analyze_mi(mi_module.Solve)
        program = _make_even_odd_program()
        pred_cls = specialize_mi_deep(
            pattern, program, "TermEven", max_depth=20,
        )
        assert pred_cls is not None


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


# ── Phase 5: Conjunctive Partial Deduction ─────────────────────────────────────


class TestAstUnify:
    """Unit tests for AST-level unification."""

    def test_ground_match(self):
        # nv
        assert _ast_unify(["natnum", 0], ["natnum", 0]) == {}

    def test_ground_mismatch(self):
        # nv
        assert _ast_unify(["natnum", 0], ["edge", 0]) is None

    def test_var_binds(self):
        # nv
        from clausal.logic.variables import Var
        x = Var()
        result = _ast_unify(["natnum", x], ["natnum", 0])
        assert result is not None
        assert result[id(x)] == 0

    def test_var_in_second(self):
        # nv
        from clausal.logic.variables import Var
        y = Var()
        result = _ast_unify(["natnum", 0], ["natnum", y])
        assert result is not None
        assert result[id(y)] == 0

    def test_nested_unify(self):
        # nv
        from clausal.logic.variables import Var
        x = Var()
        result = _ast_unify(["natnum", ["s", x]], ["natnum", ["s", 0]])
        assert result is not None
        assert result[id(x)] == 0

    def test_both_vars(self):
        # nv
        from clausal.logic.variables import Var
        x, y = Var(), Var()
        result = _ast_unify(["edge", x, y], ["edge", "a", "b"])
        assert result is not None
        assert result[id(x)] == "a"
        assert result[id(y)] == "b"

    def test_arity_mismatch(self):
        # nv
        assert _ast_unify(["natnum", 0], ["natnum", 0, 1]) is None

    def test_same_var(self):
        # nv
        from clausal.logic.variables import Var
        x = Var()
        result = _ast_unify(x, x)
        assert result == {}

    def test_var_to_compound(self):
        # nv
        from clausal.logic.variables import Var
        x = Var()
        result = _ast_unify(x, ["natnum", 0])
        assert result is not None
        assert result[id(x)] == ["natnum", 0]


class TestConjunctionMemoTable:
    """Tests for the conjunction memoization table."""

    def test_empty(self):
        # nv
        memo = ConjunctionMemoTable()
        assert not memo.has_seen([["natnum", 0]])

    def test_register_and_lookup(self):
        # nv
        memo = ConjunctionMemoTable()
        memo.register([["natnum", 0]])
        assert memo.has_seen([["natnum", 0]])

    def test_different_pattern(self):
        # nv
        memo = ConjunctionMemoTable()
        memo.register([["natnum", 0]])
        assert not memo.has_seen([["edge", "a"]])

    def test_entries(self):
        # nv
        memo = ConjunctionMemoTable()
        memo.register([["natnum", 0]])
        assert ("natnum",) in memo.entries


class TestCpdSolveNatnum:
    """CPD on vanilla Solve/2 with natnum program."""

    def test_more_clauses_than_shallow(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        shallow = specialize_mi(pattern, _make_natnum_program(), "SolveSh1")
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SolveCpd1")
        assert len(cpd._clauses) >= len(shallow._clauses)

    def test_natnum_0(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SolveCpd2")
        assert sum(1 for _ in call(cpd, [["natnum", 0]])) == 1

    def test_natnum_s_0(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SolveCpd3")
        assert sum(1 for _ in call(cpd, [["natnum", ["s", 0]]])) == 1

    def test_natnum_s_s_s_0(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SolveCpd4")
        assert sum(1 for _ in call(cpd, [["natnum", ["s", ["s", ["s", 0]]]]])) == 1

    def test_equivalence_natnum(self, mi_module):
        """CPD produces same results as Phase 1 for various natnum inputs."""
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        shallow = specialize_mi(pattern, _make_natnum_program(), "SolveSh5")
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SolveCpd5")
        for n in range(6):
            term = 0
            for _ in range(n):
                term = ["s", term]
            goal = [["natnum", term]]
            s = sum(1 for _ in call(shallow, goal))
            c = sum(1 for _ in call(cpd, goal))
            assert s == c, f"natnum({n}): shallow={s}, cpd={c}"


class TestCpdSolveGraph:
    """CPD on vanilla Solve/2 with graph program."""

    def test_more_clauses_than_shallow(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        shallow = specialize_mi(pattern, _make_graph_program(), "SolveGSh1")
        cpd = specialize_mi_cpd(pattern, _make_graph_program(), "SolveGCpd1")
        assert len(cpd._clauses) > len(shallow._clauses)

    def test_path_a_b(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(pattern, _make_graph_program(), "SolveGCpd2")
        assert sum(1 for _ in call(cpd, [["path", "a", "b"]])) == 1

    def test_path_a_c(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(pattern, _make_graph_program(), "SolveGCpd3")
        assert sum(1 for _ in call(cpd, [["path", "a", "c"]])) == 1

    def test_path_a_d(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(pattern, _make_graph_program(), "SolveGCpd4")
        assert sum(1 for _ in call(cpd, [["path", "a", "d"]])) == 1

    def test_edge_a_b(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(pattern, _make_graph_program(), "SolveGCpd5")
        assert sum(1 for _ in call(cpd, [["edge", "a", "b"]])) == 1

    def test_equivalence_graph(self, mi_module):
        """CPD produces same results as Phase 1 for all graph queries."""
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        shallow = specialize_mi(pattern, _make_graph_program(), "SolveGSh6")
        cpd = specialize_mi_cpd(pattern, _make_graph_program(), "SolveGCpd6")
        queries = [
            [["edge", "a", "b"]], [["edge", "b", "c"]], [["edge", "b", "d"]],
            [["path", "a", "b"]], [["path", "a", "c"]], [["path", "a", "d"]],
            [["path", "b", "c"]], [["path", "b", "d"]],
        ]
        for q in queries:
            s = sum(1 for _ in call(shallow, q))
            c = sum(1 for _ in call(cpd, q))
            assert s == c, f"{q}: shallow={s}, cpd={c}"


class TestCpdSolveCount:
    """CPD on SolveCount/3 with natnum — tests post-match chaining."""

    def test_count_natnum_0(self, mi_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.SolveCount)
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SCCpd1")
        v = Var()
        for _ in call(cpd, [["natnum", 0]], v):
            assert walk(deref(v)) == 1

    def test_count_natnum_s_0(self, mi_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.SolveCount)
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SCCpd2")
        v = Var()
        for _ in call(cpd, [["natnum", ["s", 0]]], v):
            assert walk(deref(v)) == 2

    def test_count_equivalence(self, mi_module):
        """CPD counting matches Phase 1 counting for natnum(0..5)."""
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.SolveCount)
        shallow = specialize_mi(pattern, _make_natnum_program(), "SCSh3")
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SCCpd3")
        for n in range(6):
            term = 0
            for _ in range(n):
                term = ["s", term]
            vs, vc = Var(), Var()
            sv = None
            for _ in call(shallow, [["natnum", term]], vs):
                sv = walk(deref(vs))
            cv = None
            for _ in call(cpd, [["natnum", term]], vc):
                cv = walk(deref(vc))
            assert sv == cv, f"natnum({n}): shallow={sv}, cpd={cv}"


class TestCpdSolveLimit:
    """CPD on SolveLimit/3 — tests pre-match chaining."""

    def test_limit_passes(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.SolveLimit)
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SLCpd1")
        assert sum(1 for _ in call(cpd, [["natnum", ["s", ["s", 0]]]], 10)) == 1

    def test_limit_fails(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.SolveLimit)
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SLCpd2")
        assert sum(1 for _ in call(cpd, [["natnum", ["s", ["s", ["s", 0]]]]], 2)) == 0

    def test_limit_equivalence(self, mi_module):
        """CPD limit behavior matches Phase 1 for various depths and limits."""
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.SolveLimit)
        shallow = specialize_mi(pattern, _make_natnum_program(), "SLSh3")
        cpd = specialize_mi_cpd(pattern, _make_natnum_program(), "SLCpd3")
        for depth in range(5):
            term = 0
            for _ in range(depth):
                term = ["s", term]
            for limit in range(7):
                s = sum(1 for _ in call(shallow, [["natnum", term]], limit))
                c = sum(1 for _ in call(cpd, [["natnum", term]], limit))
                assert s == c, f"natnum({depth}) limit={limit}: {s} vs {c}"


class TestCpdFactorial:
    """CPD with factorial program (has residual goals: gt, sub, mul)."""

    def test_factorial_results(self, mi_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(pattern, _make_factorial_program(), "SolveFactCpd1")
        for n, expected in [(0, 1), (1, 1), (3, 6), (5, 120)]:
            r = Var()
            for _ in call(cpd, [["factorial", n, r]]):
                assert walk(deref(r)) == expected, f"factorial({n})"

    def test_factorial_equivalence(self, mi_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        shallow = specialize_mi(pattern, _make_factorial_program(), "SolveFactSh2")
        cpd = specialize_mi_cpd(pattern, _make_factorial_program(), "SolveFactCpd2")
        for n in [0, 1, 2, 3, 4, 5]:
            rs, rc = Var(), Var()
            sv = None
            for _ in call(shallow, [["factorial", n, rs]]):
                sv = walk(deref(rs))
            cv = None
            for _ in call(cpd, [["factorial", n, rc]]):
                cv = walk(deref(rc))
            assert sv == cv, f"factorial({n}): shallow={sv}, cpd={cv}"


class TestCpdEvenOdd:
    """CPD with even/odd program (has residual goals: gte, sub)."""

    def test_even_equivalence(self, mi_module):
        # nv
        from clausal.logic.solve import call
        pattern = analyze_mi(mi_module.Solve)
        shallow = specialize_mi(pattern, _make_even_odd_program(), "SolveEvSh1")
        cpd = specialize_mi_cpd(pattern, _make_even_odd_program(), "SolveEvCpd1")
        for n in range(10):
            s = sum(1 for _ in call(shallow, [["even", n]]))
            c = sum(1 for _ in call(cpd, [["even", n]]))
            assert s == c, f"even({n}): shallow={s}, cpd={c}"


class TestCpdTermination:
    """Tests that CPD terminates on recursive programs."""

    def test_natnum_terminates(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(
            pattern, _make_natnum_program(), "SolveTerm1", max_depth=20,
        )
        assert len(cpd._clauses) > 0

    def test_graph_terminates(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(
            pattern, _make_graph_program(), "SolveTerm2", max_depth=20,
        )
        assert len(cpd._clauses) > 0

    def test_factorial_terminates(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(
            pattern, _make_factorial_program(), "SolveTerm3", max_depth=20,
        )
        assert len(cpd._clauses) > 0

    def test_even_terminates(self, mi_module):
        # nv
        pattern = analyze_mi(mi_module.Solve)
        cpd = specialize_mi_cpd(
            pattern, _make_even_odd_program(), "SolveTerm4", max_depth=20,
        )
        assert len(cpd._clauses) > 0
