"""Tests for clausal.reflection — AST reflection into Clausal compound terms.

Phase 1 of implementation_plans/clausal-ast-reflection-and-structural-matching.md:
``reify_source`` / ``reify_ast`` map ``.clausal`` source onto a reified term
vocabulary (Clause, Goal, Variable, Atom, Escape, …) without executing the
module, loading directives, or compiling any predicate.
"""

import ast
import os

import pytest

from clausal.logic.cells import chars
from clausal.reflection import (
    Atom,
    Clause,
    Escape,
    FormatString,
    Goal,
    IfThenElse,
    ModuleDirective,
    PythonCode,
    ReifyError,
    Variable,
    reify_ast,
    reify_source,
)


EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clausal", "examples",
)


def clauses_of(items):
    return [item for item in items if isinstance(item, Clause)]


def directives_of(items):
    return [item for item in items if isinstance(item, ModuleDirective)]


# ── Facts ────────────────────────────────────────────────────────────────────


class TestFacts:
    def test_ground_fact_becomes_clause_with_empty_goals(self):
        items = reify_source("edge(1, 2),\n")
        (clause,) = clauses_of(items)
        assert clause.goals == []

    def test_fact_head_is_goal_with_functor_and_args(self):
        items = reify_source("edge(1, 2),\n")
        (clause,) = clauses_of(items)
        head = clause.head
        assert isinstance(head, Goal)
        assert head.name == "edge"
        assert head.args == [1, 2]
        assert head.kwargs == []

    def test_multiple_facts_in_order(self):
        items = reify_source("edge(1, 2),\nedge(2, 3),\n")
        heads = [c.head.args for c in clauses_of(items)]
        assert heads == [[1, 2], [2, 3]]

    def test_quoted_atom_reifies_as_atom_and_a_float_stays_raw(self):
        # THE FLIP: ``'widget'`` is an ATOM in every mode, and the reified
        # vocabulary spells an atom ``Atom(name)`` -- the SAME term the bare
        # name ``widget`` reifies to (see the next test).  A number stays raw.
        items = reify_source("item('widget', 2.5),\n")
        (clause,) = clauses_of(items)
        assert clause.head.args == [Atom("widget"), 2.5]

    def test_string_literal_stays_raw(self):
        # A STRING (chars mode) reifies as the plain ``str`` it is.
        items = reify_source('-double_quotes(chars)\nitem("widget", 2.5),\n')
        (clause,) = clauses_of(items)
        assert clause.head.args == ["widget", 2.5]   # STAGE 2: the vocabulary spells a string as the str; an atom is Atom(name)

    def test_atom_argument_reifies_as_atom(self):
        items = reify_source("status(ok, 1),\n")
        (clause,) = clauses_of(items)
        atom, one = clause.head.args
        assert atom == Atom("ok")
        assert one == 1

    def test_negative_number_literal(self):
        items = reify_source("temp(-40),\n")
        (clause,) = clauses_of(items)
        assert clause.head.args == [-40]

    def test_list_argument_reifies_elementwise(self):
        items = reify_source("path([1, 2, 3]),\n")
        (clause,) = clauses_of(items)
        assert clause.head.args == [[1, 2, 3]]


# ── Rules ────────────────────────────────────────────────────────────────────


