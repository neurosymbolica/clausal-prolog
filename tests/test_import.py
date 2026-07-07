"""Tests for Step 6 — import hook wiring.

Verifies that importing a ``.clausal`` predicate module:
  - Creates a LogicModule (database.Module) as ``$module``
  - Asserts all clauses into the database
  - Compiles every predicate so ``dispatch_fn`` is non-None
  - Injects Var, Compound, Trail, unify, deref, walk into the module namespace
  - Produces dispatch functions that correctly match/fail on ground queries
  - Handles recursive predicates (reach via edge)
  - Supports runtime assertz after import via lazy recompile
"""

from __future__ import annotations

import sys
import os
import types

import pytest

# Ensure the import hook is active.
import clausal.import_hook
from clausal.import_hook import _load_module
from clausal.logic.trampoline import StepGenerator, DONE


def _run_dispatch(dispatch, *args):
    """Drive a trampoline-protocol dispatch function, return list of solution counts."""
    # args = (*pred_args, trail) — trail is last, ignore the old trailing None
    # include out trailing None from old simple-mode call pattern
    from clausal.logic.variables import Trail
    sg = StepGenerator(dispatch, None, None, None, *args)
    results = []
    gen, value = sg.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return results
            results.append(value)
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


# ── Fixture loading helper ────────────────────────────────────────────────────


def _load_fixture(filename: str, mod_name: str | None = None) -> object:
    """Load a .clausal file from tests/fixtures/ using the PredicateLoader.

    Each call loads a fresh module instance (any cached entry is evicted first)
    so tests are independent.
    """
    path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
    name = mod_name or f"_test_fixture_{filename.replace('.', '_')}"
    return _load_module(name, path)


# ── $module is a real LogicModule ─────────────────────────────────────────────


def test_module_is_logic_module():
    # nv
    from clausal.logic.database import Module as LogicModule
    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]
    assert isinstance(logic_mod, LogicModule)


def test_module_name_matches_import_name():
    # nv
    from clausal.logic.database import Module as LogicModule
    name = "_test_edge_name"
    mod = _load_fixture("edge_graph.clausal", name)
    logic_mod = mod.__dict__["$module"]
    assert logic_mod.name == name


# ── Predicates are defined and compiled ───────────────────────────────────────


def test_edge_predicate_is_defined():
    # nv
    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]
    assert logic_mod.db.is_defined("Edge", 2)


def test_reach_predicate_is_defined():
    # nv
    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]
    assert logic_mod.db.is_defined("Reach", 2)


def test_edge_dispatch_fn_is_compiled():
    # nv
    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]
    dispatch = logic_mod.db.get_dispatch("Edge", 2)
    assert dispatch is not None


def test_reach_dispatch_fn_is_compiled():
    # nv
    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]
    dispatch = logic_mod.db.get_dispatch("Reach", 2)
    assert dispatch is not None


def test_edge_has_three_clauses():
    # nv
    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]
    clauses = logic_mod.db.clauses_for("Edge", 2)
    assert len(clauses) == 3


def test_reach_has_two_clauses():
    # nv
    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]
    clauses = logic_mod.db.clauses_for("Reach", 2)
    assert len(clauses) == 2


# ── Runtime namespace injections ──────────────────────────────────────────────


def test_var_injected():
    # nv
    from clausal.logic.variables import Var
    mod = _load_fixture("edge_graph.clausal")
    assert mod.__dict__["Var"] is Var


def test_compound_injected():
    # nv
    from clausal.terms import Compound
    mod = _load_fixture("edge_graph.clausal")
    assert mod.__dict__["Compound"] is Compound


def test_trail_injected():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    assert mod.__dict__["Trail"] is Trail


def test_unify_injected():
    # nv — A12-F004: injected under the reserved $-prefix, not the public name.
    from clausal.logic.variables import unify
    mod = _load_fixture("edge_graph.clausal")
    assert mod.__dict__["$unify"] is unify
    assert "unify" not in mod.__dict__  # public name freed for user predicates


def test_deref_injected():
    # nv — A12-F004: injected under the reserved $-prefix.
    from clausal.logic.variables import deref
    mod = _load_fixture("edge_graph.clausal")
    assert mod.__dict__["$deref"] is deref
    assert "deref" not in mod.__dict__


# ── edge dispatch: ground queries ─────────────────────────────────────────────


def test_edge_matches_1_2():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    dispatch = mod.__dict__["$module"].db.get_dispatch("Edge", 2)
    results = _run_dispatch(dispatch, 1, 2, Trail())
    assert len(results) == 1


def test_edge_matches_2_3():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    dispatch = mod.__dict__["$module"].db.get_dispatch("Edge", 2)
    results = _run_dispatch(dispatch, 2, 3, Trail())
    assert len(results) == 1


def test_edge_matches_1_3():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    dispatch = mod.__dict__["$module"].db.get_dispatch("Edge", 2)
    results = _run_dispatch(dispatch, 1, 3, Trail())
    assert len(results) == 1


def test_edge_no_match_2_1():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    dispatch = mod.__dict__["$module"].db.get_dispatch("Edge", 2)
    results = _run_dispatch(dispatch, 2, 1, Trail())
    assert len(results) == 0


def test_edge_no_match_9_9():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    dispatch = mod.__dict__["$module"].db.get_dispatch("Edge", 2)
    results = _run_dispatch(dispatch, 9, 9, Trail())
    assert len(results) == 0


