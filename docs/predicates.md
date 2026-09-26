# Predicates & Rules

Predicates are the core building block of Clausal programs. A predicate defines a **relation** between its arguments — it describes when something is true. Each predicate is defined by one or more **clauses**: either facts (unconditionally true) or rules (true when certain conditions hold). See [Thinking Relationally](thinking_relationally.md) for a deeper treatment of this idea.

---

## Quick Example

```clausal
# Facts: edge/2 is true for these pairs
edge(1, 2),
edge(2, 3),
edge(1, 3),

# Rule: reach/2 is true when there is a path
reach(X, Y) <- edge(X, Y)
reach(X, Y) <- (
    edge(X, Z),
    reach(Z, Y)
)
```

Query: `reach(1, 3)` succeeds (both directly and via node 2).

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
classify(N, 'positive') <- (N > 0)
classify(0, 'zero'),
classify(N, 'negative') <- (N < 0)
```

The condition `N > 0` ensures the first clause only holds for positive numbers. Without it, the clause head would unify with any N.

### Clause Ordering

when multiple clause heads unify with the goal, Clausal explores them in source order:

```clausal
maximum(X, Y, X) <- (X >= Y)
maximum(X, Y, Y) <- (X < Y)

test("max 3 5") <- (maximum(3, 5, R), R == 5)
test("max 7 2") <- (maximum(7, 2, R), R == 7)
```

For `maximum(3, 5, R)`: the first clause's condition `3 >= 5` does not hold, so Clausal explores the second clause, which holds with `R = 5`.

---

## Worked Example: Family Tree to Reachability

Start with a simple family tree:

```clausal
parent('alice', 'bob'),
parent('bob', 'carol'),
parent('carol', 'dave'),
```

**Direct parent query**: `parent('alice', 'bob')` succeeds.

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

test("length 0") <- length([], 0)
test("length 3") <- (length([1, 2, 3], N), N == 3)
```

For [list](lists.md) relations, the base clause typically holds for the empty list `[]`, and the recursive clause relates a non-empty list `[HEAD, *TAIL]` to its parts (Clausal uses `*` for the tail, like Python).

---

## Private Predicates

The `-private` directive marks predicates as internal to the module — not part of the surface other modules are meant to build on:

```clausal
-private([helper(X, Y)])

# Documented surface: other modules are meant to call this
compute(X, R) <- (
    helper(X, TEMP),
    R == TEMP * 2
)

# Internal: an implementation detail of compute/2
helper(X, Y) <- (Y == X + 1)
```

Use `-private` when a predicate is an implementation detail that other modules should not depend on.

!!! warning "`-private` is advisory, not enforced"
    A `-private` predicate is **still importable**. `-import_from(this_module, [helper])` succeeds and binds this module's `helper` predicate (its handle). Clausal has no access control — the marker discourages coupling, it does not prevent it, exactly like a leading underscore in Python. See [Directives § `-private`](directives.md#-private) for the full meaning of the directive.

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

Unrelated, but not both definable **in one file**: there a name has exactly one
arity, and writing `foo(a, b),` and `foo(a),` together does not give you `foo/2`
and `foo/1`.

Both orders fail at load, naming both sites and telling you to rename one of
them:

- Shorter head first (`foo(a),` then `foo(a, b),`): *functor foo/2 conflicts
  with the declaration of foo/1 in the same file*.
- Longer head first (`foo(a, b),` then `foo(a),`): *functor foo/1 conflicts
  with the declaration of foo/2 in the same file* — a clause head is not a
  partial term, so the short head is refused rather than silently padded to
  `foo(a, _)` and absorbed into `foo/2` (which is what happened before this
  check: the padded clause matched `foo(a, ANYTHING)` and no `foo/1` ever
  existed). A padded position that really means "anything" must be spelled
  `_`; a head that names only *some* fields by keyword (`foo(a=1),`) stays
  legal, because there the unbound remainder is explicit.

The partial-term rule (`citation(REF)` in argument position builds a term with
a fresh variable) still holds everywhere *except* a clause head. Two arities
of one name are kept genuinely separate only in separate modules.

Calling a predicate at an arity it does not have is an error, and it is reported
as one:

```
citation takes 3 arguments, but this call passes 2
  citation/3 is defined at citations.clausal:14.
  -> pass 3 arguments to citation, or give the 2-argument predicate a
     different name: a second citation head with 2 arguments in the same file
     does not define citation/2 — one name has one arity, and the head is
     refused at load.
```

This is a `PredicateArityMismatchError`, which is a `TypeError` and, since
2026-09-25, also a `LogicException` carrying the ISO term Scryer raises for the
same call: `error(existence_error(procedure, citation/2), Message)` -- the
indicator at the *called* arity, the message above as the context. So
`catch(G, error(existence_error(procedure, PI), _), Recovery)` catches it, as do
`except TypeError` in Python and a `++TypeError` catcher. If the name is
not in scope at *any* arity, the failure is a `PredicateNotFoundError` instead
and the message lists what is reachable — see [Importing](import.md).

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

### Predicates from Python

A loaded module's attribute for a predicate is the predicate's **handle**: a
`str` naming the module that owns it and the predicate. It names the
predicate; it is not a class and not something to call. To run a predicate,
build a goal **cell** — its name followed by its arguments — and pass the
module (see [Querying from Python](python_integration.md#querying-from-python)):

```python
from clausal import Var, solve
from clausal.examples import fibonacci

for trail in solve(("fib", 10, F := Var()), module=fibonacci):
    print(F.value)  # 55
```

### Rows and signatures

A predicate's state — its clauses, its compiled dispatch, whether it is
locked — lives on its row in the module's `Database`, and its field names are
recorded there too. Ask the database, by name and arity:

```python
from clausal.examples import fibonacci
from clausal.logic.predicate import resolve_predicate_row

db = fibonacci.__clausal_module__.db
row = db.row("fib", 2)
row.locked                       # True  — not declared -dynamic
len(row.clauses)                 # 3
db.field_names_at("fib", 2)      # ('N', 'F') — from the -module declaration

# From a handle, e.g. one a module imported: the OWNER's row
resolve_predicate_row(fibonacci.fib, arity=2) is row   # True
```

### Locking

Predicates are locked after module loading — `assertz`/`retract` on one raise the ISO `permission_error(modify, static_procedure, Name/Arity)`. Use `-dynamic(pred/arity)` to allow runtime modification; from Python, run the builtin as a goal: `once(("assertz", ("counter", 1)), module=m)`. See [Directives](directives.md) and [Database Operations](database_ops.md).

---

??? info "Test coverage"

    - `tests/test_compiled_programs.py` (41 tests): graph reachability, fibonacci, N-queens, NAF
    - `tests/test_predicate_meta.py` (53 tests): PredicateMeta class behavior
    - `tests/fixtures/edge_graph.clausal`: example fact + rule predicate file

---

*See also: [Directives](directives.md) — `-dynamic`, `-table`, `-private`, and other predicate property declarations.*
*See also: [If-Then-Else](reified_ite.md) — conditional expressions within rule bodies.*
*See also: [Lambdas](lambdas.md) — anonymous predicates (goal closures).*
