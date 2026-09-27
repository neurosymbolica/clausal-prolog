# Exception Handling

Clausal provides structured exception handling via `throw/1`, `catch/3`, `Catch/2`, `catch_recover/3`, `halt/0`, and `halt/1`. Exceptions use ISO-Prolog-style structured error terms and are implemented via Python's native exception mechanism.

The implementation lives in `clausal/logic/exceptions.py`.

---

## Syntax

### throw/1

Raises an exception with a structured error term:

```clausal
--8<-- "tests/fixtures/docs/exceptions_sigs.txt:throw_1"
```

Any term can be thrown — strings, atoms, or structured error terms.

### Catch/2

Catches any exception and binds the error term to a variable or pattern:

```clausal
--8<-- "tests/fixtures/docs/exceptions_sigs.txt:catch_2"
```

- **Goal** — the goal to execute; all solutions pass through if no exception
- **ERROR** — unified against the thrown term on exception; may be a variable (catches all) or a structured pattern (selective catch with no re-raise on mismatch)

`Catch/2` never re-raises — it is equivalent to `catch(Goal, ERROR, true)` but with unified exception representation. Python exceptions appear as `ClassName(Message)` terms, identical in shape to logic `throw/1` terms.

```clausal
--8<-- "tests/fixtures/docs/exceptions_sigs.txt:catch_2_ex2"
```

### catch_recover/3

Like `Catch/2` but with an explicit recovery goal:

```clausal
--8<-- "tests/fixtures/docs/exceptions_sigs.txt:catch_recover_3"
```

- **Goal** — the goal to execute
- **ERROR** — unified against the thrown term on exception
- **Recovery** — goal run after ERROR is bound; has access to ERROR's bindings

`catch_recover` never re-raises on pattern mismatch. For selective catch with re-raise on mismatch, use `catch/3`.

### catch/3

The standard form with selective matching and re-raise on mismatch:

```clausal
safe_div(X, Y, R) <- catch(
    (R == X / Y),
    error(evaluation_error(zero_divisor), _),
    R is "undefined"
)
```

`catch(Goal, Catcher, Recovery)`:

- **Goal** — the goal to execute
- **Catcher** — a pattern unified against the thrown term; re-raises if no match
- **Recovery** — the goal to execute if the exception matches

`catch/3` also intercepts **plain Python exceptions** raised inside the goal
(including from [`++()` escapes](python_integration.md)). These are wrapped as `ClassName(Message)` — a
term whose functor is the exception class name — so the catcher can match
them the same way as logic throw terms:

```clausal
--8<-- "tests/fixtures/docs/exceptions_sigs.txt:catch_3"
```

If the Python exception does not match the catcher it is re-raised unchanged.

This holds wherever in the goal the exception is raised — in the clause that
wrote the `catch/3`, or several predicate calls down. Whether a handler is live
never depends on how the engine chose to compile the call.

### `++` catchers: matching the Python exception object

The `ClassName(Message)` shape above matches by *spelling*. A catcher written
as a [`++()` escape](python_integration.md) instead matches the **original
Python exception object**:

```clausal
risky(X) <- (X is ++int("nope"))

guarded_class(R) <- catch(risky(_A), ++ValueError, R is "caught")

guarded_msg(M) <- catch(risky(_B), ++ValueError(M), true)
```

- A catcher that evaluates to an exception **class** (`++ValueError`) matches
  by `isinstance` — Python semantics, so `++ArithmeticError` catches a
  `ZeroDivisionError` and `++Exception` catches any stray Python exception.
- A catcher that evaluates to an exception **instance** (`++ValueError(M)`)
  matches by `isinstance` on its type and unifies its `args` against the real
  exception's `args` — binding `M` to the actual message. Arity counts: a
  two-arg pattern only matches a two-arg exception.
- A `++` catcher never matches a logic `throw/1` ball, so it stays selective
  in both directions.

Prefer `++` catchers when writing for portability: Clausal's ALL_CAPS
variable rule means a bare `ValueError(M)` catcher is a *functor* here but
reads as a **variable** under ISO's initial-capital rule, silently widening a
specific catcher to a catch-all if the code is ever translated outward. The
marked `++` form makes the Python-specific region visible, and a translator
must handle it deliberately.

