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
from tests._suffix import SEAM, seam_path


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    from clausal.import_hook import _load_module
    return _load_module(name, seam_path(os.path.join(FIXTURES, f"{name}.clausal")))


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
        assert e.add_answer((1, 2)) == 0    # the new row's index
        assert e.answers == [(1, 2)]
        assert (1, 2) in e.answer_set

    def test_add_answer_duplicate(self):
        # nv
        e = TableEntry()
        e.add_answer((1, 2))
        assert e.add_answer((1, 2)) is None
        assert len(e.answers) == 1

    def test_add_answer_preserves_order(self):
        # nv
        e = TableEntry()
        e.add_answer((1,))
        e.add_answer((2,))
        e.add_answer((3,))
        assert e.answers == [(1,), (2,), (3,)]


# ── Task 4: cell interning at the add_answer freeze boundary ─────────────────


class TestAddAnswerCellInterning:
    """``TableEntry.add_answer`` is the single Python funnel every frozen
    tabled answer passes through, regardless of whether ``freeze_args``
    resolved to the pure-Python fallback or the C twin (both freeze a cell
    as a plain tuple either way -- see ``clausal.logic.tabling.add_answer``'s
    docstring, Task 4 of the Phase 2 bridge plan). These tests exercise the
    interning hook installed there, gated by ``cells.is_intern_enabled()``.
    """

    @pytest.fixture(autouse=True)
    def _clean(self):
        from clausal.logic.cells import clear_intern_table, set_intern_enabled
        clear_intern_table()
        set_intern_enabled(False)
        yield
        clear_intern_table()
        set_intern_enabled(False)

    def test_two_structurally_equal_ground_cell_answers_are_the_same_object(self):
        # nv -- the headline proof required by the task brief: with
        # interning enabled, two DIFFERENT TableEntry rows (as two
        # subgoals of the same or different tabled predicates would each
        # produce) that store structurally-equal ground cell answers end up
        # holding the identical object, not merely equal tuples.
        from clausal.logic.cells import make_cell, set_intern_enabled

        set_intern_enabled(True)
        e1 = TableEntry()
        e2 = TableEntry()
        c1 = make_cell("point", 1, 2)
        c2 = make_cell("point", 1, 2)
        assert c1 is not c2

        e1.add_answer((c1,))
        e2.add_answer((c2,))

        assert e1.answers[0][0] == e2.answers[0][0]
        assert e1.answers[0][0] is e2.answers[0][0]

    def test_interning_disabled_by_default_leaves_cell_answers_distinct(self):
        # nv -- DEFAULT-PATH INVARIANT at the hook itself: with the switch
        # at its default (OFF), two structurally-equal cell answers stored
        # in two entries remain the two DISTINCT objects that were passed
        # in -- add_answer does not even look at cells.is_cell without the
        # switch on.
        from clausal.logic.cells import make_cell, is_intern_enabled

        assert is_intern_enabled() is False
        e1 = TableEntry()
        e2 = TableEntry()
        c1 = make_cell("point", 1, 2)
        c2 = make_cell("point", 1, 2)

        e1.add_answer((c1,))
        e2.add_answer((c2,))

        assert e1.answers[0][0] is c1
        assert e2.answers[0][0] is c2
        assert e1.answers[0][0] is not e2.answers[0][0]

    def test_class_term_answers_are_byte_identical_with_interning_enabled(self):
        # nv -- regression test: class-term (non-cell) answers are
        # completely unaffected by the interning switch -- same object
        # identity, same dedup behavior, whether the switch is on or off.
        # This is the "class terms and non-cell values never touch the
        # intern table" half of the Global Constraints.
        from clausal.logic.cells import set_intern_enabled

        @dataclass
        class Pt:
            x: object
            y: object

        set_intern_enabled(True)
        e = TableEntry()
        p1 = Pt(1, 2)
        p2 = Pt(1, 2)  # a distinct, but "equal" (dataclass __eq__), instance
        assert e.add_answer((p1,)) == 0
        assert e.answers == [(p1,)]
        assert e.answers[0][0] is p1  # untouched -- never passed to intern_cell

        # A second, distinct-but-equal instance is still a NEW answer row
        # (dataclasses are not deduped by interning -- add_answer's own
        # variant-key dedup is the only thing that would collapse them, and
        # it uses value equality, independent of this hook).
        set_intern_enabled(False)
        e2 = TableEntry()
        assert e2.add_answer((p1,)) == 0
        assert e2.add_answer((p2,)) is None  # value-equal dataclass: dedup'd
        assert e2.answers == [(p1,)]

    def test_mixed_cell_and_scalar_answer_only_the_cell_slot_is_interned(self):
        # nv -- a per-arg gate: only the cell-shaped slot(s) of a
        # multi-arg answer go through intern_cell; a scalar sibling arg is
        # passed through completely unchanged.
        from clausal.logic.cells import make_cell, set_intern_enabled

        set_intern_enabled(True)
        e1 = TableEntry()
        e2 = TableEntry()
        c1 = make_cell("point", 1, 2)
        c2 = make_cell("point", 1, 2)

        e1.add_answer((99, c1))
        e2.add_answer((99, c2))

        assert e1.answers[0][0] == 99 == e2.answers[0][0]
        assert e1.answers[0][1] is e2.answers[0][1]

    def test_a_ground_cell_answer_still_tables(self):
        # nv (P3-2 Task 5 regression): the §1b slot-0 narrowing (Var
        # functors deprecated) does not touch str/TUPLE_TAG cells at all --
        # a ground str-functor cell answer still dedups and interns exactly
        # as before. Guards against a narrowing regression accidentally
        # widening ``is_cell``'s exclusions past Var functors.
        from clausal.logic.cells import make_cell, set_intern_enabled

        set_intern_enabled(True)
        e1 = TableEntry()
        e2 = TableEntry()
        c1 = make_cell("cons", 1, "nil")
        c2 = make_cell("cons", 1, "nil")
        assert c1 is not c2

        assert e1.add_answer((c1,)) == 0
        assert e2.add_answer((c2,)) == 0
        assert e1.answers[0][0] is e2.answers[0][0]  # interned to one object

    def test_a_var_functor_tuple_answer_no_longer_reaches_intern_cell(self):
        # nv (P3-2 Task 5, §1b): a Var-functor tuple is DEPRECATED as a
        # cell -- ``is_cell`` now reads slot 0 raw and answers False for
        # it, so ``add_answer``'s ``intern_cell(a) if is_cell(a) else a``
        # gate takes the "else" branch: the tuple is passed straight
        # through UNTOUCHED, the same as any other non-cell value (a class
        # term, scalar, ...). It never reaches ``intern_cell`` -- and
        # because ``intern_cell`` itself now also short-circuits on
        # ``is_cell`` before touching the table (see
        # ``tests/test_cells.py::TestInternCell::
        # test_var_functor_tuple_is_not_a_cell_so_never_reaches_the_intern_walk``),
        # this is true from either direction: the gate here never calls
        # it, and it would have been a no-op even if it had.
        from clausal.logic.cells import (
            is_cell, is_intern_enabled, set_intern_enabled,
        )

        set_intern_enabled(True)
        f = Var()
        c1 = (f, 1, 2)  # a raw tuple -- NOT built via make_cell, not a cell
        assert is_cell(c1) is False
        e = TableEntry()

        assert e.add_answer((c1,)) == 0
        assert e.answers[0][0] is c1  # untouched -- never passed to intern_cell
        assert is_intern_enabled() is True  # sanity: the switch really was on


