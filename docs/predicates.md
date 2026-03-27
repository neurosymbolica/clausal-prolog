# Predicates & Rules

Predicates are the core building block of Clausal programs. A predicate defines a **relation** between its arguments — it describes when something is true. Each predicate is defined by one or more **clauses**: either facts (unconditionally true) or rules (true when certain conditions hold). See [Thinking Relationally](thinking_relationally.md) for a deeper treatment of this idea.

---

## Quick Example

```clausal
# Facts: Edge/2 is true for these pairs
Edge(1, 2),
Edge(2, 3),
Edge(1, 3),

# Rule: Reach/2 is true when there is a path
Reach(X, Y) <- Edge(X, Y)
Reach(X, Y) <- (
    Edge(X, Z),
    Reach(Z, Y)
)
```

Query: `Reach(1, 3)` succeeds (both directly and via node 2).

---

## Facts

A fact is a clause with no body — it is unconditionally true. Facts end with a trailing comma:

```clausal
color(red, warm),
color(blue, cool),
color(green, cool),
```

Facts define the base data of your program. Think of them as rows in a database table.

Multiple facts for the same predicate are logical alternatives. Clausal searches for those that unify with the goal, in source order. `color(X, cool)` unifies with `color(blue, cool)` first, then `color(green, cool)`.

---

## Rules

A rule has a **head** (the conclusion) and a **body** (the conditions). The head holds when all conditions in the body hold:

```clausal
warm_color(C) <- color(C, warm)
```

Read this as: "C is a warm color if `color(C, warm)` holds."

### Multi-Goal Bodies

when a rule has multiple goals, they are comma-separated and wrapped in parentheses:

```clausal
friend_of_friend(A, C) <- (
    friend(A, B),
    friend(B, C),
    dif(A, C)
)
```

The conditions in the body must all hold for the head to hold. If a condition does not hold, Clausal explores the remaining clause alternatives.

---

## Clause Alternatives

A predicate can have multiple clauses — facts and rules mixed freely. These are logical alternatives; Clausal searches for those whose heads unify with the goal, in source order:

```clausal
factorial(0, 1),
factorial(N, F) <- (
    N > 0,
    N1 == N - 1,
    factorial(N1, F1),
    F == N1 * F1
)
```

The first clause states that the factorial of 0 is 1. The second clause states the recursive relationship: the factorial of N is F when N is positive, and F is N-1's factorial times N. These clauses are logical alternatives.

### Guards

Guards are conditions in the rule body that state when a clause holds:

```clausal
classify(N, "positive") <- (N > 0)
classify(0, "zero"),
classify(N, "negative") <- (N < 0)
```

The condition `N > 0` ensures the first clause only holds for positive numbers. Without it, the clause head would unify with any N.

### Clause Ordering

when multiple clause heads unify with the goal, Clausal explores them in source order:

```clausal
maximum(X, Y, X) <- (X >= Y)
maximum(X, Y, Y) <- (X < Y)

Test("max 3 5") <- (maximum(3, 5, R), R == 5)
Test("max 7 2") <- (maximum(7, 2, R), R == 7)
```

For `maximum(3, 5, R)`: the first clause's condition `3 >= 5` does not hold, so Clausal explores the second clause, which holds with `R = 5`.

---

## Worked Example: Family Tree to Reachability

Start with a simple family tree:

```clausal
parent("alice", "bob"),
parent("bob", "carol"),
parent("carol", "dave"),
```

**Direct parent query**: `parent("alice", "bob")` succeeds.

**Ancestor relation** — generalize parent to any depth:

```clausal
ancestor(X, Y) <- parent(X, Y)
ancestor(X, Y) <- (
    parent(X, Z),
    ancestor(Z, Y)
)
```

Now `ancestor("alice", "dave")` holds — the relation connects them through the chain alice → bob → carol → dave.

**Add metadata** — track the generation distance:

```clausal
ancestor(X, Y, 1) <- parent(X, Y)
ancestor(X, Y, N) <- (
    parent(X, Z),
    ancestor(Z, Y, N1),
    N == N1 + 1
)
```

