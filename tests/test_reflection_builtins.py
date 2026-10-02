"""Tests for clausal.modules.reflection — matching reified terms from Clausal.

Phase 2 of implementation_plans/clausal-ast-reflection-and-structural-matching.md:
``-import_from(reflection, [...])`` exposes the reified vocabulary plus
enumeration/destructuring builtins, so linters and matchers are written in
Clausal itself.
"""

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.reflection import Clause, is_v
from tests._suffix import SEAM


EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clausal", "examples",
)


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


# Atom-mode source (this file pins ``-double_quotes(atom)``): every ``"…"`` below is a
# NAME — the functor name ``goal_functor/3`` reads and answers (§6.4) — so it
# must be an atom.  The reified ``Goal.name`` FIELD is still the raw spelling
# ``str``, which is why the DCG terminal below goes through ``goal_functor``
# rather than destructuring ``Goal("Edge", _, _)`` directly.
_MATCHERS = """\
-double_quotes(atom)
-import_from(reflection, [
    reified_item, reified_clause, reified_file_item,
    clause_head, clause_body, goal_functor, reified_subterm,
    Clause, Goal, Variable, Atom, Escape,
])

head_name(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

direct_head_name(SRC, NAME) <- reified_clause(SRC, Clause(Goal(NAME, _, _), _, _))

fact_name(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_body(CLAUSE, []),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

called_predicate(SRC, NAME, ARITY) <- (
    reified_clause(SRC, CLAUSE),
    clause_body(CLAUSE, GOALS),
    GOAL in GOALS,
    goal_functor(GOAL, NAME, ARITY)
)

defined_name(SRC, NAME) <- head_name(SRC, NAME)

undefined_call(SRC, NAME) <- (
    called_predicate(SRC, NAME, _),
    not defined_name(SRC, NAME)
)

escape_code(SRC, CODE) <- (
    reified_item(SRC, ITEM),
    reified_subterm(ITEM, Escape(CODE, _, _))
)

file_head_name(PATH, NAME) <- (
    reified_file_item(PATH, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

# ── DCG construction matching over a body's goal list (phase 3) ──────────────

edge_goal >> ([GOAL], {goal_functor(GOAL, "edge", _)})
any_goal >> ([_])
any_goals >> ([])
any_goals >> (any_goal, any_goals)

starts_with_edge >> (edge_goal, any_goals)

starts_with_edge(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _),
    clause_body(CLAUSE, GOALS),
    phrase(starts_with_edge, GOALS)
)
"""

_TARGET = """\
edge(1, 2),
edge(2, 3),

connected(X, Y) <- edge(X, Y)
connected(X, Y) <- (edge(X, Z), connected(Z, Y), ghost(Z))

size(L, N) <- (N is ++len(L))
"""


@pytest.fixture(scope="module")
def matchers(tmp_path_factory):
    path = tmp_path_factory.mktemp("reflection") / f"matchers{SEAM}"
    path.write_text(_MATCHERS)
    mod = _load_module("_test_reflection_matchers", str(path))
    return mod.__dict__["$module"]


def _all_bindings(functor, *args, module):
    """Call with a trailing Var, collect every deref'd binding."""
    out = Var()
    results = []
    for _ in call(functor, *args, out, module=module):
        results.append(deref(out))
    return results


class TestEnumeration:
    def test_head_names_enumerate_all_clauses(self, matchers):
        # goal_functor/3 answers a NAME, so the bindings are ATOMS (§6.4).
        names = _all_bindings("head_name", chars(_TARGET), module=matchers)
        assert names == [
            mint("edge"), mint("edge"),
            mint("connected"), mint("connected"), mint("size"),
        ]

    def test_direct_pattern_matching_without_accessors(self, matchers):
        # Destructuring the reified ``Goal`` FIELD, not the accessor: the field
        # holds the raw spelling ``str``, which is a string post-flip.
        names = _all_bindings("direct_head_name", chars(_TARGET), module=matchers)
        assert set(names) == {"edge", "connected", "size"}

    def test_fact_names_only_facts(self, matchers):
        names = _all_bindings("fact_name", chars(_TARGET), module=matchers)
        assert names == [mint("edge"), mint("edge")]


