# Provenance Semirings — Differentiable Datalog over Tagged Facts

Implementation plan for **`clausal-provenance`**, a new optional package
that adds **provenance-tagged bottom-up Datalog** to Clausal — a peer
evaluation strategy to SLG, with semirings ranging from plain Boolean
Datalog through to PyTorch/JAX-differentiable probabilistic inference.
Users opt in with `pip install clausal-provenance` and get a Python-side
API + a `provenance` Clausal module via `-import_from(provenance, [...])`.

Following the same handoff shape as `clpfd`, `clpq`, `clpsat`, `clpz3`
(declarative goal + tagged facts → solver → tagged results), but
delivered as a separate distribution rather than as a core feature —
neurosymbolic ML is not a default use case, and the implementation pulls
in optional dependencies (torch, jax) that core users shouldn't pay for.

The primary motivation is neurosymbolic AI — gradients flowing from a
logic query's answer probabilities back to a perception model's
parameters — but the underlying machinery (a stratified bottom-up engine
generic over a tag algebra) is independently useful for plain Datalog
reachability, security/lineage analysis, and probabilistic databases.

---

## Status

This plan elaborates and partly subsumes phase **N-4 (Rule-weight learning)** from
[`NEUROSYMBOLIC_PLATFORM_SKETCH.md`](NEUROSYMBOLIC_PLATFORM_SKETCH.md), currently
parked as a research ticket
([`neurosymbolic_platform/phase_n4_rule_weight_learning.md`](neurosymbolic_platform/phase_n4_rule_weight_learning.md)).
Provenance semirings are the more general framing of what N-4 sketched as
"learnable scalar weights per clause" — that case is recovered by a single
semiring (`add_mult_prob` with learnable scalars), and the same machinery covers
several other useful regimes (top-k-proofs, dual-number AD, exact discrete
provenance).

**Delivery: a separate package, not a core feature.** Lives in
`packages/clausal-provenance/` alongside `clausal-torch`, `clausal-jax`,
`clausal-yaml`, `clausal-scipy`, etc. Aligns with the strategy in
[`PACKAGE_EXTRACTION.md`](PACKAGE_EXTRACTION.md): core stays small, optional
features ship as their own PyPI distributions. Core has zero new
dependencies; users who don't install `clausal-provenance` see no change.

The plan deliberately targets **zero core changes** for P-1 — every hook
the engine needs is implemented within the package, using existing
Clausal extensibility (term expansion, builtin registration via
`clausal.modules.*`, `_RegexPredicate`-style adapters). One ergonomic
shortcut (true `-bottom_up` / `-pure` directives) would benefit from a
small core hook; that is called out as a "post-P-1" enhancement, not a
prerequisite.

This is a Clausal-extension component, **not a Python-library wrapper**. The
[`EXTERNAL_WRAPPER_CHECKLIST`](EXTERNAL_WRAPPER_CHECKLIST.md) is referenced for
naming (Checklist A), `.clausal` syntax rules (Checklist I), phasing (Step 10),
and the Issues-section discipline (Step 11). Its bijective-map and per-predicate
Quantity-propagator sections do not apply.

---

## Background: the provenance-semiring landscape

### The semiring framework (2007)

Green, Karvounarakis & Tannen, *Provenance Semirings* (PODS 2007), introduced
the unifying observation that many "tagged" extensions of relational algebra
fall out of a single algebraic structure: a **commutative semiring** `(K, ⊕, ⊗,
0, 1)` where ⊕ aggregates alternative derivations and ⊗ combines steps within
a derivation. Specialising the semiring recovers the various forms:

| Semiring | ⊕ | ⊗ | What it computes |
|---|---|---|---|
| **(B, ∨, ∧, ⊥, ⊤)** | OR | AND | Set semantics — plain Datalog |
| **(N, +, ×, 0, 1)** | + | × | Bag semantics — counts |
| **(N∪{∞}, min, +, ∞, 0)** | min | + | Tropical — shortest-path costs |
| **(P[X], +, ×, 0, 1)** | sum of monomials | product | Polynomial provenance — full lineage |
| **([0,1], max, ·, 0, 1)** | max | · | Fuzzy/Gödel min-max-prob |
| **([0,1], +, ·, 0, 1)** with independence | sum-with-clip | · | Add-mult-prob |
| **DNF**, **top-k DNF** | ∪ / top-k | ∧ | Boolean-formula lineage |

Bottom-up evaluation of a Datalog program over any such semiring computes a
correct tag for every derived fact, by tagging input facts and lifting the
recursive least-fixpoint computation point-wise into the tag algebra. This is
the mathematical core of every system in the next two sections.

### From provenance to differentiable proofs

DeepProbLog (Manhaeve et al., NeurIPS 2018) and Scallop (Huang/Li/Naik, NeurIPS
2021; Li et al., PLDI 2023) independently arrived at the same engineering
observation: if the tag algebra carries gradient information (via PyTorch's
autograd or dual-number arithmetic), then bottom-up evaluation produces
*differentiable* answer tags. Loss flows backward through the proof structure
to the input fact tags, which can be the output of a perception model. End-to-
end training of `CNN → Datalog → loss → backward` works.

DeepProbLog uses a probabilistic semantics over Sentential Decision Diagrams.
Scallop generalises further: a `Provenance` Rust trait abstracts the tag
algebra and the bottom-up engine is generic over it, giving 14+ pluggable
semirings (boolean, top-k-proofs, diff-top-k-proofs, diff-add-mult-prob,
diff-min-max-prob, sample-k-proofs, tropical, …). Differentiable proofs are
just one tier of the lattice.

Lobster (Biberstein et al., ASPLOS 2026, arXiv 2503.21937) is a follow-on
research artefact from the same group: it compiles a Datalog subset to a new
"Abstract Provenance Machine" IR and emits CUDA. 3.9× geomean over Scallop
with peaks past 100×. It is a clean re-implementation, not a Scallop backend
flag, and is not in the public scallop-lang repo as of writing — useful as
future-state reference, not a current dependency.

### Current systems and why this is a clean-room design

| System | Lang | Strengths | Why we don't embed |
|---|---|---|---|
| **Scallop** (Rust, scallopy via PyO3) | Rust + Datalog DSL | Mature, 14 semirings, fast | Rust toolchain dependency; per-tuple GIL on Python foreign predicates; source-string boundary kills "Clausal terms in, Clausal terms out"; static type system (`I32`/`F64`/`Tensor`) clashes with Clausal's dynamic typing. |
| **DeepProbLog** | Python + ProbLog | First system to do this | ProbLog's evaluation is exact via SDDs — slow on large programs, no top-k approximation, and we already have our own logic engine. |
| **PyReason** (Python) | Python | Pure Python, accessible | Annotated-logic flavour, not semiring-based; not differentiable. |
| **Lobster** | Rust + CUDA | GPU-accelerated | Not yet public; not a Scallop backend flag — a separate language. |

