# How to Write a Clausal Wrapper Plan

A meta-plan: the process for producing a wrapper plan document (like
`scikit-learn.md`) for any Python library. The output of following this
process is a plan; the output of following *that* plan is code.

---

## What the Process Produces

Following this meta-plan yields a plan document in `implementation_plans/`
with these sections filled in:

1. **Core Abstraction** — the library's central concept and lifecycle
2. **Bijective Map** — procedural pairs collapsed into single predicates
3. **Purity Analysis** — what's pure, what needs state threading, what needs solver-style wrapping
4. **Tier Classification** — every planned predicate assigned to a tier
5. **Scope Decision** — what's in, what's out, what stays as `++()`
6. **Term Language** — tagged tuples and their semantics
7. **Predicate Catalogue** — name, arity variants, modes, tier, purity
8. **Submodule Breakdown** — how to split a large library across files
9. **Phased Implementation** — phases with predicates, `.clausal` tests, and docs per phase
10. **Issues** — reviewed, all resolved (fixed / dismissed / deferred to a phase)

---

## Step 1 — Identify the Core Abstraction

Every library worth wrapping has a unifying concept. Find it before doing
anything else — it determines how many predicates you need.

Questions to answer:

- What is the central object/concept? (estimator, tensor, document, graph)
- What lifecycle does it follow? (construct -> configure -> use -> query)
- How uniform is the library? (Does one pattern cover 80% of classes, or
  is it a grab-bag of unrelated utilities?)
- Which operations are pure vs stateful?

**Write-up:** A paragraph or two in the plan describing the abstraction,
why it's the right one, and what lifecycle the wrapper will model.

If the library has **multiple independent subsystems** (like PyTorch has
tensors, nn, optim, data), identify the core abstraction for each and
note which subsystems share terms.

---

## Step 2 — Find Bijective Relationships

The highest-leverage step. Scan the library's API for operations that are
inverses of each other, or mappings queryable in either direction. In
procedural Python these are separate functions; in Clausal they collapse
into a single multi-mode predicate.

### What to look for

| Procedural pattern | Relational collapse |
|---|---|
| `encode(X) -> Y` / `decode(Y) -> X` | `encoding(X, Y)` — unify either way |
| `to_json(obj) -> str` / `from_json(str) -> obj` | `json(OBJ, STR)` — bidirectional |
| `compress(data) -> z` / `decompress(z) -> data` | `compressed(RAW, PACKED)` |
| `key_to_value[k]` / `value_to_key[v]` | `mapping(K, V)` — lookup or enumerate |
| `parent(node)` / `children(node)` | `parent(NODE, CHILD)` — query either arg |
| `name_to_code[n]` / `code_to_name[c]` | `code(NAME, CODE)` — single fact table |
| `reshape(T, shape)` / `T.shape` | `shape(TENSOR, SHAPE)` — set or query |

Not every operation is bijective — `Fit` genuinely consumes data and
produces a new thing. But surprisingly many paired APIs are the same
relationship viewed from two directions.

### Broader relational patterns beyond strict bijections

- **Enumerable collections** — anything iterable becomes a nondeterministic
  predicate that yields elements via backtracking
- **Constraint-like relationships** — operations where the "direction" of
  computation isn't fixed (e.g. broadcasting rules, shape inference)
- **Hierarchical containment** — model layers, graph nodes, document tokens —
  parent/child as a single relation

**Write-up:** A table in the plan listing every identified pair/pattern,
the proposed predicate name, and whether full bidirectionality is feasible
or only partial (forward + enumeration but not reverse computation).

---

## Step 3 — Purity Analysis

Every predicate must be **safe to backtrack over**. This is not optional —
it's what makes logic programming work. Analyse every operation in your
working list and classify it:

### 3.1 Pure operations (backtracking-safe by nature)

Functions that take values in and produce values out, with no side effects.
These are the easiest to wrap — they're already monotonic.

```
% Pure: backtracking just re-computes the same result
distance(A, B, D)
reshape(T, Shape, T2)
```

### 3.2 Stateful operations (need explicit state threading)

Operations that modify state (model weights, optimizer state, running
statistics) must **never mutate hidden state**. Instead, thread state
through arguments — state in, new state out — so that backtracking
naturally restores the previous state by abandoning the output.

```
% BAD: hidden mutation, backtracking leaves corrupted state
train_step(MODEL, BATCH)

% GOOD: state threaded explicitly, old state survives backtracking
train_step(MODEL0, BATCH, MODEL1)
optimizer_step(OPT0, GRADS, OPT1)
```

