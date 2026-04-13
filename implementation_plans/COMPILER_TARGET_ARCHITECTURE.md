# Compiler target architecture

Companion to `clausal/logic/compiler/README.md` (which describes what
the compiler *is today*) — this document describes what the compiler
*should become*. It's a proposal, not a plan: it commits to a set of
design principles and sketches the structure they imply.

A separate migration plan (step 4 of the broader refactor) will turn
this into concrete phased work.

---

## 1. Design goals and principles

The stated goal is: **understandability, rigour, and correctness by
construction**, not minimum-line-count or minimum-effort.

Ten principles follow. Each is a thing we explicitly commit to.

### P1. Phases are named, typed, and pure where possible

Each compilation phase has an explicit name, an input type, and an
output type. Phases connect by passing typed values, not by shared
mutable state. When mutable state is unavoidable (e.g. `var_context`),
its ownership and lifetime are specified.

### P2. Strategy is an explicit abstraction, not a duplicated implementation

Shallow and trampoline compilation share most structure. The parts
that differ are captured behind a `Strategy` interface with a
documented contract. Neither strategy gets to cheat by reading from
the other's internals.

### P3. Runtime helpers and compile-time helpers are separated

Code that runs inside compiled predicates (unification helpers,
trampoline protocol, etc.) lives in a different package from code
that runs during compilation. This makes it structurally impossible
to accidentally couple them.

This is **not** about AOT vs JIT — the compiler itself runs at
Python runtime every time a `.clausal` module is imported, every
time `assertz/1` adds a new clause to a dynamic predicate, and any
time a user invokes the compile API directly. The split is between
*compilation-time code paths* (the `compiler/` package) and
*compiled-predicate runtime code paths* (the `runtime/` package).
Both execute in the same Python process; they just do different
jobs.

### P4. Optimisations are distinct passes, not embedded in the main compiler

Each optimisation (indexing, TRO, destructive-reuse, call-site
specialisation) is its own pass with a clear before/after contract.
Turning an optimisation off should be one flag, and should never
affect correctness.

### P5. Mutable state is owned by a named type

No module-level mutable state (other than a module-level fresh-name
counter that is explicitly a process-wide service). No thread-locals
as backchannels. `CompilationContext` owns what compilations mutate;
`PredicateArtifact` owns what compiled outputs hold.

### P6. An intermediate representation separates "what" from "how"

