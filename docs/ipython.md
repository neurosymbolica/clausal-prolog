# IPython / Jupyter REPL

Clausal has first-class IPython integration that turns an IPython session into a
Prolog-style REPL.  Queries use a `*(goals)` syntax, uppercase names are
automatically treated as logic variables, and solutions are presented
interactively one at a time — separated by `or`, just as Clausal's disjunction
operator reads.

---

## Quick start

```python
# Cell 1 — one-time setup per session
from clausal.import_hook import enable_ipython
enable_ipython(globals())

# Cell 2 — load a module
import clausal.examples.sudoku as sudoku

# Cell 3 — query
*(sudoku.Problem(1, ROWS), sudoku.Sudoku(ROWS))
```

`ROWS` is declared automatically as a fresh logic variable — no `Var()` needed.

---

## Auto-enable via environment variable

Set `CLAUSAL_IPYTHON=1` (or `true` / `yes` / `y`) in your shell profile and
the integration activates automatically whenever `clausal` is imported:

```bash
# ~/.zshrc or ~/.bashrc
export CLAUSAL_IPYTHON=1
```

With the env var set, the session simplifies to:

```python
import clausal.examples.sudoku as sudoku

*(sudoku.Problem(1, ROWS), sudoku.Sudoku(ROWS))
```

---

## Query syntax

Queries use the `*(goals)` form — a starred parenthesised expression.  This is
valid Python at parse time (it produces a `Starred` AST node) but would be a
compile-time error; the Clausal AST transformer intercepts it before
compilation.

### Single goal

```python
*(Solve(ROWS))
```

### Conjunction

```python
*(Problem(1, ROWS), Sudoku(ROWS))
```

All goals share a single `Trail` for correct backtracking across the
conjunction.

---

## Variable auto-declaration

Any uppercase name inside a `*(...)` query is automatically assigned a fresh
`Var()` before the query runs:

```python
*(Member(X, [1, 2, 3]), X > 1)
# X is declared as Var() automatically
```

This mirrors Prolog's convention that uppercase identifiers are variables.  If
you need to share a variable across multiple cells, declare it explicitly with
`X = Var()` before the query.

---

## Interactive solution browsing

Solutions are presented one at a time with an `or` separator between them,
matching Clausal's disjunction syntax:

```
ROWS = [[1, 5, 6, ...], ...]
   [SPACE/n: next  |  ENTER/.: stop  |  ESC/q: abort  |  a: all]
```

Key bindings follow standard Prolog REPL conventions:

| Key | Action |
|-----|--------|
| `SPACE`, `n` | next solution |
| `ENTER`, `.` | stop (commit to current solution) |
| `ESC`, `q` | abort (no output) |
| `a` | show all remaining solutions |

---

## Using `Solutions` directly

For programmatic use, wrap any iterator of binding dicts:

```python
from clausal import Var, call, Solutions
from clausal.logic.variables import walk, Trail

ROWS = Var()
trail = Trail()

def gen():
    for _ in call(sudoku.Problem, 1, ROWS, trail=trail):
        for _ in call(sudoku.Solve, ROWS, trail=trail):
            yield {'ROWS': walk(ROWS)}

Solutions(gen())
```

`Solutions` also accepts a predicate instance directly:

```python
ROWS = Var()
Solutions(sudoku.Sudoku(ROWS))
```

---

## `call` with predicate classes

`call()` accepts a predicate class directly — no `module=` argument needed:

```python
from clausal import call

for _ in call(sudoku.Solve, ROWS):
    print(walk(ROWS))
```

String functor names still work when a module is provided:

```python
for _ in call("Solve", ROWS, module=mod):
    ...
```
