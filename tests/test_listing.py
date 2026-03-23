"""Tests for Phase 2 clause inspection builtins: Listing/1, PortrayClause/1."""

from __future__ import annotations

import io
import sys

import pytest

from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.predicate import PredicateMeta
from clausal.logic.database import Clause
from clausal.logic.exceptions import LogicException


# ── Helpers ──────────────────────────────────────────────────────────────────

def _capture_listing(pred):
    """Run Listing(pred) and return captured stdout."""
    dispatch = get_builtin_dispatch("Listing", 1, None)
    trail = Trail()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        solutions(StepGenerator(dispatch, None, pred, trail))
    finally:
        sys.stdout = old
    return buf.getvalue()


def _capture_portray(term):
    """Run PortrayClause(term) and return captured stdout."""
    dispatch = get_builtin_dispatch("PortrayClause", 1, None)
    trail = Trail()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        solutions(StepGenerator(dispatch, None, term, trail))
    finally:
        sys.stdout = old
    return buf.getvalue()


# ── Test predicates ──────────────────────────────────────────────────────────

class color(metaclass=PredicateMeta):
    _fields = ("name", "hex")

class animal(metaclass=PredicateMeta):
    _fields = ("species",)

class empty_pred(metaclass=PredicateMeta):
    _fields = ("x",)


# ── Listing/1 ────────────────────────────────────────────────────────────────

class TestListing:
    def setup_method(self):
        """Reset predicate clauses before each test."""
        color._clauses = []
        color._locked = False
        animal._clauses = []
        animal._locked = False
        empty_pred._clauses = []
        empty_pred._locked = False

    def test_no_clauses(self):
        output = _capture_listing(empty_pred)
        assert "no clauses" in output
        assert "empty_pred/1" in output

    def test_single_fact(self):
        color._assertz(Clause(color("red", "#ff0000"), []))
        output = _capture_listing(color)
        assert "color/2" in output
        assert "1 clause(s)" in output
        assert "color(" in output

    def test_multiple_facts(self):
        color._assertz(Clause(color("red", "#ff0000"), []))
        color._assertz(Clause(color("green", "#00ff00"), []))
        color._assertz(Clause(color("blue", "#0000ff"), []))
        output = _capture_listing(color)
        assert "3 clause(s)" in output

    def test_fact_with_ground_head(self):
        animal._assertz(Clause(animal("cat"), []))
        output = _capture_listing(animal)
        assert "animal(" in output
        assert "'cat'" in output

    def test_instance_resolves_to_class(self):
        """Listing with a PredicateMeta instance resolves to its class."""
        color._assertz(Clause(color("red", "#ff0000"), []))
        inst = color("red", "#ff0000")
        output = _capture_listing(inst)
        assert "color/2" in output

    def test_non_predicate_error(self):
        trail = Trail()
        dispatch = get_builtin_dispatch("Listing", 1, None)
        with pytest.raises(LogicException):
            solutions(StepGenerator(dispatch, None, 42, trail))

    def test_fact_format_ends_with_dot(self):
        animal._assertz(Clause(animal("dog"), []))
        output = _capture_listing(animal)
        lines = [l for l in output.strip().split("\n") if not l.startswith("%")]
        assert all(l.endswith(".") for l in lines if l.strip())

    def test_clause_count_in_header(self):
        color._assertz(Clause(color("red", "#ff0000"), []))
        color._assertz(Clause(color("blue", "#0000ff"), []))
        output = _capture_listing(color)
        assert "2 clause(s)" in output


# ── PortrayClause/1 ─────────────────────────────────────────────────────────

class TestPortrayClause:
    def test_simple_string(self):
        output = _capture_portray("hello")
        assert "hello" in output

    def test_integer(self):
        output = _capture_portray(42)
        assert "42" in output

    def test_list(self):
        output = _capture_portray([1, 2, 3])
        assert "1" in output
        assert "2" in output
        assert "3" in output

    def test_nested_list(self):
        output = _capture_portray([[1, 2], [3, 4]])
        assert "1" in output
        assert "4" in output

    def test_unbound_var(self):
        v = Var()
        output = _capture_portray(v)
        assert output.strip().startswith("_")