The case for re-implementation has already been made in conversation; in short:
the load-bearing ideas (provenance protocol + bottom-up driver + autograd
bridge) are ~3-4K LOC of Python on top of Clausal's existing engine, vs ~45K
LOC of Rust + a marshalling tax at every Clausal↔solver boundary. The user-
facing payoff is "Clausal terms go in, Clausal terms come out, Torch/JAX
gradients flow back" without an FFI hop.

---

## Position: a separate package

### Distribution and module path

The component is a separate PyPI distribution `clausal-provenance`,
shipped from `packages/clausal-provenance/` in the monorepo. The Python
import path inside the namespace is `clausal.modules.provenance`. From a
user's perspective:

```bash
pip install clausal-provenance        # depends on clausal core
pip install clausal-provenance[torch] # adds PyTorch
pip install clausal-provenance[jax]   # adds JAX
pip install clausal-provenance[all]   # both frameworks
```

```clausal
-import_from(provenance, [solve, boolean, add_mult_prob, diff_add_mult_prob])
```

The package follows the precedent set by `clausal-yaml`, `clausal-torch`,
`clausal-scipy`, etc. — PEP 420 namespace package contributing files into
`clausal/modules/`; no `__init__.py` at `clausal/` or `clausal/modules/`
since those are owned by the core distribution.

### File layout

```
packages/clausal-provenance/
    pyproject.toml             # name = "clausal-provenance"; deps: clausal>=X.Y
                               # optional-deps: torch / jax / all
    README.md
    clausal/                   # PEP 420 namespace — no __init__.py
        modules/               # PEP 420 namespace — no __init__.py
            provenance/        # subpackage owned by this distribution
                __init__.py    # public surface: solve, semiring values, query()
                engine.py      # Bottom-up semi-naive driver (semiring-generic)
                protocol.py    # Provenance ABC + AggregateProvenance
                stratify.py    # SCC over rule dependency graph
                _registration.py  # bottom_up_/1, pure_/1 module-load goals
                _pure_default.py  # default-pure builtin whitelist
                semirings/
                    __init__.py
                    boolean.py
                    add_mult_prob.py
                    diff_add_mult_prob.py
                    top_k_proofs.py
                    diff_top_k_proofs.py
                    min_max_prob.py
                    diff_min_max_prob.py
                bridges/
                    __init__.py
                    torch_bridge.py    # autograd.Function for top-k diff
                    jax_bridge.py      # custom_vjp for the same
                builtins/
                    __init__.py
                    solver.py    # provenance.solve/4, aggregate/4
    docs/
        provenance.md          # user-facing docs (also pulled into core docs/)
    tests/
        test_provenance_engine.py
        test_diff_provenance.py
        test_top_k_proofs.py
        test_mnist_sum.py
        fixtures/
            provenance_reach.clausal
            mnist_sum.clausal
```

### Package architecture

- **PEP 420 namespace.** Both `clausal/` and `clausal/modules/` are
  implicit namespace packages (no `__init__.py`). The core `clausal`
  distribution ships some `clausal/modules/*.py` files; this package
  ships `clausal/modules/provenance/` as a subpackage. `setuptools`
  picks them up via `[tool.setuptools.packages.find]` with
  `include = ["clausal*"]`. Same convention as `clausal-yaml`
  (`packages/clausal-yaml/pyproject.toml:23-29`).

- **Core dependency.** `pyproject.toml` declares `dependencies =
  ["clausal>=X.Y"]`. No version of core needs to be modified for P-1 —
  the package uses only the existing extension points (module
  registration, builtin adapters in the `_RegexPredicate` / `_ScipySpecialPredicate`
  pattern, `clausal.query` extension via additional kwargs accepted by
  the user-side `query()` function rather than core).

- **Optional ML dependencies.** `pyproject.toml` declares
  `[project.optional-dependencies]` for `torch` and `jax`. The semiring
  modules import these lazily — `import torch` inside a function body,
  not at module load — so users who install the `clausal-provenance`
  base distribution without the ML extras can still use `boolean` and
  `add_mult_prob` without import errors.

- **Discoverability.** Once installed, `-import_from(provenance, …)`
  works without any user configuration — Clausal's import hook resolves
  bare names by walking `clausal.modules.*`, which now includes the new
  subpackage by virtue of namespace package discovery.

### Relation to existing components

- **Sibling packages** in `packages/`: `clausal-torch`, `clausal-jax`,
  `clausal-scipy`, `clausal-sklearn`, `clausal-sympy`, `clausal-spacy`,
  `clausal-yaml`. New optional capabilities live here, not in core.
- **Peer in spirit to** `clpfd`, `clpb`, `clpq`, `clpr`, `clpz3`,
  `clpsat` — same handoff shape (declarative goal + facts → solver →
  results). Those happen to live in core because they predate the
  package-extraction strategy and have no heavyweight optional deps.
- **Reuses but does not modify** the term layer (`clausal/terms.py`,
  `PredicateMeta`), the import hook, `term_expansion`, `goal_expansion`.
- **Adds a peer evaluation strategy** to SLG (`clausal/logic/tabling.py`)
  and the standard trampoline (`clausal/logic/trampoline.py`) at the
  *package* level — the default top-down engine in core is unchanged;
  bottom-up evaluation is opted into per-predicate by importing this
  package and registering predicates with it.
- **Cross-references** [`docs/purity.md`](../docs/purity.md) for the
  monotonic-pure-deterministic invariant that the foreign-predicate FFI
  enforces (see *Foreign-predicate constraint* below).

### When to use `-bottom_up` vs `-table`

Both are alternative evaluation strategies opted into per-predicate. The
choice is mostly about query shape and data shape:

| Use `-bottom_up` when… | Use `-table` when… |
|---|---|
| Fact base is large and ground (rows in a database, perception model output, sensor readings) | Fact base is small or implicit (recursive definitions, structural rules) |
| Query is "compute the closure" — all answers, or all answers matching a small filter | Query is goal-directed — "is there a derivation of *this* term?" |
| Tags / probabilities / provenance matter | Plain Boolean answers are sufficient |
| Recursion is over flat tuples (transitive closure, reachability, lineage) | Recursion is over structured terms (parsing, term rewriting, symbolic differentiation) |
| You want gradient flow into input tags | You want top-down search with structural unification |

Rules of thumb: graph reachability over a 10K-edge graph → `-bottom_up`;
Fibonacci or Ackermann → `-table`; MNIST-Sum → `-bottom_up`; an SLD
meta-interpreter → `-table`. They compose: a `-bottom_up` rule body can
call a `-pure`-declared `-table`d predicate (the SCC analysis treats it as
a leaf), and a top-down predicate can call `provenance.solve` for a
sub-query whose semantics need semiring tags.

### What this plan does not cover

- **Top-down probabilistic inference.** A future phase could explore SLG-with-
  semirings (Riguzzi-style), but that requires solving the proof-cycle problem
  for tagged answers and is not on the path. Bottom-up first.
- **Soft unification / fuzzy matching.** Not in scope; Clausal unifies
  structurally and that's not changing.
- **Differentiating through backtracking** in the top-down engine. That is
  N-5 territory and remains parked.

