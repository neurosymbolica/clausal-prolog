"""A text's rest is a view of it, not a copy.

Matching ``[a|Rest]`` against text -- a DCG terminal, or a clause head over a
string -- bound ``Rest`` to a fresh str holding the rest, and the choice points
of the parse kept every one of those alive: parsing n chars held about n^2/2
chars (a 32,000-char DCG parse peaked at 723 MB).  A long rest is now a view
(``cells._Text``) of the same str, held in the chars carrier in place of a str.
A view IS its text: equal, ordered and hashed like it, one dict key and one
tabling key with it.
"""
from __future__ import annotations

import tracemalloc

import pytest

from clausal import to_python
from clausal.logic.cells import _Text, chars, chars_text, is_chars, text_slice, VIEW_MIN
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.testing import load_clausal_module

TEXT = "".join(chr(97 + i % 26) for i in range(500))


def _view(lo=10, hi=400):
    v = text_slice(TEXT, lo, hi)
    assert type(v) is _Text
    return v


# ── what a view is ──────────────────────────────────────────────────────────

def test_a_short_slice_is_a_str_and_a_long_one_a_view():
    assert type(text_slice(TEXT, 0, VIEW_MIN - 1)) is str
    assert type(text_slice(TEXT, 0, VIEW_MIN)) is _Text


def test_a_view_is_its_text():
    v, s = _view(), TEXT[10:400]
    assert v == s and s == v and not (v != s)
    assert hash(v) == hash(s)
    assert len(v) == len(s) and v[0] == s[0] and v[-1] == s[-1]
    assert str(v) == s and list(v) == list(s)
    assert v != TEXT[10:401] and v != TEXT[11:401]


def test_a_view_orders_like_its_text():
    v = _view()
    for other in (TEXT[10:400], "a", "zzz", TEXT[:390]):
        assert (v < other) == (TEXT[10:400] < other)
        assert (v > other) == (TEXT[10:400] > other)


def test_a_slice_of_a_view_is_a_view_of_the_same_str():
    w = _view()[5:300]
    assert type(w) is _Text and w.base is TEXT and w == TEXT[15:310]
    assert type(_view()[5:20]) is str


def test_a_mismatched_length_never_builds_the_text():
    v = _view()
    assert v != "short" and v._flat is None


def test_a_view_carrier_is_a_carrier_and_crosses_out_as_a_str():
    c = (chars("x")[0], _view())
    assert is_chars(c) and chars_text(c) == TEXT[10:400]
    assert to_python(c) == TEXT[10:400] and type(to_python(c)) is str


def test_a_view_carrier_and_a_str_carrier_are_one_dict_key():
    d = {chars(TEXT[10:400]): 1}
    assert d[(chars("x")[0], _view())] == 1


def test_a_view_carrier_and_a_str_carrier_have_one_tabling_key():
    from clausal.logic.tabling import _normalize_for_key, _normalize_for_key_py
    c = (chars("x")[0], _view())
    for norm in (_normalize_for_key, _normalize_for_key_py):
        assert norm(c) == norm(chars(TEXT[10:400]))


@pytest.mark.parametrize("other", [
    lambda: chars(TEXT[10:400]),
    lambda: list(TEXT[10:400]),
])
def test_a_view_carrier_unifies_with_its_text(other):
    t = Trail()
    assert unify((chars("x")[0], _view()), other(), t)
    assert not unify((chars("x")[0], _view()), chars(TEXT[10:399]), t)


# ── views made by programs ──────────────────────────────────────────────────

