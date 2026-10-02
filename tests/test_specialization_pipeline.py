"""Tests for Phase 2: MI specialization pipeline integration.

End-to-end tests that import .clausal fixtures using -metainterpreter
and -specialize directives, verifying that specialized predicates are
compiled and callable.
"""

from __future__ import annotations

import pytest
from clausal.logic.atoms import mint


def _module_db(mod):
    """The Database of a loaded .clausal module."""
    return mod.__clausal_module__.db


def _pred_row(mod, name, arity):
    """The live row the module-dict binding *name* denotes at *arity*.

    After the W4b-2d flip the binding is a mangled predicate HANDLE (a str),
    not a class, so row reads go through the module's Database."""
    from clausal.logic.predicate import resolve_predicate_row
    return resolve_predicate_row(getattr(mod, name), arity=arity,
                                 db=_module_db(mod))


def _assert_is_module_predicate(mod, name, arity):
    """*name* is bound in *mod* to a declared predicate at *arity* whose
    row is a real (not detached) row of the module's own Database."""
    from clausal.logic.predicate import is_declared_predicate
    db = _module_db(mod)
    binding = getattr(mod, name)
    assert is_declared_predicate(binding, arity=arity, db=db), binding
    row = _pred_row(mod, name, arity)
    assert row is not None and not row.detached, (name, arity, row)
    assert row is db.row(name, arity)


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
        assert hasattr(specialize_natnum, "solve_count_natnum")

    def test_specialized_predicate_is_predicate_meta(self, specialize_natnum):
        # nv
        _assert_is_module_predicate(specialize_natnum, "solve_count_natnum", 2)

    def test_specialized_fields_no_program(self, specialize_natnum):
        """Specialized predicate should drop the PROGRAM field."""
        # nv
        fields = _module_db(specialize_natnum).signature_for(
            "solve_count_natnum", 2)
        assert "PROGRAM" not in fields
        assert "GOALS" in fields
        assert "COUNT" in fields

    def test_specialized_has_clauses(self, specialize_natnum):
        """Specialized predicate should have compiled clauses."""
        # nv
        assert len(_pred_row(specialize_natnum, "solve_count_natnum", 2).clauses) == 3

    def test_specialized_has_dispatch(self, specialize_natnum):
        """Specialized predicate should have a dispatch function."""
        # nv
        assert _pred_row(specialize_natnum, "solve_count_natnum", 2).dispatch_fn is not None


# ── SolveCount specialization tests ─────────────────────────────────────────


class TestSpecializeCountNatnum:
    """Specialized solve_count with natnum — end-to-end via .clausal fixture."""

    def test_count_natnum_0(self, specialize_natnum):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.solve_count_natnum, [[mint("natnum"), 0]], count):
            results.append(walk(deref(count)))
        assert 1 in results

    def test_count_natnum_s0(self, specialize_natnum):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.solve_count_natnum, [[mint("natnum"), [mint("s"), 0]]], count):
            results.append(walk(deref(count)))
        assert 2 in results

    def test_count_natnum_ss0(self, specialize_natnum):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_natnum.solve_count_natnum, [[mint("natnum"), [mint("s"), [mint("s"), 0]]]], count):
            results.append(walk(deref(count)))
        assert 3 in results

    def test_clausal_inline_tests(self, specialize_natnum):
        """All test(...) predicates in the fixture should have passed."""
        # nv
        assert hasattr(specialize_natnum, "test")


# ── Solve specialization tests (graph) ──────────────────────────────────────


class TestSpecializeSolveGraph:
    """Specialized solve with graph — end-to-end via .clausal fixture."""

    def test_specialized_exists(self, specialize_graph):
        # nv
        assert hasattr(specialize_graph, "solve_graph")

    def test_edge_ab(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.solve_graph, [[mint("edge"), mint("a"), mint("b")]]))
        assert len(results) >= 1

    def test_path_ab(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.solve_graph, [[mint("path"), mint("a"), mint("b")]]))
        assert len(results) >= 1

    def test_path_ac_transitive(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.solve_graph, [[mint("path"), mint("a"), mint("c")]]))
        assert len(results) >= 1

    def test_path_ad_transitive(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.solve_graph, [[mint("path"), mint("a"), mint("d")]]))
        assert len(results) >= 1

    def test_no_path_ca(self, specialize_graph):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_graph.solve_graph, [[mint("path"), mint("c"), mint("a")]]))
        assert len(results) == 0

    def test_solve_graph_fields(self, specialize_graph):
        # nv
        fields = _module_db(specialize_graph).signature_for("solve_graph", 1)
        assert "PROGRAM" not in fields
        assert "GOALS" in fields


