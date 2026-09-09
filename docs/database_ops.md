# Database Operations

Clausal supports runtime modification of the predicate database — adding and
removing clauses while a program is running. This enables dynamic state,
memoization, and self-modifying programs.

---

## Quick Example

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:quick_example"
```

---

## The `-dynamic` Directive

By default, predicates are **locked** after loading — you cannot add or remove
clauses at runtime. To allow runtime modification, declare the predicate as
dynamic (see [Directives](directives.md) for other directive types):

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:dynamic_directive"
```

Without this directive, `assertz` and `retract` will raise a permission error.

---

## Adding Clauses

### assertz/1

`assertz(Term)` — add a fact at the **end** of the clause list (like Prolog's
`assertz`).

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:assertz_example"
```

### asserta/1

`asserta(Term)` — add a fact at the **beginning** of the clause list (like
Prolog's `asserta`). The new clause will be tried first on subsequent queries.

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:asserta_example"
```

---

## Removing Clauses

### retract/1

`retract(Term)` — remove the first clause whose head unifies with `Term`.

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:retract_example"
```

`retract` uses unification for matching, so you can retract by pattern:

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:retract_pattern"
```

---

## Table Management

### abolish_table/2

`abolish_table(functor, Arity)` — clear cached answers for a specific tabled
predicate.

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:abolish_table_example"
```

### abolish_all_tables/0

`abolish_all_tables()` — clear all tabling caches at once.

```clausal
test("clear all") <- abolish_all_tables()
```

---

## Patterns & Recipes

### Memoization

Use assert to cache computed results:

```clausal
--8<-- "tests/fixtures/docs/database_ops_sigs.txt:memoization_recipe"
```

(For automatic memoization, consider [`-table`](tabling.md) instead.)

### Counter / mutable state

```clausal
--8<-- "tests/fixtures/docs/database_ops_sigs.txt:counter_recipe"
```

### Collecting facts from a computation

```clausal
--8<-- "tests/fixtures/docs/database_ops_sigs.txt:collect_recipe"
```

(Prefer [`findall`](meta_predicates.md) for this pattern — it is cleaner and
does not require dynamic predicates.)

---

## Gotchas

- **Must declare `-dynamic`** — without it, assertz/asserta/retract raise a
  typed `permission_error(modify, static_procedure, Name/Arity)` (catchable by
  `catch/3`). This is intentional: it prevents accidental modification of
  predicates that should be stable.
- **assertz adds facts, not rules** — `assertz(foo(X) <- bar(X))` is not
  supported and raises a typed `permission_error(assert, rule, Head)` at
  assert time (the predicate's existing clauses are left untouched). Only
  ground or partially-ground facts can be asserted.
- **assertz keeps the partial-term rule** — `assertz(foo(a))` against a
  `foo/2` predicate asserts `foo(a, _)`, an open fact whose second field
  matches anything. A clause head *written in a file* at the wrong arity is
  refused at load (see [Predicates](predicates.md)), but at assert time
  `foo(a)` and `foo(a, _)` are the same already-built term — the argument
  count the author wrote is gone — so no refusal is possible here. Spell the
  open field as `_` to make the intent visible.
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