_SRC = """\
as(0) --> [].
as(N) --> [a], { N > 0, M is N - 1 }, as(M).
acc(N, N) --> [].
acc(N0, N) --> [a], { N1 is N0 + 1 }, acc(N1, N).
parse(N, Text) :- phrase(acc(0, N), Text).
hp(N, N, []).
hp(N0, N, [a|T]) :- N1 is N0 + 1, hp(N1, N, T).
hparse(N, Text) :- hp(0, N, Text).
rest(Text, Rest) :- phrase(as(3), Text, Rest).
head_rest([_, _, _|T], T).
wrap(Text, [x, R, f(R)]) :- head_rest(Text, R).
:- dynamic(fact/1).
keep(Text, Y) :- rest(Text, R), assertz(fact(R)), fact(Y).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("views") / "views.clausal"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _one(mod, *goal):
    v = Var()
    assert next(solve((*goal, v) if goal[0] in ("rest", "head_rest", "keep", "wrap") else (goal[0], v, *goal[1:]), mod), None) is not None
    return deref(v)


@pytest.mark.parametrize("goal", ["rest", "head_rest"])
def test_the_rest_of_a_long_text_is_a_view(mod, goal):
    text = "aaa" + TEXT
    rest = _one(mod, goal, chars(text))
    assert is_chars(rest) and type(rest[1]) is _Text
    assert rest == chars(TEXT) and chars_text(rest) == TEXT


@pytest.mark.parametrize("goal", ["parse", "hparse"])
def test_parsing_answers_as_before(mod, goal):
    assert _one(mod, goal, chars("a" * 3000)) == 3000


@pytest.mark.parametrize("goal", ["parse", "hparse"])
def test_parsing_holds_memory_linear_in_the_text(mod, goal):
    """Peak memory at 2n over peak at n: 2.0 when the rests are views; on the
    copying engine 2.8 (DCG) and 3.4 (head) at these sizes, rising toward 4
    as n grows.  tracemalloc counts allocations, so this does not depend on
    machine load."""
    def peak(n):
        tracemalloc.start()
        try:
            assert _one(mod, goal, chars("a" * n)) == n
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
    peak(500)                                  # warm caches outside the measurement
    small, large = peak(8000), peak(16000)
    assert large / small < 2.4, (small, large)


# ── views leaving the parse ─────────────────────────────────────────────────

def test_an_asserted_view_is_stored_as_its_text(mod):
    """The clause compiler embeds a literal: a view is embedded as its text
    (an asserted clause must not keep the whole parse input alive either)."""
    got = _one(mod, "keep", chars("aaa" + TEXT))
    assert got == chars(TEXT) and type(got[1]) is str


def test_a_view_answer_can_be_passed_back_into_a_query(mod):
    rest = _one(mod, "rest", chars("aaa" + TEXT))
    assert type(rest[1]) is _Text
    n = Var()
    assert next(solve(("length", rest, n), mod), None) is not None
    assert deref(n) == len(TEXT)


def test_a_tampered_view_is_an_error_not_a_crash():
    import subprocess, sys, textwrap
    src = textwrap.dedent("""
        from clausal.logic.cells import _Text, text_slice
        from clausal.logic.tabling import _normalize_for_key
        v = text_slice("x" * 200, 0, 150)
        _Text.flat = property(lambda self: self.base[self.lo:self.hi])   # does not cache
        try:
            _normalize_for_key(("$chars", v))
        except TypeError as e:
            print("TypeError", e)
    """)
    r = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True,
                       timeout=60, env={**__import__("os").environ, "PYTHONMALLOC": "debug"})
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.startswith("TypeError"), r.stdout


# ── the answer boundary: views stay inside a parse ──────────────────────────

def test_value_hands_out_the_text_not_a_view(mod):
    r = Var()
    assert next(solve(("head_rest", chars("aaa" + TEXT), r), mod), None) is not None
    assert type(deref(r)[1]) is _Text            # inside the engine: a view
    assert r.value == chars(TEXT) and type(r.value[1]) is str


@pytest.mark.parametrize("walker", ["c", "py"])
def test_a_walked_answer_holds_no_view(mod, walker):
    import json
    from clausal.logic import solve as S
    walk = {"c": S._deref_walk, "py": S._deref_walk_py}[walker]
    w = Var()
    assert next(solve(("wrap", chars("aaa" + TEXT), w), mod), None) is not None
    out = walk(w.value)
    assert out[1] == chars(TEXT) and type(out[1][1]) is str
    assert type(out[2][1][1]) is str              # nested in f(R) too
    json.dumps(out)                               # a walked answer is plain Python data


def test_a_query_cache_key_holds_the_text_not_a_view():
    from clausal.logic.solve import _structural_key

    def has_view(x):
        return type(x) is _Text or (type(x) is tuple and any(has_view(e) for e in x))
    assert not has_view(_structural_key(("f", (chars("x")[0], _view())), {}))
