# Process Module

The `py.process` standard library module provides relational predicates for running shell commands, launching subprocesses, and sleeping. For environment variables and system metadata, see the [OS](os.md) module.

The implementation lives in `clausal/modules/py/process.py`.

---

## Import

```seam
-import_from(py.process, [shell, shell_output, process_create, sleep])
```

Or via [module import](import.md):

```seam
-import_module(py.process)
# then use py.process.shell("ls"), py.process.sleep(1.0), etc.
```

---

## Predicates

### shell/1

`shell(Command)` — run a shell command. Succeeds if the exit code is 0, fails otherwise.

```seam
run_tests <- shell("python -m pytest -x")
```

### shell/2

`shell(Command, ExitCode)` — run a shell command and unify ExitCode with the integer exit code. Always succeeds (even for non-zero exit codes).

```seam
check_status(CMD, CODE) <- shell(CMD, CODE)
```

### shell_output/2

`shell_output(Command, Output)` — run a shell command and capture stdout as a string (trailing newline included). Fails on non-zero exit code.

```seam
git_status(STATUS) <- shell_output("git status --porcelain", STATUS)
```

### shell_output/3

`shell_output(Command, Output, Error)` — run a shell command and capture both stdout and stderr. Fails on non-zero exit code.

```seam
compile_and_check(CMD, OUT, ERR) <- shell_output(CMD, OUT, ERR)
```

### process_create/3

`process_create(Program, Args, Result)` — run a program with an argument list (no shell). Result is a [`DictTerm`](dicts_sets.md) keyed by the atoms `exit_code`, `stdout`, `stderr` — read it with `RESULT.stdout` or `get(RESULT, stdout, OUT)` (declare the bare key names, e.g. `-private([stdout, exit_code])`, or single-quote them). The captured output is a string.

```seam
-private([stdout, exit_code])

run_python(CODE, RESULT) <- process_create("python3", ["-c", CODE], RESULT)

python_answer(OUT, CODE) <- (
    run_python("print(42)", R),
    OUT is R.stdout,          # "42\n"
    CODE is R.exit_code       # 0
)
```

A program that cannot be started raises (ruled 2026-10-02; it used to
fail): a program that does not exist is `existence_error(source_sink,
Program)`, one that may not be executed (no execute permission, a
directory) is `permission_error(create, process, Program)` -- Scryer's
`process_create/3` term -- and a `cwd` option naming a missing directory is
`existence_error(source_sink, Cwd)`. A nonzero exit status is a value, not
an error: `exit_code` holds it.

### process_create/4

`process_create(Program, Args, Options, Result)` — like process_create/3 with an options [`DictTerm`](dicts_sets.md). Supported options:

| Key | Type | Description |
|---|---|---|
| `cwd` | string | Working directory for the subprocess |
| `timeout` | number | Timeout in seconds; on expiry the process is killed and `exit_code` is the atom `timeout` |
| `input` | string | String to send to stdin |
| `env` | DictTerm | Extra environment variables (merged with current env) |

The option keys are names: write them bare and declare them, or single-quote
them (`'cwd'`, `'input'`, no declaration needed). A double-quoted `"cwd"` is
also found -- an option key is matched by its text whichever way it was
quoted -- but under the default `-double_quotes(chars)` it is a string, so
prefer the atom spellings:

```seam
-private([cwd, input])

run_in_dir(DIR, RESULT) <- process_create(
    "python3", ["-c", "import os; print(os.getcwd())"],
    {cwd: DIR}, RESULT
)

run_with_input(INPUT, RESULT) <- process_create(
    "cat", [], {input: INPUT}, RESULT
)
```

### sleep/1

`sleep(Seconds)` — pause execution for the given number of seconds (integer or float).

```seam
wait_and_retry(GOAL) <- (sleep(1.0), call(GOAL))
```

---

## Example

```seam
-import_from(py.process, [shell, shell_output, process_create, sleep])
-import_from(py.json, [parse, get])

git_status(STATUS) <- shell_output("git status --porcelain", STATUS)

run_tests(RESULT) <- process_create(
    "python3", ["-m", "pytest", "-x"],
    {'timeout': 60.0}, RESULT
)

poll_until_ready(URL) <- (shell_output(f"curl -sf {URL}", _))
poll_until_ready(URL) <- (sleep(1.0), poll_until_ready(URL))
```
