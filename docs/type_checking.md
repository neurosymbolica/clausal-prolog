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
test("unbound") <- var(_)
test("bound fails") <- (not var(42))
```

### nonvar/1

`nonvar(X)` — succeeds if `X` is *not* an unbound variable. The complement of
`var`.

```clausal
test("number") <- nonvar(42)
test("string") <- nonvar("hello")
test("list") <- nonvar([1, 2])
test("unbound") <- (not nonvar(_))
```

---

## The atom / string / list table

Atoms and strings are disjoint kinds ([Syntax § Atoms vs strings](syntax.md#atoms-vs-strings)).
An atom **is** the interned Python `str`; a string is a distinct value — the
list of its one-character atoms, not a bare `str`. Everything below follows
from that:

| | atom `bar` | string `"bar"` | `""` = `[]` | `['a','b']` | compound `f(1)` | number |
|---|---|---|---|---|---|---|
| `atom/1` | ✓ | | ✓ | | | |
| `string/1`, `is_str/1` | | ✓ | ✓ | ✓ | | |
| `atomic/1` | ✓ | | ✓ | | | ✓ |
| `compound/1` | | ✓ | | ✓ | ✓ | |
| `callable_/1` | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `is_list/1` | | ✓ | ✓ | ✓ | | |
| `is_chars/1` | | ✓ | ✓ | ✓ | | |
| `ground/1` | ✓ | ✓ | ✓ | ✓ | per args | ✓ |

This is ISO's reading, where a string is its char list: a non-empty list is the
compound `'.'/2` (so `compound/1` and `callable_/1` hold), and the empty list
`[]` — which is also the empty string `""` — is the atom `'[]'` (so `atom/1`,
`atomic/1` and `callable_/1` hold). `atomic/1` is false for a non-empty string
because a string is a **list**, not an atomic constant. `compound/1` is false
for an atom because an atom has arity 0.

`string/1` follows the **term**, not the representation: `""` and `[]` are one
and the same term, and so are `"ab"` and `['a', 'b']`, so `string/1` holds for
all four. A string is stored compactly (wrapping its text), but that is a
representation choice and no test keys on it — and it is not a bare `str`,
since a bare `str` is now an atom.

```clausal
--8<-- "tests/fixtures/docs/type_checking_sigs.txt:atom_vs_string"
```

---

## Atomic Type Tests

### atom/1

`atom(X)` — succeeds if `X` is an atom: a bare identifier such as `red`, or a
single-quoted spelling such as `'hello world'`. Bare atoms must be declared
(`-private([red])`, `-module(m, [red])`, an import).

```clausal
-private([red, blue])

test("bare atom") <- atom(red)
test("quoted atom") <- atom('hello world')
test("string is not atom") <- (not atom("hello"))
test("int is not atom") <- (not atom(42))
```

### string/1 and is_str/1

`string(X)` and `is_str(X)` are the same test: succeeds if `X` is a **string**
— the term a `"…"` literal denotes, which is the list of its character atoms.
That covers a ground string, a partial string that has become ground, `[]`,
and a proper list of char atoms, since those are the same terms. It does
**not** match atoms — a bare `str` is an atom now, not a string — and it does
not match a list with a non-character element.

```clausal
-private([red])

test("str") <- is_str("hello")
test("string") <- string("hello")
test("empty string") <- string("")
test("empty list") <- string([])
test("char list") <- string(['h', 'i'])
test("not str") <- (not is_str(42))
test("list with a non-char") <- (not string([1, 2]))
test("atom is not a string") <- (not string(red))
```

### atomic/1

`atomic(X)` — succeeds if `X` is an atom, a number, or another atomic constant.
It is **false for a non-empty string**, which is a list (`""` is `[]`, an atom).

```clausal
-private([red])

test("atom is atomic") <- atomic(red)
test("number is atomic") <- atomic(42)
test("string is not atomic") <- (not atomic("red"))
```

### integer/1

`integer(X)` — succeeds if `X` is an integer. Booleans are excluded (even though
Python's `bool` is a subclass of `int`).

```clausal
test("int") <- integer(42)
test("not float") <- (not integer(3.14))
test("not bool") <- (not integer(True))
```

### float_/1

`float_(X)` — succeeds if `X` is a float.

```clausal
test("float") <- float_(3.14)
test("not int") <- (not float_(42))
```

### number/1

`number(X)` — succeeds if `X` is an int or float (but not bool).

```clausal
test("int") <- number(42)
test("float") <- number(3.14)
test("not bool") <- (not number(True))
test("not str") <- (not number("42"))
```

---

## Structural Tests

### compound/1

`compound(X)` — succeeds if `X` is a compound term with arity > 0: a cell
such as `('point', 1, 2, 3)`, and — as in ISO — a non-empty list or string,
which is the `'.'/2` structure. An **atom
is not compound**: it has arity 0 (it is a name, not a functor application),
and arity 0 is not `> 0`.

```clausal
-private([red])

