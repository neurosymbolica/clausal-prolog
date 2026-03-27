# Thinking Relationally

This page introduces the most important idea in logic programming: **thinking
in terms of relations**. If you absorb one thing from this documentation, let
it be this.

!!! note "Clausal vs Prolog syntax"

    Clausal and Prolog syntax may slightly differ — for example, variables are
    `ALLCAPS`, rules use `<-` instead of `:-`, and lists are Python-style. Keep
    this in mind when comparing with Prolog resources.

In Clausal, every predicate defines a relation between its arguments. A
relation is not a function — it has no fixed inputs or outputs. A relation
simply *holds* or *doesn't hold* for a given combination of arguments. This
shift in perspective — from "what does the program do?" to "when does this
relation hold?" — is what gives logic programming its extraordinary power.

---

## What is a relation?

A relation is a set of tuples for which a statement is true.

```clausal
parent("alice", "bob"),
parent("alice", "carol"),
parent("bob", "dave"),
```

Each fact states that the `parent` relation holds between two people. This is
not an assignment. It is not a function call. It is a **declaration**: "it is
true that alice is a parent of bob."

A predicate with a body extends the relation with conditions:

```clausal
grandparent(X, Z) <- (
    parent(X, Y),
    parent(Y, Z)
)
```

Read this as: "the grandparent relation holds between X and Z when there exists
some Y such that the parent relation holds between X and Y, and the parent
relation holds between Y and Z."

Our job as logic programmers is to state what holds under what conditions.
This is declarative programming — we describe the situation, and we leave it to
the system to derive logical consequences of our description.

---

## Relations vs. functions

A function maps inputs to outputs. It has a fixed direction: you provide
arguments, it produces a result. A relation has no such restriction.

Consider `Append/3`, which relates three lists:

```clausal
Test("concatenate") <- Append([1, 2], [3, 4], [1, 2, 3, 4])

Test("split") <- (
    Append(LEFT, RIGHT, [1, 2, 3]),
    LEFT == [1],
    RIGHT == [2, 3]
)

Test("suffix") <- Append([1, 2], REST, [1, 2, 3, 4, 5])
```

The same definition of `Append/3` can:

- **Concatenate**: given the first two lists, find the third
- **Split**: given the third list, enumerate all ways to divide it into two
- **Verify**: given all three lists, confirm they are related
- **Generate**: given partial information, enumerate completions

If we said `Append` "concatenates two lists," we would only capture one of
these modes. The other three would be invisible — not because the code can't do
them, but because our description limited our thinking.

This is why we say `Append/3` **describes the relation** between a prefix, a
suffix, and their concatenation. This wording captures all usage modes.

---

## The key question: "When does this hold?"

When writing a predicate, the wrong question is: "What should the program do in
this case?"

The right question is: **"What are the conditions that make this relation true
for its arguments?"**

Consider `list_sum/2`:

```clausal
list_sum([], 0),
list_sum([HEAD, *TAIL], TOTAL) <- (
    list_sum(TAIL, SUBTOTAL),
    TOTAL == SUBTOTAL + HEAD
)
```

Read this declaratively:

- The sum of the empty list is 0.
- The sum of a list [HEAD, *TAIL] is TOTAL when the sum of TAIL is SUBTOTAL
  and TOTAL is SUBTOTAL + HEAD.

These are **statements about when the relation holds**, not instructions for
what to do. This way of reading the code does justice to its full generality —
we can use it to compute a sum, to verify a sum, or (with CLP(ℤ) constraints)
to reason about partially-known lists.

---

## The most general query

A query where all arguments are fresh variables is called the **most general
query**. It asks: for which arguments does the predicate hold at all?

```python
# The most general query for list_sum
list(clausal.query(list_sum(LIST, SUM)))
```

This asks: "Are there any lists and sums for which `list_sum` holds?" A truly
relational predicate gives meaningful answers to its most general query.

When working with Clausal programs, it is often a good idea to try the most
general query to see which solutions exist in general. It reveals whether a
predicate is genuinely relational or secretly directional.

If the most general query raises an error or gives no answers, it often means
the predicate depends on certain arguments being ground — a sign that it could
be made more general.

---

## Reading clauses declaratively

Every clause can be read as a logical statement. This is called the
**declarative reading**, and it is the primary way to understand Clausal code.

### Facts

A fact is a clause with no body. It states something that is unconditionally
true:

```clausal
edge("a", "b"),
```

Read: "It is true that the edge relation holds between 'a' and 'b'."

### Rules

A rule has a head and a body. The head holds when all conditions in the body
hold:

```clausal
reachable(X, Y) <- edge(X, Y)
reachable(X, Y) <- (
    edge(X, Z),
    reachable(Z, Y)
)
```

Read the first clause: "X and Y are reachable if there is an edge from X to Y."

Read the second clause: "X and Y are reachable if there is an edge from X to
some Z and Z and Y are reachable."

### Clauses are logical alternatives

Multiple clauses for the same predicate are **logical alternatives**: if *any*
clause is true, the whole predicate is true. They are not cases in a switch
statement. They are not tried and discarded. They are different conditions under
which the same relation holds.

