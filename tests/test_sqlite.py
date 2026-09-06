"""Tests for the SQLite module — clausal.modules.sqlite.

Covers three layers:
1. Connection management (connect, disconnect, current_connection)
2. Raw SQL queries (query, exec, row_count)
3. Schema introspection (table, column)
"""

from __future__ import annotations

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.logic.solve import call, query
from clausal.logic.variables import Var, deref, Trail
from clausal.import_hook import _load_module
from clausal.modules.py.sqlite import (
    _CONNECTIONS,
    _LOCK,
    _sqlite_connect_2,
    _sqlite_disconnect_1,
    _sqlite_exec_2,
    _sqlite_exec_3,
    _sqlite_query_3,
    _sqlite_query_4,
    _sqlite_row_count_3,
    _sqlite_table_2,
    _sqlite_column_4,
    _sqlite_current_connection_1,
    connect,
    disconnect,
    query,
    exec,
    row_count,
    table,
    column,
    current_connection,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

_SQLITE_IMPORT = (
    "-import_from(sqlite, [connect, disconnect, query, "
    "exec, row_count, table, column])\n"
)


def _load(name, src_text, tmp_path):
    """write a .clausal file and load it."""
    p = tmp_path / f"{name}.clausal"
    p.write_text(_SQLITE_IMPORT + src_text)
    mod = _load_module(name, str(p))
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


def _first(functor, *args, module, out_index=-1):
    """Call with a Var at out_index, return first deref'd result."""
    v = Var()
    full = list(args)
    if out_index == -1:
        full.append(v)
    else:
        full.insert(out_index, v)
    for _ in call(functor, *full, module=module):
        return deref(v)
    return None


def _all(functor, *args, module, out_index=-1):
    """Call with a Var at out_index, return all deref'd results."""
    v = Var()
    full = list(args)
    if out_index == -1:
        full.append(v)
    else:
        full.insert(out_index, v)
    results = []
    for _ in call(functor, *full, module=module):
        results.append(deref(v))
    return results


# ── Simple-mode test helpers ─────────────────────────────────────────────────

def _run_simple(fn, *args):
    """Run a simple-mode predicate, return list of yielded values."""
    trail = Trail()
    return list(fn(*args, trail, None))


def _run_trampoline(fn, *args):
    """Run a trampoline-mode predicate, collect solution values."""
    trail = Trail()
    parent = object()
    results = []
    for gen, val in fn(None, parent, parent, parent, *args, trail):
        if gen is parent and val is None:
            results.append(None)
        elif gen is parent:
            break  # DONE
    return results


@pytest.fixture(autouse=True)
def _cleanup_connections():
    """Ensure all connections are closed after each test."""
    yield
    with _LOCK:
        for conn in _CONNECTIONS.values():
            try:
                conn.close()
            except Exception:
                pass
        _CONNECTIONS.clear()


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: Connection Management
# ══════════════════════════════════════════════════════════════════════════════


class TestSQLiteConnect:
    """connect/2: open database and register alias."""

    def test_connect_memory(self):
        # nv
        results = _run_simple(_sqlite_connect_2, ":memory:", "testdb")
        assert len(results) == 1
        assert "testdb" in _CONNECTIONS

    def test_connect_file(self, tmp_path):
        # nv
        db_path = str(tmp_path / "test.db")
        results = _run_simple(_sqlite_connect_2, db_path, "filedb")
        assert len(results) == 1
        assert "filedb" in _CONNECTIONS

    def test_connect_duplicate_alias_idempotent(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "dup")
        results = _run_simple(_sqlite_connect_2, ":memory:", "dup")
        assert len(results) == 1  # succeeds idempotently

    def test_connect_multiple_aliases(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "db1")
        _run_simple(_sqlite_connect_2, ":memory:", "db2")
        assert "db1" in _CONNECTIONS
        assert "db2" in _CONNECTIONS


class TestSQLiteDisconnect:
    """disconnect/1: close and unregister."""

    def test_disconnect(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "dc1")
        results = _run_simple(_sqlite_disconnect_1, "dc1")
        assert len(results) == 1
        assert "dc1" not in _CONNECTIONS

    def test_disconnect_nonexistent_fails(self):
        # nv
        results = _run_simple(_sqlite_disconnect_1, "nope")
        assert len(results) == 0  # fails — no solution


class TestSQLiteCurrentConnection:
    """current_connection/1: enumerate open aliases."""

    def test_enumerate_all(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "cc1")
        _run_simple(_sqlite_connect_2, ":memory:", "cc2")
        trail = Trail()
        parent = object()
        v = Var()
        results = []
        for gen, val in _sqlite_current_connection_1(None, parent, parent, parent, v, trail):
            if gen is parent and val is None:
                results.append(deref(v))
            elif gen is parent:
                break
        assert set(results) >= {"cc1", "cc2"}

    def test_check_specific(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "cc3")
        trail = Trail()
        parent = object()
        solutions = []
        for gen, val in _sqlite_current_connection_1(None, parent, parent, parent, "cc3", trail):
            if gen is parent and val is None:
                solutions.append(True)
            elif gen is parent:
                break
        assert len(solutions) == 1

    def test_check_missing(self):
        # nv
        trail = Trail()
        parent = object()
        solutions = []
        for gen, val in _sqlite_current_connection_1(None, parent, parent, parent, "nope", trail):
            if gen is parent and val is None:
                solutions.append(True)
            elif gen is parent:
                break
        assert len(solutions) == 0


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: Raw SQL Queries
# ══════════════════════════════════════════════════════════════════════════════

def _setup_people_db(alias="qdb"):
    """Create an in-memory DB with a people table for testing."""
    _run_simple(_sqlite_connect_2, ":memory:", alias)
    conn = _CONNECTIONS[alias]
    conn.execute("CREATE TABLE people (name TEXT, age INTEGER)")
    conn.execute("INSERT INTO people VALUES ('alice', 30)")
    conn.execute("INSERT INTO people VALUES ('bob', 25)")
    conn.execute("INSERT INTO people VALUES ('carol', 35)")
    conn.commit()


class TestSQLiteQuery:
    """query/3,4: nondeterministic row iteration."""

    def test_query_all_rows(self):
        # nv
        _setup_people_db("q1")
        trail = Trail()
        parent = object()
        v = Var()
        rows = []
        for gen, val in _sqlite_query_3(None, parent, parent, parent, "q1", "SELECT * FROM people", v, trail):
            if gen is parent and val is None:
                rows.append(deref(v))
            elif gen is parent:
                break
        assert rows == [("alice", 30), ("bob", 25), ("carol", 35)]

    def test_query_single_column(self):
        # nv
        _setup_people_db("q2")
        trail = Trail()
        parent = object()
        v = Var()
        rows = []
        for gen, val in _sqlite_query_3(None, parent, parent, parent, "q2", "SELECT name FROM people", v, trail):
            if gen is parent and val is None:
                rows.append(deref(v))
            elif gen is parent:
                break
        # Single-column rows unwrap
        assert rows == ["alice", "bob", "carol"]

    def test_query_no_results(self):
        # nv
        _setup_people_db("q3")
        trail = Trail()
        parent = object()
        v = Var()
        rows = []
        for gen, val in _sqlite_query_3(None, parent, parent, parent, "q3", "SELECT * FROM people WHERE age > 100", v, trail):
            if gen is parent and val is None:
                rows.append(deref(v))
            elif gen is parent:
                break
        assert rows == []

    def test_query_parameterized(self):
        # nv
        _setup_people_db("q4")
        trail = Trail()
        parent = object()
        v = Var()
        rows = []
        for gen, val in _sqlite_query_4(None, parent, parent, parent, "q4",
            "SELECT name FROM people WHERE age > ?", [26], v, trail
        ):
            if gen is parent and val is None:
                rows.append(deref(v))
            elif gen is parent:
                break
        assert rows == ["alice", "carol"]

    def test_query_multiple_params(self):
        # nv
        _setup_people_db("q5")
        trail = Trail()
        parent = object()
        v = Var()
        rows = []
        for gen, val in _sqlite_query_4(None, parent, parent, parent, "q5",
            "SELECT name FROM people WHERE age >= ? AND age <= ?", [25, 30], v, trail
        ):
            if gen is parent and val is None:
                rows.append(deref(v))
            elif gen is parent:
                break
        assert set(rows) == {"alice", "bob"}

    def test_query_types_preserved(self):
        """INT, TEXT, REAL, NULL types come through correctly."""
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "q6")
        conn = _CONNECTIONS["q6"]
        conn.execute("CREATE TABLE types (i INTEGER, t TEXT, r REAL, n TEXT)")
        conn.execute("INSERT INTO types VALUES (42, 'hello', 3.14, NULL)")
        conn.commit()
        trail = Trail()
        parent = object()
        v = Var()
        rows = []
        for gen, val in _sqlite_query_3(None, parent, parent, parent, "q6", "SELECT * FROM types", v, trail):
            if gen is parent and val is None:
                rows.append(deref(v))
            elif gen is parent:
                break
        assert rows == [(42, "hello", 3.14, None)]

    def test_query_join(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "q7")
        conn = _CONNECTIONS["q7"]
        conn.execute("CREATE TABLE dept (id INTEGER, name TEXT)")
        conn.execute("CREATE TABLE emp (name TEXT, dept_id INTEGER)")
        conn.execute("INSERT INTO dept VALUES (1, 'engineering')")
        conn.execute("INSERT INTO dept VALUES (2, 'marketing')")
        conn.execute("INSERT INTO emp VALUES ('alice', 1)")
        conn.execute("INSERT INTO emp VALUES ('bob', 2)")
        conn.commit()
        trail = Trail()
        parent = object()
        v = Var()
        rows = []
        sql = "SELECT emp.name, dept.name FROM emp JOIN dept ON emp.dept_id = dept.id"
        for gen, val in _sqlite_query_3(None, parent, parent, parent, "q7", sql, v, trail):
            if gen is parent and val is None:
                rows.append(deref(v))
            elif gen is parent:
                break
        assert rows == [("alice", "engineering"), ("bob", "marketing")]

    def test_query_aggregate(self):
        # nv
        _setup_people_db("q8")
        trail = Trail()
        parent = object()
        v = Var()
        rows = []
        for gen, val in _sqlite_query_3(None, parent, parent, parent, "q8", "SELECT COUNT(*) FROM people", v, trail):
            if gen is parent and val is None:
                rows.append(deref(v))
            elif gen is parent:
                break
        assert rows == [3]

    def test_query_bad_alias_raises(self):
        # nv
        trail = Trail()
        parent = object()
        v = Var()
        with pytest.raises(ValueError, match="No SQLite connection"):
            list(_sqlite_query_3(None, parent, parent, parent, "nonexistent", "SELECT 1", v, trail))