`ancestor("alice", "dave", N)` yields `N = 3`.

This pattern — base case as a fact, recursive case as a rule — is the fundamental building block of Clausal programs.

---

## Recursive Predicates

Recursive predicates define relations over inductively structured data (like lists or natural numbers). The pattern is: a base clause and a recursive clause:

```clausal
length([], 0),
length([_, *REST], N) <- (
    length(REST, N1),
    N == N1 + 1
)

Test("length 0") <- length([], 0)
Test("length 3") <- (length([1, 2, 3], N), N == 3)
```

For [list](lists.md) relations, the base clause typically holds for the empty list `[]`, and the recursive clause relates a non-empty list `[HEAD, *TAIL]` to its parts (Clausal uses `*` for the tail, like Python).

---

## Private Predicates

The `-private` directive marks predicates as internal to the module — they are not exposed for import:

```clausal
-private([Helper(X, Y)])

# Public: can be imported by other modules
Compute(X, R) <- (
    Helper(X, TEMP),
    R == TEMP * 2
)

# Private: only accessible within this module
Helper(X, Y) <- (Y == X + 1)
```

Use `-private` when a predicate is an implementation detail that other modules should not depend on. This prevents accidental coupling between modules.

---

## Fields and Arity

Predicate fields are inferred from clause heads — no separate declaration needed:

```clausal
# point/2 has fields (arg0, arg1)
point(0, 0),
point(1, 1),

# distance/3 has fields (arg0, arg1, arg2)
distance(X1, X2, D) <- (D == abs(X2 - X1))
```

The **arity** is the number of fields. `point/2` means "point with 2 arguments." Different arities define different predicates: `foo/1` and `foo/2` are unrelated.

---

## Defining Predicates in `.clausal` Files

Clausal files use [Python syntax](syntax.md) with logic programming semantics:

```clausal
# Comments start with #

# Facts end with a comma
color(red, warm),
color(blue, cool),

# Rules use <- (implication arrow)
warm_color(C) <- color(C, warm)

# Multi-goal bodies are parenthesized, comma-separated
nice_color(C) <- (
    color(C, cool),
    C != blue
)
```

Files are loaded via Python's [import system](import.md). `import my_module` loads `my_module.clausal` and compiles all predicates.

---

## Python API (advanced)

> For most use cases, define predicates in `.clausal` files. This section covers the lower-level Python API for embedding or advanced use.

### PredicateMeta

Every predicate is a Python class with `PredicateMeta` as its metaclass. in_ `.clausal` files this is generated automatically from clause heads. For programmatic use:

```python
from clausal.logic.predicate import PredicateMeta

class fib(metaclass=PredicateMeta):
    _fields = ('n', 'result')
```

### Term Instances

Calling the class creates a term instance:

```python
fib(n=7, result=13)      # fully specified term
fib(n=7)                 # partial — result field gets a fresh Var()
fib()                    # all fields get fresh Var()
```

### Dynamic Predicate Creation

```python
from clausal import make_predicate

foo = make_predicate("foo", ["a", "b"])
```

### Locking

Predicates are locked after module loading — `assertz`/`retract` raise `RuntimeError`. Use `-dynamic(pred/arity)` to allow runtime modification. See [Directives](directives.md) and [Database Operations](database_ops.md).

---

??? info "Test coverage"

    - `tests/test_compiled_programs.py` (41 tests): graph reachability, fibonacci, N-queens, NAF
    - `tests/test_predicate_meta.py` (53 tests): PredicateMeta class behavior
    - `tests/fixtures/edge_graph.clausal`: example fact + rule predicate file

---

*See also: [Directives](directives.md) — `-dynamic`, `-table`, `-private`, and other predicate property declarations.*
*See also: [If-Then-Else](reified_ite.md) — conditional expressions within rule bodies.*
*See also: [Lambdas](lambdas.md) — anonymous predicates (goal closures).*
