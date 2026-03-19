# Exception Handling

Clausal provides structured exception handling via `throw/1`, `catch/3`, `halt/0`, and `halt/1`. Exceptions use ISO-Prolog-style structured error terms and are implemented via Python's native exception mechanism.

The implementation lives in `clausal/logic/exceptions.py`.

---

## Syntax

### throw/1

Raises an exception with a structured error term:

```
Throw(error(type_error(integer, foo), context))
```

Any term can be thrown — strings, atoms, or structured error terms.

### catch/3

Catches exceptions matching a pattern:

```
safe_div(X_, Y_, R_) <- Catch(
    (R_ := X_ / Y_),
    error(evaluation_error(zero_divisor), _),
    R_ is "undefined"
)
```

`Catch(Goal, Catcher, Recovery)`:

- **Goal** — the goal to execute
- **Catcher** — a pattern that the thrown term is unified against
- **Recovery** — the goal to execute if the exception matches

If the thrown term does not unify with Catcher, the exception propagates to the next enclosing `Catch` or surfaces as a Python `LogicException`.

`catch/3` also intercepts **plain Python exceptions** raised inside the goal
(including from `++()` escapes). These are wrapped as
`python_error(ClassName, Message)` so the catcher can match on them:

```python
catch(
    ++(some_python_call()),
    python_error("ValueError", MSG),
    handle_error(MSG)
)
```

If the Python exception does not match the catcher it is re-raised unchanged.

### halt/0, halt/1

```
done() <- Halt()
done_with_code() <- Halt(1)
```

`Halt()` raises `SystemExit(0)`. `Halt(N)` raises `SystemExit(N)`.

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

Uncaught `Throw` goals surface as `LogicException` in Python code. Caught exceptions (via `Catch`) never leave the logic layer.

---

??? example "Examples"

    **Catch a type error:**
    ```
    check_int(X_, R_) <- Catch(
        (X_ > 0 and R_ is "positive"),
        error(type_error(_, _), _),
        R_ is "not a number"
    )
    ```

    **Re-throw after logging:**
    ```
    logged_div(X_, Y_, R_) <- Catch(
        (R_ := X_ / Y_),
        E_,
        (Write(E_) and Throw(E_))
    )
    ```

    **Catch-all:**
    ```
    safe_run(Goal_, R_) <- Catch(
        (CallGoal(Goal_) and R_ is "ok"),
        _,
        R_ is "error"
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

## python_error/2

Any plain Python exception that escapes through a `++()` escape or other
Python-level code inside a goal is automatically wrapped:

```
python_error(ClassName, Message)
```

where `ClassName` is the exception class name (a string) and `Message` is
`str(exc)`. This term can be matched in a catcher pattern:

```python
# Catch any Python exception
catch(Goal, python_error(_, _), Recovery)

# Catch a specific class
catch(Goal, python_error("UnitsMismatch", Msg), handle(Msg))

# Catch several classes with disjunction
catch(Goal, python_error("ValueError", _), recovery_a)
catch(Goal, python_error("TypeError",  _), recovery_b)
```

`python_error/2` is a `Compound` term — it unifies structurally with standard
term unification including variable args.

---

## Compiler Integration

- `Throw(term)` compiles to `raise LogicException(term)`
- `Catch(goal, catcher, recovery)` compiles to a `try/except Exception` block;
  `LogicException` yields `.term` directly, any other Python exception is
  wrapped as `python_error(ClassName, Message)` before being unified against
  the catcher pattern
- `Halt()` / `Halt(N)` compile to `raise SystemExit(0)` / `raise SystemExit(N)`

---

??? info "Test coverage"

    Tests are in `tests/test_exceptions.py` (31 tests) and
    `tests/test_units.py::TestPythonExceptionCatch` (5 tests).

    - **Throw**: ground term, string, structured error, uncaught surfaces as LogicException
    - **Catch**: matching/non-matching catcher, nested catch, recovery goal, variable catcher (catch-all)
    - **Python exceptions**: `UnitsMismatch` caught as `python_error/2`, message bound, recovery skipped when no error, unmatched exception re-raised
    - **Halt**: exit code 0, exit code N, raises SystemExit
    - **Structured errors**: type_error, instantiation_error, existence_error, permission_error, evaluation_error
    - **Import integration**: `.clausal` file with catch/throw and python_error patterns
