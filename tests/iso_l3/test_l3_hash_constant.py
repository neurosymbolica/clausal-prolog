"""``#(Name)`` is ``constant(Name)`` (operator ruling 2026-11-04, "Declared
wins"): with an ATOM argument, ``#`` folds at compile time to the declared
(or imported) constant's value, units and all, anywhere the native front
end folds ``constant/1``.  An undeclared name is a load error with
constant/1's own words, spelled ``#(Name)`` -- except that inside a
CLP(Q) ``{}/1`` the four clp(q,r) 1.3.3 names ``p``, ``pi``, ``e`` and
``zero``, when NOT declared, are lowered exactly as before (pinned here
under both solvers).  CLP(Z)'s ``#X`` / ``#3`` markers (a variable or an
integer argument) are untouched, and a ``#(Name)`` cell built at run time
is a plain term, as a run-time ``constant(Name)`` cell is.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.terms import Quantity

V = object()   # a fresh variable in a call pattern
ROOT = pathlib.Path(__file__).resolve().parents[2]
EURO = {"euro": 1}


def _all(mod, name, *args):
    real = [Var() if a is V else a for a in args]
    return [tuple(walk(deref(a)) for a in real)
            for _ in call(name, *real, module=mod)]


def _load(native, name, text, suffix=".clausal"):
    return native.load(name, textwrap.dedent(text), suffix=suffix)


def _refusal(native, name, text, suffix=".clausal"):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, textwrap.dedent(text), suffix=suffix)
    assert name not in sys.modules
    return ei.value


# ── the fold ────────────────────────────────────────────────────────────────


def test_hash_folds_in_is_and_comparisons_like_constant(native):
    mod = _load(native, "hc_is", """\
        :- constant_value(max_retries, 3).
        next_try(X) :- X is #(max_retries) + 1.
        next_try_c(X) :- X is constant(max_retries) + 1.
        too_many(N) :- N > #(max_retries).
    """)
    assert _all(mod, "next_try", V) == [(4,)] == _all(mod, "next_try_c", V)
    assert _all(mod, "too_many", 4) == [(4,)]
    assert _all(mod, "too_many", 3) == []


def test_hash_folds_in_data_positions(native):
    mod = _load(native, "hc_data", """\
        :- constant_value(max_retries, 3).
        :- constant_value(greeting, hello).
        :- constant_value(limits, [1, 2, 3]).
        :- constant_value(retries_again, #(max_retries)).
        lim(#(max_retries)).
        word(W) :- W = f(#(greeting)).
        lims(L) :- L = [0|#(limits)].
        again(X) :- X = constant(retries_again).
        names(L) :- L = [greeting, other].
    """)
    assert _all(mod, "lim", V) == [(3,)]
    assert _all(mod, "lim", 3) == [(3,)]
    assert _all(mod, "word", V) == [(("f", "hello"),)]
    assert _all(mod, "lims", V) == [([0, 1, 2, 3],)]
    assert _all(mod, "again", V) == [(3,)]
    # A fold, not data: neither ``#`` nor the name is an atom use.
    st = mod.__loader__.l3_stats
    assert st["auto_declared"]["atoms"] == 1, st          # other
    assert "#" not in vars(mod)


def test_hash_folds_an_imported_constant(native):
    _load(native, "hc_prov", """\
        :- module(hc_prov, [rate/0]).
        :- constant_value(rate, 7).
        :- end_module(hc_prov).
    """)
    mod = _load(native, "hc_use", """\
        :- use_module(library(clpq)).
        :- use_module(hc_prov, [rate]).
        a(X) :- X is #(rate) + 1.
        q(X) :- {X = 2 * #(rate)}.
    """)
    assert _all(mod, "a", V) == [(8,)]
    assert _all(mod, "q", V) == [(14,)]


CLPQ_UNITS = """\
    :- use_module(library(clpq)).
    :- use_module(european_union, [euro]).
    :- constant_number_units(one_euro, 1, euro).
    :- constant_number_units(max_fine, 5000, euro).
    :- constant_number_units(big, 6000, euro).
    :- constant_number_units(tiny, 10, euro).

    price(Q)  :- {Q = 100 * #(one_euro)}.
    price_c(Q) :- {Q = 100 * constant(one_euro)}.
    fine(R)   :- {Q >= #(max_fine)}, Q = #(big), R = Q.
    fine_fails(R) :- {Q >= #(max_fine)}, Q = #(tiny), R = Q.
    split(N)  :- {Q = N * #(one_euro)}, Q is 300 * #(one_euro).
    half(Q)   :- {2 * Q = 3 * #(one_euro)}.
"""


def test_hash_folds_a_unit_constant_inside_clpq_braces(native):
    """docs/clpq.md's Units examples, with ``#(Name)`` for ``constant(Name)``."""
    mod = _load(native, "hc_units", CLPQ_UNITS)
    assert _all(mod, "price", V) == [(Quantity(Decimal("100"), EURO),)]
    assert _all(mod, "price", V) == _all(mod, "price_c", V)
    assert _all(mod, "fine", V) == [(Quantity(Decimal("6000"), EURO),)]
    assert _all(mod, "fine_fails", V) == []
    [(n,)] = _all(mod, "split", V)
    assert n == 300 and type(n) is int
    [(h,)] = _all(mod, "half", V)
    assert h == Quantity(Fraction(3, 2), EURO) and type(h.value) is Fraction


def test_a_declared_pi_shadows_the_clpq_constant(native):
    """Declared wins: ``#(pi)`` is the module's ``pi``, in ``{}`` and out."""
    mod = _load(native, "hc_pi", """\
        :- use_module(library(clpq)).
        :- constant_value(pi, 3).
        :- constant_value(e, 2).
        q(X) :- {X = #(pi)}.
        q2(X) :- {X = 2 * #(e)}.
        i(X) :- X is #(pi).
    """)
    assert _all(mod, "q", V) == [(3,)]
    assert _all(mod, "q2", V) == [(4,)]
    assert _all(mod, "i", V) == [(3,)]


# ── refusals ────────────────────────────────────────────────────────────────


def test_an_undeclared_hash_name_is_a_load_error_naming_the_line(native):
    err = _refusal(native, "hc_undecl", """\
        p(1).
        q(X) :- X is #(foo) + 1.
    """)
    assert err.lineno == 2, err
    assert "#(foo): nothing declares `foo`" in str(err), err


def test_an_undeclared_hash_name_in_braces_is_a_load_error(native):
    err = _refusal(native, "hc_undecl_q", """\
        :- use_module(library(clpq)).
        q(X) :- {X = #(tau)}.
    """)
    assert err.lineno == 2, err
    assert "#(tau): nothing declares `tau`" in str(err), err


def test_an_undeclared_pi_outside_braces_is_a_load_error(native):
    """The clp(q,r) names are exempt inside ``{}/1`` only."""
    err = _refusal(native, "hc_undecl_pi", """\
        q(X) :- X is #(pi).
    """)
    assert err.lineno == 1, err
    assert "#(pi): nothing declares `pi`" in str(err), err


def test_a_hash_declared_below_its_use_is_refused(native):
    err = _refusal(native, "hc_below", """\
        q(X) :- X = #(later).
        :- constant_value(later, 1).
    """)
    assert err.lineno == 1 and "nothing declares `later`" in str(err), err


def test_the_pl_surface_folds_hash_too(native):
    """The native front end is shared: a ``.pl`` folds ``#(Name)`` as it
    folds ``constant(Name)``."""
    mod = _load(native, "hc_pl", """\
        :- constant_value(k, 3).
        a(X) :- X is #(k) * 2.
    """, suffix=".pl")
    assert _all(mod, "a", V) == [(6,)]


# ── CLP(Z): the markers are untouched ───────────────────────────────────────


def test_clpz_markers_and_comparisons_are_untouched(native):
    """``#X`` / ``#3`` (a variable or an integer under ``#``) are clpz's
    markers, never a constant reference: they read and are kept as the
    ``#/1`` cells they are."""
    mod = _load(native, "hc_clpz", """\
        :- use_module(library(clpz)).
        :- constant_value(k, 3).
        z(X) :- X #= 3.
        shapes(T, U, W) :- T = (#_X #= #3), U = #(-1), W = ?(_).
        f(X) :- X #= #(k) + 1.
        g(X) :- X is #k + 1.
        bad(E) :- catch(_ #= #(3), error(E, _), true).
    """)
    assert _all(mod, "z", V) == [(3,)]
    [(t, u, w)] = _all(mod, "shapes", V, V, V)
    assert t[0] == "#=" and t[1][0] == "#" and t[2] == ("#", 3), t
    assert u == ("#", -1) and w[0] == "?", (u, w)
    assert _all(mod, "f", V) == [(4,)]
    # clpz's prefix ``#`` reads ``#k`` as ``#(k)``: the same fold.
    assert _all(mod, "g", V) == [(4,)]
    # An integer marker in a CLP(Z) goal keeps clpz's own diagnosis.
    assert _all(mod, "bad", V) == [
        (("domain_error", "clpz_expression", ("#", 3)),)]


# ── a cell built at run time is a term, as constant/1's is ──────────────────


def test_a_run_time_hash_cell_is_a_term_like_a_run_time_constant_cell(native):
    mod = _load(native, "hc_late", """\
        :- constant_value(k, 3).
        late_c(E) :- T =.. [constant, k], catch(_ is T, error(E, _), true).
        late_h(E) :- T =.. ['#', k], catch(_ is T, error(E, _), true).
        data(T) :- T =.. ['#', k].
    """)
    assert _all(mod, "late_c", V) == [
        (("type_error", "evaluable", ("/", "constant", 1)),)]
    assert _all(mod, "late_h", V) == [
        (("type_error", "evaluable", ("/", "#", 1)),)]
    assert _all(mod, "data", V) == [(("#", "k"),)]


def test_an_asserted_rule_keeps_a_run_time_hash_cell_as_data(native):
    """A ``.pl`` rule asserted at run time goes through the front end's own
    clause lowering; a ``#(Name)`` cell in it is spliced in verbatim, as a
    ``constant(Name)`` cell is -- never folded at assert time."""
    mod = _load(native, "hc_assert", """\
        :- dynamic(d1/1).
        :- dynamic(d2/1).
        :- dynamic(d3/1).
        :- constant_value(k, 3).
        a1(R) :- T =.. [constant, k],
                 catch((assertz((d1(X) :- X is T)), d1(R)), error(E, _), R = err(E)).
        a2(R) :- T =.. ['#', k],
                 catch((assertz((d2(X) :- X is T)), d2(R)), error(E, _), R = err(E)).
        a3(R) :- T =.. ['#', foo],
                 catch((assertz((d3(X) :- X = T)), d3(R)), error(E, _), R = err(E)).
    """, suffix=".pl")
    assert _all(mod, "a1", V) == [
        (("err", ("type_error", "evaluable", ("/", "constant", 1))),)]
    assert _all(mod, "a2", V) == [
        (("err", ("type_error", "evaluable", ("/", "#", 1))),)]
    assert _all(mod, "a3", V) == [(("#", "foo"),)]


# ── undeclared p/pi/e/zero inside {}: unchanged, under BOTH solvers ─────────

_HOLZBAUR_PROBE = r'''
import importlib, sys, textwrap
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.logic.clpq import normal_form as nf
import clausal.logic.clpq as clpq
assert clpq.SOLVER == sys.argv[2], clpq.SOLVER
sys.path.insert(0, sys.argv[1])
out = {}
# Written at the top of a {}/1 comparison: refused at load, as before.
for name in ("p", "pi", "e", "zero"):
    mod = "hcq_top_" + name
    with open(f"{sys.argv[1]}/{mod}.clausal", "w") as f:
        f.write(":- use_module(library(clpq)).\nq(X) :- {X = 2 * #(%s)}.\n" % name)
    try:
        importlib.import_module(mod)
        out[name] = "loaded"
    except SyntaxError as e:
        out[name] = (e.lineno, str(e))
# Under a {}/1 function, and built at run time: type_error(evaluable, #/1).
with open(f"{sys.argv[1]}/hcq_late.clausal", "w") as f:
    f.write(textwrap.dedent("""\
        :- use_module(library(clpq)).
        nested(E) :- catch({_ = sin(#(pi))}, error(E, _), true).
        late(N, E) :- T =.. ['#', N], catch({_ = T}, error(E, _), true).
    """))
m = importlib.import_module("hcq_late")
v = Var()
out["nested"] = [walk(deref(v)) for _ in call("nested", v, module=m)]
for name in ("p", "pi", "e", "zero"):
    v = Var()
    out["late_" + name] = [walk(deref(v)) for _ in call("late", name, v, module=m)]
# The port's own normal form keeps nf.pl's monash_constant/2.
out["nf"] = [nf.monash_constant(n) for n in ("p", "pi", "e", "zero", "tau")]
print(repr(out))
'''


@pytest.mark.parametrize("solver", ["legacy", "holzbaur"])
def test_undeclared_clpq_names_in_braces_are_unchanged(solver, tmp_path):
    env = dict(os.environ, CLAUSAL_CLPQ=solver, PYTHONPATH=str(ROOT))
    env.pop("CLAUSAL_PL_FRONTEND", None)
    r = subprocess.run([sys.executable, "-c", _HOLZBAUR_PROBE,
                        str(tmp_path), solver],
                       cwd=tmp_path, env=env, capture_output=True,
                       text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    out = eval(r.stdout.strip().splitlines()[-1])
    for name in ("p", "pi", "e", "zero"):
        line, message = out[name]
        assert line == 2 and (
            f":2: {{}}/1 (clpq): ('#', '{name}') is not an arithmetic "
            f"expression (numbers, variables, + - * /, abs sin cos tan "
            f"min max exp pow ^)") in message, (name, out[name])
        assert out["late_" + name] == [
            ("type_error", "evaluable", ("/", "#", 1))], out
    assert out["nested"] == [("type_error", "evaluable", ("/", "#", 1))], out
    from clausal.logic.clpq.arithmetic import ZERO
    assert out["nf"] == [3.141592653589793, 3.141592653589793,
                         2.718281828459045, ZERO, None], out
    assert ZERO == (0, 1)
