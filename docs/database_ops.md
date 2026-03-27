# Database Operations

Clausal supports runtime modification of the predicate database — adding and
removing clauses while a program is running. This enables dynamic state,
memoization, and self-modifying programs.

---

## Quick Example

```clausal
# skip
-dynamic(color/1)

color("red"),
color("blue"),

Test("assert and query") <- (
    assertz(color("green")),
    color("green")
)
```

---

## The `-dynamic` Directive

By default, predicates are **locked** after loading — you cannot add or remove
clauses at runtime. To allow runtime modification, declare the predicate as
dynamic (see [Directives](directives.md) for other directive types):

```clausal
# skip
-dynamic(counter/1)
-dynamic(cache/2)
```

Without this directive, `assertz` and `retract` will raise a permission error.

---

## Adding Clauses

### assertz/1

`assertz(Term)` — add a fact at the **end** of the clause list (like Prolog's
`assertz`).

```clausal
# skip
-dynamic(fact/1)

Test("assert") <- (
    assertz(fact(42)),
    fact(42)
)
```

### asserta/1

`asserta(Term)` — add a fact at the **beginning** of the clause list (like
Prolog's `asserta`). The new clause will be tried first on subsequent queries.

```clausal
# skip
-dynamic(priority/1)

priority("low"),

Test("assert first") <- (
    asserta(priority("high")),
    once(priority(X)),
    X == "high"
)
```

---

## Removing Clauses

### retract/1

`retract(Term)` — remove the first clause whose head unifies with `Term`.

```clausal
# skip
-dynamic(item/1)

item("a"),
item("b"),
item("c"),

Test("retract") <- (
    retract(item("b")),
    not item("b"),
    item("a"),
    item("c")
)
```

`retract` uses unification for matching, so you can retract by pattern:

```clausal
# skip
-dynamic(pair/2)

pair("x", 1),
pair("y", 2),
pair("z", 3),

Test("retract by pattern") <- (
    retract(pair("y", _)),
    not pair("y", 2)
)
```

---

## Table Management

### abolish_table/2

`abolish_table(functor, Arity)` — clear cached answers for a specific tabled
predicate.

```clausal
# skip
-table(memo_fib/2)

Test("clear") <- abolish_table("memo_fib", 2)
```

### abolish_all_tables/0

`abolish_all_tables()` — clear all tabling caches at once.

```clausal
Test("clear all") <- abolish_all_tables()
```

---

## Patterns & Recipes

### Memoization

Use assert to cache computed results:

```clausal
# skip
-dynamic(fib_cache/2)

fib(0, 0),
fib(1, 1),
fib(N, F) <- (
    N > 1,
    N1 == N - 1,
    N2 == N - 2,
    fib(N1, F1),
    fib(N2, F2),
    F == F1 + F2,
    assertz(fib_cache(N, F))
)
```

(For automatic memoization, consider [`-table`](tabling.md) instead.)

### Counter / mutable state

```clausal
# skip
-dynamic(counter/1)

counter(0),

increment(NEW) <- (
    retract(counter(OLD)),
    NEW == OLD + 1,
    assertz(counter(NEW))
),

Test("counter") <- (
    increment(1),
    increment(2),
    counter(2)
)
```

### Collecting facts from a computation

```clausal
# skip
-dynamic(result/1)

collect_evens(LIST) <- (
    in_(X, LIST),
    X % 2 == 0,
    assertz(result(X)),
    False
),
collect_evens(_)
```

(Prefer [`findall`](meta_predicates.md) for this pattern — it is cleaner and
does not require dynamic predicates.)

---

## Gotchas

- **Must declare `-dynamic`** — without it, assertz/retract raise a permission
  error. This is intentional: it prevents accidental modification of predicates
  that should be stable.
- **assertz adds facts, not rules** — `assertz(foo(X) <- bar(X))` is not
  supported. Only ground or partially-ground facts can be asserted.
- **retract removes one clause** — it removes the *first* matching clause only.
  Call it in a loop (or use `findall` + multiple retracts) to remove all
  matches.
- **Order matters** — `assertz` appends, `asserta` prepends. The clause
  order affects which solution is found first.
- **Tabling interaction** — if a tabled predicate depends on dynamic facts,
  remember to `abolish_table` after modifying the facts, or the cached answers
  will be stale.

---

*See also: [Directives](directives.md) — `-dynamic` and other predicate
directives, [Tabling](tabling.md) — automatic memoization with `-table`,
[Meta-Predicates](meta_predicates.md) — findall as an alternative to
assert-based collection.*