This is the same principle as difference lists or DCG state threading.
If backtracking occurs, `MODEL1` / `OPT1` are simply never used — the
old `MODEL0` / `OPT0` remain valid.

For operations where full state copying is too expensive (large models,
GPU tensors), document this in the plan and consider:
- Making the predicate **deterministic-only** (no backtracking over it)
- Using handle-based snapshots with explicit save/restore predicates
- Keeping it as `++()` escape hatch rather than pretending it's pure

### 3.3 Constraint-like operations (need solver-style wrapping)

Some library operations are best understood as constraints over a domain —
they don't compute a result immediately but instead describe relationships
that a solver resolves. These must be **collected as data terms and passed
to a solver predicate atomically**, not asserted one-by-one with side effects.

This is the pattern used throughout Clausal's constraint infrastructure:

```
% CLP(Q): rational constraints as a tuple, passed to solver
clpq.rational((X + Y <= 10, X >= 0, Y >= 0))

% Z3: integer constraints as a tuple, passed to solver
z3.integer((1 <= X <= 10, 1 <= Y <= 10, X + Y == 15))

% CLP(SAT): boolean constraints, Python bitwise operators
pysat.cadical(X | Y, ~X | Z)
```

The key properties of this pattern:
- Constraints are **data terms** (tuples of AST nodes), not side effects
- They're passed to a **single solver predicate** that processes them atomically
- The solver manages its own backtracking (push/pop scopes, tableau snapshots)
- Individual constraints are meaningless outside the solver context

**When to use this pattern in a wrapper:**
- Optimisation objectives and constraints (PyTorch optimizers, scipy.optimize)
- Graph constraints (NetworkX path/flow constraints)
- Any domain where the user declares *what* should hold and a solver
  figures out *how* — rather than the user specifying computation steps

