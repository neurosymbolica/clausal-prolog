"""Tests for clausal.modules.py.csv — CSV predicates."""

from __future__ import annotations

import os

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.csv import (
    Parse, ParseRow, ParseRecords, Generate, GenerateRecords,
    ReadFile, ReadRecords, WriteFile,
    _parse_row_2, _parse_2, _parse_records_3,
    _generate_2, _generate_records_3,
    _read_file_2, _read_records_2, _write_file_2,
)
from clausal.terms import DictTerm
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── ParseRow/2 ──────────────────────────────────────────────────────────


class TestParseRow:
    def test_simple(self):
        # nv
        row = Var()
        sols, trail = simple_solutions(_parse_row_2, "a,b,c", row)
        assert len(sols) == 1
        assert deref(row) == ["a", "b", "c"]

    def test_quoted_fields(self):
        # nv
        row = Var()
        sols, trail = simple_solutions(_parse_row_2, '"hello, world",b', row)
        assert len(sols) == 1
        assert deref(row) == ["hello, world", "b"]

    def test_empty_string(self):
        # nv
        row = Var()
        sols, trail = simple_solutions(_parse_row_2, "", row)
        assert len(sols) == 1
        assert deref(row) == []

    def test_single_field(self):
        # nv
        row = Var()
        sols, _ = simple_solutions(_parse_row_2, "hello", row)
        assert len(sols) == 1
        assert deref(row) == ["hello"]

    def test_unbound_string_fails(self):
        # nv
        sols, _ = simple_solutions(_parse_row_2, Var(), Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        row = Var()
        sols, trail = trampoline_solutions(ParseRow, "x,y", row)
        assert len(sols) == 1
        assert deref(row) == ["x", "y"]


# ── Parse/2 ─────────────────────────────────────────────────────────────


class TestParse:
    def test_multi_line(self):
        # nv
        rows = Var()
        csv_text = "a,b,c\n1,2,3\n4,5,6"
        sols, trail = simple_solutions(_parse_2, csv_text, rows)
        assert len(sols) == 1
        result = deref(rows)
        assert len(result) == 3
        assert result[0] == ["a", "b", "c"]
        assert result[1] == ["1", "2", "3"]
        assert result[2] == ["4", "5", "6"]

    def test_empty_input(self):
        # nv
        rows = Var()
        sols, trail = simple_solutions(_parse_2, "", rows)
        assert len(sols) == 1
        assert deref(rows) == []

    def test_mixed_quoted(self):
        # nv
        rows = Var()
        csv_text = 'a,"b,c"\n"d,e",f'
        sols, trail = simple_solutions(_parse_2, csv_text, rows)
        assert len(sols) == 1
        result = deref(rows)
        assert result[0] == ["a", "b,c"]
        assert result[1] == ["d,e", "f"]

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_parse_2, Var(), Var())
        assert len(sols) == 0


# ── ParseRecords/3 ─────────────────────────────────────────────────────


class TestParseRecords:
    def test_basic(self):
        # nv
        headers, records = Var(), Var()
        csv_text = "name,age\nalice,30\nbob,25"
        sols, trail = simple_solutions(_parse_records_3, csv_text, headers, records)
        assert len(sols) == 1
        assert deref(headers) == ["name", "age"]
        recs = deref(records)
        assert len(recs) == 2
        assert isinstance(recs[0], DictTerm)
        assert recs[0].data["name"] == "alice"
        assert recs[0].data["age"] == "30"
        assert recs[1].data["name"] == "bob"

    def test_headers_only(self):
        # nv
        headers, records = Var(), Var()
        csv_text = "name,age"
        sols, trail = simple_solutions(_parse_records_3, csv_text, headers, records)
        assert len(sols) == 1
        assert deref(headers) == ["name", "age"]
        assert deref(records) == []

    def test_empty_fails(self):
        """Empty string has no headers."""
        # nv
        sols, _ = simple_solutions(_parse_records_3, "", Var(), Var())
        assert len(sols) == 0

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_parse_records_3, Var(), Var(), Var())
        assert len(sols) == 0


