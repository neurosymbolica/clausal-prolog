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
    gap: cells never reach ``_infer_module``, which keeps serving legacy
    class-instance goals only.

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
from clausal.import_hook import _load_module
from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import (
    _tabled_entry_for_goal, call as pcall, query_wfs, resolve_module, solve,
)
from clausal.logic.variables import Trail, Var, deref
from clausal.terms import Compound


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
        assert inner == Compound("existence_error", ("module", repr(name)))

    @pytest.mark.parametrize("designator", [7, 1.5, ("m",), (":",), b"m", None])
    def test_a_non_designator_is_an_existence_error(self, designator):
        with pytest.raises(LogicException) as exc_info:
            resolve_module(designator, None)
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound(
            "existence_error", ("module", repr(designator)))

    def test_an_unbound_var_designator_is_an_existence_error(self):
        """An unbound Var names no module; it must not bind to one either."""
        V = Var()
        with pytest.raises(LogicException):
            resolve_module(V, None)
        assert deref(V) is V

    def test_resolution_never_imports(self):
        """Lookup-only: an importable but unimported module does NOT resolve."""
        name = "tests.fixtures.t6_lib"
        sys.modules.pop(name, None)
        with pytest.raises(LogicException):
            resolve_module(name, None)
        assert name not in sys.modules


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
                                        mods.importer)] == ["exporter"]

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
        assert len(list(solve((":", EXPORTER, ("ready",)),
                              mods.importer))) == 1

    def test_a_bare_atom_inner_goal_is_the_zero_arity_cell(self, mods):
        """``M:k`` with a bare-str ``k`` is ``M:k()`` — the same cell path.

        A bare ``str`` is an atom (P3-1 §1b/R2) and names a zero-arity
        predicate, so the qualified form accepts it where the unqualified
        top-level cell path cannot yet spell it (see
        todo/bare-zero-arity-predicate-body-goal-does-not-compile).
        """
        assert len(list(solve((":", EXPORTER, "ready"), mods.importer))) == 1

    def test_an_unresolvable_module_is_an_existence_error(self, mods):
        with pytest.raises(LogicException) as exc_info:
            list(solve((":", "t6_nope", ("p", Var())), mods.importer))
        inner, context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", ("module", "'t6_nope'"))
        assert "solve/1" in context

    def test_a_non_str_module_designator_is_an_existence_error(self, mods):
        with pytest.raises(LogicException) as exc_info:
            list(solve((":", 7, ("p", Var())), mods.importer))
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", ("module", "7"))

    def test_a_control_construct_under_a_qualification_is_still_refused(
            self, mods):
        cell = (":", EXPORTER, (",", ("p", 11), ("p", 12)))
        with pytest.raises(LogicException) as exc_info:
            list(solve(cell, mods.importer))
        inner, context = _error_term(exc_info.value)
        assert inner.functor == "type_error"
        assert inner.args[0] == "callable_control_construct_unsupported"
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
        assert inner == Compound("existence_error", ("module", "'t6_nope'"))

    def test_an_unresolvable_inner_module_raises(self, mods):
        goal = (":", EXPORTER, (":", "t6_nope", ("p", Var())))
        with pytest.raises(LogicException) as exc_info:
            list(solve(goal, mods.importer))
        inner, _context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", ("module", "'t6_nope'"))


