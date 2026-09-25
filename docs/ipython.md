# IPython / Jupyter REPL

Clausal has first-class IPython integration that turns an IPython session into a
Prolog-style REPL.  Queries use a `*(goals)` syntax, uppercase names are
automatically treated as [logic variables](syntax.md), and solutions are presented
interactively one at a time — separated by `or`, just as Clausal's disjunction
operator reads. For notebook-specific rendering, see [Jupyter Notebooks](jupyter.md).

---

## Quick start

After [setting up the IPython startup hook](#set-up-the-ipython-startup-hook)
(one-time, per profile):

```python
# Cell 1 — load a module
import clausal.examples.sudoku as sudoku

# Cell 2 — query
*(sudoku.problem(1, ROWS), sudoku.sudoku(ROWS))
```

`ROWS` is declared automatically as a fresh logic variable — no `Var()` needed.

---

## Set up the IPython startup hook

IPython parses each cell *before* executing any code in it, so the AST
transformer that rewrites `-import_from(...)` and `*(...)` queries has to
be registered **before your first cell runs**.  The cleanest way is an
IPython startup file that imports Clausal once at session start.

### Recommended — install command

```bash
clausal-install-ipython
```

This drops a single file at
`~/.ipython/profile_default/startup/00-clausal.py`.  Every IPython session
in that profile picks it up automatically; you can delete the file to opt
back out.  Useful flags:

```bash
clausal-install-ipython --profile myprofile   # different IPython profile
clausal-install-ipython --force               # overwrite existing file
clausal-install-ipython --uninstall           # remove the hook
clausal-install-ipython --print               # print the script to stdout
```

### Manual — write the file yourself

If you'd rather not run the install command, the hook is a five-line
file you can copy in by hand:

```python
# ~/.ipython/profile_default/startup/00-clausal.py
try:
    from clausal.import_hook import enable_ipython as _enable_clausal
    _enable_clausal(get_ipython().user_ns)
except ImportError:
    pass
```

### Per-session — call `enable_ipython` from cell 1

Without a startup file, every session needs an explicit setup cell:

```python
from clausal.import_hook import enable_ipython
enable_ipython(globals())
```

After that, subsequent cells can use `*(...)` and `-import_from(...)`.

### Environment-variable opt-in (advanced)

Setting `CLAUSAL_IPYTHON=1` makes `import clausal` *itself* register the
AST transformer — handy if your workflow already imports clausal at the
top of every session, but on its own it doesn't help: until something
imports clausal, IPython has no way to know about the integration.  Use
this in combination with a startup file or a `--ext` IPython extension
that imports clausal during startup:

```bash
# ~/.zshrc or ~/.bashrc
export CLAUSAL_IPYTHON=1
```

---

## Query syntax

There are two ways to query in IPython:

### Plain Python: `solve` with a goal cell

Build the goal as a cell — the predicate's name followed by its arguments —
and run it against the module that defines it, with a standard `for` loop:

```python
from clausal import Var, solve
import hello

for trail in solve(("greeting", X := Var()), module=hello):
    print(X.value)
```

This works identically in plain Python scripts and IPython. A module
attribute such as `hello.greeting` is the predicate's handle (a `str`), not
something to call — see [Querying from Python](python_integration.md#querying-from-python).

### `*(goals)` — IPython-specific shorthand

The `*(goals)` form is an IPython-specific shorthand that auto-declares
uppercase variables and displays solutions interactively.  It is rewritten at
the text level into a valid Python call before compilation (for compatibility
with Python 3.13+).

The entire expression inside `*(...)` is treated as a **clause body**, not
ordinary Python.  Operators that have special meaning in Python are rewritten
into Clausal goals:

| Inside `*(...)` | Goal constructed |
|----------------|-----------------|
| `X is Y` | `Unify(left=X, right=Y)` |
| `X == Y` | `ArithEq(left=X, right=Y)` |
| `X != Y` | `ArithNeq(left=X, right=Y)` |
| `X < Y` | `Lt(left=X, right=Y)` |
| `A and B` | `And(left=A, right=B)` |
| `A or B` | `Or(left=A, right=B)` |

### Single goal

```python
*(solve(ROWS))
```

### Conjunction — comma-separated

```python
*(problem(1, ROWS), sudoku(ROWS))
```

Multiple comma-separated goals are folded into a left-associative `And` chain
and share a single solver context for correct backtracking.

### Unification goal

```python
*(X is ["asdfa", 1, Y, some_term])
```

`is` inside `*(...)` is **unification**, not Python identity.

---

## Variable auto-declaration

Any uppercase name inside a `*(...)` query is automatically allocated as a
fresh `Var()` via a walrus assignment embedded in the goal expression itself:

```python
*(X in [1, 2, 3], X > 1)
# X is allocated as Var() automatically
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

## Terminal colours

In a terminal IPython session (`ipython` command, not Jupyter), ANSI colours
are enabled automatically.  Unbound variables, atoms, numbers, strings, and
brackets each get a distinct colour with rainbow bracket-depth cycling.

Control the style from any cell using the injected helpers:

```python
# Disable colours
set_style(TermStyle())

# Re-enable default colours
set_style(TermStyle(colors=ANSI_COLORS))

# Change the anonymous-variable symbol (default: '_')
set_style(TermStyle(anon_var='?'))

# Custom colour scheme
set_style(TermStyle(colors={
    'number':   '\033[33m',
    'string':   '\033[32m',
    'atom':     '\033[36m',
    'var':      '\033[35m',
    'brackets': ['\033[91m', '\033[93m', '\033[92m', '\033[96m', '\033[94m', '\033[95m'],
    'reset':    '\033[0m',
}))
```

`set_style`, `TermStyle`, and `ANSI_COLORS` are automatically injected into the
IPython namespace by `enable_ipython`.  Colours are **not** enabled in Jupyter
kernels, which render output as HTML rather than a terminal.

---

## Using `Solutions` directly

For programmatic use, wrap any iterator of binding dicts. Run the goals with
`call` — the predicate's name, its arguments, and the module that defines it —
on one shared `Trail`, so the second goal sees the first one's bindings.
`problem/2` fetches a puzzle and `solve/1` constrains and labels it:

```python
from clausal import Var, call, Solutions
from clausal.logic.variables import walk, Trail
from clausal.examples import sudoku

ROWS = Var()
trail = Trail()

def gen():
    for _ in call("problem", 1, ROWS, module=sudoku, trail=trail):
        for _ in call("solve", ROWS, module=sudoku, trail=trail):
            yield {'ROWS': walk(ROWS)}

Solutions(gen())
```

For a single goal, `solve` with a cell does the same job. This one only
fetches puzzle 1 — its blanks stay unbound variables; solving it is the
second goal above:

```python
from clausal import Var, solve, Solutions
from clausal.logic.variables import walk
from clausal.examples import sudoku

ROWS = Var()
Solutions({"ROWS": walk(ROWS)}
          for _ in solve(("problem", 1, ROWS), module=sudoku))
```

`Solutions` does not run a goal cell handed to it directly — a cell is a
tuple, and `Solutions(("problem", 1, ROWS))` would iterate its elements.
Pass the iterator that `solve` or `call` returns.
