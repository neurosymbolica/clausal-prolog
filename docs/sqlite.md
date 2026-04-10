# Clausal — SQLite Database (`sqlite` module)

## Overview

The `sqlite` module provides SQLite database predicates backed by Python's `sqlite3` stdlib module. It exposes connection management, parameterized SQL queries, DML execution, and schema introspection as Clausal predicates.

Since Python's `sqlite3` module is the backend, all SQLite features are available — in-memory databases, WAL mode, JSON1 extension, full-text search, etc.

```clausal
-import_from(sqlite, [SQLiteConnect, SQLiteExec, SQLiteQuery, SQLiteDisconnect])

Main <- (
    SQLiteConnect(":memory:", "mydb"),
    SQLiteExec("mydb", "CREATE TABLE users (name TEXT, age INTEGER)"),
    SQLiteExec("mydb", "INSERT INTO users VALUES (?, ?)", ["alice", 30]),
    SQLiteQuery("mydb", "SELECT name FROM users WHERE age > ?", [25], NAME),
    ++print(f"Found: {NAME}")
)
```

Or via [module import](import.md):

```clausal
-import_module(sqlite)

Main <- (
    sqlite.SQLiteConnect(":memory:", "db"),
    sqlite.SQLiteExec("db", "CREATE TABLE t (x INTEGER)"),
    sqlite.SQLiteQuery("db", "SELECT x FROM t", X)
)
```

---

## Import

```clausal
-import_from(sqlite, [
    SQLiteConnect, SQLiteDisconnect, SQLiteCurrentConnection,
    SQLiteQuery, SQLiteExec, SQLiteRowCount,
    SQLiteTable, SQLiteColumn
])
```

---

## Connection management

Connections are identified by string aliases. A module-level registry maps aliases to `sqlite3.Connection` objects. The registry is thread-safe.

### `SQLiteConnect/2`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:connect_sig"
```

Open a SQLite database at `Path` and register it under `Alias`. `Path` can be a file path or `":memory:"` for an in-memory database.

**Idempotent**: if `Alias` is already connected, succeeds without opening a new connection.

### `SQLiteDisconnect/1`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:disconnect_sig"
```

Close the connection and unregister `Alias`. **Fails** if `Alias` is not connected.

### `SQLiteCurrentConnection/1`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:current_connection_sig"
```

when `Alias` is unbound, **nondeterministically enumerates** all open connection aliases. when `Alias` is ground, succeeds if that alias is currently connected.

```clausal
ListDbs <- (
    SQLiteCurrentConnection(A),
    ++print(f"Open: {A}")
)
```

---

## Raw SQL queries

All SQL execution uses parameterized queries (`?` placeholders) internally. **String interpolation into SQL is never used** — this prevents SQL injection by design.

### `SQLiteQuery/3`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:query_sig"
```

Execute a SELECT query and **nondeterministically iterate** over result rows via [backtracking](control.md). Each solution binds `Row` to one row. Multi-column rows are Python tuples; single-column rows are unwrapped to the bare value.

```clausal
# Multi-column: Row unifies with a tuple
AllUsers(ROW) <- SQLiteQuery("db", "SELECT name, age FROM users", ROW)

# Single-column: Row unifies with the value directly
AllNames(NAME) <- SQLiteQuery("db", "SELECT name FROM users", NAME)
```

**Fails** (produces zero solutions) if the query returns no rows.

### `SQLiteQuery/4`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:query_params_sig"
```

Parameterized query with `?` placeholders. `Params` is a list of values.

```clausal
OlderThan(MIN_AGE, NAME) <- (
    SQLiteQuery("db", "SELECT name FROM users WHERE age > ?", [MIN_AGE], NAME)
)
```

### `SQLiteExec/2`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:exec_sig"
```

Execute a DDL or DML statement (CREATE, INSERT, UPDATE, DELETE). **Succeeds once** and auto-commits.

```clausal
Setup <- (
    SQLiteExec("db", "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"),
    SQLiteExec("db", "INSERT INTO items VALUES (1, 'widget')")
)
```

