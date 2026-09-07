# Python Integration

Clausal and Python work together seamlessly. From `.clausal` files, use `++()` to call any Python expression. From Python code, use `query()` to run logic programs and collect results.

---

## `++()` — Python Escape

The `++()` operator evaluates an arbitrary Python expression at search time with logic variables automatically dereferenced.

### As a Value

Use `++expr` on the right side of `==` or `is` to compute a Python value:

```clausal
list_len(L, N) <- (N is ++len(L))
to_upper(S, R) <- (R is ++S.upper())
inc(X, R) <- (R is ++(X + 1))
first(L, R) <- (R is ++L[0])
get_key(D, K, R) <- (R is ++D[K])
join_words(W, R) <- (R is ++", ".join(W))
double_all(L, R) <- (R is ++[x*2 for x in L])
```

Any valid Python expression works: function calls, method calls, subscripts, comprehensions, arithmetic.

### As a Goal

Use `++expr` as a standalone goal for side effects:

```clausal
show(X) <- ++print(X)
```

when used as a goal, `++()` always succeeds once.

### Multiple Variables

All logic variables in the expression are dereferenced before evaluation:

```clausal
add_len(A, B, R) <- (R is ++(len(A) + len(B)))
```

### Per-Solution Evaluation

`PyThunk` values are evaluated fresh for each solution during backtracking:

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:python_escape_example"
```

---

## `--` — The Seam: Python Speaks Terms

`++()` escapes from Clausal to Python. `--` is the escape in the other direction:
inside Python code hosted by a `.clausal` file (a function body, a module-level
assignment), `--term` yields the runtime **term** — the same tuple the engine
builds for that source in a clause — at the point of execution.

```clausal
-module(oracle, [verdict(STATUS, IDS, CITATIONS)])
-double_quotes(chars)
-import_from(rulebase, [decide])

def expected(status, ids, cites):
    return --verdict(++status, ++ids, ++cites)      # ('verdict', status, ids, cites)

GOLD = --verdict(permitted, ["r1"], [])              # ('verdict', ('permitted',), ['r1'], [])
```

Inside `--` the grammar is Clausal's, under the host module's own rules:

- a **bare name** is the atom the module declares or imports (`permitted` →
  `('permitted',)`); an undeclared one is the usual strict-atoms error, or is
  minted under `-implicit_atoms`;
- an **ALL-CAPS or `_leading` name** is a fresh logic variable, shared within
  the one `--` expression;
- `'...'` is an atom in every mode; `"..."` follows the module's
  `-double_quotes` mode — declare it explicitly, because under the engine
  default `atom` a `"..."` a Python author reads as a string is an atom (the
  seam warns once per literal when the module never chose);
- a **functor** must be declared, imported, or opened with `-implicit_functors`;
  it builds the cell, functor first, positional arguments filling the declared
  slots and keywords their named slots; a predicate name builds the same cell,
  which `call/N` runs as a goal — no class instance is ever minted;
- a **Python value** enters only through `++expr`, evaluated at once; seams
  nest to any depth (`--outer(++[--inner(++x) for x in xs])`);
- ground **arithmetic** is a value, as in a clause body (`--f(1 + 2)` is
  `('f', 3)`); `foo()` is not a term — the atom is `foo`.

Outside `--`, the hosting Python is untouched: its strings are `str`, its
names are Python names. `~~expr` is unrelated: it yields Python `ast` nodes.

### Text crossings: `str(x)` and `f"{x}"`

Going the other way — an engine answer reaching Python **text** — the two
places Python makes text explicitly are rewritten to an atom-aware helper:
`str(x)` and an f-string's `{x}` (also `{x!s}`, with or without a format
spec) give an atom's **spelling**, and plain `str` for anything else. Without
this, `str(answer)` on the atom `('ok',)` is the tuple repr `"('ok',)"`, and a
comparison against text scores a wrong answer with no error. The rewrite is
skipped in a file that binds `str` itself. It covers only those explicit
forms: `%s`, `.format`, `print`, `json.dumps` and container reprs still show
the cell — call `spelling()` there, or better, lift the text side to a term
with `mint()` and compare terms.

Two cautions. The rewrite fires **only** in Python hosted by a `.clausal`
file; a plain `.py` module never gets it, so verify it from a host or you
will measure the wrong thing. And it is for display and serialization, not
for an oracle's comparison: `str(atom) == str(text)` is `True` for a domain
that wrongly returns the string where the atom belongs, so a text-space
comparison can no longer see that class of wrong answer. Compare terms.

### Goal position: `if --goal`, `for ... in --goal`

A term in goal position is called. Goal positions are exactly: the test of
`if`/`elif`/`while`, the iterable of `for`, and `not` inside those tests.

```clausal
if --(verdict(S, IDS, _) is ++answer):      # unify once; S, IDS become locals
    use(S, IDS)
