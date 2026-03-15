# Clausal V2 — Roadmap

## Status

V1 (Steps 1–9 + keyword work items WK-1 through WK-6) is complete.
V2-D through V2-13 are complete. 2486 tests passing.
The system compiles `.clausal` files to Python generator functions via an import hook,
with full backtracking search, unification, builtins, and a query API.

**Naming convention**: All predicates, atoms, and builtins use **TitleCase** (e.g.
`Color`, `Adjacent`, `ForAll`, `MapList`). Logic variables use trailing underscore
(`X_`, `Foo_`) or ALL-CAPS (`X`, `COLORING`). Bare `_` is the anonymous variable.

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
V2-6   CLP(FD) integration (using :=)                                 ✓
V2-7   Well-founded semantics                                          ✓
V2-8   If-then-else (reification of IfExpr)                              ✓
V2-9   Pythonic lambdas (goal closures)                                  ✓
V2-10  Meta-predicates (Call/N, FindAll, BagOf, SetOf, ForAll)           ✓
V2-11  List processing builtins (MapList, Filter, Exclude, FoldLeft)     ✓
V2-12  Arithmetic builtins                                        ✓
V2-13  Term inspection builtins                                         ✓
V2-14  Control / exception handling (Catch/3, Throw/1)                  ✓
V2-15  I/O builtins                                                     ✓
V2-16  Python interop                                                  ✓
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
| `-meta_predicate(template)` | Declares argument roles for higher-order predicates (e.g., `-meta_predicate(MapList(2, +, -))` — first arg is a goal with 2 extra args). Enables the compiler to correctly handle module-qualified calls. |

**Argument syntax notes:**

- `Pred/Arity` is written as Python division: `Path / 2` or `Path/2`. The parser sees
  `Div(Name("Path"), Constant(2))` — easy to destructure.
- Multiple predicates can be listed: `-dynamic(Path/2, Edge/2)`.
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
- `-dynamic(Foo/2)` allows `Assertz(Foo(1, 2))` at runtime without error
- Asserting into a non-dynamic predicate raises an error
- `-discontiguous(Foo/1)` suppresses non-contiguous clause warning
- `-table(Fib/2)` sets the tabled flag (full tabling tested in V2-4)
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
- Same predicate called in different modes (e.g. `Append([], B, C)` vs
  `Append(A, B, [1,2,3])`) hits different plans
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
  -table(Fib/2, Path/3)
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
- `Path/2` over cyclic graph terminates (currently would loop)
- `Fib/2` with tabling computes in O(n) instead of O(2^n)
- Same-generation problem (classic tabling benchmark)
- Subsumption: more general answers subsume more specific ones
- `AbolishTable/1` clears a table; subsequent calls recompute

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
| `AllDifferent(Xs)` | global constraint |
| `Label(Xs)` | enumerate solutions |

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
- `Win/1` game: `Win(X) <- Move(X, Y) and not Win(Y)` — classic WFS example
- Stable model programs with unique well-founded model
- Programs with `undefined` residuals

---

## V2-8 — If-then-else (reification of IfExpr) ✓

**Status: DONE.** 99 tests in `tests/test_reified_ite.py`. Both simple and trampoline modes.
Supports reified (Unify/Dif/CLP(FD) tests with three-way branch) and general (sub-generator
with committed choice) if-then-else, plus `once/1`.

**Depends on:** V2-7 (complete system)

**Goal:** compile Python's ternary `if` expression as committed-choice control flow in goal
position. This is a compiler feature, not a builtin — it extends `compile_goal` /
`compile_goal_trampoline` to handle `IfExpr` nodes.

**Syntax:** Python's ternary if-expression in goal position:

```
action1(X_) if condition(X_) else action2(X_)
```

**Semantics** (Prolog's `->` / `;`): try `Cond` — if it succeeds (first solution only,
committed choice), execute `Then`; if it fails, execute `Else`. No backtracking into `Cond`
after committing.

**Parsing:** Already handled — `TermTransformer.visit_IfExp` produces `IfExpr(test, body, orelse)`.
Currently not compiled.

**Compilation** (trampoline mode — the only production path):

Cond is compiled in simple mode as a sub-generator (same pattern as NAF). Then/Else are
compiled in trampoline mode with normal `k_stmts`.

