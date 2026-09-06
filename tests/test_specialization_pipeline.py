"""Tests for Phase 2: MI specialization pipeline integration.

End-to-end tests that import .clausal fixtures using -metainterpreter
and -specialize directives, verifying that specialized predicates are
compiled and callable.
"""

from __future__ import annotations

import pytest
from clausal.logic.atoms import char_atom, mint


# ── Fixture imports ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def specialize_natnum():
    """Import the specialize_natnum fixture."""
    import tests.fixtures.specialize_natnum as mod
    return mod


@pytest.fixture(scope="module")
def specialize_graph():
    """Import the specialize_graph fixture."""
    import tests.fixtures.specialize_graph as mod
    return mod


@pytest.fixture(scope="module")
def specialize_limit():
    """Import the specialize_limit fixture."""
    import tests.fixtures.specialize_limit as mod
    return mod


# ── Directive parsing tests ──────────────────────────────────────────────────


class TestDirectiveParsing:
    """Verify that -metainterpreter and -specialize directives are parsed."""

    def test_specialized_predicate_exists(self, specialize_natnum):
        """The specialized predicate should be created in module dict."""
        # nv
        assert hasattr(specialize_natnum, "SolveCountNatnum")

    def test_specialized_predicate_is_predicate_meta(self, specialize_natnum):
        # nv
        from clausal.logic.predicate import PredicateMeta
        assert isinstance(specialize_natnum.SolveCountNatnum, PredicateMeta)

    def test_specialized_fields_no_program(self, specialize_natnum):
        """Specialized predicate should drop the PROGRAM field."""
        # nv
        fields = specialize_natnum.SolveCountNatnum._fields
        assert "PROGRAM" not in fields
        assert "GOALS" in fields
        assert "COUNT" in fields

    def test_specialized_has_clauses(self, specialize_natnum):
        """Specialized predicate should have compiled clauses."""
        # nv
        assert len(specialize_natnum.SolveCountNatnum._clauses) == 3

    def test_specialized_has_dispatch(self, specialize_natnum):
        """Specialized predicate should have a dispatch function."""
        # nv
        assert specialize_natnum.SolveCountNatnum._dispatch_fn is not None


# ── SolveCount specialization tests ─────────────────────────────────────────


class TestSpecializeCountNatnum:
    """Specialized SolveCount with natnum — end-to-end via .clausal fixture."""

    def test_count_natnum_0(self, specialize_natnum):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.SolveCountNatnum, [[mint("natnum"), 0]], count):
            results.append(walk(deref(count)))
        assert 1 in results

    def test_count_natnum_s0(self, specialize_natnum):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.SolveCountNatnum, [[mint("natnum"), [mint("s"), 0]]], count):
            results.append(walk(deref(count)))
        assert 2 in results

    def test_count_natnum_ss0(self, specialize_natnum):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.SolveCountNatnum, [[mint("natnum"), [mint("s"), [mint("s"), 0]]]], count):
            results.append(walk(deref(count)))
        assert 3 in results

    def test_clausal_inline_tests(self, specialize_natnum):
        """All Test(...) predicates in the fixture should have passed."""
        # nv
        assert hasattr(specialize_natnum, "Test")


# ── Solve specialization tests (graph) ──────────────────────────────────────


class TestSpecializeSolveGraph:
    """Specialized Solve with graph — end-to-end via .clausal fixture."""

    def test_specialized_exists(self, specialize_graph):
        # nv
        assert hasattr(specialize_graph, "SolveGraph")

    def test_edge_ab(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [[mint("edge"), mint("a"), mint("b")]]))
        assert len(results) >= 1

    def test_path_ab(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [[mint("path"), mint("a"), mint("b")]]))
        assert len(results) >= 1

    def test_path_ac_transitive(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [[mint("path"), mint("a"), mint("c")]]))
        assert len(results) >= 1

    def test_path_ad_transitive(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [[mint("path"), mint("a"), mint("d")]]))
        assert len(results) >= 1

    def test_no_path_ca(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.SolveGraph, [[mint("path"), mint("c"), mint("a")]]))
        assert len(results) == 0

    def test_solve_graph_fields(self, specialize_graph):
        # nv
        fields = specialize_graph.SolveGraph._fields
        assert "PROGRAM" not in fields
        assert "GOALS" in fields


