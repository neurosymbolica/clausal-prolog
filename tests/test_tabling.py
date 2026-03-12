"""Tests for V2-4b: SLG tabling via trampoline suspension."""

import os
import sys
import pytest

from clausal.logic.tabling import (
    TableEntry,
    SuspendedConsumer,
    _VAR,
    _TABLING_SUSPEND,
    _TABLING_RESUME,
    _normalize_for_key,
    make_subgoal_key,
    freeze_args,
    _unify_answer,
    make_tabled_wrapper_simple,
    make_tabled_wrapper_trampoline,
    _trampoline_to_simple_adapter,
)
from clausal.logic.variables import Var, Trail, unify, deref, is_var
from clausal.logic.database import Database, Clause, Module, head_key
from clausal.logic.trampoline import StepGenerator, DONE, solutions
from clausal.logic.solve import call
from clausal.logic.predicate import PredicateMeta
from clausal.terms import Compound


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    from clausal.import_hook import _load_module
    return _load_module(name, os.path.join(FIXTURES, f"{name}.clausal"))


def _module(mod):
    return mod.__dict__["$module"]


# ── Unit tests: TableEntry ────────────────────────────────────────────────────


class TestTableEntry:
    def test_initial_state(self):
        e = TableEntry()
        assert e.status == "evaluating"
        assert e.answers == []
        assert e.answer_set == set()
        assert e.suspended == []

    def test_add_answer_new(self):
        e = TableEntry()
        assert e.add_answer((1, 2)) is True
        assert e.answers == [(1, 2)]
        assert (1, 2) in e.answer_set

    def test_add_answer_duplicate(self):
        e = TableEntry()
        e.add_answer((1, 2))
        assert e.add_answer((1, 2)) is False
        assert len(e.answers) == 1

    def test_add_answer_preserves_order(self):
        e = TableEntry()
        e.add_answer((1,))
        e.add_answer((2,))
        e.add_answer((3,))
        assert e.answers == [(1,), (2,), (3,)]


# ── Unit tests: key computation ───────────────────────────────────────────────


class TestKeyComputation:
    def test_ground_scalar(self):
        assert _normalize_for_key(42) == 42
        assert _normalize_for_key("hello") == "hello"
        assert _normalize_for_key(True) is True
        assert _normalize_for_key(None) is None

    def test_unbound_var(self):
        v = Var()
        assert _normalize_for_key(v) is _VAR

    def test_bound_var(self):
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        assert _normalize_for_key(v) == 42

    def test_list(self):
        result = _normalize_for_key([1, 2, 3])
        assert result == ("__list__", 1, 2, 3)

    def test_compound(self):
        c = Compound("f", (1, 2))
        result = _normalize_for_key(c)
        assert result == ("f", 1, 2)

    def test_make_subgoal_key_ground(self):
        trail = Trail()
        key = make_subgoal_key((1, "a"), trail)
        assert key == (1, "a")

    def test_make_subgoal_key_with_vars(self):
        trail = Trail()
        v = Var()
        key = make_subgoal_key((1, v), trail)
        assert key == (1, _VAR)

    def test_variant_keys_match(self):
        trail = Trail()
        k1 = make_subgoal_key((1, 2), trail)
        k2 = make_subgoal_key((1, 2), trail)
        assert k1 == k2

    def test_variant_keys_vars_match(self):
        trail = Trail()
        k1 = make_subgoal_key((1, Var()), trail)
        k2 = make_subgoal_key((1, Var()), trail)
        assert k1 == k2


# ── Unit tests: answer freezing and unification ──────────────────────────────


class TestFreezeAndUnify:
    def test_freeze_ground(self):
        trail = Trail()
        result = freeze_args((1, "hello"), trail)
        assert result == (1, "hello")

    def test_freeze_bound_var(self):
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        result = freeze_args((v,), trail)
        assert result == (42,)

    def test_unify_answer_success(self):
        v = Var()
        trail = Trail()
        result = _unify_answer((v,), (42,), trail)
        assert result is True
        assert deref(v) == 42

    def test_unify_answer_failure(self):
        trail = Trail()
        result = _unify_answer((1,), (2,), trail)
        assert result is False