The two things `catch/3` does **not** intercept are the signals that are
control flow rather than errors: `halt/0` and `halt/1` (`SystemExit`),
`KeyboardInterrupt`, and abandoning a solution iterator early (`GeneratorExit`).
Those are `BaseException`s and pass straight through any handler.

### halt/0, halt/1

```clausal
done() <- halt()
done_with_code() <- halt(1)
```

`halt()` raises `SystemExit(0)`. `halt(N)` raises `SystemExit(N)`.

---

## Unified Exception Representation

Both logic `throw/1` terms and Python exceptions are represented as plain
Clausal terms during catch. Python exceptions become the term
`ClassName(Message)` (the cell `('ClassName', message)` in Python) — the same
structural shape as any predicate term — so there is
no distinction between catching a logic throw and catching a Python exception:

```clausal
--8<-- "tests/fixtures/docs/exceptions_sigs.txt:unified_exception_representation"
```

---

## Structured Error Terms

Clausal follows the [ISO Prolog](iso_prolog_compatibility_report.md) convention of wrapping errors in `error(ErrorTerm, Context)` compounds. Helper functions in `clausal.logic.exceptions` build these:

| Helper | Error term |
|---|---|
| `type_error(valid_type, culprit)` | `error(type_error(Type, Culprit), ...)` |
| `instantiation_error()` | `error(instantiation_error, ...)` |
| `existence_error(object_type, culprit)` | `error(existence_error(Type, Culprit), ...)` |
| `permission_error(op, type, culprit)` | `error(permission_error(Op, Type, Culprit), ...)` |
| `evaluation_error(kind)` | `error(evaluation_error(Kind), ...)` |
| `domain_error(domain, culprit)` | `error(domain_error(Domain, Culprit), ...)` |

The second argument is ISO `context(Culprit, Message)`. `Culprit` is the
predicate indicator of the builtin that raised the error (`atom_length/2`), and
`Message` is free text; either is an unbound variable when there is none. Every
builder takes the context as text: `"atom_length/2"` gives
`context(atom_length/2, _)`, `"solve/1: the goal is unbound"` gives
`context(solve/1, 'the goal is unbound')`, and text without a leading
`Name/Arity` becomes the message alone, `context(_, 'text')`.

```clausal
catch(atom_length(1, _), error(type_error(T, V), _), true)          % T = atom, V = 1
catch(atom_length(1, _), error(_, context(PI, _)), true)            % PI = atom_length/2
```

### Reading an error term from Python

An error term is a plain **cell**: a tuple whose first element is the functor.
`clausal.cell_functor` and `clausal.cell_args` read it, and `clausal.make_cell`
builds one. They replace the `.functor` / `.args` attributes of the retired
`Compound` class.

```python
from clausal import LogicException, cell_args, cell_functor

try:
    ...  # a query that raises
except LogicException as e:
    assert cell_functor(e.term) == "error"
    formal, context = cell_args(e.term)
    # formal  == ('type_error', 'atom', 1)
    # context == ('context', ('/', 'atom_length', 2), _)
```

`clausal.logic.exceptions.error_context_text(term)` gives the context as display
text (`"atom_length/2"`, `"solve/1: the goal is unbound"`); the indicator is
re-rendered the way `writeq` writes it, so an operator name is in parentheses
(`"(is)/2"`). To select on the message, read the term itself
(`error_context_message(term)`).

---

## Raising well-formedness guards in library code

