# OS Module

The `py.os` standard library module provides relational predicates for environment variables, working directory management, and system metadata. For running shell commands and subprocesses, see the [Process](process.md) module.

The implementation lives in `clausal/modules/py/os.py`.

---

## Import

```clausal
-import_from(py.os, [EnvironmentVariable, SetEnvironmentVariable,
                     WorkingDirectory, ChangeDirectory,
                     Pid, Argv, Platform, CPUCount])
```

Or via [module import](import.md):

```clausal
-import_module(py.os)
# then use py.os.EnvironmentVariable("HOME", H_), py.os.Pid(P_), etc.
```

---

## Predicates

### EnvironmentVariable/2

`EnvironmentVariable(Name, Value)` — get or enumerate environment variables.

- **Name bound**: look up the value. Fails if the variable is not set.
- **Name unbound**: enumerate all environment variables via backtracking.

```clausal
home_directory(HOME) <- EnvironmentVariable("HOME", HOME)
```

### SetEnvironmentVariable/2

`SetEnvironmentVariable(Name, Value)` — set an environment variable. Both arguments must be ground strings.

```clausal
configure_env <- SetEnvironmentVariable("MY_APP_MODE", "production")
```

### UnsetEnvironmentVariable/1

`UnsetEnvironmentVariable(Name)` — remove an environment variable. Fails if the variable is not set.

### WorkingDirectory/1

`WorkingDirectory(Path)` — unify Path with the current working directory.

```clausal
show_cwd(CWD) <- WorkingDirectory(CWD)
```

### ChangeDirectory/1

`ChangeDirectory(Path)` — change the current working directory. Path must be ground. Fails if the path does not exist.

```clausal
work_in_tmp <- ChangeDirectory("/tmp")
```

### Pid/1

`Pid(P)` — unify P with the current process ID (integer).

```clausal
show_pid(P) <- Pid(P)
```

### Argv/1

`Argv(Args)` — unify Args with `sys.argv` as a Python list.

```clausal
get_args(ARGS) <- Argv(ARGS)
```

### Platform/1

`Platform(P)` — unify P with `sys.platform` (e.g. `"linux"`, `"darwin"`, `"win32"`).

```clausal
is_linux <- Platform("linux")
```

### CPUCount/1

`CPUCount(N)` — unify N with the number of CPUs available.

```clausal
show_cpus(N) <- CPUCount(N)
```

---

## Example

```clausal
-import_from(py.os, [EnvironmentVariable, WorkingDirectory, Pid, Platform])

show_info(INFO) <- (
    WorkingDirectory(CWD),
    Pid(P),
    Platform(PLAT),
    INFO is f"PID {P} on {PLAT} in {CWD}"
)

home_directory(HOME) <- EnvironmentVariable("HOME", HOME)
```
