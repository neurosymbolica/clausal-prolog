# Command line

The `clausal` command runs a Clausal Prolog (`.clausal`) or ISO Prolog
(`.pl`) program. It is installed with the package (`pip install clausal`);
`python -m clausal` is the same command.

```text
clausal [-g GOAL]... [--once] [--test] FILE [-- ARGS...]
clausal                      # no FILE: the interactive REPL
```

## Running a program

Given only a file, `clausal` loads it and runs `main/0`:

```prolog
% hello.clausal
:- module(hello, []).

main :- write('Hello, world'), nl.

:- end_module(hello).
```

```bash
$ clausal hello.clausal
Hello, world
```

The exit status is 0 when `main` succeeds and 1 when it fails or raises.
`main/0` need not be exported. A program with no `main/0` is only loaded, so
`clausal lib.clausal` is a quick load check: it reports a syntax or load
error and exits 1, or exits 0.

Clausal Prolog refuses `:- initialization(...)`, so `main/0` is the entry
point by name.

## Running goals: `-g`

`-g GOAL` runs a goal in the program's module, instead of `main/0`, and
prints each answer the way a Prolog toplevel does:

```bash
$ clausal family.clausal -g "grandparent(tom, X)"
X = ann.
X = pat.
$ clausal family.clausal -g "grandparent(tom, ann)"
true.
$ clausal family.clausal -g "grandparent(ann, X)"
false.
```

- `-g` can be given more than once; the goals run in order.
- `--once` (or `-1`) prints only the first answer of each goal.
- Variables whose names start with `_` are not printed.
- A goal can use the operators the program has: its own `op/3` directives
  and those of the libraries it imports, such as `#=` after
  `:- use_module(library(clpz)).`
- A goal that fails prints `false.` and ends the run with status 1. A goal
  that raises prints the error term on standard error and exits 1. A goal
  that does not parse is a usage error, status 2.

## Running tests: `--test`

`clausal --test FILE` runs the program's `test/1` and `test/2` clauses, the
same as `python -m clausal.testing FILE`. See [Testing](testing.md).

## Program arguments: `--`

Everything after `--` is passed to the program, as a list of atoms in the
read-only `argv` flag:

```prolog
main :- current_prolog_flag(argv, Args), write(Args), nl.
```

```bash
$ clausal echo.clausal -- one two 3
[one,two,3]
```

Each argument is an atom, so the `3` above is the atom `'3'`, not a number.
Without `--`, `argv` is `[]`.

## Exit status

| Status | Meaning |
|---|---|
| 0 | `main/0` or every `-g` goal succeeded, the tests passed, or the program loaded |
| 1 | a goal failed or raised, a test failed, or the program did not load |
| 2 | a usage error: a missing or unsupported FILE, a goal that does not parse, conflicting options |

`--test` returns the test runner's own statuses; see [Testing](testing.md).
