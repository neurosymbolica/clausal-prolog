"""unnecessary_lambda.clausal: eta-reduce forwarding lambdas; refuse the rest.

A lambda argument that merely forwards its parameters to a predicate --
``((X) <- add_one(X))`` -- is that predicate, and the engine treats the bare
reference identically (pinned in test_reflection_contract.py).  The rule
replaces the lambda with ``Atom(callee)`` -- and refuses whenever the lambda
does anything besides forward: extra or reordered or repeated arguments, a
multi-goal body, an operator body, a captured enclosing variable, a variable
callee, keyword arguments, or a position that is not a direct argument of a
top-level Goal conjunct.
"""

import ast

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, call
from clausal.logic.variables import Var
from clausal.reflection import Atom, Goal, Variable, reify_ast, vfield
from clausal.rewrite.driver import rewrite_source


@pytest.fixture(scope="module")
def rules(unnecessary_lambda_rules):
    module = _load_module(
        "_rules_unnecessary_lambda_test", str(unnecessary_lambda_rules[0])
    )
    return module.__dict__["$module"]


def _reify(source):
    tree = ast.parse(source)
    stmt = tree.body[0]
    return reify_ast(stmt, source=ast.get_source_segment(source, stmt))


def _rewrite(rules_module, source):
    """The first ``rewrite_clause`` solution for the statement, or ``None``."""
    out = Var()
    for _ in call("rewrite_clause", _reify(source), out, module=rules_module):
        return _deref_walk(out)
    return None


# ---- reductions ------------------------------------------------------------


def test_reduces_single_param_forwarding_lambda(rules):
    out = _rewrite(rules, "t(L) <- (maplist(((X) <- add_one(X)), L))\n")
    assert out is not None
    assert vfield(out, "goals") == [Goal("maplist", [Atom("add_one"), Variable("L")], [])]


def test_reduces_multi_param_forwarding_lambda(rules):
    out = _rewrite(rules, "t(L, R) <- (fold(((X, V) <- score(X, V)), L, R))\n")
    assert out is not None
    assert vfield(out, "goals")[0].args[0] == Atom("score")


def test_reduces_zero_param_forwarding_lambda(rules):
    out = _rewrite(rules, "t() <- (call_goal((() <- pings())))\n")
    assert out is not None
    assert vfield(out, "goals")[0].args[0] == Atom("pings")


def test_reduces_dotted_callee_to_dotted_reference(rules):
    out = _rewrite(rules, "t(L) <- (maplist((X <- mod.pred(X)), L))\n")
    assert out is not None
    assert vfield(out, "goals")[0].args[0] == Atom("mod.pred")


def test_reduces_a_lambda_in_any_direct_argument_position(rules):
    out = _rewrite(rules, "t(L, R) <- (wrap(L, ((X) <- p(X)), R))\n")
    assert out is not None
    assert vfield(out, "goals")[0].args[1] == Atom("p")


def test_reduces_a_mid_body_goal_not_just_the_first(rules):
    out = _rewrite(rules, "t(L) <- (m(L), maplist((X <- p(X)), L), r(L))\n")
    assert out is not None
    assert vfield(out, "goals")[0] == Goal("m", [Variable("L")], [])
    assert vfield(out, "goals")[1].args[0] == Atom("p")
    assert out.goals[2] == Goal("r", [Variable("L")], [])


def test_reduces_one_argument_per_firing(rules):
    out = _rewrite(
        rules, "t(L) <- (combine((X <- p(X)), (Y <- q(Y)), L))\n"
    )
    assert out is not None
    args = vfield(out, "goals")[0].args
    assert args[0] == Atom("p")
    assert type(args[1]).__name__ == "Lambda"  # the second waits its turn


def test_containing_goal_keyword_arguments_no_longer_reach_the_rule(rules):
    """Was: keyword arguments on the CONTAINING goal ride through the
    reduction (``maplist((X <- p(X)), L, mode=2)`` keeps ``kwargs``).

    A term is built positionally since 2026-09-19, so no source reaches the
    rule carrying kwargs.  The rule's kwargs handling is untouched and goes
    with the keyword machinery in P4; two REFUSAL cases that fed it keyword
    sources were dropped from ``test_refusals`` for the same reason.
    """
    with pytest.raises(SyntaxError, match="keyword arguments"):
        _rewrite(rules, "t(L) <- (maplist((X <- p(X)), L, mode=2))\n")


def test_reduces_when_param_shadows_an_enclosing_variable(rules):
    """The engine shadows (docs/lambdas.md, pinned in the contract tests), so
    the collision is sound to reduce."""
    out = _rewrite(rules, "t(X, L) <- (m(X), maplist((X <- p(X)), L))\n")
    assert out is not None
    assert vfield(out, "goals")[1].args[0] == Atom("p")


