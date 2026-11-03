"""How the CLP(Q) port's time grows with the size of the store.

Times the operations a program hits on the port of clp(q,r) 1.3.3
(CLAUSAL_CLPQ=holzbaur, clausal/logic/clpq/) at a ladder of sizes, fits
the log-log slope of time against n, counts the algorithm's work at each
size (back substitutions, rows read and rewritten, terms read, bb_inf
nodes, Fourier-Motzkin cross products, Python calls), and profiles the
largest size that ran.  The counts separate "1.3.3 does k*n^p units of
work" from "the port spends more per unit as n grows" (overhead).

Each point runs in a fresh subprocess under CLAUSAL_CLPQ=holzbaur, so one
point cannot warm or poison another and a point past the cap is killed.

Usage (from the repo root, the engine built):

    python benchmarks/clpq_port_scaling.py                 # every case
    python benchmarks/clpq_port_scaling.py chain_le left_sum
    python benchmarks/clpq_port_scaling.py --list
    python benchmarks/clpq_port_scaling.py --cap 60 --jobs 4 --json out.json
    python benchmarks/clpq_port_scaling.py --profile left_sum  # cProfile, largest n
    python benchmarks/clpq_port_scaling.py --scryer chain_le   # 1.3.3's text in Scryer

--scryer runs the same shape on Scryer's copy of the 1.3.3 text
(tests/_oracles.SCRYER) and reads its `time/1` CPU seconds and
inferences.  That copy evaluates rationals in an interpreted eval_q:
compare exponents, not constants.

The survey that uses this script:
implementation_plans/clpq/2026-11-03-port-complexity-survey.md.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAPS = False        # --caps: keep the port's D24 resource caps

# ---------------------------------------------------------------- cases
#
# Each case is (setup, sizes, scryer).  setup(n) builds what is not timed
# and returns a callable that does the timed operation once and returns
# True; a fresh setup is made for every repetition.  scryer is None or
# (program text, goal template with {n}).

CASES = {}


def case(sizes, scryer=None, reps_under=1.0):
    def register(function):
        CASES[function.__name__] = dict(setup=function, sizes=sizes,
                                        scryer=scryer, doc=function.__doc__)
        return function
    return register


def _api():
    from clausal.logic.clpq import holzbaur
    from clausal.logic.pending import drain
    from clausal.logic.variables import Trail, Var, deref, unify
    return holzbaur, drain, Trail, Var, deref, unify


def _sum(variables, coefficients=None):
    """c1*X1 + c2*X2 + ... as the reader builds it: left-leaning."""
    from clausal.pythonic_ast.nodes import Add, Mult
    result = None
    for i, v in enumerate(variables):
        term = v if coefficients is None or coefficients[i] == 1 \
            else Mult(left=coefficients[i], right=v)
        result = term if result is None else Add(left=result, right=term)
    return result


def _chain(h, t, xs, relation="le"):
    post = {"le": h.q_le, "lt": h.q_lt}[relation]
    for a, b in zip(xs, xs[1:]):
        assert post(a, b, t)


def _bounded_chain(n):
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    _chain(h, t, xs)
    assert h.q_ge(xs[0], 0, t) and h.q_le(xs[-1], 100, t)
    return h, t, xs


_CHAIN_PL = """
:- use_module(library(clpq)).
:- use_module(library(time)).
:- use_module(library(lists)).
chain([_]).
chain([A,B|T]) :- {A =< B}, chain([B|T]).
lst([X],X).
lst([_|T],X) :- lst(T,X).
bchain(N, L) :- length(L, N), chain(L), L = [F|_], lst(L, La), {F >= 0, La =< 100}.
"""


@case([100, 200, 400, 800, 1600, 3200],
      scryer=(_CHAIN_PL, "length(L, {n}), time(chain(L))"))
def chain_le(n):
    """Post X1 =< X2 =< ... =< Xn, one constraint at a time."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    return lambda: _chain(h, t, xs) or True


