# CSV Module

The `py.csv` standard library module provides relational predicates for parsing and generating CSV data. CSV records with headers map to [`DictTerm`](dicts_sets.md) for unification-aware access.

The implementation lives in `clausal/modules/py/csv.py`.

---

## Import

```clausal
-import_from(py.csv, [parse, parse_row, parse_records, generate,
                      generate_records, read_file, read_records, write_file])
```

Or via [module import](import.md):

```clausal
-import_module(py.csv)
# then use py.csv.read_file("data.csv", ROWS_), etc.
```

---

## Type Mapping

- CSV rows → Python `list` of `str`
- CSV with headers → `list` of [`DictTerm`](dicts_sets.md) (one per record)
- All values are strings — no automatic type coercion. Use [`++int(X)`](python_integration.md) or `number_chars` for conversion.

---

## Predicates

### parse_row/2

`parse_row(String, Row)` — parse a single CSV line into a list of strings. Handles quoting.

```clausal
parse_line(LINE, FIELDS) <- parse_row(LINE, FIELDS)
```

### parse/2

`parse(String, Rows)` — parse a multi-line CSV string into a list of rows (each row a list of strings).

### parse_records/3

`parse_records(String, Headers, Records)` — parse CSV with the first row as headers. Each record is a `DictTerm` with header keys.

```clausal
-import_from(py.csv, [parse_records])
-import_from(py.json, [get])

parse_and_get_name(CSV_TEXT, NAME) <- (
    parse_records(CSV_TEXT, HEADERS_UNUSED, RECORDS),
    Member(RECORD, RECORDS),
    get(RECORD, "name", NAME)
)
```

### generate/2

`generate(Rows, String)` — serialize a list of rows (lists of values) to a CSV string. Values with commas are automatically quoted.

### generate_records/3

`generate_records(Headers, Records, String)` — serialize DictTerm records with a header row.

### read_file/2

`read_file(Path, Rows)` — read and parse a CSV file into a list of rows. Fails on file error.

### read_records/2

`read_records(Path, Records)` — read a CSV file with headers, returning a list of DictTerms.

```clausal
load_data(RECORDS) <- read_records("data.csv", RECORDS)
```

### write_file/2

`write_file(Path, Rows)` — serialize rows and write to a CSV file. Fails if rows contain unbound variables.

---

## Example

```clausal
-import_from(py.csv, [read_records, parse_row, generate])

load_data(RECORDS) <- read_records("data.csv", RECORDS)

parse_line(LINE, ROW) <- parse_row(LINE, ROW)

export_rows(ROWS, CSV) <- generate(ROWS, CSV)
```
