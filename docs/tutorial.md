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
    If you have existing `.pl` files, you can [import them directly](importing_prolog.md).

---

## Your first .clausal file

Create a file called `hello.clausal`:

```seam
greeting('hello'),
greeting('hi'),
greeting('hey there'),
```

Each line is a **fact** — an unconditional statement that something is true.
The trailing comma is the separator between clauses (think of the file as one big
expression).

Query it from Python. Next to `hello.clausal`, create `ask.seam`: a `.seam`
file is Python that can also speak Clausal terms (`.clausal` and `.seam` are
the same format under two names).

```python
# ask.seam
-import_from(hello, [greeting])

if --greeting('hello'):
    print("yes")

for X in --greeting(X):
    print(X)
```

and run it:

```bash
python -c "import clausal, ask"
```

(`import clausal` installs the import hook that loads `.clausal` and `.seam`
files as Python modules.)

`--` marks a Clausal goal inside Python. After `if`, the goal is asked once:
`greeting('hello')` holds, so this prints `yes`. After `for ... in`, every
solution is produced in turn, and the ALL-CAPS name `X` comes back as an
ordinary Python variable: `hello`, `hi`, `hey there`.

From a plain `.py` file, where `--` is not available, the same questions go
through `solve`: a goal is a **cell** — a tuple of the predicate's name
followed by its arguments — run against the module you pass:

```python
from clausal import Var, solve
import hello

for trail in solve(("greeting", "hello"), module=hello):
    print("yes")

for trail in solve(("greeting", X := Var()), module=hello):
    print(X.value)
```