class TestSQLiteExec:
    """exec/2,3: DDL/DML execution."""

    def test_exec_create_table(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "e1")
        results = _run_simple(_sqlite_exec_2, "e1", "CREATE TABLE t (x INTEGER)")
        assert len(results) == 1

    def test_exec_insert(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "e2")
        conn = _CONNECTIONS["e2"]
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
        results = _run_simple(_sqlite_exec_2, "e2", "INSERT INTO t VALUES (42)")
        assert len(results) == 1
        # Verify the row was inserted
        rows = list(conn.execute("SELECT x FROM t"))
        assert rows == [(42,)]

    def test_exec_parameterized_insert(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "e3")
        conn = _CONNECTIONS["e3"]
        conn.execute("CREATE TABLE t (name TEXT, val INTEGER)")
        conn.commit()
        results = _run_simple(_sqlite_exec_3, "e3",
                              "INSERT INTO t VALUES (?, ?)", ["hello", 99])
        assert len(results) == 1
        rows = list(conn.execute("SELECT * FROM t"))
        assert rows == [("hello", 99)]

    def test_exec_update(self):
        # nv
        _setup_people_db("e4")
        _run_simple(_sqlite_exec_3, "e4",
                    "UPDATE people SET age = ? WHERE name = ?", [31, "alice"])
        conn = _CONNECTIONS["e4"]
        rows = list(conn.execute("SELECT age FROM people WHERE name = 'alice'"))
        assert rows == [(31,)]

    def test_exec_delete(self):
        # nv
        _setup_people_db("e5")
        _run_simple(_sqlite_exec_3, "e5",
                    "DELETE FROM people WHERE name = ?", ["bob"])
        conn = _CONNECTIONS["e5"]
        rows = list(conn.execute("SELECT name FROM people"))
        names = [r[0] for r in rows]
        assert "bob" not in names


