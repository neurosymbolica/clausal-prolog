# Clausal Prolog — SQLite Database (`sqlite` module)

!!! note "Clausal Prolog examples"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`), which uses ISO Prolog syntax. Clausal Prolog reaches
    Python only through a `.seam` module, so it imports this module through
    its facade `library(sqlite)`; the [seam](syntax.md) imports `sqlite`
    directly (`-import_from(sqlite, [...])`). One feature is seam-only: a
    multi-column row (see [`query/3`](#query3)).

## Overview

The `sqlite` module provides SQLite database predicates backed by Python's `sqlite3` stdlib module. It exposes connection management, parameterized SQL queries, DML execution, and schema introspection as Clausal Prolog predicates.

Since Python's `sqlite3` module is the backend, all SQLite features are available — in-memory databases, WAL mode, JSON1 extension, full-text search, etc.

```clausal
:- use_module(library(sqlite), [connect/2, exec/2, exec/3, query/4]).

main(NAME) :-
    connect(":memory:", "mydb"),
    exec("mydb", "CREATE TABLE users (name TEXT, age INTEGER)"),
    exec("mydb", "INSERT INTO users VALUES (?, ?)", ["alice", 30]),
    query("mydb", "SELECT name FROM users WHERE age > ?", [25], NAME),
    format("Found: ~s~n", [NAME]).

test("main") :-
    main(NAME),
    NAME == "alice".
```

Or import the whole module and qualify each call with the module name:

```clausal
:- use_module(library(sqlite)).

main(X) :-
    sqlite:connect(":memory:", "db"),
    sqlite:exec("db", "CREATE TABLE t (x INTEGER)"),
    sqlite:exec("db", "INSERT INTO t VALUES (7)"),
    sqlite:query("db", "SELECT x FROM t", X),
    format("Found: ~w~n", [X]).

test("qualified") :-
    main(X),
    X == 7.
```

A TEXT value is a string, so `format/2` prints it with `~s`; `~w` writes a
string as its list of characters. (The seam prints with a Python
f-string, `++print(f"Found: {NAME}")`.)

---

## Import

```clausal
:- use_module(library(sqlite), [
    connect/2, disconnect/1, current_connection/1,
    query/3, query/4, exec/2, exec/3, row_count/3,
    table/2, column/4
]).
```

---

## Connection management

Connections are identified by string aliases. A module-level registry maps aliases to `sqlite3.Connection` objects. The registry is thread-safe.

### `connect/2`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:connect_sig"
```

Open a SQLite database at `Path` and register it under `Alias`. `Path` can be a file path or `":memory:"` for an in-memory database.

**Idempotent**: if `Alias` is already connected, succeeds without opening a new connection.

### `disconnect/1`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:disconnect_sig"
```

Close the connection and unregister `Alias`. **Fails** if `Alias` is not connected.

### `current_connection/1`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:current_connection_sig"
```

when `Alias` is unbound, **nondeterministically enumerates** all open connection aliases, as atoms (an alias is a name; a bound `Alias` may be an atom or a string). when `Alias` is ground, succeeds if that alias is currently connected.

```clausal
:- use_module(library(sqlite), [connect/2, current_connection/1]).

list_dbs :-
    current_connection(A),
    format("Open: ~w~n", [A]).

test("enumerate") :-
    connect(":memory:", "doc_cc"),
    findall(A, current_connection(A), ALIASES),
    in_(doc_cc, ALIASES).

test("ground alias") :-
    connect(":memory:", "doc_cc"),
    current_connection("doc_cc"),
    current_connection(doc_cc).
```

---

## Raw SQL queries

All SQL execution uses parameterized queries (`?` placeholders) internally. **String interpolation into SQL is never used** — this prevents SQL injection by design.

