# Examples

Clausal ships with example programs in `clausal/examples/`. Each is a self-contained `.clausal` module demonstrating different language features.

---

## Basics

### fibonacci.clausal

Classic Fibonacci sequence with pattern-matching base cases:

```
Fib(N=0, F=0),
Fib(N=1, F=1),
Fib(N_, F_) <- (N_ > 1 and ...)
```

### peano.clausal

Peano arithmetic: natural number representation, addition, multiplication, and ordering via structural recursion.

### graph.clausal

Graph traversal: `Path/3` (path finding with cycle detection), `Reachable/2`, and `Connected/2` over edge facts.

---

## Algorithms

### sorting.clausal

Two sorting algorithms:

- `NaiveSort/2` — permutation sort (generate-and-test)
- `Qsort/2` — quicksort with partition

### nqueens.clausal

N-Queens puzzle using CLP(FD) constraints: `InDomain`, `AllDifferent`, and diagonal constraint checking.

### hanoi.clausal

Tower of Hanoi: generates the sequence of moves to solve the puzzle for N disks.

---

## Symbolic Computation

### symbolic_diff.clausal

Symbolic differentiation: `Diff(Expr, Var, Deriv)` computes the derivative of an algebraic expression with respect to a variable. Handles constants, variables, addition, multiplication, power, and chain rule.

---

## Constraint Satisfaction

### map_coloring.clausal

Four-color map coloring: given a map of regions and adjacency constraints, finds valid colorings using `Dif/2` (disequality constraints).

---

## Higher-Order & Lambdas

### lambdas.clausal

Lambda (goal closure) examples: `ApplyVal`, `AddOne`, `AddZ`, `DoubleVal`, and more. Demonstrates variable capture, multi-arg closures, and conjunction bodies.

### higher_order.clausal

Higher-order list predicates: `Doubles` (MapList/3), `AllPositive` (MapList/2), `KeepPositive` (Filter/3), `RemoveNegative` (Exclude/3), and `FoldSum` (FoldLeft/4).

### meta_predicates.clausal

Meta-predicate examples: `Squares` (FindAll/3), `Positives` (BagOf/3), `UniqueMembers` (SetOf/3), `AllPositive` (ForAll/2).

---

## DCGs

### dcg_state.clausal

DCG state threading patterns: counter (`inc`, `count3`), tree leaf counting (`count_leaves`, `num_leaves`), and accumulator (`push`, `push_all`, `collect_items`).

---

## Running Examples

Import any example as a module:

```python
import clausal.examples.fibonacci as fib

from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

N, F = Var(), Var()
for trail in call("Fib", 10, F, module=fib.__dict__["$module"]):
    print(deref(F))  # 55
```

Or use the query API:

```python
from clausal.logic.solve import query
from clausal.logic.variables import Var
from clausal.terms import Call, LoadName

N, F = Var(), Var()
goal = Call(LoadName("Fib"), (N, F))
for bindings in query(goal, {"N": N, "F": F}, module=fib.__dict__["$module"]):
    print(bindings)
```
