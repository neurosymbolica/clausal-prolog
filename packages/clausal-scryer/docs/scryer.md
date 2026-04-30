# Scryer Prolog Embedding

Clausal includes an embedded [Scryer Prolog](https://github.com/mthom/scryer-prolog) engine via a PyO3/Rust extension. This gives you an in-process, ISO-conformant Prolog engine that you can load `.clausal` or `.pl` programs into and query with lazy iteration.

## About Scryer Prolog

[Scryer Prolog](https://www.scryer.pl) is a modern Prolog implementation written in Rust, designed from the ground up for ISO conformance and correctness. Where many Prolog systems treat the ISO standard as a rough guide, Scryer takes it seriously — it is one of the most standards-compliant Prolog implementations available, and the developers actively participate in standards work.

Scryer is built on a proper WAM (Warren Abstract Machine) with a focus on getting the foundations right: sound unification, correct arithmetic, first-class constraints (CLP(Z), CLP(B)), tabling, and a clean library ecosystem. It supports features like rational trees, attributed variables, and well-founded semantics out of the box.

By embedding Scryer in-process, clausal gives you access to a production-quality ISO Prolog engine alongside the native Python-integrated engine — the best of both worlds.

---

## when to use Scryer vs the native engine

Clausal's **native engine** is tightly integrated with Python: predicates are Python classes, variables are Python objects, unification and backtracking use Python's own runtime. This is the right choice for most programs.

The **Scryer embedding** is for when you need:

- **ISO Prolog conformance** — correct semantics for arithmetic, unification, error handling, and the full ISO built-in repertoire
- **Constraint solving** — CLP(Z) for integer constraints, CLP(B) for Boolean satisfiability, all built in
- **Scryer's library ecosystem** — tabling, DCGs, `library(lists)`, `library(between)`, `library(assoc)`, and more
- **Validation** — run the same program on both engines to cross-check results

The two engines are separate worlds connected by Clausal's translation pipeline. You cannot unify a native Clausal `Var` with a Scryer variable directly.

!!! note "Scryer embedding vs `.pl` import"

    Clausal offers two ways to run Prolog code:

    - **[Importing `.pl` files](importing_prolog.md)** translates Prolog to Clausal syntax and runs it on the native engine. Predicates become `PredicateMeta` classes, fully integrated with Python. Best for most programs.
    - **Scryer embedding** (this page) runs Prolog on an actual ISO Prolog engine in-process. Best when you need Scryer's native constraint solvers, its library ecosystem, or strict ISO conformance.
    - **[Trealla embedding](trealla.md)** is a lighter-weight alternative — faster startup, smaller footprint, but no tabling.

    All three approaches can coexist in the same project.

---

## Building the extension

The Scryer embedding requires a Rust toolchain and the `scryer-prolog` source:

```bash
# Install Rust (if needed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build the extension (first build compiles scryer-prolog — takes a few minutes)
cd prolog_backends/scryer
maturin develop --release
```

After building, verify:

```python
from clausal.scryer import AVAILABLE
print(AVAILABLE)  # True
```

If `AVAILABLE` is `False`, the extension is not built. The rest of clausal works normally without it.

---

## Quick start

```python
from clausal.scryer import Scryer

with Scryer() as s:
    s.load_string("parent(tom, bob). parent(bob, ann).")

    for sol in s.query("parent(X, Y)."):
        print(f"{sol['X']} -> {sol['Y']}")
    # tom -> bob
    # bob -> ann
```

---

## Creating a session

```python
from clausal.scryer import Scryer

s = Scryer()
```

`Scryer()` creates a new Scryer Prolog machine. This takes ~200ms (bootstrapping the standard library) and uses ~100MB of memory. **Create once, reuse across many queries.**

The session supports the context manager protocol:

```python
with Scryer() as s:
    s.load_string("fact(1).")
    # ... queries ...
# machine released on exit
```

After `close()` or exiting the `with` block, any further use raises `RuntimeError`.

---

## Loading programs

### Prolog source

```python
s.consult_string("parent(tom, bob). parent(bob, ann).")
```

`consult_string` uses Scryer's full `consult` path. Standard Prolog semantics apply: consulting the same predicate again **replaces** earlier clauses.

`load_string` uses a simpler loading path but also replaces earlier clauses for the same predicate.

For true clause accumulation, declare predicates as `:- dynamic` and use `assertz`:

```python
s.consult_string(":- dynamic(likes/2).")
list(s.query("assertz(likes(alice, bob))."))
list(s.query("assertz(likes(bob, carol))."))
s.query_all("likes(X, Y).")
# [{'X': 'alice', 'Y': 'bob'}, {'X': 'bob', 'Y': 'carol'}]
```

### Clausal source

```python
s.consult_clausal("""
    Edge(1, 2),
    Edge(2, 3),
    Edge(3, 4),
    Reach(X, Y) <- Edge(X, Y)
    Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
""")

s.query_all("reach(1, X).")
# [{'X': 2}, {'X': 3}, {'X': 4}]
```

`consult_clausal` translates the `.clausal` source to Prolog via `clausal_source_to_prolog` with the Scryer dialect, then loads it. All the usual translation rules apply: `PascalCase` becomes `snake_case`, `:=` becomes `is`, `<=` becomes `=<`, etc.

### Files

```python
s.consult_file("clausal/examples/fibonacci.clausal")
s.query_one("fib(10, R).")
# {'R': 55}

s.consult_file("my_library.pl")
```

`consult_file` auto-detects the file extension: `.clausal` files are translated; `.pl` files are loaded as raw Prolog. Module declarations (`:- module(...)`) in translated `.clausal` files are stripped so predicates land in the `user` module.

---

## Querying

### Lazy iteration

```python
for sol in s.query("color(X)."):
    print(sol["X"])
```

`query()` returns a **lazy iterator**. Each call to `next()` resumes Prolog backtracking for one more solution. You can break out of the loop early — the iterator cleans up automatically.

While an iterator is alive, the machine is exclusively held by it. Attempting to load code or start another query raises `ScryerError` with a clear message. The iterator can be closed explicitly:

```python
it = s.query("color(X).")
first = next(it)
it.close()  # return the machine immediately
# now s is usable again
```

### Convenience methods

```python
# First solution only (stops after 1)
s.query_one("parent(tom, X).")
# {'X': 'bob'}  or  None

# All solutions as a list
s.query_all("color(X).")
# [{'X': 'red'}, {'X': 'green'}, {'X': 'blue'}]

# Success/failure check (stops after 1)
s.query_bool("parent(tom, bob).")
# True
```

### Solution format

Each solution is a `dict` mapping Prolog variable names (strings) to Python values:

| Prolog term | Python type |
|---|---|
| integer | `int` (arbitrary precision) |
| rational | `fractions.Fraction` |
| float | `float` |
| atom | `str` |
| string (char list) | `str` |
| list | `list` |
| compound `f(a, b)` | `Compound("f", (a, b))` from `clausal.terms` |
| unbound variable | `str` (the variable name) |

Ground goals that succeed with no variables return `{}` (empty dict).

---

## Building query strings from Python values

Use `to_prolog()` to safely embed Python values into Prolog query text:

```python
from clausal.scryer import Scryer, to_prolog

with Scryer() as s:
    s.load_string("member_check(X, L) :- member(X, L).")
    s.consult_string(":- use_module(library(lists)).")
    items = [1, 2, 3]
    s.query_bool(f"member_check(2, {to_prolog(items)}).")
    # True
```

`to_prolog` handles `int`, `float`, `str` (quoted as atoms), `bool`, `None` (→ `[]`), `list`, and `Compound`.

---

## Using Scryer's libraries

Scryer Prolog has a rich standard library. Load modules with `:- use_module`:

```python
with Scryer() as s:
    s.consult_string(":- use_module(library(lists)).")
    s.consult_string(":- use_module(library(between)).")
    s.load_string("nums(L) :- numlist(1, 5, L).")
    s.query_one("nums(L).")
    # {'L': [1, 2, 3, 4, 5]}
```

Common Scryer libraries:

| Library | Contents |
|---|---|
| `library(lists)` | `member/2`, `append/3`, `length/2`, `nth0/3`, `msort/2`, `permutation/2` |
| `library(between)` | `between/3`, `numlist/3` |
| `library(clpz)` | CLP(Z) — constraints over integers |
| `library(clpb)` | CLP(B) — Boolean constraint solving |
| `library(dcgs)` | Definite Clause Grammars |
| `library(tabling)` | Tabling / memoization for recursive predicates |
| `library(assoc)` | Association lists (balanced binary trees) |
| `library(dif)` | `dif/2` — sound disequality |

---

## Error handling

Prolog errors and exceptions become Python `ScryerError` exceptions:

```python
import _scryer_ext

try:
    s.query_all("X is foo.")
except _scryer_ext.ScryerError as e:
    print(e)
    # Prolog error: Compound("error", [Compound("type_error", ...)])
```

---

## Relationship to the Prolog translation pipeline

The Scryer embedding sits on top of Clausal's existing [Prolog translation](prolog_translation.md) infrastructure:

```
.clausal source → clausal_source_to_prolog(dialect=Scryer) → Prolog text → Scryer machine
```

All translation features work: naming conventions, operator mapping, library remapping (e.g. `clausal.logic.clpfd` → `library(clpz)`), tabling directives. The `Dialect.scryer()` configuration handles Scryer-specific differences automatically.

---

## Comparison with Trealla embedding

Both Scryer and [Trealla](trealla.md) are ISO-conformant Prolog engines embedded in clausal. They share the same Python API, so code written against one is portable to the other.

### API compatibility

| Method | Scryer | Trealla | Notes |
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
| error type | `ScryerError` | `TreallaError` | |

Switching between backends is a one-line change:

```python
# from clausal.trealla import Trealla as Engine
from clausal.scryer import Scryer as Engine

with Engine() as e:
    e.load_string("parent(tom, bob).")
    print(e.query_one("parent(tom, X)."))
```

### Implementation differences

| Aspect | Scryer | Trealla |
|---|---|---|
| Language | Rust (PyO3) | C (ctypes) |
| Build | `maturin develop --release` | `make` + `cc -shared` |
| Startup | ~200ms | instant |
| Memory | ~100MB | ~5MB |
| Session isolation | independent per `Scryer()` | singleton (shared state) |
| Query protocol | Rust API (`QueryState::next`) | stdout capture + `pl_query`/`pl_redo` |
| One query at a time | enforced (machine lock) | no restriction |
| Module parameter | fully supported | accepted, ignored |
| Tabling | yes | not available |
| CLP(B) | yes | no |
| Rational numbers | yes (`fractions.Fraction`) | no |

Choose **Scryer** for session isolation, tabling, rational numbers, and strict ISO conformance. Choose **Trealla** for speed and simplicity.

---

## Limitations

- **Machine is not thread-safe.** Scryer's `Machine` uses `Rc<>` internally and must stay on one thread. Under Python's free-threading mode (3.13+), do not share a `Scryer` session across threads.
- **One query at a time.** While iterating over solutions, no other operations on the session are possible. Close or exhaust the iterator first.
- **No live state bridge.** You cannot share logic variables between the native Clausal engine and Scryer. They are separate runtimes.
- **Bootstrap cost.** Each `Scryer()` takes ~200ms to create. Reuse sessions rather than creating per-query.
- **`consult` replaces clauses.** Both `consult_string` and `load_string` replace earlier clauses for the same predicate. Use `:- dynamic` and `assertz/1` for accumulation.
