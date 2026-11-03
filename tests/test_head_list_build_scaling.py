"""A list a clause head builds after its body: the work it takes, and the
answers it gives.

``mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).`` builds ``[N|T]`` at
the solution, once the body has bound ``T``
(``_head_list_unify_output``, clausal/logic/runtime/_list_unify.c, and its
Python twin in clausal/logic/runtime/list_unify.py).  With an unbound tail,
``T`` is a partial list, and the output used to read it through
``SegList.__walk__``, which walks every element of the rest at every level:
N^2/2 ``walk`` calls.  It reads it shallowly now (``_walk_raw(False)``);
the elements are read through their bindings by whoever reads the list.
todo/a-list-a-clause-head-builds-after-its-body-copies-the-tail-quadratic-2026-11-03.md.

The work is counted, not timed: the Python and C function calls the whole
build makes (``sys.setprofile``) at two lengths four times apart.
"""
from __future__ import annotations

import sys

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_PROGRAM = """\
mk(0, L, L).
mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).

mkx(0, L, L, []).
mkx(N, L, [f(X)|T], [X|Xs]) :- N > 0, N1 is N-1, mkx(N1, L, T, Xs).

build(Z, N) :- mk(N, Z, _).

% An element bound after its link was built, and read back.
late(L) :- mkx(3, Z, L, [a, b, c]), Z = [].
late_open(L, Z) :- mkx(3, Z, L, Xs), Xs = [a, b, c].

% The f60e3211 shape through a head-built list: findall/3 copies the
% elements as they are bound, not as live variables.
snap(R) :- findall(L, (mkx(2, Z, L, [X, Y]), X = 1, Y = g(W), W = 2, Z = []), R).
snap_open(R) :- findall(L-Z, (mkx(2, Z, L, [X, Y]), X = 1, Y = g(W), W = 2), R).

open_eq(yes) :- mk(5, Z, L), mk(5, Z, L2), L == L2.
open_bind(L) :- mk(3, Z, L), Z = [x, y].
open_chars(L) :- mkc(Z, L), Z = [].
mkc(Z, [a, b|T]) :- mkc2(Z, T).
mkc2(Z, [c|Z]).
"""

SMALL, LARGE = 500, 2000          # x4
LINEAR_BOUND = 6                  # linear grows ~x4, the per-element walk ~x16


@pytest.fixture(scope="module")
def m(tmp_path_factory):
    path = tmp_path_factory.mktemp("head_list") / "mk.clausal"
    path.write_text(_PROGRAM)
    return load_clausal_module(path)


def _calls(fn):
    count = 0

    def profile(frame, event, arg):
        nonlocal count
        if event in ("call", "c_call"):
            count += 1

    sys.setprofile(profile)
    try:
        fn()
    finally:
        sys.setprofile(None)
    return count


def _build(m, tail, n):
    z = Var() if tail == "open" else {"nil": [], "improper": "foo"}[tail]
    assert sum(1 for _ in solve(("build", z, n), m)) == 1


@pytest.mark.parametrize("tail", ["nil", "open", "improper"])
def test_building_takes_a_linear_number_of_calls(m, tail):
    _build(m, tail, 50)                       # compile and warm the caches
    small = _calls(lambda: _build(m, tail, SMALL))
    large = _calls(lambda: _build(m, tail, LARGE))
    assert large < LINEAR_BOUND * small, (
        f"building a {tail}-tailed list: {small} calls at {SMALL}, "
        f"{large} at {LARGE} (x{large / small:.1f}; linear is ~x4)")


def _one(m, goal):
    for _ in solve(goal, m):
        return True
    return False


def _show(t):
    from clausal.terms import term_writeq
    return term_writeq(deref(t))


def test_an_element_bound_after_the_build_is_read_through_its_binding(m):
    L = Var()
    assert _one(m, ("late", L))
    assert _show(L) == "[f(a),f(b),f(c)]"


def test_an_element_bound_after_the_build_of_an_open_list(m):
    L, Z = Var(), Var()
    assert _one(m, ("late_open", L, Z))
    assert _show(L).startswith("[f(a),f(b),f(c)|")


def test_findall_copies_the_bound_elements_of_a_head_built_list(m):
    R = Var()
    assert _one(m, ("snap", R))
    assert _show(R) == "[[f(1),f(g(2))]]"


def test_findall_copies_the_bound_elements_of_an_open_head_built_list(m):
    R = Var()
    assert _one(m, ("snap_open", R))
    shown = _show(R)
    assert shown.startswith("[[f(1),f(g(2))|_") and "-_" in shown, shown


def test_two_open_head_built_lists_are_identical(m):
    R = Var()
    assert _one(m, ("open_eq", R))
    assert _show(R) == "yes"


def test_binding_the_tail_of_an_open_head_built_list(m):
    L = Var()
    assert _one(m, ("open_bind", L))
    assert _show(L) == "[3,2,1,x,y]"


def test_a_head_built_list_of_chars(m):
    L = Var()
    assert _one(m, ("open_chars", L))
    assert _show(L) == '"abc"'      # promoted to text, as before


# ── The C output and its Python twin agree on every star a SegList can be ──

def _stars():
    """``(name, star)`` pairs: the partial-list shapes a star can hold."""
    from clausal.logic.variables import Trail, unify
    from clausal.terms import ConcreteSeg, SegList, SegListView, VarSeg
    tr = Trail()
    x, z, t = Var(), Var(), Var()
    unify(x, ("f", 7), tr)
    open_ = SegList([ConcreteSeg([1, x]), VarSeg(z)])           # [1, X|Z], X bound
    t2 = Var()
    unify(t2, [x, 3], tr)
    closed = SegList([ConcreteSeg([1]), VarSeg(t2)])             # [1, X, 3]
    t3 = Var()
    unify(t3, "foo", tr)
    improper = SegList([ConcreteSeg([1, x]), VarSeg(t3)])        # [1, X|foo]
    from clausal.terms import char_atom
    t4 = Var()
    unify(t4, [char_atom("b")], tr)
    chars = SegList([ConcreteSeg([char_atom("a")]), VarSeg(t4)])  # [a, b]
    view = SegListView(list(range(100)), 10, 90)
    chain_tail = Var()
    link2 = SegList([ConcreteSeg([2]), VarSeg(chain_tail)])
    t5 = Var()
    unify(t5, link2, tr)
    chain = SegList([ConcreteSeg([1]), VarSeg(t5)])               # [1|[2|_]]
    return [("open", open_), ("closed", closed), ("improper", improper),
            ("chars", chars), ("view", view), ("chain", chain)], tr


@pytest.mark.parametrize("before", [[], ["h"]])
def test_the_c_output_and_its_python_twin_build_the_same_term(before):
    from clausal.logic.runtime import _list_unify as c
    from clausal.logic.runtime.list_unify import _head_list_unify_output_py
    from clausal.logic.variables import Trail
    from clausal.terms import term_writeq
    stars, _keep = _stars()
    for name, star in stars:
        shown = []
        for fn in (c._head_list_unify_output, _head_list_unify_output_py):
            sv = Var()
            tr = Trail()
            from clausal.logic.variables import unify
            assert unify(sv, star, tr)
            target = Var()
            ok = fn(target, list(before), sv, [], tr)
            shown.append((bool(ok), term_writeq(deref(target))))
        assert shown[0] == shown[1], (name, shown)
