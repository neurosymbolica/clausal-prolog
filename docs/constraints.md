# Constraints

Clausal supports constraint logic programming through attributed variables. The C extension provides `AttVar` (attributed variable), `put_attr`/`get_attr`/`del_attr` (all trailed), `register_attr_hook`, and a wakeup queue in `do_unify_and_wake`. Constraint solvers register hooks that fire when a constrained variable is unified.

!!! note "Clausal vs Prolog syntax"

    Clausal and Prolog syntax may slightly differ — for example, variables are
    `ALLCAPS`, rules use `<-` instead of `:-`, and lists are Python-style. Keep
    this in mind when comparing with Prolog resources.

Two constraint solvers are built in:

- **Dif/2** — disequality constraint (`clausal.logic.constraints`)
- **CLP(ℤ)** — integer constraints (`clausal.logic.clpfd`)

---

## Dif/2 — Disequality constraint

`Dif(X, Y)` constrains X and Y to be different. Unlike a point-in-time check, the constraint survives and is re-evaluated whenever either variable gets bound.

### Syntax

In `.clausal` files, `is not` has dif semantics:

```clausal
safe_assign(X, Y) <- (
    X is not Y,
    X is 1,
    Y is 2
)
```

This succeeds because X and Y end up with different values (1 and 2), even though at the time of `is not` they are both unbound.

The builtin `Dif/2` can also be called explicitly:

```clausal
constrained(X, Y) <- (
    Dif(X, Y),
    X is 1,
    Y is 2
)
```

### Semantics

| Clausal syntax | Semantics | Prolog equivalent |
|---|---|---|
| `X is not Y` | Constraint: must end up different | `Dif(X, Y)` |
| `not (X is Y)` | Immediate: don't unify right now | `\=(X, Y)` |

The `is not` operator uses `dif/2` constraint semantics rather than immediate `\=`. The old immediate-check semantics are still available as `not (X is Y)` — negation-as-failure of unification — which already works via the existing `Not(Unify(...))` compilation path.

??? example "Examples"

    **Constraint succeeds — terms stay different:**
    ```clausal
# skip
    X is not Y, X is 1, Y is 2    # succeeds: 1 ≠ 2
    ```

    **Constraint fails — terms become equal:**
    ```clausal
# skip
    X is not Y, X is 1, Y is 1    # fails: dif violated when Y=1
    ```

    **Multiple constraints:**
    ```clausal
# skip
    X is not 1, X is not 2, X is 3    # succeeds: 3 ≠ 1 and 3 ≠ 2
    X is not 1, X is not 2, X is 1    # fails: dif(X, 1) violated
    ```

    **Immediate check (old semantics):**
    ```clausal
# skip
    not (X is Y)    # fails if X and Y are both unbound (they CAN unify)
    ```

    ---

??? abstract "Design details"

    ### All Vars are AttVars

    `clausal.logic.variables` aliases `Var = AttVar`. Every logic variable created with `Var()` is an attributed variable from birth. `AttVar` inherits from the C `Var` type via `tp_base`, so `is_var()`, `deref()`, and `unify()` work unchanged. The only overhead is 8 bytes per variable for a NULL attributes pointer (no dict is allocated until a constraint is actually attached).

    The original `Var` type is available as `PlainVar` if needed.

    ### Constraint algorithm

    When `dif(x, y, trail)` is called:

    1. Deref both arguments.
    2. Sandbox-unify with occurs check (`_structural_unify_oc`).
    3. **Unify fails** → structurally incompatible (e.g. `dif(1, 2)`) → return True immediately.
    4. **Unify succeeds, no trail growth** → terms already identical (e.g. `dif(X, X)`) → return False.
    5. **Unify succeeds with trail growth** → terms could become equal → undo sandbox, collect all free variables in both terms, attach `(x, y)` constraint pair to each via `put_attr`, return True.

    `_structural_unify_oc` extends the C extension's `unify_with_occurs_check` to handle `Compound`, `PredicateMeta` instances, and lists (which the C extension treats as opaque objects and compares with `==`).

    ### Attribute hook

    When a constrained variable is unified, the `_dif_hook` fires:

    1. For each `(x, y)` constraint pair on the variable:
       - Deref and sandbox-unify.
       - **Fails** → constraint satisfied, drop it.
       - **Succeeds, no trail growth** → terms now identical, constraint violated → return False (blocks unification).
       - **Succeeds with trail growth** → still pending → undo sandbox, re-attach to remaining free variables.
    2. If all constraints survive, return True.

    Constraint deduplication uses tuple identity (`is`) to avoid attaching the same pair to a variable twice during re-attachment.

    ### Backtracking

    All `put_attr` calls go through the trail, so constraint attachment is automatically undone on `trail.undo(mark)`. No explicit cleanup is needed.

    ### Compiler integration

    The `DoesNotUnify` goal node compiles to:

    ```python
    if _dif(X, Y, trail):
        k_stmts
    ```

    No mark/undo wrapper — `dif` handles its own sandboxing. `_dif` is injected into `base_globals` in both `compile_predicate` and `compile_predicate_trampoline`.

    ---

