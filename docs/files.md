# Files Module

The `py.files` standard library module provides relational predicates for file and directory operations: existence checks, listing, metadata, CRUD, path manipulation, and temporary files.

The implementation lives in `clausal/modules/py/files.py`.

---

## Import

```clausal
-import_from(py.files, [FileExists, DirectoryFiles, ReadFileToString,
                        WriteStringToFile, JoinPath, MakeDirectoryPath])
```

Or via module import:

```clausal
-import_module(py.files)
# then use py.files.FileExists("data.csv"), py.files.JoinPath(A_, B_, P_), etc.
```

---

## Predicates

### Existence Checks

#### FileExists/1

`FileExists(Path)` — succeeds if Path is a regular file.

```clausal
check_config <- FileExists("config.json")
```

#### DirectoryExists/1

`DirectoryExists(Path)` — succeeds if Path is a directory.

#### PathExists/1

`PathExists(Path)` — succeeds if Path exists (file, directory, or other).

### Directory Listing

#### DirectoryFiles/2

`DirectoryFiles(Dir, Files)` — unify Files with a sorted list of filenames in Dir. Deterministic (one solution, full list).

```clausal
list_dir(DIR, FILES) <- DirectoryFiles(DIR, FILES)
```

#### DirectoryEntries/2

`DirectoryEntries(Dir, Entry)` — enumerate directory entries one at a time via backtracking.

```clausal
# skip
print_entries(DIR) <- (DirectoryEntries(DIR, ENTRY), Writeln(ENTRY), fail)
```

### File Metadata

#### FileSize/2

`FileSize(Path, Size)` — unify Size with file size in bytes (integer).

```clausal
is_large_file(PATH) <- (FileSize(PATH, SIZE), SIZE > 1000000)
```

#### FileModificationTime/2

`FileModificationTime(Path, Time)` — unify Time with the modification timestamp (float, seconds since epoch).

### Destructive Operations

All destructive predicates require ground path arguments.

#### DeleteFile/1

`DeleteFile(Path)` — delete a file. Fails if the file does not exist.

#### DeleteDirectory/1

`DeleteDirectory(Path)` — delete an empty directory. Fails if not empty or not found.

#### RenameFile/2

`RenameFile(Old, New)` — rename or move a file or directory.

#### CopyFile/2

`CopyFile(Source, Destination)` — copy a file (preserves metadata). Not for directories.

### Directory Creation

#### MakeDirectory/1

`MakeDirectory(Path)` — create a directory. Fails if it already exists.

#### MakeDirectoryPath/1

`MakeDirectoryPath(Path)` — create a directory and all parents (like `mkdir -p`). Succeeds even if the directory already exists.

```clausal
ensure_output_dir <- MakeDirectoryPath("output/reports/2024")
```

### File I/O

#### ReadFileToString/2

`ReadFileToString(Path, Contents)` — read an entire file as a UTF-8 string. Fails on missing files or binary content.

```clausal
read_config(PATH, CONTENT) <- (FileExists(PATH), ReadFileToString(PATH, CONTENT))
```

#### WriteStringToFile/2

`WriteStringToFile(Path, Contents)` — write a string to a file, overwriting any existing content.

#### AppendStringToFile/2

`AppendStringToFile(Path, Contents)` — append a string to a file. Creates the file if it does not exist.

### Path Manipulation

#### AbsolutePath/2

`AbsolutePath(Relative, Absolute)` — resolve a relative path to an absolute path.

#### JoinPath/3

`JoinPath(Base, Relative, Joined)` — join two path components.

```clausal
output_path(DIR, NAME, PATH) <- JoinPath(DIR, NAME, PATH)
```

#### SplitPath/3

`SplitPath(Path, Directory, Filename)` — split a path into its directory and filename parts.

```clausal
get_filename(PATH, NAME) <- SplitPath(PATH, _, NAME)
```

#### FileExtension/2

`FileExtension(Path, Extension)` — unify Extension with the file extension (including the dot, e.g. `".csv"`). Empty string if no extension.

```clausal
is_python_file(PATH) <- FileExtension(PATH, ".py")
```

### Temporary Files

#### TempFile/1

`TempFile(Path)` — create a temporary file and unify Path with its path. The caller is responsible for cleanup.

#### TempDirectory/1

`TempDirectory(Path)` — create a temporary directory and unify Path with its path. The caller is responsible for cleanup.

---

## Example

```clausal
-import_from(py.files, [FileExists, DirectoryFiles, ReadFileToString,
                        WriteStringToFile, JoinPath, MakeDirectoryPath,
                        FileExtension])

save_output(DIR, NAME, CONTENT) <- (
    MakeDirectoryPath(DIR),
    JoinPath(DIR, NAME, PATH),
    WriteStringToFile(PATH, CONTENT)
)

python_files(DIR, FILES) <- (
    DirectoryFiles(DIR, ALL),
    Filter(is_py, ALL, FILES)
)
is_py(F) <- FileExtension(F, ".py")

read_config(PATH, CONTENT) <- (
    FileExists(PATH),
    ReadFileToString(PATH, CONTENT)
)
```
