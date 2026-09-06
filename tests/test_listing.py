"""Tests for Phase 2 clause inspection builtins: listing/1, portray_clause/1."""

from __future__ import annotations

import io
import sys

import pytest

from clausal.logic.atoms import mint
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
        assert '"cat"' in output

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
            'color("red", "#ff0000").\n'
            'color("green", "#00ff00").\n'
            'color("blue", "#0000ff").\n'
        )


# ── atom / Name-Arity indicator arguments (P3-3 Task 8, NEW) ─────────────────


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


class TestListingAtomArgument:
    """(d): an ATOM names a predicate; ``db.row(name, 0)`` backs it.

    THE FLIP: the atom is the arity-0 cell ``("greet",)``; a plain ``str``
    is a STRING and is refused (Task 12).
    """

    def test_atom_lists_the_zero_arity_predicate_by_name(self):
        db = _db_with_fact("greet", 0)
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, mint("greet"))
        assert "greet/0" in output
        assert "1 clause(s)" in output

    def test_string_name_with_no_db_raises_type_error(self):
        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException):
            _run_listing(dispatch, "greet")

    def test_atom_naming_an_absent_predicate_raises_existence_error(self):
        from clausal.logic.database import Database

        db = Database()
        dispatch = get_builtin_dispatch("listing", 1, db)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, mint("no_such_predicate"))
        err = exc_info.value.term
        # error(existence_error(procedure, Compound("/", (name, arity))), _)
        assert isinstance(err, Compound) and err.functor == "error"
        inner = err.args[0]
        assert isinstance(inner, Compound) and inner.functor == "existence_error"
        assert inner.args[0] == mint("procedure")
        indicator = inner.args[1]
        assert isinstance(indicator, Compound) and indicator.functor == "/"
        # The engine's own indicator builders carry the SPELLING in the
        # Name slot (uniformly across the tree: see test_cell_goals'
        # existence-error rows); only the type/domain NAMES are atoms.
        assert indicator.args == ("no_such_predicate", 0)