# ── Integration tests: tabled fibonacci ──────────────────────────────────────


class TestTabledFib:
    def test_fib_basic(self):
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("fib", 10, F, module=_module(m)):
            results.append(deref(F))
        assert results == [55]

    def test_fib_zero(self):
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("fib", 0, F, module=_module(m)):
            results.append(deref(F))
        assert results == [0]

    def test_fib_one(self):
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("fib", 1, F, module=_module(m)):
            results.append(deref(F))
        assert results == [1]

    def test_fib_cache_hit(self):
        """Second query should use cached table (COMPLETE path)."""
        m = _load("tabled_fib")
        db = _module(m).db

        # First query
        F = Var()
        list(call("fib", 5, F, module=_module(m)))
        assert len(db.table_store) > 0

        # Second query should hit cache
        F2 = Var()
        results = []
        for trail in call("fib", 5, F2, module=_module(m)):
            results.append(deref(F2))
        assert results == [5]

    def test_fib_ground_query_success(self):
        """fib(5, 5) should succeed."""
        m = _load("tabled_fib")
        results = list(call("fib", 5, 5, module=_module(m)))
        assert len(results) == 1

    def test_fib_ground_query_failure(self):
        """fib(5, 6) should fail (5 != 6)."""
        m = _load("tabled_fib")
        results = list(call("fib", 5, 6, module=_module(m)))
        assert len(results) == 0


# ── Integration tests: tabled cyclic path ────────────────────────────────────


class TestTabledPath:
    def test_cyclic_path_terminates(self):
        """path/2 on a cyclic graph terminates with tabling."""
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("path", 1, X, module=_module(m)):
            results.add(deref(X))
        # From 1: can reach 2, 3, and 1 (via cycle)
        assert results == {1, 2, 3}

    def test_path_all_pairs(self):
        """All reachable pairs in cyclic graph."""
        m = _load("tabled_path")
        X, Y = Var(), Var()
        results = set()
        for trail in call("path", X, Y, module=_module(m)):
            results.add((deref(X), deref(Y)))
        expected = {(a, b) for a in [1, 2, 3] for b in [1, 2, 3]}
        assert results == expected

    def test_path_from_node_2(self):
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("path", 2, X, module=_module(m)):
            results.add(deref(X))
        assert results == {1, 2, 3}

    def test_path_from_node_3(self):
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("path", 3, X, module=_module(m)):
            results.add(deref(X))
        assert results == {1, 2, 3}

    def test_path_ground_true(self):
        m = _load("tabled_path")
        results = list(call("path", 1, 3, module=_module(m)))
        assert len(results) >= 1

    def test_path_ground_self(self):
        """path(1, 1) should succeed via the cycle."""
        m = _load("tabled_path")
        results = list(call("path", 1, 1, module=_module(m)))
        assert len(results) >= 1

    def test_table_entry_complete_after_query(self):
        """After a full query, table entries should be marked COMPLETE."""
        m = _load("tabled_path")
        db = _module(m).db
        X = Var()
        list(call("path", 1, X, module=_module(m)))
        for entry in db.table_store.values():
            assert entry.status == "complete"


# ── Database integration tests ───────────────────────────────────────────────


