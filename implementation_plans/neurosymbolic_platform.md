# A Neurosymbolic Platform: Prolog-in-Python with Homoiconic Neural Architectures

## Motivation

The current state of machine learning infrastructure has a gap that nobody has cleanly filled. On one side, we have mature symbolic systems — Prolog, Datalog, SAT/SMT solvers, theorem provers — that excel at structured reasoning, backtracking search, and first-order inference, but are isolated from the statistical methods that dominate modern AI. On the other side, we have the Python numerical stack — JAX, PyTorch, Keras, Flax — which has conquered perception and pattern recognition but lacks any native notion of logical structure, rule learning, or verifiable inference.

The usual response is a pipeline: neural network produces features, symbolic system consumes them. This is unsatisfying because the coupling is loose. Gradients don't flow across the boundary, constraints don't propagate backward into perception, and the symbolic structure can't be learned jointly with the neural components. Systems like DeepProbLog, Scallop, and PyReason have each addressed pieces of this, but none offers the full combination of a mature logic programming language, the entire Python scientific ecosystem, and end-to-end differentiability.

This document outlines the motivation for a platform that closes this gap: a Prolog implementation in Python where neural networks are first-class predicates, where JAX and PyTorch are integrated as computational backends, and where the homoiconic nature of Prolog is exploited to make neural architectures themselves manipulable as logical terms.

## What the Platform Is

At its core, the platform is a Prolog runtime written in Python. It provides first-order predicate logic with unification, backtracking, and SLD resolution. What distinguishes it from conventional Prolog is three additional layers of integration.

The first is that arbitrary Python functions can be declared as predicates. This is table stakes for any modern logic language embedded in a host language, but the scope is broader here: the full Python scientific ecosystem — NumPy, SciPy, scikit-learn, NetworkX, SymPy, the SAT and SMT solvers — is available as declarative primitives. Constraint solvers become goals that can be invoked, satisfied, and backtracked over just like any other predicate.

The second is deep integration with JAX and PyTorch as differentiable computational substrates. Neural networks are not external black boxes called from Prolog; they are predicates whose satisfaction involves differentiable computation, and gradients flow through the proof structure itself. A proof tree becomes a computation graph, and training can optimize both the neural components and the logical structure simultaneously.

The third is the exploitation of Prolog's homoiconicity — the property that programs and data share the same representation — to make neural architectures themselves manipulable objects. A ResNet block, a Transformer layer, or an entire model can be expressed as a Prolog term, reasoned about by unification and pattern matching, transformed by term rewriting, and compiled on demand to a concrete PyTorch or Flax module.

## Why Differentiable Logic Programming Matters

Before discussing the homoiconicity angle, it's worth being specific about where end-to-end differentiable logic programming actually pays off, because it's overkill for many problems. If your logic program is fixed and merely calls neural predicates as oracles, you don't need differentiable resolution — train the neural bits separately and plug them in. The full machinery earns its keep when one of three conditions holds: the structure of the logic program itself has learnable parameters, credit needs to flow across multiple neural predicates within a single proof, or you're doing weak supervision where only the final answer is labeled.

Concrete domains where this combination wins include rule learning and theory induction (learning interpretable first-order rules from data, subsuming classical ILP), knowledge graph completion with learnable logical structure, semantic parsing trained only on question-answer pairs, neuro-symbolic visual reasoning over compositional queries, weakly supervised structured prediction (math word problems, program synthesis), constraint-respecting generative models (valid molecules, type-correct code), and meta-learning of inference strategies where the search heuristics themselves are learned alongside the domain theory.

The common thread is that each requires tight coupling — proofs whose structure and whose neural components are jointly optimized — not the pipeline architecture that external integrations of Prolog and PyTorch can provide.

## The Homoiconicity Insight

Neural architectures are overwhelmingly compositional tree structures. A ResNet is a tree of blocks. A Transformer is a stack of attention-plus-FFN units. A U-Net is a symmetric encoder-decoder tree. A mixture-of-experts layer is a routing tree over subnetworks.

