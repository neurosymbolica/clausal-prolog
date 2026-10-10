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

from clausal.logic.to_python import to_python
from clausal.modules.py import ModulePredicate, simple_to_trampoline, to_text, text_result
from clausal.modules.py import symbol as _symbol
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE



def _text(val, what: str) -> str:
    """The ``str`` *val* denotes -- a string or an ATOM (spec §9.4).

    THE FLIP (2026-09-06-atoms-as-cells-strings): these arguments used to be
    coerced with ``str()``, which post-flip renders the atom ``(':memory:',)``
    as its Python tuple REPR -- during the flip that literally created a file
    named ``(':memory:',)``.  ``to_text`` unwraps the atom and answers
    ``None`` for anything that is not text (a compound, a number, an unbound
    Var); here that is a loud ``type_error``, since every one of these
    positions is a database path, alias, table name or SQL string.
    """
    text = to_text(val)
    if text is None:
        from clausal.logic.exceptions import LogicException, type_error
        raise LogicException(type_error("text", val, f"sqlite {what}"))
    return text


# ── Connection registry ────────────────────────────────────────────────────

_CONNECTIONS: dict[str, _sqlite3.Connection] = {}
_LOCK = _threading.Lock()


def _get_connection(alias: str) -> _sqlite3.Connection:
    """Look up a connection by alias; raise if not found."""
    alias = _text(alias, "alias")
    conn = _CONNECTIONS.get(alias)
    if conn is None:
        raise ValueError(f"No SQLite connection with alias {alias!r}")
    return conn


# ── Layer 1: Connection management ───────────────────────────────────────

def _sqlite_connect_2(path, alias, trail, k):
    """connect/2: open a database and register under alias."""
    path = deref(path)
    alias = deref(alias)
    path_str = _text(path, "path")
    alias_str = _text(alias, "alias")
    # NEVER yield while holding ``_LOCK``: a generator suspended at a yield
    # inside the ``with`` is abandoned (not closed) whenever the caller drops
    # its choice point — the test harness's diagnostic re-run is one such
    # caller — and the lock is then held for the life of the process, so the
    # NEXT ``connect/2`` blocks forever.  The idempotent "already connected"
    # branch used to yield inside; it now records the decision and yields
    # after the lock is released, like the fresh-connection path always did.
    with _LOCK:
        if alias_str not in _CONNECTIONS:
            try:
                _CONNECTIONS[alias_str] = _sqlite3.connect(path_str)
            except _sqlite3.OperationalError as exc:
                _raise_open_error(exc, path, path_str, "connect/2")
    yield None


def _raise_open_error(exc, path_term, path_str, pred):
    """sqlite3 reports every failure to open a database file as the one
    ``OperationalError("unable to open database file")``; RULED 2026-10-02,
    a file-system failure raises the ISO term, so the cause is read off the
    file system: a missing directory -> ``existence_error(source_sink, P)``,
    a directory or a place that may not be opened ->
    ``permission_error(open, source_sink, P)``.  Anything else is sqlite's
    own error and propagates as itself."""
    import errno as _errno  # noqa: PLC0415
    import os as _os  # noqa: PLC0415
    from clausal.modules.py import raise_os_error  # noqa: PLC0415
    parent = _os.path.dirname(_os.path.abspath(path_str))
    if not _os.path.isdir(parent):
        cause = FileNotFoundError(_errno.ENOENT, "no such directory", path_str)
    elif _os.path.isdir(path_str):
        cause = IsADirectoryError(_errno.EISDIR, "is a directory", path_str)
    elif (not _os.access(parent, _os.W_OK | _os.X_OK)
          or (_os.path.exists(path_str)
              and not _os.access(path_str, _os.R_OK))):
        cause = PermissionError(_errno.EACCES, "permission denied", path_str)
    else:
        raise exc
    raise_os_error(cause, path_term, pred, arg=1, path=path_str)


def _sqlite_disconnect_1(alias, trail, k):
    """disconnect/1: close and unregister a connection."""
    alias = deref(alias)
    alias_str = _text(alias, "alias")
    with _LOCK:
        conn = _CONNECTIONS.pop(alias_str, None)
    if conn is None:
        return  # fail — no such connection
    conn.close()
    yield None


