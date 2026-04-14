"""Slice D6a parallel-implementation harness for TRO analysis.

For each clause shape exercised by ``tests/test_tail_recursion.py``'s
``TestDetectTroClause``, run both:

- legacy ``_detect_tro_clause`` / ``_get_tro_check_indices`` (operates
  on raw body terms, the source of truth today), and
- IR-side ``tro.analyse_ir`` (operates on the :class:`Sequence` produced
  by ``terms_to_goalop``).

…and assert the two agree on both eligibility and ``check_indices``.
This is the D6 option-1 verification gate: the IR analysis is shadow
today; D7 promotes it to primary.  Any divergence here fails the test
loudly so a silent compile-time regression cannot ship.
"""

from __future__ import annotations

import pytest

from clausal.logic.database import Clause
from clausal.logic.predicate import PredicateMeta
from clausal.logic.variables import Var
from clausal.terms import (
    Add, Sub,
    Compound,
    Unify, Evaluate,
    Gt,
    Call, LoadName,
)
from clausal.pythonic_ast.nodes import StarUnpack


def _pred(name: str, fields: tuple[str, ...]):
    return PredicateMeta(name, (), {"_fields": fields})


def _case_no_body():
    P = _pred("P", ("x",))
    return ("no_body", "P", 1, Clause(head=P(x=Var()), body=[]))


def _case_self_call_passthrough():
    Q = _pred("Q", ("x",))
    x = Var()
    return ("self_call_passthrough", "Q", 1, Clause(
        head=Q(x),
        body=[Call(func=LoadName(name="Q"), args=[x], kwargs=[])],
    ))


def _case_det_prefix():
    Fact = _pred("Fact", ("n", "result"))
    n, n1, result = Var(), Var(), Var()
    return ("det_prefix", "Fact", 2, Clause(
        head=Fact(n, result),
        body=[
            Gt(left=n, right=0),
            Evaluate(left=n1, right=Sub(left=n, right=1)),
            Call(func=LoadName(name="Fact"), args=[n1, result], kwargs=[]),
        ],
    ))


def _case_nondet_prefix():
    R = _pred("R", ("n",))
    n = Var()
    return ("nondet_prefix", "R", 1, Clause(
        head=R(n),
        body=[
            Call(func=LoadName(name="Helper"), args=[n], kwargs=[]),
            Call(func=LoadName(name="R"), args=[n], kwargs=[]),
        ],
    ))


def _case_different_functor():
    S = _pred("S", ("x",))
    x = Var()
    return ("different_functor", "S", 1, Clause(
        head=S(x),
        body=[Call(func=LoadName(name="Other"), args=[x], kwargs=[])],
    ))


def _case_no_prefix_body_only_vars():
    Rev = _pred("Rev", ("list", "acc", "result"))
    h, t, acc, result = Var(), Var(), Var(), Var()
    return ("no_prefix_body_only_vars", "Rev", 3, Clause(
        head=Rev(Var(), acc, result),
        body=[
            Call(func=LoadName(name="Rev"),
                 args=[t, [h, StarUnpack(value=acc)], result], kwargs=[]),
        ],
    ))


def _case_star_unpack_with_prefix():
    Rev = _pred("Rev", ("list", "acc", "result"))
    h, t, acc, result, acc2 = Var(), Var(), Var(), Var(), Var()
    return ("star_unpack_with_prefix", "Rev", 3, Clause(
        head=Rev([h, StarUnpack(value=t)], acc, result),
        body=[
            Unify(left=acc2, right=[h, StarUnpack(value=acc)]),
            Call(func=LoadName(name="Rev"),
                 args=[t, acc2, result], kwargs=[]),
        ],
    ))


def _case_compound_arg_with_prefix():
    Acc = _pred("Acc", ("n", "state"))
    n, n1, acc = Var(), Var(), Var()
    return ("compound_arg_with_prefix", "Acc", 2, Clause(
        head=Acc(n, acc),
        body=[
            Gt(left=n, right=0),
            Evaluate(left=n1, right=Sub(left=n, right=1)),
            Call(func=LoadName(name="Acc"),
                 args=[n1, Compound("s", (n, acc))], kwargs=[]),
        ],
    ))


def _case_compound_arg_no_prefix():
    P = _pred("P", ("a", "b"))
    x, y = Var(), Var()
    return ("compound_arg_no_prefix", "P", 2, Clause(
        head=P(x, y),
        body=[
            Call(func=LoadName(name="P"),
                 args=[Compound("f", (x,)), y], kwargs=[]),
        ],
    ))


_CASES = [
    _case_no_body(),
    _case_self_call_passthrough(),
    _case_det_prefix(),
    _case_nondet_prefix(),
    _case_different_functor(),
    _case_no_prefix_body_only_vars(),
    _case_star_unpack_with_prefix(),
    _case_compound_arg_with_prefix(),
    _case_compound_arg_no_prefix(),
]


@pytest.mark.parametrize(
    "name,functor,arity,clause",
    [(n, f, a, c) for (n, f, a, c) in _CASES],
    ids=[c[0] for c in _CASES],
)
def test_tro_analyse_ir_agrees_with_legacy(name, functor, arity, clause):
    # Import inside the test so the references survive any sys.modules
    # scrubbing performed by ``test_runtime_compiler_boundary`` earlier
    # in the session.  Module-level imports here would leave us holding
    # stale ``ir.Sequence`` classes while ``terms_to_goalop`` (re-imported
    # below) produces fresh ones — every isinstance check inside
    # ``analyse_ir`` would then quietly return False.
    from clausal.logic.compiler import _detect_tro_clause
    from clausal.logic.compiler.tro import analyse_ir, _get_tro_check_indices
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop

    legacy_eligible = _detect_tro_clause(functor, arity, clause)
    legacy_check = (
        _get_tro_check_indices(functor, arity, clause)
        if legacy_eligible else frozenset()
    )

    # ``terms_to_goalop`` accepts ``db=None`` because none of the test
    # cases use kwarg calls (which would need a signature for WK-4).
    ir = terms_to_goalop(clause.body, db=None)
    ir_eligible, ir_check = analyse_ir(ir, clause.head, functor, arity)

    assert ir_eligible == legacy_eligible, (
        f"{name}: eligibility disagreement — "
        f"legacy={legacy_eligible}, ir={ir_eligible}"
    )
    assert ir_check == legacy_check, (
        f"{name}: check_indices disagreement — "
        f"legacy={legacy_check}, ir={ir_check}"
    )
