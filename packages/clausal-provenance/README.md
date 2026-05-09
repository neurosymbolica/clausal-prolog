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

Phases **P-1**..**P-4** landed. The package ships:

- a stratified semi-naive bottom-up engine generic over a `Provenance`
  protocol, with `bottom_up_/1` and `pure_/1` registration goals;
- the `boolean` semiring (plain Datalog set semantics);
- `add_mult_prob` (independence-assumption probability) and
  `diff_add_mult_prob` (PyTorch / JAX-differentiable on tensors);
- stratified negation and `AggregateProvenance` with semiring-aware
  `count` / `sum` / `argmax`;
- `top_k_proofs(k)` (DNF lineage with k-truncated union, exact
  probabilities via inclusion-exclusion) and `diff_top_k_proofs(k)`
  with optional `torch.autograd.Function` / `jax.custom_vjp` bridges;
- in-source builtins `provenance.solve/4`, `aggregate/4`, `recover/3`
  and a Python-side `query()` helper.

```python
import torch
from clausal.modules.provenance import diff_add_mult_prob, query
# probs = softmax(cnn(images)), shape (N, 10), requires_grad=True
facts = [(Digit(img, v), probs[img, v]) for img in range(N) for v in range(10)]
answers = query(SumDigits(0, 1, true_sum), facts=facts, semiring=diff_add_mult_prob)
loss = -torch.log(answers[0][1] + 1e-12)
loss.backward()      # gradients flow into probs and back into the CNN
```

See [`docs/provenance.md`](docs/provenance.md) for the user guide and
[`implementation_plans/PROVENANCE_SEMIRINGS.md`](../../implementation_plans/PROVENANCE_SEMIRINGS.md)
for the full plan, including the deferred dual-number semirings (P-5).
