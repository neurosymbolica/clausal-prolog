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
greet(NAME) <- (Write("Hello, "), Write(NAME), Nl()),

show_all(XS) <- (
    In(X, XS),
    Writeln(X)
),

indented(X) <- (Tab(4), Writeln(X)),
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

## Var Display

Logic variables have `__str__` and `__format__` methods (in the C extension) that auto-deref for display:

- Bound var: displays the bound value
- Unbound var: displays `_VarN` (unique ID)

This means `f"{X}"` and `Write(X)` show the value if bound, or a placeholder if unbound.

---

??? info "Test coverage"

    Tests are in `tests/test_io.py` (43 tests).

    - **Var display**: `__str__`, `__format__`, bound/unbound, nested
    - **Write/Writeln/PrintTerm**: atoms, numbers, strings, compounds, lists, vars
    - **Nl/Tab**: output formatting
    - **WriteToString/TermToString**: term conversion to string
    - **F-string integration**: variable interpolation, multiple vars, expressions

---

*See also: [Python Integration](python_integration.md) — using `++()` escape for Python calls inside logic goals.*
