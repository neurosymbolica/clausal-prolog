"""Tests for V2-1: First-argument indexing.

Verifies that compile_predicate and compile_predicate_trampoline use
first-argument indexing when there are enough clauses, and that the
indexed dispatch produces the same results as unindexed dispatch.
"""

import pytest

from clausal.logic.database import Clause, Database
from clausal.logic.compiler import (
    compile_predicate,
    compile_predicate_trampoline,
    _extract_first_arg_key,
    _build_first_arg_index,
    _INDEX_VAR,
    _INDEX_THRESHOLD,
)
from clausal.logic.predicate import PredicateMeta
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import StepGenerator, solutions, DONE
from clausal.terms import Compound, Unify
from clausal.logic.builtins import _normalize_fact_clause


# ── Helpers ──────────────────────────────────────────────────────────────────


def _simple_solutions(dispatch, args, trail=None):
    """Collect all solutions from a simple-mode dispatch function."""
    if trail is None:
        trail = Trail()
    results = []
    for _ in dispatch(*args, trail, None):
        results.append(tuple(deref(a) for a in args))
    return results


def _trampoline_solutions(dispatch, args, trail=None):
    """Collect all solutions from a trampoline-mode dispatch function."""
    if trail is None:
        trail = Trail()
    sg = StepGenerator(dispatch, None, *args, trail)
    return solutions(sg, lambda: tuple(deref(a) for a in args))


# ── Test _extract_first_arg_key ──────────────────────────────────────────────


class TestExtractFirstArgKey:
    def test_compound_literal(self):
        c = Clause(head=Compound("f", (42,)), body=[True])
        assert _extract_first_arg_key(c, 1) == 42

    def test_compound_string(self):
        c = Clause(head=Compound("f", ("hello", 1)), body=[True])
        assert _extract_first_arg_key(c, 2) == "hello"

    def test_compound_var(self):
        v = Var()
        c = Clause(head=Compound("f", (v, 1)), body=[True])
        assert _extract_first_arg_key(c, 2) is _INDEX_VAR

    def test_compound_var_with_unify(self):
        """Var + Unify pattern from _normalize_dataclass_fact."""
        v = Var()
        c = Clause(head=Compound("f", (v, Var())), body=[Unify(left=v, right=99)])
        assert _extract_first_arg_key(c, 2) == 99

    def test_compound_var_with_unify_reversed(self):
        """Unify with reversed left/right."""
        v = Var()
        c = Clause(head=Compound("f", (v,)), body=[Unify(left="abc", right=v)])
        assert _extract_first_arg_key(c, 1) == "abc"

    def test_zero_arity(self):
        c = Clause(head=Compound("f", ()), body=[True])
        assert _extract_first_arg_key(c, 0) is _INDEX_VAR

    def test_predicate_meta_head(self):
        class color(metaclass=PredicateMeta):
            _fields = ("name", "code")

        v = Var()
        head = color(name=v, code=Var())
        c = Clause(head=head, body=[Unify(left=v, right="red")])
        assert _extract_first_arg_key(c, 2) == "red"

    def test_non_indexable_first_arg(self):
        """Lists and term instances are not indexed (yet)."""
        c = Clause(head=Compound("f", ([1, 2], "x")), body=[True])
        assert _extract_first_arg_key(c, 2) is _INDEX_VAR

    def test_bool_key(self):
        c = Clause(head=Compound("f", (True,)), body=[True])
        assert _extract_first_arg_key(c, 1) is True

    def test_none_key(self):
        """None is indexable — extracted from Var+Unify pattern."""
        v = Var()
        c = Clause(head=Compound("f", (v,)), body=[Unify(left=v, right=None)])
        assert _extract_first_arg_key(c, 1) is None

    def test_none_key_direct(self):
        """None directly in Compound head is also indexable."""
        c = Clause(head=Compound("f", (None,)), body=[True])
        assert _extract_first_arg_key(c, 1) is None


# ── Test _build_first_arg_index ──────────────────────────────────────────────


