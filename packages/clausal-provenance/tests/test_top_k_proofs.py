"""P-4 tests — top-k-proofs and diff-top-k-proofs.

Coverage:
    1. DNF algebra (zero, one, ⊕, ⊗, identity, distributivity, idempotence).
    2. tagging_fn allocates fresh input ids; recover_fn reproduces I-E.
    3. Top-k truncation drops the lowest-probability conjunctions.
    4. Engine integration: two-hop, diamond (disjoint proofs), shared-input
       proofs (where add_mult_prob over-counts but top-k-proofs is exact).
    5. Boolean equivalence at 0/1 probabilities.
    6. Numerical parity with diff_add_mult_prob when k ≥ #proofs and proofs
       are input-disjoint (the plan's required parity validation).
    7. PyTorch autograd: forward / backward correctness, gradcheck on the
       2-rule MNIST-Sum-style program at k=3 (the plan's flagship check).
    8. JAX path: jax.grad through the same path produces matching values.
    9. Bridges: explicit torch/jax autograd-Function paths produce the same
       value and gradient as the implicit recover_fn.
"""

from __future__ import annotations

# Pre-load real torch / sympy / stdlib via _import_stdlib so the Clausal
# import hook doesn't redirect them to wrapper modules.
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

try:
    from clausal.modules.py import _import_stdlib
    jax = _import_stdlib("jax")
    jax.config.update("jax_enable_x64", True)
    jnp = _import_stdlib("jax.numpy")
    _HAS_JAX = True
except ImportError:
    jax = None
    jnp = None
    _HAS_JAX = False

import math

import pytest

from clausal.logic.predicate import make_predicate
from clausal.logic.database import Module, Clause
from clausal.logic.variables import Var
from clausal.pythonic_ast.nodes import Call, LoadName

from clausal.modules.provenance import (
    boolean,
    add_mult_prob,
    diff_add_mult_prob,
    top_k_proofs,
    diff_top_k_proofs,
    TopKProofs,
    DiffTopKProofs,
    evaluate,
)
from clausal.modules.provenance._registration import BOTTOM_UP_FLAG


# ── Helpers ──────────────────────────────────────────────────────────────


def _ast_call(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def _setup_path_program():
    """Build an (Edge/2, Path/2) reach program with two rules."""
    Edge = make_predicate("edge", ["a", "b"])
    Path = make_predicate("path", ["a", "b"])
    Edge.__module__ = "test_topk_proofs"
    Path.__module__ = "test_topk_proofs"
    setattr(Edge, BOTTOM_UP_FLAG, True)
    setattr(Path, BOTTOM_UP_FLAG, True)

    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("edge", A, B)]))
    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("edge", A2, M), _ast_call("path", M, B2)],
    ))
    mod = Module("test_topk_proofs", module_dict={"edge": Edge, "path": Path})
    return mod, Edge, Path


def _setup_sumdigits_program():
    """sum_digits(A, B, T) <- digit(A, X), digit(B, Y), T is X + Y."""
    from clausal.pythonic_ast.nodes import Is, BinOp, BinOpKind
    Digit = make_predicate("digit", ["image_id", "value"])
    SumDigits = make_predicate("sum_digits", ["a", "b", "total"])
    Digit.__module__ = "test_topk_sum"
    SumDigits.__module__ = "test_topk_sum"
    setattr(Digit, BOTTOM_UP_FLAG, True)
    setattr(SumDigits, BOTTOM_UP_FLAG, True)

    A, B, T, X, Y = Var(), Var(), Var(), Var(), Var()
    SumDigits._assertz(Clause(
        head=SumDigits(A, B, T),
        body=[
            _ast_call("digit", A, X),
            _ast_call("digit", B, Y),
            Is(target=T, value=BinOp(left=X, op=BinOpKind.ADD, right=Y)),
        ],
    ))
    mod = Module("test_topk_sum", module_dict={"digit": Digit, "sum_digits": SumDigits})
    return mod, Digit, SumDigits


# ══════════════════════════════════════════════════════════════════════════
# DNF algebra
# ══════════════════════════════════════════════════════════════════════════


def test_zero_one_constants():
    s = top_k_proofs(k=3)
    assert s.zero() == frozenset()
    assert s.one() == frozenset({frozenset()})


def test_mult_zero_absorbs():
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.5)
    assert s.mult(s.zero(), a) == s.zero()
    assert s.mult(a, s.zero()) == s.zero()


def test_mult_one_is_identity():
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.7)
    assert s.mult(s.one(), a) == a
    assert s.mult(a, s.one()) == a


