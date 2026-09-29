"""Slice 6: constants, units and dicts on the native ``.pl`` front end (plan
native-iso-reader-step2 §4 Slice 6; rulings D6-D8, 2026-09-30).

* D8: ``:- constant_value(Name, Value).`` verbatim; the goal
  ``constant_value(Name, V)`` reads it program-wide.
* D7: units come ONLY from the declaration family
  (``constant_number_units/3``, ``constant_number_currency/3``, the
  ``constants_number_*`` tables); ``5*euro`` is an ordinary ISO term.
* ``constant(Name)`` is TERM EXPANSION: folded at compile time exactly as the
  seam folds it (a thunk over the declared module global), never a runtime
  evaluable.  An undeclared name is a load error naming the ``.pl`` line.
* D6: dicts are predicate forms only; ``get_strict/3`` is the strict read
  (``existence_error(dict_key, K)`` on a miss, as the seam subscript).

Each ``.pl`` module is paired with a ``.seam`` twin that must give the SAME
all-answers, type-strict.  Every native load clears ``__pycache__`` and
asserts the native loader ran over a non-zero population (``native``).
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk

V = object()   # a fresh variable in a call pattern


def _all(mod, name, *args):
    real = [Var() if a is V else a for a in args]
    return [tuple(walk(deref(a)) for a in real)
            for _ in call(name, *real, module=mod)]


def _strict(t):
    """Tells 1 from 1.0 and from True, a list from a tuple, and a quantity's
    magnitude KIND (``Decimal('100')`` from ``100``) by its repr."""
    if isinstance(t, (list, tuple)):
        return (type(t).__name__, tuple(_strict(x) for x in t))
    return (type(t).__name__, repr(t))


def _twin_ab(native, pl_name, pl_src, seam_name, seam_src, calls):
    nat = native.load(pl_name, textwrap.dedent(pl_src))
    twin = native.load(seam_name, textwrap.dedent(seam_src), suffix=".seam",
                       frontend=None)
    n_ans = 0
    for name, *args in calls:
        a, b = _all(nat, name, *args), _all(twin, name, *args)
        assert _strict(a) == _strict(b), (name, args, a, b)
        n_ans += len(a)
    # A comparison over no answers proves nothing.
    assert n_ans >= len(calls), n_ans
    return nat, twin


def _refusal(native, name, text):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, textwrap.dedent(text))
    assert name not in sys.modules
    return ei.value


# ── exit 1: constant_value/2 ─────────────────────────────────────────────────

S6C_PL = """\
    :- constant_value(max_retries, 3).
    :- constant_value(greeting, hello).
    :- constant_value(limits, [1, 2, 3]).

    retries(N) :- constant_value(max_retries, N).
    next_try(X) :- X is constant(max_retries) + 1.
    too_many(N) :- N > constant(max_retries).
    lim(constant(max_retries)).
    word(W) :- W = constant(greeting).
    lims(L) :- L = constant(limits).
"""

S6C_SEAM = """\
    -constant_value(max_retries, 3)
    -constant_value(greeting, 'hello')
    -constant_value(limits, [1, 2, 3])

    retries(N) <- constant_value('max_retries', N)
    next_try(X) <- (X == constant(max_retries) + 1)
    too_many(N) <- (N > constant(max_retries))
    lim(constant(max_retries)),
    word(W) <- (W is constant(greeting))
    lims(L) <- (L is constant(limits))
"""


def test_constant_value_declaration_goal_and_fold(native):
    nat, _ = _twin_ab(native, "s6c", S6C_PL, "s6c_twin", S6C_SEAM, [
        ("retries", V), ("next_try", V), ("too_many", 4), ("too_many", 3),
        ("lim", V), ("lim", 3), ("word", V), ("lims", V)])
    # Program-wide (Triska convention): the twin declares it too.
    assert set(_all(nat, "retries", V)) == {(3,)}
    assert _all(nat, "next_try", V) == [(4,)]
    assert _all(nat, "too_many", 4) == [(4,)]
    assert _all(nat, "too_many", 3) == []
    assert _all(nat, "lim", V) == [(3,)]
    assert _all(nat, "word", V) == [("hello",)]
    assert _all(nat, "lims", V) == [([1, 2, 3],)]


def test_the_fold_is_compile_time_not_a_runtime_evaluable(native):
    """``constant/1`` is no evaluable functor: the reference is replaced
    where the clause is compiled, so a ``constant(N)`` built at RUN time is
    just a term -- Scryer's ``type_error(evaluable, constant/1)``."""
    mod = native.load("s6fold", textwrap.dedent("""\
        :- constant_value(max_retries, 3).
        late(E) :- T =.. [constant, max_retries],
                   catch(_ is T, error(E, _), true).
    """))
    [(err,)] = _all(mod, "late", V)
    assert err == ("type_error", "evaluable", ("/", "constant", 1)), err


