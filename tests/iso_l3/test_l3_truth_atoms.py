"""D35 closed: ``true``/``false``/``undefined`` are ATOMS to the engine, on
BOTH front ends, while their objects stay Python ``True``/``False`` and the
Kleene ``Undefined`` (the ruling: the objects, for interop).

One program, written twice -- ISO for the native ``.pl`` reader, the seam's
spelling for ``.seam`` -- and one answer table.  The ``scryer`` column was
measured with::

    /workspace/scryer-prolog-clpq/target/release/scryer-prolog probe.pl \\
        -g run_all -g halt

on the ISO text (``:- use_module(library(lists)).`` prepended; ``run/1`` =
``findall`` over ``call(N, X)`` with ``catch``), 2026-09-30.  Where the two
front ends legitimately differ the row says so: the seam's ``==``/``<`` are
CLP(FD) posts (``#=``/``#<``): a bool LEAF inside an expression, or beside
a var, is clpz's ``domain_error(clpz_expression, true)`` -- also Scryer's
answer for ``X #= true`` -- while two GROUND operands compare as the atoms
they are (``X == True`` holds, ``1 < true`` is ``type_error(orderable,
true)`` exactly as ``1 < a``); ``is/2`` and ``=:=`` give ISO's
``type_error(evaluable, true/0)``.
"""
from __future__ import annotations

import contextlib
import io
import textwrap

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.terms import Undefined

ISO = """\
    u1(ok) :- true = 1.
    u2(ok) :- f(true) = f(1).
    u3(ok) :- [true] = [1].
    u4(ok) :- true == 1.
    u5(ok) :- false = 0.
    u6(ok) :- true \\= 1.
    u7(ok) :- undefined = undefined.
    u8(ok) :- true = true, false = false.
    t1(ok) :- atom(true).
    t2(ok) :- atomic(true).
    t4(ok) :- number(true).
    t5(ok) :- integer(true).
    t6(ok) :- atom(undefined).
    t7(ok) :- atom(false).
    a1(N) :- atom_length(false, N).
    a2(C) :- atom_codes(true, C).
    a3(X) :- atom_chars(X, [t, r, u, e]).
    a4(S) :- sub_atom(true, 0, 1, _, S).
    a5(X) :- atom_concat(true, x, X).
    a6(ok) :- atom_chars(X, [t, r, u, e]), X == true.
    f1(F) :- functor(F, true, 1), F = true(x).
    f2(G) :- G =.. [true, x].
    f3([N, A]) :- functor(true, N, A).
    f4(L) :- true =.. L.
    f5(ok) :- functor(true(x), N, 1), N == true.
    c1(O) :- compare(O, true, a).
    c2(O) :- compare(O, true, 1).
    c4(ok) :- true @< 1.
    c5(ok) :- 1 @< true.
    c6(L) :- sort([true, false, undefined, a, z], L).
    r3(ok) :- T = true, T =:= 1.
    p(true). p(1). p(false). p(0). p(a).
    ix1(N) :- findall(X, p(X), L), length(L, N).
    ix2(ok) :- p(true).
    ix3(ok) :- p(1).
    ix4(ok) :- p(0).
    ix5(ok) :- p(false).
    m1(ok) :- member(true, [1]).
    m2(ok) :- memberchk(1, [true]).
    s1(L) :- sort([1, true, 0, false], L).
    s2(L) :- list_to_set([1, true, 0, false], L).
    w1(ok) :- write(true), nl, writeq(false), nl, write(undefined), nl,
              writeq(g(true, [false])), nl.
    """

