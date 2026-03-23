# I/O Builtins

Clausal provides built-in predicates for formatted output and term-to-string conversion. The `.clausal` file format also supports f-string interpolation for string construction.


---

## Output Predicates

| Builtin | Arity | Description |
|---|---|---|
| `Write` | 1 | Write a term to stdout (no newline) |
| `Writeln` | 1 | Write a term to stdout followed by a newline |
| `PrintTerm` | 1 | Write a term using its string representation |
| `Nl` | 0 | Write a newline |
| `Tab` | 1 | Write N spaces |

### Examples

```clausal
greet(NAME) <- (Write("Hello, "), Write(NAME), Nl())

show_all(XS) <- (
    In(X, XS),
    Writeln(X)
)

indented(X) <- (Tab(4), Writeln(X))
```

---

## String Conversion

| Builtin | Arity | Description |
|---|---|---|
| `WriteToString` | 2 | `WriteToString(Term, String)` — unify String with the Write representation |
| `TermToString` | 2 | `TermToString(Term, String)` — unify String with the str() representation |

```clausal
format_pair(K, V, S) <- WriteToString(K - V, S)
```

---

## F-String Support

In `.clausal` files, f-strings are supported for string construction. Logic variables are automatically dereferenced before interpolation:

```clausal
describe(NAME, AGE, S) <- (
    S is f"Name: {NAME}, Age: {AGE}"
)
```

This uses `FStringThunk` / `FStringPart` for deferred evaluation — the f-string is evaluated at search time after variables are bound.

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

- Bound var: displays the bound value
- Unbound var: displays `_VarN` (unique ID)

This means `f"{X}"` and `Write(X)` show the value if bound, or a placeholder if unbound.

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
