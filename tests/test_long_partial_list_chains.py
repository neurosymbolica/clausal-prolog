"""A list built forward through its open tail reads back at any length.

A DCG, or ``Hole = [a|Hole1]`` in a loop, binds each open tail to the next
partial list: the answer is a CHAIN of SegLists, one link per element.  Every
reader walked the chain recursively -- ``SegList.__walk__`` in Python, and the
C walkers behind ground/1, copy_term/2, term_variables/2 and findall/3 -- so
a DCG result of a few thousand elements raised RecursionError in unify, ==,
length/2, atom_chars/2 and the rest.  They now follow the chain iteratively.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

N = 20000      # past both old limits: ~4,000 links (Python), ~16,000 (C)

_SRC = """\
loop(0, Hole) :- Hole = [].
loop(N, Hole) :- N > 0, Hole = [a|Hole1], M is N - 1, loop(M, Hole1).
as(0) --> [].
as(N) --> [a], { N > 0, M is N - 1 }, as(M).
dcg(N, L) :- phrase(as(N), L).
ss(0) --> [].
ss(N) --> "a", { N > 0, M is N - 1 }, ss(M).
dcgs(N, L) :- phrase(ss(N), L).
opn(0, H, H).
opn(N, H, T) :- N > 0, H = [a|H1], M is N - 1, opn(M, H1, T).

c_ground(B, N) :- call(B, N, L), ground(L).
c_unify(B, N) :- call(B, N, L), length(T, N), maplist(=(a), T), L = T.
c_eq(B, N) :- call(B, N, L), call(B, N, L2), L == L2.
c_compare(B, N) :- call(B, N, L), call(B, N, L2), compare(=, L, L2).
c_copy(B, N) :- call(B, N, L), copy_term(L, C), length(C, N).
c_findall(B, N) :- findall(L, call(B, N, L), [X]), length(X, N).
c_length(B, N) :- call(B, N, L), length(L, N).
c_atom(B, N) :- call(B, N, L), atom_chars(A, L), atom_length(A, N).
c_last(B, N) :- call(B, N, L), last(L, a).
c_reverse(B, N) :- call(B, N, L), reverse(L, R), length(R, N).
c_msort(B, N) :- call(B, N, L), msort(L, S), length(S, N).

o_ground(N) :- opn(N, L, _), ground(L).
o_vars(N, Vs) :- opn(N, L, T), term_variables(L, Vs), Vs = [V], V == T.
o_copy(N) :- opn(N, L, T), copy_term(L-T, C-CT), CT = [], length(C, N), var(T).

vs(0) --> [].
vs(N) --> [_], { N > 0, M is N - 1 }, vs(M).
v_length(N, R) :- phrase(vs(N), L), length(L, R).
v_is_list(N) :- phrase(vs(N), L), is_list(L).
v_copy(N, R) :- phrase(vs(N), L), copy_term(L, C), length(C, R).
v_rest(N, R) :- phrase(vs(N), L, T), T = [], length(L, R).
v_maplist(N, R) :- phrase(vs(N), L), maplist(=(z), L), length(L, R).
v_open(N) :- phrase(vs(N), L, _), is_list(L).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("chains") / "chains.clausal"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _holds(mod, *goal):
    return next(solve(goal, mod), None) is not None


_CONSUMERS = ["c_ground", "c_unify", "c_eq", "c_compare", "c_copy", "c_findall",
              "c_length", "c_atom", "c_last", "c_reverse", "c_msort"]


@pytest.mark.parametrize("builder", ["dcg", "loop", "dcgs"])
@pytest.mark.parametrize("consumer", _CONSUMERS)
def test_a_long_chain_reads_back(mod, builder, consumer):
    assert _holds(mod, consumer, builder, N)


def test_the_answer_walks_to_text(mod):
    v = Var()
    assert next(solve(("dcg", N, v), mod), None) is not None
    assert deref(v).__walk__() == ("$chars", "a" * N)


def test_an_open_chain_is_not_ground(mod):
    assert not _holds(mod, "o_ground", N)


def test_an_open_chain_has_exactly_its_tail_as_a_variable(mod):
    assert _holds(mod, "o_vars", N, Var())


def test_a_copy_of_an_open_chain_does_not_share_its_tail(mod):
    assert _holds(mod, "o_copy", N)


def test_a_cyclic_chain_is_an_error_not_a_hang():
    src = textwrap.dedent("""
        from clausal.terms import SegList, ConcreteSeg, VarSeg
        from clausal.logic.variables import Var, Trail, unify
        x = Var()
        s = SegList([ConcreteSeg(["a"]), VarSeg(x)])
        unify(x, s, Trail())
        try:
            s.__walk__()
        except RecursionError as e:
            print("RecursionError", e)
    """)
    r = subprocess.run([sys.executable, "-c", src], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.startswith("RecursionError"), r.stdout


# A DCG over ``[_]`` builds ``[V1, *T]`` with ``T`` bound to ``[]``: a proper
# list whose elements are unbound.  length/2, is_list/1 and the list builtins
# took "not ground" for "open tail" and failed on it, at every length.
@pytest.mark.parametrize("n", [0, 1, 2, 3, 50])
@pytest.mark.parametrize("goal", ["v_length", "v_copy", "v_rest", "v_maplist"])
def test_a_closed_list_of_unbound_elements_is_a_list(mod, goal, n):
    v = Var()
    assert [deref(v) for _ in solve((goal, n, v), mod)] == [n]


@pytest.mark.parametrize("n", [0, 1, 2, 50])
def test_is_list_holds_for_unbound_elements(mod, n):
    assert _holds(mod, "v_is_list", n)


@pytest.mark.parametrize("n", [0, 1, 2])
def test_an_open_tail_is_still_not_a_list(mod, n):
    assert not _holds(mod, "v_open", n)
