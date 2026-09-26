"""P3-3 Task 6 (R10): module-qualified goals ``(":", M, G)`` and the resolver.

Task 5 made a CELL a goal but left one cell functor deferred: the
module-qualified form ``(":", M, G)``, which raised an ``existence_error``
naming ``cells.resolve_qualified_goal_cell`` as the stub Task 6 replaces.
This module pins the replacement.

What a qualified goal now means, and what each pin here is for:

  - ``resolve_module(designator, calling_module)`` turns a module DESIGNATOR
    into the ``Module`` whose database answers.  The chain is the R10 one:
    a ``str`` is a dotted Python module name looked up in ``sys.modules``
    (which is where the import hook registers every ``.clausal`` module), and
    from there — as for a Python module object handed in directly —
    ``_coerce_module`` finishes the job via ``__clausal_module__``.  A
    ``Module`` is already the answer.  Anything else, and any ``str`` that
    misses, is an ``existence_error(module, <designator repr'd>)``.  Lookup
    only: resolution never IMPORTS, so a name that is merely importable does
    not resolve.

  - ``(":", M, G)`` in goal position resolves *M* and runs *G* against THAT
    module — the module-locality pin: the exporter's ``p/1`` answers even
    though the importer defines its own ``p/1`` with different facts.  It is
    the same answer set the dotted call-node spelling produces (the parity
    pin), which is what makes the cell spelling a real second spelling of one
    feature rather than a second feature.

  - nesting is innermost-wins (ISO's ``m1:m2:G``), and every designator in the
    chain is resolved, so an unresolvable OUTER module still raises.

  - ``solve(goal, module=...)`` accepts the same designators, so
    ``module="dotted.name"`` is a spelling of the module argument.  A cell goal
    with no module and no qualification is an ``existence_error`` naming the
    gap (there is no class-instance goal to walk back to any more, W4b-3
    slice 7).

  - ``call/N`` resolves a qualified goal and dispatches in the EXPORTING db,
    through the exporter's own dispatch table or — for a predicate the
    exporter itself imported — its namespace.

  - the tabling entry lookup follows the qualification, so a tabled predicate
    called through a qualified cell tables into the EXPORTER's table store,
    not the caller's.

The fixtures are real cross-module loads: ``tests/fixtures/t6_lib.clausal``
(``libp/1``), ``t6_exporter.clausal`` (``p/1``, ``tp/1`` tabled, ``home/1``,
``pair/2``, ``ready/0``, plus ``libp/1`` imported from the lib) and
``t6_importer.clausal``, which defines its own same-spelled ``p/1``, ``tp/1``
and ``home/1`` with different facts.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.import_hook import _load_module
from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import (
    _tabled_entry_for_goal, call as pcall, query_wfs, resolve_module, solve,
)
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.terms import Compound, Undefined


EXPORTER = "tests.fixtures.t6_exporter"
IMPORTER = "tests.fixtures.t6_importer"
LIB = "tests.fixtures.t6_lib"


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


class _Mods:
    """The three loaded fixtures, both as Python modules and as ``Module``s."""

    def __init__(self, lib, exporter, importer):
        self.lib_py, self.exporter_py, self.importer_py = lib, exporter, importer
        self.lib = lib.__dict__["$module"]
        self.exporter = exporter.__dict__["$module"]
        self.importer = importer.__dict__["$module"]


@pytest.fixture
def mods():
    """Load the three fixtures fresh.

    Function-scoped on purpose: the tabling pins read ``db.table_store``, and a
    shared load would let one test's table decide another's assertion.
    """
    lib = _load_module(LIB, _fixture_path("t6_lib.clausal"))
    exporter = _load_module(EXPORTER, _fixture_path("t6_exporter.clausal"))
    importer = _load_module(IMPORTER, _fixture_path("t6_importer.clausal"))
    return _Mods(lib, exporter, importer)


def _error_term(exc: LogicException):
    """``(inner_error_term, context_message)`` from a raised LogicException."""
    return exc.term.args[0], exc.term.args[1]


# ── resolve_module ─────────────────────────────────────────────────────────


class TestResolveModule:
    def test_a_dotted_str_resolves_through_sys_modules(self, mods):
        assert resolve_module(EXPORTER, None) is mods.exporter

    def test_a_module_resolves_to_itself(self, mods):
        assert resolve_module(mods.exporter, None) is mods.exporter

    def test_a_python_module_resolves_through_clausal_module(self, mods):
        assert resolve_module(mods.exporter_py, None) is mods.exporter

    def test_a_plain_python_module_is_wrapped(self):
        """The ``_coerce_module`` last resort, reached through the resolver."""
        py = types.ModuleType("t6_plain_python_module")
        py.whatever = 1
        resolved = resolve_module(py, None)
        assert isinstance(resolved, Module)
        assert resolved.name == "t6_plain_python_module"

    def test_a_str_that_misses_in_sys_modules_is_an_existence_error(self):
        name = "t6_no_such_module_anywhere"
        assert name not in sys.modules
        with pytest.raises(LogicException) as exc_info:
            resolve_module(name, None)
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), repr(name)))

    @pytest.mark.parametrize("designator", [7, 1.5, ("m",), (":",), b"m", None])
    def test_a_non_designator_is_an_existence_error(self, designator):
        with pytest.raises(LogicException) as exc_info:
            resolve_module(designator, None)
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound(
            "existence_error", (mint("module"), repr(designator)))

    def test_an_unbound_var_designator_is_an_existence_error(self):
        """An unbound Var names no module; it must not bind to one either."""
        V = Var()
        with pytest.raises(LogicException):
            resolve_module(V, None)
        assert deref(V) is V

    def test_resolution_never_imports(self, monkeypatch):
        """Lookup-only: an importable but unimported module does NOT resolve.

        ``monkeypatch.delitem`` rather than ``sys.modules.pop`` so the entry is
        put back for whatever runs next (fix round 1, F7)."""
        name = "tests.fixtures.t6_lib"
        monkeypatch.delitem(sys.modules, name, raising=False)
        with pytest.raises(LogicException):
            resolve_module(name, None)
        assert name not in sys.modules

    def test_the_culprit_is_the_dereferenced_designator(self, mods):
        """A ``M`` slot is routinely a Var bound to the real designator;
        reporting the Var names the plumbing, not the fault (F6)."""
        V = Var()
        unify(V, 7, Trail())
        with pytest.raises(LogicException) as exc_info:
            resolve_module(V, None)
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), "7"))


# ── the qualified goal in solve() ──────────────────────────────────────────


class TestQualifiedCellGoal:
    def test_module_locality_the_exporter_answers_not_the_caller(self, mods):
        """THE core pin: same spelling, two modules, the qualification decides."""
        X, Y = Var(), Var()
        qualified = [deref(X)
                     for _ in solve((":", EXPORTER, ("p", X)), mods.importer)]
        local = [deref(Y) for _ in solve(("p", Y), mods.importer)]
        assert qualified == [11, 12]
        assert local == [1, 2]

    def test_the_locality_pin_holds_at_a_second_arity(self, mods):
        A, B = Var(), Var()
        assert [(deref(A), deref(B))
                for _ in solve((":", EXPORTER, ("pair", A, B)),
                               mods.importer)] == [(11, 12)]

    def test_a_qualified_goal_answers_the_exporters_witness(self, mods):
        W = Var()
        assert [deref(W) for _ in solve((":", EXPORTER, ("home", W)),
                                        mods.importer)] == [mint("exporter")]

    def test_a_qualified_goal_needs_no_module_argument(self, mods):
        """The qualification names the module, so ``module=`` is redundant."""
        X = Var()
        assert [deref(X) for _ in solve((":", EXPORTER, ("p", X)))] == [11, 12]

    def test_a_module_designator_may_be_the_module_object_itself(self, mods):
        X = Var()
        assert [deref(X) for _ in solve((":", mods.exporter, ("p", X)),
                                        mods.importer)] == [11, 12]
        Y = Var()
        assert [deref(Y) for _ in solve((":", mods.exporter_py, ("p", Y)),
                                        mods.importer)] == [11, 12]

    def test_a_zero_arity_inner_goal_runs(self, mods):
        assert len(list(solve((":", EXPORTER, "ready"),
                              mods.importer))) == 1

    def test_a_bare_atom_inner_goal_is_the_zero_arity_cell(self, mods):
        """``M:k`` with an ATOM ``k`` is ``M:k()`` — the same cell path.

        THE FLIP (2026-09-06-atoms-as-cells-strings §6.4): the atom is the
        arity-0 cell -- and since stage 2 the atom IS the ``str``, so a bare
        ``str`` inner goal is the call of ``ready/0``.  A STRING
        (``chars("ready")``) raises through the same route an unqualified
        string goal does -- Task 15 item 3's ``existence_error(procedure,
        '.'/2)``, the string being the ``'.'/2`` compound whose procedure
        does not exist.
        """
        assert len(list(solve((":", EXPORTER, mint("ready")),
                              mods.importer))) == 1
        with pytest.raises(LogicException) as exc_info:
            list(solve((":", EXPORTER, chars("ready")), mods.importer))
        assert _error_term(exc_info.value)[0] == Compound(
            "existence_error", (mint("procedure"),
                                Compound("/", (mint("."), 2))))

    def test_an_unresolvable_module_is_an_existence_error(self, mods):
        with pytest.raises(LogicException) as exc_info:
            list(solve((":", "t6_nope", ("p", Var())), mods.importer))
        inner, context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), "'t6_nope'"))
        assert "solve/1" in context

    def test_a_non_str_module_designator_is_an_existence_error(self, mods):
        with pytest.raises(LogicException) as exc_info:
            list(solve((":", 7, ("p", Var())), mods.importer))
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), "7"))

    def test_a_control_construct_under_a_qualification_is_still_refused(
            self, mods):
        cell = (":", EXPORTER, (",", ("p", 11), ("p", 12)))
        with pytest.raises(LogicException) as exc_info:
            list(solve(cell, mods.importer))
        inner, context = _error_term(exc_info.value)
        assert inner.functor == "type_error"
        assert inner.args[0] == mint("callable_control_construct_unsupported")
        assert ",/2 is a control construct" in context


class TestNestedQualification:
    def test_the_innermost_module_answers(self, mods):
        """``m1:m2:G`` is ``m2:G`` — ISO's own reading."""
        X = Var()
        goal = (":", EXPORTER, (":", IMPORTER, ("p", X)))
        assert [deref(X) for _ in solve(goal, mods.importer)] == [1, 2]

    def test_the_innermost_module_answers_the_other_way_round(self, mods):
        X = Var()
        goal = (":", IMPORTER, (":", EXPORTER, ("p", X)))
        assert [deref(X) for _ in solve(goal, mods.importer)] == [11, 12]

    def test_an_unresolvable_outer_module_still_raises(self, mods):
        """m1 is resolved even though m2 is the one that answers."""
        goal = (":", "t6_nope", (":", EXPORTER, ("p", Var())))
        with pytest.raises(LogicException) as exc_info:
            list(solve(goal, mods.importer))
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), "'t6_nope'"))

    def test_an_unresolvable_inner_module_raises(self, mods):
        goal = (":", EXPORTER, (":", "t6_nope", ("p", Var())))
        with pytest.raises(LogicException) as exc_info:
            list(solve(goal, mods.importer))
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), "'t6_nope'"))

    def test_a_cyclic_qualification_terminates_with_an_error(self, mods):
        """``V`` bound to ``(":", M, V)`` has no innermost goal.  ``unify``
        builds cyclic terms and nothing forbids them, so the peel loop is
        BOUNDED rather than trusting the term to bottom out (fix round 1, F5).
        The assertion is simply that it raises — reaching it at all is the
        pin, since the unbounded loop hung."""
        V = Var()
        cyclic = (":", EXPORTER, V)
        unify(V, cyclic, Trail())
        with pytest.raises(LogicException) as exc_info:
            list(solve(cyclic, mods.importer))
        inner, context = _error_term(exc_info.value)
        assert inner.functor == "existence_error"
        assert inner.args[0] == mint("module")
        assert "cyclic" in context

    def test_a_qualification_nested_past_the_cap_is_refused(self, mods):
        from clausal.logic.cells import MAX_QUALIFICATION_DEPTH
        goal = ("p", Var())
        for _ in range(MAX_QUALIFICATION_DEPTH + 1):
            goal = (":", EXPORTER, goal)
        with pytest.raises(LogicException) as exc_info:
            list(solve(goal, mods.importer))
        assert _error_term(exc_info.value)[0].args[0] == mint("module")

    def test_a_qualification_at_the_cap_still_answers(self, mods):
        """The bound is a guard, not a new limit on legitimate nesting: the
        cap is the deepest chain that WORKS, one shy of the refusal above."""
        from clausal.logic.cells import MAX_QUALIFICATION_DEPTH
        X = Var()
        goal = ("p", X)
        for _ in range(MAX_QUALIFICATION_DEPTH):
            goal = (":", EXPORTER, goal)
        assert [deref(X) for _ in solve(goal, mods.importer)] == [11, 12]