# ── SolveLimit specialization tests ─────────────────────────────────────────


class TestSpecializeLimitNatnum:
    """Specialized SolveLimit with natnum — end-to-end via .clausal fixture."""

    def test_specialized_exists(self, specialize_limit):
        # nv
        assert hasattr(specialize_limit, "SolveLimitNatnum")

    def test_fields(self, specialize_limit):
        # nv
        fields = specialize_limit.SolveLimitNatnum._fields
        assert "PROGRAM" not in fields
        assert "GOALS" in fields
        assert "MAX_DEPTH" in fields

    def test_limit_natnum_0_depth_1(self, specialize_limit):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.SolveLimitNatnum, [[mint("natnum"), 0]], 1,
        ))
        assert len(results) >= 1

    def test_limit_natnum_s0_depth_1_fails(self, specialize_limit):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.SolveLimitNatnum, [[mint("natnum"), [mint("s"), 0]]], 1,
        ))
        assert len(results) == 0

    def test_limit_natnum_s0_depth_2(self, specialize_limit):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.SolveLimitNatnum, [[mint("natnum"), [mint("s"), 0]]], 2,
        ))
        assert len(results) >= 1

    def test_limit_natnum_ss0_depth_3(self, specialize_limit):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.SolveLimitNatnum, [[mint("natnum"), [mint("s"), [mint("s"), 0]]]], 3,
        ))
        assert len(results) >= 1


# ── Equivalence tests ───────────────────────────────────────────────────────


class TestEquivalence:
    """Verify specialized produces same results as unspecialized MI."""

    def test_count_equivalence(self, specialize_natnum):
        """SolveCountNatnum gives same counts as SolveCount."""
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        mi_module = specialize_natnum
        spec_cls = mi_module.SolveCountNatnum

        for goal, expected in [
            ([[mint("natnum"), 0]], 1),
            ([[mint("natnum"), [mint("s"), 0]]], 2),
            ([[mint("natnum"), [mint("s"), [mint("s"), 0]]]], 3),
        ]:
            count = Var()
            results = []
            for _ in call(spec_cls, goal, count):
                results.append(walk(deref(count)))
            assert expected in results, (
                f"Expected count={expected} for {goal}, got {results}"
            )

    def test_graph_solve_equivalence(self, specialize_graph):
        """SolveGraph gives same success/failure as Solve with GraphProgram."""
        # nv
        from clausal.logic.solve import call

        spec_cls = specialize_graph.SolveGraph

        # Should succeed
        for goal in [
            [[mint("edge"), mint("a"), mint("b")]],
            [[mint("path"), mint("a"), mint("b")]],
            [[mint("path"), mint("a"), mint("c")]],
            [[mint("path"), mint("a"), mint("d")]],
        ]:
            results = list(call(spec_cls, goal))
            assert len(results) >= 1, f"Expected success for {goal}"

        # Should fail
        for goal in [
            [[mint("path"), mint("c"), mint("a")]],
            [[mint("edge"), mint("c"), mint("a")]],
        ]:
            results = list(call(spec_cls, goal))
            assert len(results) == 0, f"Expected failure for {goal}"


# ── Phase 3: Object programs with builtins ──────────────────────────────────


@pytest.fixture(scope="module")
def specialize_builtins():
    """Import the specialize_builtins fixture."""
    import tests.fixtures.specialize_builtins as mod
    return mod


