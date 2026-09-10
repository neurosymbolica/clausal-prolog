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
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:fib_definition"
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
sudoku(ROWS) <- (
    ROWS is [R1, R2, R3, R4, R5, R6, R7, R8, R9],
    flatten(ROWS, VS),
    in_domain(VS, 1, 9),
    maplist(all_different, ROWS),
    transpose(ROWS, COLUMNS),
    maplist(all_different, COLUMNS),
    blocks(R1, R2, R3), blocks(R4, R5, R6), blocks(R7, R8, R9)
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
solve([], _PROGRAM_UNUSED),
solve([GOAL, *GOALS], PROGRAM) <- (
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve(ALL_GOALS, PROGRAM)
)

match_clause(GOAL, FRESH_BODY, PROGRAM) <- (
    in_(CLAUSE, PROGRAM),
    copy_term(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
    GOAL is FRESH_HEAD
)
```

**SolveCount/3** — counts inference steps:

```clausal
solve_count([], _PROGRAM_UNUSED, 0),
solve_count([GOAL, *GOALS], PROGRAM, COUNT) <- (
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve_count(ALL_GOALS, PROGRAM, SUB_COUNT),
    COUNT == SUB_COUNT + 1
)
```

**SolveLimit/3** — depth-limited search. Each clause resolution consumes one unit of depth:

```clausal
solve_limit([], _PROGRAM_UNUSED, _MAX_UNUSED),
solve_limit([GOAL, *GOALS], PROGRAM, MAX) <- (
    MAX > 0,
    MAX1 == MAX - 1,
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve_limit(ALL_GOALS, PROGRAM, MAX1)
)
```

**SolveIterativeDeepening/2** — complete search via increasing depth limits. Finds solutions even in cyclic programs where naive DFS diverges:

```clausal
solve_iterative_deepening(GOALS, PROGRAM) <- (
    between(0, 1000, DEPTH),
    solve_limit(GOALS, PROGRAM, DEPTH)
)
```

**SolveTree/3** — builds explicit proof trees. Each node is `[Goal, [subtrees...]]`:

```clausal
solve_tree([], _PROGRAM_UNUSED, []),
solve_tree([GOAL, *GOALS], PROGRAM, [[GOAL, BODY_TREE], *GOALS_TREE]) <- (
    match_clause(GOAL, BODY, PROGRAM),
    solve_tree(BODY, PROGRAM, BODY_TREE),
    solve_tree(GOALS, PROGRAM, GOALS_TREE)
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
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:fib_test"
```

Or query from [Python](python_integration.md):

```python
from clausal import Var
from clausal.examples.fibonacci import Fib

for trail in Fib(10, F := Var()):
    print(F.value)  # 55
```