# ── SolveLimit specialization tests ─────────────────────────────────────────


class TestSpecializeLimitNatnum:
    """Specialized solve_limit with natnum — end-to-end via .clausal fixture."""

    def test_specialized_exists(self, specialize_limit):
        # nv
        assert hasattr(specialize_limit, "solve_limit_natnum")

    def test_fields(self, specialize_limit):
        # nv
        fields = _module_db(specialize_limit).signature_for(
            "solve_limit_natnum", 2)
        assert "PROGRAM" not in fields
        assert "GOALS" in fields
        assert "MAX_DEPTH" in fields

    def test_limit_natnum_0_depth_1(self, specialize_limit):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.solve_limit_natnum, [[mint("natnum"), 0]], 1,
        ))
        assert len(results) >= 1

    def test_limit_natnum_s0_depth_1_fails(self, specialize_limit):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.solve_limit_natnum, [[mint("natnum"), [mint("s"), 0]]], 1,
        ))
        assert len(results) == 0

    def test_limit_natnum_s0_depth_2(self, specialize_limit):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.solve_limit_natnum, [[mint("natnum"), [mint("s"), 0]]], 2,
        ))
        assert len(results) >= 1

    def test_limit_natnum_ss0_depth_3(self, specialize_limit):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_limit.solve_limit_natnum, [[mint("natnum"), [mint("s"), [mint("s"), 0]]]], 3,
        ))
        assert len(results) >= 1


# ── Equivalence tests ───────────────────────────────────────────────────────


class TestEquivalence:
    """Verify specialized produces same results as unspecialized MI."""

    def test_count_equivalence(self, specialize_natnum):
        """solve_count_natnum gives same counts as solve_count."""
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        mi_module = specialize_natnum
        spec_cls = mi_module.solve_count_natnum

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
        """solve_graph gives same success/failure as solve with GraphProgram."""
        # nv
        from clausal.logic.solve import call

        spec_cls = specialize_graph.solve_graph

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
    """Specialized solve + factorial (has gt, sub, mul builtins)."""

    def test_specialized_exists(self, specialize_builtins):
        # nv
        assert hasattr(specialize_builtins, "solve_factorial")

    def test_has_catch_all(self, specialize_builtins):
        """Factorial has builtins → specialized predicate should have catch-all."""
        # 1 base + 2 object clauses + 1 catch-all = 4
        # nv
        assert len(_pred_row(specialize_builtins, "solve_factorial", 1).clauses) == 4

    def test_factorial_0(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_factorial, [[mint("factorial"), 0, 1]]))
        assert len(results) >= 1

    def test_factorial_3(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_factorial, [[mint("factorial"), 3, 6]]))
        assert len(results) >= 1

    def test_factorial_5(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_factorial, [[mint("factorial"), 5, 120]]))
        assert len(results) >= 1

    def test_factorial_query_var(self, specialize_builtins):
        """Query with result as Var — binding should propagate."""
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        r = Var()
        results = []
        for _ in call(specialize_builtins.solve_factorial, [[mint("factorial"), 4, r]]):
            results.append(walk(deref(r)))
        assert 24 in results

    def test_factorial_wrong_fails(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_factorial, [[mint("factorial"), 3, 7]]))
        assert len(results) == 0


class TestSpecializeCountFactorial:
    """Specialized solve_count + factorial."""

    def test_specialized_exists(self, specialize_builtins):
        # nv
        assert hasattr(specialize_builtins, "solve_count_factorial")

    def test_count_factorial_0(self, specialize_builtins):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call

        count = Var()
        results = []
        for _ in call(specialize_builtins.solve_count_factorial, [[mint("factorial"), 0, 1]], count):
            results.append(walk(deref(count)))
        assert 1 in results


class TestSpecializeLimitFactorial:
    """Specialized solve_limit + factorial."""

    def test_specialized_exists(self, specialize_builtins):
        # nv
        assert hasattr(specialize_builtins, "solve_limit_factorial")

    def test_limit_factorial_0_depth_1(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_limit_factorial, [[mint("factorial"), 0, 1]], 1))
        assert len(results) >= 1

    def test_limit_factorial_3_depth_30(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_limit_factorial, [[mint("factorial"), 3, 6]], 30))
        assert len(results) >= 1