**Write-up:** For each operation, document in the plan:
- Whether it's pure, stateful, or constraint-like
- If stateful: how state is threaded (or why it can't be)
- If constraint-like: what the constraint terms look like and what solver
  predicate collects them
- Any operations that are fundamentally impure and should stay as `++()`

---

## Step 4 — Classify Operations by Tier

| Tier | Description | State | Examples |
|---|---|---|---|
| **1 — Pure** | Input -> output, no side effects | None | Distance metrics, math, reshaping |
| **2 — Fact tables** | Static knowledge, enumerable | None | Algorithm registries, dtype catalogs |
| **3 — Handle-based** | Construct, query, free | Opaque handle | Models, optimizers, data loaders |
| **4 — Streaming/IO** | Read/write external resources | Side effects | Checkpoints, datasets from disk |

For each operation you identified in Steps 1-2, assign it a tier.

**Write-up:** The predicate catalogue table (Step 6) includes a tier column.
At this stage, just annotate your working list.

---

## Step 5 — Decide Scope

A typical library has hundreds of functions. The wrapper exposes tens of
predicates. The filter:

- **Wrap** what benefits from being relational — backtracking, unification,
  multi-mode, enumeration, composability with other Clausal predicates
- **Skip** what `++lib.function(...)` already handles fine — one-shot pure
  functions with no relational upside
- **Defer** what's niche — note it in a "Future Work" section of the plan

The goal: find the smallest set of predicates that covers the library's
most common workflows. scikit-learn has ~300 classes; the wrapper has ~40
predicates. That 10:1 ratio is typical.

**Write-up:** An explicit "In Scope / Out of Scope / Deferred" section
in the plan, with rationale for borderline calls.

---

## Step 6 — Design the Term Language

Before predicates, design the **terms** — the data structures that flow
between predicates. This is the most important design decision because
terms determine composability.

Terms can be tagged tuples *or* Python classes — use whichever is natural
for the wrapped library. Python classes are first-class in Clausal: they
can be matched in clause heads, constructed in clause bodies, and unified.
If the library has meaningful data classes (e.g. `torch.Tensor`,
`torch.dtype`), use them directly rather than reinventing as tuples.

### Guidelines

- One term per major concept in the API
- If the library has Python classes that matter, use them as terms directly
- Tagged tuples for lightweight groupings that don't correspond to library
  classes: decompose with `tag(FIELD1, FIELD2)` syntax
- Opaque handles are whatever the API uses natively (objects, integers, etc.)
- Check composability: can your terms flow into other wrappers' predicates?
  Can they be collected with `findall`? Pattern-matched in clause heads?

**Write-up:** A "Term Language" section in the plan defining each term
constructor with its fields, semantics, and decomposition examples.

---

## Step 7 — Write the Predicate Catalogue

For each predicate, document:

| Column | Description |
|---|---|
| **Name** | lowercase Prolog-style, following verb conventions (see Checklist A) |
| **Arity variants** | e.g. `/3, /4` for optional params |
| **Modes** | Which arguments can be input (+) vs output (-) |
| **Tier** | 1-4 from Step 4 |
| **Purity** | pure / state-threaded / solver-style / impure (from Step 3) |
| **Bijective?** | If it collapses a procedural pair, note which |
| **Nondeterministic?** | Does it yield multiple solutions? |
| **Brief description** | One line |

Group predicates by subsystem or conceptual area.

**Write-up:** This table *is* the core of the plan document.

---

## Step 8 — Plan Submodule Breakdown (Large Libraries Only)

If the library has clearly independent subsystems, split across files:

```
py/lib.py           # Core / shared terms
py/lib_nn.py        # Neural network layer
py/lib_optim.py     # Optimization layer
py/lib_data.py      # Data loading layer
```

Decide which terms are shared (defined in the core module and imported by
sub-modules) vs local to a subsystem.

**Write-up:** A file layout section in the plan showing the split and
what each file is responsible for.

---

## Step 9 — Write a Showcase Example

Draft a realistic `.clausal` program that demonstrates the wrapper in
action. This serves as both a design validation and the seed of docs.

The example should:
- Import predicates from the wrapper
- Use at least one bijective/multi-mode predicate
- Demonstrate backtracking or enumeration
- Show term decomposition with `is`
- Be a program someone would actually want to write

If the example feels awkward, the predicate design needs revision — go
back to Steps 2/5/6.

**Write-up:** Include the example in the plan. It becomes the "Full
Example" in the docs later.

---

## Step 10 — Phase the Implementation

The plan must break work into **phases**. Each phase is a shippable
increment — it adds predicates, tests, and docs as a unit.

### File structure

Plans live in a folder inside `implementation_plans/` named after the
library:

```
implementation_plans/pytorch/
    overview.md              # Steps 1-9, design decisions, predicate catalogue
    phase1_tensor_core.md    # Self-contained phase plan
    phase2_modules.md        # Self-contained phase plan
    phase3_registries.md     # Self-contained phase plan
```

The overview links to each phase file. Each phase file is standalone —
it can be handed to an implementer (or Sonnet) without the overview.

Phases may be tackled by different agents (e.g. Sonnet) without the
surrounding conversation context. Therefore **each phase must be
self-contained and detailed enough to implement from the phase description
alone**.

Each phase must include:

- **Predicates:** which predicates are implemented in this phase, with
  their full signatures, modes, arity variants, and brief semantics.
- **Context:** what this phase builds on. Reference specific files,
  functions, and line numbers in the existing codebase. For example:
  "Follow the pattern in `clausal/modules/py/scipy_spatial.py` — see
  `_pure()` at line 45 and `_pred()` at line 72." If the phase depends
  on output from a previous phase, say exactly what (file paths, term
  constructors, exported names).
- **Examples:** concrete `.clausal` code showing how the predicates in
  this phase are used. These become the basis for both tests and docs.
- **Reference patterns:** if a predicate follows the same pattern as an
  existing wrapper predicate, name it explicitly. E.g. "handle lifecycle
  follows `make_kd_tree`/`kd_tree_query`/`free` in `py/scipy_spatial.py`."
- **Tests:** `.clausal` integration tests for every predicate in the phase.
  Python unit tests only for infrastructure (handle registries, lazy imports,
  type conversion internals). The majority of tests should be `.clausal`.
- **Docs:** updates to `docs/` for the predicates added. All code examples
  in docs must be backed by tests — if a doc shows a usage pattern, a
  `.clausal` test must exercise it.

Phasing guidelines:
- Phase 1 should cover the core abstraction and the most useful predicates
- Later phases add breadth (more operations, more modes, niche features)
- Each phase is independently reviewable and mergeable
- Dependencies between phases are explicit — name the files/terms/predicates
  that must exist before this phase can start

---

## Step 11 — Review (Issues Section)

Every phase plan must have an **Issues** section, initially empty. This
is primarily for **unexpected issues that arise during implementation** —
not for upfront design predictions (those belong in the overview's
Design Notes).

During implementation, when something turns out to be awkward, broken,
inconsistent, or surprising, record it in the phase's Issues section.
The review question is:

> Is there anything awkward, dubious, inconsistent, or missing?
> Are there untested edge cases? Confusing parts? Naming collisions?

For each issue found:
- **Fix it** — update the plan and code
- **Dismiss it** — document why it's a non-issue
- **Defer it** — assign it to a specific phase that will deal with it

The Issues section stays in the plan as a record of what was learned.

**Write-up:** An "Issues" section at the end of each phase plan file,
starting with `_To be populated during implementation._`

---

# Generic Checklists

The following checklists are reusable across all wrapper plans. Reference
them from any plan document rather than duplicating.

---

## Checklist A — Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Predicate names | Follow wrapped library's convention; usually lowercase | `cross_distance`, `load_model` |
| Datatype constructors | TitleCase if the library uses it | `Tensor`, `Dataset`, `Quantity` |
| Variables | ALLCAPS | `X`, `RESULT`, `HANDLE` |
| Module path | `py.library_name` | `py.scipy_spatial`, `py.torch` |
| Private helpers | `_snake_case` | `_ensure_loaded()`, `_alloc_handle()` |
| Atoms/constants | snake_case | `random_forest`, `euclidean` |

### Abbreviations

Avoid abbreviated names **unless the abbreviation is well-understood
outside of the specific library** — i.e. it's a domain term, not library
jargon. `fft` is fine (standard engineering term). `cdist` is not
(scipy-specific shorthand for `cross_distance`). When in doubt, expand.

### Verb prefix semantics

| Prefix | Meaning | Example |
|---|---|---|
| `make_` | Construct a handle-based object | `make_kd_tree`, `make_model` |
| `load_` | Retrieve from external source | `load_model`, `load_dataset` |
| (no verb) | Fact, relationship, or pure transform | `algorithm`, `shape`, `dtype` |
| `free` | Deallocate a handle | `free/1` |
| `_attr` / `get_` | Extract attribute from handle | `convex_hull_attr`, `get_weight` |

### Argument order

```
predicate(+Input1, +Input2, ..., +Options, -Output)
```

Inputs first, output last. For multi-mode predicates, any argument may be
input or output depending on the mode.

---

## Checklist B — Tier Classification

For each predicate, confirm:

- [ ] **Tier 1 (Pure):** No state. Uses `_pure()` helper or equivalent.
      Input -> output only.
- [ ] **Tier 2 (Fact table):** Enumerable. Uses `trail.mark()/undo()` loop.
      No Python objects held.
- [ ] **Tier 3 (Handle-based):** Uses handle registry or native objects.
      Has matching `Free` if cleanup needed. Handle is whatever the API uses.
- [ ] **Tier 4 (IO):** Side-effecting. Documented as such. Placed at the
      boundary of the program, not in the middle of pure logic.

---

## Checklist C — Bijective Audit

For each candidate pair:

- [ ] Both directions are computationally feasible (not just theoretically
      invertible — `hash(X, H)` is not practically reversible)
- [ ] Reversing doesn't require exhaustive search over an unbounded domain
- [ ] The predicate name is a **noun or relationship**, not a verb
      (`encoding`, not `encode`)
- [ ] Modes are documented: which argument combinations are supported
- [ ] If only partial bijectivity, document which modes work and which don't

---

## Checklist D — Purity and Backtracking Safety

For every predicate, confirm one of these categories:

### Pure predicates
- [ ] No side effects — same inputs always produce same outputs
- [ ] Safe to call multiple times during backtracking
- [ ] No hidden state modified

### State-threaded predicates
- [ ] State flows through arguments: `pred(STATE_IN, ..., STATE_OUT)`
- [ ] Old state remains valid if backtracking abandons `STATE_OUT`
- [ ] No hidden mutation of `STATE_IN` (copy or functional update)
- [ ] If full copy is too expensive, documented as deterministic-only
      or kept as `++()` escape

### Solver-style predicates
- [ ] Constraints expressed as data terms (tuples), not side-effecting assertions
- [ ] Collected and passed to a single solver predicate atomically
- [ ] Solver manages its own backtracking scope (push/pop)
- [ ] Individual constraints have no meaning outside the solver context
- [ ] Pattern follows existing Clausal convention: `solver.domain((C1, C2, ...))`

### Impure predicates (escape hatch)
- [ ] Documented as impure — user knows backtracking may produce unexpected results
- [ ] Placed at program boundaries (IO, checkpointing), not in core logic
- [ ] Considered whether `++()` is more honest than a pseudo-relational wrapper

---

## Checklist E — Predicate Quality

For every predicate in the catalogue:

- [ ] Name follows the wrapped library's convention (usually lowercase;
      TitleCase for datatypes/constructors if the library uses it)
