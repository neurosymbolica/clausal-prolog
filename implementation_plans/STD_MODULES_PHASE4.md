# Std Modules Phase 4 — OS & File System

**Status: COMPLETE**

**Depends on:** Module infrastructure (clausal/modules/py/), DictTerm (terms.py)

**Goal:** Add three utility modules wrapping Python's `os`, `pathlib`, and
`subprocess` for system interaction and scripting use cases. These are thin
relational wrappers — predicates participate in unification where it makes
sense (e.g., `WorkingDirectory/2` can both get and set), but most are
deterministic one-answer operations.

**Non-goal:** Re-implementing Python's full `os` or `shutil` surface. Only
predicates that benefit from a named relational interface are included.
Everything else is one `++()` call away.

---

## Design Principles

1. **Module adapter pattern.** Each module defines a `_XxxPredicate` adapter
   class (same pattern as `_RandomPredicate`, `_JsonPredicate`). Simple-mode
   functions are wrapped via `_simple_to_trampoline()`.

2. **Safety first.** File deletion and process execution are side-effecting
   and potentially destructive. Predicates that modify the filesystem or
   execute commands require all path/command arguments to be ground — unbound
   args raise an instantiation error (not silent failure).

3. **Deterministic predicates.** Most predicates succeed once or fail. The
   exceptions are `DirectoryFiles/2` which can enumerate entries via
   backtracking, and `EnvironmentVariable/3` which can enumerate all env vars
   when the key is unbound.

4. **Use `pathlib` internally.** Even for the `os` module predicates, use
   `pathlib.Path` under the hood for cross-platform correctness.

5. **Clausal naming conventions.** TitleCase predicates, expanded names.

---

## 4a — OS Module

**Files:** `clausal/modules/py/os.py` (new), `clausal/modules/os_mod.py`
(alias), `tests/test_os_module.py` (new)

### Predicates

| Predicate | Description |
|---|---|
| `EnvironmentVariable/2` | `EnvironmentVariable(Name, Value)` — get env var. Name bound → look up value. Name unbound → enumerate all env vars via backtracking. |
| `SetEnvironmentVariable/2` | `SetEnvironmentVariable(Name, Value)` — set env var. Both must be ground. |
| `UnsetEnvironmentVariable/1` | `UnsetEnvironmentVariable(Name)` — remove env var. Fails if not set. |
| `WorkingDirectory/1` | `WorkingDirectory(Path)` — unify Path with the current working directory. |
| `ChangeDirectory/1` | `ChangeDirectory(Path)` — change CWD. Path must be ground. Fails if path doesn't exist. |
| `Pid/1` | `Pid(P)` — unify P with the current process ID. |
| `Argv/1` | `Argv(Args)` — unify Args with `sys.argv` as a Python list. |
| `Platform/1` | `Platform(P)` — unify P with `sys.platform` (e.g. `"linux"`, `"darwin"`, `"win32"`). |
| `CPUCount/1` | `CPUCount(N)` — unify N with `os.cpu_count()`. |

### Implementation notes

- `EnvironmentVariable/2`: When Name is unbound, iterate `os.environ.items()`
  and yield each (Name, Value) pair with trail mark/undo for backtracking.
  When Name is bound, `os.environ.get(name)` — fail if missing.
- `SetEnvironmentVariable/2` and `UnsetEnvironmentVariable/1` both require
  ground arguments. `os.environ[name] = value` / `del os.environ[name]`.
- `WorkingDirectory/1` calls `os.getcwd()` and unifies. Read-only — use
  `ChangeDirectory/1` to change.
- `Argv/1`: `_import_stdlib("sys").argv`.
- All simple-mode, wrapped with `_simple_to_trampoline()`.

### Semantics

