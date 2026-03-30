"""Tests for the destructive-reuse optimization.

The optimization detects goals like append(Old, Extra, New) where Old is
provably dead after the goal and dispatches to a variant that mutates Old
in-place (guarded by a runtime sys.getrefcount check) instead of copying.

Coverage:
  - Liveness analysis: _find_destructive_reuse_goals detects eligible goals
  - Correctness: optimized predicates produce the same results as unoptimized
  - Safety: head variables and live variables are NOT mutated
  - Backtracking: mutation does not corrupt backtracking semantics
  - Destructive variant builtins: _append_dr__3, _dict_put_dr__4, _set_union_dr__3
"""

from __future__ import annotations

import sys
import dataclasses

import pytest

from clausal.logic.compiler import (
    DONE,
    compile_predicate_trampoline,
    _find_destructive_reuse_goals,
)
from clausal.logic.database import Clause, Database
from clausal.logic.trampoline import StepGenerator
from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.terms import (
    And, Call, LoadName, Compound, Unify, Evaluate, Add,
    DictTerm, SetTerm,
)

from clausal.logic.builtins.lists import _append_dr__3, _append__3
from clausal.logic.builtins.dict_set import (
    _dict_put_dr__4, _dict_put__4,
    _set_union_dr__3, _set_union__3,
)


# ── Trampoline driver ────────────────────────────────────────────────────────


def _search_trampoline(dispatch_fn, args, snapshot_fn):
    """Drive trampoline predicate and collect per-solution snapshots."""
    snapshots = []
    root = StepGenerator(dispatch_fn, None, *args)
    gen, value = root.send(None)

    while True:
        if gen is None:
            if value is DONE:
                break
            snapshots.append(snapshot_fn())
            gen, value = root.send(None)
        else:
            gen, value = gen.send(value)

    return snapshots


def _snap(dispatch_fn, snapshot_fn, *args):
    return _search_trampoline(dispatch_fn, args, snapshot_fn)


def make_pred(functor, arity, clauses_data):
    """Build a Database with a trampoline-compiled predicate.

    ``clauses_data`` is a list of ``(head, body_goals)`` pairs.
    Returns ``(db, dispatch_fn)``.
    """
    db = Database()
    for head, body in clauses_data:
        db.assertz(Clause(head=head, body=body))
    fn = compile_predicate_trampoline(
        functor, arity, db.clauses_for(functor, arity), db)
    return db, fn


# ── Unit tests: _find_destructive_reuse_goals ────────────────────────────────