# ── Unit tests: key computation ───────────────────────────────────────────────


class TestKeyComputation:
    def test_ground_scalar(self):
        # nv
        assert _normalize_for_key(42) == 42            # exact int stays canonical
        assert _normalize_for_key("hello") == "hello"
        # A04-F006: numeric leaves are type-tagged so 1/True/1.0 do not conflate
        assert _normalize_for_key(True) == "true"   # D35: a truth ATOM keys as its spelling, never as the int
        assert _normalize_for_key(1.0) == (float, 1.0)
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
        result = _normalize_for_key([1, 2, 300])
        assert result == ("__list__", 1, 2, 300)
        # [1, 2, 3] is a code list -- the term b"\x01\x02\x03" -- so it keys
        # as those bytes (test_tabling_char_and_code_list_key.py).

    def test_compound(self):
        # nv
        # A compound term is the cell ("f", 1, 2); it keys as that tuple.
        assert _normalize_for_key(("f", 1, 2)) == ("__tuple__", "f", 1, 2)

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
        for trail in call("fib", 10, F, module=_module(m)):
            results.append(deref(F))
        assert results == [55]

    def test_fib_zero(self):
        # nv
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("fib", 0, F, module=_module(m)):
            results.append(deref(F))
        assert results == [0]

    def test_fib_one(self):
        # nv
        m = _load("tabled_fib")
        F = Var()
        results = []
        for trail in call("fib", 1, F, module=_module(m)):
            results.append(deref(F))
        assert results == [1]

    def test_fib_cache_hit(self):
        """Second query should use cached table (COMPLETE path)."""
        # nv
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
        # nv
        m = _load("tabled_fib")
        results = list(call("fib", 5, 5, module=_module(m)))
        assert len(results) == 1

    def test_fib_ground_query_failure(self):
        """fib(5, 6) should fail (5 != 6)."""
        # nv
        m = _load("tabled_fib")
        results = list(call("fib", 5, 6, module=_module(m)))
        assert len(results) == 0