# ── exit 2: units ────────────────────────────────────────────────────────────

S6U_PL = """\
    :- use_module(european_union, [euro, eur_cent]).
    :- constant_number_units(max_fine, 5000, euro).
    :- constant_number_units(one_euro, 1, euro).
    :- constant_number_units(small_fine, 5000, eur_cent).
    :- constant_number_currency(fee, "292.00", euro).

    hundred(Q) :- Q is 100 * constant(one_euro).
    over(N, Q) :- Q is N * constant(one_euro), Q > constant(max_fine).
    at_most(N) :- Q is N * constant(one_euro), Q =< constant(max_fine).
    declared(N, U) :- constant_number_units(max_fine, N, U).
    declared_small(N, U) :- constant_number_units(small_fine, N, U).
    declared_fee(N, U) :- constant_number_units(fee, N, U).
    value(V) :- constant_value(max_fine, V).
    value_small(V) :- constant_value(small_fine, V).
    fee_value(V) :- V = constant(fee).
    mine(C) :- constant_number_units(C, _, _).
"""

S6U_SEAM = """\
    -import_from(european_union, [euro, eur_cent])
    -constant_number_units(max_fine, 5000, euro)
    -constant_number_units(one_euro, 1, euro)
    -constant_number_units(small_fine, 5000, eur_cent)
    -constant_number_currency(fee, "292.00", euro)

    hundred(Q) <- (Q == 100 * constant(one_euro))
    over(N, Q) <- (Q == N * constant(one_euro), Q > constant(max_fine))
    at_most(N) <- (Q == N * constant(one_euro), Q <= constant(max_fine))
    declared(N, U) <- constant_number_units(max_fine, N, U)
    declared_small(N, U) <- constant_number_units(small_fine, N, U)
    declared_fee(N, U) <- constant_number_units(fee, N, U)
    value(V) <- constant_value('max_fine', V)
    value_small(V) <- constant_value('small_fine', V)
    fee_value(V) <- (V is constant(fee))
    mine(C) <- constant_number_units(C, _, _)
"""


def test_units_declarations_fold_compare_and_reflect(native):
    from decimal import Decimal
    from clausal.terms import Quantity
    nat, _ = _twin_ab(native, "s6u", S6U_PL, "s6u_twin", S6U_SEAM, [
        ("hundred", V), ("over", 6000, V), ("over", 4000, V),
        ("at_most", 5000), ("at_most", 5001), ("declared", V, V),
        ("declared_small", V, V), ("declared_fee", V, V), ("value", V),
        ("value_small", V), ("fee_value", V), ("mine", V)])
    [(q,)] = _all(nat, "hundred", V)
    assert isinstance(q, Quantity) and repr(q) == repr(
        Quantity(Decimal("100"), {"euro": 1})), repr(q)
    assert len(_all(nat, "over", 6000, V)) == 1
    assert _all(nat, "over", 4000, V) == []
    assert _all(nat, "at_most", 5000) == [(5000,)]
    assert _all(nat, "at_most", 5001) == []
    assert _all(nat, "declared", V, V) == [(5000, "euro")]
    # A scaled unit stays as declared: 5000 cent is not rescaled to 50.
    assert _all(nat, "declared_small", V, V) == [(5000, "eur_cent")]
    [(dn, du)] = _all(nat, "declared_fee", V, V)
    assert du == "euro" and str(dn) == "292.00"
    # constant_value/2 is program-wide (the twin answers too) and gives
    # the NORMALISED value.
    assert {repr(v) for (v,) in _all(nat, "value_small", V)} == {
        repr(Quantity(Decimal("50.00"), {"euro": 1}))}
    assert sorted(c for (c,) in _all(nat, "mine", V)) == [
        "fee", "max_fine", "one_euro", "small_fine"]


def test_a_units_table_directive_defines_its_facts(native):
    _twin_ab(native, "s6t", """\
        :- use_module(european_union, [euro]).
        :- constants_number_currency(snap_max/2, [[1, 29200], (2, "536.00")],
                                     euro, money_at(2)).
        :- constants_number_units(bands/3, [[low, 1, 10], [high, 2, 20]],
                                  euro, number_at(3)).
    """, "s6t_twin", """\
        -import_from(european_union, [euro])
        -private([low, high])
        -constants_number_currency(snap_max/2, [(1, 29200), (2, "536.00")], euro, money_at(2))
        -constants_number_units(bands/3, [(low, 1, 10), (high, 2, 20)], euro, number_at(3))
    """, [("snap_max", V, V), ("snap_max", 2, V), ("bands", V, V, V)])


