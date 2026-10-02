"""Tests for clausal.logic.clportools — CP-SAT infrastructure unit tests.

Problem-solving tests (domains, arithmetic, all_different, labeling,
optimization, etc.) live in tests/fixtures/ortools_cpsat.seam.

These Python tests cover infrastructure that can't be tested from .clausal:
  - Internal var_map / rev_map data structures
  - Idempotent registration
  - Error handling (ground var)
  - Weakref GC cleanup
  - Activation literal backtracking mechanism (mark/undo)
  - Scheduling (interval vars, no_overlap, cumulative, 2D packing)
  - Circuit with BoolVar arc literals
  - Builtin registration wiring
"""

import gc

import pytest

from clausal.logic.variables import Var, Trail, deref, is_var, unify

from clausal.logic.clportools import (
    get_cpsat_state,
    _cpsat_states,
    or_var_for,
    or_var_from_domain,
    or_bool_for,
    or_push,
    or_add_constraint,
    or_check,
    or_in,
    or_bool,
    or_constraint_block,
    or_all_different,
    label_or,
    # Phase 3
    or_interval,
    or_interval_scoped,
    or_no_overlap,
    or_no_overlap_2d,
    or_cumulative,
    # Phase 4
    or_circuit,
)

from clausal.pythonic_ast.nodes import LtE


class TestCPSATVarInfrastructure:

    def test_var_mapping_bidirectional(self):
        # nv
        trail = Trail()
        x = Var()
        state = get_cpsat_state(trail)
        cpsat_x = or_var_for(x, 0, 10, trail)
        assert id(x) in state.var_map
        assert state.var_map[id(x)] is cpsat_x
        assert state.rev_map[cpsat_x.Index()] is x

    def test_var_mapping_idempotent(self):
        # nv
        trail = Trail()
        x = Var()
        v1 = or_var_for(x, 0, 10, trail)
        v2 = or_var_for(x, 0, 10, trail)
        assert v1 is v2

    def test_bool_var_mapping(self):
        # nv
        trail = Trail()
        b = Var()
        cpsat_b = or_bool_for(b, trail)
        state = get_cpsat_state(trail)
        assert id(b) in state.var_map
        assert state.rev_map[cpsat_b.Index()] is b

    def test_sparse_domain(self):
        # nv
        trail = Trail()
        x = Var()
        cpsat_x = or_var_from_domain(x, [1, 3, 5, 7], trail)
        state = get_cpsat_state(trail)
        assert id(x) in state.var_map

    def test_ground_var_raises(self):
        # nv
        trail = Trail()
        x = Var()
        unify(x, 1, trail)
        with pytest.raises(TypeError):
            or_var_for(x, 0, 10, trail)

    def test_state_cleanup_on_gc(self):
        # nv
        trail = Trail()
        get_cpsat_state(trail)
        tid = id(trail)
        assert tid in _cpsat_states
        del trail
        gc.collect()
        assert tid not in _cpsat_states


