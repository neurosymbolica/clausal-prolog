# Meta-Interpreters

A *meta-interpreter* is an interpreter written in the same language it interprets. In logic programming, this means a Prolog (or Clausal) program that evaluates another logic program represented as data. Meta-interpreters are a classical demonstration of logic programming's homoiconicity: programs and data share the same representation.

This page follows the structure of Markus Triska's [A Couple of Meta-Interpreters in Prolog](https://www.metalevel.at/acomip/), adapting the examples to Clausal syntax.

!!! note "Clausal vs Prolog syntax"

    Clausal and Prolog syntax may slightly differ — for example, variables are
    `ALLCAPS`, rules use `<-` instead of `:-`, and [lists](lists.md) are Python-style. Keep
    this in mind when comparing with Prolog resources.

The full source is in `clausal/examples/metainterpreters.seam`.

---

## Object Programs as Data

The key idea is to represent an *object-level* program — the program being interpreted — as a list of clauses, where each clause is a pair `[Head, Body]`. `Head` is a term, `Body` is a list of goals (also terms).

In Clausal, object-level terms are ordinary compound terms — cells such as `('natnum', ('succ', 0))`. We declare the object-level functors with `-private` so they are treated purely as data, not called directly:

```seam
-private([natnum(VALUE), succ(INNER), edge(FROM, TO), path(FROM, TO)])
```

A program is then a list of such clauses:

```seam
natnum_program(PROGRAM) <- (
    PROGRAM is [
        [natnum(0), []],
        [natnum(succ(X)), [natnum(X)]]
    ]
)
```

This encodes the two-clause natural number predicate:

```
natnum(0).
natnum(s(X)) :- natnum(X).
```

Similarly, a graph reachability program:

```seam
graph_program(PROGRAM) <- (
    PROGRAM is [
        [edge('a', 'b'), []],
        [edge('b', 'c'), []],
        [edge('b', 'd'), []],
        [path(X, Y), [edge(X, Y)]],
        [path(X, Y), [edge(X, Z), path(Z, Y)]]
    ]
)
```

---

## Clause Matching

All meta-interpreters share a helper that finds a clause in the program whose head unifies with a given goal, returning a fresh copy of the body (to avoid variable clashes between different resolution steps):

```seam
match_clause(GOAL, FRESH_BODY, PROGRAM) <- (
    CLAUSE in PROGRAM,
    copy_term(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
    GOAL is FRESH_HEAD,
)
```

[`copy_term`](term_inspection.md) renames all variables in the clause, so the same clause can be used multiple times without its variables interfering with each other. Unifying `GOAL is FRESH_HEAD` then binds the fresh variables to match the current goal.

---

## 1. Vanilla Meta-Interpreter

The simplest meta-interpreter processes a *list* of goals, replacing each goal with the body of a matching clause, and recursing until the list is empty.

```seam
solve([], _PROGRAM_UNUSED),
solve([GOAL, *GOALS], PROGRAM) <- (
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve(ALL_GOALS, PROGRAM),
)
```