The rest of this tutorial uses the `--` form; see
[Python Integration](python_integration.md#querying-from-python) for both.

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

```seam
parent('alice', 'bob'),
parent('alice', 'carol'),
parent('bob', 'dave'),
parent('bob', 'eve'),

grandparent(GRANDPARENT, GRANDCHILD) <- (
    parent(GRANDPARENT, MIDDLE),
    parent(MIDDLE, GRANDCHILD)
)
```

The first four lines are **facts**: `parent('alice', 'bob')` means "alice is a parent
of bob".

The last block is a **rule**. Read it as: "GRANDPARENT is a grandparent of GRANDCHILD
if there exists some MIDDLE such that GRANDPARENT is a parent of MIDDLE and MIDDLE is
a parent of GRANDCHILD."

The `<-` arrow means "is true if". Goals in the body are separated by **commas** and
the body is wrapped in parentheses.

Query it from a `.seam` file:

```python
-import_from(family, [grandparent])

for X in --grandparent('alice', X):
    print(X)
```

Result: `dave` then `eve` — both of alice's grandchildren.

### Multiple solutions and backtracking

Clausal finds all clauses whose heads unify with the goal — these represent
logical alternatives. If a condition in the body does not hold, Clausal
explores the remaining alternatives.

`for X in --goal:` iterates every solution; `if --goal:` takes just the first
one, and its variables stay bound after the `if`. The lower-level
equivalents are `solve(goal, module=…)` and `once(goal, module=…)`.

---

## Logic variables

Variables in `.clausal` files are written in **ALLCAPS**: `X`, `PARENT`, `CHILD`,
`RESULT`, `HEAD`, `TAIL`. This makes them easy to spot in a rule.

```seam
sibling(A, B) <- (
    parent(PARENT, A),
    parent(PARENT, B)
)
```

`A` and `B` are logic variables — they stand for any term at all. when Clausal
searches for clauses whose heads unify with a goal, variables are bound to make
the terms identical: if `A` is unbound and unifies with `'bob'`, then `A`
becomes `'bob'` for the rest of that branch.

The **anonymous variable** `_` unifies with anything and is never reported in
results:

```seam
has_child(PERSON) <- parent(PERSON, _)
```

"PERSON has a child" — we don't care what the child's name is.

### How unification works

Unification finds the most general way to make two terms identical. Both terms
can contain variables, and variables on **either side** can be bound. This
bidirectionality is what makes relations work in all directions.

when you query `parent('alice', CHILD)`, Clausal searches for clauses whose
heads unify with the goal. The clause `parent('alice', 'bob')` unifies when
CHILD is bound to `'bob'`. No assignment, no mutation — each branch of the
search has its own consistent set of bindings.

---

## [Lists](lists.md)

Lists are written with square brackets: `[]` (empty), `[1, 2, 3]`, `['a', 'b']`.
(`'a'` is an atom, a symbolic constant; `"a"` is a string, text.)
The head/tail pattern uses a star:

```seam
first(HEAD, [HEAD, *_]),

rest(TAIL, [_, *TAIL]),
```

`[HEAD, *TAIL]` unifies with any non-empty list, binding `HEAD` to the first
element and `TAIL` to the remaining elements.

### in_/2 and append/3

These are built-in predicates. `in_(X, LIST)` describes the membership relation
— it holds for each element of `LIST` in turn:

```seam
contains_three(LIST) <- in_(3, LIST)
```

`append(PREFIX, SUFFIX, WHOLE)` relates three lists such that `PREFIX` concatenated
with `SUFFIX` gives `WHOLE`. You can use it forwards (split a list) or backwards
(build one):

```seam
last(ELEMENT, LIST) <- append(_, [ELEMENT], LIST)
```

### Describing list relations in clause heads

Clause heads can describe the structure of list arguments directly, which is
often cleaner than stating the structure as a separate condition in the body:

```seam
sum_list([], 0),
sum_list([HEAD, *TAIL], TOTAL) <- (
    sum_list(TAIL, SUBTOTAL),
    TOTAL == SUBTOTAL + HEAD
)
```

The first clause states that the sum of the empty list is 0. The second states
that the sum of [HEAD, *TAIL] is TOTAL when the sum of TAIL is SUBTOTAL and
TOTAL is SUBTOTAL + HEAD.

```seam
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

## [Arithmetic](arithmetic.md)

Use `==` to post an arithmetic constraint between a variable and an expression:

```seam
square(N, SQ) <- (SQ == N * N)

factorial(0, 1),
factorial(N, F) <- (
    N > 0,
    N1 == N - 1,
    factorial(N1, F1),
    F == N * F1
)
```

Supported operators: `+`, `-`, `*`, `/`, `//`, `%` and `**`. Written bare,
as here, an operator keeps its Python meaning (`-7 // 2` is -4); inside a `==` constraint `/` is exact (`X == 7 / 2`
gives 7/2). [Operators](operators.md) has the full table, including the
quoted Prolog spellings.

`==` posts a [CLP(ℤ)](constraints.md) constraint that works in all directions — even when
variables are unbound. `is` is **unification**, not evaluation: `X is 1 + 2`
binds `X` to the term `1 + 2`. To evaluate eagerly, use `eval_(1 + 2, X)` or
a Python escape, `X is ++(1 + 2)`.

### Comparisons

The standard comparison operators work directly as goals:

```seam
positive(N) <- (N > 0)
in_range(LOW, HIGH, N) <- (
    N >= LOW,
    N <= HIGH
)
```

Comparison operators `<`, `>`, `>=`, `<=` work directly as goals. Use `==` and
`!=` for arithmetic equality and inequality.

### A worked example: fizzbuzz

```seam
fizzbuzz(N, 'fizzbuzz') <- (N % 15 == 0)
fizzbuzz(N, 'fizz') <- (N % 3 == 0, N % 5 != 0)
fizzbuzz(N, 'buzz') <- (N % 5 == 0, N % 3 != 0)
fizzbuzz(N, N) <- (N % 3 != 0, N % 5 != 0)
```

Each clause states exactly when it holds, so every number has one label.
Query it from a `.seam` file, passing each Python `n` in with `++`:

```python
-import_from(fizzbuzz, [fizzbuzz])

def labels(upto):
    results = []
    for n in range(1, upto + 1):
        if --fizzbuzz(++n, LABEL):
            results.append(LABEL)
    return results
```

`labels(15)` is `[1, 2, 'fizz', 4, 'buzz', 'fizz', 7, 8, 'fizz', 'buzz', 11, 'fizz', 13, 14, 'fizzbuzz']`.

---

## Negation

`not goal` is **negation as failure**: it succeeds if `goal` has no solutions.

```seam
safe_to_delete(FILE) <- (not important(FILE))
```

### when to use it

Negation as failure is appropriate when you want to express "there is no evidence
that...". It works correctly when all the relevant facts are already known — the
classic **closed-world assumption**.

```seam
bachelor(PERSON) <- (
    male(PERSON),
    not married(PERSON)
)
```

If `married('alice')` is not in the database, `not married('alice')` succeeds.

### when not to use it

Avoid `not goal` when the variables inside `goal` are unbound. This query:

```text
5 not in LIST
```

will almost always fail, because Clausal can instantiate `LIST` to something that
contains 5. Instead, make sure any variables in the negated goal are already bound
before the check:

```seam
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
    CLP(ℤ) constraints for arithmetic.

---

## Testing your code

Clausal has a lightweight convention for inline tests. Define `test/1` predicates:

```seam
sum_list([], 0),
sum_list([HEAD, *TAIL], TOTAL) <- (
    sum_list(TAIL, SUBTOTAL),
    TOTAL == SUBTOTAL + HEAD
)

test("sum [1,2,3,4] = 10") <- (
    sum_list([1, 2, 3, 4], TOTAL),
    TOTAL == 10
)

test("sum [] = 0") <- (
    sum_list([], TOTAL),
    TOTAL == 0
)
```

Run the whole test suite with:

```bash
python -m pytest
```

Clausal's [import hook](import.md) picks up `.clausal` files automatically. The test runner
collects any Python test files that import and exercise your predicates.

A Python test can also run one `test/1` clause by its description. The
description `"sum [1,2,3,4] = 10"` is a **string**, so from a `.py` file build
it with `chars` (a plain Python `str` would be the atom of that spelling, a
different term):

```python
from clausal import once
from clausal.logic.cells import chars
import mymodule

def test_sum():
    assert once(("test", chars("sum [1,2,3,4] = 10")), module=mymodule) is not None
```

A wrapper that runs more than a couple of goals should build them through one
helper function of its own rather than repeating the tuple and the `module=`
at every call site — see
[Driving Clausal from a test suite](python_integration.md#driving-clausal-from-a-test-suite).

See [Testing](testing.md) for the full testing guide, including how to use fixtures
and parametrize.

---

## A complete example: graph reachability

Let's put it all together with a classic logic programming problem — finding reachable
nodes in a directed graph.

```seam
edge('a', 'b'),
edge('b', 'c'),
edge('c', 'd'),
edge('b', 'd'),

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

Query it from a `.seam` file:

```python
-import_from(graph, [reachable])

print(sorted({DEST for DEST in --reachable('a', DEST)}))
# ['b', 'c', 'd']
```

or from a plain `.py` file:

```python
from clausal import Var, solve
import graph

results = set()
for trail in solve(("reachable", "a", DEST := Var()), module=graph):
    results.add(DEST.value)
print(sorted(results))
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
- **[Constraints](constraints.md)** — `dif/2` for structural inequality; CLP(ℤ) for
  integer constraint solving (N-queens, Sudoku, SEND+MORE=MONEY)
- **[DCGs](dcg.md)** — Definite Clause Grammars for parsing and string generation
- **[Examples](examples.md)** — worked examples: map colouring, Sudoku, graph
  algorithms, and more
- **[Predicate index](builtins.md)** — every built-in predicate with examples