def test_a_bare_unit_product_is_an_ordinary_iso_term(native):
    """D7: ``5*euro`` has no unit meaning in ``.pl``, even with the unit
    imported: it is the term ``'*'(5, euro)``, and ``euro`` is no
    evaluable (Scryer's ``type_error(evaluable, euro/0)``)."""
    mod = native.load("s6term", textwrap.dedent("""\
        :- use_module(european_union, [euro]).
        t(X) :- X = 5*euro.
        e(E) :- catch(_ is 5*euro, error(E, _), true).
    """))
    assert _all(mod, "t", V) == [(("*", 5, "euro"),)]
    assert _all(mod, "e", V) == [(("type_error", "evaluable",
                                   ("/", "euro", 0)),)]


def test_a_python_modules_bare_import_binds_the_value_not_an_atom(native):
    """``use_module(european_union, [euro])``: european_union is a Python
    module, so the bare name imports its VALUE (as the seam's
    ``-import_from`` does), and no D11 bare-atom warning is raised."""
    import warnings
    from clausal.lint_warnings import ClausalBareAtomImportWarning
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        mod = native.load("s6imp", textwrap.dedent("""\
            :- use_module(european_union, [euro]).
            :- constant_number_units(one_eur, 1, euro).
            one(Q) :- Q = constant(one_eur).
        """))
    assert not [w for w in got
                if issubclass(w.category, ClausalBareAtomImportWarning)]
    [(q,)] = _all(mod, "one", V)
    assert "euro" in repr(q)


# ── {C}: CLP(Q) with a folded constant (turns on when {C} lowers) ───────────


def _curly_supported(native) -> bool:
    try:
        mod = native.load("s6curly_probe", "p(X) :- {X = 2*3}.\n")
    except SyntaxError:
        return False
    try:
        return _all(mod, "p", V) == [(6,)]
    except Exception:  # noqa: BLE001 -- any failure: {C} not there yet
        return False


def test_clp_goal_takes_a_folded_constant(native):
    if not _curly_supported(native):
        pytest.skip("the {C} CLP(Q) goal does not lower natively yet "
                    "(native ISO reader slice 5)")
    _twin_ab(native, "s6q", """\
        :- use_module(european_union, [euro]).
        :- constant_number_units(one_euro, 1, euro).
        :- constant_value(rate, 3).
        q(Q) :- {Q = 100 * constant(one_euro)}.
        r(X) :- {X = 2 * constant(rate)}.
    """, "s6q_twin", """\
        -import_from(european_union, [euro])
        -constant_number_units(one_euro, 1, euro)
        -constant_value(rate, 3)
        q(Q) <- {Q == 100 * constant(one_euro)}
        r(X) <- {X == 2 * constant(rate)}
    """, [("q", V), ("r", V)])


# ── exit 3: refusals, each naming the .pl line ───────────────────────────────


def test_an_undeclared_constant_is_a_load_error_naming_the_line(native):
    err = _refusal(native, "s6undecl", """\
        p(1).
        q(X) :- X is constant(foo) + 1.
    """)
    assert err.lineno == 2 and "nothing declares `foo`" in str(err), err


def test_a_constant_declared_below_its_use_is_refused(native):
    err = _refusal(native, "s6below", """\
        q(X) :- X = constant(later).
        :- constant_value(later, 1).
    """)
    assert err.lineno == 1 and "nothing declares `later`" in str(err), err


@pytest.mark.parametrize("arg", ["compute()", "f(a)", "Y", "1"])
def test_constant_takes_a_name_never_an_expression(native, arg):
    err = _refusal(native, "s6expr", f"""\
        :- constant_value(a, 1).
        q(X) :- X is constant({arg}).
    """)
    assert err.lineno == 2 and "constant() takes the name" in str(err), err


def test_constant_number_units_of_an_undeclared_name_is_refused(native):
    err = _refusal(native, "s6cnu", """\
        :- constant_value(a, 1).
        q(N, U) :- constant_number_units(nope, N, U).
    """)
    assert err.lineno == 2 and "`nope` is not a constant" in str(err), err


@pytest.mark.parametrize("decl, needle", [
    (":- constant_number_units(a, abc, euro).", "only numbers carry units"),
    (":- constant_number_units(a, '5000', euro).", "only numbers carry units"),
    (":- constant_number_units(a, 1, 5+euro).", "not a unit expression"),
    (":- constant_value(a, X).", "must be ground"),
    (":- constant_value(A, 1).", "must be an atom"),
])
def test_a_malformed_declaration_is_refused_naming_the_line(native, decl,
                                                            needle):
    err = _refusal(native, "s6bad", f"""\
        :- use_module(european_union, [euro]).
        {decl}
    """)
    assert err.lineno == 2 and needle in str(err), err