class TestCPSATBacktrackingMechanism:
    """Tests the activation-literal backtracking mechanism (mark/undo)."""

    def test_backtracking_retracts_constraints(self):
        # nv
        trail = Trail()
        x = Var()
        cpsat_x = or_var_for(x, 0, 10, trail)

        mark = trail.mark()
        or_push(trail)
        or_add_constraint(cpsat_x >= 8, trail)
        or_add_constraint(cpsat_x <= 3, trail)
        assert not or_check(trail)

        trail.undo(mark)
        assert or_check(trail)

    def test_nested_backtracking(self):
        # nv
        trail = Trail()
        x = Var()
        cpsat_x = or_var_for(x, 0, 10, trail)

        or_push(trail)
        or_add_constraint(cpsat_x >= 5, trail)
        mark = trail.mark()

        or_push(trail)
        or_add_constraint(cpsat_x <= 3, trail)
        assert not or_check(trail)

        trail.undo(mark)
        assert or_check(trail)

    def test_three_nested_scopes(self):
        # nv
        trail = Trail()
        x = Var()
        cpsat_x = or_var_for(x, 0, 100, trail)

        or_push(trail)
        or_add_constraint(cpsat_x >= 10, trail)
        mark1 = trail.mark()

        or_push(trail)
        or_add_constraint(cpsat_x >= 50, trail)
        mark2 = trail.mark()

        or_push(trail)
        or_add_constraint(cpsat_x >= 200, trail)
        assert not or_check(trail)

        trail.undo(mark2)
        assert or_check(trail)

        trail.undo(mark1)
        assert or_check(trail)

    def test_label_blocking_clauses_scoped(self):
        """Blocking clauses from label_or don't persist across calls."""
        # nv
        trail = Trail()
        x = Var()
        or_in(x, 1, 10, trail)
        mark = trail.mark()
        or_push(trail)
        or_add_constraint(get_cpsat_state(trail).var_map[id(x)] <= 3, trail)
        count1 = sum(1 for _ in label_or([x], trail))
        assert count1 == 3

        trail.undo(mark)
        count2 = sum(1 for _ in label_or([x], trail))
        assert count2 == 10


class TestCPSATScheduling:
    """Scheduling uses IntervalVar objects — can't be tested from .clausal yet."""

    def test_simple_no_overlap(self):
        # nv
        trail = Trail()
        s1, s2 = Var(), Var()
        e1, e2 = Var(), Var()
        or_in(s1, 0, 5, trail)
        or_in(s2, 0, 5, trail)
        or_in(e1, 0, 8, trail)
        or_in(e2, 0, 8, trail)

        iv1 = or_interval(s1, 3, e1, trail)
        iv2 = or_interval(s2, 3, e2, trail)
        or_no_overlap([iv1, iv2], trail)

        assert or_check(trail)
        sols = []
        for _ in label_or([s1, s2], trail):
            sols.append((deref(s1), deref(s2)))
        assert all(abs(a - b) >= 3 for a, b in sols)

    def test_no_overlap_unsat(self):
        # nv
        trail = Trail()
        starts = [Var() for _ in range(3)]
        ends = [Var() for _ in range(3)]
        for s in starts:
            or_in(s, 0, 5, trail)
        for e in ends:
            or_in(e, 0, 9, trail)

        intervals = []
        for s, e in zip(starts, ends):
            intervals.append(or_interval(s, 4, e, trail))
        or_no_overlap(intervals, trail)

        assert not or_check(trail)

    def test_cumulative_allows_overlap(self):
        # nv
        trail = Trail()
        s1, s2 = Var(), Var()
        e1, e2 = Var(), Var()
        or_in(s1, 0, 10, trail)
        or_in(s2, 0, 10, trail)
        or_in(e1, 0, 15, trail)
        or_in(e2, 0, 15, trail)

        iv1 = or_interval(s1, 5, e1, trail)
        iv2 = or_interval(s2, 5, e2, trail)
        or_cumulative([iv1, iv2], [2, 2], 4, trail)

        assert or_check(trail)

    def test_2d_packing(self):
        # nv
        trail = Trail()
        x1, x2, y1, y2 = Var(), Var(), Var(), Var()
        xe1, xe2, ye1, ye2 = Var(), Var(), Var(), Var()
        for v in [x1, x2, y1, y2]:
            or_in(v, 0, 2, trail)
        for v in [xe1, xe2, ye1, ye2]:
            or_in(v, 0, 4, trail)

        xiv1 = or_interval(x1, 2, xe1, trail)
        xiv2 = or_interval(x2, 2, xe2, trail)
        yiv1 = or_interval(y1, 2, ye1, trail)
        yiv2 = or_interval(y2, 2, ye2, trail)

        or_no_overlap_2d([xiv1, xiv2], [yiv1, yiv2], trail)
        assert or_check(trail)

    def test_job_shop(self):
        # nv
        trail = Trail()
        s00, e00, s01, e01 = Var(), Var(), Var(), Var()
        s10, e10, s11, e11 = Var(), Var(), Var(), Var()

        horizon = 20
        for v in [s00, e00, s01, e01, s10, e10, s11, e11]:
            or_in(v, 0, horizon, trail)

        iv00 = or_interval(s00, 3, e00, trail)
        iv01 = or_interval(s01, 2, e01, trail)
        iv10 = or_interval(s10, 4, e10, trail)
        iv11 = or_interval(s11, 1, e11, trail)

        or_constraint_block((LtE(left=e00, right=s01),), trail)
        or_constraint_block((LtE(left=e10, right=s11),), trail)

        or_no_overlap([iv00, iv11], trail)
        or_no_overlap([iv01, iv10], trail)

        assert or_check(trail)

    def test_scheduling_backtrack(self):
        # nv
        trail = Trail()
        s1, s2 = Var(), Var()
        e1, e2 = Var(), Var()
        or_in(s1, 0, 10, trail)
        or_in(s2, 0, 10, trail)
        or_in(e1, 0, 15, trail)
        or_in(e2, 0, 15, trail)

        mark = trail.mark()
        or_push(trail)
        iv1 = or_interval_scoped(s1, 5, e1, trail)
        iv2 = or_interval_scoped(s2, 5, e2, trail)
        or_no_overlap([iv1, iv2], trail)

        assert or_check(trail)

        trail.undo(mark)
        assert or_check(trail)