??? example "Python API"

    ```python
    from clausal.logic.variables import Var, Trail, unify, deref
    from clausal.logic.constraints import dif
    
    trail = Trail()
    x, y = Var(), Var()
    
    # Post constraint
    dif(x, y, trail)  # True — constraint posted
    
    # Bind to different values: succeeds
    unify(x, 1, trail)  # True
    unify(y, 2, trail)  # True — dif satisfied
    
    # Or bind to same value: fails
    trail2 = Trail()
    a, b = Var(), Var()
    dif(a, b, trail2)   # True
    unify(a, 1, trail2)  # True
    unify(b, 1, trail2)  # False — dif violated
    ```

    ---

??? info "Test coverage"

    Tests are in `tests/test_dif.py` (42 tests).

    - **`_collect_free_vars`**: scalars, Vars, bound vars, tuples, lists, Compounds, nested structures, deduplication
    - **Direct `dif`**: ground equal/different, same var, one var, both vars, compound terms
    - **Occurs check**: `dif(X, f(X))` → succeed (can never be equal)
    - **Constraint propagation**: same/different values, multiple constraints, compound args, transitive via shared var
    - **Backtracking**: constraint undone on trail undo, binding failure doesn't corrupt trail
    - **Compiled integration**: `is not` with later binding (succeed/fail), ground terms, same var, `not (X is Y)` still works, multiple constraints
    - **Builtin `Dif/2`**: callable from clausal code, with vars and ground terms
    - **Import hook**: `.clausal` file with `is not` using proper dif semantics

    ---

## CLP(ℤ) — Integer constraints

