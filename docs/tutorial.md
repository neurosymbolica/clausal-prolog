# Tutorial

Welcome to Clausal — logic programming embedded in Python. This tutorial walks you
through the essentials, starting from a single fact and building up to recursive
rules, arithmetic, and list processing. No Prolog experience required.

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
),
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
dictionary per answer. Clausal searches all matching clauses automatically. If a rule
body fails partway through, it backtracks and tries the next clause.

To get just the first answer use `clausal.once(...)`. To collect everything into a
list use `list(clausal.query(...))`.

---

## Logic variables

Variables in `.clausal` files are written in **ALLCAPS**: `X`, `PARENT`, `CHILD`,
`RESULT`, `HEAD`, `TAIL`. This makes them easy to spot in a rule.

```clausal
sibling(A, B) <- (
    parent(PARENT, A),
    parent(PARENT, B),
    not (A = B)
),
```

`A` and `B` are logic variables — they stand for "some value". When Clausal tries to
satisfy a goal it **unifies** variables with terms: if `A` is unbound and you unify
`A` with `"bob"`, then `A` becomes `"bob"` for the rest of that branch.

The **anonymous variable** `_` is a wildcard that matches anything and is never
reported in results:

```clausal
has_child(PERSON) <- parent(PERSON, _),
```

"PERSON has a child" — we don't care what the child's name is.

### How unification works

Unification is two-way pattern matching. When Clausal sees:

```clausal
parent("alice", CHILD)
```

it looks for facts of the form `parent("alice", something)` and binds `CHILD` to
each matching second argument in turn. No assignment, no mutation — each branch of
the search has its own consistent set of bindings.

---

## Lists

Lists are written with square brackets: `[]` (empty), `[1, 2, 3]`, `["a", "b"]`.
The head/tail pattern uses a star:

```clausal
first(HEAD, [HEAD, *_]),

rest(TAIL, [_, *TAIL]),
```

`[HEAD, *TAIL]` matches any non-empty list, binding `HEAD` to the first element and
`TAIL` to the remainder.

### In/2 and Append/3

These are built-in predicates. `In(X, LIST)` uses Python's `in` operator — it
succeeds once for each element of `LIST`:

```clausal
contains_three(LIST) <- In(3, LIST),
```

`Append(PREFIX, SUFFIX, WHOLE)` relates three lists such that `PREFIX` concatenated
with `SUFFIX` gives `WHOLE`. You can use it forwards (split a list) or backwards
(build one):

```clausal
last(ELEMENT, LIST) <- Append(_, [ELEMENT], LIST),
```

### Pattern matching on lists in clause heads

You can pattern-match directly in the head of a clause, which is often cleaner than
putting a pattern in the body:

```clausal
sum_list([], 0),
sum_list([HEAD, *TAIL], TOTAL) <- (
    sum_list(TAIL, SUBTOTAL),
    TOTAL := SUBTOTAL + HEAD
),
```

The first clause handles the empty list. The second peels off `HEAD`, recurses on
`TAIL`, and adds `HEAD` to the subtotal.

```clausal
double_list([], []),
double_list([HEAD, *TAIL], [DOUBLED, *REST]) <- (
    DOUBLED := HEAD * 2,
    double_list(TAIL, REST)
),
```

Each clause head matches a different list shape. Clausal tries them top-to-bottom and
backtracks if a match fails.

---

## Arithmetic

Use the **walrus operator** `(N := expression)` to evaluate an arithmetic expression
and unify the result with a variable:

```clausal
square(N, SQ) <- (SQ := N * N),

factorial(0, 1),
factorial(N, F) <- (
    N > 0,
    N1 := N - 1,
    factorial(N1, F1),
    F := N1 * F1 + F1
),
```

Supported operators: `+`, `-`, `*`, `/`, `//` (integer division), `**` (power),
`mod` (modulo), `abs(X)`, `min(X, Y)`, `max(X, Y)`.

### Comparisons

The standard comparison operators work directly as goals:

```clausal
positive(N) <- N > 0,
between(LOW, HIGH, N) <- (
    N >= LOW,
    N =< HIGH
),
```

Note: use `=<` for "less than or equal" (to avoid ambiguity with `<=` in Python
expressions). `<`, `>`, `>=` work as you'd expect. Use `=:=` and `=\=` to compare
arithmetic expressions for equality and inequality.

### A worked example: fizzbuzz

```clausal
fizzbuzz(N, "fizzbuzz") <- N mod 15 =:= 0,
fizzbuzz(N, "fizz")     <- N mod 3  =:= 0,
fizzbuzz(N, "buzz")     <- N mod 5  =:= 0,
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
safe_to_delete(FILE) <- not important(FILE),

different(X, Y) <- not (X = Y),
```

### When to use it

Negation as failure is appropriate when you want to express "there is no evidence
that...". It works correctly when all the relevant facts are already known — the
classic **closed-world assumption**.

```clausal
bachelor(PERSON) <- (
    male(PERSON),
    not married(PERSON)
),
```

If `married("alice")` is not in the database, `not married("alice")` succeeds.

### When not to use it

Avoid `not goal` when the variables inside `goal` are unbound. This query:

```clausal
not member(5, LIST)
```

will almost always fail, because Clausal can instantiate `LIST` to something that
contains 5. Instead, make sure any variables in the negated goal are already bound
before the `not`:

```clausal
no_fives(LIST) <- not member(5, LIST),
```

is fine when `LIST` is passed in fully instantiated; it is not a generator of lists
that avoid 5.

For constraint-based "not equal" on partially-instantiated terms, use `dif/2` from
the constraints module (see the [constraints guide](constraints.md)).

---

## Testing your code

Clausal has a lightweight convention for inline tests. Define `Test/1` predicates:

```clausal
Test("sum [1,2,3,4] = 10") <- (
    sum_list([1, 2, 3, 4], TOTAL),
    TOTAL = 10
),

Test("double [1,2,3] = [2,4,6]") <- (
    double_list([1, 2, 3], RESULT),
    RESULT = [2, 4, 6]
),

Test("fizzbuzz 15") <- (
    fizzbuzz(15, WORD),
    WORD = "fizzbuzz"
),
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

reachable(FROM, TO) <- edge(FROM, TO),

reachable(FROM, TO) <- (
    edge(FROM, MIDDLE),
    reachable(MIDDLE, TO)
),
```

There are two clauses for `reachable/2`: the base case (a direct edge) and the
recursive case (hop through an intermediate node). Clausal tries both clauses and
returns all paths.

Query it from Python:

```python
from graph import reachable
print(sorted(s["TO"] for s in clausal.query(reachable("a", TO))))
# ['b', 'c', 'd']
```

For large graphs with cycles, use the `-table` directive to enable tabling (memoised
search) — see [Tabling](tabling.md).

---

## Where to go next

- **[Syntax reference](syntax.md)** — full grammar, all operators, clause forms
- **[Constraints](constraints.md)** — `dif/2` for structural inequality; CLP(FD) for
  finite-domain constraint solving (N-queens, Sudoku, SEND+MORE=MONEY)
- **[DCGs](dcg.md)** — Definite Clause Grammars for parsing and string generation
- **[Examples](examples.md)** — worked examples: map colouring, Sudoku, graph
  algorithms, and more
- **[Predicate index](builtins.md)** — every built-in predicate with examples
