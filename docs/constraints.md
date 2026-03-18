# Constraints

Clausal supports constraint logic programming through attributed variables. The C extension provides `AttVar` (attributed variable), `put_attr`/`get_attr`/`del_attr` (all trailed), `register_attr_hook`, and a wakeup queue in `do_unify_and_wake`. Constraint solvers register hooks that fire when a constrained variable is unified.

Two constraint solvers are built in:

- **Dif/2** — disequality constraint (`clausal.logic.constraints`)
- **CLP(FD)** — finite-domain constraints (`clausal.logic.clpfd`)

---

## Dif/2 — Disequality constraint

`Dif(X, Y)` constrains X and Y to be different. Unlike a point-in-time check, the constraint survives and is re-evaluated whenever either variable gets bound.

### Syntax

In `.clausal` files, `is not` has dif semantics:

```
safe_assign(X_, Y_) <- (
    X_ is not Y_
    and X_ is 1
    and Y_ is 2
)
```

This succeeds because X and Y end up with different values (1 and 2), even though at the time of `is not` they are both unbound.

The builtin `Dif/2` can also be called explicitly:

```
constrained(X_, Y_) <- (
    Dif(X_, Y_)
    and X_ is 1
    and Y_ is 2
)
```

### Semantics

| Clausal syntax | Semantics | Prolog equivalent |
|---|---|---|
| `X_ is not Y_` | Constraint: must end up different | `Dif(X, Y)` |
| `not (X_ is Y_)` | Immediate: don't unify right now | `\=(X, Y)` |

The `is not` operator uses `dif/2` constraint semantics rather than immediate `\=`. The old immediate-check semantics are still available as `not (X_ is Y_)` — negation-as-failure of unification — which already works via the existing `Not(Unify(...))` compilation path.