CLP(ℤ) is built into the language as the default way to reason about integers (per Markus Triska's recommendation). The comparison operators `==`, `!=`, `<`, `>`, `<=`, `>=` are CLP(ℤ) constraint operators.

The implementation lives in `clausal.logic.clpfd`.

### Operator semantics

| Operator | Meaning |
|---|---|
| `==` | CLP(ℤ) arithmetic equality |
| `!=` | CLP(ℤ) arithmetic disequality |
| `<` `>` `<=` `>=` | CLP(ℤ) comparison constraints |
| `is` | Unification (unchanged) |
| `is not` | `Dif/2` constraint (unchanged) |
| `:=` | Eager arithmetic eval + unify (unchanged) |

When both sides are ground (no unbound Vars), the operators fall back to direct Python comparison. When at least one side is an unbound Var, CLP(ℤ) constraints are posted.

The old structural-equality behaviour of `==` is available as the named builtin `Equivalent/2`.

??? abstract "Domain representation"

    Domains are sorted tuples of `(lo, hi)` inclusive integer intervals:

    ```python
    Domain = tuple[tuple[int, int], ...]  # e.g., ((1, 5), (8, 10))
    ```

    Most domains are contiguous `((lo, hi),)` — single-interval fast path is optimised throughout.

??? abstract "FDVar — per-variable state"

    Each constrained variable stores an `FDVar` as an attributed-variable attribute under the key `"fd"`:

    ```python
    class FDVar:
        __slots__ = ('domain', 'constraints')
        domain: Domain
        constraints: tuple[Constraint, ...]  # immutable for trail safety
    ```

    **Trail safety**: every domain narrowing or constraint addition creates a new `FDVar` and calls `put_attr(var, "fd", new_state, trail)`. The old state is automatically restored on `trail.undo()`. Never mutate in place.

??? abstract "Auto-domain"

    When a CLP(ℤ) operator encounters an unbound Var with no domain, it auto-creates a default domain of `(-2^63, 2^63)` — effectively unbounded for practical purposes, stored as a single interval.

??? abstract "Constraint types"

    **Binary / unary constraints** (posted by `==`, `!=`, `<`, `<=`, `>`, `>=`):

    | Constraint | Description |
    |---|---|
    | `EqConstraint(lhs, rhs)` | X == Y — narrow both domains to intersection |
    | `NeConstraint(lhs, rhs)` | X != Y — when one side is singleton, remove from other |
    | `LtConstraint(lhs, rhs)` | X < Y — upper-bound X by max(Y)-1, lower-bound Y by min(X)+1 |
    | `LeConstraint(lhs, rhs)` | X <= Y — upper-bound X by max(Y), lower-bound Y by min(X) |
    | `AllDiffConstraint(vars)` | all_different — when one var is ground, remove from all others |

    **Global constraints** (posted by `Sum/3`, `ScalarProduct/4`, `Element/3`, `Circuit/1`):

    | Constraint | Description |
    |---|---|
    | `SumConstraint(vars, total)` | Σ vars = total — bounds-consistency: narrows total to [min_sum, max_sum] and each var using slack |
    | `ScalarProductConstraint(coeffs, vars, total)` | Σ cᵢ·vᵢ = total — same as Sum but with signed coefficients; division direction flips for negative coefficients |
    | `ElementConstraint(index, lst, value)` | value = lst[index−1] — AC-3: narrows index to positions whose list element overlaps value's domain, narrows value to union of those elements' domains |
    | `CircuitConstraint(vars)` | Hamiltonian circuit — restricts domains to [1,n], removes self-loops, delegates to AllDiffConstraint, prunes premature sub-tours via forced-chain detection |

    Inequality operators (`#<`, `#>`, `#=<`, `#>=`, `#\=`) for `Sum` and `ScalarProduct` introduce an intermediate total variable, post the equality constraint on it, then chain the appropriate binary relational constraint.

??? abstract "Propagation (AC-3)"

    Constraints are propagated via an AC-3 fixpoint loop. When a propagator narrows a domain:

    1. Create new `FDVar` with narrowed domain + same constraints.
    2. `put_attr(var, "fd", new_state, trail)` — trailed.
    3. If singleton `{v}`: `unify(var, v, trail)` → fires FD hook + dif hooks.
    4. If empty: return False (wipeout → backtrack).
    5. Add var to propagation queue.

    The queue is drained to fixpoint — a variable is re-processed every time its domain shrinks, so cascading narrowing (e.g. X < Y < Z, fix Z → Y narrows → X narrows) converges without explicit re-scheduling.

??? abstract "FD attribute hook"

    `_fd_hook` fires when an FD-constrained variable is unified:

    - **Bound to integer**: check domain membership, propagate all constraints.
    - **Bound to another Var**: intersect domains, merge constraints, check singleton, propagate.
    - **Bound to non-integer/non-Var**: fail.

??? abstract "Expression domain arithmetic"

    CLP(ℤ) constraint functions walk arithmetic expression trees (`Add`, `Sub`, `Mult`, `Div`, `FloorDiv`, `Mod`, `Pow`, `Negate`) to compute domain bounds:

    ```
    [a,b] + [c,d] = [a+c, b+d]
    [a,b] - [c,d] = [a-d, b-c]
    [a,b] * [c,d] = [min(corners), max(corners)]
    -[a,b]        = [-b, -a]
    ```

    Ground arithmetic expressions (including `//` and `%`) are evaluated before comparison.

### Builtins

| Builtin | Arity | Description |
|---|---|---|
| `InDomain` | 3 | `InDomain(Var_or_list, Lo, Hi)` — post domain [Lo, Hi] |
| `Label` | 1 | `Label(Vars)` — enumerate values, first-fail strategy |
| `AllDifferent` | 1 | `AllDifferent(Vars)` — pairwise disequality constraint |
| `Equivalent` | 2 | `Equivalent(X, Y)` — structural equality (old `==` behavior) |
| `Sum` | 3 | `Sum(+Vars, +Op, +Value)` — bounds-consistency propagation for Σ Vars Op Value |
| `ScalarProduct` | 4 | `ScalarProduct(+Coeffs, +Vars, +Op, +Value)` — bounds-consistency for Σ Cᵢ·Vᵢ Op Value |
| `Element` | 3 | `Element(?Index, +List, ?Value)` — arc-consistency: Value = List[Index] (1-based) |
| `Circuit` | 1 | `Circuit(+Vars)` — Hamiltonian circuit with sub-tour elimination during propagation |

### Syntax examples

**Domain declaration and labeling:**
```clausal
solve(X) <- (
    InDomain(X, 1, 10),
    Label([X])
)
```

**Chained comparison (natural Python syntax):**
```clausal
bounded(X) <- (1 <= X, X <= 10, Label([X]))
```

Since `<=` is CLP(ℤ), `1 <= X` and `X <= 10` naturally constrain X's domain.

**N-Queens via AllDifferent:**
```clausal
queens(N, QS) <- (
    InDomain(QS, 1, N),
    AllDifferent(QS),
    Label(QS),
    check_diagonals(QS)
)
```

**SEND + MORE = MONEY:**
```clausal
sendmoney(S, E, N, D, M, O, R, Y) <- (
    InDomain([S, E, N, D, M, O, R, Y], 0, 9),
    AllDifferent([S, E, N, D, M, O, R, Y]),
    S != 0,
    M != 0,
    S * 1000 + E * 100 + N * 10 + D + (M * 1000 + O * 100 + R * 10 + E) == M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    Label([S, E, N, D, M, O, R, Y])
)
```

The `==` constraint is posted *before* `Label` so the solver propagates the equation across all eight domains before any labeling begins. See the gotcha below.

### Gotcha: generate-and-test vs constraint-and-label

A common mistake is to call `Label` first and then check the arithmetic — this is **generate-and-test** and is extremely slow:

```clausal
# SLOW -- generate-and-test: Label runs before the equation is known
sendmoney_slow(S, E, N, D, M, O, R, Y) <- (
    InDomain([S, E, N, D, M, O, R, Y], 0, 9),
    AllDifferent([S, E, N, D, M, O, R, Y]),
    S != 0,
    M != 0,
    Label([S, E, N, D, M, O, R, Y]),        # labels all 8 vars with no arithmetic constraint
    SEND := S * 1000 + E * 100 + N * 10 + D,
    MORE := M * 1000 + O * 100 + R * 10 + E,
    MONEY := M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    SEND + MORE == MONEY                     # checked after the fact
)
```

`:=` is eager arithmetic evaluation (`is/2`), not a constraint — it requires its arguments to already be ground. Putting `Label` before `:=` forces enumeration of all ~40,000 `AllDifferent` permutations before any pruning from the equation can happen.

The fix is to post the equation as a `==` constraint *before* `Label`:

```clausal
# FAST -- constraint-and-label: equation is propagated before any labeling
sendmoney_fast(S, E, N, D, M, O, R, Y) <- (
    InDomain([S, E, N, D, M, O, R, Y], 0, 9),
    AllDifferent([S, E, N, D, M, O, R, Y]),
    S != 0,
    M != 0,
    S * 1000 + E * 100 + N * 10 + D + (M * 1000 + O * 100 + R * 10 + E) == M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    Label([S, E, N, D, M, O, R, Y])         # labels with equation already constraining domains
)
```

`==` with unbound variables posts a CLP(ℤ) constraint. The equation is normalised to a `ScalarProductConstraint` and propagated via AC-3 before the first value is tried. This reduces the effective search space from ~40,000 to a handful of candidates, cutting solve time by ~70×.

**Rule of thumb:** use `==` for arithmetic — it posts constraints that propagate before labeling. Reserve `:=` for Python interop (e.g., string operations with `++`).

??? example "Python API"

    ```python
    from clausal.logic.variables import Var, Trail, deref, unify
    from clausal.logic.clpfd import in_domain, label, all_different, fd_eq, fd_ne, fd_lt

    trail = Trail()
    x, y = Var(), Var()

    # Post domains
    in_domain([x, y], 1, 10, trail)

    # Post constraint: X < Y
    fd_lt(x, y, trail)

    # Label (enumerate solutions)
    for _ in label([x, y], trail):
        print(deref(x), deref(y))
    ```

??? abstract "Interaction with dif/2 and CLP(ℝ)"

    CLP(ℤ), CLP(ℝ), and dif/2 use independent attribute keys (`"fd"`, `"real"`, and `"dif"`). All hooks fire independently when a variable is bound. A variable can have integer, real, and dif constraints simultaneously.

    **FD + Real coexistence:** a variable can carry both an FD domain and a real interval at the same time. The FD domain enforces integrality and domain holes; the real interval handles continuous narrowing. When FD propagation narrows the domain, the real interval is tightened to match. When computing bounds for real constraints, the tightest bounds from both attributes are used. See [CLP(ℝ)](clpr.md) for details on mixed-domain usage.

??? abstract "Compiler integration"

    `ArithEq`/`ArithNeq` and `Lt`/`LtE`/`Gt`/`GtE` goal nodes compile to:

    ```python
    if _fd_eq(l, r, trail):    # ==
        k_stmts
    if _fd_ne(l, r, trail):    # !=
        k_stmts
    if _fd_lt(l, r, trail):    # <
        k_stmts
    ```

    Both sides are compiled with `eval_arith=False` so arithmetic expression trees survive as structural terms for CLP(ℤ) domain arithmetic. The `_fd_*` functions are injected into `base_globals` in both `compile_predicate` and `compile_predicate_trampoline`.

??? info "Test coverage"

    Tests are in `tests/test_clpfd.py` (76 tests) and `tests/test_phase5_builtins.py` (global constraint tests).

    - **Domain operations**: from_range, contains, min/max, size, singleton, intersection, remove, remove_above/below, values
    - **in_domain**: post domain, unify succeeds/fails, list, narrows existing, singleton binds, empty fails, ground int
    - **label**: single var, two vars (cartesian product), backtracking restores, all ground
    - **Equivalent**: same/different atoms, compounds, vars, bound vars
    - **fd_eq/ne/lt/le/gt/ge**: ground values, var-int, var-var, auto-domain, wipeout
    - **Propagation**: lt chain, eq propagation, wipeout, backtracking restores domains
    - **AC-3 fixpoint**: cascaded `<` chain (X<Y<Z, fix Z → X,Y ground without labeling), Ne narrows after domain change
    - **Compiler integration**: ground eq/ne/lt/le/gt/ge, var eq via solve, chained le, ne with label, evaluate unchanged, is unchanged, is-not unchanged
    - **AllDifferent**: basic permutations, ground ok/fail, via solve
    - **N-Queens**: 4-queens (2 solutions), 8-queens (92 solutions)
    - **SEND+MORE=MONEY**: unique solution (9567 + 1085 = 10652)
    - **FD + dif interaction**: both constraints on same var, independent operation
    - **SumConstraint**: narrows total, narrows vars from total, wipeout, inequality narrows, label produces only valid pairs, ground vars with unbound value
    - **ScalarProductConstraint**: narrows total, backward narrowing, negative coefficients, wipeout
    - **ElementConstraint**: narrows value from index domain, narrows index from value, wipeout, bidirectional narrowing
    - **CircuitConstraint**: self-loop pruning, sub-tour detection, forced chain completion, all solutions

    ---

## CLP(B) — Boolean Constraints

CLP(B) provides constraint logic programming over Booleans via reduced ordered BDDs. See the dedicated [CLP(B)](clpb.md) page for full documentation including operators, builtins, BDD internals, and examples.

Quick reference:

### Operator syntax

Python's bitwise operators are used for Boolean expressions:

| Operator | Meaning |
|---|---|
| `X & Y` | AND |
| `X \| Y` | OR |
| `X ^ Y` | XOR |
| `~X` | NOT |
| `BoolEq(X, Y)` | Equivalence (iff) |
| `BoolImpl(X, Y)` | Implication (X→Y) |

These operators are unused by the arithmetic compiler path — `BitAnd`, `BitOr`, `BitXor`, and `Invert` nodes pass through `term_to_ast_expr` as structural terms and are walked by `_expr_to_bdd` at runtime.

??? abstract "BDD representation"

    - **`BDD_TRUE = 1`**, **`BDD_FALSE = 0`** — terminal constants (plain ints)
    - **`BDDNode(var_id, high, low)`** — immutable internal node
      - `var_id`: integer ordering index (lower = closer to root)
      - `high`: child BDD when var=1
      - `low`: child BDD when var=0
    - **Per-variable unique tables** (Triska/Knuth technique): each variable stores its own node lookup dict, eliminating the need for a global unique table
    - **Reduction rule**: if `high == low`, the node is skipped (returns the child directly)
    - **Local memoization**: `apply()` creates a fresh memo dict per call, not persisted globally

??? abstract "Variable ordering"

    Static first-appearance order via a module-level monotonic counter. Variables are assigned ordering IDs on first encounter in `enumerate_var()`. No dynamic reordering.

??? abstract "BoolState — per-variable state"

    Each constrained variable stores a `BoolState` as an attributed-variable attribute under the key `"clpb"`:

    ```python
    class BoolState:
        __slots__ = ('sat_expr', 'bdd', 'root_var')
        sat_expr: Any         # original Boolean formula (for rebuild on aliasing)
        bdd: Any              # current BDD (BDDNode or terminal)
        root_var: Var         # shared root variable linking all vars in this network
    ```

    **Trail safety**: every state change creates a new `BoolState` and calls `put_attr(var, "clpb", new_state, trail)`. The old state is automatically restored on `trail.undo()`. Never mutate in place.

??? abstract "Connected-component merging"

    When `sat()` is called with an expression containing variables that already have constraints, ALL connected BDDs are conjoined into a single combined BDD. This ensures that multiple `sat()` calls sharing variables form a single constraint network — binding any variable propagates through all constraints in the network.

### Builtins

| Builtin | Arity | Description |
|---|---|---|
| `Sat` | 1 | `Sat(Expr)` — post Boolean constraint, fail if unsatisfiable |
| `Taut` | 2 | `Taut(Expr, T)` — T=1 if tautology, T=0 if contradiction, else fail |
| `SatCount` | 2 | `SatCount(Expr, N)` — N is the number of satisfying assignments |
| `BoolLabeling` | 1 | `BoolLabeling(Vars)` — enumerate 0/1 assignments |

### Syntax examples

**Posting constraints:**
```clausal
# skip
Sat(X & Y)                # both must be 1
Sat(X | Y)                # at least one must be 1
Sat(~X)                    # X must be 0
Sat(BoolEq(X, Y))         # X ↔ Y (equivalence)
Sat(BoolImpl(X, Y))       # X → Y (implication)
```

**Half adder:**
```clausal
HalfAdder(X, Y, SUM, CARRY) <- (
    Sat(BoolEq(SUM, X ^ Y)),
    Sat(BoolEq(CARRY, X & Y))
)
```

**Tautology check (De Morgan's law):**
```clausal
# skip
Taut(BoolEq(~(X & Y), ~X | ~Y), T)   # T = 1
```

**Model counting:**
```clausal
# skip
SatCount(X ^ Y, N)       # N = 2
SatCount(X & Y, N)       # N = 1
SatCount(X | Y, N)       # N = 3
```

**Labeling (enumerate all solutions):**
```clausal
solve(X, Y) <- (
    Sat(X ^ Y),
    BoolLabeling([X, Y])
)
# yields (0,1) and (1,0)
```

**Pigeon-hole (unsatisfiable):**
```clausal
PigeonHole() <- (
    Sat(P11 | P12),
    Sat(P21 | P22),
    Sat(P31 | P32),
    Sat(~(P11 & P21)),
    Sat(~(P11 & P31)),
    Sat(~(P21 & P31)),
    Sat(~(P12 & P22)),
    Sat(~(P12 & P32)),
    Sat(~(P22 & P32)),
    BoolLabeling([P11, P12, P21, P22, P31, P32])
)
# no solutions — 3 pigeons can't fit in 2 holes
```

??? example "Python API"

    ```python
    from clausal.logic.variables import Var, Trail, deref, unify
    from clausal.logic.clpb import sat, taut, sat_count, bool_labeling, BoolEq
    from clausal.pythonic_ast.nodes import BitAnd, BitOr, BitXor, Invert
    
    trail = Trail()
    x, y = Var(), Var()
    
    # Post constraint: X XOR Y must be true
    sat(BitXor(left=x, right=y), trail)
    
    # Label (enumerate solutions)
    for _ in bool_labeling([x, y], trail):
        print(deref(x), deref(y))   # prints 0 1, then 1 0
    
    # Tautology check
    t = Var()
    taut(BitOr(left=x, right=Invert(operand=x)), t, Trail())
    # t = 1 (tautology)
    
    # Model counting
    n = Var()
    sat_count(BitXor(left=Var(), right=Var()), n, Trail())
    # n = 2
    ```

??? abstract "Attribute hook"

    `_bool_hook` fires when a CLP(B)-constrained variable is unified:

    - **Bound to 0 or 1**: restrict BDD at this variable's level, propagate forced values on remaining variables
    - **Bound to another Var (aliasing)**: conjoin both variables' BDDs, update combined state on surviving variable, propagate
    - **Bound to other integer**: fail (only 0/1 are valid Boolean values)
    - **Bound to non-integer/non-Var**: fail

??? abstract "Interaction with other constraints"

    CLP(B) uses the attribute key `"clpb"`, independent of CLP(ℤ) (`"fd"`), CLP(ℝ) (`"real"`), and dif/2 (`"dif"`). All hooks fire independently when a variable is bound. A variable can have CLP(B), CLP(ℤ), CLP(ℝ), and dif constraints simultaneously (though combining CLP(B) with numeric domains on the same variable is unusual).

    **Important:** CLP(B) variables are constrained to `0`/`1` (integers), not Python booleans (`True`/`False`). Booleans are explicitly rejected by CLP(ℝ) and CLP(ℤ) — they are distinct types in Clausal's constraint system.

??? info "Test coverage"

    Tests are in `tests/test_clpb.py` (87 tests).

    - **BDDNode**: construction, identity equality, hashable, repr
    - **make_node**: reduction rule, unique table sharing, different children
    - **apply**: all terminal cases (and/or/xor/equiv/impl), variable operands, two-variable xor, negate
    - **restrict**: terminal, identity, higher var
    - **_expr_to_bdd**: int/bool constants, invalid int, Var, BitAnd/BitOr/BitXor/Invert, BoolEq/BoolImpl, nested, unsupported type
    - **sat**: ground true/false, single var forced, and/negation/or forcing, contradiction, tautology, sequential conjunction
    - **taut**: tautology (T=1), contradiction (T=0), indeterminate (fail), ground, xor, equiv
    - **sat_count**: xor/and/or/tautology/contradiction counts, single var, three vars
    - **BoolLabeling**: single var (2 sols), two vars (4 sols), constrained xor (2 sols), all bound (1 sol)
    - **Attribute hook**: bind constrained var, invalid int, var-var merge, incompatible merge
    - **Trail safety**: backtrack restores state, labeling backtracks cleanly
    - **BoolEq/BoolImpl**: construction, equivalence in sat, implication in sat
    - **Half adder**: complete truth table (4 tests)
    - **Full adder**: 5 input combinations
    - **Pigeon-hole**: 3 pigeons 2 holes → unsatisfiable
    - **Circuit equivalence**: De Morgan's law via Taut, non-equivalence
    - **Fixture integration**: HalfAdder, FullAdder, PigeonHole via `.clausal` file

---

## CLP(ℝ) — Real-domain Constraints

CLP(ℝ) provides constraint logic programming over the reals using interval arithmetic over IEEE doubles with outward rounding. See the dedicated [CLP(ℝ)](clpr.md) page for full documentation including builtins, HC4 propagation internals, and examples.

Quick reference:

### Builtins

| Builtin | Description |
|---|---|
| `InReal(Var)` | Declare real variable with domain `[−∞, +∞]` |
| `InReal(Var, Lo, Hi)` | Declare real variable with domain `[Lo, Hi]` |
| `LabelReal(Vars)` | Bisect intervals to IEEE float precision |
| `LabelReal(Vars, Eps)` | Bisect until interval width ≤ Eps |

### Unified dispatch

The same comparison operators (`==`, `!=`, `<`, `>`, `<=`, `>=`) route to CLP(ℝ) automatically when either operand is a `float` literal or a variable declared with `InReal`. No separate operator set or brace syntax is needed.

```clausal
# skip
# Float literal triggers CLP(ℝ)
sqrt2(X) <- (
    InReal(X, 0.0, 2.0),
    X * X == 2.0,
    LabelReal([X], 1.0e-12)
)
# → X ≈ 1.4142135623730951
```

### Cross-domain notes

- **FD + Real coexistence:** a variable can carry both an FD domain and a real interval. The FD domain enforces integrality; the real interval handles continuous narrowing. Both stay in sync.
- **Booleans are not numbers:** Python's `True`/`False` are not valid in CLP(ℝ) or CLP(ℤ) expressions. Use `0`/`1` if you need numeric values. Booleans belong to CLP(B).
- **Labeling order:** for mixed-domain variables, use `Label` (FD) first to fix integer values, then `LabelReal` for remaining real variables. `LabelReal` does not enforce integrality.
- **Large integers:** integers beyond 2^53 lose precision when converted to IEEE doubles during interval propagation. Ground integer-integer comparisons are done exactly.

---

*See also: [CLP(B)](clpb.md) — Boolean constraint solving · [CLP(ℝ)](clpr.md) — real-domain interval arithmetic · [Tabling](tabling.md) — memoised search, required for Well-Founded Semantics.*
