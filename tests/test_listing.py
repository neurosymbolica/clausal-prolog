"""Tests for Phase 2 clause inspection builtins: listing/1, portray_clause/1."""

from __future__ import annotations

import io
import sys

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
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
        color._state_row().clauses = []
        color._state_row().locked = False
        animal._state_row().clauses = []
        animal._state_row().locked = False
        empty_pred._state_row().clauses = []
        empty_pred._state_row().locked = False

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

    def test_a_compound_cell_is_not_a_predicate_indicator(self):
        """FLIPPED 2026-09-25 -- Operator ruling 2026-09-25 ("do what Scryer does").

        This used to be ``test_a_cell_resolves_to_its_predicate``: the
        compound ``color(red, ...)`` listed ``color/2``.  Scryer's
        ``listing/1`` accepts only ``Name/Arity`` and ``Name//Arity``; a
        compound term is ``type_error(predicate_indicator, PI)``.
        """
        db = _db_with_fact("color", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        cell = ("color", "red", "#ff0000")
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, cell)
        formal = _formal(exc_info)
        assert formal.functor == "type_error"
        assert formal.args == (mint("predicate_indicator"), cell)

    def test_a_term_instance_is_named_as_itself_not_its_class(self):
        """``listing(Compound("foo", (1,)))``: a term INSTANCE is not an
        indicator either, and the refusal's culprit is the term PASSED --
        the Python-object arm swapped it for ``type(val)`` before raising,
        so the error named the ``Compound`` CLASS (roborev Low, 2026-09-25)."""
        db = _db_with_fact("color", 2)
        dispatch = get_builtin_dispatch("listing", 1, db)
        term = Compound("foo", (1,))
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, term)
        formal = _formal(exc_info)
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("predicate_indicator")
        assert formal.args[1] is term

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
# reading (``val._clauses`` off a ``PredicateMeta``, then) builtin to a db-receiving
# one that also accepts a bare str atom and a ``Name/Arity`` cell (P3-3 Task
# 8's new (d)/(e) argument shapes). The class-argument path must keep
# printing this EXACT text — not just "contains the right substrings" like
# the tests above — across that migration.


class TestListingClassArgumentGoldenOutput:
    def test_multi_clause_class_output_is_byte_identical(self):
        color._state_row().clauses = []
        color._state_row().locked = False
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


def _listing_answers(dispatch, pred):
    """``(number of answers, stdout)`` of one ``listing/1`` call -- the
    Scryer-contract cases FAIL (zero answers) and print nothing."""
    trail = Trail()
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        n = len(list(solutions(
            StepGenerator(dispatch, None, None, None, pred, trail))))
    finally:
        sys.stdout = old
    return n, buf.getvalue()


