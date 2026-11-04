"""The clause compiler's compile-time twin for deep ground data
(``clausal/logic/compiler/deep_literals.py``): a ground sub-term nested past
``DEEP_LITERAL_DEPTH`` becomes a ``DeepLiteral`` leaf in the clauses the
compiler reads, and nothing else changes -- shallow clauses come back as the
same objects, a variable keeps the sub-term it sits in structural, and the
stored clause is untouched.  The end-to-end rows (assertz of a 100k-nested
term, clause/2 reading it back) are in tests/iso/test_cyclic_terms_scryer.py."""
from __future__ import annotations

import itertools
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.logic.compiler.deep_literals import (
    DEEP_LITERAL_DEPTH, DeepLiteral, rewrite_clauses, rewrite_term,
)
from clausal.logic.database import Clause
from clausal.logic.solve import call as pcall
from clausal.logic.variables import Var, Trail, unify
from clausal.pythonic_ast.nodes import Call, LoadName


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


# ── A call whose arguments are ALL ground and deep ──────────────────────────
#
# ``Call.args`` is the call's argument SEQUENCE, not a list term.  It used to
# be rewritten as one term, so when every argument was ground and the
# sequence nested past the limit the whole ``args`` list became one
# DeepLiteral, and the first ``len(call.args)`` (the globals collector, the
# head matcher, the indexer) raised ``TypeError: object of type
# 'DeepLiteral' has no len()`` at load time.


def test_a_call_node_keeps_its_argument_list_and_each_deep_argument_is_a_leaf():
    deep = _nested(DEEP_LITERAL_DEPTH + 1, "a")
    goal = Call(func=LoadName(name="call"), args=[deep, 1], kwargs=[])
    head = Call(func=LoadName(name="h"), args=[deep], kwargs=[])
    out = rewrite_clauses([Clause(head=head, body=[goal], hoisted=0)])[0]
    for node in (out.head, out.body[0]):
        assert type(node.args) is list
        assert type(node.args[0]) is DeepLiteral and node.args[0].term is deep
    assert out.body[0].args[1] == 1
    # One level short of the limit: nothing to rewrite, the same objects.
    shallow = Call(func=LoadName(name="call"),
                   args=[_nested(DEEP_LITERAL_DEPTH - 1, "a")], kwargs=[])
    c = Clause(head="t", body=[shallow], hoisted=0)
    assert rewrite_clauses([c])[0] is c


_names = itertools.count()


def _conj(depth, last, n=20):
    """``(true, ..., true, call((... last)))``: n goals per level, *depth*
    levels of call/1 -- about 21 nested cells per level, so 12 levels nest
    well past DEEP_LITERAL_DEPTH, and the whole goal is ground."""
    goals = ["true"] * n
    goals.append(f"call(({_conj(depth - 1, last, n)}))" if depth else last)
    return ", ".join(goals)


D = f"({_conj(12, 'true')})"
DF = f"({_conj(12, 'fail')})"
DM = f"({_conj(12, 'member(_, [1, 2, 3])')})"
T = "(" + "+".join(["a"] * 300) + ")"
T2 = "(" + "+".join(["b"] * 300) + ")"
N = "(" + "+".join(["1"] * 300) + ")"

#: name -> (source, answers of t/0).  The deep goal is RUN, never taken for
#: ``true``: the ``DF`` rows fail at its bottom and the ``DM`` rows count its
#: answers.
_PROGRAMS = {
    "call": (f"t :- call({D}).", 1),
    "call_fails": (f"t :- call({DF}).", 0),
    "call_answers": (f"t :- call({DM}).", 3),
    "naf": (f"t :- \\+ {DF}, \\+ \\+ {D}.", 1),
    "findall": (f"t :- findall(x, {DF}, []), findall(x, {DM}, [x, x, x]).", 1),
    "aggregate_all": (f"t :- aggregate_all(count, {DF}, 0), "
                      f"aggregate_all(count, {D}, 1).", 1),
    "conjunction": (f"t :- true, {D}, true.", 1),
    "call_closure": (f"t :- call(','({D}), true).", 1),
    "head_and_index": (f"h(a). h({T}). h(b). h(c). h({T2}).\n"
                       f"t :- h({T}), h({T2}), findall(x, h(_), [_, _, _, _, _]).", 1),
    "head_mismatch": (f"h(a). h({T}). h(b). h(c).\nt :- h({T2}).", 0),
    "two_deep_args": (f"p({T}, {T2}).\nt :- p({T}, {T2}), \\+ p({T2}, {T}).", 1),
    "arith": (f"t :- X is {N}, X =:= 300, {N} > 299.", 1),
    "builtin": (f"t :- functor({T}, F, A), F == (+), A == 2, arg(2, {T}, a).", 1),
}


@pytest.mark.parametrize("ext", [".pl", ".clausal"])
@pytest.mark.parametrize("name", sorted(_PROGRAMS))
def test_a_deep_ground_call_argument_loads_and_runs(tmp_path, name, ext):
    src, answers = _PROGRAMS[name]
    mod = f"deeplit{next(_names)}"
    if ext == ".clausal":
        src = f":- module({mod}, [t/0]).\n{src}\n:- end_module({mod}).\n"
    path = tmp_path / f"{mod}{ext}"
    path.write_text(src + "\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # singleton-variable lint
        m = _load_module(mod, str(path)).__dict__["$module"]
    assert sum(1 for _ in pcall("t", module=m)) == answers
