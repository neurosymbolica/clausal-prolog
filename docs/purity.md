# Purity and Monotonicity

This page explains *why* certain patterns in logic programming are preferred
over others, and what concrete properties you gain by staying within the
**pure monotonic core** of Clausal Prolog.

If [Thinking Relationally](thinking_relationally.md) is about the mindset,
this page is about the discipline that makes the mindset pay off.

!!! note "Seam vs Prolog syntax"

    Examples on this page use seam syntax (`.seam`), which differs slightly from
    Prolog's — for example, variables are `ALLCAPS`, rules use `<-` instead of
    `:-`, and lists are Python-style. Keep this in mind when comparing with
    Prolog resources. [Clausal Prolog](clausal_prolog.md) (`.clausal`) uses ISO
    Prolog syntax.

---

## What is logical purity?

A predicate is **pure** if the set of ground instances for which it holds fully
determines its behavior. Informally: a pure predicate has the properties we
expect from a relation. It does not perform destructive changes and does not
have side effects.

Pure predicates:

- Can be used in **all directions** — any argument may be a variable,
  partially instantiated, or fully ground
- Can have their **clauses reordered** without changing the set of solutions
- Can have **goals in the body reordered** without changing the set of
  solutions (modulo termination)
- Are automatically **thread-safe**
- Can be **reasoned about** declaratively — each clause can be read and
  understood in isolation

Clausal Prolog has a pure monotonic core, and you automatically get all of these
desirable properties as long as you stay within it.

---

## The four key properties

The pure monotonic core of Clausal Prolog guarantees four properties that make
declarative reasoning possible.

### 1. Monotonicity

Adding a constraint can at most yield **fewer** solutions, never more.
Removing a constraint can at most yield **more** solutions, never fewer.

This is the most important property. It means you can reason about your
program by adding and removing goals:

- If a predicate gives too many answers, add a condition to narrow it down.
- If a predicate gives too few answers (or none), remove a condition to find
  which one is too restrictive.

```seam
-allow_singletons
# These three queries are in order of increasing specificity: X stays
# unbound in the first Test on purpose — that's what makes it "the most
# general query" (see for_prolog_programmers.md).
# The most general query — every element of the list
test("general") <- in_(X, [1, 2, 3])

# More specific — only elements of [1, 2, 3] greater than 1
test("specific") <- (in_(X, [1, 2, 3]), X > 1)

# Even more specific — only 2
test("most specific") <- in_(2, [1, 2, 3])
```

Each additional constraint can only reduce the set of solutions. This is
monotonicity, and it is the foundation of declarative debugging.

### 2. Commutativity of conjunction

`A, B` means the same as `B, A`. You can exchange goals, and the set of
solutions stays the same. (Termination behavior may differ, but the *logical*
meaning does not.)

This property allows automatic reordering of goals for optimization — and it
means the reader can understand each goal independently without worrying about
execution order.

### 3. Idempotency

Stating a goal once means the same as stating it several times. With this
property, duplicated or logically entailed goals can be eliminated
automatically.

### 4. Separability

Clauses and predicates can be read and reasoned about **in isolation**. You
do not need to read the entire program to understand a single clause.

This property is what makes large logic programs manageable. It is also what
makes Clausal Prolog's [import system](import.md) meaningful — a predicate imported from another
module can be understood from its definition alone.

---

## What breaks purity

The power of logic programming is rooted in the logical properties listed
above. when these properties are violated, the core advantages are lost.

### Negation as failure with unbound variables

`not goal` is negation as failure: it holds when `goal` has no solutions.
This is **not monotonic** — adding information (binding a variable) can cause
a previously successful negation to fail.

```seam
# Dangerous: X is unbound, so not in_(X, [1,2,3]) may behave unexpectedly
risky(X) <- (not in_(X, [1, 2, 3]))

# Commutativity is lost: the order of the goals changes the answer
test("bind first") <- (X is 5, risky(X))         # succeeds
test("negate first") <- (not (risky(X), X is 5))  # risky(X) fails while X is unbound
```

For disequality with unbound variables, use [`dif/2`](constraints.md) (`is not`) instead — it
is a monotonic constraint that survives and is rechecked as variables become
bound:

```seam
# Safe: dif is a constraint, not a point-in-time check
safe(X) <- (X is not 1, X is not 2)

test("dif survives") <- (safe(X), X is 3)          # X = 3
test("dif rechecks") <- (not (safe(X), X is 1))    # binding X to 1 later fails
```

### Arithmetic with `==`

The `==` operator posts [CLP(ℤ)](constraints.md) constraints that work in all directions,
even when variables are unbound:

```seam
# Works in all directions:
square(N, SQ) <- (SQ == N * N)
```

`eval_/2` and `is` with a `++` escape are available for eager Python-side
evaluation (e.g., string operations), but `==` should be the default for arithmetic.

### I/O side effects

Writing output (see [I/O](io.md)), reading files, and sending network requests are inherently
non-monotonic — they have effects that cannot be undone on backtracking.

The mitigation is to **describe output declaratively as a term, then emit it
as the very last step**. If the output exists only on the terminal, you cannot
easily reason about it. If it exists as a term, you can test it, transform it,
and reason about it with the full power of logic programming.

```seam
# Describe the output as a term (an f-string builds the text in one step):
greeting_text(NAME, TEXT) <- (
    TEXT is f"Hello, {NAME}!"
)

# Test it without side effects:
test("greeting") <- greeting_text('world', "Hello, world!")

# Emit it only at the boundary:
greet(NAME) <- (
    greeting_text(NAME, TEXT),
    writeln_text(TEXT)
)
```

### assertz/retract at runtime

