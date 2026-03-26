# Tutorial

Welcome to Clausal — logic programming embedded in Python. This tutorial
introduces the core concepts: defining relations, querying them, and
understanding how unification connects goals to clauses. No Prolog experience
required.

!!! note "Clausal vs Prolog syntax"

    This tutorial is based on material from [The Power of Prolog](https://www.metalevel.at/prolog).
    Clausal and Prolog syntax may slightly differ — for example, Clausal uses
    `ALLCAPS` variables, `<-` instead of `:-`, and Python-style lists. If you are
    comparing with Prolog resources, keep these differences in mind.

---

## Your first .clausal file

Create a file called `hello.clausal`:

```clausal
greeting("hello"),
greeting("hi"),
greeting("hey there"),
```

Each line is a **fact** — an unconditional statement that something is true.
The trailing comma is the separator between clauses (think of the file as one big
expression).

Query it from Python:

```python
import clausal
from hello import greeting
print(list(clausal.query(greeting("hello"))))
```

You should see `[{}]` — one solution, no variables to report. Try querying with a
variable:

```python
print(list(clausal.query(greeting(X))))   # X is a logic variable
```

This prints every greeting in turn: `[{'X': 'hello'}, {'X': 'hi'}, {'X': 'hey there'}]`.

??? tip "Thinking relationally"

    In Clausal, every predicate defines a **relation** — it describes when
    something is true about its arguments. This is different from functions,
    which map inputs to outputs. A single relation can often be used in
    multiple directions: to compute, to verify, to generate. See
    [Thinking Relationally](thinking_relationally.md) for a deeper exploration
    of this idea.

---

## Facts and rules

Let's model a small family tree. Create `family.clausal`:

```clausal
parent("alice", "bob"),
parent("alice", "carol"),
parent("bob", "dave"),
parent("bob", "eve"),

grandparent(GRANDPARENT, GRANDCHILD) <- (
    parent(GRANDPARENT, MIDDLE),
    parent(MIDDLE, GRANDCHILD)
)
```

The first four lines are **facts**: `parent("alice", "bob")` means "alice is a parent
of bob".

The last block is a **rule**. Read it as: "GRANDPARENT is a grandparent of GRANDCHILD
if there exists some MIDDLE such that GRANDPARENT is a parent of MIDDLE and MIDDLE is
a parent of GRANDCHILD."

The `<-` arrow means "is true if". Goals in the body are separated by **commas** and
the body is wrapped in parentheses.

Query it from Python:

```python
from family import grandparent
print(list(clausal.query(grandparent("alice", X))))
```

Result: `[{'X': 'dave'}, {'X': 'eve'}]` — both of alice's grandchildren.

### Multiple solutions and backtracking

When you call `clausal.query(...)` you get a **generator** that yields one solution
dictionary per answer. Clausal finds all clauses whose heads unify with the goal —
these represent logical alternatives. If a condition in the body does not hold,
Clausal explores the remaining alternatives.

To get just the first answer use `clausal.once(...)`. To collect everything into a
list use `list(clausal.query(...))`.

---

## Logic variables

Variables in `.clausal` files are written in **ALLCAPS**: `X`, `PARENT`, `CHILD`,
`RESULT`, `HEAD`, `TAIL`. This makes them easy to spot in a rule.

```clausal
sibling(A, B) <- (
    parent(PARENT, A),
    parent(PARENT, B)
)
```

`A` and `B` are logic variables — they stand for any term at all. When Clausal
searches for clauses whose heads unify with a goal, variables are bound to make
the terms identical: if `A` is unbound and unifies with `"bob"`, then `A`
becomes `"bob"` for the rest of that branch.

The **anonymous variable** `_` unifies with anything and is never reported in
results:

```clausal
has_child(PERSON) <- parent(PERSON, _)
```

"PERSON has a child" — we don't care what the child's name is.

### How unification works

Unification finds the most general way to make two terms identical. Both terms
can contain variables, and variables on **either side** can be bound. This
bidirectionality is what makes relations work in all directions.

When you query `parent("alice", CHILD)`, Clausal searches for clauses whose
heads unify with the goal. The clause `parent("alice", "bob")` unifies when
CHILD is bound to `"bob"`. No assignment, no mutation — each branch of the
search has its own consistent set of bindings.

---

## Lists

Lists are written with square brackets: `[]` (empty), `[1, 2, 3]`, `["a", "b"]`.
The head/tail pattern uses a star:

```clausal
first(HEAD, [HEAD, *_]),

rest(TAIL, [_, *TAIL]),
```

`[HEAD, *TAIL]` unifies with any non-empty list, binding `HEAD` to the first
element and `TAIL` to the remaining elements.

### In/2 and Append/3

These are built-in predicates. `In(X, LIST)` describes the membership relation
— it holds for each element of `LIST` in turn:

```clausal
contains_three(LIST) <- In(3, LIST)
```

`Append(PREFIX, SUFFIX, WHOLE)` relates three lists such that `PREFIX` concatenated
with `SUFFIX` gives `WHOLE`. You can use it forwards (split a list) or backwards
(build one):

```clausal
last(ELEMENT, LIST) <- Append(_, [ELEMENT], LIST)
```

### Describing list relations in clause heads

Clause heads can describe the structure of list arguments directly, which is
often cleaner than stating the structure as a separate condition in the body:

```clausal
sum_list([], 0),
sum_list([HEAD, *TAIL], TOTAL) <- (
    sum_list(TAIL, SUBTOTAL),
    TOTAL == SUBTOTAL + HEAD
)
```

The first clause states that the sum of the empty list is 0. The second states
that the sum of [HEAD, *TAIL] is TOTAL when the sum of TAIL is SUBTOTAL and
TOTAL is SUBTOTAL + HEAD.

```clausal
double_list([], []),
double_list([HEAD, *TAIL], [DOUBLED, *REST]) <- (
    DOUBLED == HEAD * 2,
    double_list(TAIL, REST)
)
```

Each clause describes a different case in which the relation holds. Clauses are
logical alternatives — Clausal searches for those whose heads unify with the
goal.

---

## Arithmetic

Use `==` to post an arithmetic constraint between a variable and an expression:

```clausal
square(N, SQ) <- (SQ == N * N)

factorial(0, 1),
factorial(N, F) <- (
    N > 0,
    N1 == N - 1,
    factorial(N1, F1),
    F == N1 * F1 + F1
)
```

Supported operators: `+`, `-`, `*`, `/`, `//` (integer division), `**` (power),
`mod` (modulo), `abs(X)`, `min(X, Y)`, `max(X, Y)`.

`==` posts a CLP(FD) constraint that works in all directions — even when
variables are unbound. Use `:=` only for eager Python-side evaluation
(e.g., `LABEL := ++"fizz"` for string operations).

### Comparisons

The standard comparison operators work directly as goals:

```clausal
positive(N) <- (N > 0)
between(LOW, HIGH, N) <- (
    N >= LOW,
    N <= HIGH
)
```

Comparison operators `<`, `>`, `>=`, `<=` work directly as goals. Use `==` and
`!=` for arithmetic equality and inequality.

### A worked example: fizzbuzz

```clausal
fizzbuzz(N, LABEL) <- (N % 15 == 0, LABEL := ++"fizzbuzz")
fizzbuzz(N, LABEL) <- (N % 3 == 0, LABEL := ++"fizz")
fizzbuzz(N, LABEL) <- (N % 5 == 0, LABEL := ++"buzz")
fizzbuzz(N, N),
```

Query it from Python:

```python
from fizzbuzz import fizzbuzz
results = [clausal.once(fizzbuzz(n, X))["X"] for n in range(1, 16)]
```

---

## Negation

`not goal` is **negation as failure**: it succeeds if `goal` has no solutions.

```clausal
safe_to_delete(FILE) <- (not important(FILE))
```

### When to use it

Negation as failure is appropriate when you want to express "there is no evidence
that...". It works correctly when all the relevant facts are already known — the
classic **closed-world assumption**.

```clausal
bachelor(PERSON) <- (
    male(PERSON),
    not married(PERSON)
)
```

If `married("alice")` is not in the database, `not married("alice")` succeeds.

### When not to use it

Avoid `not goal` when the variables inside `goal` are unbound. This query:

```text
5 not in LIST
```

will almost always fail, because Clausal can instantiate `LIST` to something that
contains 5. Instead, make sure any variables in the negated goal are already bound
before the check:

```clausal
no_fives(LIST) <- (5 not in LIST)
```

is fine when `LIST` is passed in fully instantiated; it is not a generator of lists
that avoid 5.

For constraint-based "not equal" on partially-instantiated terms, use `dif/2`
(`is not`) from the constraints module (see the [constraints guide](constraints.md)).

!!! note "Monotonicity"

    Negation as failure is inherently non-monotonic — binding a variable can
    cause a previously successful negation to fail. For monotonic alternatives
    that preserve [logical purity](purity.md), use `dif/2` for disequality and
    CLP(FD) constraints for arithmetic.

---

## Testing your code

Clausal has a lightweight convention for inline tests. Define `Test/1` predicates:

```clausal
sum_list([], 0),
sum_list([HEAD, *TAIL], TOTAL) <- (
    sum_list(TAIL, SUBTOTAL),
    TOTAL == SUBTOTAL + HEAD
)

Test("sum [1,2,3,4] = 10") <- (
    sum_list([1, 2, 3, 4], TOTAL),
    TOTAL == 10
)

Test("sum [] = 0") <- (
    sum_list([], TOTAL),
    TOTAL == 0
)
```

Run the whole test suite with:

```bash
python -m pytest
```

Clausal's import hook picks up `.clausal` files automatically. The test runner
collects any Python test files that import and exercise your predicates.

A typical Python test wrapper looks like:

```python
import clausal
from mymodule import test_sum_list

def test_sum():
    assert list(clausal.query(test_sum_list()))
```

See [Testing](testing.md) for the full testing guide, including how to use fixtures
and parametrize.

---

## A complete example: graph reachability

Let's put it all together with a classic logic programming problem — finding reachable
nodes in a directed graph.

```clausal
edge("a", "b"),
edge("b", "c"),
edge("c", "d"),
edge("b", "d"),

reachable(SOURCE, DEST) <- edge(SOURCE, DEST)

reachable(SOURCE, DEST) <- (
    edge(SOURCE, MID),
    reachable(MID, DEST)
)
```

The first clause states that SOURCE and DEST are reachable if there is a direct
edge between them. The second states that they are reachable if there is an edge
from SOURCE to some MID, and MID and DEST are reachable. These two clauses are
logical alternatives — together they define the complete reachability relation.

Query it from Python:

```python
from graph import reachable
print(sorted(s["DEST"] for s in clausal.query(reachable("a", DEST))))
# ['b', 'c', 'd']
```

For large graphs with cycles, use the `-table` directive to enable tabling (memoised
search) — see [Tabling](tabling.md).

---

## Where to go next

- **[Thinking Relationally](thinking_relationally.md)** — the most important
  idea in logic programming: predicates as relations, not functions
- **[Purity and Monotonicity](purity.md)** — why pure code has better
  properties and how to write it
- **[Syntax reference](syntax.md)** — full grammar, all operators, clause forms
- **[Constraints](constraints.md)** — `dif/2` for structural inequality; CLP(FD) for
  finite-domain constraint solving (N-queens, Sudoku, SEND+MORE=MONEY)
- **[DCGs](dcg.md)** — Definite Clause Grammars for parsing and string generation
- **[Examples](examples.md)** — worked examples: map colouring, Sudoku, graph
  algorithms, and more
- **[Predicate index](builtins.md)** — every built-in predicate with examples
