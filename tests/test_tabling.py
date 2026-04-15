"""Tests for V2-4b: SLG tabling via trampoline suspension."""

import os
import sys
from dataclasses import dataclass
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
from clausal.logic.solve import call, _deref_walk
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
        # nv
        e = TableEntry()
        assert e.status == "evaluating"
        assert e.answers == []
        assert e.answer_set == set()
        assert e.suspended == []

    def test_add_answer_new(self):
        # nv
        e = TableEntry()
        assert e.add_answer((1, 2)) is True
        assert e.answers == [(1, 2)]
        assert (1, 2) in e.answer_set

    def test_add_answer_duplicate(self):
        # nv
        e = TableEntry()
        e.add_answer((1, 2))
        assert e.add_answer((1, 2)) is False
        assert len(e.answers) == 1

    def test_add_answer_preserves_order(self):
        # nv
        e = TableEntry()
        e.add_answer((1,))
        e.add_answer((2,))
        e.add_answer((3,))
        assert e.answers == [(1,), (2,), (3,)]


# ── Unit tests: key computation ───────────────────────────────────────────────


class TestKeyComputation:
    def test_ground_scalar(self):
        # nv
        assert _normalize_for_key(42) == 42
        assert _normalize_for_key("hello") == "hello"
        assert _normalize_for_key(True) is True
        assert _normalize_for_key(None) is None

    def test_unbound_var(self):
        # nv
        v = Var()
        assert _normalize_for_key(v) is _VAR

    def test_bound_var(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        assert _normalize_for_key(v) == 42

    def test_list(self):
        # nv
        result = _normalize_for_key([1, 2, 3])
        assert result == ("__list__", 1, 2, 3)

    def test_compound(self):
        # nv
        c = Compound("f", (1, 2))
        result = _normalize_for_key(c)
        assert result == ("f", 1, 2)

    def test_make_subgoal_key_ground(self):
        # nv
        trail = Trail()
        key = make_subgoal_key((1, "a"), trail)
        assert key == (1, "a")

    def test_make_subgoal_key_with_vars(self):
        # nv
        trail = Trail()
        v = Var()
        key = make_subgoal_key((1, v), trail)
        assert key == (1, _VAR)

    def test_variant_keys_match(self):
        # nv
        trail = Trail()
        k1 = make_subgoal_key((1, 2), trail)
        k2 = make_subgoal_key((1, 2), trail)
        assert k1 == k2

    def test_variant_keys_vars_match(self):
        # nv
        trail = Trail()
        k1 = make_subgoal_key((1, Var()), trail)
        k2 = make_subgoal_key((1, Var()), trail)
        assert k1 == k2


# ── Unit tests: answer freezing and unification ──────────────────────────────


class TestFreezeAndUnify:
    def test_freeze_ground(self):
        # nv
        trail = Trail()
        result = freeze_args((1, "hello"), trail)
        assert result == (1, "hello")

    def test_freeze_bound_var(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        result = freeze_args((v,), trail)
        assert result == (42,)

    def test_unify_answer_success(self):
        # nv
        v = Var()
        trail = Trail()
        result = _unify_answer((v,), (42,), trail)
        assert result is True
        assert deref(v) == 42

    def test_unify_answer_failure(self):
        # nv
        trail = Trail()
        result = _unify_answer((1,), (2,), trail)
        assert result is False


# ── Unit tests: @dataclass terms through C tabling path ──────────────────────


@dataclass
class Point:
    x: object
    y: object


@dataclass
class Nested:
    label: str
    child: object


class TestDataclassTerms:
    """Exercises _normalize_for_key, _deref_walk, make_subgoal_key,
    freeze_args, and _unify_answer with @dataclass term instances,
    ensuring the capsule's is_term_instance + term_field_names handles
    dataclasses correctly (not just PredicateMeta)."""

    def test_normalize_dataclass_ground(self):
        # nv
        p = Point(1, 2)
        result = _normalize_for_key(p)
        assert result == ("Point", 1, 2)

    def test_normalize_dataclass_with_var(self):
        # nv
        v = Var()
        p = Point(v, 42)
        result = _normalize_for_key(p)
        assert result == ("Point", _VAR, 42)

    def test_normalize_dataclass_with_bound_var(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, 99, trail)
        p = Point(v, 1)
        result = _normalize_for_key(p)
        assert result == ("Point", 99, 1)

    def test_normalize_nested_dataclass(self):
        # nv
        inner = Point(3, 4)
        outer = Nested("origin", inner)
        result = _normalize_for_key(outer)
        assert result == ("Nested", "origin", ("Point", 3, 4))

    def test_make_subgoal_key_dataclass(self):
        # nv
        trail = Trail()
        p = Point(1, 2)
        key = make_subgoal_key((p, "extra"), trail)
        assert key == (("Point", 1, 2), "extra")

    def test_make_subgoal_key_dataclass_with_var(self):
        # nv
        trail = Trail()
        v = Var()
        p = Point(v, 10)
        key = make_subgoal_key((p,), trail)
        assert key == (("Point", _VAR, 10),)

    def test_freeze_dataclass_ground(self):
        # nv
        trail = Trail()
        p = Point(1, 2)
        result = freeze_args((p,), trail)
        assert len(result) == 1
        assert isinstance(result[0], Point)
        assert result[0].x == 1
        assert result[0].y == 2

    def test_freeze_dataclass_with_bound_var(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        p = Point(v, 7)
        result = freeze_args((p,), trail)
        frozen = result[0]
        assert isinstance(frozen, Point)
        assert frozen.x == 42
        assert frozen.y == 7

    def test_deref_walk_dataclass_ground(self):
        # nv
        p = Point(1, 2)
        result = _deref_walk(p)
        assert isinstance(result, Point)
        assert result.x == 1
        assert result.y == 2

    def test_deref_walk_dataclass_with_bound_var(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, "hello", trail)
        p = Point(v, 3)
        result = _deref_walk(p)
        assert isinstance(result, Point)
        assert result.x == "hello"
        assert result.y == 3

    def test_deref_walk_nested_dataclass(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, 99, trail)
        inner = Point(v, 2)
        outer = Nested("test", inner)
        result = _deref_walk(outer)
        assert isinstance(result, Nested)
        assert result.label == "test"
        assert isinstance(result.child, Point)
        assert result.child.x == 99
        assert result.child.y == 2

    def test_unify_answer_dataclass(self):
        """_unify_answer unifies arg-by-arg, not the dataclass itself,
        so we test a Var that will be bound to a dataclass via freeze."""
        # nv
        v = Var()
        trail = Trail()
        p = Point(1, 2)
        result = _unify_answer((v,), (p,), trail)
        assert result is True
        assert deref(v) is p

    def test_variant_keys_dataclass_match(self):
        """Two calls with same-shape dataclass args (different Vars)
        must produce the same variant key."""
        # nv
        trail = Trail()
        k1 = make_subgoal_key((Point(Var(), 1),), trail)
        k2 = make_subgoal_key((Point(Var(), 1),), trail)
        assert k1 == k2

    def test_variant_keys_dataclass_differ(self):
        """Different ground field values must produce different keys."""
        # nv
        trail = Trail()
        k1 = make_subgoal_key((Point(1, 2),), trail)
        k2 = make_subgoal_key((Point(1, 3),), trail)
        assert k1 != k2


# ── Integration tests: tabled fibonacci ──────────────────────────────────────


class TestTabledFib:
    def test_fib_basic(self):
        # nv
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("Fib", 10, F, module=_module(m)):
            results.append(deref(F))
        assert results == [55]

    def test_fib_zero(self):
        # nv
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("Fib", 0, F, module=_module(m)):
            results.append(deref(F))
        assert results == [0]

    def test_fib_one(self):
        # nv
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("Fib", 1, F, module=_module(m)):
            results.append(deref(F))
        assert results == [1]

    def test_fib_cache_hit(self):
        """Second query should use cached table (COMPLETE path)."""
        # nv
        m = _load("tabled_fib")
        db = _module(m).db

        # First query
        F = Var()
        list(call("Fib", 5, F, module=_module(m)))
        assert len(db.table_store) > 0

        # Second query should hit cache
        F2 = Var()
        results = []
        for trail in call("Fib", 5, F2, module=_module(m)):
            results.append(deref(F2))
        assert results == [5]

    def test_fib_ground_query_success(self):
        """Fib(5, 5) should succeed."""
        # nv
        m = _load("tabled_fib")
        results = list(call("Fib", 5, 5, module=_module(m)))
        assert len(results) == 1

    def test_fib_ground_query_failure(self):
        """Fib(5, 6) should fail (5 != 6)."""
        # nv
        m = _load("tabled_fib")
        results = list(call("Fib", 5, 6, module=_module(m)))
        assert len(results) == 0


# ── Integration tests: tabled cyclic path ────────────────────────────────────


class TestTabledPath:
    def test_cyclic_path_terminates(self):
        """path/2 on a cyclic graph terminates with tabling."""
        # nv
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("Path", 1, X, module=_module(m)):
            results.add(deref(X))
        # From 1: can reach 2, 3, and 1 (via cycle)
        assert results == {1, 2, 3}

    def test_path_all_pairs(self):
        """All reachable pairs in cyclic graph."""
        # nv
        m = _load("tabled_path")
        X, Y = Var(), Var()
        results = set()
        for trail in call("Path", X, Y, module=_module(m)):
            results.add((deref(X), deref(Y)))
        expected = {(a, b) for a in [1, 2, 3] for b in [1, 2, 3]}
        assert results == expected

    def test_path_from_node_2(self):
        # nv
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("Path", 2, X, module=_module(m)):
            results.add(deref(X))
        assert results == {1, 2, 3}

    def test_path_from_node_3(self):
        # nv
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("Path", 3, X, module=_module(m)):
            results.add(deref(X))
        assert results == {1, 2, 3}

    def test_path_ground_true(self):
        # nv
        m = _load("tabled_path")
        results = list(call("Path", 1, 3, module=_module(m)))
        assert len(results) >= 1

    def test_path_ground_self(self):
        """path(1, 1) should succeed via the cycle."""
        # nv
        m = _load("tabled_path")
        results = list(call("Path", 1, 1, module=_module(m)))
        assert len(results) >= 1

    def test_table_entry_complete_after_query(self):
        """After a full query, table entries should be marked COMPLETE."""
        # nv
        m = _load("tabled_path")
        db = _module(m).db
        X = Var()
        list(call("Path", 1, X, module=_module(m)))
        for entry in db.table_store.values():
            assert entry.status == "complete"


# ── Database integration tests ───────────────────────────────────────────────


class TestDatabaseTabling:
    def test_table_store_property(self):
        # nv
        db = Database()
        assert db.table_store == {}
        assert db.table_store is db._table_store

    def test_abolish_table(self):
        # nv
        db = Database()
        db._table_store[("foo", 2, (1, _VAR))] = TableEntry()
        db._table_store[("foo", 2, (2, _VAR))] = TableEntry()
        db._table_store[("bar", 1, (1,))] = TableEntry()
        db.abolish_table("foo", 2)
        assert len(db._table_store) == 1
        assert ("bar", 1, (1,)) in db._table_store

    def test_abolish_all_tables(self):
        # nv
        db = Database()
        db._table_store[("foo", 2, (1,))] = TableEntry()
        db._table_store[("bar", 1, (1,))] = TableEntry()
        db.abolish_all_tables()
        assert db._table_store == {}

    def test_assertz_auto_invalidates_tabled(self):
        # nv
        db = Database()
        db.mark_tabled("foo", 1)
        db._table_store[("foo", 1, (1,))] = TableEntry()
        db.assertz(Clause(head=Compound("foo", (99,)), body=[]))
        assert len(db._table_store) == 0

    def test_retract_auto_invalidates_tabled(self):
        # nv
        db = Database()
        db.mark_tabled("foo", 1)
        head = Compound("foo", (1,))
        db.assertz(Clause(head=head, body=[]))
        db._table_store[("foo", 1, (1,))] = TableEntry()
        db.retract(head)
        assert len(db._table_store) == 0

    def test_assertz_non_tabled_no_invalidation(self):
        # nv
        db = Database()
        db._table_store[("bar", 1, (1,))] = TableEntry()
        db.assertz(Clause(head=Compound("foo", (1,)), body=[]))
        assert len(db._table_store) == 1


# ── Import hook integration ──────────────────────────────────────────────────


class TestImportHookTabling:
    def test_tabled_directive_sets_metadata(self):
        # nv
        m = _load("tabled_fib")
        db = _module(m).db
        assert db.is_tabled("Fib", 2)

    def test_tabled_predicate_wrapped(self):
        # nv
        m = _load("tabled_path")
        db = _module(m).db
        assert db.is_tabled("Path", 2)
        assert not db.is_tabled("Edge", 2)

    def test_non_tabled_predicate_still_works(self):
        # nv
        m = _load("tabled_path")
        X = Var()
        results = []
        for trail in call("Edge", 1, X, module=_module(m)):
            results.append(deref(X))
        assert sorted(results) == [2]


# ── Abolish table integration ────────────────────────────────────────────────


class TestAbolishTable:
    def test_abolish_recomputes(self):
        """After abolish_table, next query recomputes from scratch."""
        # nv
        m = _load("tabled_fib")
        db = _module(m).db

        F = Var()
        list(call("Fib", 5, F, module=_module(m)))
        assert len(db.table_store) > 0

        db.abolish_all_tables()
        assert len(db.table_store) == 0

        F2 = Var()
        results = []
        for trail in call("Fib", 5, F2, module=_module(m)):
            results.append(deref(F2))
        assert results == [5]
        assert len(db.table_store) > 0


# ── Multiple tabled predicates ───────────────────────────────────────────────


class TestMultipleTabled:
    def test_two_tabled_predicates(self):
        # nv
        fixture = os.path.join(FIXTURES, "_test_multi_tabled.clausal")
        with open(fixture, "w") as f:
            f.write("""-table(Anc/2)
-table(Desc/2)

Parent(1, 2),
Parent(2, 3),
Parent(3, 4),

Anc(X, Y) <- Parent(X, Y)
Anc(X, Y) <- (
    Parent(X, Z),
    Anc(Z, Y)
)

Desc(X, Y) <- Anc(Y, X)
""")
        try:
            from clausal.import_hook import _load_module
            m = _load_module("_test_multi_tabled", fixture)
            lm = _module(m)
            assert lm.db.is_tabled("Anc", 2)
            assert lm.db.is_tabled("Desc", 2)

            # Test Anc: ancestors of 1 are 2, 3, 4
            Y = Var()
            results = set()
            for trail in call("Anc", 1, Y, module=lm):
                results.add(deref(Y))
            assert results == {2, 3, 4}

            # Test Desc: descendants of 4 are 1, 2, 3
            X = Var()
            results = set()
            for trail in call("Desc", 4, X, module=lm):
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
        # nv
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
        # nv
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
        # nv
        table_store = {}

        def my_pred(this_gen, _proceed, _fail, _catcher, arg0, trail):
            mark = trail.mark()
            if unify(arg0, 42, trail):
                yield (_proceed, None)
            trail.undo(mark)
            yield (_fail, DONE)

        wrapped = make_tabled_wrapper_trampoline(my_pred, "my_pred", 1, table_store)

        trail = Trail()
        X = Var()
        root = StepGenerator(wrapped, None, None, None, X, trail)
        # Use snapshot to capture binding while it's live (solutions() collects a list)
        results = solutions(root, snapshot=lambda: deref(X))
        assert results == [42]

        assert len(table_store) == 1
        entry = list(table_store.values())[0]
        assert entry.status == "complete"

    def test_trampoline_wrapper_multiple_answers(self):
        # nv
        table_store = {}

        def my_pred(this_gen, _proceed, _fail, _catcher, arg0, trail):
            mark = trail.mark()
            if unify(arg0, 1, trail):
                yield (_proceed, None)
            trail.undo(mark)
            mark = trail.mark()
            if unify(arg0, 2, trail):
                yield (_proceed, None)
            trail.undo(mark)
            yield (_fail, DONE)

        wrapped = make_tabled_wrapper_trampoline(my_pred, "my_pred", 1, table_store)

        trail = Trail()
        X = Var()
        root = StepGenerator(wrapped, None, None, None, X, trail)
        results = solutions(root, snapshot=lambda: deref(X))
        assert sorted(results) == [1, 2]

    def test_trampoline_to_simple_adapter(self):
        # nv
        table_store = {}

        def my_pred(this_gen, _proceed, _fail, _catcher, arg0, trail):
            mark = trail.mark()
            if unify(arg0, 1, trail):
                yield (_proceed, None)
            trail.undo(mark)
            mark = trail.mark()
            if unify(arg0, 2, trail):
                yield (_proceed, None)
            trail.undo(mark)
            yield (_fail, DONE)

        wrapped_trampoline = make_tabled_wrapper_trampoline(
            my_pred, "my_pred", 1, table_store)
        adapted = _trampoline_to_simple_adapter(wrapped_trampoline, 1)

        trail = Trail()
        X = Var()
        results = []
        for _ in adapted(X, trail, None):
            results.append(deref(X))
        assert sorted(results) == [1, 2]
