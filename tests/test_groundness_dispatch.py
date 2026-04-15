"""Tests for V2-2: Groundness-keyed dispatch (multi-plan compilation).

Verifies that compile_predicate_trampoline uses multi-argument indexing
when multiple argument positions have indexable values, and that the
groundness-keyed selector picks the best plan at call time based on
which arguments are ground.
"""

import pytest

from clausal.logic.database import Clause, Database
from clausal.logic.compiler import compile_predicate_trampoline as compile_predicate
from clausal.logic.compiler.arg_index import (
    _extract_arg_key,
    _build_arg_index,
    _analyze_index_positions,
    _INDEX_VAR,
    _INDEX_THRESHOLD,
)
from clausal.logic.predicate import PredicateMeta
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import StepGenerator, solutions, DONE
from clausal.terms import Compound, Unify
from clausal.logic.builtins import _normalize_fact_clause


# ── Helpers ──────────────────────────────────────────────────────────────────


def _trampoline_solutions(dispatch, args, trail=None):
    """Collect all solutions from a trampoline-mode dispatch function."""
    if trail is None:
        trail = Trail()
    sg = StepGenerator(dispatch, None, *args, trail)
    return solutions(sg, lambda: tuple(deref(a) for a in args))


def _make_fact_db(functor, facts):
    """Build a Database with normalized fact clauses."""
    db = Database()
    for fact_args in facts:
        clause = _normalize_fact_clause(Compound(functor, tuple(fact_args)))
        db.assertz(clause)
    return db


# ── Test _extract_arg_key (generalized) ─────────────────────────────────────


class TestExtractArgKey:
    def test_position_zero(self):
        # nv
        c = Clause(head=Compound("f", (42, "hello")), body=[True])
        assert _extract_arg_key(c, 0, 2) == 42

    def test_position_one(self):
        # nv
        c = Clause(head=Compound("f", (42, "hello")), body=[True])
        assert _extract_arg_key(c, 1, 2) == "hello"

    def test_var_at_position(self):
        # nv
        v = Var()
        c = Clause(head=Compound("f", (42, v)), body=[True])
        assert _extract_arg_key(c, 1, 2) is _INDEX_VAR

    def test_var_with_unify_at_position(self):
        """Var + Unify pattern from _normalize_dataclass_fact at non-first position."""
        # nv
        v0, v1 = Var(), Var()
        c = Clause(
            head=Compound("f", (v0, v1)),
            body=[Unify(left=v0, right=1), Unify(left=v1, right="abc")],
        )
        assert _extract_arg_key(c, 0, 2) == 1
        assert _extract_arg_key(c, 1, 2) == "abc"

    def test_out_of_range(self):
        # nv
        c = Clause(head=Compound("f", (1,)), body=[True])
        assert _extract_arg_key(c, 1, 1) is _INDEX_VAR
        assert _extract_arg_key(c, 5, 1) is _INDEX_VAR

    def test_predicate_meta_second_field(self):
        # nv
        class color(metaclass=PredicateMeta):
            _fields = ("name", "code")

        v1, v2 = Var(), Var()
        head = color(name=v1, code=v2)
        c = Clause(
            head=head,
            body=[Unify(left=v1, right="red"), Unify(left=v2, right=255)],
        )
        assert _extract_arg_key(c, 0, 2) == "red"
        assert _extract_arg_key(c, 1, 2) == 255


# ── Test _build_arg_index ───────────────────────────────────────────────────