class TestQualifiedDottedParity:
    """The cell spelling and the dotted call-node spelling are one feature."""

    def test_the_two_spellings_answer_alike_through_a_fixture_predicate(
            self, mods):
        X, Y = Var(), Var()
        by_cell = [deref(X)
                   for _ in solve((":", EXPORTER, ("p", X)), mods.importer)]
        by_dotted = [deref(Y)
                     for _ in solve(("dotted_p", Y), mods.importer)]
        assert by_cell == by_dotted == [11, 12]

    def test_the_two_spellings_answer_alike_as_goal_nodes(self, mods):
        """The dotted Call node built by hand, against the same fixtures."""
        from clausal.terms import Call as AstCall, LoadAttr, LoadName
        dotted = LoadName(name="tests")
        for part in ("fixtures", "t6_exporter", "p"):
            dotted = LoadAttr(object=dotted, attr=part)
        X, Y = Var(), Var()
        by_node = [deref(X) for _ in solve(
            AstCall(func=dotted, args=[X], kwargs=[]), mods.importer)]
        by_cell = [deref(Y)
                   for _ in solve((":", EXPORTER, ("p", Y)), mods.importer)]
        assert by_node == by_cell == [11, 12]


# ── solve(module=<designator>) ─────────────────────────────────────────────