### `SQLiteExec/3`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:exec_params_sig"
```

Parameterized DML with `?` placeholders. Auto-commits.

```clausal
AddUser(NAME, AGE) <- (
    SQLiteExec("db", "INSERT INTO users VALUES (?, ?)", [NAME, AGE])
)
```

### `SQLiteRowCount/3`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:row_count_sig"
```

Execute DML and unify `Count` with the number of affected rows.

```clausal
Cleanup(N) <- (
    SQLiteRowCount("db", "DELETE FROM sessions WHERE expired = 1", N),
    ++print(f"Removed {N} expired sessions")
)
```

---

## Schema introspection

### `SQLiteTable/2`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:table_sig"
```

when `TableName` is unbound, **nondeterministically enumerates** all table names. when ground, succeeds if that table exists.

```clausal
HasUsersTable <- SQLiteTable("db", "users")

ListTables(T) <- SQLiteTable("db", T)
```

### `SQLiteColumn/4`

```clausal
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:column_sig"
```

Enumerate columns of a table. Yields `(ColName, ColType)` pairs. Column types are SQLite type strings: `"TEXT"`, `"INTEGER"`, `"REAL"`, `"BLOB"`, etc.

```clausal
ShowSchema(COL, TYPE) <- (
    SQLiteColumn("db", "users", COL, TYPE),
    ++print(f"  {COL}: {TYPE}")
)
```

---

??? example "Examples"

    ### CRUD operations

    ```clausal
    --8<-- "tests/fixtures/docs/sqlite_sigs.txt:crud_example"
    ```

    ### Joining tables

    ```clausal
    --8<-- "tests/fixtures/docs/sqlite_sigs.txt:join_example"
    ```

    ### Schema exploration

    ```clausal
    --8<-- "tests/fixtures/docs/sqlite_sigs.txt:schema_example"
    ```

    ---

## Safety

- **No SQL injection**: all queries use `cursor.execute(sql, params)` with `?` placeholders. String formatting is never used for SQL construction.
- **Connection aliases are strings**: validated at lookup time. Invalid aliases produce a clear `ValueError`.
- **Thread-safe registry**: the connection registry uses a `threading.Lock`.

---

??? abstract "Implementation"

    - **Module:** `clausal/modules/sqlite.py`
    - **Adapter class:** `_SQLitePredicate` (same pattern as `_RegexPredicate` in `clausal/modules/regex.py`)
    - **Backend:** Python's `sqlite3` module (stdlib, always available)
    - **Tests:** `tests/test_sqlite.py` (37 tests: 31 unit + 6 `.clausal` integration)

    ---

??? abstract "Design decisions"

    1. **Named connection aliases** — connections are identified by string aliases, not opaque handles. This makes them easy to reference across predicates in `.clausal` files where values must be ground or logic variables.
    2. **Idempotent connect** — `SQLiteConnect` with an existing alias succeeds silently. This simplifies predicates that call a shared `setup` predicate from multiple entry points.
    3. **Auto-commit on exec** — `SQLiteExec` commits after each statement. For multi-statement atomicity, use Python's transaction support via [`++()`](python_integration.md) interop.
    4. **Single-column unwrap** — `SQLiteQuery` unwraps single-column rows to bare values (not 1-tuples), making common patterns like `SELECT name FROM ...` cleaner.
    5. **Nondeterministic iteration** — `SQLiteQuery`, `SQLiteTable`, `SQLiteColumn`, and `SQLiteCurrentConnection` yield one solution per row/item on backtracking, following the standard Prolog database query pattern.
    6. **No C FFI** — unlike prosqlite (SWI-Prolog) which wraps libsqlite3 via C, this module delegates entirely to Python's `sqlite3` stdlib. Zero external dependencies.

---

*See also: [Database Ops](database_ops.md) — Clausal's assert/retract for in-memory facts · [Python Interop](python_integration.md) — direct SQL via `++()` escape.*
