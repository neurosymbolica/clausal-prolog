# Files Module

The files library (`library(py_files)`, the Python module `py.files`) provides relational predicates for file and directory operations: existence checks, listing, metadata, CRUD, path manipulation, and temporary files. For higher-level file formats, see the [JSON](json.md), [CSV](csv.md), and [YAML](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-yaml/docs/yaml.md) modules.

The implementation lives in `clausal/modules/py/files.py`.

Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`). They
reach the Python module through its `library(py_files)` facade; the
[seam](syntax.md) imports the module itself, `-import_from(py.files, [...])`.

---

## Import

```clausal
:- use_module(library(py_files), [file_exists/1, directory_files/2,
                                  read_file_to_string/2, write_string_to_file/2,
                                  join_path/3, make_directory_path/1]).
```

Or import every predicate, and call them module-qualified if you like:

```clausal
:- use_module(library(py_files)).

% then call file_exists("data.csv"), or py_files:file_exists("data.csv"), etc.
has_data :-
    py_files:file_exists("data.csv").
```

---

## Text in, text out

A path or content argument may be a string (`"data.csv"`) or an atom
(`'data.csv'`; from the seam, also a Python `str` passed in with `++`). Every text the module
hands back — file names, joined paths, file contents, extensions — is a
**string**: `directory_files` on a directory holding `a.py` and `b.txt` gives
`["a.py", "b.txt"]`, which Python sees as `[('$chars', 'a.py'), ('$chars', 'b.txt')]`
(use `clausal.to_python` for plain `str`s).

---

## Errors

A file-system failure in an action **raises** an ISO error (ruled
2026-10-02; these predicates used to fail):

| Failure | Error |
|---|---|
| the path does not exist (or goes through a file: `a.txt/b`) | `existence_error(source_sink, Path)` |
| no permission; a directory where a file is needed, or a file where a directory is needed; the name is already taken; the directory is not empty | `permission_error(Action, source_sink, Path)` |
| too many open files; no space left | `resource_error(file_descriptors)`; `resource_error(disk_space)` |

`Action` is `open` for reading, writing and listing (ISO `open/4`), `modify`
for `delete_file`, `delete_directory`, `rename_file`, and `create` for
`make_directory`, `make_directory_path`, `temp_file`, `temp_directory`.
`Path` is the argument as written; for `rename_file` and `copy_file` it is
the argument the failure is about. The three **tests** below
(`file_exists`, `directory_exists`, `path_exists`) never raise: their
failure is the answer, also for a path the process may not look at.

## Predicates

### Existence Checks

#### file_exists/1

`file_exists(Path)` — succeeds if Path is a regular file.

```clausal
:- use_module(library(py_files), [file_exists/1]).

check_config :-
    file_exists("config.json").
```

#### directory_exists/1

`directory_exists(Path)` — succeeds if Path is a directory.

#### path_exists/1

`path_exists(Path)` — succeeds if Path exists (file, directory, or other).

### Directory listing

#### directory_files/2

`directory_files(Dir, Files)` — unify Files with a sorted list of filenames in Dir. Deterministic (one solution, full list).

```clausal
:- use_module(library(py_files), [directory_files/2, temp_directory/1,
                                  join_path/3, write_string_to_file/2]).

list_dir(DIR, FILES) :-
    directory_files(DIR, FILES).

test("sorted names, as strings") :-
    temp_directory(DIR),
    join_path(DIR, "b.txt", B), write_string_to_file(B, "b"),
    join_path(DIR, "a.py", A), write_string_to_file(A, "a"),
    list_dir(DIR, FILES),
    FILES == ["a.py", "b.txt"].
```

#### directory_entries/2

`directory_entries(Dir, Entry)` — enumerate directory entries one at a time via backtracking.

```clausal
:- use_module(library(py_files), [directory_entries/2, temp_directory/1,
                                  join_path/3, write_string_to_file/2]).

print_entries(DIR) :-
    forall(directory_entries(DIR, ENTRY), format("~s~n", [ENTRY])).

test("one entry per solution") :-
    temp_directory(DIR),
    join_path(DIR, "only.txt", P), write_string_to_file(P, "x"),
    findall(E, directory_entries(DIR, E), ES),
    ES == ["only.txt"],
    print_entries(DIR).
```

### File Metadata

#### file_size/2

`file_size(Path, Size)` — unify Size with file size in bytes (integer).

```clausal
:- use_module(library(py_files), [file_size/2]).

is_large_file(PATH) :-
    file_size(PATH, SIZE),
    SIZE > 1000000.
