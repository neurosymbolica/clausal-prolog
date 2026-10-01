# Files Module

The `py.files` standard library module provides relational predicates for file and directory operations: existence checks, listing, metadata, CRUD, path manipulation, and temporary files. For higher-level file formats, see the [JSON](json.md), [CSV](csv.md), and [YAML](yaml.md) modules.

The implementation lives in `clausal/modules/py/files.py`.

---

## Import

```seam
-import_from(py.files, [file_exists, directory_files, read_file_to_string,
                        write_string_to_file, join_path, make_directory_path])
```

Or via [module import](import.md):

```seam
-import_module(py.files)
# then use py.files.file_exists("data.csv"), py.files.join_path(A_, B_, P_), etc.
```

---

## Text in, text out

A path or content argument may be a string (`"data.csv"`) or an atom
(`'data.csv'`, or a Python `str` passed in with `++`). Every text the module
hands back — file names, joined paths, file contents, extensions — is a
**string**: `directory_files` on a directory holding `a.py` and `b.txt` gives
`["a.py", "b.txt"]`, which Python sees as `[('$chars', 'a.py'), ('$chars', 'b.txt')]`
(use `clausal.to_python` for plain `str`s).

---

## Predicates

### Existence Checks

#### file_exists/1

`file_exists(Path)` — succeeds if Path is a regular file.

```seam
check_config <- file_exists("config.json")
```

#### directory_exists/1

`directory_exists(Path)` — succeeds if Path is a directory.

#### path_exists/1

`path_exists(Path)` — succeeds if Path exists (file, directory, or other).

### Directory listing

#### directory_files/2

`directory_files(Dir, Files)` — unify Files with a sorted list of filenames in Dir. Deterministic (one solution, full list).

```seam
list_dir(DIR, FILES) <- directory_files(DIR, FILES)
```

#### directory_entries/2

`directory_entries(Dir, Entry)` — enumerate directory entries one at a time via backtracking.

```seam
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:directory_listing"
```

### File Metadata

#### file_size/2

`file_size(Path, Size)` — unify Size with file size in bytes (integer).

```seam
is_large_file(PATH) <- (file_size(PATH, SIZE), SIZE > 1000000)
```

#### file_modification_time/2

`file_modification_time(Path, Time)` — unify Time with the modification timestamp (float, seconds since epoch).

### Destructive Operations

All destructive predicates require ground path arguments.

#### delete_file/1

`delete_file(Path)` — delete a file. Fails if the file does not exist.

#### delete_directory/1

`delete_directory(Path)` — delete an empty directory. Fails if not empty or not found.

#### rename_file/2

`rename_file(Old, New)` — rename or move a file or directory.

#### copy_file/2

`copy_file(Source, Destination)` — copy a file (preserves metadata). Not for directories.

### Directory Creation

#### make_directory/1

`make_directory(Path)` — create a directory. Fails if it already exists.

#### make_directory_path/1

`make_directory_path(Path)` — create a directory and all parents (like `mkdir -p`). Succeeds even if the directory already exists.

```seam
ensure_output_dir <- make_directory_path("output/reports/2024")
```

### File I/O

#### read_file_to_string/2

`read_file_to_string(Path, Contents)` — read an entire file as a UTF-8 string. Fails on missing files or binary content.

```seam
read_config(PATH, CONTENT) <- (file_exists(PATH), read_file_to_string(PATH, CONTENT))
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

```seam
output_path(DIR, NAME, PATH) <- join_path(DIR, NAME, PATH)
```

#### split_path/3

`split_path(Path, Directory, Filename)` — split a path into its directory and filename parts.

```seam
get_filename(PATH, NAME) <- split_path(PATH, _, NAME)
```

#### file_extension/2

`file_extension(Path, Extension)` — unify Extension with the file extension (including the dot, e.g. `".csv"`). Empty string if no extension.

```seam
is_python_file(PATH) <- file_extension(PATH, ".py")
```

### Temporary Files

#### temp_file/1

`temp_file(Path)` — create a temporary file and unify Path with its path. The caller is responsible for cleanup.

#### temp_directory/1

`temp_directory(Path)` — create a temporary directory and unify Path with its path. The caller is responsible for cleanup.

---

## Example

This example uses [`include`](higher_order.md) to select files by extension.

```seam
-import_from(py.files, [file_exists, directory_files, read_file_to_string,
                        write_string_to_file, join_path, make_directory_path,
                        file_extension])

save_output(DIR, NAME, CONTENT) <- (
    make_directory_path(DIR),
    join_path(DIR, NAME, PATH),
    write_string_to_file(PATH, CONTENT)
)

python_files(DIR, FILES) <- (
    directory_files(DIR, ALL),
    include(is_py, ALL, FILES)
)
is_py(F) <- file_extension(F, ".py")

read_config(PATH, CONTENT) <- (
    file_exists(PATH),
    read_file_to_string(PATH, CONTENT)
)
```