```python
# (Then if Cond else Else) compiles to:
_if_m = trail.mark()
_if_found = False
def _if_cond():
    k = None  # needed for simple-mode predicate calls in sub-generator
    <compiled Cond with k_stmts = [yield None]>
    return; yield
for _ in _if_cond():
    _if_found = True
    break
if _if_found:
    <compiled Then with k_stmts>
else:
    trail.undo(_if_m)
    <compiled Else with k_stmts>
```

**Key details:**

- **`k = None` in sub-generators:** When `compile_goal` (simple mode) is used inside a nested
  generator function (for NAF, find_all, if-then-else cond), any predicate call in the goal
  generates `_tramp_call(fname._get_dispatch(), args, trail)`. Since `_get_dispatch()` returns
  trampoline-mode functions, simple-mode sub-generators cannot call them directly — they need
  the `_tramp_call` wrapper that drives the trampoline and yields None per solution. This
  applies to ALL sub-generator patterns (NAF, find_all, if-then-else cond, bag_of, set_of).

- **`_tramp_call` helper:** A runtime function injected into `base_globals` that takes a
  trampoline dispatch fn + args and drives it with a temporary `StepGenerator`, yielding None
  per solution. `_dispatch_call_iter` should generate `_tramp_call(dispatch, args, trail)`
  instead of `dispatch(args, trail, k)`.

- **`orelse=True` means "succeed":** When `else_` is `True` (no explicit else branch), the
  else path should emit `k_stmts` directly (not be treated as a no-op). `True` = succeed =
  pass through to continuation.

- **Test pattern:** Bindings are undone after generator exhaustion. Tests must capture
  `deref()` values DURING iteration, not after `list(fn(...))`.

**Also support:** `Then if Cond` (no else) — equivalent to `IfExpr(test=Cond, body=Then, orelse=None)`.
When `orelse is None`, if Cond fails the whole thing fails silently (no else branch at all).

**Files:**
- `clausal/logic/compiler.py` — `_compile_if_then_else` (simple), `_compile_if_then_else_trampoline`
- `tests/test_if_then_else.py` (~15 tests): committed choice, binding preservation/undo,
  nested if-then-else, if-without-else, trampoline mode

---

## V2-9 — Pythonic lambdas (goal closures) ✓

**Status: DONE.** See `V2_9_LAMBDAS.md` for full design. Tests in `tests/test_lambdas.py`.

**Depends on:** V2-8 (if-then-else demonstrates sub-generator compilation)

**Goal:** first-class goal closures using Python lambda syntax, enabling higher-order
programming. Lambdas are the mechanism for adapting predicates in meta-predicates.
Needed before call/N and higher-order predicates can be useful.

**Syntax:** `Z_ >> lambda X_, Y_: Y_ := X_ + Z_`

- `>>` (RShift) specifies closure variables on the left
- `lambda X_, Y_: <goal_body>` specifies parameters and a goal body
- Without closure vars: `lambda X_: X_ > 0` (bare lambda, no `>>`)

**Canonical form:** New `GoalLambda` term node in `clausal/terms.py`:

```python
@dataclass
class GoalLambda:
    params: tuple          # ('x_', 'y_') — string parameter names
    param_vars: tuple      # (Var, Var) — Var objects for each param
    body: Any              # goal term tree
    closure_vars: tuple = ()  # Var references from enclosing scope
```

**`_make_goal_lambda` runtime helper:** Since TermTransformer generates AST code but Var
objects only exist at runtime, use a Python lambda as a body builder:

```python
def _make_goal_lambda(param_names, closure_vars, body_builder):
    param_vars = tuple(Var() for _ in param_names)
    body = body_builder(*param_vars)
    return GoalLambda(params=param_names, param_vars=param_vars, body=body, closure_vars=closure_vars)
```

**Parsing:** `TermTransformer._visit_goal_lambda` handles both `RShift(vars, Lambda(...))` and
bare `Lambda(...)`. Key: use `name_remap` dict to map original param names to unique internal
names (`_lp{counter}_{i}`) to avoid scope contamination between nested lambdas and enclosing
scope variables.

**Compilation:** When `GoalLambda` appears in a goal argument position (inside a Call to
map_list, find_all, etc.), `_compile_goal_lambda` compiles it to a local `FunctionDef`
following the trampoline dispatch protocol:

