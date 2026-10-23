"""A number unifies only with a number of its own KIND (ISO 7.3): ``1 = 1.0``
fails, on every surface and at every site that unifies.

Operator ruling 2026-10-23, closing
todo/done/iso-unify-conflates-int-and-float-2026-09-09.md (and its tabling
half, todo/done/a01-d001-tabling-half-2026-09-09.md).  Before it,
``clausal.logic.variables.unify`` fell back to Python ``==`` for two
non-container ground terms, so ``1 = 1.0``, ``f(1) = f(1.0)``, ``X = 1,
X = 1.0``, ``p(1.0)`` against a fact ``p(1)``, ``retract(q(1.0))`` of
``q(1)``, and the seam's ``1 in [1.0]`` all succeeded, and ``dif(X, 1.0),
X = 1`` failed.  The Scryer oracle half of this matrix is
``tests/iso/test_int_float_unify_scryer.py``.

The rule is the one ``'=='``/2 and ``compare/3`` already held (every numeric
type its own kind, a Decimal keeping its scale), now shared through
``clausal.logic.number_kinds`` by the unifier (C), ``structural_eq``, the
tabling variant keys (Python and C twins), setof/3's dedup and the constant
list membership set.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from clausal._suffixes import (
    CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX as PL, SEAM_SUFFIX as SEAM,
)

CLAUSAL = CLAUSAL_PROLOG_SUFFIXES[0]
from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref, unify

# ── the programs: one ISO text for .pl and .clausal, one seam text ──────────

ISO_SRC = """\
:- use_module(library(clpz)).
:- dynamic(q/1).
:- table(tp/1).
p(1).
r(1). r(1.0). r(2). r(3). r(4). r(5).
tp(1). tp(1.0).
t(1) :- 1 = 1.0.
t(2) :- f(1) = f(1.0).
t(3) :- X = 1, X = 1.0.
t(4) :- [1] = [1.0].
t(5) :- p(1.0).
t(6) :- dif(X, 1.0), X = 1.
t(7) :- assertz(q(1)), retract(q(1.0)).
t(8) :- X #= 1, X = 1.0.
t(9) :- 1 \\= 1.0.
t(10) :- copy_term(f(1), f(1.0)).
t(11) :- 1 = 1.
t(12) :- 1.0 = 1.0.
t(13) :- X = 1.0, X = 1.0.
t(14) :- assertz(q(2)), retract(q(2)).
t(15) :- memberchk(1, [1.0, 1]).
t(16) :- memberchk(1.0, [1]).
t(17) :- setof(X, member(X, [1, 1.0, 2]), [1.0, 1, 2]).
t(18) :- dif(X, 1.0), X = 1.0.
t(19) :- X = f(1), X = f(1.0).
"""

SEAM_SRC = """\
-module(_hN, [t(N), p(X), r(X), tp(X)])
-private([f(X), q(X)])
-dynamic(q/1)
-table(tp/1)
p(1),
r(1),
r(1.0),
r(2),
r(3),
r(4),
r(5),
tp(1),
tp(1.0),
t(1) <- (1 is 1.0)
t(2) <- (f(1) is f(1.0))
t(3) <- (X is 1, X is 1.0)
t(4) <- ([1] is [1.0])
t(5) <- p(1.0)
t(6) <- (dif(X, 1.0), X is 1)
t(7) <- (assertz(q(1)), retract(q(1.0)))
t(8) <- (X == 1, X is 1.0)
t(9) <- (1 in [1.0, 2.0])
t(10) <- (1.0 in [1, 2])
t(11) <- (1 is 1)
t(12) <- (1.0 is 1.0)
t(13) <- (X is 1.0, X is 1.0)
t(14) <- (assertz(q(2)), retract(q(2)))
t(15) <- (1 in [1.0, 1])
t(16) <- (2 in [1, 2.0, 3])
t(17) <- (2.0 in [1, 2.0, 3])
t(18) <- (dif(X, 1.0), X is 1.0)
t(19) <- (X is f(1), X is f(1.0))
"""

# t/1 cases and their answers: the ISO text and the seam text number the
# shared cases alike (1-8, 11-14, 18, 19); 9, 10 and 15-17 differ per text.
ISO_EXPECT = {
    1: False, 2: False, 3: False, 4: False, 5: False,
    6: True,            # dif(X, 1.0), X = 1: 1 and 1.0 can never unify
    7: False,           # retract(q(1.0)) does not match the fact q(1)
    8: False,           # X #= 1 binds 1; 1 = 1.0 fails
    9: True,            # 1 \= 1.0
    10: False,          # copy_term(f(1), f(1.0))
    11: True, 12: True, 13: True, 14: True,
    15: True,           # memberchk(1, [1.0, 1]): the second element
    16: False,          # memberchk(1.0, [1])
    17: True,           # setof keeps 1.0 and 1 apart, float first
    18: False,          # dif(X, 1.0), X = 1.0
    19: False,
}
SEAM_EXPECT = {
    1: False, 2: False, 3: False, 4: False, 5: False,
    6: True, 7: False, 8: False,
    9: False,           # 1 in [1.0, 2.0]: the constant-list set keys by kind
    10: False,          # 1.0 in [1, 2]
    11: True, 12: True, 13: True, 14: True,
    15: True,           # 1 in [1.0, 1]: the second element
    16: False, 17: True,
    18: False, 19: False,
}


@pytest.fixture(scope="module")
def programs(tmp_path_factory):
    d = tmp_path_factory.mktemp("int_float")
    mods = {}
    for suffix, src in ((PL, ISO_SRC), (CLAUSAL, ISO_SRC), (SEAM, SEAM_SRC)):
        name = f"_int_float_{suffix.lstrip('.')}"
        path = d / f"{name}{suffix}"
        path.write_text(src.replace("_hN", name))
        mods[suffix] = _load_module(name, str(path))
    return mods


def _count(goal, mod) -> int:
    return sum(1 for _ in solve(goal, mod, Trail()))


def _answers(goal, var, mod) -> list:
    return [deref(var) for _ in solve(goal, mod, Trail())]


# ── the three surfaces ────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", sorted(ISO_EXPECT))
@pytest.mark.parametrize("suffix", [PL, CLAUSAL])
def test_iso_text(programs, suffix, n):
    assert _count(("t", n), programs[suffix]) == int(ISO_EXPECT[n]), \
        f"t({n}) on {suffix}: {ISO_SRC.splitlines()[6 + n]}"


@pytest.mark.parametrize("n", sorted(SEAM_EXPECT))
def test_seam_text(programs, n):
    assert _count(("t", n), programs[SEAM]) == int(SEAM_EXPECT[n]), \
        f"t({n}) on the seam: {SEAM_SRC.splitlines()[12 + n]}"


@pytest.mark.parametrize("suffix", [PL, CLAUSAL, SEAM])
class TestEverySurface:
    def test_first_argument_index_keeps_p1_and_p1_0_apart(self, programs, suffix):
        """``r/1`` has six clauses, past the first-argument index threshold:
        ``r(1)`` and ``r(1.0)`` are two clauses in one hash bucket (Python
        hashes ``1`` and ``1.0`` alike), and each caller reaches only its
        own."""
        mod = programs[suffix]
        assert _count(("r", 1), mod) == 1
        assert _count(("r", 1.0), mod) == 1
        v = Var()
        got = _answers(("r", v), v, mod)
        assert got == [1, 1.0, 2, 3, 4, 5]
        assert [type(x) for x in got[:2]] == [int, float]

    def test_tabled_tp1_and_tp1_0_are_two_answers(self, programs, suffix):
        """The variant keys of ``tp(1)`` and ``tp(1.0)`` differ, and so do
        the two answers of ``tp(X)``."""
        mod = programs[suffix]
        assert _count(("tp", 1), mod) == 1
        assert _count(("tp", 1.0), mod) == 1
        v = Var()
        got = _answers(("tp", v), v, mod)
        assert sorted(map(repr, got)) == ["1", "1.0"]

    def test_the_fact_p1_does_not_answer_p1_0(self, programs, suffix):
        mod = programs[suffix]
        assert _count(("p", 1), mod) == 1
        assert _count(("p", 1.0), mod) == 0
        v = Var()
        assert _answers(("p", v), v, mod) == [1]


# ── the engine API: the unifier and its twins ────────────────────────────────

UNIFY_MATRIX = [
    # (a, b, unifies)
    (1, 1.0, False),
    (1.0, 1, False),
    (1, 1, True),
    (1.0, 1.0, True),
    (0.0, -0.0, True),                      # one float kind, equal value
    (1, Decimal("1"), False),               # a Decimal is its own kind
    (1.0, Decimal("1.0"), False),
    (Decimal("1.0"), Decimal("1.0"), True),
    (Decimal("1.0"), Decimal("1.00"), False),   # scale is part of the term
    (Decimal("1E+1"), Decimal("10"), False),
    (Decimal("NaN"), Decimal("NaN"), False),
    (Fraction(1, 2), 0.5, False),           # and so is a Fraction
    (Fraction(1, 2), Fraction(1, 2), True),
    (2, Fraction(2, 1), False),
    (1, complex(1), False),
    (complex(1), complex(1), True),
    (1, True, False),                       # a truth value is an ATOM (D35)
    (0, False, False),
    (True, "true", True),
    (1, "1", False),
    (("f", 1), ("f", 1.0), False),
    ([1], [1.0], False),
    ([1, 2], [1, 2], True),
]


@pytest.mark.parametrize("a, b, expected", UNIFY_MATRIX,
                         ids=[f"{a!r}={b!r}" for a, b, _ in UNIFY_MATRIX])
def test_unify_matrix(a, b, expected):
    assert bool(unify(a, b, Trail())) is expected


def test_a_bound_variable_keeps_its_kind():
    t = Trail()
    x = Var()
    assert unify(x, 1, t)
    assert not unify(x, 1.0, t)
    assert unify(x, 1, t)
    y = Var()
    assert unify(y, Decimal("2.50"), t)
    assert not unify(y, Decimal("2.5"), t)
    assert unify(y, Decimal("2.50"), t)


def test_unify_with_occurs_check_agrees():
    from clausal.logic.variables import unify_with_occurs_check
    t = Trail()
    assert not unify_with_occurs_check(1, 1.0, t)
    assert not unify_with_occurs_check(("f", 1), ("f", 1.0), t)
    assert unify_with_occurs_check(("f", 1), ("f", 1), t)


def test_structural_eq_agrees_with_unify():
    from clausal.logic.constraints import structural_eq
    for a, b, expected in UNIFY_MATRIX:
        if isinstance(a, (list, tuple)):
            continue                    # the general path IS unify
        assert structural_eq(a, b) is expected, (a, b)


def test_dif_sees_two_terms():
    from clausal.logic.constraints import dif
    t = Trail()
    x = Var()
    assert dif(x, 1.0, t)
    assert unify(x, 1, t)
    t2 = Trail()
    y = Var()
    assert dif(y, 1.0, t2)
    assert not unify(y, 1.0, t2)
    assert not dif(1, 1, Trail())
    assert dif(1, 1.0, Trail())


def test_tabling_variant_keys_count_the_terms_the_unifier_counts():
    """Python and C normalisers in lock-step (P52): ``1``, ``1.0``,
    ``Decimal('1')``, ``Decimal('1.0')``, ``Decimal('1.00')`` and
    ``Fraction(1)`` are six keys, in both."""
    from clausal.logic import tabling
    from clausal.logic._tabling_core import _normalize_for_key as c_key
    py_key = tabling._normalize_for_key_py
    terms = [1, 1.0, Decimal("1"), Decimal("1.0"), Decimal("1.00"),
             Fraction(1, 1), Fraction(1, 2), Decimal("NaN"),
             [1, Decimal("1.0")], ("f", Decimal("2.5"), Fraction(1, 3))]
    keys_py = [py_key(x) for x in terms]
    keys_c = [c_key(x) for x in terms]
    assert keys_py == keys_c
    assert [hash(k) for k in keys_py] == [hash(k) for k in keys_c]
    assert len(set(keys_py[:6])) == 6
    assert tabling._normalize_for_key is c_key or tabling._normalize_for_key is py_key


def test_constant_list_set_keys_by_kind():
    from clausal.logic.runtime.const_set import _const_set
    s = _const_set([1, 2.0, "a", None])
    assert (int, 1) in s and (float, 2.0) in s
    assert (float, 1.0) not in s and (int, 2) not in s
    assert _const_set([1, 1.0]) == frozenset({(int, 1), (float, 1.0)})
    assert _const_set([1, 1]) is False      # a true duplicate is still refused
    assert _const_set([True, "x"]) == frozenset({"true", "x"})


def test_setof_keeps_equal_valued_numbers_of_different_kinds():
    from clausal.logic.compiler.globals_env import _set_of_sort_dedup
    assert _set_of_sort_dedup([1, 1.0, 2, 1, 1.0]) == [1.0, 1, 2]
    assert _set_of_sort_dedup([("f", 1), ("f", 1.0), ("f", 1)]) == [("f", 1.0), ("f", 1)]
    assert _set_of_sort_dedup([Decimal("1.0"), Decimal("1.00"), Decimal("1.0")]) \
        == [Decimal("1.0"), Decimal("1.00")] or \
        _set_of_sort_dedup([Decimal("1.0"), Decimal("1.00"), Decimal("1.0")]) \
        == [Decimal("1.00"), Decimal("1.0")]


def test_the_census_counts_the_refused_pairs():
    """``unify_census`` keeps measuring the population the ruling changed:
    cross-kind pairs of equal value, now refused."""
    from clausal.logic.variables._variables import (
        unify_census, unify_census_start, unify_census_stop,
    )
    unify_census_start()
    try:
        t = Trail()
        assert not unify(1, 1.0, t)
        assert not unify(Decimal("1"), 1, t)
        assert not unify(1, 2.0, t)         # not equal: not a conflation
        assert unify(1, 1, t)
        report = unify_census()
    finally:
        unify_census_stop()
    assert report["conflations"] == 2
    assert report["by_type_pair"] == {"int/float": 1, "int/decimal.Decimal": 1}   # keyed by tp_name


def test_decimal_head_literal_keeps_its_scale(tmp_path):
    """An opaque head literal (``Decimal``) is matched by ``$unify`` alone,
    with no same-type ``==`` short-circuit: ``Decimal.__eq__`` ignores
    scale, the term does not."""
    from clausal.logic.solve import call
    path = tmp_path / f"_dec{SEAM}"
    path.write_text("-module(_dec, [amount(X)])\n-dynamic(amount/1)\n")
    mod = _load_module("_dec", str(path))
    for _ in call("assertz", ("amount", Decimal("2.50")), module=mod):
        break
    else:
        pytest.fail("assertz failed")
    assert _count(("amount", Decimal("2.50")), mod) == 1
    assert _count(("amount", Decimal("2.5")), mod) == 0
    assert _count(("amount", 2.5), mod) == 0
    v = Var()
    assert _answers(("amount", v), v, mod) == [Decimal("2.50")]
