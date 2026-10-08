"""Unifying a partial list does not remember earlier unifications.

``SegList.__unify__`` (and its SegString / SegBytes twins) cached a suspended
split enumerator per term, keyed by the target's CONTENT and the trail, so
that calling it again on the same trail resumed at the next split.  A second
target EQUAL to the first therefore resumed the first one's drive instead of
starting its own: ``P = [1|T], member(P, [[1,2],[1,2],[1,2]])`` answered
twice, not three times.  Building the key also tupled and hashed the whole
target on every call, which made a DCG over a token list quadratic in time.

Each call now starts from the first split.  A partial list with one hole has
at most one split, so for it unify is exact.
"""
from __future__ import annotations

import gc
import weakref

import pytest

from clausal.logic.cells import chars
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import ConcreteSeg, SegBytes, SegList, SegString, VarSeg
from clausal.testing import load_clausal_module

_SRC = """\
mem(X, [X|_]).
mem(X, [_|T]) :- mem(X, T).
same(P)     :- P = [1|_], member(P, [[1,2],[1,2],[1,2]]).
mixed(P)    :- P = [1|_], member(P, [[1,2],[1,3],[1,2]]).
user_mem(P) :- P = [1|_], mem(P, [[1,2],[1,2],[1,2]]).
fresh(P)    :- member([1|P], [[1,2],[1,2],[1,2]]).
text(P)     :- P = [a|_], member(P, ["ab", "ab", "ab"]).
toks(0) --> [].
toks(N) --> [t], { N > 0, M is N - 1 }, toks(M).
tokens(N) :- length(L, N), maplist(=(t), L), phrase(toks(N), L).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("plmem") / "plmem.clausal"
    p.write_text(_SRC)
    return load_clausal_module(p)


@pytest.mark.parametrize("goal", ["same", "mixed", "user_mem", "fresh", "text"])
def test_every_equal_list_is_an_answer(mod, goal):
    assert sum(1 for _ in solve((goal, Var()), mod)) == 3


@pytest.mark.parametrize("term, target", [
    (lambda: SegList([ConcreteSeg([1]), VarSeg(Var())]), lambda: [1, 2]),
    (lambda: SegString(["a", VarSeg(Var())]), lambda: chars("ab")),
    (lambda: SegBytes([b"a", VarSeg(Var())]), lambda: b"ab"),
], ids=["list", "text", "bytes"])
def test_unifying_again_with_an_equal_target_succeeds_again(term, target):
    """The protocol behind the member/2 rows, at the unify call."""
    t, trail = term(), Trail()
    for _ in range(3):
        mark = trail.mark()
        assert unify(t, target(), trail)
        trail.undo(mark)


def test_a_two_hole_pattern_binds_its_first_split_every_time():
    a, b = Var(), Var()
    sl, trail = SegList([VarSeg(a), VarSeg(b)]), Trail()
    for _ in range(3):
        mark = trail.mark()
        assert unify(sl, [1, 2], trail)
        assert (deref(a), deref(b)) == ([], [1, 2])
        trail.undo(mark)


def test_unify_does_not_hash_the_target():
    """The per-call cost that made token-list parsing quadratic."""
    hashed = []

    class Tok:
        def __hash__(self):
            hashed.append(self)
            return 0

    target = [Tok() for _ in range(50)]
    assert unify(SegList([ConcreteSeg([Var()]), VarSeg(Var())]), target, Trail())
    assert hashed == []


def test_a_term_holds_no_trail():
    sl = SegList([VarSeg(Var()), VarSeg(Var())])
    refs = []
    for _ in range(5):
        t = Trail()
        unify(sl, [1, 2, 3], t)
        refs.append(weakref.ref(t))
        del t
    gc.collect()
    assert all(r() is None for r in refs)
    assert not hasattr(sl, "_unify_gens")


def test_token_list_parsing_answers(mod):
    assert next(solve(("tokens", 3000), mod), None) is not None
