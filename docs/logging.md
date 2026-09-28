# Clausal — Structured Logging (`log` module)

## Overview

The `log` module provides structured logging predicates backed by Python's `logging` module. It exposes logger creation, leveled log output, handler/formatter configuration, and level management as Clausal predicates.

Since Python's `logging` module is the backend, all of Python's handler ecosystem is available — file rotation, syslog, SMTP, JSON formatters, etc.

```clausal
-import_from(log, [get_logger, info, debug, warning, error, set_level])

main(NAME) <- (
    get_logger("myapp", L),
    set_level(L, "debug"),
    debug(L, f"Starting with name={NAME}"),
    info(L, f"Hello, {NAME}!")
)
```

Or via [module import](import.md):

```clausal
-import_module(log)

main <- (
    log.get_logger("myapp", L),
    log.info(L, "ready")
)
```

---

## Import

```clausal
-import_from(log, [
    get_logger, debug, info, warning, error, critical,
    set_level, get_level, is_enabled_for, log,
    add_handler, remove_handler,
    stream_handler, file_handler, set_formatter,
    basic_config
])
```

The module name is `log` (not `logging`) to avoid shadowing Python's stdlib `logging` module.

---

## log levels

Levels follow Python's standard hierarchy (ascending severity):

| Level | String | Python constant |
|-------|--------|-----------------|
| DEBUG | `"debug"` | `logging.DEBUG` (10) |
| INFO | `"info"` | `logging.INFO` (20) |
| WARNING | `"warning"` (or `"warn"`) | `logging.WARNING` (30) |
| ERROR | `"error"` | `logging.ERROR` (40) |
| CRITICAL | `"critical"` (or `"fatal"`) | `logging.CRITICAL` (50) |

Level names are case-insensitive, written as strings (or atoms) when passed to predicates.

---

## Logging predicates

All logging predicates **always succeed** — they are side-effects. A message below the logger's configured level is silently discarded (the predicate still succeeds).

### `debug/1`, `debug/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:debug_sig"
```

log `Msg` at DEBUG level. The arity-1 form uses the default `"clausal"` logger.

### `info/1`, `info/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:info_sig"
```

log at INFO level.

### `warning/1`, `warning/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:warning_sig"
```

log at WARNING level.

### `error/1`, `error/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:error_sig"
```

log at ERROR level.

### `critical/1`, `critical/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:critical_sig"
```

log at CRITICAL level.

### `log/3`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:log_sig"
```

log at an arbitrary level. `Level` is a string (`"debug"`, `"info"`, etc.) or an integer.

### Messages and f-strings

A message is a string or an atom (an f-string is a string, like `"..."`). Clausal's [f-string support](io.md) means interpolation works naturally:

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:fstring_example"
```

Logic variables in f-strings are auto-dereferenced at search time.

---

## Logger management

### `get_logger/1`, `get_logger/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:get_logger_sig"
```

Unify `Logger` with a Python `logging.Logger` instance. The arity-1 form returns the default `"clausal"` logger. Logger objects are opaque — they unify via identity, not structure.

Python's logger hierarchy applies: `get_logger("myapp.db", L)` creates a child of `"myapp"`. Calling `get_logger` with the same name always returns the same logger instance.

### `set_level/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:set_level_sig"
```

Set the logger's level. Messages below this level will be discarded (but the logging predicate still succeeds). `Level` is a string or integer.

### `get_level/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:get_level_sig"
```

Unify `Level` with the logger's effective level name, a string (e.g. `"DEBUG"`, `"WARNING"`).

### `is_enabled_for/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:is_enabled_for_sig"
```

**Succeeds** if the logger would process a message at `Level`; **fails** otherwise. This is the one logging predicate that can fail — useful for guarding expensive message construction:

```clausal
process(L, DATA) <- (
    ((is_enabled_for(L, "debug"), debug(L, f"Processing: {DATA}")) or True),
    do_work(DATA)
)
```

---

## Handler management

### `stream_handler/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:stream_handler_sig"
```

Create a `logging.StreamHandler`. `StreamName` is `"stdout"` or `"stderr"`.

### `file_handler/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:file_handler_sig"
```

Create a `logging.FileHandler` that writes to the given file path.

### `set_formatter/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:set_formatter_sig"
```

Set a `logging.Formatter` on the handler using Python's format string syntax (e.g. `"%(asctime)s [%(levelname)s] %(message)s"`).

### `add_handler/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:add_handler_sig"
```

Add a handler to the logger.

### `remove_handler/2`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:remove_handler_sig"
```

Remove a handler from the logger.

### `basic_config/1`

```clausal
--8<-- "tests/fixtures/docs/logging_sigs.txt:basic_config_sig"
```

Call `logging.basicConfig()` with a dict of options (`{level: "info"}`, keys declared or single-quoted). Supported keys: `level`, `format`, `datefmt`, `filename`, `filemode`, `stream`. Note: `basicConfig` only takes effect if the root logger has no handlers yet.

---

??? example "Examples"

    ### Basic usage

    ```clausal
    --8<-- "tests/fixtures/docs/logging_sigs.txt:basic_usage"
    ```

    ### Custom handler and formatter

    ```clausal
    --8<-- "tests/fixtures/docs/logging_sigs.txt:custom_handler"
    ```

    ### Logger hierarchy

    ```clausal
    --8<-- "tests/fixtures/docs/logging_sigs.txt:logger_hierarchy"
    ```

    ---

??? abstract "Implementation"

    - **Module:** `clausal/modules/py/logging.py`
    - **Predicates:** `ModulePredicate` wrappers, the same pattern as the other `clausal/modules/py/` modules
    - **Backend:** Python's `logging` module — all predicates delegate to `logging.Logger` methods
    - **Tests:** `tests/test_logging_module.py`, `tests/fixtures/logging_basic.clausal`

    ---

??? abstract "Design decisions"

    1. **Logger objects are opaque Python values** — passed around via unification, not inspectable as terms.
    2. **Logging predicates always succeed** — they are side effects. Level filtering happens inside Python's logging; the Clausal predicate succeeds regardless.
    3. **`is_enabled_for/2` is the exception** — it succeeds or fails based on level, useful for guarding expensive message construction.
    4. **Level names are strings** — maps to Python constants internally. Both `"warn"`/`"warning"` and `"fatal"`/`"critical"` are accepted.
    5. **f-string messages** — no special formatting needed; Clausal's f-string support handles interpolation with auto-deref of logic variables.
    6. **Module name is `log`** — avoids shadowing Python's `logging` stdlib module in the import machinery.

---

*See also: [I/O](io.md) — `write`, `writeln`, and f-string output · [Python Interop](python_integration.md) — `++()` escape for custom logging handlers.*
