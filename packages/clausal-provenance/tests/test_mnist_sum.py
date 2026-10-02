"""MNIST-Sum showcase smoke test.

End-to-end: a tiny perception model maps "image features" to digit logits;
softmax probabilities feed into ``Digit/2`` facts; the bottom-up engine
under ``diff_add_mult_prob`` produces a probability for each candidate
sum; loss is computed against the true sum and backprop flows back to
the perception model. We don't need real MNIST — random features + a
small linear model exercise the same gradient path.
"""

from __future__ import annotations

# Bypass the Clausal import hook to load real torch / sympy.
try:
    from clausal.modules.py import _import_stdlib
    # Pre-load stdlib modules that torch's deferred imports later request,
    # before the Clausal import hook redirects them to wrapper modules.
    for _name in ("uuid", "datetime", "json", "random", "os", "csv", "logging"):
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

from clausal.testing import load_clausal_module
from clausal.modules.provenance import diff_add_mult_prob, evaluate


pytestmark = pytest.mark.skipif(not _HAS_TORCH, reason="PyTorch not installed")


@pytest.fixture(scope="module")
def mnist_sum_program():
    """Load the .clausal fixture once for the test module."""
    import os
    here = os.path.dirname(__file__)
    path = os.path.join(here, "fixtures", "mnist_sum.seam")
    mod = load_clausal_module(path)
    cm = mod.__dict__["$module"]
    return mod.digit, mod.SumDigits, cm


def _digit_facts(probs, image_ids=(0, 1)):
    """Build ``(Digit(img, v), p)`` pairs from a (n_images, 10) probability tensor."""
    from clausal.testing import load_clausal_module
    facts = []
    return [
        (probs_module_digit, p)
        for probs_module_digit, p in []
    ]


def test_mnist_sum_forward_pass(mnist_sum_program):
    """Forward pass: probs in → tagged answers out."""
    Digit, SumDigits, cm = mnist_sum_program
    # Confident probs: image 0 → digit 3 with 0.9; image 1 → digit 5 with 0.8.
    probs = torch.zeros(2, 10, dtype=torch.float64)
    probs[0, 3] = 0.9
    probs[1, 5] = 0.8
    facts = [
        (Digit(img, v), probs[img, v])
        for img in (0, 1)
        for v in range(10)
        if probs[img, v] > 0
    ]
    out = evaluate(diff_add_mult_prob, facts, SumDigits(0, 1, 8), module=cm)
    assert len(out) == 1
    _, tag = out[0]
    assert abs(tag.item() - 0.72) < 1e-9   # 0.9 * 0.8


def test_mnist_sum_backward_propagates(mnist_sum_program):
    """Gradient flows from the answer probability back to the input probs tensor."""
    Digit, SumDigits, cm = mnist_sum_program
    probs = torch.zeros(2, 10, dtype=torch.float64, requires_grad=True)
    # Use a non-trivial spread so multiple paths to TOTAL=8 exist.
    with torch.no_grad():
        probs[0, 3] = 0.5
        probs[0, 4] = 0.3
        probs[1, 4] = 0.2
        probs[1, 5] = 0.6
    probs.requires_grad_(True)

    facts = [
        (Digit(img, v), probs[img, v])
        for img in (0, 1)
        for v in range(10)
    ]
    out = evaluate(diff_add_mult_prob, facts, SumDigits(0, 1, 8), module=cm)
    # Exactly one ground answer for total=8; its tag = noisy_or over the
    # contributing (a, b) pairs whose sum is 8.
    assert len(out) == 1
    _, tag = out[0]
    assert tag.requires_grad
    tag.backward()
    assert probs.grad is not None
    # Cells that contribute to a 'sum=8' pair should have non-zero grad:
    # (3, 5), (4, 4) — image 0 digit 3, image 0 digit 4, image 1 digit 5,
    # image 1 digit 4.
    assert probs.grad[0, 3].abs().item() > 0
    assert probs.grad[0, 4].abs().item() > 0
    assert probs.grad[1, 5].abs().item() > 0
    assert probs.grad[1, 4].abs().item() > 0


@pytest.mark.timeout(60)
def test_mnist_sum_training_loop_decreases_loss(mnist_sum_program):
    """Optimising the perception model on a fixed (true_sum=7) target reduces loss.

    Runtime: ~10–15s in CI. Gives the engine 20 evaluate+backward passes —
    enough for noisy-OR to find a confident attribution and Adam to drive
    the loss down 1+ orders of magnitude.
    """
    Digit, SumDigits, cm = mnist_sum_program

    torch.manual_seed(0)
    # 2 images × 4 features each → 10 digit logits via a shared Linear head.
    n_features = 4
    head = torch.nn.Linear(n_features, 10, dtype=torch.float64)
    img_a = torch.randn(n_features, dtype=torch.float64)
    img_b = torch.randn(n_features, dtype=torch.float64)
    true_sum = 7

    opt = torch.optim.Adam(head.parameters(), lr=0.1)

    losses = []
    for _step in range(20):
        logits = head(torch.stack([img_a, img_b]))  # (2, 10)
        probs = torch.softmax(logits, dim=-1)
        facts = [
            (Digit(img, v), probs[img, v])
            for img in (0, 1)
            for v in range(10)
        ]
        out = evaluate(diff_add_mult_prob, facts, SumDigits(0, 1, true_sum), module=cm)
        if not out:
            # Diff semiring may have discarded all proofs at this point —
            # that's an edge case at the start of training only.
            losses.append(float("inf"))
            continue
        _, prob_correct = out[0]
        loss = -torch.log(prob_correct + 1e-12)
        opt.zero_grad()
        loss.backward()
        opt.step()
        losses.append(loss.item())

    # Loss should have decreased substantially over 40 steps.
    assert losses[-1] < losses[0], f"loss didn't decrease: {losses[0]:.4f} -> {losses[-1]:.4f}"
    assert losses[-1] < 1.0, f"final loss {losses[-1]:.4f} still high — training didn't converge"