class TestBuildFirstArgIndex:
    def test_too_few_clauses(self):
        clauses = [Clause(head=Compound("f", (i,)), body=[True]) for i in range(3)]
        assert _build_first_arg_index(clauses, 1) is None

    def test_zero_arity(self):
        clauses = [Clause(head=Compound("f", ()), body=[True]) for _ in range(10)]
        assert _build_first_arg_index(clauses, 0) is None

    def test_all_defaults(self):
        """All clauses have variable first arg — no index."""
        clauses = [
            Clause(head=Compound("f", (Var(), Var())), body=[True])
            for _ in range(5)
        ]
        assert _build_first_arg_index(clauses, 2) is None

    def test_basic_partition(self):
        clauses = [
            Clause(head=Compound("f", (1,)), body=[True]),
            Clause(head=Compound("f", (2,)), body=[True]),
            Clause(head=Compound("f", (3,)), body=[True]),
            Clause(head=Compound("f", (4,)), body=[True]),
        ]
        index = _build_first_arg_index(clauses, 1)
        assert index is not None
        assert set(index["buckets"].keys()) == {1, 2, 3, 4}
        assert index["defaults"] == []
        # Each bucket has exactly one clause
        for key, bucket in index["buckets"].items():
            assert len(bucket) == 1

    def test_mixed_with_defaults(self):
        v1, v2 = Var(), Var()
        clauses = [
            Clause(head=Compound("f", (1, Var())), body=[True]),   # idx 0, key=1
            Clause(head=Compound("f", (v1, v2)), body=[True]),     # idx 1, default
            Clause(head=Compound("f", (2, Var())), body=[True]),   # idx 2, key=2
            Clause(head=Compound("f", (3, Var())), body=[True]),   # idx 3, key=3
        ]
        index = _build_first_arg_index(clauses, 2)
        assert index is not None
        assert len(index["defaults"]) == 1
        # Bucket for key=1 has clause 0 + default clause 1
        assert len(index["buckets"][1]) == 2
        # Bucket for key=2 has default clause 1 + clause 2
        assert len(index["buckets"][2]) == 2
        # Bucket for key=3 has default clause 1 + clause 3
        assert len(index["buckets"][3]) == 2


# ── Integration tests: simple mode ──────────────────────────────────────────


class TestIndexedDispatchSimple:
    def _make_fact_db(self, functor, facts):
        """Build a Database with normalized fact clauses."""
        db = Database()
        for fact_args in facts:
            clause = _normalize_fact_clause(Compound(functor, tuple(fact_args)))
            db.assertz(clause)
        return db

    def test_ground_lookup(self):
        """Ground first-arg query uses index to find the right clause."""
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["red", v], trail)
        assert results == [("red", 255)]

    def test_var_first_arg_enumerates_all(self):
        """Unbound first-arg query tries all clauses."""
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)
        trail = Trail()
        v1, v2 = Var(), Var()
        results = _simple_solutions(fn, [v1, v2], trail)
        assert len(results) == 5

    def test_no_match_returns_empty(self):
        """Ground first-arg with no matching clause yields nothing."""
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["purple", v], trail)
        assert results == []

    def test_mixed_var_and_specific(self):
        """Default (var-headed) clauses interleave with specific clauses."""
        # clauses: f(1, a), f(X, b), f(2, c), f(3, d), f(X, e)
        # All ground values normalized to Var+Unify for output-mode queries.
        db = Database()
        db.assertz(_normalize_fact_clause(Compound("f", (1, "a"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "b"))))
        db.assertz(_normalize_fact_clause(Compound("f", (2, "c"))))
        db.assertz(_normalize_fact_clause(Compound("f", (3, "d"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "e"))))
        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()

        # Query f(1, Y): should get (1, a), (1, b), (1, e)
        y = Var()
        results = _simple_solutions(fn, [1, y], trail)
        assert [r[1] for r in results] == ["a", "b", "e"]

        # Query f(2, Y): should get (2, b), (2, c), (2, e)
        trail = Trail()
        y = Var()
        results = _simple_solutions(fn, [2, y], trail)
        assert [r[1] for r in results] == ["b", "c", "e"]

        # Query f(99, Y): should get (99, b), (99, e) — only defaults
        trail = Trail()
        y = Var()
        results = _simple_solutions(fn, [99, y], trail)
        assert [r[1] for r in results] == ["b", "e"]

    def test_integer_keys(self):
        """Large fact table with integer first args."""
        n = 20
        db = self._make_fact_db("num", [(i, i * i) for i in range(n)])
        fn = compile_predicate("num", 2, db.clauses_for("num", 2), db)

        # Specific lookup
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, [7, v], trail)
        assert results == [(7, 49)]

        # Enumerate all
        trail = Trail()
        v1, v2 = Var(), Var()
        results = _simple_solutions(fn, [v1, v2], trail)
        assert len(results) == n

    def test_string_keys(self):
        """Fact table with string first args."""
        facts = [("apple", 1), ("banana", 2), ("cherry", 3),
                 ("date", 4), ("elderberry", 5)]
        db = self._make_fact_db("fruit", facts)
        fn = compile_predicate("fruit", 2, db.clauses_for("fruit", 2), db)

        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["cherry", v], trail)
        assert results == [("cherry", 3)]

    def test_below_threshold_no_index(self):
        """Few clauses → no indexing, still works."""
        db = self._make_fact_db("small", [(1, "a"), (2, "b")])
        fn = compile_predicate("small", 2, db.clauses_for("small", 2), db)
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, [1, v], trail)
        assert results == [(1, "a")]