def _formal(exc_info):
    """The formal term of a caught ``error(Formal, Context)``."""
    err = exc_info.value.term
    assert isinstance(err, Compound) and err.functor == "error"
    return err.args[0]


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

    def test_a_bare_atom_is_not_a_predicate_indicator(self):
        """FLIPPED 2026-09-25 -- Operator ruling 2026-09-25 ("do what Scryer does").

        This used to be ``test_atom_lists_the_zero_arity_predicate_by_name``
        (``listing(greet)`` listed ``greet/0``).  Scryer:
        ``listing(fib)`` is ``type_error(predicate_indicator, fib)`` -- even
        when ``greet/0`` exists.  ``listing(greet/0)`` is the spelling."""
        db = _db_with_fact("greet", 0)
        dispatch = get_builtin_dispatch("listing", 1, db)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, mint("greet"))
        formal = _formal(exc_info)
        assert formal.functor == "type_error"
        assert formal.args == (mint("predicate_indicator"), mint("greet"))
        n, output = _listing_answers(dispatch, ("/", mint("greet"), 0))
        assert n == 1 and "greet/0" in output and "1 clause(s)" in output

    def test_string_name_with_no_db_raises_type_error(self):
        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException):
            _run_listing(dispatch, "greet")

    def test_atom_naming_an_absent_predicate_is_still_a_type_error(self):
        """FLIPPED 2026-09-25 -- Operator ruling 2026-09-25 ("do what Scryer does").  Was an ``existence_error`` for
        ``no_such_predicate/0``; Scryer refuses the SHAPE before it looks
        anything up, so a bare atom is ``type_error(predicate_indicator)``
        whether or not anything of that name exists."""
        from clausal.logic.database import Database

        db = Database()
        dispatch = get_builtin_dispatch("listing", 1, db)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, mint("no_such_predicate"))
        formal = _formal(exc_info)
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("predicate_indicator")


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

    def test_name_arity_cell_with_no_db_fails(self):
        """FLIPPED 2026-09-25 -- Operator ruling 2026-09-25 ("do what Scryer does").  Was a ``type_error``: with no
        database the indicator names no clauses, and Scryer's
        ``\\+ \\+ clause(Head, _)`` guard FAILS for that."""
        dispatch = get_builtin_dispatch("listing", 1, None)
        assert _listing_answers(dispatch, ("/", mint("pt"), 2)) == (0, "")

    def test_name_arity_indicator_naming_an_absent_predicate_fails(self):
        """FLIPPED 2026-09-25 -- Operator ruling 2026-09-25 ("do what Scryer does").  Was ``existence_error(procedure,
        no_such_predicate/3)``.  Scryer: ``listing(nosuch/1)`` FAILS, and
        so does an indicator naming a predicate with no clauses
        (``:- dynamic(d/1)``, ``listing(d/1)``)."""
        from clausal.logic.database import Database

        db = Database()
        dispatch = get_builtin_dispatch("listing", 1, db)
        assert _listing_answers(
            dispatch, ("/", mint("no_such_predicate"), 3)) == (0, "")
        db.mark_dynamic("dyn_empty", 1)
        assert db.row("dyn_empty", 1, create=True).clauses == []
        assert _listing_answers(dispatch, ("/", mint("dyn_empty"), 1)) == (0, "")

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

        # The CLASS form is passed from Python: in source, ``listing(fib)``
        # passes the plain ATOM ``fib`` (ruling S, 2026-09-24), which is
        # type_error(predicate_indicator, fib) since 2026-09-25 (Scryer).
        buf = _io.StringIO()
        saved = _sys.stdout
        _sys.stdout = buf
        try:
            list(call("listing", mod.fib, module=m))
        finally:
            _sys.stdout = saved
        out_class = buf.getvalue()
        out_indicator = _capture("debug_fib_by_indicator")
        assert out_indicator == out_class
        # Operator ruling 2026-09-25: the source spelling ``fib // 0``
        # (Scryer's Name//Arity) names fib/2 -- the same listing.
        assert _capture("debug_fib_by_nonterminal") == out_class
        assert "fib/2" in out_class
        assert "3 clause(s)" in out_class

    def test_div_with_a_plain_int_left_operand_raises_type_error_atom(self):
        """UPDATED 2026-09-25 -- Operator ruling 2026-09-25 ("do what Scryer does").  ``3/2`` IS ``Name/Arity``-shaped, so
        Scryer hands it to ``functor(Head, 3, 2)``, whose error is
        ``type_error(atom, 3)`` (the culprit is the NAME operand, not the
        whole ``Div`` as before)."""
        from clausal.terms import Div

        dispatch = get_builtin_dispatch("listing", 1, None)
        with pytest.raises(LogicException) as exc_info:
            _run_listing(dispatch, Div(left=3, right=2))
        formal = _formal(exc_info)
        assert formal.functor == "type_error"
        assert formal.args == (mint("atom"), 3)

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

        by_name = self._capture(user, "list_by_name")
        assert "qq/1" in by_name and "2 clause(s)" in by_name
        assert self._capture(user, "list_by_class_indicator") == by_name
        assert self._capture(user, "list_by_str_indicator") == by_name


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
    """P3-3 Task 7's ``-specialize`` alias (``solve_count_natnum/2``, 3
    clauses — Task 7's own review confirmed the row) listed through its
    ``Name/Arity`` cell, exercising ``listing/1`` against a REAL module
    database rather than a hand-built one."""

    def test_specialize_natnum_alias_lists_via_name_arity_cell(self):
        import tests.fixtures.specialize_natnum as specialize_natnum

        db = specialize_natnum.__clausal_module__.db
        dispatch = get_builtin_dispatch("listing", 1, db)
        output = _run_listing(dispatch, ("/", mint("solve_count_natnum"), 2))
        assert "solve_count_natnum/2" in output
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

        obj = _BUILTIN_CLASSES["listing"]
        # A ``BuiltinTerm`` since W4b-3 slice 3 (a class with a private row
        # before): the db-free dispatch it holds at arity 1.
        assert obj._dispatch_by_arity.get(1) is not None
        assert obj._get_dispatch() is not None

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
        color._state_row().clauses = []
        color._state_row().locked = False
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