Body goals compile first into a small, strategy-agnostic IR ("goal
operations"). Strategy-specific lowering walks the IR and emits
Python AST. Analyses and optimisations operate on the IR, not on
source terms or Python AST.

### P7. Safety invariants are asserted, not assumed

Every phase boundary has an `invariant(...)` check (compiled out in
release, present in tests). If a phase's precondition is violated, we
get a readable failure message, not a mystery `UnboundLocalError` in
generated code twelve levels up.

### P8. Generated code is debuggable

Every AST node carries source position info (see
`todo/ast_source_locations.md`). Tracebacks from compiled predicates
point at the `.clausal` source line, not at a generated file with
location 0:0.

### P9. No reach-arounds

Every submodule depends on clearly named other submodules. No `_m.*`
lazy attribute access. No `for _n in dir(_m)` bulk-copy. No
`__getattr__` delegation. If a circular dependency exists, we name
and break it explicitly (via an interface / protocol / abstract
method), not paper over it.

### P10. Public API is small and stable

External callers (`solve.py`, tests, tools) see a tight surface:
about a dozen functions, clearly documented, with type annotations
that describe contracts — not a soup of dozens of private helpers
that happen to be importable.

---

## 2. End-state package structure

```
clausal/logic/
├── compiler/              ← compile-time only
│   ├── __init__.py              – explicit public API
│   ├── README.md                – this document's companion
│   ├── pipeline.py              – top-level orchestration
│   ├── context.py               – CompilationContext + FreshNames
│   ├── ir.py                    – intermediate representation
│   ├── strategy.py              – Strategy interface + two implementations
│   │
│   ├── phases/
│   │   ├── load.py              – phase 1 (target resolution, globals)
│   │   ├── analyse.py           – phase 2 (indexing / TRO / DR analysis)
│   │   ├── plan.py              – phase 3 (dispatch plan)
│   │   ├── head.py              – phase 4 (head → match pattern)
│   │   ├── body.py              – phase 5 (goals → IR → AST)
│   │   ├── assemble.py          – phase 6 (FunctionDef assembly)
│   │   ├── codegen.py           – phase 7 (AST → callable)
│   │   └── install.py           – phase 8 (db/class registration)
│   │
│   ├── optimisations/
│   │   ├── __init__.py
│   │   ├── indexing.py          – groundness / joint / secondary
│   │   ├── tro.py               – tail recursion optimisation
│   │   ├── destructive_reuse.py – source-dead container reuse
│   │   └── call_site.py         – bucket-ref specialisation
│   │
│   └── emit/
│       ├── __init__.py
│       ├── ast_helpers.py       – _name, _call, _fresh, …
│       ├── term_expr.py         – term → AST expression lowering
│       ├── head_match.py        – head patterns + list-guards
│       └── goal_shallow.py      – IR → AST, shallow strategy
│           goal_trampoline.py   – IR → AST, trampoline strategy
│
└── runtime/                ← used by compiled code only
    ├── __init__.py
    ├── list_unify.py            – _head_list_unify_input_py, etc.
    ├── body_star_unify.py       – body-Is runtime
    ├── tramp_call.py            – _tramp_call bridge
    └── _list_unify.c            – C-accelerated versions
```

Two rules:

- Nothing under `runtime/` imports from `compiler/`.
- Nothing under `compiler/` is imported by compiled predicate code
  (base_globals refers only to runtime helpers, plus term-class refs
  from `clausal.terms`).

A CI check enforces these rules.

---

## 3. The pipeline, as functions

The compiler is a sequence of eight pure functions. Each takes a
`CompilationContext` plus the previous phase's output, and produces
the next phase's input. The top-level orchestrator is a straightforward
composition:

```python
# compiler/pipeline.py

def compile_predicate(
    functor: str,
    arity: int,
    clauses: list[Clause],
    *,
    strategy: Strategy,
    db: Database | None = None,
    module_globals: Mapping[str, Any] = MappingProxyType({}),
    pred_cls: PredicateMeta | None = None,
) -> CompiledPredicate:
    """Compile a predicate into a dispatch function, end-to-end."""
    ctx = CompilationContext(
        functor=functor,
        arity=arity,
        clauses=clauses,
        strategy=strategy,
        db=db,
        module_globals=module_globals,
        pred_cls=pred_cls,
    )
    loaded    = phases.load(ctx)
    analysed  = phases.analyse(ctx, loaded)
    planned   = phases.plan(ctx, analysed)
    heads     = phases.head(ctx, planned)
    bodies    = phases.body(ctx, planned)
    units     = phases.assemble(ctx, planned, heads, bodies)
    functions = phases.codegen(ctx, units)
    artifact  = phases.install(ctx, functions)
    return artifact
```

Each phase lives in `phases/<name>.py` with exactly one public
function. Each has a docstring stating its input / output types,
preconditions, postconditions, and which `CompilationContext` fields
it reads vs mutates.

### Phase signatures

```python
# phases/load.py
def load(ctx: CompilationContext) -> LoadedPredicate: ...
#   Pre:  ctx.clauses is the raw clause list.
#   Post: ctx.base_globals populated with types, thunks, resolved
#         call targets.  Returns LoadedPredicate carrying the
#         type / thunk / target info for downstream phases.

# phases/analyse.py
def analyse(ctx: CompilationContext, loaded: LoadedPredicate) -> AnalysedPredicate: ...
#   Pre:  load() complete.
#   Runs all analyses (indexing, TRO, DR) and returns their results.
#   Pure w.r.t. ctx — analyses observe, they don't mutate.

# phases/plan.py
def plan(ctx: CompilationContext, analysed: AnalysedPredicate) -> DispatchPlan: ...
#   Translates the analysis into a DispatchPlan: a tree of Bucket
#   nodes, each holding the clauses to compile and what role they
#   play (fallback / index-key / default / inlined / ...).

# phases/head.py
def head(ctx: CompilationContext, planned: DispatchPlan) -> dict[BucketId, HeadCompilation]: ...
#   For every bucket in the plan: compile each clause head into a
#   (match_pattern, guard_stmts) pair, plus head-var context.

# phases/body.py
def body(ctx: CompilationContext, planned: DispatchPlan) -> dict[BucketId, BodyCompilation]: ...
#   For every bucket / clause: lower the body goals to the IR, then
#   lower the IR to Python AST via ctx.strategy.

# phases/assemble.py
def assemble(
    ctx: CompilationContext,
    planned: DispatchPlan,
    heads: dict[BucketId, HeadCompilation],
    bodies: dict[BucketId, BodyCompilation],
) -> CompilationUnit: ...
#   Build one ast.FunctionDef per bucket + the dispatch wrapper(s).

# phases/codegen.py
def codegen(ctx: CompilationContext, units: CompilationUnit) -> dict[str, Callable]: ...
#   ast.fix_missing_locations (on anything that's genuinely generated
#   rather than source-derived), compile(), exec() into callables.

# phases/install.py
def install(ctx: CompilationContext, fns: dict[str, Callable]) -> CompiledPredicate: ...
#   Register with ctx.db / ctx.pred_cls; return an artifact handle.
```

---

## 4. Core types

### `CompilationContext`

Single owner of per-compilation state. Passed explicitly to every
phase; not a thread-local.

```python
@dataclass
class CompilationContext:
    # Immutable inputs — set at construction, never mutated.
    functor: str
    arity: int
    clauses: list[Clause]
    strategy: Strategy
    db: Database | None
    module_globals: Mapping[str, Any]  # frozen via MappingProxyType
    pred_cls: PredicateMeta | None

    # Mutable — grows monotonically during compilation.
    var_context: dict[int, str] = field(default_factory=dict)
    base_globals: dict[str, Any] = field(default_factory=dict)
    fresh: FreshNames = field(default_factory=FreshNames)

    # Populated by later phases for earlier-phase-aware emission.
    locked_dispatch_keys: frozenset[str] = frozenset()
    bucket_ref_map: dict[BucketRefKey, str] = field(default_factory=dict)

    # Trail/self/parent parameter names — configurable but default to
    # the compiler's reserved names.
    trail_name: str = "trail"
    self_name: str = "this_generator"
    parent_name: str = "_tramp_parent"
```

Ownership rule: **every mutable field is mutated by exactly one phase**
(or at most two, if documented). Violations surface in code review.

### `FreshNames`

Per-compilation fresh-name generator. Replaces today's module-level
`_compile_counter` global. Counter resets per compilation, so
names are deterministic given the input (helpful for testing and
diffing generated AST).

```python
class FreshNames:
    def __init__(self) -> None:
        self._counter = 0
    def new(self, prefix: str = "_t") -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"
```

### `Strategy` (protocol)

```python
class Strategy(Protocol):
    # Hooks emitted by body-IR lowering.
    # Strategy identity is the class itself — callers that need to
    # dispatch on strategy use isinstance() or match/case, not a
    # string field.  A __repr__ exists for logging.
    def emit_leaf_yield(self, ctx: CompilationContext) -> ast.stmt:
        """AST for 'a solution is available' — the innermost k_stmts."""

    def emit_exhaustion_yield(self, ctx: CompilationContext) -> ast.stmt | None:
        """AST for 'search exhausted' at the end of the function.
        Shallow returns None (the generator just returns)."""

    def emit_sub_call(
        self, ctx: CompilationContext,
        fname: str, arity: int, arg_exprs: list[ast.expr],
        k_stmts: list[ast.stmt],
    ) -> list[ast.stmt]:
        """AST for calling a sub-predicate and wrapping the continuation.
        Shallow: ast.For over the sub-generator.
        Trampoline: StepGenerator + yield loop."""

    # Strategy features — queried by optimisation passes.
    supports_tro: bool
    supports_destructive_reuse: bool

    # Clause preprocess — trampoline applies DR rewrite; shallow is
    # identity.  Returns a fresh goal list.
    def preprocess_clause(self, clause: Clause) -> list[Any]: ...

    # Compiled function signature — shallow and trampoline differ in
    # their parameter layout.
    def function_params(self, ctx: CompilationContext, arg_names: list[str]) -> list[str]: ...
```

Two implementations: `ShallowStrategy`, `TrampolineStrategy`. They
live in `compiler/strategy.py` and are 30-50 lines each.

### `GoalOp` — the body IR

A small tagged union of *operations* that a compiled body reduces
to. **Target-agnostic and strategy-agnostic**: no Python AST, no
yield protocols, no C types, no LLVM instructions. Just logic-level
operations over logic-level operands.

```python
# Operands are logic-level — the same types Clause.body uses.
# Term = Var | Compound | int | str | ... | TupleLiteral | DictTerm | ...
# Subset of clausal.terms chosen for the IR.

class GoalOp:
    """Base for compiled goal operations."""

# ── Binding / constraint ops ──

@dataclass
class Unify(GoalOp):
    l: Term
    r: Term
    # Needs trail mark/undo around the k-continuation? Yes for unify,
    # no for dif (which only posts a constraint).
    needs_mark: bool = True

@dataclass
class Dif(GoalOp):
    """Post a dis-equality constraint on two terms."""
    l: Term
    r: Term

@dataclass
class StructuralEq(GoalOp):
    """Prolog ==/2 — succeed iff structurally identical without binding."""
    l: Term
    r: Term
    negate: bool = False  # \==/2

@dataclass
class ArithEval(GoalOp):
    """Evaluate an arithmetic expression and unify with target."""
    target: Term       # usually a Var
    expr: ArithExpr    # Add | Sub | Mult | ... tree

@dataclass
class FDCompare(GoalOp):
    """CLP(FD) comparison constraint."""
    op: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    l: Term
    r: Term

# ── Control flow ops ──

@dataclass
class Sequence(GoalOp):
    ops: list[GoalOp]

@dataclass
class Alternate(GoalOp):
    """Disjunction (Or)."""
    ops: list[GoalOp]

@dataclass
class Negate(GoalOp):
    """Negation as failure."""
    op: GoalOp

@dataclass
class Branch(GoalOp):
    """If-then-else.  reified_test is set for reifiable conditions
    (Unify, Dif, FDCompare) so backends can emit the three-way
    reified form; None means general single-evaluation ITE."""
    test: GoalOp
    then: GoalOp
    else_: GoalOp
    reified_test: Literal["unify", "dif", "fd_eq", ...] | None = None

# ── Membership ops ──

@dataclass
class MemberIn(GoalOp):
    """elem in collection — backtracks over collection elements."""
    elem: Term
    collection: Term
    negate: bool = False  # NotIn

# ── Call ops ──

@dataclass
class SubCall(GoalOp):
    """Call a named sub-predicate.  Resolved call target sits in
    base_globals (by phase 1), so fname is enough — no need to
    reference a Python callable here."""
    fname: str
    arity: int
    args: list[Term]
    # Optimisation hints — set by passes, consumed by backends.
    direct_bucket_ref: str | None = None    # call-site specialisation
    tail_recursive: bool = False            # TRO eligibility
    destructive_reuse: bool = False         # DR-rewritten variant

@dataclass
class MetaCall(GoalOp):
    """Meta-predicate call (once, findall, catch, setup_call_cleanup, …).
    The 'kind' enumerates a closed set; args is a structured record
    whose shape is determined by kind.  Backends pattern-match on
    kind to lower."""
    kind: Literal[
        "once", "call_nth", "count_all", "setup_call_cleanup",
        "freeze", "when", "findall", "bagof", "setof",
        "throw", "catch", "catch_error", "catch_recover",
        "forall", "halt",
    ]
    args: dict[str, Any]  # kind-specific field bag

# ── Low-level ops ──

@dataclass
class ListPatternUnify(GoalOp):
    """Runtime bidirectional list-pattern unification guard.
    Backends emit a call to their runtime's equivalent of
    _head_list_unify_input/output.  See compiler/README.md §7."""
    target: Term
    before_vars: list[Term]
    star_var: Term | None
    after_vars: list[Term]
    phase: Literal["input", "output"]
```

The IR captures **meaning**, not execution. It is the pivot point
between the analysis passes (which don't need to know about targets
or strategies) and the lowering passes (which do).

Why this shape:

- Analysis passes (TRO, DR, call-site specialisation) run on
  `GoalOp` trees and write back optimisation hints (fields on
  `SubCall` etc.). They don't need to know about yield protocols.
- Strategy-specific *lowering* happens at one place per op kind,
  per backend. Shallow and trampoline differ only in the lowering
  of a small number of ops (`SubCall`, the leaf yield at the end
  of a `Sequence`, `Negate`).
- **Multiple backends are planned** — Python AST today, potentially
  C / LLVM / WASM later. The IR deliberately does not reference
  any target's concrete types. See §5b *Future backends*.

### Operands in the IR

`Term` in the IR is the same type clauses carry — `Var`, `Compound`,
scalars, `DictTerm`, `TupleLiteral`, `StarUnpack`, etc. The IR does
**not** pre-lower terms to AST expressions — that's a backend
concern.

Arithmetic expressions use a distinct mini-IR (`ArithExpr` — Add,
Sub, Mult, Negate, …) because arithmetic has its own evaluation
semantics that differ from general term handling (native math vs
unification).

### `DispatchPlan`

```python
@dataclass
class DispatchPlan:
    root: DispatchNode

class DispatchNode: ...  # tagged union

@dataclass
class Flat(DispatchNode):
    """All clauses in one bucket."""
    clauses: list[Clause]

@dataclass
class Indexed(DispatchNode):
    """Single-position index."""
    pos: int
    buckets: dict[Any, DispatchNode]
    default: DispatchNode
    fallback: DispatchNode

@dataclass
class Joint(DispatchNode):
    """(arg_i, arg_j) joint key."""
    pos_i: int
    pos_j: int
    buckets: dict[tuple[Any, Any], DispatchNode]
    single_i: DispatchNode
    single_j: DispatchNode
    fallback: DispatchNode

@dataclass
class Secondary(DispatchNode):
    """Two-level hierarchical."""
    pos_i: int
    pos_j: int
    levels: dict[Any, DispatchNode]  # each is itself Indexed on pos_j
    fallback: DispatchNode

@dataclass
class Groundness(DispatchNode):
    """Groundness-keyed: plans sorted by selectivity."""
    plans: list[tuple[int, dict[Any, DispatchNode]]]
    fallback: DispatchNode
```

The plan is a **pure data structure**, built in phase 3. Phases 4-6
consume it by recursion. Emission of the dispatch wrappers is
entirely driven by the plan's shape.

---

## 5. Two axes of variation: strategy and backend

The compiler has **two** orthogonal axes along which output varies:

- **Strategy** — how solution enumeration and backtracking are
  structured. Today's "shallow" and "trampoline" are both
  *Python-language* strategies; they differ in call-stack
  discipline. In a low-level backend (C / LLVM), strategy takes
  different forms — perhaps an explicit choice-point stack plus
  continuations, or a WAM-style environment frame.

- **Backend** — what kind of code we emit. Python AST is today.
  C source, LLVM IR, WASM are potential futures.

The pipeline through phase 5 (IR production) is independent of
both. Phases 6 (assemble) and 7 (codegen) are backend-specific;
strategy influences emission within a backend.

```
         ┌───────────────────────────────────────────────┐
         │  phases 1-5: target-agnostic                  │
         │    load, analyse, plan, head, body → IR       │
         │    (optimisation passes operate here)         │
         └───────────────────────────────────────────────┘
                              │
                              ▼                       ┌── ShallowStrategy
         ┌────────────────────────────┐               │
 Python  │ lower_python_{shallow,     │ ◀─── pick ────┤── TrampolineStrategy
 backend │ trampoline}(IR, ctx)       │               │
         │ → ast.FunctionDef          │               │
         └────────────────────────────┘               │
                              │                       │
                              ▼                       │
         ┌────────────────────────────┐               │
         │ phases 6-8 (Python path):  │               │
         │   assemble, codegen,       │               │
         │   install                  │               │
         └────────────────────────────┘               │
                                                       │
         ┌────────────────────────────┐                │
 Future  │ lower_c / lower_llvm /     │ ◀── pick ──────┘
 backends│ lower_wasm(IR, ctx)        │
         │ → target-specific output   │
         └────────────────────────────┘
```

Today, only the Python backend exists. The IR is designed so that
adding a backend means: implement `lower_<backend>(ir, ctx)` +
a backend-specific assemble/codegen/install path. The analyses and
optimisations run unchanged on the shared IR.

## 6. Future backends (C / LLVM / WASM)

This subsection is aspirational — no code today — but the target
architecture must not foreclose on it. Notes on what each backend
would need:

### C source backend

- Target: a `.c` file defining each predicate as a function taking
  an explicit choice-point stack.
- Compiled via `cc` into a `.so` loaded via `ctypes` or a Python
  C-API extension.
- Strategy: probably a single strategy — WAM-style environment
  frames with an explicit trail and choice-point stack. No Python
  generator protocol available; no trampoline needed.
- Runtime: a C runtime library providing `unify`, `deref`, `trail`,
  `deref_walk`, the list-unify helpers. Mirrors the current
  `clausal/logic/_list_unify.c` etc. but standalone (not a Python
  extension).
- Use cases: hot predicates benchmarked against the Python
  compiled version, production-sensitive deployments.

### LLVM backend

- Target: LLVM IR directly via `llvmlite` (or similar).
- JIT-compilable for hot predicates (ties into
  `todo/jit_indexing.md`).
- AOT-compilable for distribution.
- Strategy: similar to C backend.
- Runtime: could share the C runtime library.
- Use cases: performance-critical computation-heavy predicates.

### WASM backend

- Target: portable WASM module loadable from Python, JS, or
  anywhere WASM runs.
- Enables browser / edge-deployment use cases.
- Probably lowers via LLVM → WASM (leveraging the LLVM backend)
  rather than emitting WASM text directly.

### What the architecture gives us for free

Because the IR is target-agnostic, **adding any of these backends
does not require changes to the analysis or optimisation passes**.
TRO, destructive reuse, indexing, call-site specialisation all
operate on `GoalOp` trees. A new backend consumes the optimised IR
and lowers it to its target language.

What each new backend *does* require:

- A new `lower_<target>(ir, ctx)` function.
- A new `<target>_Strategy` implementation (if the backend has
  strategy choices — a native C backend might have just one).
- A new runtime library (in the target's language).
- New `assemble`, `codegen`, `install` phases appropriate to the
  target.
- Tests verifying the backend produces the same solutions as the
  Python backend on a shared test corpus.

### What won't transfer

Some current Python-specific features may not map cleanly:

- Python `ast.Lambda` goal arguments — backends that don't have
  first-class closures need an alternative representation.
- `PyThunk` f-string escapes — native backends probably need a
  callback-to-Python or a pre-compiled expression.
- Some Python builtins (`write/1`, `print_term/1`) are trivially
  implementable in any backend; others (`time_goal/2` with
  introspection) tie more deeply to Python.

These are acknowledged limitations, not architectural problems. A
minimal C backend would compile a defined subset of Clausal
predicates (pure logic + arithmetic + FD) and fall back to the
Python backend for features the C backend doesn't yet support. The
target architecture supports this falback — each predicate chooses
its backend at compile time.

---

## 7. Runtime / compile-time boundary

`clausal/logic/runtime/` holds everything that runs inside compiled
predicates:

- `list_unify.py` — `_head_list_unify_input_py`, `_head_list_unify_output_py`,
  `_head_multi_star_error`, `_body_star_unify`, `_build_star_list`,
  `_build_multi_star_list`, `_body_multi_star_unify`, `_in_iter`.
  Plus the C-extension optimised versions.
- `tramp_call.py` — `_tramp_call` bridge for simple-mode callers of
  trampoline-mode dispatch fns.

`clausal/logic/compiler/` may NOT import from `clausal/logic/runtime/`
(it doesn't need to; it references runtime helpers by name in
`base_globals`). Verified by a CI check that scans imports.

Compiled functions reference runtime helpers by the names present in
their `base_globals`. The compiler doesn't need the helpers imported
to emit a call site; it just emits `_name("_head_list_unify_input")`
and relies on `base_globals["_head_list_unify_input"]` being set by
the "load" phase.

This separation is **physical**, not just conventional. It prevents
future cross-contamination.

---

## 8. Safety and invariants

Principle P7: invariants are asserted. Each phase states its
preconditions and postconditions in docstring and in code.

Examples of invariants that would become explicit assertions:

```python
def body(ctx: CompilationContext, planned: DispatchPlan) -> ...:
    """Lower bodies for each bucket.

    Precondition: for every clause, every Var reachable from the body
                  tree is in ctx.var_context.
    """
    assert_body_vars_preallocated(ctx, planned.all_clauses())
    # … rest of phase …
```

```python
def assert_body_vars_preallocated(
    ctx: CompilationContext, clauses: Iterable[Clause]
) -> None:
    for clause in clauses:
        for var in walk_vars(clause.body):
            if var._id not in ctx.var_context:
                raise InvariantError(
                    f"Var {var!r} not pre-allocated in var_context "
                    f"before body compilation of {ctx.functor}/{ctx.arity} "
                    f"— phase 4/5 invariant violated"
                )
```

Invariants documented in the README §10 become assertions:

1. Body Vars pre-allocated before `body` phase.
2. Call targets resolvable in `base_globals` before `body` phase.
3. `_mark` / `undo` paired on every branch. (Checked by a post-phase
   AST walker; emission helpers enforce at build time by pairing.)
4. Trampoline funcdefs end with exactly one `(parent, _DONE)` yield.
   (Checked by AST walker in phase 6.)
5. TRO rewrites are semantics-preserving. (Type system of the
   analysis ensures `_tro_args_safe` returned True.)
6. Destructive-reuse rewrite only applies to eligible sites. (Ditto.)

In release builds these assertions can be compiled out with `-O`; in
tests (and CI) they run. When they fire, the failure message points
to the offending clause / phase.

---

## 9. Strategy contract

The `Strategy` protocol formalises what each strategy must provide.
Both implementations are small:

```python
# strategy.py

class ShallowStrategy:
    supports_tro = False
    supports_destructive_reuse = False

    def emit_leaf_yield(self, ctx):
        return ast.Expr(ast.Yield(ast.Constant(None)))

    def emit_exhaustion_yield(self, ctx):
        return None  # pure generator; falls off the end

    def emit_sub_call(self, ctx, fname, arity, arg_exprs, k_stmts):
        iter_expr = build_dispatch_iter(ctx, fname, arity, arg_exprs)
        return [ast.For(
            target=_name("_", ast.Store()),
            iter=iter_expr,
            body=k_stmts or [ast.Pass()],
            orelse=[],
        )]

    def preprocess_clause(self, clause):
        return list(clause.body)  # no rewrite

    def function_params(self, ctx, arg_names):
        return arg_names + [ctx.trail_name, "k"]
```

```python
class TrampolineStrategy:
    supports_tro = True
    supports_destructive_reuse = True

    def emit_leaf_yield(self, ctx):
        return _yield_step(_name(ctx.parent_name), ast.Constant(None))

    def emit_exhaustion_yield(self, ctx):
        return _yield_step(_name(ctx.parent_name), _name("_DONE"))

    def emit_sub_call(self, ctx, fname, arity, arg_exprs, k_stmts):
        return build_trampoline_sub_call(ctx, fname, arity, arg_exprs, k_stmts)

    def preprocess_clause(self, clause):
        flat = flatten_and(clause.body)
        eligible = find_dr_goals(clause)
        return apply_dr(flat, eligible)

    def function_params(self, ctx, arg_names):
        return [ctx.self_name, ctx.parent_name] + arg_names + [ctx.trail_name]
```

Both strategies are ~30 lines each, sharing nothing but the protocol.
All the code that looks the same between them lives once, in the
shared pipeline.

A **test harness** compiles representative clauses under both
strategies and asserts that the compiled results, when driven,
produce the same solutions. This is the safety net that lets us
aggressively dedupe without fear.

---

## 10. What goes where: a concrete example

Consider compiling `append/3`:

```clausal
append([], B, B)
append([H, *T], B, [H, *R]) <- append(T, B, R)
```

**Phase 1 (load)** — Scan clauses for `(fname, arity)` targets;
find `append/3` recursively, resolve to own `PredicateMeta`. Collect
types (none). Collect PyThunks (none). Populate `ctx.base_globals`
with runtime helpers + `append` class ref + head-type dict.

**Phase 2 (analyse)** — Run indexing analysis: first-arg key varies
(`[]` vs list). Indexing eligible at position 0. Clause 1 is base
case; clause 2 is self-recursive with a simple tail call. TRO
eligible (via `TrampolineStrategy.supports_tro`). DR eligible?
Yes — clause 2's `append(T, B, R)` with source = `T`; `T` dead
after the call. Record as a DR candidate.

**Phase 3 (plan)** — `DispatchPlan(root=Indexed(
pos=0, buckets={empty_list: Flat([clause1]),
list_cons: Flat([clause2])}, default=Flat([]), fallback=Flat(both)))`.

**Phase 4 (head)** — For bucket 1: head is `append([], B, B)`,
compile pattern to `case ([], _v_B, _v_B_1):` with dup-guard
`unify(_v_B, _v_B_1, trail)`. For bucket 2: head is
`append([H, *T], B, [H, *R])`, list patterns → MatchAs capture +
list_unify guards.

**Phase 5 (body)** — For bucket 1: empty body → `Sequence([])`
(noop) — IR is trivial. For bucket 2: body is `append(T, B, R)` →
`Sequence([SubCall(fname="append", arity=3, arg_exprs=[T, B, R])])`,
with TRO rewrite marking it as a tail-recursive SubCall. Lower IR
to AST via `ctx.strategy.emit_sub_call`. TRO pass (phase 5b) rewrites
the SubCall into a loop-restart pattern if strategy supports it.

**Phase 6 (assemble)** — Build one `FunctionDef` per bucket
(`append__3__p0_b0`, `append__3__p0_b1`, `append__3__p0_dflt`),
plus the dispatch wrapper `append__3` built from
`Indexed(pos=0, ...)`.

**Phase 7 (codegen)** — Compile each FunctionDef.

**Phase 8 (install)** — Register `append__3` on the database /
`PredicateMeta`.

Every step has clear input / output. No phase reaches forward or
backward. No mutable state is shared across phase boundaries except
through named fields on `ctx`.

---

## 11. Optimisations as passes

Each optimisation is a pass with a clear before/after contract.

### TRO pass

- **When:** phase 5b (after body IR, before AST lowering).
- **Input:** `Sequence(ops)` where the last op is a `SubCall` to the
  same functor/arity, and all preceding ops are deterministic.
- **Output:** `Sequence(ops_prefix + [TailRecurse(new_args)])` where
  `TailRecurse` is a new IR op meaning "restart the loop with new
  args".
- **Precondition:** `ctx.strategy.supports_tro` is True.
- **Correctness:** `_tro_args_safe(clause)` returned True during
  analysis.

### Destructive-reuse pass

- **When:** phase 5a (before TRO).
- **Input:** `SubCall(fname=append, ...)` (or dict_put / set_union)
  where source arg is a dead body-only Var.
- **Output:** `SubCall(fname=_dr_append__3, ...)`.
- **Precondition:** `ctx.strategy.supports_destructive_reuse`.
- **Correctness:** `_find_destructive_reuse_goals` returned the site.

### Indexing analysis

- **When:** phase 2.
- **Input:** clause list.
- **Output:** `AnalysedPredicate.indexing_plan` — describes which
  positions are viable and what buckets to build.
- **Consumers:** phase 3 (plan builds dispatch tree from this).

### Call-site bucket-ref specialisation

- **When:** phase 5, during body compilation of each clause.
- **Input:** `SubCall(fname, arity, arg_exprs)` where some arg_exprs
  are static constants AND the called predicate has a known
  indexing plan.
- **Output:** `SubCall` with `direct_bucket_ref="{fname}__p0_bK"`.
  Emission skips the dispatch wrapper and calls the bucket directly.
- **Correctness:** the bucket's key equals the static arg's runtime
  key.

Each pass is one file. Each has a test that asserts pre/post
behavioural equivalence on a suite of test predicates.

---

## 12. Thread-local state: none

Today's `_compile_context_local: threading.local` becomes fields on
`CompilationContext`. The thread-local existed because the compile
context wasn't threaded through every helper — now it is.

Specifically:

- `locked_dispatch_keys` → `ctx.locked_dispatch_keys` (frozenset,
  set by phase 1).
- `bucket_ref_map` / `joint_bucket_ref_map` → `ctx.bucket_ref_map`
  (dict, populated by the call-site specialisation pass during
  phase 5).

Phase 8 (install) discards ctx; nothing survives compilation.

Thread-safety becomes trivial because there's no shared state. Two
compilations on different threads have two `CompilationContext`
instances; they never see each other.

The process-level `FreshNames` counter (today's `_compile_counter`)
becomes per-ctx — names are scoped to one compilation. Two
compilations produce identical names for identical inputs, which is
useful for testing and diffing.

---

## 13. Public API

`clausal/logic/compiler/__init__.py` exposes:

```python
__all__ = [
    # Main entry points
    "compile_predicate",                  # new unified entry
    "compile_predicate_trampoline",       # back-compat alias
    "compile_predicate_shallow",          # back-compat alias
    "compile_predicate_ast",              # returns FunctionDef, for tools
    # Strategies
    "Strategy", "ShallowStrategy", "TrampolineStrategy",
    # Context — exposed for callers that need it (e.g. partial compilation)
    "CompilationContext",
    # Types callers need to construct or inspect
    "CompiledPredicate", "DispatchPlan",
]
```

The `__getattr__` delegation to `_monolith` goes away. Private
helpers are private — callers that imported them from the public
module get an error telling them where to import from instead (a
deprecation period is reasonable — one release with a `__getattr__`
that emits `DeprecationWarning` and forwards, then removal).

---

## 14. How this differs from today — summary table

| Concern                          | Today                                       | Target                                   |
|----------------------------------|---------------------------------------------|------------------------------------------|
| Pipeline structure               | Implicit; most logic in one 500-line funcdef | 8 named phases, each its own file/function |
| Strategy abstraction             | Parallel implementations, ad-hoc dedup       | Explicit `Strategy` protocol, two impls, shared pipeline |
| Intermediate representation      | None — clauses → AST directly                | `GoalOp` tagged union between clause and AST |
| Optimisations                    | Interleaved with main compile                | Separate passes, each with before/after contract |
| Mutable state                    | Scattered (dict + thread-local + globals)    | Owned by `CompilationContext`; no thread-locals |
| Runtime vs compile-time          | Mixed in one package                         | Two packages, enforced by CI             |
| Cross-submodule coupling         | `_m.*` lazy access, `_monolith` shim         | Explicit deps; no reach-arounds          |
| Invariants                       | Implicit; docstring comments at best         | Asserted at phase boundaries             |
| Source-location fidelity         | `fix_missing_locations` wipes everything     | Terms carry positions; AST nodes inherit |
| Public API                       | Broad; many private imports leak out         | Small, documented, stable                |
| Thread-safety                    | Implicit; relies on GIL + thread-local       | Explicit; no shared state                |

---

## 15. Open questions to resolve before migrating

These need answers, not just hand-waving:

**Q1. Does `GoalOp` actually simplify things, or does it add a layer
without payoff?**
Risk: building an IR for a compiler that already works may be
over-engineering. Mitigation: prototype IR lowering for a small
subset (Unify, SubCall, Sequence, Branch) and see if the resulting
strategy-specific emit functions are short and obvious. If they're
as long as today's `compile_goal` arms, the IR isn't earning its
keep.

**Q2. Is `Strategy` a protocol or an ABC?**
Python protocols are duck-typed and don't require runtime checks;
ABCs do. I lean protocol (simpler, more flexible); the ABC version
would only matter if we want `isinstance(s, Strategy)` checks in
client code, which we probably don't.

**Q3. Where do the C-accelerated runtime helpers live?**
Today: `clausal/logic/_list_unify.c` / `_trampoline.c` / etc.
alongside the Python modules that use them. Under the proposed
separation they'd move to `clausal/logic/runtime/`. The build system
(setup.py) needs updating. Not hard, but worth flagging.

**Q4. Do we keep `compile_predicate_shallow_ast` etc. as separate
entry points, or have one `compile_predicate_ast(strategy=...)`?**
The `_ast` variants are used by `clausal/tools/visualize.py`. Either
shape works. The unified shape is cleaner.

**Q5. What's the contract for tests that currently import private
helpers (e.g. `_body_multi_star_unify`, `_extract_first_arg_key`)?**
Option A: move those tests to import from the new precise location
(`runtime.list_unify._body_multi_star_unify`). Option B: keep a
`compiler.__getattr__` delegation forever for test-only access.
Option C: make the helpers part of the public API.

Lean toward A: the tests are testing implementation details that
happen to work today because the private helpers happen to be
importable. Either the behaviour is a contract (move test to public
API), or it's implementation detail (the test shouldn't exist as
written).

**Q6. How do we handle the `-shallow` directive?**
It's currently a per-predicate flag that selects strategy. The
`Strategy` proposal makes this a per-call argument to `compile_predicate`.
The directive processor would pass the appropriate `Strategy`
instance. Clean.

**Q7. Does the compile_predicate_v2 (pipeline split) work belong in
this picture?**
`compiler_v2.py` does module-level compilation: source → Python AST.
It's orthogonal to predicate compilation. Probably stays separate;
the target architecture here is for the predicate compiler
specifically.

---

## 16. What we get

If we execute this architecture well, the pay-off is:

- **Any new contributor reads the README and pipeline phase-by-phase,
  then opens individual phase files. They are 100-200 lines each
  with clear input/output types. Understanding one phase doesn't
  require understanding the others.** Today, understanding
  `compile_goal` requires understanding `_compile_catch`,
  `_compile_reified_ite`, and half a dozen other things simultaneously.

- **Adding a new optimisation is a new file in `optimisations/` plus
  a test.** Today it's a new branch threaded through existing code.

- **Adding a new strategy (e.g. a prolog-compatible backend that
  targets WAM bytecode) is a new `Strategy` implementation.** Today
  it would be a third parallel implementation to maintain.

- **Source-location fidelity makes debugging viable.** Today a
  traceback into generated code is a dead end.

- **Thread-safety is trivial.** Today it works because the GIL
  mostly hides the issues and `threading.local` helps.

- **The deferred-refactor list from `COMPILER_MODULE_SPLIT.md`
  collapses.** Most items there are symptoms of the issues this
  architecture fixes. #2 (context object) is built in. #3
  (long-function breakup) happens naturally when phases are files.
  #8 (retire `_monolith`) is replaced by structural separation.
  Only #4 (naming) and #5 (builtin-call name table) survive as
  separate items.

---

## 17. What this proposal does NOT answer

- **The migration path.** That's step 4. Probably a parallel
  implementation behind a feature flag, migrate tests one by one,
  flip the flag when green, delete the old code. Or incremental:
  phases migrate one at a time, each phase PR stands alone.
- **Benchmarks.** The new structure shouldn't be slower than the
  old. Likely the same or faster (fewer function-call layers, no
  thread-local lookups, specialised emission paths). But this needs
  to be measured.
- **Backward compatibility guarantees.** `solve.py`, `compiler_v2.py`,
  and other internal callers can be updated as part of the migration.
  External users of `from clausal.logic.compiler import X` where X
  is a private helper need a deprecation path.

---

## 18. Concluding thoughts

The proposal commits to structure. It says:

- The compiler has a shape (pipeline).
- Each phase has a contract (types + invariants).
- Variation is explicit (strategy is a protocol).
- State is owned (one context object, no thread-locals).
- Generated code is debuggable (source locations preserved).
- Optimisations are composable (independent passes).
- The runtime/compile boundary is enforced (package separation).

It does not say "do X before Y" or "this function should be renamed
to Z." Those decisions belong to the migration plan.

If this document survives your review — the principles hold, the
phase decomposition makes sense, the `Strategy` abstraction captures
the real variation — then the migration plan can follow. If parts
feel wrong, we argue about them here before any code moves.