def test_a_constant_declared_twice_is_refused(native):
    err = _refusal(native, "s6twice", """\
        :- constant_value(a, 1).
        :- constant_value(a, 2).
    """)
    assert err.lineno == 2 and "already bound" in str(err), err


# ── exit 4: dicts, predicate forms only (D6) ─────────────────────────────────

S6D_PL = """\
    mk(D) :- dict_pairs(D, [a-1, b-2]).
    hit(V) :- mk(D), get_strict(D, a, V).
    miss(E) :- mk(D), catch(get_strict(D, zz, _), error(E, _), true).
    unbound(E) :- catch(get_strict(_, a, _), error(E, _), true).
    notdict(E) :- catch(get_strict(foo, a, _), error(E, _), true).
    soft(V) :- mk(D), get(D, a, V).
    softmiss(K) :- mk(D), K = zz, \\+ get(D, K, _).
    defaulted(V) :- mk(D), get(D, zz, V, none).
    put(P) :- mk(D), dict_put(c, 3, D, D2), dict_pairs(D2, P).
    put_pairs(P) :- mk(D), dict_put_pairs([a-9, d-4], D, D2), dict_pairs(D2, P).
"""

S6D_SEAM = """\
    -private([a, b, c, d, zz, foo, none])
    mk(D) <- dict_pairs(D, [a-1, b-2])
    hit(V) <- (mk(D), get_strict(D, a, V))
    miss(E) <- (mk(D), catch(get_strict(D, zz, _), error(E, _), True))
    unbound(E) <- catch(get_strict(_, a, _), error(E, _), True)
    notdict(E) <- catch(get_strict(foo, a, _), error(E, _), True)
    soft(V) <- (mk(D), get(D, a, V))
    softmiss(K) <- (mk(D), K is zz, not get(D, K, _))
    defaulted(V) <- (mk(D), get(D, zz, V, none))
    put(P) <- (mk(D), dict_put(c, 3, D, D2), dict_pairs(D2, P))
    put_pairs(P) <- (mk(D), dict_put_pairs([a-9, d-4], D, D2), dict_pairs(D2, P))
"""


def test_dict_predicate_forms_and_get_strict_native_and_seam(native):
    nat, _ = _twin_ab(native, "s6d", S6D_PL, "s6d_twin", S6D_SEAM, [
        ("hit", V), ("miss", V), ("unbound", V), ("notdict", V),
        ("soft", V), ("softmiss", V), ("defaulted", V), ("put", V),
        ("put_pairs", V)])
    assert _all(nat, "hit", V) == [(1,)]
    assert _all(nat, "miss", V) == [(("existence_error", "dict_key", "zz"),)]
    assert _all(nat, "unbound", V) == [("instantiation_error",)]
    assert _all(nat, "notdict", V) == [(("type_error", "dict", "foo"),)]
    assert _all(nat, "soft", V) == [(1,)]
    assert _all(nat, "softmiss", V) == [("zz",)]
    assert _all(nat, "defaulted", V) == [("none",)]
    assert _all(nat, "put", V) == [([("-", "a", 1), ("-", "b", 2),
                                     ("-", "c", 3)],)]
    assert _all(nat, "put_pairs", V) == [([("-", "a", 9), ("-", "b", 2),
                                           ("-", "d", 4)],)]


def test_get_strict_raises_what_the_seam_subscript_raises(native):
    """The same error term as ``V is P[K]`` (tests/test_dict_set_compiler.py
    ``test_subscript_missing_throws``), from the quoted seam call too."""
    mod = native.load("s6sub", textwrap.dedent("""\
        -private([a, zz])
        sub(E) <- (D is {a: 1}, catch(V is D[zz], error(E, _), True))
        strict(E) <- (D is {a: 1}, catch('get_strict'(D, zz, _), error(E, _), True))
        hit(V) <- (D is {a: 1}, 'get_strict'(D, a, V))
    """), suffix=".seam", frontend=None)
    assert _all(mod, "sub", V) == _all(mod, "strict", V) == [
        (("existence_error", "dict_key", "zz"),)]
    assert _all(mod, "hit", V) == [(1,)]


def test_a_constant_named_like_a_predicate_is_refused(native):
    """The seam's check: the declaration writes a module global, which would
    overwrite the predicate of the same name (a runtime TypeError before)."""
    err = _refusal(native, "s6clash", """\
        :- constant_value(fee, 1).
        fee(V) :- V = constant(fee).
    """)
    assert err.lineno == 2 and "already bound by a predicate" in str(err), err