class TestCallGraph:
    def test_called_predicates_with_arity(self, matchers):
        name, arity = Var(), Var()
        found = set()
        for _ in call("called_predicate", chars(_TARGET), name, arity, module=matchers):
            found.add((deref(name), deref(arity)))
        assert (mint("edge"), 2) in found
        assert (mint("connected"), 2) in found
        assert (mint("ghost"), 1) in found

    def test_undefined_call_lint_finds_ghost(self, matchers):
        names = _all_bindings("undefined_call", chars(_TARGET), module=matchers)
        assert set(names) == {mint("ghost")}


class TestEscapes:
    def test_escape_code_found_by_subterm_walk(self, matchers):
        codes = _all_bindings("escape_code", chars(_TARGET), module=matchers)
        assert codes == ["len(L)"]


class TestFiles:
    def test_file_head_names_from_real_example(self, matchers):
        path = os.path.join(EXAMPLES_DIR, "graph.clausal")
        names = _all_bindings("file_head_name", chars(path), module=matchers)
        assert mint("path") in names
        assert names.count(mint("edge")) == 7


class TestDcgMatching:
    def test_dcg_matches_bodies_starting_with_edge_call(self, matchers):
        names = _all_bindings("starts_with_edge", chars(_TARGET), module=matchers)
        assert names == [mint("connected"), mint("connected")]


class TestSourceWrittenTextArgument:
    """The SOURCE/PATH argument is a TEXT position (§9.4).

    Under ``-double_quotes(atom)`` (which this source pins) a source-written ``"…"`` is
    the atom ``("…",)``, so the old ``isinstance(source, str)`` gate made
    every source-written call fail silently — no error, no solutions.  Each
    row here writes the argument as a literal in that atom-mode source and
    asserts the real effect, not just "did not raise".
    """

    @pytest.fixture(scope="class")
    def literal_matchers(self, tmp_path_factory):
        example = os.path.join(EXAMPLES_DIR, "graph.clausal")
        source = f'''\
-double_quotes(atom)
-import_from(reflection, [
    reified_item, reified_clause, reified_file_item,
    clause_head, goal_functor, Clause,
])

# reified_clause/2 over a source-written source TEXT
literal_clause_name(NAME) <- (
    reified_clause("edge(1, 2),\\nghost(3),\\n", CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

# reified_item/2 over a source-written source TEXT
literal_item(ITEM) <- reified_item("edge(1, 2),\\nghost(3),\\n", ITEM)

# reified_file_item/2 over a source-written PATH
literal_file_name(NAME) <- (
    reified_file_item("{example}", CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)
'''
        path = tmp_path_factory.mktemp("reflection_literal") / f"m{SEAM}"
        path.write_text(source)
        mod = _load_module("_test_reflection_literal_matchers", str(path))
        return mod.__dict__["$module"]

    def test_reified_clause_reads_a_source_written_text(self, literal_matchers):
        names = _all_bindings("literal_clause_name", module=literal_matchers)
        assert names == [mint("edge"), mint("ghost")]

    def test_reified_item_reads_a_source_written_text(self, literal_matchers):
        items = _all_bindings("literal_item", module=literal_matchers)
        assert len(items) == 2
        assert all(is_v(item, Clause) for item in items)

    def test_reified_file_item_reads_a_source_written_path(
        self, literal_matchers
    ):
        names = _all_bindings("literal_file_name", module=literal_matchers)
        assert mint("path") in names
        assert names.count(mint("edge")) == 7

    def test_goal_functor_answers_an_atom_not_a_string(self, matchers):
        names = _all_bindings("head_name", chars("edge(1, 2),\n"), module=matchers)
        assert names == [mint("edge")]
        assert names[0] != chars("edge")  # a STRING would be a silent-mismatch bug


class TestPythonSide:
    def test_module_exports_vocabulary_and_builtins(self):
        from clausal.modules import reflection

        for name in (
            "reified_item", "reified_clause", "reified_file_item",
            "clause_head", "clause_body", "goal_functor", "reified_subterm",
            "Clause", "Goal", "Variable", "Atom", "Escape",
        ):
            assert hasattr(reflection, name), name
