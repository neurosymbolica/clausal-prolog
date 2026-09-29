"""A set literal in GOAL position is a CLP(Q) constraint set (operator
ruling 2026-09-30): the seam twin of clpq's ``{C}``.

    two(N, Q) <- {Q == N * 2}
    within(X) <- {0 <= X <= 10}

Each case is written three ways and must agree:

* the set spelling (under test),
* the long spelling ``clpq.rational((...))`` (its twin -- the set lowers to
  that very goal, so the two are one GoalOp), and
* for the unit-free cases, Scryer's ``{C}`` from library(clpq) (the clean
  clpq build at ``SCRYER``; its answers are the oracle).

The units cases go through ``constant(Name)`` (a compile-time fold) with a
``-constant_number_units`` declaration: CLP(Q) takes a unit-carrying
Quantity through the units side channel, as the bare comparators do.

A set in DATA position (a head, an argument, ``is``) keeps meaning a set;
``{}`` is a dict, not a constraint set; a non-constraint element is a load
error naming it.
"""
from __future__ import annotations

import itertools
import os
import re
import subprocess
from fractions import Fraction

import pytest

from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk, is_var, get_attr
from clausal.terms import Quantity, SetTerm, term_str

SCRYER = "/workspace/scryer-prolog-clpq/target/release/scryer-prolog"

_N = itertools.count()

UNITS = ("-import_from(european_union, [euro])\n"
         "-constant_number_units(one_euro, 1, euro)\n"
         "-constant_number_units(max_fine, 5000, euro)\n")


def _module(tmp_path, body: str, heads: list[str], extra: str = ""):
    name = f"_set_goal_{next(_N)}"
    src = (f"-module({name}, [{', '.join(heads)}])\n-allow_singletons\n"
           f"{extra}{body}\n")
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


def _answers(mod, pred, *args, n=1):
    """Answers of ``pred(*args, Out1..Outn)``, each a tuple of walked outs."""
    outs = [Var() for _ in range(n)]
    return [tuple(walk(o) for o in outs)
            for _ in call(pred, *args, *outs, module=mod)]


