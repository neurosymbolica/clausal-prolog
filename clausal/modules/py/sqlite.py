"""clausal.modules.py.sqlite — SQLite predicates for Clausal.

Provides SQLiteConnect, SQLiteDisconnect, SQLiteQuery, SQLiteExec,
SQLiteRowCount, SQLiteTable, SQLiteColumn, and SQLiteCurrentConnection
as importable predicate objects for use in .clausal files via::

    -import_from(py.sqlite, [SQLiteConnect, SQLiteDisconnect, SQLiteQuery,
                          SQLiteExec, SQLiteTable, SQLiteColumn])

Or via module import::

    -import_module(py.sqlite)
    # then use py.sqlite.SQLiteConnect(...), py.sqlite.SQLiteQuery(...), etc.

Layers
------
1. **Connection management** — SQLiteConnect/2,3, SQLiteDisconnect/1,
   SQLiteCurrentConnection/1
2. **Raw SQL** — SQLiteQuery/3,4 (parameterized, nondeterministic),
   SQLiteExec/2,3, SQLiteRowCount/3
3. **Schema introspection** — SQLiteTable/2, SQLiteColumn/4

All SQL execution uses parameterized queries (``?`` placeholders) —
never string interpolation.
"""

from __future__ import annotations

import sqlite3 as _sqlite3
import threading as _threading
from typing import Any, Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Connection registry ────────────────────────────────────────────────────

_CONNECTIONS: dict[str, _sqlite3.Connection] = {}
_LOCK = _threading.Lock()


def _get_connection(alias: str) -> _sqlite3.Connection:
    """Look up a connection by alias; raise if not found."""
    alias = str(alias)
    conn = _CONNECTIONS.get(alias)
    if conn is None:
        raise ValueError(f"No SQLite connection with alias {alias!r}")
    return conn


# ── Dispatch adapter ──────────────────────────────────────────────────────