class TestSolveModuleDesignator:
    def test_a_str_module_argument_resolves(self, mods):
        X = Var()
        assert [deref(X) for _ in solve(("p", X), EXPORTER)] == [11, 12]

    def test_the_str_and_the_module_object_agree(self, mods):
        X, Y = Var(), Var()
        assert ([deref(X) for _ in solve(("p", X), IMPORTER)]
                == [deref(Y) for _ in solve(("p", Y), mods.importer)]
                == [1, 2])

    def test_a_python_module_argument_still_works(self, mods):
        X = Var()
        assert [deref(X) for _ in solve(("p", X), mods.exporter_py)] == [11, 12]

    def test_an_unresolvable_str_module_argument_is_an_existence_error(self):
        with pytest.raises(LogicException) as exc_info:
            list(solve(("p", Var()), "t6_nope"))
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), "'t6_nope'"))

    def test_an_unqualified_cell_goal_without_a_module_names_the_gap(self):
        """A cell names no module -- the gap is reported, not guessed."""
        Q = Var()
        goal = ("p", Q)
        with pytest.raises(LogicException) as exc_info:
            list(solve(goal))
        inner, context = _error_term(exc_info.value)
        # The culprit is the REPR, not the live cell (fix round 1, F4): the
        # cell holds the caller's Var, so a catch/3 pattern unifying with the
        # culprit would alias it.
        assert inner == Compound("existence_error", (mint("module"), repr(goal)))
        assert isinstance(inner.args[1], str)
        assert "module=" in context and "qualify" in context
        # ...and unifying with it therefore leaves the user's Var alone.
        unify(("p", Var()), inner.args[1], Trail())
        assert deref(Q) is Q

    def test_a_binding_built_goal_without_a_module_still_infers(self, mods):
        """The goal built from a module BINDING -- the handle-headed cell
        (a class term before W4b-2d) -- still answers, with its module passed and without one (a
        handle is its own module designator)."""
        handle = mods.exporter_py.p
        assert handle != "p"
        X = Var()
        assert [deref(X) for _ in solve((handle, X), mods.exporter_py)] == [11, 12]
        X = Var()
        assert [deref(X) for _ in solve((handle, X))] == [11, 12]