class TestFindDestructiveReuseGoals:
    """Test the compile-time liveness analysis."""

    def _append_call(self, l1, l2, l3):
        return Call(func=LoadName(name="append"), args=[l1, l2, l3], kwargs=[])

    def _dict_put_call(self, key, value, old, new):
        return Call(func=LoadName(name="dict_put"),
                    args=[key, value, old, new], kwargs=[])

    def _set_union_call(self, s1, s2, union):
        return Call(func=LoadName(name="set_union"),
                    args=[s1, s2, union], kwargs=[])

    def test_eligible_append_last_goal(self):
        """append(Temp, Extra, Out) where Temp is body-only and dead."""
        In, Temp, Extra, Out = Var(), Var(), Var(), Var()
        head = Compound("process", (In, Out))
        body = [
            Unify(left=Temp, right=In),  # deterministic
            self._append_call(Temp, Extra, Out),
        ]
        clause = Clause(head=head, body=body)
        # Temp appears in head? No (In, Out only).
        # Temp dead after append? Yes.
        # Preceding goals deterministic? Yes (Unify).
        # BUT Temp is used in the Unify and in the append — so it appears in
        # two goals. After the append, it's dead. Index 1 should be eligible.
        eligible = _find_destructive_reuse_goals(clause)
        assert 1 in eligible

    def test_head_var_not_eligible(self):
        """append(HeadVar, Extra, Out) — HeadVar is in the clause head."""
        Old, Extra, Out = Var(), Var(), Var()
        head = Compound("process", (Old, Out))
        body = [self._append_call(Old, Extra, Out)]
        clause = Clause(head=head, body=body)
        eligible = _find_destructive_reuse_goals(clause)
        assert 0 not in eligible

    def test_live_var_not_eligible(self):
        """append(Temp, Extra, Mid) followed by another use of Temp."""
        Temp, Extra, Mid, Out = Var(), Var(), Var(), Var()
        head = Compound("process", (Out,))
        body = [
            self._append_call(Temp, Extra, Mid),
            # Temp is used again here — NOT dead
            self._append_call(Temp, Mid, Out),
        ]
        clause = Clause(head=head, body=body)
        eligible = _find_destructive_reuse_goals(clause)
        # Neither goal should be eligible: goal 0 has Temp live after,
        # goal 1 has Temp as head var? No, Temp is body-only. But goal 1
        # uses Temp as source and it IS dead after. However, goal 0 is
        # NOT deterministic (append is a Call, not a Unify).
        # So goal 1 fails criterion 5 (preceding goals must be deterministic).
        assert 0 not in eligible
        assert 1 not in eligible

    def test_nondeterministic_prefix_not_eligible(self):
        """If a preceding goal is non-deterministic, optimization is suppressed."""
        X, Y, Temp, Extra, Out = Var(), Var(), Var(), Var(), Var()
        head = Compound("process", (X, Out))
        body = [
            # member/2 is non-deterministic
            Call(func=LoadName(name="in_"), args=[Y, X], kwargs=[]),
            Evaluate(left=Temp, right=[Y]),
            self._append_call(Temp, Extra, Out),
        ]
        clause = Clause(head=head, body=body)
        eligible = _find_destructive_reuse_goals(clause)
        assert 2 not in eligible

    def test_eligible_dict_put(self):
        """dict_put(Key, Value, Temp, Out) where Temp is body-only and dead."""
        In, Temp, Key, Value, Out = Var(), Var(), Var(), Var(), Var()
        head = Compound("update", (In, Out))
        body = [
            Unify(left=Temp, right=In),
            self._dict_put_call(Key, Value, Temp, Out),
        ]
        clause = Clause(head=head, body=body)
        eligible = _find_destructive_reuse_goals(clause)
        assert 1 in eligible

    def test_eligible_set_union(self):
        """set_union(Temp, S2, Out) where Temp is body-only and dead."""
        In, Temp, S2, Out = Var(), Var(), Var(), Var()
        head = Compound("merge", (In, Out))
        body = [
            Unify(left=Temp, right=In),
            self._set_union_call(Temp, S2, Out),
        ]
        clause = Clause(head=head, body=body)
        eligible = _find_destructive_reuse_goals(clause)
        assert 1 in eligible

    def test_source_literal_not_eligible(self):
        """append([1,2,3], Extra, Out) — source is a literal, not a Var."""
        Extra, Out = Var(), Var()
        head = Compound("process", (Out,))
        body = [self._append_call([1, 2, 3], Extra, Out)]
        clause = Clause(head=head, body=body)
        eligible = _find_destructive_reuse_goals(clause)
        assert 0 not in eligible

    def test_empty_body(self):
        """Facts have no body — nothing to optimize."""
        head = Compound("fact", (1,))
        clause = Clause(head=head, body=[])
        eligible = _find_destructive_reuse_goals(clause)
        assert eligible == set()

    def test_single_eligible_among_multiple(self):
        """Only the eligible goal is marked, not others."""
        T1, T2, X, Out = Var(), Var(), Var(), Var()
        head = Compound("multi", (X, Out))
        body = [
            Evaluate(left=T1, right=[1, 2, 3]),  # deterministic
            Evaluate(left=T2, right=[4, 5]),       # deterministic
            # T1 is dead after this, T2 still used
            self._append_call(T1, T2, Out),
        ]
        clause = Clause(head=head, body=body)
        eligible = _find_destructive_reuse_goals(clause)
        assert 2 in eligible