```

#### file_modification_time/2

`file_modification_time(Path, Time)` — unify Time with the modification timestamp (float, seconds since epoch).

### Destructive Operations

All destructive predicates require ground path arguments.

#### delete_file/1

`delete_file(Path)` — delete a file. A missing file is `existence_error(source_sink, Path)`; a directory is `permission_error(modify, source_sink, Path)`.

#### delete_directory/1

`delete_directory(Path)` — delete an empty directory. A missing one is `existence_error(source_sink, Path)`; a non-empty one, or a file, `permission_error(modify, source_sink, Path)`.

#### rename_file/2

`rename_file(Old, New)` — rename or move a file or directory.

#### copy_file/2

`copy_file(Source, Destination)` — copy a file (preserves metadata). Not for directories.

### Directory Creation

#### make_directory/1

`make_directory(Path)` — create a directory. A path that already exists is `permission_error(create, source_sink, Path)`; a missing parent `existence_error(source_sink, Path)`.

#### make_directory_path/1

`make_directory_path(Path)` — create a directory and all parents (like `mkdir -p`). Succeeds even if the directory already exists.

```clausal
:- use_module(library(py_files), [make_directory_path/1]).

ensure_output_dir :-
    make_directory_path("output/reports/2024").
```

### File I/O

#### read_file_to_string/2

`read_file_to_string(Path, Contents)` — read an entire file as a UTF-8 string. A missing file is `existence_error(source_sink, Path)`; content that is not UTF-8 fails.

```clausal
:- use_module(library(py_files), [file_exists/1, read_file_to_string/2]).

read_config(PATH, CONTENT) :-
    file_exists(PATH),
    read_file_to_string(PATH, CONTENT).
```

#### write_string_to_file/2

`write_string_to_file(Path, Contents)` — write a string to a file, overwriting any existing content.

#### append_string_to_file/2

`append_string_to_file(Path, Contents)` — append a string to a file. Creates the file if it does not exist.

### Path Manipulation

#### absolute_path/2

`absolute_path(Relative, Absolute)` — resolve a relative path to an absolute path.

#### join_path/3

`join_path(Base, Relative, Joined)` — join two path components.

```clausal
:- use_module(library(py_files), [join_path/3]).

output_path(DIR, NAME, PATH) :-
    join_path(DIR, NAME, PATH).

test("join") :-
    output_path("out", "report.txt", PATH),
    PATH == "out/report.txt".
```

#### split_path/3

`split_path(Path, Directory, Filename)` — split a path into its directory and filename parts.

```clausal
:- use_module(library(py_files), [split_path/3]).

get_filename(PATH, NAME) :-
    split_path(PATH, _, NAME).

test("split") :-
    get_filename("out/report.txt", NAME),
    NAME == "report.txt".
```

#### file_extension/2

`file_extension(Path, Extension)` — unify Extension with the file extension (including the dot, e.g. `".csv"`). Empty string if no extension.

```clausal
:- use_module(library(py_files), [file_extension/2]).

is_python_file(PATH) :-
    file_extension(PATH, ".py").

test("extension") :-
    is_python_file("src/main.py"),
    \+ is_python_file("README.md").
```

### Temporary Files

#### temp_file/1

`temp_file(Path)` — create a temporary file and unify Path with its path. The caller is responsible for cleanup.

#### temp_directory/1

`temp_directory(Path)` — create a temporary directory and unify Path with its path. The caller is responsible for cleanup.

---

## Example

This example uses [`include`](higher_order.md) to select files by extension.

```clausal
:- use_module(library(py_files), [file_exists/1, directory_files/2,
                                  read_file_to_string/2, write_string_to_file/2,
                                  join_path/3, make_directory_path/1,
                                  file_extension/2, temp_directory/1]).

save_output(DIR, NAME, CONTENT) :-
    make_directory_path(DIR),
    join_path(DIR, NAME, PATH),
    write_string_to_file(PATH, CONTENT).

python_files(DIR, FILES) :-
    directory_files(DIR, ALL),
    include(is_py, ALL, FILES).

is_py(F) :-
    file_extension(F, ".py").

read_config(PATH, CONTENT) :-
    file_exists(PATH),
    read_file_to_string(PATH, CONTENT).

test("save, select, read back") :-
    temp_directory(TMP),
    join_path(TMP, "out", DIR),
    save_output(DIR, "main.py", "print(1)"),
    save_output(DIR, "notes.txt", "todo"),
    python_files(DIR, FILES),
    FILES == ["main.py"],
    join_path(DIR, "notes.txt", NOTES),
    read_config(NOTES, CONTENT),
    CONTENT == "todo".
```
