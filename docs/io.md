# I/O Builtins

Clausal provides built-in predicates for formatted output, term-to-string conversion, and f-string interpolation. Whether you need to print debug output, format a table, or build strings from logic variables, the I/O builtins have you covered.

---

## Quick Example

```clausal
greet(NAME) <- (
    Write("Hello, "),
    Writeln(NAME)
)

Test("greet") <- greet("Alice")
```

---

## Output Predicates

### Write/1 vs Writeln/1 vs PrintTerm/1

All three write a term to stdout, but differ in formatting:

| Builtin | Newline? | Strings | Terms |
|---|---|---|---|
| `Write/1` | No | Quoted (`"hello"`) | Functor notation |
| `Writeln/1` | Yes | Quoted (`"hello"`) | Functor notation |
| `PrintTerm/1` | No | Unquoted (`hello`) | `str()` representation |

```clausal
# Write: no newline, quoted strings
Test("write") <- (Write("hello"), Write(" "), Write("world"), Nl())

# Writeln: like Write + Nl
Test("writeln") <- Writeln("hello")

# PrintTerm: unquoted, str()-style
Test("print term") <- PrintTerm("hello")
```

**When to use which:**

- `Write` / `Writeln` — standard output, preserves Clausal term syntax
- `PrintTerm` — human-readable output (no quotes around strings)
- `Write` + `Nl` — when you need precise control over newlines

### Nl/0

Write a newline character:

```clausal
Test("newline") <- (Nl(), Nl())
```

### Tab/1

Write N spaces:

```clausal
indented(X) <- (Tab(4), Writeln(X))

Test("indented") <- indented("hello")
```

---

## String Conversion

### WriteToString/2

`WriteToString(Term, String)` — unify String with the Write representation of Term (quoted strings, functor notation):

```clausal
format_pair(K, V, S) <- WriteToString(K - V, S)

Test("write to string") <- (
    format_pair("name", "alice", S),
    IsBound(S)
)
```

### TermToString/2

`TermToString(Term, String)` — unify String with the `str()` representation of Term (unquoted strings):

```clausal
label(X, S) <- TermToString(X, S)

Test("term to string int") <- (label(42, S), S == "42")
Test("term to string str") <- (label("hello", S), IsBound(S))
```

**WriteToString vs TermToString:**

| Input | WriteToString | TermToString |
|---|---|---|
| `42` | `"42"` | `"42"` |
| `"hello"` | quoted | unquoted |
| `[1, 2]` | `"[1, 2]"` | `"[1, 2]"` |

Use `TermToString` when building human-readable strings. Use `WriteToString` when you need a representation that could be read back.

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
    Length(XS, N),
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
    In(X, XS),
    Writeln(X)
)

Test("show all") <- show_all([1, 2, 3])
```

### String Building with TermToString

```clausal
format_item(X, S) <- TermToString(X, S)

Test("format item") <- (
    format_item(42, S),
    S == "42"
)
```

### Building Strings with FoldLeft

Use `:=` with `+` to concatenate strings inside a FoldLeft closure:

```clausal
concat_all(XS, RESULT) <- (
    FoldLeft(
        ((E, A, R) <- (R := A + E)),
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
| `Listing` | 1 | `Listing(Pred)` — print all clauses of a predicate to stdout |
| `PortrayClause` | 1 | `PortrayClause(Term)` — pretty-print a term with indentation |

### Examples

```clausal
% List all clauses for a predicate:
debug_fib <- Listing(fib)

% Pretty-print a complex term:
show_deep(TERM) <- PortrayClause(TERM)
```

`Listing` accepts a predicate class or instance. It prints a header with clause count, then each clause in `head <- (body).` format.

---

## Var Display

Logic variables have `__str__` and `__format__` methods (in the C extension) that auto-deref for display:

- **Bound var**: displays the bound value
- **Unbound var**: displays `_N` (unique numeric ID)

This means `f"{X}"` and `Write(X)` show the value if bound, or a placeholder if unbound. This works in both `.clausal` files and Python code:

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

- **Write quotes strings**, PrintTerm does not. If your output has unwanted quotes, switch to `PrintTerm` or use f-strings.
- **F-strings evaluate at search time**, not at parse time. An f-string with an unbound variable will show the Var placeholder (`_N`), not raise an error.
- **Nl/0 takes no arguments** — `Nl()` not `Nl(1)`. Use `Tab(N)` for spacing.

---

??? info "Test coverage"

    Tests are in `tests/test_io.py` (43 tests) and `tests/test_listing.py` (13 tests).

    - **Var display**: `__str__`, `__format__`, bound/unbound, nested
    - **Write/Writeln/PrintTerm**: atoms, numbers, strings, compounds, lists, vars
    - **Nl/Tab**: output formatting
    - **WriteToString/TermToString**: term conversion to string
    - **F-string integration**: variable interpolation, multiple vars, expressions
    - **Listing/1**: facts, rules, no-clauses, instance→class resolution, error handling
    - **PortrayClause/1**: simple terms, lists, nested structures, unbound vars

---

*See also: [Python Integration](python_integration.md) — using `++()` escape for Python calls inside logic goals.*
*See also: [Lambdas](lambdas.md) — goal closures used with FoldLeft and other higher-order predicates.*
