"""clausal.modules.py.sqlite — SQLite predicates for Clausal.

Provides connect, disconnect, query, exec,
row_count, table, column, and current_connection
as importable predicate objects for use in .clausal files via::

    -import_from(py.sqlite, [connect, disconnect, query,
                          exec, table, column])

Or via module import::

    -import_module(py.sqlite)
    # then use py.sqlite.connect(...), py.sqlite.query(...), etc.

Layers
------
1. **Connection management** — connect/2,3, disconnect/1,
   current_connection/1
2. **Raw SQL** — query/3,4 (parameterized, nondeterministic),
   exec/2,3, row_count/3
3. **Schema introspection** — table/2, column/4

All SQL execution uses parameterized queries (``?`` placeholders) —
never string interpolation.
"""

from __future__ import annotations

import sqlite3 as _sqlite3
import threading as _threading
from typing import Any

from clausal.modules.py import ModulePredicate, simple_to_trampoline
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


# ── Layer 1: Connection management ───────────────────────────────────────

def _sqlite_connect_2(path, alias, trail, k):
    """connect/2: open a database and register under alias."""
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
    """disconnect/1: close and unregister a connection."""
    alias = deref(alias)
    alias_str = str(alias)
    with _LOCK:
        conn = _CONNECTIONS.pop(alias_str, None)
    if conn is None:
        return  # fail — no such connection
    conn.close()
    yield None


def _sqlite_current_connection_1(this_generator, _proceed, _fail, _catcher, alias, trail):
    """current_connection/1: enumerate open connection aliases."""
    alias = deref(alias)
    if not is_var(alias):
        # Check if this specific alias exists
        if str(alias) in _CONNECTIONS:
            yield (_proceed, None)
        yield (_fail, DONE)
        return
    # Nondeterministic: iterate all aliases
    with _LOCK:
        aliases = list(_CONNECTIONS.keys())
    for a in aliases:
        mark = trail.mark()
        if unify(alias, a, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Layer 2: Raw SQL queries ─────────────────────────────────────────────

def _sqlite_query_3(this_generator, _proceed, _fail, _catcher, alias, sql, row_var, trail):
    """query/3: execute SQL, backtrack over result rows as tuples."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    cur = conn.execute(str(sql))
    for row in cur:
        mark = trail.mark()
        # Single-column rows unwrap to the value itself
        value = row[0] if len(row) == 1 else row
        if unify(row_var, value, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _sqlite_query_4(this_generator, _proceed, _fail, _catcher, alias, sql, params, row_var, trail):
    """query/4: parameterized query with ? placeholders."""
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
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _sqlite_exec_2(alias, sql, trail, k):
    """exec/2: execute DDL/DML statement, succeed once."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    conn.execute(str(sql))
    conn.commit()
    yield None


def _sqlite_exec_3(alias, sql, params, trail, k):
    """exec/3: parameterized DDL/DML with ? placeholders."""
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
    """row_count/3: execute DML and unify affected row count."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    cur = conn.execute(str(sql))
    conn.commit()
    if unify(count_var, cur.rowcount, trail):
        yield None


# ── Layer 3: Schema introspection ────────────────────────────────────────

def _sqlite_table_2(this_generator, _proceed, _fail, _catcher, alias, table_var, trail):
    """table/2: enumerate table names (nondeterministic)."""
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
                yield (_proceed, None)
                yield (_fail, DONE)
                return
        yield (_fail, DONE)
        return
    # Nondeterministic: iterate all tables
    for (name,) in cur:
        mark = trail.mark()
        if unify(table_var, name, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _sqlite_column_4(this_generator, _proceed, _fail, _catcher, alias, table, col_name, col_type, trail):
    """column/4: enumerate columns of a table with their types."""
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
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Build and export predicate objects ───────────────────────────────────

connect = ModulePredicate("connect")
connect._register(2, simple_to_trampoline(_sqlite_connect_2))

disconnect = ModulePredicate("disconnect")
disconnect._register(1, simple_to_trampoline(_sqlite_disconnect_1))

current_connection = ModulePredicate("current_connection")
current_connection._register(1, _sqlite_current_connection_1)

query = ModulePredicate("query")
query._register(3, _sqlite_query_3)
query._register(4, _sqlite_query_4)

exec = ModulePredicate("exec")
exec._register(2, simple_to_trampoline(_sqlite_exec_2))
exec._register(3, simple_to_trampoline(_sqlite_exec_3))

row_count = ModulePredicate("row_count")
row_count._register(3, simple_to_trampoline(_sqlite_row_count_3))

table = ModulePredicate("table")
table._register(2, _sqlite_table_2)

column = ModulePredicate("column")
column._register(4, _sqlite_column_4)