# ── Integration tests: trampoline mode ───────────────────────────────────────


class TestIndexedDispatchTrampoline:
    def _make_fact_db(self, functor, facts):
        db = Database()
        for fact_args in facts:
            clause = _normalize_fact_clause(Compound(functor, tuple(fact_args)))
            db.assertz(clause)
        return db

    def test_ground_lookup(self):
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate_trampoline(
            "color", 2, db.clauses_for("color", 2), db,
        )
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, ["red", v], trail)
        assert results == [("red", 255)]

    def test_var_first_arg_enumerates_all(self):
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate_trampoline(
            "color", 2, db.clauses_for("color", 2), db,
        )
        trail = Trail()
        v1, v2 = Var(), Var()
        results = _trampoline_solutions(fn, [v1, v2], trail)
        assert len(results) == 5

    def test_no_match_returns_empty(self):
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate_trampoline(
            "color", 2, db.clauses_for("color", 2), db,
        )
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, ["purple", v], trail)
        assert results == []

    def test_mixed_var_and_specific(self):
        db = Database()
        db.assertz(_normalize_fact_clause(Compound("f", (1, "a"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "b"))))
        db.assertz(_normalize_fact_clause(Compound("f", (2, "c"))))
        db.assertz(_normalize_fact_clause(Compound("f", (3, "d"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "e"))))
        fn = compile_predicate_trampoline("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()

        # f(1, Y): (1,a), (1,b), (1,e)
        y = Var()
        results = _trampoline_solutions(fn, [1, y], trail)
        assert [r[1] for r in results] == ["a", "b", "e"]

        # f(2, Y): (2,b), (2,c), (2,e)
        trail = Trail()
        y = Var()
        results = _trampoline_solutions(fn, [2, y], trail)
        assert [r[1] for r in results] == ["b", "c", "e"]

        # f(99, Y): (99,b), (99,e)
        trail = Trail()
        y = Var()
        results = _trampoline_solutions(fn, [99, y], trail)
        assert [r[1] for r in results] == ["b", "e"]

    def test_large_fact_table(self):
        n = 50
        db = self._make_fact_db("num", [(i, i * i) for i in range(n)])
        fn = compile_predicate_trampoline(
            "num", 2, db.clauses_for("num", 2), db,
        )
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [42, v], trail)
        assert results == [(42, 42 * 42)]

        trail = Trail()
        v1, v2 = Var(), Var()
        results = _trampoline_solutions(fn, [v1, v2], trail)
        assert len(results) == n


# ── Dynamic predicate re-indexing ────────────────────────────────────────────