# ── reach dispatch: transitive closure ───────────────────────────────────────


def test_reach_direct_edge():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    dispatch = mod.__dict__["$module"].db.get_dispatch("Reach", 2)
    # Reach(1, 2) via Edge(1, 2) directly
    results = _run_dispatch(dispatch, 1, 2, Trail())
    assert len(results) >= 1


def test_reach_transitive():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    dispatch = mod.__dict__["$module"].db.get_dispatch("Reach", 2)
    # Reach(1, 3): directly via Edge(1,3), and transitively via Edge(1,2)->Reach(2,3)
    results = _run_dispatch(dispatch, 1, 3, Trail())
    assert len(results) >= 1


def test_reach_no_path_3_1():
    # nv
    from clausal.logic.variables import Trail
    mod = _load_fixture("edge_graph.clausal")
    dispatch = mod.__dict__["$module"].db.get_dispatch("Reach", 2)
    # No reverse edges, so 3 cannot reach 1
    results = _run_dispatch(dispatch, 3, 1, Trail())
    assert len(results) == 0


# ── Runtime assertz after import ──────────────────────────────────────────────


def test_runtime_assertz_adds_clause():
    # nv
    from clausal.logic.variables import Trail
    from clausal.logic.database import Clause
    import dataclasses

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    # Before: no Edge(3, 4)
    dispatch = logic_mod.db.get_dispatch("Edge", 2)
    assert _run_dispatch(dispatch, 3, 4, Trail()) == []

    # Add Edge(3, 4) at runtime.  We need an Edge instance — get the class
    # from the module namespace (it was created by _make_functor_class_ast).
    edge_cls = type(logic_mod.db.clauses_for("Edge", 2)[0].head)
    new_head = edge_cls(arg_0=3, arg_1=4)
    logic_mod.db.assertz(Clause(head=new_head, body=[]))
    # Lazy recompile kicks in on next get_dispatch() call.
    dispatch2 = logic_mod.db.get_dispatch("Edge", 2)
    results = _run_dispatch(dispatch2, 3, 4, Trail())
    assert len(results) == 1


# ── Step 7: solve/call/query/once via imported module ─────────────────────────


def test_call_edge_ground_success():
    """call() with two ground args succeeds when the edge exists.

    Note: edge clauses in the fixture have literals in both head positions,
    so both args must be ground (no Var enumeration via call).
    """
    # nv
    from clausal.logic.solve import call

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    results = list(call("Edge", 1, 2, module=logic_mod))
    assert len(results) == 1


def test_call_edge_ground_failure():
    """call() with ground args fails when edge does not exist."""
    # nv
    from clausal.logic.solve import call

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    results = list(call("Edge", 3, 1, module=logic_mod))
    assert results == []


def test_call_reach_ground_success():
    """call() with both ground args succeeds for a reachable pair.

    Note: edge_graph.clausal fixture has literal heads in both positions for Edge,
    so Reach can only be queried with ground args (both src and dst specified).
    """
    # nv
    from clausal.logic.solve import call

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    # 1 can reach 3 (directly via Edge(1,3))
    results = list(call("Reach", 1, 3, module=logic_mod))
    assert len(results) >= 1


def test_call_reach_no_solution():
    """call() yields nothing when no path exists."""
    # nv
    from clausal.logic.solve import call

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    results = list(call("Reach", 3, 1, module=logic_mod))
    assert results == []


def test_query_reach_ground_via_api():
    """query() works on a ground Reach query."""
    # nv
    from clausal.logic.solve import query
    from clausal.terms import Call, LoadName

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    goal = Call(func=LoadName(name="Reach"), args=[1, 3], kwargs=[])
    results = list(query(goal, {}, logic_mod))
    assert len(results) >= 1


def test_once_reach_ground_success():
    """once() returns non-None when Reach succeeds (ground query)."""
    # nv
    from clausal.logic.solve import once
    from clausal.terms import Call, LoadName

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    goal = Call(func=LoadName(name="Reach"), args=[1, 2], kwargs=[])
    trail = once(goal, logic_mod)
    assert trail is not None


def test_once_reach_failure_returns_none():
    """once() returns None when no path exists."""
    # nv
    from clausal.logic.solve import once
    from clausal.terms import Call, LoadName

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    goal = Call(func=LoadName(name="Reach"), args=[3, 1], kwargs=[])
    result = once(goal, logic_mod)
    assert result is None


def test_module_solve_method_on_imported():
    """Module.solve() works on an imported predicate."""
    # nv
    from clausal.terms import Call, LoadName

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    goal = Call(func=LoadName(name="Reach"), args=[2, 3], kwargs=[])
    results = list(logic_mod.solve(goal))
    assert len(results) >= 1


def test_solve_ground_edge_goal():
    """solve() with a ground Call goal succeeds for an existing edge."""
    # nv
    from clausal.logic.solve import solve
    from clausal.terms import Call, LoadName

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    goal = Call(func=LoadName(name="Edge"), args=[1, 2], kwargs=[])
    results = list(solve(goal, logic_mod))
    assert len(results) == 1


def test_call_unknown_predicate_raises():
    """call() with an undefined predicate raises KeyError."""
    # nv
    from clausal.logic.solve import call

    mod = _load_fixture("edge_graph.clausal")
    logic_mod = mod.__dict__["$module"]

    with pytest.raises(KeyError):
        list(call("no_such_predicate", 1, module=logic_mod))