SEAM = """\
    -private([u1, u2, u3, u4, u5, u6, u7, u8, t1, t2, t3, t4, t5, t6, t7,
              a1, a2, a3, a4, a5, a6, f1, f2, f3, f4, f5, c1, c2, c4, c5, c6,
              r1, r2, r3, p, ix1, ix2, ix3, ix4, ix5, m1, m2, s1, s2, w1,
              ok, a, x, z, b, e, r, t, u, f(_), g(_, _)])
    u1(ok) <- (true is 1)
    u2(ok) <- (f(true) is f(1))
    u3(ok) <- ([true] is [1])
    u4(ok) <- ('=='(true, 1))
    u5(ok) <- (false is 0)
    u6(ok) <- (true is not 1)
    u7(ok) <- (undefined is undefined)
    u8(ok) <- (true is true, false is false)
    t1(ok) <- (atom(true))
    t2(ok) <- (atomic(true))
    t3(ok) <- (callable_(true))
    t4(ok) <- (number(true))
    t5(ok) <- (integer(true))
    t6(ok) <- (atom(undefined))
    t7(ok) <- (atom(false))
    a1(N) <- (atom_length(false, N))
    a2(C) <- (atom_codes(true, C))
    a3(X) <- (atom_chars(X, [t, r, u, e]))
    a4(S) <- (sub_atom(true, 0, 1, _, S))
    a5(X) <- (atom_concat(true, x, X))
    a6(ok) <- (atom_chars(X, [t, r, u, e]), '=='(X, true))
    f1(F) <- (functor(F, true, 1), '=..'(F, [true, x]))
    f2(G) <- ('=..'(G, [true, x]))
    f3([N, A]) <- (functor(true, N, A))
    f4(L) <- ('=..'(true, L))
    f5(ok) <- ('=..'(G, [true, x]), functor(G, N, 1), '=='(N, true))
    c1(O) <- (compare(O, true, a))
    c2(O) <- (compare(O, true, 1))
    c4(ok) <- ('@<'(true, 1))
    c5(ok) <- ('@<'(1, true))
    c6(L) <- (sort([true, false, undefined, a, z], L))
    r1(X) <- (T is true, X == T + 1)
    r2(ok) <- (T is true, 1 < T)
    r3(ok) <- (T is true, '=:='(T, 1))
    p(true),
    p(1),
    p(false),
    p(0),
    p(a),
    ix1(N) <- (findall(X, p(X), L), length(L, N))
    ix2(ok) <- (p(true))
    ix3(ok) <- (p(1))
    ix4(ok) <- (p(0))
    ix5(ok) <- (p(false))
    m1(ok) <- (member(true, [1]))
    m2(ok) <- (memberchk(1, [true]))
    s1(L) <- (sort([1, true, 0, false], L))
    s2(L) <- (list_to_set([1, true, 0, false], L))
    w1(ok) <- (write(true), nl, writeq(false), nl, write(undefined), nl,
               writeq(g(true, [false])), nl)
    """

TRUE_0 = ("/", True, 0)


def _err(kind, *args):
    """An error expectation: the ISO error term's formal, compared on the
    formal only (the context differs per front end)."""
    return ("RAISES", (kind, *args))


#: name -> (expected answers or _err(...), Scryer's measured answer).  The
#: Scryer column is DATA, kept next to the expectation so a drift is visible.
TABLE = {
    "u1": ([], "[]"),
    "u2": ([], "[]"),
    "u3": ([], "[]"),
    "u4": ([], "[]"),
    "u5": ([], "[]"),
    "u6": (["ok"], "[ok]"),
    "u7": (["ok"], "[ok]"),
    "u8": (["ok"], "[ok]"),
    "t1": (["ok"], "[ok]"),
    "t2": (["ok"], "[ok]"),
    "t4": ([], "[]"),
    "t5": ([], "[]"),
    "t6": (["ok"], "[ok]"),
    "t7": (["ok"], "[ok]"),
    "a1": ([5], "[5]"),
    "a2": ([[116, 114, 117, 101]], "[[116,114,117,101]]"),
    "a3": ([True], "[true]"),
    "a4": (["t"], "[t]"),
    "a5": (["truex"], "[truex]"),
    "a6": (["ok"], "[ok]"),
    "f1": ([("true", "x")], "[true(x)]"),
    "f2": ([("true", "x")], "[true(x)]"),
    "f3": ([[True, 0]], "[[true,0]]"),
    "f4": ([[True]], "[[true]]"),
    "f5": (["ok"], "[ok]"),
    "c1": ([">"], "[>]"),
    "c2": ([">"], "[>]"),
    "c4": ([], "[]"),
    "c5": (["ok"], "[ok]"),
    "c6": ([["a", False, True, Undefined, "z"]], "[[a,false,true,undefined,z]]"),
    "r3": (_err("type_error", "evaluable", TRUE_0),
           "raises(error(type_error(evaluable,true/0),(is)/2))"),
    "ix1": ([5], "[5]"),
    "ix2": (["ok"], "[ok]"),
    "ix3": (["ok"], "[ok]"),
    "ix4": (["ok"], "[ok]"),
    "ix5": (["ok"], "[ok]"),
    "m1": ([], "[]"),
    "m2": ([], "[]"),
    "s1": ([[0, 1, False, True]], "[[0,1,false,true]]"),
    "s2": ([[1, True, 0, False]], "(no list_to_set/2 in Scryer; ==/2 dedup)"),
}

