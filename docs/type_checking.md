# Type Checking

Clausal provides predicates for testing the type of a term at runtime. These
succeed or fail — they never bind variables.

---

## Quick Example

```clausal
--8<-- "tests/fixtures/docs/type_checking_sigs.txt:describe_example"
```

---

## Variable Tests

### var/1

`var(X)` — succeeds if `X` is an unbound logic variable.

```clausal
Test("unbound") <- var(_)
Test("bound fails") <- (not var(42))
```

### nonvar/1

`nonvar(X)` — succeeds if `X` is *not* an unbound variable. The complement of
`var`.

```clausal
Test("number") <- nonvar(42)
Test("string") <- nonvar("hello")
Test("list") <- nonvar([1, 2])
Test("unbound") <- (not nonvar(_))
```

---

## The atom / string / list table

Atoms and strings are disjoint kinds ([Syntax § Atoms vs strings](syntax.md#atoms-vs-strings)).
An atom is the arity-0 cell `("bar",)`; a string is a Python `str`, which *is*
the list of its one-character atoms. Everything below follows from that:

| | atom `bar` | string `"bar"` | `""` | `[]` | `['a','b']` | compound `f(1)` | number |
|---|---|---|---|---|---|---|---|
| `atom/1` | ✓ | | | | | | |
| `string/1`, `is_str/1` | | ✓ | ✓ | ✓ | ✓ | | |
| `atomic/1` | ✓ | | | | | | ✓ |
| `compound/1` | | | | | | ✓ | |
| `callable_/1` | ✓ | | | | | ✓ | |
| `is_list/1` | | ✓ | ✓ | ✓ | ✓ | | |
| `is_chars/1` | | ✓ | ✓ | ✓ | ✓ | | |
| `ground/1` | ✓ | ✓ | ✓ | ✓ | ✓ | per args | ✓ |

`atomic/1` is false for a string because a string is a **list**, not an atomic
constant. `compound/1` is false for an atom because an atom has arity 0.

`string/1` follows the **term**, not the representation: `""` and `[]` are one
and the same term, and so are `"ab"` and `['a', 'b']`, so `string/1` holds for
all four. A string is stored compactly as a `str`, but that is a
representation choice and no test keys on it.

```clausal
--8<-- "tests/fixtures/docs/type_checking_sigs.txt:atom_vs_string"
```

---

## Atomic Type Tests

### atom/1

`atom(X)` — succeeds if `X` is an atom: a bare identifier such as `red`, or a
single-quoted spelling such as `'hello world'`. Bare atoms must be declared
(`-private([red])`, `-module(m, [red])`, an import) unless the file carries
[`-implicit_atoms`](directives.md#-implicit_atoms).

```clausal
-private([red, blue])
-double_quotes(chars)

Test("bare atom") <- atom(red)
Test("quoted atom") <- atom('hello world')
Test("string is not atom") <- (not atom("hello"))
Test("int is not atom") <- (not atom(42))
```

### string/1 and is_str/1

`string(X)` and `is_str(X)` are the same test: succeeds if `X` is a **string**
— the term a `"…"` literal denotes, which is the list of its character atoms.
That covers a Python `str`, a partial string that has become ground, `[]`, and
a proper list of char atoms, since those are the same terms. It does **not**
match atoms, and it does not match a list with a non-character element.

```clausal
-private([red])
-double_quotes(chars)

Test("str") <- is_str("hello")
Test("string") <- string("hello")
Test("empty string") <- string("")
Test("empty list") <- string([])
Test("char list") <- string(['h', 'i'])
Test("not str") <- (not is_str(42))
Test("list with a non-char") <- (not string([1, 2]))
Test("atom is not a string") <- (not string(red))
```

### atomic/1

`atomic(X)` — succeeds if `X` is an atom, a number, or another atomic constant.
It is **false for a string**, which is a list.

```clausal
-private([red])
-double_quotes(chars)

Test("atom is atomic") <- atomic(red)
Test("number is atomic") <- atomic(42)
Test("string is not atomic") <- (not atomic("red"))
```

### integer/1

`integer(X)` — succeeds if `X` is an integer. Booleans are excluded (even though
Python's `bool` is a subclass of `int`).

```clausal
Test("int") <- integer(42)
Test("not float") <- (not integer(3.14))
Test("not bool") <- (not integer(True))
```

### float_/1

`float_(X)` — succeeds if `X` is a float.

```clausal
Test("float") <- float_(3.14)
Test("not int") <- (not float_(42))
```

### number/1

`number(X)` — succeeds if `X` is an int or float (but not bool).

```clausal
Test("int") <- number(42)
Test("float") <- number(3.14)
Test("not bool") <- (not number(True))
Test("not str") <- (not number("42"))
```

---

## Structural Tests

### compound/1

`compound(X)` — succeeds if `X` is a compound term with arity > 0. This
includes predicate instances, `Compound` terms, and `KWTerm` values. An **atom
is not compound**: it is the arity-0 cell, and arity 0 is not `> 0`.

```clausal
-private([red])

point(1, 2, 3),

Test("compound") <- compound(point(1, 2, 3))
Test("atom is not compound") <- (not compound(red))
```

### callable_/1

`callable_(X)` — succeeds if `X` is an **atom** or a compound term: something
that could appear as a goal. A string is not callable — `call("foo")` raises
`type_error(callable, "foo")` rather than calling `foo`.

```clausal
-private([red])
-double_quotes(chars)

point(1, 2, 3),

Test("atom") <- callable_(red)
Test("compound") <- callable_(point(1, 2, 3))
Test("not string") <- (not callable_("hello"))
Test("not int") <- (not callable_(42))
```

### is_list/1

`is_list(X)` — succeeds if `X` is a list. A **string is a list** (of its
character atoms), so `is_list/1` accepts one, agreeing with every list-flavoured
builtin: `append`, `length`, `reverse`, `member`, `maplist`, `take`, `drop`.
`is_str/1` narrows that to the lists that are *character* sequences — it is not
a test for the Python `str` representation (see below).

```clausal
-double_quotes(chars)

Test("list") <- is_list([1, 2, 3])
Test("empty") <- is_list([])
Test("string is a list") <- is_list("hello")
Test("empty string is a list") <- is_list("")
Test("not int") <- (not is_list(42))
```

### is_chars/1

`is_chars(X)` — succeeds if `X` is a character sequence: either a string or a
list. Use this when you want to accept both spellings uniformly.

```clausal
-double_quotes(chars)

Test("string") <- is_chars("hello")
Test("list") <- is_chars([1, 2, 3])
Test("not int") <- (not is_chars(42))
```

| Predicate | `"hello"` | `['h','i']` | `[]` | `[1, 2]` | Purpose |
|-----------|-----------|-------------|------|----------|---------|
| `is_list/1` | Succeeds | Succeeds | Succeeds | Succeeds | Is this list-shaped? |
| `is_str/1` | Succeeds | Succeeds | Succeeds | Fails | Is this a character sequence? (the same test as `string/1`) |
| `is_chars/1` | Succeeds | Succeeds | Succeeds | Fails | The same test again, under the name the char-family builtins use |

All three follow the **term**, never the representation. `"hi"` and
`['h','i']` are one and the same term, and so are `""` and `[]`, so no test
can separate them — and there is deliberately no term-level predicate that
asks "is this stored as a Python `str` rather than a `list`?". That is a
representation question, and a program that thinks it needs the answer almost
always wants `is_str/1` (a character sequence) or `is_list/1` (list-shaped)
instead.

See [Strings as Lists](strings_as_lists.md) for the full story on string/list
interchangeability.

---

## Groundness

### ground/1

`ground(X)` — succeeds if `X` contains no unbound logic variables, anywhere
in its structure. Recursively checks lists, compound terms, and predicate
fields.

```clausal
Test("ground int") <- ground(42)
Test("ground list") <- ground([1, 2, 3])
Test("unbound fails") <- (not ground([1, _, 3]))
```

This is useful as a guard before [arithmetic](arithmetic.md) or [I/O](io.md) operations that require all
values to be determined:

```clausal
safe_print(X) <- (ground(X), writeln(X))
```

---

## Patterns & Recipes

### Type-dispatched processing

A string is a list, so an `is_list/1` clause would also catch strings. Test
`is_str/1` first and let clause order do the work:

```clausal
-double_quotes(chars)

process(X, R) <- (var(X),                    R is 'unknown')
process(X, R) <- (nonvar(X), integer(X),     R == X * 2)
process(X, R) <- (nonvar(X), is_str(X),      R is f"got: {X}")
process(X, R) <- (nonvar(X), is_list(X),     length(X, R))

Test("dispatch on string") <- (process("ab", R1), R1 == "got: ab")
Test("dispatch on list") <- (process([1, 2], R2), R2 == 2)
# `[]` and a char list ARE strings, so they reach the is_str/1 clause and come
# back with a text answer, not a length.
Test("dispatch on empty") <- (process([], R3), is_str(R3))
Test("dispatch on char list") <- (process(['a'], R4), is_str(R4))
```

Adding `not is_str(X)` to the list clause is a **different** filter, and
usually not the one you want: because `is_str/1` is the term test, it excludes
`[]` and every character list too, so `process([], R)` and `process(['a'], R)`
would fall through to the `other` clause rather than being measured. Reach for
it only when you genuinely mean "a list that is not a character sequence".

### Safe arithmetic guard

```clausal
safe_add(X, Y, Z) <- (
    number(X), number(Y),
    Z == X + Y
)
```

---

## Gotchas

- **`integer` excludes booleans** — Python's `True`/`False` are `int` subclasses
  but `integer(True)` fails. Use `nonvar` if you want to accept any non-variable.
- **`var` tests the current binding** — if `X` was unified earlier in the
  clause, `var(X)` will fail even though `X` started as a variable.
- **`is_list` accepts strings** — a string *is* the list of its char atoms, so
  `is_list("hello")` succeeds. `is_str/1` narrows it to *character* lists, not
  to the `str` representation: `is_str([])` and `is_str(['h','i'])` succeed
  too. (Neither recognises `'.'/2` cons-cell chains: Clausal stores lists as
  native Python lists and strings as `str`, and only ever *shows* the cons
  form, through `write_canonical/1`, `functor/3` and `=..`.)
- **A string is not atomic, an atom is not compound** — `atomic("bar")` fails
  because a string is a list; `compound(bar)` fails because an atom has arity 0.
- **Order matters** — put `var` checks first in multi-clause predicates,
  since they match the broadest case.

---

*See also: [Term Inspection](term_inspection.md) — decompose terms with functor,
arg, unpack; [Arithmetic](arithmetic.md) — number guards before computation.*