class TestRules:
    def test_rule_body_is_list_of_goals(self):
        items = reify_source(
            "connected(X, Y) <- edge(X, Y)\n"
        )
        (clause,) = clauses_of(items)
        assert clause.head == Goal("connected", [Variable("X"), Variable("Y")], [])
        (goal,) = clause.goals
        assert goal == Goal("edge", [Variable("X"), Variable("Y")], [])

    def test_conjunction_flattens_to_goal_list(self):
        items = reify_source(
            "grandparent(X, Z) <- (parent(X, Y), parent(Y, Z))\n"
        )
        (clause,) = clauses_of(items)
        assert [g.name for g in clause.goals] == ["parent", "parent"]

    def test_head_and_body_share_variable_terms(self):
        items = reify_source("connected(X, Y) <- edge(X, Y)\n")
        (clause,) = clauses_of(items)
        assert clause.head.args == clause.goals[0].args

    def test_anonymous_variables_are_numbered_distinctly(self):
        items = reify_source("reachable(X) <- edge(_, _)\n")
        (clause,) = clauses_of(items)
        a, b = clause.goals[0].args
        assert isinstance(a, Variable) and isinstance(b, Variable)
        assert a.name != b.name

    def test_leading_underscore_variable_keeps_its_name(self):
        items = reify_source("foo(_x) <- bar(_x)\n")
        (clause,) = clauses_of(items)
        assert clause.head.args == [Variable("_x")]

    def test_qualified_goal_gets_dotted_name(self):
        items = reify_source("uses(X) <- mod.Other(X)\n")
        (clause,) = clauses_of(items)
        assert clause.goals[0].name == "mod.Other"

    def test_a_keyword_goal_argument_is_refused_at_load(self):
        """Was: ``bar(Y=X)`` reifies with ``kwargs == [["Y", Variable("X")]]``.

        The keyword SPELLING was retired 2026-09-19 (a term is built
        positionally), so no source can produce a goal with kwargs any more.
        The reified ``Goal.kwargs`` FIELD still exists and is still populated
        by anything building a Goal directly — what is gone is the surface
        that reached it, which is why this pins the refusal rather than the
        reification.
        """
        with pytest.raises(SyntaxError, match="keyword arguments"):
            reify_source("foo(X) <- bar(Y=X)\n")

    def test_compound_argument_in_head_reifies_as_goal(self):
        items = reify_source("holds(state(X)) <- check(X)\n")
        (clause,) = clauses_of(items)
        (arg,) = clause.head.args
        assert arg == Goal("state", [Variable("X")], [])

    def test_clause_position_covers_source_line(self):
        items = reify_source("edge(1, 2),\nconnected(X, Y) <- edge(X, Y)\n")
        fact, rule = clauses_of(items)
        assert fact.position[0] == 1
        assert rule.position[0] == 2


# ── Operator / control goals ─────────────────────────────────────────────────