# ── call/N over a qualified goal ───────────────────────────────────────────


class TestQualifiedCallN:
    def test_call_over_a_qualified_cell_dispatches_in_the_exporting_db(
            self, mods):
        X = Var()
        assert [deref(X) for _ in pcall(
            "call_host1", (":", EXPORTER, ("p", X)),
            module=mods.importer)] == [11, 12]

    def test_the_atom_spelling_agrees_with_the_cell_spelling(self, mods):
        """``call(":", M, G)`` folds to ``call((":", M, G))`` — F4's pin, now
        with both spellings ANSWERING rather than both raising."""
        X, Y = Var(), Var()
        by_cell = [deref(X) for _ in pcall(
            "call_host1", (":", EXPORTER, ("p", X)), module=mods.importer)]
        by_atom = [deref(Y) for _ in pcall(
            "call_host3", mint(":"), EXPORTER, ("p", Y),
            module=mods.importer)]
        assert by_cell == by_atom == [11, 12]

    def test_call_over_a_qualified_cell_does_not_see_the_callers_predicate(
            self, mods):
        """Locality again, this time through call/N."""
        X, Y = Var(), Var()
        qualified = [deref(X) for _ in pcall(
            "call_host1", (":", EXPORTER, ("p", X)), module=mods.importer)]
        local = [deref(Y) for _ in pcall(
            "call_host1", ("p", Y), module=mods.importer)]
        assert qualified == [11, 12]
        assert local == [1, 2]

    def test_a_qualified_goal_resolves_through_the_exporters_namespace(
            self, mods):
        """``libp/1`` is ``-import_from``'d BY the exporter, so it is not in
        the exporter's own dispatch table — the qualified call has to take the
        ``_namespace_dispatch`` route in the exporting db."""
        assert mods.exporter.db.get_dispatch("libp", 1) is None
        X = Var()
        assert [deref(X) for _ in pcall(
            "call_host1", (":", EXPORTER, ("libp", X)),
            module=mods.importer)] == [31, 32]

    def test_a_qualified_goal_with_an_atom_inner_goal_runs(self, mods):
        assert len(list(pcall("call_host1", (":", EXPORTER, mint("ready")),
                              module=mods.importer))) == 1

    def test_an_unresolvable_module_raises_out_of_call(self, mods):
        with pytest.raises(LogicException) as exc_info:
            list(pcall("call_host1", (":", "t6_nope", ("p", Var())),
                       module=mods.importer))
        inner, context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), "'t6_nope'"))
        assert "call/1" in context

    def test_a_control_construct_under_a_qualification_runs_in_the_module(
            self, mods):
        """FLIPPED, operator ruling 2026-09-25 (call-runs-body-terms round 2: follow Scryer): ``M:(A, B)`` runs the conjunction with
        M as the context of the whole body -- it answers exactly as the two
        qualified conjuncts do one after the other."""
        whole = list(pcall("call_host1",
                           (":", EXPORTER, (",", ("p", 11), ("p", 12))),
                           module=mods.importer))
        a = list(pcall("call_host1", (":", EXPORTER, ("p", 11)),
                       module=mods.importer))
        b = list(pcall("call_host1", (":", EXPORTER, ("p", 12)),
                       module=mods.importer))
        assert len(a) == len(b) == 1      # the exporter's p(11), p(12)
        assert len(whole) == 1

    def test_a_qualified_goal_naming_nothing_raises_existence_error(self, mods):
        """FLIPPED 2026-09-25 -- operator ruling 2 ("like Scryer"): a meta-call naming an UNKNOWN procedure raises ISO existence_error(procedure, Name/Arity), catchable; it used to fail silently (the retired §4.2 contract).

        This used to be ``test_a_qualified_goal_naming_nothing_fails_silently``
        ("a resolvable module does not change that")."""
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as exc:
            list(pcall("call_host1", (":", EXPORTER, ("nosuch", Var())),
                       module=mods.importer))
        formal = exc.value.term.args[0]
        assert formal.functor == "existence_error"
        assert tuple(formal.args[1].args) == ("nosuch", 1)

    def test_call_over_a_qualified_cell_with_extras_dispatches_in_the_exporting_db(
            self, mods):
        """``call(M:G, X)`` is ``M:call(G, X)`` — the extras fold onto the
        INNER goal, not onto the ``:`` cell.

        This is the arm that used to fold to a ``:``/3 lookup and fail
        silently (P3-3 Task 6 fix round 1, ruling R-A)."""
        X = Var()
        assert [deref(X) for _ in pcall(
            "call_host2", (":", EXPORTER, mint("p")), X,
            module=mods.importer)] == [11, 12]
        B = Var()
        assert [deref(B) for _ in pcall(
            "call_host2", (":", EXPORTER, ("pair", 11)), B,
            module=mods.importer)] == [12]

    def test_the_atom_spelling_with_extras_agrees(self, mods):
        """F4 again, at the arity the extras make up: ``call(":", M, G, X)``
        folds to the same goal as ``call((":", M, G), X)``."""
        X, Y = Var(), Var()
        by_cell = [deref(X) for _ in pcall(
            "call_host2", (":", EXPORTER, ("pair", 11)), X,
            module=mods.importer)]
        by_atom = [deref(Y) for _ in pcall(
            "call_host4", mint(":"), EXPORTER, ("pair", 11), Y,
            module=mods.importer)]
        assert by_cell == by_atom == [12]

    def test_the_extras_form_does_not_see_the_callers_predicate(self, mods):
        """Locality holds once the extras have folded, too."""
        X = Var()
        assert [deref(X) for _ in pcall(
            "call_host2", (":", EXPORTER, mint("p")), X,
            module=mods.importer)] == [11, 12]
        Y = Var()
        assert [deref(Y) for _ in pcall(
            "call_host2", mint("p"), Y, module=mods.importer)] == [1, 2]

    def test_an_unresolvable_module_with_extras_still_raises(self, mods):
        with pytest.raises(LogicException) as exc_info:
            list(pcall("call_host2", (":", "t6_nope", mint("p")), Var(),
                       module=mods.importer))
        inner, context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", (mint("module"), "'t6_nope'"))
        assert "call/2" in context


