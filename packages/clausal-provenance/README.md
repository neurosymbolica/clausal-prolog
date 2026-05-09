# clausal-provenance

Provenance-tagged bottom-up Datalog for [Clausal](https://gitlab.com/MikeAmy/clausal).

A peer evaluation strategy to SLG, with semirings ranging from plain Boolean
Datalog through to PyTorch/JAX-differentiable probabilistic inference. The
underlying machinery — a stratified semi-naive bottom-up engine generic over a
tag algebra — is independently useful for plain Datalog reachability,
security/lineage analysis, and probabilistic databases.

The primary motivation is **neurosymbolic AI**: gradients flowing from a logic
query's answer probabilities back to a perception model's parameters.

## Install

```bash
pip install clausal-provenance        # core: boolean + add_mult_prob
pip install clausal-provenance[torch] # adds PyTorch (diff_add_mult_prob, ...)
pip install clausal-provenance[jax]   # adds JAX
pip install clausal-provenance[all]   # both frameworks
```

## Quick start

```clausal
-import_from(provenance, [bottom_up_, solve, boolean])

-module(reach, [Edge(A, B), Path(A, B)])

bottom_up_(Edge)
bottom_up_(Path)

Path(A, B) <- Edge(A, B)
Path(A, C) <- (Edge(A, B), Path(B, C))

Test("transitive closure under boolean") <- (
    FACTS is [(Edge("a", "b"), True), (Edge("b", "c"), True)],
    solve(boolean, FACTS, Path("a", "c"), [(_, True)])
)
```

## Status

Phase **P-2** — package skeleton + tag-threading bottom-up engine +
boolean / add_mult_prob / diff_add_mult_prob semirings + autograd flow
(PyTorch and JAX).

```python
import torch
from clausal.modules.provenance import diff_add_mult_prob, evaluate
# probs = softmax(cnn(images)), shape (N, 10), requires_grad=True
facts = [(Digit(img, v), probs[img, v]) for img in range(N) for v in range(10)]
answers = evaluate(diff_add_mult_prob, facts, SumDigits(0, 1, true_sum), module=mod)
loss = -torch.log(answers[0][1] + 1e-12)
loss.backward()      # gradients flow into probs and back into the CNN
```

See [`implementation_plans/PROVENANCE_SEMIRINGS.md`](../../implementation_plans/PROVENANCE_SEMIRINGS.md)
for the full plan including stratified negation + aggregation (P-3),
top_k_proofs (P-4), and dual-number semirings (P-5).
