"""``#(Name)`` is ``constant(Name)`` (operator ruling 2026-11-04, "Declared
wins"): with an ATOM argument, ``#`` folds at compile time to the declared
(or imported) constant's value, units and all, anywhere the native front
end folds ``constant/1``.  An undeclared name is a load error with
constant/1's own words, spelled ``#(Name)``.  A module that loads
library(clpq) has clp(q,r) 1.3.3's ``p``, ``pi``, ``e`` and ``zero``
declared for ``constant/1`` and ``#/1`` (follow-up ruling 2026-11-04, "let
CLPQ declare them too"), its own declaration winning; the atoms stay
atoms.  CLP(Z)'s ``#X`` / ``#3`` markers (a variable or an
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


@pytest.mark.parametrize("ref", ["#(pi)", "constant(e)", "#(zero)", "#p"])
def test_without_clpq_its_names_are_undeclared(native, ref):
    """library(clpq) declares p/pi/e/zero; a module that does not load it
    has nothing declaring them (clpz's prefix ``#`` reads ``#p``)."""
    name = ref.strip("#()").replace("constant(", "")
    err = _refusal(native, "hc_noclpq", f"""\
        :- use_module(library(clpz)).
        q(X) :- X is {ref}.
    """)
    assert err.lineno == 2, err
    assert f"nothing declares `{name}`" in str(err), err


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


# ── library(clpq) declares p, pi, e, zero: under BOTH solvers ───────────────

_CLPQ_PROBE = r'''
import importlib, sys, textwrap
from fractions import Fraction
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
import clausal.logic.clpq as clpq
assert clpq.SOLVER == sys.argv[2], clpq.SOLVER
sys.path.insert(0, sys.argv[1])
with open(f"{sys.argv[1]}/hcq_lib.clausal", "w") as f:
    f.write(textwrap.dedent("""\
        :- use_module(library(clpq)).
        :- constant_value(half_turn, #(pi)).
        two_pi(X) :- {X = 2 * #(pi)}.
        two_pi_literal(X) :- {X = 2 * 3.141592653589793}.
        pi_alone(X) :- {X = #(pi)}.
        pi_literal(X) :- {X = 3.141592653589793}.
        p_alone(X) :- {X = #(p)}.
        e_is(X) :- X is #(e).
        pi_constant(X) :- X is constant(pi).
        zero(X) :- {X = 1 + #(zero)}.
        zero_data(X) :- X = #(zero).
        half(X) :- X = constant(half_turn).
        late(E) :- T =.. ['#', pi], catch({_ = T}, error(E, _), true).
    """))
m = importlib.import_module("hcq_lib")
out = {}
for p in ("two_pi", "two_pi_literal", "pi_alone", "pi_literal", "p_alone",
          "e_is", "pi_constant", "zero", "zero_data", "half", "late"):
    v = Var()
    out[p] = [walk(deref(v)) for _ in call(p, v, module=m)]
out["pi_global"] = vars(m).get("pi", "<unbound>")
print(repr(out))
'''


def _under(solver, tmp_path):
    env = dict(os.environ, CLAUSAL_CLPQ=solver, PYTHONPATH=str(ROOT))
    env.pop("CLAUSAL_PL_FRONTEND", None)
    r = subprocess.run([sys.executable, "-c", _CLPQ_PROBE, str(tmp_path),
                        solver], cwd=tmp_path, env=env, capture_output=True,
                       text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    return eval(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("solver", ["legacy", "holzbaur"])
def test_clpq_declares_p_pi_e_zero(solver, tmp_path):
    out = _under(solver, tmp_path)
    # A folded #(pi) meets the solver as the float literal does.
    assert out["two_pi"] == out["two_pi_literal"], out
    assert out["pi_alone"] == out["pi_literal"] == out["p_alone"], out
    [two_pi] = out["two_pi"]
    [pi] = out["pi_alone"]
    assert type(two_pi) is Fraction and two_pi == 2 * pi, out
    if solver == "holzbaur":
        # The port reads a float through 1.3.3's float_rat, so the folded
        # value is exactly what its own #(pi) gave (normal_form_number).
        from clausal.logic.clpq import normal_form as nf
        [m] = nf.normal_form(("#", "pi"))
        assert pi == Fraction(*m.coefficient) == Fraction(245850922, 78256779)
    else:
        # The legacy solver takes a float's exact binary value.
        assert pi == Fraction(3.141592653589793)
    assert out["e_is"] == [2.718281828459045], out
    assert out["pi_constant"] == [3.141592653589793], out
    assert out["zero"] == [1] and out["zero_data"] == [0], out
    assert out["half"] == [3.141592653589793], out
    # A cell built at run time is still no constant reference.
    assert out["late"] == [("type_error", "evaluable", ("/", "#", 1))], out
    # No module global: the atom pi is not the constant.
    assert out["pi_global"] != 3.141592653589793, out


def test_the_library_values_are_the_ports_monash_constants():
    from clausal.tools.iso_l3 import CLPQ_LIBRARY_CONSTANTS
    from clausal.logic.clpq import normal_form as nf
    for name, value in CLPQ_LIBRARY_CONSTANTS.items():
        assert nf.monash_constant(name) == value or name == "zero", name
        assert ([(m.coefficient, m.powers) for m in nf.normal_form(("#", name))]
                == [(m.coefficient, m.powers) for m in nf.normal_form(value)]
                ), name


def test_the_atoms_stay_atoms_with_clpq_loaded(native):
    src = """\
        :- use_module(library(clpq)).
        names(L) :- L = [p, pi, e, zero].
        f(pi).
        g(X) :- X = e.
    """
    for suffix in (".clausal", ".pl"):
        mod = _load(native, "hc_atoms" + suffix[1:], src, suffix=suffix)
        assert _all(mod, "names", V) == [(["p", "pi", "e", "zero"],)]
        assert _all(mod, "f", V) == [("pi",)]
        assert _all(mod, "g", V) == [("e",)]
        assert vars(mod).get("e", "e") == "e"
        assert vars(mod).get("pi", "pi") == "pi"
    seam = native.load("hc_atoms_seam", textwrap.dedent("""\
        -private([pi, e])
        f(pi),
        g(X) <- (X is e)
    """), suffix=".seam", frontend=None)
    assert _all(seam, "f", V) == [("pi",)]
    assert _all(seam, "g", V) == [("e",)]


def test_a_declared_or_imported_name_wins_over_clpqs(native):
    _load(native, "hc_pi_prov", """\
        :- module(hc_pi_prov, [e/0]).
        :- constant_value(e, 10).
        :- end_module(hc_pi_prov).
    """)
    mod = _load(native, "hc_pi_imp", """\
        :- use_module(library(clpq)).
        :- use_module(hc_pi_prov, [e]).
        q(X) :- {X = 2 * #(e)}.
        i(X) :- X is constant(e).
    """)
    assert _all(mod, "q", V) == [(20,)]
    assert _all(mod, "i", V) == [(10,)]


# ── a later declaration of a name used above as clpq's constant ─────────────


@pytest.mark.parametrize("decl", [
    ":- constant_value(pi, 3).",
    ":- constant_number_units(pi, 3, euro).",
])
def test_declaring_a_clpq_name_after_its_use_is_refused(native, decl):
    """Above it, ``#(pi)`` folded to library(clpq)'s pi; below, it would be
    the module's: one name, two values in one file.  Refused at the
    declaration, naming the first use's line."""
    err = _refusal(native, "hc_late_decl", f"""\
        :- use_module(library(clpq)).
        :- use_module(european_union, [euro]).
        q(X) :- {{X = 2 * #(pi)}}.
        {decl}
        r(X) :- X is constant(pi).
    """)
    assert err.lineno == 4, err
    head = decl[3:decl.index(",")]
    assert (f"{head}, …): `pi` is already used above as library(clpq)'s "
            f"constant (line 3); declare it before its first use") in str(err), err


def test_a_use_in_a_declared_value_counts(native):
    err = _refusal(native, "hc_late_val", """\
        :- use_module(library(clpq)).
        :- constant_value(half_turn, #(e)).
        :- constant_value(e, 3).
    """)
    assert err.lineno == 3, err
    assert "`e` is already used above as library(clpq)'s constant (line 2)" \
        in str(err), err


def test_importing_a_clpq_name_after_its_use_is_refused(native):
    _load(native, "hc_e_prov", """\
        :- module(hc_e_prov, [e/0]).
        :- constant_value(e, 10).
        :- end_module(hc_e_prov).
    """)
    err = _refusal(native, "hc_late_imp", """\
        :- use_module(library(clpq)).
        q(X) :- X is #(e) + 1.
        :- use_module(hc_e_prov, [e]).
    """)
    assert err.lineno == 3, err
    assert ("use_module(hc_e_prov, …): `e` is already used above as "
            "library(clpq)'s constant (line 2)") in str(err), err


def test_declaring_before_the_first_use_is_fine(native):
    mod = _load(native, "hc_early_decl", """\
        :- use_module(library(clpq)).
        q(X) :- {X = 2 * #(e)}.
        :- constant_value(pi, 3).
        r(X) :- X is #(pi).
    """)
    assert _all(mod, "r", V) == [(3,)]
    assert len(_all(mod, "q", V)) == 1