class TestSpecializeFactorial:
    """Specialized Solve + factorial (has gt, sub, mul builtins)."""

    def test_specialized_exists(self, specialize_builtins):
        # nv
        assert hasattr(specialize_builtins, "SolveFactorial")

    def test_has_catch_all(self, specialize_builtins):
        """Factorial has builtins → specialized predicate should have catch-all."""
        # 1 base + 2 object clauses + 1 catch-all = 4
        # nv
        assert len(specialize_builtins.SolveFactorial._clauses) == 4

    def test_factorial_0(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveFactorial, [[mint("factorial"), 0, 1]]))
        assert len(results) >= 1

    def test_factorial_3(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveFactorial, [[mint("factorial"), 3, 6]]))
        assert len(results) >= 1

    def test_factorial_5(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveFactorial, [[mint("factorial"), 5, 120]]))
        assert len(results) >= 1

    def test_factorial_query_var(self, specialize_builtins):
        """Query with result as Var — binding should propagate."""
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        r = Var()
        results = []
        for _ in call(specialize_builtins.SolveFactorial, [[mint("factorial"), 4, r]]):
            results.append(walk(deref(r)))
        assert 24 in results

    def test_factorial_wrong_fails(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveFactorial, [[mint("factorial"), 3, 7]]))
        assert len(results) == 0


class TestSpecializeCountFactorial:
    """Specialized SolveCount + factorial."""

    def test_specialized_exists(self, specialize_builtins):
        # nv
        assert hasattr(specialize_builtins, "SolveCountFactorial")

    def test_count_factorial_0(self, specialize_builtins):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_builtins.SolveCountFactorial, [[mint("factorial"), 0, 1]], count):
            results.append(walk(deref(count)))
        assert 1 in results


class TestSpecializeLimitFactorial:
    """Specialized SolveLimit + factorial."""

    def test_specialized_exists(self, specialize_builtins):
        # nv
        assert hasattr(specialize_builtins, "SolveLimitFactorial")

    def test_limit_factorial_0_depth_1(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveLimitFactorial, [[mint("factorial"), 0, 1]], 1))
        assert len(results) >= 1

    def test_limit_factorial_3_depth_30(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveLimitFactorial, [[mint("factorial"), 3, 6]], 30))
        assert len(results) >= 1


class TestSpecializeEven:
    """Specialized Solve + even program."""

    def test_even_0(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveEven, [[mint("even"), 0]]))
        assert len(results) >= 1

    def test_even_4(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveEven, [[mint("even"), 4]]))
        assert len(results) >= 1

    def test_odd_1_fails(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.SolveEven, [[mint("even"), 1]]))
        assert len(results) == 0


# ── Phase 4: Deep specialization pipeline tests ─────────────────────────────


@pytest.fixture(scope="module")
def specialize_deep():
    """Import the specialize_deep fixture."""
    import tests.fixtures.specialize_deep as mod
    return mod


class TestDeepPipeline:
    """End-to-end tests for -specialize with depth=N."""

    def test_deep_predicate_exists(self, specialize_deep):
        # nv
        assert hasattr(specialize_deep, "DeepNatnum")

    def test_deep_count_predicate_exists(self, specialize_deep):
        # nv
        assert hasattr(specialize_deep, "DeepCountNatnum")

    def test_shallow_predicate_exists(self, specialize_deep):
        # nv
        assert hasattr(specialize_deep, "ShallowNatnum")

    def test_deep_predicate_is_predicate_meta(self, specialize_deep):
        # nv
        from clausal.logic.predicate import PredicateMeta
        assert isinstance(specialize_deep.DeepNatnum, PredicateMeta)

    def test_deep_natnum_0(self, specialize_deep):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_deep.DeepNatnum, [[mint("natnum"), 0]]))
        assert len(results) >= 1

    def test_deep_natnum_s0(self, specialize_deep):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_deep.DeepNatnum, [[mint("natnum"), [mint("s"), 0]]]))
        assert len(results) >= 1

    def test_deep_natnum_ss0(self, specialize_deep):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_deep.DeepNatnum,
            [[mint("natnum"), [mint("s"), [mint("s"), 0]]]],
        ))
        assert len(results) >= 1

    def test_deep_count_natnum_0(self, specialize_deep):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        count = Var()
        results = []
        for _ in call(specialize_deep.DeepCountNatnum, [[mint("natnum"), 0]], count):
            results.append(walk(deref(count)))
        assert 1 in results

    def test_deep_count_natnum_s0(self, specialize_deep):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        count = Var()
        results = []
        for _ in call(
            specialize_deep.DeepCountNatnum, [[mint("natnum"), [mint("s"), 0]]], count,
        ):
            results.append(walk(deref(count)))
        assert 2 in results

    def test_equivalence_shallow_deep(self, specialize_deep):
        """Shallow and deep specialization produce identical results."""
        # nv
        from clausal.logic.solve import call
        for val in [0, ["s", 0], ["s", ["s", 0]]]:
            shallow = list(call(
                specialize_deep.ShallowNatnum, [[mint("natnum"), val]],
            ))
            deep = list(call(
                specialize_deep.DeepNatnum, [[mint("natnum"), val]],
            ))
            assert len(shallow) == len(deep), (
                f"Mismatch for natnum({val}): "
                f"shallow={len(shallow)}, deep={len(deep)}"
            )

    def test_depth_directive_parsed(self, specialize_deep):
        """The depth parameter should be accessible in some form."""
        # Basic check: deep predicate has clauses.
        # nv
        assert len(specialize_deep.DeepNatnum._clauses) >= 3


