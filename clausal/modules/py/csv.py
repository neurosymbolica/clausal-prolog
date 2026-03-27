"""clausal.modules.py.csv — CSV predicates for Clausal.

Provides relational predicates for parsing and generating CSV data.
Import via::

    -import_from(py.csv, [Parse, ParseRow, ParseRecords, Generate, ReadFile])

Or via module import::

    -import_module(py.csv)
    # then use py.csv.Parse(S_, ROWS_), py.csv.ReadFile("data.csv", ROWS_), etc.

Type mapping
------------
- CSV rows  → Python ``list`` of ``str``
- CSV with headers → ``list`` of ``DictTerm`` (one per record)
- All values are strings — no automatic type coercion.

Use ``++int(X)`` or ``number_chars`` for conversion if needed.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_csv = _import_stdlib("csv")

import io

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import DictTerm


# ── Helpers ─────────────────────────────────────────────────────────────


def _deref_row(row):
    """Deref all elements in a row, converting to strings."""
    result = []
    for item in row:
        v = deref(item)
        if is_var(v):
            raise TypeError("Cannot serialize unbound variable to CSV")
        result.append(str(v))
    return result


# ── Predicates ──────────────────────────────────────────────────────────


def _parse_row_2(string, row, trail, k):
    """ParseRow/2: parse a single CSV line into a list of strings."""
    string = deref(string)
    if is_var(string) or not isinstance(string, str):
        return
    reader = _csv.reader(io.StringIO(string))
    try:
        result = next(reader)
    except StopIteration:
        result = []
    if unify(row, result, trail):
        yield None


def _parse_2(string, rows, trail, k):
    """Parse/2: parse a multi-line CSV string into a list of rows."""
    string = deref(string)
    if is_var(string) or not isinstance(string, str):
        return
    reader = _csv.reader(io.StringIO(string))
    result = [row for row in reader]
    if unify(rows, result, trail):
        yield None


def _parse_records_3(string, headers, records, trail, k):
    """ParseRecords/3: parse CSV with headers → list of DictTerms."""
    string = deref(string)
    if is_var(string) or not isinstance(string, str):
        return
    reader = _csv.DictReader(io.StringIO(string))
    header_list = reader.fieldnames
    if header_list is None:
        return
    record_list = [DictTerm(dict(row)) for row in reader]
    mark = trail.mark()
    if unify(headers, list(header_list), trail) and unify(records, record_list, trail):
        yield None
    else:
        trail.undo(mark)


def _generate_2(rows, string, trail, k):
    """Generate/2: serialize a list of rows to CSV string."""
    rows = deref(rows)
    if is_var(rows) or not isinstance(rows, list):
        return
    try:
        buf = io.StringIO()
        writer = _csv.writer(buf)
        for row in rows:
            row = deref(row)
            if not isinstance(row, list):
                return
            writer.writerow(_deref_row(row))
        result = buf.getvalue()
    except (TypeError, ValueError):
        return
    if unify(string, result, trail):
        yield None


def _generate_records_3(headers, records, string, trail, k):
    """GenerateRecords/3: serialize DictTerm records with header row."""
    headers, records = deref(headers), deref(records)
    if is_var(headers) or not isinstance(headers, list):
        return
    if is_var(records) or not isinstance(records, list):
        return
    try:
        header_strs = [str(deref(h)) for h in headers]
        buf = io.StringIO()
        writer = _csv.DictWriter(buf, fieldnames=header_strs)
        writer.writeheader()
        for record in records:
            record = deref(record)
            if not isinstance(record, DictTerm):
                return
            row_dict = {k: str(deref(v)) for k, v in record.data.items()}
            writer.writerow(row_dict)
        result = buf.getvalue()
    except (TypeError, ValueError):
        return
    if unify(string, result, trail):
        yield None


def _read_file_2(path, rows, trail, k):
    """ReadFile/2: read and parse a CSV file into list of rows."""
    path = deref(path)
    if is_var(path) or not isinstance(path, str):
        return
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = _csv.reader(f)
            result = [row for row in reader]
    except OSError:
        return
    if unify(rows, result, trail):
        yield None


def _read_records_2(path, records, trail, k):
    """ReadRecords/2: read CSV file with headers → list of DictTerms."""
    path = deref(path)
    if is_var(path) or not isinstance(path, str):
        return
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = _csv.DictReader(f)
            result = [DictTerm(dict(row)) for row in reader]
    except OSError:
        return
    if unify(records, result, trail):
        yield None


def _write_file_2(path, rows, trail, k):
    """WriteFile/2: serialize rows and write to CSV file."""
    path, rows = deref(path), deref(rows)
    if is_var(path) or not isinstance(path, str):
        return
    if is_var(rows) or not isinstance(rows, list):
        return
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = _csv.writer(f)
            for row in rows:
                row = deref(row)
                if not isinstance(row, list):
                    return
                writer.writerow(_deref_row(row))
    except (TypeError, ValueError, OSError):
        return
    yield None


# ── Build and export predicate objects ──────────────────────────────────

ParseRow = ModulePredicate("ParseRow")
ParseRow._register(2, simple_to_trampoline(_parse_row_2))

Parse = ModulePredicate("Parse")
Parse._register(2, simple_to_trampoline(_parse_2))

ParseRecords = ModulePredicate("ParseRecords")
ParseRecords._register(3, simple_to_trampoline(_parse_records_3))

Generate = ModulePredicate("Generate")
Generate._register(2, simple_to_trampoline(_generate_2))

GenerateRecords = ModulePredicate("GenerateRecords")
GenerateRecords._register(3, simple_to_trampoline(_generate_records_3))

ReadFile = ModulePredicate("ReadFile")
ReadFile._register(2, simple_to_trampoline(_read_file_2))

ReadRecords = ModulePredicate("ReadRecords")
ReadRecords._register(2, simple_to_trampoline(_read_records_2))

WriteFile = ModulePredicate("WriteFile")
WriteFile._register(2, simple_to_trampoline(_write_file_2))
