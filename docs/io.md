# I/O Builtins

Clausal provides built-in predicates for formatted output, term-to-string conversion, and f-string interpolation. Whether you need to print debug output, format a table, or build strings from logic variables, the I/O builtins have you covered. For calling Python functions directly, see [Python Integration](python_integration.md).

---

## Quick Example

```clausal
greet(NAME) <- (
    write_text("Hello, "),
    writeln_text(NAME)
)

Test("greet") <- greet("Alice")
```

`write_text/1` and `writeln_text/1` are the **text** writers — a string prints
as its characters. `write/1` and `writeln/1` are the **ISO** writers and print
a string as the list of characters it is (`[H, e, l, l, o]`). Pick by whether
you are producing human text or showing a term; the three families are laid
out below.

---

## Output Predicates

### Three families of writer

Clausal has **three** groups of writing predicates. Which one you want depends
on whether you are producing human text, spelling out a term the ISO way, or
showing a term so a reader can tell an atom from a string.

| Family | Predicates | A string prints as |
|---|---|---|
| **ISO** | `write/1`, `writeq/1`, `write_canonical/1`, `write_term/2` (and `writeln/1`, `write_to_string/2`, which are `write/1`'s semantics under non-ISO names) | the LIST of its characters — `[a, b, c]` |
| **Clausal text** | `write_text/1`, `writeln_text/1`, `write_text_to_string/2` | its text — `abc` |
| **Clausal display** | `print_term/1`, `term_to_string/2` | the double-quoted form — `"abc"` |

#### The ISO writers: `write/1`, `writeq/1`, `write_canonical/1`

They differ in **how much of the term's structure they spell out**:

| Builtin | Quotes? | List syntax | Use it for |
|---|---|---|---|
| `write/1` | No — an atom prints its bare spelling | Yes | ISO term output |
| `writeq/1` | Yes — an atom is quoted when it needs it | Yes | ISO term output you can read back |
| `write_canonical/1` | Yes | **No** — every list, string included, prints as the `'.'/2` structure it denotes | a form another Prolog can read back |

| Term | `write` | `writeq` | `write_canonical` |
|---|---|---|---|
| atom `foo` | `foo` | `foo` | `foo` |
| atom `'foo bar'` | `foo bar` | `'foo bar'` | `'foo bar'` |
| string `"abc"` | `[a, b, c]` | `[a, b, c]` | `'.'(a,'.'(b,'.'(c,[])))` |
| char list `[a, b]` | `[a, b]` | `[a, b]` | `'.'(a,'.'(b,[]))` |
| `[1, 2]` | `[1, 2]` | `[1, 2]` | `'.'(1,'.'(2,[]))` |
| `""` / `[]` | `[]` | `[]` | `[]` |
| `foo(bar, "baz")` | `foo(bar, [b, a, z])` | `foo(bar, [b, a, z])` | `foo(bar,'.'(b,'.'(a,'.'(z,[]))))` |
| `1 + 2` | `+(1, 2)` | `+(1, 2)` | `+(1,2)` |

A string *is* the list of its characters, so all three spell it out; they only
differ in quoting and in whether list syntax is used at all.
`write_canonical/1` prints no space after commas and no operator forms, so its
output is byte-comparable with other ISO systems; the string stays a compact
`str` internally, the writer only *shows* the cons structure.

```clausal
--8<-- "tests/fixtures/docs/io_examples.clausal:three_writers"
```

#### The text writers: `write_text/1`, `writeln_text/1`, `write_text_to_string/2`

These print a string as its **text** and a char list as the text it spells; an
atom prints its bare spelling, and every other term prints exactly as `write/1`
prints it. This is Clausal's `~s`, and it is where f-strings go:

| Term | `write_text` |
|---|---|
| string `"abc"` | `abc` |
| char list `[a, b]` | `ab` |
| atom `'foo bar'` | `foo bar` |
| `[1, 2]` | `[1, 2]` |
| `""` / `[]` | `[]` |

`writeln_text(f"X is {X}")` is the idiomatic way to print an interpolated line.

#### The display writers: `print_term/1`, `term_to_string/2`

Exactly `write_term(Term, [quoted(true), double_quotes(true)])` — a string
prints in double quotes (`"abc"`), a char list as the string it is (`"ab"`),
and an atom is quoted when it needs to be. Reach for these when you need to
tell an atom from a string in the output; that is what Scryer's *toplevel*
displays for the same term. `print_term/1` adds a newline.

### write_term/2

`write_term(Term, Options)` is the ISO writer with its switches named. Both
Boolean options default to **false**, so an option-free call is the strict
ISO display.

| Option | Meaning |
|---|---|
| `quoted(Bool)` | quote an atom that would not read back as itself (`'foo bar'`) |
| `double_quotes(Bool)` | print a string (and the char list that *is* one) as `"abc"` rather than as `[a, b, c]` |
| `ignore_ops(Bool)` | accepted and inert — the write family here never prints operator forms to begin with |

| Call | Output |
|---|---|
| `write_term("abc", [])` | `[a, b, c]` |
| `write_term("abc", [quoted(true)])` | `[a, b, c]` |
| `write_term("abc", [quoted(true), double_quotes(true)])` | `"abc"` |
| `write_term([a, b], [])` | `[a, b]` |
| `write_term('a b', [quoted(true)])` | `'a b'` |

`write_term(T, [quoted(true), double_quotes(true)])` is exactly `writeq/1`.
An unrecognised option raises `domain_error(write_option, Opt)`; a non-list
`Options` raises `type_error(list, Options)`. Streams are out of scope, so
there is no `write_term/3`, and `max_depth(N)` is not supported.

The engine's display spacing (`f(a, b)`, `[a, b, c]`) is kept here as it is in
every writer but `write_canonical/1` — that one alone is byte-comparable with
other ISO systems.

```clausal
--8<-- "tests/fixtures/docs/io_examples.clausal:write_term"
```

### The newline and string forms of each family

| Builtin | Family | Newline? |
|---|---|---|
| `write/1`, `writeln/1`, `write_to_string/2` | ISO (`write`) | `writeln` only |
| `write_text/1`, `writeln_text/1`, `write_text_to_string/2` | Clausal text | `writeln_text` only |
| `print_term/1`, `term_to_string/2` | Clausal display | `print_term` only |
| `writeq/1` | ISO, quoted | no |
| `write_canonical/1` | canonical | no |

```clausal
--8<-- "tests/fixtures/docs/io_examples.clausal:write_family"
```

**When to use which:**

- `write_text` / `writeln_text` — human-facing output and f-strings; text comes
  out bare
- `print_term` / `term_to_string` — debugging: you can tell an atom from a
  string
- `write` / `writeq` — ISO term output; a string spells itself out
- `write_canonical` — a form another Prolog can read back
- `write_text` + `nl` — when you need precise control over newlines

### nl/0

write a newline character:

```clausal
Test("newline") <- (nl(), nl())
```

### tab/1

write N spaces:

```clausal
indented(X) <- (tab(4), writeln_text(X))

Test("indented") <- indented("hello")
```

---

## String Conversion

Both answer with a **string**, never with an atom.

### write_text_to_string/2

`write_text_to_string(Term, String)` — unify String with the `write_text/1`
rendering of Term: text comes out bare. This is the one to build
human-readable text with.

```clausal
-double_quotes(chars)

format_pair(K, V, S) <- write_text_to_string(K - V, S)

Test("write text to string") <- (
    format_pair("name", "alice", S),
    S == "name - alice"
)
```

### write_to_string/2

`write_to_string(Term, String)` — unify String with the `write/1` (ISO)
rendering of Term: unquoted, list syntax intact, and a string spelled out as
the char list it is.

```clausal
-double_quotes(chars)

iso_form(X, S) <- write_to_string(X, S)

Test("write to string is ISO") <- (
    iso_form("ab", S),
    S == "[a, b]"
)
```

### term_to_string/2

`term_to_string(Term, String)` — unify String with the Clausal *display*
rendering of Term (`write_term(Term, [quoted(true), double_quotes(true)])`):
quoted, so an atom is distinguishable from a string.

```clausal
-double_quotes(chars)

label(X, S) <- term_to_string(X, S)

Test("term to string int") <- (label(42, S), S == "42")
Test("term to string keeps the quotes") <- (label("hello", S2), S2 == "\"hello\"")
```

**The three string forms side by side:**

| Input | `write_text_to_string` | `write_to_string` | `term_to_string` |
|---|---|---|---|
| `42` | `"42"` | `"42"` | `"42"` |
| the atom `hello` | `"hello"` | `"hello"` | `"hello"` |
| the atom `'a b'` | `"a b"` | `"a b"` | `"'a b'"` |
| the string `"hi"` | `"hi"` | `"[h, i]"` | `"\"hi\""` |
| `[1, 2]` | `"[1, 2]"` | `"[1, 2]"` | `"[1, 2]"` |

Use `write_text_to_string` when building human-readable text. Use
`term_to_string` when you need to see which kind a value is; use
`write_canonical/1` when you need a representation another Prolog can read
back.

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
    writeln_text(X)
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

This means `f"{X}"` and `write_text(X)` show the value if bound, or a placeholder if unbound. This works in both `.clausal` files and Python code:

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

- **`write/1` prints a string as `[a, b, c]`, not as `abc`.** It is the ISO
  writer, and a string *is* a list of characters. For human text — and for
  f-strings — use `write_text/1` / `writeln_text/1`.
- **`write/1` does NOT quote; `print_term/1` and `term_to_string/2` do.** If
  your output has unwanted quotes, switch to the text writers.
- **`write_text/1` cannot tell an atom from a string** — both print bare. Use
  `print_term/1` when the distinction matters, `write_canonical/1` when you need
  to see the list structure a string denotes.
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