# ── the tabling entry follows the qualification ────────────────────────────


class TestQualifiedTabling:
    def test_a_tabled_predicate_answers_through_a_qualified_goal(self, mods):
        X, Y = Var(), Var()
        assert [deref(X) for _ in solve((":", EXPORTER, ("tp", X)),
                                        mods.importer)] == [21, 22]
        assert [deref(Y) for _ in solve(("tp", Y), mods.importer)] == [3, 4]

    def test_the_table_lands_in_the_exporters_store(self, mods):
        assert mods.exporter.db.table_store == {}
        assert mods.importer.db.table_store == {}
        list(solve((":", EXPORTER, ("tp", Var())), mods.importer))
        assert [k[:2] for k in mods.exporter.db.table_store] == [("tp", 1)]
        assert mods.importer.db.table_store == {}

    def test_the_entry_lookup_follows_the_qualification(self, mods):
        X = Var()
        goal = (":", EXPORTER, ("tp", X))
        list(solve(goal, mods.importer))
        entry, goal_args = _tabled_entry_for_goal(goal, mods.importer, Trail())
        assert entry is not None
        assert entry in mods.exporter.db.table_store.values()
        assert goal_args == [X]

    def test_an_unqualified_cell_goal_also_reaches_the_entry_lookup(self, mods):
        """The cell shape was invisible to the entry lookup before this task;
        the qualified path could not be added without it."""
        Y = Var()
        goal = ("tp", Y)
        list(solve(goal, mods.importer))
        entry, goal_args = _tabled_entry_for_goal(goal, mods.importer, Trail())
        assert entry is not None
        assert entry in mods.importer.db.table_store.values()
        assert goal_args == [Y]

    def test_query_wfs_annotates_a_qualified_tabled_goal(self, mods):
        X = Var()
        rows = query_wfs((":", EXPORTER, ("tp", X)), {"x": X}, mods.importer)
        assert [r["x"] for r in rows] == [21, 22]
        assert all(r["_truth"] is True and r["_delays"] == frozenset()
                   for r in rows)