class _SQLitePredicate:
    """Adapter with ``_get_dispatch()`` for an SQLite predicate.

    Supports multi-arity dispatch (e.g. SQLiteQuery/3 + SQLiteQuery/4).
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"sqlite.{self._name}/{arities}"


# ── Simple-mode wrapper ──────────────────────────────────────────────────

def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Layer 1: Connection management ───────────────────────────────────────

def _sqlite_connect_2(path, alias, trail, k):
    """SQLiteConnect/2: open a database and register under alias."""
    path = deref(path)
    alias = deref(alias)
    path_str = str(path)
    alias_str = str(alias)
    with _LOCK:
        if alias_str in _CONNECTIONS:
            # Already connected under this alias — succeed idempotently
            yield None
            return
        conn = _sqlite3.connect(path_str)
        _CONNECTIONS[alias_str] = conn
    yield None


def _sqlite_disconnect_1(alias, trail, k):
    """SQLiteDisconnect/1: close and unregister a connection."""
    alias = deref(alias)
    alias_str = str(alias)
    with _LOCK:
        conn = _CONNECTIONS.pop(alias_str, None)
    if conn is None:
        return  # fail — no such connection
    conn.close()
    yield None


def _sqlite_current_connection_1(this_generator, parent, alias, trail):
    """SQLiteCurrentConnection/1: enumerate open connection aliases."""
    alias = deref(alias)
    if not is_var(alias):
        # Check if this specific alias exists
        if str(alias) in _CONNECTIONS:
            yield (parent, None)
        yield (parent, DONE)
        return
    # Nondeterministic: iterate all aliases
    with _LOCK:
        aliases = list(_CONNECTIONS.keys())
    for a in aliases:
        mark = trail.mark()
        if unify(alias, a, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


# ── Layer 2: Raw SQL queries ─────────────────────────────────────────────

def _sqlite_query_3(this_generator, parent, alias, sql, row_var, trail):
    """SQLiteQuery/3: execute SQL, backtrack over result rows as tuples."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    cur = conn.execute(str(sql))
    for row in cur:
        mark = trail.mark()
        # Single-column rows unwrap to the value itself
        value = row[0] if len(row) == 1 else row
        if unify(row_var, value, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


def _sqlite_query_4(this_generator, parent, alias, sql, params, row_var, trail):
    """SQLiteQuery/4: parameterized query with ? placeholders."""
    alias = deref(alias)
    sql = deref(sql)
    params = deref(params)
    # Accept list or tuple of params
    if isinstance(params, (list, tuple)):
        param_seq = tuple(deref(p) for p in params)
    else:
        param_seq = (params,)
    conn = _get_connection(alias)
    cur = conn.execute(str(sql), param_seq)
    for row in cur:
        mark = trail.mark()
        value = row[0] if len(row) == 1 else row
        if unify(row_var, value, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


def _sqlite_exec_2(alias, sql, trail, k):
    """SQLiteExec/2: execute DDL/DML statement, succeed once."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    conn.execute(str(sql))
    conn.commit()
    yield None


def _sqlite_exec_3(alias, sql, params, trail, k):
    """SQLiteExec/3: parameterized DDL/DML with ? placeholders."""
    alias = deref(alias)
    sql = deref(sql)
    params = deref(params)
    if isinstance(params, (list, tuple)):
        param_seq = tuple(deref(p) for p in params)
    else:
        param_seq = (params,)
    conn = _get_connection(alias)
    conn.execute(str(sql), param_seq)
    conn.commit()
    yield None


def _sqlite_row_count_3(alias, sql, count_var, trail, k):
    """SQLiteRowCount/3: execute DML and unify affected row count."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    cur = conn.execute(str(sql))
    conn.commit()
    if unify(count_var, cur.rowcount, trail):
        yield None


# ── Layer 3: Schema introspection ────────────────────────────────────────

def _sqlite_table_2(this_generator, parent, alias, table_var, trail):
    """SQLiteTable/2: enumerate table names (nondeterministic)."""
    alias = deref(alias)
    table_var_d = deref(table_var)
    conn = _get_connection(alias)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "ORDER BY name"
    )
    if not is_var(table_var_d):
        # Check if specific table exists
        table_name = str(table_var_d)
        for (name,) in cur:
            if name == table_name:
                yield (parent, None)
                yield (parent, DONE)
                return
        yield (parent, DONE)
        return
    # Nondeterministic: iterate all tables
    for (name,) in cur:
        mark = trail.mark()
        if unify(table_var, name, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


def _sqlite_column_4(this_generator, parent, alias, table, col_name, col_type, trail):
    """SQLiteColumn/4: enumerate columns of a table with their types."""
    alias = deref(alias)
    table = deref(table)
    conn = _get_connection(alias)
    cur = conn.execute(f"PRAGMA table_info({str(table)})")
    for row in cur:
        # row: (cid, name, type, notnull, dflt_value, pk)
        name = row[1]
        typ = row[2]
        mark = trail.mark()
        if unify(col_name, name, trail) and unify(col_type, typ, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


# ── Build and export predicate objects ───────────────────────────────────

SQLiteConnect = _SQLitePredicate("SQLiteConnect")
SQLiteConnect._register(2, _simple_to_trampoline(_sqlite_connect_2))

SQLiteDisconnect = _SQLitePredicate("SQLiteDisconnect")
SQLiteDisconnect._register(1, _simple_to_trampoline(_sqlite_disconnect_1))

SQLiteCurrentConnection = _SQLitePredicate("SQLiteCurrentConnection")
SQLiteCurrentConnection._register(1, _sqlite_current_connection_1)

SQLiteQuery = _SQLitePredicate("SQLiteQuery")
SQLiteQuery._register(3, _sqlite_query_3)
SQLiteQuery._register(4, _sqlite_query_4)

SQLiteExec = _SQLitePredicate("SQLiteExec")
SQLiteExec._register(2, _simple_to_trampoline(_sqlite_exec_2))
SQLiteExec._register(3, _simple_to_trampoline(_sqlite_exec_3))

SQLiteRowCount = _SQLitePredicate("SQLiteRowCount")
SQLiteRowCount._register(3, _simple_to_trampoline(_sqlite_row_count_3))

SQLiteTable = _SQLitePredicate("SQLiteTable")
SQLiteTable._register(2, _sqlite_table_2)

SQLiteColumn = _SQLitePredicate("SQLiteColumn")
SQLiteColumn._register(4, _sqlite_column_4)