def _sqlite_current_connection_1(this_generator, _proceed, _fail, _catcher, alias, trail):
    """current_connection/1: enumerate open connection aliases.

    An unbound Alias enumerates every open alias as an ATOM (a symbolic name:
    atom out, text in). A bound Alias may be an atom or text; it checks that
    the alias is open.
    """
    alias = deref(alias)
    if not is_var(alias):
        # Check if this specific alias exists
        if _text(alias, "alias") in _CONNECTIONS:
            yield (_proceed, None)
        yield (_fail, DONE)
        return
    # Nondeterministic: iterate all aliases
    with _LOCK:
        aliases = list(_CONNECTIONS.keys())
    for a in aliases:
        mark = trail.mark()
        # An alias is a symbolic NAME (like an ISO stream alias): an ATOM,
        # "atom out, text in" (ruled 2026-10-04).
        if unify(alias, text_result(_symbol(a)), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Layer 2: Raw SQL queries ─────────────────────────────────────────────

def _row_term(row: tuple) -> Any:
    """A result row as a term: a single-column row unwraps to its value, a
    multi-column row is the tuple of its values.  A TEXT value is a STRING
    (the chars carrier) either way (ruling R15, 2026-09-29): database text is
    data, not symbols.  Before, a multi-column row kept its raw ``str``
    columns, which are ATOMS -- ``SELECT name, age`` gave ``('alice', 30)``,
    which is also the compound ``alice(30)``."""
    if len(row) == 1:
        return text_result(row[0])
    return tuple(text_result(v) for v in row)


def _sqlite_query_3(this_generator, _proceed, _fail, _catcher, alias, sql, row_var, trail):
    """query/3: execute SQL, backtrack over result rows as tuples."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    cur = conn.execute(_text(sql, "sql"))
    for row in cur:
        mark = trail.mark()
        if unify(row_var, _row_term(row), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _param_seq(params):
    """The ``?`` values: each element of a list, none for ``[]``, and any
    other value (a number, a text) as the one parameter.  A text is a tuple
    carrier, so testing ``(list, tuple)`` here split it into ``'$chars'`` and
    the text: two parameters for one."""
    if isinstance(params, list):
        return tuple(to_python(p) for p in params)
    if type(params) is tuple and not params:
        return ()                       # () is the nil, []
    return (to_python(params),)


def _sqlite_query_4(this_generator, _proceed, _fail, _catcher, alias, sql, params, row_var, trail):
    """query/4: parameterized query with ? placeholders."""
    alias = deref(alias)
    sql = deref(sql)
    param_seq = _param_seq(deref(params))
    conn = _get_connection(alias)
    cur = conn.execute(_text(sql, "sql"), param_seq)
    for row in cur:
        mark = trail.mark()
        if unify(row_var, _row_term(row), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _sqlite_exec_2(alias, sql, trail, k):
    """exec/2: execute DDL/DML statement, succeed once."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    conn.execute(_text(sql, "sql"))
    conn.commit()
    yield None


def _sqlite_exec_3(alias, sql, params, trail, k):
    """exec/3: parameterized DDL/DML with ? placeholders."""
    alias = deref(alias)
    sql = deref(sql)
    param_seq = _param_seq(deref(params))
    conn = _get_connection(alias)
    conn.execute(_text(sql, "sql"), param_seq)
    conn.commit()
    yield None


def _sqlite_row_count_3(alias, sql, count_var, trail, k):
    """row_count/3: execute DML and unify affected row count."""
    alias = deref(alias)
    sql = deref(sql)
    conn = _get_connection(alias)
    cur = conn.execute(_text(sql, "sql"))
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
        table_name = _text(table_var_d, "table")
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
        if unify(table_var, text_result(name), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _sqlite_column_4(this_generator, _proceed, _fail, _catcher, alias, table, col_name, col_type, trail):
    """column/4: enumerate columns of a table with their types."""
    alias = deref(alias)
    table = deref(table)
    conn = _get_connection(alias)
    cur = conn.execute(f"PRAGMA table_info({_text(table, 'table')})")
    for row in cur:
        # row: (cid, name, type, notnull, dflt_value, pk)
        name = row[1]
        typ = row[2]
        mark = trail.mark()
        if unify(col_name, text_result(name), trail) and unify(col_type, text_result(typ), trail):
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