class TestBuildArgIndex:
    def test_position_zero_matches_first_arg(self):
        """Position 0 index matches _build_first_arg_index behavior."""
        # nv
        clauses = [
            Clause(head=Compound("f", (i, "x")), body=[True])
            for i in range(5)
        ]
        idx = _build_arg_index(clauses, 2, 0)
        assert idx is not None
        assert set(idx["buckets"].keys()) == {0, 1, 2, 3, 4}

    def test_position_one_index(self):
        """Second argument has indexable values."""
        # nv
        clauses = [
            Clause(head=Compound("f", (Var(), "a")), body=[True]),
            Clause(head=Compound("f", (Var(), "b")), body=[True]),
            Clause(head=Compound("f", (Var(), "c")), body=[True]),
            Clause(head=Compound("f", (Var(), "d")), body=[True]),
        ]
        idx = _build_arg_index(clauses, 2, 1)
        assert idx is not None
        assert set(idx["buckets"].keys()) == {"a", "b", "c", "d"}

    def test_no_index_all_vars(self):
        # nv
        clauses = [
            Clause(head=Compound("f", (Var(), Var())), body=[True])
            for _ in range(5)
        ]
        assert _build_arg_index(clauses, 2, 0) is None
        assert _build_arg_index(clauses, 2, 1) is None

    def test_n_distinct(self):
        # nv
        clauses = [
            Clause(head=Compound("f", (1, "a")), body=[True]),
            Clause(head=Compound("f", (1, "b")), body=[True]),
            Clause(head=Compound("f", (2, "c")), body=[True]),
            Clause(head=Compound("f", (3, "d")), body=[True]),
        ]
        idx = _build_arg_index(clauses, 2, 0)
        assert idx is not None
        assert idx["n_distinct"] == 3  # keys: 1, 2, 3


# ── Test _analyze_index_positions ────────────────────────────────────────────


class TestAnalyzeIndexPositions:
    def test_both_positions_indexable(self):
        """Both arg positions have indexable values."""
        # nv
        facts = [(1, "a"), (2, "b"), (3, "c"), (4, "d")]
        db = _make_fact_db("f", facts)
        clauses = db.clauses_for("f", 2)
        positions = _analyze_index_positions(clauses, 2)
        assert len(positions) == 2
        # Both positions should have 4 distinct keys
        pos_set = {p for p, _ in positions}
        assert pos_set == {0, 1}

    def test_only_second_arg_indexable(self):
        """First arg is always Var, second has distinct values."""
        # nv
        clauses = [
            Clause(head=Compound("f", (Var(), val)), body=[True])
            for val in ["a", "b", "c", "d"]
        ]
        positions = _analyze_index_positions(clauses, 2)
        assert len(positions) == 1
        assert positions[0][0] == 1  # only position 1

    def test_sorted_by_selectivity(self):
        """Most selective position comes first."""
        # Position 0: 2 distinct values; Position 1: 4 distinct values
        # nv
        clauses = [
            Clause(head=Compound("f", (1, "a")), body=[True]),
            Clause(head=Compound("f", (1, "b")), body=[True]),
            Clause(head=Compound("f", (2, "c")), body=[True]),
            Clause(head=Compound("f", (2, "d")), body=[True]),
        ]
        positions = _analyze_index_positions(clauses, 2)
        assert len(positions) == 2
        # Position 1 has 4 distinct keys, position 0 has 2 — pos 1 first
        assert positions[0][0] == 1
        assert positions[1][0] == 0

    def test_empty_for_few_clauses(self):
        # nv
        clauses = [Clause(head=Compound("f", (i,)), body=[True]) for i in range(2)]
        assert _analyze_index_positions(clauses, 1) == []

    def test_three_arg_predicate(self):
        """Three-argument predicate: all positions indexable."""
        # nv
        facts = [(1, "a", True), (2, "b", False), (3, "c", True), (4, "d", False)]
        db = _make_fact_db("f", facts)
        clauses = db.clauses_for("f", 3)
        positions = _analyze_index_positions(clauses, 3)
        assert len(positions) == 3


# ── Integration: second-arg lookup ───────────────────────────────────────────