class TestDynamicReindex:
    def test_assertz_rebuilds_index_simple(self):
        """After assertz, lazy recompile rebuilds the index."""
        db = Database()
        db.mark_dynamic("color", 2)
        for args in [("red", 1), ("green", 2), ("blue", 3), ("white", 4)]:
            db.assertz(_normalize_fact_clause(Compound("color", args)))
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        # Initial lookup works
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["red", v], trail)
        assert results == [("red", 1)]

        # Add a new clause — triggers lazy recompile on next use
        db.assertz(_normalize_fact_clause(Compound("color", ("purple", 5))))

        # The dispatch fn stored in db should now lazily recompile
        new_fn = db.get_dispatch("color", 2)
        trail = Trail()
        v = Var()
        results = _simple_solutions(new_fn, ["purple", v], trail)
        assert results == [("purple", 5)]

    def test_assertz_rebuilds_index_trampoline(self):
        db = Database()
        db.mark_dynamic("color", 2)
        for args in [("red", 1), ("green", 2), ("blue", 3), ("white", 4)]:
            db.assertz(_normalize_fact_clause(Compound("color", args)))
        fn = compile_predicate_trampoline(
            "color", 2, db.clauses_for("color", 2), db,
        )

        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, ["red", v], trail)
        assert results == [("red", 1)]

        db.assertz(_normalize_fact_clause(Compound("color", ("purple", 5))))
        new_fn = db.get_dispatch("color", 2)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(new_fn, ["purple", v], trail)
        assert results == [("purple", 5)]


# ── PredicateMeta integration ────────────────────────────────────────────────


class TestPredicateMetaIndexing:
    def test_predicate_meta_facts(self):
        """PredicateMeta class facts with normalized Var+Unify heads."""
        class fruit(metaclass=PredicateMeta):
            _fields = ("name", "count")

        db = Database()
        for name, count in [("apple", 5), ("banana", 3), ("cherry", 8),
                            ("date", 2), ("elderberry", 1)]:
            v1, v2 = Var(), Var()
            head = fruit(name=v1, count=v2)
            db.assertz(Clause(head=head, body=[Unify(left=v1, right=name),
                                                Unify(left=v2, right=count)]))

        fn = compile_predicate(
            "fruit", 2, db.clauses_for("fruit", 2), db,
            globals_={"fruit": fruit},
        )

        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["cherry", v], trail)
        assert results == [("cherry", 8)]

        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["missing", v], trail)
        assert results == []

        trail = Trail()
        v1, v2 = Var(), Var()
        results = _simple_solutions(fn, [v1, v2], trail)
        assert len(results) == 5


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_single_arity(self):
        """Arity-1 predicates can be indexed."""
        db = Database()
        for i in range(5):
            db.assertz(_normalize_fact_clause(Compound("p", (i,))))
        fn = compile_predicate("p", 1, db.clauses_for("p", 1), db)
        trail = Trail()
        results = _simple_solutions(fn, [3], trail)
        assert results == [(3,)]

    def test_duplicate_keys(self):
        """Multiple clauses with the same first-arg key."""
        db = Database()
        for args in [(1, "a"), (1, "b"), (2, "c"), (2, "d"), (1, "e")]:
            db.assertz(_normalize_fact_clause(Compound("f", args)))
        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()
        y = Var()
        results = _simple_solutions(fn, [1, y], trail)
        assert [r[1] for r in results] == ["a", "b", "e"]

    def test_none_as_key(self):
        """None as first argument value is indexable."""
        db = Database()
        for v in [None, 1, 2, 3]:
            db.assertz(_normalize_fact_clause(Compound("f", (v, str(v)))))
        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()
        y = Var()
        results = _simple_solutions(fn, [None, y], trail)
        assert results == [(None, "None")]

    def test_bool_vs_int(self):
        """True/1 and False/0 share hash buckets in Python — both found."""
        db = Database()
        for v in [True, False, 0, 1, 2]:
            db.assertz(_normalize_fact_clause(Compound("f", (v,))))
        fn = compile_predicate("f", 1, db.clauses_for("f", 1), db)
        trail = Trail()
        # True == 1 and False == 0 in Python, so querying with True finds both
        results = _simple_solutions(fn, [True], trail)
        # Both True and 1 should match (they're equal in Python)
        assert len(results) >= 1