@case([100, 200, 400, 800, 1600, 3200])
def chain_lt(n):
    """Post X1 < X2 < ... < Xn (strict bounds)."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    return lambda: _chain(h, t, xs, "lt") or True


_EQ_PL = _CHAIN_PL + """
eqs([_]).
eqs([A,B|T]) :- {A + B = 1}, eqs([B|T]).
"""


@case([100, 200, 400, 800, 1600, 3200],
      scryer=(_EQ_PL, "length(L, {n}), time(eqs(L))"))
def chain_eq(n):
    """Post Xi + Xi+1 = 1 for i < n: each equation eliminates a variable."""
    h, drain, Trail, Var, deref, unify = _api()
    from clausal.pythonic_ast.nodes import Add
    t = Trail()
    xs = [Var() for _ in range(n)]

    def run():
        for a, b in zip(xs, xs[1:]):
            assert h.q_eq(Add(left=a, right=b), 1, t)
        return True
    return run


def _dense(n):
    """n rows over n variables, every coefficient nonzero, feasible at 0."""
    rows = []
    for i in range(n):
        coefficients = [((i * 7 + j * 13) % 11) - 5 or 1 for j in range(n)]
        rows.append((coefficients, n + i))
    return rows


_DENSE_PL = _CHAIN_PL + """
dense(N, Xs) :- length(Xs, N), dense_rows(0, N, Xs).
dense_rows(I, N, _) :- I >= N, !.
dense_rows(I, N, Xs) :- row(I, 0, Xs, 0, E), B is N + I, {E =< B}, I1 is I + 1, dense_rows(I1, N, Xs).
row(_, _, [], E, E).
row(I, J, [X|Xs], E0, E) :- C0 is ((I*7 + J*13) mod 11) - 5, (C0 =:= 0 -> C = 1 ; C = C0), J1 is J + 1, row(I, J1, Xs, E0 + C*X, E).
"""


@case([5, 10, 20, 40, 80], scryer=(_DENSE_PL, "time(dense({n}, _))"))
def dense_rows(n):
    """Post n dense inequalities sum_j c_ij*Xj =< n + i, all c_ij nonzero."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    rows = _dense(n)

    def run():
        for coefficients, bound in rows:
            assert h.q_le(_sum(xs, coefficients), bound, t)
        return True
    return run


@case([100, 200, 400, 800, 1600])
def diseq(n):
    """On a posted chain, post Xi + Xi+1 =\\= i for every i."""
    h, drain, Trail, Var, deref, unify = _api()
    from clausal.pythonic_ast.nodes import Add
    t = Trail()
    xs = [Var() for _ in range(n)]
    _chain(h, t, xs)

    def run():
        for i, (a, b) in enumerate(zip(xs, xs[1:])):
            assert h.q_ne(Add(left=a, right=b), i, t)
        return True
    return run


_BIND_PL = _CHAIN_PL + """
nums(I, N, []) :- I >= N, !.
nums(I, N, [I|T]) :- I1 is I + 1, nums(I1, N, T).
bindn(N) :- length(L, N), chain(L), nums(0, N, Ns), time(L = Ns).
"""


@case([50, 100, 200, 400, 800, 1600], scryer=(_BIND_PL, "bindn({n})"))
def bind_numbers(n):
    """A chain X1 =< ... =< Xn bound to [0, ..., n-1] in one unification."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    _chain(h, t, xs)

    def run():
        assert unify(xs, list(range(n)), t)
        for _ in drain(t):
            return True
        return False
    return run


_BIND_EACH_PL = _BIND_PL + """
each([], []).
each([X|Xs], [N|Ns]) :- X = N, each(Xs, Ns).
binde(N) :- length(L, N), chain(L), nums(0, N, Ns), time(each(L, Ns)).
"""


@case([50, 100, 200, 400, 800, 1600], scryer=(_BIND_EACH_PL, "binde({n})"))
def bind_numbers_each(n):
    """The chain of bind_numbers bound to [0, ..., n-1] one variable at a
    time, first to last (n unifications)."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    _chain(h, t, xs)

    def run():
        for i, x in enumerate(xs):
            assert unify(x, i, t)
            for _ in drain(t):
                break
            else:
                return False
        return True
    return run


_VARVAR_PL = _CHAIN_PL + """
nonneg([]).
nonneg([Y|T]) :- {Y >= 0}, nonneg(T).
vv(N) :- length(L, N), chain(L), length(M, N), nonneg(M), time(L = M).
"""