---

## Design overview

### Architecture

```
                        ┌────────────────────────────────────────────┐
                        │   Clausal predicates declared bottom-up    │
                        │   ( -bottom_up(Pred/N) directive )         │
                        └──────────────────┬─────────────────────────┘
                                           │ (rules + ground-fact tags)
                                           ▼
┌──────────────┐    semiring-generic  ┌────────────────────┐    pure callbacks
│  Provenance  │ ◄───────────────────►│  Bottom-up engine  │ ◄────────────────► Clausal
│   protocol   │   (zero, one, add,   │   semi-naive       │   ( -pure(...) )    SLG
│              │    mult, negate, …)  │   stratified       │                     trampoline
└──────┬───────┘                      │   trail-aware      │
       │                              └─────────┬──────────┘
       │                                        │
       ▼                                        ▼
┌──────────────────┐               ┌────────────────────────────┐
│ Semirings        │               │ Tagged answer relation     │
│  Boolean         │               │ { (ground_term, tag) … }   │
│  AddMultProb     │               └────────────┬───────────────┘
│  DiffAddMultProb │                            │
│  DiffMinMaxProb  │                            │ (provenance.solve)
│  TopKProofs      │                            │
│  DiffTopKProofs  │                            ▼
└────────┬─────────┘                ┌────────────────────────┐
         │                          │  Caller (Clausal/Py)   │
         │                          │  ── reads tag, calls   │
         │                          │     loss.backward()    │
         ▼                          └────────────────────────┘
┌────────────────────┐
│ Framework bridges  │
│   torch.autograd   │
│   jax.custom_vjp   │
└────────────────────┘
```

### Three orthogonal concerns

1. **Engine** — bottom-up semi-naive evaluation, stratified by SCC, with a
   well-defined foreign-predicate boundary. Independent of any semiring; runs
   plain Datalog under the boolean semiring.
2. **Protocol** — the algebraic surface area a tag type must implement
   (`zero`, `one`, `add`, `mult`, optionally `negate`/`saturated`/`discard`).
3. **Semiring library** — concrete implementations of the protocol, each in
   its own file. New semirings are added without touching the engine.

The split is the same one that makes Scallop's runtime swap-able and is the
key reason this component is not a fork of `tabling.py` — they solve different
problems.

### CLP-style handoff

The interaction pattern matches the existing constraint solvers exactly:

```clausal
# CLP(Q): rational constraints
clpq.rational((X + Y == 1, X - Y == 1/2)),

# CLP(SAT): boolean constraints
pysat.cadical(X | Y, ~X | Z),

# Z3: integer constraints
z3.integer((1 <= X <= 10, X + Y == 7)),

# Provenance: tagged-fact bottom-up evaluation
provenance.solve(diff_add_mult_prob, FACTS, Goal, Result),
```

`FACTS` is a list of `(GroundTerm, Tag)` pairs. `Goal` is an ordinary Clausal
goal whose predicates have been declared `-bottom_up`. `Result` binds to the
tagged answer relation — a list of `(GroundTerm, Tag)` for every ground term
that satisfies `Goal`. The semiring (`diff_add_mult_prob`, `boolean`,
`top_k_proofs(k=3)`, …) is a value, not a syntactic class — it can be
selected per call.

**The analogy holds for the handoff *shape*, not for *where the data comes
from*.** `clpq.rational((C1, C2))`, `z3.integer(...)`, and `pysat.cadical(...)`
take constraints that are typically *written by a domain expert in source*.
Provenance facts are the opposite: they are *runtime data* — perception-model
output, database rows, sensor readings — where the Clausal source holds
only the rules and signatures. The closer Clausal analogy at the data-loading
level is the SQLite / HTTP / CSV modules: declarative source, dynamic facts.
This is why the API surface (below) leads with the Python-side bulk-load
form; in-source `provenance.solve` calls are mainly for tests and examples.

### Foreign-predicate constraint

Bottom-up evaluation of a Datalog program with semiring tags requires the rule
bodies to be **pure, monotonic, and deterministic** (P-M-D) — exactly the
properties [`docs/purity.md`](../docs/purity.md) already names as the core of
declarative reasoning in Clausal. Predicates whose bodies escape into Clausal
SLG predicates can do so safely **only if** those predicates are P-M-D.

| Property | Why it matters here |
|---|---|
| **Pure** | No side effects — the engine may call a body multiple times during semi-naive iteration; impurity would leak. |
| **Monotonic** | Adding a fact never removes a derivation — required by least-fixpoint semantics. |
| **Deterministic** | Finitely many answers per call (ideally functional) — required by termination of the fixpoint. |

This is enforced by a new `-pure(Pred/N)` directive. Predicates without it
cannot be called from the body of a `-bottom_up` rule. Inference of purity is
not attempted (well-known undecidable; the explicit annotation also serves as
documentation).

| ✅ Naturally pure | ⚠️ Wrap with care | ❌ Forbidden |
|---|---|---|
| `+`, `*`, comparison, `length/2` | `MapList/3` (pure iff the closure is) | `assertz`/`retract` |
| Regex `Match/2,3`, `Search/2,3` | `findall/3` over an SLG goal (pure iff the goal terminates) | I/O builtins |
| `Sign/2`, `Gcd/3`, `DivMod/4` | `NumberVars/3` (pure if outputs are discarded) | CLP(FD) labeling, CLP(SAT) solving |
| All scipy/numpy wrappers (Tier 1) | Tabled predicates (correct under pure tabling) | dif/2 inside a rule body |
| `++(...)` over pure Python | | dynamic predicates |

The directive is checked at compile time when a `-bottom_up` rule body is
analysed; an unmarked callee raises a clear error pointing the user at the
purity doc.

### Ground-tuple contract

Bottom-up Datalog is a *ground-tuple* fixpoint: every derived tuple in a
`-bottom_up` predicate's relation is fully ground. If a rule body produces
a tuple that still contains an unbound `Var` (the head has more variables
than the body binds), the engine raises `NonGroundTupleError` at fixpoint
time, naming the offending rule, the tuple, and the unbound variable(s).
This is a hard error — no partial-tuple bookkeeping. The check fires on
the *first* non-ground tuple, so the failure mode is local and the message
points at the bug.

Practical consequence: the head of a `-bottom_up` rule must have all its
variables bound by the body. Variables introduced by `is`, by `-pure`
helpers, or by other `-bottom_up` predicates count as bound.

---

## Provenance protocol