for S, IDS in --decide(++profile, verdict(S, IDS, _)):   # every solution
    use(S, IDS)
if not --decide(++profile, _):               # failure test; exports nothing
    ...
while --next(++cur, N):                      # re-run each iteration
    cur = N
```

Exported names are ordinary locals: on success they survive the block; on
failure nothing is assigned (a later read is an `UnboundLocalError`). A
`for` exports exactly its target names, which must be variables of the goal.
Values are copies; two seams never share a variable — goals that must share
one go in one seam as a conjunction. The sugar is strict: a WFS-conditional
answer raises `UndefinedAnswer` (use `query_wfs`), and an export that is
unbound and constrained raises `ResidualConstraints` (keep the store with an
explicit `Trail`, or ask for the residue inside the goal). Everywhere else
`--` is still the term.

## Crossing the boundary: atoms out, strings back

There are **two** outbound conversions, and which one a boundary gets is a
decided trade rather than an accident.

`clausal.logic.to_python.to_python` is the **deep** one, and every `py.*`
wrapper argument goes through it:

| Term | What the Python callee sees |
|---|---|
| atom `bar` (the cell `("bar",)`) | the `str` `'bar'` — its spelling |
| string `"bar"` | the `str` `'bar'` |
| a partial string that has become ground | the `str` it walks to |
| compound cell `foo(bar, 1)` | the tuple `('foo', 'bar', 1)` (converted elementwise) |
| list `[bar, 1]` | `['bar', 1]` |
| `DictTerm` / dict | a `dict`, **keys converted too** — an atom key becomes a `str` key |
| anything else | itself |

`clausal.logic.to_python.unwrap_atom` is the **top-level** one, and it is what
a `++` escape or an f-string argument gets: it unwraps an atom **argument** to
its spelling and hands everything else over as it stands.

| Term at a `++` / f-string argument | What the Python expression sees |
|---|---|
| atom `bar` (the cell `("bar",)`) | the `str` `'bar'` — its spelling |
| anything else, **including containers** | itself, unconverted |

So a nested atom crosses **raw**: `++len(L)` on `L = [bar, baz]` sees
`[('bar',), ('baz',)]`, not `['bar', 'baz']`, and a `DictTerm` argument arrives
as a `DictTerm`. When you want the deep conversion at a `++`, ask for it by
name — `from clausal.modules.py._helpers import to_python` in the Python module
you are escaping into, and call it on the argument there.

Why the asymmetry: a `py.*` call crosses a bounded argument list into a
foreign library that cannot read engine terms at all, and pays for the walk
once. A `++` escape is inline in a clause body, runs in the inner loop, and is
written by someone who can see exactly what they are passing — and the walk
cost 7.4 % of a `++`-heavy benchmark against a 3 % bar (the design's §9.1
recorded this fallback in advance; it was applied 2026-09-07 on the measurement).

Inbound is deliberately **not** symmetric: a Python `str` coming back is a
**string**, never the atom that went out. So

```clausal
-double_quotes(chars)
-private([bar])

round_trip(X, Y) <- (Y is ++X)

Test("an atom crosses out as text and comes back as a string") <- (
    round_trip(bar, Y),
    string(Y),
    Y is "bar",
    not (Y is bar)
)
```

That is the ISO/Scryer rule — foreign text is a string — and it is loud on
purpose: a program that silently treated a file line as a symbol was relying
on the two kinds being confused. A program that needs an atom back **mints
one**: `atom_chars(A, Text)` in Clausal, or `mint(text)` in Python.

### The Python atom API

```python
from clausal.logic.atoms import mint, is_atom, spelling, char_atom

