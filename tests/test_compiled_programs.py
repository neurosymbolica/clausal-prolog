"""Meatier end-to-end tests for the compiled predicate stack.

These tests use compile_predicate and compile_predicate_trampoline to build
realistic logic programs and verify their behaviour.  No import hook is needed —
predicates are assembled directly via Clause / Database APIs.

Key design rule
---------------
Literal values in a clause head generate MatchValue patterns — they only match
when the *caller* passes the exact same ground value.  For output-mode arguments
(where the caller passes an unbound Var to receive a result), the head position
must be a Var, and the clause body must unify that Var with the intended value
via an Is goal.

    WRONG (literal in output position):
        Clause(head=Compound("fib", (0, 0)), body=[])
        # fib(n=0, result_var) → match [0, 0] fails; result_var is a Var not 0.

    RIGHT (Var in output position + Is in body):
        rv = Var()
        Clause(head=Compound("fib", (0, rv)), body=[Is(left=rv, right=0)])
        # fib(n=0, result_var) → match [0, _v] succeeds; body unifies _v (=result_var) with 0.

Programs covered
----------------
  - Graph reachability: edge/2 facts + path/2 transitive closure
  - Classification: animal/2 with compound-head (functor dataclass) pattern matching
  - Fibonacci: recursive fib/2 with correct Var/literal head design
  - permutation + N-queens: in_ enumeration + arithmetic constraints
  - Combination search: multiple predicate calls in conjunction
  - Visualizer smoke tests
"""

from __future__ import annotations

import dataclasses
import pytest

from clausal.logic.compiler import compile_predicate_trampoline, compile_predicate_trampoline as compile_predicate
from clausal.logic.database import Clause, Database
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import (
    And, Or, Not,
    Unify as Is, DoesNotUnify as IsNot, Evaluate, ArithEq, ArithNeq,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    Add, Sub, Mult, Negate,
    Call, LoadName,
    Compound,
)


# ── Search helpers ─────────────────────────────────────────────────────────────


def fresh_trail() -> Trail:
    return Trail()


def solutions_simple(dispatch_fn, *args_then_snapshot) -> list:
    """Drive a dispatch_fn and collect per-solution snapshots.

    Call as: solutions_simple(fn, arg0, arg1, ..., trail, snapshot_fn)
    snapshot_fn is called while the generator is suspended (bindings live).

    Delegates to solutions_trampoline since all dispatch fns are now trampoline mode.
    """
    snapshot_fn = args_then_snapshot[-1]
    gen_args = args_then_snapshot[:-1]   # includes trail as last positional arg
    return solutions_trampoline(dispatch_fn, gen_args, snapshot_fn)


def solutions_trampoline(dispatch_fn, args_tuple, snapshot_fn) -> list:
    """Drive a trampoline-mode dispatch_fn and collect per-solution snapshots."""
    from clausal.logic.compiler import DONE
    from clausal.logic.trampoline import StepGenerator

    snapshots = []
    root = StepGenerator(dispatch_fn, None, None, None, *args_tuple)
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


# ── Graph reachability ─────────────────────────────────────────────────────────
#
# Graph: a→b→c→d, b→d (directed).
#
# edge/2: each fact uses a literal source and a Var destination + Is body,
# so that callers can pass a Var for the destination to receive the target.
#
# path(X, Y) :- edge(X, Y).
# path(X, Y) :- edge(X, Z), path(Z, Y).


