"""Tests for clausal.modules.py.csv — CSV predicates."""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars, chars_text
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.csv import (
    parse, parse_row, parse_records, generate, generate_records,
    read_file, read_records, write_file,
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


def raised(fn, *args):
    """The error term a simple-mode builtin raises.  RULED 2026-10-02: an
    argument of the wrong type raises type_error, an unbound required one
    instantiation_error -- neither fails the goal."""
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


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


# ── parse_row/2 ──────────────────────────────────────────────────────────


class TestParseRow:
    def test_simple(self):
        # nv
        row = Var()
        sols, trail = simple_solutions(_parse_row_2, chars("a,b,c"), row)
        assert len(sols) == 1
        assert deref(row) == [chars("a"), chars("b"), chars("c")]

    def test_quoted_fields(self):
        # nv
        row = Var()
        sols, trail = simple_solutions(_parse_row_2, chars('"hello, world",b'), row)
        assert len(sols) == 1
        assert deref(row) == [chars("hello, world"), chars("b")]

    def test_empty_string(self):
        # nv
        row = Var()
        sols, trail = simple_solutions(_parse_row_2, chars(""), row)
        assert len(sols) == 1
        assert deref(row) == []

    def test_single_field(self):
        # nv
        row = Var()
        sols, _ = simple_solutions(_parse_row_2, chars("hello"), row)
        assert len(sols) == 1
        assert deref(row) == [chars("hello")]

    def test_unbound_string_raises(self):
        # nv
        term = raised(_parse_row_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'parse_row', 2))

    def test_trampoline(self):
        # nv
        row = Var()
        sols, trail = trampoline_solutions(parse_row, chars("x,y"), row)
        assert len(sols) == 1
        assert deref(row) == [chars("x"), chars("y")]


# ── parse/2 ─────────────────────────────────────────────────────────────


class TestParse:
    def test_multi_line(self):
        # nv
        rows = Var()
        csv_text = "a,b,c\n1,2,3\n4,5,6"
        sols, trail = simple_solutions(_parse_2, chars(csv_text), rows)
        assert len(sols) == 1
        result = deref(rows)
        assert len(result) == 3
        assert result[0] == [chars("a"), chars("b"), chars("c")]
        assert result[1] == [chars("1"), chars("2"), chars("3")]
        assert result[2] == [chars("4"), chars("5"), chars("6")]

    def test_empty_input(self):
        # nv
        rows = Var()
        sols, trail = simple_solutions(_parse_2, chars(""), rows)
        assert len(sols) == 1
        assert deref(rows) == []

    def test_mixed_quoted(self):
        # nv
        rows = Var()
        csv_text = 'a,"b,c"\n"d,e",f'
        sols, trail = simple_solutions(_parse_2, chars(csv_text), rows)
        assert len(sols) == 1
        result = deref(rows)
        assert result[0] == [chars("a"), chars("b,c")]
        assert result[1] == [chars("d,e"), chars("f")]

    def test_unbound_raises(self):
        # nv
        term = raised(_parse_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'parse', 2))


# ── parse_records/3 ─────────────────────────────────────────────────────


class TestParseRecords:
    def test_basic(self):
        # nv
        headers, records = Var(), Var()
        csv_text = "name,age\nalice,30\nbob,25"
        sols, trail = simple_solutions(_parse_records_3, chars(csv_text), headers, records)
        assert len(sols) == 1
        # Task 12c: a header cell names a column, so it is an ATOM — both as
        # the record key (§6.8) and in the Headers answer, which names the
        # same columns.  The VALUES stay strings (CSV coerces nothing).
        assert deref(headers) == [mint("name"), mint("age")]
        recs = deref(records)
        assert len(recs) == 2
        assert isinstance(recs[0], DictTerm)
        assert recs[0].data[mint("name")] == chars("alice")
        assert recs[0].data[mint("age")] == chars("30")
        assert recs[1].data[mint("name")] == chars("bob")

    def test_headers_only(self):
        # nv
        headers, records = Var(), Var()
        csv_text = "name,age"
        sols, trail = simple_solutions(_parse_records_3, chars(csv_text), headers, records)
        assert len(sols) == 1
        assert deref(headers) == [mint("name"), mint("age")]
        assert deref(records) == []

    def test_empty_fails(self):
        """Empty string has no headers."""
        # nv
        sols, _ = simple_solutions(_parse_records_3, chars(""), Var(), Var())
        assert len(sols) == 0

    def test_unbound_raises(self):
        # nv
        term = raised(_parse_records_3, Var(), Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'parse_records', 3))


# ── generate/2 ─────────────────────────────────────────────────────────


class TestGenerate:
    def test_basic(self):
        # nv
        s = Var()
        rows = [[chars("a"), chars("b")], [chars("1"), chars("2")]]
        sols, trail = simple_solutions(_generate_2, rows, s)
        assert len(sols) == 1
        result = deref(s)
        assert "a,b" in chars_text(result)
        assert "1,2" in chars_text(result)

    def test_quoting(self):
        # nv
        s = Var()
        rows = [[chars("hello, world"), chars("b")]]
        sols, trail = simple_solutions(_generate_2, rows, s)
        assert len(sols) == 1
        result = deref(s)
        assert '"hello, world"' in chars_text(result)

    def test_round_trip(self):
        """parse then generate yields same rows."""
        # nv
        original = "a,b\r\n1,2\r\n"
        rows = Var()
        simple_solutions(_parse_2, chars(original), rows)
        s = Var()
        simple_solutions(_generate_2, deref(rows), s)
        assert deref(s) == chars(original)

    def test_unbound_raises(self):
        # nv
        term = raised(_generate_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'generate', 2))

    def test_non_list_row_raises(self):
        # nv
        term = raised(_generate_2, ["not_a_list"], Var())
        assert term == ('error', ('type_error', 'list', 'not_a_list'), ('/', 'generate', 2))


