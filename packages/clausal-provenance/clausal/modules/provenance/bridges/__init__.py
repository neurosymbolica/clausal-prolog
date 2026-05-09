"""Framework-specific autograd bridges for provenance semirings.

Used by ``diff_top_k_proofs`` to provide an explicit autograd-Function
forward/backward pair: forward computes ``P(disj)`` and the sparse
Jacobian in one Python pass; backward is a single sparse-Jacobian ×
upstream-grad multiplication.

The default recover path on ``DiffTopKProofs`` already produces a
correctly-traced tensor by recomputing the inclusion-exclusion sum on
the original input tensors (PyTorch / JAX trace through the I-E formula
naturally). The bridges here are an opt-in optimisation for cases where
the same DNF is recovered many times.
"""

from clausal.modules.provenance.bridges.torch_bridge import topk_recover_torch
from clausal.modules.provenance.bridges.jax_bridge import topk_recover_jax

__all__ = ["topk_recover_torch", "topk_recover_jax"]