point(1, 2, 3),

test("compound") <- compound(point(1, 2, 3))
test("atom is not compound") <- (not compound(red))
```

### callable_/1

`callable_(X)` — succeeds if `X` is an **atom** or a compound term: something
that could appear as a goal. As in ISO, that includes a string, which is a list
(`'.'/2`), so `callable_("hello")` succeeds — and calling one does not call
`hello`: `call("foo")` raises `error(existence_error(procedure, '.'/2), '.'/2)`.

```clausal
-private([red])

point(1, 2, 3),

test("atom") <- callable_(red)
test("compound") <- callable_(point(1, 2, 3))
test("string is a list, so callable") <- callable_("hello")
test("not int") <- (not callable_(42))
```

### is_list/1

`is_list(X)` — succeeds if `X` is a list. A **string is a list** (of its
character atoms), so `is_list/1` accepts one, agreeing with every list-flavoured
builtin: `append`, `length`, `reverse`, `member`, `maplist`, `take`, `drop`.
`is_str/1` narrows that to the lists that are *character* sequences — it is not
a test for a particular representation (see below).

```clausal

test("list") <- is_list([1, 2, 3])
test("empty") <- is_list([])
test("string is a list") <- is_list("hello")
test("empty string is a list") <- is_list("")
test("not int") <- (not is_list(42))
```

### is_chars/1

`is_chars(X)` — succeeds if `X` is a string or any list (its elements are not
checked; `is_str/1` is the test that they are characters). A `bytes` value is a
*code* sequence and is rejected — use `is_codes/1` for that.

```clausal

test("string") <- is_chars("hello")
test("list") <- is_chars([1, 2, 3])
test("not int") <- (not is_chars(42))
```

| Predicate | `"hello"` | `['h','i']` | `[]` | `[1, 2]` | Purpose |
|-----------|-----------|-------------|------|----------|---------|
| `is_list/1` | Succeeds | Succeeds | Succeeds | Succeeds | Is this list-shaped? |
| `is_str/1` | Succeeds | Succeeds | Succeeds | Fails | Is this a character sequence? (the same test as `string/1`) |
| `is_chars/1` | Succeeds | Succeeds | Succeeds | Succeeds | Is this a list or a string? (a `bytes` value is rejected — see `is_codes/1`) |

All three follow the **term**, never the representation. `"hi"` and
`['h','i']` are one and the same term, and so are `""` and `[]`, so no test
can separate them — and there is deliberately no term-level predicate that
asks "is this stored compactly rather than as a proper `list`?". That is a
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
test("ground int") <- ground(42)
test("ground list") <- ground([1, 2, 3])
test("unbound fails") <- (not ground([1, _, 3]))
```

This is useful as a guard before [arithmetic](arithmetic.md) or [I/O](io.md) operations that require all
values to be determined:

```clausal
safe_print(X) <- (ground(X), writeln_text(X))
```

---

## Patterns & Recipes

### Type-dispatched processing

Clausal has no cut, so **every** clause whose guard holds answers: keep the
guards mutually exclusive. A string is a list, so the list clause must exclude
character sequences with `not is_str(X)` — and because `is_str/1` is the term
test, `[]` and every character list land in the text clause too:

```clausal
-private([unknown, text(s), items(n)])

process(X, R) <- (var(X),                                R is unknown)
process(X, R) <- (nonvar(X), integer(X),                 R == X * 2)
process(X, R) <- (nonvar(X), is_str(X),                  R is text(X))
process(X, R) <- (nonvar(X), is_list(X), not is_str(X),  length(X, N), R is items(N))

test("dispatch on string") <- process("ab", text("ab"))
test("dispatch on list") <- process([1, 2], items(2))
test("dispatch on integer") <- process(21, 42)
# `[]` and a char list ARE strings, so they reach the is_str/1 clause.
test("dispatch on empty") <- process([], text(""))
test("dispatch on char list") <- process(['a'], text("a"))
```

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
  to a particular representation: `is_str([])` and `is_str(['h','i'])` succeed
  too. (Neither recognises `'.'/2` cons-cell chains: Clausal stores lists as
  native Python lists and strings as a compact carrier, and only ever *shows*
  the cons form, through `write_canonical/1`, `functor/3` and `=..`.)
- **A string is not atomic, an atom is not compound** — `atomic("bar")` fails
  and `compound("bar")` succeeds because a non-empty string is a list; `compound(bar)`
  fails because an atom has arity 0.
- **Every matching clause answers** — there is no cut, so a multi-clause
  dispatcher needs mutually exclusive guards (`var(X)` / `nonvar(X)`, `is_str(X)` /
  `not is_str(X)`), not clause order.

---

*See also: [Term Inspection](term_inspection.md) — decompose terms with functor,
arg, unpack; [Arithmetic](arithmetic.md) — number guards before computation.*