# ── generate_records/3 ──────────────────────────────────────────────────


class TestGenerateRecords:
    def test_basic(self):
        # nv
        s = Var()
        headers = [chars("name"), chars("age")]
        records = [DictTerm({chars("name"): chars("alice"), chars("age"): chars("30")})]
        sols, trail = simple_solutions(_generate_records_3, headers, records, s)
        assert len(sols) == 1
        result = deref(s)
        assert "name,age" in chars_text(result)
        assert "alice,30" in chars_text(result)

    def test_unbound_headers_raises(self):
        # nv
        term = raised(_generate_records_3, Var(), [], Var())
        assert term == ('error', 'instantiation_error', ('/', 'generate_records', 3))

    def test_non_dict_term_record_raises(self):
        # nv
        term = raised(
            _generate_records_3, [chars("a")], ["not_a_dict_term"], Var()
        )
        assert term == ('error', ('type_error', 'dict', 'not_a_dict_term'), ('/', 'generate_records', 3))


# ── read_file/2 & write_file/2 ───────────────────────────────────────────


class TestFileIO:
    def test_round_trip(self, tmp_path):
        # nv
        path = str(tmp_path / "test.csv")
        rows = [[chars("name"), chars("age")], [chars("alice"), chars("30")], [chars("bob"), chars("25")]]
        sols, _ = simple_solutions(_write_file_2, chars(path), rows)
        assert len(sols) == 1

        result = Var()
        sols, trail = simple_solutions(_read_file_2, chars(path), result)
        assert len(sols) == 1
        data = deref(result)
        assert len(data) == 3
        assert data[0] == [chars("name"), chars("age")]
        assert data[1] == [chars("alice"), chars("30")]

    def test_read_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_read_file_2, chars("/nonexistent/file.csv"), Var())
        assert len(sols) == 0

    def test_read_unbound_path_raises(self):
        # nv
        term = raised(_read_file_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'read_file', 2))

    def test_write_unbound_rows_raises(self):
        # nv
        term = raised(_write_file_2, chars("/tmp/test.csv"), Var())
        assert term == ('error', 'instantiation_error', ('/', 'write_file', 2))


# ── read_records/2 ──────────────────────────────────────────────────────


class TestReadRecords:
    def test_basic(self, tmp_path):
        # nv
        path = str(tmp_path / "records.csv")
        with open(path, "w") as f:
            f.write("name,age\nalice,30\nbob,25\n")

        records = Var()
        sols, trail = simple_solutions(_read_records_2, chars(path), records)
        assert len(sols) == 1
        recs = deref(records)
        assert len(recs) == 2
        assert isinstance(recs[0], DictTerm)
        assert recs[0].data[mint("name")] == chars("alice")
        assert recs[1].data[mint("age")] == chars("25")

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_read_records_2, chars("/nonexistent/file.csv"), Var())
        assert len(sols) == 0


# ── Task 12c: header cells are ATOMS on the way out (§6.8, §9.2) ────────


class TestRecordKeysAreAtoms:
    """A CSV header cell is DATA, and §9.2's precedent — ``py.json`` mints
    parsed object keys — governs data-derived keys too.  Without it
    ``R.name`` (which looks up ``("name",)``) missed every record and
    ``get(R, name, V)`` failed silently."""

    def test_generate_records_reads_back_what_parse_records_answered(self):
        """The documented round trip has to close: ``generate_records/3`` is
        the inverse of ``parse_records/3``, so it reads atom headers and atom
        record keys — and would otherwise write ``('name',)`` as a column."""
        # nv
        headers, records = Var(), Var()
        sols, _ = simple_solutions(
            _parse_records_3, chars("name,age\nalice,30\n"), headers, records)
        assert len(sols) == 1
        out = Var()
        sols, _ = simple_solutions(
            _generate_records_3, deref(headers), deref(records), out)
        assert len(sols) == 1
        assert deref(out) == chars("name,age\r\nalice,30\r\n")

    def test_a_python_built_str_keyed_record_still_generates(self):
        """The other side stays open: a ``DictTerm`` built in Python has
        ``str`` keys, and both denote the same column name (§9.4)."""
        # nv
        out = Var()
        sols, _ = simple_solutions(
            _generate_records_3, [chars("name")], [DictTerm({chars("name"): chars("alice")})], out)
        assert len(sols) == 1
        assert deref(out) == chars("name\r\nalice\r\n")

    def test_an_overlong_row_keeps_the_dictreader_restkey(self):
        """``csv.DictReader`` files a too-long row's overflow under the key
        ``None``; that is not a header cell and is not minted."""
        # nv
        headers, records = Var(), Var()
        sols, _ = simple_solutions(
            _parse_records_3, chars("name\nalice,30\n"), headers, records)
        assert len(sols) == 1
        data = deref(records)[0].data
        assert data[mint("name")] == chars("alice")
        assert data[None] == [chars("30")]
