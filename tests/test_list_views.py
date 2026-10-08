"""A list's rest is a view of it, not a copy.

Matching ``[H|T]`` against a list -- a DCG terminal over a token list, a
clause head ``[a|T]`` recursing down one -- bound ``T`` to a fresh copy of the
rest, and the choice points of the parse kept every copy alive: parsing n
tokens copied and held about n^2/2 elements (32,000 tokens: 7.9 GB).  A long
rest is now a view (``terms.SegListView``) of the same list.  A view is a
SegList whose holes are all filled; it holds the same element objects a copy
would, so it is the same term: these tests read one through every consumer,
with ground elements and with variables in it.
"""
from __future__ import annotations

import copy
import pickle
import tracemalloc

import pytest

from clausal.logic.solve import solve, _deref_walk, _deref_walk_py
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import (ConcreteSeg, LIST_VIEW_MIN, SegList, SegListView,
                           VarSeg, list_rest)
from clausal.testing import load_clausal_module

N = 200
TOKS = [f"t{i}" for i in range(N)]

_SRC = """\
:- dynamic(fact/1).
toks(0) --> [].
toks(N) --> [_], { N > 0, M is N - 1 }, toks(M).
tokens(N, L) :- length(L, N), maplist(=(t), L).
parse(N) :- tokens(N, L), phrase(toks(N), L).
hp([], N, N).
hp([_|T], N0, N) :- N1 is N0 + 1, hp(T, N1, N).
hparse(N) :- tokens(N, L), hp(L, 0, N).
three --> [_, _, _].
rest(L, R) :- phrase(three, L, R).
head_rest([_, _, _|T], T).
eq_rest(L, T) :- L = [_, _, _|T].

c_ground(L) :- rest(L, R), ground(R).
c_copy(L, C) :- rest(L, R), copy_term(R, C).
c_vars(L, Vs) :- rest(L, R), term_variables(R, Vs).
c_eq(L) :- rest(L, R), head_rest(L, R2), R == R2.
c_compare(L, O) :- rest(L, R), compare(O, R, L).
c_msort(L, S) :- rest(L, R), msort(R, S).
c_length(L, N) :- rest(L, R), length(R, N).
c_last(L, X) :- rest(L, R), last(R, X).
c_reverse(L, X) :- rest(L, R), reverse(R, [X|_]).
c_nth(L, X) :- rest(L, R), nth0(5, R, X).
c_append(L, X) :- rest(L, R), append(R, [end], A), last(A, X).
c_member(L) :- rest(L, R), member(t9, R).
c_unify_list(L, M) :- rest(L, R), R = M.
c_dif(L, M) :- rest(L, R), dif(R, M).
c_findall(L, Rs) :- findall(R, rest(L, R), Rs).
c_assert(L, Y) :- rest(L, R), assertz(fact(R)), fact(Y).
c_atom(L, A) :- rest(L, R), atom_chars(A, R).

:- table(tl/2).
tl(L, N) :- length(L, N).
c_table(L, N) :- rest(L, R), tl(R, N).
c_table_twice(L, N) :- rest(L, R), tl(R, N), L = [_, _, _|R2], tl(R2, N).

shared(X, C) :- L = [a, b, c, X|_], length(L, 200), rest(L, R), copy_term(X-R, C).
undone(X, Rs) :- L = [a, b, c, X|_], length(L, 200),
                 findall(R, (X = 1, rest(L, R)), Rs).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("lviews") / "lviews.clausal"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _one(mod, name, *args):
    v = Var()
    assert next(solve((name, *args, v), mod), None) is not None, name
    return v


def _holds(mod, *goal):
    return next(solve(goal, mod), None) is not None


# ── what a view is ──────────────────────────────────────────────────────────

def test_a_short_rest_is_a_list_and_a_long_one_a_view():
    assert type(list_rest(TOKS, 0, LIST_VIEW_MIN - 1)) is list
    v = list_rest(TOKS, 0, LIST_VIEW_MIN)
    assert type(v) is SegListView and v.base is TOKS


def test_a_view_is_its_elements():
    v = list_rest(TOKS, 10, 150)
    assert v == TOKS[10:150] and len(v) == 140 and list(v) == TOKS[10:150]
    assert v[0] == "t10" and v[-1] == "t149" and v.__walk__() == TOKS[10:150]
    assert v != TOKS[10:151]
    w = v[5:100]
    assert type(w) is SegListView and w.base is TOKS and w == TOKS[15:110]


def test_a_view_unifies_as_its_elements():
    t = Trail()
    assert unify(list_rest(TOKS, 10, 150), list(TOKS[10:150]), t)
    assert not unify(list_rest(TOKS, 10, 150), TOKS[10:149], t)
    assert not unify(list_rest(TOKS, 10, 150), [], t)
    x = Var()
    pattern = SegList([ConcreteSeg(["t10"]), VarSeg(x)])
    assert unify(pattern, list_rest(TOKS, 10, 150), t)
    assert deref(x) == TOKS[11:150]


def test_a_rebuilt_view_is_a_seglist():
    """A copier rebuilds a Seg* as ``type(t)(segments)``."""
    v = list_rest(TOKS, 10, 150)
    r = type(v)(v._segments)
    assert type(r) is SegList and r == TOKS[10:150]


def test_a_view_copies_and_pickles_as_its_elements():
    v = list_rest(TOKS, 10, 150)
    assert copy.deepcopy(v) == TOKS[10:150]
    assert pickle.loads(pickle.dumps(v)) == TOKS[10:150]


def test_a_shrunk_list_under_a_view_is_an_error_not_a_crash():
    base = list(TOKS)
    v = list_rest(base, 10, 150)
    del base[20:]
    with pytest.raises(Exception):
        v.elements()
    from clausal.logic.runtime._list_unify import _head_list_unify_input
    with pytest.raises(ValueError):
        _head_list_unify_input(v, [Var()], Var(), [], Trail())


# ── views made by programs ──────────────────────────────────────────────────

@pytest.mark.parametrize("goal", ["rest", "head_rest", "eq_rest"])
def test_the_rest_of_a_long_list_is_a_view(mod, goal):
    r = deref(_one(mod, goal, list(TOKS)))
    assert type(r) is SegListView and r == TOKS[3:]


@pytest.mark.parametrize("goal", ["parse", "hparse"])
def test_parsing_answers_as_before(mod, goal):
    assert _holds(mod, goal, 3000)


@pytest.mark.parametrize("goal", ["parse", "hparse"])
def test_parsing_holds_memory_linear_in_the_list(mod, goal):
    """Peak memory at 2n over peak at n: about 2 with views, toward 4 with
    copies.  tracemalloc counts allocations, so load does not move it."""
    def peak(n):
        tracemalloc.start()
        try:
            assert _holds(mod, goal, n)
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
    peak(500)
    small, large = peak(4000), peak(8000)
    assert large / small < 2.6, (small, large)


# ── every consumer reads a view as the list it is ──────────────────────────

REST = TOKS[3:]


@pytest.mark.parametrize("goal, expected", [
    ("c_copy", REST), ("c_vars", []), ("c_msort", sorted(REST)),
    ("c_length", N - 3), ("c_last", TOKS[-1]), ("c_reverse", TOKS[-1]),
    ("c_nth", TOKS[8]), ("c_append", "end"), ("c_compare", ">"),
    ("c_findall", [REST]), ("c_assert", REST),
])
def test_a_consumer_answers_on_a_view(mod, goal, expected):
    got = _one(mod, goal, list(TOKS)).value
    assert got == expected
    if isinstance(expected, list) and expected:
        assert type(got) is list or type(got) is SegList


@pytest.mark.parametrize("goal", ["c_ground", "c_eq", "c_member"])
def test_a_test_holds_on_a_view(mod, goal):
    assert _holds(mod, goal, list(TOKS))


def test_unify_and_dif_read_a_view(mod):
    assert _holds(mod, "c_unify_list", list(TOKS), list(REST))
    assert not _holds(mod, "c_unify_list", list(TOKS), REST[:-1])
    assert _holds(mod, "c_dif", list(TOKS), REST[:-1])
    assert not _holds(mod, "c_dif", list(TOKS), list(REST))


def test_a_view_is_a_tabled_call_argument(mod):
    assert _one(mod, "c_table", list(TOKS)).value == N - 3
    assert _one(mod, "c_table_twice", list(TOKS)).value == N - 3


def test_atom_chars_reads_a_view(mod):
    chars = [chr(97 + i % 26) for i in range(N)]
    assert _one(mod, "c_atom", chars).value == "".join(chars[3:])


def test_an_asserted_view_is_stored_as_its_elements(mod):
    got = _one(mod, "c_assert", list(TOKS))
    assert type(deref(got)) is not SegListView


# ── views with variables in them ────────────────────────────────────────────

def test_a_view_with_unbound_variables_is_not_ground(mod):
    lst = list(TOKS)
    lst[100] = Var()
    assert not _holds(mod, "c_ground", lst)
    vs = _one(mod, "c_vars", lst).value
    assert len(vs) == 1 and vs[0] is lst[100]


def test_copy_term_maps_a_variable_inside_a_view_with_the_rest(mod):
    x, c = Var(), Var()
    assert _holds(mod, "shared", x, c)
    cx, cr = deref(c)[1], deref(deref(c)[2])
    cr = cr.__walk__() if hasattr(cr, "__walk__") else cr
    assert deref(cx) is not x and cr[0] is deref(cx)


def test_a_copied_view_keeps_a_binding_that_backtracking_undoes(mod):
    """``findall`` copies each answer: a view whose element was bound in the
    answer and unbound after must copy the bound value."""
    x = Var()
    rs = _one(mod, "undone", x).value
    assert not x.is_bound
    (r,) = rs
    r = r.__walk__() if hasattr(r, "__walk__") else r
    assert r[0] == 1


# ── views leaving the engine ────────────────────────────────────────────────

def test_value_hands_out_a_list_not_a_view(mod):
    r = _one(mod, "rest", list(TOKS))
    assert type(deref(r)) is SegListView
    assert type(r.value) is list and r.value == REST


@pytest.mark.parametrize("walk", [_deref_walk, _deref_walk_py], ids=["c", "py"])
def test_a_walked_answer_holds_no_view(mod, walk):
    r = _one(mod, "rest", list(TOKS))
    out = walk(("f", deref(r), [deref(r)]))
    assert type(out[1]) is list and type(out[2][0]) is list and out[1] == REST


# ── hostile and boundary cases (security review, 2026-10-09) ────────────────

_SHRINK = """
import sys
from clausal.logic.variables import Var, Trail
from clausal.terms import list_rest
from clausal.logic.runtime._list_unify import _head_list_unify_input as H
class Shrinker:
    def __unify__(self, other, trail):
        victim.clear()
        return True