```
EnvironmentVariable("HOME", HOME)          % HOME = "/home/user"
EnvironmentVariable(NAME, VALUE)           % enumerates all env vars
SetEnvironmentVariable("MY_VAR", "hello")  % sets MY_VAR=hello
UnsetEnvironmentVariable("MY_VAR")         % removes MY_VAR
WorkingDirectory(CWD)                      % CWD = "/workspace/..."
ChangeDirectory("/tmp")                    % changes CWD
Pid(P)                                     % P = 12345
Argv(ARGS)                                 % ARGS = ["script.py", "--flag"]
Platform(P)                                % P = "linux"
CPUCount(N)                               % N = 8
```

### Test plan (~30 tests)

**EnvironmentVariable/2:**
- Bound name → get value (e.g. HOME, PATH).
- Missing name → fail.
- Unbound name → enumerate all env vars (collect at least 3 solutions).
- Unify value with specific string succeeds when correct, fails when wrong.

**SetEnvironmentVariable/2:**
- Set and then get → value matches.
- Unbound name or value raises instantiation error.

**UnsetEnvironmentVariable/1:**
- Set, unset, then get → fails.
- Unset non-existent var → fails.

**WorkingDirectory/1:**
- Returns a non-empty string.
- Unifies with actual `os.getcwd()`.

**ChangeDirectory/1:**
- Change to /tmp, verify WorkingDirectory reflects change. Restore original after.
- Non-existent path → fails.
- Unbound path raises instantiation error.

**Pid/1:**
- Returns positive integer.
- Matches `os.getpid()`.

**Argv/1:**
- Returns a list.

**Platform/1:**
- Returns one of known platform strings.

**CPUCount/1:**
- Returns positive integer.

---

## 4b — Files Module

**Files:** `clausal/modules/py/files.py` (new), `clausal/modules/files_mod.py`
(alias), `tests/test_files_module.py` (new)

### Predicates

| Predicate | Description |
|---|---|
| `FileExists/1` | `FileExists(Path)` — succeeds if Path is a regular file. |
| `DirectoryExists/1` | `DirectoryExists(Path)` — succeeds if Path is a directory. |
| `PathExists/1` | `PathExists(Path)` — succeeds if Path exists (file, directory, or other). |
| `DirectoryFiles/2` | `DirectoryFiles(Dir, Files)` — unify Files with a list of filenames in Dir. |
| `DirectoryEntries/2` | `DirectoryEntries(Dir, Entry)` — enumerate directory entries via backtracking (one per solution). |
| `FileSize/2` | `FileSize(Path, Size)` — unify Size with file size in bytes. |
| `FileModificationTime/2` | `FileModificationTime(Path, Time)` — unify Time with modification timestamp (float, seconds since epoch). |
| `DeleteFile/1` | `DeleteFile(Path)` — delete a file. Fails if not found. |
| `DeleteDirectory/1` | `DeleteDirectory(Path)` — delete an empty directory. Fails if not empty or not found. |
| `RenameFile/2` | `RenameFile(Old, New)` — rename/move a file or directory. |
| `CopyFile/2` | `CopyFile(Source, Destination)` — copy a file (not directory). |
| `MakeDirectory/1` | `MakeDirectory(Path)` — create a directory. Fails if it already exists. |
| `MakeDirectoryPath/1` | `MakeDirectoryPath(Path)` — create a directory and all parents (like `mkdir -p`). Always succeeds. |
| `ReadFileToString/2` | `ReadFileToString(Path, Contents)` — read entire file as a string. |
| `WriteStringToFile/2` | `WriteStringToFile(Path, Contents)` — write a string to a file (overwrite). |
| `AppendStringToFile/2` | `AppendStringToFile(Path, Contents)` — append a string to a file. |
| `AbsolutePath/2` | `AbsolutePath(Relative, Absolute)` — resolve relative path to absolute. |
| `JoinPath/3` | `JoinPath(Base, Relative, Joined)` — join two path components. |
| `SplitPath/3` | `SplitPath(Path, Directory, Filename)` — split path into directory and filename. |
| `FileExtension/2` | `FileExtension(Path, Extension)` — unify Extension with the file extension (including dot). |
| `TempFile/1` | `TempFile(Path)` — create a temporary file and unify Path with its path. |
| `TempDirectory/1` | `TempDirectory(Path)` — create a temporary directory and unify Path with its path. |