# ── Integration tests: tabled compound-chain answers ─────────────────────────
#
# struct_tabling.seam's Nats/2 is bench_struct_tabling's fixture (see
# benchmarks/workloads.py) -- a tabled predicate whose answers are cons/nil
# chains, not scalars.  Unlike TestTabledFib above (which safely lets
# `for trail in call(...)` run to natural exhaustion, since a scalar answer
# is captured by value the instant `deref` is called), these tests `break`
# immediately after the first solution: abandoning the generator early is
# what forces the *next* fresh call to recompute from scratch instead of
# hitting the COMPLETE fast path (test_nats_break_drops_table below verifies
# an abandoned-via-break query leaves ``db.table_store`` empty; a query
# drained via ``list(...)`` leaves the table intact instead, per
# test_nats_cache_hit below -- see task-4-report.md for the timings this
# produces). Reading a nested
# field (``node.T``) off a compound answer *before* the generator is
# abandoned/exhausted is required for the same reason bench_qsort/
# bench_tabling break after the first answer: continuing to iterate a
# deterministic predicate's generator past its one solution backtracks the
# trail looking for a next answer that doesn't exist, which can unbind
# nested chain variables the top-level `deref` never reached.


class TestStructTabling:
    def test_nats_zero(self):
        # nv
        m = _load("struct_tabling")
        L = Var()
        results = []
        for trail in call("nats", 0, L, module=_module(m)):
            results.append(deref(L))
            break
        assert results == [m.nil]

    def test_nats_chain_shape(self):
        """nats(3, L) builds cons(3, cons(2, cons(1, nil))) -- one answer."""
        # nv
        m = _load("struct_tabling")
        L = Var()
        results = []
        for trail in call("nats", 3, L, module=_module(m)):
            results.append(deref(L))
            break
        node = results[0]
        values = []
        # P3-2 Task 2 (THE FLIP, R6): ``cons`` is a data functor, so a chain
        # link is the cell ``("cons", H, T)`` -- slots, not attributes.
        while node != m.nil:
            values.append(node[1])
            node = deref(node[2])
        assert values == [3, 2, 1]

    def test_nats_open_query_determinism(self):
        """nats/2 is functionally deterministic: an OPEN query (L unbound)
        drained to exhaustion (no break) must yield exactly one solution.
        This is the property bench_struct_tabling's break-after-first shape
        relies on. test_nats_chain_shape's break-based check can't assert
        it -- len(results) there would be trivially 1 after any break,
        whether or not a second solution exists -- so it's asserted here
        instead, with a full drain at a small n (safe: no nested-field
        access after the drain, so the backtrack-driven unbinding the
        module comment above warns about doesn't matter here)."""
        # nv
        m = _load("struct_tabling")
        L = Var()
        results = list(call("nats", 3, L, module=_module(m)))
        assert len(results) == 1

    def test_nats_break_drops_table(self):
        """Verifies the module comment's claim above: abandoning the
        generator via break (instead of draining it) leaves
        db.table_store empty afterward -- unlike a full drain, which
        leaves it populated (test_nats_cache_hit below). This is why
        bench_struct_tabling must reload the module every rep instead of
        relying on break alone to force recomputation."""
        # nv
        m = _load("struct_tabling")
        db = _module(m).db
        L = Var()
        for trail in call("nats", 5, L, module=_module(m)):
            deref(L)
            break
        assert len(db.table_store) == 0

    def test_nats_cache_hit(self):
        """Second query should use cached table (COMPLETE path), same as
        TestTabledFib.test_fib_cache_hit above. The first query is drained
        via list(...) (not break) so the table survives for the second
        query to hit -- see the module comment above."""
        # nv
        m = _load("struct_tabling")
        db = _module(m).db

        L = Var()
        list(call("nats", 5, L, module=_module(m)))
        assert len(db.table_store) > 0

        L2 = Var()
        results = []
        for trail in call("nats", 5, L2, module=_module(m)):
            results.append(deref(L2))
            break
        assert len(results) == 1
        node = results[0]
        length = 0
        # R6: cell slots, as in test_nats_chain_shape above.
        while node != m.nil:
            length += 1
            node = deref(node[2])
        assert length == 5

    def test_nats_ground_query_success(self):
        """nats(3, cons(3, cons(2, cons(1, nil)))) should succeed."""
        # nv
        m = _load("struct_tabling")
        # R6: the caller hands in the CELL chain the module's clauses build.
        chain = ("cons", 3, ("cons", 2, ("cons", 1, m.nil)))
        results = list(call("nats", 3, chain, module=_module(m)))
        assert len(results) == 1

    def test_nats_ground_query_failure(self):
        """nats(3, cons(99, ...)) should fail (wrong head value)."""
        # nv
        m = _load("struct_tabling")
        # R6: cell chain, as in the success twin above.
        chain = ("cons", 99, ("cons", 2, ("cons", 1, m.nil)))
        results = list(call("nats", 3, chain, module=_module(m)))
        assert len(results) == 0


