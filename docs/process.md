# Process Module

The `py.process` standard library module provides relational predicates for running shell commands, launching subprocesses, and sleeping. For environment variables and system metadata, see the [OS](os.md) module.

The implementation lives in `clausal/modules/py/process.py`.

---

## Import

```clausal
-import_from(py.process, [shell, shell_output, process_create, sleep])
```

Or via [module import](import.md):

```clausal
-import_module(py.process)
# then use py.process.shell("ls"), py.process.sleep(1.0), etc.
```

---

## Predicates

### shell/1

`shell(Command)` — run a shell command. Succeeds if the exit code is 0, fails otherwise.

```clausal
run_tests <- shell("python -m pytest -x")
```

### shell/2

`shell(Command, ExitCode)` — run a shell command and unify ExitCode with the integer exit code. Always succeeds (even for non-zero exit codes).

```clausal
check_status(CMD, CODE) <- shell(CMD, CODE)
```

### shell_output/2

`shell_output(Command, Output)` — run a shell command and capture stdout as a string (trailing newline included). Fails on non-zero exit code.

```clausal
git_status(STATUS) <- shell_output("git status --porcelain", STATUS)
```

### shell_output/3

`shell_output(Command, Output, Error)` — run a shell command and capture both stdout and stderr. Fails on non-zero exit code.

```clausal
compile_and_check(CMD, OUT, ERR) <- shell_output(CMD, OUT, ERR)
```

### process_create/3

`process_create(Program, Args, Result)` — run a program with an argument list (no shell). Result is a [`DictTerm`](dicts_sets.md) keyed by the atoms `exit_code`, `stdout`, `stderr` — read it with `RESULT.stdout` or `get(RESULT, stdout, OUT)` (declare the bare key names, e.g. `-private([stdout, exit_code])`, or single-quote them). The captured output is a string.

```clausal
-private([stdout, exit_code])

run_python(CODE, RESULT) <- process_create("python3", ["-c", CODE], RESULT)

python_answer(OUT, CODE) <- (
    run_python("print(42)", R),
    OUT is R.stdout,          # "42\n"
    CODE is R.exit_code       # 0
)
```

### process_create/4

`process_create(Program, Args, Options, Result)` — like process_create/3 with an options [`DictTerm`](dicts_sets.md). Supported options:

| Key | Type | Description |
|---|---|---|
| `cwd` | string | Working directory for the subprocess |
| `timeout` | number | Timeout in seconds (fails on expiry) |
| `input` | string | String to send to stdin |
| `env` | DictTerm | Extra environment variables (merged with current env) |

The option keys are names: write them bare and declare them, or single-quote
them (`'cwd'`, `'input'`, no declaration needed). A double-quoted `"cwd"` is
also found -- an option key is matched by its text whichever way it was
quoted -- but under the default `-double_quotes(chars)` it is a string, so
prefer the atom spellings:

```clausal
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

```clausal
wait_and_retry(GOAL) <- (sleep(1.0), call(GOAL))
```

---

## Example

```clausal
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
