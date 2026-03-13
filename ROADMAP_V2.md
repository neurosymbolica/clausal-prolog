# Clausal V2 — Roadmap

## Status

V1 (Steps 1–9 + keyword work items WK-1 through WK-6) is complete.
V2-D through V2-5 are complete. 1943 tests passing.
The system compiles `.clausal` files to Python generator functions via an import hook,
with full backtracking search, unification, builtins, and a query API.

**Directives** (`-name(...)` syntax) are supported at module level. The `-module(name, [exports])`
directive is implemented. The directive infrastructure in `EmbedTransformer` is extensible to
support additional directives (dynamic, tabling, etc.) — see V2-D below.

This roadmap covers the next phase of work: directives, performance, caching, advanced
resolution strategies, and constraint logic programming.

---

## V2 step overview

```
V2-D   Directives (-dynamic, -table, -discontiguous, -meta_predicate)   ✓
V2-1   First-argument indexing                                          ✓
V2-2   Groundness-keyed dispatch (multi-plan compilation)               ✓
V2-3   __pycache__ bytecode caching                                     ✓
V2-4   Tabling (SLG resolution)                                         ✓
V2-5   Full dif via attribute variables                                 ✓
V2-6   CLP(FD) integration (using :=)
V2-7   Well-founded semantics
V2-8   Standard library expansion
```

Deferred beyond V2: type-directed dispatch (see note at end).

---

## V2-D — Directives

**Depends on:** nothing (V1 complete)

**Goal:** extend the `-directive(...)` syntax (already used for `-module(name, [exports])`) to
support compile-time declarations that control predicate behaviour. Directives are the
mechanism by which `.clausal` files declare metadata about predicates — analogous to Prolog's
`:-` directives, but using the `-name(...)` syntax native to clausal.

**Syntax:** a directive is a module-level statement beginning with `-` immediately followed by
a call expression (no space between `-` and the name). The parser already recognises this
pattern in `EmbedTransformer.visit_Expr` and dispatches to `_handle_directive`. Currently only
`-module(...)` is handled; this step adds the remaining directives.

**Directives to implement:**

| Directive | Meaning |
|---|---|
| `-module(Name, [Exports])` | Module declaration with exported predicate signatures. **Already implemented.** |
| `-dynamic(pred/arity, ...)` | Marks predicates as dynamic — may be modified at runtime via `assertz`/`retract`. The compiler skips locking checks and enables lazy recompile. Without this directive, runtime assertion into a statically-defined predicate is an error. |
| `-table(pred/arity, ...)` | Declares predicates as tabled (memoised). The compiler wraps dispatch in the SLG tabling machinery (V2-4). |
| `-discontiguous(pred/arity, ...)` | Allows clauses for a predicate to appear non-contiguously in the file. Without this, the import hook may warn or error when clauses for the same predicate are separated by other definitions. |
| `-meta_predicate(template)` | Declares argument roles for higher-order predicates (e.g., `-meta_predicate(maplist(2, +, -))` — first arg is a goal with 2 extra args). Enables the compiler to correctly handle module-qualified calls. |

**Argument syntax notes:**

- `pred/arity` is written as Python division: `path / 2` or `path/2`. The parser sees
  `Div(Name("path"), Constant(2))` — easy to destructure.
- Multiple predicates can be listed: `-dynamic(path/2, edge/2)`.
- `-table` is the preferred spelling over `-tabled` (shorter, matches XSB/SWI convention).

**Design:**

- `_handle_directive` dispatches on `name` to per-directive handlers.
- Each handler validates arguments and records metadata on the `Module` / `Database`:
  - `-dynamic` → `db.mark_dynamic(functor, arity)` — sets a flag consulted by `assertz` and
    the locking checks.
  - `-table` → `db.mark_tabled(functor, arity)` — the compiler emits tabling wrappers (V2-4).
  - `-discontiguous` → `db.mark_discontiguous(functor, arity)` — suppresses ordering warnings.
  - `-meta_predicate` → stores mode template for higher-order call expansion (V2-8 or later).
- Directives produce no runtime code — they are compile-time only. `_handle_directive` returns
  `Pass()` for each directive after recording the metadata.

**Phasing:**

Not all directives need to land at once. Recommended order:

1. **`-dynamic`** — immediately useful; enables safe runtime assertion.
2. **`-discontiguous`** — low effort; quality-of-life.
3. **`-table`** — lands with V2-4 (tabling).
4. **`-meta_predicate`** — lands with higher-order stdlib predicates (V2-8).