### `query/3`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:query_sig"
```

Execute a SELECT query and **nondeterministically iterate** over result rows via [backtracking](control.md). Each solution binds `Row` to one row. Single-column rows are unwrapped to the bare value. A multi-column row is the tuple of its values: `SELECT name, age` gives `("alice", 30)`. In the seam, a tuple pattern, `(NAME, AGE)`, takes it apart; Clausal Prolog
has no term that unifies with that tuple (`(NAME, AGE)` is the `','/2` compound
there, and `[NAME, AGE]` a list; both fail), so a multi-column row is
**seam-only**. A TEXT value is a **string** (database text is data, not a symbol) in both shapes; an INTEGER or REAL is a number and NULL is `None`.

```clausal
:- use_module(library(sqlite), [connect/2, exec/2, query/3]).

setup :-
    connect(":memory:", "doc_q3"),
    exec("doc_q3", "CREATE TABLE IF NOT EXISTS users (name TEXT, age INTEGER)"),
    exec("doc_q3", "DELETE FROM users"),
    exec("doc_q3", "INSERT INTO users VALUES ('alice', 30)"),
    exec("doc_q3", "INSERT INTO users VALUES ('bob', 25)").

% Single-column: Row unifies with the value directly
all_names(NAME) :-
    query("doc_q3", "SELECT name FROM users", NAME).

test("single column") :-
    setup,
    findall(NAME, all_names(NAME), NAMES),
    NAMES == ["alice", "bob"].

test("text is a string") :-
    setup,
    all_names(NAME),
    string(NAME).
```

The multi-column forms, in the seam:

```seam
-import_from(sqlite, [query])

# Multi-column: Row unifies with a tuple
all_users(ROW) <- query("db", "SELECT name, age FROM users", ROW)

# ...which a tuple pattern takes apart: NAME = "alice" (a string), AGE = 30
user_age(NAME, AGE) <- query("db", "SELECT name, age FROM users", (NAME, AGE))
```

**Fails** (produces zero solutions) if the query returns no rows.

### `query/4`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:query_params_sig"
```

Parameterized query with `?` placeholders. `Params` is a list of values.

```clausal
:- use_module(library(sqlite), [connect/2, exec/2, query/4]).

older_than(MIN_AGE, NAME) :-
    query("doc_q4", "SELECT name FROM users WHERE age > ?", [MIN_AGE], NAME).

test("older than") :-
    connect(":memory:", "doc_q4"),
    exec("doc_q4", "CREATE TABLE users (name TEXT, age INTEGER)"),
    exec("doc_q4", "INSERT INTO users VALUES ('alice', 30)"),
    exec("doc_q4", "INSERT INTO users VALUES ('bob', 20)"),
    findall(NAME, older_than(25, NAME), NAMES),
    NAMES == ["alice"].

test("no rows fails") :-
    \+ older_than(99, _).
```

### `exec/2`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:exec_sig"
```

Execute a DDL or DML statement (CREATE, INSERT, UPDATE, DELETE). **Succeeds once** and auto-commits.

```clausal
:- use_module(library(sqlite), [connect/2, exec/2, query/3]).

setup :-
    connect(":memory:", "doc_e2"),
    exec("doc_e2", "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"),
    exec("doc_e2", "INSERT INTO items VALUES (1, 'widget')").

test("exec") :-
    setup,
    query("doc_e2", "SELECT name FROM items", NAME),
    NAME == "widget".
```

### `exec/3`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:exec_params_sig"
```

Parameterized DML with `?` placeholders. Auto-commits.

```clausal
:- use_module(library(sqlite), [connect/2, exec/2, exec/3, query/4]).

add_user(NAME, AGE) :-
    exec("doc_e3", "INSERT INTO users VALUES (?, ?)", [NAME, AGE]).

test("add user") :-
    connect(":memory:", "doc_e3"),
    exec("doc_e3", "CREATE TABLE users (name TEXT, age INTEGER)"),
    add_user("carol", 41),
    query("doc_e3", "SELECT age FROM users WHERE name = ?", ["carol"], AGE),
    AGE == 41.
```