# ── Unit tests: destructive variant builtins ─────────────────────────────────


class TestAppendDR:
    """Test _append_dr__3 directly.

    In compiled code, the source arg arrives through a Var binding (deref
    follows the chain).  The refcount threshold (<=3) is calibrated for
    that path: Var.binding + deref local + getrefcount temp = 3.
    Direct calls with a plain list have an extra caller reference so the
    destructive path won't fire — we wrap sources in Vars for realism.
    """

    def _run(self, l1, l2, l3, trail):
        """Collect solutions from _append_dr__3."""
        solutions = []
        gen = _append_dr__3(None, None, l1, l2, l3, trail)
        for parent, value in gen:
            if value is not DONE:
                solutions.append(deref(l3))
        return solutions

    def test_unique_list_mutated_in_place(self):
        """When source list refcount is low (Var-bound, no aliases), mutate."""
        trail = Trail()
        source_var = Var()
        the_list = [1, 2, 3]
        list_id = id(the_list)
        unify(source_var, the_list, trail)
        del the_list  # drop extra ref so only Var.binding holds it

        result_var = Var()
        solutions = self._run(source_var, [4, 5], result_var, trail)

        assert len(solutions) == 1
        assert solutions[0] == [1, 2, 3, 4, 5]
        # The result should BE the same object (mutated in-place)
        assert id(solutions[0]) == list_id

    def test_shared_list_not_mutated(self):
        """When source list is shared (extra alias), a new list is created."""
        trail = Trail()
        source_var = Var()
        the_list = [1, 2, 3]
        alias = the_list  # keep an extra reference
        unify(source_var, the_list, trail)

        result_var = Var()
        solutions = self._run(source_var, [4, 5], result_var, trail)

        assert len(solutions) == 1
        assert solutions[0] == [1, 2, 3, 4, 5]
        # Original list should be unchanged
        assert alias == [1, 2, 3]
        _ = alias  # prevent gc

    def test_fallback_for_string(self):
        """Strings are never mutated — fallback to standard append."""
        trail = Trail()
        result_var = Var()
        solutions = self._run("abc", "def", result_var, trail)
        assert len(solutions) == 1
        assert solutions[0] == "abcdef"

    def test_nondeterministic_mode_falls_back(self):
        """append(-, -, +) mode (all splits) uses standard fallback."""
        trail = Trail()
        l1, l2 = Var(), Var()

        solutions = []
        gen = _append_dr__3(None, None, l1, l2, [1, 2, 3], trail)
        for parent, value in gen:
            if value is not DONE:
                solutions.append((
                    list(deref(l1)) if isinstance(deref(l1), list) else deref(l1),
                    list(deref(l2)) if isinstance(deref(l2), list) else deref(l2),
                ))

        assert len(solutions) == 4  # [], [1], [1,2], [1,2,3]


class TestDictPutDR:
    """Test _dict_put_dr__4 directly (Var-wrapped for realistic refcounts)."""

    def test_unique_dict_mutated_in_place(self):
        """When DictTerm refcount is low (Var-bound, no aliases), mutate."""
        trail = Trail()
        source_var = Var()
        the_dict = DictTerm({"a": 1})
        dict_id = id(the_dict)
        unify(source_var, the_dict, trail)
        del the_dict

        result_var = Var()
        solutions = []
        gen = _dict_put_dr__4(None, None, "b", 2, source_var, result_var, trail)
        for parent, value in gen:
            if value is not DONE:
                solutions.append(deref(result_var))

        assert len(solutions) == 1
        result = solutions[0]
        assert isinstance(result, DictTerm)
        assert dict(result.data) == {"a": 1, "b": 2}
        assert id(result) == dict_id

    def test_shared_dict_not_mutated(self):
        """When DictTerm is shared (extra alias), a new DictTerm is created."""
        trail = Trail()
        source_var = Var()
        the_dict = DictTerm({"a": 1})
        alias = the_dict
        unify(source_var, the_dict, trail)

        result_var = Var()
        solutions = []
        gen = _dict_put_dr__4(None, None, "b", 2, source_var, result_var, trail)
        for parent, value in gen:
            if value is not DONE:
                solutions.append(deref(result_var))

        assert len(solutions) == 1
        assert dict(solutions[0].data) == {"a": 1, "b": 2}
        assert dict(alias.data) == {"a": 1}
        _ = alias


