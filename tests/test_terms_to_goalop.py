"""Slice D2: ``terms_to_goalop`` subset coverage.

Unit tests for the prototype term → GoalOp converter.  Lowering lives
in Slice D3; this file only checks the IR shape produced for the D2
subset (binding / constraint / membership + list/tuple conjunction).
"""

from __future__ import annotations

import pytest

from clausal.pythonic_ast import nodes
from clausal.logic.compiler.ir import (
    ArithEval,
    Dif,
    FDCompare,
    MemberIn,
    Sequence,
    StructuralEq,
    Unify,
)
from clausal.logic.compiler.terms_to_goalop import terms_to_goalop


# Terms are opaque to ``terms_to_goalop`` — it never inspects operands,
# only forwards them into IR fields.  Plain strings stand in as term
# sentinels so dataclass equality in assertions is well-defined without
# depending on Var identity semantics.
def _vars(*names):
    return list(names)


# Node dataclasses declare a ``position`` field first, so positional
# args would land there — always construct binary-op nodes via kwargs.
def _b(cls, l, r):
    return cls(left=l, right=r)


def test_empty_body_is_empty_sequence():
    assert terms_to_goalop([]) == Sequence(ops=[])


def test_unify_and_dif():
    x, y = _vars("X", "Y")
    ir = terms_to_goalop([_b(nodes.Unify, x, y), _b(nodes.DoesNotUnify, x, y)])
    assert ir == Sequence(ops=[Unify(l=x, r=y), Dif(l=x, r=y)])


def test_evaluate_to_aritheval():
    x, y = _vars("X", "Y")
    ir = terms_to_goalop([_b(nodes.Evaluate, x, y)])
    assert ir == Sequence(ops=[ArithEval(target=x, expr=y)])


@pytest.mark.parametrize("cmp_cls,op", [
    (nodes.ArithEq, "eq"),
    (nodes.ArithNeq, "ne"),
    (nodes.Lt, "lt"),
    (nodes.LtE, "le"),
    (nodes.Gt, "gt"),
    (nodes.GtE, "ge"),
])
def test_fd_compare(cmp_cls, op):
    x, y = _vars("X", "Y")
    ir = terms_to_goalop([_b(cmp_cls, x, y)])
    assert ir == Sequence(ops=[FDCompare(op=op, l=x, r=y)])


def test_structural_eq_and_neq():
    x, y = _vars("X", "Y")
    ir = terms_to_goalop([
        _b(nodes.StructuralEq, x, y),
        _b(nodes.StructuralNeq, x, y),
    ])
    assert ir == Sequence(ops=[
        StructuralEq(l=x, r=y, negate=False),
        StructuralEq(l=x, r=y, negate=True),
    ])


def test_member_in_and_not_in():
    x, y = _vars("X", "Y")
    ir = terms_to_goalop([_b(nodes.in_, x, y), _b(nodes.NotIn, x, y)])
    assert ir == Sequence(ops=[
        MemberIn(elem=x, collection=y, negate=False),
        MemberIn(elem=x, collection=y, negate=True),
    ])


def test_tuple_literal_flattens_into_sequence():
    x, y, z = _vars("X", "Y", "Z")
    body = [nodes.TupleLiteral(elements=[_b(nodes.Unify, x, y), _b(nodes.Unify, y, z)])]
    assert terms_to_goalop(body) == Sequence(ops=[
        Unify(l=x, r=y), Unify(l=y, r=z),
    ])


def test_nested_list_flattens():
    x, y, z = _vars("X", "Y", "Z")
    body = [
        _b(nodes.Unify, x, y),
        [_b(nodes.Unify, y, z), _b(nodes.Unify, x, z)],
    ]
    assert terms_to_goalop(body) == Sequence(ops=[
        Unify(l=x, r=y), Unify(l=y, r=z), Unify(l=x, r=z),
    ])


def test_and_flattens_into_sequence():
    x, y, z, w = _vars("X", "Y", "Z", "W")
    body = [_b(nodes.And, _b(nodes.And, _b(nodes.Unify, x, y),
                                          _b(nodes.Unify, y, z)),
                          _b(nodes.Unify, z, w))]
    assert terms_to_goalop(body) == Sequence(ops=[
        Unify(l=x, r=y), Unify(l=y, r=z), Unify(l=z, r=w),
    ])


def test_unsupported_raises_not_implemented():
    # ``Or`` is deferred to Slice D5b.
    x, y = _vars("X", "Y")
    with pytest.raises(NotImplementedError, match="not yet supported"):
        terms_to_goalop([_b(nodes.Or, x, y)])