# ── Generate/2 ─────────────────────────────────────────────────────────


class TestGenerate:
    def test_basic(self):
        # nv
        s = Var()
        rows = [["a", "b"], ["1", "2"]]
        sols, trail = simple_solutions(_generate_2, rows, s)
        assert len(sols) == 1
        result = deref(s)
        assert "a,b" in result
        assert "1,2" in result

    def test_quoting(self):
        # nv
        s = Var()
        rows = [["hello, world", "b"]]
        sols, trail = simple_solutions(_generate_2, rows, s)
        assert len(sols) == 1
        result = deref(s)
        assert '"hello, world"' in result

    def test_round_trip(self):
        """Parse then generate yields same rows."""
        # nv
        original = "a,b\r\n1,2\r\n"
        rows = Var()
        simple_solutions(_parse_2, original, rows)
        s = Var()
        simple_solutions(_generate_2, deref(rows), s)
        assert deref(s) == original

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_generate_2, Var(), Var())
        assert len(sols) == 0

    def test_non_list_row_fails(self):
        # nv
        sols, _ = simple_solutions(_generate_2, ["not_a_list"], Var())
        assert len(sols) == 0


# ── GenerateRecords/3 ──────────────────────────────────────────────────


class TestGenerateRecords:
    def test_basic(self):
        # nv
        s = Var()
        headers = ["name", "age"]
        records = [DictTerm({"name": "alice", "age": "30"})]
        sols, trail = simple_solutions(_generate_records_3, headers, records, s)
        assert len(sols) == 1
        result = deref(s)
        assert "name,age" in result
        assert "alice,30" in result

    def test_unbound_headers_fails(self):
        # nv
        sols, _ = simple_solutions(_generate_records_3, Var(), [], Var())
        assert len(sols) == 0

    def test_non_dict_term_record_fails(self):
        # nv
        sols, _ = simple_solutions(
            _generate_records_3, ["a"], ["not_a_dict_term"], Var()
        )
        assert len(sols) == 0


# ── ReadFile/2 & WriteFile/2 ───────────────────────────────────────────


class TestFileIO:
    def test_round_trip(self, tmp_path):
        # nv
        path = str(tmp_path / "test.csv")
        rows = [["name", "age"], ["alice", "30"], ["bob", "25"]]
        sols, _ = simple_solutions(_write_file_2, path, rows)
        assert len(sols) == 1

        result = Var()
        sols, trail = simple_solutions(_read_file_2, path, result)
        assert len(sols) == 1
        data = deref(result)
        assert len(data) == 3
        assert data[0] == ["name", "age"]
        assert data[1] == ["alice", "30"]

    def test_read_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_read_file_2, "/nonexistent/file.csv", Var())
        assert len(sols) == 0

    def test_read_unbound_path_fails(self):
        # nv
        sols, _ = simple_solutions(_read_file_2, Var(), Var())
        assert len(sols) == 0

    def test_write_unbound_rows_fails(self):
        # nv
        sols, _ = simple_solutions(_write_file_2, "/tmp/test.csv", Var())
        assert len(sols) == 0


# ── ReadRecords/2 ──────────────────────────────────────────────────────


class TestReadRecords:
    def test_basic(self, tmp_path):
        # nv
        path = str(tmp_path / "records.csv")
        with open(path, "w") as f:
            f.write("name,age\nalice,30\nbob,25\n")

        records = Var()
        sols, trail = simple_solutions(_read_records_2, path, records)
        assert len(sols) == 1
        recs = deref(records)
        assert len(recs) == 2
        assert isinstance(recs[0], DictTerm)
        assert recs[0].data["name"] == "alice"
        assert recs[1].data["age"] == "25"

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_read_records_2, "/nonexistent/file.csv", Var())
        assert len(sols) == 0