@case([25, 50, 100, 200, 400], scryer=(_VARVAR_PL, "vv({n})"))
def bind_varvar(n):
    """A chain X1 =< ... =< Xn, Yi >= 0, then [X1..Xn] = [Y1..Yn] (D24 Low 8)."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    ys = [Var() for _ in range(n)]
    _chain(h, t, xs)
    for y in ys:
        assert h.q_ge(y, 0, t)

    def run():
        assert unify(xs, ys, t)
        for _ in drain(t):
            return True
        return False
    return run


_SUP_PL = _CHAIN_PL + """
sumv([X], X).
sumv([X|T], X + S) :- T = [_|_], sumv(T, S).
supc(N) :- bchain(N, L), sumv(L, S), time(sup(S, _)).
"""


@case([50, 100, 200, 400, 800, 1600], scryer=(_SUP_PL, "supc({n})"))
def sup_chain(n):
    """sup(X1 + ... + Xn) over 0 =< X1 =< ... =< Xn =< 100."""
    h, drain, Trail, Var, deref, unify = _api()
    h, t, xs = _bounded_chain(n)
    objective = _sum(xs)

    def run():
        value = Var()
        assert h.sup(objective, value, t)
        assert deref(value) == 100 * n
        return True
    return run


@case([50, 100, 200, 400, 800, 1600])
def inf_chain(n):
    """inf(Xn - X1) over the bounded chain (0: one pivot path)."""
    h, drain, Trail, Var, deref, unify = _api()
    h, t, xs = _bounded_chain(n)
    from clausal.pythonic_ast.nodes import Sub
    objective = Sub(left=xs[-1], right=xs[0])

    def run():
        value = Var()
        assert h.inf(objective, value, t) and deref(value) == 0
        return True
    return run


def _lp(n):
    """Xi >= 0, Xi + Xi+1 =< 10 + i mod 3: a path LP."""
    h, drain, Trail, Var, deref, unify = _api()
    from clausal.pythonic_ast.nodes import Add
    t = Trail()
    xs = [Var() for _ in range(n)]
    for x in xs:
        assert h.q_ge(x, 0, t)
    for i, (a, b) in enumerate(zip(xs, xs[1:])):
        assert h.q_le(Add(left=a, right=b), 10 + i % 3, t)
    return h, t, xs


_LP_PL = _CHAIN_PL + """
sumv([X], X).
sumv([X|T], X + S) :- T = [_|_], sumv(T, S).
nonneg([]).
nonneg([Y|T]) :- {Y >= 0}, nonneg(T).
path(_, [_]).
path(I, [A,B|T]) :- C is 10 + I mod 3, {A + B =< C}, I1 is I + 1, path(I1, [B|T]).
lp(N, L) :- length(L, N), nonneg(L), path(0, L).
lpmax(N) :- lp(N, L), sumv(L, S), time(maximize(S)).
"""


@case([25, 50, 100, 200, 400, 800], scryer=(_LP_PL, "lpmax({n})"))
def lp_maximize(n):
    """maximize(X1 + ... + Xn) over the path LP Xi + Xi+1 =< 10 + i mod 3."""
    h, drain, Trail, Var, deref, unify = _api()
    h, t, xs = _lp(n)
    objective = _sum(xs)

    def run():
        value = Var()
        return h.maximize(objective, value, t)
    return run


@case([25, 50, 100, 200, 400, 800])
def lp_post(n):
    """Post the path LP itself (2n constraints) -- lp_maximize's setup."""
    return lambda: _lp(n) and True


def _knapsack(n):
    weights = [10 + (i * 37) % 23 for i in range(n)]
    values = [w + (i * 11) % 7 for i, w in enumerate(weights)]
    return weights, values, sum(weights) // 2


_KNAP_PL = _CHAIN_PL + """
items(I, N, [], [], []) :- I >= N, !.
items(I, N, [X|Xs], [W|Ws], [V|Vs]) :- W is 10 + (I*37) mod 23, V is W + (I*11) mod 7,
    {X >= 0, X =< 1}, I1 is I + 1, items(I1, N, Xs, Ws, Vs).
dot([], [], 0).
dot([X|Xs], [C|Cs], C*X + E) :- dot(Xs, Cs, E).
total([], 0).
total([W|Ws], S) :- total(Ws, S0), S is S0 + W.
knap(N) :- items(0, N, Xs, Ws, Vs), total(Ws, T), Cap is T // 2, dot(Xs, Ws, We), {We =< Cap},
    dot(Xs, Vs, Ve), time(bb_inf(Xs, -Ve, _)).
"""


