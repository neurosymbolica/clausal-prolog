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

### write/1 vs writeln/1 vs print_term/1

All three write a term to stdout, but differ in formatting:

| Builtin | Newline? | Strings | Terms |
|---|---|---|---|
| `write/1` | No | Quoted (`"hello"`) | functor notation |
| `writeln/1` | Yes | Quoted (`"hello"`) | functor notation |
| `print_term/1` | No | Unquoted (`hello`) | `str()` representation |

```clausal
# write: no newline, quoted strings
Test("write") <- (write("hello"), write(" "), write("world"), nl())

# writeln: like write + nl
Test("writeln") <- writeln("hello")

# print_term: unquoted, str()-style
Test("print term") <- print_term("hello")
```

**when to use which:**

- `write` / `writeln` — standard output, preserves Clausal term syntax
- `print_term` — human-readable output (no quotes around strings)
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

### write_to_string/2

`write_to_string(Term, String)` — unify String with the write representation of Term (quoted strings, functor notation):

```clausal
format_pair(K, V, S) <- write_to_string(K - V, S)

Test("write to string") <- (
    format_pair("name", "alice", S),
    nonvar(S)
)
```

### term_to_string/2

`term_to_string(Term, String)` — unify String with the `str()` representation of Term (unquoted strings):

```clausal
label(X, S) <- term_to_string(X, S)

Test("term to string int") <- (label(42, S), S == "42")
Test("term to string str") <- (label("hello", S), nonvar(S))
```

**write_to_string vs term_to_string:**

| Input | write_to_string | term_to_string |
|---|---|---|
| `42` | `"42"` | `"42"` |
| `"hello"` | quoted | unquoted |
| `[1, 2]` | `"[1, 2]"` | `"[1, 2]"` |

Use `term_to_string` when building human-readable strings. Use `write_to_string` when you need a representation that could be read back.

---

## F-String Support

In `.clausal` files, f-strings build strings with logic variable interpolation. Variables are automatically dereferenced before the f-string is evaluated:

```clausal
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
format_item(X, S) <- term_to_string(X, S)

Test("format item") <- (
    format_item(42, S),
    S == "42"
)
```

### Building Strings with [foldl](higher_order.md)

Use `==` with `+` to concatenate strings inside a foldl closure:

```clausal
concat_all(XS, RESULT) <- (
    foldl(
        ((E, A, R) <- (R == A + E)),
        XS, "", RESULT
    )
)

Test("concat all") <- (
    concat_all(["a", "b", "c"], R),
    R == "abc"
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

# Pretty-print a complex term:
show_deep(TERM) <- portray_clause(TERM)
```

`listing` accepts a predicate class or instance. It prints a header with clause count, then each clause in `head <- (body).` format.

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

- **write quotes strings**, print_term does not. If your output has unwanted quotes, switch to `print_term` or use f-strings.
- **F-strings evaluate at search time**, not at parse time. An f-string with an unbound variable will show the Var placeholder (`_N`), not raise an error.
- **nl/0 takes no arguments** — `nl()` not `nl(1)`. Use `tab(N)` for spacing.

---

??? info "Test coverage"

    Tests are in `tests/test_io.py` (43 tests) and `tests/test_listing.py` (13 tests).

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