# ── query_wfs resolves its module ONCE, like solve ─────────────────────────


WFS_UNDEF = "tests.fixtures.t6_wfs_undefined"


@pytest.fixture
def undef():
    """A module whose tabled ``win/1`` is WFS-*Undefined* for every answer.

    ``wfs_win.clausal`` is the suite's canonical symmetric win cycle; it is
    loaded here under a dotted name so the same goal can be asked with a str
    designator, with a Module, and through a qualification.
    """
    return _load_module(WFS_UNDEF, _fixture_path("wfs_win.clausal"))


class TestQueryWfsModuleResolution:
    """P3-3 Task 6 fix round 1, F1 and F2.

    ``query_wfs`` asks two questions — "what answers?" (``solve``) and "what
    are their truth values?" (``_tabled_entry_for_goal``) — and both have to be
    asked of the SAME module.  Passing the raw ``module`` argument to both let
    them disagree, and the disagreement was silent: the truth annotation, not
    the answer list, was what came out wrong.
    """

    def _truths(self, goal, module, X):
        rows = query_wfs(goal, {"x": X}, module)
        return [(r["x"], r["_truth"]) for r in rows]

    def test_a_str_designator_does_not_crash_the_entry_lookup(self, undef):
        """F1: the goal ran, then the annotation pass raised an uncaught
        TypeError out of ``_coerce_module("dotted.name")``."""
        lm = undef.__dict__["$module"]
        X, Y = Var(), Var()
        assert (self._truths(("win", X), WFS_UNDEF, X)
                == self._truths(("win", Y), lm, Y))

    def test_the_str_designator_reports_the_real_truth_values(self, undef):
        X = Var()
        rows = self._truths(("win", X), WFS_UNDEF, X)
        assert len(rows) == 2
        assert all(t is Undefined for _v, t in rows)

    def test_a_qualified_goal_without_a_module_keeps_its_truth_values(
            self, undef):
        """F2: ``_tabled_entry_for_goal`` bailed on ``module=None``, and
        ``query_wfs`` defaults an unlocated row to ``True`` — so every
        Undefined answer of a moduleless qualified goal read as True."""
        lm = undef.__dict__["$module"]
        X, Y = Var(), Var()
        moduleless = self._truths((":", WFS_UNDEF, ("win", X)), None, X)
        with_module = self._truths(("win", Y), lm, Y)
        assert moduleless == with_module
        assert len(moduleless) == 2
        assert all(t is Undefined for _v, t in moduleless)

    def test_a_qualified_goal_with_a_foreign_caller_keeps_its_truth_values(
            self, undef, mods):
        """The same, asked from a module that has never heard of the exporter."""
        X = Var()
        rows = self._truths((":", WFS_UNDEF, ("win", X)), mods.importer, X)
        assert len(rows) == 2
        assert all(t is Undefined for _v, t in rows)

    def test_the_delays_survive_the_resolution_too(self, undef):
        X = Var()
        rows = query_wfs((":", WFS_UNDEF, ("win", X)), {"x": X}, None)
        assert all(r["_delays"] for r in rows), (
            "an Undefined answer carries a non-empty delay set")