class TestOperatorGoals:
    def test_arith_goal_stays_raw_operator_node(self):
        from clausal.pythonic_ast.nodes import Unify, Add

        items = reify_source("next(X, Y) <- (Y == X + 1)\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        # ArithEq node ('==') — right side is a raw Add over reified leaves.
        assert goal.right == Add(left=Variable("X"), right=1)

    def test_comparison_goal_stays_raw(self):
        from clausal.pythonic_ast.nodes import Gt

        items = reify_source("positive(X) <- (X > 0)\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        assert isinstance(goal, Gt)
        assert goal.left == Variable("X")
        assert goal.right == 0

    def test_negation_stays_raw_not_node(self):
        from clausal.pythonic_ast.nodes import Not

        items = reify_source("free(X) <- (not busy(X))\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        assert isinstance(goal, Not)
        assert goal.operand == Goal("busy", [Variable("X")], [])

    def test_disjunction_stays_raw_or_node(self):
        from clausal.pythonic_ast.nodes import Or

        items = reify_source("either(X) <- (alpha(X) or beta(X))\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        assert isinstance(goal, Or)
        assert goal.left == Goal("alpha", [Variable("X")], [])
        assert goal.right == Goal("beta", [Variable("X")], [])

    def test_disjunction_of_conjunctions_normalizes_sides_to_lists(self):
        from clausal.pythonic_ast.nodes import Or

        items = reify_source("either(X) <- ((alpha(X), beta(X)) or gamma(X))\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        assert isinstance(goal, Or)
        assert [g.name for g in goal.left] == ["alpha", "beta"]
        assert goal.right == Goal("gamma", [Variable("X")], [])

    def test_if_expression_reifies_as_if_then_else(self):
        items = reify_source("sign(X, S) <- (S is if_(X > 0, 1, -1))\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        ite = goal.right
        assert isinstance(ite, IfThenElse)
        assert ite.then == 1
        assert ite.otherwise == -1


# ── Escapes and f-strings ────────────────────────────────────────────────────


class TestEscapes:
    def test_value_escape_reifies_with_code_and_vars(self):
        items = reify_source("len(L, N) <- (N is ++len(L))\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        esc = goal.right
        assert isinstance(esc, Escape)
        assert esc.code == "len(L)"
        assert esc.vars == [Variable("L")]

    def test_goal_escape_reifies_as_escape_goal(self):
        items = reify_source("show(X) <- ++print(X)\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        assert isinstance(goal, Escape)
        assert goal.code == "print(X)"

    def test_escape_is_not_executed_during_reification(self):
        # Reifying must never run the escaped Python.
        reify_source("boom(X) <- ++__import__('sys').exit(99)\n")

    def test_fstring_reifies_as_format_string(self):
        items = reify_source("msg(X, S) <- (S is f'value {X}')\n")
        (clause,) = clauses_of(items)
        (goal,) = clause.goals
        fs = goal.right
        assert isinstance(fs, FormatString)
        assert fs.vars == [Variable("X")]
        assert "value" in fs.code


# ── Directives ───────────────────────────────────────────────────────────────


class TestDirectives:
    def test_dynamic_directive(self):
        items = reify_source("-dynamic(color/2)\n")
        (directive,) = directives_of(items)
        assert directive.name == "dynamic"
        assert directive.args == [["color", 2]]

    def test_import_from_directive(self):
        items = reify_source("-import_from(regex, [match, search])\n")
        (directive,) = directives_of(items)
        assert directive.name == "import_from"
        assert directive.args == ["regex", ["match", "search"]]

    def test_module_declaration(self):
        items = reify_source(
            "-module(graph, [path(X, Y, PATH)])\n\npath(X, Y, PATH) <- step(X, Y, PATH)\n"
        )
        (directive,) = directives_of(items)
        assert directive.name == "module"
        assert directive.args[0] == "graph"


# ── Embedded Python ──────────────────────────────────────────────────────────


class TestEmbeddedPython:
    def test_python_function_becomes_python_code_item(self):
        items = reify_source("def helper(x):\n    return x + 1\n")
        (item,) = [i for i in items if isinstance(i, PythonCode)]
        assert item.kind == "function"
        assert item.name == "helper"

    def test_top_level_python_is_not_executed(self, capsys):
        items = reify_source("print('SIDE EFFECT')\n\nedge(1, 2),\n")
        assert capsys.readouterr().out == ""
        assert len(clauses_of(items)) == 1


# ── reify_ast ────────────────────────────────────────────────────────────────


class TestReifyAst:
    def test_reify_ast_on_parsed_statement(self):
        node = ast.parse("connected(X, Y) <- edge(X, Y)").body[0]
        clause = reify_ast(node)
        assert isinstance(clause, Clause)
        assert clause.head.name == "connected"

    def test_reify_ast_on_expression_node(self):
        node = ast.parse("edge(X, 1)", mode="eval").body
        goal = reify_ast(node)
        assert goal == Goal("edge", [Variable("X"), 1], [])


# ── Matching (the point of the feature) ──────────────────────────────────────


class TestStructuralMatching:
    def test_reified_clause_unifies_with_goal_pattern(self):
        from clausal.logic.builtins import structural_unify
        from clausal.logic.variables import Trail, Var, deref

        items = reify_source("connected(X, Y) <- edge(X, Y)\n")
        (clause,) = clauses_of(items)
        name, args = Var(), Var()
        trail = Trail()
        assert structural_unify(Goal(name, args), clause.head, trail)
        assert deref(name) == "connected"

    def test_goal_pattern_with_fewer_fields_acts_as_wildcard(self):
        from clausal.logic.builtins import structural_unify
        from clausal.logic.variables import Trail, Var

        items = reify_source("edge(1, 2),\n")
        (clause,) = clauses_of(items)
        head_var = Var()
        trail = Trail()
        assert structural_unify(Clause(head_var, []), clause, trail)


# ── Real example files ───────────────────────────────────────────────────────


class TestRealExamples:
    def test_graph_example_reifies(self):
        source = open(os.path.join(EXAMPLES_DIR, "graph.clausal")).read()
        items = reify_source(source, filename="graph.clausal")
        clauses = clauses_of(items)
        directives = directives_of(items)
        assert {d.name for d in directives} >= {"module", "private"}
        edge_facts = [
            c for c in clauses
            if c.head.name == "edge" and c.goals == []
        ]
        assert len(edge_facts) == 7
        path_rules = [c for c in clauses if c.head.name == "path"]
        assert len(path_rules) == 1

    def test_symbolic_diff_example_reifies_operator_heads(self):
        source = open(os.path.join(EXAMPLES_DIR, "symbolic_diff.clausal")).read()
        items = reify_source(source, filename="symbolic_diff.clausal")
        assert clauses_of(items)

    def test_all_examples_reify_without_error(self):
        import glob

        for path in glob.glob(os.path.join(EXAMPLES_DIR, "*.clausal")):
            items = reify_source(open(path).read(), filename=path)
            assert items, f"no items reified from {path}"


# ── Errors ───────────────────────────────────────────────────────────────────


class TestErrors:
    def test_syntax_error_raises_reify_error(self):
        with pytest.raises((ReifyError, SyntaxError)):
            reify_source("foo(X <- bar(X)\n")
