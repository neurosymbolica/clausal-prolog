"""clausal.modules.py.csv — CSV predicates for Clausal.

Provides relational predicates for parsing and generating CSV data.
Import via::

    -import_from(py.csv, [parse, parse_row, parse_records, generate, read_file])

Or via module import::

    -import_module(py.csv)
    # then use py.csv.parse(S_, ROWS_), py.csv.read_file("data.csv", ROWS_), etc.

Type mapping
------------
- CSV rows  → Python ``list`` of ``str``
- CSV with headers → ``list`` of ``DictTerm`` (one per record), keyed by the
  header cell ATOMS (spec §6.8/§9.2), so ``R.name`` reads a record
- All values are strings — no automatic type coercion.

Use ``++int(X)`` or ``number_chars`` for conversion if needed.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    note_mismatch,
    note_rejected_call,
    simple_to_trampoline,
    text_or_str,
    to_text,
)
_csv = _import_stdlib("csv")

import io

from clausal.logic.atoms import mint
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import DictTerm


# ── Helpers ─────────────────────────────────────────────────────────────


def _field_key(name):
    """The record-dict key a CSV header cell denotes: the ATOM of its text.

    A header cell is DATA, and §9.2 already rules the data-derived case for
    the only other place the engine builds a dict out of parsed input:
    ``py.json``'s object keys are minted.  The same reading applies here,
    and it is what makes the answer readable — spec §6.8 keeps an atom key
    distinct from the string of the same spelling, so ``R.name`` (which
    looks up ``("name",)``) found nothing in a ``str``-keyed record and
    ``get(R, name, V)`` failed silently.

    ``csv.DictReader`` uses ``None`` as the key for the overflow fields of a
    too-long row (its ``restkey``); that is not a header cell and is left
    exactly as it is.
    """
    return mint(name) if type(name) is str else name


def _require_text(val, pred, arg):
    """The ``str`` a String or Path argument denotes, or ``None`` (noted).

    Spec §9.4: a wrapper that takes text accepts a string or an ATOM, and both
    convert to the same ``str``.  THE FLIP (2026-09-06-atoms-as-cells-strings)
    made the bare ``expect_type(x, str, ...)`` guards below reject every
    source-written argument, silently -- and a PATH that went through ``str()``
    would have opened a file literally named ``('/tmp/x',)``.

    A bound value that is not text keeps this module's existing behaviour --
    a recorded type-mismatch note and a clean failure, not a raise.
    """
    text = to_text(val)
    if text is not None:
        return text
    expect_type(val, str, pred, arg=arg)   # records the note; always False here
    return None


def _deref_row(row):
    """Deref all elements in a row, converting to strings."""
    result = []
    for item in row:
        v = deref(item)
        if is_var(v):
            raise TypeError("Cannot serialize unbound variable to CSV")
        # Spec §9.4: text is a string or an ATOM; ``str()`` on the arity-0
        # cell would write its Python tuple repr into the file.
        result.append(text_or_str(v))
    return result


# ── Predicates ──────────────────────────────────────────────────────────


def _parse_row_2(string, row, trail, k):
    """parse_row/2: parse a single CSV line into a list of strings."""
    string = _require_text(deref(string), "parse_row/2", 1)
    if string is None:
        return
    reader = _csv.reader(io.StringIO(string))
    try:
        result = next(reader)
    except StopIteration:
        result = []
    if unify(row, result, trail):
        yield None


def _parse_2(string, rows, trail, k):
    """parse/2: parse a multi-line CSV string into a list of rows."""
    string = _require_text(deref(string), "parse/2", 1)
    if string is None:
        return
    reader = _csv.reader(io.StringIO(string))
    result = [row for row in reader]
    if unify(rows, result, trail):
        yield None


def _parse_records_3(string, headers, records, trail, k):
    """parse_records/3: parse CSV with headers → list of DictTerms.

    Each record is keyed by the header cell's ATOM, and Headers answers the
    same atoms: they name the same columns, so ``member(H, Headers),
    get(R, H, V)`` has to reach the wrapper's own records.  The VALUES stay
    strings — CSV does no type coercion.
    """
    string = _require_text(deref(string), "parse_records/3", 1)
    if string is None:
        return
    reader = _csv.DictReader(io.StringIO(string))
    header_list = reader.fieldnames
    if header_list is None:
        return
    record_list = [
        DictTerm({_field_key(k): v for k, v in row.items()}) for row in reader
    ]
    mark = trail.mark()
    if (unify(headers, [_field_key(h) for h in header_list], trail)
            and unify(records, record_list, trail)):
        yield None
    else:
        trail.undo(mark)


def _generate_2(rows, string, trail, k):
    """generate/2: serialize a list of rows to CSV string."""
    rows = deref(rows)
    if not expect_type(rows, list, "generate/2", arg=1):
        return
    try:
        buf = io.StringIO()
        writer = _csv.writer(buf)
        for row in rows:
            row = deref(row)
            if not isinstance(row, list):
                note_mismatch(
                    "generate/2",
                    f"was called with a list containing {type(row).__name__} "
                    "where a list of row lists is required (argument 1)",
                )
                return
            writer.writerow(_deref_row(row))
        result = buf.getvalue()
    except (TypeError, ValueError) as exc:
        note_rejected_call("generate/2", exc)
        return
    if unify(string, result, trail):
        yield None


def _generate_records_3(headers, records, string, trail, k):
    """generate_records/3: serialize DictTerm records with header row.

    The inverse of ``parse_records/3``, so it reads the ATOM headers and
    atom record keys that predicate answers — and a plain-``str`` header or
    key just as well, since both denote the same column name (§9.4).
    """
    headers, records = deref(headers), deref(records)
    if not expect_type(headers, list, "generate_records/3", arg=1):
        return
    if not expect_type(records, list, "generate_records/3", arg=2):
        return
    try:
        header_strs = [text_or_str(h) for h in headers]
        buf = io.StringIO()
        writer = _csv.DictWriter(buf, fieldnames=header_strs)
        writer.writeheader()
        for record in records:
            record = deref(record)
            if not isinstance(record, DictTerm):
                note_mismatch(
                    "generate_records/3",
                    f"was called with a list containing {type(record).__name__} "
                    "where a list of DictTerm records is required (argument 2)",
                )
                return
            row_dict = {text_or_str(k): text_or_str(v)
                        for k, v in record.data.items()}
            writer.writerow(row_dict)
        result = buf.getvalue()
    except (TypeError, ValueError) as exc:
        note_rejected_call("generate_records/3", exc)
        return
    if unify(string, result, trail):
        yield None


def _read_file_2(path, rows, trail, k):
    """read_file/2: read and parse a CSV file into list of rows."""
    path = _require_text(deref(path), "read_file/2", 1)
    if path is None:
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
    """read_records/2: read CSV file with headers → list of DictTerms.

    Records are keyed by the header cells' ATOMS, as ``parse_records/3``.
    """
    path = _require_text(deref(path), "read_records/2", 1)
    if path is None:
        return
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = _csv.DictReader(f)
            result = [
                DictTerm({_field_key(k): v for k, v in row.items()})
                for row in reader
            ]
    except OSError:
        return
    if unify(records, result, trail):
        yield None


def _write_file_2(path, rows, trail, k):
    """write_file/2: serialize rows and write to CSV file."""
    path, rows = _require_text(deref(path), "write_file/2", 1), deref(rows)
    if path is None:
        return
    if not expect_type(rows, list, "write_file/2", arg=2):
        return
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = _csv.writer(f)
            for row in rows:
                row = deref(row)
                if not isinstance(row, list):
                    note_mismatch(
                        "write_file/2",
                        f"was called with a list containing {type(row).__name__} "
                        "where a list of row lists is required (argument 2)",
                    )
                    return
                writer.writerow(_deref_row(row))
    except (TypeError, ValueError) as exc:
        note_rejected_call("write_file/2", exc)
        return
    except OSError:
        return
    yield None


# ── Build and export predicate objects ──────────────────────────────────

parse_row = ModulePredicate("parse_row")
parse_row._register(2, simple_to_trampoline(_parse_row_2))

parse = ModulePredicate("parse")
parse._register(2, simple_to_trampoline(_parse_2))

parse_records = ModulePredicate("parse_records")
parse_records._register(3, simple_to_trampoline(_parse_records_3))

generate = ModulePredicate("generate")
generate._register(2, simple_to_trampoline(_generate_2))

generate_records = ModulePredicate("generate_records")
generate_records._register(3, simple_to_trampoline(_generate_records_3))

read_file = ModulePredicate("read_file")
read_file._register(2, simple_to_trampoline(_read_file_2))

read_records = ModulePredicate("read_records")
read_records._register(2, simple_to_trampoline(_read_records_2))

write_file = ModulePredicate("write_file")
write_file._register(2, simple_to_trampoline(_write_file_2))
