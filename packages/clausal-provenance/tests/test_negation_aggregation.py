"""P-3 tests — stratified negation + semiring-aware aggregation."""

from __future__ import annotations

# Pre-load stdlib + torch ahead of any clausal import that might
# redirect them to wrapper modules.
try:
    from clausal.modules.py import _import_stdlib
    for _name in ("uuid", "datetime", "random", "logging"):
        try:
            _import_stdlib(_name)
        except ImportError:
            pass
    torch = _import_stdlib("torch")
    try:
        _import_stdlib("sympy")
    except ImportError:
        pass
    _HAS_TORCH = True
except ImportError:
    torch = None
    _HAS_TORCH = False

import pytest

from clausal.logic.predicate import make_predicate
from clausal.logic.database import Module, Clause
from clausal.logic.variables import Var
from clausal.pythonic_ast.nodes import Call, LoadName, Not

from clausal.modules.provenance import (
    boolean,
    add_mult_prob,
    diff_add_mult_prob,
    evaluate,
    NonGroundTupleError,
    StratificationError,
)
from clausal.modules.provenance._registration import BOTTOM_UP_FLAG


# ── Helpers ──────────────────────────────────────────────────────────


def _ast_call(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def _setup_negation_program():
    """Two-stratum program: Block, Reachable<-Edge, Allowed<-Reachable & not Block."""
    Edge = make_predicate("Edge", ["a", "b"])
    Block = make_predicate("Block", ["x"])
    Reachable = make_predicate("Reachable", ["x"])
    Allowed = make_predicate("Allowed", ["x"])
    for cls in (Edge, Block, Reachable, Allowed):
        cls.__module__ = "test_negation"
        setattr(cls, BOTTOM_UP_FLAG, True)

    # Reachable(X) <- Edge(_, X)
    A, X = Var(), Var()
    Reachable._assertz(Clause(
        head=Reachable(X),
        body=[_ast_call("Edge", A, X)],
    ))

    # Allowed(X) <- Reachable(X), not Block(X)
    X2 = Var()
    Allowed._assertz(Clause(
        head=Allowed(X2),
        body=[
            _ast_call("Reachable", X2),
            Not(operand=_ast_call("Block", X2)),
        ],
    ))

    mod = Module("test_negation", module_dict={
        "Edge": Edge, "Block": Block,
        "Reachable": Reachable, "Allowed": Allowed,
    })
    return mod, Edge, Block, Reachable, Allowed


# Stratified negation under boolean and add_mult_prob is dogfooded in
# tests/fixtures/negation_aggregate.clausal — the 6 cases there cover
# blocked / unblocked / all-blocked under boolean, and certain /
# probabilistic / no-block under add_mult_prob.


# ══════════════════════════════════════════════════════════════════════
# Stratified negation gradient flow under diff_add_mult_prob
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_negation_grad_flows():
    """Gradient on the block probability flows through ``not Block(x)``."""
    mod, Edge, Block, Reachable, Allowed = _setup_negation_program()
    p_edge = torch.tensor(0.7, requires_grad=True, dtype=torch.float64)
    p_block = torch.tensor(0.4, requires_grad=True, dtype=torch.float64)
    facts = [
        (Edge("a", "b"), p_edge),
        (Block("b"), p_block),
    ]
    out = evaluate(diff_add_mult_prob, facts, Allowed("b"), module=mod)
    assert len(out) == 1
    _, tag = out[0]
    # tag = p_edge * (1 - p_block) = 0.7 * 0.6 = 0.42
    assert abs(tag.item() - 0.42) < 1e-9
    tag.backward()
    # ∂tag/∂p_edge = (1 - p_block) = 0.6
    # ∂tag/∂p_block = -p_edge = -0.7
    assert abs(p_edge.grad.item() - 0.6) < 1e-9
    assert abs(p_block.grad.item() - (-0.7)) < 1e-9


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_negation_gradcheck():
    mod, Edge, Block, Reachable, Allowed = _setup_negation_program()

    def model(probs):
        facts = [
            (Edge("a", "b"), probs[0]),
            (Block("b"), probs[1]),
        ]
        out = evaluate(diff_add_mult_prob, facts, Allowed("b"), module=mod)
        return out[0][1]

    probs = torch.tensor([0.6, 0.3], dtype=torch.float64, requires_grad=True)
    assert torch.autograd.gradcheck(model, (probs,), eps=1e-6, atol=1e-5)


# ══════════════════════════════════════════════════════════════════════
# Negation safety — non-ground negated atom rejected
# ══════════════════════════════════════════════════════════════════════


def test_negation_with_unbound_args_raises():
    """``not Q(X)`` with X free fails fast."""
    Q = make_predicate("Q", ["x"])
    Z = make_predicate("Z", ["x"])
    Q.__module__ = "test_neg_safety"
    Z.__module__ = "test_neg_safety"
    setattr(Q, BOTTOM_UP_FLAG, True)
    setattr(Z, BOTTOM_UP_FLAG, True)
    X = Var()
    # Z(X) <- not Q(X)   ← X is free at the negation
    Z._assertz(Clause(head=Z(X), body=[Not(operand=_ast_call("Q", X))]))
    mod = Module("test_neg_safety", module_dict={"Q": Q, "Z": Z})
    with pytest.raises(NonGroundTupleError, match="Negation"):
        evaluate(boolean, [(Q(1), True)], Z(Var()), module=mod)


# ══════════════════════════════════════════════════════════════════════
# AggregateProvenance — Boolean
# ══════════════════════════════════════════════════════════════════════


def test_boolean_count_cardinality():
    assert boolean.aggregate_count([True, False, True, True]) == 3
    assert boolean.aggregate_count([]) == 0
    assert boolean.aggregate_count([False, False]) == 0


def test_boolean_sum_over_true_tags():
    assert boolean.aggregate_sum([(1, True), (2, False), (3, True)]) == 4
    assert boolean.aggregate_sum([]) == 0


def test_boolean_argmax_largest_true():
    assert boolean.aggregate_argmax([(1, True), (2, False), (3, True)]) == (3, True)
    assert boolean.aggregate_argmax([(1, False), (2, False)]) == (None, False)


# ══════════════════════════════════════════════════════════════════════
# AggregateProvenance — AddMultProb
# ══════════════════════════════════════════════════════════════════════


def test_add_mult_prob_count_is_expected_count():
    # Σ p_i
    out = add_mult_prob.aggregate_count([0.3, 0.5, 0.2])
    assert abs(out - 1.0) < 1e-12


def test_add_mult_prob_sum_is_expected_sum():
    # Σ v_i p_i
    out = add_mult_prob.aggregate_sum([(3, 0.7), (5, 0.3)])
    assert abs(out - (3 * 0.7 + 5 * 0.3)) < 1e-12


def test_add_mult_prob_argmax_picks_max_prob():
    assert add_mult_prob.aggregate_argmax([(3, 0.4), (5, 0.7), (8, 0.6)]) == (5, 0.7)


# ══════════════════════════════════════════════════════════════════════
# AggregateProvenance — DiffAddMultProb (gradient flow)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_aggregate_count_grad():
    """Gradient of expected count w.r.t. each tag is 1."""
    p1 = torch.tensor(0.4, requires_grad=True, dtype=torch.float64)
    p2 = torch.tensor(0.3, requires_grad=True, dtype=torch.float64)
    p3 = torch.tensor(0.2, requires_grad=True, dtype=torch.float64)
    out = diff_add_mult_prob.aggregate_count([p1, p2, p3])
    assert abs(out.item() - 0.9) < 1e-9
    out.backward()
    assert abs(p1.grad.item() - 1.0) < 1e-9
    assert abs(p2.grad.item() - 1.0) < 1e-9
    assert abs(p3.grad.item() - 1.0) < 1e-9


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_aggregate_sum_grad():
    """Gradient of Σ v_i p_i w.r.t. p_i is v_i."""
    p1 = torch.tensor(0.6, requires_grad=True, dtype=torch.float64)
    p2 = torch.tensor(0.4, requires_grad=True, dtype=torch.float64)
    out = diff_add_mult_prob.aggregate_sum([(3.0, p1), (7.0, p2)])
    out.backward()
    assert abs(p1.grad.item() - 3.0) < 1e-9
    assert abs(p2.grad.item() - 7.0) < 1e-9


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_aggregate_count_gradcheck():
    def model(tags):
        # Cast to a list of scalars (each entry preserves grad).
        return diff_add_mult_prob.aggregate_count([tags[i] for i in range(len(tags))])
    tags = torch.tensor([0.4, 0.3, 0.2], dtype=torch.float64, requires_grad=True)
    assert torch.autograd.gradcheck(model, (tags,), eps=1e-6, atol=1e-5)


# provenance.aggregate/4 happy-path coverage (count / sum / argmax under
# boolean and add_mult_prob) lives in
# tests/fixtures/negation_aggregate.clausal. The Python tests below keep
# only the rejection paths that need pytest.raises.


def test_aggregate_4_rejects_non_aggregate_semiring():
    """A bare ``Provenance`` (no aggregation methods) must be rejected."""
    from clausal.modules.provenance.protocol import Provenance
    from clausal.modules.provenance import aggregate as agg
    from clausal.logic.solve import call as logic_call

    class _Plain(Provenance):
        name = "_plain"
        def zero(self): return 0
        def one(self): return 1
        def add(self, a, b): return a + b
        def mult(self, a, b): return a * b

    plain = _Plain()
    R = Var()
    with pytest.raises(TypeError, match="AggregateProvenance"):
        for _ in logic_call(agg, plain, "count", [1, 2], R):
            pass


def test_aggregate_4_rejects_unknown_op():
    from clausal.modules.provenance import aggregate as agg
    from clausal.logic.solve import call as logic_call
    R = Var()
    with pytest.raises(ValueError, match="op must be one of"):
        for _ in logic_call(agg, boolean, "median", [1, 2], R):
            pass


# ══════════════════════════════════════════════════════════════════════
# Cyclic negation still rejected at stratify time
# ══════════════════════════════════════════════════════════════════════


def test_cyclic_negation_still_rejected():
    from clausal.modules.provenance.stratify import stratify
    P_clauses = [Clause(head=None, body=[Not(operand=_ast_call("Q", Var()))])]
    Q_clauses = [Clause(head=None, body=[Not(operand=_ast_call("P", Var()))])]
    program = {("P", 1): P_clauses, ("Q", 1): Q_clauses}
    with pytest.raises(StratificationError):
        stratify(program)