#: Rows that exist on one front end only, or answer differently by design.
SEAM_ONLY = {
    "t3": (["ok"], "[ok]  (callable/1)"),
    # the seam's ``==`` and ``<`` are CLP(FD) posts: Scryer's ``X #= true``
    # is ``domain_error(clpz_expression, true)``
    "r1": (_err("domain_error", "clpz_expression", True),
           "X #= true: raises(error(domain_error(clpz_expression,true),_))"),
    # the seam's ``<`` on two GROUND operands is Python's ``<`` over the
    # atom's spelling, as for any atom: ``1 < true`` is the same
    # type_error(orderable, true) as ``1 < a`` (measured on the base engine)
    "r2": (_err("type_error", "orderable", "true"),
           "1 #< true: raises(error(domain_error(clpz_expression,true),_)) -- clpz posts; the seam's ground < does not"),
}

WRITE_OUT = "true\nfalse\nundefined\ng(true,[false])\n"


def _run(mod, name):
    v = Var()
    out = []
    try:
        for _ in call(name, v, module=mod):
            out.append(walk(deref(v)))
    except LogicException as e:
        term = e.term
        assert type(term) is tuple and term[0] == "error", term
        return ("RAISES", term[1])
    return out


@pytest.fixture
def iso_mod(native):
    return native.load("l3_truth_iso", textwrap.dedent(ISO))


@pytest.fixture
def seam_mod(native):
    return native.load("l3_truth_seam", textwrap.dedent(SEAM), suffix=".seam",
                       frontend=None)


@pytest.mark.parametrize("name", sorted(TABLE))
def test_native_pl_reads_the_truth_values_as_scryers_atoms(iso_mod, name):
    expected, _scryer = TABLE[name]
    assert _run(iso_mod, name) == expected


@pytest.mark.parametrize("name", sorted(TABLE) + sorted(SEAM_ONLY))
def test_seam_reads_the_truth_values_as_scryers_atoms(seam_mod, name):
    expected, _scryer = (TABLE.get(name) or SEAM_ONLY[name])
    assert _run(seam_mod, name) == expected


@pytest.mark.parametrize("which", ["iso", "seam"])
def test_the_writers_print_the_spellings(native, which, capsys):
    text = ISO if which == "iso" else SEAM
    kw = {} if which == "iso" else {"suffix": ".seam", "frontend": None}
    mod = native.load(f"l3_truth_w_{which}", textwrap.dedent(text), **kw)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert _run(mod, "w1") == ["ok"]
    assert buf.getvalue() + capsys.readouterr().out == WRITE_OUT


def test_the_objects_stay_python_true_false_undefined(iso_mod):
    """The ruling's other half: what a Python caller reads back IS the
    object, never a str -- including an atom the program BUILT."""
    assert _run(iso_mod, "a3") == [True]
    assert _run(iso_mod, "a3")[0] is True
    assert _run(iso_mod, "f4")[0][0] is True
    assert _run(iso_mod, "c6")[0][3] is Undefined


def test_native_callable_1_of_true(native):
    """callable/1 is an engine builtin under its ISO name, so the native
    front end runs it, and the atom true is callable."""
    mod = native.load("l3_truth_callable", "t3(ok) :- callable(true).\n")
    assert _run(mod, "t3") == ["ok"]