class TestSecondArgLookup:
    def test_lookup_by_second_arg(self):
        """when first arg is Var but second is ground, use second-arg index."""
        # nv
        facts = [
            ("red", "warm"), ("blue", "cool"), ("green", "cool"),
            ("yellow", "warm"), ("white", "neutral"),
        ]
        db = _make_fact_db("color", facts)
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        # Query with ground second arg, var first arg
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [v, "warm"], trail)
        assert sorted(r[0] for r in results) == ["red", "yellow"]

    def test_lookup_by_first_arg_still_works(self):
        """First-arg lookup still works as before."""
        # nv
        facts = [
            ("red", "warm"), ("blue", "cool"), ("green", "cool"),
            ("yellow", "warm"), ("white", "neutral"),
        ]
        db = _make_fact_db("color", facts)
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, ["blue", v], trail)
        assert results == [("blue", "cool")]

    def test_all_vars_enumerate(self):
        """when no arg is ground, fallback to full scan."""
        # nv
        facts = [
            ("red", "warm"), ("blue", "cool"), ("green", "cool"),
            ("yellow", "warm"), ("white", "neutral"),
        ]
        db = _make_fact_db("color", facts)
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        trail = Trail()
        v1, v2 = Var(), Var()
        results = _trampoline_solutions(fn, [v1, v2], trail)
        assert len(results) == 5

    def test_both_args_ground(self):
        """Both args ground — uses most selective index."""
        # nv
        facts = [
            ("red", "warm"), ("blue", "cool"), ("green", "cool"),
            ("yellow", "warm"), ("white", "neutral"),
        ]
        db = _make_fact_db("color", facts)
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        trail = Trail()
        results = _trampoline_solutions(fn, ["red", "warm"], trail)
        assert results == [("red", "warm")]

        trail = Trail()
        results = _trampoline_solutions(fn, ["red", "cool"], trail)
        assert results == []

    def test_no_match_second_arg(self):
        """Ground second arg with no matching value yields nothing."""
        # nv
        facts = [
            ("red", "warm"), ("blue", "cool"), ("green", "cool"),
            ("yellow", "warm"), ("white", "neutral"),
        ]
        db = _make_fact_db("color", facts)
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [v, "freezing"], trail)
        assert results == []

    def test_three_arg_middle_ground(self):
        """Three-arg predicate: query by middle arg only."""
        # nv
        facts = [
            (1, "a", 100), (2, "b", 200), (3, "a", 300),
            (4, "c", 400), (5, "b", 500),
        ]
        db = _make_fact_db("t", facts)
        fn = compile_predicate("t", 3, db.clauses_for("t", 3), db)

        trail = Trail()
        v1, v2 = Var(), Var()
        results = _trampoline_solutions(fn, [v1, "a", v2], trail)
        assert sorted(r[0] for r in results) == [1, 3]

    def test_three_arg_last_ground(self):
        """Three-arg predicate: query by last arg only."""
        # nv
        facts = [
            (1, "a", 100), (2, "b", 200), (3, "a", 100),
            (4, "c", 400), (5, "b", 100),
        ]
        db = _make_fact_db("t", facts)
        fn = compile_predicate("t", 3, db.clauses_for("t", 3), db)

        trail = Trail()
        v1, v2 = Var(), Var()
        results = _trampoline_solutions(fn, [v1, v2, 100], trail)
        assert sorted(r[0] for r in results) == [1, 3, 5]


# ── Same predicate, different modes ─────────────────────────────────────────


class TestDifferentModes:
    """Same predicate called in different modes hits different plans."""

    def test_color_all_modes(self):
        # nv
        facts = [
            ("red", "warm"), ("blue", "cool"), ("green", "cool"),
            ("yellow", "warm"), ("orange", "warm"),
        ]
        db = _make_fact_db("color", facts)
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        # Mode 1: first arg ground
        trail = Trail()
        v = Var()
        r1 = _trampoline_solutions(fn, ["red", v], trail)
        assert r1 == [("red", "warm")]

        # Mode 2: second arg ground
        trail = Trail()
        v = Var()
        r2 = _trampoline_solutions(fn, [v, "cool"], trail)
        assert sorted(r[0] for r in r2) == ["blue", "green"]

        # Mode 3: both ground
        trail = Trail()
        r3 = _trampoline_solutions(fn, ["blue", "cool"], trail)
        assert r3 == [("blue", "cool")]

        # Mode 4: neither ground
        trail = Trail()
        v1, v2 = Var(), Var()
        r4 = _trampoline_solutions(fn, [v1, v2], trail)
        assert len(r4) == 5


# ── Mixed var/specific clauses with multi-arg indexing ───────────────────────


