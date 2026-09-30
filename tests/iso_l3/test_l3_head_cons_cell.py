"""A clause-head list pattern takes the ISO cons cell ``'.'(H, T)`` apart
(D50 follow-up).  After D50 an improper list such as ``[b|foo]`` is the
compound ``('.', H, T)``; body unification already destructured it
(``SegList.__unify__``), but the head matcher ``_head_list_unify_input``
(C, and its Python twin) failed on any tuple, so ``p([H|T], H, T)`` called
with ``[b|foo]`` had no answer.  Every expected answer below is Scryer's
(``-g Goal -g halt``)."""
from __future__ import annotations

import pytest

SRC = """\
p([H|T], H, T).
q([a, b|T], T).
r([a|T], T).
two([a, b]).
one([X], X).
f([], empty).
f([H|_], H).
f(foo, atom).
f(g(X), X).
idx([_|_], list).
idx('.'(_, _), dot).
idx(foo, foo).
t1(H-T) :- p([b|foo], H, T).
t2(T) :- q([a,b|foo], T).
t3(T) :- q([a|foo], T).
t4(T) :- r([a,b|foo], T).
t5 :- two([a,b|foo]).
t6 :- two('.'(a,'.'(b,[]))).
t7(X) :- one('.'(y,[]), X).
t8(L) :- findall(X, f([z|foo], X), L).
t9(L) :- findall(X, idx([z|foo], X), L).
t10(L) :- findall(X, idx('.'(z,[]), X), L).
t11(T) :- q([a,c|foo], T).
t12(L) :- findall(H-T, p('.'(a,'.'(b,c)), H, T), L).
t13(L) :- findall(X, f([z], X), L).
g([a|foo], lit).
g([H|_], H).
g(foo, atom).
g(bar, atom2).
g(h(1), c).
d([], nil).
d([H|_], H).
m([], [], nil).
m([H|T], H, T).
t14(L) :- findall(X, g([a|foo], X), L).
t15(L) :- findall(X, g([a], X), L).
t16(L) :- findall(X, d([q|foo], X), L).
t17(L) :- findall(H-T, m([q,r|foo], H, T), L).
"""


@pytest.fixture
def mod(native):
    return native.load("d50_head_cons", SRC)


def test_head_H_T_takes_the_cell_apart(mod, ans):
    assert ans(mod, "t1") == [("-", "b", "foo")]
    assert ans(mod, "t12") == [[("-", "a", (".", "b", "c"))]]


def test_head_with_leading_elements_walks_nested_cells(mod, ans):
    assert ans(mod, "t2") == ["foo"]
    assert ans(mod, "t4") == [(".", "b", "foo")]
    assert ans(mod, "t3") == []          # the chain is too short
    assert ans(mod, "t11") == []         # c does not match b


def test_a_proper_head_pattern_needs_the_chain_to_end_in_nil(mod, ans):
    assert ans(mod, "t5", 0) == []
    assert ans(mod, "t6", 0) == [()]
    assert ans(mod, "t7") == ["y"]


def test_first_argument_indexing_reaches_the_list_clauses(mod, ans):
    assert ans(mod, "t8") == [["z"]]
    assert ans(mod, "t9") == [["list", "dot"]]
    assert ans(mod, "t10") == [["list", "dot"]]
    assert ans(mod, "t13") == [["z"]]    # an ordinary list: unchanged
    # a literal cell head and a list-pattern head, among indexed atoms
    assert ans(mod, "t14") == [["lit", "a"]]
    assert ans(mod, "t15") == [["a"]]


def test_nil_cons_list_dispatch_scans_the_cell(mod, ans):
    assert ans(mod, "t16") == [["q"]]
    assert ans(mod, "t17") == [[("-", "q", (".", "r", "foo"))]]


@pytest.mark.parametrize("impl", ["c", "py"])
def test_c_and_python_twins_agree(impl):
    from clausal.logic.runtime import list_unify as lu
    from clausal.logic.variables import Trail, Var, deref, walk
    fn = (lu._head_list_unify_input if impl == "c"
          else lu._head_list_unify_input_py)
    if impl == "c":
        assert fn is not lu._head_list_unify_input_py, "C twin not built"
    cell = (".", "a", (".", "b", "foo"))
    h, t = Var(), Var()
    assert fn(cell, [h], t, [], Trail()) is True
    assert (deref(h), walk(deref(t))) == ("a", (".", "b", "foo"))
    t = Var()
    assert fn(cell, ["a", "b"], t, [], Trail()) is True
    assert deref(t) == "foo"
    assert fn(cell, ["a", "b", "c"], Var(), [], Trail()) is False
    assert fn(cell, ["a", "b"], None, [], Trail()) is False
    nil_cell = (".", "a", (".", "b", []))
    assert fn(nil_cell, ["a", "b"], None, [], Trail()) is True
    assert fn(nil_cell, ["a"], None, [], Trail()) is False
    # a pattern with elements after the star is a proper list: fails
    assert fn(cell, [], Var(), ["foo"], Trail()) is False
    # a failed match leaves nothing bound
    x = Var()
    tr = Trail()
    assert fn(cell, [x, "z"], Var(), [], tr) is False
    assert isinstance(deref(x), Var)
    # other tuples still fail
    assert fn(("f", "a", "b"), [Var()], Var(), [], Trail()) is False


def test_body_star_unify_takes_the_cell_apart():
    """The body-position star-list path routes a cons cell to the head
    matcher rather than failing on the tuple."""
    from clausal.logic.runtime.body_star_unify import _body_star_unify
    from clausal.logic.variables import Trail, Var, deref
    h, t = Var(), Var()
    assert _body_star_unify((".", "b", "foo"), [h], t, [], Trail())
    assert (deref(h), deref(t)) == ("b", "foo")
    assert not _body_star_unify((".", "b", "foo"), [Var(), Var()], Var(),
                                [], Trail())
