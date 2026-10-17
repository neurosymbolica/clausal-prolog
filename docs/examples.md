# Examples

Clausal Prolog ships with example programs in `clausal/examples/`. Each is a self-contained module demonstrating different language features. The files themselves are written in the [seam](syntax.md) (`.seam`), Clausal's Python-syntax surface; the excerpts on this page are shown in [Clausal Prolog](clausal_prolog.md) (`.clausal`, ISO Prolog syntax); each one loads as written, and most carry a test.

!!! note "Using the examples from Clausal Prolog"

    A `.clausal` file can import any of these modules, because they are
    Python-free seam modules: `:- use_module(clausal/examples/fibonacci, [fib/2]).`
    (see [Running Examples](#running-examples)). You can also
    [import Prolog `.pl` files directly](importing_prolog.md) without rewriting them.

---

## Basics

### fibonacci.seam

Classic Fibonacci sequence with pattern-matching base cases:

```clausal
:- use_module(library(clpz)).

fib(0, 0).
fib(1, 1).
fib(N, F) :-
    N #> 1,
    N1 #= N - 1,
    N2 #= N - 2,
    fib(N1, F1),
    fib(N2, F2),
    F #= F1 + F2.

test("fib 10") :-
    fib(10, 55).
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

```clausal
:- use_module(library(clpz)).

sudoku(ROWS) :-
    ROWS = [R1, R2, R3, R4, R5, R6, R7, R8, R9],
    flatten(ROWS, VS),
    VS ins 1..9,
    maplist(all_different, ROWS),
    transpose(ROWS, COLUMNS),
    maplist(all_different, COLUMNS),
    blocks(R1, R2, R3),
    blocks(R4, R5, R6),
    blocks(R7, R8, R9).

blocks([], [], []).
blocks([N1, N2, N3|NS1], [N4, N5, N6|NS2], [N7, N8, N9|NS3]) :-
    all_different([N1, N2, N3, N4, N5, N6, N7, N8, N9]),
    blocks(NS1, NS2, NS3).

transpose([], []).
transpose([[]|_], []).
transpose(MATRIX, [HEADS|REST_COLS]) :-
    extract_column(MATRIX, HEADS, TAILS),
    transpose(TAILS, REST_COLS).

extract_column([], [], []).
extract_column([[HEAD|TAIL]|ROWS], [HEAD|REST_HEADS], [TAIL|REST_TAILS]) :-
    extract_column(ROWS, REST_HEADS, REST_TAILS).

problem(1, [[1,_,_,8,_,4,_,_,_],
            [_,2,_,_,_,_,4,5,6],
            [_,_,3,2,_,5,_,_,_],
            [_,_,_,4,_,_,8,_,5],
            [7,8,9,_,5,_,_,_,_],
            [_,_,_,_,_,6,2,_,3],
            [8,_,1,_,_,_,7,_,_],
            [_,_,_,1,2,3,_,8,_],
            [2,_,5,_,_,_,_,_,9]]).

test("problem 1") :-
    problem(1, ROWS),
    sudoku(ROWS),
    flatten(ROWS, VS),
    label(VS),
    ROWS = [FIRST|_],
    FIRST == [1, 5, 6, 8, 9, 4, 3, 2, 7].
```

The excerpt also includes the file's `blocks/3`, its recursive `transpose/2`, and the first sample puzzle. Features: nested [list patterns](lists.md) (`[[HEAD|TAIL]|ROWS]`), builtin predicates as [higher-order](higher_order.md) arguments (`maplist(all_different, ...)`), recursive transpose.

*See: [CLP(ℤ)](constraints.md), [Higher-order predicates](higher_order.md), [Meta-predicates](meta_predicates.md)*

### map_coloring.seam

Four-color map coloring: given a map of regions and adjacency constraints, finds valid colorings using `forall/2` and disequality (`X is not Y`, the seam's spelling of [`dif/2`](constraints.md)).

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

```clausal
solve([], _PROGRAM_UNUSED).

solve([GOAL|GOALS], PROGRAM) :-
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve(ALL_GOALS, PROGRAM).

match_clause(GOAL, FRESH_BODY, PROGRAM) :-
    in_(CLAUSE, PROGRAM),
    copy_term(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
    GOAL = FRESH_HEAD.

natnum_program([
    [natnum(0), []],
    [natnum(succ(X)), [natnum(X)]]
]).

test("solve natnum(succ(succ(0)))") :-
    natnum_program(P),
    solve([natnum(succ(succ(0)))], P).
```

The blocks below reuse `match_clause/3` from this one.

**solve_count/3** — counts inference steps:

```clausal
:- use_module(library(clpz)).

solve_count([], _PROGRAM_UNUSED, 0).

solve_count([GOAL|GOALS], PROGRAM, COUNT) :-
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve_count(ALL_GOALS, PROGRAM, SUB_COUNT),
    COUNT #= SUB_COUNT + 1.
```

**solve_limit/3** — depth-limited search. Each clause resolution consumes one unit of depth:

```clausal
:- use_module(library(clpz)).

solve_limit([], _PROGRAM_UNUSED, _MAX_UNUSED).

solve_limit([GOAL|GOALS], PROGRAM, MAX) :-
    MAX #> 0,
    MAX1 #= MAX - 1,
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve_limit(ALL_GOALS, PROGRAM, MAX1).
```

**solve_iterative_deepening/2** — complete search via increasing depth limits. Finds solutions even in cyclic programs where naive DFS diverges:

```clausal
solve_iterative_deepening(GOALS, PROGRAM) :-
    between(0, 1000, DEPTH),
    solve_limit(GOALS, PROGRAM, DEPTH).
```

**solve_tree/3** — builds explicit proof trees. Each node is `[Goal, [subtrees...]]`:

```clausal
solve_tree([], _PROGRAM_UNUSED, []).

solve_tree([GOAL|GOALS], PROGRAM, [[GOAL, BODY_TREE]|GOALS_TREE]) :-
    match_clause(GOAL, BODY, PROGRAM),
    solve_tree(BODY, PROGRAM, BODY_TREE),
    solve_tree(GOALS, PROGRAM, GOALS_TREE).
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

Write test predicates in a `.clausal` file that imports the example, then run it with pytest (see [Testing](testing.md)):

```clausal
% fib_test.clausal
:- use_module(clausal/examples/fibonacci, [fib/2]).

test("fib 10") :-
    fib(10, 55).
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