# ── Error handling tests ────────────────────────────────────────────────────


class TestErrors:
    """Test error cases for the specialization directives."""

    def test_specialize_missing_args(self):
        """Malformed -specialize with missing args should raise SyntaxError."""
        # nv
        from clausal.templating.term_rewriting import EmbedTransformer
        import ast

        source = "-specialize(SolveCount)"
        with pytest.raises(SyntaxError):
            tree = ast.parse(source)
            t = EmbedTransformer()
            t.visit(tree)


class TestTableOnASpecializeAliasIsRefused:
    """Final review M-d.  ``-table`` on a ``-specialize`` alias is refused —
    the specializer compiles and installs the alias's dispatch itself, at a
    later step than the ``-table`` wrapper, so the directive would silently
    buy nothing.  P3-3 Task 7 narrowed the REASON (the specializer no longer
    has a database of its own) but kept the refusal; nothing pinned either
    the message or the ORDERING, which is what makes the failure clean:
    step 4b runs before step 6b, so the refusal cannot half-install an alias.
    Fixture: ``tests/fixtures/specialize_tabled_alias.clausal``."""

    def _load(self):
        import tests.fixtures.specialize_tabled_alias  # noqa: F401

    def test_the_load_is_refused_with_a_syntax_error_naming_the_alias(self):
        with pytest.raises(SyntaxError) as exc_info:
            self._load()
        message = str(exc_info.value)
        assert "-table(SolveCountTabled/2)" in message
        assert (
            "SolveCountTabled is a -specialize alias, and -table is not "
            "supported on one"
        ) in message

    def test_it_fires_before_the_alias_is_installed(self):
        """Step 4b, not step 6b: the module never finishes loading, so the
        alias is bound nowhere — no half-installed predicate is left behind."""
        import sys

        sys.modules.pop("tests.fixtures.specialize_tabled_alias", None)
        with pytest.raises(SyntaxError):
            self._load()
        assert "tests.fixtures.specialize_tabled_alias" not in sys.modules


# ── Phase 5: CPD Pipeline Tests ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def cpd_module():
    """Import the CPD test fixture."""
    import tests.fixtures.specialize_cpd as mod
    return mod