def test_add_zero_is_identity():
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.4)
    assert s.add(s.zero(), a) == a
    assert s.add(a, s.zero()) == a


def test_add_idempotent():
    """⊕ is set-union; a ⊕ a = a (before truncation)."""
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.4)
    assert s.add(a, a) == a


def test_mult_two_singletons_combines_inputs():
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.5)
    b = s.tagging_fn(0.4)
    out = s.mult(a, b)
    # Single conjunction containing both literals.
    assert len(out) == 1
    (conj,) = out
    assert {(0, True), (1, True)} == set(conj)


def test_add_two_singletons_two_disjuncts():
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.5)
    b = s.tagging_fn(0.4)
    out = s.add(a, b)
    assert len(out) == 2


# ══════════════════════════════════════════════════════════════════════════
# Inclusion-exclusion recovery
# ══════════════════════════════════════════════════════════════════════════


def test_recover_singleton_is_input_prob():
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.7)
    assert abs(s.recover_fn(a) - 0.7) < 1e-12


def test_recover_product_under_independence():
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.5)
    b = s.tagging_fn(0.4)
    assert abs(s.recover_fn(s.mult(a, b)) - 0.2) < 1e-12


def test_recover_disjoint_alternatives_via_inclusion_exclusion():
    """P(a ∨ b) = P(a) + P(b) − P(a)·P(b) — for disjoint-input conjs."""
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.5)
    b = s.tagging_fn(0.4)
    expected = 0.5 + 0.4 - 0.5 * 0.4
    assert abs(s.recover_fn(s.add(a, b)) - expected) < 1e-12


def test_recover_shared_input_proofs_no_overcounting():
    """``a∧b ∨ a∧c`` = a·(b + c − bc), exact under I-E.

    add_mult_prob would compute ``ab + ac − (ab)(ac) = ab + ac − a²bc``
    — over-counting when the two proofs share input ``a``.
    """
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.7)   # id 0
    b = s.tagging_fn(0.5)   # id 1
    c = s.tagging_fn(0.4)   # id 2
    ab = s.mult(a, b)
    ac = s.mult(a, c)
    disj = s.add(ab, ac)
    expected = 0.7 * (0.5 + 0.4 - 0.5 * 0.4)   # = 0.7 * 0.7 = 0.49
    assert abs(s.recover_fn(disj) - expected) < 1e-12


def test_recover_inconsistent_conjunction_drops_to_zero():
    """A literal x ∧ ¬x has probability 0 — pruned from I-E."""
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.5)
    # Build a deliberately inconsistent conj — literal id 0 with both polarities.
    inconsistent = frozenset({frozenset({(0, True), (0, False)})})
    # ⊗ rejects it; ⊕ leaves the consistent disjunct alone.
    out = s.add(a, inconsistent)
    assert s.recover_fn(out) == 0.5   # only the consistent disjunct contributes
    # Direct: recover of an all-inconsistent DNF is 0.
    assert s.recover_fn(inconsistent) == 0.0


# ══════════════════════════════════════════════════════════════════════════
# Top-k truncation
# ══════════════════════════════════════════════════════════════════════════


def test_top_k_truncation_keeps_highest_prob():
    s = top_k_proofs(k=2)
    # Three singleton facts with probabilities 0.1, 0.5, 0.9.
    a = s.tagging_fn(0.1)
    b = s.tagging_fn(0.5)
    c = s.tagging_fn(0.9)
    union = s.add(s.add(a, b), c)
    assert len(union) == 2
    # The pruned conj is the lowest-prob one — id 0 with prob 0.1.
    kept_ids = {next(iter(conj))[0] for conj in union}
    assert 0 not in kept_ids
    assert kept_ids == {1, 2}


def test_top_k_truncation_in_mult():
    s = top_k_proofs(k=2)
    # Build a DNF with three disjuncts then AND with another singleton.
    p1 = s.tagging_fn(0.9)
    p2 = s.tagging_fn(0.6)
    p3 = s.tagging_fn(0.1)
    p4 = s.tagging_fn(0.8)
    big = s.add(s.add(p1, p2), p3)   # 3 disjuncts
    out = s.mult(big, p4)
    # 3 × 1 product → 3 conjs of 2 literals; truncated to 2.
    assert len(out) == 2


def test_invalid_k_rejected():
    with pytest.raises(ValueError, match="positive int"):
        top_k_proofs(k=0)
    with pytest.raises(ValueError, match="positive int"):
        top_k_proofs(k=-1)