@case([5, 10, 15, 20, 25, 30, 35, 40], scryer=(_KNAP_PL, "knap({n})"))
def bb_knapsack(n):
    """bb_inf on a 0/1 knapsack: 0 =< xi =< 1, sum wi*xi =< W, min -sum vi*xi."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    weights, values, capacity = _knapsack(n)
    xs = [Var() for _ in range(n)]
    for x in xs:
        assert h.q_ge(x, 0, t) and h.q_le(x, 1, t)
    assert h.q_le(_sum(xs, weights), capacity, t)
    objective = _sum(xs, [-v for v in values])

    def run():
        return h.bb_inf(xs, objective, Var(), t)
    return run


_WIDE_PL = _CHAIN_PL + """
sumv([X], X).
sumv([X|T], X + S) :- T = [_|_], sumv(T, S).
half([]).
half([X|T]) :- {X >= 1/2}, half(T).
wide(N) :- length(L, N), half(L), sumv(L, S), time(bb_inf(L, S, _)).
"""


@case([25, 50, 100, 200, 400], scryer=(_WIDE_PL, "wide({n})"))
def bb_wide(n):
    """bb_inf(Xs, sum Xs) with every Xi >= 1/2: n branches, one per variable."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    from fractions import Fraction
    for x in xs:
        assert h.q_ge(x, Fraction(1, 2), t)
    objective = _sum(xs)

    def run():
        value = Var()
        assert h.bb_inf(xs, objective, value, t) and deref(value) == n
        return True
    return run


_DUMP_PL = _CHAIN_PL + """
dsmall(N) :- bchain(N, L), L = [F|_], lst(L, La), time(dump([F, La], [f, l], _)).
dlarge(N) :- bchain(N, L), length(L, K), length(Ns, K), time(dump(L, Ns, _)).
"""


@case([25, 50, 100, 200, 400, 800], scryer=(_DUMP_PL, "dsmall({n})"))
def dump_small(n):
    """dump([X1, Xn]) of the bounded chain: n - 2 variables eliminated."""
    h, t, xs = _bounded_chain(n)
    return lambda: h.dump([xs[0], xs[-1]], ["f", "l"], t) is not None


@case([25, 50, 100, 200, 400, 800], scryer=(_DUMP_PL, "dlarge({n})"))
def dump_large(n):
    """dump(Xs) of the bounded chain onto all n variables."""
    h, t, xs = _bounded_chain(n)
    names = [f"x{i}" for i in range(n)]
    return lambda: h.dump(xs, names, t) is not None


def _sparse(n, seed=1):
    """n variables in [0, 10], 2n random rows of three terms each."""
    import random
    rng = random.Random(seed)
    rows = []
    for _ in range(2 * n):
        picked = rng.sample(range(n), 3)
        coefficients = [rng.choice([-3, -2, -1, 1, 2, 3]) for _ in picked]
        rows.append((picked, coefficients, rng.randint(5, 20)))
    return rows


@case([6, 8, 10, 12, 16, 20, 24])
def dump_sparse(n):
    """dump([X0, X1]) of n bounded variables under 2n random 3-term rows
    (Fourier-Motzkin's growth on an unstructured store)."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]
    for x in xs:
        assert h.q_ge(x, 0, t) and h.q_le(x, 10, t)
    for picked, coefficients, bound in _sparse(n):
        if not h.q_le(_sum([xs[i] for i in picked], coefficients), bound, t):
            raise AssertionError("infeasible store")
    return lambda: h.dump(xs[:2], ["a", "b"], t) is not None


_ENT_PL = _CHAIN_PL + """
ent(N) :- bchain(N, L), L = [F|_], lst(L, La), time(entailed(F =< La)).
"""


@case([50, 100, 200, 400, 800, 1600], scryer=(_ENT_PL, "ent({n})"))
def entailed(n):
    """entailed(X1 =< Xn) on the bounded chain."""
    h, t, xs = _bounded_chain(n)
    return lambda: h.entailed("=<", xs[0], xs[-1], t)


@case([100, 200, 400, 800, 1600, 3200])
def nonlinear_post(n):
    """Post Zi = Xi * Yi for n triples (each waits: not linear)."""
    h, drain, Trail, Var, deref, unify = _api()
    from clausal.pythonic_ast.nodes import Mult
    t = Trail()
    triples = [(Var(), Var(), Var()) for _ in range(n)]

    def run():
        for x, y, z in triples:
            assert h.q_eq(z, Mult(left=x, right=y), t)
        return True
    return run


@case([100, 200, 400, 800, 1600, 3200])
def nonlinear_wake(n):
    """After Zi = Xi * Yi and Zi =< Zi+1, bind every Yi to a number: each
    binding wakes its delayed goal, which posts a linear row."""
    h, drain, Trail, Var, deref, unify = _api()
    from clausal.pythonic_ast.nodes import Mult
    t = Trail()
    triples = [(Var(), Var(), Var()) for _ in range(n)]
    for x, y, z in triples:
        assert h.q_eq(z, Mult(left=x, right=y), t)
    _chain(h, t, [z for _, _, z in triples])
    ys = [y for _, y, _ in triples]

    def run():
        assert unify(ys, [i + 1 for i in range(n)], t)
        for _ in drain(t):
            return True
        return False
    return run


@case([50, 100, 200, 400, 800, 1600])
def backtrack_rounds(n):
    """On the bounded chain, n rounds of: mark, post Xi >= 50 (a pivot's
    worth of work), undo."""
    h, t, xs = _bounded_chain(n)

    def run():
        for x in xs:
            mark = t.mark()
            assert h.q_ge(x, 50, t)
            t.undo(mark)
        return True
    return run


@case([100, 200, 400, 800, 1600, 3200])
def backtrack_deep(n):
    """A choice point before each link of the chain, then undo them all,
    newest first (chain_le plus n marks and n undos)."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    xs = [Var() for _ in range(n)]

    def run():
        marks = []
        for a, b in zip(xs, xs[1:]):
            marks.append(t.mark())
            assert h.q_le(a, b, t)
        for mark in reversed(marks):
            t.undo(mark)
        return True
    return run


