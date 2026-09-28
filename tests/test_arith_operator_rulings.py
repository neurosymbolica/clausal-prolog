"""Operator rulings of 2026-09-28: a BARE operator keeps Python's meaning.

Today's source syntax -- a ``.clausal`` or ``.seam`` file, clause bodies and
``--`` expressions alike -- is the Python-shaped (seam) syntax, and in it a
bare ``//``, ``%``, ``**`` means what it means in Python: ``-7 // 2`` is -4
and ``2 ** 3`` is the integer 8.  The QUOTED spelling (``'//'(-7, 2)``, a
cell built at runtime) follows Scryer instead; those rows, with Scryer as
the oracle, are in tests/iso/test_arith_rulings_scryer.py.

A zero divisor is ``evaluation_error(zero_divisor)`` naming the operator on
every spelling -- a logic-level error, never a raw Python ZeroDivisionError
(Q4).
"""
from __future__ import annotations

import itertools
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref

_N = itertools.count()

#: A row that has no answer (the goal fails).
FAILS = object()

#: (clause body binding X, what X is -- the error term it raises, or FAILS)
BARE_ROWS = [
    ("eval_(-7 // 2, X)", -4),               # Python floor division
    ("eval_(7 // -2, X)", -4),
    ("eval_(-7 % 2, X)", 1),                 # Python modulo
    ("eval_(2 ** 3, X)", 8),                 # Python power: an int
    ("eval_(2 ** -1, X)", 0.5),
    ("eval_(0 ** 0, X)", 1),
    ("'is'(X, -7 // 2)", -4),                # a bare node under ISO is/2
    ("'is'(X, 2 ** 3)", 8),
    ("X == -7 // 2", -4),                    # a CLP(FD) post
    ("(Y is -7, X == Y // 2)", -4),
    ("X == 2 ** 3", 8),
    # the quoted spelling beside it: Scryer
    ("eval_('//'(-7, 2), X)", -3),
    ("eval_('**'(2, 3), X)", 8.0),
    ("eval_('^'(2, 3), X)", 8),
    ("eval_('//'(-7, 2) // 2, X)", -2),      # each operator by its own spelling
    # an integral rational operand is an integer (a nested rdiv(4, 2) is 2)
    ("'is'(X, '//'(rdiv(4, 2), 1))", 2),
    ("'is'(X, '^'(2, rdiv(6, 2)))", 8),       # 8, not 8.0
    ("'is'(X, mod(rdiv(4, 2), 3))", 2),
    # Q15: / in EVALUATION is Python's when bare, Scryer's when quoted (both
    # floats for int/int); rdiv is the exact spelling; inside a CLP post
    # (==) / stays rational
    ("eval_(7 / 2, X)", 3.5),
    ("eval_(6 / 2, X)", 3.0),
    ("'is'(X, 7 / 2)", 3.5),
    ("'is'(X, '/'(6, 2))", 3.0),
    ("eval_(rdiv(7, 2) / 2, X)", Fraction(7, 4)),     # Python: Fraction / int
    ("'is'(X, '/'(rdiv(7, 2), 2))", 1.75),            # Scryer: a float
    ("'is'(X, rdiv(7, 2))", Fraction(7, 2)),
    ("'is'(X, rdiv(6, 2))", 3),
    ("'is'(X, rdiv(7, 2) + 1)", Fraction(9, 2)),
    ("eval_(decimal(15, 1) / 2, X)", Decimal("0.75")),  # Python: Decimal / int
    ("X == 7 / 2", Fraction(7, 2)),
    ("X == 6 / 2", 3),
    ("X == '/'(7, 2)", Fraction(7, 2)),
    ("(Y is 7, X == Y / 2)", Fraction(7, 2)),
    ("(Y is -7, X == '//'(Y, 2))", -3),
    ("(X == '//'(Y, 2), Y is -7)", -3),      # posted first, bound after
    ("(X == Y // 2, Y is -7)", -4),
    # Q4: zero divisors, every spelling
    ("eval_(1 // 0, X)", "error(evaluation_error(zero_divisor),(//)/2)"),
    ("eval_(1 % 0, X)", "error(evaluation_error(zero_divisor),(mod)/2)"),
    ("eval_(decimal(15, 1) % 0, X)", "error(evaluation_error(zero_divisor),(mod)/2)"),
    ("eval_(decimal(0, 1) // 0, X)", "error(evaluation_error(zero_divisor),(//)/2)"),
    ("eval_(1 / 0, X)", "error(evaluation_error(zero_divisor),(/)/2)"),
    ("eval_(0 ** -1, X)", "error(evaluation_error(zero_divisor),(**)/2)"),
    ("(Z is 0, eval_(1 // Z, X))", "error(evaluation_error(zero_divisor),(//)/2)"),
    ("(Z is 0, eval_(1 / Z, X))", "error(evaluation_error(zero_divisor),(/)/2)"),
    ("'is'(X, 1 // 0)", "error(evaluation_error(zero_divisor),(//)/2)"),
    ("'=:='(1, 1 / 0)", "error(evaluation_error(zero_divisor),(/)/2)"),
    ("'<'(1, 1 // 0)", "error(evaluation_error(zero_divisor),(//)/2)"),
    # Ruling Q14 (2026-09-28): a CLP(FD) constraint over an expression with
    # no value FAILS, as in Scryer ("(#=)/2 is a relation: failure means that
    # there are no solutions"), in EVERY goal order.  It succeeded before,
    # leaving X unbound.
    ("X == 1 // 0", FAILS),
    ("(Y is 0, X == 1 // Y)", FAILS),
    ("(X == 1 // Y, Y is 0)", FAILS),
    ("(X == 1 // Y, Y == 0)", FAILS),
    ("X == 1 / 0", FAILS),
    ("X == 1 % 0", FAILS),
    ("X == '//'(1, 0)", FAILS),
    ("X == mod(1, 0)", FAILS),
    ("X != 1 // 0", FAILS),
    ("1 < 1 // 0", FAILS),
    ("X == '^'(2, -1)", FAILS),
    # reified: the relation is false
    ("if_(Z == 1 // 0, X is yes, X is no)", "no"),
    ("eval_(div(1, 0), X)", "error(evaluation_error(zero_divisor),(div)/2)"),
    # ... but a divisor that becomes 0 while a CLP(FD) search runs prunes
    # that branch, as Scryer's clpz does (``X #= 10 // Y, Y in 0..2,
    # label([Y])`` gives Y = 1 and Y = 2 there)
    ("findall(Y, (Z == 10 // Y, in_domain(Y, 0, 2), label([Y])), X)", [1, 2]),
    ("findall(Y, (Z == '//'(10, Y), in_domain(Y, -1, 1), label([Y])), X)", [-1, 1]),
    # a ground '**' nested in a CLP(FD) tree is refused like one over a var
    ("(X == Y + '**'(2, 3), Y is 1)",
     "error(domain_error(clpz_expression,2**3),_)"),
    # a negative exponent of '^' prunes while labelling, as in Scryer's clpz
    # (``X #= 2^Y, Y in -1..2`` labels Y = 0, 1, 2; with base 0 too)
    ("findall(Y, (Z == '^'(2, Y), in_domain(Y, -1, 2), label([Y])), X)", [0, 1, 2]),
    ("findall(Y, (Z == '^'(0, Y), in_domain(Y, -1, 2), label([Y])), X)", [0, 1, 2]),
    # between/3 is not a clpz post: a '**' bound is its float, refused as a
    # non-integer bound
    ("between(1, '**'(2, 2), X)", "error(type_error(integer,4.0),between/3)"),
]


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("arith_rulings")
    # strict functors: the evaluable functors need no declaration (Q16);
    # decimal/2 is an exact-number cell, not an evaluable functor
    src = "-allow_singletons\n-private([yes, no, decimal(M, S)])\n" + "".join(
        f"g{i}(X) <- ({body}),\n" for i, (body, _) in enumerate(BARE_ROWS))
    p = d / "_arith_operator_rulings.clausal"
    p.write_text(src)
    return _load_module("_arith_operator_rulings", str(p))


