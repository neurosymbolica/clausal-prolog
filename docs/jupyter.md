# Jupyter Notebooks

Clausal integrates with Jupyter notebooks — query logic programs interactively
from notebook cells and see results rendered with syntax colouring.  The
[`*(goals)` query syntax](ipython.md) and automatic variable declaration work the same as in
terminal IPython; the difference is that solutions are rendered as styled HTML
instead of a terminal-interactive keypress loop.

---

## Setup

One-time setup in the first cell of your notebook:

```python
from clausal.import_hook import enable_ipython
enable_ipython(globals())
```

Or set `CLAUSAL_IPYTHON=1` in your environment to auto-enable on import:

```bash
# ~/.zshrc or ~/.bashrc
export CLAUSAL_IPYTHON=1
```

---

## Your first query

Import a Clausal module and query it with the `*(goals)` syntax:

```python
import clausal.examples.fibonacci as fib

*(fib.fib(8, N))
```

This displays `N is 21` with syntax colouring.  Uppercase names like `N` are
automatically allocated as fresh logic variables.

---

## How solutions display

In a Jupyter notebook, all solutions are rendered at once (up to a configurable
limit) as styled HTML.  Each solution is separated by **or**:

```python
*(X in [1, 2, 3])
```

Displays:

> X is 1<br>
> or<br>
> X is 2<br>
> or<br>
> X is 3<br>
> No more solutions.

In terminal IPython, the same code uses interactive keypresses instead.

---

## Solution limits

By default, at most **20 solutions** are shown in a Jupyter notebook.  This
prevents accidentally rendering thousands of results from a large search space.

Override per-query by building the `Solutions` yourself — it wraps any
iterator of binding dicts — and passing `limit`. The goal is a cell run
against a module with `solve`:

```python
from clausal import Module, Var, solve, Solutions

X = Var()
Solutions(({"X": X.value}
           for _ in solve(("in_", X, list(range(100))), module=Module("scratch"))),
          limit=5)
```

Or change the global default:

```python
Solutions.DEFAULT_JUPYTER_LIMIT = 50
```

---

## Worked examples

The following examples are written in Clausal's `.clausal` syntax.  Each block
is automatically tested by the documentation test runner.

### Family tree

```clausal
parent("alice", "bob"),
parent("alice", "carol"),
parent("bob", "dave"),
parent("bob", "eve"),

grandparent(GP, GC) <- (
    parent(GP, MID),
    parent(MID, GC)
)

test("alice is grandparent of dave") <- (grandparent("alice", "dave"))
test("alice is grandparent of eve") <- (grandparent("alice", "eve"))
```

In a notebook you would query this as:

```python
import family
*(family.grandparent("alice", GC))
```

### List membership and append

```clausal
member(X, [X, *_]),
member(X, [_, *REST]) <- member(X, REST)

my_append([], YS, YS),
my_append([H, *XS], YS, [H, *ZS]) <- my_append(XS, YS, ZS)

test("member finds element") <- (member(2, [1, 2, 3]))
test("append two lists") <- (my_append([1, 2], [3, 4], [1, 2, 3, 4]))
```

### Recursive length

```clausal
my_len([], 0),
my_len([_, *T], N) <- (
    my_len(T, N1),
    N == N1 + 1
)

test("length of empty list") <- (my_len([], 0))
test("length of three-element list") <- (my_len(["a", "b", "c"], 3))
```

### Accumulator pattern

```clausal
sum_list([], 0),
sum_list([H, *T], S) <- (
    sum_list(T, S1),
    S == S1 + H
)

test("sum of 1..4 is 10") <- (
    sum_list([1, 2, 3, 4], S),
    S == 10
)
test("sum of empty is 0") <- (
    sum_list([], S),
    S == 0
)
```

### Fibonacci

```clausal
fib(0, 0),
fib(1, 1),
fib(N, F) <- (
    N > 1,
    N1 == N - 1,
    N2 == N - 2,
    fib(N1, F1),
    fib(N2, F2),
    F == F1 + F2
)

test("fib(0) = 0") <- (fib(0, 0))
test("fib(5) = 5") <- (fib(5, 5))
test("fib(8) = 21") <- (fib(8, 21))
```

---

## Differences from terminal IPython

| Feature | Terminal IPython | Jupyter Notebook |
|---------|-----------------|------------------|
| Solution display | One at a time, key-driven | All at once (up to limit) |
| Interaction | SPACE/n/ENTER/ESC keys | No interactive keys |
| Colours | ANSI escape codes | CSS spans |
| Default limit | Unlimited (manual stepping) | 20 solutions |

See [IPython / Jupyter](ipython.md) for the full reference on the `*(goals)`
syntax, variable auto-declaration, and the `Solutions` class API.
