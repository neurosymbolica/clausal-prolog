# Meta-Interpreters

A *meta-interpreter* is an interpreter written in the same language it interprets. In logic programming, this means a Prolog (or Clausal) program that evaluates another logic program represented as data. Meta-interpreters are a classical demonstration of logic programming's homoiconicity: programs and data share the same representation.

This page follows the structure of Markus Triska's [A Couple of Meta-Interpreters in Prolog](https://www.metalevel.at/acomip/), adapting the examples to Clausal syntax.

The full source is in `clausal/examples/metainterpreters.clausal`.

---

## Object Programs as Data

The key idea is to represent an *object-level* program — the program being interpreted — as a list of clauses, where each clause is a pair `[Head, Body]`. `Head` is a term, `Body` is a list of goals (also terms).

In Clausal, object-level terms are ordinary predicate instances. We declare private functor classes for the object level so they are treated purely as data, not called directly:

```clausal
-private([Natnum(VALUE), Succ(INNER), Edge(FROM, TO), Path(FROM, TO)])
```

A program is then a list of such clauses:

```clausal
NatnumProgram(PROGRAM) <- (
    PROGRAM is [
        [Natnum(0), []],
        [Natnum(Succ(X)), [Natnum(X)]]
    ]
)
```

This encodes the two-clause natural number predicate:

```
natnum(0).
natnum(s(X)) :- natnum(X).
```

Similarly, a graph reachability program:

```clausal
GraphProgram(PROGRAM) <- (
    PROGRAM is [
        [Edge("a", "b"), []],
        [Edge("b", "c"), []],
        [Edge("b", "d"), []],
        [Path(X, Y), [Edge(X, Y)]],
        [Path(X, Y), [Edge(X, Z), Path(Z, Y)]]
    ]
)
```

---

## Clause Matching

All meta-interpreters share a helper that finds a clause in the program whose head unifies with a given goal, returning a fresh copy of the body (to avoid variable clashes between different resolution steps):

```clausal
MatchClause(GOAL, FRESH_BODY, PROGRAM) <- (
    CLAUSE in PROGRAM,
    CopyTerm(CLAUSE, [FRESH_HEAD, FRESH_BODY]),
    GOAL is FRESH_HEAD,
)
```

`CopyTerm` renames all variables in the clause, so the same clause can be used multiple times without its variables interfering with each other. Unifying `GOAL is FRESH_HEAD` then binds the fresh variables to match the current goal.

---

## 1. Vanilla Meta-Interpreter

The simplest meta-interpreter processes a *list* of goals, replacing each goal with the body of a matching clause, and recursing until the list is empty.

```clausal
Solve([], _PROGRAM),
Solve([GOAL, *GOALS], PROGRAM) <- (
    MatchClause(GOAL, BODY, PROGRAM),
    Append(BODY, GOALS, ALL_GOALS),
    Solve(ALL_GOALS, PROGRAM),
)
```