@pytest.mark.parametrize("i", range(len(BARE_ROWS)), ids=[r[0] for r in BARE_ROWS])
def test_bare_python_quoted_scryer(mod, i):
    want = BARE_ROWS[i][1]
    x = Var()
    try:
        got = [deref(x) for _ in solve((f"g{i}", x), mod)]
    except LogicException as exc:
        assert isinstance(want, str), render_error_term(exc.term)
        assert render_error_term(exc.term) == want
        return
    if want is FAILS:
        assert got == [], got
        return
    assert not (isinstance(want, str) and want.startswith("error(")), got
    assert got == [want] and type(got[0]) is type(want), got


def test_ne_prunes_a_zero_divisor_while_labelling(tmp_path):
    """The C-accelerated ``!=`` propagator's both-ground arm sees a no-value
    expression as differing from nothing, so the branch fails (ruling Q14;
    ``clpfd._eval_ground_for_c``) -- it raised before."""
    p = tmp_path / "_arith_rulings_ne.clausal"
    p.write_text("-allow_singletons\n"
                 "g(X) <- findall(Y, (10 // Y != 3, in_domain(Y, 0, 4), "
                 "label([Y])), X)\n")
    m = _load_module("_arith_rulings_ne", str(p))
    x = Var()
    assert [deref(x) for _ in solve(("g", x), m)] == [[1, 2, 4]]


# ── Q16: the evaluable functors are builtins -- in scope, and still terms ──

_STRICT_SRC = """-module({name}, [ev(N, X), fact(T), head(T, A, B), same(T), mine(X)])
-allow_singletons
ev(1, X) <- 'is'(X, rdiv(7, 2))
ev(2, X) <- 'is'(X, '//'(-7, 2))
ev(3, X) <- 'is'(X, '^'(2, 3))
ev(4, X) <- 'is'(X, '**'(2, 3))
ev(5, X) <- 'is'(X, div(-7, 2))
ev(6, X) <- 'is'(X, mod(-7, 2))
ev(7, X) <- 'is'(X, '/'(7, 2))
ev(8, X) <- 'is'(X, '+'(1, '*'(2, '-'(5, 1))))
ev(9, X) <- 'is'(X, '-'(5))
ev(10, X) <- (X == rdiv(7, 2))
fact(rdiv(1, 2)),
fact('//'(7, 2)),
head(rdiv(A, B), A, B),
same(T) <- (T is '^'(2, 3))
"""