victim = [Shrinker()] + [object() for _ in range(199)]
t = list_rest(victim, 0, 200) if sys.argv[1] == "view" else victim
try:
    H(t, ["a", "b", "c"], Var(), [], Trail())
except ValueError as e:
    print("ValueError", e)
"""


@pytest.mark.parametrize("shape", ["view", "list"])
def test_a_list_shrunk_by_a_hook_mid_match_is_an_error_not_a_crash(shape):
    """The plain-list arm read past the end of a list a unify hook had
    cleared (a segfault on main); both arms now re-check the bound."""
    import subprocess, sys
    r = subprocess.run([sys.executable, "-c", _SHRINK, shape], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.startswith("ValueError"), r.stdout


def test_python_code_at_an_escape_gets_a_list(tmp_path):
    p = tmp_path / "esc.seam"
    p.write_text(
        "kind(K) <- (L is ++list(range(200)), [_, _, _, *R] is L,"
        " K is ++type(R).__name__)\n")
    m = load_clausal_module(p)
    k = Var()
    assert next(solve(("kind", k), m), None) is not None
    assert k.value == "list"


def test_value_hands_out_the_elements_as_a_copy_would():
    x = Var()
    lst = ["a"] * 10 + [x] + ["b"] * 189
    r, t = Var(), Trail()
    assert unify(r, list_rest(lst, 3, 200), t)
    assert type(r.value) is list and r.value[7] is x


def test_a_pickled_view_holds_its_window_not_its_base():
    big = list(range(1_000_000))
    v = list_rest(big, 10, 110)
    assert len(pickle.dumps(v)) < 2000
    assert pickle.loads(pickle.dumps(v)) == big[10:110]


def test_a_view_equals_a_seglist_of_its_elements_however_segmented():
    v = list_rest(TOKS, 10, 150)
    s = SegList([ConcreteSeg(TOKS[10:11]), ConcreteSeg(TOKS[11:150])])
    assert v == s and s == v
    assert not (v == SegList([ConcreteSeg(TOKS[10:149])]))


def test_a_views_window_is_read_only():
    v = list_rest(TOKS, 10, 150)
    for attr in ("base", "lo", "hi"):
        with pytest.raises(AttributeError):
            setattr(v, attr, 0)