### `row_count/3`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:row_count_sig"
```

Execute DML and unify `Count` with the number of affected rows.

```clausal
:- use_module(library(sqlite), [connect/2, exec/2, row_count/3]).

cleanup(N) :-
    row_count("doc_rc", "DELETE FROM sessions WHERE expired = 1", N),
    format("Removed ~w expired sessions~n", [N]).

test("cleanup") :-
    connect(":memory:", "doc_rc"),
    exec("doc_rc", "CREATE TABLE sessions (id INTEGER, expired INTEGER)"),
    exec("doc_rc", "INSERT INTO sessions VALUES (1, 1), (2, 0), (3, 1)"),
    cleanup(N),
    N == 2.
```

---

## Schema introspection

### `table/2`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:table_sig"
```

when `TableName` is unbound, **nondeterministically enumerates** all table names. when ground, succeeds if that table exists.

```clausal
:- use_module(library(sqlite), [connect/2, exec/2, table/2]).

has_users_table :-
    table("doc_tbl", "users").

list_tables(T) :-
    table("doc_tbl", T).

test("tables") :-
    connect(":memory:", "doc_tbl"),
    exec("doc_tbl", "CREATE TABLE users (name TEXT)"),
    has_users_table,
    findall(T, list_tables(T), TABLES),
    TABLES == ["users"].
```

### `column/4`

```text
--8<-- "tests/fixtures/docs/sqlite_sigs.txt:column_sig"
```

Enumerate columns of a table, one `ColName`/`ColType` solution per column. Both are strings; column types are SQLite type names: `"TEXT"`, `"INTEGER"`, `"REAL"`, `"BLOB"`, etc.

```clausal
:- use_module(library(sqlite), [connect/2, exec/2, column/4]).

show_schema(COL, TYPE) :-
    column("doc_col", "users", COL, TYPE),
    format("  ~s: ~s~n", [COL, TYPE]).

test("schema") :-
    connect(":memory:", "doc_col"),
    exec("doc_col", "CREATE TABLE users (name TEXT, age INTEGER)"),
    findall(COL-TYPE, show_schema(COL, TYPE), COLS),
    COLS == ["name"-"TEXT", "age"-"INTEGER"].
```

---

??? example "Examples"

    The CRUD and join examples take multi-column rows apart with a tuple
    pattern, which is seam-only (see [`query/3`](#query3)), so they are the
    seam spelling.

    ### CRUD operations

    ```seam
    --8<-- "tests/fixtures/docs/sqlite_sigs.txt:crud_example"
    ```

    ### Joining tables

    ```seam
    --8<-- "tests/fixtures/docs/sqlite_sigs.txt:join_example"
    ```

    ### Schema exploration

    ```text
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

    1. **Named connection aliases** — connections are identified by string aliases, not opaque handles. This makes them easy to reference across predicates in source files where values must be ground or logic variables.
    2. **Idempotent connect** — `connect` with an existing alias succeeds silently. This simplifies predicates that call a shared `setup` predicate from multiple entry points.
    3. **Auto-commit on exec** — `exec` commits after each statement. For multi-statement atomicity, use Python's transaction support via the seam's [`++()`](python_integration.md) interop (not available in `.clausal`).
    4. **Single-column unwrap** — `query` unwraps single-column rows to bare values (not 1-tuples), making common patterns like `SELECT name FROM ...` cleaner.
    5. **Nondeterministic iteration** — `query`, `table`, `column`, and `current_connection` yield one solution per row/item on backtracking, following the standard Prolog database query pattern.
    6. **No C FFI** — unlike prosqlite (SWI-Prolog) which wraps libsqlite3 via C, this module delegates entirely to Python's `sqlite3` stdlib. Zero external dependencies.

---

*See also: [Database Ops](database_ops.md) — Clausal Prolog's assert/retract for in-memory facts · [Python Interop](python_integration.md) — direct SQL via the seam's `++()` escape.*
