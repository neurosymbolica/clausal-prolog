"""Differentiable provenance tests — autograd flow through the engine.

Tests `diff_add_mult_prob` under PyTorch and JAX, verifying:
    1. ⊕ and ⊗ produce tensor-typed tags with grad fns intact.
    2. A 3-fact, 2-rule program admits ``torch.autograd.gradcheck``.
    3. Mixing torch and jax tags in one ``solve`` raises.

PyTorch is imported *before* clausal so the real PyPI torch package is
loaded rather than the clausal-torch wrapper. Same trick for JAX.
"""

from __future__ import annotations

# Use clausal.modules.py._import_stdlib to bypass the Clausal import
# hook — bare `import torch` post-clausal-import returns the
# clausal-torch wrapper module, which is not what we want here.
try:
    from clausal.modules.py import _import_stdlib
    torch = _import_stdlib("torch")
    # gradcheck imports sympy internally — pre-load real sympy to dodge
    # the Clausal wrapper's circular-init when imported via gradcheck.
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
    # Enable float64 before any tracer is created — otherwise jnp.float64
    # silently downcasts to float32 and gradcheck-style numerics fail.
    jax.config.update("jax_enable_x64", True)
    jnp = _import_stdlib("jax.numpy")
    _HAS_JAX = True
except ImportError:
    jax = None
    jnp = None
    _HAS_JAX = False

import pytest

from clausal.logic.predicate import make_predicate
from clausal.logic.database import Module, Clause
from clausal.logic.variables import Var
from clausal.pythonic_ast.nodes import Call, LoadName

from clausal.modules.provenance import (
    boolean,
    add_mult_prob,
    diff_add_mult_prob,
    evaluate,
)
from clausal.modules.provenance._registration import BOTTOM_UP_FLAG


# ── Helpers ────────────────────────────────────────────────────────────


def _ast_call(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def _setup_path_program():
    """Build a fresh (Edge/2, Path/2) reach program with two rules."""
    Edge = make_predicate("Edge", ["a", "b"])
    Path = make_predicate("Path", ["a", "b"])
    Edge.__module__ = "test_diff_prov"
    Path.__module__ = "test_diff_prov"
    setattr(Edge, BOTTOM_UP_FLAG, True)
    setattr(Path, BOTTOM_UP_FLAG, True)

    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))

    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("Edge", A2, M), _ast_call("Path", M, B2)],
    ))

    mod = Module("test_diff_prov", module_dict={"Edge": Edge, "Path": Path})
    return mod, Edge, Path


# ── add_mult_prob algebra ──────────────────────────────────────────────


def test_add_mult_prob_zero_one():
    assert add_mult_prob.zero() == 0.0
    assert add_mult_prob.one() == 1.0


def test_add_mult_prob_mult_is_product():
    assert add_mult_prob.mult(0.5, 0.4) == 0.2
    assert add_mult_prob.mult(1.0, 0.7) == 0.7
    assert add_mult_prob.mult(0.0, 0.7) == 0.0


def test_add_mult_prob_add_is_noisy_or():
    # 0.5 + 0.4 - 0.5*0.4 = 0.7
    assert abs(add_mult_prob.add(0.5, 0.4) - 0.7) < 1e-12
    # ⊕ identity at 0
    assert add_mult_prob.add(0.0, 0.7) == 0.7
    # ⊕ saturates at 1
    assert add_mult_prob.add(1.0, 0.5) == 1.0


def test_add_mult_prob_saturated_with_tolerance():
    assert add_mult_prob.saturated(0.5, 0.5 + 1e-12) is True
    assert add_mult_prob.saturated(0.5, 0.5 + 1e-3) is False


def test_add_mult_prob_discard_below_eps():
    assert add_mult_prob.discard(1e-12) is True
    assert add_mult_prob.discard(1e-3) is False


# add_mult_prob through the engine (two-hop, alternative paths via
# noisy-OR, zero-input propagation) is dogfooded in
# tests/fixtures/provenance_reach.clausal under the
# "add_mult_prob through the engine" section.


