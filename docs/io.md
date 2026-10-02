# I/O Builtins

Clausal provides built-in predicates for formatted output, term-to-string conversion, and f-string interpolation. Whether you need to print debug output, format a table, or build strings from logic variables, the I/O builtins have you covered. For calling Python functions directly, see [Python Integration](python_integration.md).

---

## Quick Example

```seam
greet(NAME) <- (
    write_text("Hello, "),
    writeln_text(NAME)
)

test("greet") <- greet("Alice")
```

`write_text/1` and `writeln_text/1` are the **text** writers — a string prints
as its characters. `write/1` and `writeln/1` are the **ISO** writers and print
a string as the list of characters it is (`[H,e,l,l,o]`). Pick by whether
you are producing human text or showing a term; the three families are laid
out below.

---

## Output Predicates

### Three families of writer

Clausal has **three** groups of writing predicates. Which one you want depends
on whether you are producing human text, spelling out a term the ISO way, or
showing a term so a reader can tell an atom from a string.

| Family | Predicates | A string prints as | After a comma |
|---|---|---|---|
| **ISO** | `write/1`, `writeq/1`, `write_canonical/1`, `write_term/2` (and `writeln/1`, `write_to_string/2`, which are `write/1`'s semantics under non-ISO names) | the LIST of its characters — `[a,b,c]` | nothing |
| **Clausal text** | `write_text/1`, `writeln_text/1`, `write_text_to_string/2` | its text — `abc` | a space |
| **Clausal display** | `print_term/1`, `term_to_string/2` | the double-quoted form — `"abc"` | a space |

The ISO family prints **no whitespace after a comma** — `[a,b,c]`, `f(a,b)`,
`{k:v}` — so its output is byte-comparable with other ISO systems. The two
Clausal families keep the engine's `", "` display spacing.

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
| string `"abc"` | `[a,b,c]` | `[a,b,c]` | `'.'(a,'.'(b,'.'(c,[])))` |
| char list `[a, b]` | `[a,b]` | `[a,b]` | `'.'(a,'.'(b,[]))` |
| `[1, 2]` | `[1,2]` | `[1,2]` | `'.'(1,'.'(2,[]))` |
| code list `b"ab"` | `[97,98]` | `[97,98]` | `'.'(97,'.'(98,[]))` |
| `""` / `[]` / `b""` | `[]` | `[]` | `[]` |
| `foo(bar, "baz")` | `foo(bar,[b,a,z])` | `foo(bar,[b,a,z])` | `foo(bar,'.'(b,'.'(a,'.'(z,[]))))` |
| `'+'(1, 2)` | `+(1,2)` | `+(1,2)` | `+(1,2)` |

A string *is* the list of its characters, so all three spell it out; a `b"…"`
code list is the list of its code numbers and spells out the same way. The
three differ in quoting and in whether list syntax is used at all.

The `'+'(1, 2)` row is the quoted cell. A bare `1 + 2` written as an argument
in today's syntax is a runtime operator node, not that cell, and every writer
prints it in its source form, `(1 + 2)`; see [Operators](operators.md).
`write_canonical/1` additionally drops operator forms, so its output is the
`'.'/2` structure itself; the string stays a compact `str` internally, the
writer only *shows* the cons structure.

```seam
--8<-- "tests/fixtures/docs/io_examples.seam:three_writers"
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
| code list `b"ab"` | `b'ab'` |
| `""` / `[]` | `[]` |

`writeln_text(f"X is {X}")` is the idiomatic way to print an interpolated line.

#### The display writers: `print_term/1`, `term_to_string/2`

A string prints in double quotes (`"abc"`), a char list as the string it is
(`"ab"`), and an atom is quoted when it needs to be. Reach for these when you
need to tell an atom from a string in the output; the double-quoted spelling
is what Scryer's *toplevel* displays for the same term, and it is the one
`write_term/2`'s `double_quotes(true)` selects. These two keep the display
comma spacing (`f(a, "bc")`) that the ISO family drops. `print_term/1` adds a
newline.

### write_term/2

`write_term(Term, Options)` is the ISO writer with its switches named. Both
Boolean options default to **false**, so an option-free call is exactly
`write/1`.

| Option | Meaning |
|---|---|
| `quoted(Bool)` | quote an atom that would not read back as itself (`'foo bar'`) |
| `double_quotes(Bool)` | print a string (and the char list that *is* one) as `"abc"` rather than as `[a,b,c]` |
| `ignore_ops(Bool)` | accepted and inert — the write family here never prints operator forms to begin with |
| `numbervars(Bool)` | accepted and inert — there is no `'$VAR'/1` convention here |

| Call | Output |
|---|---|
| `write_term("abc", [])` | `[a,b,c]` |
| `write_term("abc", [quoted(true)])` | `[a,b,c]` |
| `write_term("abc", [quoted(true), double_quotes(true)])` | `"abc"` |
| `write_term([a, b], [])` | `[a,b]` |
| `write_term([1, 2], [])` | `[1,2]` |
| `write_term('a b', [quoted(true)])` | `'a b'` |

`write_term(T, [])` is exactly `write/1` and `write_term(T, [quoted(true)])`
is exactly `writeq/1`. `write_term(T, [quoted(true), double_quotes(true)])`
gives a string the *spelling* `print_term/1` and `term_to_string/2` give it —
those two additionally keep the display comma spacing, which this writer,
being ISO, does not.

An unrecognised option raises `domain_error(write_option, Opt)`; a non-list
`Options` raises `type_error(list, Options)`; an unbound or partial one
(`[quoted(true) | _]`) raises `instantiation_error`. Streams are out of
scope, so there is no `write_term/3`, and `max_depth(N)` is not supported.

```seam
--8<-- "tests/fixtures/docs/io_examples.seam:write_term"
```

### The newline and string forms of each family

| Builtin | Family | Newline? |
|---|---|---|
| `write/1`, `writeln/1`, `write_to_string/2` | ISO (`write`) | `writeln` only |
| `write_text/1`, `writeln_text/1`, `write_text_to_string/2` | Clausal text | `writeln_text` only |
| `print_term/1`, `term_to_string/2` | Clausal display | `print_term` only |
| `writeq/1` | ISO, quoted | no |
| `write_canonical/1` | canonical | no |

```seam
--8<-- "tests/fixtures/docs/io_examples.seam:write_family"
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

```seam
test("newline") <- (nl(), nl())
```

### tab/1

write N spaces:

```seam
indented(X) <- (tab(4), writeln_text(X))

test("indented") <- indented("hello")
```

---

## String Conversion

Both answer with a **string**, never with an atom.

### write_text_to_string/2

`write_text_to_string(Term, String)` — unify String with the `write_text/1`
rendering of Term: text comes out bare. This is the one to build
human-readable text with.

```seam
-double_quotes(chars)

format_pair(K, V, S) <- write_text_to_string(K - V, S)

test("write text to string") <- (
    format_pair('name', 'alice', S),
    S == "name - alice"
)
```

### write_to_string/2

`write_to_string(Term, String)` — unify String with the `write/1` (ISO)
rendering of Term: unquoted, list syntax intact, and a string spelled out as
the char list it is.

```seam
-double_quotes(chars)

iso_form(X, S) <- write_to_string(X, S)

test("write to string is ISO") <- (
    iso_form("ab", S),
    S == "[a,b]"
)
```

### term_to_string/2

`term_to_string(Term, String)` — unify String with the Clausal *display*
rendering of Term (`write_term(Term, [quoted(true), double_quotes(true)])`):
quoted, so an atom is distinguishable from a string.

```seam
-double_quotes(chars)

label(X, S) <- term_to_string(X, S)

test("term to string int") <- (label(42, S), S == "42")
test("term to string keeps the quotes") <- (label("hello", S2), S2 == "\"hello\"")
```

**The three string forms side by side:**

| Input | `write_text_to_string` | `write_to_string` | `term_to_string` |
|---|---|---|---|
| `42` | `"42"` | `"42"` | `"42"` |
| the atom `hello` | `"hello"` | `"hello"` | `"hello"` |
| the atom `'a b'` | `"a b"` | `"a b"` | `"'a b'"` |
| the string `"hi"` | `"hi"` | `"[h,i]"` | `"\"hi\""` |
| `[1, 2]` | `"[1, 2]"` | `"[1,2]"` | `"[1, 2]"` |

Use `write_text_to_string` when building human-readable text. Use
`term_to_string` when you need to see which kind a value is; use
`write_canonical/1` when you need a representation another Prolog can read
back.

---

## F-String Support

In `.clausal` files, f-strings build text with logic variable interpolation. Variables are automatically dereferenced before the f-string is evaluated, and a string interpolates as its text.

An f-string is a **string**: the same term a `"..."` literal is under the
module's `-double_quotes` mode — the chars string by default, and an atom
under `-double_quotes(atom)` (ruled 2026-09-28; it used to be an atom in every
mode). Compare it with a `"..."` literal:

```seam
-double_quotes(chars)

describe(NAME, AGE, S) <- (
    S is f"Name: {NAME}, Age: {AGE}"
)

test("describe") <- (
    describe("Alice", 30, S),
    S is "Name: Alice, Age: 30"
)

test("an f-string is a string") <- (
    describe("Alice", 30, S),
    string(S)
)
```

### Expressions in F-Strings

F-strings support arbitrary Python expressions inside `{}`:

```seam
-double_quotes(chars)

summarize(XS, S) <- (
    length(XS, N),
    S is f"List has {N} element(s)"
)

test("summarize") <- (
    summarize([1, 2, 3], S),
    S is "List has 3 element(s)"
)
```

### Multi-Variable F-Strings

All logic variables referenced in the f-string are dereferenced:

```seam
-double_quotes(chars)

full_name(FIRST, LAST, S) <- (
    S is f"{FIRST} {LAST}"
)

test("full name") <- (
    full_name("Alice", "Smith", S),
    S is "Alice Smith"
)
```

### Deferred Evaluation

F-strings use deferred evaluation — the f-string is evaluated at search time, after variables are bound. This means f-strings work correctly with backtracking:

```seam
-double_quotes(chars)

color("red"),
color("green"),
color("blue"),

describe_color(S) <- (
    color(C),
    S is f"The color is {C}"
)

test("deferred f-string") <- (
    describe_color(S),
    S is "The color is red"
)
```

---

## Formatting Patterns

### Printing a List

```seam
show_all(XS) <- (
    in_(X, XS),
    writeln_text(X)
)

test("show all") <- show_all([1, 2, 3])
```

### String Building with term_to_string

```seam
-double_quotes(chars)

format_item(X, S) <- term_to_string(X, S)

test("format item") <- (
    format_item(42, S),
    S == "42"
)
```

### Building Strings with [foldl](higher_order.md)

A string is a list, so `append/3` concatenates one — use it inside a foldl
closure. (`+` is arithmetic, not concatenation: `R == A + E` on text raises
`type_error(integer, "ab")` from the CLP(ℤ) expression. `==` itself is fine on
strings — it is the `+` that has no text meaning.)

```seam
-double_quotes(chars)

concat_all(XS, RESULT) <- (
    foldl(
        ((E, A, R) <- append(A, E, R)),
        XS, "", RESULT
    )
)

test("concat all") <- (
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

```seam
fib(0, 0),
fib(1, 1),

digits([D, *T]) >> (digit(D), digits(T))
digits([D]) >> digit(D)
digit(D) >> [D]

# List all clauses for a predicate, by its Name/Arity indicator -- `fib/2`
# here is `/`, the arithmetic operator, applied to a name and an int; it is
# NOT data (see the paragraph below):
debug_fib <- listing(fib/2)

# Name//Arity (a DCG nonterminal indicator) names Name/(Arity+2):
debug_digits <- listing(digits // 1)

# Pretty-print a complex term:
show_deep(TERM) <- portray_clause(TERM)
```

`listing/1` follows Scryer Prolog's contract (operator ruling 2026-09-25,
"do what Scryer does"). Its argument is a predicate indicator, `Name/Arity`
or `Name//Arity`:

- an **unbound** argument fails;
- an indicator naming no predicate, or a predicate with **no clauses**, fails;
- anything that is not an indicator -- a bare atom (`listing(fib)`), a
  compound term (`listing(color(R, H))`), a string, a number -- raises
  `type_error(predicate_indicator, PI)`;
- a malformed operand raises what `functor/3` raises for it: an unbound name
  or arity `instantiation_error`, a non-integer arity
  `type_error(integer, A)`, a negative one
  `domain_error(not_less_than_zero, A)`, a string name
  `type_error(atomic, N)`, a number name `type_error(atom, N)`.

The indicator has several representations: the cells `('/', Name, Arity)` /
`('//', Name, Arity)` (reachable from Python/engine callers that already hold the name and arity as
data), and -- what a user-written `foo/2` or `foo // 2` actually compiles to
in `.clausal` source -- a runtime `Div` / `FloorDiv` node, since `/` and `//`
are arithmetic operators and a structural (non-`is`) use stays a reified
operator term rather than data. It prints a header with clause count, then
each clause in `head <- (body).` format.

From Python, `listing` also takes a predicate handle (`listing(mod.fib)`
lists every arity the module defines under that name, and prints
`"% name/arity — no clauses"` for an empty one) or a builtin
(`"% name/arity — builtin"`).

The indicator finds an IMPORTED predicate as well as a local one: an
`-import_from` binds the exporter's predicate, so `listing(qq/1)` and
`listing('qq'/1)` from the importer print exactly what `listing(qq/1)`
prints in the exporting module.

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

- **`write/1` prints a string as `[a,b,c]`, not as `abc`.** It is the ISO
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

    Tests are in `tests/test_io.py` and `tests/test_listing.py`.

    - **Var display**: `__str__`, `__format__`, bound/unbound, nested
    - **write/writeln/print_term**: atoms, numbers, strings, compounds, lists, vars
    - **nl/tab**: output formatting
    - **write_to_string/term_to_string**: term conversion to string
    - **F-string integration**: variable interpolation, multiple vars, expressions
    - **listing/1**: facts, rules, no-clauses, predicate handles, error handling
    - **portray_clause/1**: simple terms, lists, nested structures, unbound vars

---

*See also: [Python Integration](python_integration.md) — using `++()` escape for Python calls inside logic goals.*
*See also: [Lambdas](lambdas.md) — goal closures used with foldl and other higher-order predicates.*
