# Clausal Prolog — Structured Logging (`library(logging)`)

!!! note "Clausal Prolog examples"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`), which uses ISO Prolog syntax. Clausal Prolog reaches
    Python only through a `.seam` module, so it imports this module through
    its facade `library(logging)`; the [seam](syntax.md) imports it as `log`
    (`-import_from(log, [...])`).

## Overview

The logging module provides structured logging predicates backed by Python's `logging` module. It exposes logger creation, leveled log output, handler/formatter configuration, and level management as Clausal Prolog predicates.

Since Python's `logging` module is the backend, all of Python's handler ecosystem is available — file rotation, syslog, SMTP, JSON formatters, etc.

```clausal
:- use_module(library(logging), [get_logger/2, info/2, debug/2, set_level/2]).

main(NAME) :-
    get_logger("myapp", L),
    set_level(L, "debug"),
    append("Starting with name=", NAME, DEBUG_MSG),
    debug(L, DEBUG_MSG),
    append(["Hello, ", NAME, "!"], INFO_MSG),
    info(L, INFO_MSG).

test("main") :-
    main("alice").
```

Or import the whole module and qualify each call with the module name:

```clausal
:- use_module(library(logging)).

main :-
    logging:get_logger("myapp", L),
    logging:info(L, "ready").

test("qualified") :-
    main.
```

---

## Import

```clausal
:- use_module(library(logging), [
    get_logger/1, get_logger/2,
    debug/1, debug/2, info/1, info/2, warning/1, warning/2,
    error/1, error/2, critical/1, critical/2,
    set_level/2, get_level/2, is_enabled_for/2, log/3,
    add_handler/2, remove_handler/2,
    stream_handler/2, file_handler/2, set_formatter/2,
    basic_config/1
]).
```

In the seam the module name is `log` (not `logging`) to avoid shadowing Python's stdlib `logging` module; Clausal Prolog names it by its facade, `library(logging)`.

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

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:debug_sig"
```

log `Msg` at DEBUG level. The arity-1 form uses the default `"clausal"` logger.

### `info/1`, `info/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:info_sig"
```

log at INFO level.

### `warning/1`, `warning/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:warning_sig"
```

log at WARNING level.

### `error/1`, `error/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:error_sig"
```

log at ERROR level.

### `critical/1`, `critical/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:critical_sig"
```

log at CRITICAL level.

### `log/3`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:log_sig"
```

log at an arbitrary level. `Level` is a string (`"debug"`, `"info"`, etc.) or an integer.

### Building messages

A message is a string or an atom. Clausal Prolog has no f-strings; a string
is a list of characters, so `append/2,3` builds a message from its parts
(`number_chars/2` turns a number into characters first):

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:fstring_example"
```

In the seam a message can be an f-string, `info(L, f"User {USERID} logged in from {IP}")`, and the seam's [f-string support](io.md) dereferences logic variables at search time.

---

## Logger management

### `get_logger/1`, `get_logger/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:get_logger_sig"
```

Unify `Logger` with a Python `logging.Logger` instance. The arity-1 form returns the default `"clausal"` logger. Logger objects are opaque — they unify via identity, not structure.

Python's logger hierarchy applies: `get_logger("myapp.db", L)` creates a child of `"myapp"`. Calling `get_logger` with the same name always returns the same logger instance.

### `set_level/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:set_level_sig"
```

Set the logger's level. Messages below this level will be discarded (but the logging predicate still succeeds). `Level` is a string or integer.

### `get_level/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:get_level_sig"
```

Unify `Level` with the logger's effective level name, a lowercase atom (e.g. `debug`, `warning`) -- the spelling `set_level/2` takes. A bound `Level` may be the atom or the string, in either case (`'WARNING'`, `"warning"`). A custom level name (`logging.addLevelName(5, "TRACE")`) is a lowercase atom too (`trace`); an unnamed numeric level (`"Level 15"`) comes back as a string.

### `is_enabled_for/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:is_enabled_for_sig"
```

**Succeeds** if the logger would process a message at `Level`; **fails** otherwise. This is the one logging predicate that can fail — useful for guarding expensive message construction:

```clausal
:- use_module(library(logging), [get_logger/2, set_level/2, debug/2,
                                 is_enabled_for/2]).

process(L, DATA) :-
    (   is_enabled_for(L, "debug"),
        append("Processing: ", DATA, MSG),
        debug(L, MSG)
    ;   true
    ),
    do_work(DATA).

do_work(_).

test("guarded") :-
    get_logger("myapp.guard", L),
    set_level(L, "info"),
    \+ is_enabled_for(L, "debug"),
    process(L, "abc").
```

---

## Handler management

### `stream_handler/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:stream_handler_sig"
```

Create a `logging.StreamHandler`. `StreamName` is `"stdout"` or `"stderr"`.

### `file_handler/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:file_handler_sig"
```

Create a `logging.FileHandler` that writes to the given file path.

### `set_formatter/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:set_formatter_sig"
```

Set a `logging.Formatter` on the handler using Python's format string syntax (e.g. `"%(asctime)s [%(levelname)s] %(message)s"`).

### `add_handler/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:add_handler_sig"
```

Add a handler to the logger.

### `remove_handler/2`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:remove_handler_sig"
```

Remove a handler from the logger.

### `basic_config/1`

```text
--8<-- "tests/fixtures/docs/logging_sigs.txt:basic_config_sig"
```

Call `logging.basicConfig()` with a dict of options. In Clausal Prolog build the dict with `dict_pairs/2` (`dict_pairs(OPTS, [level-"info"])`), since ISO syntax has no dict literal (see [Dicts](dicts_sets.md)); the seam writes the literal `{level: "info"}`. Supported keys: `level`, `format`, `datefmt`, `filename`, `filemode`, `stream`. Note: `basicConfig` only takes effect if the root logger has no handlers yet.

---

??? example "Examples"

    ### Basic usage

    ```text
    --8<-- "tests/fixtures/docs/logging_sigs.txt:basic_usage"
    ```

    ### Custom handler and formatter

    ```text
    --8<-- "tests/fixtures/docs/logging_sigs.txt:custom_handler"
    ```

    ### Logger hierarchy

    ```text
    --8<-- "tests/fixtures/docs/logging_sigs.txt:logger_hierarchy"
    ```

    ---

??? abstract "Implementation"

    - **Module:** `clausal/modules/py/logging.py`
    - **Predicates:** `ModulePredicate` wrappers, the same pattern as the other `clausal/modules/py/` modules
    - **Backend:** Python's `logging` module — all predicates delegate to `logging.Logger` methods
    - **Tests:** `tests/test_logging_module.py`, `tests/fixtures/logging_basic.seam`

    ---

??? abstract "Design decisions"

    1. **Logger objects are opaque Python values** — passed around via unification, not inspectable as terms.
    2. **Logging predicates always succeed** — they are side effects. Level filtering happens inside Python's logging; the predicate succeeds regardless.
    3. **`is_enabled_for/2` is the exception** — it succeeds or fails based on level, useful for guarding expensive message construction.
    4. **Level names are strings** — maps to Python constants internally. Both `"warn"`/`"warning"` and `"fatal"`/`"critical"` are accepted.
    5. **Messages are plain text** — no special formatting predicates; a `.clausal` message is built with `append/2,3`, and the seam's f-string support handles interpolation with auto-deref of logic variables.
    6. **Seam module name is `log`** — avoids shadowing Python's `logging` stdlib module in the import machinery.

---

*See also: [I/O](io.md) — `write`, `writeln`, and f-string output · [Python Interop](python_integration.md) — the seam's `++()` escape for custom logging handlers.*
