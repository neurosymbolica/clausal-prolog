# I/O Builtins

Clausal provides built-in predicates for formatted output, term-to-string conversion, and f-string interpolation. Whether you need to print debug output, format a table, or build strings from logic variables, the I/O builtins have you covered. For calling Python functions directly, see [Python Integration](python_integration.md).

---

## Quick Example

```clausal
greet(NAME) <- (
    write("Hello, "),
    writeln(NAME)
)

Test("greet") <- greet("Alice")
```

---

## Output Predicates

### The three writers: `write/1`, `writeq/1`, `write_canonical/1`

Clausal has the three ISO writers, and they differ in **how much of the term's
structure they spell out**:

| Builtin | Quotes? | Operators / list syntax | Use it for |
|---|---|---|---|
| `write/1` | No — text comes out bare | Yes | human-facing output |
| `writeq/1` | Yes — atoms quoted when needed, strings in `"…"` | Yes | showing a term's structure |
| `write_canonical/1` | Yes | **No** — every list, string included, prints as the `'.'/2` structure it denotes | a form another Prolog can read back |

| Term | `write` | `writeq` | `write_canonical` |
|---|---|---|---|
| atom `foo` | `foo` | `foo` | `foo` |
| atom `'foo bar'` | `foo bar` | `'foo bar'` | `'foo bar'` |
| string `"abc"` | `abc` | `"abc"` | `'.'(a,'.'(b,'.'(c,[])))` |
| char list `[a, b]` | `ab` | `"ab"` | `'.'(a,'.'(b,[]))` |
| `[1, 2]` | `[1, 2]` | `[1, 2]` | `'.'(1,'.'(2,[]))` |
| `[]` | `[]` | `[]` | `[]` |
| `foo(bar, "baz")` | `foo(bar, baz)` | `foo(bar, "baz")` | `foo(bar,'.'(b,'.'(a,'.'(z,[]))))` |
| `1 + 2` | `+(1, 2)` | `+(1, 2)` | `+(1,2)` |

A list of characters *is* a string, so `writeq/1` prints `[a, b]` as `"ab"` —
they are the same term. `write_canonical/1` prints no space after commas and no
operator forms, so its output is byte-comparable with other ISO systems; the
string stays a compact `str` internally, the writer only *shows* the cons
structure.

```clausal
--8<-- "tests/fixtures/docs/io_examples.clausal:three_writers"
```

### writeln/1, print_term/1 and the string forms

| Builtin | Family | Newline? |
|---|---|---|
| `write/1`, `writeln/1`, `write_to_string/2` | unquoted (`write`) | `writeln` only |
| `writeq/1`, `print_term/1`, `term_to_string/2` | quoted (`writeq`) | `print_term` only |
| `write_canonical/1` | canonical | no |

```clausal
--8<-- "tests/fixtures/docs/io_examples.clausal:write_family"
```

**When to use which:**

- `write` / `writeln` — human-facing output; text comes out bare
- `writeq` / `print_term` — debugging: you can tell an atom from a string
- `write_canonical` — a form another Prolog can read back
- `write` + `nl` — when you need precise control over newlines

### nl/0

write a newline character:

```clausal
Test("newline") <- (nl(), nl())
```

### tab/1

write N spaces:

```clausal
indented(X) <- (tab(4), writeln(X))

Test("indented") <- indented("hello")
```

---

## String Conversion

Both answer with a **string**, never with an atom.

### write_to_string/2

`write_to_string(Term, String)` — unify String with the `write/1` rendering of
Term: unquoted, operators and list syntax intact.

```clausal
-double_quotes(chars)

format_pair(K, V, S) <- write_to_string(K - V, S)

Test("write to string") <- (
    format_pair("name", "alice", S),
    S == "name - alice"
)
```

### term_to_string/2

`term_to_string(Term, String)` — unify String with the `writeq/1` rendering of
Term: quoted, so an atom is distinguishable from a string.