Current practice expresses these trees as imperative Python code — constructor calls that produce stateful objects. This has several costs that are rarely articulated because the community has normalized them. You cannot easily analyze an architecture without instantiating and running it. You cannot pattern-match structurally ("find every place where a residual connection wraps a normalization layer"). You cannot synthesize architectures as data and compile them to executables in the same language. And every neural architecture search framework ends up reinventing a half-formed DSL because Python code is not tractable as data.

In a homoiconic logic language, an architecture is just a term. The same object that will be executed (by compiling to a Keras, Flax, or PyTorch module and training it) is also the object that can be queried, mutated, pattern-matched, unified against, proven things about, and searched over. A sketch of what this looks like:

```prolog
architecture(resnet_block(Width),
    add(sequential([
            conv2d(Width, kernel(3,3)),
            batch_norm,
            relu,
            conv2d(Width, kernel(3,3)),
            batch_norm
        ]),
        identity)).

architecture(transformer_block(Dim, Heads, FFNMult),
    sequential([
        residual(sequential([layer_norm, multi_head_attention(Dim, Heads)])),
        residual(sequential([layer_norm, ffn(Dim, FFNMult)]))
    ])).
```

Both terms are executable (compile to concrete neural modules) and inspectable (unify against patterns, extract subterms, check properties). This is a genuine capability that does not cleanly exist anywhere in the current ML stack.

## What the Homoiconicity Unlocks

Several categories of work become dramatically more natural when architectures are terms rather than imperative code.

Declarative architecture search becomes idiomatic. You write logical constraints — depth bounds, required components, parameter count ceilings, residual-connection density, memory budgets — and the logic engine enumerates architectures satisfying them by ordinary backtracking. This is what NAS frameworks like DARTS, ENAS, and their descendants simulate using bespoke controller networks or gradient tricks; in a Prolog setting it falls out of the basic evaluation model.

Pattern-based refactoring of architectures becomes a term-rewriting problem. Transformations like "replace every `batch_norm; relu` with `relu; batch_norm`" or "wrap every attention block in a residual connection" or "promote every fp32 layer to bf16 where safe" are trivial rewrites on terms, compared to the ad-hoc AST manipulation or framework-specific graph rewriting they require today.

Architecture families can be expressed as predicates. A `transformer_block/3` predicate expands to the right term structure. A `gpt_style_model/3` predicate calls it recursively. A `mixture_of_experts/2` predicate wraps a base architecture in routing. These compose and can be queried — "is this architecture a transformer variant?" becomes unification against a family template.

Shape and type safety become proof obligations. Constraints like "this layer's output shape must match the next layer's input expectation" are encoded as logical goals, and shape inference becomes proof search. Invalid architectures fail to unify rather than throwing runtime errors halfway through training.

Differentiable architecture search falls out naturally. Because the platform already supports differentiable proofs, soft choices over architectural variants — where a rule's weight determines how much each candidate layer contributes — become a straightforward use of the same mechanism. What DARTS implements as a custom framework becomes a few lines of declarative logic.

Architectures become version-control-friendly and human-readable. A diff between two model variants is a diff between terms, not a diff between two Python files that might happen to produce different computation graphs at runtime.

## The Role of Keras, JAX, PyTorch, and Flax

The numerical backends serve different purposes in this design and should not be conflated.

JAX provides the computational substrate where this approach shines hardest. Proof search is embarrassingly parallel across alternative unifications and rule choices, and `jax.vmap` combined with `jax.jit` makes it possible to batch alternative proof branches and compile them to efficient GPU or TPU code. This is the key technical lever that makes differentiable Prolog competitive with bespoke neural architectures on performance.

PyTorch provides the dominant neural ecosystem. The vast majority of pretrained models, research code, and production serving infrastructure lives in PyTorch, and the platform must support importing arbitrary `torch.nn.Module` instances as predicates to be useful.

Flax and particularly the newer NNX API provide the most natural compilation target from Prolog terms, because Flax modules are essentially just Python objects with explicit parameters and a forward function. This maps cleanly onto what a compiled term should produce.