def _scryer(tmp_path, program: str, goal: str, outs: str) -> list:
    """Run ``goal`` under Scryer's library(clpq) and return its answers
    (``[]`` when it fails) with ``A rdiv B`` read as a Fraction."""
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    f = tmp_path / f"oracle{next(_N)}.pl"
    f.write_text(":- use_module(library(clpq)).\n" + program)
    proc = subprocess.run(
        [SCRYER, str(f), "-g",
         f"(findall({outs}, {goal}, L), writeq(answers(L)), nl, halt)"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120)
    m = re.search(r"answers\((.*)\)\s*$", proc.stdout.strip())
    assert m, (proc.stdout, proc.stderr)
    text = m.group(1)

    def value(s: str):
        s = s.strip()
        r = re.fullmatch(r"(-?\d+) rdiv (\d+)", s)
        if r:
            return Fraction(int(r.group(1)), int(r.group(2)))
        return int(s)

    inner = text[1:-1]
    if not inner:
        return []
    return [tuple(value(v) for v in item.split(","))
            for item in re.findall(r"\(([^()]*)\)", inner)] \
        if inner.startswith("(") else [(value(v),) for v in inner.split(",")]


# ── the cases: (name, set body, long body, head, call arguments -- ``None``
#    is a fresh output variable --, expected answers (the outputs, walked),
#    scryer clause, scryer goal, scryer output template) ─────────────────────
CASES = [
    ("forward",
     "two(N, Q) <- {Q == N * 2}",
     "two(N, Q) <- clpq.rational(Q == N * 2)",
     "two(N, Q)", (3, None), [(6,)],
     "two(N, Q) :- {Q = N * 2}.", "two(3, Q)", "Q"),
    ("backward",
     "two(N, Q) <- {Q == N * 2}",
     "two(N, Q) <- clpq.rational(Q == N * 2)",
     "two(N, Q)", (None, 8), [(4,)],
     "two(N, Q) :- {Q = N * 2}.", "two(N, 8)", "N"),
    ("rational",
     "half(X) <- {2 * X == 3}",
     "half(X) <- clpq.rational(2 * X == 3)",
     "half(X)", (None,), [(Fraction(3, 2),)],
     "half(X) :- {2 * X = 3}.", "half(X)", "X"),
    ("chained",
     "within(X) <- ({0 <= X <= 10}, X == 7)",
     "within(X) <- (clpq.rational(0 <= X <= 10), X == 7)",
     "within(X)", (None,), [(7,)],
     "within(X) :- {0 =< X, X =< 10}, X = 7.", "within(X)", "X"),
    ("chained_out_of_range",
     "within(X) <- ({0 <= X <= 10}, X == 11)",
     "within(X) <- (clpq.rational(0 <= X <= 10), X == 11)",
     "within(X)", (None,), [],
     "within(X) :- {0 =< X, X =< 10}, X = 11.", "within(X)", "X"),
    ("two_constraints",
     "box(X, Y) <- {X + Y == 1, X - Y == 1/2}",
     "box(X, Y) <- clpq.rational((X + Y == 1, X - Y == 1/2))",
     "box(X, Y)", (None, None), [(Fraction(3, 4), Fraction(1, 4))],
     "box(X, Y) :- {X + Y = 1, X - Y = 1/2}.", "box(X, Y)", "(X, Y)"),
    ("inequality_then_binding",
     "above(X) <- ({X > 1}, X == 2)",
     "above(X) <- (clpq.rational(X > 1), X == 2)",
     "above(X)", (None,), [(2,)],
     "above(X) :- {X > 1}, X = 2.", "above(X)", "X"),
    ("inequality_then_refused_binding",
     "above(X) <- ({X > 1}, X == 1)",
     "above(X) <- (clpq.rational(X > 1), X == 1)",
     "above(X)", (None,), [],
     "above(X) :- {X > 1}, X = 1.", "above(X)", "X"),
    ("both_unbound_then_propagation",
     "both(Q) <- ({Q == N * 2}, N == 4)",
     "both(Q) <- (clpq.rational(Q == N * 2), N == 4)",
     "both(Q)", (None,), [(8,)],
     "both(Q) :- {Q = N * 2}, N = 4.", "both(Q)", "Q"),
]
_IDS = [c[0] for c in CASES]


def _run(tmp_path, body, head, call_args):
    """Load ``body`` and call ``head``'s predicate with ``call_args``, a
    ``None`` being a fresh output variable; answers are the outputs, walked."""
    mod = _module(tmp_path, body, [head])
    pred = head.split("(")[0]
    args = [Var() if a is None else a for a in call_args]
    outs = [a for a, given in zip(args, call_args) if given is None]
    return [tuple(walk(o) for o in outs) for _ in call(pred, *args, module=mod)]


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_set_goal_answers_equal_its_twin(tmp_path, case):
    """The set spelling answers exactly as its ``clpq.rational`` twin, in
    the engine's presentation (an int, or a Fraction when non-integral)."""
    _, set_body, long_body, head, call_args, expected, *_ = case
    got_set = _run(tmp_path, set_body, head, call_args)
    got_long = _run(tmp_path, long_body, head, call_args)
    assert got_set == expected, got_set
    assert got_set == got_long, (got_set, got_long)
    for row in got_set:
        for v in row:
            assert type(v) in (int, Fraction), (v, type(v))


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_scryers_clpq_braces_answer_the_same(tmp_path, case):
    """The oracle: Scryer's ``{C}`` (library(clpq)) gives the answers the
    engine's table expects.  Needs the clpq build at ``SCRYER``; set
    ``CLAUSAL_ISO_ALLOW_NO_SCRYER`` to skip instead of fail without it."""
    _, _, _, _, _, expected, pl_clause, pl_goal, pl_outs = case
    assert _scryer(tmp_path, pl_clause, pl_goal, pl_outs) == expected


def test_both_unbound_leaves_a_residual_rational_constraint(tmp_path):
    """``two(N, Q)`` with both unbound: no binding, both variables carry
    the CLP(Q) attribute the long spelling leaves, and the constraint is
    live (binding N later solves Q)."""
    for body in ("two(N, Q) <- {Q == N * 2}",
                 "two(N, Q) <- clpq.rational(Q == N * 2)"):
        mod = _module(tmp_path, body, ["two(N, Q)"])
        N, Q = Var(), Var()
        seen = 0
        for _ in call("two", N, Q, module=mod):
            seen += 1
            assert is_var(N) and is_var(Q)
            assert get_attr(N, "clpq") is not None
            assert get_attr(Q, "clpq") is not None
        assert seen == 1


def test_the_set_lowers_to_the_clpq_rational_goal():
    """The two spellings are one GoalOp: a ``SubCall`` of ``clpq.rational/1``
    whose argument is the constraint (a ``TupleLiteral`` of them)."""
    from clausal.pythonic_ast import nodes
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.logic.compiler.ir import SubCall
    x, y = Var(), Var()
    c1 = nodes.ArithEq(left=x, right=nodes.Mult(left=y, right=2))
    c2 = nodes.Gt(left=x, right=0)
    one = terms_to_goalop([nodes.SetLiteral(elements=[c1])])
    assert [type(op) for op in one.ops] == [SubCall]
    assert (one.ops[0].fname, one.ops[0].arity) == ("clpq.rational", 1)
    assert one.ops[0].args == [c1]
    two = terms_to_goalop([nodes.SetLiteral(elements=[c1, c2])])
    arg, = two.ops[0].args
    assert isinstance(arg, nodes.TupleLiteral) and arg.elements == [c1, c2]
    twin = terms_to_goalop([nodes.Call(
        func=nodes.LoadAttr(object=nodes.LoadName(name="clpq"),
                            attr="rational"),
        args=[nodes.TupleLiteral(elements=[c1, c2])], kwargs=[])])
    assert (twin.ops[0].fname, twin.ops[0].arity, twin.ops[0].args[0].elements) \
        == (two.ops[0].fname, two.ops[0].arity, arg.elements)


# ── units: constant(Name) folds to a Quantity the block accepts ─────────────

@pytest.mark.parametrize("set_body, long_body", [
    ("amount(Q) <- {Q == 100 * constant(one_euro)}",
     "amount(Q) <- clpq.rational(Q == 100 * constant(one_euro))"),
])
def test_a_united_constant_inside_the_set(tmp_path, set_body, long_body):
    """``{Q == 100 * constant(one_euro)}`` gives ``100 euro``: the Quantity
    the bare comparator ``Q == 100 * constant(one_euro)`` gives (the
    positive control: that path always took units)."""
    got = [_answers(_module(tmp_path, b, ["amount(Q)"], UNITS), "amount")
           for b in (set_body, long_body,
                     "amount(Q) <- (Q == 100 * constant(one_euro))")]
    assert got[0] == got[1] == got[2], got
    (q,), = got[0]
    assert isinstance(q, Quantity) and (q.value, q.dims) == (100, {"euro": 1})


@pytest.mark.parametrize("spell", ["set", "long"])
def test_an_inequality_against_a_declared_united_constant(tmp_path, spell):
    con = ("{F >= constant(max_fine)}" if spell == "set"
           else "clpq.rational(F >= constant(max_fine))")
    body = (f"big() <- (F == 6000 * constant(one_euro), {con})\n"
            f"small() <- (F == 4000 * constant(one_euro), {con})\n"
            f"later(F) <- ({con}, F == 6000 * constant(one_euro))\n"
            f"later_small(F) <- ({con}, F == 4000 * constant(one_euro))\n")
    mod = _module(tmp_path, body, ["big()", "small()", "later(F)",
                                   "later_small(F)"], UNITS)
    assert _answers(mod, "big", n=0) == [()]
    assert _answers(mod, "small", n=0) == []
    (f,), = _answers(mod, "later")
    assert isinstance(f, Quantity) and (f.value, f.dims) == (6000, {"euro": 1})
    assert _answers(mod, "later_small") == []


def test_a_units_mismatch_inside_the_set_is_the_iso_error(tmp_path):
    body = "bad() <- ({Q == 100 * constant(one_euro)}, Q == 5)"
    mod = _module(tmp_path, body, ["bad()"], UNITS)
    with pytest.raises(LogicException) as ei:
        _answers(mod, "bad", n=0)
    assert "units_mismatch" in term_str(ei.value.term)


# ── refusals and the data position ──────────────────────────────────────────

@pytest.mark.parametrize("body, culprit", [
    ("bad(X) <- {X + 1, X > 1}", "+ 1"),
    ("bad(X) <- {foo(X)}", "foo("),
    ("bad(X) <- {X in [1, 2]}", "in [1, 2]"),
    ("bad(X) <- ({X > 0}, {X})", "is not one"),
])
def test_a_non_constraint_element_is_a_load_error_naming_it(tmp_path, body,
                                                             culprit):
    from clausal.logic.compiler.terms_to_goalop import SetGoalElementError
    with pytest.raises(SetGoalElementError) as ei:
        _module(tmp_path, body, ["bad(X)"])
    text = str(ei.value)
    assert "a set literal in goal position is a CLP(Q) constraint set" in text
    assert culprit in text and "bad/1" in text, text


def test_an_empty_brace_pair_in_goal_position_is_a_dict_not_a_set(tmp_path):
    """``{}`` is Python's empty dict; in goal position it is refused as the
    dict it is (the compiler's unsupported-goal-shape error names
    ``DictTerm``), never read as an empty constraint set."""
    with pytest.raises(NotImplementedError) as ei:
        _module(tmp_path, "e() <- {}", ["e()"])
    assert "DictTerm" in str(ei.value) and "CLP(Q)" not in str(ei.value)


def test_a_set_in_data_position_is_still_a_set(tmp_path):
    body = ("colors({1, 2, 3})\n"
            "named(S) <- (S is {1, 2})\n"
            "passed(S) <- colors(S)\n"
            "checked(X) <- (colors(S), X in S)\n")
    mod = _module(tmp_path, body, ["colors(S)", "named(S)", "passed(S)",
                                   "checked(X)"])
    (s,), = _answers(mod, "colors")
    assert isinstance(s, SetTerm) and set(s) == {1, 2, 3}
    (t,), = _answers(mod, "named")
    assert isinstance(t, SetTerm) and set(t) == {1, 2}
    (u,), = _answers(mod, "passed")
    assert set(u) == {1, 2, 3}
    assert sorted(x for (x,) in _answers(mod, "checked")) == [1, 2, 3]
