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

```
greet(Name_) <- (Write("Hello, ") and Write(Name_) and Nl())

show_all(Xs_) <- (
    In(X_, Xs_)
    and Writeln(X_)
)

indented(X_) <- (Tab(4) and Writeln(X_))
```

---

## String Conversion

| Builtin | Arity | Description |
|---|---|---|
| `WriteToString` | 2 | `WriteToString(Term, String)` — unify String with the Write representation |
| `TermToString` | 2 | `TermToString(Term, String)` — unify String with the str() representation |

```
format_pair(K_, V_, S_) <- WriteToString(K_ - V_, S_)
```

---

## F-String Support

In `.clausal` files, f-strings are supported for string construction. Logic variables are automatically dereferenced before interpolation:

```
describe(Name_, Age_, S_) <- (
    S_ is f"Name: {Name_}, Age: {Age_}"
)
```

This uses `FStringThunk` / `FStringPart` for deferred evaluation — the f-string is evaluated at search time after variables are bound.

---

## Var Display

Logic variables have `__str__` and `__format__` methods (in the C extension) that auto-deref for display:

- Bound var: displays the bound value
- Unbound var: displays `_VarN` (unique ID)

This means `f"{X_}"` and `Write(X_)` show the value if bound, or a placeholder if unbound.

---

??? info "Test coverage"

    Tests are in `tests/test_io.py` (43 tests).

    - **Var display**: `__str__`, `__format__`, bound/unbound, nested
    - **Write/Writeln/PrintTerm**: atoms, numbers, strings, compounds, lists, vars
    - **Nl/Tab**: output formatting
    - **WriteToString/TermToString**: term conversion to string
    - **F-string integration**: variable interpolation, multiple vars, expressions