Keras 3 occupies a specific niche. The historical Keras — the TensorFlow-only high-level API — is not where modern research happens. But Keras 3, rewritten in late 2023, is a different product: a multi-backend framework that runs on JAX, TensorFlow, or PyTorch by setting an environment variable. Keras 3 is relevant to this platform in two ways. It is a useful import format, since users with existing Keras models should be able to wrap them as predicates. And its `keras.ops` namespace provides a backend-agnostic NumPy-like API that can be used when defining custom differentiable predicates. However, Keras is probably not the primary compilation target for homoiconic architectures, because its `Sequential`/`Functional`/`Model` abstractions impose a lifecycle (build, compile, fit) that fights the more flexible module model needed when generating architectures from logical terms.

The guiding principle is that the platform targets the lowest sensible abstraction for compilation (Flax NNX or raw PyTorch modules) while supporting the higher-level abstractions (Keras layers, Hugging Face models) as importable predicates.

## High-Level Structure

The platform decomposes into several layers.

At the base is a Prolog engine written in Python. It provides unification, SLD resolution with backtracking, a clause database, standard built-in predicates, and the ability to declare Python functions as predicates. This layer is largely conventional and could be built on existing work (PySwip, Pyke, or a fresh implementation tuned for the integrations above).

Above this sits the neural predicate layer. This is where Python functions that happen to involve differentiable computation are registered as predicates, with metadata describing their parameters, shapes, and gradient behavior. A neural predicate's satisfaction involves running a forward pass; training a predicate involves collecting gradients from the proofs it participates in.

The differentiable resolution layer is where the engine supports end-to-end gradient flow across proof structure. When proofs are constructed with differentiable predicates, the proof tree becomes a computation graph, and standard automatic differentiation machinery (from JAX or PyTorch) handles the backward pass. This layer also handles the batching of alternative proofs via `vmap` so that GPU-scale parallelism is available.

The architecture compilation layer interprets Prolog terms representing neural architectures and emits concrete Flax or PyTorch modules. This is where homoiconicity is cashed in: a term like `transformer_block(512, 8, 4)` is resolved, expanded according to its definition, and compiled to runnable code.

The solver integration layer exposes SAT solvers, SMT solvers, MILP solvers, and constraint propagators as predicates that participate in ordinary proof search. This allows hybrid reasoning where logical goals delegate subproblems to specialized solvers and receive back models or unsat cores that feed further unification.

A library of standard architectures and rule templates sits on top. This is where transformer, convolutional, graph-neural, and state-space model families are defined as predicates, and where common ILP templates and neurosymbolic patterns are packaged for reuse.

## What This Enables That Nothing Else Does

The specific combination of capabilities here creates a workspace that current tools approximate only with significant friction. A researcher could define a family of architectures with logical constraints on their shape, train individual members end-to-end with standard loss functions, use the logic engine to search over architectural variants under resource budgets, prove shape-correctness before training, inject domain knowledge as hard logical constraints that the model cannot violate, extract interpretable rules from trained models by reading off the weighted logic program, and compose all of this with the full Python scientific ecosystem.

The closest existing approximations — pure neural frameworks with bolted-on config systems, pure symbolic systems with neural pipelines, or specialized NAS frameworks — each miss one or more of the core capabilities. A homoiconic neurosymbolic platform is not merely a more convenient packaging of existing ideas; it is the substrate that makes a class of ML work feasible as ordinary programming rather than as framework engineering.

## What to Build First

For an initial demonstration that captures the platform's distinctive capabilities, two candidates stand out. The first is declarative architecture search: write a Prolog specification of an architecture family with resource constraints, enumerate valid instances, train them, and report results — ideally beating a standard NAS baseline on sample efficiency while providing a human-readable description of the search space. The second is learning interpretable rules from perceptual data: train a neurosymbolic system on a physics or visual-reasoning task and show that the learned model can be inspected as a readable Prolog program, not just queried as a black box.

Either of these showcases the three ingredients — symbolic structure, neural computation, end-to-end learning — and produces outputs whose legibility is the point. That legibility, more than any efficiency argument, is the reason a neurosymbolic platform should exist in the first place.