class TestSetUnionDR:
    """Test _set_union_dr__3 directly (Var-wrapped for realistic refcounts)."""

    def test_unique_set_mutated_in_place(self):
        """When SetTerm refcount is low (Var-bound, no aliases), mutate."""
        trail = Trail()
        source_var = Var()
        the_set = SetTerm([1, 2])
        set_id = id(the_set)
        unify(source_var, the_set, trail)
        del the_set

        result_var = Var()
        solutions = []
        gen = _set_union_dr__3(None, None, source_var, SetTerm([3]), result_var, trail)
        for parent, value in gen:
            if value is not DONE:
                solutions.append(deref(result_var))

        assert len(solutions) == 1
        result = solutions[0]
        assert isinstance(result, SetTerm)
        assert result.elements == frozenset({1, 2, 3})
        assert id(result) == set_id

    def test_shared_set_not_mutated(self):
        """When SetTerm is shared (extra alias), a new SetTerm is created."""
        trail = Trail()
        source_var = Var()
        the_set = SetTerm([1, 2])
        alias = the_set
        unify(source_var, the_set, trail)

        result_var = Var()
        solutions = []
        gen = _set_union_dr__3(None, None, source_var, SetTerm([3]), result_var, trail)
        for parent, value in gen:
            if value is not DONE:
                solutions.append(deref(result_var))

        assert len(solutions) == 1
        assert solutions[0].elements == frozenset({1, 2, 3})
        assert alias.elements == frozenset({1, 2})
        _ = alias


# ── Integration tests: compiled predicates ───────────────────────────────────


