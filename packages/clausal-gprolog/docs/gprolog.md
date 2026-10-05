# GNU Prolog Embedding

Clausal Prolog includes an embedded [GNU Prolog](http://www.gprolog.org) engine via a Python C extension linked directly against `libgprolog`. This gives you an in-process Prolog engine with native-code compilation and built-in finite domain constraint solving.

## About GNU Prolog

[GNU Prolog](http://www.gprolog.org) is a mature, high-performance Prolog system written in C. It compiles Prolog to native code via its own WAM (Warren Abstract Machine) and includes a powerful built-in finite domain constraint solver — no library imports needed.

GNU Prolog is notable for:

- **Native compilation** — Prolog clauses compile to machine code, not bytecode
- **Built-in FD solver** — finite domain constraints (`fd_domain/3`, `#=/2`, `fd_labeling/1`) are available without imports
- **ISO conformance** — strong adherence to the ISO Prolog standard
- **Lightweight** — fast startup, small memory footprint

By embedding GNU Prolog in-process, Clausal Prolog gives you access to a fast, constraint-capable Prolog engine alongside the native Python-integrated engine and the [Scryer embedding](scryer.md).

---

## When to use GNU Prolog vs other engines

Clausal Prolog's **native engine** is tightly integrated with Python. This is the right choice for most programs.

The **GNU Prolog embedding** is for when you need:

- **Finite domain constraints** — GNU Prolog's built-in FD solver is fast and well-tested
- **Native-code performance** — compiled Prolog for compute-intensive queries
- **Lightweight engine** — faster startup and lower memory than Scryer
- **Cross-engine validation** — run the same program on multiple engines to cross-check results

The **[Scryer embedding](scryer.md)** is better when you need:

- **Tabling** — GNU Prolog has no tabling support
- **CLP(B)** — Boolean constraints are not available in GNU Prolog
- **Module system** — GNU Prolog has no module system
- **Multiple concurrent engines** — GNU Prolog only allows one engine per process

!!! note "GNU Prolog embedding vs `.pl` import"

    Clausal Prolog offers three ways to run Prolog code:

    - **[Importing `.pl` files](importing_prolog.md)** translates Prolog to seam source and runs it on the native engine.
    - **[Scryer embedding](scryer.md)** runs Prolog on an ISO Prolog engine in-process.
    - **GNU Prolog embedding** (this page) runs Prolog on a native-code Prolog engine with built-in FD constraints.

    All three approaches can coexist in the same project.

---

## Building the extension

The GNU Prolog embedding requires GNU Prolog compiled with `--disable-regs` and `-fPIC` (for shared library compatibility):

```bash
# Build GNU Prolog for embedding (if needed)
# Standard package installs (apt install gprolog) won't work —
# they use hardware register mapping which conflicts with Python.
cd /path/to/gprolog-1.5.0/src
CFLAGS="-O2 -fPIC" ./configure --prefix=/opt/gprolog-embed --disable-regs --with-c-flags="-fPIC"
make -j$(nproc)
make install

# Build the extension
export GPROLOG_HOME=/opt/gprolog-embed/gprolog-1.5.0
cd prolog_backends/gprolog
pip install -e .
```

The `--disable-regs` flag prevents GNU Prolog from mapping WAM registers to hardware CPU registers (which would corrupt Python's callee-saved registers). The `-fPIC` flag allows the code to be linked into a shared library.

After building, verify:

```python
from clausal.gprolog import AVAILABLE
print(AVAILABLE)  # True
```

If `AVAILABLE` is `False`, the extension is not built. The rest of clausal works normally without it.

You can also set the `GPROLOG_HOME` environment variable to point to your GNU Prolog installation if it's not in a standard location.

---

## Quick start

```python
from clausal.gprolog import GnuProlog

with GnuProlog() as g:
    g.consult_string("parent(tom, bob). parent(bob, ann).")

    for sol in g.query("parent(X, Y)."):
        print(f"{sol['X']} -> {sol['Y']}")
    # tom -> bob
    # bob -> ann
```

---

## Creating a session

```python
from clausal.gprolog import GnuProlog

g = GnuProlog()
```

`GnuProlog()` initializes the GNU Prolog engine. This is fast (a few milliseconds) and lightweight.

**Important: only one `GnuProlog` instance may exist per process lifetime.** GNU Prolog uses a single global C engine that cannot be restarted after shutdown. Create a `GnuProlog` instance once and reuse it for all queries. Closing the session is final — no new instances can be created afterwards.

The session supports the context manager protocol:

```python
with GnuProlog() as g:
    g.consult_string("fact(1).")
    # ... queries ...
# engine released on exit
```

After `close()` or exiting the `with` block, any further use raises `RuntimeError`.

---

## Loading programs

### Prolog source

```python
g.consult_string("parent(tom, bob). parent(bob, ann).")
```

`consult_string` writes the source to a temporary file and consults it. Standard Prolog semantics apply: consulting the same predicate again **replaces** earlier clauses.

For true clause accumulation, declare predicates as `:- dynamic` and use `assertz`:

```python
g.consult_string(":- dynamic(likes/2).")
g.query_bool("assertz(likes(alice, bob)).")
g.query_bool("assertz(likes(bob, carol)).")
g.query_all("likes(X, Y).")
# [{'X': 'alice', 'Y': 'bob'}, {'X': 'bob', 'Y': 'carol'}]
```

### Seam source

```python
g.consult_clausal("""
    Edge(1, 2),
    Edge(2, 3),
    Edge(3, 4),
    Reach(X, Y) <- Edge(X, Y)
    Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
""")

g.query_all("reach(1, X).")
# [{'X': 2}, {'X': 3}, {'X': 4}]
```

`consult_clausal` translates seam (`.seam`) source text to Prolog via `clausal_source_to_prolog` with the GNU Prolog dialect, then loads it. Module directives are automatically stripped since GNU Prolog has no module system.

### Files

```python
g.consult_file("clausal/examples/fibonacci.seam")
g.query_one("fib(10, R).")
# {'R': 55}

g.consult_file("my_library.pl")
```

`consult_file` picks by file extension. A seam (`.seam`) file is run through the seam translator with `Dialect.gprolog()`. A Clausal Prolog (`.clausal`) file is already Prolog: it is consulted as written, except that `:- end_module(...)` is commented out. Any other file (`.pl`) is consulted by GNU Prolog itself.

---

## Querying

### Lazy iteration

```python
for sol in g.query("color(X)."):
    print(sol["X"])
```

`query()` returns a **lazy iterator**. Each call to `next()` resumes Prolog backtracking for one more solution. You can break out of the loop early — the iterator cleans up automatically.

While an iterator is alive, the machine is exclusively held by it. Attempting to load code or start another query raises `GnuPrologError`. The iterator can be closed explicitly:

```python
it = g.query("color(X).")
first = next(it)
it.close()  # return the machine immediately
# now g is usable again
```

### Convenience methods

```python
# First solution only (stops after 1)
g.query_one("parent(tom, X).")
# {'X': 'bob'}  or  None

# All solutions as a list
g.query_all("color(X).")
# [{'X': 'red'}, {'X': 'green'}, {'X': 'blue'}]

# Success/failure check (stops after 1)
g.query_bool("parent(tom, bob).")
# True
```

### Solution format

Each solution is a `dict` mapping Prolog variable names (strings) to Python values:

| Prolog term | Python type |
|---|---|
| integer | `int` |
| float | `float` |
| atom | `str` |
| list | `list` |
| compound `f(a, b)` | the cell `("f", a, b)` |
| unbound variable | `str` (`"_"`) |
| FD variable | `str` (`"_FD"`) |

Ground goals that succeed with no variables return `{}` (empty dict).

---

## Finite domain constraints

GNU Prolog's FD solver is built-in — no library imports needed:

```python
with GnuProlog() as g:
    g.consult_string("""
        solve(X, Y) :-
            fd_domain([X, Y], 1, 10),
            X + Y #= 15,
            X #< Y,
            fd_labeling([X, Y]).
    """)

    for sol in g.query("solve(X, Y)."):
        print(f"X={sol['X']}, Y={sol['Y']}")
    # X=5, Y=10
    # X=6, Y=9
    # X=7, Y=8
```

### Key FD predicates

| Predicate | Purpose |
|---|---|
| `fd_domain(Vars, Min, Max)` | Set domain range for FD variables |
| `fd_domain(Var, List)` | Set domain from explicit value list |
| `X #= Y`, `X #\= Y` | FD equality / disequality |
| `X #< Y`, `X #> Y` | FD ordering |
| `X #=< Y`, `X #>= Y` | FD ordering (non-strict) |
| `fd_all_different(List)` | All variables take distinct values |
| `fd_labeling(Vars)` | Enumerate solutions (default strategy) |
| `fd_labeling(Vars, Options)` | Enumerate with labeling options |
| `fd_var(X)` | Test if X is an FD variable |
| `fd_inf(X, Min)` | Get minimum of X's domain |
| `fd_sup(X, Max)` | Get maximum of X's domain |
| `fd_size(X, Size)` | Get domain size |

### Constraint mapping from seam source

When using `consult_clausal()`, the translation pipeline maps seam constraint names to GNU Prolog equivalents:

| Seam | GNU Prolog |
|---|---|
| `AllDifferent(...)` | `fd_all_different(...)` |
| `Label(...)` | `fd_labeling(...)` |
| `Labeling(...)` | `fd_labeling(...)` |
| `InDomain(...)` | `fd_domain(...)` |

---

## Building query strings from Python values

Use `to_prolog()` to safely embed Python values into Prolog query text:

```python
from clausal.gprolog import GnuProlog, to_prolog

with GnuProlog() as g:
    g.consult_string("check(X, L) :- member(X, L).")
    items = [1, 2, 3]
    g.query_bool(f"check(2, {to_prolog(items)}).")
    # True
```

`to_prolog` handles `int`, `float`, `str` (quoted as atoms), `bool`, `None` (→ `[]`), `list`, and a cell `("f", a, b)`.

---

## Error handling

Prolog errors become Python `GnuPrologError` exceptions:

```python
import _gprolog_ext

try:
    g.query_all("X is foo.")
except _gprolog_ext.GnuPrologError as e:
    print(e)
```

---

## Relationship to the Prolog translation pipeline

The GNU Prolog embedding sits on top of Clausal Prolog's existing [Prolog translation](prolog_translation.md) infrastructure:

```
seam source → clausal_source_to_prolog(dialect=gprolog) → Prolog text → GNU Prolog engine
```

The `Dialect.gprolog()` configuration handles GNU Prolog-specific differences:

- **No module directives** — module declarations are stripped (GNU Prolog has no module system)
- **No library imports** — FD constraints and standard predicates are built-in
- **No tabling** — tabling directives emit a warning comment
- **FD naming** — constraint predicate names use GNU Prolog's `fd_*` convention

---

## Limitations

- **Single engine per process lifetime.** GNU Prolog's C runtime cannot be restarted after shutdown. Create once and keep alive; closing is permanent.
- **No module system.** All predicates live in a single global namespace. There is no `:- module(...)` or `:- use_module(...)`.
- **No tabling.** GNU Prolog does not support tabling/memoization. Recursive predicates that need tabling should use the Scryer embedding.
- **No CLP(B).** Boolean constraint solving is not available. Use Scryer for CLP(B).
- **One query at a time.** While iterating over solutions, no other operations on the session are possible.
- **No live state bridge.** You cannot share logic variables between the native Clausal Prolog engine and GNU Prolog.
- **`consult_string` uses temp files.** Since GNU Prolog only consults from files, string sources are written to temporary files.
- **Must compile GNU Prolog with `--disable-regs` and `-fPIC`.** Standard installs use hardware register mapping which crashes when loaded as a shared library inside Python.
- **`pl2wam` must be on PATH.** GNU Prolog's `consult/1` compiles Prolog source to native code at runtime, requiring the `pl2wam` compiler.
- **Not thread-safe.** Do not share a `GnuProlog` session across threads.