mint("bar")            # → ('bar',)   the canonical atom for a spelling
is_atom(("bar",))      # → True       the term test
spelling(("bar",))     # → 'bar'      TypeError if not an atom
char_atom("a")         # → ('a',)     the one-character atom
```

Write new Python-side atom handling against these four names rather than
against the tuple shape. Compare atoms with `==`, **never** with `is`:
`mint` returns a fresh (equal) tuple each call, and a compiler-emitted atom
constant unmarshalled from a `.pyc` is a different object again.

A module attribute for a declared atom is that cell:

```python
import my_module
from clausal.logic.atoms import mint

my_module.bar == mint("bar")      # True
my_module.bar                     # ('bar',)
```

### What the `py.*` wrappers accept and answer

- **Text arguments** (a path, a URL, a header name, an environment variable
  name, a regex) accept an **atom or a string** — both convert to the same
  `str`, so `read_file('/tmp/x', T)` and `read_file("/tmp/x", T)` reach the
  library identically.
- **Text results** (a file line, an environment value, a regex group, a
  header value, a JSON string value) are **strings**.
- **Result dicts** built by a wrapper — `py.process`'s
  `exit_code`/`stdout`/`stderr`, `py.url.parse/2`'s
  `scheme`/`host`/`port`/`path`, `py.csv`'s header cells, `py.json.parse/2`'s
  object keys — are keyed by **atoms**, which is what makes `R.stdout` and
  `get(R, stdout, V)` work.

!!! note "Interpolated containers are terms, not converted Python"
    The thunk path unwraps a **top-level** atom only, so an interpolated
    container reaches `format()` as the engine term it is — `f"{D}"` on a dict
    `D = {a: 1}` renders that `DictTerm`'s own `__format__`/`repr`, with the
    key still the cell `('a',)`. For a rendering you control, ask for one:
    `term_to_string(D, S)` (or `print_term/1`), then interpolate `S`.

---

## Querying from Python

### Direct iteration — the simplest way

> Legacy surface: iterating a predicate class instance predates the cell
> representation. New code uses goal-position `--` above.

Predicate term instances are directly iterable.  Each iteration yields the
`Trail` after a solution — read bindings via `Var.value`, `int()`, `float()`,
or `str()`:

```python
from clausal import Var
from fibonacci import Fib

for trail in Fib(10, F := Var()):
    print(F.value)  # 55
```

The module is inferred automatically from the predicate class.  No `solve` or
`deref` import needed.

`Var` objects support Python coercion:

| Access | Behaviour |
|--------|-----------|
| `X.value` | Dereferenced value (Var if still unbound) |
| `str(X)` | String of dereferenced value (`_N` if unbound) |
| `int(X)` | Integer coercion (raises `UnboundVarCoercionError` if unbound) |
| `float(X)` | Float coercion (raises `UnboundVarCoercionError` if unbound) |
| `bool(X)` | Bool coercion (raises `UnboundVarCoercionError` if unbound) |
| `f"{X}"` | F-string auto-deref |

### `solve` — iterate with explicit module

Use `solve` when you need to pass the module explicitly or when working with
non-predicate goal terms:

```python
from clausal import Var, solve
from fibonacci import Fib

for trail in solve(Fib(10, F := Var())):
    print(F.value)  # 55
```

You can pass the module explicitly (as an imported Python module or a `Module`
object):

```python
import fibonacci
for trail in solve(Fib(10, F := Var()), fibonacci):
    print(F.value)
```

### `once` — first solution only

```python
from clausal import Var, once
from fibonacci import Fib

trail = once(Fib(10, F := Var()))
if trail is not None:
    print(F.value)  # 55
```

Returns the `Trail` for the first solution, or `None` if the goal fails.

### `call` — drive a named predicate by string

Lowest-overhead path — dispatches directly to the compiled function:

```python
from clausal import Var, call
import fibonacci

for trail in call("Fib", 7, N := Var(), module=fibonacci):
    print(N.value)
```

### `query` — collect binding dicts (deprecated)

!!! warning "Deprecated"
    `query()` is deprecated.  Iterate the goal directly and use `Var.value`:
    `for trail in pred(X := Var()): print(X.value)`

```python
from clausal import Var, query
from fibonacci import Fib

F = Var()
for bindings in query(Fib(10, F), {"F": F}):
    print(bindings)  # {"F": 55}
```

---

## Python Objects as Terms

Any Python object works as a ground term. The C `unify` function (see [Architecture](architecture.md)) handles non-Var objects via Python's `==`:

```python
import datetime as dt
from clausal.logic.variables import Var, Trail, unify, deref

