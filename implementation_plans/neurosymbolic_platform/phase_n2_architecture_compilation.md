# Phase N-2 — Architecture compilation

Compile homoiconic architecture terms — `sequential([...])`,
`residual(...)`, `multi_head_attention(dim_=512, heads_=8)`, and
compositions thereof — to concrete Flax NNX modules. The compilation
pipeline reuses term expansion (V3-2) for the term-to-term rewrites
(library-level architecture families expand to primitive building
blocks) and adds a new pass, `architecture_to_module.py`, that
walks a ground architecture term and emits an `nnx.Module`.

This is the phase that most directly validates the homoiconic
claim from the motivation doc: the *same* object that the engine
unifies, pattern-matches, and backtracks over is also the object
that compiles to runnable neural code.

---

## Rationale

This is the most Clausal-idiomatic phase:
- It piggybacks on the existing compiler (term expansion is already
  how V3-2 rewrites module-level terms).
- It produces a legible demo — pattern-match and synthesise a
  transformer variant, then compile it.
- It validates homoiconicity before any differentiation work
  is committed, so if the experience is bad, we find out cheaply.

Flax NNX is the target because its module model is a plain Python
object with explicit parameters and a forward function — the cleanest
sink for term-driven generation. See the sketch,
`../NEUROSYMBOLIC_PLATFORM_SKETCH.md:49`.

Pretrained imports stay on the PyTorch side via N-1. Don't let
the two use cases muddle — N-2 produces NNX modules from terms;
N-1 wraps PyTorch modules as predicates.

---

## Scope

### In scope
- `clausal/modules/py/flax_nnx.py` (name TBD): adapter module that
  exposes primitive Flax NNX layers as Clausal term constructors —
  `layer_norm`, `linear(in_=..., out_=...)`, `multi_head_attention(...)`,
  `conv2d(...)`, `relu`, `sigmoid`, `dropout(p_=...)`. These are
  pure term constructors (no network built yet); they exist so users
  can write architecture terms in `.clausal` files.
- `clausal/logic/architecture_to_module.py`: the compilation pass.
  Walks a ground architecture term, resolves combinators (`sequential`,
  `residual`, `parallel`, `branch`), recurses into primitive layer
  terms, and emits a single `nnx.Module` instance.
- `compile_architecture/2` builtin: `compile_architecture(ARCH_TERM, MODULE_)`
  is the Clausal-level entry point. Succeeds if the term is ground
  and compiles; fails otherwise.
- Library of common architecture families as term-expansion rules:
  `transformer_block/3`, `resnet_block/2`, `ffn/2`, `mlp/3`. Live
  in `clausal/examples/architectures.clausal` (not a core module —
  start as examples, promote if stable).
- Showcase: a `.clausal` file that defines a transformer variant
  as a term, unifies against a pattern ("find every residual-wrapped
  attention block"), rewrites via term expansion, and compiles.

### Out of scope (intentionally)
- Gradients, training. N-3 and beyond.
- Importing Flax NNX modules as predicates. That's the dual of
  N-1 — possible future work but not required for this phase's
  claim.
- Shape inference at compile time. Flax NNX handles shape at first
  call (lazy init); N-2 inherits that posture. Compile-time shape
  checking is deferred (see `../pytorch/overview.md:241` for the
  "shape-as-constraints" note).
- Hyperparameter search over architectures. That's a downstream
  use case *enabled* by this phase; it doesn't belong in the phase
  plan itself.

### Assumes (prerequisites)
- **V3-2 term expansion** —
  `clausal/logic/term_expansion.py`, `run_term_expansion()`.
  Architecture-family rules (`transformer_block/3` etc.) are
  `TermExpansion/4` rules.
- **V3-1 module system** — for `-import_from(py.flax_nnx, ...)`.
- Optional: **N-1** — not a hard prerequisite, but once N-1 lands,
  compiled NNX modules can be wrapped as neural predicates and the
  round-trip ("synthesise → compile → call as a goal") works.

---

## File layout

```
clausal/modules/py/flax_nnx.py              # new: primitive layer constructors
clausal/modules/flax_nnx.py                 # new: re-export alias
clausal/logic/architecture_to_module.py     # new: the compilation pass
clausal/logic/builtins/architecture.py      # new: compile_architecture/2 builtin
clausal/logic/builtins/__init__.py          # modify: register the new builtin
clausal/examples/architectures.clausal      # new: transformer_block, resnet_block, etc.
clausal/examples/compile_transformer.clausal  # new: showcase
tests/test_architecture_compilation.py      # new: unit tests per combinator + end-to-end
tests/fixtures/arch_transformer.clausal     # new: transformer-compilation fixture
```

---

## Term language

The architecture term language is small. Start with these combinators:

| Combinator | Signature | Semantics |
|---|---|---|
| `sequential/1` | `sequential([L1, L2, ..., Ln])` | Pipeline; output of L_i feeds L_(i+1) |
| `residual/1` | `residual(SubArch)` | `y = x + SubArch(x)` |
| `parallel/1` | `parallel([Branches])` | Run branches in parallel; return tuple |
| `branch/2` | `branch(Predicate, Arch1, Arch2)` | Runtime branch (rarely useful; include for completeness) |
| `lambda/2` | `lambda(Params, Body)` | Inline computation; body uses PyThunk `++()` |

And these primitive leaf layers (each a Clausal term constructor
in `flax_nnx.py`):

| Leaf | Constructor | NNX class |
|---|---|---|
| `linear(in_=I, out_=O)` | `Linear` | `nnx.Linear` |
| `layer_norm` | `LayerNorm` (no args in simple form) | `nnx.LayerNorm` |
| `multi_head_attention(dim_=D, heads_=H)` | `MultiHeadAttention` | `nnx.MultiHeadAttention` |
| `conv2d(in_=I, out_=O, kernel_=K)` | `Conv2d` | `nnx.Conv` with 2D shape |
| `ffn(dim_=D, mult_=M)` | `FFN` | Composite (linear → gelu → linear) |
| `dropout(p_=P)` | `Dropout` | `nnx.Dropout` |
| `relu`, `gelu`, `sigmoid`, `tanh` | atoms, no args | `nnx.relu` etc. |

The showcase term from the sketch
(`../NEUROSYMBOLIC_PLATFORM_SKETCH.md:41`) should compile verbatim:

```clausal
architecture(transformer_block(dim_=512, heads_=8, ffn_mult_=4),
    sequential([
        residual(sequential([layer_norm, multi_head_attention(dim_=512, heads_=8)])),
        residual(sequential([layer_norm, ffn(dim_=512, mult_=4)]))
    ])
)
```

---

## Compilation pass — `architecture_to_module.py`

Signature:
```
def compile_architecture(term, *, rng_key=None) -> nnx.Module: ...
```

Invariants:
- `term` must be fully ground (no unbound `Var`). Raise `LogicException`
  with the first non-ground subterm on failure; the builtin wrapper
  translates this into predicate failure.
- Term expansion runs *before* the walker sees the term. The walker
  only handles the combinators and primitive leaves enumerated above.
- The walker is a simple recursive pattern match on the term's
  predicate class. One case per combinator, one case per primitive.
- Output is a single `nnx.Module` whose `__call__` implements the
  architecture. Combinators produce composed modules using NNX's
  own composition primitives where they exist (`nnx.Sequential`),
  or a small generated subclass where they don't (`residual`,
  `parallel`).