??? example "Examples"

    **Constraint succeeds — terms stay different:**
    ```
    X_ is not Y_, X_ is 1, Y_ is 2    # succeeds: 1 ≠ 2
    ```

    **Constraint fails — terms become equal:**
    ```
    X_ is not Y_, X_ is 1, Y_ is 1    # fails: dif violated when Y=1
    ```

    **Multiple constraints:**
    ```
    X_ is not 1, X_ is not 2, X_ is 3    # succeeds: 3 ≠ 1 and 3 ≠ 2
    X_ is not 1, X_ is not 2, X_ is 1    # fails: dif(X, 1) violated
    ```

    **Immediate check (old semantics):**
    ```
    not (X_ is Y_)    # fails if X and Y are both unbound (they CAN unify)
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

## CLP(FD) — Finite-domain constraints

CLP(FD) is built into the language as the default way to reason about integers (per Markus Triska's recommendation). The comparison operators `==`, `!=`, `<`, `>`, `<=`, `>=` are CLP(FD) constraint operators.

The implementation lives in `clausal.logic.clpfd`.

### Operator semantics

| Operator | Meaning |
|---|---|
| `==` | CLP(FD) arithmetic equality |
| `!=` | CLP(FD) arithmetic disequality |
| `<` `>` `<=` `>=` | CLP(FD) comparison constraints |
| `is` | Unification (unchanged) |
| `is not` | `Dif/2` constraint (unchanged) |
| `:=` | Eager arithmetic eval + unify (unchanged) |

When both sides are ground (no unbound Vars), the operators fall back to direct Python comparison. When at least one side is an unbound Var, CLP(FD) constraints are posted.

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

    When a CLP(FD) operator encounters an unbound Var with no FD domain, it auto-creates a default domain of `(-2^63, 2^63)` — effectively unbounded for practical purposes, stored as a single interval.

??? abstract "Constraint types"

    | Constraint | Description |
    |---|---|
    | `EqConstraint(lhs, rhs)` | X == Y — narrow both domains to intersection |
    | `NeConstraint(lhs, rhs)` | X != Y — when one side is singleton, remove from other |
    | `LtConstraint(lhs, rhs)` | X < Y — upper-bound X by max(Y)-1, lower-bound Y by min(X)+1 |
    | `LeConstraint(lhs, rhs)` | X <= Y — upper-bound X by max(Y), lower-bound Y by min(X) |
    | `AllDiffConstraint(vars)` | all_different — when one var is ground, remove from all others |

??? abstract "Propagation (AC-3)"

    Constraints are propagated via an AC-3 fixpoint loop. When a propagator narrows a domain:

    1. Create new `FDVar` with narrowed domain + same constraints.
    2. `put_attr(var, "fd", new_state, trail)` — trailed.
    3. If singleton `{v}`: `unify(var, v, trail)` → fires FD hook + dif hooks.
    4. If empty: return False (wipeout → backtrack).
    5. Add var to propagation queue.

??? abstract "FD attribute hook"

    `_fd_hook` fires when an FD-constrained variable is unified:

    - **Bound to integer**: check domain membership, propagate all constraints.
    - **Bound to another Var**: intersect domains, merge constraints, check singleton, propagate.
    - **Bound to non-integer/non-Var**: fail.

??? abstract "Expression domain arithmetic"

    CLP(FD) constraint functions walk arithmetic expression trees (`Add`, `Sub`, `Mult`, `Negate`) to compute domain bounds:

    ```
    [a,b] + [c,d] = [a+c, b+d]
    [a,b] - [c,d] = [a-d, b-c]
    [a,b] * [c,d] = [min(corners), max(corners)]
    -[a,b]        = [-b, -a]
    ```

    Ground arithmetic expressions are evaluated before comparison.

### Builtins

| Builtin | Arity | Description |
|---|---|---|
| `InDomain` | 3 | `InDomain(Var_or_list, Lo, Hi)` — post domain [Lo, Hi] |
| `Label` | 1 | `Label(Vars)` — enumerate values, first-fail strategy |
| `AllDifferent` | 1 | `AllDifferent(Vars)` — pairwise disequality constraint |
| `Equivalent` | 2 | `Equivalent(X, Y)` — structural equality (old `==` behavior) |

### Syntax examples

**Domain declaration and labeling:**
```
solve(X_) <- (
    InDomain(X_, 1, 10)
    and Label([X_])
)
```

**Chained comparison (natural Python syntax):**
```
bounded(X_) <- (1 <= X_ and X_ <= 10 and Label([X_]))
```

Since `<=` is CLP(FD), `1 <= X_` and `X_ <= 10` naturally constrain X's domain.

**N-Queens via AllDifferent:**
```
queens(N_, Qs_) <- (
    InDomain(Qs_, 1, N_)
    and AllDifferent(Qs_)
    and Label(Qs_)
    and check_diagonals(Qs_)
)
```

**SEND + MORE = MONEY:**
```
sendmoney(S_, E_, N_, D_, M_, O_, R_, Y_) <- (
    InDomain([S_, E_, N_, D_, M_, O_, R_, Y_], 0, 9)
    and AllDifferent([S_, E_, N_, D_, M_, O_, R_, Y_])
    and S_ != 0
    and M_ != 0
    and Label([S_, E_, N_, D_, M_, O_, R_, Y_])
    and (Send_ := S_ * 1000 + E_ * 100 + N_ * 10 + D_)
    and (More_ := M_ * 1000 + O_ * 100 + R_ * 10 + E_)
    and (Money_ := M_ * 10000 + O_ * 1000 + N_ * 100 + E_ * 10 + Y_)
    and (Sum_ := Send_ + More_)
    and Sum_ == Money_
)
```

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

??? abstract "Interaction with dif/2"

    CLP(FD) and dif/2 use independent attribute keys (`"fd"` and `"dif"`). Both hooks fire when a variable is bound. They do not interfere with each other. A variable can have both FD constraints and dif constraints simultaneously.

??? abstract "Compiler integration"

    `StructuralEq`/`StructuralNeq` and `Lt`/`LtE`/`Gt`/`GtE` goal nodes compile to:

    ```python
    if _fd_eq(l, r, trail):    # ==
        k_stmts
    if _fd_ne(l, r, trail):    # !=
        k_stmts
    if _fd_lt(l, r, trail):    # <
        k_stmts
    ```

    Both sides are compiled with `eval_arith=False` so arithmetic expression trees survive as structural terms for CLP(FD) domain arithmetic. The `_fd_*` functions are injected into `base_globals` in both `compile_predicate` and `compile_predicate_trampoline`.

??? info "Test coverage"

    Tests are in `tests/test_clpfd.py` (74 tests).

    - **Domain operations**: from_range, contains, min/max, size, singleton, intersection, remove, remove_above/below, values
    - **in_domain**: post domain, unify succeeds/fails, list, narrows existing, singleton binds, empty fails, ground int
    - **label**: single var, two vars (cartesian product), backtracking restores, all ground
    - **Equivalent**: same/different atoms, compounds, vars, bound vars
    - **fd_eq/ne/lt/le/gt/ge**: ground values, var-int, var-var, auto-domain, wipeout
    - **Propagation**: lt chain, eq propagation, wipeout, backtracking restores domains
    - **Compiler integration**: ground eq/ne/lt/le/gt/ge, var eq via solve, chained le, ne with label, evaluate unchanged, is unchanged, is-not unchanged
    - **AllDifferent**: basic permutations, ground ok/fail, via solve
    - **N-Queens**: 4-queens (2 solutions), 8-queens (92 solutions)
    - **SEND+MORE=MONEY**: unique solution (9567 + 1085 = 10652)
    - **FD + dif interaction**: both constraints on same var, independent operation

    ---

## CLP(B) — Boolean Constraints

CLP(B) provides constraint logic programming over Booleans via reduced ordered BDDs. See the dedicated [CLP(B)](clpb.md) page for full documentation including operators, builtins, BDD internals, and examples.

Quick reference:

### Operator syntax

Python's bitwise operators are used for Boolean expressions:

| Operator | Meaning |
|---|---|
| `X_ & Y_` | AND |
| `X_ \| Y_` | OR |
| `X_ ^ Y_` | XOR |
| `~X_` | NOT |
| `BoolEq(X_, Y_)` | Equivalence (iff) |
| `BoolImpl(X_, Y_)` | Implication (X→Y) |

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
```
Sat(X_ & Y_)                # both must be 1
Sat(X_ | Y_)                # at least one must be 1
Sat(~X_)                     # X must be 0
Sat(BoolEq(X_, Y_))         # X ↔ Y (equivalence)
Sat(BoolImpl(X_, Y_))       # X → Y (implication)
```

**Half adder:**
```
HalfAdder(X_, Y_, Sum_, Carry_) <- (
    Sat(BoolEq(Sum_, X_ ^ Y_))
    and Sat(BoolEq(Carry_, X_ & Y_))
)
```

**Tautology check (De Morgan's law):**
```
Taut(BoolEq(~(X_ & Y_), ~X_ | ~Y_), T_)   # T_ = 1
```

**Model counting:**
```
SatCount(X_ ^ Y_, N_)       # N_ = 2
SatCount(X_ & Y_, N_)       # N_ = 1
SatCount(X_ | Y_, N_)       # N_ = 3
```

**Labeling (enumerate all solutions):**
```
solve(X_, Y_) <- (
    Sat(X_ ^ Y_)
    and BoolLabeling([X_, Y_])
)
# yields (0,1) and (1,0)
```

**Pigeon-hole (unsatisfiable):**
```
PigeonHole() <- (
    Sat(P11_ | P12_)
    and Sat(P21_ | P22_)
    and Sat(P31_ | P32_)
    and Sat(~(P11_ & P21_))
    and Sat(~(P11_ & P31_))
    and Sat(~(P21_ & P31_))
    and Sat(~(P12_ & P22_))
    and Sat(~(P12_ & P32_))
    and Sat(~(P22_ & P32_))
    and BoolLabeling([P11_, P12_, P21_, P22_, P31_, P32_])
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

    CLP(B) uses the attribute key `"clpb"`, independent of CLP(FD) (`"fd"`) and dif/2 (`"dif"`). All three hooks fire independently when a variable is bound. A variable can have CLP(B), CLP(FD), and dif constraints simultaneously (though combining CLP(B) with CLP(FD) on the same variable is unusual).

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
