"""Tests for Phase 2 clause inspection builtins: listing/1, portray_clause/1."""

from __future__ import annotations

import io
import sys

import pytest

from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.builtins.io import _format_clause_head
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.predicate import PredicateMeta
from clausal.logic.database import Clause
from clausal.logic.exceptions import LogicException
from clausal.terms import Compound


# ── Helpers ──────────────────────────────────────────────────────────────────

def _capture_listing(pred):
    """Run listing(pred) and return captured stdout."""
    dispatch = get_builtin_dispatch("listing", 1, None)
    trail = Trail()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        solutions(StepGenerator(dispatch, None, None, None, pred, trail))
    finally:
        sys.stdout = old
    return buf.getvalue()


def _capture_portray(term):
    """Run portray_clause(term) and return captured stdout."""
    dispatch = get_builtin_dispatch("portray_clause", 1, None)
    trail = Trail()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        solutions(StepGenerator(dispatch, None, None, None, term, trail))
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


# ── listing/1 ────────────────────────────────────────────────────────────────

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
        # nv
        output = _capture_listing(empty_pred)
        assert "no clauses" in output
        assert "empty_pred/1" in output

    def test_single_fact(self):
        # nv
        color._assertz(Clause(color("red", "#ff0000"), []))
        output = _capture_listing(color)
        assert "color/2" in output
        assert "1 clause(s)" in output
        assert "color(" in output

    def test_multiple_facts(self):
        # nv
        color._assertz(Clause(color("red", "#ff0000"), []))
        color._assertz(Clause(color("green", "#00ff00"), []))
        color._assertz(Clause(color("blue", "#0000ff"), []))
        output = _capture_listing(color)
        assert "3 clause(s)" in output

    def test_fact_with_ground_head(self):
        # nv
        animal._assertz(Clause(animal("cat"), []))
        output = _capture_listing(animal)
        assert "animal(" in output
        assert "'cat'" in output

    def test_instance_resolves_to_class(self):
        """listing with a PredicateMeta instance resolves to its class."""
        # nv
        color._assertz(Clause(color("red", "#ff0000"), []))
        inst = color("red", "#ff0000")
        output = _capture_listing(inst)
        assert "color/2" in output

    def test_non_predicate_error(self):
        # nv
        trail = Trail()
        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException):
            solutions(StepGenerator(dispatch, None, None, None, 42, trail))

    def test_fact_format_ends_with_dot(self):
        # nv
        animal._assertz(Clause(animal("dog"), []))
        output = _capture_listing(animal)
        lines = [l for l in output.strip().split("\n") if not l.startswith("%")]
        assert all(l.endswith(".") for l in lines if l.strip())

    def test_clause_count_in_header(self):
        # nv
        color._assertz(Clause(color("red", "#ff0000"), []))
        color._assertz(Clause(color("blue", "#0000ff"), []))
        output = _capture_listing(color)
        assert "2 clause(s)" in output


# ── Golden: byte-identical output for a class argument (P3-3 Task 8) ─────────
#
# Pinned at BASE (commit 4687fc18), before ``listing/1`` moved from a class-
# reading (``val._clauses`` off a ``PredicateMeta``) builtin to a db-receiving
# one that also accepts a bare str atom and a ``Name/Arity`` cell (P3-3 Task
# 8's new (d)/(e) argument shapes). The class-argument path must keep
# printing this EXACT text — not just "contains the right substrings" like
# the tests above — across that migration.


class TestListingClassArgumentGoldenOutput:
    def test_multi_clause_class_output_is_byte_identical(self):
        color._clauses = []
        color._locked = False
        color._assertz(Clause(color("red", "#ff0000"), []))
        color._assertz(Clause(color("green", "#00ff00"), []))
        color._assertz(Clause(color("blue", "#0000ff"), []))
        output = _capture_listing(color)
        assert output == (
            "% color/2 — 3 clause(s)\n"
            "color('red', '#ff0000').\n"
            "color('green', '#00ff00').\n"
            "color('blue', '#0000ff').\n"
        )


# ── str atom / Name-Arity indicator arguments (P3-3 Task 8, NEW) ─────────────


def _run_listing(dispatch, pred):
    """Drive an already-resolved ``listing/1`` dispatch fn and return stdout."""
    trail = Trail()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        solutions(StepGenerator(dispatch, None, None, None, pred, trail))
    finally:
        sys.stdout = old
    return buf.getvalue()


def _db_with_fact(name, arity):
    from clausal.logic.database import Database

    db = Database()
    head = Compound(name, tuple(Var() for _ in range(arity)))
    db.assertz(Clause(head, []))
    return db


class TestListingStrAtomArgument:
    """(d): a bare str atom names a predicate; ``db.row(name, 0)`` backs it."""

    def test_str_atom_lists_the_zero_arity_predicate_by_name(self):
        db = _db_with_fact("greet", 0)
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, "greet")
        assert "greet/0" in output
        assert "1 clause(s)" in output

    def test_str_atom_with_no_db_raises_type_error(self):
        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException):
            _run_listing(dispatch, "greet")

    def test_str_atom_naming_an_absent_predicate_raises_existence_error(self):
        from clausal.logic.database import Database

        db = Database()
        dispatch = get_builtin_dispatch("listing", 1, db)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, "no_such_predicate")
        err = exc_info.value.term
        # error(existence_error(procedure, Compound("/", (name, arity))), _)
        assert isinstance(err, Compound) and err.functor == "error"
        inner = err.args[0]
        assert isinstance(inner, Compound) and inner.functor == "existence_error"
        assert inner.args[0] == "procedure"
        indicator = inner.args[1]
        assert isinstance(indicator, Compound) and indicator.functor == "/"
        assert indicator.args == ("no_such_predicate", 0)