Non-invariants (things the pass is *not* responsible for):
- Parameter initialisation. NNX handles that lazily on first forward.
- Weight sharing across subterms. Emergent from term identity:
  if two subterms are literally the same object, they share; if
  not, they don't. Document this explicitly so users don't expect
  syntactic equality to imply sharing.
- Pretty-printing the compiled module. Users can inspect
  `module.tabulate()` via Flax's own tools.

---

## Design notes

- **Term expansion ordering.** Architecture families (`transformer_block/3`)
  are `TermExpansion/4` rules, expanded at module load time. The
  compilation pass never sees them — only the primitive combinators
  and leaves. This is the same posture V3-2 already takes for
  other term-level rewrites.
- **Parameter inspection.** Once compiled, the module's parameters
  are visible via the usual PyTorch-wrapper predicates from the
  `pytorch/` track (adapted for NNX — `nnx_parameter/2` etc., if
  someone wants them). That's a separate plan; N-2 just emits the
  module.
- **Pattern-matching on architectures.** This is the *point* — that
  Clausal can unify against `architecture(_, sequential([..., residual(_), ...]))`
  and backtrack to find every residual-wrapped subterm. That works
  automatically once architecture terms are ordinary Clausal terms;
  N-2 just has to make sure the terms are sensible to match against.
  Don't invent a separate "architecture AST" type; the existing
  `Compound` / predicate-class terms are fine.
- **JAX dependency.** Flax pulls in JAX as a transitive dep. That's
  fine — this is the first Clausal module that requires JAX, but
  N-5 will need it too, and users who don't install JAX simply
  can't import `py.flax_nnx` (same pattern as the SciPy wrappers
  requiring `scipy`).
- **Error messages.** A compilation failure ("`residual` expects a
  single sub-architecture, got list") should include the offending
  subterm's `term_str` representation. Reuse `term_str` from
  `clausal/terms.py`.

---

## Success criteria

- `tests/test_architecture_compilation.py` has ≥ 30 tests covering:
  each primitive leaf compiles, each combinator compiles (sequential,
  residual, parallel), combinations compose, shape-correct inputs
  flow through, ground-term requirement is enforced, helpful error
  on non-ground terms, the sketch's transformer_block example
  compiles and runs on a synthetic input.
- `clausal/examples/compile_transformer.clausal` end-to-end:
  - Defines `transformer_block/3` as a term-expansion rule.
  - Uses it to build a small model as a term.
  - Pattern-matches to find all `residual(...)` subterms.
  - Compiles the full term to an `nnx.Module`.
  - Runs one forward pass on a synthetic tensor.
  - The whole file reads as one legible program, not a tutorial.
- The sketch's claim "pattern-match and synthesise a transformer
  variant, then compile it" (`../NEUROSYMBOLIC_PLATFORM_SKETCH.md:51`)
  is literally demonstrable by running that example.

---

## Issues

_To be populated during implementation._
