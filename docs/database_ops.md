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

## Declare first: the `-dynamic` directive

`assertz`, `asserta` and `retract` work **only on a predicate declared
`-dynamic`**. Every other predicate is static once its module has loaded, as in
ISO Prolog: modifying it raises
`permission_error(modify, static_procedure, Name/Arity)`, with the builtin
as the culprit (Scryer's form; see [Exceptions](exceptions.md)).

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:declare_first"
```

The declaration also makes the predicate exist before it has clauses: a
`-dynamic` predicate with no clauses simply fails, where an undeclared name is
refused with the same `permission_error(modify, static_procedure, Name/Arity)`
(it is static by default). Declare several at once:

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:dynamic_directive"
```

See [Directives](directives.md) for the other directives.

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

Cache computed results in a dynamic predicate. Arithmetic goes through a
constraint (`N1 == N - 1`): a bare `X is N - 1` is unification and would
bind `X` to the unevaluated term (see [Operators](operators.md)).


```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:memoization_recipe"
```

(For automatic memoization, consider [`-table`](tabling.md) instead.)

### Counter / mutable state

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:counter_recipe"
```

### Collecting facts from a computation

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:collect_recipe"
```

(Prefer [`findall`](meta_predicates.md) for this pattern — it is cleaner and
does not require dynamic predicates.)

---

## Gotchas

- **Must declare `-dynamic`** — without it, assertz/asserta/retract raise
  `error(permission_error(modify, static_procedure, Name/Arity), assertz/1)`
  (catchable by `catch/3`). A name with no declaration and no clauses is
  refused too. To match the culprit in a catch pattern, quote it:
  `'/'('assertz', 1)` (a bare builtin name in a term is the builtin's object,
  not the atom).
- **assertz adds facts, not rules** — `assertz(foo(X) <- bar(X))` is not
  supported and raises `permission_error(assert, rule, Head)` at
  assert time (the predicate's existing clauses are left untouched). Only
  ground or partially-ground facts can be asserted.
- **Arity is part of the name** — `assertz(foo(a))` when only `foo/2` is
  declared dynamic is refused with
  `error(permission_error(modify, static_procedure, foo/1), assertz/1)`:
  `foo/1` is a different predicate, it is not declared, and an undeclared
  procedure is static (ISO 7.5.2).
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