Shared library predicates (a harness's `library/` modules, for example) often want to
**raise** on malformed input — a non-ground term, the wrong shape, the wrong type —
rather than *fail logically*. Logical failure inside a `findall` is indistinguishable
from a legitimate empty result: the `findall` collapses to `[]`, a downstream
aggregation (`max_list`, etc.) returns its default, and a wrong verdict propagates
silently with nothing to locate. A raised exception, by contrast, travels out of the
`findall` and lands on the loud, well-diagnosed **RAISED** channel — the same channel a
Python-side exception reaches.

No special primitive is needed: `throw/1` **already** does this, and an exception thrown
inside a `findall` body propagates out of it rather than being swallowed as a logical
failure. Write the guard as an ordinary Clausal clause that `throw`s when the input is
malformed. Declare the error functor in `-private([...])` so it constructs a term under
the [strict-atoms default](strict-atoms-migration.md) instead of tripping the
undeclared-atom guard:

```clausal
-private([is_ymd_triple(REF), wf_bad_shape(MSG, CULPRIT)])

is_ymd_triple([Y, M, D]) <- (integer(Y), integer(M), integer(D))

window_days_used(REF_YMD, _DAYS_UNUSED) <- (
    not is_ymd_triple(REF_YMD),
    throw(wf_bad_shape("window_days_used: REF_YMD must be [Y,M,D]", REF_YMD))
)
window_days_used([_Y_UNUSED, _M_UNUSED, _D_UNUSED], 7),

test("malformed input raises, not a silent empty findall") <- (
    catch(
        findall(D, window_days_used("2020-01-01", D), _DAYS_UNUSED),
        wf_bad_shape(_MSG_UNUSED, CULPRIT),
        CULPRIT == "2020-01-01"
    )
)  # nv
```

The thrown term carries both a human-readable message and the offending term, so a test
report (or an outer `catch/3`) names the bad argument, not just the predicate. Uncaught,
it surfaces on the `raised:` line of the failure diagnostic, naming the `findall` the
throw escaped from.

To use the ISO `error(...)` taxonomy above instead of your own functor, import the
constructor from `clausal.logic.exceptions` — the helper builds the nested `error(...)`
term for you, so no functor declaration is needed:

```clausal
from clausal.logic.exceptions import type_error

-private([is_ymd_triple(REF)])

is_ymd_triple([Y, M, D]) <- (integer(Y), integer(M), integer(D))

window_days_used(REF_YMD, _DAYS_UNUSED) <- (
    not is_ymd_triple(REF_YMD),
    throw(type_error("[Y,M,D]", REF_YMD))
)
window_days_used([_Y_UNUSED, _M_UNUSED, _D_UNUSED], 7),

test("iso type_error term raises from a guard") <- (
    catch(
        findall(D, window_days_used("2020-01-01", D), _DAYS_UNUSED),
        error(type_error(_T_UNUSED, CULPRIT), _CTX_UNUSED),
        CULPRIT == "2020-01-01"
    )
)  # nv
```

Regression coverage for the propagation-through-`findall` behaviour lives in
`tests/test_exceptions.py::TestRaisingGuardThroughFindAll` (with the fixture
`tests/fixtures/raising_guard_lib.clausal`).

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
    --8<-- "tests/fixtures/docs/exceptions_sigs.txt:logicexception"
    ```

    **Catch a Python exception (no recovery needed):**
    ```clausal
    --8<-- "tests/fixtures/docs/exceptions_sigs.txt:logicexception_ex2"
    ```

    **catch_recover with error access:**
    ```clausal
    --8<-- "tests/fixtures/docs/exceptions_sigs.txt:logicexception_ex3"
    ```

    **Re-throw after logging:**
    ```clausal
    --8<-- "tests/fixtures/docs/exceptions_sigs.txt:logicexception_ex4"
    ```

    **Catch-all:**
    ```clausal
    --8<-- "tests/fixtures/docs/exceptions_sigs.txt:logicexception_ex5"
    ```

    ---

??? example "Python API"

    ```python
    from clausal.logic.exceptions import LogicException, type_error, instantiation_error

    # Build an error term
    err = type_error("integer", "foo", "succ/2")
    # → ('error', ('type_error', 'integer', 'foo'),
    #    ('context', ('/', 'succ', 2), _))

    # Raise from Python
    raise LogicException(err)
    # The message shows the term as Scryer prints an uncaught error
    # (writeq text with operators), not its Python repr; a variable that
    # occurs once prints as `_`:
    #   Uncaught logic exception: error(type_error(integer,foo),context(succ/2,_))
    ```

    ---

## Compiler Integration

- `Throw(term)` compiles to `raise LogicException(term)`
- `catch(goal, catcher, recovery)` compiles to a `try/except Exception` block;
  `LogicException` yields `.term` directly, any other Python exception is
  wrapped as `ClassName(message)` before being unified against the catcher pattern;
  re-raises if no match
- `Catch(goal, error)` — like `catch/3` but always catches (no re-raise); recovery = `true`
- `catch_recover(goal, error, recovery)` — like `catch/3` but always catches (no re-raise)
- `halt()` / `halt(N)` compile to `raise SystemExit(0)` / `raise SystemExit(N)`

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

*See also: [Builtins](builtins.md) — for a list of built-in predicates that can throw exceptions,
[Control](control.md) — once and time_goal for execution flow.*