- [ ] Arity variants cover required-only through useful optional combos
- [ ] Defaulted keyword arguments from the wrapped library passed via dict
- [ ] All supported modes documented
- [ ] Nondeterministic predicates identified and marked
- [ ] Tier assigned
- [ ] At least one usage example in .clausal syntax

---

## Checklist F — Term Language Quality

Terms can be tagged tuples or Python classes — use whichever fits the
wrapped library. Python classes are first-class in Clausal: they can be
matched in clause heads, constructed in clause bodies, and unified.

For every term in the design:

- [ ] Represents a concept important to the API
- [ ] If the library has meaningful data classes/structures, use them
      directly as Python classes rather than reinventing as tuples
- [ ] Decomposes with `tag(FIELD1, FIELD2)` syntax (not S-expression style)
- [ ] Opaque handles are whatever the wrapped API uses (objects, integers,
      file descriptors — whatever is natural)
- [ ] Works with `findall`, `copy_term`, clause head matching
- [ ] Documented with constructor signature and field semantics

---

## Checklist G — Scope Validation

- [ ] If something *can* be relational, it *is* relational (multi-mode,
      backtracking, enumeration). Relational benefit is a reason to invest
      design effort, not a gate for inclusion.
- [ ] Thin/thick renames are fine when they serve integration (e.g. handling
      dimensional units via `Quantity`, normalising argument conventions)