# ── the lowering surface itself ────────────────────────────────────────────


class TestTermToGoalQualified:
    def test_the_qualified_cell_lowers_to_the_inner_goals_call_node(self, mods):
        from clausal.logic.solve import _term_to_goal
        from clausal.pythonic_ast.nodes import Call as AstCall, LoadName
        X = Var()
        assert _term_to_goal((":", EXPORTER, ("p", X))) == AstCall(
            func=LoadName(name="p"), args=[X], kwargs=[])

    def test_the_nested_qualified_cell_lowers_to_the_innermost_goal(self, mods):
        from clausal.logic.solve import _term_to_goal
        from clausal.pythonic_ast.nodes import Call as AstCall, LoadName
        assert _term_to_goal(
            (":", EXPORTER, (":", IMPORTER, ("p", 1)))) == AstCall(
                func=LoadName(name="p"), args=[1], kwargs=[])

    def test_colon_slash_3_is_still_an_ordinary_call(self, mods):
        from clausal.logic.solve import _term_to_goal
        from clausal.pythonic_ast.nodes import Call as AstCall, LoadName
        assert _term_to_goal((":", 1, 2, 3)) == AstCall(
            func=LoadName(name=":"), args=[1, 2, 3], kwargs=[])

    def test_the_qualified_cell_goal_is_cached_per_resolved_module(self, mods):
        """The compiled query is keyed on the module that ANSWERS, so the same
        qualified goal asked from two callers shares one entry, and the same
        inner goal asked of two modules does not."""
        from clausal.logic.solve import _goal_cache_key, _query_cache
        _query_cache.clear()
        X, Y, Z = Var(), Var(), Var()
        list(solve((":", EXPORTER, ("p", X)), mods.importer))
        after_first = len(_query_cache)
        assert after_first == 1
        # A second caller, same qualification → the same compiled query.
        list(solve((":", EXPORTER, ("p", Y)), mods.exporter))
        assert len(_query_cache) == after_first
        # The unqualified goal against the OTHER module → a second entry.
        list(solve(("p", Z), mods.importer))
        assert len(_query_cache) == after_first + 1
        # And the key that entry is under is the resolved module's.
        assert _goal_cache_key(("p", X), mods.exporter) in _query_cache

    def test_the_qualified_goal_is_templatized_after_the_strip(self, mods):
        """A ground argument under a qualification parameterizes like any
        other, so two ground values share one compiled query."""
        from clausal.logic.solve import _query_cache
        _query_cache.clear()
        assert len(list(solve((":", EXPORTER, ("p", 11)), mods.importer))) == 1
        one = len(_query_cache)
        assert len(list(solve((":", EXPORTER, ("p", 12)), mods.importer))) == 1
        assert len(_query_cache) == one