**Files to change:**
- `clausal/templating/term_rewriting.py` — extend `_handle_directive` with per-directive handlers
- `clausal/logic/database.py` — `mark_dynamic()`, `mark_tabled()`, `mark_discontiguous()` methods
  and corresponding flag storage

**Tests:**
- `-dynamic(foo/2)` allows `assertz(foo(1, 2))` at runtime without error
- Asserting into a non-dynamic predicate raises an error
- `-discontiguous(foo/1)` suppresses non-contiguous clause warning
- `-table(fib/2)` sets the tabled flag (full tabling tested in V2-4)
- Unknown directive name produces a clear error
- Malformed directive args (e.g., missing arity) produce a clear error

---

## V2-1 — First-argument indexing

**Depends on:** nothing (V1 complete)

**Goal:** avoid trying every clause when the first argument is ground. Build a dispatch
index keyed on the first argument's type and value, so that ground-first-arg calls jump
directly to the relevant clause subset.

**Design:**

- At compile time, partition clauses into buckets by the first-argument head pattern:
  - Literal value (int, str, etc.) → bucket keyed on that value
  - Functor class (e.g. `cons`, `point`) → bucket keyed on that class
  - Variable → goes into the "default" bucket (tried for all calls)
- The dispatch function becomes a two-level lookup:
  1. `deref(arg0)` to get the ground value
  2. Hash lookup into the index; fall through to default bucket on miss
  3. Each bucket is a mini match-case over its clause subset
- `Database` stores the index alongside `_dispatch` via `set_index(f, a, index)` /
  `get_index(f, a)`.
- Lazy recompile rebuilds the index when clauses change.

**Files to change:**
- `clausal/logic/compiler.py` — new `_build_first_arg_index()`, modify `compile_predicate`
  and `compile_predicate_trampoline` to emit indexed dispatch
- `clausal/logic/database.py` — index storage slots

**Tests:**
- Predicates with many fact clauses: verify only matching clauses are tried
- Mixed variable/ground first args: default bucket includes variable-headed clauses
- Dynamic assert invalidates and rebuilds index
- Benchmark: large fact table (100+ clauses) with ground lookups

---

## V2-2 — Groundness-keyed dispatch (multi-plan compilation)

**Depends on:** V2-1

**Goal:** compile multiple match functions per predicate, each optimised for a different
pattern of ground/unbound arguments. At call time, inspect which arguments are ground and
select the best plan.

**Design:**

- Groundness is represented as a bit-vector: bit N = 1 if arg N is ground (not an
  unbound Var) at call time.
- The compiler generates plans for common groundness patterns observed in clause heads:
  - All-ground (fact lookup) → hash-based dispatch
  - First-arg-ground (extends V2-1) → first-arg indexed dispatch
  - All-unbound (enumeration) → linear scan
  - Mode-specific plans for predicates where certain argument positions are always
    input or always output across all clauses
- `_dispatch` stores a dict `{groundness_bitvec: compiled_fn}` plus a fallback.
- A lightweight selector function checks `isinstance(deref(argN), Var)` for each arg
  and dispatches to the right plan.

**Files to change:**
- `clausal/logic/compiler.py` — plan generation per groundness pattern
- `clausal/logic/database.py` — multi-plan dispatch storage

**Tests:**
- Same predicate called in different modes (e.g. `append([], B, C)` vs
  `append(A, B, [1,2,3])`) hits different plans
- Fallback plan handles unexpected groundness patterns

---

## V2-3 — `__pycache__` bytecode caching

**Depends on:** V1 complete (independent of V2-1/V2-2, but benefits from stable dispatch)

**Goal:** compiled predicate dispatch functions are cached as `.pyc` bytecode in
`__pycache__`, so re-importing an unchanged `.clausal` file skips recompilation entirely.

**Design:**

- The import hook already transforms `.clausal` source to a Python AST `Module`. Currently
  the compiled predicate functions are built separately and installed at runtime.
- Change: inject the predicate `FunctionDef` AST nodes directly into the module's
  `ast.Module.body` *before* calling `compile()`. This way they become part of the
  module's bytecode.
- Python's import machinery handles `.pyc` freshness checking (source mtime + size).
  On cache hit, the module loads from `.pyc` with predicate functions already defined.
- `$define_predicate` becomes a no-op registration (just populates the database dispatch
  slot from the already-compiled function in module globals) rather than a full recompile.
- Only statically-defined predicates benefit. Predicates added at runtime via
  `assertz`/`asserta` still use the WK-LAZY recompile path.

**Files to change:**
- `clausal/templating/term_rewriting.py` — inject predicate FunctionDefs into module AST
- `clausal/import_hook.py` (or wherever `_predicate_loader` lives) — use `compile()` +
  `marshal` for `.pyc` output, or rely on `importlib` default caching