class TestDatabaseTabling:
    def test_table_store_property(self):
        db = Database()
        assert db.table_store == {}
        assert db.table_store is db._table_store

    def test_abolish_table(self):
        db = Database()
        db._table_store[("foo", 2, (1, _VAR))] = TableEntry()
        db._table_store[("foo", 2, (2, _VAR))] = TableEntry()
        db._table_store[("bar", 1, (1,))] = TableEntry()
        db.abolish_table("foo", 2)
        assert len(db._table_store) == 1
        assert ("bar", 1, (1,)) in db._table_store

    def test_abolish_all_tables(self):
        db = Database()
        db._table_store[("foo", 2, (1,))] = TableEntry()
        db._table_store[("bar", 1, (1,))] = TableEntry()
        db.abolish_all_tables()
        assert db._table_store == {}

    def test_assertz_auto_invalidates_tabled(self):
        db = Database()
        db.mark_tabled("foo", 1)
        db._table_store[("foo", 1, (1,))] = TableEntry()
        db.assertz(Clause(head=Compound("foo", (99,)), body=[]))
        assert len(db._table_store) == 0

    def test_retract_auto_invalidates_tabled(self):
        db = Database()
        db.mark_tabled("foo", 1)
        head = Compound("foo", (1,))
        db.assertz(Clause(head=head, body=[]))
        db._table_store[("foo", 1, (1,))] = TableEntry()
        db.retract(head)
        assert len(db._table_store) == 0

    def test_assertz_non_tabled_no_invalidation(self):
        db = Database()
        db._table_store[("bar", 1, (1,))] = TableEntry()
        db.assertz(Clause(head=Compound("foo", (1,)), body=[]))
        assert len(db._table_store) == 1


# ── Import hook integration ──────────────────────────────────────────────────


class TestImportHookTabling:
    def test_tabled_directive_sets_metadata(self):
        m = _load("tabled_fib")
        db = _module(m).db
        assert db.is_tabled("fib", 2)

    def test_tabled_predicate_wrapped(self):
        m = _load("tabled_path")
        db = _module(m).db
        assert db.is_tabled("path", 2)
        assert not db.is_tabled("edge", 2)

    def test_non_tabled_predicate_still_works(self):
        m = _load("tabled_path")
        X = Var()
        results = []
        for trail in call("edge", 1, X, module=_module(m)):
            results.append(deref(X))
        assert sorted(results) == [2]


# ── Abolish table integration ────────────────────────────────────────────────


class TestAbolishTable:
    def test_abolish_recomputes(self):
        """After abolish_table, next query recomputes from scratch."""
        m = _load("tabled_fib")
        db = _module(m).db

        F = Var()
        list(call("fib", 5, F, module=_module(m)))
        assert len(db.table_store) > 0

        db.abolish_all_tables()
        assert len(db.table_store) == 0

        F2 = Var()
        results = []
        for trail in call("fib", 5, F2, module=_module(m)):
            results.append(deref(F2))
        assert results == [5]
        assert len(db.table_store) > 0


# ── Multiple tabled predicates ───────────────────────────────────────────────


class TestMultipleTabled:
    def test_two_tabled_predicates(self):
        fixture = os.path.join(FIXTURES, "_test_multi_tabled.clausal")
        with open(fixture, "w") as f:
            f.write("""-table(anc/2)
-table(desc/2)

parent(1, 2),
parent(2, 3),
parent(3, 4),

anc(X, Y) <- parent(X, Y)
anc(X, Y) <- (
    parent(X, Z),
    anc(Z, Y)
)

desc(X, Y) <- anc(Y, X)
""")
        try:
            from clausal.import_hook import _load_module
            m = _load_module("_test_multi_tabled", fixture)
            lm = _module(m)
            assert lm.db.is_tabled("anc", 2)
            assert lm.db.is_tabled("desc", 2)

            # Test anc: ancestors of 1 are 2, 3, 4
            Y = Var()
            results = set()
            for trail in call("anc", 1, Y, module=lm):
                results.add(deref(Y))
            assert results == {2, 3, 4}

            # Test desc: descendants of 4 are 1, 2, 3
            X = Var()
            results = set()
            for trail in call("desc", 4, X, module=lm):
                results.add(deref(X))
            assert results == {1, 2, 3}
        finally:
            os.unlink(fixture)
            pycache = os.path.join(FIXTURES, "__pycache__")
            if os.path.isdir(pycache):
                for fn in os.listdir(pycache):
                    if fn.startswith("_test_multi_tabled"):
                        os.unlink(os.path.join(pycache, fn))


