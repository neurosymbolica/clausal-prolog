"""A long list a clause head builds after its body is a link, not a copy.

``mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).`` builds ``[N|T]`` at
the solution, once the body has bound ``T``.  When ``T`` is a long list
(``LIST_VIEW_MIN`` elements or more), a list view, or a link itself, the
head output builds a ``terms.HeadLink`` -- the elements before the star
and the star's variable -- instead of copying the rest.  The first read
flattens the chain once; ``deref`` then rebinds the variable to the plain
list the copy would have been.  A partial (open) tail is still copied.
todo/a-list-a-clause-head-builds-after-its-body-copies-the-tail-quadratic-2026-11-03.md.

Pinned here: the answers, the representation readers see, variable
identity, promotion to text, backtracking over a rebinding, and the C and
Python twins building the same term.  The build's cost is pinned by
``test_building_a_long_list_copies_no_rest``.
"""
from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref, deref_raw, unify, walk
from clausal.terms import (
    LIST_VIEW_MIN, ConcreteSeg, HeadLink, SegList, SegListView, VarSeg,
    char_atom, is_chars, term_writeq)
from clausal.testing import load_clausal_module

N = 3 * LIST_VIEW_MIN
LETTERS = "b" * N

_PROGRAM = f"""\
mk(0, L, L).
mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).
mkc(0, L, L).
mkc(N, L, [a|T]) :- N > 0, N1 is N-1, mkc(N1, L, T).
mkv(0, L, L).
mkv(N, L, [_|T]) :- N > 0, N1 is N-1, mkv(N1, L, T).
bind_all([]).
bind_all([b|T]) :- bind_all(T).

choice(L) :- ( mk({N}, [], L) ; mk({N - 10}, [x], L) ).
lengths(R) :- findall(Len-Last, (choice(L), length(L, Len), last(L, Last)), R).
chars_text(L) :- mkc({N}, [], L).
late_chars(L) :- mkv({N}, [], L), bind_all(L).
late_chars_copy(C) :- late_chars(L), copy_term(L, C).
late_chars_findall(R) :- late_chars(L), findall(L, true, R).
late_chars_rest(T) :- late_chars(L), L = [_|T].
late_chars_eq(R) :- late_chars(L), ( L == "{LETTERS}", R = eq ; L \\== "{LETTERS}", R = ne ).
mixed(R) :- mk({N}, [], T), mkc(3, T, M), M = [A, B, C, D|_], R = [A, B, C, D].
mixed_chars(R) :- mk({N}, [], T), mkc(30, T, R).
shared(R) :- mkv({N}, [], L), nth1(50, L, X), X = zz, nth1(50, L, R).
open_end(R) :- mk({N}, Z, L), Z = [end], last(L, R).
open_partial(L, Z) :- mk({N}, Z, L).
open_eq(R) :- mk({N}, Z, L), mk({N}, Z, L2), ( L == L2, R = eq ; L \\== L2, R = ne ).
compared(R) :- mk({N}, [], L), mk({N - 1}, [], L2), compare(R, L, L2).
sorted(S) :- mk({N}, [], L), msort(L, [S|_]).
rest_length(R) :- mk({N}, [], L), L = [_|T], length(T, R).
unified(R) :- mk({N}, [], L), mk({N}, [], L2), ( L = L2, R = yes ; \\+ L = L2, R = no ).
built(L) :- mk({N}, [], L).
"""


@pytest.fixture(scope="module")
def m(tmp_path_factory):
    path = tmp_path_factory.mktemp("head_link") / "mk.clausal"
    path.write_text(_PROGRAM)
    return load_clausal_module(path)


def _answer(m, name, *extra):
    out = Var()
    for _ in solve((name, out, *extra), m):
        return walk(out)
    raise AssertionError(f"{name} failed")


def test_answers_on_backtracking(m):
    assert _answer(m, "lengths") == [("-", N, 1), ("-", N - 9, "x")]


def test_a_long_list_of_chars_is_text(m):
    assert is_chars(_answer(m, "chars_text"))


@pytest.mark.parametrize("goal", ["late_chars", "late_chars_copy", "late_chars_rest"])
def test_chars_bound_after_the_build_stay_a_list_as_before(m, goal):
    # The copy held the variables, not chars, so it was never promoted.
    out = _answer(m, goal)
    assert type(out) is list and set(out) == {"b"}, out


def test_chars_bound_after_the_build_equal_their_text(m):
    assert _answer(m, "late_chars_eq") == "eq"
    found = _answer(m, "late_chars_findall")
    assert len(found) == 1 and set(found[0]) == {"b"}


def test_a_char_prefix_over_a_long_list_of_numbers(m):
    assert _answer(m, "mixed") == ["a", "a", "a", N]
    out = _answer(m, "mixed_chars")
    assert out[:30] == ["a"] * 30 and out[30:] == list(range(N, 0, -1))