class TestGraphReachability:
    """Graph: a→b→c→d, b→d.  Reachable from 'a': b, c, d (multiple paths to d)."""

    def _build_db(self):
        db = Database()

        # edge facts: literal source, Var destination + Is body.
        for src, dst in [("a", "b"), ("b", "c"), ("c", "d"), ("b", "d")]:
            dv = Var()
            db.assertz(Clause(
                head=Compound("edge", (src, dv)),
                body=[Is(left=dv, right=dst)],
            ))

        compile_predicate("edge", 2, db.clauses_for("edge", 2), db)

        # path(X, Y) :- edge(X, Y).
        px, py = Var(), Var()
        db.assertz(Clause(
            head=Compound("path", (px, py)),
            body=[Call(func=LoadName(name="edge"), args=[px, py], kwargs=[])],
        ))

        # path(X, Y) :- edge(X, Z), path(Z, Y).
        rx, ry, rz = Var(), Var(), Var()
        db.assertz(Clause(
            head=Compound("path", (rx, ry)),
            body=[
                Call(func=LoadName(name="edge"), args=[rx, rz], kwargs=[]),
                Call(func=LoadName(name="path"), args=[rz, ry], kwargs=[]),
            ],
        ))

        compile_predicate("path", 2, db.clauses_for("path", 2), db)
        return db

    def test_direct_edge(self):
        """path(a, b) holds — direct edge."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("path", 2)
        trail = fresh_trail()
        dest = Var()
        results = solutions_simple(fn, "a", dest, trail, lambda: deref(dest))
        assert "b" in results

    def test_transitive_reachability(self):
        """From 'a', can reach b, c, d (but not a itself in a DAG)."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("path", 2)
        trail = fresh_trail()
        dest = Var()
        results = solutions_simple(fn, "a", dest, trail, lambda: deref(dest))
        assert set(results) >= {"b", "c", "d"}

    def test_no_path_backwards(self):
        """No outgoing edges from 'd' → path(d, Y) has no solutions."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("path", 2)
        trail = fresh_trail()
        dest = Var()
        results = solutions_simple(fn, "d", dest, trail, lambda: deref(dest))
        assert results == []

    def test_path_to_specific_dest(self):
        """path(a, d) is provable (at least one path: a→b→d or a→b→c→d)."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("path", 2)
        trail = fresh_trail()
        # when second arg is ground, the match arm body fails if unification fails.
        # Because 'd' is a string and the Is body produces "b"/"c"/"d", we need
        # the head's Var for dest to unify with 'd'.  Since the head for path uses
        # a Var (py), calling with 'd' will match and the body Is(py, 'd') would
        # unify the captured Var with 'd' — but edge's body already bound dv to the
        # actual destination, so we check if that deref'd value equals 'd'.
        # Simplest: pass Var and filter.
        dest = Var()
        results = solutions_simple(fn, "a", dest, trail, lambda: deref(dest))
        assert "d" in results

    def test_edge_count(self):
        """edge/2 has exactly 4 clauses (one per edge in the graph)."""
        # nv
        db = self._build_db()
        assert len(db.clauses_for("edge", 2)) == 4


# ── Classification via compound-head (functor dataclass) matching ─────────────
#
# animal(dog(_), "mammal").   ← dog with any name → mammal
# animal(eagle(_), "bird").
# animal(salmon(_), "fish").


@dataclasses.dataclass
class dog:
    name: object = None


@dataclasses.dataclass
class eagle:
    name: object = None


@dataclasses.dataclass
class salmon:
    name: object = None