```clausal
-double_quotes(chars)

label(X, S) <- term_to_string(X, S)

Test("term to string int") <- (label(42, S), S == "42")
Test("term to string keeps the quotes") <- (label("hello", S2), S2 == "\"hello\"")
```

**write_to_string vs term_to_string:**

| Input | `write_to_string` | `term_to_string` |
|---|---|---|
| `42` | `"42"` | `"42"` |
| the atom `hello` | `"hello"` | `"hello"` |
| the atom `'a b'` | `"a b"` | `"'a b'"` |
| the string `"hello"` | `"hello"` | `"\"hello\""` |
| `[1, 2]` | `"[1, 2]"` | `"[1, 2]"` |

Use `write_to_string` when building human-readable text. Use `term_to_string`
when you need to see which kind a value is; use `write_canonical/1` when you
need a representation another Prolog can read back.

---

## F-String Support

In `.clausal` files, f-strings build strings with logic variable interpolation. Variables are automatically dereferenced before the f-string is evaluated:

```clausal
-double_quotes(chars)

describe(NAME, AGE, S) <- (
    S is f"Name: {NAME}, Age: {AGE}"
)

Test("describe") <- (
    describe("Alice", 30, S),
    S == "Name: Alice, Age: 30"
)
```

### Expressions in F-Strings

F-strings support arbitrary Python expressions inside `{}`:

```clausal
-double_quotes(chars)

summarize(XS, S) <- (
    length(XS, N),
    S is f"List has {N} element(s)"
)

Test("summarize") <- (
    summarize([1, 2, 3], S),
    S == "List has 3 element(s)"
)
```

### Multi-Variable F-Strings

All logic variables referenced in the f-string are dereferenced:

```clausal
-double_quotes(chars)

full_name(FIRST, LAST, S) <- (
    S is f"{FIRST} {LAST}"
)

Test("full name") <- (
    full_name("Alice", "Smith", S),
    S == "Alice Smith"
)
```

### Deferred Evaluation

F-strings use deferred evaluation — the f-string is evaluated at search time, after variables are bound. This means f-strings work correctly with backtracking:

```clausal
-double_quotes(chars)

color("red"),
color("green"),
color("blue"),

describe_color(S) <- (
    color(C),
    S is f"The color is {C}"
)

Test("deferred f-string") <- (
    describe_color(S),
    S == "The color is red"
)
```

---

## Formatting Patterns

### Printing a List

```clausal
show_all(XS) <- (
    in_(X, XS),
    writeln(X)
)

Test("show all") <- show_all([1, 2, 3])
```

### String Building with term_to_string

```clausal
-double_quotes(chars)

format_item(X, S) <- term_to_string(X, S)

Test("format item") <- (
    format_item(42, S),
    S == "42"
)
```

### Building Strings with [foldl](higher_order.md)

A string is a list, so `append/3` concatenates one — use it inside a foldl
closure. (`+` is arithmetic, not concatenation: `R == A + E` on text raises
`type_error(integer, "ab")` from the CLP(ℤ) expression. `==` itself is fine on
strings — it is the `+` that has no text meaning.)

```clausal
-double_quotes(chars)

concat_all(XS, RESULT) <- (
    foldl(
        ((E, A, R) <- append(A, E, R)),
        XS, "", RESULT
    )
)

Test("concat all") <- (
    concat_all(["a", "b", "c"], R),
    R is "abc"
)
```

---

## Clause Inspection

| Builtin | Arity | Description |
|---|---|---|
| `listing` | 1 | `listing(Pred)` — print all clauses of a predicate to stdout |
| `portray_clause` | 1 | `portray_clause(Term)` — pretty-print a term with indentation |

### Examples