def test_elements_keep_their_identity(m):
    assert _answer(m, "shared") == "zz"


def test_open_tails_are_still_copied(m):
    assert _answer(m, "open_end") == "end"
    assert _answer(m, "open_eq") == "eq"
    L, Z = Var(), Var()
    for _ in solve(("open_partial", L, Z), m):
        shown = term_writeq(deref(L))
        assert shown.startswith(f"[{N},{N - 1},") and "|_" in shown, shown
        assert type(deref(L)) is SegList
        break


def test_readers(m):
    assert _answer(m, "compared") == ">"
    assert _answer(m, "sorted") == 1
    assert _answer(m, "rest_length") == N - 1
    assert _answer(m, "unified") == "yes"


def test_deref_hands_out_the_plain_list(m):
    L = Var()
    for _ in solve(("built", L), m):
        assert type(deref_raw(L)) is HeadLink
        assert L.value == list(range(N, 0, -1))
        d = deref(L)
        assert type(d) is list and d == list(range(N, 0, -1))
        assert deref_raw(L) is d                # rebound: later reads are O(1)
        break


def _chain(tr, n):
    """A closed chain of n links over a long list, built by hand as the
    head output builds it."""
    base = list(range(LIST_VIEW_MIN))
    star = Var()
    assert unify(star, base, tr)
    for i in range(n):
        link = HeadLink([("e", i)], star)
        star = Var()
        assert unify(star, link, tr)
    return star


def test_flattening_reads_the_chain_once_and_becomes_a_view():
    tr = Trail()
    top = _chain(tr, 5)
    link = deref_raw(top)
    assert type(link) is HeadLink
    assert len(link) == 5 + LIST_VIEW_MIN
    assert type(link) is SegListView              # flattened in place
    assert link.elements()[:5] == [("e", i) for i in range(4, -1, -1)]


def test_undo_of_a_rebound_variable_unbinds_it():
    tr = Trail()
    mark = tr.mark()
    holder = Var()
    top = _chain(tr, 3)
    assert unify(holder, top, tr)
    assert type(deref(holder)) is list            # rebound to the plain list
    tr.undo(mark)
    assert deref(holder) is holder and deref(top) is top


@pytest.mark.parametrize("before", [[], ["h"], [char_atom("a")]])
def test_the_c_output_and_its_python_twin_build_the_same_link(before):
    from clausal.logic.runtime import _list_unify as c
    from clausal.logic.runtime.list_unify import _head_list_unify_output_py
    tr = Trail()
    z = Var()
    long_list = list(range(LIST_VIEW_MIN))
    long_chars = [char_atom("c")] * LIST_VIEW_MIN
    stars = {
        "long list": long_list,
        "long chars": long_chars,
        "view": SegListView(list(range(200)), 10, 190),
        "link": HeadLink([1], _bound(long_list, tr)),
        "open": SegList([ConcreteSeg([1, 2]), VarSeg(z)]),
    }
    for name, star in stars.items():
        built = []
        for fn in (c._head_list_unify_output, _head_list_unify_output_py):
            sv = _bound(star, tr)
            target = Var()
            assert fn(target, list(before), sv, [], tr)
            built.append((type(deref_raw(target)).__name__,
                          term_writeq(deref(target))))
        assert built[0] == built[1], (name, built)


def _bound(value, tr):
    v = Var()
    assert unify(v, value, tr)
    return v


def test_building_a_long_list_copies_no_rest(m):
    """Every level above LIST_VIEW_MIN is a link: building twice as many
    elements makes about twice as many links, never a copy of the rest."""
    for n in (1000, 2000):
        L = Var()
        for _ in solve(("mk", n, [], L), m):
            raw = deref_raw(L)
            links = 0
            while type(raw) is HeadLink:
                links += 1
                raw = deref_raw(raw._mat)
            assert links == n - LIST_VIEW_MIN, (n, links)
            assert type(raw) is list and len(raw) == LIST_VIEW_MIN
            break


@pytest.mark.parametrize("shape", ["closed", "view"])
def test_the_c_flatten_and_its_python_twin_agree(shape):
    from clausal.logic.runtime._list_unify import _head_link_flatten
    shown = []
    for flatten in (_head_link_flatten, HeadLink._flatten_py):
        tr = Trail()
        if shape == "closed":
            star = _bound(list(range(LIST_VIEW_MIN)), tr)
            link = HeadLink(["a"], _bound(HeadLink([1, 2], star), tr))
        elif shape == "view":
            star = _bound(SegListView(list(range(200)), 5, 150), tr)
            link = HeadLink([("f", 1)], _bound(HeadLink([0], star), tr))
        flatten(link)
        inner_type = type(link).__name__
        flat = link._base
        shown.append((inner_type, link._lo, type(flat).__name__, term_writeq(flat)))
    assert shown[0] == shown[1], shown