# ---- refusals --------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        # extra/constant arguments -- the vat bisect_flip shape
        "t(L) <- (maplist(((X, V) <- reaches_percent(X, 10000, 50, V)), L))\n",
        # swapped argument order
        "t(L) <- (maplist(((X, Y) <- f(Y, X)), L))\n",
        # non-distinct params: calling the lambda also unifies them
        "t(L) <- (maplist(((X, X) <- p(X, X)), L))\n",
        # multi-goal lambda body
        "t(L) <- (maplist((X <- (p(X), q(X))), L))\n",
        # closure capture: Y comes from the enclosing clause
        "t(X, Y) <- (call_goal((V <- (helper(V, Y))), X))\n",
        # a genuine less-than-negative comparison, left untouched
        "t(A, B) <- (check(A < -B))\n",
        # an operator body is a computation, not a forward
        "t(L) <- (maplist((X <- (X > 0)), L))\n",
        # a call through a variable is not a plain predicate name
        "t(F, L) <- (maplist((X <- F(X)), L))\n",
        # forwards only SOME params
        "t(L) <- (maplist(((X, Y) <- p(X)), L))\n",
        # repeats a param: p sees it twice, the bare form would not
        "t(L) <- (maplist((X <- p(X, X)), L))\n",
        # deeper than a direct argument of a top-level conjunct
        "t(B) <- (wrap(inner((X <- p(X)), B)))\n",
        # inside an or-group
        "t(L) <- ((maplist((X <- p(X)), L)) or (m(L)))\n",
        # inside a negation
        "t(L) <- (not maplist((X <- p(X)), L))\n",
        # a fact: nothing to reduce
        "f(1),\n",
        # (two keyword-argument cases lived here — a keyword in the body call
        #  and a lambda passed by keyword.  Both sources stopped loading on
        #  2026-09-19 when a term became positional-only, so they could no
        #  longer reach the rule to be refused by it.)
    ],
)
def test_refusals(rules, source):
    assert _rewrite(rules, source) is None


# ---- through the driver ----------------------------------------------------


def test_task_examples_end_to_end(unnecessary_lambda_rules):
    result = rewrite_source(
        "t(L) <- (maplist(((X) <- add_one(X)), L))\n", unnecessary_lambda_rules
    )
    assert result.text == "t(L) <- (\n    maplist(add_one, L)\n)\n"
    result = rewrite_source(
        "t(L, R) <- (fold(((X, V) <- score(X, V)), L, R))\n",
        unnecessary_lambda_rules,
    )
    assert result.text == "t(L, R) <- (\n    fold(score, L, R)\n)\n"


def test_comments_on_the_reduced_goal_ride_unmarked(unnecessary_lambda_rules):
    src = (
        "t(L) <- (\n"
        "    m(L),\n"
        "    # check every element\n"
        "    maplist(((X) <- add_one(X)), L)  # bumped\n"
        ")\n"
    )
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert result.text == (
        "t(L) <- (\n"
        "    m(L),\n"
        "    # check every element\n"
        "    maplist(add_one, L)  # bumped\n"
        ")\n"
    )
    assert "maybe stale" not in result.text


def test_surviving_lambda_and_reduced_lambda_in_one_goal(unnecessary_lambda_rules):
    """The arrow-safety proof the driver extension demands: a goal holding
    BOTH a surviving nested lambda and the eta-reduced one emits correctly --
    the survivor keeps its ``<-``, nothing decays to ``< -``."""
    src = "t(B) <- (combine(((X, V) <- (V == X * 2)), ((Y) <- add_one(Y)), B))\n"
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert "combine(((X, V) <- (V == X * 2)), add_one, B)" in result.text
    assert "< -" not in result.text
    assert len(result.fired) == 1


def test_fixpoint_reduces_every_reducible_lambda(unnecessary_lambda_rules):
    src = "t(L, R) <- (maplist((X <- p(X)), L), fold(((A, B) <- q(A, B)), L, R))\n"
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert "maplist(p, L)" in result.text
    assert "fold(q, L, R)" in result.text
    assert len(result.fired) == 2


def test_rewritten_output_rewrites_to_itself(unnecessary_lambda_rules):
    src = "t(B) <- (combine(((X, V) <- (V == X * 2)), ((Y) <- add_one(Y)), B))\n"
    once = rewrite_source(src, unnecessary_lambda_rules)
    again = rewrite_source(once.text, unnecessary_lambda_rules)
    assert again.text == once.text
    assert again.fired == []


def test_genuine_less_than_negative_survives_the_driver(unnecessary_lambda_rules):
    src = "t(A, B) <- (m(A), check(A < -B))\n"
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert result.fired == []
    assert "check(A < -B)" in result.text


def test_both_shipped_rules_cooperate_on_one_clause(shipped_rules):
    """head_fold folds the unify goal, unnecessary_lambda reduces the lambda;
    the fixpoint applies both to the same clause."""
    src = "t(L, S) <- (maplist(((X) <- add_one(X)), L), S is done(L))\n"
    result = rewrite_source(src, shipped_rules)
    assert "t(L, done(L))" in result.text
    assert "maplist(add_one, L)" in result.text
    assert len(result.fired) == 2
