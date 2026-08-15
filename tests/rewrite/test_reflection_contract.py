"""The reflection behaviors clausal-rewrite is built on, pinned as tests.

Each test documents an assumption of the rewrite driver or of a rule written in
Clausal.  A failure here is a DESIGN problem, not a bug to route around: the
rewriter reads clauses through :mod:`clausal.reflection` and writes rules as
ordinary Clausal predicates over the reified vocabulary, so if reification does
not preserve what these tests claim, the rules cannot be written this way at
all.
"""

import ast
import textwrap

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.reflection import Clause, Goal, Variable, reify_ast, render_source


def _reify_stmt(source):
    """Reify the first statement of ``source`` the way the driver will.

    Always with the original source segment: reification reads the ``<-``
    arrow off the spacing, so a segment is not an optimization, it is the only
    thing that distinguishes a lambda from a comparison.
    """
    tree = ast.parse(source)
    stmt = tree.body[0]
    return reify_ast(stmt, source=ast.get_source_segment(source, stmt))


def _rules_module(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text))
    return _load_module(name, str(path)).__dict__["$module"]


def test_inline_lambda_arrow_and_genuine_lt_reify_differently():
    lam = _reify_stmt("t(B) <- (fold(((X) <- p(X)), B))\n")
    lt = _reify_stmt("t(A, B) <- (check(A < -B))\n")
    assert repr(lam.goals) != repr(lt.goals)
    assert "< -" not in render_source(lam)
    assert "A < -B" in render_source(lt)


def test_unify_goal_reifies_as_matchable_operator_node():
    clause = _reify_stmt("r(K, S) <- (m(K, M), S is unknown(M))\n")
    assert len(clause.goals) == 2
    assert type(clause.goals[1]).__name__ == "Unify"


def test_clausal_pattern_matches_unify_goal_and_extracts_sides(tmp_path):
    """The core move of a fold rule: destructure ``V is TERM`` in Clausal."""
    module = _rules_module(tmp_path, "_spike_unify_sides", """\
        -import_from(reflection, [Clause, Goal, Variable, Atom])

        UnifySides((A is B), A, B),
        """)
    clause = _reify_stmt("r(K, S) <- (m(K, M), S is unknown(M))\n")
    left, right = Var(), Var()
    hits = 0
    for _ in call("UnifySides", clause.goals[1], left, right, module=module):
        hits += 1
        assert deref(left) == Variable("S")
        assert deref(right) == Goal("unknown", [Variable("M")], [])
        break
    assert hits == 1


def test_reified_subterm_walks_goal_lists_and_finds_variables(tmp_path):
    module = _rules_module(tmp_path, "_spike_occurs", """\
        -import_from(reflection, [reified_subterm, Variable])

        OccursIn(X, V) <- reified_subterm(X, V)
        """)
    clause = _reify_stmt("r(K, S) <- (m(K, M), S is unknown(M))\n")
    rest = [clause.goals[0]]  # the body minus the unify goal

    def occurs(container, name):
        for _ in call("OccursIn", container, Variable(name), module=module):
            return True
        return False

    assert occurs(rest, "M")  # M is used by m(K, M)
    assert not occurs(rest, "S")  # S is not -- which is what makes it foldable


def test_render_of_mutated_clause_emits_valid_clausal():
    clause = _reify_stmt("r(K, S) <- (m(K, M), S is unknown(M))\n")
    folded = Clause(
        Goal("r", [Variable("K"), Goal("unknown", [Variable("M")], [])], []),
        [clause.goals[0]],
        clause.position,
    )
    text = render_source(folded)
    assert "r(K, unknown(M))" in text
    assert "is unknown" not in text
    reparsed = reify_ast(ast.parse(text).body[0], source=text)
    assert reparsed.head == folded.head