```python
# Z_ >> lambda X_, Y_: Y_ := X_ + Z_
# compiles to:
def _lambda_N(this_generator, parent, _arg_x, _arg_y, trail):
    # Z_ captured from enclosing scope (same var_context name)
    <compiled goal body>
    yield (parent, DONE)
_lambda_N  # expression value = reference to this function
```

**Files:**
- `clausal/terms.py` — `GoalLambda`, `_make_goal_lambda`
- `clausal/templating/term_rewriting.py` — `_visit_goal_lambda`, `name_remap`
- `clausal/logic/compiler.py` — `_compile_goal_lambda` in `term_to_ast_expr`
- `clausal/import_hook.py` — add `GoalLambda`, `_make_goal_lambda` to predicate builtins
- `tests/test_lambdas.py` (~20 tests): construction, parsing, closure capture, compilation

---

## V2-10 — Meta-predicates (Call/N, FindAll, BagOf, SetOf, ForAll) ✓

**Status: DONE.** 23 tests in `tests/test_meta.py`. FindAll/3, BagOf/3, SetOf/3, ForAll/2
as compiler special forms. Call/1..8 and CallGoal/4..8 builtins.

**Depends on:** V2-9 (lambdas), V2-8 (if-then-else demonstrates sub-generator pattern)

**Goal:** compiler special forms for all-solutions predicates and dynamic predicate dispatch.
These are NOT builtins — they are compiled inline by the compiler, like NAF.

### call/N — Dynamic predicate dispatch

`call(Goal)` through `call(Goal, Arg1, ..., Arg7)` — compiler special forms.

**Runtime helper** `_call_goal(goal, extra_args, trail, module_globals)`:
- Deref goal
- If callable function (compiled lambda): call directly with extra_args via trampoline
- If `PredicateMeta` class: dispatch with extra_args
- If `BuiltinPredicate`: dispatch directly
- Yields solutions

**New file:** `clausal/logic/meta.py` — `_call_goal` runtime helper, injected into `base_globals`.

### find_all/3 — All-solutions collection

Compiler special form in `_SPECIAL_FORMS_SIMPLE` / `_SPECIAL_FORMS_TRAMPOLINE`.

```python
# find_all(Template, Goal, Bag) compiles to:
_fa_results = []
_fa_m = trail.mark()
def _fa_gen():
    k = None  # for simple-mode pred calls
    <compiled Goal with k_stmts = [yield None]>
    return; yield
for _ in _fa_gen():
    _fa_results.append(_deref_walk(template))
trail.undo(_fa_m)
# Now unify Bag with results as part of normal continuation:
_fa_om = trail.mark()
if unify(bag, _fa_results, trail):
    <k_stmts>
trail.undo(_fa_om)
```

**Key:** `_deref_walk` (from `solve.py`) deep-copies the template with current bindings.
The inner goal's bindings are undone before the bag unification, but the bag unification
itself is part of the normal continuation (not isolated).

### bag_of/3, set_of/3

Same pattern as find_all but:
- `bag_of`: fails if no solutions (wrap unify in `if _results:`)
- `set_of`: bag_of + `_set_of_dedup(results)` (sort + dedup)

### for_all/2

Rewrite `for_all(Cond, Action)` → `Not(And(Cond, Not(Action)))` and delegate to existing
NAF compilation. No new codegen.

**Files:**
- `clausal/logic/compiler.py` — special forms dispatch, `_compile_find_all_simple/trampoline`,
  `_compile_call_n_simple/trampoline`, etc.
- `clausal/logic/meta.py` (new) — `_call_goal` runtime helper
- `clausal/logic/solve.py` — export `_deref_walk`
- `tests/test_find_all.py` (~20 tests)
- `tests/test_call_n.py` (~15 tests)

---

## V2-11 — List processing builtins ✓

**Status: DONE.** 28 tests in `tests/test_higher_order.py`. All TitleCase names:
`MapList/2`, `MapList/3`, `Filter/3`, `Exclude/3`, `FoldLeft/4`.

**Depends on:** V2-10 (meta-predicates needed for higher-order list ops)

**Goal:** higher-order list predicates that use `_call_goal` internally.