class TestSQLiteRowCount:
    """row_count/3: row count unification."""

    def test_row_count_insert(self):
        # nv
        _run_simple(_sqlite_connect_2, ":memory:", "rc1")
        conn = _CONNECTIONS["rc1"]
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
        trail = Trail()
        v = Var()
        results = list(_sqlite_row_count_3(
            "rc1", "INSERT INTO t VALUES (1)", v, trail, None
        ))
        assert len(results) == 1
        assert deref(v) == 1

    def test_row_count_update(self):
        # nv
        _setup_people_db("rc2")
        trail = Trail()
        v = Var()
        results = list(_sqlite_row_count_3(
            "rc2", "UPDATE people SET age = age + 1", v, trail, None
        ))
        assert len(results) == 1
        assert deref(v) == 3  # 3 rows updated

    def test_row_count_delete(self):
        # nv
        _setup_people_db("rc3")
        trail = Trail()
        v = Var()
        results = list(_sqlite_row_count_3(
            "rc3", "DELETE FROM people WHERE age < 30", v, trail, None
        ))
        assert len(results) == 1
        assert deref(v) == 1  # only bob (age 25)


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3: Schema Introspection
# ══════════════════════════════════════════════════════════════════════════════


class TestSQLiteTable:
    """table/2: enumerate table names."""

    def test_table_enumerate(self):
        # nv
        _setup_people_db("t1")
        conn = _CONNECTIONS["t1"]
        conn.execute("CREATE TABLE cities (name TEXT, pop INTEGER)")
        conn.commit()
        trail = Trail()
        parent = object()
        v = Var()
        tables = []
        for gen, val in _sqlite_table_2(None, parent, parent, parent, "t1", v, trail):
            if gen is parent and val is None:
                tables.append(deref(v))
            elif gen is parent:
                break
        assert set(tables) >= {"people", "cities"}

    def test_table_specific_exists(self):
        # nv
        _setup_people_db("t2")
        trail = Trail()
        parent = object()
        solutions = []
        for gen, val in _sqlite_table_2(None, parent, parent, parent, "t2", "people", trail):
            if gen is parent and val is None:
                solutions.append(True)
            elif gen is parent:
                break
        assert len(solutions) == 1

    def test_table_specific_not_exists(self):
        # nv
        _setup_people_db("t3")
        trail = Trail()
        parent = object()
        solutions = []
        for gen, val in _sqlite_table_2(None, parent, parent, parent, "t3", "nope", trail):
            if gen is parent and val is None:
                solutions.append(True)
            elif gen is parent:
                break
        assert len(solutions) == 0


