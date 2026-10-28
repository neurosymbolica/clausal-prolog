# Constraints

Clausal Prolog supports constraint logic programming through attributed variables. The C extension provides `AttVar` (attributed variable), `put_attr`/`get_attr`/`del_attr` (all trailed), `register_attr_hook`, and a wakeup queue in `do_unify_and_wake`. Constraint solvers register hooks that fire when a constrained variable is unified.

!!! note "Clausal Prolog examples"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`), which uses ISO Prolog syntax: CLP(ℤ) is
    `library(clpz)`'s `#=`, `#\=`, `#<`, ... as in Scryer. The
    [seam](syntax.md) writes the same constraints with Python's bare
    comparison operators (`==`, `!=`, `<`, ...); where its spelling or
    behaviour differs, this page says so. CLP(B) is the exception: its
    Boolean expressions can only be written in the seam (see
    [CLP(B)](#clpb-boolean-constraints)).
    Prolog constraint programs using `library(clpfd)` or `library(clpz)` can be [imported directly](importing_prolog.md).

Two constraint solvers are built in:

- **dif/2** — disequality constraint (`clausal.logic.constraints`)
- **CLP(ℤ)** — integer constraints over all integers (`clausal.logic.clpfd`)

---

## dif/2 — Disequality constraint

`dif(X, Y)` constrains X and Y to be different. Unlike a point-in-time check, the constraint survives and is re-evaluated whenever either variable gets bound.

### Syntax

`dif/2` is a builtin; no import is needed:

```clausal
constrained(X, Y) :-
    dif(X, Y),
    X = 1,
    Y = 2.

test("constrained") :-
    constrained(1, 2).
```

This succeeds because X and Y end up with different values (1 and 2), even though at the time of `dif/2` they are both unbound. (The seam also spells `dif(X, Y)` as `X is not Y`.)

### Semantics

| Clausal Prolog | Semantics | Seam spelling |
|---|---|---|
| `dif(X, Y)` | Constraint: must end up different | `X is not Y` |
| `X \= Y` | Immediate: don't unify right now | `not (X is Y)` |

`dif/2` is a constraint, posted now and checked whenever its terms are bound
further; ISO `\=` is the immediate check, negation-as-failure of unification.

??? example "Examples"

    **Constraint succeeds — terms stay different:**
    ```text
    --8<-- "tests/fixtures/docs/constraints_sigs.txt:semantics"
    ```

    **Constraint fails — terms become equal:**
    ```text
    --8<-- "tests/fixtures/docs/constraints_sigs.txt:semantics_ex2"
    ```

    **Multiple constraints:**
    ```text
    --8<-- "tests/fixtures/docs/constraints_sigs.txt:semantics_ex3"
    ```

    **Immediate check:**
    ```text
    --8<-- "tests/fixtures/docs/constraints_sigs.txt:semantics_ex4"
    ```

    ---

??? abstract "Design details"

    ### All Vars are AttVars

    `clausal.logic.variables` aliases `Var = AttVar`. Every logic variable created with `Var()` is an attributed variable from birth. `AttVar` inherits from the C `Var` type via `tp_base`, so `is_var()`, `deref()`, and `unify()` work unchanged. The only overhead is 8 bytes per variable for a NULL attributes pointer (no dict is allocated until a constraint is actually attached).

    The original `Var` type is available as `PlainVar` if needed.

    ### Constraint algorithm

    when `dif(x, y, trail)` is called:

    1. Deref both arguments.
    2. Sandbox-unify as `=/2` does, with no occurs check (`_structural_unify`): a rational tree is a solution, so `dif(X, f(X))` suspends and a later `X = f(X)` fails, as in Scryer and SICStus.
    3. **Unify fails** → structurally incompatible (e.g. `dif(1, 2)`) → return True immediately.
    4. **Unify succeeds, no trail growth** → terms already identical (e.g. `dif(X, X)`) → return False.
    5. **Unify succeeds with trail growth** → terms could become equal → undo sandbox, collect all free variables in both terms, attach `(x, y)` constraint pair to each via `put_attr`, return True.

    `_structural_unify` (and its occurs-checked sibling `_structural_unify_oc`, behind `subsumes_term/2` and `unify_with_occurs_check/2`) walks term instances and partial lists itself and hands everything else to the engine's unify, whose rational-tree walk terminates on a cyclic term. The variable collection of step 5 is iterative past a depth threshold, with a visited set, so a cyclic or very deep pair suspends instead of raising.

    ### Attribute hook

    when a constrained variable is unified, the `_dif_hook` fires:

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

    Tests are in `tests/test_dif.py`.

    - **`_collect_free_vars`**: scalars, Vars, bound vars, compound cells, lists, nested structures, deduplication
    - **Direct `dif`**: ground equal/different, same var, one var, both vars, compound terms
    - **Rational trees**: `dif(X, f(X))` suspends (`X = f(X)` is a solution); a pair holding a cyclic or 100k-deep term suspends or decides as in Scryer (`tests/iso/test_dif_cyclic_scryer.py`)
    - **Constraint propagation**: same/different values, multiple constraints, compound args, transitive via shared var
    - **Backtracking**: constraint undone on trail undo, binding failure doesn't corrupt trail
    - **Compiled integration** (seam): `is not` with later binding (succeed/fail), ground terms, same var, `not (X is Y)` still works, multiple constraints
    - **Builtin `dif/2`**: callable from clausal code, with vars and ground terms
    - **Import hook**: `.seam` file with `is not` using proper dif semantics

    ---

## CLP(ℤ) — Integer constraints

CLP(ℤ) is built into the language as the default way to reason about integers (per Markus Triska's recommendation). In Clausal Prolog it is `library(clpz)`: `#=`, `#\=`, `#<`, `#>`, `#=<`, `#>=` are its constraint operators. (In the seam the bare comparison operators `==`, `!=`, `<`, `>`, `<=`, `>=` are these constraints.) See also [Arithmetic](arithmetic.md) for relational arithmetic predicates like `plus/3`, `between/3`, and `divmod_/4`.

The implementation lives in `clausal.logic.clpfd`.

### Operator semantics

| Clausal Prolog | Meaning | Seam spelling |
|---|---|---|
| `X #= Y` | CLP(ℤ) arithmetic equality | `X == Y` |
| `X #\= Y` | CLP(ℤ) arithmetic disequality | `X != Y` |
| `#<` `#>` `#=<` `#>=` | CLP(ℤ) comparison constraints | `<` `>` `<=` `>=` |
| `X = Y` | Unification, no evaluation | `X is Y` |
| `dif(X, Y)` | `dif/2` constraint | `X is not Y` |
| `X is Expr` | Eager ISO arithmetic evaluation + unify | `eval_(Expr, X)` |
| `X == Y` | Structural equality (ISO `==/2`) | `'=='(X, Y)` or `structural_eq/2` |

When both sides are ground (no unbound variables), the comparison is decided at once. When at least one side is an unbound variable, a constraint is posted: CLP(ℤ) for integers, [CLP(ℝ)](clpr.md) when a float is involved. Exact rationals are [CLP(ℚ)](clpq.md), `library(clpq)`'s `{...}` constraints.

What an operator means is defined once in [Operators](operators.md); evaluation is in [Arithmetic](arithmetic.md). Three rules matter most for constraints:

- **`/` inside a CLP(ℤ) constraint is exact integer division.** `X #= 6 / 2` gives `3`, and `X #= 7 / 2` has no solution, as in Scryer's clpz. In evaluation `X is 7 / 2` is the float `3.5`; for the exact rational write the CLP(ℚ) constraint `{X = 7/2}`, which answers `X = 7 rdiv 2`. (The seam's `X == 7 / 2` is the exact rational instead.)
- **A zero divisor makes a constraint fail**, it does not raise. `X #= 1 // 0` has no solutions, and a divisor that becomes 0 during labeling fails only that branch. Evaluation (`X is 1 // 0`) raises `evaluation_error(zero_divisor)` instead.
- **A non-arithmetic term is a domain error.** `X #= foo(1)` raises Scryer's clpz error `error(domain_error(clpz_expression, foo(1)), (#=)/2)`.

```clausal
:- use_module(library(clpz)).

exact(X) :-
    X #= 6 / 2.                         % X = 3
no_half(X) :-
    X #= 7 / 2.                         % fails: 7 is not a multiple of 2
no_value(X) :-
    X #= 1 // 0.                        % fails: no solutions
quotients(X, Y) :-                      % Y = 0 fails its branch only
    in_domain(Y, 0, 3),
    X #= 12 // Y,
    label([Y]).                         % 12-1, 6-2, 4-3

test("exact") :-
    exact(X),
    X == 3.

test("no half") :-
    \+ no_half(_).

test("zero divisor fails") :-
    \+ no_value(_).

test("quotients") :-
    findall(X-Y, quotients(X, Y), PAIRS),
    PAIRS == [12-1, 6-2, 4-3].

test("not an expression") :-
    catch(_ #= foo(1),
          error(domain_error(clpz_expression, foo(1)), _),
          true).

test("eager division") :-
    X is 7 / 2,
    X == 3.5,
    catch(_ is 1 // 0, error(evaluation_error(zero_divisor), _), true).
```

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

    when a CLP(ℤ) operator encounters an unbound Var with no domain, it auto-creates a default domain of `(-∞, +∞)` — the entire integer line, stored as a single interval. This is true CLP(Z) semantics: variables range over all integers until explicitly constrained. To enumerate solutions with `label/1`, variables must first be given finite bounds via `in_domain/3` or comparison constraints.

??? abstract "Constraint types"

    **Binary / unary constraints** (posted by `#=`, `#\=`, `#<`, `#=<`, `#>`, `#>=`):

    | Constraint | Description |
    |---|---|
    | `EqConstraint(lhs, rhs)` | X #= Y — narrow both domains to intersection |
    | `NeConstraint(lhs, rhs)` | X #\= Y — when one side is singleton, remove from other |
    | `LtConstraint(lhs, rhs)` | X #< Y — upper-bound X by max(Y)-1, lower-bound Y by min(X)+1 |
    | `LeConstraint(lhs, rhs)` | X #=< Y — upper-bound X by max(Y), lower-bound Y by min(X) |
    | `AllDiffConstraint(vars)` | all_different — when one var is ground, remove from all others |

    **Global constraints** (posted by `sum_/3`, `scalar_product/4`, `element/3`, `circuit/1`):

    | Constraint | Description |
    |---|---|
    | `SumConstraint(vars, total)` | Σ vars = total — bounds-consistency: narrows total to [min_sum, max_sum] and each var using slack |
    | `ScalarProductConstraint(coeffs, vars, total)` | Σ cᵢ·vᵢ = total — same as sum_ but with signed coefficients; division direction flips for negative coefficients |
    | `ElementConstraint(index, lst, value)` | value = lst[index−1] — AC-3: narrows index to positions whose list element overlaps value's domain, narrows value to union of those elements' domains |
    | `CircuitConstraint(vars)` | Hamiltonian circuit — restricts domains to [1,n], removes self-loops, delegates to AllDiffConstraint, prunes premature sub-tours via forced-chain detection |

    Inequality operators (`#<`, `#>`, `#=<`, `#>=`, `#\=`) for `sum_` and `scalar_product` introduce an intermediate total variable, post the equality constraint on it, then chain the appropriate binary relational constraint.

    A non-linear sub-expression of a comparison -- `*` of two unknowns, `//`, `div`, `mod`, `rem`, `^`, `min`, `max`, `abs` -- is lifted into a fresh variable with a propagator of its own (`clausal/logic/clpfd_nonlinear.py`), as clpz does, and the comparison is posted over it. Each propagator narrows in every direction (the result from the operands, each operand from the result and the other operand), removes 0 from a divisor, and is domain consistent while the operands are small: `R*T #= 14, T = 7` gives `R = 2`, `X #= Y mod 3` gives `X in 0..2`. A linear disequality removes its one excluded value as soon as all but one variable are known (`X #\= Y + 1, Y = 2` removes 3 from X), and a sum left with two unit-coefficient variables keeps their holes (`X - Y #= 0` with `Y in 1\/3\/5` gives `X in 1\/3\/5`).

??? abstract "Propagation (AC-3)"

    Constraints are propagated via an AC-3 fixpoint loop. when a propagator narrows a domain:

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
| `in_domain` | 3 | `in_domain(Var_or_list, Lo, Hi)` — post domain [Lo, Hi] |
| `label` | 1 | `label(Vars)` — enumerate values, first-fail strategy (see [labeling gotcha](#gotcha-generate-and-test-vs-constraint-and-label)) |
| `all_different` | 1 | `all_different(Vars)` — pairwise disequality constraint |
| `structural_eq` | 2 | `structural_eq(X, Y)` — true structural equality (Prolog `==/2`; in `.clausal`, just `X == Y`) |
| `sum_` | 3 | `sum_(+Vars, +Op, +Value)` — bounds-consistency propagation for Σ Vars Op Value |
| `scalar_product` | 4 | `scalar_product(+Coeffs, +Vars, +Op, +Value)` — bounds-consistency for Σ Cᵢ·Vᵢ Op Value |
| `element` | 3 | `element(?Index, +List, ?Value)` — arc-consistency: Value = List[Index] (1-based) |
| `circuit` | 1 | `circuit(+Vars)` — Hamiltonian circuit with sub-tour elimination during propagation |

### Syntax examples

**Domain declaration and labeling:**
```clausal
:- use_module(library(clpz)).

solve(X) :-
    in_domain(X, 1, 10),
    label([X]).

test("first value") :-
    solve(X),
    X == 1.
```

(`X in 1..10`, Scryer's spelling, works too.)

**Comparison constraints bound a domain:**
```clausal
:- use_module(library(clpz)).

bounded(X) :-
    1 #=< X,
    X #=< 10,
    label([X]).

test("ten values") :-
    findall(X, bounded(X), XS),
    length(XS, 10).
```

Since `#=<` is CLP(ℤ), `1 #=< X` and `X #=< 10` constrain X's domain. (The seam writes this as Python's chained comparison, `1 <= X, X <= 10`.)

**N-Queens via all_different:**
```clausal
:- use_module(library(clpz)).

queens(N, QS) :-
    length(QS, N),
    in_domain(QS, 1, N),
    all_different(QS),
    safe(QS),
    label(QS).

% No two queens share a diagonal
safe([]).
safe([Q|QS]) :-
    no_attack(Q, QS, 1),
    safe(QS).

no_attack(_, [], _).
no_attack(Q, [Q1|QS], D) :-
    Q #\= Q1 + D,
    Q #\= Q1 - D,
    D1 #= D + 1,
    no_attack(Q, QS, D1).

test("four queens") :-
    findall(QS, queens(4, QS), ALL),
    ALL == [[2, 4, 1, 3], [3, 1, 4, 2]].
```

**SEND + MORE = MONEY:**
```clausal
:- use_module(library(clpz)).

sendmoney(S, E, N, D, M, O, R, Y) :-
    in_domain([S, E, N, D, M, O, R, Y], 0, 9),
    all_different([S, E, N, D, M, O, R, Y]),
    S #\= 0,
    M #\= 0,
    S * 1000 + E * 100 + N * 10 + D + (M * 1000 + O * 100 + R * 10 + E) #=
        M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    label([S, E, N, D, M, O, R, Y]).

test("send more money") :-
    sendmoney(S, E, N, D, M, O, R, Y),
    [S, E, N, D, M, O, R, Y] == [9, 5, 6, 7, 1, 0, 8, 2].
```

The `#=` constraint is posted *before* `label` so the solver propagates the equation across all eight domains before any labeling begins. See the gotcha below.

**Querying from Python.** This is seam-only, since Clausal Prolog never escapes into Python. In a `.seam` file, a goal in `for` position runs and hands back each answer; the goal's variables become ordinary locals (seam syntax):

```seam
-module(puzzle, [])

sendmoney(S, E, N, D, M, O, R, Y) <- (
    in_domain([S, E, N, D, M, O, R, Y], 0, 9),
    all_different([S, E, N, D, M, O, R, Y]),
    S != 0,
    M != 0,
    S * 1000 + E * 100 + N * 10 + D + (M * 1000 + O * 100 + R * 10 + E) == M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    label([S, E, N, D, M, O, R, Y])
)

def main():
    for S, E, N, D, M, O, R, Y in --sendmoney(S, E, N, D, M, O, R, Y):
        print(S, E, N, D, M, O, R, Y)      # 9 5 6 7 1 0 8 2
```

Call `main()` after the module has loaded; a query at module top level runs before the module's predicates are registered. A variable that is still constrained when the answer is handed back (for example one that was never labeled) raises `ResidualConstraints`: label it inside the goal, or use the lower-level `solve(goal, module=m, trail=t)` from a plain `.py` file and read its attributes. See [Python Integration](python_integration.md).

### Gotcha: generate-and-test vs constraint-and-label

A common mistake is to call `label` first and then check the arithmetic — this is **generate-and-test** and is extremely slow:

```clausal
:- use_module(library(clpz)).

% SLOW -- generate-and-test: label runs before the equation is known
sendmoney_slow(S, E, N, D, M, O, R, Y) :-
    in_domain([S, E, N, D, M, O, R, Y], 0, 9),
    all_different([S, E, N, D, M, O, R, Y]),
    S #\= 0,
    M #\= 0,
    label([S, E, N, D, M, O, R, Y]),        % labels all 8 vars with no arithmetic constraint
    SEND is S * 1000 + E * 100 + N * 10 + D,
    MORE is M * 1000 + O * 100 + R * 10 + E,
    MONEY is M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    SEND + MORE =:= MONEY.                  % checked after the fact
```

`is/2` is eager arithmetic evaluation, not a constraint — it requires its arguments to already be ground. Putting `label` before the `is` goals forces enumeration of all ~40,000 `all_different` permutations before any pruning from the equation can happen.

The fix is to post the equation as a `#=` constraint *before* `label`:

```clausal
:- use_module(library(clpz)).

% FAST -- constraint-and-label: equation is propagated before any labeling
sendmoney_fast(S, E, N, D, M, O, R, Y) :-
    in_domain([S, E, N, D, M, O, R, Y], 0, 9),
    all_different([S, E, N, D, M, O, R, Y]),
    S #\= 0,
    M #\= 0,
    S * 1000 + E * 100 + N * 10 + D + (M * 1000 + O * 100 + R * 10 + E) #=
        M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    label([S, E, N, D, M, O, R, Y]).        % labels with equation already constraining domains

test("fast") :-
    sendmoney_fast(9, E, N, D, 1, O, R, Y),
    [E, N, D, O, R, Y] == [5, 6, 7, 0, 8, 2].
```

`#=` with unbound variables posts a CLP(ℤ) constraint. The equation is normalised to a `ScalarProductConstraint` and propagated via AC-3 before the first value is tried. This reduces the effective search space from ~40,000 to a handful of candidates, cutting solve time by ~70×.

**Rule of thumb:** use `#=` for arithmetic — it posts constraints that propagate before labeling. Reserve `is/2` for eager evaluation of ground expressions. (In the seam: `==` for the constraint, `eval_/2` for eager evaluation, and `is` with `++` for [Python interop](python_integration.md).)

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

    # label (enumerate solutions)
    for _ in label([x, y], trail):
        print(deref(x), deref(y))
    ```

??? abstract "Interaction with dif/2 and CLP(ℝ)"

    CLP(ℤ), CLP(ℝ), and dif/2 use independent attribute keys (`"fd"`, `"real"`, and `"dif"`). All hooks fire independently when a variable is bound. A variable can have integer, real, and dif constraints simultaneously.

    **FD + Real coexistence:** a variable can carry both an FD domain and a real interval at the same time. The FD domain enforces integrality and domain holes; the real interval handles continuous narrowing. when FD propagation narrows the domain, the real interval is tightened to match. when computing bounds for real constraints, the tightest bounds from both attributes are used. See [CLP(ℝ)](clpr.md) for details on mixed-domain usage.

??? abstract "Compiler integration"

    `ArithEq`/`ArithNeq` and `Lt`/`LtE`/`Gt`/`GtE` goal nodes compile to:

    ```python
    if _fd_eq(l, r, trail):    # #=  (seam ==)
        k_stmts
    if _fd_ne(l, r, trail):    # #\= (seam !=)
        k_stmts
    if _fd_lt(l, r, trail):    # #<  (seam <)
        k_stmts
    ```

    Both sides are compiled with `eval_arith=False` so arithmetic expression trees survive as structural terms for CLP(ℤ) domain arithmetic. The `_fd_*` functions are injected into `base_globals` in both `compile_predicate` and `compile_predicate_trampoline`.

??? info "Test coverage"

    Tests are in `tests/test_clpfd.py`, `tests/test_clpz.py` (CLP(Z) infinite-domain semantics), and `tests/test_phase5_builtins.py` (global constraint tests).

    - **Domain operations**: from_range, contains, min/max, size, singleton, intersection, remove, remove_above/below, values
    - **in_domain**: post domain, unify succeeds/fails, list, narrows existing, singleton binds, empty fails, ground int
    - **label**: single var, two vars (cartesian product), backtracking restores, all ground
    - **equivalent**: same/different atoms, compounds, vars, bound vars
    - **fd_eq/ne/lt/le/gt/ge**: ground values, var-int, var-var, auto-domain, wipeout
    - **Propagation**: lt chain, eq propagation, wipeout, backtracking restores domains
    - **AC-3 fixpoint**: cascaded `<` chain (X<Y<Z, fix Z → X,Y ground without labeling), Ne narrows after domain change
    - **Compiler integration**: ground eq/ne/lt/le/gt/ge, var eq via solve, chained le, ne with label, evaluate unchanged, is unchanged, is-not unchanged
    - **all_different**: basic permutations, ground ok/fail, via solve
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

!!! warning "CLP(B) expressions are seam-only"

    A CLP(B) expression is built from Python's bitwise operators and the
    `BoolEq`/`BoolImpl` classes, which only the seam can write. In a
    `.clausal` file `sat/1` accepts a bare variable (`sat(X)` binds `X = 1`)
    but no expression: `sat(X * Y)` and `sat(X + Y)` raise
    `TypeError: CLP(B): unsupported expression type tuple`, `~X` is a syntax
    error, and `library(clpb)` is not a library the native front end knows.
    The examples in this section are therefore the seam spelling.

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

`BoolEq` and `BoolImpl` are term constructors (Python classes), so a `.seam`
file names them in its import list — `-import_from(clausal.logic.clpb, [BoolEq, BoolImpl])`
— the one place a TitleCase name is declared; bare in a clause they would be
rejected as TitleCase.

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

    when `sat()` is called with an expression containing variables that already have constraints, ALL connected BDDs are conjoined into a single combined BDD. This ensures that multiple `sat()` calls sharing variables form a single constraint network — binding any variable propagates through all constraints in the network.

### Builtins

| Builtin | Arity | Description |
|---|---|---|
| `sat` | 1 | `sat(Expr)` — post Boolean constraint, fail if unsatisfiable |
| `taut` | 2 | `taut(Expr, T)` — T=1 if tautology, T=0 if contradiction, else fail |
| `sat_count` | 2 | `sat_count(Expr, N)` — N is the number of satisfying assignments |
| `bool_labeling` | 1 | `bool_labeling(Vars)` — enumerate 0/1 assignments |

### Syntax examples

**Posting constraints:**
```seam
--8<-- "tests/fixtures/docs/constraints_sigs.txt:syntax_examples"
```

**Half adder:**
```seam
-import_from(clausal.logic.clpb, [BoolEq])

half_adder(X, Y, SUM, CARRY) <- (
    sat(BoolEq(SUM, X ^ Y)),
    sat(BoolEq(CARRY, X & Y))
)
```

**Tautology check (De Morgan's law):**
```seam
--8<-- "tests/fixtures/docs/constraints_sigs.txt:syntax_examples_ex2"
```

**Model counting:**
```seam
--8<-- "tests/fixtures/docs/constraints_sigs.txt:syntax_examples_ex3"
```

**Labeling (enumerate all solutions):**
```seam
solve(X, Y) <- (
    sat(X ^ Y),
    bool_labeling([X, Y])
)
# yields (0,1) and (1,0)
```

**Pigeon-hole (unsatisfiable):**
```seam
pigeon_hole() <- (
    sat(P11 | P12),
    sat(P21 | P22),
    sat(P31 | P32),
    sat(~(P11 & P21)),
    sat(~(P11 & P31)),
    sat(~(P21 & P31)),
    sat(~(P12 & P22)),
    sat(~(P12 & P32)),
    sat(~(P22 & P32)),
    bool_labeling([P11, P12, P21, P22, P31, P32])
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
    
    # label (enumerate solutions)
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

    **Important:** CLP(B) variables are constrained to `0`/`1` (integers), not Python booleans (`True`/`False`). Booleans are explicitly rejected by CLP(ℝ) and CLP(ℤ) — they are distinct types in Clausal Prolog's constraint system.

??? info "Test coverage"

    Tests are in `tests/test_clpb.py`.

    - **BDDNode**: construction, identity equality, hashable, repr
    - **make_node**: reduction rule, unique table sharing, different children
    - **apply**: all terminal cases (and/or/xor/equiv/impl), variable operands, two-variable xor, negate
    - **restrict**: terminal, identity, higher var
    - **_expr_to_bdd**: int/bool constants, invalid int, Var, BitAnd/BitOr/BitXor/Invert, BoolEq/BoolImpl, nested, unsupported type
    - **sat**: ground true/false, single var forced, and/negation/or forcing, contradiction, tautology, sequential conjunction
    - **taut**: tautology (T=1), contradiction (T=0), indeterminate (fail), ground, xor, equiv
    - **sat_count**: xor/and/or/tautology/contradiction counts, single var, three vars
    - **bool_labeling**: single var (2 sols), two vars (4 sols), constrained xor (2 sols), all bound (1 sol)
    - **Attribute hook**: bind constrained var, invalid int, var-var merge, incompatible merge
    - **Trail safety**: backtrack restores state, labeling backtracks cleanly
    - **BoolEq/BoolImpl**: construction, equivalence in sat, implication in sat
    - **Half adder**: complete truth table (4 tests)
    - **Full adder**: 5 input combinations
    - **Pigeon-hole**: 3 pigeons 2 holes → unsatisfiable
    - **circuit equivalence**: De Morgan's law via taut, non-equivalence
    - **Fixture integration**: HalfAdder, FullAdder, PigeonHole via `.seam` file

---

## CLP(ℝ) — Real-domain Constraints

CLP(ℝ) provides constraint logic programming over the reals using interval arithmetic over IEEE doubles with outward rounding. See the dedicated [CLP(ℝ)](clpr.md) page for full documentation including builtins, HC4 propagation internals, and examples.

Quick reference:

### Builtins

| Builtin | Description |
|---|---|
| `in_real(Var)` | Declare real variable with domain `[−∞, +∞]` |
| `in_real(Var, Lo, Hi)` | Declare real variable with domain `[Lo, Hi]` |
| `label_real(Vars)` | Bisect intervals to IEEE float precision |
| `label_real(Vars, Eps)` | Bisect until interval width ≤ Eps |

### Unified dispatch

The same CLP(ℤ) operators (`#=`, `#\=`, `#<`, `#>`, `#=<`, `#>=`, with `library(clpz)` imported) route to CLP(ℝ) automatically when either operand is a `float` literal or a variable declared with `in_real`. No separate operator set or brace syntax is needed. (In the seam the bare `==`, `!=`, `<`, ... dispatch the same way.)

```text
--8<-- "tests/fixtures/docs/constraints_sigs.txt:unified_dispatch"
```

`label_real/2` narrows `X`'s interval to the tolerance; `X` stays a
constrained variable, so `X #> 1.5` and `X #< 1.4` both fail afterwards.

### Cross-domain notes

- **FD + Real coexistence:** a variable can carry both an FD domain and a real interval. The FD domain enforces integrality; the real interval handles continuous narrowing. Both stay in sync.
- **Write a float operand in a real constraint:** `/` inside `#=` is integer division, so `in_real(X), X #= 7 / 2` fails; `in_real(X), X #= 7.0 / 2` narrows `X` to 3.5. (In the seam, `/` is exact, and `in_real(X), X == 7 / 2` raises `TypeError: cannot mix CLP(Q) rational and CLP(R) float in the same constraint`.)
- **Booleans are not numbers:** Python's `True`/`False` are not valid in CLP(ℝ) or CLP(ℤ) expressions (in `.clausal`, `X #= true + 1` is `domain_error(clpz_expression, true)`). Use `0`/`1` if you need numeric values. Booleans belong to CLP(B).
- **Labeling order:** for mixed-domain variables, use `label` (FD) first to fix integer values, then `label_real` for remaining real variables. `label_real` does not enforce integrality.
- **Large integers:** integers beyond 2^53 lose precision when converted to IEEE doubles during interval propagation. Ground integer-integer comparisons are done exactly.

---

*See also: [CLP(B)](clpb.md) — Boolean constraint solving · [CLP(ℝ)](clpr.md) — real-domain interval arithmetic · [Tabling](tabling.md) — memoised search, required for Well-Founded Semantics · [Trealla Prolog Embedding](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-trealla/docs/trealla.md) — fast CLP(Z) via embedded Trealla · [Scryer Prolog Embedding](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scryer/docs/scryer.md) — CLP(Z) with tabling and strict ISO conformance.*