**Already implemented (committed):** `In/2`, `InCheck/2`, `Append/3`, `Length/2`,
`Last/2`, `Reverse/2`, `GetItem/3`, `Flatten/2`, `MergeSort/2`, `Sort/2`,
`Permutation/2`, `Select/3`, `Subtract/3`, `Intersection/3`, `Union/3`, `ToSet/2`,
`Unzip/3`, `PairKeys/2`, `PairValues/2`.

**New predicates:**

| Predicate | Description |
|-----------|-------------|
| `MapList/2` | `MapList(Goal, List)` — Goal succeeds for each element |
| `MapList/3` | `MapList(Goal, Xs, Ys)` — Goal maps each X to Y |
| `Filter/3` | Keep elements where Goal succeeds |
| `Exclude/3` | Keep elements where Goal fails |
| `FoldLeft/4` | `FoldLeft(Goal, List, V0, V)` — left fold |

These are **Python builtins** that call `_call_goal` internally with proper trail mark/undo.

**Files:**
- `clausal/logic/builtins.py` — higher-order builtins
- `tests/test_higher_order.py` (28 tests)

---

## V2-12 — Arithmetic builtins ✓

**Status: DONE.** All arithmetic builtins implemented. 26 tests in `TestArithmetic` class
in `tests/test_builtins.py`.

**Builtins:** `Between/3`, `Succ/2`, `Plus/3`, `Abs/2`, `Max/3`, `Min/3`, `SumList/2`,
`MaxList/2`, `MinList/2`, `Sign/2`, `Gcd/3`, `DivMod/4`.

**Files:**
- `clausal/logic/builtins.py`
- `tests/test_builtins.py` — `TestArithmetic` class

---

## V2-13 — Term inspection builtins

**Depends on:** nothing beyond V2-7

**Goal:** predicates for examining and manipulating term structure at runtime.

**Already implemented (committed):** `Functor/3`, `Arg/3`, `Unpack/2`.

**New predicates:**

| Predicate | Description |
|-----------|-------------|
| `CopyTerm/2` | Deep copy with fresh Vars |
| `TermVariables/2` | Collect all unbound Vars in term |
| `NumberVars/3` | Bind unbound Vars to `$VAR(N)` atoms |

**Files:**
- `clausal/logic/builtins.py`
- `tests/test_term_inspection.py` (~20 tests)

---

## V2-14 — Control / exception handling

**Depends on:** V2-8 (if-then-else), V2-10 (meta-predicates for find_all interaction)

**Goal:** Prolog-style exception handling integrated with backtracking and the trail.

**Design:**

```python
class LogicException(Exception):
    """Wraps a logic term thrown by throw/1."""
    def __init__(self, term): self.term = term
```

- `Throw/1` — builtin that raises `LogicException(deref_walk(term))`
- `Catch/3` — **compiler special form** (Goal and Recovery are goals, Pattern is a
  term for unification with the thrown value)

**Compilation pattern:**

```python
# Catch(Goal, Catcher, Recovery) compiles to:
_m_catch = trail.mark()
try:
    <compiled Goal with k_stmts>
except LogicException as _e:
    trail.undo(_m_catch)
    _m_match = trail.mark()
    if unify(<catcher_expr>, _e.term, trail):
        <compiled Recovery with k_stmts>
    trail.undo(_m_match)
```

**Key:** When an exception is caught, trail bindings from the failed Goal are undone before
Recovery runs. Python exceptions from builtins can also be caught by wrapping them.

**Files:**
- `clausal/logic/compiler.py` — `_compile_catch_simple`, `_compile_catch_trampoline`
- `clausal/logic/builtins.py` — `Throw/1`, `LogicException`
- `tests/test_exceptions.py` (~15 tests)

---

## V2-15 — I/O builtins ✓

**Status: DONE.** 43 tests in `tests/test_io.py`. Var `__str__`/`__format__` in C extension
auto-deref for f-string support. FStringThunk/FStringPart deferred evaluation for `.clausal` files.

**Depends on:** nothing beyond V2-7

**Goal:** basic formatted output predicates with natural f-string support. Python f-strings
containing logic variables auto-deref at search time — no manual `deref()` needed.