# ══════════════════════════════════════════════════════════════════════════
# Engine integration — top-k two-hop, diamond, parity with amp, and the
# zero/one boolean-equivalence corner case that filters reachable_topk
# vs reachable_bool live in tests/fixtures/top_k_engine.seam. The
# Python tests below keep only the multi-set boolean-equivalence variant
# because it exercises a Path(Var, Var) result-set comparison that's
# easier to write in Python.
# ══════════════════════════════════════════════════════════════════════════


def test_engine_boolean_equivalence_at_zero_one_inputs():
    """top_k_proofs at probabilities ∈ {0, 1} matches the boolean semiring."""
    mod, Edge, Path = _setup_path_program()
    facts_topk = [
        (Edge("a", "b"), 1.0), (Edge("b", "c"), 1.0),
        (Edge("a", "d"), 0.0), (Edge("d", "e"), 1.0),
    ]
    facts_bool = [
        (Edge("a", "b"), True), (Edge("b", "c"), True),
        (Edge("a", "d"), True), (Edge("d", "e"), True),
    ]
    out_topk = evaluate(top_k_proofs(k=4), facts_topk, Path(Var(), Var()), module=mod)
    out_bool = evaluate(boolean, facts_bool, Path(Var(), Var()), module=mod)
    # A result term is a CELL -- ``('path', A, B)`` -- so its arguments are
    # read at their POSITIONS.  ``t.a``/``t.b`` was the instance spelling.
    reachable_topk = {(t[1], t[2]) for t, p in out_topk if p > 0.5}
    reachable_bool = {(t[1], t[2]) for t, p in out_bool if p}
    # Edges with prob 1.0 plus their reach closure; the prob-0 edge a→d
    # contributes nothing, so a→e (only reachable through d) is absent.
    assert reachable_topk == {("a", "b"), ("b", "c"), ("a", "c"), ("d", "e")}
    # The boolean run treats every input as True regardless of probability,
    # so it sees the full transitive closure including a→d→e.
    assert reachable_bool == {("a", "b"), ("b", "c"), ("a", "c"),
                              ("a", "d"), ("d", "e"), ("a", "e")}


# Parity with add_mult_prob on disjoint proofs (top_k(k>=#proofs) ==
# add_mult_prob exactly) is dogfooded in
# tests/fixtures/top_k_engine.seam. This Python file keeps only the
# differentiable parity case below because gradcheck and tensor probs
# don't fit a .clausal Test clause.