class TestSpecializeEven:
    """Specialized solve + even program."""

    def test_even_0(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_even, [[mint("even"), 0]]))
        assert len(results) >= 1

    def test_even_4(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_even, [[mint("even"), 4]]))
        assert len(results) >= 1

    def test_odd_1_fails(self, specialize_builtins):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_builtins.solve_even, [[mint("even"), 1]]))
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
        assert hasattr(specialize_deep, "deep_natnum")

    def test_deep_count_predicate_exists(self, specialize_deep):
        # nv
        assert hasattr(specialize_deep, "deep_count_natnum")

    def test_shallow_predicate_exists(self, specialize_deep):
        # nv
        assert hasattr(specialize_deep, "shallow_natnum")

    def test_deep_predicate_is_predicate_meta(self, specialize_deep):
        # nv
        _assert_is_module_predicate(specialize_deep, "deep_natnum", 1)

    def test_deep_natnum_0(self, specialize_deep):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_deep.deep_natnum, [[mint("natnum"), 0]]))
        assert len(results) >= 1

    def test_deep_natnum_s0(self, specialize_deep):
        # nv
        from clausal.logic.solve import call
        results = list(call(specialize_deep.deep_natnum, [[mint("natnum"), [mint("s"), 0]]]))
        assert len(results) >= 1

    def test_deep_natnum_ss0(self, specialize_deep):
        # nv
        from clausal.logic.solve import call
        results = list(call(
            specialize_deep.deep_natnum,
            [[mint("natnum"), [mint("s"), [mint("s"), 0]]]],
        ))
        assert len(results) >= 1

    def test_deep_count_natnum_0(self, specialize_deep):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        count = Var()
        results = []
        for _ in call(specialize_deep.deep_count_natnum, [[mint("natnum"), 0]], count):
            results.append(walk(deref(count)))
        assert 1 in results

    def test_deep_count_natnum_s0(self, specialize_deep):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        count = Var()
        results = []
        for _ in call(
            specialize_deep.deep_count_natnum, [[mint("natnum"), [mint("s"), 0]]], count,
        ):
            results.append(walk(deref(count)))
        assert 2 in results

    def test_equivalence_shallow_deep(self, specialize_deep):
        """Shallow and deep specialization produce identical results."""
        # nv
        from clausal.logic.solve import call
        for val in [0, ["s", 0], ["s", ["s", 0]]]:
            shallow = list(call(
                specialize_deep.shallow_natnum, [[mint("natnum"), val]],
            ))
            deep = list(call(
                specialize_deep.deep_natnum, [[mint("natnum"), val]],
            ))
            assert len(shallow) == len(deep), (
                f"Mismatch for natnum({val}): "
                f"shallow={len(shallow)}, deep={len(deep)}"
            )

    def test_depth_directive_parsed(self, specialize_deep):
        """The depth parameter should be accessible in some form."""
        # Basic check: deep predicate has clauses.
        # nv
        assert len(_pred_row(specialize_deep, "deep_natnum", 1).clauses) >= 3


# ── Error handling tests ────────────────────────────────────────────────────