The base case: an empty goal list means all goals are proved. The recursive case: take the first goal, find a matching clause, prepend its body to the remaining goals, and continue. This is the *list-based* form (`mi_list2` in Triska's article), which is tail-recursive and avoids the overhead of a conjunction stack.

**Querying it:**

```python
from clausal.examples.metainterpreters import NatnumProgram, GraphProgram
from clausal.examples.metainterpreters import Solve, Natnum, Succ, Path, Edge

# Does natnum(s(s(0))) hold?
p = next(NatnumProgram.query())
result = list(Solve.query(goals=[Natnum(Succ(Succ(0)))], program=p))
# → one solution (the proof succeeds)

# Is there a path from a to c?
g = next(GraphProgram.query())
result = list(Solve.query(goals=[Path("a", "c")], program=g))
# → one solution
```

---

## 2. Inference-Counting Meta-Interpreter

By adding a counter argument, we can count the number of resolution steps (clause applications) the interpreter performs:

```clausal
SolveCount([], _PROGRAM, 0),
SolveCount([GOAL, *GOALS], PROGRAM, COUNT) <- (
    MatchClause(GOAL, BODY, PROGRAM),
    Append(BODY, GOALS, ALL_GOALS),
    SolveCount(ALL_GOALS, PROGRAM, SUB_COUNT),
    COUNT := SUB_COUNT + 1,
)
```

Each recursive call adds one to the count after the sub-proof completes. The count accumulates bottom-up as the recursion unwinds.

**Examples:**

| Query | Steps |
|---|---|
| `Natnum(0)` | 1 — one fact applied |
| `Natnum(Succ(0))` | 2 — recursive clause + base fact |
| `Natnum(Succ(Succ(0)))` | 3 — two recursive steps + base |
| `Edge("a","b")` | 1 — one fact |
| `Path("a","b")` | 2 — one path clause + one edge fact |
| `Path("a","c")` | 4 — path + edge + path + edge |

---

## 3. Depth-Limited Meta-Interpreter

The vanilla interpreter will loop forever on programs that have cycles or infinite derivations. Adding a depth limit causes it to fail rather than diverge:

```clausal
SolveLimit([], _PROGRAM, _MAX),
SolveLimit([GOAL, *GOALS], PROGRAM, MAX) <- (
    MAX > 0,
    MAX1 := MAX - 1,
    MatchClause(GOAL, BODY, PROGRAM),
    Append(BODY, GOALS, ALL_GOALS),
    SolveLimit(ALL_GOALS, PROGRAM, MAX1),
)
```

Each resolution step decrements the depth counter. When `MAX` reaches zero, the guard `MAX > 0` fails, cutting off that branch.

**Examples:**

```
SolveLimit([Natnum(Succ(0))], P, 1)     → fails  (needs 2 steps)
SolveLimit([Natnum(Succ(0))], P, 2)     → succeeds
SolveLimit([Path("a","c")], P, 3)       → fails  (needs 4 steps)
SolveLimit([Path("a","c")], P, 4)       → succeeds
```

---

## 4. Iterative Deepening

Iterative deepening combines the completeness of breadth-first search with the space efficiency of depth-first search. It repeatedly tries increasing depth limits until a proof is found:

```clausal
SolveIterativeDeepening(GOALS, PROGRAM) <- (
    Between(0, 1000, DEPTH),
    SolveLimit(GOALS, PROGRAM, DEPTH),
)
```

`Between` generates 0, 1, 2, … in order. For each candidate depth, `SolveLimit` either finds a proof or fails. On failure, backtracking increments the depth and tries again. The first depth at which a proof exists is found, and the proof is returned.

**The key advantage** is completeness on programs where naive DFS would loop. Consider a cyclic graph where the only successful path clause is listed *after* the recursive one:

```clausal
CyclicProgram(PROGRAM) <- (
    PROGRAM is [
        [Edge("a", "b"), []],
        [Edge("b", "a"), []],
        [Path(X, Y), [Edge(X, Z), Path(Z, Y)]],   # recursive — tried first
        [Path(X, Y), [Edge(X, Y)]]                  # base — tried second
    ]
)
```

`Solve([Path("a","b")], CyclicProgram)` loops forever — the recursive clause is always tried first, generating `a→b→a→b→…`. But `SolveIterativeDeepening([Path("a","b")], CyclicProgram)` succeeds at depth 2, because at depth 1 both branches are exhausted, and at depth 2 `a→b` is found via the base clause.

---

## 5. Proof Tree Meta-Interpreter

The proof tree interpreter extends the vanilla interpreter to build a *trace* of the proof — a tree recording which clause was used to resolve each goal, and how its body was proved:

```clausal
SolveTree([], _PROGRAM, []),
SolveTree([GOAL, *GOALS], PROGRAM, [[GOAL, BODY_TREE], *GOALS_TREE]) <- (
    MatchClause(GOAL, BODY, PROGRAM),
    SolveTree(BODY, PROGRAM, BODY_TREE),
    SolveTree(GOALS, PROGRAM, GOALS_TREE),
)
```

Each node in the tree is `[Goal, SubTree]` where `SubTree` is the proof tree for the body goals that were used to resolve `Goal`. Facts (clauses with empty body) produce leaf nodes `[Goal, []]`.

**Example: `Path("a","c")`**

```
Path("a", "c")
└─ Edge("a", "b")          ← leaf (fact)
└─ Path("b", "c")
   └─ Edge("b", "c")       ← leaf (fact)
```

In Clausal list notation:

```clausal
Test("tree path(a,c) transitive") <- (
    GraphProgram(P),
    SolveTree([Path("a", "c")], P, TREE),
    TREE is [
        [Path("a", "c"), [
            [Edge("a", "b"), []],
            [Path("b", "c"), [
                [Edge("b", "c"), []]
            ]]
        ]]
    ],
)
```

**Example: `Natnum(s(s(0)))`**

```
Natnum(Succ(Succ(0)))
└─ Natnum(Succ(0))
   └─ Natnum(0)             ← leaf (fact)
```

```clausal
TREE is [
    [Natnum(Succ(Succ(0))), [
        [Natnum(Succ(0)), [
            [Natnum(0), []]
        ]]
    ]]
],
```

---

## Key Design Points

**Object programs as actual terms** — unlike some presentations that use `assert`/`clause` to store the object program in the Prolog database, these interpreters pass the program as an explicit list. This makes the interpretation *transparent*: the program being interpreted is visible data that can be inspected, transformed, or generated.

**`CopyTerm` for fresh variables** — without freshening, reusing a clause that contains `X` twice would unify all occurrences of `X` across different resolution steps. `CopyTerm` renames all variables in a clause before unification, exactly as a real Prolog interpreter would.

**Composability** — each interpreter is a small, self-contained predicate. They can be combined: for example, `SolveCount` could be extended with a depth limit (producing a counted, depth-bounded interpreter) by merging the two patterns.

---

??? info "Source and tests"

    Full source: `clausal/examples/metainterpreters.clausal`

    The file contains 30 `Test` clauses covering all five interpreters across the natural number and graph programs, including the iterative deepening completeness test on the cyclic graph.

*See also: [Tabling](tabling.md) — built-in memoisation for left-recursive predicates.*
*See also: [Meta-Predicates](meta_predicates.md) — FindAll, BagOf, SetOf, ForAll.*
*See also: [Term Inspection](term_inspection.md) — CopyTerm, TermVariables, NumberVars.*