Dynamically [adding or removing clauses](database_ops.md) breaks separability — the meaning of a
predicate now depends on what has happened during execution, not just on its
definition. Use dynamic predicates only when genuinely needed (e.g., caching,
configuration), and be aware that they move you outside the pure core.

---

## Monotonic alternatives in Clausal Prolog

Many common impure patterns have pure counterparts in Clausal Prolog:

| Impure pattern | Pure alternative | Why better |
|---|---|---|
| `not (X is Y)` (immediate check) | `X is not Y` (dif constraint) | Monotonic; works with unbound variables |
| `N > 0` (arithmetic guard) | `N #> 0` (CLP(ℤ) constraint) | Works in all directions |
| `eval_/2` (eager evaluation) | `==` (CLP(ℤ) constraint) | Works with unbound variables |
| `not Goal` with unbound vars | Reified if-then-else | Monotonic; see [If-Then-Else](reified_ite.md) |
| Type-testing (`integer(X)`) | Clean representations | Symbolic distinction via functors; see [below](#clean-vs-defaulty-representations) |

### Clean vs. defaulty representations

A **clean** representation lets you distinguish all cases symbolically by the
principal functor of a term. A **defaulty** representation requires guards or
type tests to distinguish cases.

```seam
# Defaulty: need a guard to tell if the value is special
handle(0, 'zero'),
handle(N, 'positive') <- (N > 0)
handle(N, 'negative') <- (N < 0)

# Clean: cases are distinguished by the functor — the wrapped value
# doesn't matter here, only which functor it's wrapped in
-private([zero, positive(n), negative(n)])

classify(zero, 'zero'),
classify(positive(_), 'positive'),
classify(negative(_), 'negative'),
```

Clean representations are not only good for semantic reasons — they also enable
[argument indexing](indexing.md), which avoids redundant choice points and enables tail call
optimization. Correctness and efficiency go hand in hand.

---

## Declarative debugging

when a pure predicate gives wrong answers, you can locate the mistake without
tracing execution.

### Too many answers (program is too general)

The predicate holds for cases where it shouldn't. Add constraints to narrow
down which clause is responsible:

1. Start with a query that produces an incorrect answer.
2. Add a constraint that rules out the incorrect answer.
3. If the correct answers are still produced, the problem is in a clause that
   was eliminated. If correct answers are also lost, the problem is elsewhere.
4. Repeat, narrowing down to the specific clause.

### Too few answers (program is too specific)

The predicate fails when it should hold. Generalize the program to find which
condition is too restrictive:

1. Start with a query that should hold but doesn't.
2. Remove a goal from the body of a clause.
3. If the query now holds, the removed goal was too restrictive.
4. If it still doesn't hold, restore the goal and try removing a different one.

This technique — called **failure slicing** — was developed by Ulrich
Neumerkel. It works because of monotonicity: removing a goal can only make a
program more general, never more specific. This guarantee only holds for pure,
monotonic code.

---

## Algorithm = Logic + Control

A logic program can be decomposed into two parts:

- **Logic**: what must hold for a solution — the conditions, the constraints,
  the relations
- **Control**: how to search for solutions — the order of exploration, the
  labeling strategy

Our goal as programmers is to state the logic as clearly as we can. The
control can be changed flexibly, independently of the logic.

This separation is a major attraction of logic programming, and it only works
within the pure monotonic core. Consider the N-Queens problem:

```seam
# Logic: describe what must hold
n_queens(N, QUEENS) <- (
    length(QUEENS, N),
    in_domain(QUEENS, 1, N),
    all_different(QUEENS),
    safe_queens(QUEENS)
)

safe_queens([]),
safe_queens([Q, *QS]) <- (
    no_attack(Q, QS, 1),
    safe_queens(QS)
)

no_attack(_Q, [], _D),
no_attack(Q, [Q1, *QS], D) <- (
    Q != Q1 + D,
    Q != Q1 - D,
    D1 == D + 1,
    no_attack(Q, QS, D1)
)

# Control: choose how to search
test("8 queens") <- (
    n_queens(8, QUEENS),
    label(QUEENS)
)
```

The same `n_queens/2` definition can be searched in different ways — `label/1`
(first-fail order), or handing the posted constraints to another solver — without
changing the logic. The logic specifies *what* must hold; the labeling specifies *how*
to search. This decoupling makes the approach flexible and versatile.

---

## Practical guidance

1. **Use `==` (CLP(ℤ) constraints) for arithmetic.** Constraints
   work in all directions and preserve multi-directional use. Reserve `eval_/2`
   and `++` escapes for Python interop (e.g., string operations).

2. **Use `dif/2` (`is not`) instead of `not (X is Y)`.** dif is a monotonic
   constraint; negation-of-unification is a point-in-time check.

3. **Use reified if-then-else instead of negation as failure for conditional
   logic.** See [If-Then-Else](reified_ite.md).

4. **Name predicates relationally.** Describe what the arguments are and how
   they relate. See [Thinking Relationally](thinking_relationally.md).

5. **Test with the most general query.** If your predicate gives meaningful
   answers when all arguments are variables, it is truly relational.

6. **Describe output as terms, emit as the last step.** Keep the description
   pure and testable; confine side effects to the boundary.

7. **Use clean representations.** Distinguish cases by functor, not by guards
   or type tests. This is good for correctness and for performance.

8. **Stay in the pure monotonic core.** You automatically get monotonicity,
   commutativity, idempotency, and separability. These properties make your
   code easier to understand, test, debug, and optimize.

---

*See also: [Thinking Relationally](thinking_relationally.md) — the mindset
behind pure logic programming.*

*See also: [Constraints](constraints.md) — dif/2, CLP(ℤ), CLP(B), CLP(ℝ).*

*See also: [If-Then-Else](reified_ite.md) — monotonic conditional
expressions.*