_EV_WANT = {1: Fraction(7, 2), 2: -3, 3: 8, 4: 8.0, 5: -4, 6: 1, 7: 3.5,
            8: 9, 9: -5, 10: Fraction(7, 2)}


@pytest.fixture(scope="module")
def strict_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("arith_q16")
    name = f"_arith_q16_{next(_N)}"
    p = d / f"{name}.clausal"
    p.write_text(_STRICT_SRC.format(name=name))
    return _load_module(name, str(p))


@pytest.mark.parametrize("n", sorted(_EV_WANT))
def test_q16_evaluable_functors_are_in_scope_in_a_strict_module(strict_mod, n):
    x = Var()
    got = [deref(x) for _ in solve(("ev", n, x), strict_mod)]
    assert got == [_EV_WANT[n]] and type(got[0]) is type(_EV_WANT[n]), got


def test_q16_as_data_and_in_a_head_they_are_just_terms(strict_mod):
    t = Var()
    assert [deref(t) for _ in solve(("fact", t), strict_mod)] == [
        ("rdiv", 1, 2), ("//", 7, 2)]
    a, b = Var(), Var()
    assert [(deref(a), deref(b)) for _ in solve(
        ("head", ("rdiv", 1, 2), a, b), strict_mod)] == [(1, 2)]
    assert [deref(t) for _ in solve(("same", t), strict_mod)] == [("^", 2, 3)]


def test_q16_a_module_declaration_of_the_spelling_answers_first(tmp_path):
    """A module's own declaration of an evaluable spelling wins, with its
    usual arity error: a data functor rdiv/3 makes ``rdiv(1, 2)`` too few."""
    p = tmp_path / "_arith_q16_shadow.clausal"
    p.write_text("-private([rdiv(A, B, C)])\n"
                 "g(X) <- 'is'(X, rdiv(1, 2))\n")
    with pytest.raises(SyntaxError, match=r"rdiv/3 was constructed with 2"):
        _load_module("_arith_q16_shadow", str(p))


# ── the seam (``--``) in Python-hosted code ─────────────────────────────────

_SEAM_SRC = '''-module({name}, [p(A)])
-implicit_atoms
-implicit_functors
def floor_value(): return --p(-7 // 2)
def pow_value(): return --p(2 ** 3)
def quoted_term(): return --p('//'(-7, 2))
def zero(): return --p(1 // 0)
def goal_bare():
    if --eval_(-7 // 2, X): return X
def goal_quoted():
    if --eval_('//'(-7, 2), X): return X
def goal_pow_quoted():
    if --eval_('**'(2, 3), X): return X
'''


@pytest.fixture(scope="module")
def seam_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("arith_rulings_seam")
    name = f"_arith_rulings_seam{next(_N)}"
    p = d / f"{name}.clausal"
    p.write_text(_SEAM_SRC.format(name=name))
    return _load_module(name, str(p))


def test_seam_bare_operators_are_python(seam_mod):
    assert seam_mod.floor_value() == ("p", -4)
    assert seam_mod.pow_value() == ("p", 8)
    assert type(seam_mod.pow_value()[1]) is int
    assert seam_mod.goal_bare() == -4


def test_seam_quoted_operators_are_scryer(seam_mod):
    # a quoted cell in term position is a TERM, evaluated by whoever uses it
    assert seam_mod.quoted_term() == ("p", ("//", -7, 2))
    assert seam_mod.goal_quoted() == -3
    got = seam_mod.goal_pow_quoted()
    assert got == 8.0 and type(got) is float


def test_seam_zero_divisor_is_the_logic_error(seam_mod):
    with pytest.raises(LogicException) as info:
        seam_mod.zero()
    assert render_error_term(info.value.term) == (
        "error(evaluation_error(zero_divisor),(//)/2)")


def test_no_value_in_propagation_reads_the_error_terms_it_absorbs():
    """The CLP "no value" test recognises the formals as the builders make
    them (atoms ARE their str): '^''s type_error(float, B) and any
    evaluation_error; clpz's own domain_error and other errors are not."""
    from clausal.logic.clpfd import _no_value_in_propagation
    from clausal.logic.exceptions import (
        domain_error, evaluation_error, type_error)
    assert _no_value_in_propagation(LogicException(type_error("float", 2, "(^)/2")))
    assert _no_value_in_propagation(LogicException(evaluation_error("zero_divisor", "(/)/2")))
    assert _no_value_in_propagation(LogicException(evaluation_error("undefined", "(^)/2")))
    assert not _no_value_in_propagation(LogicException(
        domain_error("clpz_expression", "a", "clpfd expression")))
    assert not _no_value_in_propagation(LogicException(type_error("integer", 1.5, "(//)/2")))