_LSUM_PL = _CHAIN_PL + """
lsum(0, S, S) :- !.
lsum(N, S0, S) :- N1 is N - 1, lsum(N1, S0 + _, S).
ls(N) :- lsum(N, 0, E), time({T = E}).
"""


@case([250, 500, 1000, 2000, 4000, 8000, 32000],
      scryer=(_LSUM_PL, "ls({n})"))
def left_sum(n):
    """{S = X1 + X2 + ... + Xn}, the sum left-leaning as the reader builds it."""
    h, drain, Trail, Var, deref, unify = _api()
    t = Trail()
    expression = _sum([Var() for _ in range(n)])
    return lambda: h.q_eq(Var(), expression, t)


@case([250, 500, 1000, 2000, 4000, 8000, 32000])
def right_sum(n):
    """{S = X1 + (X2 + (... + Xn))}, the sum right-leaning."""
    h, drain, Trail, Var, deref, unify = _api()
    from clausal.pythonic_ast.nodes import Add
    t = Trail()
    xs = [Var() for _ in range(n)]
    expression = xs[-1]
    for x in reversed(xs[:-1]):
        expression = Add(left=x, right=expression)
    return lambda: h.q_eq(Var(), expression, t)


@case([100, 200, 400, 800, 1600, 3200])
def components(n):
    """n independent components {Ai + Bi = 1, Ai >= 0, Bi >= 0}, then
    sup(An) on the last."""
    h, drain, Trail, Var, deref, unify = _api()
    from clausal.pythonic_ast.nodes import Add
    t = Trail()
    pairs = [(Var(), Var()) for _ in range(n)]

    def run():
        for a, b in pairs:
            assert h.q_eq(Add(left=a, right=b), 1, t)
            assert h.q_ge(a, 0, t) and h.q_ge(b, 0, t)
        value = Var()
        assert h.sup(pairs[-1][0], value, t) and deref(value) == 1
        return True
    return run


# The engine path: the same shape as a Clausal Prolog program, loaded and
# queried through the engine, against the bare API (engine_*_bare).

_ENGINE_CHAIN = """\
:- use_module(library(clpq)).
chain([_]).
chain([A,B|T]) :- {A =< B}, chain([B|T]).
lst([X],X).
lst([_|T],X) :- lst(T,X).
go(N, S) :- length(L, N), chain(L), L = [F|_], lst(L, La), {F >= 0, La =< 100}, sup(La, S).
lsum(0, S, S).
lsum(N, S0, S) :- N > 0, N1 is N - 1, lsum(N1, S0 + _, S).
ls(N) :- lsum(N, 0, E), {_ = E}.
"""


def _engine(goal):
    from clausal.logic.solve import solve
    from clausal.testing import load_clausal_module
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "clpq_scaling_engine.clausal")
    with open(path, "w") as handle:
        handle.write(_ENGINE_CHAIN)
    module = load_clausal_module(path)

    def run():
        for _ in solve(goal, module=module):
            return True
        return False
    return run


@case([100, 200, 400, 800, 1600])
def engine_chain(n):
    """go(N, S) through the engine: build the chain, bound it, sup(Xn)."""
    from clausal.logic.variables import Var
    return _engine(("go", n, Var()))


