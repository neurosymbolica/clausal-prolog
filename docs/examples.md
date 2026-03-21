# Examples

Clausal ships with example programs in `clausal/examples/`. Each is a self-contained `.clausal` module demonstrating different language features.

---

## Basics

### fibonacci.clausal

Classic Fibonacci sequence with pattern-matching base cases:

```clausal
# skip
Fib(N=0, F=0),
Fib(N=1, F=1),
Fib(N, F) <- (N > 1, ...)
```

*See: [Tabling](tabling.md), [Arithmetic builtins](builtins.md#arithmetic)*

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

*See: [List builtins](builtins.md#lists)*

### nqueens.clausal

N-Queens puzzle using CLP(FD) constraints: `InDomain`, `AllDifferent`, and diagonal constraint checking.

*See: [CLP(FD) constraints](constraints.md)*

### hanoi.clausal

Tower of Hanoi: generates the sequence of moves to solve the puzzle for N disks.

---

## Symbolic Computation

### symbolic_diff.clausal

Symbolic differentiation: `Diff(Expr, Var, Deriv)` computes the derivative of an algebraic expression with respect to a variable. Handles constants, variables, addition, multiplication, power, and chain rule.

---

## Constraint Satisfaction

### sudoku.clausal

Classic Sudoku solver using CLP(FD) constraints, ported from [Markus Triska's `sudoku.pl`](https://www.metalevel.at/sudoku/). Posts row, column, and 3×3 block `AllDifferent` constraints, then labels. Includes three sample puzzles.

```clausal
Sudoku(ROWS) <- (
    ROWS := [R1, R2, R3, R4, R5, R6, R7, R8, R9],
    Flatten(ROWS, VS),
    InDomain(VS, 1, 9),
    MapList(AllDifferent, ROWS),
    Transpose(ROWS, COLUMNS),
    MapList(AllDifferent, COLUMNS),
    Blocks(R1, R2, R3), Blocks(R4, R5, R6), Blocks(R7, R8, R9)
)
```

Features: nested star-list patterns (`[[HEAD, *TAIL], *ROWS]`), builtin predicates as higher-order arguments (`MapList(AllDifferent, ...)`), recursive transpose.

*See: [CLP(FD)](constraints.md), [Higher-order predicates](meta_predicates.md)*

### map_coloring.clausal

Four-color map coloring: given a map of regions and adjacency constraints, finds valid colorings using `Dif/2` (disequality constraints).

*See: [Dif/2](constraints.md#dif2)*

---

## Higher-Order & Lambdas

### lambdas.clausal

Lambda (goal closure) examples: `ApplyVal`, `AddOne`, `AddZ`, `DoubleVal`, and more. Demonstrates variable capture, multi-arg closures, and conjunction bodies.

*See: [Lambdas](lambdas.md)*

### higher_order.clausal

Higher-order list predicates: `Doubles` (MapList/3), `AllPositive` (MapList/2), `KeepPositive` (Filter/3), `RemoveNegative` (Exclude/3), and `FoldSum` (FoldLeft/4).

*See: [Higher-order predicates](meta_predicates.md)*

### meta_predicates.clausal

Meta-predicate examples: `Squares` (FindAll/3), `Positives` (BagOf/3), `UniqueMembers` (SetOf/3), `AllPositive` (ForAll/2).

*See: [Meta-predicates](meta_predicates.md)*

---

## DCGs

### dcg_state.clausal

DCG state threading patterns: counter (`inc`, `count3`), tree leaf counting (`count_leaves`, `num_leaves`), and accumulator (`push`, `push_all`, `collect_items`).

*See: [DCGs](dcg.md)*

---

## Running Examples

Add test predicates to any example file, then run with pytest:

```clausal
# In your .clausal file
test("fib 10") <- fib(10, 55)
```

Or query from Python:

```python
import clausal
from clausal.examples import fibonacci

for s in clausal.query(fibonacci.fib(10, F)):
    print(s[F])  # 55
```