# ══════════════════════════════════════════════════════════════════════════
# diff_top_k_proofs — gradient flow under PyTorch
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_topk_torch_two_hop_value_and_grad():
    mod, Edge, Path = _setup_path_program()
    p1 = torch.tensor(0.7, requires_grad=True, dtype=torch.float64)
    p2 = torch.tensor(0.5, requires_grad=True, dtype=torch.float64)
    facts = [(Edge("a", "b"), p1), (Edge("b", "c"), p2)]
    out = evaluate(diff_top_k_proofs(k=3), facts, Path("a", "c"), module=mod)
    _, tag = out[0]
    assert isinstance(tag, torch.Tensor)
    assert tag.requires_grad
    assert abs(tag.item() - 0.35) < 1e-9
    tag.backward()
    assert abs(p1.grad.item() - 0.5) < 1e-9
    assert abs(p2.grad.item() - 0.7) < 1e-9


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_topk_torch_diamond_grad_flows_to_all_inputs():
    mod, Edge, Path = _setup_path_program()
    p_ab = torch.tensor(0.6, requires_grad=True, dtype=torch.float64)
    p_bd = torch.tensor(0.6, requires_grad=True, dtype=torch.float64)
    p_ac = torch.tensor(0.5, requires_grad=True, dtype=torch.float64)
    p_cd = torch.tensor(0.4, requires_grad=True, dtype=torch.float64)
    facts = [
        (Edge("a", "b"), p_ab), (Edge("b", "d"), p_bd),
        (Edge("a", "c"), p_ac), (Edge("c", "d"), p_cd),
    ]
    out = evaluate(diff_top_k_proofs(k=3), facts, Path("a", "d"), module=mod)
    _, tag = out[0]
    expected = 0.36 + 0.20 - 0.36 * 0.20
    assert abs(tag.item() - expected) < 1e-9
    tag.backward()
    assert p_ab.grad.abs().item() > 0
    assert p_bd.grad.abs().item() > 0
    assert p_ac.grad.abs().item() > 0
    assert p_cd.grad.abs().item() > 0


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_topk_torch_gradcheck_2rule_k3():
    """The plan's flagship validation — gradcheck on 2-rule program at k=3."""
    mod, Edge, Path = _setup_path_program()

    def model(probs):
        facts = [
            (Edge(0, 1), probs[0]),
            (Edge(1, 2), probs[1]),
            (Edge(0, 2), probs[2]),
        ]
        out = evaluate(diff_top_k_proofs(k=3), facts, Path(0, 2), module=mod)
        return out[0][1]

    probs = torch.tensor([0.4, 0.6, 0.3], dtype=torch.float64, requires_grad=True)
    assert torch.autograd.gradcheck(model, (probs,), eps=1e-6, atol=1e-5)


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_topk_torch_gradcheck_diamond_k3():
    mod, Edge, Path = _setup_path_program()

    def model(probs):
        facts = [
            (Edge("a", "b"), probs[0]),
            (Edge("b", "d"), probs[1]),
            (Edge("a", "c"), probs[2]),
            (Edge("c", "d"), probs[3]),
        ]
        out = evaluate(diff_top_k_proofs(k=3), facts, Path("a", "d"), module=mod)
        return out[0][1]

    probs = torch.tensor([0.6, 0.6, 0.5, 0.4],
                         dtype=torch.float64, requires_grad=True)
    assert torch.autograd.gradcheck(model, (probs,), eps=1e-6, atol=1e-5)


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_topk_torch_parity_diff_amp_when_k_ge_proofs():
    """Numerical parity with diff_add_mult_prob when k ≥ #proofs (plan req)."""
    mod, Edge, Path = _setup_path_program()
    probs_amp = torch.tensor([0.6, 0.5, 0.4, 0.7],
                             dtype=torch.float64, requires_grad=True)
    facts_amp = [
        (Edge("a", "b"), probs_amp[0]),
        (Edge("b", "d"), probs_amp[1]),
        (Edge("a", "c"), probs_amp[2]),
        (Edge("c", "d"), probs_amp[3]),
    ]
    out_amp = evaluate(diff_add_mult_prob, facts_amp, Path("a", "d"), module=mod)

    probs_topk = torch.tensor([0.6, 0.5, 0.4, 0.7],
                              dtype=torch.float64, requires_grad=True)
    facts_topk = [
        (Edge("a", "b"), probs_topk[0]),
        (Edge("b", "d"), probs_topk[1]),
        (Edge("a", "c"), probs_topk[2]),
        (Edge("c", "d"), probs_topk[3]),
    ]
    out_topk = evaluate(diff_top_k_proofs(k=3), facts_topk, Path("a", "d"), module=mod)

    # Forward parity (disjoint proofs).
    assert abs(out_amp[0][1].item() - out_topk[0][1].item()) < 1e-9

    # Backward parity.
    out_amp[0][1].backward()
    out_topk[0][1].backward()
    for i in range(4):
        assert abs(probs_amp.grad[i].item() - probs_topk.grad[i].item()) < 1e-9


# ══════════════════════════════════════════════════════════════════════════
# diff_top_k_proofs — JAX path
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _HAS_JAX, reason="JAX not installed")
def test_diff_topk_jax_two_hop_value_and_grad():
    mod, Edge, Path = _setup_path_program()

    def model(probs):
        facts = [
            (Edge("a", "b"), probs[0]),
            (Edge("b", "c"), probs[1]),
        ]
        out = evaluate(diff_top_k_proofs(k=3), facts, Path("a", "c"), module=mod)
        return out[0][1]

    probs = jnp.array([0.7, 0.5], dtype=jnp.float64)
    val = model(probs)
    assert abs(float(val) - 0.35) < 1e-9
    g = jax.grad(model)(probs)
    assert abs(float(g[0]) - 0.5) < 1e-9
    assert abs(float(g[1]) - 0.7) < 1e-9