@case([100, 200, 400, 800, 1600])
def engine_chain_bare(n):
    """engine_chain's work through the bare API."""
    h, drain, Trail, Var, deref, unify = _api()

    def run():
        h2, t, xs = _bounded_chain(n)
        value = Var()
        return h.sup(xs[-1], value, t)
    return run


@case([250, 500, 1000, 2000, 4000])
def engine_left_sum(n):
    """ls(N) through the engine: {_ = 0 + _ + ... + _}, n terms."""
    return _engine(("ls", n))


# ---------------------------------------------------------------- counting

def _install_counters():
    """Wrap the functions whose calls are 1.3.3's units of work, in every
    clpq module that imported them.  Returns the counts dict."""
    import importlib
    import pkgutil
    import clausal.logic.clpq as package
    from clausal.logic.clpq import (bounded_simplex, branch_and_bound,
                                    fourier_motzkin, linear_forms)
    counts = dict(back_substitutions=0, rows_read=0, rows_rewritten=0,
                  terms_read=0, terms_scanned=0, pivots=0, bb_nodes=0, fm_cross=0,
                  fm_eliminations=0)
    modules = [importlib.import_module(f"clausal.logic.clpq.{m.name}")
               for m in pkgutil.iter_modules(package.__path__)]

    def patch(owner, name, wrapper):
        original = getattr(owner, name)
        wrapped = wrapper(original)
        for module in modules:
            if getattr(module, name, None) is original:
                setattr(module, name, wrapped)

    def substitute(original):
        def counting(variable, form_variable, form_x):
            counts["rows_read"] += 1
            counts["terms_scanned"] += len(form_x.terms)
            form = original(variable, form_variable, form_x)
            if form is not None:
                counts["rows_rewritten"] += 1
                counts["terms_read"] += len(form_x.terms)
            return form
        return counting

    def calls(key):
        def wrapper(original):
            def counting(*arguments, **keywords):
                counts[key] += 1
                return original(*arguments, **keywords)
            return counting
        return wrapper

    def cross(original):
        def counting(occurrences):
            result = original(occurrences)
            counts["fm_cross"] += len(result)
            return result
        return counting

    patch(linear_forms, "normal_form_substitute", substitute)
    patch(bounded_simplex, "back_substitute_variables", calls("back_substitutions"))
    patch(bounded_simplex, "pivot", calls("pivots"))
    patch(bounded_simplex, "pivot_ignoring_bounds", calls("pivots"))
    patch(branch_and_bound, "branch_and_bound_reoptimize", calls("bb_nodes"))
    patch(fourier_motzkin, "crossproduct", cross)
    patch(fourier_motzkin, "eliminate_minimum", calls("fm_eliminations"))
    return counts


# ---------------------------------------------------------------- one point

