"""ISO Prolog conformity: dynamic database (assert/retract).

ISO §8.9.1 — asserta/1
ISO §8.9.2 — assertz/1
ISO §8.9.3 — retract/1
ISO §8.9.4 — abolish/1

Clausal equivalents:
  asserta/1 → asserta(Clause)
  assertz/1 → assertz(Clause)
  retract/1 → retract(head)  — matches by clause.head == head

Not available:
  abolish/1     → no equivalent
  retractall/1  → no builtin
  assert/1      → deprecated; use assertz/1

Differences from ISO:
  - Prolog: assertz((foo(X) :- bar(X))).
    Clausal: db.assertz(Clause(head=..., body=[...]))
  - Dynamic predicates need recompilation after assert/retract.
    Clausal handles this via lazy recompile.
  - Prolog retract/1 does pattern matching on clause head+body.
    Clausal retract matches on the head term by equality.
  - retract requires exact head match including any Var objects — not
    pattern matching.  Practical retract is done by removing by index
    or using clauses_for() to find and remove.
"""

from __future__ import annotations

import pytest
from clausal.logic.database import Clause, Module
from clausal.logic.compiler import compile_predicate
from clausal.logic.solve import solve, once, call
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound, Unify as Is, Call, LoadName


def _make_module_with_facts(name, functor, facts):
    """Create a module with ground facts.

    facts: list of tuples, each tuple is the args for the functor.
    """
    mod = Module(name)
    db = mod.db
    for fact_args in facts:
        vars_ = tuple(Var() for _ in fact_args)
        body = [Is(left=v, right=val) for v, val in zip(vars_, fact_args)]
        db.assertz(Clause(
            head=Compound(functor, vars_),
            body=body,
        ))
    compile_predicate(functor, len(facts[0]), db.clauses_for(functor, len(facts[0])), db)
    return mod


# ── assertz/1 ────────────────────────────────────────────────────────────────


class TestAssertz:
    """ISO §8.9.2 — assertz/1."""

    def test_assertz_adds_at_end(self):
        """Facts asserted with assertz appear in order."""
        mod = _make_module_with_facts("test", "color", [("red",), ("green",)])

        x = Var()
        results_before = [
            deref(x) for _ in call("color", x, module=mod)
        ]
        assert results_before == ["red", "green"]

        # assertz a new fact
        db = mod.db
        v = Var()
        db.assertz(Clause(
            head=Compound("color", (v,)),
            body=[Is(left=v, right="blue")],
        ))
        compile_predicate("color", 1, db.clauses_for("color", 1), db)

        x2 = Var()
        results_after = [
            deref(x2) for _ in call("color", x2, module=mod)
        ]
        assert results_after == ["red", "green", "blue"]

    def test_assertz_new_predicate(self):
        """assertz can create a predicate that didn't exist."""
        mod = Module("test")
        db = mod.db

        v = Var()
        db.assertz(Clause(
            head=Compound("greeting", (v,)),
            body=[Is(left=v, right="hello")],
        ))
        compile_predicate("greeting", 1, db.clauses_for("greeting", 1), db)

        x = Var()
        results = [deref(x) for _ in call("greeting", x, module=mod)]
        assert results == ["hello"]

    def test_assertz_multiple(self):
        """Multiple assertz calls accumulate in order."""
        mod = Module("test")
        db = mod.db
        for val in [1, 2, 3, 4, 5]:
            v = Var()
            db.assertz(Clause(
                head=Compound("num", (v,)),
                body=[Is(left=v, right=val)],
            ))
        compile_predicate("num", 1, db.clauses_for("num", 1), db)

        x = Var()
        results = [deref(x) for _ in call("num", x, module=mod)]
        assert results == [1, 2, 3, 4, 5]


# ── asserta/1 ────────────────────────────────────────────────────────────────


class TestAsserta:
    """ISO §8.9.1 — asserta/1."""

    def test_asserta_adds_at_front(self):
        """Facts asserted with asserta appear before existing clauses."""
        mod = _make_module_with_facts("test", "item", [("b",), ("c",)])

        db = mod.db
        v = Var()
        db.asserta(Clause(
            head=Compound("item", (v,)),
            body=[Is(left=v, right="a")],
        ))
        compile_predicate("item", 1, db.clauses_for("item", 1), db)

        x = Var()
        results = [deref(x) for _ in call("item", x, module=mod)]
        assert results == ["a", "b", "c"]


# ── retract/1 ────────────────────────────────────────────────────────────────


class TestRetract:
    """ISO §8.9.3 — retract/1.

    Clausal's retract matches by clause.head == head (identity match on
    the head term).  This differs from Prolog's pattern-based retract.
    We test by retrieving clauses, finding the one to remove, and
    retracting it by its actual head object.
    """

    def test_retract_by_head_reference(self):
        """Retract a clause by its stored head reference."""
        mod = Module("test")
        db = mod.db
        for val in [1, 2, 3]:
            v = Var()
            db.assertz(Clause(
                head=Compound("num", (v,)),
                body=[Is(left=v, right=val)],
            ))
        compile_predicate("num", 1, db.clauses_for("num", 1), db)

        # Retract the second clause (value=2) by its stored head
        clauses = db.clauses_for("num", 1)
        assert len(clauses) == 3
        head_to_remove = clauses[1].head
        removed = db.retract(head_to_remove)
        assert removed

        compile_predicate("num", 1, db.clauses_for("num", 1), db)

        x = Var()
        results = [deref(x) for _ in call("num", x, module=mod)]
        assert 2 not in results
        assert 1 in results
        assert 3 in results

    def test_retract_first_clause(self):
        """Retract the first clause."""
        mod = Module("test")
        db = mod.db
        for val in ["a", "b", "c"]:
            v = Var()
            db.assertz(Clause(
                head=Compound("letter", (v,)),
                body=[Is(left=v, right=val)],
            ))
        compile_predicate("letter", 1, db.clauses_for("letter", 1), db)

        # Retract first clause
        head_to_remove = db.clauses_for("letter", 1)[0].head
        db.retract(head_to_remove)
        compile_predicate("letter", 1, db.clauses_for("letter", 1), db)

        x = Var()
        results = [deref(x) for _ in call("letter", x, module=mod)]
        assert results == ["b", "c"]

    def test_retract_all_clauses(self):
        """Retracting all clauses means the predicate has no solutions."""
        mod = Module("test")
        db = mod.db
        v = Var()
        db.assertz(Clause(
            head=Compound("single", (v,)),
            body=[Is(left=v, right=42)],
        ))
        compile_predicate("single", 1, db.clauses_for("single", 1), db)

        # Retract the only clause
        head = db.clauses_for("single", 1)[0].head
        db.retract(head)

        clauses = db.clauses_for("single", 1)
        assert clauses == []