- `clausal/logic/database.py` — `$define_predicate` fast path when function already exists

**Tests:**
- Import a `.clausal` file, verify `__pycache__` contains a `.pyc`
- Delete the `.pyc`, re-import, verify it's recreated
- Modify the `.clausal` source, verify `.pyc` is invalidated and recompiled
- Verify predicate functions work identically from cache vs fresh compile

---

## V2-4 — Tabling (SLG resolution)

**Depends on:** V2-D (directives), V2-1 (indexing helps table lookup performance)

**Goal:** memoised subgoal calls that prevent infinite loops on recursive predicates and
guarantee termination for programs with finite models. Implements SLG resolution with
answer subsumption.

**Design:**

- A predicate is declared tabled via the `-table` directive (V2-D):
  ```
  -table(fib/2, path/3)
  ```
- The table stores `{subgoal_key: [answers]}` where the subgoal key is the call pattern
  after deref.
- On a tabled call:
  1. Check if the subgoal is already in the table.
  2. If complete: iterate stored answers (no recomputation).
  3. If incomplete (active): suspend the current computation, register as a consumer.
  4. When the producing computation finds a new answer, resume all suspended consumers.
- Completion detection: a subgoal is complete when all its consumers have been resumed
  with all its answers and no new answers were produced.
- The trampoline architecture (`clausal.trampoline`) provides the right abstraction for
  suspend/resume — tabled calls yield a `Suspend` step type alongside the existing `Step`.

**New files:**
- `clausal/logic/tabling.py` — table store, suspension mechanism, completion detection

**Files to change:**
- `clausal/logic/compiler.py` — emit tabling wrapper for tabled predicates
- `clausal/logic/solve.py` — trampoline loop handles `Suspend` steps

**Tests:**
- `path/2` over cyclic graph terminates (currently would loop)
- `fib/2` with tabling computes in O(n) instead of O(2^n)
- Same-generation problem (classic tabling benchmark)
- Subsumption: more general answers subsume more specific ones
- `abolish_table/1` clears a table; subsequent calls recompute

---

## V2-5 — Full dif via attribute variables ✓

**Status: DONE.** Implemented in `clausal/logic/constraints.py`. 42 tests in `tests/test_dif.py`.
See `docs/constraints.md` for full documentation.

**Summary:**

- All `Var()` are now `AttVar` (attributed variables) from birth — `Var = AttVar` alias in
  `clausal/logic/variables/__init__.py`. Zero overhead when no constraints are attached.
- `dif(x, y, trail)` implements the disequality constraint: sandbox-unify with occurs check,
  attach `(x, y)` constraint pairs to all free variables, re-evaluate via `_dif_hook` when
  any constrained variable is bound.
- `is not` now has `dif/2` semantics (constraint), not `\=/2` (immediate check). The old
  immediate check is still available as `not (X_ is Y_)` (NAF of unification).
- `dif/2` registered as a builtin for explicit use from `.clausal` files.
- Compiler emits `if _dif(l, r, trail): k_stmts` — no mark/undo wrapper needed.
- `_structural_unify_oc` extends C `unify_with_occurs_check` to handle Compound, PredicateMeta,
  and list types that the C extension falls through to `==` on

---

## V2-6 — CLP(FD) integration

**Depends on:** V2-5 (attribute variables), V2-4 (tabling, nice-to-have)

**Goal:** finite-domain constraint logic programming. Integer variables can have domain
constraints; propagation narrows domains; labeling enumerates solutions.

**The `:=` operator** (arithmetic binding, already parsed as `Evaluate` nodes) serves as
the CLP(FD) constraint posting syntax:

```
N := X + Y       % constrains N to equal X + Y over finite domains
X := 1..10       % domain declaration: X ∈ {1, 2, ..., 10}
```

When all variables in a `:=` expression have finite domains, it becomes a constraint that
propagates. When some are ground, it evaluates eagerly (current behaviour). This gives
`:=` a dual role: ground arithmetic evaluation AND constraint posting, distinguished by
whether the arguments are ground or domain-constrained.

**Design:**

- Domain representation: sorted list of intervals `[(lo, hi), ...]` per variable,
  stored as attribute variable data.
- Propagators: each `:=` constraint registers a propagator that narrows domains when
  other variables' domains change.
- Arc consistency (AC-3 or similar) as the propagation algorithm.
- `label/1` (or `indomain/1`) enumerates values from a variable's domain, triggering
  further propagation.
