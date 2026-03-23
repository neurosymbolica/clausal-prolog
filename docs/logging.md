# Clausal — Structured Logging (`log` module)

## Overview

The `log` module provides structured logging predicates backed by Python's `logging` module. It exposes logger creation, leveled log output, handler/formatter configuration, and level management as Clausal predicates.

Since Python's `logging` module is the backend, all of Python's handler ecosystem is available — file rotation, syslog, SMTP, JSON formatters, etc.

```clausal
-import_from(log, [GetLogger, Info, Debug, Warning, Error, SetLevel])

Main(NAME) <- (
    GetLogger("myapp", L),
    SetLevel(L, "debug"),
    Debug(L, f"Starting with name={NAME}"),
    Info(L, f"Hello, {NAME}!")
)
```

Or via module import:

```clausal
-import_module(log)

Main <- (
    log.GetLogger("myapp", L),
    log.Info(L, "ready")
)
```

---

## Import

```clausal
-import_from(log, [
    GetLogger, Debug, Info, Warning, Error, Critical,
    SetLevel, GetLevel, IsEnabledFor, Log,
    AddHandler, RemoveHandler,
    StreamHandler, FileHandler, SetFormatter,
    BasicConfig
])
```

The module name is `log` (not `logging`) to avoid shadowing Python's stdlib `logging` module.

---

## Log levels

Levels follow Python's standard hierarchy (ascending severity):

| Level | String | Python constant |
|-------|--------|-----------------|
| DEBUG | `"debug"` | `logging.DEBUG` (10) |
| INFO | `"info"` | `logging.INFO` (20) |
| WARNING | `"warning"` (or `"warn"`) | `logging.WARNING` (30) |
| ERROR | `"error"` | `logging.ERROR` (40) |
| CRITICAL | `"critical"` (or `"fatal"`) | `logging.CRITICAL` (50) |

Level names are case-insensitive strings when passed to predicates.

---

## Logging predicates

All logging predicates **always succeed** — they are side-effects. A message below the logger's configured level is silently discarded (the predicate still succeeds).

### `Debug/1`, `Debug/2`

```clausal
# skip
Debug(+Msg)
Debug(+Logger, +Msg)
```

Log `Msg` at DEBUG level. The arity-1 form uses the default `"clausal"` logger.

### `Info/1`, `Info/2`

```clausal
# skip
Info(+Msg)
Info(+Logger, +Msg)
```

Log at INFO level.

### `Warning/1`, `Warning/2`

```clausal
# skip
Warning(+Msg)
Warning(+Logger, +Msg)
```

Log at WARNING level.

### `Error/1`, `Error/2`

```clausal
# skip
Error(+Msg)
Error(+Logger, +Msg)
```

Log at ERROR level.

### `Critical/1`, `Critical/2`

```clausal
# skip
Critical(+Msg)
Critical(+Logger, +Msg)
```

Log at CRITICAL level.

### `Log/3`

```clausal
# skip
Log(+Logger, +Level, +Msg)
```

Log at an arbitrary level. `Level` is a string (`"debug"`, `"info"`, etc.) or an integer.

### Messages and f-strings

Messages are Python strings. Clausal's f-string support means interpolation works naturally:

```clausal
# skip
Info(L, f"User {USERID} logged in from {IP}")
```

Logic variables in f-strings are auto-dereferenced at search time.

---

## Logger management

### `GetLogger/1`, `GetLogger/2`

```clausal
# skip
GetLogger(-Logger)
GetLogger(+Name, -Logger)
```

Unify `Logger` with a Python `logging.Logger` instance. The arity-1 form returns the default `"clausal"` logger. Logger objects are opaque — they unify via identity, not structure.

Python's logger hierarchy applies: `GetLogger("myapp.db", L)` creates a child of `"myapp"`. Calling `GetLogger` with the same name always returns the same logger instance.

### `SetLevel/2`

```clausal
# skip
SetLevel(+Logger, +Level)
```

Set the logger's level. Messages below this level will be discarded (but the logging predicate still succeeds). `Level` is a string or integer.

### `GetLevel/2`

```clausal
# skip
GetLevel(+Logger, -Level)
```

Unify `Level` with the logger's effective level name (e.g. `"DEBUG"`, `"WARNING"`).

### `IsEnabledFor/2`

```clausal
# skip
IsEnabledFor(+Logger, +Level)
```