### Implementation notes

- Use `pathlib.Path` for all path operations: `Path.exists()`, `Path.is_file()`,
  `Path.is_dir()`, `Path.stat()`, `Path.iterdir()`, `Path.resolve()`,
  `Path.parent`, `Path.name`, `Path.suffix`, `Path.rename()`, `Path.unlink()`,
  `Path.mkdir()`.
- Use `shutil.copy2` for `CopyFile/2` (preserves metadata).
- `DirectoryEntries/2` is non-deterministic: iterates `Path.iterdir()` yielding
  one entry per solution with trail mark/undo. `DirectoryFiles/2` is
  deterministic: returns the full list at once.
- `TempFile/1` and `TempDirectory/1` use `tempfile.NamedTemporaryFile(delete=False)`
  and `tempfile.mkdtemp()`. The caller is responsible for cleanup.
- Destructive predicates (`DeleteFile`, `DeleteDirectory`, `RenameFile`,
  `WriteStringToFile`) require all path arguments to be ground.
- `ReadFileToString/2` fails on non-existent files and on binary files that
  can't be decoded as UTF-8.

### Semantics

```
FileExists("config.json")                     % succeeds if file exists
DirectoryExists("/tmp")                        % succeeds
DirectoryFiles("/tmp", FILES)                  % FILES = ["file1", "file2", ...]
DirectoryEntries("/tmp", ENTRY)                % ENTRY = "file1" ; ENTRY = "file2" ; ...
FileSize("data.bin", SIZE)                     % SIZE = 1024
DeleteFile("old.txt")                          % deletes the file
RenameFile("old.txt", "new.txt")               % renames
CopyFile("src.txt", "dst.txt")                 % copies
MakeDirectory("output")                        % creates directory
MakeDirectoryPath("a/b/c")                     % creates a, a/b, a/b/c
ReadFileToString("config.json", CONTENTS)      % CONTENTS = "{...}"
WriteStringToFile("out.txt", "hello world")    % writes file
AbsolutePath("../foo", ABS)                    % ABS = "/workspace/foo"
JoinPath("/home", "user", P)                   % P = "/home/user"
SplitPath("/home/user/file.txt", DIR, NAME)    % DIR = "/home/user", NAME = "file.txt"
FileExtension("data.csv", EXT)                 % EXT = ".csv"
TempFile(PATH)                                 % PATH = "/tmp/tmpXXXXXX"
TempDirectory(PATH)                            % PATH = "/tmp/tmpXXXXXX"
```

### Test plan (~45 tests)

**Existence checks:**
- `FileExists`: existing file succeeds, non-existent fails, directory fails.
- `DirectoryExists`: existing dir succeeds, file fails.
- `PathExists`: both files and dirs succeed.
- Unbound path raises instantiation error.

**Directory listing:**
- `DirectoryFiles/2`: returns list of strings, non-existent dir fails.
- `DirectoryEntries/2`: yields one entry per solution, collect matches DirectoryFiles.

**File metadata:**
- `FileSize/2`: returns integer > 0 for known file.
- `FileModificationTime/2`: returns float.
- Non-existent file fails.

**Destructive operations:**
- `DeleteFile/1`: create file, delete, verify gone.
- `DeleteDirectory/1`: create empty dir, delete, verify gone. Non-empty fails.
- `RenameFile/2`: rename, verify old gone and new exists.
- `CopyFile/2`: copy, verify both exist with same content.

**Directory creation:**
- `MakeDirectory/1`: create, verify exists. Already exists fails.
- `MakeDirectoryPath/1`: create nested, verify all levels exist.

