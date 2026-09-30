"""D47 review findings (2026-09-30): the places where Python's ``True == 1``
still leaked into the ENGINE after the truth values became the atoms
true/false/undefined.  Each row was measured against Scryer
(``/workspace/scryer-prolog-clpq/target/release/scryer-prolog``) on the same
ISO text; the Scryer answer is kept beside the expectation.

1. CLP(FD): a bool HAS ``.denominator == 1``, so the C fd hook re-admitted
   it as the integer 1/0; the ground-int arms of ``#\\=`` and
   all_different read it as an int.  clpz: ``type_error(integer, true)``.
2. The nested head-literal guard short-circuited on Python ``==``.
3. setof/3 deduplicated by Python ``==``.
4. subtract/intersection/union used Python ``in``; max_list/min_list
   Python ``max``/``min``.
5. assertz(true) escaped as a raw TypeError; retract(true) failed.
6. list_to_set/2 was a quadratic scan.
7. A str truth spelling crossed to Python unlike its object.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.terms import Undefined

ISO = """\
    :- use_module(library(lists)).
    :- use_module(library(clpz)).
    :- dynamic(d/1).
    c1(ok) :- X in 0..2, X #\\= Y, Y = true, X = 1.
    c2(ok) :- X in 0..2, X #= Y, Y = true, X = 1.
    c3(X) :- X in 0..2, X = false.
    c4(X) :- X in 0..2, X = undefined.
    c5(ok) :- X in 0..2, X + Y #= 2, Y = true, X = 1.
    c6(L) :- [X, Y] ins 0..2, all_different([X, Y]), Y = true,
             findall(X, label([X]), L).
    c7(L) :- X in 0..2, Y in 0..2, X #< Y, Y = true, findall(X, label([X]), L).
    c8(ok) :- all_different([true, X]), X = 1.
    c9(X) :- X in 0..2, X = 1.
    p(f(true)). p(f(1)). p(f(false)). p(f(0)). p(f(a)).
    h1(L) :- findall(x, p(f(1)), L).
    h2(L) :- findall(x, p(f(true)), L).
    h3(L) :- findall(x, p(f(0)), L).
    h4(L) :- findall(x, p(f(false)), L).
    h5(L) :- findall(X, p(f(X)), L).
    h6(L) :- findall(x, p(f(1.0)), L).
    h7(L) :- assertz(d(f(true))), assertz(d(f(1))), assertz(d(f(false))),
             assertz(d(f(0))), assertz(d(f(a))),
             findall(x, d(f(1)), L1), findall(x, d(f(false)), L2),
             L = [L1, L2].
    s1(L) :- setof(X, member(X, [true, 1, false, 0, true]), L).
    s2(L) :- setof(X-Y, member(X-Y, [a-true, a-1, b-false, b-0]), L).
    s3(L) :- setof(X, member(X, [f(true), f(1), f(1.0)]), L).
    s4(L) :- setof(X, member(X, [1, 1.0, 2]), L).
    l1(L) :- subtract([true, 1, 0, false], [1], L).
    l2(L) :- intersection([true, 1, 0, false], [1, false], L).
    l3(L) :- union([1, 0], [true, false, 1], L).
    l4(X) :- max_list([true, 1], X).
    l5(X) :- min_list([0, false], X).
    l6(X) :- max_list([3, 1, 4], X).
    l7(L) :- list_to_set([1, true, 0, false, 1, true, 1.0], L).
    a1(ok) :- assertz(true).
    a2(ok) :- asserta(false).
    a3(ok) :- retract(true).
    a4(ok) :- retract((false :- true)).
    a5(ok) :- retractall(true).
    a6(ok) :- assertz((true :- a)).
    a7(ok) :- assertz(undefined).
    """


def _err(kind, *args):
    return ("RAISES", (kind, *args))


def _pi(name):
    return ("/", name, 0)


#: name -> (expected, Scryer's answer as measured)
TABLE = {
    # 1. CLP(FD)
    "c1": (_err("type_error", "integer", True), "error(type_error(integer,true),_)"),
    "c2": (_err("type_error", "integer", True), "error(type_error(integer,true),_)"),
    "c3": (_err("type_error", "integer", False), "error(type_error(integer,false),_)"),
    "c4": (_err("type_error", "integer", Undefined),
           "(undefined is an ordinary atom there) error(type_error(integer,undefined),_)"),
    "c5": (_err("type_error", "integer", True), "error(type_error(integer,true),_)"),
    "c6": (_err("type_error", "integer", True), "error(type_error(integer,true),_)"),
    "c7": (_err("type_error", "integer", True), "error(type_error(integer,true),_)"),
    "c8": (_err("type_error", "integer", True), "error(type_error(integer,true),can_be/2)"),
    "c9": ([1], "[1]"),
    # 2. head literals, >= _INDEX_THRESHOLD clauses, static and dynamic
    "h1": ([["x"]], "[[x]]"),
    "h2": ([["x"]], "[[x]]"),
    "h3": ([["x"]], "[[x]]"),
    "h4": ([["x"]], "[[x]]"),
    "h5": ([[True, 1, False, 0, "a"]], "[[true,1,false,0,a]]"),
    # 1 = 1.0 unifies in the engine (parked, A01-D001 / todo
    # iso-unify-conflates-int-and-float): the guard answers what unify does
    "h6": ([["x"]], "[[]]  -- the parked int/float unify residual"),
    "h7": ([[["x"], ["x"]]], "[[[x],[x]]]"),
    # 3. setof/3
    "s1": ([[0, 1, False, True]], "[[0,1,false,true]]"),
    "s2": ([[("-", "a", 1), ("-", "a", True), ("-", "b", 0), ("-", "b", False)]],
           "[[a-1,a-true,b-0,b-false]]"),
    # f(1) and f(1.0) stay merged: A01-D001 (c) keeps 1 == 1.0 in setof
    "s3": ([[("f", 1.0), ("f", True)]], "[[f(1.0),f(1),f(true)]]  -- A01-D001 residual"),
    "s4": ([[1.0, 2]], "[[1.0,1,2]]  -- A01-D001 residual"),
    # 4. lists (no subtract/3 etc. in Scryer's library(lists): ==/2 membership)
    "l1": ([[True, 0, False]], "(n/a)"),
    "l2": ([[1, False]], "(n/a)"),
    "l3": ([[1, 0, True, False]], "(n/a)"),
    "l4": (_err("type_error", "evaluable", _pi(True)), "list_max: type_error(evaluable,true/0)"),
    "l5": (_err("type_error", "evaluable", _pi(False)), "list_min: type_error(evaluable,false/0)"),
    "l6": ([4], "[4]"),
    "l7": ([[1, True, 0, False, 1.0]], "[[1,true,0,false,1.0]]"),
    # 5. the database
    "a1": (_err("permission_error", "modify", "static_procedure", _pi(True)),
           "error(permission_error(modify,static_procedure,true/0),assertz/1)"),
    "a2": (_err("permission_error", "modify", "static_procedure", _pi(False)),
           "error(permission_error(modify,static_procedure,false/0),asserta/1)"),
    "a3": (_err("permission_error", "modify", "static_procedure", _pi(True)),
           "error(permission_error(modify,static_procedure,true/0),retract/1)"),
    "a4": (_err("permission_error", "modify", "static_procedure", _pi(False)),
           "error(permission_error(modify,static_procedure,false/0),retract/1)"),
    "a5": (_err("permission_error", "modify", "static_procedure", _pi(True)),
           "error(permission_error(modify,static_procedure,true/0),retract/1)"),
    "a6": (_err("permission_error", "modify", "static_procedure", _pi(True)),
           "error(permission_error(modify,static_procedure,true/0),assertz/1)"),
    # undefined/0 is reserved in Clausal (slice 4); in Scryer it is an
    # ordinary atom and the assert succeeds
    "a7": (_err("permission_error", "modify", "static_procedure", _pi(Undefined)),
           "[ok]  -- undefined is not reserved there"),
}


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
    return native.load("l3_truth_review_iso", textwrap.dedent(ISO))


@pytest.mark.parametrize("name", sorted(TABLE))
def test_review_rows(iso_mod, name):
    expected, _scryer = TABLE[name]
    got = _run(iso_mod, name)
    assert got == expected
    # the type is part of the answer: True is not 1
    if isinstance(expected, list):
        assert [type(x) for x in got] == [type(x) for x in expected]


SEAM = """\
    -private([p, t, q1, q2, q3, q4, f(_), x, a])
    p(f(true)),
    p(f(1)),
    p(f(false)),
    p(f(0)),
    p(f(a)),
    t(true),
    t(1),
    t(false),
    t(0),
    t(a),
    q1(L) <- (findall(x, p(f(1)), L))
    q2(L) <- (findall(x, p(f(true)), L))
    q3(L) <- (findall(x, t(1), L))
    q4(L) <- (findall(x, t(true), L))
    """


@pytest.mark.parametrize("name", ["q1", "q2", "q3", "q4"])
def test_seam_head_literals_keep_true_and_1_apart(native, name):
    mod = native.load("l3_truth_review_seam", textwrap.dedent(SEAM),
                      suffix=".seam", frontend=None)
    assert _run(mod, name) == [["x"]]


# ── 1. the C fd hook and its Python twin, in lock-step ───────────────────────

_CLP_MATRIX = r'''
import sys, json
if sys.argv[1] == "python":
    sys.modules["clausal.logic._clpfd_propagate"] = None
from clausal.logic import clpfd
from clausal.logic.variables import Var, Trail, unify
from clausal.logic.exceptions import LogicException
from clausal.terms import Undefined
assert clpfd._USE_C_PROPAGATE == (sys.argv[1] == "C"), clpfd._USE_C_PROPAGATE

def dom(*vs):
    t = Trail()
    for v in vs:
        clpfd.in_domain(v, 0, 2, t)
    return t

def hook_false():
    X = Var(); t = dom(X); return unify(X, False, t)
def hook_undefined():
    X = Var(); t = dom(X); return unify(X, Undefined, t)
def ne_then_true():
    X, Y = Var(), Var(); t = dom(X); clpfd.fd_ne(X, Y, t); return unify(Y, True, t)
def eq_then_true():
    X, Y = Var(), Var(); t = dom(X); clpfd.fd_eq(X, Y, t); return unify(Y, True, t)
def alldiff_post():
    X = Var(); t = Trail(); return clpfd.all_different([True, X], t)
def alldiff_bind():
    X, Y = Var(), Var(); t = dom(X, Y); clpfd.all_different([X, Y], t); return unify(Y, True, t)
def alldiff_propagate():
    # the propagator itself, reached without the hook
    c = clpfd.AllDiffConstraint((True, Var()))
    from collections import deque
    return c.propagate(Trail(), deque() if not clpfd._USE_C_PROPAGATE else [])
def int_ok():
    X = Var(); t = dom(X); return unify(X, 1, t)
def atom_fails():
    X = Var(); t = dom(X); return unify(X, "a", t)

out = {}
for fn in (hook_false, hook_undefined, ne_then_true, eq_then_true, alldiff_post,
           alldiff_bind, alldiff_propagate, int_ok, atom_fails):
    try:
        out[fn.__name__] = f"-> {fn()!r}"
    except LogicException as e:
        out[fn.__name__] = f"RAISES {e.term[1]!r}"
    except Exception as e:
        out[fn.__name__] = f"RAW {type(e).__name__}: {e}"
print(json.dumps(out))
'''

_CLP_EXPECTED = {
    "hook_false": "RAISES ('type_error', 'integer', False)",
    "hook_undefined": "RAISES ('type_error', 'integer', Undefined)",
    "ne_then_true": "RAISES ('type_error', 'integer', True)",
    "eq_then_true": "RAISES ('type_error', 'integer', True)",
    "alldiff_post": "RAISES ('type_error', 'integer', True)",
    "alldiff_bind": "RAISES ('type_error', 'integer', True)",
    "alldiff_propagate": "RAISES ('type_error', 'integer', True)",
    "int_ok": "-> True",
    "atom_fails": "-> False",
}


def _clp_matrix(cfg: str) -> dict:
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    proc = subprocess.run([sys.executable, "-c", _CLP_MATRIX, cfg],
                          capture_output=True, text=True, env=env, cwd=os.getcwd())
    assert proc.returncode == 0, proc.stderr[-1500:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("cfg", ["C", "python"])
def test_clpfd_twins_refuse_a_truth_atom_as_an_integer(cfg):
    from clausal.logic import clpfd
    if cfg == "C" and not clpfd._USE_C_PROPAGATE:
        pytest.skip("C propagate module not built here")
    got = _clp_matrix(cfg)
    assert len(got) == len(_CLP_EXPECTED)          # the extraction is not empty
    assert got == _CLP_EXPECTED


# ── 6. list_to_set/2 is linear ───────────────────────────────────────────────

def test_list_to_set_is_not_quadratic(native):
    """20 000 distinct ints: the quadratic ==/2 scan took ~5 s at 4 500
    (~100 s here); the key set takes milliseconds.  The bound is loose."""
    mod = native.load("l3_truth_review_l2s",
                      "q(N) :- numlist(1, 20000, L0), append(L0, L0, L),\n"
                      "        list_to_set(L, S), length(S, N).\n")
    t0 = time.perf_counter()
    assert _run(mod, "q") == [20000]
    assert time.perf_counter() - t0 < 5.0


# ── 7. both spellings of a truth atom cross to Python alike ──────────────────

def test_a_str_truth_spelling_crosses_as_the_object():
    from clausal.logic.atoms import crossing_value
    from clausal.logic.to_python import to_python, unwrap_atom
    for spell, obj in (("true", True), ("false", False), ("undefined", Undefined)):
        assert crossing_value(spell) is obj
        assert to_python(spell) is obj
        assert unwrap_atom(spell) is obj
        assert to_python([spell])[0] is obj
    assert to_python("foo") == "foo"
    assert crossing_value("foo") == "foo"