**F-string support:** `Var.__str__` and `Var.__format__` (in C extension) auto-deref bound
values. Unbound vars format as `_N`. Format specs work: `f"{X_:.2f}"`. In `.clausal` files,
f-strings are deferred to search time via `FStringThunk`/`FStringPart` term nodes — the
TermTransformer's `visit_JoinedStr` constructs structured parts, and the compiler
reconstructs `JoinedStr` AST with proper local variable references.

| Predicate | Description |
|-----------|-------------|
| `Write/1` | Print dereffed term to stdout (no newline) |
| `Writeln/1` | Print term + newline |
| `PrintTerm/1` | Print structured term_str representation + newline |
| `Nl/0` | Print a newline |
| `Tab/1` | Print N spaces |
| `WriteToString/2` | Unify result with string representation of term |
| `TermToString/2` | Unify result with structured term_str representation |

**Files:**
- `clausal/logic/variables/_variables.c` — `Var_str`, `Var_format`, `Var_methods`
- `clausal/terms.py` — `FStringThunk`, `FStringPart`
- `clausal/templating/term_rewriting.py` — `visit_JoinedStr`, `_LogicVarRemapper`
- `clausal/logic/compiler.py` — `term_to_ast_expr` handles `FStringThunk`
- `clausal/import_hook.py` — `FStringThunk`/`FStringPart` in predicate builtins
- `clausal/logic/builtins.py` — I/O builtins
- `tests/test_io.py` (43 tests)

---

## V2-16 — Python interop ✓

**Depends on:** V2-9 (lambdas provide the escape hatch pattern)

**Goal:** call arbitrary Python code from logic predicates via the `++()` escape.

### Design

The `++()` operator (double unary plus) marks a Python expression inside a `.clausal`
clause body. The expression is wrapped in a lambda at AST transformation time, with
logic variable names as parameters. At search time, the compiler emits a call to the
lambda with `deref()`'d values.

**As a value** (predicate argument): `R_ is ++len(L_)` — evaluates the Python expression
and unifies the result with the LHS.

**As a goal** (clause body): `++print(X_)` — evaluates the Python expression for side
effects and succeeds once.

### Implementation

- **`PyThunk`** class in `clausal/terms.py` — stores `(fn, var_objects)` pair where `fn` is
  a lambda and `var_objects` is a tuple of `Var` instances in parameter order.
- **`TermTransformer.visit_UnaryOp`** in `clausal/templating/term_rewriting.py` — detects
  `UAdd(UAdd(expr))` with adjacent columns, collects logic var `Name` nodes via
  `_VarCollector`, wraps expression in a lambda, returns `PyThunk(lambda, [vars])` AST.
- **`term_to_ast_expr`** in `clausal/logic/compiler.py` — emits `_pyt_<id>(deref(v0), ...)`.
- **`_collect_py_thunks`** — walks clause bodies, returns `{_pyt_<id>: thunk.fn}` dict for
  globals injection.
- **`compile_goal` / `compile_goal_trampoline`** — handles PyThunk as a goal (evaluate +
  continue).

### Key files

- `clausal/terms.py` — `PyThunk` class
- `clausal/templating/term_rewriting.py` — `++()` detection in `visit_UnaryOp`
- `clausal/logic/compiler.py` — PyThunk handling in `term_to_ast_expr`, `compile_goal`, `_collect_py_thunks`
- `tests/test_python_interop.py` (10 tests)

---

## Dependency graph

```
V2-8  (if-then-else)  ──→ V2-9  (lambdas) ──→ V2-10 (meta-predicates) ──→ V2-11 (list HOF)
                                                                        ──→ V2-14 (exceptions)
V2-12 (arithmetic)     — independent
V2-13 (term inspection) — independent
V2-15 (I/O)            — independent
V2-16 (Python interop) — depends on V2-9
```

---

## Implementation notes from V2-8 through V2-11

All resolved:

1. **Sub-generator `k` scoping:** Resolved via `_tramp_call` runtime helper that bridges
   simple-mode sub-generators to trampoline-mode dispatch functions.

2. **`_dispatch_call_iter`:** Generates `_tramp_call(fname._get_dispatch(), (args...), trail)`
   which uses `StepGenerator` internally, yielding `None` per solution.

3. **Test pattern for bindings:** Tests capture `deref()` values DURING iteration.

4. **`IfExpr` orelse=True/None:** Both handled correctly in `_compile_general_ite` and
   `_compile_reified_ite`.

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
