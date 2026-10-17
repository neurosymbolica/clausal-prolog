# CSV Module

The `py.csv` standard library module provides relational predicates for parsing and generating CSV data. CSV records with headers map to [`DictTerm`](dicts_sets.md) for unification-aware access.

The implementation lives in `clausal/modules/py/csv.py`.

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`, ISO Prolog syntax). Clausal Prolog reaches the Python
    module `py.csv` through its facade, `library(py_csv)` (the `py_` prefix
    keeps the name clear of Scryer's own `library(csv)`; see
    [Importing Prolog](importing_prolog.md)). The [seam](syntax.md)
    imports the module directly, as `-import_from(py.csv, [...])`.

---

## Import

```clausal
:- use_module(library(py_csv), [parse/2, parse_row/2, parse_records/3,
                                generate/2, generate_records/3,
                                read_file/2, read_records/2, write_file/2]).
```

Or import the whole module and qualify the calls (see
[module import](import.md)):

```clausal
:- use_module(library(py_csv)).

% then call py_csv:read_file("data.csv", Rows), etc.
test("qualified") :-
    py_csv:parse_row("x,y", Row),
    Row == ["x", "y"].
```

---

## Type Mapping

- CSV rows → a list of rows, each a list of **strings**
- CSV with headers → `list` of [`DictTerm`](dicts_sets.md) (one per record)
- All values are strings — no automatic type coercion. Use `number_chars/2` (a string is a list of chars) to convert.

---

## Predicates

### parse_row/2

`parse_row(String, Row)` — parse a single CSV line into a list of strings. Handles quoting.

```clausal
:- use_module(library(py_csv), [parse_row/2]).

parse_line(Line, Fields) :-
    parse_row(Line, Fields).

test("quoted field") :-
    parse_line("a,\"b,c\",d", Fields),
    Fields == ["a", "b,c", "d"].
```

### parse/2

`parse(String, Rows)` — parse a multi-line CSV string into a list of rows (each row a list of strings).

```clausal
:- use_module(library(py_csv), [parse/2]).

test("parse") :-
    parse("a,b\nc,d\n", Rows),
    Rows == [["a", "b"], ["c", "d"]].
```

### parse_records/3

`parse_records(String, Headers, Records)` — parse CSV with the first row as headers. Each record is a `DictTerm` keyed by the header **atoms**, and `Headers` is the list of those same atoms, so `get(Record, name, V)` reads a column (the seam also spells it `RECORD.name`). Values stay strings.

```clausal
:- use_module(library(py_csv), [parse_records/3]).
:- use_module(library(json), [get/3]).

parse_and_get_name(CsvText, Name) :-
    parse_records(CsvText, _Headers, Records),
    in_(Record, Records),
    % the atom key; "name" would fail
    get(Record, name, Name).

test("one name per record") :-
    findall(N, parse_and_get_name("name,age\nann,3\nbob,4\n", N), Names),
    Names == ["ann", "bob"].

test("headers are atoms") :-
    parse_records("name,age\nann,3\nbob,4\n", Headers, _),
    Headers == [name, age].
```

With the text `"name,age\nann,3\nbob,4\n"` this yields `Name = "ann"`, then
`Name = "bob"`; `_Headers` is `[name, age]`.

### generate/2

`generate(Rows, String)` — serialize a list of rows (lists of values) to a CSV string. Values with commas are automatically quoted; rows end in `\r\n`, as Python's `csv` writes them.

```clausal
:- use_module(library(py_csv), [generate/2]).

test("generate") :-
    generate([["a", "b,c"], ["1", "2"]], Csv),
    Csv == "a,\"b,c\"\r\n1,2\r\n".
```

### generate_records/3

`generate_records(Headers, Records, String)` — serialize DictTerm records with a header row. The inverse of `parse_records/3`: it accepts the atom headers and atom record keys that predicate answers, and plain strings just as well.

### read_file/2

`read_file(Path, Rows)` — read and parse a CSV file into a list of rows. Fails on file error.

### read_records/2

`read_records(Path, Records)` — read a CSV file with headers, returning a list of DictTerms keyed by the header atoms.

```clausal
:- use_module(library(py_csv), [read_records/2]).

load_data(Records) :-
    read_records("data.csv", Records).
```

### write_file/2

`write_file(Path, Rows)` — serialize rows and write to a CSV file. Fails if rows contain unbound variables.

---

## Example

```clausal
:- use_module(library(py_csv), [read_records/2, parse_row/2, generate/2]).

load_data(Records) :-
    read_records("data.csv", Records).

parse_line(Line, Row) :-
    parse_row(Line, Row).

export_rows(Rows, Csv) :-
    generate(Rows, Csv).
```