class TestCPSATCircuit:
    """Circuit uses BoolVar arc literals — can't be tested from .clausal yet."""

    def test_tsp_3_cities(self):
        # nv
        trail = Trail()
        arcs_vars = {}
        for i in range(3):
            for j in range(3):
                if i != j:
                    arcs_vars[(i, j)] = Var()
                    or_bool(arcs_vars[(i, j)], trail)

        arcs = [(i, j, v) for (i, j), v in arcs_vars.items()]
        or_circuit(arcs, trail)
        assert or_check(trail)

    def test_circuit_2_nodes(self):
        # nv
        trail = Trail()
        a01, a10 = Var(), Var()
        or_bool(a01, trail)
        or_bool(a10, trail)
        or_circuit([(0, 1, a01), (1, 0, a10)], trail)
        assert or_check(trail)


class TestORToolsBuiltinRegistration:

    def test_cpsat_registered(self):
        # nv
        from clausal.logic.builtins._registry import get_builtin_predicate
        assert get_builtin_predicate("ortools.cpsat", 1) is not None

    def test_cpsat_in_registered(self):
        # nv
        from clausal.logic.builtins._registry import get_builtin_predicate
        assert get_builtin_predicate("ortools.cpsat.in", 3) is not None

    def test_cpsat_solve_registered(self):
        # nv
        from clausal.logic.builtins._registry import get_builtin_predicate
        assert get_builtin_predicate("ortools.cpsat.solve", 1) is not None

    def test_glop_registered(self):
        # nv
        from clausal.logic.builtins._registry import get_builtin_predicate
        assert get_builtin_predicate("ortools.glop", 1) is not None

    def test_scip_registered(self):
        # nv
        from clausal.logic.builtins._registry import get_builtin_predicate
        assert get_builtin_predicate("ortools.scip", 1) is not None

    def test_max_flow_registered(self):
        # nv
        from clausal.logic.builtins._registry import get_builtin_predicate
        assert get_builtin_predicate("ortools.graph.max_flow", 4) is not None

    def test_tsp_registered(self):
        # nv
        from clausal.logic.builtins._registry import get_builtin_predicate
        assert get_builtin_predicate("ortools.routing.tsp", 4) is not None

    def test_knapsack_registered(self):
        # nv
        from clausal.logic.builtins._registry import get_builtin_predicate
        assert get_builtin_predicate("ortools.knapsack", 5) is not None
