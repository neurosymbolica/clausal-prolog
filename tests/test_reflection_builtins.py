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
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.reflection import Clause


EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clausal", "examples",
)


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


# DEFAULT-mode source (no ``-double_quotes(chars)``): every ``"…"`` below is a
# NAME — the functor name ``goal_functor/3`` reads and answers (§6.4) — so it
# must be an atom.  The reified ``Goal.name`` FIELD is still the raw spelling
# ``str``, which is why the DCG terminal below goes through ``goal_functor``
# rather than destructuring ``Goal("Edge", _, _)`` directly.
_MATCHERS = """\
-import_from(reflection, [
    reified_item, reified_clause, reified_file_item,
    clause_head, clause_body, goal_functor, reified_subterm,
    Clause, Goal, Variable, Atom, Escape,
])

HeadName(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

DirectHeadName(SRC, NAME) <- reified_clause(SRC, Clause(Goal(NAME, _, _), _, _))

FactName(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_body(CLAUSE, []),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

CalledPredicate(SRC, NAME, ARITY) <- (
    reified_clause(SRC, CLAUSE),
    clause_body(CLAUSE, GOALS),
    GOAL in GOALS,
    goal_functor(GOAL, NAME, ARITY)
)

DefinedName(SRC, NAME) <- HeadName(SRC, NAME)

UndefinedCall(SRC, NAME) <- (
    CalledPredicate(SRC, NAME, _),
    not DefinedName(SRC, NAME)
)

EscapeCode(SRC, CODE) <- (
    reified_item(SRC, ITEM),
    reified_subterm(ITEM, Escape(CODE, _, _))
)

FileHeadName(PATH, NAME) <- (
    reified_file_item(PATH, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

# ── DCG construction matching over a body's goal list (phase 3) ──────────────

edge_goal >> ([GOAL], {goal_functor(GOAL, "Edge", _)})
any_goal >> ([_])
any_goals >> ([])
any_goals >> (any_goal, any_goals)

starts_with_edge >> (edge_goal, any_goals)

StartsWithEdge(SRC, NAME) <- (
    reified_clause(SRC, CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _),
    clause_body(CLAUSE, GOALS),
    phrase(starts_with_edge, GOALS)
)
"""

_TARGET = """\
Edge(1, 2),
Edge(2, 3),

Connected(X, Y) <- Edge(X, Y)
Connected(X, Y) <- (Edge(X, Z), Connected(Z, Y), Ghost(Z))

Size(L, N) <- (N is ++len(L))
"""


@pytest.fixture(scope="module")
def matchers(tmp_path_factory):
    path = tmp_path_factory.mktemp("reflection") / "matchers.clausal"
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
        names = _all_bindings("HeadName", _TARGET, module=matchers)
        assert names == [
            mint("Edge"), mint("Edge"),
            mint("Connected"), mint("Connected"), mint("Size"),
        ]

    def test_direct_pattern_matching_without_accessors(self, matchers):
        # Destructuring the reified ``Goal`` FIELD, not the accessor: the field
        # holds the raw spelling ``str``, which is a string post-flip.
        names = _all_bindings("DirectHeadName", _TARGET, module=matchers)
        assert set(names) == {"Edge", "Connected", "Size"}

    def test_fact_names_only_facts(self, matchers):
        names = _all_bindings("FactName", _TARGET, module=matchers)
        assert names == [mint("Edge"), mint("Edge")]


class TestCallGraph:
    def test_called_predicates_with_arity(self, matchers):
        name, arity = Var(), Var()
        found = set()
        for _ in call("CalledPredicate", _TARGET, name, arity, module=matchers):
            found.add((deref(name), deref(arity)))
        assert (mint("Edge"), 2) in found
        assert (mint("Connected"), 2) in found
        assert (mint("Ghost"), 1) in found

    def test_undefined_call_lint_finds_ghost(self, matchers):
        names = _all_bindings("UndefinedCall", _TARGET, module=matchers)
        assert set(names) == {mint("Ghost")}


class TestEscapes:
    def test_escape_code_found_by_subterm_walk(self, matchers):
        codes = _all_bindings("EscapeCode", _TARGET, module=matchers)
        assert codes == ["len(L)"]


class TestFiles:
    def test_file_head_names_from_real_example(self, matchers):
        path = os.path.join(EXAMPLES_DIR, "graph.clausal")
        names = _all_bindings("FileHeadName", path, module=matchers)
        assert mint("Path") in names
        assert names.count(mint("Edge")) == 7


class TestDcgMatching:
    def test_dcg_matches_bodies_starting_with_edge_call(self, matchers):
        names = _all_bindings("StartsWithEdge", _TARGET, module=matchers)
        assert names == [mint("Connected"), mint("Connected")]


class TestSourceWrittenTextArgument:
    """The SOURCE/PATH argument is a TEXT position (§9.4).

    In the default ``-double_quotes(atom)`` mode a source-written ``"…"`` is
    the atom ``("…",)``, so the old ``isinstance(source, str)`` gate made
    every source-written call fail silently — no error, no solutions.  Each
    row here writes the argument as a literal in DEFAULT-mode source and
    asserts the real effect, not just "did not raise".
    """

    @pytest.fixture(scope="class")
    def literal_matchers(self, tmp_path_factory):
        example = os.path.join(EXAMPLES_DIR, "graph.clausal")
        source = f'''\
-import_from(reflection, [
    reified_item, reified_clause, reified_file_item,
    clause_head, goal_functor, Clause,
])

# reified_clause/2 over a source-written source TEXT
LiteralClauseName(NAME) <- (
    reified_clause("Edge(1, 2),\\nGhost(3),\\n", CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)

# reified_item/2 over a source-written source TEXT
LiteralItem(ITEM) <- reified_item("Edge(1, 2),\\nGhost(3),\\n", ITEM)

# reified_file_item/2 over a source-written PATH
LiteralFileName(NAME) <- (
    reified_file_item("{example}", CLAUSE),
    clause_head(CLAUSE, HEAD),
    goal_functor(HEAD, NAME, _)
)
'''
        path = tmp_path_factory.mktemp("reflection_literal") / "m.clausal"
        path.write_text(source)
        mod = _load_module("_test_reflection_literal_matchers", str(path))
        return mod.__dict__["$module"]

    def test_reified_clause_reads_a_source_written_text(self, literal_matchers):
        names = _all_bindings("LiteralClauseName", module=literal_matchers)
        assert names == [mint("Edge"), mint("Ghost")]

    def test_reified_item_reads_a_source_written_text(self, literal_matchers):
        items = _all_bindings("LiteralItem", module=literal_matchers)
        assert len(items) == 2
        assert all(isinstance(item, Clause) for item in items)

    def test_reified_file_item_reads_a_source_written_path(
        self, literal_matchers
    ):
        names = _all_bindings("LiteralFileName", module=literal_matchers)
        assert mint("Path") in names
        assert names.count(mint("Edge")) == 7

    def test_goal_functor_answers_an_atom_not_a_string(self, matchers):
        names = _all_bindings("HeadName", "Edge(1, 2),\n", module=matchers)
        assert names == [mint("Edge")]
        assert names[0] != "Edge"  # a STRING would be a silent-mismatch bug


class TestPythonSide:
    def test_module_exports_vocabulary_and_builtins(self):
        from clausal.modules import reflection

        for name in (
            "reified_item", "reified_clause", "reified_file_item",
            "clause_head", "clause_body", "goal_functor", "reified_subterm",
            "Clause", "Goal", "Variable", "Atom", "Escape",
        ):
            assert hasattr(reflection, name), name
