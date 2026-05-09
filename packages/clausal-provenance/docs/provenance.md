# Clausal — Provenance (`provenance` module)

## Overview

The `provenance` module provides **provenance-tagged bottom-up Datalog**: a
peer evaluation strategy to SLG, where every derived fact carries a tag from
a chosen [semiring](#semirings). The same engine runs plain Boolean Datalog
(reachability, transitive closure), independence-assumption probabilistic
inference, top-k DNF lineage, and PyTorch / JAX-differentiable variants of
all of the above — gradients flow from a query's answer probabilities back
into a perception model's parameters.

```clausal
-import_from(provenance, [bottom_up_, solve, boolean, add_mult_prob])

-module(reach, [Edge(A, B), Path(A, B)])

bottom_up_(Edge)
bottom_up_(Path)

Path(A, B) <- Edge(A, B)
Path(A, C) <- (Edge(A, B), Path(B, C))

Test("reachability under boolean") <- (
    FACTS is [(Edge("a", "b"), True), (Edge("b", "c"), True)],
    solve(boolean, FACTS, Path("a", "c"), [(_, True)])
)
```

The module is a separate distribution; install it with:

```bash
pip install clausal-provenance         # boolean + add_mult_prob
pip install clausal-provenance[torch]  # adds diff_add_mult_prob, diff_top_k_proofs
pip install clausal-provenance[jax]    # JAX variant of the same
pip install clausal-provenance[all]    # both frameworks
```

---

## When to use bottom-up

Bottom-up is the right choice when the fact base is large and ground
(perception output, database rows, sensor readings), the query is "compute
the closure" rather than "is there a derivation of *this* term", and you
need tags / probabilities / provenance — not just a Boolean answer.

For goal-directed search over structured terms (parsing, term rewriting,
meta-interpretation), use [tabling](../../../docs/tabling.md) instead.
The two compose: a `-bottom_up` rule body can call a `-pure`-declared
tabled predicate (the SCC analysis treats it as a leaf), and a top-down
predicate can call `provenance.solve/4` for a sub-query that needs
semiring tags.

---

## Anatomy of a provenance program

A program has three pieces:

1. **Rules** — ordinary Clausal `<-` rules whose head predicates are
   declared bottom-up. Variables in the head must be bound by the body.
2. **Tagged facts** — a list of `(ground_term, tag)` pairs supplied at
   solve time, either inline in `.clausal` source (typically tests) or
   from Python (typically training data).
3. **Semiring** — a value, not a class, passed per call. The semiring
   chooses what tags mean (`bool`, `float`, `Tensor`, DNF formula, …).

```clausal
-import_from(provenance, [bottom_up_, solve, boolean, add_mult_prob])

-module(mnist_sum, [Digit(IMG, V), SumDigits(A, B, T)])

bottom_up_(Digit)
bottom_up_(SumDigits)

SumDigits(IMG_A, IMG_B, TOTAL) <- (
    Digit(IMG_A, A),
    Digit(IMG_B, B),
    TOTAL == A + B,
)

Test("boolean: enumerate possible sums") <- (
    FACTS is [
        (Digit(0, 3), True),
        (Digit(0, 4), True),
        (Digit(1, 5), True),
    ],
    solve(boolean, FACTS, SumDigits(0, 1, T), R),
    length(R, 2)
)
```

Three things to notice:

- **`bottom_up_(Digit)`** registers `Digit/2` for bottom-up evaluation.
  The same fact base must consistently be tagged: either every `Digit`
  fact carries a tag, or none do.
- **`==` (not `is`)** binds `TOTAL`. Clausal's `is` is *structural unify*,
  not arithmetic eval — it would fail here. `==` is `ArithEq`.
- **No `,` after `bottom_up_(Digit)`** — a trailing comma at top level
  turns the directive into a clause-with-empty-body and fails. Keep each
  registration on its own line.

---

## Semirings

A semiring is a `Provenance` instance — a value with `zero`, `one`, `add`
(`⊕`, alternative derivations), `mult` (`⊗`, body conjunction), and
optionally `negate`, `discard`, `tagging_fn`, `recover_fn`. Pick one per
call:

| Name | Tag type | What it computes | Differentiable? |
|---|---|---|---|
| `boolean` | `bool` | Plain Datalog set semantics | — |
| `add_mult_prob` | `float ∈ [0, 1]` | Independence-assumption probability | — |
| `diff_add_mult_prob` | `Tensor` (torch / jax) | Same algebra, on tensors | yes (autograd) |
| `top_k_proofs(k)` | DNF over input ids | Top-k highest-prob proofs, exact via inclusion-exclusion | — |
| `diff_top_k_proofs(k)` | DNF over input tensors | Top-k proofs, autograd through I-E | yes |

### `boolean` — plain Datalog

`⊕ = or`, `⊗ = and`. Tags are `True` / `False`. The engine drops
`False`-tagged tuples from the relation under set semantics, so
`not P(x)` records nothing instead of recording an entry for the head
with tag `False`.

```clausal
FACTS is [(Edge("a", "b"), True), (Edge("b", "c"), True)],
solve(boolean, FACTS, Path("a", "c"), [(_, True)])
```

`boolean` is also the engine smoke test: any program that runs under any
other semiring must run under `boolean` and produce a structurally
identical answer set.

### `add_mult_prob` — independence-assumption probability

`⊕ = clip(a + b − a·b, 0, 1)`, `⊗ = a · b`. Tags are floats in `[0, 1]`.
Treats alternative derivations as independent events:

```clausal
Test("add_mult_prob: confident pair multiplies cleanly") <- (
    FACTS is [
        (Digit(0, 3), 0.7),
        (Digit(1, 5), 0.9),
    ],
    solve(add_mult_prob, FACTS, SumDigits(0, 1, 8), R),
    R == [(SumDigits(0, 1, 8), 0.63)]
)
```

The tag `0.63 = 0.7 · 0.9`: there's exactly one proof of
`SumDigits(0, 1, 8)` and `⊗` multiplies the two confidences.

When the same input fact appears in multiple proofs of one tuple,
`add_mult_prob` over-counts (treats them as independent when they share
inputs). For exact probabilities under a probabilistic-database
semantics, use `top_k_proofs` instead.

### `diff_add_mult_prob` — differentiable, the **Tier 1 ML payoff**

Same algebra as `add_mult_prob` but tags are PyTorch tensors or JAX
arrays. `⊕` and `⊗` are tensor operations; autograd traces through them
naturally. No custom `autograd.Function` needed at this tier — the
operations are smooth on the open `[0, 1]` interval.

```python
import torch
from clausal.modules.provenance import diff_add_mult_prob, query
from mnist_sum import Digit, SumDigits

# probs: shape (2, 10), requires_grad=True — softmax(cnn(images))
facts = [(Digit(img, v), probs[img, v]) for img in (0, 1) for v in range(10)]

answers = query(SumDigits(0, 1, T_),
                facts=facts,
                semiring=diff_add_mult_prob)
# [(SumDigits(0, 1, 0), tensor), (SumDigits(0, 1, 1), tensor), …]

correct = next(t for ((_, _, total), t) in answers if total == true_sum)
loss = -torch.log(correct + 1e-12)
loss.backward()       # → probs.grad → cnn.parameters().grad
```

Mixing torch and jax tags in one `solve` call is an error — the engine
detects framework from the first tagged fact and rejects mixed input.

### `top_k_proofs(k)` — DNF lineage, exact probabilities

Tags are DNF formulas over input literals. Each input fact is allocated a
fresh integer id; a derived tuple's tag is the disjunction of conjunctions
of input literals that prove it. The `recover_fn` reduces a DNF to a
probability via inclusion-exclusion, which is exact (no
shared-input over-counting) but exponential in `k`.

```python
from clausal.modules.provenance import top_k_proofs, query

s = top_k_proofs(k=3)            # ← factory, fresh per solve
answers = query(SumDigits(0, 1, T_), facts=facts, semiring=s)
```

**The factory is mandatory.** `top_k_proofs(k=...)` returns a *fresh*
stateful instance every call. Each instance owns the `input_id → tag`
mapping that `tagging_fn` populates as it allocates ids. Sharing one
instance across calls would conflate inputs from different solves.

`k` controls the truncation: only the `k` highest-probability proofs
are kept after each `⊕`. Higher `k` → tighter approximation, slower
inclusion-exclusion. `k = 3` is a reasonable default; the field standard
for neurosymbolic learning is `k = 3`–`5`.

`top_k_proofs` is `AggregateProvenance`: it supports `aggregate_count`
(expected count under independence), `aggregate_sum` (expected sum),
and `aggregate_argmax`.

### `diff_top_k_proofs(k)` — differentiable top-k

Inherits the DNF carrier from `top_k_proofs` unchanged — proof selection
ranks by detached scalar probability. The `recover_fn` recomputes the
inclusion-exclusion sum on the original input *tensors*, so PyTorch /
JAX autograd traces backward through the I-E expression.

```python
from clausal.modules.provenance import diff_top_k_proofs, query

answers = query(SumDigits(0, 1, T_),
                facts=facts,
                semiring=diff_top_k_proofs(k=3))
correct = next(t for ((_, _, total), t) in answers if total == true_sum)
loss = -torch.log(correct + 1e-12)
loss.backward()
```

For a DNF that is decoded many times with different input tensors, the
opt-in `bridges/torch_bridge.py` and `bridges/jax_bridge.py` provide an
explicit `torch.autograd.Function` / `jax.custom_vjp` path that computes
the sparse Jacobian once and reuses it on `backward`. Same value and
same first-order gradient as the implicit path.

---

## Registration: `bottom_up_/1` and `pure_/1`

Bottom-up evaluation operates on **ground tuples** in a relation; rule
bodies must be **pure, monotonic, and deterministic** — see
[`docs/purity.md`](../../../docs/purity.md). Two registration goals
declare the engine's view of your predicates:

```clausal
-import_from(provenance, [bottom_up_, pure_])

bottom_up_(SumDigits)       # SumDigits/3 is evaluated bottom-up
pure_(SafeColor)            # SafeColor/2 may be called from a -bottom_up body
```

`bottom_up_(P)` and `pure_(P)` are not directives — they're **module-load
goals**: the parser turns the line into a Python call executed at module
load time, which sets a flag on the predicate's `PredicateMeta` class.
The trailing underscore matches existing Clausal naming for "registration
predicate that doubles as a directive."

A future small core hook would let us promote these to true `-bottom_up`
/ `-pure` directives. Strictly cosmetic; the load-time form behaves
identically.

### Default-pure builtins

Standard P-M-D builtins are implicitly pure — no `pure_/1` needed:

- Arithmetic: `is`, `succ`, `plus`, `abs`, `sign`, `min`, `max`, `gcd`, `==`, `!=`, `<`, `>`, `=<`, `>=`.
- Term inspection: `var`, `nonvar`, `ground`, `atom`, `number`, `length`, `functor`, `arg`, `copy_term`.
- Pure list builtins: `member`, `memberchk`, `append`, `nth0`, `nth1`, `last`, `reverse`, `msort`, `sort`.

Anything not on the whitelist must be marked explicitly. Calling an
unmarked impure predicate from a `-bottom_up` body raises `PurityError`
naming the offending callee.

### Forbidden in bottom-up bodies

`assertz`, `retract`, dynamic predicates, I/O, CLP(FD) labelling,
CLP(SAT) solving, `dif/2`, attributed-variable propagation. The purity
discipline rejects them at registration time.

---

## Entry points

### `solve/4` — the in-source builtin

```clausal
solve(+Semiring, +Facts, +Goal, -Result)
```

`Semiring` is a Provenance instance. `Facts` is a list of `(GroundTerm, Tag)`
pairs. `Goal` is an ordinary goal whose head predicate is `-bottom_up`.
`Result` unifies with the list of `(GroundFact, Tag)` answers — same shape
across semirings, only the tag type changes.

```clausal
solve(boolean, FACTS, Path("a", DST), R)
```

There is no `provenance.fact/2` posting builtin — facts always pass as a
list. This keeps `solve/4` pure-functional from the caller's view; no
hidden dependency on prior `assertz` calls.

### `aggregate/4` — semiring-aware aggregation

```clausal
aggregate(+Semiring, +Op, +TaggedList, -Result)
```

`Op` is `"count"`, `"sum"`, or `"argmax"`.

| Semiring | `count` | `sum` | `argmax` |
|---|---|---|---|
| `boolean` | cardinality | plain Σ over True-tagged | max value among True-tagged |
| `add_mult_prob` | `Σ p_i` (expected count) | `Σ v_i · p_i` (expected sum) | `(v*, p*)` — value with max p |
| `diff_add_mult_prob` | tensor `Σ p_i` | tensor `Σ v_i · p_i` | `(v*, t*)` — argmax detached, tag's gradient preserved |
| `top_k_proofs(k)` | `Σ recover_fn(t_i)` (I-E per term) | `Σ v_i · recover_fn(t_i)` | `(v*, t*)` |

```clausal
Test("aggregate count under add_mult_prob = expected count") <- (
    aggregate(add_mult_prob, "count", [0.3, 0.5, 0.2], EXPECTED),
    EXPECTED < 1.0000000001,
    EXPECTED > 0.9999999999
)
```

### `recover/3` — apply `recover_fn` explicitly

```clausal
recover(+Semiring, +InternalTag, -OutputTag)
```

Usually called automatically inside `solve/4`; useful when threading the
internal tag through multiple `solve` calls or inspecting the DNF
carrier directly.

### `query()` — Python-side primary API

```python
from clausal.modules.provenance import query

answers = query(goal, facts=facts, semiring=...)
# → list[(ground_term, tag)]
```

This is the primary entry point for neurosymbolic workloads: facts come
from a perception model's output (a tensor), and the `.clausal` source
holds only the rules and signatures. `query()` accepts an optional
`module=` kwarg if the goal's predicate class doesn't carry an inferable
home module.

---

## Stratified negation

Negation is supported as long as the dependency graph is **stratified** —
no SCC contains both a positive and a negative edge. The engine builds
the graph at registration time and rejects cyclic negation with a clear
error message naming the offending predicates.

```clausal
-module(network, [Edge(A, B), Block(N), Reachable(N), Allowed(N)])

bottom_up_(Edge)
bottom_up_(Block)
bottom_up_(Reachable)
bottom_up_(Allowed)

Reachable(X) <- Edge(_, X)

Allowed(X) <- (
    Reachable(X),
    not Block(X),
)

Test("certain block excludes via 1 - 1.0 = 0") <- (
    FACTS is [
        (Edge("a", "b"), 0.7),
        (Block("b"), 1.0),
    ],
    solve(add_mult_prob, FACTS, Allowed("b"), [])
)
```

`Allowed` depends positively on `Reachable` and negatively on `Block`;
these live in lower strata and saturate before `Allowed` runs. Under
`add_mult_prob`, `negate(1.0) = 0.0`, so the `Allowed("b")` candidate is
multiplied by `0` and pruned via `discard`.

---

## Showcase: MNIST-Sum

The canonical neurosymbolic benchmark. Two MNIST images go in; the
predicted sum (0..18) comes out; loss is computed against the true
sum; gradients train a CNN that has never seen image-level digit labels.

```clausal
# packages/clausal-provenance/tests/fixtures/mnist_sum.clausal
-import_from(provenance, [bottom_up_, solve, boolean, add_mult_prob])

-module(mnist_sum, [
    Digit(IMAGE_ID, VALUE),
    SumDigits(IMAGE_A, IMAGE_B, TOTAL),
])

bottom_up_(Digit)
bottom_up_(SumDigits)

SumDigits(IMG_A, IMG_B, TOTAL) <- (
    Digit(IMG_A, A),
    Digit(IMG_B, B),
    TOTAL == A + B,
)
```

```python
import torch
from clausal import load_clausal_module
from clausal.modules.provenance import diff_add_mult_prob, query

mod = load_clausal_module("mnist_sum.clausal")
Digit, SumDigits = mod.Digit, mod.SumDigits

cnn = MyCnn()                                    # outputs logits over 10 digits
opt = torch.optim.Adam(cnn.parameters(), lr=1e-3)

for image_a, image_b, true_sum in train_loader:
    probs = torch.softmax(
        cnn(torch.stack([image_a, image_b])), dim=-1)   # (2, 10), grad
    facts = [
        (Digit(img, v), probs[img, v])
        for img in (0, 1)
        for v in range(10)
    ]

    answers = query(SumDigits(0, 1, T_),
                    facts=facts,
                    semiring=diff_add_mult_prob,
                    module=mod)
    correct = next(t for ((_, _, total), t) in answers if total == true_sum)
    loss = -torch.log(correct + 1e-12)

    opt.zero_grad()
    loss.backward()       # propagates through facts → probs → CNN
    opt.step()
```

Three things this exercises end-to-end:

1. **Clausal terms throughout.** No string-passing, no parallel AST.
2. **Tag = tensor.** No marshalling at any boundary; PyTorch autograd
   traces straight through `add` and `mult`.
3. **Default-pure builtins.** `==` (the rule's only callback into Clausal)
   is on the engine's whitelist, so no `pure_/1` annotation is needed.

For tighter probabilities — when several digit-pair combinations sum to
the same target and `add_mult_prob`'s independence assumption
over-counts — swap `diff_add_mult_prob` for `diff_top_k_proofs(k=3)`.
The DNF carrier records *which* input facts each proof uses, and
inclusion-exclusion produces the exact joint probability.

---

## Errors

| Error | Raised by | Meaning |
|---|---|---|
| `NonGroundTupleError` | engine | A rule produced a head tuple whose variables aren't all bound. The error names the rule, the tuple, and the unbound variable(s). |
| `PurityError` | engine | A `-bottom_up` rule body called a predicate that is neither default-pure nor explicitly marked `pure_/1`. Points at [`docs/purity.md`](../../../docs/purity.md). |
| `StratificationError` | `stratify` | The dependency graph contains an SCC with both positive and negative edges (cyclic negation). The error names the predicates in the offending SCC. |

All three fire at registration / fixpoint time, not silently — the
failure mode is local and the message points at the bug.

---

## See also

- [`docs/tabling.md`](../../../docs/tabling.md) — SLG, the peer top-down
  evaluation strategy. Compose: `-bottom_up` bodies can call
  `-pure`-marked tabled predicates.
- [`docs/purity.md`](../../../docs/purity.md) — the
  monotonic-pure-deterministic invariant the foreign-predicate FFI
  enforces.
- [`docs/constraints.md`](../../../docs/constraints.md) — peer constraint
  domains (CLP(FD), CLP(B), CLP(ℝ), CLP(ℚ), CLP(SAT), Z3). These do not
  compose with bottom-up bodies — `-bottom_up` rules cannot post
  attributed-variable constraints.
- [`implementation_plans/PROVENANCE_SEMIRINGS.md`](../../../implementation_plans/PROVENANCE_SEMIRINGS.md)
  — full implementation plan, semiring catalogue, and the Issues section
  recording design decisions made during the build.

### References

- Green, Karvounarakis & Tannen. *Provenance Semirings.* PODS 2007.
- Manhaeve et al. *DeepProbLog.* NeurIPS 2018.
- Huang et al. *Scallop.* NeurIPS 2021. Li et al. *Scallop: A Language
  for Neurosymbolic Programming.* PLDI 2023.