class TestListingNameArityIndicatorArgument:
    """(e): a ``Name/Arity`` indicator — the CELL shape ``('/', name,
    arity)``, or the engine-internal ``Compound`` shape other builtins in
    this package build. (A user-written ``foo/2`` in ``.clausal`` source
    compiles to neither of these: ``/`` is arithmetic, so it stays a
    runtime ``Div`` node — see ``TestListingDivIndicatorArgument`` below,
    P3-3 Task 8 fix round 1 F1.)"""

    def test_name_arity_cell_lists_the_predicate(self):
        db = _db_with_fact("pt", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, ("/", mint("pt"), 2))
        assert "pt/2" in output
        assert "1 clause(s)" in output

    def test_name_arity_compound_lists_the_predicate(self):
        db = _db_with_fact("pt", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, Compound("/", (mint("pt"), 2)))
        assert "pt/2" in output
        assert "1 clause(s)" in output

    def test_name_arity_cell_with_no_db_raises_type_error(self):
        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException):
            _run_listing(dispatch, ("/", mint("pt"), 2))

    def test_name_arity_indicator_naming_an_absent_predicate_raises_existence_error(self):
        from clausal.logic.database import Database

        db = Database()
        dispatch = get_builtin_dispatch("listing", 1, db)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, ("/", mint("no_such_predicate"), 3))
        err = exc_info.value.term
        assert isinstance(err, Compound) and err.functor == "error"
        inner = err.args[0]
        assert inner.functor == "existence_error"
        indicator = inner.args[1]
        assert indicator.args == ("no_such_predicate", 3)

    def test_name_arity_cell_with_bound_vars_in_the_slots_lists_the_predicate(self):
        """P3-3 Task 8 fix round 1 (F2): the name/arity slots are ordinary
        term slots that may hold a trail-bound Var -- unlike slot 0 of a
        str-functor cell, which the rest of the codebase's discipline reads
        RAW by design. ``('/', N, A)`` with ``N``/``A`` bound on the trail
        must resolve exactly like the ground cell."""
        db = _db_with_fact("pt", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        trail = Trail()
        name_v, arity_v = Var(), Var()
        assert unify(name_v, mint("pt"), trail)
        assert unify(arity_v, 2, trail)
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            solutions(StepGenerator(
                dispatch, None, None, None, ("/", name_v, arity_v), trail,
            ))
        finally:
            sys.stdout = old
        output = buf.getvalue()
        assert "pt/2" in output
        assert "1 clause(s)" in output

    def test_name_arity_compound_with_bound_vars_in_the_slots_lists_the_predicate(self):
        db = _db_with_fact("pt", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        trail = Trail()
        name_v, arity_v = Var(), Var()
        assert unify(name_v, mint("pt"), trail)
        assert unify(arity_v, 2, trail)
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            solutions(StepGenerator(
                dispatch, None, None, None,
                Compound("/", (name_v, arity_v)), trail,
            ))
        finally:
            sys.stdout = old
        output = buf.getvalue()
        assert "pt/2" in output
        assert "1 clause(s)" in output


class TestListingDivIndicatorArgument:
    """(f), P3-3 Task 8 fix round 1 (F1): a runtime ``Div`` node
    (``clausal.pythonic_ast.nodes.Div``) is what a user-written ``foo/2``
    ACTUALLY compiles to in ``.clausal`` source today -- ``/`` is the
    arithmetic operator, so a structural (non-``is``) use of it stays a
    reified operator term rather than a cell or a ``Compound``. The earlier
    round's docs/comments claimed ``foo/2`` compiled to the cell; it does
    not, and this class + ``tests/fixtures/listing_div_indicator.clausal``
    pin what actually happens, byte-identically, plus the rejection case."""

    def test_div_of_an_atom_name_and_int_lists_the_predicate(self):
        """The runtime shape ``Div(left=<atom>, right=int)`` -- what
        ``pt / 2`` compiles to when the left operand is a name that did NOT
        resolve to a predicate class (see
        ``test_div_of_a_predicate_class_lists_the_predicate`` below for the
        class-left shape).  Task 12: the name half is an ATOM, so a plain
        ``str`` there is a string and is refused."""
        from clausal.terms import Div

        db = _db_with_fact("pt", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, Div(left=mint("pt"), right=2))
        assert "pt/2" in output
        assert "1 clause(s)" in output

    def test_div_of_a_predicate_class_lists_the_predicate(self):
        """The runtime shape ``Div(left=<PredicateMeta class>, right=int)``
        -- what ``fib/2`` compiles to when ``fib`` is a declared predicate
        in the calling module (probed and reproduced directly here without
        compiling a module; the end-to-end compiled case is pinned by
        ``test_div_end_to_end_matches_class_form_byte_identically``)."""
        from clausal.terms import Div
        from clausal.logic.predicate import make_predicate

        db = _db_with_fact("qr", 1)
        cls = make_predicate("qr", ["x"])
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, Div(left=cls, right=1))
        assert "qr/1" in output
        assert "1 clause(s)" in output

    def test_div_end_to_end_matches_class_form_byte_identically(self):
        """Compile a real ``.clausal`` module and drive ``listing(fib/2)``
        (the doc's exact form) against it -- output must be byte-identical
        to ``listing(fib)`` (the class form) for the SAME predicate."""
        import io as _io
        import sys as _sys
        import tests.fixtures.listing_div_indicator as mod
        from clausal.logic.database import Module
        from clausal.logic.solve import call

        db = mod.__clausal_module__.db
        m = Module("_t8_div_e2e", db=db)

        def _capture(name):
            buf = _io.StringIO()
            saved = _sys.stdout
            _sys.stdout = buf
            try:
                list(call(name, module=m))
            finally:
                _sys.stdout = saved
            return buf.getvalue()

        out_class = _capture("DebugFibByClass")
        out_indicator = _capture("DebugFibByIndicator")
        assert out_indicator == out_class
        assert "fib/2" in out_class
        assert "3 clause(s)" in out_class

    def test_div_with_a_plain_int_left_operand_raises_type_error(self):
        """``3/2`` -- no predicate-denoting operand -- is genuine
        arithmetic, not an indicator, and must still raise ``type_error``
        exactly as an unrecognized shape always has."""
        from clausal.terms import Div

        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, Div(left=3, right=2))
        err = exc_info.value.term
        assert isinstance(err, Compound) and err.functor == "error"
        inner = err.args[0]
        assert inner.functor == "type_error"
        # The culprit is the actual Div INSTANCE, not (as an earlier,
        # buggy ordering produced) the Div CLASS -- see the
        # is_indicator_shaped gate in io.py.
        culprit = inner.args[1]
        assert isinstance(culprit, Div)
        assert culprit.left == 3 and culprit.right == 2

    def test_div_with_a_non_int_right_operand_raises_type_error(self):
        """``fib/"oops"`` -- a predicate-denoting (atom) left operand but a
        non-int right operand -- is not a valid arity and must raise."""
        from clausal.terms import Div

        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException):
            _run_listing(dispatch, Div(left=mint("fib"), right="oops"))