# ── Integration tests: tabled cyclic path ────────────────────────────────────


class TestTabledPath:
    def test_cyclic_path_terminates(self):
        """path/2 on a cyclic graph terminates with tabling."""
        # nv
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("path", 1, X, module=_module(m)):
            results.add(deref(X))
        # From 1: can reach 2, 3, and 1 (via cycle)
        assert results == {1, 2, 3}

    def test_path_all_pairs(self):
        """All reachable pairs in cyclic graph."""
        # nv
        m = _load("tabled_path")
        X, Y = Var(), Var()
        results = set()
        for trail in call("path", X, Y, module=_module(m)):
            results.add((deref(X), deref(Y)))
        expected = {(a, b) for a in [1, 2, 3] for b in [1, 2, 3]}
        assert results == expected

    def test_path_from_node_2(self):
        # nv
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("path", 2, X, module=_module(m)):
            results.add(deref(X))
        assert results == {1, 2, 3}

    def test_path_from_node_3(self):
        # nv
        m = _load("tabled_path")
        X = Var()
        results = set()
        for trail in call("path", 3, X, module=_module(m)):
            results.add(deref(X))
        assert results == {1, 2, 3}

    def test_path_ground_true(self):
        # nv
        m = _load("tabled_path")
        results = list(call("path", 1, 3, module=_module(m)))
        assert len(results) >= 1

    def test_path_ground_self(self):
        """path(1, 1) should succeed via the cycle."""
        # nv
        m = _load("tabled_path")
        results = list(call("path", 1, 1, module=_module(m)))
        assert len(results) >= 1

    def test_table_entry_complete_after_query(self):
        """After a full query, table entries should be marked COMPLETE."""
        # nv
        m = _load("tabled_path")
        db = _module(m).db
        X = Var()
        list(call("path", 1, X, module=_module(m)))
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
        db.assertz(Clause(head=("foo", 99), body=[]))
        assert len(db._table_store) == 0

    def test_retract_auto_invalidates_tabled(self):
        # nv
        db = Database()
        db.mark_tabled("foo", 1)
        head = ("foo", 1)
        db.assertz(Clause(head=head, body=[]))
        db._table_store[("foo", 1, (1,))] = TableEntry()
        db.retract(head)
        assert len(db._table_store) == 0

    def test_assertz_non_tabled_no_invalidation(self):
        # nv
        db = Database()
        db._table_store[("bar", 1, (1,))] = TableEntry()
        db.assertz(Clause(head=("foo", 1), body=[]))
        assert len(db._table_store) == 1


# ── Import hook integration ──────────────────────────────────────────────────


class TestImportHookTabling:
    def test_tabled_directive_sets_metadata(self):
        # nv
        m = _load("tabled_fib")
        db = _module(m).db
        assert db.is_tabled("fib", 2)

    def test_tabled_predicate_wrapped(self):
        # nv
        m = _load("tabled_path")
        db = _module(m).db
        assert db.is_tabled("path", 2)
        assert not db.is_tabled("edge", 2)

    def test_non_tabled_predicate_still_works(self):
        # nv
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
        # nv
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
        # nv
        fixture = os.path.join(FIXTURES, f"_test_multi_tabled{SEAM}")
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