trail = Trail()
v = Var()
unify(v, dt.date(2026, 3, 16), trail)
deref(v)  # → datetime.date(2026, 3, 16)
```

This means `datetime`, `Decimal`, `pathlib.Path`, and any other Python type with `__eq__` works as a logic term without wrapping. `datetime.date`, naive `datetime`/`time`, and `timedelta` are also accepted directly as **query arguments** — `solve(m.same_day(date(2024, 1, 1), X))` just works, both as direct arguments and nested inside list/compound arguments — no `[Y, M, D]` triple encoding needed on the Python-interop path. Call methods via `++()`:

```clausal
-import_from(date_time, [date])

IsoDate(Y, M, D, S) <- (
    date(Y, M, D, DT),
    S is ++DT.isoformat()
)
```

---

## Using `Module` Directly

For tests or programmatic use without the [import hook](import.md):

```python
from clausal.logic.database import Module, Clause
from clausal.logic.predicate import make_predicate
from clausal.logic.compiler import compile_predicate
from clausal.logic.variables import Var

fib = make_predicate("fib", ["n", "result"])
fib._assertz(Clause(head=fib(n=Var(), result=Var()), body=[True]))
compile_predicate("fib", 2, fib._clauses, pred_cls=fib)

mod = Module("test", module_dict={"fib": fib})
```

---

??? abstract "Low-Level API Details"

    ### The Trail

    The `Trail` (from `clausal.logic.variables`, a C extension) records variable bindings for backtracking:

    ```python
    from clausal.logic.variables import Trail, Var, unify, deref

    trail = Trail()
    mark = trail.mark()
    v = Var()
    unify(v, 42, trail)   # binds v → 42
    deref(v)              # → 42
    trail.undo(mark)      # undoes the binding
    deref(v)              # → v  (unbound again)
    ```

    ### Custom Undo Callbacks

    `trail.record(callable)` pushes a no-arg callable for backtrackable mutations:

    ```python
    d = {}
    _ABSENT = object()

    def trailed_put(key, value, trail):
        old = d.get(key, _ABSENT)
        def undo():
            if old is _ABSENT:
                d.pop(key, None)
            else:
                d[key] = old
        trail.record(undo)
        d[key] = value
    ```

    ### Dispatch Lookup Order

    `call(functor, *args, module)` resolves predicates in this order:

    1. `module.module_dict[functor]._get_dispatch()` — PredicateMeta class from module globals
    2. `get_builtin_predicate(functor, arity, db)._get_dispatch()` — builtin predicates
    3. `module.db.get_dispatch(functor, arity)` — Database fallback

    ### `structural_unify`

    `clausal.logic.builtins.structural_unify(t1, t2, trail)` is a Python-level recursive unifier for `Compound`, `KWTerm`, PredicateMeta instances, and `@dataclass` instances. The C `unify` handles `Var` binding, tuples, lists, and atomic equality.

    ### Term Dereferencing

    `deref(var)` unwraps one level. For full recursive dereferencing:

    ```python
    from clausal.logic.solve import _deref_walk

    _deref_walk(term)  # recursively dereferences Compound, lists, etc.
    ```

    ### Builtin Predicate Classes

    Every builtin has a constructable `PredicateMeta` class:

    ```python
    from clausal.logic.builtins import get_builtin_class

    append = get_builtin_class("append")
    t = append([1, 2], [3], Var())   # → append(l1=[1, 2], l2=[3], l3=Var())
    ```

    Multi-arity builtins (`maplist`, `phrase`) use `MultiArityBuiltin`.

    ### assertz/retract from Python

    when called from a `.clausal` module, these builtins:

    1. Check that the target predicate is not locked (see [Directives](directives.md) for `-dynamic`)
    2. assertz/retract the clause on the [Database](database_ops.md)
    3. Look up the PredicateMeta class from `db.module_dict`
    4. Sync `pred_cls._clauses` with the database
    5. Recompile with module globals

    ### `++()` Implementation

    The `++` syntax is detected by `visit_UnaryOp` in `term_rewriting.py` as `UAdd(UAdd(expr))`. The compiler emits a `_pyt_<id>(deref(...))` call wrapping the expression in a `PyThunk` lambda.

---

*See also: [I/O](io.md) — write, writeln, f-strings for formatted output.*
*See also: [Predicates](predicates.md) — defining predicates in `.clausal` files.*
