# CLP(B) — Boolean Constraints

CLP(B) provides constraint logic programming over Booleans, enabling SAT solving, tautology checking, model counting, and combinatorial problems. The implementation follows Markus Triska's design using reduced ordered BDDs (Binary Decision Diagrams).

The implementation lives in `clausal/logic/clpb.py` (V3-4).

!!! note
    For CLP(FD) (finite-domain integer constraints) and Dif/2 (disequality), see [Constraints](constraints.md).

---

## Operator Syntax

Python's bitwise operators express Boolean formulas:

| Operator | Meaning |
|---|---|
| `X_ & Y_` | AND |
| `X_ \| Y_` | OR |
| `X_ ^ Y_` | XOR |
| `~X_` | NOT |
| `BoolEq(X_, Y_)` | Equivalence (iff) |
| `BoolImpl(X_, Y_)` | Implication (X → Y) |

Variables in CLP(B) are constrained to values 0 (false) and 1 (true).

---

## Builtins

| Builtin | Arity | Description |
|---|---|---|
| `Sat` | 1 | `Sat(Expr)` — post Boolean constraint; fail if unsatisfiable |
| `Taut` | 2 | `Taut(Expr, T)` — T=1 if tautology, T=0 if contradiction, else fail |
| `SatCount` | 2 | `SatCount(Expr, N)` — N is the number of satisfying assignments |
| `BoolLabeling` | 1 | `BoolLabeling(Vars)` — enumerate 0/1 assignments |

### Sat/1

Posts a Boolean constraint. Fails immediately if the formula is unsatisfiable:

```
Sat(X_ & Y_)                # both must be 1
Sat(X_ | Y_)                # at least one must be 1
Sat(~X_)                     # X must be 0
Sat(BoolEq(X_, Y_))         # X ↔ Y (equivalence)
Sat(BoolImpl(X_, Y_))       # X → Y (implication)
```

Multiple `Sat` calls on shared variables build a single constraint network:

```
Sat(X_ | Y_), Sat(~X_ | Z_), Sat(Y_ & Z_)
```

### Taut/2

Tests if a formula is a tautology, contradiction, or neither:

```
# De Morgan's law — tautology
Taut(BoolEq(~(X_ & Y_), ~X_ | ~Y_), T_)   # T_ = 1

# Contradiction
Taut(X_ & ~X_, T_)                          # T_ = 0

# Neither (indeterminate) — Taut fails
Taut(X_ | Y_, T_)                            # fails
```

### SatCount/2

Counts the number of satisfying assignments:

```
SatCount(X_ ^ Y_, N_)       # N_ = 2  (XOR has 2 solutions)
SatCount(X_ & Y_, N_)       # N_ = 1  (AND has 1 solution)
SatCount(X_ | Y_, N_)       # N_ = 3  (OR has 3 solutions)
```

### BoolLabeling/1

Enumerates all 0/1 assignments for a list of variables:

```
solve(X_, Y_) <- (
    Sat(X_ ^ Y_)
    and BoolLabeling([X_, Y_])
)
# yields (0, 1) and (1, 0)
```

---

## Examples

### Half Adder

```
HalfAdder(X_, Y_, Sum_, Carry_) <- (
    Sat(BoolEq(Sum_, X_ ^ Y_))
    and Sat(BoolEq(Carry_, X_ & Y_))
)
```

### Pigeon-Hole (unsatisfiable)

3 pigeons in 2 holes — no solution exists:

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
# no solutions
```

### Circuit Equivalence

Verify De Morgan's law via tautology check:

```
Taut(BoolEq(~(X_ & Y_), ~X_ | ~Y_), T_)   # T_ = 1
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

When `Sat()` is called with variables that already have constraints, all connected BDDs are conjoined. This ensures multiple `Sat` calls sharing variables form a single constraint network.

---

## Python API

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

CLP(B) uses attribute key `"clpb"`, independent of CLP(FD) (`"fd"`) and dif/2 (`"dif"`). All three hooks fire independently when a variable is bound.

---

## Test Coverage

Tests are in `tests/test_clpb.py` (87 tests).

- **BDD operations**: make_node, apply, restrict, _expr_to_bdd
- **Sat**: forcing, contradiction, tautology, sequential conjunction
- **Taut**: tautology/contradiction/indeterminate
- **SatCount**: various formulas
- **BoolLabeling**: unconstrained, constrained
- **Attribute hook**: bind, merge, incompatible
- **Trail safety**: backtrack, labeling
- **Half adder**: complete truth table
- **Full adder**: 5 input combinations
- **Pigeon-hole**: unsatisfiable
- **Circuit equivalence**: De Morgan's law
