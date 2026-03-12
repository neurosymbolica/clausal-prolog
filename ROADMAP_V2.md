# Clausal V2 — Roadmap

## Status

V1 (Steps 1–9 + keyword work items WK-1 through WK-6) is complete. 1174 tests passing.
The system compiles `.clausal` files to Python generator functions via an import hook,
with full backtracking search, unification, builtins, and a query API.

This roadmap covers the next phase of work: performance, caching, advanced resolution
strategies, and constraint logic programming.

---

## V2 step overview

```
V2-1   First-argument indexing
V2-2   Groundness-keyed dispatch (multi-plan compilation)
V2-3   __pycache__ bytecode caching
V2-4   Tabling (SLG resolution)
V2-5   Full dif via attribute variables
V2-6   CLP(FD) integration (using :=)
V2-7   Well-founded semantics
V2-8   Standard library expansion
```

Deferred beyond V2: type-directed dispatch (see note at end).

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

**Depends on:** V2-1 (indexing helps table lookup performance)

**Goal:** memoised subgoal calls that prevent infinite loops on recursive predicates and
guarantee termination for programs with finite models. Implements SLG resolution with
answer subsumption.

**Design:**

- A predicate is declared tabled via a decorator or pragma (syntax TBD — possibly
  `# tabled` comment annotation in `.clausal` files, or a `tabled(pred/arity)` directive).
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

## V2-5 — Full dif via attribute variables

**Depends on:** V1 complete (independent, but V2-4 is a nice-to-have first)

**Goal:** proper `dif/2` (disequality constraint) propagation using the attribute variable
hooks already present in `clausal.logic.variables`. Currently `is not` uses a deferred
check at solution time; this step makes it a true constraint that propagates eagerly.

**Design:**

- `clausal.logic.variables` already has attr-var hook slots (`attr_unify_hook`). These
  fire when a variable with attributes is unified.
- `dif(X, Y)` attaches a disequality constraint to the relevant variables. When either
  variable is unified, the hook checks whether the constraint is violated, satisfied
  (can be removed), or still pending (re-attach to remaining variables).
- A constraint store (per-trail or per-search) tracks active dif constraints.
- At solution time, all remaining dif constraints are verified (residual check).

**Files to change:**
- `clausal/logic/variables/` — implement `attr_unify_hook` dispatch
- `clausal/logic/builtins.py` — replace deferred-check `is not` with proper dif
- New: `clausal/logic/constraints.py` — constraint store abstraction

**Tests:**
- `X is not Y, X is 1, Y is 1` → fails (constraint violation on unification)
- `X is not Y, X is 1, Y is 2` → succeeds
- `X is not 1` as a constraint: `X is 2` succeeds, `X is 1` fails
- Residual constraints: unresolved dif reported at solution time
- Interaction with backtracking: constraints are undone on trail undo

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

Requires a proper module system with import/export signatures. The current single-file
import hook doesn't support this. Deferred until a module system is designed.

### Wiring dicts

The `{TargetKey: ProtocolKey}` mechanism from the keyword predicates spec is deferred
indefinitely. Python lambdas cover the same use cases with less cognitive overhead.