class TestMixedClauses:
    def test_var_headed_clauses_in_all_buckets(self):
        """Clauses with Var at a position appear in every bucket for that position."""
        # nv
        db = Database()
        # Position 0: specific keys 1, 2, 3 plus 2 catch-all (Var) clauses
        # Position 1: all specific ("a" through "e") — no defaults
        db.assertz(_normalize_fact_clause(Compound("f", (1, "a"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "b"))))
        db.assertz(_normalize_fact_clause(Compound("f", (2, "c"))))
        db.assertz(_normalize_fact_clause(Compound("f", (3, "d"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "e"))))
        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)

        # Query by first arg 1: should get (1, a) + catch-alls (_, b), (_, e)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [1, v], trail)
        assert [r[1] for r in results] == ["a", "b", "e"]

        # Query by second arg "d": position 1 has no defaults → only (3, d)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [v, "d"], trail)
        assert [r[1] for r in results] == ["d"]

    def test_true_catch_all_clauses(self):
        """Clauses with Var at ALL positions are defaults for every index."""
        # nv
        db = Database()
        db.assertz(_normalize_fact_clause(Compound("f", (1, "a"))))
        db.assertz(_normalize_fact_clause(Compound("f", (2, "b"))))
        db.assertz(_normalize_fact_clause(Compound("f", (3, "c"))))
        # This clause has Var at position 0 AND Var at position 1 (no Unify)
        db.assertz(Clause(head=Compound("f", (Var(), Var())), body=[True]))
        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)

        # Query by first arg: gets specific + catch-all
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [1, v], trail)
        assert len(results) == 2  # (1, "a") + catch-all

        # Query by second arg: gets specific + catch-all
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [v, "b"], trail)
        assert len(results) == 2  # (2, "b") + catch-all


# ── Dynamic predicate re-indexing with multi-plan dispatch ──────────────────


class TestDynamicReindexGroundness:
    def test_assertz_rebuilds_multi_index(self):
        # nv
        db = Database()
        db.mark_dynamic("color", 2)
        for args in [("red", "warm"), ("green", "cool"),
                     ("blue", "cool"), ("white", "neutral")]:
            db.assertz(_normalize_fact_clause(Compound("color", args)))
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        # Initial second-arg lookup
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [v, "cool"], trail)
        assert sorted(r[0] for r in results) == ["blue", "green"]

        # Add new fact and trigger recompile
        db.assertz(_normalize_fact_clause(Compound("color", ("purple", "cool"))))
        new_fn = db.get_dispatch("color", 2)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(new_fn, [v, "cool"], trail)
        assert sorted(r[0] for r in results) == ["blue", "green", "purple"]


# ── Backward compatibility with V2-1 ────────────────────────────────────────


class TestBackwardCompat:
    def test_single_position_matches_v2_1_behavior(self):
        """when only position 0 is indexable, behavior matches V2-1."""
        # All second args are Var → only position 0 is indexable
        # nv
        clauses = [
            Clause(head=Compound("f", (i, Var())), body=[True])
            for i in range(5)
        ]
        db = Database()
        for c in clauses:
            db.assertz(c)

        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [3, v], trail)
        assert len(results) == 1
        assert results[0][0] == 3

    def test_below_threshold_no_dispatch(self):
        """Too few clauses → no groundness dispatch, still correct."""
        # nv
        db = _make_fact_db("small", [(1, "a"), (2, "b")])
        fn = compile_predicate("small", 2, db.clauses_for("small", 2), db)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [1, v], trail)
        assert results == [(1, "a")]


# ── PredicateMeta integration ───────────────────────────────────────────────


class TestPredicateMetaGroundness:
    def test_second_field_lookup(self):
        # nv
        class fruit(metaclass=PredicateMeta):
            _fields = ("name", "color")

        db = Database()
        for name, color in [("apple", "red"), ("banana", "yellow"),
                            ("cherry", "red"), ("grape", "purple"),
                            ("strawberry", "red")]:
            v1, v2 = Var(), Var()
            head = fruit(name=v1, color=v2)
            db.assertz(Clause(
                head=head,
                body=[Unify(left=v1, right=name), Unify(left=v2, right=color)],
            ))

        fn = compile_predicate(
            "fruit", 2, db.clauses_for("fruit", 2), db,
            globals_={"fruit": fruit},
        )

        # Lookup by color (second field)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [v, "red"], trail)
        assert sorted(r[0] for r in results) == ["apple", "cherry", "strawberry"]

        # Lookup by name (first field)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, ["banana", v], trail)
        assert results == [("banana", "yellow")]