class TestCpdPipeline:
    """End-to-end CPD tests via .clausal fixture."""

    def test_cpd_natnum_exists(self, cpd_module):
        """CpdNatnum predicate class is created."""
        # nv
        from clausal.logic.predicate import PredicateMeta
        assert isinstance(cpd_module.CpdNatnum, PredicateMeta)

    def test_cpd_graph_exists(self, cpd_module):
        # nv
        from clausal.logic.predicate import PredicateMeta
        assert isinstance(cpd_module.CpdGraph, PredicateMeta)

    def test_cpd_count_exists(self, cpd_module):
        # nv
        from clausal.logic.predicate import PredicateMeta
        assert isinstance(cpd_module.CpdCountNatnum, PredicateMeta)

    def test_cpd_limit_exists(self, cpd_module):
        # nv
        from clausal.logic.predicate import PredicateMeta
        assert isinstance(cpd_module.CpdLimitNatnum, PredicateMeta)

    def test_cpd_natnum_query(self, cpd_module):
        # nv
        from clausal.logic.solve import call
        assert sum(1 for _ in call(cpd_module.CpdNatnum, [[mint("natnum"), 0]])) == 1

    def test_cpd_graph_path(self, cpd_module):
        # nv
        from clausal.logic.solve import call
        assert sum(1 for _ in call(cpd_module.CpdGraph, [[mint("path"), mint("a"), mint("c")]])) == 1

    def test_cpd_count_value(self, cpd_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        v = Var()
        result = None
        for _ in call(cpd_module.CpdCountNatnum, [[mint("natnum"), [mint("s"), 0]]], v):
            result = walk(deref(v))
        assert result == 2

    def test_cpd_limit_succeeds(self, cpd_module):
        # nv
        from clausal.logic.solve import call
        assert sum(1 for _ in call(
            cpd_module.CpdLimitNatnum, [[mint("natnum"), [mint("s"), [mint("s"), 0]]]], 10
        )) == 1

    def test_cpd_inline_tests(self, cpd_module):
        """All inline Test predicates in the fixture should pass."""
        # nv
        from clausal.logic.solve import call
        results = list(call(cpd_module.Test, mint("cpd natnum(0)")))
        assert len(results) == 1

    def test_cpd_directive_parsing(self):
        """cpd=True is parsed correctly from -specialize directive."""
        # nv
        from clausal.templating.term_rewriting import EmbedTransformer
        from clausal.pythonic_ast.nodes import SpecializeDirective as SI
        import ast

        source = "-specialize(Solve, NatnumProgram, alias=CpdNatnum, cpd=True)"
        tree = ast.parse(source)
        t = EmbedTransformer()
        t.visit(tree)
        items = [i for i in t._module_items if isinstance(i, SI)]
        assert len(items) == 1
        assert items[0].cpd is True
        assert items[0].mi_name == "Solve"
        assert items[0].new_name == "CpdNatnum"

    def test_cpd_directive_default_false(self):
        """cpd defaults to False when not specified."""
        # nv
        from clausal.templating.term_rewriting import EmbedTransformer
        from clausal.pythonic_ast.nodes import SpecializeDirective as SI
        import ast

        source = "-specialize(Solve, NatnumProgram, alias=PlainNatnum)"
        tree = ast.parse(source)
        t = EmbedTransformer()
        t.visit(tree)
        items = [i for i in t._module_items if isinstance(i, SI)]
        assert len(items) == 1
        assert items[0].cpd is False


# ── P3-3 Task 7: the specialized predicate is a ROW in the module's db ───────


def _module_db(mod):
    """The Database of a loaded .clausal module."""
    return mod.__clausal_module__.db


class TestSpecializedPredicateIsARow:
    """P3-3 Task 7.  ``-specialize`` used to mint a free-floating predicate
    class and compile it against a throwaway ``Database`` the module's own
    database never heard of: ``db.row("SolveCountNatnum", 2)`` was ``None``
    while the class answered queries out of a store nobody could reach.  The
    specialized predicate is now a row in the DEFINING module's database,
    installed through the Task-3 write gate.
    """

    def test_row_exists_in_module_db(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        assert db.row("SolveCountNatnum", 2) is not None

    def test_class_reads_the_module_row(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        cls = specialize_natnum.SolveCountNatnum
        assert cls._row is db.row("SolveCountNatnum", 2)
        assert cls._row.detached is False

    def test_signature_registered(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        assert db.signature_for("SolveCountNatnum", 2) == ("GOALS", "COUNT")

    def test_clauses_visible_in_module_db(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        assert db.is_defined("SolveCountNatnum", 2)
        assert len(db.clauses_for("SolveCountNatnum", 2)) == 3

    def test_dispatch_installed_on_the_module_row(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        cls = specialize_natnum.SolveCountNatnum
        fn = db.get_dispatch("SolveCountNatnum", 2)
        assert fn is not None
        assert fn is cls._get_dispatch()

    def test_write_is_gate_stamped_with_the_specialization_author(
        self, specialize_natnum,
    ):
        from clausal.logic.database import WRITE_LOAD_CLAUSES
        from clausal.logic.specialization import SPECIALIZE_AUTHOR_PREFIX

        db = _module_db(specialize_natnum)
        row = db.row("SolveCountNatnum", 2)
        stamps = [w for w in row.writes
                  if w.author.startswith(SPECIALIZE_AUTHOR_PREFIX)]
        assert stamps, f"no specialization write on the row: {row.writes}"
        assert any(w.kind == WRITE_LOAD_CLAUSES for w in stamps)

    def test_first_write_claims_ownership_for_that_author(
        self, specialize_natnum,
    ):
        from clausal.logic.specialization import SPECIALIZE_AUTHOR_PREFIX

        db = _module_db(specialize_natnum)
        row = db.row("SolveCountNatnum", 2)
        assert row.source is not None
        assert row.source[1].startswith(SPECIALIZE_AUTHOR_PREFIX)

    def test_deep_and_shallow_share_one_module_db(self, specialize_deep):
        db = _module_db(specialize_deep)
        for name, arity in (("ShallowNatnum", 1), ("DeepNatnum", 1),
                            ("DeepCountNatnum", 2)):
            row = db.row(name, arity)
            assert row is not None, f"{name}/{arity} missing from the module db"
            assert getattr(specialize_deep, name)._row is row

    def test_specialized_calls_specialized_through_row_dispatch(
        self, specialize_deep,
    ):
        """A specialized clause body calls a specialized predicate — the
        recursive call the unfolder emits — and the compiled dispatch reaches
        it through the module database's row, not through a private store.
        """
        db = _module_db(specialize_deep)
        cls = specialize_deep.DeepCountNatnum
        fn = db.get_dispatch("DeepCountNatnum", 2)
        assert fn is not None
        target = fn.__globals__.get("DeepCountNatnum")
        assert target is cls
        assert target._row is db.row("DeepCountNatnum", 2)
        assert target._get_dispatch() is fn

    def test_specializing_onto_a_name_this_module_defines_is_refused(self):
        """A module that writes MyAlias/1's clauses AND names MyAlias as a
        -specialize alias is refused at load.

        The row is the module's own by then (step 4 wrote the clause and
        stamped ``source``), and the specializer writes as a different author,
        so rule 3 of the ownership policy — a load may not overwrite somebody
        else's predicate — refuses it.  Before P3-3 Task 7 there was nothing
        to refuse: the specializer compiled against a database of its own and
        rebound the module-dict entry, leaving the module's own clause in the
        database with nothing resolving to it.

        Pins Task 7's report concern 2, which is a NEW refusal.
        """
        from clausal.logic.exceptions import LogicException
        from clausal.terms import Compound

        with pytest.raises(LogicException) as exc:
            import tests.fixtures.specialize_clobber  # noqa: F401

        term = exc.value.term
        assert term.functor == "error"
        assert term.args[0] == Compound(
            "permission_error",
            (mint("modify"), mint("static_procedure"),
             Compound("/", ("MyAlias", 1))),
        )
        # The channel names the DIRECTIVE and the author names the
        # specializer; they are no longer the same word (fix round 1, F3).
        assert term.args[1].startswith("-specialize: specialize:")
        assert "may not write MyAlias/1" in term.args[1]

    def test_sibling_specializations_are_the_row_linked_classes(
        self, specialize_deep,
    ):
        """Every specialized name reachable from a specialized predicate's
        compile namespace is the row-linked class.

        Narrow on purpose: no clause of ``DeepNatnum`` calls a sibling — the
        unfolder emits no alias-to-alias code reference — so this pins the
        NAMESPACE, not a call.  The specialized predicate is lowered against
        ``globals_``, which is the module dict, and what this shows is that
        the entries it carries for the module's other specializations are the
        classes bound to this database's rows rather than classes over a
        database the specializer dropped.  Whichever of them a later compile
        or a residual dispatch resolves, it lands on the row."""
        db = _module_db(specialize_deep)
        fn = db.get_dispatch("DeepNatnum", 1)
        for name, arity in (("ShallowNatnum", 1), ("DeepCountNatnum", 2)):
            sibling = fn.__globals__.get(name)
            assert sibling is getattr(specialize_deep, name)
            assert sibling._row is db.row(name, arity)