class TestClassification:
    """Pattern-match on functor dataclass heads to classify animals."""

    def _build_db(self):
        db = Database()

        for cls_, category in [(dog, "mammal"), (eagle, "bird"), (salmon, "fish")]:
            nv = Var()   # wildcard for name field
            cv = Var()   # output: category
            db.assertz(Clause(
                head=Compound("animal", (cls_(name=nv), cv)),
                body=[Is(left=cv, right=category)],
            ))

        compile_predicate("animal", 2, db.clauses_for("animal", 2), db)
        return db

    def test_dog_is_mammal(self):
        # nv
        db = self._build_db()
        fn = db.get_dispatch("animal", 2)
        trail = fresh_trail()
        cat = Var()
        results = solutions_simple(fn, dog(name="rex"), cat, trail, lambda: deref(cat))
        assert results == ["mammal"]

    def test_eagle_is_bird(self):
        # nv
        db = self._build_db()
        fn = db.get_dispatch("animal", 2)
        trail = fresh_trail()
        cat = Var()
        results = solutions_simple(fn, eagle(name="goldie"), cat, trail, lambda: deref(cat))
        assert results == ["bird"]

    def test_salmon_is_fish(self):
        # nv
        db = self._build_db()
        fn = db.get_dispatch("animal", 2)
        trail = fresh_trail()
        cat = Var()
        results = solutions_simple(fn, salmon(name="coho"), cat, trail, lambda: deref(cat))
        assert results == ["fish"]

    def test_name_is_irrelevant(self):
        """Different names for the same species → same category."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("animal", 2)
        for name in ["fido", "rex", "spot"]:
            trail = fresh_trail()
            cat = Var()
            results = solutions_simple(fn, dog(name=name), cat, trail, lambda c=cat: deref(c))
            assert results == ["mammal"], f"dog(name={name!r}) should be mammal"

    def test_unknown_matches_nothing(self):
        """A string is not a known animal term → no solutions."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("animal", 2)
        trail = fresh_trail()
        cat = Var()
        results = solutions_simple(fn, "not_an_animal", cat, trail, lambda: deref(cat))
        assert results == []

    def test_ground_category_check(self):
        """animal(eagle(_), 'mammal') fails; animal(eagle(_), 'bird') succeeds."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("animal", 2)

        t1 = fresh_trail()
        results_wrong = solutions_simple(
            fn, eagle(name="e"), "mammal", t1, lambda: True
        )
        assert results_wrong == [], "eagle is not a mammal"

        t2 = fresh_trail()
        results_right = solutions_simple(
            fn, eagle(name="e"), "bird", t2, lambda: True
        )
        assert results_right == [True], "eagle is a bird"


# ── Fibonacci ──────────────────────────────────────────────────────────────────
#
# fib(0, R) :- R = 0.
# fib(1, R) :- R = 1.
# fib(N, R) :- N > 1, N1 is N-1, N2 is N-2,
#              fib(N1, R1), fib(N2, R2), R is R1+R2.
#
# Base cases use (literal N, Var R) heads so they match when the caller
# passes N=0 or N=1 as a ground integer and R as an unbound Var.


class TestFibonacci:

    def _build_db(self):
        db = Database()

        # fib(0, R) :- R = 0.
        r0 = Var()
        db.assertz(Clause(head=Compound("fib", (0, r0)), body=[Is(left=r0, right=0)]))

        # fib(1, R) :- R = 1.
        r1 = Var()
        db.assertz(Clause(head=Compound("fib", (1, r1)), body=[Is(left=r1, right=1)]))

        # fib(N, R) :- N > 1, N1 := N-1, N2 := N-2,
        #              fib(N1, R1), fib(N2, R2), R := R1+R2.
        n, r, n1, n2, ra, rb = Var(), Var(), Var(), Var(), Var(), Var()
        db.assertz(Clause(
            head=Compound("fib", (n, r)),
            body=[
                Gt(left=n, right=1),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Evaluate(left=n2, right=Sub(left=n, right=2)),
                Call(func=LoadName(name="fib"), args=[n1, ra], kwargs=[]),
                Call(func=LoadName(name="fib"), args=[n2, rb], kwargs=[]),
                Evaluate(left=r, right=Add(left=ra, right=rb)),
            ],
        ))

        compile_predicate("fib", 2, db.clauses_for("fib", 2), db)
        return db

    @pytest.mark.parametrize("n,expected", [
        (0, 0), (1, 1), (2, 1), (3, 2), (4, 3), (5, 5), (6, 8), (7, 13),
    ])
    def test_fib_values(self, n, expected):
        # nv
        db = self._build_db()
        fn = db.get_dispatch("fib", 2)
        trail = fresh_trail()
        result = Var()
        results = solutions_simple(fn, n, result, trail, lambda: deref(result))
        assert results == [expected], f"fib({n}): expected {expected}, got {results}"

    def test_fib_deterministic(self):
        """fib(N, R) yields exactly one solution for each ground N."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("fib", 2)
        for n in range(8):
            trail = fresh_trail()
            result = Var()
            results = solutions_simple(fn, n, result, trail, lambda: True)
            assert len(results) == 1, f"fib({n}) should have exactly 1 solution"


