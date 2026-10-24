"""The clause compiler's compile-time twin for deep ground data
(``clausal/logic/compiler/deep_literals.py``): a ground sub-term nested past
``DEEP_LITERAL_DEPTH`` becomes a ``DeepLiteral`` leaf in the clauses the
compiler reads, and nothing else changes -- shallow clauses come back as the
same objects, a variable keeps the sub-term it sits in structural, and the
stored clause is untouched.  The end-to-end rows (assertz of a 100k-nested
term, clause/2 reading it back) are in tests/iso/test_cyclic_terms_scryer.py."""
from __future__ import annotations

from clausal.logic.compiler.deep_literals import (
    DEEP_LITERAL_DEPTH, DeepLiteral, rewrite_clauses, rewrite_term,
)
from clausal.logic.database import Clause
from clausal.logic.variables import Var, Trail, unify


def _nested(n, leaf):
    t = leaf
    for _ in range(n):
        t = ("f", t)
    return t


def test_a_shallow_term_is_the_same_object():
    t = ("g", [1, ("h", "a")], _nested(DEEP_LITERAL_DEPTH - 1, "a"))
    assert rewrite_term(t) is t                  # nested exactly to the limit
    assert type(rewrite_term(("g", t))) is DeepLiteral   # one level past it


def test_a_deep_ground_cell_becomes_one_literal_at_the_top():
    deep = _nested(DEEP_LITERAL_DEPTH + 1, "a")
    out = rewrite_term(deep)
    assert type(out) is DeepLiteral and out.term is deep


def test_the_literal_is_the_maximal_ground_sub_term():
    deep = _nested(DEEP_LITERAL_DEPTH + 50, "a")
    t = ("g", 1, deep)                       # ground, deep: the whole argument
    out = rewrite_term(t)
    assert type(out) is DeepLiteral and out.term is t
    x = Var()
    u = ("g", x, deep)                       # a variable keeps g structural
    out = rewrite_term(u)
    assert type(out) is tuple and out[0] == "g" and out[1] is x
    assert type(out[2]) is DeepLiteral and out[2].term is deep


def test_a_deep_list_and_a_bound_variable_into_a_deep_term():
    deep = [["x"]]
    for _ in range(DEEP_LITERAL_DEPTH + 5):
        deep = [deep]
    assert type(rewrite_term(deep)) is DeepLiteral
    v = Var()
    assert unify(v, _nested(DEEP_LITERAL_DEPTH + 5, "a"), Trail())
    # A BOUND variable is its value: g(V) is ground and deep, one literal.
    out = rewrite_term(("g", v))
    assert type(out) is DeepLiteral and out.term[1] is v
    # An unbound one keeps g structural; the deep value beside it is the literal.
    w = Var()
    out = rewrite_term(("g", w, v))
    assert type(out) is tuple and out[1] is w and type(out[2]) is DeepLiteral


def test_rewrite_clauses_keeps_shallow_clauses_and_the_stored_ones():
    shallow = Clause(head=("p", 1, ("q", "a")), body=[("r", [1, 2])])
    deep_term = _nested(DEEP_LITERAL_DEPTH + 1, "a")
    deep = Clause(head=("p", deep_term), body=[], hoisted=0)
    clauses = [shallow, deep]
    out = rewrite_clauses(clauses)
    assert out is not clauses
    assert out[0] is shallow
    assert out[1] is not deep and type(out[1].head[1]) is DeepLiteral
    assert deep.head[1] is deep_term, "the stored clause is as written"
    assert rewrite_clauses([shallow]) == [shallow]