### Avoid procedural reading

The alternative to declarative reading is *procedural reading*: mentally
tracing what the system does step by step. This is almost always a mistake.

Procedural reading is too hard to apply correctly — it requires understanding
the precise steps the system performs at every point. And it doesn't capture
the full generality of the code, because it only traces one particular mode of
use. If you slightly change the program or the query, you have to trace the
steps all over again.

Worse, procedural reading is counterproductive: it encourages thinking about
predicates as procedures, which takes you away from the true generality of
logic programming.

Declarative reading scales. Procedural reading does not.

---

## Why this matters

### Generality

A single relational definition can be used in multiple ways — to compute, to
verify, to generate, to complete. We say we are *describing* a relation because
it would not do the code justice to say we only compute or only generate. We
have a general description and we can use it in different modes.

### Correctness and reasoning

Pure, relational predicates can be reasoned about declaratively:

- Adding a condition in the body can only *reduce* the set of solutions, never
  increase it.
- Removing a condition can only *extend* the set of solutions.
- Clauses can be read and understood in isolation.

These properties — collectively called **monotonicity** — make it possible to
locate mistakes by reasoning about the code, rather than by tracing execution.
See [Purity and Monotonicity](purity.md) for a deeper treatment.

### Testability

Tests for relational predicates are simply queries that should hold or not
hold. No mock objects, no test harnesses, no elaborate setup. A test is just a
fact about the relation:

```clausal
Test("sum of [1,2,3] is 6") <- list_sum([1, 2, 3], 6)
Test("sum of [] is 0") <- list_sum([], 0)
```

### Working with reasoning, not against it

A decisive property of good Clausal code is that it can be reasoned about in
several ways: by posting queries, by writing test cases, by generalizing and
specializing queries and programs to find out more and to locate mistakes. Code
that undermines these properties — by using side effects, by depending on
evaluation order, by testing instantiation — works *against* reasoning and
sacrifices the core advantages of logic programming.

---

## Naming predicates relationally

The name of a predicate should describe what its arguments are and how they
relate to each other — not what the predicate "does" in one particular mode.

An imperative name like `get_length` or `compute_sum` suggests a direction:
you provide a list, you get a number. But the relation holds between a list
and a number regardless of which is known. The name should capture this.

| Imperative name | Relational name | Why better |
|---|---|---|
| `get_length(List, N)` | `list_length(LIST, N)` | Names what is related |
| `compute_sum(List, S)` | `list_sum(LIST, SUM)` | No verb implies direction |
| `find_path(A, B, P)` | `path(A, B, P)` | The predicate IS the relation |
| `remove(X, L, R)` | `list_without(LIST, ELEM, REST)` | Not imperative |
| `flatten(Nested, Flat)` | `nested_flat(NESTED, FLAT)` | Names both arguments |

A name like "flatten" is already problematic because it is an imperative —
thinking about the relation imperatively limits what we can describe with it.

For auxiliary predicates with extra arguments (like accumulators), a useful
convention is to append an underscore to indicate there are additional
arguments that are not part of the name.

---

## "How not what"

A common characterization of declarative programming is "what, not how" — you
say *what* you want, not *how* to get it. But this does not adequately capture
what makes logic programming special.

In fact, the opposite is closer to the truth: **how, not what** — because it
matters *how* we express our task, not *what* is being executed. A well-chosen
representation, good naming, and relational framing are not cosmetic choices.
They determine whether the code can be used in all directions, whether it can
be reasoned about, and whether it can be combined with other code in ways we
didn't anticipate.

The *form* of the description is the substance. This is why this page exists.

---

## Common traps for imperative programmers

**Thinking of clauses as cases in a switch statement.** They are logical
alternatives. If any clause is true, the predicate is true. Clauses don't
"fall through" — they represent independent conditions under which the relation
holds.

**Thinking of the body as steps to execute.** The body states conditions that
must hold. The comma between goals means "and," not "then." The order of goals
affects efficiency and termination, but not the logical meaning (in pure code).

**Thinking of variables as slots to fill.** Logic variables are unknowns that
participate in unification. They can be bound on either side — in the goal or
in the clause head. This bidirectionality is what makes relations work in all
directions.

**Using eager evaluation when constraints would be more general.** The
`:=` operator requires the right-hand side to be ground. Use `==` instead —
it posts CLP(ℤ) constraints that work with unbound variables and preserve
multi-directional use. Reserve `:=` for Python interop (e.g., `++` for strings).

**Naming predicates with verbs that imply a direction.** "Find," "get,"
"compute," "check," "remove" — all suggest a specific mode. Describe what the
arguments are and how they relate instead.

**Trying to understand execution at a low level.** You do not need to know
about choice points, stack frames, or tail call optimization to write excellent
Clausal code. Elegant, general, efficient, easy-to-understand code comes from
following a few basic principles — chief among them: think in terms of
relations.

---

*See also: [Purity and Monotonicity](purity.md) — why pure code has better
properties and how to write it.*

*See also: [Tutorial](tutorial.md) — learn Clausal by example.*