def _point(name, n, reps, profile, count, caps=False):
    """Run one point in this process; return a dict."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 100_000))
    import clausal  # noqa: F401 -- the import hook
    from clausal.logic.clpq import SOLVER
    assert SOLVER == "holzbaur", SOLVER
    if not caps:
        from clausal.logic.clpq import limits
        for resource in limits.DEFAULTS:
            limits.set_limit(resource, 10 ** 15)
    setup = CASES[name]["setup"]
    result = dict(case=name, n=n, caps=caps)
    times = []
    try:
        for _ in range(reps):
            run = setup(n)
            start = time.perf_counter()
            ok = run()
            times.append(time.perf_counter() - start)
            if not ok:
                result["error"] = "the operation failed"
                return result
            if times[-1] > 5:
                break
    except Exception as exc:  # noqa: BLE001 -- reported per point
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        if times:
            result["seconds"] = min(times)
        return result
    result["seconds"] = min(times)
    print(json.dumps(result), flush=True)   # kept if counting times out
    if count:
        counts = _install_counters()
        import cProfile
        import pstats
        run = setup(n)
        for key in counts:              # the timed operation's work only
            counts[key] = 0
        profiler = cProfile.Profile()
        profiler.enable()
        run()
        profiler.disable()
        stats = pstats.Stats(profiler)
        counts["python_calls"] = stats.total_calls
        result["counts"] = counts
    if profile:
        import cProfile
        import io
        import pstats
        run = setup(n)
        profiler = cProfile.Profile()
        profiler.enable()
        run()
        profiler.disable()
        text = []
        for key in ("cumulative", "tottime"):
            stream = io.StringIO()
            stats = pstats.Stats(profiler, stream=stream)
            stats.strip_dirs().sort_stats(key).print_stats(25)
            text.append(f"--- sorted by {key}\n{stream.getvalue()}")
        result["profile"] = "\n".join(text)
    return result


def _run_point(name, n, cap, reps, profile, count):
    """The point in a subprocess under CLAUSAL_CLPQ=holzbaur, killed at
    *cap* seconds (times 3 when it also counts and profiles)."""
    environment = dict(os.environ, CLAUSAL_CLPQ="holzbaur",
                       PYTHONPATH=str(ROOT))
    argv = [sys.executable, str(pathlib.Path(__file__).resolve()),
            "--point", name, str(n), "--reps", str(reps)]
    if profile:
        argv.append("--profile")
    if count:
        argv.append("--count")
    if CAPS:
        argv.append("--caps")
    try:
        done = subprocess.run(argv, env=environment, capture_output=True,
                              text=True, timeout=cap * (3 if profile or count else 1.2) + 30,
                              cwd=ROOT)
    except subprocess.TimeoutExpired as expired:
        output = expired.stdout or ""
        if isinstance(output, bytes):
            output = output.decode()
        lines = [line for line in output.splitlines() if line.startswith("{")]
        if lines:                       # timed, then the counting ran over
            return json.loads(lines[-1])
        return dict(case=name, n=n, error=f"timeout past {cap} s")
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    if not lines:
        return dict(case=name, n=n, error=f"exit {done.returncode}: "
                    f"{done.stderr.strip()[-300:]}")
    return json.loads(lines[-1])


def _slope(points):
    """Least-squares slope of log(seconds) on log(n)."""
    good = [(math.log(p["n"]), math.log(p["seconds"])) for p in points
            if "seconds" in p and "error" not in p and p["seconds"] > 0.002]
    if len(good) < 2:
        return None
    mx = sum(x for x, _ in good) / len(good)
    my = sum(y for _, y in good) / len(good)
    sxx = sum((x - mx) ** 2 for x, _ in good)
    return sum((x - mx) * (y - my) for x, y in good) / sxx if sxx else None


def _top_slope(points, key=None):
    """The slope between the last two good points (the asymptote)."""
    good = [p for p in points if "error" not in p and "seconds" in p
            and (key is None or p.get("counts", {}).get(key))]
    if len(good) < 2:
        return None
    a, b = good[-2], good[-1]
    if key is None:
        ya, yb = a["seconds"], b["seconds"]
    else:
        ya, yb = a["counts"][key], b["counts"][key]
    if ya <= 0 or yb <= 0:
        return None
    return math.log(yb / ya) / math.log(b["n"] / a["n"])


def run_case(name, cap, sizes=None, profile=False, count=True):
    """The ladder for *name*: stops at a failure, or when the next point
    would pass *cap* at the slope so far."""
    sizes = sizes or CASES[name]["sizes"]
    points = []
    for n in sizes:
        if points and "seconds" in points[-1] and len(points) >= 2:
            slope = max(_top_slope(points) or 1.0, 1.0)
            last = points[-1]
            if last["seconds"] * (n / last["n"]) ** slope > cap:
                break
        reps = 3
        point = _run_point(name, n, cap, reps, False,
                           count and (not points or points[-1].get("seconds", cap) < cap / 20))
        points.append(point)
        print(f"  {name:20} n={n:6} " + (
            f"{point['seconds']:9.4f} s" if "seconds" in point else "")
            + (f"  ERROR {point['error']}" if "error" in point else "")
            + (f"  {point['counts']}" if "counts" in point else ""),
            flush=True)
        if "error" in point:
            break
    summary = dict(case=name, doc=CASES[name]["doc"], points=points,
                   slope=_slope(points), top_slope=_top_slope(points))
    for key in ("terms_read", "terms_scanned", "rows_read", "python_calls", "bb_nodes",
                "fm_cross", "back_substitutions"):
        s = _top_slope(points, key)
        if s is not None:
            summary[f"slope_{key}"] = s
    if profile:
        good = [p for p in points if "error" not in p]
        if good:
            biggest = good[-1]["n"]
            summary["profile"] = _run_point(name, biggest, cap, 1, True,
                                            False).get("profile")
    return summary


# ---------------------------------------------------------------- Scryer

_SCRYER_TIME = re.compile(r"% CPU time: ([0-9.]+)s, ([0-9_]+) inferences")


def scryer_case(name, cap, sizes=None):
    sys.path.insert(0, str(ROOT))
    from tests._oracles import SCRYER
    spec = CASES[name]["scryer"]
    if spec is None:
        return None
    program, goal = spec
    sizes = sizes or CASES[name]["sizes"]
    points = []
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, f"{name}.pl")
        with open(path, "w") as handle:
            handle.write(program)
        for n in sizes:
            if len(points) >= 2:
                slope = max(_top_slope(points) or 1.0, 1.0)
                if points[-1]["seconds"] * (n / points[-1]["n"]) ** slope > cap:
                    break
            argv = [SCRYER, path, "-g", goal.format(n=n), "-g", "halt"]
            try:
                done = subprocess.run(argv, capture_output=True, text=True,
                                      timeout=cap * 1.5 + 10,
                                      stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                points.append(dict(n=n, error="timeout"))
                break
            found = _SCRYER_TIME.findall(done.stdout + done.stderr)
            if not found or " causes: " in done.stdout + done.stderr:
                points.append(dict(n=n, error=(done.stdout + done.stderr)[-200:]))
                break
            seconds, inferences = found[-1]
            points.append(dict(n=n, seconds=float(seconds),
                               counts=dict(inferences=int(inferences.replace("_", "")))))
            print(f"  scryer {name:13} n={n:6} {float(seconds):9.4f} s "
                  f"{inferences} inferences", flush=True)
    return dict(case=name, points=points, slope=_slope(points),
                top_slope=_top_slope(points),
                slope_inferences=_top_slope(points, "inferences"))


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", nargs="*")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--cap", type=float, default=60.0,
                        help="seconds a point may take (default 60)")
    parser.add_argument("--sizes", help="comma-separated n, for every case")
    parser.add_argument("--jobs", type=int, default=1,
                        help="cases run at once (each point is a process)")
    parser.add_argument("--profile", action="store_true",
                        help="cProfile the largest n that ran")
    parser.add_argument("--no-count", action="store_true")
    parser.add_argument("--scryer", action="store_true",
                        help="also run the case's shape on Scryer's 1.3.3 copy")
    parser.add_argument("--json", help="write every result here")
    parser.add_argument("--caps", action="store_true",
                        help="keep the port's resource caps (DEVIATIONS.md "
                             "D24); by default they are lifted, to measure "
                             "1.3.3's algorithm past them")
    parser.add_argument("--point", nargs=2, metavar=("CASE", "N"),
                        help=argparse.SUPPRESS)
    parser.add_argument("--reps", type=int, default=3, help=argparse.SUPPRESS)
    parser.add_argument("--count", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    global CAPS
    CAPS = args.caps

    if args.point:
        name, n = args.point
        print(json.dumps(_point(name, int(n), args.reps, args.profile,
                                args.count, args.caps)))
        return 0
    if args.list:
        for name, spec in CASES.items():
            mark = " [scryer]" if spec["scryer"] else ""
            print(f"{name:20} {spec['sizes']}{mark}\n    {spec['doc']}")
        return 0
    names = args.cases or list(CASES)
    unknown = [name for name in names if name not in CASES]
    if unknown:
        parser.error(f"unknown cases: {', '.join(unknown)}")
    sizes = [int(s) for s in args.sizes.split(",")] if args.sizes else None
    results = {}

    def one(name):
        summary = run_case(name, args.cap, sizes, args.profile,
                           not args.no_count)
        if args.scryer:
            summary["scryer"] = scryer_case(name, args.cap, sizes)
        return name, summary

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        for name, summary in pool.map(one, names):
            results[name] = summary

    print("\ncase                   sizes        seconds (min)                      slope  top")
    for name, s in results.items():
        good = [p for p in s["points"] if "seconds" in p]
        fmt = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
        print(f"{name:22} {good[0]['n'] if good else '-'}..{good[-1]['n'] if good else '-'}"
              f"  {' '.join(f'{p['seconds']:.3g}' for p in good)}"
              f"  slope {fmt(s['slope'])} top {fmt(s['top_slope'])}"
              + (f"  scryer top {fmt(s['scryer']['top_slope'])}"
                 if s.get("scryer") else ""))
    if args.json:
        with open(args.json, "w") as handle:
            json.dump(results, handle, indent=1)
    if args.profile:
        for name, s in results.items():
            if s.get("profile"):
                print(f"\n================ {name}\n{s['profile']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