class TestListingNameArityIndicatorArgument:
    """(e): a ``Name/Arity`` indicator, either the default cell shape a
    user-written ``foo/2`` compiles to, or the engine-internal ``Compound``
    shape other builtins in this package build."""

    def test_name_arity_cell_lists_the_predicate(self):
        db = _db_with_fact("pt", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, ("/", "pt", 2))
        assert "pt/2" in output
        assert "1 clause(s)" in output

    def test_name_arity_compound_lists_the_predicate(self):
        db = _db_with_fact("pt", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, Compound("/", ("pt", 2)))
        assert "pt/2" in output
        assert "1 clause(s)" in output

    def test_name_arity_cell_with_no_db_raises_type_error(self):
        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException):
            _run_listing(dispatch, ("/", "pt", 2))

    def test_name_arity_indicator_naming_an_absent_predicate_raises_existence_error(self):
        from clausal.logic.database import Database

        db = Database()
        dispatch = get_builtin_dispatch("listing", 1, db)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, ("/", "no_such_predicate", 3))
        err = exc_info.value.term
        assert isinstance(err, Compound) and err.functor == "error"
        inner = err.args[0]
        assert inner.functor == "existence_error"
        indicator = inner.args[1]
        assert indicator.args == ("no_such_predicate", 3)


class TestListingSpecializedAliasByIndicator:
    """P3-3 Task 7's ``-specialize`` alias (``SolveCountNatnum/2``, 3
    clauses — Task 7's own review confirmed the row) listed through its
    ``Name/Arity`` cell, exercising ``listing/1`` against a REAL module
    database rather than a hand-built one."""

    def test_specialize_natnum_alias_lists_via_name_arity_cell(self):
        import tests.fixtures.specialize_natnum as specialize_natnum

        db = specialize_natnum.__clausal_module__.db
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, ("/", "SolveCountNatnum", 2))
        assert "SolveCountNatnum/2" in output
        assert "3 clause(s)" in output


# ── _format_clause_head / Compound heads ─────────────────────────────────────
#
# functor_arity() (clausal/logic/builtins/_helpers.py) treats a Compound as a
# term shape it resolves directly, in preference to falling through to the
# generic is_term_instance()/type name path.  _format_clause_head must NOT
# route a Compound head through functor_arity(): a str-functor Compound would
# then print its functor name instead of "Compound(...)", and a var-functor
# Compound makes functor_arity() return None, which crashes the 2-tuple
# unpack.  These pin the pre-funnel behavior: the type name, not the funneled
# functor, is what a Compound head prints as.

class TestFormatClauseHeadCompound:
    def test_str_functor_compound_prints_type_name(self):
        head = Compound("foo", (1, 2))
        result = _format_clause_head(head)
        # Old shape: "Compound(<functor repr>, <args repr>, <position repr>)"
        # — the funneled functor ("foo") must NOT stand in for the type name.
        assert result == "Compound('foo', (1, 2), None)"
        assert not result.startswith("foo(")

    def test_var_functor_compound_does_not_crash(self):
        head = Compound(Var(), (1, 2))
        result = _format_clause_head(head)
        assert result.startswith("Compound(")
        assert "(1, 2)" in result


# ── Cell-valued clause arguments (P3-2 Task 7) ────────────────────────────────
#
# ``_format_clause_term`` fell to plain ``str(val)`` for any value it did not
# specially recognize -- correct for a ``Compound`` (which has its own
# ``__str__``) but wrong for a CELL, a plain tuple with no custom ``__str__``,
# so ``str()`` on it is the Python tuple repr: an argument like
# ``("rgb", 255, 0, 0)`` printed ``('rgb', 255, 0, 0)`` in listing/1 output
# instead of ``rgb(255, 0, 0)``.

class TestCellValuedClauseArgument:
    def test_format_clause_term_renders_a_cell_as_a_term(self):
        from clausal.logic.builtins.io import _format_clause_term

        assert _format_clause_term(("rgb", 255, 0, 0)) == "rgb(255, 0, 0)"

    def test_format_clause_term_renders_a_tuple_data_cell_as_a_plain_tuple(self):
        from clausal.logic.builtins.io import _format_clause_term
        from clausal.logic.cells import TUPLE_TAG

        assert _format_clause_term((TUPLE_TAG, 1, 2)) == "(1, 2)"

    def test_listing_prints_a_cell_valued_field_as_a_term_not_a_repr(self):
        color._clauses = []
        color._locked = False
        color._assertz(Clause(color("red", ("rgb", 255, 0, 0)), []))
        output = _capture_listing(color)
        assert "rgb(255, 0, 0)" in output
        assert "('rgb'" not in output


# ── portray_clause/1 ─────────────────────────────────────────────────────────

class TestPortrayClause:
    def test_simple_string(self):
        # nv
        output = _capture_portray("hello")
        assert "hello" in output

    def test_integer(self):
        # nv
        output = _capture_portray(42)
        assert "42" in output

    def test_list(self):
        # nv
        output = _capture_portray([1, 2, 3])
        assert "1" in output
        assert "2" in output
        assert "3" in output

    def test_nested_list(self):
        # nv
        output = _capture_portray([[1, 2], [3, 4]])
        assert "1" in output
        assert "4" in output

    def test_unbound_var(self):
        # nv
        v = Var()
        output = _capture_portray(v)
        assert output.strip().startswith("_")