**File I/O:**
- `ReadFileToString/2`: read known file, verify content.
- `WriteStringToFile/2`: write, read back, verify match.
- `AppendStringToFile/2`: write then append, verify concatenation.
- Non-existent file for read → fails.

**Path manipulation:**
- `AbsolutePath/2`: relative → absolute.
- `JoinPath/3`: components → joined path.
- `SplitPath/3`: path → dir + filename.
- `FileExtension/2`: path → extension.

**Temp files:**
- `TempFile/1`: returns path that exists.
- `TempDirectory/1`: returns path that is a directory.

---

## 4c — Process Module

**Files:** `clausal/modules/py/process.py` (new), `clausal/modules/process_mod.py`
(alias), `tests/test_process_module.py` (new)

### Predicates

| Predicate | Description |
|---|---|
| `Shell/1` | `Shell(Command)` — run shell command via `subprocess.run(cmd, shell=True)`. Succeeds if exit code is 0, fails otherwise. |
| `Shell/2` | `Shell(Command, ExitCode)` — run shell command, unify ExitCode with the integer exit code. Always succeeds (exit code may be non-zero). |
| `ShellOutput/2` | `ShellOutput(Command, Output)` — run shell command, capture stdout as string. Fails on non-zero exit code. |
| `ShellOutput/3` | `ShellOutput(Command, Output, Error)` — run shell command, capture both stdout and stderr. Fails on non-zero exit code. |
| `ProcessCreate/3` | `ProcessCreate(Program, Args, Result)` — run a program with argument list (no shell). Result is a DictTerm with keys `exit_code`, `stdout`, `stderr`. |
| `ProcessCreate/4` | `ProcessCreate(Program, Args, Options, Result)` — like ProcessCreate/3 with an options DictTerm for `cwd`, `env`, `timeout`, `input`. |
| `Sleep/1` | `Sleep(Seconds)` — pause execution for the given number of seconds (float or int). |

### Implementation notes

- `Shell/1,2`: `subprocess.run(cmd, shell=True, capture_output=False)`.
  Shell/1 fails on non-zero return code. Shell/2 always succeeds and unifies
  the exit code.
- `ShellOutput/2,3`: `subprocess.run(cmd, shell=True, capture_output=True,
  text=True)`. Captures stdout (and stderr for /3). Fails on non-zero
  exit code.
- `ProcessCreate/3,4`: `subprocess.run([program] + args, capture_output=True,
  text=True, **opts)`. No shell involved — safer for untrusted input. Result
  is a `DictTerm` with `exit_code`, `stdout`, `stderr` keys.
- Options DictTerm for ProcessCreate/4:
  - `"cwd"` → working directory (string)
  - `"env"` → environment DictTerm (merged with os.environ)
  - `"timeout"` → timeout in seconds (float)
  - `"input"` → stdin string
- `Sleep/1`: `time.sleep(deref(seconds))`. Requires ground numeric argument.
- All command/program arguments must be ground.

### Semantics

```
Shell("echo hello")                            % succeeds (exit code 0)
Shell("false", CODE)                           % CODE = 1
ShellOutput("echo hello", OUT)                 % OUT = "hello\n"
ShellOutput("ls /nonexistent", OUT, ERR)       % fails (non-zero exit)
ProcessCreate("python3", ["-c", "print(42)"], R)
    % R = {"exit_code": 0, "stdout": "42\n", "stderr": ""}
ProcessCreate("python3", ["-c", "print(42)"],
    {"timeout": 5.0, "cwd": "/tmp"}, R)
    % R = {"exit_code": 0, "stdout": "42\n", "stderr": ""}
Sleep(0.5)                                     % pauses 500ms
```

### Test plan (~25 tests)

**Shell/1:**
- `Shell("true")` succeeds.
- `Shell("false")` fails.
- Unbound command raises instantiation error.

**Shell/2:**
- `Shell("true", CODE)` → CODE = 0.
- `Shell("false", CODE)` → CODE = 1.