class TestSQLiteColumn:
    """column/4: enumerate columns with types."""

    def test_column_enumerate(self):
        # nv
        _setup_people_db("c1")
        trail = Trail()
        parent = object()
        name_v = Var()
        type_v = Var()
        cols = []
        for gen, val in _sqlite_column_4(None, parent, parent, parent, "c1", "people", name_v, type_v, trail
        ):
            if gen is parent and val is None:
                cols.append((deref(name_v), deref(type_v)))
            elif gen is parent:
                break
        assert cols == [("name", "TEXT"), ("age", "INTEGER")]

    def test_column_specific_name(self):
        """when col_name is ground, only matching column succeeds."""
        # nv
        _setup_people_db("c2")
        trail = Trail()
        parent = object()
        type_v = Var()
        results = []
        for gen, val in _sqlite_column_4(None, parent, parent, parent, "c2", "people", "name", type_v, trail
        ):
            if gen is parent and val is None:
                results.append(deref(type_v))
            elif gen is parent:
                break
        assert results == ["TEXT"]


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION: .clausal fixture tests
# ══════════════════════════════════════════════════════════════════════════════


class TestSQLiteClausalIntegration:
    """End-to-end tests via .clausal files."""

    def test_connect_exec_query(self, tmp_path):
        # nv
        mod = _load("sq1", """
setup(_db) <- (connect(":memory:", _db) and exec(_db, "CREATE TABLE items (name TEXT, qty INTEGER)") and exec(_db, "INSERT INTO items VALUES ('apple', 3)") and exec(_db, "INSERT INTO items VALUES ('banana', 5)"))

item_name(_n) <- (setup("testdb") and query("testdb", "SELECT name FROM items", _n))
""", tmp_path)
        names = _all("item_name", module=mod)
        assert names == ["apple", "banana"]

    def test_parameterized_query(self, tmp_path):
        # nv
        mod = _load("sq2", """
setup <- (connect(":memory:", "db2") and exec("db2", "CREATE TABLE nums (v INTEGER)") and exec("db2", "INSERT INTO nums VALUES (10)") and exec("db2", "INSERT INTO nums VALUES (20)") and exec("db2", "INSERT INTO nums VALUES (30)"))

big_num(_n) <- (setup() and query("db2", "SELECT v FROM nums WHERE v > ?", [15], _n))
""", tmp_path)
        nums = _all("big_num", module=mod)
        assert nums == [20, 30]

    def test_table_introspection(self, tmp_path):
        # nv
        mod = _load("sq3", """
setup <- (connect(":memory:", "db3") and exec("db3", "CREATE TABLE alpha (x TEXT)") and exec("db3", "CREATE TABLE beta (y INTEGER)"))

table_name(_t) <- (setup() and table("db3", _t))
""", tmp_path)
        tables = _all("table_name", module=mod)
        assert set(tables) >= {"alpha", "beta"}

    def test_column_introspection(self, tmp_path):
        # nv
        mod = _load("sq4", """
setup <- (connect(":memory:", "db4") and exec("db4", "CREATE TABLE things (id INTEGER, label TEXT, weight REAL)"))

col(_name, _type) <- (setup() and column("db4", "things", _name, _type))
""", tmp_path)
        v1 = Var()
        v2 = Var()
        cols = []
        for _ in call("col", v1, v2, module=mod):
            cols.append((deref(v1), deref(v2)))
        assert ("id", "INTEGER") in cols
        assert ("label", "TEXT") in cols
        assert ("weight", "REAL") in cols

    def test_disconnect(self, tmp_path):
        # nv
        mod = _load("sq5", """
open_close <- (connect(":memory:", "db5") and disconnect("db5"))
""", tmp_path)
        assert _succeeds("open_close", module=mod)
        assert "db5" not in _CONNECTIONS  # cleanup ran

    def test_exec_with_params(self, tmp_path):
        # nv
        mod = _load("sq6", """
setup <- (connect(":memory:", "db6") and exec("db6", "CREATE TABLE kv (k TEXT, v INTEGER)") and exec("db6", "INSERT INTO kv VALUES (?, ?)", ["x", 1]) and exec("db6", "INSERT INTO kv VALUES (?, ?)", ["y", 2]))

kv_key(_k) <- (setup() and query("db6", "SELECT k FROM kv", _k))
""", tmp_path)
        keys = _all("kv_key", module=mod)
        assert set(keys) == {"x", "y"}