- [ ] The "Out of Scope" list exists and has rationale
- [ ] The "Deferred" list captures ideas for future iterations

---

## Checklist H — Plan Document Completeness

Before the plan is considered ready for implementation:

- [ ] Core Abstraction section written (Step 1)
- [ ] Bijective Map table filled (Step 2)
- [ ] Purity analysis complete for all operations (Step 3)
- [ ] Tier classification done for all predicates (Step 4)
- [ ] Scope decision documented with rationale (Step 5)
- [ ] Term Language section with all constructors (Step 6)
- [ ] Predicate Catalogue table complete (Step 7)
- [ ] Submodule breakdown if needed (Step 8)
- [ ] Showcase example validates the design (Step 9)
- [ ] Implementation phased, each phase has predicates + `.clausal` tests + docs (Step 10)
- [ ] All doc examples backed by `.clausal` tests
- [ ] Python tests limited to infrastructure unit tests only
- [ ] Issues section complete — all issues fixed, dismissed, or deferred with phase (Step 11)
- [ ] All names pass Checklist A
- [ ] All predicates pass Checklist D (purity)
- [ ] All predicates pass Checklist E (quality)
- [ ] All terms pass Checklist F
- [ ] Scope passes Checklist G

---

## Design Principles (Reference)

1. **Pure and backtrackable.** Every predicate must be safe to backtrack
   over. Pure functions are ideal. Stateful operations thread state through
   arguments (in/out). Anything that can't be made backtracking-safe should
   stay as `++()` rather than wearing a relational disguise.

2. **Relational over procedural.** If two functions are inverses, make one
   multi-mode predicate. If a collection can be iterated, make it enumerate
   via backtracking.

3. **Bijective collapse.** Every encode/decode, to/from, lookup/reverse-lookup
   pair is a candidate for a single predicate.

4. **Constraints as data.** Operations that describe relationships over a
   domain (optimisation, satisfiability, graph constraints) must collect
   constraints as data terms and pass them to a solver predicate atomically —
   following the `clpq.rational/1`, `z3.integer/1` pattern. Never assert
   constraints as side effects.

5. **Python-native where possible.** Don't reimplement what `++()` gives you.
   But wrapping is fine even for thin renames when it aids integration
   (e.g. `Quantity` for dimensional units, normalising argument conventions).

6. **Small predicate count.** Find the uniform abstraction and build a small
   vocabulary around it.

7. **Use the library's own types.** Python classes from the wrapped library
   are first-class Clausal terms — matchable in clause heads, constructible
   in bodies. Use them directly rather than reinventing as tagged tuples.
   Handles are whatever the API uses natively.

8. **Fail, don't crash.** Python exceptions become predicate failure, enabling
   backtracking. Never propagate exceptions to the user.

9. **Follow the library's naming.** Predicate names match the wrapped
   library's conventions. Usually lowercase; TitleCase for datatypes if
   the library uses it. ALLCAPS variables. No unnecessary renaming.
   Avoid abbreviations unless they're domain-standard (e.g. `fft` is fine,
   `cdist` is not — expand to `cross_distance`).

10. **Progressive arity.** Required args at the core arity. Defaulted
    keyword arguments from the wrapped library passed via dict.