```python
# packages/clausal-provenance/clausal/modules/provenance/protocol.py

from typing import TypeVar, Generic
Tag = TypeVar("Tag")    # whatever the semiring uses as a tag

class Provenance(Generic[Tag]):
    """A provenance semiring with the operations needed for stratified
    bottom-up Datalog evaluation. Concrete subclasses live in
    `clausal/modules/provenance/semirings/` (within the
    clausal-provenance package)."""

    name: str

    # ── Algebra ───────────────────────────────────────────────────────────
    def zero(self) -> Tag: ...                         # additive identity
    def one(self) -> Tag: ...                          # multiplicative identity
    def add(self, a: Tag, b: Tag) -> Tag: ...          # ⊕  (alternative derivations)
    def mult(self, a: Tag, b: Tag) -> Tag: ...         # ⊗  (rule body conjunction)

    # ── Stratified extras (optional; default impls raise) ────────────────
    def negate(self, a: Tag) -> Tag: ...               # for stratified negation
    def saturated(self, old: Tag, new: Tag) -> bool:   # fixpoint check on a tuple
        return old == new
    def discard(self, a: Tag) -> bool:                 # cull below-threshold tags
        return False

    # ── Boundary ─────────────────────────────────────────────────────────
    # Default identity; override only when the user-facing tag form differs
    # from the internal carrier (e.g., diff_top_k_proofs uses a DNF + tape
    # internally but reports a probability tensor at the boundary).
    def tagging_fn(self, user_tag) -> Tag:
        return user_tag
    def recover_fn(self, internal_tag: Tag):
        return internal_tag


class AggregateProvenance(Provenance):
    """Extension for semirings that support meaningful aggregation
    (count, sum, argmax). Boolean Datalog gets these for free; probabilistic
    semirings need expectation-aware versions."""

    def aggregate_count(self, tags: list[Tag]) -> Tag: ...
    def aggregate_sum(self, vals_tags: list[tuple[float, Tag]]) -> Tag: ...
    def aggregate_argmax(self, vals_tags: list[tuple[float, Tag]]) -> tuple[float, Tag]: ...
```

Six required methods, three or four optional. Single `Tag` type parameter
keeps the protocol simple — most Tier 1 semirings use the same type for
input, internal, and output (a probability is a probability). Semirings
where the internal representation is richer than the user-facing form
(`diff_top_k_proofs`, where the internal carrier is a DNF + back-pointer
tape but the user receives a tensor) override `tagging_fn` and `recover_fn`
to bridge.

---

## Semiring catalogue

Three tiers, ordered by implementation cost and value-per-LOC.

### Tier 1 — port first

| Semiring | Tag type | ⊕ | ⊗ | When it's used |
|---|---|---|---|---|
| **`boolean`** | `bool` | `or` | `and` | Plain Datalog. Engine smoke test. Independently useful for transitive-closure / reachability. |
| **`add_mult_prob`** | `float ∈ [0, 1]` | clip(a + b - a·b, 0, 1) | a · b | Independence-assumption probability — non-differentiable baseline. |
| **`diff_add_mult_prob`** | `torch.Tensor` or `jax.Array` with grad | tensor `+` (clipped) | tensor `*` | Differentiable counterpart. **The key Tier 1 semiring** — autograd flows for free because the operations are tensor ops. ~150 LOC. |

The diff variant is the entire ML payoff for Tier 1: tags are tensors, ⊕ and
⊗ are tensor ops, and PyTorch/JAX autograd traces through naturally. No custom
`autograd.Function` needed at this tier. Either framework works without code
changes — the bridge for Tier 1 is detection (`isinstance(tag, torch.Tensor)`
vs `isinstance(tag, jax.Array)`), not lifting.

### Tier 2 — the Scallop workhorse (port second)

| Semiring | Tag type | ⊕ | ⊗ | Note |
|---|---|---|---|---|
| **`top_k_proofs`** | DNF formula over `(input_id, …)` | DNF union, truncated to top-k | DNF AND | Tracks the k highest-probability proofs. The non-diff variant of Scallop's headline. |
| **`diff_top_k_proofs`** | DNF + back-pointer tape | top-k union | AND with tape append | The neurosymbolic gold standard. Needs `torch.autograd.Function` / `jax.custom_vjp` because proof selection is non-differentiable. |

This is the field-standard semiring for neurosymbolic learning — Scallop's
flagship and the one the PLDI 2023 paper recommends as the default. Tier 2
because the implementation cost is concentrated here: ~800 LOC including the
autograd bridges. The only semiring that justifies its own
`bridges/torch_bridge.py` and `bridges/jax_bridge.py` files. It is "Tier 2
in cost", "Tier 1 in importance" — port immediately after Tier 1 lands.

### Tier 3 — dual-number variants (port when a workload asks)

| Semiring | Tag type | ⊕ | ⊗ | Note |
|---|---|---|---|---|
| **`min_max_prob`** | `float ∈ [0, 1]` | `max` | `min` | Gödel logic / fuzzy. Non-differentiable at kinks. |
| **`diff_min_max_prob`** (dmmp) | dual numbers `(value, deriv)` | dual `max` | dual `min` | Forward-mode AD via dual numbers. ~150 LOC. |
| **`damp`** | dual numbers | clamped dual `max` | dual `min` | Variant: real part clamped, derivative preserved. |

Dual-number semirings compose better with JAX (`jax.jvp`) than PyTorch
(forward-mode AD is a second-class citizen in PyTorch). They handle problems
where add-mult-prob over-counts proofs — useful for some neurosymbolic
workloads but not the default. Defer until a workload asks. ~600 LOC total
when added.

### Out of scope (skip until requested)

- `prob_proofs` (exact probabilistic via SDD) — needs an SDD library, rare in
  practice, top-k approximation is the field standard.
- `sample_k_proofs`, `sampled_k_proofs` — different algorithm class (Monte
  Carlo); orthogonal feature.
- Tropical family (`tropical`, `real_tropical`, `real_tropical_proofs`) —
  shortest-path-as-Datalog is interesting but a separate use case.
- Counting (`natural`) — recoverable as a special case of `top_k_proofs` with
  a count aggregator; not a separate phase.
- `diff_top_k_proofs_debug`, `diff_top_bottom_k_clauses`, `diff_nand_*` —
  minor variants.

---

## Term language

The CLP-style handoff lets us avoid inventing new term constructors. The four
things that flow across the boundary:

### 1. Facts — ordinary Clausal terms

Bottom-up rules and tagged facts use the same predicates as the rest of
Clausal — no mirror class hierarchy. Field names are declared the standard
Clausal way: in the module export list (or `-private` for internal
predicates), with names taken from the variable names in the export tuple:

```clausal
-module(mnist_sum, [
    Digit(IMAGE_ID, VALUE),
    SumDigits(IMAGE_A, IMAGE_B, TOTAL),
])
```

Facts are constructed exactly as in any other Clausal program:
`Digit(0, 3)`, `Digit(IMG, V)`, etc. Whether to add a Clausal-wide
`-type(Digit(image_id=int, value=int))` directive that carries Python type
information is a separate, broader question — out of scope for this plan.

### 2. Tags — Python primitives, tensors, or dual numbers

The tag is whatever the chosen semiring says it is. There is no "Tag" wrapper
class on the user side. Tagged facts are passed as a list of
`(GroundTerm, Tag)` pairs to `provenance.solve`:

```clausal
# boolean semiring — tags are bool
FACTS is [(Digit(0, 3), True), (Digit(1, 5), True)],
provenance.solve(boolean, FACTS, Goal, R),

# add_mult_prob — tags are float in [0, 1]
FACTS is [(Digit(0, 3), 0.7), (Digit(1, 5), 0.9)],
provenance.solve(add_mult_prob, FACTS, Goal, R),
```

```python
# diff_add_mult_prob — tags are torch.Tensor with grad (Python-side)
facts = [(Digit(0, v), probs[0, v]) for v in range(10)]
answers = query(Goal, facts=facts, semiring=diff_add_mult_prob)
```

**Tag granularity: per-fact, not per-value.** A tag annotates the whole ground
tuple, not any individual argument — the standard Green/Karvounarakis/Tannen
2007 model and what Scallop also does (despite scallopy's arity-1 form
`(0.1, 1)` looking deceptively like a value-tag pair; the arity-2 form
`(0.1, ("A", "blue"))` resolves it — outer tuple is `(tag, fact)`, inner is
the fact's positional args). Attribute-level (per-cell) provenance is a
richer, more expensive variant and is out of scope here.

The neurosymbolic idiom of "each cell of a Python probability tensor becomes
one tagged fact" is layered on top of this, not in conflict with it: a tensor
of shape `(N_images, 10_classes)` produces `N × 10` tagged binary facts, each
tag still attached to the whole `(image_id, value)` tuple. The cell-to-fact
mapping is the caller's responsibility (a list comprehension typically); the
component does not introduce a special "tensor input" type.

### 3. Tagged answer relation — list of pairs

`provenance.solve` binds its result variable to a list of `(GroundFact, Tag)`
pairs. The shape is uniform across semirings; only the tag type changes.

### 4. Semiring selector — value, not class

Semirings are imported as ordinary Python values from `clausal.modules.provenance`
and passed to `solve` by name. Per-call configuration (e.g., `k` for top-k) is
a constructor argument:

```clausal
-import_from(provenance, [solve, boolean, diff_add_mult_prob, diff_top_k_proofs])

# Choose at call site
solve(boolean, FACTS, Goal, R),                       # plain Datalog
solve(diff_add_mult_prob, FACTS, Goal, R),            # Tier 1 differentiable
solve(diff_top_k_proofs(k=3), FACTS, Goal, R),        # Tier 2 differentiable
```

This mirrors `pysat.cadical` (no config) vs `pysat.glucose(args)` (with
config) — the semiring is a first-class argument the same way the SAT solver
is.

---

## API surface

The neurosymbolic workflow loads facts and tags from Python at query time
(perception-model output is a tensor, not a literal); the `.clausal` source
holds the rules, signatures, and tests. The API surface is ordered to match
that primacy: Python-side first, in-source forms second.

### Predicate registration (in source)

Because this is a package — and `-table`, `-dynamic`, `-discontiguous`
are core directives hardcoded in the compiler — P-1 ships **module-load-
time goal calls**, not new directives. They are imported from the
`provenance` module like any other predicate, and they execute when the
`.clausal` file is loaded, registering metadata on the named predicate's
`PredicateMeta` class:

```clausal
-import_from(provenance, [bottom_up_, pure_, solve, ...])

bottom_up_(SumDigits/3),    # registers SumDigits for bottom-up evaluation
pure_(SafeColor/2),          # marks SafeColor as pure-callable from -bottom_up bodies
```

The trailing underscore matches existing Clausal naming for "registration
predicates that double as directives" (cf. `-discontiguous` builtin
discussions in core). Functionally identical to a directive: the call
produces no goal-time effect; it sets a flag on the target predicate
that the engine reads at solve time.

**Post-P-1 ergonomic upgrade (optional).** A small core hook (~10 lines)
that lets packages register passive directive names — directives that
the parser accepts and routes to a package-supplied handler instead of
erroring — would let us promote these to `-bottom_up(SumDigits/3)` and
`-pure(SafeColor/2)`. Strictly cosmetic; not on the critical path. File
under "core enhancement requests" once the package is otherwise working.

**Default-pure whitelist.** The engine treats Clausal's standard pure-
deterministic builtins as implicitly pure so users do not call `pure_/1`
on every helper. The whitelist covers: arithmetic (`is`, `+`, `-`, `*`,
`/`, `mod`, `abs`, integer comparison), term-level comparison (`==`,
`<`, `=<`, …), term inspection (`var/1`, `nonvar/1`, `atom/1`,
`length/2`, `functor/3`), and pure list builtins (`member/2` in det
modes, `append/3` in det modes, `nth0/3`, `last/2`). Anything not on
the whitelist must be marked explicitly. The whitelist lives in
`clausal/modules/provenance/_pure_default.py` and is treated as
implementation detail — users override only by calling `pure_/1` for
their own predicates, never by mutating the whitelist.

### Python-side API — primary surface

The primary API surface is the existing `clausal.query` / `clausal.solve`
extended with `facts=` and `semiring=` kwargs:

```python
import torch
from clausal import query
from mnist_sum import Digit, SumDigits          # imported from .clausal
from clausal.modules.provenance import diff_add_mult_prob

# probs has shape (N, 10), requires_grad=True — output of a CNN
facts = [
    (Digit(i, v), probs[i, v])
    for i in range(N)
    for v in range(10)
]

answers = query(SumDigits(0, 1, TOTAL_),
                facts=facts,
                semiring=diff_add_mult_prob)
# answers : list[(GroundFact, Tensor)] — gradients connect back to probs
correct_tag = next(t for (f, t) in answers if f.total == ground_truth_sum)
loss = -torch.log(correct_tag + 1e-12)
loss.backward()                                # propagates through facts → probs → CNN
```

`facts` is any iterable of `(GroundTerm, Tag)` pairs. No `fact_set` helper
class — a list comprehension is the idiom. The `(GroundTerm, Tag)` ordering
matches scallopy's `(tag, fact)` tuples flipped (we keep the term first to
read left-to-right with the "term-then-its-property" Clausal convention).

### In-source builtins (for tests and examples)

For test fixtures and `.clausal`-only examples where facts are written by
hand, a thin in-source surface mirrors the Python-side API:

| Predicate | Modes | Purity | Description |
|---|---|---|---|
| `provenance.solve/4` | `(+Semiring, +Facts, +Goal, -Result)` | pure (functional) | Run the bottom-up engine; `Result` binds to a list of `(GroundFact, Tag)`. |
| `provenance.aggregate/4` | `(+Semiring, +AggOp, +TaggedList, -Tag)` | pure | Semiring-aware aggregation (`count`, `sum`, `argmax`). |
| `provenance.recover/3` | `(+Semiring, +InternalTag, -OutputTag)` | pure | Apply `recover_fn` — usually called automatically inside `solve`. |

There is **no** `provenance.fact/2` posting builtin. Facts always go in as a
list, in source or from Python — the same shape both ways. Avoiding a
posting form keeps the engine pure-functional from the caller's view; no
hidden `solve`-time dependency on prior asserts.

### Semiring values (re-exported from `clausal.modules.provenance`)

