# CSV Module

The `py.csv` standard library module provides relational predicates for parsing and generating CSV data. CSV records with headers map to [`DictTerm`](dicts_sets.md) for unification-aware access.

The implementation lives in `clausal/modules/py/csv.py`.

---

## Import

```clausal
-import_from(py.csv, [Parse, ParseRow, ParseRecords, Generate,
                      GenerateRecords, ReadFile, ReadRecords, WriteFile])
```

Or via [module import](import.md):

```clausal
-import_module(py.csv)
# then use py.csv.ReadFile("data.csv", ROWS_), etc.
```

---

## Type Mapping

- CSV rows → Python `list` of `str`
- CSV with headers → `list` of [`DictTerm`](dicts_sets.md) (one per record)
- All values are strings — no automatic type coercion. Use [`++int(X)`](python_integration.md) or `number_chars` for conversion.

---

## Predicates

### ParseRow/2

`ParseRow(String, Row)` — parse a single CSV line into a list of strings. Handles quoting.

```clausal
parse_line(LINE, FIELDS) <- ParseRow(LINE, FIELDS)
```

### Parse/2

`Parse(String, Rows)` — parse a multi-line CSV string into a list of rows (each row a list of strings).

### ParseRecords/3

`ParseRecords(String, Headers, Records)` — parse CSV with the first row as headers. Each record is a `DictTerm` with header keys.

```clausal
-import_from(py.csv, [ParseRecords])
-import_from(py.json, [Get])

parse_and_get_name(CSV_TEXT, NAME) <- (
    ParseRecords(CSV_TEXT, HEADERS, RECORDS),
    Member(RECORD, RECORDS),
    Get(RECORD, "name", NAME)
)
```

### Generate/2

`Generate(Rows, String)` — serialize a list of rows (lists of values) to a CSV string. Values with commas are automatically quoted.

### GenerateRecords/3

`GenerateRecords(Headers, Records, String)` — serialize DictTerm records with a header row.

### ReadFile/2

`ReadFile(Path, Rows)` — read and parse a CSV file into a list of rows. Fails on file error.

### ReadRecords/2

`ReadRecords(Path, Records)` — read a CSV file with headers, returning a list of DictTerms.

```clausal
load_data(RECORDS) <- ReadRecords("data.csv", RECORDS)
```

### WriteFile/2

`WriteFile(Path, Rows)` — serialize rows and write to a CSV file. Fails if rows contain unbound variables.

---

## Example

```clausal
-import_from(py.csv, [ReadRecords, ParseRow, Generate])

load_data(RECORDS) <- ReadRecords("data.csv", RECORDS)

parse_line(LINE, ROW) <- ParseRow(LINE, ROW)

export_rows(ROWS, CSV) <- Generate(ROWS, CSV)
```
