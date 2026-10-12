"""Building text one char at a time is linear, not quadratic.

A Python str cannot grow, so ``[a|T]`` with ``T`` a long text, or
``append("a", T, L)``, copied all of ``T`` at every step: building n chars
copied about n^2/2.  A long text built by concatenation is now a ROPE: the
same ``cells._Text`` that holds views, in its second form, a node joining
two texts (a short leaf and the shared rest).  Prepending to a node whose
leaf is short copies only the leaf; nothing is ever mutated, so an older
term -- a choice point's, another branch's -- keeps its own text.  The first
reader that needs the whole str builds it once (operator ruling 2026-10-12).
"""
from __future__ import annotations

import tracemalloc

import pytest

from clausal.logic.cells import _Text, chars, chars_text, is_chars, text_concat, ROPE_LEAF, ROPE_MIN
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_SRC = """\
rec(0, []).
rec(N, [a|T]) :- N > 0, M is N - 1, rec(M, T).
recs(0, "").
recs(N, L) :- N > 0, M is N - 1, recs(M, T), append("a", T, L).
rece(0, "").
rece(N, L) :- N > 0, M is N - 1, rece(M, T), append(T, "a", L).
two(N, X, Y) :- recs(N, T), append("x", T, X), append("y", T, Y).
recl(0, []).
recl(N, [f(N)|T]) :- N > 0, M is N - 1, recl(M, T).
as(0) --> [].
as(N) --> [a], as(M), { N is M + 1 }.
parse_built(N, K) :- recs(N, T), phrase(as(K), T).
peek(0, "").
peek(N, L) :- N > 0, M is N - 1, peek(M, T), append("a", T, L), L = [C|_], C == a.
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("ropes") / "ropes.clausal"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _solve(mod, *goal):
    out = [Var() for _ in range(goal[-1])]
    assert next(solve((*goal[:-1], *out), mod), None) is not None
    return out


# ── what a rope is ──────────────────────────────────────────────────────────

def test_a_short_concat_is_a_str_and_a_long_one_a_rope():
    assert type(text_concat("a", "b" * (ROPE_MIN - 2))) is str
    r = text_concat("a", "b" * ROPE_MIN)
    assert type(r) is _Text and r == "a" + "b" * ROPE_MIN


def test_a_rope_is_its_text():
    s = "x" * 100
    r = text_concat("ab", s)
    assert r == "ab" + s and "ab" + s == r and hash(r) == hash("ab" + s)
    assert len(r) == 102 and r[0] == "a" and r[-1] == "x" and r[1:4] == "bxx"
    assert str(r) == "ab" + s and list(r) == list("ab" + s)
    assert (r < "ac") and (r > "aa")


def test_prepending_shares_the_rest_and_copies_at_most_a_leaf():
    rest = "y" * 1000
    r1 = text_concat("a", rest)
    r2 = text_concat("b", r1)
    assert r2.right is r1.right                   # the rest is shared, not copied
    assert r2 == "ba" + rest and r1 == "a" + rest  # the older text is unchanged


def test_a_rope_carrier_and_a_str_carrier_are_one_term():
    from clausal.logic.variables import Trail, unify
    c = (chars("x")[0], text_concat("a", "b" * 200))
    assert is_chars(c) and chars_text(c) == "a" + "b" * 200
    assert unify(c, chars("a" + "b" * 200), Trail())
    assert {chars("a" + "b" * 200): 1}[c] == 1


def test_a_deep_rope_is_freed_without_a_crash():
    import subprocess, sys
    src = ("from clausal.logic.cells import text_concat\n"
           "t = 'z' * 100\n"
           "for _ in range(2_000_000): t = text_concat('a', t)\n"
           "assert len(t) == 2_000_100\n"
           "del t\nprint('ok')\n")
    r = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr[-2000:]


def _rope_nodes(t):
    n, stack = 0, [t]
    while stack:
        x = stack.pop()
        if type(x) is _Text and x.base is None:
            n += 1
            stack += [x.left, x.right]
    return n


def test_a_build_alternating_both_ends_makes_a_node_per_leaf():
    """Prepending and appending in turn still fills the short leaves -- the
    front leaf sits one level down, under the last append's node -- instead
    of making one node per char."""
    t, front, back = "x" * 64, [], []
    for i in range(4000):
        if i % 2:
            t = text_concat("p", t); front.append("p")
        else:
            t = text_concat(t, str(i % 10)); back.append(str(i % 10))
    assert _rope_nodes(t) <= 2 * 4064 // ROPE_LEAF + 4   # before a read flattens it
    assert t[0] == "p" and t.base is None                 # the front reads in place
    assert t == "".join(front[::-1]) + "x" * 64 + "".join(back)


def test_a_text_copies_as_itself_and_pickles_as_its_str():
    import copy, pickle
    deep = "z" * 64
    for _ in range(20_000):                       # deeper than the recursion limit
        deep = text_concat("a", deep)
    for t in (deep, _Text("v" * 100_000, 10, 200)):
        assert copy.copy(t) is t and copy.deepcopy(t) is t
        back = pickle.loads(pickle.dumps(t))
        assert back == t and type(back) is _Text
    # A view pickles its own chars, not the str it is a view of.
    assert len(pickle.dumps(_Text("v" * 100_000, 10, 200))) < 1000


# ── building in the engine ──────────────────────────────────────────────────

@pytest.mark.parametrize("goal", ["rec", "recs", "rece"])
def test_built_text_answers_as_before(mod, goal):
    (t,) = _solve(mod, goal, 5000, 1)
    assert t.value == chars("a" * 5000) and type(t.value[1]) is str


@pytest.mark.parametrize("goal", ["rec", "recs", "rece", "peek"])
def test_building_text_holds_memory_linear_in_the_text(mod, goal):
    """Peak memory building n chars, against the same recursion building a
    list of compounds (``recl``), which copies nothing.  When every step
    copied the text, each level kept its copy: at 20,000 chars 249-268 MB
    against recl's 55 (4.5x), and 3.3x for 2x the chars.  A rope stays
    within a small factor of recl and doubles with n.  tracemalloc counts allocations, so this does not
    depend on machine load."""
    def peak(g, n):
        tracemalloc.start()
        try:
            _solve(mod, g, n, 1)
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
    peak(goal, 500), peak("recl", 500)           # warm caches outside the measurement
    small, large, lst = peak(goal, 10_000), peak(goal, 20_000), peak("recl", 20_000)
    assert large < 3 * lst, (goal, large, lst)   # peek's extra goals keep frames: ~2.2x
    assert large / small < 2.4, (goal, small, large)


def test_two_branches_built_on_one_text_keep_their_own(mod):
    x, y = _solve(mod, "two", 300, 2)
    assert x.value == chars("x" + "a" * 300) and y.value == chars("y" + "a" * 300)


def test_a_built_rope_parses(mod):
    (k,) = _solve(mod, "parse_built", 3000, 1)
    assert deref(k) == 3000


def test_reading_the_front_of_a_rope_does_not_flatten_it():
    """``[C|Rest]`` against a rope built by prepending: the first char is in
    the leftmost leaf, and the rest is a new node sharing everything after
    it -- the rope is never built into one str."""
    r = "z" * 1000
    for _ in range(500):
        r = text_concat("a", r)
    assert r[0] == "a"
    rest = r[1:]
    assert type(rest) is _Text and rest == "a" * 499 + "z" * 1000
    assert r.base is None and r._flat is None          # still a rope