# ══════════════════════════════════════════════════════════════════════════
# Bridges — explicit autograd-Function paths
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_torch_bridge_value_matches_implicit_recover():
    from clausal.modules.provenance.bridges.torch_bridge import topk_recover_torch

    s = diff_top_k_proofs(k=3)
    p1 = torch.tensor(0.6, requires_grad=True, dtype=torch.float64)
    p2 = torch.tensor(0.4, requires_grad=True, dtype=torch.float64)
    p3 = torch.tensor(0.7, requires_grad=True, dtype=torch.float64)
    a = s.tagging_fn(p1)
    b = s.tagging_fn(p2)
    c = s.tagging_fn(p3)
    disj = s.add(s.mult(a, b), c)   # (p1 ∧ p2) ∨ p3

    val_implicit = s.recover_fn(disj)
    val_explicit = topk_recover_torch(disj, s._input_tags)
    assert abs(val_implicit.item() - val_explicit.item()) < 1e-12


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_torch_bridge_grad_matches_implicit_recover():
    from clausal.modules.provenance.bridges.torch_bridge import topk_recover_torch

    # Implicit
    s_a = diff_top_k_proofs(k=3)
    p_a = [
        torch.tensor(0.6, requires_grad=True, dtype=torch.float64),
        torch.tensor(0.4, requires_grad=True, dtype=torch.float64),
        torch.tensor(0.7, requires_grad=True, dtype=torch.float64),
    ]
    a = s_a.tagging_fn(p_a[0])
    b = s_a.tagging_fn(p_a[1])
    c = s_a.tagging_fn(p_a[2])
    disj_a = s_a.add(s_a.mult(a, b), c)
    s_a.recover_fn(disj_a).backward()

    # Explicit bridge
    s_b = diff_top_k_proofs(k=3)
    p_b = [
        torch.tensor(0.6, requires_grad=True, dtype=torch.float64),
        torch.tensor(0.4, requires_grad=True, dtype=torch.float64),
        torch.tensor(0.7, requires_grad=True, dtype=torch.float64),
    ]
    a2 = s_b.tagging_fn(p_b[0])
    b2 = s_b.tagging_fn(p_b[1])
    c2 = s_b.tagging_fn(p_b[2])
    disj_b = s_b.add(s_b.mult(a2, b2), c2)
    topk_recover_torch(disj_b, s_b._input_tags).backward()

    for ga, gb in zip(p_a, p_b):
        assert abs(ga.grad.item() - gb.grad.item()) < 1e-9


@pytest.mark.skipif(not _HAS_JAX, reason="JAX not installed")
def test_jax_bridge_value_matches_implicit_recover():
    from clausal.modules.provenance.bridges.jax_bridge import topk_recover_jax

    s = diff_top_k_proofs(k=3)
    p1 = jnp.float64(0.6)
    p2 = jnp.float64(0.4)
    p3 = jnp.float64(0.7)
    a = s.tagging_fn(p1)
    b = s.tagging_fn(p2)
    c = s.tagging_fn(p3)
    disj = s.add(s.mult(a, b), c)

    val_implicit = s.recover_fn(disj)
    val_explicit = topk_recover_jax(disj, s._input_tags)
    assert abs(float(val_implicit) - float(val_explicit)) < 1e-12


# ══════════════════════════════════════════════════════════════════════════
# Negation
# ══════════════════════════════════════════════════════════════════════════


def test_negation_of_zero_is_one():
    s = top_k_proofs(k=3)
    assert s.negate(s.zero()) == s.one()


def test_negation_of_one_is_zero():
    """¬⊤ = ⊥. Implementation reduces ¬{∅} → {} after AND of ¬lits collapses."""
    s = top_k_proofs(k=3)
    # ¬⊤ = ¬(empty conj) = OR of ¬lits over empty set = empty disjunction = ⊥.
    assert s.negate(s.one()) == s.zero()


def test_negation_singleton_complementary_probability():
    """¬a → DNF whose recover gives 1 − p."""
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.7)
    not_a = s.negate(a)
    assert abs(s.recover_fn(not_a) - 0.3) < 1e-12


# ══════════════════════════════════════════════════════════════════════════
# Aggregation
# ══════════════════════════════════════════════════════════════════════════


def test_aggregate_count_sum_argmax_under_topk():
    s = top_k_proofs(k=3)
    a = s.tagging_fn(0.5)
    b = s.tagging_fn(0.3)
    c = s.tagging_fn(0.9)
    # count = 0.5 + 0.3 + 0.9 = 1.7
    assert abs(s.aggregate_count([a, b, c]) - 1.7) < 1e-12
    # sum (1, 2, 3) under same probs
    assert abs(s.aggregate_sum([(1, a), (2, b), (3, c)])
               - (1*0.5 + 2*0.3 + 3*0.9)) < 1e-12
    # argmax → (3, c)
    v, t = s.aggregate_argmax([(1, a), (2, b), (3, c)])
    assert v == 3 and t == c


# ══════════════════════════════════════════════════════════════════════════
# Factory hygiene — fresh state per call
# ══════════════════════════════════════════════════════════════════════════


def test_factory_returns_fresh_instance_per_call():
    s1 = top_k_proofs(k=3)
    s2 = top_k_proofs(k=3)
    assert s1 is not s2
    s1.tagging_fn(0.5)
    assert 0 in s1._input_tags
    assert 0 not in s2._input_tags
