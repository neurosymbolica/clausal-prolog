# OS Module

The `py.os` standard library module provides relational predicates for environment variables, working directory management, and system metadata. For running shell commands and subprocesses, see the [Process](process.md) module.

The implementation lives in `clausal/modules/py/os.py`.

---

## Import

```clausal
-import_from(py.os, [environment_variable, set_environment_variable,
                     working_directory, change_directory,
                     pid, argv, platform, cpu_count])
```

Or via [module import](import.md):

```clausal
-import_module(py.os)
# then use py.os.environment_variable("HOME", H_), py.os.pid(P_), etc.
```

---

Names and values may be passed as strings or atoms; every text the module
hands back (a variable's value, the working directory, the platform, each
`argv` entry) is a **string**, so `platform("linux")` matches.

---

## Predicates

### environment_variable/2

`environment_variable(Name, Value)` — get or enumerate environment variables.

- **Name bound**: look up the value. Fails if the variable is not set.
- **Name unbound**: enumerate all environment variables via backtracking.

```clausal
home_directory(HOME) <- environment_variable("HOME", HOME)
```

### set_environment_variable/2

`set_environment_variable(Name, Value)` — set an environment variable. Both arguments must be ground strings.

```clausal
configure_env <- set_environment_variable("MY_APP_MODE", "production")
```

### unset_environment_variable/1

`unset_environment_variable(Name)` — remove an environment variable. Fails if the variable is not set.

### working_directory/1

`working_directory(Path)` — unify Path with the current working directory.

```clausal
show_cwd(CWD) <- working_directory(CWD)
```

### change_directory/1

`change_directory(Path)` — change the current working directory. Path must be ground. Fails if the path does not exist.

```clausal
work_in_tmp <- change_directory("/tmp")
```

### pid/1

`pid(P)` — unify P with the current process ID (integer).

```clausal
show_pid(P) <- pid(P)
```

### argv/1

`argv(Args)` — unify Args with `sys.argv` as a list of strings.

```clausal
get_args(ARGS) <- argv(ARGS)
```

### platform/1

`platform(P)` — unify P with `sys.platform` (e.g. `"linux"`, `"darwin"`, `"win32"`).

```clausal
is_linux <- platform("linux")
```

### cpu_count/1

`cpu_count(N)` — unify N with the number of CPUs available.

```clausal
show_cpus(N) <- cpu_count(N)
```

---

## Example

```clausal
-import_from(py.os, [environment_variable, working_directory, pid, platform])

show_info(INFO) <- (
    working_directory(CWD),
    pid(P),
    platform(PLAT),
    INFO is f"PID {P} on {PLAT} in {CWD}"      # an atom: an f-string is a Python str
)

home_directory(HOME) <- environment_variable("HOME", HOME)
```