class TestListingAnImportedPredicateByIndicator:
    """Final review M-a.  An ``-import_from`` binds the EXPORTER's class, whose
    clauses live on the exporter's row, so reducing the indicator's left
    operand to ``__name__`` and looking that name up in the CALLING database
    found nothing: ``listing(qq)`` worked while ``listing(qq/1)`` and
    ``listing("qq"/1)`` raised ``existence_error`` for a predicate the caller
    can see and call.  All three spellings name one predicate and must print
    one thing."""

    @staticmethod
    def _capture(module, goal_name):
        import io as _io
        import sys as _sys
        from clausal.logic.database import Module
        from clausal.logic.solve import call

        m = Module("_ma_listing", db=module.__clausal_module__.db)
        buf = _io.StringIO()
        saved = _sys.stdout
        _sys.stdout = buf
        try:
            list(call(goal_name, module=m))
        finally:
            _sys.stdout = saved
        return buf.getvalue()

    def test_all_three_spellings_are_byte_identical_from_the_importer(self):
        import tests.fixtures.listing_import_user as user

        by_name = self._capture(user, "ListByName")
        assert "qq/1" in by_name and "2 clause(s)" in by_name
        assert self._capture(user, "ListByClassIndicator") == by_name
        assert self._capture(user, "ListByStrIndicator") == by_name


class TestListingIndicatorInstantiation:
    """Final review M-a: an indicator-SHAPED term with an unbound operand is
    not a malformed indicator, it is an unfinished one.  ``type_error`` said
    "``/`` is the wrong sort of term here" when the term is right and only the
    variable is missing."""

    def _instantiation_error_for(self, val):
        from clausal.logic.database import Database

        dispatch = get_builtin_dispatch("listing", 1, Database())
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, val)
        return exc_info.value.term

    def test_an_unbound_left_operand_is_an_instantiation_error(self):
        from clausal.terms import Div

        err = self._instantiation_error_for(Div(left=Var(), right=2))
        assert err.functor == "error"
        assert err.args[0] == mint("instantiation_error")
        assert "listing/1" in err.args[1]

    def test_an_unbound_arity_is_an_instantiation_error_too(self):
        err = self._instantiation_error_for(("/", "pt", Var()))
        assert err.args[0] == mint("instantiation_error")

    def test_a_bound_but_wrong_operand_is_still_a_type_error(self):
        """Only the UNBOUND case moved: ``3/2`` and ``fib/"oops"`` are
        well-instantiated and genuinely the wrong shape."""
        from clausal.terms import Div

        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, Div(left=3, right=2))
        assert exc_info.value.term.args[0].functor == "type_error"


class TestListingSpecializedAliasByIndicator:
    """P3-3 Task 7's ``-specialize`` alias (``SolveCountNatnum/2``, 3
    clauses — Task 7's own review confirmed the row) listed through its
    ``Name/Arity`` cell, exercising ``listing/1`` against a REAL module
    database rather than a hand-built one."""

    def test_specialize_natnum_alias_lists_via_name_arity_cell(self):
        import tests.fixtures.specialize_natnum as specialize_natnum

        db = specialize_natnum.__clausal_module__.db
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, ("/", mint("SolveCountNatnum"), 2))
        assert "SolveCountNatnum/2" in output
        assert "3 clause(s)" in output


class TestListingBuiltinClassHasDispatch:
    """P3-3 Task 8 fix round 1 (F3): ``_db_optional`` on the ``listing``
    factory is LOAD-BEARING, not a consistency nicety --
    ``_build_all_builtin_classes()`` (called once at
    ``clausal.logic.builtins`` import time) calls
    ``_stateless_dispatch("listing", 1)`` to populate
    ``_BUILTIN_CLASSES["listing"]._dispatch_fn``; without the flag that
    call returns ``None`` and the builtin CLASS (as opposed to the
    ``get_builtin_dispatch`` path the rest of this file drives) is left with
    no dispatch at all -- a regression from BASE, where ``listing`` lived in
    ``_BUILTINS`` and ``_stateless_dispatch`` answered it unconditionally.
    Pinning this so the ``_db_optional`` line cannot be deleted silently."""

    def test_builtin_class_has_a_dispatch_fn(self):
        from clausal.logic.builtins._registry import _BUILTIN_CLASSES

        cls = _BUILTIN_CLASSES["listing"]
        assert cls._dispatch_fn is not None

    def test_stateless_dispatch_answers_for_listing(self):
        from clausal.logic.builtins._registry import _stateless_dispatch

        assert _stateless_dispatch("listing", 1) is not None


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
        assert result == 'Compound("foo", (1, 2), None)'
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
