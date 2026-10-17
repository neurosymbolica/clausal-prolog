# OS Module

The `py.os` standard library module provides relational predicates for environment variables, working directory management, and system metadata. For running shell commands and subprocesses, see the [Process](process.md) module.

The implementation lives in `clausal/modules/py/os.py`. Clausal Prolog
imports it through its facade, `library(py_os)` (the name `library(os)` is
Scryer's; see [Importing Prolog](importing_prolog.md)).

Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`):
ISO Prolog syntax, without cut. (The [seam](syntax.md), Clausal's
Python-syntax surface, imports the module as `py.os`.)

---

## Import

```clausal
:- use_module(library(py_os), [environment_variable/2,
                               set_environment_variable/2,
                               working_directory/1, change_directory/1,
                               pid/1, argv/1, platform/1, cpu_count/1]).
```

Or import every predicate the module exports:

```clausal
:- use_module(library(py_os)).
```

(The seam can also import the module whole, `-import_module(py.os)`, and
call `py.os.pid(P)`; see [module import](import.md).)

---

Names and values may be passed as strings or atoms. Free-form text the module
hands back (a variable's value, the working directory, each `argv` entry) is
a **string**; the platform is a symbolic name and comes back as an **atom**
(`linux`), and `platform("linux")` matches it too ("atom out, text in").

---

## Predicates

### environment_variable/2

`environment_variable(Name, Value)` — get or enumerate environment variables.

- **Name bound**: look up the value. Fails if the variable is not set.
- **Name unbound**: enumerate all environment variables via backtracking.

```clausal
:- use_module(library(py_os), [environment_variable/2]).

home_directory(HOME) :-
    environment_variable("HOME", HOME).

test("a set variable reads back as a string") :-
    environment_variable(NAME, _),
    environment_variable(NAME, VALUE),
    string(VALUE).
```

### set_environment_variable/2

`set_environment_variable(Name, Value)` — set an environment variable. Both arguments must be ground strings.

```clausal
:- use_module(library(py_os), [set_environment_variable/2,
                               environment_variable/2,
                               unset_environment_variable/1]).

configure_env :-
    set_environment_variable("MY_APP_MODE", "production").

test("set, read back, unset") :-
    configure_env,
    environment_variable("MY_APP_MODE", "production"),
    unset_environment_variable("MY_APP_MODE"),
    \+ environment_variable("MY_APP_MODE", _).
```

### unset_environment_variable/1

`unset_environment_variable(Name)` — remove an environment variable. Fails if the variable is not set.

### working_directory/1

`working_directory(Path)` — unify Path with the current working directory.

```clausal
:- use_module(library(py_os), [working_directory/1]).

show_cwd(CWD) :-
    working_directory(CWD).

test("the working directory is a string") :-
    show_cwd(CWD),
    string(CWD).
```

### change_directory/1

`change_directory(Path)` — change the current working directory. Path must be ground. Fails if the path does not exist.

```clausal
:- use_module(library(py_os), [change_directory/1, working_directory/1]).

work_in_tmp :-
    change_directory("/tmp").

test("change to the current directory") :-
    working_directory(CWD),
    change_directory(CWD).
```

### pid/1

`pid(P)` — unify P with the current process ID (integer).

```clausal
:- use_module(library(py_os), [pid/1]).

show_pid(P) :-
    pid(P).

test("the pid is an integer") :-
    show_pid(P),
    integer(P).
```

### argv/1

`argv(Args)` — unify Args with `sys.argv` as a list of strings.

```clausal
:- use_module(library(py_os), [argv/1]).

get_args(ARGS) :-
    argv(ARGS).

test("argv is a list") :-
    get_args(ARGS),
    is_list(ARGS).
```

### platform/1

`platform(P)` — unify P with `sys.platform` as an atom (e.g. `linux`, `darwin`, `win32`); a bound P may be the atom or the string.

```clausal
:- use_module(library(py_os), [platform/1]).

is_linux :-
    platform(linux).

test("the platform is an atom") :-
    platform(P),
    atom(P),
    platform(P).
```

### cpu_count/1

`cpu_count(N)` — unify N with the number of CPUs available.

```clausal
:- use_module(library(py_os), [cpu_count/1]).

show_cpus(N) :-
    cpu_count(N).

test("at least one cpu") :-
    show_cpus(N),
    N >= 1.
```

---

## Example

```clausal
:- use_module(library(py_os), [environment_variable/2, working_directory/1,
                               pid/1, platform/1]).

% A string is a list of characters, so append/2 joins the pieces.
show_info(INFO) :-
    working_directory(CWD),
    pid(P),
    platform(PLAT),
    write_to_string(P, P_TEXT),
    write_to_string(PLAT, PLAT_TEXT),
    append(["PID ", P_TEXT, " on ", PLAT_TEXT, " in ", CWD], INFO).

home_directory(HOME) :-
    environment_variable("HOME", HOME).

test("show_info is a string") :-
    show_info(INFO),
    string(INFO).
```

(The seam builds `INFO` with a Python f-string,
`INFO is f"PID {P} on {PLAT} in {CWD}"`.)