# ── diff_add_mult_prob: tensor-typed tags ──────────────────────────────


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_torch_two_hop():
    mod, Edge, Path = _setup_path_program()
    p1 = torch.tensor(0.7, requires_grad=True, dtype=torch.float64)
    p2 = torch.tensor(0.5, requires_grad=True, dtype=torch.float64)
    facts = [(Edge("a", "b"), p1), (Edge("b", "c"), p2)]
    out = evaluate(diff_add_mult_prob, facts, Path("a", "c"), module=mod)
    assert len(out) == 1
    _, tag = out[0]
    assert isinstance(tag, torch.Tensor)
    assert tag.requires_grad
    # Forward value
    assert abs(tag.item() - 0.35) < 1e-9
    # Backward
    tag.backward()
    assert abs(p1.grad.item() - 0.5) < 1e-9   # ∂(p1·p2)/∂p1 = p2
    assert abs(p2.grad.item() - 0.7) < 1e-9


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_torch_alternative_paths():
    """Verify gradient flows through the noisy-OR aggregation."""
    mod, Edge, Path = _setup_path_program()
    p_ab = torch.tensor(0.6, requires_grad=True, dtype=torch.float64)
    p_bd = torch.tensor(0.6, requires_grad=True, dtype=torch.float64)
    p_ac = torch.tensor(0.5, requires_grad=True, dtype=torch.float64)
    p_cd = torch.tensor(0.4, requires_grad=True, dtype=torch.float64)
    facts = [
        (Edge("a", "b"), p_ab),
        (Edge("b", "d"), p_bd),
        (Edge("a", "c"), p_ac),
        (Edge("c", "d"), p_cd),
    ]
    out = evaluate(diff_add_mult_prob, facts, Path("a", "d"), module=mod)
    _, tag = out[0]
    expected = 0.36 + 0.20 - 0.36 * 0.20
    assert abs(tag.item() - expected) < 1e-6
    tag.backward()
    # All four edge probabilities receive a non-zero gradient.
    assert p_ab.grad.abs().item() > 0
    assert p_bd.grad.abs().item() > 0
    assert p_ac.grad.abs().item() > 0
    assert p_cd.grad.abs().item() > 0


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_torch_gradcheck_3fact_2rule():
    """The plan's key validation: gradcheck on a 3-fact, 2-rule program."""
    mod, Edge, Path = _setup_path_program()

    def model(probs):
        # 3 facts: Edge(0,1), Edge(1,2), Edge(0,2)
        facts = [
            (Edge(0, 1), probs[0]),
            (Edge(1, 2), probs[1]),
            (Edge(0, 2), probs[2]),
        ]
        out = evaluate(diff_add_mult_prob, facts, Path(0, 2), module=mod)
        # Expected answer = noisy_or(probs[2], probs[0]·probs[1])
        assert len(out) == 1
        return out[0][1]

    # Use float64 + careful initial values to avoid the saturated branches
    # of noisy-OR (where ∂/∂p of `1−(1−a)(1−b)` flips).
    probs = torch.tensor([0.4, 0.6, 0.3], dtype=torch.float64, requires_grad=True)
    assert torch.autograd.gradcheck(model, (probs,), eps=1e-6, atol=1e-5)


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_diff_add_mult_prob_torch_gradcheck_diamond():
    """Gradcheck through alternative-path noisy-OR aggregation."""
    mod, Edge, Path = _setup_path_program()

    def model(probs):
        facts = [
            (Edge("a", "b"), probs[0]),
            (Edge("b", "d"), probs[1]),
            (Edge("a", "c"), probs[2]),
            (Edge("c", "d"), probs[3]),
        ]
        out = evaluate(diff_add_mult_prob, facts, Path("a", "d"), module=mod)
        return out[0][1]

    probs = torch.tensor([0.6, 0.6, 0.5, 0.4],
                         dtype=torch.float64, requires_grad=True)
    assert torch.autograd.gradcheck(model, (probs,), eps=1e-6, atol=1e-5)


# ── diff_add_mult_prob: JAX ────────────────────────────────────────────


@pytest.mark.skipif(not _HAS_JAX, reason="JAX not installed")
def test_diff_add_mult_prob_jax_two_hop():
    mod, Edge, Path = _setup_path_program()
    p1 = jnp.float64(0.7)
    p2 = jnp.float64(0.5)
    facts = [(Edge("a", "b"), p1), (Edge("b", "c"), p2)]
    out = evaluate(diff_add_mult_prob, facts, Path("a", "c"), module=mod)
    _, tag = out[0]
    assert abs(float(tag) - 0.35) < 1e-9


@pytest.mark.skipif(not _HAS_JAX, reason="JAX not installed")
def test_diff_add_mult_prob_jax_grad_two_hop():
    """jax.grad through evaluate gives correct gradient for the simple case."""
    mod, Edge, Path = _setup_path_program()

    def model(probs):
        facts = [
            (Edge("a", "b"), probs[0]),
            (Edge("b", "c"), probs[1]),
        ]
        out = evaluate(diff_add_mult_prob, facts, Path("a", "c"), module=mod)
        return out[0][1]

    probs = jnp.array([0.7, 0.5], dtype=jnp.float64)
    g = jax.grad(model)(probs)
    # ∂(p0 p1)/∂p0 = p1 = 0.5, ∂/∂p1 = p0 = 0.7
    assert abs(float(g[0]) - 0.5) < 1e-9
    assert abs(float(g[1]) - 0.7) < 1e-9


# ── Framework-mixing rejected ──────────────────────────────────────────


@pytest.mark.skipif(not (_HAS_TORCH and _HAS_JAX),
                    reason="needs both torch and jax")
def test_mixing_torch_and_jax_tags_raises():
    from clausal.modules.provenance.semirings._framework import check_homogeneous
    with pytest.raises(ValueError, match="Mixing tag frameworks"):
        check_homogeneous([
            torch.tensor(0.5),
            jnp.float64(0.5),
        ])


# ── Sanity: framework detection without imports ────────────────────────


def test_detect_framework_python():
    from clausal.modules.provenance.semirings._framework import detect_framework
    assert detect_framework(0.5) == "python"
    assert detect_framework(True) == "python"


@pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")
def test_detect_framework_torch():
    from clausal.modules.provenance.semirings._framework import detect_framework
    assert detect_framework(torch.tensor(0.5)) == "torch"
