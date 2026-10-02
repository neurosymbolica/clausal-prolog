# Database Operations

Clausal supports runtime modification of the predicate database — adding and
removing clauses while a program is running. This enables dynamic state,
memoization, and self-modifying programs.

---

## Quick Example

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:quick_example"
```

---

## Declare first: the `-dynamic` directive

`assertz`, `asserta` and `retract` work **only on a predicate declared
`-dynamic`**. Every other predicate is static once its module has loaded, as in
ISO Prolog: modifying it raises
`permission_error(modify, static_procedure, Name/Arity)`, with the builtin
as the culprit (Scryer's form; see [Exceptions](exceptions.md)).

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:declare_first"
```

The declaration also makes the predicate exist before it has clauses: a
`-dynamic` predicate with no clauses simply fails, where an undeclared name is
refused with the same `permission_error(modify, static_procedure, Name/Arity)`
(it is static by default). The module flag
[`assert_creates_dynamic`](flags.md#assert_creates_dynamic) changes that last
case to ISO 7.5.2(2): with it `true`, asserting into a procedure that does not
exist creates it as a dynamic procedure. An imported `.pl` module has it on.
Declare several at once:

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:dynamic_directive"
```

See [Directives](directives.md) for the other directives.

### From Python: `Module.declare_dynamic`

A `Module` built from Python has no directives, so declare its dynamic
predicates with `Module.declare_dynamic(name, arity)`, the same declaration
as `-dynamic(name/arity)`. It also works on the `Module` of a loaded
`.clausal` file (`mod.__clausal_module__`).

```python
from clausal import Module, Var, solve

m = Module("counter")
m.declare_dynamic("count", 1)          # -dynamic(count/1)
list(solve(("assertz", ("count", 0)), module=m))
n = Var()
[n.value for _ in solve(("count", n), module=m)]    # [0]
```

It is idempotent. Its errors are ISO `dynamic/1`'s, raised as a
`LogicException` whose culprit is `dynamic/1`: `instantiation_error` for an
unbound argument, `type_error(atom, Name)`, `type_error(integer, Arity)`,
`domain_error(not_less_than_zero, Arity)`, and
`permission_error(modify, static_procedure, Name/Arity)` for a builtin or a
static predicate that already has clauses.

---

## Adding Clauses

### assertz/1

`assertz(Term)` — add a fact at the **end** of the clause list (like Prolog's
`assertz`).

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:assertz_example"
```

### asserta/1

`asserta(Term)` — add a fact at the **beginning** of the clause list (like
Prolog's `asserta`). The new clause will be tried first on subsequent queries.

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:asserta_example"
```

---

## Removing Clauses

### retract/1

`retract(Term)` — remove the first clause whose head unifies with `Term`.

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:retract_example"
```

As in ISO (8.9.3) and Scryer, `retract` of a name nothing declares simply
fails — there is no clause to remove — while a static predicate, a declared
data functor or a builtin raises
`error(permission_error(modify, static_procedure, Name/Arity), retract/1)`, and
an unbound `Term` raises `instantiation_error`. (`retractall/1` and
`abolish/1` are not provided.)

`retract` uses unification for matching, so you can retract by pattern:

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:retract_pattern"
```

---

## Table Management

### abolish_table/2

`abolish_table(functor, Arity)` — clear cached answers for a specific tabled
predicate.

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:abolish_table_example"
```

### abolish_all_tables/0

`abolish_all_tables()` — clear all tabling caches at once.

```seam
test("clear all") <- abolish_all_tables()
```

---

## Patterns & Recipes

### Memoization

Cache computed results in a dynamic predicate. Arithmetic goes through a
constraint (`N1 == N - 1`): a bare `X is N - 1` is unification and would
bind `X` to the unevaluated term (see [Operators](operators.md)).


```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:memoization_recipe"
```

(For automatic memoization, consider [`-table`](tabling.md) instead.)

### Counter / mutable state

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:counter_recipe"
```

### Collecting facts from a computation

```seam
--8<-- "tests/fixtures/docs/database_ops_examples.seam:collect_recipe"
```

(Prefer [`findall`](meta_predicates.md) for this pattern — it is cleaner and
does not require dynamic predicates.)

---

## Gotchas

- **Must declare `-dynamic`** — without it, assertz/asserta/retract raise
  `error(permission_error(modify, static_procedure, Name/Arity), assertz/1)`
  (catchable by `catch/3`). A name with no declaration and no clauses is
  refused too by assertz/asserta, unless the module sets the flag
  [`assert_creates_dynamic`](flags.md#assert_creates_dynamic) (an imported
  `.pl` module does); retract of such a name just fails. To match the culprit in a catch pattern, quote it:
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