The base case: an empty goal list means all goals are proved. The recursive case: take the first goal, find a matching clause, prepend its body to the remaining goals, and continue. This is the *list-based* form (`mi_list2` in Triska's article), which is tail-recursive and avoids the overhead of a conjunction stack.

**Querying it** from Python hosted in a `.seam` file, with the goal in goal position:

```seam
-import_from(clausal.examples.metainterpreters, [natnum_program, graph_program, solve])
-private([natnum(value), succ(inner), path(from_, to)])

def natnum_holds():
    # Does natnum(succ(succ(0))) hold?
    if --(natnum_program(P), solve([natnum(succ(succ(0)))], P)):
        return True        # the proof succeeds
    return False

def path_holds():
    # Is there a path from a to c?
    if --(graph_program(G), solve([path('a', 'c')], G)):
        return True
    return False
```

A functor declared in two modules is the same functor: `natnum(0)` here is the
cell `('natnum', 0)`, exactly what the example module builds.

From a plain `.py` file (no `--`), build the goal cells yourself and use the
lower-level API:

```python
from clausal import Var, once, solve
from clausal.examples import metainterpreters as mi

# The object-level terms are cells: natnum(succ(succ(0))) is
# ("natnum", ("succ", ("succ", 0))).

# Does natnum(s(s(0))) hold?
P = Var()
once(("natnum_program", P), module=mi)
result = list(solve(("solve", [("natnum", ("succ", ("succ", 0)))], P.value), module=mi))
# → one solution (the proof succeeds)

# Is there a path from a to c?
G = Var()
once(("graph_program", G), module=mi)
result = list(solve(("solve", [("path", "a", "c")], G.value), module=mi))
# → one solution
```

---

## 2. Inference-Counting Meta-Interpreter

By adding a counter argument, we can count the number of resolution steps (clause applications) the interpreter performs:

```seam
solve_count([], _PROGRAM_UNUSED, 0),
solve_count([GOAL, *GOALS], PROGRAM, COUNT) <- (
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve_count(ALL_GOALS, PROGRAM, SUB_COUNT),
    COUNT == SUB_COUNT + 1,
)
```

Each recursive call adds one to the count after the sub-proof completes. The count accumulates bottom-up as the recursion unwinds.

**Examples:**

| Query | Steps |
|---|---|
| `natnum(0)` | 1 — one fact applied |
| `natnum(succ(0))` | 2 — recursive clause + base fact |
| `natnum(succ(succ(0)))` | 3 — two recursive steps + base |
| `edge('a', 'b')` | 1 — one fact |
| `path('a', 'b')` | 2 — one path clause + one edge fact |
| `path('a', 'c')` | 4 — path + edge + path + edge |

---

## 3. Depth-Limited Meta-Interpreter

The vanilla interpreter will loop forever on programs that have cycles or infinite derivations. Adding a depth limit causes it to fail rather than diverge:

```seam
solve_limit([], _PROGRAM_UNUSED, _MAX_UNUSED),
solve_limit([GOAL, *GOALS], PROGRAM, MAX) <- (
    MAX > 0,
    MAX1 == MAX - 1,
    match_clause(GOAL, BODY, PROGRAM),
    append(BODY, GOALS, ALL_GOALS),
    solve_limit(ALL_GOALS, PROGRAM, MAX1),
)
```

Each resolution step decrements the depth counter. When `MAX` reaches zero, the guard `MAX > 0` fails, cutting off that branch.

**Examples:**

```
solve_limit([natnum(succ(0))], P, 1)     → fails  (needs 2 steps)
solve_limit([natnum(succ(0))], P, 2)     → succeeds
solve_limit([path('a', 'c')], P, 3)      → fails  (needs 4 steps)
solve_limit([path('a', 'c')], P, 4)      → succeeds
```

---

## 4. Iterative Deepening

Iterative deepening combines the completeness of breadth-first search with the space efficiency of depth-first search. It repeatedly tries increasing depth limits until a proof is found:

```seam
solve_iterative_deepening(GOALS, PROGRAM) <- (
    between(0, 1000, DEPTH),
    solve_limit(GOALS, PROGRAM, DEPTH),
)
```

`between` generates 0, 1, 2, … in order. For each candidate depth, `solve_limit` either finds a proof or fails. On failure, backtracking increments the depth and tries again. The first depth at which a proof exists is found, and the proof is returned.

**The key advantage** is completeness on programs where naive DFS would loop. Consider a cyclic graph where the only successful path clause is listed *after* the recursive one:

```seam
cyclic_program(PROGRAM) <- (
    PROGRAM is [
        [edge('a', 'b'), []],
        [edge('b', 'a'), []],
        [path(X, Y), [edge(X, Z), path(Z, Y)]],   # recursive — tried first
        [path(X, Y), [edge(X, Y)]]                  # base — tried second
    ]
)
```

`solve([path('a', 'b')], P)` with `P` the cyclic program loops forever — the recursive clause is always tried first, generating `a→b→a→b→…`. But `solve_iterative_deepening([path('a', 'b')], P)` succeeds at depth 2, because at depth 1 both branches are exhausted, and at depth 2 `a→b` is found via the base clause.

---

## 5. Proof Tree Meta-Interpreter

The proof tree interpreter extends the vanilla interpreter to build a *trace* of the proof — a tree recording which clause was used to resolve each goal, and how its body was proved:

```seam
solve_tree([], _PROGRAM_UNUSED, []),
solve_tree([GOAL, *GOALS], PROGRAM, [[GOAL, BODY_TREE], *GOALS_TREE]) <- (
    match_clause(GOAL, BODY, PROGRAM),
    solve_tree(BODY, PROGRAM, BODY_TREE),
    solve_tree(GOALS, PROGRAM, GOALS_TREE),
)
```

Each node in the tree is `[Goal, SubTree]` where `SubTree` is the proof tree for the body goals that were used to resolve `Goal`. Facts (clauses with empty body) produce leaf nodes `[Goal, []]`.

**Example: `path('a', 'c')`**

```
path('a', 'c')
└─ edge('a', 'b')          ← leaf (fact)
└─ path('b', 'c')
   └─ edge('b', 'c')       ← leaf (fact)
```

In Clausal list notation:

```seam
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:metainterp_graph_test"
```

**Example: `natnum(s(s(0)))`**

```
natnum(succ(succ(0)))
└─ natnum(succ(0))
   └─ natnum(0)             ← leaf (fact)
```

```seam
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:metainterp_tree_display"
```

---

## Key Design Points

**Object programs as actual terms** — unlike some presentations that use `assert`/`clause` to store the object program in the Prolog database, these interpreters pass the program as an explicit list. This makes the interpretation *transparent*: the program being interpreted is visible data that can be inspected, transformed, or generated.

**`copy_term` for fresh variables** — without freshening, reusing a clause that contains `X` twice would unify all occurrences of `X` across different resolution steps. `copy_term` renames all variables in a clause before unification, exactly as a real Prolog interpreter would.

**Composability** — each interpreter is a small, self-contained predicate. They can be combined: for example, `solve_count` could be extended with a depth limit (producing a counted, depth-bounded interpreter) by merging the two patterns. These interpreters can also be [specialized](specialization.md) via partial deduction to eliminate interpretation overhead.

---

??? info "Source and tests"

    Full source: `clausal/examples/metainterpreters.seam`

    The file contains 28 `test` clauses covering all five interpreters across the natural number and graph programs, including the iterative deepening completeness test on the cyclic graph.

*See also: [Tabling](tabling.md) — built-in memoisation for left-recursive predicates.*
*See also: [Meta-Predicates](meta_predicates.md) — findall, bagof, setof, forall.*
*See also: [Term Inspection](term_inspection.md) — copy_term, term_variables, numbervars.*