```python
boolean
add_mult_prob
diff_add_mult_prob
top_k_proofs(k=3)          # phase P-4
diff_top_k_proofs(k=3)     # phase P-4
min_max_prob               # phase P-5
diff_min_max_prob          # phase P-5 (alias: dmmp)
damp                       # phase P-5
```

---

## PyTorch / JAX bridges

### Tier 1 (boolean / add_mult_prob / diff_add_mult_prob)

Framework-agnostic. The semiring's `add` and `mult` are written in terms of
`+`, `*`, `min`, `max`, `clip` — which work polymorphically on Python floats,
PyTorch tensors, and JAX arrays. No bridge code needed. Detection is by tag
type:

```python
def detect_framework(tag):
    if isinstance(tag, _torch_tensor_type()): return "torch"
    if isinstance(tag, _jax_array_type()):    return "jax"
    return "python"
```

Imports of `torch` / `jax` are deferred so neither becomes a hard dependency
of the provenance component (matches the existing pattern in
`clausal/modules/py/scipy_special.py` for SciPy).

### Tier 2 (top-k-proofs and diff-top-k-proofs)

The proof-selection step (truncating a DNF formula to its top-k disjuncts) is
non-differentiable, so the diff variant requires explicit autograd plumbing.
The pattern:

- During the forward pass, the engine produces a sparse Jacobian of "answer
  tag (k probabilities) with respect to input tags (n probabilities)" by
  evaluating the selected DNF formulas.
- A `torch.autograd.Function` subclass (resp. `jax.custom_vjp`) holds this
  Jacobian; `forward` returns the answer probability, `backward` (resp. the
  vjp rule) multiplies the upstream gradient by the stored Jacobian.

This is identical to Scallop's mechanism; the difference is we wrote it once
in Python instead of once in Rust + once across PyO3.

### Tier 3 (dual-number semirings)

A small dual-number class:

```python
class Dual:
    __slots__ = ("real", "deriv")
    def __init__(self, real, deriv): ...
    # __add__, __mul__, __min__, __max__ defined
```

The `real` and `deriv` fields hold ordinary tensors (or scalars), so the
semiring composes with both frameworks. `jax.jvp` recognises dual numbers
natively if `real` and `deriv` are JAX arrays; PyTorch needs a tiny adapter
that copies `deriv` into `.grad` after the forward pass.

### When to use which framework

- **PyTorch** is the default. Pretrained-model ecosystem; native autograd
  matches Tier 1 / Tier 2 patterns.
- **JAX** wins on Tier 3 (dual numbers) and on `vmap`-batched proofs (the
  parked N-5 — not in this plan). Tier 1 works identically under both.

The framework choice is per-call (driven by tag types in the supplied facts),
not per-installation. Mixing torch and jax tags in one `solve` call is an
error.

---

## Showcase: MNIST-Sum

The canonical neurosymbolic benchmark. Two MNIST images go in; the predicted
sum (0..18) comes out; loss is computed against the true sum; gradients train
a CNN that has never seen image-level digit labels.

```clausal
# packages/clausal-provenance/tests/fixtures/mnist_sum.clausal

-module(mnist_sum, [
    Digit(IMAGE_ID, VALUE),
    SumDigits(IMAGE_A, IMAGE_B, TOTAL),
])

-import_from(provenance, [bottom_up_, pure_, solve,
                          boolean, add_mult_prob, diff_add_mult_prob])

# `Digit/2` carries the perception model's output; facts come in via solve/4.
# It still needs -dynamic so Python can populate it for the in-source tests
# (the runtime-load path goes through `solve`, but tests want to write facts
# inline as a list).
-dynamic(Digit/2)

# Register SumDigits for bottom-up evaluation (semiring is per-query, not here).
# `is` is on the default-pure whitelist, so no pure_/1 call is needed for it.
bottom_up_(SumDigits/3),

SumDigits(IMG_A, IMG_B, TOTAL) <- (
    Digit(IMG_A, A),
    Digit(IMG_B, B),
    TOTAL is A + B,
)

# ── Tests ───────────────────────────────────────────────────────────────

Test("boolean reachability ignores tags") <- (
    FACTS is [
        (Digit(0, 3), True),
        (Digit(1, 5), True),
    ],
    solve(boolean, FACTS, SumDigits(0, 1, T), [(_, True)]),
    T == 8,
)

Test("add_mult_prob multiplies confidences") <- (
    FACTS is [
        (Digit(0, 3), 0.7),
        (Digit(1, 5), 0.9),
    ],
    solve(add_mult_prob, FACTS, SumDigits(0, 1, 8), [(_, P)]),
    abs(P - 0.63) < 1e-6,
)
```

```python
# Python training loop
import torch
from clausal import query
from mnist_sum import Digit, SumDigits           # imported from .clausal
from clausal.modules.provenance import diff_add_mult_prob

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
                    semiring=diff_add_mult_prob)

    correct = next(p for ((_, _, total), p) in answers if total == true_sum)
    loss = -torch.log(correct + 1e-12)

    opt.zero_grad()
    loss.backward()
    opt.step()
```

Three things this exercises end-to-end:

1. **Clausal terms throughout.** No string-passing, no parallel AST.
2. **Tag = tensor.** No marshalling at any boundary; PyTorch autograd traces
   straight through `add` and `mult`.