# ── permutation + 4-queens ─────────────────────────────────────────────────────
#
# perm4(C0, C1, C2, C3) — enumerate permutations of 1..4 using in_ enumeration
# and pairwise IsNot checks.
#
# no_attack(Ci, Cj, Dist) — Ci != Cj AND |Ci - Cj| != Dist (no diagonal attack).
#
# queens4(C0, C1, C2, C3) — perm4 + all 6 pairwise no_attack checks.
#
# The 4-queens problem has exactly 2 solutions: (2,4,1,3) and (3,1,4,2).


class TestNQueens4:
    """4-queens: place 4 non-attacking queens on a 4×4 board."""

    def _build_db(self):
        db = Database()

        # perm4(C0, C1, C2, C3) :- C0 in [1..4], C1 in [1..4], C2 in [1..4],
        #   C3 in [1..4], all distinct.
        c0, c1, c2, c3 = Var(), Var(), Var(), Var()
        db.assertz(Clause(
            head=Compound("perm4", (c0, c1, c2, c3)),
            body=[
                in_(left=c0, right=[1, 2, 3, 4]),
                in_(left=c1, right=[1, 2, 3, 4]),
                in_(left=c2, right=[1, 2, 3, 4]),
                in_(left=c3, right=[1, 2, 3, 4]),
                IsNot(left=c0, right=c1),
                IsNot(left=c0, right=c2),
                IsNot(left=c0, right=c3),
                IsNot(left=c1, right=c2),
                IsNot(left=c1, right=c3),
                IsNot(left=c2, right=c3),
            ],
        ))
        compile_predicate("perm4", 4, db.clauses_for("perm4", 4), db)

        # no_attack(Ci, Cj, Dist):
        #   Ci != Cj (no column clash)
        #   Ci - Cj != Dist (not on same diagonal one way)
        #   Cj - Ci != Dist (not on same diagonal the other way)
        ci, cj, dist = Var(), Var(), Var()
        diff1, diff2 = Var(), Var()
        db.assertz(Clause(
            head=Compound("no_attack", (ci, cj, dist)),
            body=[
                IsNot(left=ci, right=cj),
                Evaluate(left=diff1, right=Sub(left=ci, right=cj)),
                ArithNeq(left=diff1, right=dist),
                Evaluate(left=diff2, right=Sub(left=cj, right=ci)),
                ArithNeq(left=diff2, right=dist),
            ],
        ))
        compile_predicate("no_attack", 3, db.clauses_for("no_attack", 3), db)

        # queens4(C0, C1, C2, C3) :- perm4(C0,C1,C2,C3),
        #   no_attack(C0,C1,1), no_attack(C0,C2,2), no_attack(C0,C3,3),
        #   no_attack(C1,C2,1), no_attack(C1,C3,2), no_attack(C2,C3,1).
        q0, q1, q2, q3 = Var(), Var(), Var(), Var()
        db.assertz(Clause(
            head=Compound("queens4", (q0, q1, q2, q3)),
            body=[
                Call(func=LoadName(name="perm4"), args=[q0, q1, q2, q3], kwargs=[]),
                Call(func=LoadName(name="no_attack"), args=[q0, q1, 1], kwargs=[]),
                Call(func=LoadName(name="no_attack"), args=[q0, q2, 2], kwargs=[]),
                Call(func=LoadName(name="no_attack"), args=[q0, q3, 3], kwargs=[]),
                Call(func=LoadName(name="no_attack"), args=[q1, q2, 1], kwargs=[]),
                Call(func=LoadName(name="no_attack"), args=[q1, q3, 2], kwargs=[]),
                Call(func=LoadName(name="no_attack"), args=[q2, q3, 1], kwargs=[]),
            ],
        ))
        compile_predicate("queens4", 4, db.clauses_for("queens4", 4), db)
        return db

    def test_perm4_has_24_solutions(self):
        """perm4/4 enumerates all 4! = 24 permutations of {1,2,3,4}."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("perm4", 4)
        trail = fresh_trail()
        a, b, c, d = Var(), Var(), Var(), Var()
        results = solutions_simple(
            fn, a, b, c, d, trail,
            lambda: (deref(a), deref(b), deref(c), deref(d)),
        )
        assert len(results) == 24
        assert all(len(set(p)) == 4 for p in results)

    def test_no_attack_passes_safe_queens(self):
        """no_attack(2, 4, 1) succeeds: col diff = 2 ≠ 1."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("no_attack", 3)
        trail = fresh_trail()
        results = solutions_simple(fn, 2, 4, 1, trail, lambda: True)
        assert results == [True]

    def test_no_attack_fails_diagonal(self):
        """no_attack(1, 2, 1) fails: |1-2| = 1 = dist."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("no_attack", 3)
        trail = fresh_trail()
        results = solutions_simple(fn, 1, 2, 1, trail, lambda: True)
        assert results == []

    def test_exactly_two_solutions(self):
        """4-queens has exactly 2 solutions."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("queens4", 4)
        trail = fresh_trail()
        q0, q1, q2, q3 = Var(), Var(), Var(), Var()
        results = solutions_simple(
            fn, q0, q1, q2, q3, trail,
            lambda: (deref(q0), deref(q1), deref(q2), deref(q3)),
        )
        assert len(results) == 2

    def test_known_solutions(self):
        """Both known 4-queens solutions are found."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("queens4", 4)
        trail = fresh_trail()
        q0, q1, q2, q3 = Var(), Var(), Var(), Var()
        results = solutions_simple(
            fn, q0, q1, q2, q3, trail,
            lambda: (deref(q0), deref(q1), deref(q2), deref(q3)),
        )
        assert (2, 4, 1, 3) in results
        assert (3, 1, 4, 2) in results


# ── Combination search ─────────────────────────────────────────────────────────
#
# colour/1 and size/1 each have 3 Var-headed clauses with Is bodies (enumeration).
# combo(C, S) :- colour(C), size(S).   — 3×3 = 9 solutions.
# Tested in both simple and trampoline modes.


class TestCombinationSearch:

    def _build_db(self, mode: str = "simple"):
        db = Database()
        compile_fn = compile_predicate if mode == "simple" else compile_predicate_trampoline

        for colour in ("red", "green", "blue"):
            cv = Var()
            db.assertz(Clause(
                head=Compound("colour", (cv,)),
                body=[Is(left=cv, right=colour)],
            ))

        for size in ("small", "medium", "large"):
            sv = Var()
            db.assertz(Clause(
                head=Compound("size", (sv,)),
                body=[Is(left=sv, right=size)],
            ))

        cx, sy = Var(), Var()
        db.assertz(Clause(
            head=Compound("combo", (cx, sy)),
            body=[
                Call(func=LoadName(name="colour"), args=[cx], kwargs=[]),
                Call(func=LoadName(name="size"), args=[sy], kwargs=[]),
            ],
        ))

        compile_fn("colour", 1, db.clauses_for("colour", 1), db)
        compile_fn("size", 1, db.clauses_for("size", 1), db)
        compile_fn("combo", 2, db.clauses_for("combo", 2), db)
        return db

    def test_nine_combinations_simple(self):
        # nv
        db = self._build_db(mode="simple")
        fn = db.get_dispatch("combo", 2)
        trail = fresh_trail()
        c, s = Var(), Var()
        results = solutions_simple(fn, c, s, trail, lambda: (deref(c), deref(s)))
        assert len(results) == 9
        assert ("red", "small") in results
        assert ("blue", "large") in results
        assert ("green", "medium") in results

    def test_nine_combinations_trampoline(self):
        # nv
        db = self._build_db(mode="trampoline")
        fn = db.get_dispatch("combo", 2)
        trail = fresh_trail()
        c, s = Var(), Var()
        results = solutions_trampoline(
            fn, (c, s, trail), lambda: (deref(c), deref(s))
        )
        assert len(results) == 9
        assert ("green", "medium") in results
        assert ("red", "large") in results

    def test_colour_filter(self):
        """colour(red) has exactly one solution (exact match)."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("colour", 1)
        trail = fresh_trail()
        results = solutions_simple(fn, "red", trail, lambda: True)
        assert results == [True]

    def test_size_enumeration(self):
        """size(S) with unbound S yields exactly 3 solutions."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("size", 1)
        trail = fresh_trail()
        s = Var()
        results = solutions_simple(fn, s, trail, lambda: deref(s))
        assert set(results) == {"small", "medium", "large"}


# ── Disjunction with multiple backtrack points ────────────────────────────────
#
# or_val(X) :- X = 10 ; X = 20 ; X = 30.
# or_pair(A, B) :- or_val(A), or_val(B).   → 9 solutions


class TestDisjunctionAndOr:

    def _build_db(self):
        db = Database()
        x = Var()
        db.assertz(Clause(
            head=Compound("or_val", (x,)),
            body=[Or(
                left=Is(left=x, right=10),
                right=Or(
                    left=Is(left=x, right=20),
                    right=Is(left=x, right=30),
                ),
            )],
        ))
        compile_predicate("or_val", 1, db.clauses_for("or_val", 1), db)

        a, b = Var(), Var()
        db.assertz(Clause(
            head=Compound("or_pair", (a, b)),
            body=[
                Call(func=LoadName(name="or_val"), args=[a], kwargs=[]),
                Call(func=LoadName(name="or_val"), args=[b], kwargs=[]),
            ],
        ))
        compile_predicate("or_pair", 2, db.clauses_for("or_pair", 2), db)
        return db

    def test_or_val_three_solutions(self):
        # nv
        db = self._build_db()
        fn = db.get_dispatch("or_val", 1)
        trail = fresh_trail()
        v = Var()
        results = solutions_simple(fn, v, trail, lambda: deref(v))
        assert results == [10, 20, 30]

    def test_or_pair_nine_solutions(self):
        # nv
        db = self._build_db()
        fn = db.get_dispatch("or_pair", 2)
        trail = fresh_trail()
        a, b = Var(), Var()
        results = solutions_simple(fn, a, b, trail, lambda: (deref(a), deref(b)))
        assert len(results) == 9
        assert (10, 10) in results
        assert (30, 30) in results
        assert (10, 30) in results

    def test_filter_by_first(self):
        """or_val(20) has exactly one solution."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("or_val", 1)
        trail = fresh_trail()
        results = solutions_simple(fn, 20, trail, lambda: True)
        assert results == [True]

    def test_nonexistent_value(self):
        """or_val(99) has no solutions."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("or_val", 1)
        trail = fresh_trail()
        results = solutions_simple(fn, 99, trail, lambda: True)
        assert results == []


# ── Negation-as-failure ────────────────────────────────────────────────────────
#
# not_red(C) :- colour(C), not colour_red(C).
# colour_red(red).
# Calling not_red(C) with C bound to "green" succeeds; with C = "red" fails.


class TestNegationAsFailure:

    def _build_db(self):
        db = Database()

        # colour("red"), colour("green"), colour("blue")
        for colour in ("red", "green", "blue"):
            cv = Var()
            db.assertz(Clause(
                head=Compound("colour_naf", (cv,)),
                body=[Is(left=cv, right=colour)],
            ))
        compile_predicate("colour_naf", 1, db.clauses_for("colour_naf", 1), db)

        # is_red(red).
        rv = Var()
        db.assertz(Clause(head=Compound("is_red", (rv,)), body=[Is(left=rv, right="red")]))
        compile_predicate("is_red", 1, db.clauses_for("is_red", 1), db)

        # not_red(C) :- colour_naf(C), not is_red(C).
        c = Var()
        db.assertz(Clause(
            head=Compound("not_red", (c,)),
            body=[
                Call(func=LoadName(name="colour_naf"), args=[c], kwargs=[]),
                Not(operand=Call(func=LoadName(name="is_red"), args=[c], kwargs=[])),
            ],
        ))
        compile_predicate("not_red", 1, db.clauses_for("not_red", 1), db)
        return db

    def test_not_red_with_green(self):
        """not_red("green") succeeds."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("not_red", 1)
        trail = fresh_trail()
        results = solutions_simple(fn, "green", trail, lambda: True)
        assert results == [True]

    def test_not_red_with_red_fails(self):
        """not_red("red") fails."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("not_red", 1)
        trail = fresh_trail()
        results = solutions_simple(fn, "red", trail, lambda: True)
        assert results == []

    def test_not_red_enumerates_two(self):
        """not_red(C) with unbound C yields green and blue (not red)."""
        # nv
        db = self._build_db()
        fn = db.get_dispatch("not_red", 1)
        trail = fresh_trail()
        c = Var()
        results = solutions_simple(fn, c, trail, lambda: deref(c))
        assert set(results) == {"green", "blue"}
        assert "red" not in results


# ── Visualizer smoke tests ─────────────────────────────────────────────────────


class TestVisualizer:
    """Smoke tests: visualizer produces valid, inspectable Python source."""

    def test_show_simple_produces_output(self, capsys):
        # nv
        from clausal.tools.visualize import show
        db = Database()
        x = Var()
        db.assertz(Clause(head=Compound("demo", (x,)), body=[Is(left=x, right=42)]))
        clauses = db.clauses_for("demo", 1)
        show("demo", 1, clauses, db)
        captured = capsys.readouterr()
        assert "def demo__1" in captured.out
        assert "yield" in captured.out

    def test_show_trampoline_produces_output(self, capsys):
        # nv
        from clausal.tools.visualize import show
        db = Database()
        x = Var()
        db.assertz(Clause(head=Compound("demo", (x,)), body=[Is(left=x, right=42)]))
        clauses = db.clauses_for("demo", 1)
        show("demo", 1, clauses, db, trampoline=True)
        captured = capsys.readouterr()
        assert "def demo__1" in captured.out
        assert "$DONE" in captured.out

    def test_source_is_valid_python(self):
        """predicate_to_source returns syntactically valid Python."""
        # nv
        from clausal.tools.visualize import predicate_to_source
        import ast as ast_mod
        db = Database()
        x, y = Var(), Var()
        db.assertz(Clause(
            head=Compound("add1", (x, y)),
            body=[Evaluate(left=y, right=Add(left=x, right=1))],
        ))
        src = predicate_to_source("add1", 2, db.clauses_for("add1", 2), db)
        tree = ast_mod.parse(src)
        fn_names = [n.name for n in ast_mod.walk(tree) if isinstance(n, ast_mod.FunctionDef)]
        assert "add1__2" in fn_names

    def test_ast_str_non_empty(self):
        """predicate_to_ast_str returns a non-empty string."""
        # nv
        from clausal.tools.visualize import predicate_to_ast_str
        db = Database()
        x = Var()
        db.assertz(Clause(head=Compound("p", (x,)), body=[]))
        s = predicate_to_ast_str("p", 1, db.clauses_for("p", 1), db)
        assert "FunctionDef" in s or "p__1" in s

    def test_visualize_fib_simple(self, capsys):
        """Show the compiled Fibonacci predicate in simple mode."""
        # nv
        from clausal.tools.visualize import show
        db = Database()
        r0 = Var()
        db.assertz(Clause(head=Compound("fib", (0, r0)), body=[Is(left=r0, right=0)]))
        r1 = Var()
        db.assertz(Clause(head=Compound("fib", (1, r1)), body=[Is(left=r1, right=1)]))
        n, r, n1, n2, ra, rb = Var(), Var(), Var(), Var(), Var(), Var()
        db.assertz(Clause(
            head=Compound("fib", (n, r)),
            body=[
                Gt(left=n, right=1),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Evaluate(left=n2, right=Sub(left=n, right=2)),
                Call(func=LoadName(name="fib"), args=[n1, ra], kwargs=[]),
                Call(func=LoadName(name="fib"), args=[n2, rb], kwargs=[]),
                Evaluate(left=r, right=Add(left=ra, right=rb)),
            ],
        ))
        show("fib", 2, db.clauses_for("fib", 2), db)
        captured = capsys.readouterr()
        assert "def fib__2" in captured.out
        assert "fib mode" in captured.out or "simple" in captured.out
