"""head_fold.clausal: fold ``V is TERM`` into the head; refuse everything else.

``X is T`` is unification, never arithmetic, so a body goal that only unifies a
head variable with a term is saying something the head could say itself.  The
rule moves it there -- and refuses whenever moving it would change what the
clause means.

Legality, each condition with a refusal test below: the goal is a top-level
conjunct; one side is a bare variable that occurs in the head; that variable
occurs nowhere else in the body and not inside the folded term; and the folded
term is constructor-shaped -- a Goal without keywords, an Atom, a Variable, an
int/str/bool, or a list of those.  An escape, an f-string, a lambda or an
operator term refuses.  Operator terms WOULD be sound, since they are still
unification; v1 stays strict rather than argue the case one term at a time.
"""

import ast

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, call
from clausal.logic.variables import Var
from clausal.reflection import Atom, Goal, Variable, reify_ast


@pytest.fixture(scope="module")
def rules(head_fold_rules):
    module = _load_module("_rules_head_fold_test", str(head_fold_rules[0]))
    return module.__dict__["$module"]


def _reify(source):
    tree = ast.parse(source)
    stmt = tree.body[0]
    return reify_ast(stmt, source=ast.get_source_segment(source, stmt))


def _rewrite(rules_module, source):
    """The first ``RewriteClause`` solution for the statement, or ``None``."""
    out = Var()
    for _ in call("RewriteClause", _reify(source), out, module=rules_module):
        return _deref_walk(out)
    return None


# ---- folds ----------------------------------------------------------------


def test_folds_constructor_term_into_head(rules):
    out = _rewrite(rules, "r(K, S) <- (m(K, M), S is unknown(M))\n")
    assert out is not None
    assert out.head == Goal(
        "r", [Variable("K"), Goal("unknown", [Variable("M")], [])], []
    )
    assert len(out.goals) == 1  # the unify goal is gone


def test_folds_atom(rules):
    out = _rewrite(rules, "s(P, V) <- (m(P), V is eligible)\n")
    assert out is not None
    assert out.head == Goal("s", [Variable("P"), Atom("eligible")], [])


def test_folds_whole_body_to_fact(rules):
    out = _rewrite(rules, "p(X) <- (X is 5)\n")
    assert out.head == Goal("p", [5], [])
    assert out.goals == []


def test_folds_mid_body_goal_not_just_last(rules):
    out = _rewrite(rules, "r(A, B) <- (x(1), B is tag(2), y(A))\n")
    assert out is not None
    assert out.goals == [
        Goal("x", [1], []),
        Goal("y", [Variable("A")], []),
    ]


def test_folds_variable_on_right_side(rules):
    out = _rewrite(rules, "r(K, S) <- (m(K), unknown(K) is S)\n")
    assert out is not None
    assert out.head.args[1] == Goal("unknown", [Variable("K")], [])


def test_substitutes_every_head_occurrence(rules):
    out = _rewrite(rules, "r(S, S) <- (S is ok)\n")
    assert out is not None
    assert out.head == Goal("r", [Atom("ok"), Atom("ok")], [])


def test_folds_a_list_of_constructor_shapes(rules):
    out = _rewrite(rules, "r(S) <- (S is [a, b])\n")
    assert out is not None
    assert out.head == Goal("r", [[Atom("a"), Atom("b")]], [])


def test_folds_a_nested_goal_term(rules):
    out = _rewrite(rules, "r(K, S) <- (m(K, M), S is outer(inner(M), tag))\n")
    assert out is not None
    assert out.head.args[1] == Goal(
        "outer", [Goal("inner", [Variable("M")], []), Atom("tag")], []
    )


# ---- refusals -------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        # a guard: the variable is bound by an earlier goal, and the unify goal
        # is the check.  Folding it would make head unification do the checking
        # and the guard would stop guarding.
        "r(K, S) <- (acc(K, A), A is met, s(A, S))\n",
        # the variable occurs elsewhere in the body
        "r(K, S) <- (S is unknown(K), log(S))\n",
        # the variable does not occur in the head
        "r(K) <- (m(K, M), S is unknown(M))\n",
        # occurs check: the folded term contains the variable itself
        "r(S) <- (S is wrap(S))\n",
        # inside an or-group: folding imposes one branch's binding on both
        "r(K, S) <- ((S is a) or (S is b))\n",
        # an escape in the folded term: evaluation timing must not move
        "r(L, N) <- (N is ++len(L))\n",
        # an operator term: sound, but refused in v1
        "r(A, B, S) <- (m(A, B), S is A + B)\n",
        # a lambda in the folded term
        "r(F) <- (F is ((X) <- p(X)))\n",
        # an f-string in the folded term
        'r(N, S) <- (m(N), S is f"hello {N}")\n',
        # a fact: nothing to fold
        "f(1),\n",
        # neither side is a bare variable
        "r(K) <- (m(K), tag(K) is other(K))\n",
    ],
)
def test_refusals(rules, source):
    assert _rewrite(rules, source) is None
