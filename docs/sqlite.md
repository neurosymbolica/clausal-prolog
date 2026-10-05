# Clausal Prolog — SQLite Database (`sqlite` module)

## Overview

The `sqlite` module provides SQLite database predicates backed by Python's `sqlite3` stdlib module. It exposes connection management, parameterized SQL queries, DML execution, and schema introspection as Clausal Prolog predicates.

Since Python's `sqlite3` module is the backend, all SQLite features are available — in-memory databases, WAL mode, JSON1 extension, full-text search, etc.

```seam
-import_from(sqlite, [connect, exec, query, disconnect])

main <- (
    connect(":memory:", "mydb"),
    exec("mydb", "CREATE TABLE users (name TEXT, age INTEGER)"),
    exec("mydb", "INSERT INTO users VALUES (?, ?)", ["alice", 30]),
    query("mydb", "SELECT name FROM users WHERE age > ?", [25], NAME),
    ++print(f"Found: {NAME}")
)
```

Or via [module import](import.md):

```seam
-import_module(sqlite)

main <- (
    sqlite.connect(":memory:", "db"),
    sqlite.exec("db", "CREATE TABLE t (x INTEGER)"),
    sqlite.query("db", "SELECT x FROM t", X),
    ++print(f"Found: {X}")
)
```

---

## Import

```seam
-import_from(sqlite, [
    connect, disconnect, current_connection,
    query, exec, row_count,
    table, column
])
```

---

## Connection management

Connections are identified by string aliases. A module-level registry maps aliases to `sqlite3.Connection` objects. The registry is thread-safe.

### `connect/2`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:connect_sig"
```

Open a SQLite database at `Path` and register it under `Alias`. `Path` can be a file path or `":memory:"` for an in-memory database.

**Idempotent**: if `Alias` is already connected, succeeds without opening a new connection.

### `disconnect/1`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:disconnect_sig"
```

Close the connection and unregister `Alias`. **Fails** if `Alias` is not connected.

### `current_connection/1`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:current_connection_sig"
```

when `Alias` is unbound, **nondeterministically enumerates** all open connection aliases, as atoms (an alias is a name; a bound `Alias` may be an atom or a string). when `Alias` is ground, succeeds if that alias is currently connected.

```seam
list_dbs <- (
    current_connection(A),
    ++print(f"Open: {A}")
)
```

---

## Raw SQL queries

All SQL execution uses parameterized queries (`?` placeholders) internally. **String interpolation into SQL is never used** — this prevents SQL injection by design.

### `query/3`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:query_sig"
```

Execute a SELECT query and **nondeterministically iterate** over result rows via [backtracking](control.md). Each solution binds `Row` to one row. Single-column rows are unwrapped to the bare value. A multi-column row is the tuple of its values: `SELECT name, age` gives `("alice", 30)`. Match it against a tuple pattern, `(NAME, AGE)`, to take it apart. A TEXT value is a **string** (database text is data, not a symbol) in both shapes; an INTEGER or REAL is a number and NULL is `None`.

```seam
# Multi-column: Row unifies with a tuple
all_users(ROW) <- query("db", "SELECT name, age FROM users", ROW)

# ...which a tuple pattern takes apart: NAME = "alice" (a string), AGE = 30
user_age(NAME, AGE) <- query("db", "SELECT name, age FROM users", (NAME, AGE))

# Single-column: Row unifies with the value directly
all_names(NAME) <- query("db", "SELECT name FROM users", NAME)
```

**Fails** (produces zero solutions) if the query returns no rows.

### `query/4`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:query_params_sig"
```

Parameterized query with `?` placeholders. `Params` is a list of values.

```seam
older_than(MIN_AGE, NAME) <- (
    query("db", "SELECT name FROM users WHERE age > ?", [MIN_AGE], NAME)
)
```

### `exec/2`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:exec_sig"
```

