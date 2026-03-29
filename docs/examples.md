# Examples

Clausal ships with example programs in `clausal/examples/`. Each is a self-contained `.clausal` module demonstrating different language features.

!!! note "Clausal vs Prolog syntax"

    Clausal and Prolog syntax may slightly differ — for example, variables are
    `ALLCAPS`, rules use `<-` instead of `:-`, and lists are Python-style. Keep
    this in mind when comparing with Prolog resources.
    You can also [import Prolog `.pl` files directly](importing_prolog.md) without rewriting them.

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

N-Queens puzzle using permutation-based search: `numlist`, `permutation`, `Safe/1`, and `NoAttack/3` diagonal constraint checking.

*See: [List builtins](builtins.md#lists)*

### hanoi.clausal

Tower of Hanoi: generates the sequence of moves to solve the puzzle for N disks.

---

## Symbolic Computation

### symbolic_diff.clausal

Symbolic differentiation: `Diff(Expr, Var, Deriv)` computes the derivative of an algebraic expression with respect to a variable. Handles constants, variables, addition, multiplication, power, and chain rule.

---

## Constraint Satisfaction

### sudoku.clausal

Classic Sudoku solver using CLP(ℤ) constraints, ported from [Markus Triska's `sudoku.pl`](https://www.metalevel.at/sudoku/). Posts row, column, and 3×3 block `all_different` constraints, then labels. Includes three sample puzzles.

```clausal
Sudoku(ROWS) <- (
    ROWS := [R1, R2, R3, R4, R5, R6, R7, R8, R9],
    flatten(ROWS, VS),
    in_domain(VS, 1, 9),
    maplist(all_different, ROWS),
    transpose(ROWS, COLUMNS),
    maplist(all_different, COLUMNS),
    Blocks(R1, R2, R3), Blocks(R4, R5, R6), Blocks(R7, R8, R9)
)
```

Features: nested [star-list patterns](lists.md) (`[[HEAD, *TAIL], *ROWS]`), builtin predicates as [higher-order](higher_order.md) arguments (`maplist(all_different, ...)`), recursive transpose.

*See: [CLP(ℤ)](constraints.md), [Higher-order predicates](higher_order.md), [Meta-predicates](meta_predicates.md)*

### map_coloring.clausal

Four-color map coloring: given a map of regions and adjacency constraints, finds valid colorings using `forall/2` and `is not` (structural disequality).

*See: [Meta-predicates](meta_predicates.md)*

---

## Higher-Order & Lambdas

### lambdas.clausal

Lambda (goal closure) examples: `ApplyVal`, `AddOne`, `AddZ`, `DoubleVal`, and more. Demonstrates variable capture, multi-arg closures, and conjunction bodies.

*See: [Lambdas](lambdas.md)*

### higher_order.clausal

Higher-order list predicates: `Doubles` (maplist/3), `AllPositive` (maplist/2), `KeepPositive` (include/3), `RemoveNegative` (exclude/3), and `FoldSum` (foldl/4).

*See: [Higher-order predicates](meta_predicates.md)*

### meta_predicates.clausal

Meta-predicate examples: `Squares` (findall/3), `Positives` (bagof/3), `UniqueMembers` (setof/3), `AllPositive` (forall/2).

*See: [Meta-predicates](meta_predicates.md)*

---

## Meta-interpreters

### metainterpreters.clausal

Five meta-interpreters ported from Markus Triska's [A Couple of Meta-interpreters in Prolog](https://www.metalevel.at/acomip/). Object-level programs are represented as lists of `[Head, Body]` clause pairs, where terms use the convention `["functor", arg1, arg2, ...]`. [`copy_term/2`](term_inspection.md) provides fresh variable copies at each resolution step.

**Solve/2** — vanilla list-based meta-interpreter (tail-recursive). Resolves goals against an explicit program:

```clausal
Solve([], _PROGRAM),
Solve([GOAL, *GOALS], PROGRAM) <- (
    MatchClause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    Solve(ALL_GOALS, PROGRAM)
)

MatchClause(GOAL, FRESH_BODY, PROGRAM) <- (
    in_(CLAUSE, PROGRAM),
    copy_term(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
    GOAL is FRESH_HEAD
)
```

**SolveCount/3** — counts inference steps:

```clausal
SolveCount([], _PROGRAM, 0),
SolveCount([GOAL, *GOALS], PROGRAM, COUNT) <- (
    MatchClause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    SolveCount(ALL_GOALS, PROGRAM, SUB_COUNT),
    COUNT == SUB_COUNT + 1
)
```

**SolveLimit/3** — depth-limited search. Each clause resolution consumes one unit of depth:

```clausal
SolveLimit([], _PROGRAM, _MAX),
SolveLimit([GOAL, *GOALS], PROGRAM, MAX) <- (
    MAX > 0,
    MAX1 == MAX - 1,
    MatchClause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    SolveLimit(ALL_GOALS, PROGRAM, MAX1)
)
```

**SolveIterativeDeepening/2** — complete search via increasing depth limits. Finds solutions even in cyclic programs where naive DFS diverges:

```clausal
SolveIterativeDeepening(GOALS, PROGRAM) <- (
    between(0, 1000, DEPTH),
    SolveLimit(GOALS, PROGRAM, DEPTH)
)
```

**SolveTree/3** — builds explicit proof trees. Each node is `[Goal, [subtrees...]]`:

```clausal
SolveTree([], _PROGRAM, []),
SolveTree([GOAL, *GOALS], PROGRAM, [[GOAL, BODY_TREE], *GOALS_TREE]) <- (
    MatchClause(GOAL, BODY, PROGRAM),
    SolveTree(BODY, PROGRAM, BODY_TREE),
    SolveTree(GOALS, PROGRAM, GOALS_TREE)
)
```

Three sample programs are included: natural numbers (`NatnumProgram`), an acyclic graph (`GraphProgram`), and a cyclic graph (`CyclicProgram`) that demonstrates iterative deepening's advantage over plain DFS.

*See: [Meta-Interpreters tutorial](metainterpreters.md), [Builtins](builtins.md) (copy_term, in_, append, between)*

---

## DCGs

### dcg_state.clausal

DCG state threading patterns: counter (`inc`, `count3`), tree leaf counting (`count_leaves`, `num_leaves`), and accumulator (`push`, `push_all`, `collect_items`).

*See: [DCGs](dcg.md)*

---

## Running Examples

Add test predicates to any example file, then run with pytest:

```clausal
# skip
# in_ your .clausal file
Test("fib 10") <- Fib(10, 55)
```

Or query from [Python](python_integration.md):

```python
from clausal import Var
from clausal.examples.fibonacci import Fib

for trail in Fib(10, F := Var()):
    print(F.value)  # 55
```
