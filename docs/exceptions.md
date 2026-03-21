# Exception Handling

Clausal provides structured exception handling via `throw/1`, `catch/3`, `Catch/2`, `CatchRecover/3`, `halt/0`, and `halt/1`. Exceptions use ISO-Prolog-style structured error terms and are implemented via Python's native exception mechanism.

The implementation lives in `clausal/logic/exceptions.py`.

---

## Syntax

### throw/1

Raises an exception with a structured error term:

```clausal
Throw(error(type_error(integer, foo), context))
```

Any term can be thrown — strings, atoms, or structured error terms.

### Catch/2

Catches any exception and binds the error term to a variable or pattern:

```clausal
Catch(Goal, ERROR)
```

- **Goal** — the goal to execute; all solutions pass through if no exception
- **ERROR** — unified against the thrown term on exception; may be a variable (catches all) or a structured pattern (selective catch with no re-raise on mismatch)

`Catch/2` never re-raises — it is equivalent to `catch(Goal, ERROR, true)` but with unified exception representation. Python exceptions appear as `ClassName(Message)` terms, identical in shape to logic `throw/1` terms.

```clausal
# Catch any exception
Catch(Goal, ERROR)

# Catch a specific Python exception by class
Catch(++(some_python_call()), ValueError(MSG))

# Catch a structured logic error
Catch(Goal, error(type_error(_, _), _))
```

### CatchRecover/3

Like `Catch/2` but with an explicit recovery goal:

```clausal
CatchRecover(Goal, ERROR, Recovery)
```

- **Goal** — the goal to execute
- **ERROR** — unified against the thrown term on exception
- **Recovery** — goal run after ERROR is bound; has access to ERROR's bindings

`CatchRecover` never re-raises on pattern mismatch. For selective catch with re-raise on mismatch, use `catch/3`.

### catch/3

The standard form with selective matching and re-raise on mismatch:

```clausal
safe_div(X, Y, R) <- catch(
    (R := X / Y),
    error(evaluation_error(zero_divisor), _),
    R is "undefined"
)
```

`catch(Goal, Catcher, Recovery)`:

- **Goal** — the goal to execute
- **Catcher** — a pattern unified against the thrown term; re-raises if no match
- **Recovery** — the goal to execute if the exception matches

`catch/3` also intercepts **plain Python exceptions** raised inside the goal
(including from `++()` escapes). These are wrapped as `ClassName(Message)` — a
`Compound` whose functor is the exception class name — so the catcher can match
them the same way as logic throw terms:

```clausal
catch(
    ++(some_python_call()),
    ValueError(MSG),
    handle_error(MSG)
)
```

If the Python exception does not match the catcher it is re-raised unchanged.

### halt/0, halt/1

```clausal
done() <- Halt()
done_with_code() <- Halt(1)
```

`Halt()` raises `SystemExit(0)`. `Halt(N)` raises `SystemExit(N)`.

---

## Unified Exception Representation

Both logic `throw/1` terms and Python exceptions are represented as plain
Clausal terms during catch. Python exceptions become `Compound(ClassName,
(message,))` — the same structural shape as any predicate term — so there is
no distinction between catching a logic throw and catching a Python exception:

```clausal
# Logic exception: throw(my_error(42))  →  ERROR = my_error(42)
# Python exception: ValueError("bad")  →  ERROR = ValueError("bad")

Catch(Goal, ERROR)          # always catches, binds ERROR
CatchRecover(Goal, ERROR, Recovery)  # catches, binds ERROR, runs Recovery
catch(Goal, my_error(N), Recovery)   # selective: re-raises if no match
```

---

## Structured Error Terms

Clausal follows the ISO Prolog convention of wrapping errors in `error(ErrorTerm, Context)` compounds. Helper functions in `clausal.logic.exceptions` build these:

| Helper | Error term |
|---|---|
| `type_error(valid_type, culprit)` | `error(type_error(Type, Culprit), ...)` |
| `instantiation_error()` | `error(instantiation_error, ...)` |
| `existence_error(object_type, culprit)` | `error(existence_error(Type, Culprit), ...)` |
| `permission_error(op, type, culprit)` | `error(permission_error(Op, Type, Culprit), ...)` |
| `evaluation_error(kind)` | `error(evaluation_error(Kind), ...)` |

The context field is typically a string identifying where the error occurred.

---

## LogicException

`LogicException` is a Python exception class that wraps a thrown logic term:

```python
from clausal.logic.exceptions import LogicException

try:
    # ... run a query that throws ...
except LogicException as e:
    print(e.term)  # the thrown term
```

Uncaught `Throw` goals surface as `LogicException` in Python code. Caught exceptions (via `Catch`/`catch`) never leave the logic layer.

---

??? example "Examples"

    **Catch a type error:**
    ```clausal
    check_int(X, R) <- catch(
        (X > 0, R is "positive"),
        error(type_error(_, _), _),
        R is "not a number"
    )
    ```

    **Catch a Python exception (no recovery needed):**
    ```clausal
    safe_parse(S, R) <- (
        Catch(++(int(S)), ValueError(_)),
        R is "parse error"
    )
    ```

    **CatchRecover with error access:**
    ```clausal
    logged_op(X, Y, R) <- CatchRecover(
        (R := X / Y),
        ERR,
        (Write(ERR), R is "error")
    )
    ```

    **Re-throw after logging:**
    ```clausal
    logged_div(X, Y, R) <- catch(
        (R := X / Y),
        E,
        (Write(E), Throw(E))
    )
    ```

    **Catch-all:**
    ```clausal
    safe_run(GOAL, R) <- (
        Catch(CallGoal(GOAL), _),
        R is "ok"
    )
    ```

    ---

??? example "Python API"

    ```python
    from clausal.logic.exceptions import LogicException, type_error, instantiation_error

    # Build an error term
    err = type_error("integer", "foo")
    # → Compound('error', (Compound('type_error', ('integer', 'foo')), ...))

    # Raise from Python
    raise LogicException(err)
    ```

    ---

## Compiler Integration

- `Throw(term)` compiles to `raise LogicException(term)`
- `catch(goal, catcher, recovery)` compiles to a `try/except Exception` block;
  `LogicException` yields `.term` directly, any other Python exception is
  wrapped as `ClassName(message)` before being unified against the catcher pattern;
  re-raises if no match
- `Catch(goal, error)` — like `catch/3` but always catches (no re-raise); recovery = `true`
- `CatchRecover(goal, error, recovery)` — like `catch/3` but always catches (no re-raise)
- `Halt()` / `Halt(N)` compile to `raise SystemExit(0)` / `raise SystemExit(N)`

---

??? info "Test coverage"

    Tests are in `tests/test_exceptions.py` (31 tests) and
    `tests/test_units.py::TestPythonExceptionCatch` (5 tests).

    - **Throw**: ground term, string, structured error, uncaught surfaces as LogicException
    - **Catch**: matching/non-matching catcher, nested catch, recovery goal, variable catcher (catch-all)
    - **Python exceptions**: `UnitsMismatch` caught via `Catch/2` as `UnitsMismatch(Msg)`, message bound, transparent when no error, unmatched exception re-raised via `catch/3`
    - **Halt**: exit code 0, exit code N, raises SystemExit
    - **Structured errors**: type_error, instantiation_error, existence_error, permission_error, evaluation_error
    - **Import integration**: `.clausal` file with catch/throw patterns

---

*See also: [Builtins](builtins.md) — for a list of built-in predicates that can throw exceptions.*