Execute a DDL or DML statement (CREATE, INSERT, UPDATE, DELETE). **Succeeds once** and auto-commits.

```seam
setup <- (
    exec("db", "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"),
    exec("db", "INSERT INTO items VALUES (1, 'widget')")
)
```

### `exec/3`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:exec_params_sig"
```

Parameterized DML with `?` placeholders. Auto-commits.

```seam
add_user(NAME, AGE) <- (
    exec("db", "INSERT INTO users VALUES (?, ?)", [NAME, AGE])
)
```

### `row_count/3`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:row_count_sig"
```

Execute DML and unify `Count` with the number of affected rows.

```seam
cleanup(N) <- (
    row_count("db", "DELETE FROM sessions WHERE expired = 1", N),
    ++print(f"Removed {N} expired sessions")
)
```

---

## Schema introspection

### `table/2`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:table_sig"
```

when `TableName` is unbound, **nondeterministically enumerates** all table names. when ground, succeeds if that table exists.

```seam
has_users_table <- table("db", "users")

list_tables(T) <- table("db", T)
```

### `column/4`

```seam
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:column_sig"
```

Enumerate columns of a table, one `ColName`/`ColType` solution per column. Both are strings; column types are SQLite type names: `"TEXT"`, `"INTEGER"`, `"REAL"`, `"BLOB"`, etc.

```seam
show_schema(COL, TYPE) <- (
    column("db", "users", COL, TYPE),
    ++print(f"  {COL}: {TYPE}")
)
```

---

??? example "Examples"

    ### CRUD operations

    ```seam
    --8<-- "tests/fixtures/docs/sqlite_sigs.txt:crud_example"
    ```

    ### Joining tables

    ```seam
    --8<-- "tests/fixtures/docs/sqlite_sigs.txt:join_example"
    ```

    ### Schema exploration

    ```seam
    --8<-- "tests/fixtures/docs/sqlite_sigs.txt:schema_example"
    ```

    ---

## Safety

- **No SQL injection**: all queries use `cursor.execute(sql, params)` with `?` placeholders. String formatting is never used for SQL construction.
- **Connection aliases are strings**: validated at lookup time. An alias that is not connected raises (today the thrown term is `'ValueError'('No SQLite connection with alias \'nodb\'')`, not an ISO error term).
- **Thread-safe registry**: the connection registry uses a `threading.Lock`.

---

??? abstract "Implementation"

    - **Module:** `clausal/modules/py/sqlite.py`
    - **Predicates:** `ModulePredicate` wrappers, the same pattern as the other `clausal/modules/py/` modules
    - **Backend:** Python's `sqlite3` module (stdlib, always available)
    - **Tests:** `tests/test_sqlite.py`

    ---

??? abstract "Design decisions"

    1. **Named connection aliases** — connections are identified by string aliases, not opaque handles. This makes them easy to reference across predicates in `.seam` files where values must be ground or logic variables.
    2. **Idempotent connect** — `connect` with an existing alias succeeds silently. This simplifies predicates that call a shared `setup` predicate from multiple entry points.
    3. **Auto-commit on exec** — `exec` commits after each statement. For multi-statement atomicity, use Python's transaction support via [`++()`](python_integration.md) interop.
    4. **Single-column unwrap** — `query` unwraps single-column rows to bare values (not 1-tuples), making common patterns like `SELECT name FROM ...` cleaner.
    5. **Nondeterministic iteration** — `query`, `table`, `column`, and `current_connection` yield one solution per row/item on backtracking, following the standard Prolog database query pattern.
    6. **No C FFI** — unlike prosqlite (SWI-Prolog) which wraps libsqlite3 via C, this module delegates entirely to Python's `sqlite3` stdlib. Zero external dependencies.

---

*See also: [Database Ops](database_ops.md) — Clausal Prolog's assert/retract for in-memory facts · [Python Interop](python_integration.md) — direct SQL via `++()` escape.*
