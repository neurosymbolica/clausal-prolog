# Trealla Prolog Embedding

Clausal includes an embedded [Trealla Prolog](https://github.com/trealla-prolog/trealla) engine via ctypes. This gives you an in-process, ISO-conformant Prolog engine that you can load `.clausal` or `.pl` programs into and query from Python.

## About Trealla Prolog

[Trealla Prolog](https://github.com/trealla-prolog/trealla) is a compact, fast Prolog interpreter written in plain C by Andrew Davison (Infradig). It targets ISO Prolog compliance and is designed for embedding. Key characteristics:

- **Very fast startup** — no bootstrap delay (unlike Scryer's ~200ms)
- **Small footprint** — ~2.5MB shared library, ~5MB memory per instance
- **ISO conformant** — standard arithmetic, unification, error handling
- **CLP(Z)** — Markus Triska's CLP(Z) constraint library is built in
- **Rich standard library** — lists, assoc, DCGs, dif, format, ordsets, and more

By embedding Trealla in-process, clausal gives you access to a fast, lightweight Prolog engine alongside the native Python-integrated engine.

---

## When to use Trealla vs other engines

| | Native engine | Trealla | Scryer |
|---|---|---|---|
| **Startup** | instant | instant | ~200ms |
| **Memory** | shared with Python | ~5MB | ~100MB |
| **Python interop** | full (Vars, Trail) | query strings | query strings |
| **ISO conformance** | partial | high | very high |
| **CLP(Z)** | native CLP(FD) | library(clpz) | library(clpz) |
| **Tabling** | yes | no | yes |
| **Session isolation** | per-module | singleton | per-instance |
| **Best for** | Python-integrated logic | fast ISO Prolog, embedding | strict ISO, validation |

Use **Trealla** when you need:

- **Fast, lightweight Prolog execution** — no Rust toolchain, instant startup
- **ISO Prolog conformance** — correct semantics for arithmetic, unification, error handling
- **CLP(Z) constraint solving** — integer constraints via Markus Triska's library
- **API-compatible Scryer alternative** — same Python API, one-line switch between backends

---

## Building the extension

Trealla is compiled from C source into a shared library:

```bash
# Clone Trealla (if needed)
git clone https://github.com/trealla-prolog/trealla.git trealla-prolog

# Build with -fPIC for shared library
cd trealla-prolog
make NOFFI=1 NOSSL=1 NOTHREADS=1 ISOCLINE=1 CFLAGS+=-fPIC

# Create the shared library
cc -shared -o libtpl.so *.o src/*.o library/*.o -lm
```

The shared library should be at `trealla-prolog/libtpl.so` relative to the clausal project root. After building, verify:

```python
from clausal.trealla import AVAILABLE
print(AVAILABLE)  # True
```

If `AVAILABLE` is `False`, the shared library was not found. The rest of clausal works normally without it.

---

## Quick start

```python
from clausal.trealla import Trealla

with Trealla() as t:
    t.load_string("parent(tom, bob). parent(bob, ann).")

    for sol in t.query("parent(X, Y)."):
        print(f"{sol['X']} -> {sol['Y']}")
    # tom -> bob
    # bob -> ann
```

---

## Creating a session

```python
from clausal.trealla import Trealla

t = Trealla()
```

`Trealla()` creates a session wrapping the Trealla Prolog interpreter. Unlike Scryer, there is no bootstrap delay — the machine is ready instantly.

The session supports the context manager protocol:

```python
with Trealla() as t:
    t.load_string("fact(1).")
    # ... queries ...
# session closed on exit
```

After `close()` or exiting the `with` block, any further use raises `RuntimeError`.

!!! note "Singleton machine"

    All `Trealla` sessions share a single process-global Prolog instance (Trealla's C internals use global state). This means facts loaded in one session are visible in another. For test isolation, use unique predicate names or retract facts between tests.

---

## Loading programs

### Prolog source

```python
t.consult_string("parent(tom, bob). parent(bob, ann).")
```

`consult_string` and `load_string` both load Prolog source. Standard Prolog semantics apply: consulting the same predicate again **replaces** earlier clauses.

### Clausal source

```python
t.consult_clausal("""
    Edge(1, 2),
    Edge(2, 3),
    Edge(3, 4),
    Reach(X, Y) <- Edge(X, Y)
    Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
""")

t.query_all("reach(1, X).")
# [{'X': 2}, {'X': 3}, {'X': 4}]
```

`consult_clausal` translates the `.clausal` source to Prolog via `clausal_source_to_prolog` with the Trealla dialect, then loads it. All the usual translation rules apply: `PascalCase` becomes `snake_case`, `:=` becomes `is`, `<=` becomes `=<`, etc.

### Files

```python
t.consult_file("clausal/examples/fibonacci.clausal")
t.query_one("fib(10, R).")
# {'R': 55}

t.consult_file("my_library.pl")
```

`consult_file` auto-detects the file extension: `.clausal` files are translated; `.pl` files are loaded as raw Prolog.

---

## Querying

### query()

```python
for sol in t.query("color(X)."):
    print(sol["X"])
```

`query()` returns a **lazy generator** that yields solution dicts. Each call to `next()` resumes Prolog backtracking for one more solution via `pl_query`/`pl_redo`. You can break out of the loop early without computing all solutions.

### Convenience methods

```python
# First solution only
t.query_one("parent(tom, X).")
# {'X': 'bob'}  or  None

# All solutions as a list
t.query_all("color(X).")
# [{'X': 'red'}, {'X': 'green'}, {'X': 'blue'}]

# Success/failure check
t.query_bool("parent(tom, bob).")
# True
```

### Solution format

| Prolog term | Python type |
|---|---|
| integer | `int` (arbitrary precision) |
| float | `float` |
| atom | `str` |
| list | `list` |
| compound `f(a, b)` | `Compound("f", (a, b))` from `clausal.terms` |

Ground goals that succeed with no variables return `{}` (empty dict).

---

## Building query strings from Python values

Use `to_prolog()` to safely embed Python values into Prolog query text:

```python
from clausal.trealla import Trealla, to_prolog

with Trealla() as t:
    t.load_string("member_check(X, L) :- member(X, L).")
    t.consult_string(":- use_module(library(lists)).")
    items = [1, 2, 3]
    t.query_bool(f"member_check(2, {to_prolog(items)}).")
    # True
```

---

## Using Trealla's libraries

Trealla has a rich standard library. Load modules with `:- use_module`:

```python
with Trealla() as t:
    t.consult_string(":- use_module(library(lists)).")
    t.load_string("nums(L) :- numlist(1, 5, L).")
    t.query_one("nums(L).")
    # {'L': [1, 2, 3, 4, 5]}
```

Common Trealla libraries:

| Library | Contents |
|---|---|
| `library(lists)` | `member/2`, `append/3`, `length/2`, `msort/2`, `permutation/2` |
| `library(clpz)` | CLP(Z) — constraints over integers |
| `library(dcgs)` | Definite Clause Grammars |
| `library(dif)` | `dif/2` — sound disequality |
| `library(assoc)` | Association lists |
| `library(format)` | `format/2,3` — formatted output |
| `library(ordsets)` | Ordered set operations |
| `library(pairs)` | Key-value pair operations |
| `library(freeze)` | `freeze/2` — delayed goals |
| `library(lambda)` | Lambda expressions for higher-order predicates |
| `library(reif)` | Reified conditionals (`if_/3`, `tfilter/3`) |

---

## Relationship to the Prolog translation pipeline

The Trealla embedding sits on top of Clausal's existing [Prolog translation](prolog_translation.md) infrastructure:

```
.clausal source -> clausal_source_to_prolog(dialect=Trealla) -> Prolog text -> Trealla machine
```

All translation features work: naming conventions, operator mapping, library remapping (e.g. `clausal.logic.clpfd` -> `library(clpz)`). The `Dialect.trealla()` configuration handles Trealla-specific differences automatically.

---

## Comparison with Scryer embedding

Both Trealla and [Scryer](scryer.md) are ISO-conformant Prolog engines embedded in clausal. They share the same Python API, so code written against one is portable to the other.

### API compatibility

| Method | Trealla | Scryer | Notes |
|---|---|---|---|
| `consult_string(source, module="user")` | yes | yes | Trealla ignores `module` |
| `load_string(source, module="user")` | yes | yes | Trealla ignores `module` |
| `consult_file(path, module="user")` | yes | yes | Trealla ignores `module` |
| `consult_clausal(source, module="user")` | yes | yes | Trealla ignores `module` |
| `query(goal)` | lazy iterator | lazy iterator | both truly lazy |
| `query_all(goal)` | `list[dict]` | `list[dict]` | |
| `query_one(goal)` | `dict \| None` | `dict \| None` | |
| `query_bool(goal)` | `bool` | `bool` | |
| `close()` | yes | yes | |
| context manager | yes | yes | |
| `AVAILABLE` | yes | yes | |
| `to_prolog()` | yes | yes | |
| error type | `TreallaError` | `ScryerError` | |

Switching between backends is a one-line change:

```python
# from clausal.scryer import Scryer as Engine
from clausal.trealla import Trealla as Engine

with Engine() as e:
    e.load_string("parent(tom, bob).")
    print(e.query_one("parent(tom, X)."))
```

### Implementation differences

| Aspect | Trealla | Scryer |
|---|---|---|
| Language | C (ctypes) | Rust (PyO3) |
| Build | `make` + `cc -shared` | `maturin develop --release` |
| Startup | instant | ~200ms |
| Memory | ~5MB | ~100MB |
| Session isolation | singleton (shared state) | independent per `Scryer()` |
| Query protocol | stdout capture + `pl_query`/`pl_redo` | Rust API (`QueryState::next`) |
| Lazy iteration | yes (`pl_query`/`pl_redo`) | yes (Rust iterator) |
| One query at a time | no restriction | enforced (machine lock) |
| Thread safety | not thread-safe | not thread-safe |
| Module parameter | accepted, ignored | fully supported |
| Tabling | not available | yes |
| CLP(Z) | yes (Triska's library) | yes (Triska's library) |
| CLP(B) | no | yes |
| Rational numbers | no | yes (`fractions.Fraction`) |

Choose **Trealla** for speed and simplicity. Choose **Scryer** for session isolation, tabling, rational numbers, and strict ISO conformance.

---

## Error handling

Prolog errors and exceptions become Python `TreallaError` exceptions:

```python
from clausal.trealla import Trealla, TreallaError

try:
    t.query_all("X is foo.")
except TreallaError as e:
    print(e)
    # Prolog error: error(type_error(evaluable,foo/0),(is)/2).
```

---

## Limitations

- **Singleton machine.** All `Trealla` sessions in a process share one interpreter instance. Facts loaded in one session are visible in others.
- **Not thread-safe.** Trealla uses global state internally. Do not share sessions across threads.
- **No tabling.** Trealla does not have a tabling library. For tabled predicates, use Scryer or the native engine.
- **stdout capture.** The ctypes embedding captures stdout to read Prolog output. While a query is running, stdout from other Python code may be captured too. Each query restores stdout immediately after.