**Succeeds** if the logger would process a message at `Level`; **fails** otherwise. This is the one logging predicate that can fail — useful for guarding expensive message construction:

```clausal
Process(L, DATA) <- (
    (IsEnabledFor(L, "debug"), Debug(L, f"Processing: {DATA}") or True),
    do_work(DATA)
)
```

---

## Handler management

### `StreamHandler/2`

```clausal
# skip
StreamHandler(+StreamName, -Handler)
```

Create a `logging.StreamHandler`. `StreamName` is `"stdout"` or `"stderr"`.

### `FileHandler/2`

```clausal
# skip
FileHandler(+Path, -Handler)
```

Create a `logging.FileHandler` that writes to the given file path.

### `SetFormatter/2`

```clausal
# skip
SetFormatter(+Handler, +FormatString)
```

Set a `logging.Formatter` on the handler using Python's format string syntax (e.g. `"%(asctime)s [%(levelname)s] %(message)s"`).

### `AddHandler/2`

```clausal
# skip
AddHandler(+Logger, +Handler)
```

Add a handler to the logger.

### `RemoveHandler/2`

```clausal
# skip
RemoveHandler(+Logger, +Handler)
```

Remove a handler from the logger.

### `BasicConfig/1`

```clausal
# skip
BasicConfig(+Opts)
```

Call `logging.basicConfig()` with a Python dict of options. Supported keys: `level`, `format`, `datefmt`, `filename`, `filemode`, `stream`. Note: `basicConfig` only takes effect if the root logger has no handlers yet.

---

??? example "Examples"

    ### Basic usage

    ```clausal
# skip
    -import_from(log, [GetLogger, Info, Warning, SetLevel])
    
    Init(L) <- (
        GetLogger("myapp", L),
        SetLevel(L, "info"),
        Info(L, "Application started")
    )

    ProcessItem(L, ITEM) <- (
        ITEM > 0,
        Info(L, f"Processing item {ITEM}")
    )
    ProcessItem(L, ITEM) <- (
        ITEM =< 0,
        Warning(L, f"Skipping invalid item {ITEM}")
    )
    ```

    ### Custom handler and formatter

    ```clausal
# skip
    -import_from(log, [
        GetLogger, Info, SetLevel,
        StreamHandler, FileHandler, SetFormatter, AddHandler
    ])
    
    SetupLogging(L) <- (
        GetLogger("myapp", L),
        SetLevel(L, "debug"),
        FileHandler("/var/log/myapp.log", FH),
        SetFormatter(FH, "%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
        AddHandler(L, FH),
        StreamHandler("stderr", SH),
        SetFormatter(SH, "%(levelname)s: %(message)s"),
        AddHandler(L, SH)
    )
    ```

    ### Logger hierarchy

    ```clausal
# skip
    -import_from(log, [GetLogger, Info, SetLevel])
    
    Setup <- (
        GetLogger("myapp", PARENT),
        SetLevel(PARENT, "info"),
        GetLogger("myapp.db", DBLOG),
        SetLevel(DBLOG, "debug"),
        Info(DBLOG, "DB logger inherits parent's handlers")
    )
    ```

    ---

??? abstract "Implementation"

    - **Module:** `clausal/modules/log.py`
    - **Adapter class:** `_LoggingPredicate` (same pattern as `_RegexPredicate` in `clausal/modules/regex.py`)
    - **Backend:** Python's `logging` module — all predicates delegate to `logging.Logger` methods
    - **Tests:** `tests/test_logging_module.py` (67 tests), `tests/fixtures/logging_basic.clausal` (30 fixture tests)

    ---

??? abstract "Design decisions"

    1. **Logger objects are opaque Python values** — passed around via unification, not inspectable as terms.
    2. **Logging predicates always succeed** — they are side effects. Level filtering happens inside Python's logging; the Clausal predicate succeeds regardless.
    3. **`IsEnabledFor/2` is the exception** — it succeeds or fails based on level, useful for guarding expensive message construction.
    4. **Level names are strings** — maps to Python constants internally. Both `"warn"`/`"warning"` and `"fatal"`/`"critical"` are accepted.
    5. **f-string messages** — no special formatting needed; Clausal's f-string support handles interpolation with auto-deref of logic variables.
    6. **Module name is `log`** — avoids shadowing Python's `logging` stdlib module in the import machinery.

---

*See also: [I/O](io.md) — `Write`, `Writeln`, and f-string output · [Python Interop](python_integration.md) — `++()` escape for custom logging handlers.*
