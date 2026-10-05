# Examples

Clausal Prolog ships with example programs in `clausal/examples/`. Each is a self-contained seam (`.seam`) module demonstrating different language features.

!!! note "Seam vs Prolog syntax"

    Seam and Prolog syntax may slightly differ — for example, variables are
    `ALLCAPS`, rules use `<-` instead of `:-`, and lists are Python-style. Keep
    this in mind when comparing with Prolog resources.
    [Clausal Prolog](clausal_prolog.md) (`.clausal`) uses ISO Prolog syntax instead.
    You can also [import Prolog `.pl` files directly](importing_prolog.md) without rewriting them.

---

## Basics

### fibonacci.seam

Classic Fibonacci sequence with pattern-matching base cases:

```seam
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:fib_definition"
```

*See: [Tabling](tabling.md), [Arithmetic builtins](builtins.md#arithmetic)*

### peano.seam

Peano arithmetic: natural number representation, addition, multiplication, and ordering via structural recursion.

### graph.seam

Graph traversal: `path/3` (path finding with cycle detection), `reachable/2`, and `connected/2` over edge facts.

---

## Algorithms

### sorting.seam

Two sorting algorithms:

- `naive_sort/2` — permutation sort (generate-and-test)
- `qsort/2` — quicksort with partition

*See: [List builtins](builtins.md#lists)*

### nqueens.seam

N-Queens puzzle using permutation-based search: `numlist`, `permutation`, `safe/1`, and `no_attack/3` diagonal constraint checking.

*See: [List builtins](builtins.md#lists)*

### hanoi.seam

Tower of Hanoi: generates the sequence of moves to solve the puzzle for N disks.

---

## Symbolic Computation

### symbolic_diff.seam

Symbolic differentiation: `diff(EXPR, VAR, DERIV)` computes the derivative of an algebraic expression with respect to a variable. Handles constants, variables, addition, multiplication, power, and chain rule.

---

## Constraint Satisfaction

### sudoku.seam

Classic Sudoku solver using CLP(ℤ) constraints, ported from [Markus Triska's `sudoku.pl`](https://www.metalevel.at/sudoku/). Posts row, column, and 3×3 block `all_different` constraints, then labels. Includes three sample puzzles.

```seam
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

### map_coloring.seam

Four-color map coloring: given a map of regions and adjacency constraints, finds valid colorings using `forall/2` and `is not` (structural disequality).

*See: [Meta-predicates](meta_predicates.md)*

---

## Higher-Order & Lambdas

### lambdas.seam

Lambda (goal closure) examples: `apply_val`, `add_one`, `add_z`, `double_val`, and more. Demonstrates variable capture, multi-arg closures, and conjunction bodies.

*See: [Lambdas](lambdas.md)*

### higher_order.seam

Higher-order list predicates: `doubles` (maplist/3), `all_positive` (maplist/2), `keep_positive` (include/3), `remove_negative` (exclude/3), and `sum_list_fold` (foldl/4).

*See: [Higher-order predicates](meta_predicates.md)*

### meta_predicates.seam

Meta-predicate examples: `squares` (findall/3), `bag_positives` (bagof/3), `unique_members` (setof/3), `all_positive` (forall/2).

*See: [Meta-predicates](meta_predicates.md)*

---

## Meta-interpreters

### metainterpreters.seam

Five meta-interpreters ported from Markus Triska's [A Couple of Meta-interpreters in Prolog](https://www.metalevel.at/acomip/). Object-level programs are represented as lists of `[HEAD, BODY]` clause pairs of ordinary terms (`[natnum(succ(X)), [natnum(X)]]`). [`copy_term/2`](term_inspection.md) provides fresh variable copies at each resolution step.

**solve/2** — vanilla list-based meta-interpreter (tail-recursive). Resolves goals against an explicit program:

```seam
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

**solve_count/3** — counts inference steps:

```seam
solve_count([], _PROGRAM_UNUSED, 0),
solve_count([GOAL, *GOALS], PROGRAM, COUNT) <- (
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve_count(ALL_GOALS, PROGRAM, SUB_COUNT),
    COUNT == SUB_COUNT + 1
)
```

**solve_limit/3** — depth-limited search. Each clause resolution consumes one unit of depth:

```seam
solve_limit([], _PROGRAM_UNUSED, _MAX_UNUSED),
solve_limit([GOAL, *GOALS], PROGRAM, MAX) <- (
    MAX > 0,
    MAX1 == MAX - 1,
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve_limit(ALL_GOALS, PROGRAM, MAX1)
)
```

**solve_iterative_deepening/2** — complete search via increasing depth limits. Finds solutions even in cyclic programs where naive DFS diverges:

```seam
solve_iterative_deepening(GOALS, PROGRAM) <- (
    between(0, 1000, DEPTH),
    solve_limit(GOALS, PROGRAM, DEPTH)
)
```

**solve_tree/3** — builds explicit proof trees. Each node is `[Goal, [subtrees...]]`:

```seam
solve_tree([], _PROGRAM_UNUSED, []),
solve_tree([GOAL, *GOALS], PROGRAM, [[GOAL, BODY_TREE], *GOALS_TREE]) <- (
    match_clause(GOAL, BODY, PROGRAM),
    solve_tree(BODY, PROGRAM, BODY_TREE),
    solve_tree(GOALS, PROGRAM, GOALS_TREE)
)
```

Three sample programs are included: natural numbers (`natnum_program`), an acyclic graph (`graph_program`), and a cyclic graph (`cyclic_program`) that demonstrates iterative deepening's advantage over plain DFS.

*See: [Meta-Interpreters tutorial](metainterpreters.md), [Builtins](builtins.md) (copy_term, in_, append, between)*

---

## DCGs

### dcg_state.seam

DCG state threading patterns: counter (`inc`, `count3`), tree leaf counting (`count_leaves`, `num_leaves`), and accumulator (`push`, `push_all`, `collect_items`).

*See: [DCGs](dcg.md)*

---

## Running Examples

Add test predicates to any example file, then run with pytest:

```seam
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:fib_test"
```

Or query from [Python](python_integration.md). In a `.seam`
file, write the goal in [goal position](python_integration.md#goal-position-if-goal-for-in-goal):

```python
# fib_report.seam
-import_module(clausal.examples.fibonacci)

def fib(n):
    for F in --clausal.examples.fibonacci.fib(++n, F):
        return F
```

`import clausal, fib_report; fib_report.fib(10)` is `55`. From a plain `.py`
file, build the goal cell and run it against the module:

```python
from clausal import Var, solve
from clausal.examples import fibonacci

for trail in solve(("fib", 10, F := Var()), module=fibonacci):
    print(F.value)  # 55
```