class TestQualifiedDottedParity:
    """The cell spelling and the dotted call-node spelling are one feature."""

    def test_the_two_spellings_answer_alike_through_a_fixture_predicate(
            self, mods):
        X, Y = Var(), Var()
        by_cell = [deref(X)
                   for _ in solve((":", EXPORTER, ("p", X)), mods.importer)]
        by_dotted = [deref(Y)
                     for _ in solve(mods.importer_py.DottedP(Y), mods.importer)]
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
        assert inner == Compound("existence_error", ("module", "'t6_nope'"))

    def test_an_unqualified_cell_goal_without_a_module_names_the_gap(self):
        """Cells never reach ``_infer_module`` — the gap is reported, not guessed."""
        goal = ("p", Var())
        with pytest.raises(LogicException) as exc_info:
            list(solve(goal))
        inner, context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", ("module", goal))
        assert "module=" in context and "qualify" in context

    def test_a_class_term_goal_without_a_module_still_infers(self, mods):
        """``_infer_module``'s legacy customers are untouched."""
        X = Var()
        assert [deref(X) for _ in solve(mods.exporter_py.p(X))] == [11, 12]

    def test_infer_module_documents_that_cells_never_reach_it(self):
        from clausal.logic.solve import _infer_module
        assert "cell" in _infer_module.__doc__.lower()


# ── call/N over a qualified goal ───────────────────────────────────────────


class TestQualifiedCallN:
    def test_call_over_a_qualified_cell_dispatches_in_the_exporting_db(
            self, mods):
        X = Var()
        assert [deref(X) for _ in pcall(
            "CallHost1", (":", EXPORTER, ("p", X)),
            module=mods.importer)] == [11, 12]

    def test_the_atom_spelling_agrees_with_the_cell_spelling(self, mods):
        """``call(":", M, G)`` folds to ``call((":", M, G))`` — F4's pin, now
        with both spellings ANSWERING rather than both raising."""
        X, Y = Var(), Var()
        by_cell = [deref(X) for _ in pcall(
            "CallHost1", (":", EXPORTER, ("p", X)), module=mods.importer)]
        by_atom = [deref(Y) for _ in pcall(
            "CallHost3", ":", EXPORTER, ("p", Y), module=mods.importer)]
        assert by_cell == by_atom == [11, 12]

    def test_call_over_a_qualified_cell_does_not_see_the_callers_predicate(
            self, mods):
        """Locality again, this time through call/N."""
        X, Y = Var(), Var()
        qualified = [deref(X) for _ in pcall(
            "CallHost1", (":", EXPORTER, ("p", X)), module=mods.importer)]
        local = [deref(Y) for _ in pcall(
            "CallHost1", ("p", Y), module=mods.importer)]
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
            "CallHost1", (":", EXPORTER, ("libp", X)),
            module=mods.importer)] == [31, 32]

    def test_a_qualified_goal_with_a_bare_atom_inner_goal_runs(self, mods):
        assert len(list(pcall("CallHost1", (":", EXPORTER, "ready"),
                              module=mods.importer))) == 1

    def test_an_unresolvable_module_raises_out_of_call(self, mods):
        with pytest.raises(LogicException) as exc_info:
            list(pcall("CallHost1", (":", "t6_nope", ("p", Var())),
                       module=mods.importer))
        inner, context = _error_term(exc_info.value)
        assert inner == Compound("existence_error", ("module", "'t6_nope'"))
        assert "call/1" in context

    def test_a_control_construct_under_a_qualification_is_refused_by_call(
            self, mods):
        with pytest.raises(LogicException) as exc_info:
            list(pcall("CallHost1",
                       (":", EXPORTER, (",", ("p", 11), ("p", 12))),
                       module=mods.importer))
        inner, _context = _error_term(exc_info.value)
        assert inner.args[0] == "callable_control_construct_unsupported"

    def test_a_qualified_goal_naming_nothing_fails_silently(self, mods):
        """The §4.2 contract: a name that resolves to nothing FAILS, and a
        resolvable module does not change that."""
        assert list(pcall("CallHost1", (":", EXPORTER, ("nosuch", Var())),
                          module=mods.importer)) == []

    def test_the_folded_colon_slash_3_form_is_not_the_qualified_one(
            self, mods):
        """``call((":", M, G), X)`` folds to ``:``/3, which is an ordinary
        call — unchanged from Task 5 (fix round 1, F5: only ``:``/2 is the
        qualified form, on every path)."""
        assert list(pcall("CallHost2", (":", EXPORTER, ("p", Var())), Var(),
                          module=mods.importer)) == []


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
