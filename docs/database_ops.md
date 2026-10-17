# Database Operations

Clausal Prolog supports runtime modification of the predicate database — adding and
removing clauses while a program is running. This enables dynamic state,
memoization, and self-modifying programs.

Examples on this page are [Clausal Prolog](clausal_prolog.md)
(`.clausal`): ISO Prolog syntax, without cut. (The [seam](syntax.md),
Clausal's Python-syntax surface, writes the directive `-dynamic(Name/Arity)`
and has a different default for undeclared names; the page notes where.)

---

## Quick Example

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:quick_example"
```

---

## Declare first: the `dynamic/1` directive

`assertz`, `asserta` and `retract` modify a **dynamic** predicate, declared
with `:- dynamic(Name/Arity).`. A predicate that has clauses in its module and
no declaration is static once the module has loaded, as in ISO Prolog:
modifying it raises `permission_error(modify, static_procedure, Name/Arity)`,
with the builtin as the culprit (Scryer's form; see
[Exceptions](exceptions.md)). Builtins are static too.

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:declare_first"
```

The declaration also makes the predicate exist before it has clauses: a
dynamic predicate with no clauses simply fails, where calling an undeclared
name with no clauses raises `existence_error(procedure, Name/Arity)`.
Asserting into a name that does not exist at all follows the module flag
[`assert_creates_dynamic`](flags.md#assert_creates_dynamic), which is `true`
in a `.clausal` module (and an imported `.pl` one): as in ISO 7.5.2(2), the
assert creates it as a dynamic procedure. (A seam module has the flag
`false`, so there an undeclared name is refused with the same
`permission_error(modify, static_procedure, Name/Arity)`.) Declaring the
predicate is still the clear way to say it is meant to change. Declare
several at once:

```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:dynamic_directive"
```

See [Directives](directives.md) for the other directives.

### From Python: `Module.declare_dynamic`

A `Module` built from Python has no directives, so declare its dynamic
predicates with `Module.declare_dynamic(name, arity)`, the same declaration
as `:- dynamic(name/arity).`. It also works on the `Module` of a loaded
`.seam` or `.clausal` file (`mod.__clausal_module__`).

```python
from clausal import Module, Var, solve

m = Module("counter")
m.declare_dynamic("count", 1)          # :- dynamic(count/1).
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

As in ISO (8.9.3) and Scryer, `retract` of a name nothing declares simply
fails — there is no clause to remove — while a static predicate, a declared
data functor or a builtin raises
`error(permission_error(modify, static_procedure, Name/Arity), retract/1)`, and
an unbound `Term` raises `instantiation_error`. (`retractall/1` and
`abolish/1` are not provided.)

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

`abolish_all_tables` — clear all tabling caches at once.

```clausal
test("clear all") :-
    abolish_all_tables.
```

---

## Patterns & Recipes

### Memoization

Cache computed results in a dynamic predicate. Arithmetic goes through
CLP(ℤ) constraints (`N1 #= N - 1`); ISO `N1 is N - 1` would also do here,
since `N` is bound. (In the seam, a bare `X is N - 1` is unification and
would bind `X` to the unevaluated term; see [Operators](operators.md).)


```clausal
--8<-- "tests/fixtures/docs/database_ops_examples.clausal:memoization_recipe"
```

(For automatic memoization, consider [`:- table`](tabling.md) instead.)

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

- **A predicate with clauses must be declared `dynamic`** — without it,
  assertz/asserta/retract raise
  `error(permission_error(modify, static_procedure, Name/Arity), assertz/1)`
  (catchable by `catch/3`; the culprit is matched as written, `assertz/1`).
  A name with no declaration and no clauses is created by assertz/asserta in
  a `.clausal` module, where the flag
  [`assert_creates_dynamic`](flags.md#assert_creates_dynamic) is on; retract
  of such a name just fails. (In a seam module the flag is off and the
  assert is refused; to match the culprit in a seam catch pattern, quote it,
  `'/'('assertz', 1)`, because a bare builtin name in a seam term is the
  builtin's object, not the atom.)
- **assertz adds facts, not rules** — `assertz((foo(X) :- bar(X)))` is not
  supported and raises `permission_error(assert, rule, Head)` at
  assert time (the predicate's existing clauses are left untouched). Only
  ground or partially-ground facts can be asserted.
- **Arity is part of the name** — `foo/1` and `foo/2` are different
  predicates: declaring `foo/2` dynamic says nothing about `foo/1`. In a
  `.clausal` module, `assertz(foo(a))` then creates a new dynamic `foo/1`; in
  a seam module it is refused with
  `error(permission_error(modify, static_procedure, foo/1), assertz/1)`,
  since an undeclared procedure is static there (ISO 7.5.2).
- **retract removes one clause** — it removes the *first* matching clause only.
  Call it in a loop (or use `findall` + multiple retracts) to remove all
  matches.
- **Order matters** — `assertz` appends, `asserta` prepends. The clause
  order affects which solution is found first.
- **Tabling interaction** — if a tabled predicate depends on dynamic facts,
  remember to `abolish_table` after modifying the facts, or the cached answers
  will be stale.

---

*See also: [Directives](directives.md) — `dynamic` and other predicate
directives, [Tabling](tabling.md) — automatic memoization with `table`,
[Meta-Predicates](meta_predicates.md) — findall as an alternative to
assert-based collection.*
