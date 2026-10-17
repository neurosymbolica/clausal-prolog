# Meta-Interpreters

A *meta-interpreter* is an interpreter written in the same language it interprets. In logic programming, this means a Prolog program that evaluates another logic program represented as data. Meta-interpreters are a classical demonstration of logic programming's homoiconicity: programs and data share the same representation.

This page follows the structure of Markus Triska's [A Couple of Meta-Interpreters in Prolog](https://www.metalevel.at/acomip/), with the examples in [Clausal Prolog](clausal_prolog.md) (`.clausal`).

The examples on this page, with their tests, are in `tests/fixtures/docs/metainterpreters_examples.clausal`. The same interpreters ship, written in the [seam](syntax.md), as `clausal/examples/metainterpreters.seam`.

---

## Object Programs as Data

The key idea is to represent an *object-level* program — the program being interpreted — as a list of clauses, where each clause is a pair `[Head, Body]`. `Head` is a term, `Body` is a list of goals (also terms).

Object-level terms are ordinary compound terms such as `natnum(succ(0))`: data, never called directly, so they need no declaration. (A seam module declares them first, with `-private([natnum(VALUE), succ(INNER), ...])`.) A program is then a list of such clauses:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:natnum_program"
```

This encodes the two-clause natural number predicate:

```
natnum(0).
natnum(s(X)) :- natnum(X).
```

Similarly, a graph reachability program:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:graph_program"
```

---

## Clause Matching

All meta-interpreters share a helper that finds a clause in the program whose head unifies with a given goal, returning a fresh copy of the body (to avoid variable clashes between different resolution steps):

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:match_clause"
```

[`copy_term`](term_inspection.md) renames all variables in the clause, so the same clause can be used multiple times without its variables interfering with each other. Unifying `GOAL = FRESH_HEAD` then binds the fresh variables to match the current goal.

---

## 1. Vanilla Meta-Interpreter

The simplest meta-interpreter processes a *list* of goals, replacing each goal with the body of a matching clause, and recursing until the list is empty.

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:solve"
```

The base case: an empty goal list means all goals are proved. The recursive case: take the first goal, find a matching clause, prepend its body to the remaining goals, and continue. This is the *list-based* form (`mi_list2` in Triska's article), which is tail-recursive and avoids the overhead of a conjunction stack.

**Querying it** is an ordinary goal; here as tests:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:solve_queries"
```

From Python hosted in a `.seam` file, the goal goes in goal position (this block is seam syntax):

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

A functor declared in two seam modules is the same functor: `natnum(0)` here is the
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

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:solve_count"
```

Each recursive call adds one to the count after the sub-proof completes. The count accumulates bottom-up as the recursion unwinds.

**Examples** (each row is a test in the fixture file):

| Query | Steps |
|---|---|
| `natnum(0)` | 1 — one fact applied |
| `natnum(succ(0))` | 2 — recursive clause + base fact |
| `natnum(succ(succ(0)))` | 3 — two recursive steps + base |
| `edge(a, b)` | 1 — one fact |
| `path(a, b)` | 2 — one path clause + one edge fact |
| `path(a, c)` | 4 — path + edge + path + edge |

---

## 3. Depth-Limited Meta-Interpreter

The vanilla interpreter will loop forever on programs that have cycles or infinite derivations. Adding a depth limit causes it to fail rather than diverge:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:solve_limit"
```

Each resolution step decrements the depth counter. When `MAX` reaches zero, the [CLP(ℤ)](constraints.md) guard `MAX #> 0` fails, cutting off that branch.

**Examples:**

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:solve_limit_tests"
```

---

## 4. Iterative Deepening

Iterative deepening combines the completeness of breadth-first search with the space efficiency of depth-first search. It repeatedly tries increasing depth limits until a proof is found:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:solve_iterative_deepening"
```

`between` generates 0, 1, 2, … in order. For each candidate depth, `solve_limit` either finds a proof or fails. On failure, backtracking increments the depth and tries again. The first depth at which a proof exists is found, and the proof is returned. On backtracking the same proof is found again at every larger limit, so take the first with `once/1` when one answer is all you need.

**The key advantage** is completeness on programs where naive DFS would loop. Consider a cyclic graph where the only successful path clause is listed *after* the recursive one:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:cyclic_program"
```

`solve([path(a, b)], P)` with `P` the cyclic program loops forever — the recursive clause is always tried first, generating `a→b→a→b→…`. But `solve_iterative_deepening([path(a, b)], P)` succeeds at depth 2, because at depth 1 both branches are exhausted, and at depth 2 `a→b` is found via the base clause:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:iterative_deepening_tests"
```

---

## 5. Proof Tree Meta-Interpreter

The proof tree interpreter extends the vanilla interpreter to build a *trace* of the proof — a tree recording which clause was used to resolve each goal, and how its body was proved:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:solve_tree"
```

Each node in the tree is `[Goal, SubTree]` where `SubTree` is the proof tree for the body goals that were used to resolve `Goal`. Facts (clauses with empty body) produce leaf nodes `[Goal, []]`.

**Example: `path(a, c)`**

```
path(a, c)
└─ edge(a, b)          ← leaf (fact)
└─ path(b, c)
   └─ edge(b, c)       ← leaf (fact)
```

As a term:

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:tree_path_a_c"
```

**Example: `natnum(s(s(0)))`**

```
natnum(succ(succ(0)))
└─ natnum(succ(0))
   └─ natnum(0)             ← leaf (fact)
```

```clausal
--8<-- "tests/fixtures/docs/metainterpreters_examples.clausal:tree_natnum"
```

---

## Key Design Points

**Object programs as actual terms** — unlike some presentations that use `assert`/`clause` to store the object program in the Prolog database, these interpreters pass the program as an explicit list. This makes the interpretation *transparent*: the program being interpreted is visible data that can be inspected, transformed, or generated.

**`copy_term` for fresh variables** — without freshening, reusing a clause that contains `X` twice would unify all occurrences of `X` across different resolution steps. `copy_term` renames all variables in a clause before unification, exactly as a real Prolog interpreter would.

**Composability** — each interpreter is a small, self-contained predicate. They can be combined: for example, `solve_count` could be extended with a depth limit (producing a counted, depth-bounded interpreter) by merging the two patterns. These interpreters can also be [specialized](specialization.md) via partial deduction to eliminate interpretation overhead.

---

??? info "Source and tests"

    Full source: `clausal/examples/metainterpreters.seam` (seam syntax); this
    page's Clausal Prolog version: `tests/fixtures/docs/metainterpreters_examples.clausal`.

    Each file contains 28 `test` clauses covering all five interpreters across the natural number and graph programs, including the iterative deepening completeness test on the cyclic graph.

*See also: [Tabling](tabling.md) — built-in memoisation for left-recursive predicates.*
*See also: [Meta-Predicates](meta_predicates.md) — findall, bagof, setof, forall.*
*See also: [Term Inspection](term_inspection.md) — copy_term, term_variables, numbervars.*
