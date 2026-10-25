# Command line

The `clausal` command runs a Clausal Prolog (`.clausal`) or ISO Prolog
(`.pl`) program. It is installed with the package (`pip install clausal`);
`python -m clausal` is the same command.

```text
clausal [-g GOAL]... [--once] [--test] [--prolog] FILE [-- ARGS...]
clausal [--prolog]           # no FILE: the interactive ?- top-level
clausal --python             # the Python/seam REPL
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
`main/0` need not be exported. A program with no `main/0` is only loaded when
stdin is not a terminal, so `clausal lib.clausal < /dev/null` is a quick load
check: it reports a syntax or load error and exits 1, or exits 0. From a
terminal it opens the `?-` top-level (see below; `--toplevel` forces that).

Clausal Prolog refuses `:- initialization(...)`, so `main/0` is the entry
point by name.

## The interactive top-level: `?-`

`clausal` with no FILE opens a Prolog top-level; `clausal --toplevel FILE`
loads FILE first and then opens it (a FILE with no `main/0`, run from a
terminal, does the same). Queries are read up to their closing `.`, across
lines. Answers print as `-g` prints them, one at a time, and the next
solution is computed only when you ask for it:

```text
?- member(X, [a,b,c]).
   X = a
;  X = b
;  X = c.
?- catch(member(X, [a,b]), _, true).
   X = a
;  X = b
;  false.
?- X = f(Y,Z), Y = Z, dif(W, a).
   X = f(Y,Y), Z = Y, dif(W,a).
```

| Key | Action |
|---|---|
| `;`, Space, `n` | the next solution |
| `f`, `#` *N* Enter | five, or *N*, more |
| `a` | all the rest |
| `w`, `p` | print answers in full, or with lists past 100 elements elided (`[1,2,...\|...]`) |
| `c` | cycle the colour scheme (off, variables) |
| `h`, `?` | help |
| Enter, `.`, Ctrl-C | stop this query |
| `e` | leave the top-level |

An answer the engine knows is the last is printed with its full stop at
once and the prompt returns, as Scryer's top-level does: `member/2` at the
last element, `between/3` at its upper bound, a fact whose later clauses
cannot match (`q(1)` against `q(1). q(2).`), and the other cases listed
under [`solve_with_last`](python_integration.md#solve_with_last-call_with_last-knowing-an-answer-is-the-last)
(the goals after a top-level `!` also count). Knowing this never runs the
goal further. For any other answer the top-level asks, and a requested next
solution that does not exist prints `false.` Residual `dif/2` and CLP(FD) domain
constraints print in plain form (`dif(X,a)`, `X in 4..5`).

An error is one line, `error(Formal,Context).`; Ctrl-C during a search
returns to `?-`. `consult(File)` and `[File]` load a `.clausal` or `.pl` file
and make it the module queries run in; `halt.` and `halt(N)` and Ctrl-D exit.
Lines are edited with readline, and each query is added to the history kept
in `~/.clausal_history` (Up recalls it); Ctrl-C at the prompt drops the line. When stdin is not a terminal there is
no prompt and no key prompt: the first answer of each query is printed.

Colour: `c` at the answer prompt, or F2 or Ctrl-X c at `?-` (the line typed so
far is kept), cycles the colour scheme of answers. `off` (the start, or the
scheme `CLAUSAL_COLOUR` names) prints plain text; `variables` paints each
variable name in a colour taken from a hash of the name, so a variable has the
same colour wherever it appears, in this answer and in every later one. A
pipe is never coloured.

A query may use `!`, `->` and `*->` (in goal position, not as data) when the
loaded file is a `.pl` file, or with `--prolog`; against a `.clausal` file, or
with no file, they are refused, as `.clausal` source refuses them. The
Python/seam REPL that bare `clausal` used to open is `clausal --python`.

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
- Variables whose names start with `_` are not printed. A variable left
  unbound is not printed on its own, and appears by its name inside other
  answers (`S = f(X)`).
- A rational prints as Scryer prints it: `X is 1 rdiv 2` answers
  `X = 1 rdiv 2.`
- A value is written as `writeq/1` writes the right operand of `=`, with
  the operators in force: an operator term above priority 699 and a bare
  operator atom are bracketed, as in Scryer (`T = (a,b).`, `X = (-).`).
- CLP(Q) constraints left on the answer's variables are printed after the
  bindings, projected onto those variables:

  ```prolog
  :- use_module(library(clpq)).
  dependent(X, Y) :- {X + Y = 3, 2*X + 2*Y = 6}.
  between_1_3(X) :- {X > 1, X < 3}.
  ```

  ```bash
  $ clausal lin.clausal -g "dependent(X, Y)"
  {X + Y = 3}.
  $ clausal lin.clausal -g "between_1_3(X)"
  {X > 1}, {X < 3}.
  ```

  When projecting would take too long (many constraints linking many
  variables the answer does not show), the constraints are printed as they
  are stored, over internal variables named `_Q1`, `_Q2`, …: still the
  whole answer, just not simplified.

  A strict bound that passes through a variable the answer does not show
  is printed as non-strict (`{X < Y, Y =< 3}` shows X as `{X =< 3}`), and
  a value that the constraints force is shown as constraints, not as a
  binding.

  Other constraints (`clpz`, `freeze/2`, `dif/2`) are not printed yet.
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