**ShellOutput/2:**
- `ShellOutput("echo hello", OUT)` → OUT = "hello\n".
- Non-zero exit code → fails.

**ShellOutput/3:**
- Captures both stdout and stderr.
- stderr on error command is non-empty.

**ProcessCreate/3:**
- Run `python3 -c "print(42)"` → DictTerm with exit_code=0, stdout="42\n".
- Non-existent program → fails.

**ProcessCreate/4:**
- With `cwd` option changes working directory.
- With `timeout` option times out on long-running command.
- With `input` option feeds stdin.

**Sleep/1:**
- `Sleep(0.01)` succeeds (verify it took at least ~10ms).
- Unbound argument raises instantiation error.
- Non-numeric argument raises type error.

---

## File Summary

### New files

| File | Purpose |
|---|---|
| `clausal/modules/py/os.py` | OS module implementation |
| `clausal/modules/py/files.py` | Files module implementation |
| `clausal/modules/py/process.py` | Process module implementation |
| `clausal/modules/os_mod.py` | Backward-compatible alias |
| `clausal/modules/files_mod.py` | Backward-compatible alias |
| `clausal/modules/process_mod.py` | Backward-compatible alias |
| `tests/test_os_module.py` | OS module tests (~30) |
| `tests/test_files_module.py` | Files module tests (~45) |
| `tests/test_process_module.py` | Process module tests (~25) |
| `docs/os.md` | OS module docs |
| `docs/files.md` | Files module docs |
| `docs/process.md` | Process module docs |

### Modified files

| File | Change |
|---|---|
| `clausal/modules/__init__.py` | Add py.os, py.files, py.process to docstring |
| `clausal/modules/py/__init__.py` | Add import examples to docstring |
| `docs/index.md` | Link to new module docs |
| `mkdocs.yml` | Add nav entries |

---

## Implementation Order

1. **4a — OS** (simplest, no file I/O, good warmup; `Sleep/1` deferred to process module)
2. **4b — Files** (pathlib-heavy, many predicates but all straightforward)
3. **4c — Process** (subprocess wrapping, DictTerm result, options handling)

Each sub-phase is independently testable and deployable.

---

## Usage Examples

### OS

```python
# clausal file
-import_from(py.os, [EnvironmentVariable, WorkingDirectory, Pid, Platform])

home_directory(HOME) <- EnvironmentVariable("HOME", HOME)

show_info(INFO) <- (
    WorkingDirectory(CWD),
    Pid(P),
    Platform(PLAT),
    INFO is f"PID {P} on {PLAT} in {CWD}"
)
```

### Files

```python
# clausal file
-import_from(py.files, [
    FileExists, DirectoryFiles, ReadFileToString,
    WriteStringToFile, JoinPath, MakeDirectoryPath
])

config_files(DIR, FILES) <- (
    DirectoryExists(DIR),
    DirectoryFiles(DIR, ALL),
    Filter(FileExists, ALL, FILES)
)

read_config(PATH, CONTENT) <- (
    FileExists(PATH),
    ReadFileToString(PATH, CONTENT)
)

save_output(DIR, NAME, CONTENT) <- (
    MakeDirectoryPath(DIR),
    JoinPath(DIR, NAME, PATH),
    WriteStringToFile(PATH, CONTENT)
)
```

### Process

```python
# clausal file
-import_from(py.process, [Shell, ShellOutput, ProcessCreate, Sleep])

git_status(STATUS) <- ShellOutput("git status --porcelain", STATUS)

run_tests(RESULT) <- ProcessCreate(
    "python3", ["-m", "pytest", "-x"],
    {"timeout": 60.0}, RESULT
)

poll_until_ready(URL) <- (
    ShellOutput(f"curl -s {URL}", OUT),
    OUT \= ""
)
poll_until_ready(URL) <- (
    Sleep(1.0),
    poll_until_ready(URL)
)
```
