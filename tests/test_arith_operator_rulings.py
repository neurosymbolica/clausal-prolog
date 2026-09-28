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

import pytest

from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref

_N = itertools.count()

#: (clause body binding X, what X is -- or the error term it raises)
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
    # a CLP post with a zero divisor raised nothing and succeeded before,
    # leaving X unbound
    ("X == 1 // 0", "error(evaluation_error(zero_divisor),(//)/2)"),
    ("X == 1 / 0", "error(evaluation_error(zero_divisor),(/)/2)"),
    ("1 < 1 // 0", "error(evaluation_error(zero_divisor),(//)/2)"),
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
    src = "-allow_singletons\n-implicit_functors\n" + "".join(
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
    assert not isinstance(want, str), got
    assert got == [want] and type(got[0]) is type(want), got


@pytest.mark.xfail(strict=True, reason=(
    "the C-accelerated != propagator (_clpfd_propagate.c) calls _eval_ground "
    "directly, so a divisor that becomes 0 while labelling RAISES there "
    "instead of pruning; fixing it is a C change -- "
    "todo/arith-rulings-open-edges-2026-09-28.md item 1"))
def test_ne_prunes_a_zero_divisor_while_labelling(tmp_path):
    p = tmp_path / "_arith_rulings_ne.clausal"
    p.write_text("-allow_singletons\n"
                 "g(X) <- findall(Y, (10 // Y != 3, in_domain(Y, 0, 4), "
                 "label([Y])), X)\n")
    m = _load_module("_arith_rulings_ne", str(p))
    x = Var()
    assert [deref(x) for _ in solve(("g", x), m)] == [[1, 2, 4]]


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
