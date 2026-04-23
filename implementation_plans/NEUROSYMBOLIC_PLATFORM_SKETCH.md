# Neurosymbolic Platform — Clausal Implementation Sketch

Companion to `neurosymbolic_platform.md`. The motivation doc was
written without knowledge of Clausal, so most of its enumerated
"layers" already exist (engine, Python-functions-as-predicates,
SAT/SMT/CLP solvers as goals, SciPy ecosystem, term/goal expansion
as the homoiconic layer). This sketch covers only the genuinely
new work and why each phase is shaped the way it is.

## The novel work, in five phases

Numbering follows the V2/V3 convention used elsewhere in the roadmap.
PyTorch is the primary backend; JAX is added later when `vmap` is
actually load-bearing. The compilation target for synthesised
architectures is Flax NNX; PyTorch / HuggingFace is the import
target for pretrained models. References to "Prolog" in the
motivation doc become "Clausal" throughout.

### N-1  Neural predicate adapters

New modules `clausal/modules/torch.py` (and later `flax.py`),
matching the `clausal/modules/py/...` layout used for SciPy.
Register an `nn.Module` as a predicate using the adapter pattern
already exemplified by `_ScipySpecialPredicate`. Groundness-keyed
dispatch (V2-2) handles forward vs. check modes: inputs ground →
run forward pass; unbound outputs → bind to result. No gradients
yet.

*Rationale.* Falls out of an existing pattern; unlocks "call a
pretrained model as a goal" with no new machinery. PyTorch first
because the pretrained-model ecosystem lives there.

### N-2  Architecture compilation

Compile homoiconic architecture terms to Flax NNX modules. Reuse
term expansion (V3-2) for the term-to-term rewrite portion and
write a new pass `architecture_to_module.py` that walks a ground
architecture term and emits an `nnx.Module`.

```
architecture(transformer_block(dim_=512, heads_=8, ffn_mult_=4),
    sequential([
        residual(sequential([layer_norm, multi_head_attention(dim_=512, heads_=8)])),
        residual(sequential([layer_norm, ffn(dim_=512, mult_=4)]))
    ])
)
```

*Rationale.* This is the most Clausal-idiomatic phase: piggybacks on
the existing compiler, produces a legible demo (pattern-match and
synthesise a transformer variant, then compile it), and validates
the homoiconic claim before any differentiation work is committed.
Flax NNX is the target because its module model is a plain Python
object with explicit parameters and a forward function — the
cleanest sink for term-driven generation. (Imported PyTorch /
HuggingFace models stay on the PyTorch side via N-1; the two use
cases must remain distinct so the adapter story doesn't get muddled.)

### N-3  Differentiable forward within a predicate

Gradients flow via native autograd *inside* a single neural-predicate
call. Proof structure stays classical. The engine records which
bindings are differentiable tensors and preserves the autograd tape
across unifications that touch them.

*Rationale.* This is ~80% of the usability payoff for ~20% of the
research risk. It unlocks training on a loss that depends on the
proof's final bindings without requiring differentiation of the
search itself. End of the "promised" scope.

### N-4  Rule-weight learning  *(exploratory)*

Soft choice over clauses: each alternative clause gets a learnable
weight, and the forward pass is a weighted sum over alternatives.
Modifies `PredicateMeta._get_dispatch` to support weighted
alternatives.

*Rationale.* This is where the design crosses into DeepProbLog /
Scallop territory — a research bet, not an engineering slice. Park
it until a concrete workload demands it.

### N-5  `vmap`-batched proofs  *(speculative)*

Batch alternative unifications under `jax.vmap`. The trail,
groundness-keyed dispatch, and vmap interact in non-trivial ways
that have no published treatment.

*Rationale.* This is the only phase that genuinely needs JAX rather
than PyTorch. Defer until N-1..N-3 are load-bearing and there is a
performance ceiling that vmap would actually break through.

## What to build first

N-2 (architecture compilation). It lands entirely inside Clausal's
existing machinery (term expansion + a new compilation sink),
produces a sharp demo that validates the homoiconic claim, and
doesn't require committing to any differentiation research. N-1 is
a sibling that unblocks "call a pretrained model as a goal" and
can be built in parallel.

N-3 follows once N-1 and N-2 are stable enough to host a toy
training loop. N-4 and N-5 stay in the research-tickets bucket.