- Reification: `#<==>`, `#==>`, `#\` for constraint reification (deferred to V3 if
  complex).

**Built-in constraints:**
| Syntax | Meaning |
|---|---|
| `X := Lo..Hi` | domain declaration |
| `X := Expr` | arithmetic constraint (+ - * // mod) |
| `X #< Y`, `X #> Y`, etc. | domain-aware comparison |
| `all_different(Xs)` | global constraint |
| `label(Xs)` | enumerate solutions |

**New files:**
- `clausal/logic/clpfd.py` — domain store, propagators, labeling

**Files to change:**
- `clausal/logic/compiler.py` — `:=` dispatches to CLP when args have domains
- `clausal/logic/builtins.py` — register CLP builtins

**Tests:**
- SEND + MORE = MONEY (classic CLP benchmark)
- N-queens via CLP (compare with NAF version)
- Sudoku solver
- Domain narrowing: `X := 1..10, X #> 5` → domain `{6..10}`
- Labeling produces all solutions in order
- Interaction with regular unification

---

## V2-7 — Well-founded semantics

**Depends on:** V2-4 (tabling is required)

**Goal:** three-valued semantics (true / false / undefined) for negation in recursive
predicates. Prevents unsound answers from programs with recursion through negation.

**Design:**

- Extends SLG resolution (V2-4) with a third truth value: `undefined`.
- When a negated subgoal is encountered that depends on an incomplete tabled call,
  the answer is `undefined` rather than `true` or `false`.
- After all tabling completes, the well-founded model is computed: unfounded sets
  (mutually dependent through negation with no positive support) are assigned `false`.
- The `solve` API can optionally return the truth value alongside bindings.

**Files to change:**
- `clausal/logic/tabling.py` — three-valued answer store, unfounded set detection
- `clausal/logic/solve.py` — surface truth values

**Tests:**
- `win/1` game: `win(X) <- move(X, Y) and not win(Y)` — classic WFS example
- Stable model programs with unique well-founded model
- Programs with `undefined` residuals

---

## V2-8 — Standard library expansion

**Depends on:** V2-1 through V2-6 as features become available

**Goal:** grow the standard library with predicates that exercise and depend on new V2
capabilities.

**Predicates to add:**

*List processing (pure, benefits from tabling):*
- `msort/2`, `sort/2` — merge sort, sort with dedup
- `flatten/2` — nested list flattening
- `nth0/3`, `nth1/3` — zero/one-indexed element access
- `select/3` — select element from list, return rest
- `permutation/2` — (already exists, verify tabling interaction)
- `maplist/2..5`, `foldl/4..6`, `include/3`, `exclude/3`

*Arithmetic (benefits from CLP(FD)):*
- `between/3` — (already exists, add CLP-aware version)
- `succ/2`, `plus/3` — successor and addition, reversible with CLP
- `sum_list/2`, `max_list/2`, `min_list/2`
- `abs/1`, `sign/1`, `gcd/2`

*Term inspection:*
- `functor/3`, `arg/3`, `=../2` — (partially exist, complete)
- `copy_term/2` — deep copy with fresh variables
- `numbervars/3` — number unbound variables for readable output
- `term_variables/2` — collect all variables in a term

*Control:*
- `findall/3`, `bagof/3`, `setof/3` — all-solutions predicates
- `aggregate_all/3` — aggregate with arbitrary collector
- `forall/2` — universal quantification
- `catch/3`, `throw/1` — exception handling

*I/O and interop:*
- `print_term/1`, `format/2` — formatted output
- `py_call/3` — call arbitrary Python from logic predicates

---

## Deferred beyond V2

### Type-directed dispatch

Using Python type annotations on predicate arguments to narrow dispatch at compile time
is a **no-go** for V2. Predicate heads are Python expressions, not annotated parameters —
there is no natural place for annotations in the syntax.

The right approach, if pursued later, is **type inference**: analyze clause heads and body
goals to infer which argument positions are always a certain type, then use that
information to specialise dispatch. This is substantially more complex and is deferred
to V3 or later. The groundness-keyed dispatch in V2-2 provides the foundation that
type inference would build on.

### DCG (Definite Clause Grammars)

Not part of clausal's core mission (Python-native logic programming), and the Python
ecosystem has mature parsing libraries. Deferred indefinitely.

### Cross-module keyword propagation

Requires cross-module predicate resolution. Since `.clausal` modules are imported via Python's
standard `import` statement, cross-module access works through normal Python attribute lookup.
The `-module(name, [exports])` directive (V2-D) declares what a module exports. Deferred until
there's a concrete need beyond what Python imports already provide.

### Wiring dicts

The `{TargetKey: ProtocolKey}` mechanism from the keyword predicates spec is deferred
indefinitely. Python lambdas cover the same use cases with less cognitive overhead.
