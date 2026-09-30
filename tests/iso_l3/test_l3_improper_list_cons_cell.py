"""An improper list is the ISO cons cell ``'.'(H, T)`` (D50, ruled 2026-09-30).

The native ``.pl`` front end lowered ``[b|foo]`` as the seam's ``[b, *foo]``,
and the seam splices a str -- an atom -- as its chars: ``[b|foo]`` became
``[b,f,o,o]``, a silently different term, and ``msort([b|foo], L)`` answered
``L = [b,f,o,o]``.  A tail that is not a list and not a variable now lowers
as the compound ``('.', H, T)``: the list builtins reject it with ISO's
``type_error(list, [b|foo])``, and ``[H|T]`` takes it apart.  Every expected
answer below is Scryer's."""
from __future__ import annotations

import pytest

from clausal.terms import term_write

SRC = """\
mk(X) :- X = [b|foo].
mk_num(X) :- X = [b|1].
mk_cmp(X) :- X = [b|f(x)].
mk_long(X) :- X = [a,b|foo].
mk_str(X) :- X = [b|"cd"].
ht(H-T) :- X = [b|foo], X = [H|T].
ht_rev(H-T) :- X = [b|foo], [H|T] = X.
ht2(T) :- X = [a,b|foo], X = [_,_|T].
ht1(T) :- X = [a,b|foo], X = [_|T].
too_long :- X = [b|foo], X = [_,_|_].
proper :- X = [b|foo], X = [_].
chars :- [b|foo] = [b,f,o,o].
dot(X) :- X = '.'(b, foo).
ms(E) :- catch(msort([b|foo], _), error(E, _), true).
so(E) :- catch(sort([b|foo], _), error(E, _), true).
ks(E) :- catch(keysort([b-1|foo], _), error(E, _), true).
il :- is_list([b|foo]).
len :- length([b|foo], _).
app :- append([b|foo], [c], _).
mem(X) :- member(X, [a,b|foo]).
memchk :- memberchk(b, [a,b|foo]).
ac(E) :- catch(atom_chars(_, [b|foo]), error(E, _), true).
fun(N/A) :- functor([b|foo], N, A).
univ(L) :- [b|foo] =.. L.
wq :- writeq([b|foo]), nl, writeq([a,b|c]), nl, writeq([f(1)|g(1)]), nl,
      write_canonical([b|foo]), nl.
"""


@pytest.fixture
def mod(native):
    return native.load("d50_improper", SRC)


def test_an_improper_list_is_the_cons_cell(mod, ans):
    assert ans(mod, "mk") == [(".", "b", "foo")]
    assert ans(mod, "mk_num") == [(".", "b", 1)]
    assert ans(mod, "mk_cmp") == [(".", "b", ("f", "x"))]
    assert ans(mod, "mk_long") == [(".", "a", (".", "b", "foo"))]
    assert ans(mod, "dot") == [(".", "b", "foo")]
    assert ans(mod, "chars", 0) == []         # was: succeeded
    # A double-quoted tail IS a list: [b|"cd"] = [b,c,d], as before.
    assert ans(mod, "mk_str") == [("$chars", "bcd")]   # the char list b,c,d


def test_a_list_pattern_takes_the_cell_apart(mod, ans):
    assert ans(mod, "ht") == [("-", "b", "foo")]
    assert ans(mod, "ht_rev") == [("-", "b", "foo")]
    assert ans(mod, "ht2") == ["foo"]
    assert ans(mod, "ht1") == [(".", "b", "foo")]
    assert ans(mod, "too_long", 0) == []
    assert ans(mod, "proper", 0) == []


def test_list_builtins_reject_it_as_iso_requires(mod, ans):
    cell = (".", "b", "foo")
    assert ans(mod, "ms") == [("type_error", "list", cell)]
    assert ans(mod, "so") == [("type_error", "list", cell)]
    assert ans(mod, "ks") == [("type_error", "list",
                               (".", ("-", "b", 1), "foo"))]
    assert ans(mod, "il", 0) == []
    assert ans(mod, "len", 0) == []           # Scryer's length/2 fails
    assert ans(mod, "app", 0) == []
    assert ans(mod, "mem") == ["a", "b"]      # member(X, [X|_]) walks cells
    assert ans(mod, "memchk", 0) == [()]
    assert ans(mod, "ac") == [("type_error", "list", cell)]


def test_it_is_the_compound_dot_2(mod, ans):
    assert ans(mod, "fun") == [("/", ".", 2)]
    assert ans(mod, "univ") == [[".", "b", "foo"]]


def test_writeq_prints_list_notation(mod, ans, capsys):
    assert ans(mod, "wq", 0) == [()]
    assert capsys.readouterr().out.splitlines() == [
        "[b|foo]", "[a,b|c]", "[f(1)|g(1)]", "'.'(b,foo)"]


def test_the_writer_on_the_cell():
    assert term_write((".", "a", (".", "b", "c")), quoted=True) == "[a,b|c]"
    assert term_write((".", "a", (".", "b", [])), quoted=True) == "[a,b]"
    assert term_write((".", "a", ["b"]), quoted=True) == "[a,b]"
    assert term_write((".", "a", "c"), quoted=True,
                      ignore_ops=True) == "'.'(a,c)"


def test_an_interior_hole_fails_against_the_cell():
    """A seam pattern with a hole before its end (``[*A, b]``) is a proper
    list: it fails against a cons cell, rather than recursing."""
    from clausal.logic.variables import Trail, Var, unify
    from clausal.terms import ConcreteSeg, SegList, VarSeg
    cell = (".", "x", "foo")
    for segs in ([VarSeg(Var()), ConcreteSeg(["b"])],
                 [ConcreteSeg(["x"]), VarSeg(Var()), ConcreteSeg(["b"])],
                 [VarSeg(Var()), VarSeg(Var())]):
        assert not unify(SegList(segs), cell, Trail())
    t = Var()
    assert unify(SegList([ConcreteSeg(["x"]), VarSeg(t)]), cell, Trail())
