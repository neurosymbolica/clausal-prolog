# CLP(B) — Boolean Constraints

CLP(B) provides constraint logic programming over Booleans, enabling SAT solving, tautology checking, model counting, and combinatorial problems. The implementation follows Markus Triska's design using reduced ordered BDDs (Binary Decision Diagrams).

The implementation lives in `clausal/logic/clpb.py`.

!!! note
    For CLP(ℤ) (integer constraints over all integers) and dif/2 (disequality), see [Constraints](constraints.md).

---

## Operator Syntax

Python's bitwise operators express Boolean formulas:

| Operator | Meaning |
|---|---|
| `X & Y` | AND |
| `X \| Y` | OR |
| `X ^ Y` | XOR |
| `~X` | NOT |
| `BoolEq(X, Y)` | Equivalence (iff) |
| `BoolImpl(X, Y)` | Implication (X → Y) |

Variables in CLP(B) are constrained to values 0 (false) and 1 (true).

---

## Builtins

| Builtin | Arity | Description |
|---|---|---|
| `sat` | 1 | `sat(Expr)` — post Boolean constraint; fail if unsatisfiable |
| `taut` | 2 | `taut(Expr, T)` — T=1 if tautology, T=0 if contradiction, else fail |
| `sat_count` | 2 | `sat_count(Expr, N)` — N is the number of satisfying assignments |
| `bool_labeling` | 1 | `bool_labeling(Vars)` — enumerate 0/1 assignments |

### sat/1

Posts a Boolean constraint. Fails immediately if the formula is unsatisfiable:

```clausal
--8<-- "tests/fixtures/docs/clpb_sigs.txt:sat_1"
```

Multiple `sat` calls on shared variables build a single constraint network:

```clausal
--8<-- "tests/fixtures/docs/clpb_sigs.txt:sat_1_ex2"
```

### taut/2

Tests if a formula is a tautology, contradiction, or neither:

```clausal
--8<-- "tests/fixtures/docs/clpb_sigs.txt:taut_2"
```

### sat_count/2

Counts the number of satisfying assignments:

```clausal
--8<-- "tests/fixtures/docs/clpb_sigs.txt:sat_count_2"
```

### bool_labeling/1

Enumerates all 0/1 assignments for a list of variables:

```clausal
solve(X, Y) <- (
    sat(X ^ Y),
    bool_labeling([X, Y])
)
# yields (0, 1) and (1, 0)
```

---

??? example "Examples"

    ### Half Adder

    ```clausal
    --8<-- "tests/fixtures/docs/clpb_sigs.txt:half_adder"
    ```

    ### Pigeon-Hole (unsatisfiable)

    3 pigeons in 2 holes — no solution exists:

    ```clausal
    --8<-- "tests/fixtures/docs/clpb_sigs.txt:pigeon_hole"
    ```

    ### circuit Equivalence

    Verify De Morgan's law via tautology check:

    ```clausal
    --8<-- "tests/fixtures/docs/clpb_sigs.txt:circuit_equivalence"
    ```

    ---

## BDD Internals

CLP(B) uses reduced ordered Binary Decision Diagrams:

- **Terminal nodes**: `BDD_TRUE = 1`, `BDD_FALSE = 0`
- **Internal nodes**: `BDDNode(var_id, high, low)` — `high` is the child when var=1, `low` when var=0
- **Per-variable unique tables**: each variable stores its own node lookup dict (Triska/Knuth technique)
- **Reduction rule**: if `high == low`, the node is skipped
- **Variable ordering**: static first-appearance order (no dynamic reordering)

### BoolState

Each constrained variable stores a `BoolState` as an attributed-variable attribute under the key `"clpb"`:

- `sat_expr` — original Boolean formula (for rebuild on aliasing)
- `bdd` — current BDD
- `root_var` — shared root variable linking all vars in the constraint network

Trail safety: every state change creates a new `BoolState` via `put_attr`, automatically restored on backtrack.

### Connected-Component Merging

when `sat()` is called with variables that already have constraints, all connected BDDs are conjoined. This ensures multiple `sat` calls sharing variables form a single constraint network.

---

??? example "Python API"

    ```python
    from clausal.logic.variables import Var, Trail, deref, unify
    from clausal.logic.clpb import sat, taut, sat_count, bool_labeling, BoolEq
    from clausal.pythonic_ast.nodes import BitAnd, BitOr, BitXor, Invert
    
    trail = Trail()
    x, y = Var(), Var()
    
    # Post constraint: X XOR Y
    sat(BitXor(left=x, right=y), trail)
    
    # Enumerate solutions
    for _ in bool_labeling([x, y], trail):
        print(deref(x), deref(y))   # 0 1, then 1 0
    
    # Tautology check
    t = Var()
    taut(BitOr(left=x, right=Invert(operand=x)), t, Trail())
    # t = 1
    
    # Model counting
    n = Var()
    sat_count(BitXor(left=Var(), right=Var()), n, Trail())
    # n = 2
    ```

    ---

## Interaction with Other Constraints

CLP(B) uses attribute key `"clpb"`, independent of [CLP(ℤ)](constraints.md) (`"fd"`), [CLP(ℝ)](clpr.md) (`"real"`), and dif/2 (`"dif"`). All hooks fire independently when a variable is bound.

CLP(B) variables are constrained to `0`/`1` (integers), not Python booleans (`True`/`False`). Booleans are explicitly rejected by CLP(ℝ) and CLP(ℤ) — they are distinct types in Clausal's constraint system. If you need to bridge CLP(B) with numeric constraints, bind via `0`/`1`.

---

??? info "Test coverage"

    Tests are in `tests/test_clpb.py` (87 tests).

    - **BDD operations**: make_node, apply, restrict, _expr_to_bdd
    - **sat**: forcing, contradiction, tautology, sequential conjunction
    - **taut**: tautology/contradiction/indeterminate
    - **sat_count**: various formulas
    - **bool_labeling**: unconstrained, constrained
    - **Attribute hook**: bind, merge, incompatible
    - **Trail safety**: backtrack, labeling
    - **Half adder**: complete truth table
    - **Full adder**: 5 input combinations
    - **Pigeon-hole**: unsatisfiable
    - **circuit equivalence**: De Morgan's law

---

*See also: [Constraints](constraints.md) — `dif/2` and CLP(ℤ) for integer constraints · [CLP(ℝ)](clpr.md) — real-domain constraint solving.*