class TestErrors:
    """Test error cases for the specialization directives."""

    def test_specialize_missing_args(self):
        """Malformed -specialize with missing args should raise SyntaxError."""
        # nv
        from clausal.templating.term_rewriting import EmbedTransformer
        import ast

        source = "-specialize(solve_count)"
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
    Fixture: ``tests/fixtures/specialize_tabled_alias.seam``."""

    def _load(self):
        import tests.fixtures.specialize_tabled_alias  # noqa: F401

    def test_the_load_is_refused_with_a_syntax_error_naming_the_alias(self):
        with pytest.raises(SyntaxError) as exc_info:
            self._load()
        message = str(exc_info.value)
        assert "-table(solve_count_tabled/2)" in message
        assert (
            "solve_count_tabled is a -specialize alias, and -table is not "
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
        """cpd_natnum predicate class is created."""
        # nv
        _assert_is_module_predicate(cpd_module, "cpd_natnum", 1)

    def test_cpd_graph_exists(self, cpd_module):
        # nv
        _assert_is_module_predicate(cpd_module, "cpd_graph", 1)

    def test_cpd_count_exists(self, cpd_module):
        # nv
        _assert_is_module_predicate(cpd_module, "cpd_count_natnum", 2)

    def test_cpd_limit_exists(self, cpd_module):
        # nv
        _assert_is_module_predicate(cpd_module, "cpd_limit_natnum", 2)

    def test_cpd_natnum_query(self, cpd_module):
        # nv
        from clausal.logic.solve import call
        assert sum(1 for _ in call(cpd_module.cpd_natnum, [[mint("natnum"), 0]])) == 1

    def test_cpd_graph_path(self, cpd_module):
        # nv
        from clausal.logic.solve import call
        assert sum(1 for _ in call(cpd_module.cpd_graph, [[mint("path"), mint("a"), mint("c")]])) == 1

    def test_cpd_count_value(self, cpd_module):
        # nv
        from clausal.logic.variables import Var, deref, walk
        from clausal.logic.solve import call
        v = Var()
        result = None
        for _ in call(cpd_module.cpd_count_natnum, [[mint("natnum"), [mint("s"), 0]]], v):
            result = walk(deref(v))
        assert result == 2

    def test_cpd_limit_succeeds(self, cpd_module):
        # nv
        from clausal.logic.solve import call
        assert sum(1 for _ in call(
            cpd_module.cpd_limit_natnum, [[mint("natnum"), [mint("s"), [mint("s"), 0]]]], 10
        )) == 1

    def test_cpd_inline_tests(self, cpd_module):
        """All inline test/1 clauses in the fixture should pass."""
        # nv
        from clausal.logic.solve import call
        results = list(call(cpd_module.test, mint("cpd natnum(0)")))
        assert len(results) == 1

    def test_cpd_directive_parsing(self):
        """cpd=True is parsed correctly from -specialize directive."""
        # nv
        from clausal.templating.term_rewriting import EmbedTransformer
        from clausal.pythonic_ast.nodes import SpecializeDirective as SI
        import ast

        source = "-specialize(solve, natnum_program, alias=cpd_natnum, cpd=True)"
        tree = ast.parse(source)
        t = EmbedTransformer()
        t.visit(tree)
        items = [i for i in t._module_items if isinstance(i, SI)]
        assert len(items) == 1
        assert items[0].cpd is True
        assert items[0].mi_name == "solve"
        assert items[0].new_name == "cpd_natnum"

    def test_cpd_directive_default_false(self):
        """cpd defaults to False when not specified."""
        # nv
        from clausal.templating.term_rewriting import EmbedTransformer
        from clausal.pythonic_ast.nodes import SpecializeDirective as SI
        import ast

        source = "-specialize(solve, natnum_program, alias=plain_natnum)"
        tree = ast.parse(source)
        t = EmbedTransformer()
        t.visit(tree)
        items = [i for i in t._module_items if isinstance(i, SI)]
        assert len(items) == 1
        assert items[0].cpd is False


# ── P3-3 Task 7: the specialized predicate is a ROW in the module's db ───────


class TestSpecializedPredicateIsARow:
    """P3-3 Task 7.  ``-specialize`` used to mint a free-floating predicate
    class and compile it against a throwaway ``Database`` the module's own
    database never heard of: ``db.row("solve_count_natnum", 2)`` was ``None``
    while the class answered queries out of a store nobody could reach.  The
    specialized predicate is now a row in the DEFINING module's database,
    installed through the Task-3 write gate.
    """

    def test_row_exists_in_module_db(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        assert db.row("solve_count_natnum", 2) is not None

    def test_class_reads_the_module_row(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        row = _pred_row(specialize_natnum, "solve_count_natnum", 2)
        assert row is db.row("solve_count_natnum", 2)
        assert row.detached is False

    def test_signature_registered(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        assert db.signature_for("solve_count_natnum", 2) == ("GOALS", "COUNT")

    def test_clauses_visible_in_module_db(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        assert db.is_defined("solve_count_natnum", 2)
        assert len(db.clauses_for("solve_count_natnum", 2)) == 3

    def test_dispatch_installed_on_the_module_row(self, specialize_natnum):
        db = _module_db(specialize_natnum)
        from clausal.logic.predicate import _dispatch_at
        binding = specialize_natnum.solve_count_natnum
        fn = db.get_dispatch("solve_count_natnum", 2)
        assert fn is not None
        assert fn is _dispatch_at(binding, 2, db)

    def test_write_is_gate_stamped_with_the_specialization_author(
        self, specialize_natnum,
    ):
        from clausal.logic.database import WRITE_LOAD_CLAUSES
        from clausal.logic.specialization import SPECIALIZE_AUTHOR_PREFIX

        db = _module_db(specialize_natnum)
        row = db.row("solve_count_natnum", 2)
        stamps = [w for w in row.writes
                  if w.author.startswith(SPECIALIZE_AUTHOR_PREFIX)]
        assert stamps, f"no specialization write on the row: {row.writes}"
        assert any(w.kind == WRITE_LOAD_CLAUSES for w in stamps)

    def test_first_write_claims_ownership_for_that_author(
        self, specialize_natnum,
    ):
        from clausal.logic.specialization import SPECIALIZE_AUTHOR_PREFIX

        db = _module_db(specialize_natnum)
        row = db.row("solve_count_natnum", 2)
        assert row.source is not None
        assert row.source[1].startswith(SPECIALIZE_AUTHOR_PREFIX)

    def test_deep_and_shallow_share_one_module_db(self, specialize_deep):
        db = _module_db(specialize_deep)
        for name, arity in (("shallow_natnum", 1), ("deep_natnum", 1),
                            ("deep_count_natnum", 2)):
            row = db.row(name, arity)
            assert row is not None, f"{name}/{arity} missing from the module db"
            assert _pred_row(specialize_deep, name, arity) is row

    def test_specialized_calls_specialized_through_row_dispatch(
        self, specialize_deep,
    ):
        """A specialized clause body calls a specialized predicate — the
        recursive call the unfolder emits — and the compiled dispatch reaches
        it through the module database's row, not through a private store.
        """
        db = _module_db(specialize_deep)
        from clausal.logic.predicate import _dispatch_at, resolve_predicate_row
        binding = specialize_deep.deep_count_natnum
        fn = db.get_dispatch("deep_count_natnum", 2)
        assert fn is not None
        target = fn.__globals__.get("deep_count_natnum")
        assert target is not None
        assert target == binding
        assert resolve_predicate_row(target, arity=2, db=db) \
            is db.row("deep_count_natnum", 2)
        assert _dispatch_at(target, 2, db) is fn

    def test_specializing_onto_a_name_this_module_defines_is_refused(self):
        """A module that writes my_alias/1's clauses AND names my_alias as a
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
        from clausal import cell_args, cell_functor
        from clausal.logic.exceptions import LogicException

        with pytest.raises(LogicException) as exc:
            import tests.fixtures.specialize_clobber  # noqa: F401

        term = exc.value.term
        assert cell_functor(term) == "error"
        assert cell_args(term)[0] == (
            "permission_error",
            mint("modify"), mint("static_procedure"),
            ("/", "my_alias", 1),
        )
        # The channel names the DIRECTIVE and the author names the
        # specializer; they are no longer the same word (fix round 1, F3).
        assert exc.value.message.startswith("-specialize: specialize:")
        assert "may not write my_alias/1" in exc.value.message

    def test_sibling_specializations_are_the_row_linked_classes(
        self, specialize_deep,
    ):
        """Every specialized name reachable from a specialized predicate's
        compile namespace is the row-linked class.

        Narrow on purpose: no clause of ``deep_natnum`` calls a sibling — the
        unfolder emits no alias-to-alias code reference — so this pins the
        NAMESPACE, not a call.  The specialized predicate is lowered against
        ``globals_``, which is the module dict, and what this shows is that
        the entries it carries for the module's other specializations are the
        classes bound to this database's rows rather than classes over a
        database the specializer dropped.  Whichever of them a later compile
        or a residual dispatch resolves, it lands on the row."""
        db = _module_db(specialize_deep)
        fn = db.get_dispatch("deep_natnum", 1)
        for name, arity in (("shallow_natnum", 1), ("deep_count_natnum", 2)):
            from clausal.logic.predicate import resolve_predicate_row
            sibling = fn.__globals__.get(name)
            assert sibling is not None
            assert sibling == getattr(specialize_deep, name)
            assert resolve_predicate_row(sibling, arity=arity, db=db) \
                is db.row(name, arity)
