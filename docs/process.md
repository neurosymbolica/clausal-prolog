# Process Module

The `py.process` standard library module provides relational predicates for running shell commands, launching subprocesses, and sleeping. For environment variables and system metadata, see the [OS](os.md) module.

The implementation lives in `clausal/modules/py/process.py`.

---

## Import

```clausal
-import_from(py.process, [Shell, ShellOutput, ProcessCreate, Sleep])
```

Or via [module import](import.md):

```clausal
-import_module(py.process)
# then use py.process.Shell("ls"), py.process.Sleep(1.0), etc.
```

---

## Predicates

### Shell/1

`Shell(Command)` — run a shell command. Succeeds if the exit code is 0, fails otherwise.

```clausal
run_tests <- Shell("python -m pytest -x")
```

### Shell/2

`Shell(Command, ExitCode)` — run a shell command and unify ExitCode with the integer exit code. Always succeeds (even for non-zero exit codes).

```clausal
check_status(CMD, CODE) <- Shell(CMD, CODE)
```

### ShellOutput/2

`ShellOutput(Command, Output)` — run a shell command and capture stdout as a string. Fails on non-zero exit code.

```clausal
git_status(STATUS) <- ShellOutput("git status --porcelain", STATUS)
```

### ShellOutput/3

`ShellOutput(Command, Output, Error)` — run a shell command and capture both stdout and stderr. Fails on non-zero exit code.

```clausal
compile_and_check(CMD, OUT, ERR) <- ShellOutput(CMD, OUT, ERR)
```

### ProcessCreate/3

`ProcessCreate(Program, Args, Result)` — run a program with an argument list (no shell). Result is a [`DictTerm`](dicts_sets.md) with keys `exit_code`, `stdout`, `stderr`.

```clausal
run_python(CODE, RESULT) <- ProcessCreate("python3", ["-c", CODE], RESULT)
```

### ProcessCreate/4

`ProcessCreate(Program, Args, Options, Result)` — like ProcessCreate/3 with an options [`DictTerm`](dicts_sets.md). Supported options:

| Key | Type | Description |
|---|---|---|
| `"cwd"` | string | Working directory for the subprocess |
| `"timeout"` | number | Timeout in seconds (fails on expiry) |
| `"input"` | string | String to send to stdin |
| `"env"` | DictTerm | Extra environment variables (merged with current env) |

```clausal
run_in_dir(DIR, RESULT) <- ProcessCreate(
    "python3", ["-c", "import os; print(os.getcwd())"],
    {"cwd": DIR}, RESULT
)

run_with_input(INPUT, RESULT) <- ProcessCreate(
    "cat", [], {"input": INPUT}, RESULT
)
```

### Sleep/1

`Sleep(Seconds)` — pause execution for the given number of seconds (integer or float).

```clausal
wait_and_retry(GOAL) <- (Sleep(1.0), call(GOAL))
```

---

## Example

```clausal
-import_from(py.process, [Shell, ShellOutput, ProcessCreate, Sleep])
-import_from(py.json, [Parse, Get])

git_status(STATUS) <- ShellOutput("git status --porcelain", STATUS)

run_tests(RESULT) <- ProcessCreate(
    "python3", ["-m", "pytest", "-x"],
    {"timeout": 60.0}, RESULT
)

poll_until_ready(URL) <- (ShellOutput(f"curl -sf {URL}", _))
poll_until_ready(URL) <- (Sleep(1.0), poll_until_ready(URL))
```