3. **Default-pure builtins.** `is` (the rule's only callback into Clausal) is
   on the engine's whitelist, so no `-pure` annotation is needed for it.

---

## Phasing

Each phase is independently reviewable, mergeable, and useful.

### Phase P-1 — Package skeleton + bottom-up engine + boolean semiring

**Goal.** A working `clausal-provenance` package, installable via
`pip install -e packages/clausal-provenance/`, exposing a stratified
bottom-up Datalog engine behind module-load goal calls (`bottom_up_/1`,
`pure_/1`), with the boolean semiring. Enough to evaluate plain
reachability and transitive-closure programs; no probabilistic story
yet.

**Package skeleton (model after `packages/clausal-yaml/`).**
- `packages/clausal-provenance/pyproject.toml` — `name = "clausal-provenance"`,
  `dependencies = ["clausal>=X.Y"]`, `[project.optional-dependencies]`
  for `torch` and `jax`, namespace-package config.
- `packages/clausal-provenance/README.md` — brief feature description +
  install instructions.
- PEP 420 namespace: no `__init__.py` at `clausal/` or `clausal/modules/`.

**Engine deliverables.**
- `clausal/modules/provenance/__init__.py` — public surface
  (`solve`, `boolean`, `bottom_up_`, `pure_`, plus `query` re-export).
- `clausal/modules/provenance/engine.py` — semi-naive driver (~400 LOC).
- `clausal/modules/provenance/stratify.py` — Tarjan SCC, stratification
  check rejecting bottom-up programs with cyclic negation (~150 LOC).
- `clausal/modules/provenance/protocol.py` — `Provenance` ABC.
- `clausal/modules/provenance/_registration.py` — `bottom_up_/1`,
  `pure_/1` adapters following the `_RegexPredicate` /
  `_ScipySpecialPredicate` pattern from existing wrappers.
- `clausal/modules/provenance/_pure_default.py` — default-pure whitelist.
- `clausal/modules/provenance/semirings/boolean.py` — boolean semiring.
- `clausal/modules/provenance/builtins/solver.py` — `provenance.solve/4`.

**Tests and examples.**
- `tests/test_provenance_engine.py` — engine invariants on boolean
  semiring.
- `tests/fixtures/provenance_reach.clausal` — graph reachability
  fixture.
- `tests/fixtures/datalog_reach.clausal` — showcase: bottom-up reach,
  the same program SLG would handle, run faster.
- `tests/test_package_install.py` — verifies `pip install -e .` works,
  `from clausal.modules.provenance import solve` resolves, and
  `-import_from(provenance, …)` is discoverable from `.clausal` source.

**Tests** (target ≥ 30): graph reachability over 10K-edge graph; mutual
recursion across two predicates; stratified negation (one predicate's
absence triggers another's success); cyclic negation rejected at
registration time with a clear error message naming the offending SCC
and the predicates in it; refusal of unmarked-impure callees with a
message pointing at `docs/purity.md`; non-ground tuple at fixpoint time
produces `NonGroundTupleError` naming the rule, tuple, and unbound
variable; equivalence to SLG result on the boolean cases.

**Independent value.** Even without semirings, this gives Clausal users
a bottom-up Datalog mode (via the package) that's faster than tabled SLG
for transitive closure on dense graphs.

### Phase P-2 — Probabilistic semirings + autograd-flow

**Goal.** Tagged facts and gradient flow. The first phase that delivers a
*differentiable* logic component end-to-end.

**Deliverables.**
- `clausal/modules/provenance/semirings/add_mult_prob.py` — non-diff
  baseline.
- `clausal/modules/provenance/semirings/diff_add_mult_prob.py` — Tier 1
  diff semiring; tags are torch/jax tensors; ⊕ and ⊗ are tensor ops.
- Extend `clausal/modules/provenance/builtins/solver.py` with
  `provenance.solve/4` semiring-routing and `provenance.recover/3`. (No
  `provenance.fact/2` — facts always pass as a list to `solve/4`.)
- A user-side `query()` helper in
  `clausal/modules/provenance/__init__.py` that wraps `clausal.query`
  with `facts=` and `semiring=` kwargs (no core change required —
  the helper handles fact registration and result collection on the
  package side).
- Framework detection helpers (no hard dep on torch/jax — both deferred
  imports).
- `tests/test_diff_provenance.py` — `torch.autograd.gradcheck` on a small
  program; equivalent JAX-side test using `jax.test_util.check_grads`.
- `tests/fixtures/mnist_sum.clausal` and a `tests/test_mnist_sum.py`
  smoke test that runs end-to-end with a tiny synthetic dataset (the
  showcase from §"MNIST-Sum" above).

**The key validation.** `gradcheck` passing on a 3-fact, 2-rule program
under `diff_add_mult_prob`. If this works, the architecture is sound.

### Phase P-3 — Stratified negation + semiring-aware aggregation

**Goal.** Lift negation and aggregation into the protocol.

**Deliverables.**
- `Provenance.negate` defined where meaningful (boolean: `not`;
  probabilistic: `1 - p`; differentiable: tensor `1 - p`).
- `AggregateProvenance` with `count`, `sum`, `argmax` operating semiring-
  aware. Plain count on `add_mult_prob` returns expectation; on boolean
  returns cardinality.
- `provenance.aggregate/4` builtin.
- Tests: probabilistic `count` matches expectation under `diff_add_mult_prob`
  with `gradcheck`; stratified negation works on probabilistic input.

### Phase P-4 — Top-k-proofs and diff-top-k-proofs

**Goal.** The Scallop workhorse semiring — the field-standard for
neurosymbolic learning. This is the phase that lets users replicate
Scallop's headline workloads (CLEVR-style visual reasoning, KBQA) in
Clausal.

**Deliverables.**
- DNF formula representation (`Conj`, `Disj`, hashing, k-truncation).
- `top_k_proofs(k=N)` non-diff variant.
- `diff_top_k_proofs(k=N)` with `bridges/torch_bridge.py` and
  `bridges/jax_bridge.py` (`torch.autograd.Function`, `jax.custom_vjp`).
- Sparse Jacobian construction using `torch.sparse` / `jax.experimental.sparse`.
- Tests: `gradcheck` on a 2-rule MNIST-sum-style program at `k=3`; numerical
  parity with `diff_add_mult_prob` when k = (number of proofs) and the
  program is non-recursive.

### Phase P-5 — Dual-number semirings (dmmp, damp)

**Goal.** Min-max-style differentiable inference for problems where
add-mult-prob over-counts proofs. JAX-favoured path.

**Deliverables.**
- `Dual` class.
- `min_max_prob`, `diff_min_max_prob` (dmmp), `damp`.
- JAX-side preferred path: `jax.jvp` directly consumes dual numbers.
- Tests including `gradcheck` parity with PyTorch `Dual`-via-adapter.

### Phase P-6 — Polish (deferred)

JAX-specific optimisations (`jit`, eventual `vmap` integration with N-5),
progress reporting, large-program performance tuning. Only scheduled if a
real workload benefits.

---

## Out of scope for this plan

- **Embedding scallopy.** Considered and rejected — see *Background*. If a
  user has a workload that genuinely needs Scallop's specific semirings or
  raw Rust performance, they can `pip install scallopy` and use it
  alongside Clausal; the two systems don't need to share an engine.
- **Lobster / GPU.** Not currently a Scallop backend, not yet public.
  Revisit if/when there's a stable public API.
- **SDD-based exact provenance.** Niche; top-k-proofs covers the practical
  cases.
- **Top-down probabilistic inference (PRISM/ProbLog style over SLG).**
  Different algorithmic territory. Bottom-up first.
- **Differentiating through backtracking.** Stays in N-5 territory.
- **Soft unification / fuzzy matching.** Not planned.
- **Training loop orchestration.** `optimizer.step()` stays in Python; the
  same stance the PyTorch wrapper takes.
- **Multi-machine / distributed training.** Out of scope.

---

## Risks and unknowns

1. **Non-monotonic interaction with attributed variables.** Clausal's
   constraint solvers use attributed variables for propagation (dif/2,
   CLP(FD), CLP(B)). Bottom-up evaluation operates on ground tuples and
   doesn't compose with these directly. The `-pure` discipline forbids the
   problematic cases, but pre-spike validation should confirm no surprising
   cross-talk. *Mitigation:* P-1 includes a test that `-bottom_up` rules
   are rejected if their bodies post attributed-var constraints.

2. **Autograd tape preservation across the engine.** The engine constructs
   intermediate tag values in Python sets / dicts; any operation that
   detaches from the autograd graph would silently break gradient flow.
   *Mitigation:* P-2 includes `gradcheck` as a hard pass criterion before
   merging. If tape preservation requires tensor identity tracking (it
   probably won't, but possibly), the engine grows a "tag store" abstraction.

3. **Stratification interaction with tabled predicates.** A `-bottom_up`
   predicate calling a `-table`d predicate (via `-pure` declaration) is
   sound under the purity discipline, but the SCC analysis must treat the
   tabled predicate as a leaf. *Mitigation:* documented and tested in P-1.

4. **Tag granularity assumption.** The plan commits to per-fact (per-tuple)
   tags, the standard Green/Karvounarakis/Tannen 2007 model. If a workload
   genuinely needs per-cell (attribute-level) provenance — different tags
   on different positions of the same fact — that requires a different
   algebraic structure (semimodules over the semiring, roughly) and is not
   a small extension. *Mitigation:* none planned; documented as out of
   scope. Re-open if a real workload appears.

5. **Performance below Scallop.** Pure-Python evaluation is 10–100× slower
   than Rust. *Mitigation:* documented honestly; users who need raw
   performance for inference at scale can use scallopy directly. The
   feature is delivered to make the *training* story tractable inside
   Clausal, where Python's overhead is dominated by the perception model
   anyway.

---

## Issues

_To be populated during implementation. Each issue records: what was
unexpected, the resolution (fix / dismiss / defer), and the test or commit
that closed it._

### P-4 — input-id allocation requires per-call semiring state

**Unexpected.** `top_k_proofs`'s DNF carrier indexes input facts by integer
id. The id has to be allocated when an input fact is first tagged, but
`Provenance.tagging_fn(user_tag)` only sees one tag at a time and the
engine doesn't know it should pass an id along.

**Resolution.** Made `top_k_proofs(k=...)` a *factory* that returns a
fresh stateful instance per call. The instance owns
`_input_tags: dict[int, Any]` (and `_input_prob_scalars` for ranking)
which `tagging_fn` mutates as ids are allocated. The protocol stays
unchanged; users always do `evaluate(top_k_proofs(k=3), facts, goal)`.
Closed by tests in `tests/test_top_k_proofs.py::test_factory_returns_fresh_instance_per_call`.

### P-4 — implicit autograd path is sufficient for gradcheck

**Unexpected.** The plan calls for an explicit `torch.autograd.Function`
holding a sparse Jacobian. In practice, recomputing the inclusion-exclusion
sum over the original input *tensors* in `recover_fn` produces a
correctly-traced autograd graph — no custom Function is needed for
gradcheck to pass on a 2-rule program at `k=3`.

**Resolution.** Default `recover_fn` uses the implicit path (autograd
traces through I-E). The bridges (`bridges/torch_bridge.py`,
`bridges/jax_bridge.py`) ship the explicit autograd-Function path as an
opt-in optimisation; tests verify they produce identical values and
gradients to the implicit path. Closed by
`test_torch_bridge_value_matches_implicit_recover`,
`test_torch_bridge_grad_matches_implicit_recover`,
`test_diff_topk_torch_gradcheck_2rule_k3`.

---

## References

### Foundational

- Green, Karvounarakis & Tannen. *Provenance Semirings.* PODS 2007.
  [https://web.cs.ucdavis.edu/~green/papers/pods07.pdf](https://web.cs.ucdavis.edu/~green/papers/pods07.pdf)
- Karvounarakis & Green. *Semiring-annotated data: queries and provenance.*
  SIGMOD Record, 2012.

### DeepProbLog

- Manhaeve, Dumančić, Kimmig, Demeester, De Raedt. *DeepProbLog: Neural
  Probabilistic Logic Programming.* NeurIPS 2018.
  [https://arxiv.org/abs/1805.10872](https://arxiv.org/abs/1805.10872)
- ProbLog: [https://dtai.cs.kuleuven.be/problog/](https://dtai.cs.kuleuven.be/problog/)

### Scallop

- Huang, Li, Chen, Samel, Naik, Song, Si. *Scallop: From Probabilistic
  Deductive Databases to Scalable Differentiable Reasoning.* NeurIPS 2021.
  [https://www.cis.upenn.edu/~mhnaik/papers/aiplans21.pdf](https://www.cis.upenn.edu/~mhnaik/papers/aiplans21.pdf)
- Li, Huang, Naik. *Scallop: A Language for Neurosymbolic Programming.*
  PLDI 2023. [https://arxiv.org/abs/2304.04812](https://arxiv.org/abs/2304.04812)
- Ziyang Li, *A Language for Scalable Differentiable Reasoning.* PhD
  thesis, UPenn, 2024.
  [https://www.cis.upenn.edu/~mhnaik/theses/ziyang_li_thesis.pdf](https://www.cis.upenn.edu/~mhnaik/theses/ziyang_li_thesis.pdf)
  — most detailed implementation reference; chapters 4-5 cover the
  semiring runtime in depth.
- Source: [https://github.com/scallop-lang/scallop](https://github.com/scallop-lang/scallop)
  (MIT). Read for ideas, not code; this plan describes a clean-room
  Python implementation.
- Doc site: [https://www.scallop-lang.org/doc/](https://www.scallop-lang.org/doc/)

### Lobster (future-state reference)

- Biberstein et al. *Lobster: GPU-Accelerated Datalog for Neurosymbolic
  Reasoning.* ASPLOS 2026.
  [https://arxiv.org/abs/2503.21937](https://arxiv.org/abs/2503.21937)

### Within Clausal

- [`PACKAGE_EXTRACTION.md`](PACKAGE_EXTRACTION.md) — the broader strategy
  for keeping core small and shipping optional features as separate
  PyPI distributions; this package follows that pattern.
- [`packages/clausal-yaml/`](../packages/clausal-yaml/) — the cleanest
  small-package precedent to model `clausal-provenance/` after
  (pyproject.toml, README, namespace package layout, docs/, tests/).
- [`packages/clausal-torch/`](../packages/clausal-torch/),
  [`packages/clausal-jax/`](../packages/clausal-jax/) — sibling packages
  that the bridges in P-2/P-4 will use as optional dependencies.
- [`docs/purity.md`](../docs/purity.md) — the monotonic-pure-deterministic
  invariant the foreign-predicate FFI enforces.
- [`docs/tabling.md`](../docs/tabling.md) — SLG tabling, the peer top-down
  evaluation strategy.
- [`docs/constraints.md`](../docs/constraints.md) — dif/2, CLP(ℤ), CLP(B),
  CLP(ℝ) — peer constraint domains.
- [`NEUROSYMBOLIC_PLATFORM_SKETCH.md`](NEUROSYMBOLIC_PLATFORM_SKETCH.md) —
  this plan elaborates phase N-4 of that sketch.
- [`EXTERNAL_WRAPPER_CHECKLIST.md`](EXTERNAL_WRAPPER_CHECKLIST.md) —
  referenced for naming (Checklist A), `.clausal` syntax (Checklist I),
  phasing discipline (Step 10), Issues section (Step 11).
- [`CLPQ.md`](clpq/CLPQ.md), [`CLPR.md`](clpr/CLPR.md) — internal-component
  plans this document is modelled on.
