# Process Module

The `py.process` standard library module provides relational predicates for running shell commands, launching subprocesses, and sleeping. For environment variables and system metadata, see the [OS](os.md) module.

The implementation lives in `clausal/modules/py/process.py`.

Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`),
which uses ISO Prolog syntax. A `.clausal` file reaches the module through
its library facade, `library(py_process)`.

---

## Import

```clausal
:- use_module(library(py_process),
              [shell/1, shell/2, shell_output/2, shell_output/3,
               process_create/3, process_create/4, sleep/1]).
```

Or load the whole library and call its predicates qualified by the module
name (see [module import](import.md)):

```clausal
:- use_module(library(py_process)).

% then call py_process:shell("ls"), py_process:sleep(1.0), etc.
pause :-
    py_process:sleep(0.01).

test("qualified call") :-
    pause.
```

(The [seam](syntax.md) imports the Python module itself,
`-import_from(py.process, [...])` or `-import_module(py.process)`.)

---

## Predicates

Commands, arguments and captured output are strings. In `.clausal` a
double-quoted literal is a string, and list predicates treat it as a list
of characters: the [Example](#example) builds a command with `append/3`.

### shell/1

`shell(Command)` — run a shell command. Succeeds if the exit code is 0, fails otherwise.

```clausal
:- use_module(library(py_process), [shell/1]).

run_tests :-
    shell("python -m pytest -x").

test("exit 0 succeeds, nonzero fails") :-
    shell("true"),
    \+ shell("false").
```

### shell/2

`shell(Command, ExitCode)` — run a shell command and unify ExitCode with the integer exit code. Always succeeds (even for non-zero exit codes).

```clausal
:- use_module(library(py_process), [shell/2]).

check_status(CMD, CODE) :-
    shell(CMD, CODE).

test("exit code") :-
    check_status("exit 3", CODE),
    CODE == 3.
```

### shell_output/2

`shell_output(Command, Output)` — run a shell command and capture stdout as a string (trailing newline included). Fails on non-zero exit code.

```clausal
:- use_module(library(py_process), [shell_output/2]).

git_status(STATUS) :-
    shell_output("git status --porcelain", STATUS).

test("captured stdout") :-
    shell_output("echo hi", OUT),
    OUT == "hi\n".
```

### shell_output/3

`shell_output(Command, Output, Error)` — run a shell command and capture both stdout and stderr. Fails on non-zero exit code.

```clausal
:- use_module(library(py_process), [shell_output/3]).

compile_and_check(CMD, OUT, ERR) :-
    shell_output(CMD, OUT, ERR).

test("stdout and stderr") :-
    compile_and_check("echo out; echo err >&2", OUT, ERR),
    OUT == "out\n",
    ERR == "err\n".
```

### process_create/3

`process_create(Program, Args, Result)` — run a program with an argument list (no shell). Result is a [`DictTerm`](dicts_sets.md) keyed by the atoms `exit_code`, `stdout`, `stderr` — read it with `get(RESULT, stdout, OUT)`. The captured output is a string. (The seam also reads it as `RESULT.stdout`.)

```clausal
:- use_module(library(py_process), [process_create/3]).

run_python(CODE, RESULT) :-
    process_create("python3", ["-c", CODE], RESULT).

python_answer(OUT, CODE) :-
    run_python("print(42)", R),
    get(R, stdout, OUT),          % "42\n"
    get(R, exit_code, CODE).      % 0

test("python answer") :-
    python_answer(OUT, CODE),
    OUT == "42\n",
    CODE == 0.
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

Build the options with `dict_pairs/2` from a list of `Key-Value` pairs. In
`.clausal`, `{cwd: DIR}` is a curly-brace term, not a dict; the seam writes
the dict literal `{cwd: DIR}`. The option keys are atoms: `cwd`, `input`. A
double-quoted `"cwd"` is also found -- an option key is matched by its text
whichever way it was quoted -- but it is a string, so prefer the atom:

```clausal
:- use_module(library(py_process), [process_create/4]).

run_in_dir(DIR, RESULT) :-
    dict_pairs(OPTS, [cwd-DIR]),
    process_create("python3", ["-c", "import os; print(os.getcwd())"],
                   OPTS, RESULT).

run_with_input(INPUT, RESULT) :-
    dict_pairs(OPTS, [input-INPUT]),
    process_create("cat", [], OPTS, RESULT).

test("stdin") :-
    run_with_input("hi", R),
    get(R, stdout, OUT),
    OUT == "hi".

test("timeout") :-
    dict_pairs(OPTS, [timeout-0.2]),
    process_create("sleep", ["5"], OPTS, R),
    get(R, exit_code, CODE),
    CODE == timeout.
```

### sleep/1

`sleep(Seconds)` — pause execution for the given number of seconds (integer or float).

```clausal
:- use_module(library(py_process), [sleep/1]).
:- meta_predicate(wait_and_retry(0)).

wait_and_retry(GOAL) :-
    sleep(1.0),
    call(GOAL).
```

---

## Example

```clausal
:- use_module(library(py_process),
              [shell_output/2, process_create/4, sleep/1]).

git_status(STATUS) :-
    shell_output("git status --porcelain", STATUS).

run_tests(RESULT) :-
    dict_pairs(OPTS, [timeout-60.0]),
    process_create("python3", ["-m", "pytest", "-x"], OPTS, RESULT).

poll_until_ready(URL) :-
    append("curl -sf ", URL, CMD),
    shell_output(CMD, _).
poll_until_ready(URL) :-
    sleep(1.0),
    poll_until_ready(URL).
```
