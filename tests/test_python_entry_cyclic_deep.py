"""A cyclic or deep term handed in from PYTHON works as it does inside a
program, or raises the engine's ISO error -- never a raw RecursionError
(2026-10-24, operator ruling 2026-10-24).

Inside a program, ``X = f(X), acyclic_term(X)`` fails, ``X = X`` succeeds
and ``=`` on a 100k-nested ground term succeeds (the rational-tree work).
The Python entry compiles the goal it is handed as a query, and the query
compiler's walks (its variable collector, its opaque-value lifter) are
recursive descents, so the same goals raised ``RecursionError`` at
``solve()``.  Now an argument those walks cannot descend is passed as a
run-time parameter -- the way a program's ``call/1`` passes it.

The two converters cannot answer for a cycle (a Python tuple cannot hold
itself, and a sort key for a rational tree is infinite): ``to_python`` and
``term_key`` raise ``error(resource_error(finite_memory), _)`` for a cycle,
the error the engine raises where it KNOWS it saw one (assertz of a cyclic
term), and ``error(resource_error(stack), _)`` for an acyclic term too deep
to convert -- both as a ``LogicException``.
"""
from __future__ import annotations

import pytest

import clausal
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call, once, query, solve
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.testing import load_clausal_module

PL = """\
cyc(X) :- X = f(X).
p(_).
same(X, X).
"""

DEPTH = 100_000


@pytest.fixture
def m(tmp_path):
    p = tmp_path / "pyentry_cyc.pl"
    p.write_text(PL)
    return load_clausal_module(p)


def _cyclic():
    x = Var()
    assert unify(x, ("f", x), Trail())
    return x


def _deep(n=DEPTH, leaf="a"):
    t = leaf
    for _ in range(n):
        t = ("f", t)
    return t


def _count(goal, m):
    return sum(1 for _ in solve(goal, module=m))


def _formal(exc):
    term = exc.term
    assert term[0] == "error", term
    return term[1]


# ── solve(): a cyclic argument ──────────────────────────────────────────────

def test_acyclic_term_of_a_cycle_from_python_fails(m):
    X = Var()
    for _ in solve(("cyc", X), module=m):
        assert _count(("acyclic_term", X), m) == 0
        break


def test_a_cycle_unifies_with_itself_from_python(m):
    X = Var()
    for _ in solve(("cyc", X), module=m):
        assert _count(("=", X, X), m) == 1
        break


def test_a_cycle_built_in_python_reaches_a_clause_head(m):
    x = _cyclic()
    assert _count(("same", x, x), m) == 1
    assert _count(("p", x), m) == 1
    assert _count(("acyclic_term", x), m) == 0


def test_two_cycles_are_one_rational_tree_from_python(m):
    x = _cyclic()
    y = Var()
    assert unify(y, ("f", ("f", y)), Trail())
    assert _count(("=", x, y), m) == 1
    assert _count(("==", x, y), m) == 1


def test_a_cycle_inside_a_conjunction_and_a_findall(m):
    x = _cyclic()
    assert _count((",", ("p", x), ("=", x, x)), m) == 1
    L = Var()
    for _ in solve(("findall", 1, ("acyclic_term", x), L), module=m):
        assert deref(L) == []
        break
    else:
        pytest.fail("no solution")


def test_once_and_query_and_call_take_a_cycle(m):
    x = _cyclic()
    assert once(("=", x, x), module=m) is not None
    assert list(query(("p", x), {}, module=m)) == [{}]
    assert sum(1 for _ in call("acyclic_term", x, module=m)) == 0


def test_a_cycle_answer_binds_the_callers_variable(m):
    x = _cyclic()
    Y = Var()
    for _ in solve(("=", Y, x), module=m):
        assert deref(Y) is deref(x)
        break


# ── solve(): a deep argument ────────────────────────────────────────────────

def test_a_deep_ground_term_unifies_from_python(m):
    t = _deep()
    V = Var()
    for _ in solve(("=", t, V), module=m):
        assert deref(V) is t
        break
    else:
        pytest.fail("no solution")


def test_a_deep_ground_term_reaches_a_clause_head(m):
    t = _deep()
    assert _count(("p", t), m) == 1
    assert _count(("same", t, _deep()), m) == 1
    assert _count(("acyclic_term", t), m) == 1


def test_a_deep_term_with_a_hole_binds_it(m):
    hole = Var()
    t = _deep(leaf=hole)
    assert _count(("=", t, _deep(leaf="z")), m) == 1


def test_call_takes_a_deep_argument(m):
    assert sum(1 for _ in call("p", _deep(), module=m)) == 1


# ── solve(): a goal a parameter cannot help ─────────────────────────────────

def _stack_error(goal, m):
    with pytest.raises(LogicException) as info:
        list(solve(goal, module=m))
    assert _formal(info.value) == ("resource_error", "stack")


def test_a_cyclic_conjunction_goal_is_a_stack_error(m):
    """``G = (G, true), call(G)`` inside a program raises
    resource_error(stack) (Scryer runs out of memory); handed to solve()
    the same goal raises the same error, not RecursionError."""
    g = Var()
    assert unify(g, (",", g, "true"), Trail())
    _stack_error(g, m)


def test_a_conjunction_too_deep_to_compile_is_a_stack_error(m):
    c = "true"
    for _ in range(DEPTH):
        c = (",", "true", c)
    _stack_error(c, m)


def test_an_ordinary_goal_still_compiles_and_caches(m):
    from clausal.logic import solve as solve_mod
    X = Var()
    assert _count(("=", X, ("f", ("g", 1))), m) == 1
    assert _count(("p", ("f", ("g", 1))), m) == 1
    assert solve_mod._query_cache, "an ordinary goal keeps the cache"


# ── the converters ──────────────────────────────────────────────────────────

def test_to_python_of_a_cycle_is_finite_memory():
    x = _cyclic()
    with pytest.raises(LogicException) as info:
        clausal.to_python(deref(x))
    assert _formal(info.value) == ("resource_error", "finite_memory")
    with pytest.raises(LogicException):
        clausal.to_python(x)


def test_to_python_of_a_deep_term_is_stack():
    with pytest.raises(LogicException) as info:
        clausal.to_python(_deep())
    assert _formal(info.value) == ("resource_error", "stack")


def test_term_key_of_a_cycle_is_finite_memory():
    x = _cyclic()
    with pytest.raises(LogicException) as info:
        clausal.term_key(x)
    assert _formal(info.value) == ("resource_error", "finite_memory")


def test_term_key_of_a_deep_term_is_stack():
    with pytest.raises(LogicException) as info:
        clausal.term_key(_deep())
    assert _formal(info.value) == ("resource_error", "stack")


def test_the_converters_are_unchanged_on_ordinary_terms():
    assert clausal.to_python(("f", [1, ("g", "a")])) == ("f", [1, ("g", "a")])
    assert clausal.term_key(("f", 1)) < clausal.term_key(("f", 2))


def test_compare_still_orders_cycles_from_python(m):
    """compare/3 and msort/2 catch the internal key's overflow and compare
    pairwise; the public key's loud raise does not reach them."""
    x = _cyclic()
    y = Var()
    assert unify(y, ("f", ("f", y)), Trail())
    O = Var()
    for _ in solve(("compare", O, x, y), module=m):
        assert deref(O) == "="
        break
    else:
        pytest.fail("no solution")
    S = Var()
    assert _count(("msort", [x, "a"], S), m) == 1