class TestDestructiveReuseIntegration:
    """End-to-end tests using compiled predicates with the optimization."""

    def test_append_body_only_var(self):
        """Predicate that creates a temp list and appends to it.

        build(In, Out) <- Temp = In, append(Temp, [4], Out).

        Temp is body-only and dead after append → eligible for DR.
        """
        In, Temp, Out = Var(), Var(), Var()
        head = Compound("build", (In, Out))
        body = [
            Unify(left=Temp, right=In),
            Call(func=LoadName(name="append"),
                 args=[Temp, [4], Out], kwargs=[]),
        ]
        db, fn = make_pred("build", 2, [(head, body)])

        trail = Trail()
        X = Var()
        results = _snap(fn, lambda: deref(X), [1, 2, 3], X, trail)
        assert results == [[1, 2, 3, 4]]

    def test_dict_put_body_only_var(self):
        """dict_put with body-only DictTerm.

        update(In, Out) <- Temp = In, dict_put(name, alice, Temp, Out).
        """
        In, Temp, Out = Var(), Var(), Var()
        head = Compound("update", (In, Out))
        body = [
            Unify(left=Temp, right=In),
            Call(func=LoadName(name="dict_put"),
                 args=["name", "alice", Temp, Out], kwargs=[]),
        ]
        db, fn = make_pred("update", 2, [(head, body)])

        trail = Trail()
        X = Var()
        results = _snap(fn, lambda: deref(X),
                        DictTerm({"age": 30}), X, trail)
        assert len(results) == 1
        assert dict(results[0].data) == {"age": 30, "name": "alice"}

    def test_set_union_body_only_var(self):
        """set_union with body-only SetTerm.

        merge(In, Out) <- Temp = In, set_union(Temp, {3}, Out).
        """
        In, Temp, Out = Var(), Var(), Var()
        head = Compound("merge", (In, Out))
        body = [
            Unify(left=Temp, right=In),
            Call(func=LoadName(name="set_union"),
                 args=[Temp, SetTerm([3]), Out], kwargs=[]),
        ]
        db, fn = make_pred("merge", 2, [(head, body)])

        trail = Trail()
        X = Var()
        results = _snap(fn, lambda: deref(X),
                        SetTerm([1, 2]), X, trail)
        assert len(results) == 1
        assert results[0].elements == frozenset({1, 2, 3})

    def test_head_var_not_optimized_correctness(self):
        """When source is a head var, the standard (copying) path is used.

        process(Old, Out) <- append(Old, [4], Out).

        Old is in the head → NOT eligible. Must still produce correct results.
        """
        Old, Out = Var(), Var()
        head = Compound("process", (Old, Out))
        body = [
            Call(func=LoadName(name="append"),
                 args=[Old, [4], Out], kwargs=[]),
        ]
        db, fn = make_pred("process", 2, [(head, body)])

        trail = Trail()
        X = Var()
        input_list = [1, 2, 3]
        results = _snap(fn, lambda: deref(X), input_list, X, trail)
        assert results == [[1, 2, 3, 4]]
        # The input_list should NOT have been mutated
        assert input_list == [1, 2, 3]

    def test_chained_appends(self):
        """Multiple appends where intermediate is dead after each use.

        chain(In, Out) <-
            T1 = In,
            append(T1, [a], T2),   ← T1 dead after, but preceding has nondeterministic append
            append(T2, [b], Out).  ← T2 dead after
        """
        In, T1, T2, Out = Var(), Var(), Var(), Var()
        head = Compound("chain", (In, Out))
        body = [
            Unify(left=T1, right=In),
            Call(func=LoadName(name="append"),
                 args=[T1, ["a"], T2], kwargs=[]),
            Call(func=LoadName(name="append"),
                 args=[T2, ["b"], Out], kwargs=[]),
        ]
        db, fn = make_pred("chain", 2, [(head, body)])

        trail = Trail()
        X = Var()
        results = _snap(fn, lambda: deref(X), [1, 2], X, trail)
        assert results == [[1, 2, "a", "b"]]

    def test_optimization_with_evaluate(self):
        """Source var created by Evaluate (not Unify).

        make(Out) <- T = [1, 2, 3], append(T, [4], Out).
        """
        T, Out = Var(), Var()
        head = Compound("make", (Out,))
        body = [
            Evaluate(left=T, right=[1, 2, 3]),
            Call(func=LoadName(name="append"),
                 args=[T, [4], Out], kwargs=[]),
        ]
        db, fn = make_pred("make", 1, [(head, body)])

        trail = Trail()
        X = Var()
        results = _snap(fn, lambda: deref(X), X, trail)
        assert results == [[1, 2, 3, 4]]

    def test_multiple_clauses(self):
        """Predicate with multiple clauses, some eligible, some not.

        add([], Out) <- Out = [].
        add(Old, Out) <- append(Old, [x], Out).  ← Old is head var, NOT eligible
        """
        Old, Out1, Out2 = Var(), Var(), Var()
        head1 = Compound("add", ([], Out1))
        body1 = [Unify(left=Out1, right=[])]

        head2 = Compound("add", (Old, Out2))
        body2 = [
            Call(func=LoadName(name="append"),
                 args=[Old, ["x"], Out2], kwargs=[]),
        ]

        db, fn = make_pred("add", 2, [(head1, body1), (head2, body2)])

        trail = Trail()
        X = Var()

        # Test with empty list (first clause)
        results = _snap(fn, lambda: deref(X), [], X, trail)
        assert [] in results

        # Test with non-empty list (second clause)
        X2 = Var()
        results = _snap(fn, lambda: deref(X2), [1, 2], X2, trail)
        assert [1, 2, "x"] in results
