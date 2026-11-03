# tests/clpq_port/test_unify_constrained_variables.py
"""DEVIATIONS.md D24, Low 8: unifying constrained variables with
constrained variables.

`X1 =< X2 =< ... =< Xn`, each `Yi >= 0`, then `[X1, ..., Xn] = [Y1, ...,
Yn]`.  Each binding is a constraint `X = Y` that 1.3.3 solves by pivots,
and each pivot back-substitutes into every row of the class (bv.pl,
backsubst/2 and bs/3): about n^2 rows rewritten in all, each about n/3
terms long, so the work is cubic in n in 1.3.3 itself (Scryer's copy of
the text runs 1.2M, 8.2M and 59M inferences at n = 50, 100 and 200).
These tests pin that the port does that work and no more:

- the rows rewritten are 1.3.3's count, n(n - 1);
- the merge of a pivot row into a row looks up each variable's order
  once, not twice per comparison (the port's overhead, now removed);
- n = 100 answers well inside a generous bound.
"""
import time

import pytest

from clausal.logic.clpq import bounded_simplex
from clausal.logic.clpq import holzbaur as h
from clausal.logic.clpq import linear_forms
from clausal.logic.clpq import variable_ordering
from clausal.logic.pending import drain
from clausal.logic.variables import Trail, Var, deref, unify


def _store(n):
    t = Trail()
    xs = [Var() for _ in range(n)]
    ys = [Var() for _ in range(n)]
    for a, b in zip(xs, xs[1:]):
        assert h.q_le(a, b, t)
    for y in ys:
        assert h.q_ge(y, 0, t)
    return t, xs, ys


def _unify(t, xs, ys):
    assert unify(xs, ys, t)
    assert any(True for _ in drain(t))


def _answers(t, xs):
    # X1 is now >= 0 and the least of the chain: inf(X1) = inf(Xn) = 0.
    for x in (xs[0], xs[-1]):
        s = Var()
        assert h.inf(x, s, t) and deref(s) == 0


@pytest.mark.parametrize("n", [10, 20, 40])
def test_the_rows_rewritten_are_1_3_3s_count(n, monkeypatch):
    rewritten = 0
    substitute = linear_forms.normal_form_substitute

    def counting(*arguments):
        nonlocal rewritten
        form = substitute(*arguments)
        if form is not None:
            rewritten += 1
        return form

    monkeypatch.setattr(bounded_simplex, "normal_form_substitute", counting)
    t, xs, ys = _store(n)
    rewritten = 0
    _unify(t, xs, ys)
    assert rewritten == n * (n - 1)
    _answers(t, xs)


def test_a_merge_looks_up_each_order_once(monkeypatch):
    # Counts the order lookups of the merges and scans (state_of and
    # order_key in linear_forms and variable_ordering) against the terms
    # of the rows rewritten.  A merge reads each term of the row once and
    # the pivot row's orders once per back substitution; upper_bound's
    # nf_coeff_of scans (1.3.3's too) read a row up to the sought
    # variable.  Deterministic: 1.64 lookups a term at n = 40 before the
    # fix (compare_variable_order looked up both orders at each
    # comparison), 1.16 after.
    n = 40
    lookups = 0

    def counted(function):
        def counting(argument):
            nonlocal lookups
            lookups += 1
            return function(argument)
        return counting

    terms = 0
    substitute = linear_forms.normal_form_substitute

    def reading(variable, form_variable, form_x, *rest):
        nonlocal terms
        form = substitute(variable, form_variable, form_x, *rest)
        if form is not None:
            terms += len(form_x.terms)
        return form

    t, xs, ys = _store(n)
    monkeypatch.setattr(bounded_simplex, "normal_form_substitute", reading)
    for module in (linear_forms, variable_ordering):
        for name in ("state_of", "order_key"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name,
                                    counted(getattr(module, name)))
    lookups = 0
    _unify(t, xs, ys)
    assert terms > 0
    assert lookups <= 1.3 * terms, (lookups, terms, lookups / terms)
    _answers(t, xs)


def test_n_100_answers_in_well_under_a_few_seconds():
    # 0.31 s before the fix and 0.25 s after (minimum of five, load 4
    # on 8 cores); legacy 0.03 s.  The bound is for a loaded test box.
    t, xs, ys = _store(100)
    start = time.perf_counter()
    _unify(t, xs, ys)
    elapsed = time.perf_counter() - start
    _answers(t, xs)
    assert elapsed < 3.0, elapsed