```clausal
# List all clauses for a predicate:
debug_fib <- listing(fib)

# Also accepted: an ATOM naming a 0-arity predicate, or a Name/Arity
# indicator naming any arity -- `fib/2` here is `/`, the arithmetic
# operator, applied to a predicate reference and an int; it is NOT data
# (see the paragraph below):
debug_greet <- listing('greet')
debug_fib2 <- listing(fib/2)

# Pretty-print a complex term:
show_deep(TERM) <- portray_clause(TERM)
```

`listing` accepts, in any of these shapes: a `PredicateMeta` class or
instance; a builtin predicate (prints a `"% name/arity — builtin"` line); an
**atom** naming a 0-arity predicate; or a `Name/Arity` indicator naming
a predicate at any arity. A **string** is not a name: `listing("greet")`
raises `type_error(predicate, "greet")`. The indicator has three representations: the
cell `('/', Name, Arity)` and the engine's `Compound("/", (Name, Arity))`
(both reachable from Python/engine callers that already hold the name and
arity as data), and — what a user-written `foo/2` actually compiles to in
`.clausal` source, as in the `debug_fib2` example above — a runtime `Div`
node, since `/` is the arithmetic operator and a structural (non-`is`) use
of it stays a reified operator term rather than data. For the last two, an
unknown `name/arity` raises `existence_error(procedure, Name/Arity)` — a
predicate nobody ever declared is not the same as one with an empty clause
list, which instead prints `"% name/arity — no clauses"`. An indicator whose
name or arity is an unbound variable (`listing(X/2)`) raises
`instantiation_error`. It prints a header with clause count, then each clause
in `head <- (body).` format.

The indicator finds an IMPORTED predicate as well as a local one: an
`-import_from` binds the exporter's predicate, whose clauses live on the
exporter's row, so `listing(qq/1)` and `listing('qq'/1)` from the importer
print exactly what `listing(qq)` prints there. (Before the P3-3 close-out
fix they raised `existence_error` for a predicate the importer could see and
call, because the name was looked up in the calling module's database alone.)

---

## Var Display

Logic variables have `__str__` and `__format__` methods (in the C extension) that auto-deref for display:

- **Bound var**: displays the bound value
- **Unbound var**: displays `_N` (unique numeric ID)

This means `f"{X}"` and `write(X)` show the value if bound, or a placeholder if unbound. This works in both `.clausal` files and Python code:

```python
from clausal.logic.variables import Var, Trail, unify

v = Var()
print(f"Unbound: {v}")   # _42  (placeholder)

trail = Trail()
unify(v, "hello", trail)
print(f"Bound: {v}")     # hello
```

---

## Gotchas

- **`write/1` does NOT quote; `writeq/1` and `print_term/1` do.** If your
  output has unwanted quotes, switch to `write`/`writeln` or use f-strings.
  (This is the opposite of what earlier releases of this page said.)
- **`write/1` cannot tell an atom from a string** — both print bare. Use
  `writeq/1` when the distinction matters, `write_canonical/1` when you need to
  see the list structure a string denotes.
- **F-strings evaluate at search time**, not at parse time. An f-string with an unbound variable will show the Var placeholder (`_N`), not raise an error.
- **nl/0 takes no arguments** — `nl()` not `nl(1)`. Use `tab(N)` for spacing.

---

??? info "Test coverage"

    Tests are in `tests/test_io.py` (43 tests) and `tests/test_listing.py` (36 tests).

    - **Var display**: `__str__`, `__format__`, bound/unbound, nested
    - **write/writeln/print_term**: atoms, numbers, strings, compounds, lists, vars
    - **nl/tab**: output formatting
    - **write_to_string/term_to_string**: term conversion to string
    - **F-string integration**: variable interpolation, multiple vars, expressions
    - **listing/1**: facts, rules, no-clauses, instance→class resolution, error handling
    - **portray_clause/1**: simple terms, lists, nested structures, unbound vars

---

*See also: [Python Integration](python_integration.md) — using `++()` escape for Python calls inside logic goals.*
*See also: [Lambdas](lambdas.md) — goal closures used with foldl and other higher-order predicates.*