class TestListingFollowsScryersContract:
    """Operator ruling 2026-09-25: "do what Scryer does".  Scryer's
    ``listing/1`` (library(format))::

        listing(PI) :-
                nonvar(PI),
                (   PI = Name/Arity0 -> Arity = Arity0
                ;   PI = Name//Arity0 -> Arity is Arity0 + 2
                ;   type_error(predicate_indicator, PI, listing/1)
                ),
                functor(Head, Name, Arity),
                \\+ \\+ clause(Head, _),
                ...

    Every expected term below was observed on Scryer (2026-09-25) for the
    same argument; the ``functor/3`` errors carry Clausal's own context."""

    @staticmethod
    def _dispatch():
        return get_builtin_dispatch("listing", 1, _db_with_fact("greet", 2))

    def test_an_unbound_argument_fails(self):
        assert _listing_answers(self._dispatch(), Var()) == (0, "")

    @pytest.mark.parametrize("pi", [
        chars("greet"), 42, ("greet", 1, 2), [mint("greet")],
    ], ids=["string", "number", "compound", "list"])
    def test_a_non_indicator_is_a_predicate_indicator_type_error(self, pi):
        with pytest.raises(LogicException) as exc_info:
            _run_listing(self._dispatch(), pi)
        formal = _formal(exc_info)
        assert formal.functor == "type_error"
        assert formal.args == (mint("predicate_indicator"), pi)

    @pytest.mark.parametrize("pi", [
        lambda: ("/", Var(), 2), lambda: ("/", mint("greet"), Var()),
        lambda: ("//", mint("greet"), Var()),
    ], ids=["name", "arity", "dcg-arity"])
    def test_an_unbound_operand_is_an_instantiation_error(self, pi):
        with pytest.raises(LogicException) as exc_info:
            _run_listing(self._dispatch(), pi())
        assert exc_info.value.term.args[0] == mint("instantiation_error")

    @pytest.mark.parametrize("pi, formal", [
        (("/", mint("greet"), mint("x")), ("type_error", "integer", "x")),
        (("/", mint("greet"), -1),
         ("domain_error", "not_less_than_zero", -1)),
        (("/", chars("greet"), 2), ("type_error", "atomic", None)),
        (("/", 3, 2), ("type_error", "atom", 3)),
    ], ids=["non-integer arity", "negative arity", "string name",
            "number name"])
    def test_a_malformed_operand_is_functor_3s_error(self, pi, formal):
        with pytest.raises(LogicException) as exc_info:
            _run_listing(self._dispatch(), pi)
        got = _formal(exc_info)
        kind, what, culprit = formal
        assert got.functor == kind
        assert got.args[0] == mint(what)
        assert got.args[1] == (pi[1] if culprit is None else culprit)

    @pytest.mark.parametrize("pi", [
        ("/", mint("greet"), 1), ("/", mint("nosuch"), 2),
        ("//", mint("greet"), 2),
    ], ids=["other arity", "absent name", "dcg other arity"])
    def test_an_indicator_naming_nothing_fails(self, pi):
        assert _listing_answers(self._dispatch(), pi) == (0, "")

    @pytest.mark.parametrize("make", [
        lambda: ("//", mint("greet"), 0),
        lambda: Compound("//", (mint("greet"), 0)),
        lambda: __import__("clausal.terms", fromlist=["FloorDiv"]).FloorDiv(
            left=mint("greet"), right=0),
    ], ids=["cell", "compound", "floordiv-node"])
    def test_name_dcg_arity_lists_the_arity_plus_two(self, make):
        n, out = _listing_answers(self._dispatch(), make())
        assert n == 1
        assert "greet/2" in out and "1 clause(s)" in out