# ── Unit tests: tabling wrapper (direct) ─────────────────────────────────────


class TestTabledWrapperDirect:
    def test_simple_wrapper_basic(self):
        table_store = {}
        trail = Trail()

        def my_pred(arg0, trail, k):
            mark = trail.mark()
            if unify(arg0, 1, trail):
                yield None
            trail.undo(mark)
            mark = trail.mark()
            if unify(arg0, 2, trail):
                yield None
            trail.undo(mark)

        wrapped = make_tabled_wrapper_simple(my_pred, "my_pred", 1, table_store)

        X = Var()
        results = []
        for _ in wrapped(X, trail, None):
            results.append(deref(X))
        assert sorted(results) == [1, 2]

        assert len(table_store) == 1
        entry = list(table_store.values())[0]
        assert entry.status == "complete"
        assert len(entry.answers) == 2

    def test_simple_wrapper_cache_hit(self):
        table_store = {}

        call_count = 0
        def my_pred(arg0, trail, k):
            nonlocal call_count
            call_count += 1
            mark = trail.mark()
            if unify(arg0, 42, trail):
                yield None
            trail.undo(mark)

        wrapped = make_tabled_wrapper_simple(my_pred, "my_pred", 1, table_store)

        trail = Trail()
        X = Var()
        list(wrapped(X, trail, None))
        first_count = call_count

        trail2 = Trail()
        X2 = Var()
        results = []
        for _ in wrapped(X2, trail2, None):
            results.append(deref(X2))
        assert results == [42]
        assert call_count == first_count

    def test_trampoline_wrapper_basic(self):
        table_store = {}

        def my_pred(this_gen, parent, arg0, trail):
            mark = trail.mark()
            if unify(arg0, 42, trail):
                yield (parent, None)
            trail.undo(mark)
            yield (parent, DONE)

        wrapped = make_tabled_wrapper_trampoline(my_pred, "my_pred", 1, table_store)

        trail = Trail()
        X = Var()
        root = StepGenerator(wrapped, None, X, trail)
        # Use snapshot to capture binding while it's live (solutions() collects a list)
        results = solutions(root, snapshot=lambda: deref(X))
        assert results == [42]

        assert len(table_store) == 1
        entry = list(table_store.values())[0]
        assert entry.status == "complete"

    def test_trampoline_wrapper_multiple_answers(self):
        table_store = {}

        def my_pred(this_gen, parent, arg0, trail):
            mark = trail.mark()
            if unify(arg0, 1, trail):
                yield (parent, None)
            trail.undo(mark)
            mark = trail.mark()
            if unify(arg0, 2, trail):
                yield (parent, None)
            trail.undo(mark)
            yield (parent, DONE)

        wrapped = make_tabled_wrapper_trampoline(my_pred, "my_pred", 1, table_store)

        trail = Trail()
        X = Var()
        root = StepGenerator(wrapped, None, X, trail)
        results = solutions(root, snapshot=lambda: deref(X))
        assert sorted(results) == [1, 2]

    def test_trampoline_to_simple_adapter(self):
        table_store = {}

        def my_pred(this_gen, parent, arg0, trail):
            mark = trail.mark()
            if unify(arg0, 1, trail):
                yield (parent, None)
            trail.undo(mark)
            mark = trail.mark()
            if unify(arg0, 2, trail):
                yield (parent, None)
            trail.undo(mark)
            yield (parent, DONE)

        wrapped_trampoline = make_tabled_wrapper_trampoline(
            my_pred, "my_pred", 1, table_store)
        adapted = _trampoline_to_simple_adapter(wrapped_trampoline, 1)

        trail = Trail()
        X = Var()
        results = []
        for _ in adapted(X, trail, None):
            results.append(deref(X))
        assert sorted(results) == [1, 2]
