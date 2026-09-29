# Python Integration

Clausal and Python meet at two seams, one for each direction:

- **`--term`** — Python speaks terms. In Python code hosted by a `.clausal`
  or `.seam` file, `--goal` in goal position (`if`, `for`, `while`) **runs**
  the goal and hands back its answers; anywhere else it builds the term.
- **`++expr`** — Clausal calls Python. Inside a clause (or inside a `--`
  term), `++expr` evaluates a Python expression and passes its value in.

Nothing is converted at either seam unless you ask: an answer is the engine's
own term, and [`to_python`](#the-converters-to_python-to_clausal-term_key)
turns it into Python values. From a plain `.py` file, where `--` is not
available, build a goal cell and run it with [`solve()`](#from-a-plain-py-file-solve-once-call).

---

## Querying from Python

### In a `.seam` file: `--goal`

Write the Python that asks questions in a `.seam` file (`.clausal` is the
same format; the two suffixes are aliases). It is ordinary Python plus
Clausal terms, and a term in goal position is a query:

```clausal
# report.seam
-import_from(clausal.examples.fibonacci, [fib])

def fib_of(n):
    if --fib(++n, F):              # first answer; F becomes a local
        return F

def fib_table(n):                  # every answer of a conjunction
    return [(N, F) for N, F in --(between(0, ++n, N), fib(N, F))]
```

```python
import clausal          # installs the import hook for .clausal/.seam files
import report

print(report.fib_of(10))      # 55
print(report.fib_table(4))    # [(0, 0), (1, 1), (2, 1), (3, 2), (4, 3)]
```

Inside `--` the grammar is Clausal's: an ALL-CAPS name is a logic variable,
a bare name is an atom or a predicate, `++n` passes the Python value of `n`
in. `if --g:` runs `g` for its first answer, `for X in --g:` iterates every
answer, and the goal's variables come back as ordinary Python locals. A
predicate in another module is reached with `-import_from(m, [pred])` as
above, or with `-import_module(m)` and the dotted form `--m.pred(X)`:

```clausal
-import_module(clausal.examples.fibonacci)

def fib_10():
    for F in --clausal.examples.fibonacci.fib(10, F):
        return F
```

What comes back is the **raw term**: an atom is a Python `str`, a string is
the carrier `('$chars', text)`, a compound is its cell tuple. Compare it
against a `--` term, or convert it with `to_python`. The full rules — goal
positions, exports, undefined and constrained answers, the lints — are in
[Goal position](#goal-position-if-goal-for-in-goal) below.

A top-level `--goal` over a predicate defined **in the same file** runs
while the file is still loading, before its clauses are compiled, so it
raises `existence_error(procedure, p/1)` with a message naming the file and
line and saying so. Put the query in a function called after the load, as
above, or query the predicate from another file that imports it.

### From a plain `.py` file: `solve`, `once`, `call`

A `.py` file cannot use `--`, and a goal built at runtime is data, not
source. Both use the lower-level API: a goal is a **cell** — a tuple whose
first element is the predicate's name and whose remaining elements are its
arguments — run against a **module**, the one whose database answers it.
Pass both, every time:

```python
from clausal import Var, solve
import fibonacci

for trail in solve(("fib", 10, F := Var()), module=fibonacci):
    print(F.value)  # 55
```

`module=` takes the imported `.clausal` module (as here), a `Module` object, or
the module's dotted name as a string. A cell does not carry a module of its
own, so `solve` without `module=` refuses an unqualified cell with an ISO
`existence_error(module, …)` rather than guessing where the predicate lives.

!!! warning "A module attribute is a handle, not something to call"
    `fibonacci.fib` is the predicate's **handle** — a `str` naming the module
    that owns it and the predicate — so `fibonacci.fib(10, F)` raises
    `TypeError: 'str' object is not callable`. Build the cell and pass the
    module instead, or query from a `.seam` file with `--`.

`Var` objects support Python coercion:

| Access | Behaviour |
|--------|-----------|
| `X.value` | Dereferenced value (Var if still unbound) |
| `str(X)` | String of dereferenced value (`_N` if unbound) |
| `int(X)` | Integer coercion (raises `UnboundVarCoercionError` if unbound) |
| `float(X)` | Float coercion (raises `UnboundVarCoercionError` if unbound) |
| `bool(X)` | Bool coercion (raises `UnboundVarCoercionError` if unbound) |
| `f"{X}"` | F-string auto-deref |

Read a binding **inside** the loop: each iteration yields the `Trail` with that
solution's bindings live, and they are undone before the next one.

### `once` — first solution only

```python
from clausal import Var, once
import fibonacci

trail = once(("fib", 10, F := Var()), module=fibonacci)
if trail is not None:
    print(F.value)  # 55
```

Returns the `Trail` for the first solution, or `None` if the goal fails.

### `call` — drive a named predicate directly

`call` takes the predicate name and its arguments separately and hands them
straight to the compiled dispatch function, skipping the goal compilation
`solve` does. It is the lowest-overhead path for calling one predicate many
times:

```python
from clausal import Var, call
import fibonacci

for trail in call("fib", 7, N := Var(), module=fibonacci):
    print(N.value)  # 13
```

### Driving Clausal from a test suite

Plain-Python code that runs many goals — a pytest suite around a rulebase,
a script that checks answers in bulk — should build every goal through **one
helper function of its own**, not by writing raw tuples at each call site
(in a `.seam` file, the `--` goal already names its predicate at the site):

```python
from clausal import Var, solve
import fibonacci

def answers(name, *args):
    """The one place this suite builds a goal and names its module."""
    return solve((name, *args), module=fibonacci)

def test_fib_10():
    F = Var()
    assert [F.value for _ in answers("fib", 10, F)] == [55]
```

The goal's shape and the module it runs against are then decided in exactly
one place: a change to either is one edit, and a call site cannot quietly
drift to a different module or a malformed goal.

### `query` — collect binding dicts (deprecated)

!!! warning "Deprecated"
    `query()` is deprecated. Iterate `solve(...)` and read `Var.value` inside
    the loop, as above.

```python
from clausal import Var, query
import fibonacci

F = Var()
for bindings in query(("fib", 10, F), {"F": F}, fibonacci):
    print(bindings)  # {'F': 55}
```

---

## `++()` — Python Escape

The `++()` operator evaluates an arbitrary Python expression at search time with logic variables automatically dereferenced.

### As a Value

Use `++expr` as the value in a unification (`R is ++expr`) to compute a
Python value. The value enters **unconverted**: a Python `str` is an atom, an
`int` is an integer, any other object is itself.

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
inside Python code hosted by a `.clausal` or `.seam` file (a function body, a
module-level assignment), `--term` yields the runtime **term** — the same tuple
the engine builds for that source in a clause — at the point of execution. In
[goal position](#goal-position-if-goal-for-in-goal) it runs the term as a goal
instead.

```clausal
-module(shop, [order(STATUS, ITEMS, NOTES)])
-private([shipped])

def expected(status, items, notes):
    return --order(++status, ++items, ++notes)      # ('order', status, items, notes)

WANT = --order(shipped, ['a1'], [])              # ('order', 'shipped', ['a1'], [])
TEXT = --order(shipped, ["a1"], [])              # ('order', 'shipped', [('$chars', 'a1')], [])

expected("shipped", ["a1"], []) == WANT            # True
expected("shipped", ["a1"], []) == TEXT            # False
```

A Python `str` handed in through `++` is an **atom**, while `"a1"` written
inside `--` is a **string** (`"…"` is a string by default), so the expected
value spells the id `'a1'` (an atom in every mode) to compare equal with what
`expected` builds from Python text.

Inside `--` the grammar is Clausal's, under the host module's own rules:

- a **bare name** is the atom the module declares or imports (`permitted` →
  `'permitted'`, a plain `str`); an undeclared one is the usual strict-atoms error;
- an **ALL-CAPS or `_leading` name** is a fresh logic variable, shared within
  the one `--` expression;
- `'...'` is an atom; `"..."` is a string (the carrier `('$chars', text)`),
  as in Scryer and Trealla, unless the module declares the temporary
  `-double_quotes(atom)` setting;
- a **functor** must be declared, imported, or opened with `-implicit_functors`;
  it builds the cell, functor first, then the positional arguments (a keyword
  argument, `--point(x=1)`, is a `SyntaxError`); a predicate name builds the same cell,
  which `call/N` runs as a goal — no class instance is ever minted;
- a **Python value** enters only through `++expr`, evaluated at once; seams
  nest to any depth (`--outer(++[--inner(++x) for x in xs])`);
- ground **arithmetic** is a value, as in a clause body (`--f(1 + 2)` is
  `('f', 3)`); `foo()` is not a term — the atom is `foo`.

Outside `--`, the hosting Python is untouched: its strings are `str`, its
names are Python names. `~~expr` is unrelated: it yields Python `ast` nodes.

### Text crossings: `str(x)` and `f"{x}"`

Going the other way — an engine answer reaching Python **text** — the two
places Python makes text explicitly are rewritten to a term-aware helper:
`str(x)` and an f-string's `{x}` (also `{x!s}`, with or without a format
spec) give an atom's **spelling** (an atom is already that `str`), a
string's **text**, and plain `str` for anything else. A
format spec applies to the **value**: `f"{n:02d}"` on an int is `"06"` in a
hosted file exactly as in a plain one (a bare `{x}` spells an atom and passes
anything else unchanged to `format()`; `{x!s}` keeps Python's meaning, `str`
first, then the spec). Without
this, `str(answer)` on the string `"ok"` (the cell `('$chars', 'ok')`) is the
tuple repr `"('$chars', 'ok')"`, and a comparison against text accepts a wrong
answer with no error. The rewrite is skipped in a file that binds `str`
itself. It covers only those explicit forms: `%s`, `.format`, `print`,
`json.dumps` and container reprs still show the cell — convert there
explicitly, or better, lift the text side to a term with `mint()` and compare
terms.

Two cautions. The rewrite fires **only** in Python hosted by a `.clausal`
file; a plain `.py` module never gets it, so verify it from a host or you
will measure the wrong thing. And it is for display and serialization, not
for a checker's comparison: `str(atom) == str(text)` is `True` for a rulebase
that wrongly returns the string where the atom belongs, so a text-space
comparison can no longer see that class of wrong answer. Compare terms.

### Goal position: `if --goal`, `for ... in --goal`

A term in goal position is called. Goal positions are exactly: the test of
`if`/`elif`/`while`, the iterable of `for`, and `not` inside those tests.

```clausal
-module(orders, [])
-private([small, large, open, closed, a1, a2, state(S, IDS)])

status(small, state(open, [a1, a2])),
status(large, state(closed, [a1])),
status(large, state(closed, [a2])),
next_id(N, M) <- (N < 3, M == N + 1)

def first(size):
    if --status(++size, state(S, IDS)):          # first answer; S, IDS become locals
        return S, IDS

def every(size):
    return [(S, IDS) for S, IDS in --status(++size, state(S, IDS))]   # every answer

def missing(size):
    if not --status(++size, state(_, _)):         # failure test; exports nothing
        return True
    return False

def parts(answer):
    if --(state(S, IDS) is ++answer):             # unify once
        return S, IDS

def count_up():
    cur, seen = 0, []
    while --next_id(++cur, N):                    # re-run each iteration
        cur = N
        seen.append(N)
    return seen
```

`orders.first(large)` is `('closed', ['a1'])`, `orders.every(large)` is
`[('closed', ['a1']), ('closed', ['a2'])]`, and `count_up()` is `[1, 2, 3]`.

Exported names are ordinary locals: on success they survive the block; on
failure nothing is assigned (a later read is an `UnboundLocalError`). A
`for` exports exactly its target names, which must be variables of the goal.
Two seams never share a variable — goals that must share one go in one seam
as a conjunction. An export that is unbound and constrained raises
`ResidualConstraints` (keep the store with an explicit `Trail`, or ask for
the residue inside the goal). Everywhere else `--` is still the term.

**What comes out is the engine's own term** (the dumb seam, 2026-09-26).
An atom is the plain `str`, a string is the carrier `('$chars', text)`, a
compound is its cell, a dict is the `DictTerm` — nothing is walked or
converted. Compare an answer against a `--`-wrapped term, and ask for a
Python value by name:

```clausal
-module(rawout, [])
-private([ok, done, result(STATUS, TEXT, TAG)])
from clausal import to_python

answer(result(ok, "all good", done)),
txt("some text"),

def check():
    for V in --answer(V):
        print(V == --result(ok, "all good", done))   # True: the same term
        print(to_python(V))                          # ('result', 'ok', 'all good', 'done')
    for T in --txt(T):
        print(T == --"some text")                    # True: the same string term
        print(repr(T))                               # ('$chars', 'some text')
        print(to_python(T))                          # some text
```

A plain Python literal on the other side — `T == "some text"` — is **False**
for a string answer (a carrier is not a Python `str`) and True only for an
atom answer; the lint below warns at load wherever that is written.

An answer crosses **by identity** only when it is proven to hold no logic
variable at all — it is atomic, it is a constant the compiler baked into a
clause (a fact's cell, however large: `if --g(X, DOC)` over a stored cell
never walks `DOC`), or a bounded probe walked it completely and met none.
Anything else — a compound built from body variables, a large `++`-built
object — is deref-walked into a **copy** first, because a term holding a
variable would neither compare equal to its `--` literal nor survive
backtracking. Do not mutate what you are handed; it may be the engine's own
stored term.

**The lint.** Because `T == "x"` is silently False for a string answer and
silently True for an atom answer, a name bound by a goal-position seam that
meets a Python str **literal** in the same function — `==`, `!=`, `in` /
`not in` a literal list/tuple/set of str, a `match`/`case` str pattern, also
through a plain alias `y = T` — raises `ClausalSeamTextCompareWarning` at
load, naming the site and both right spellings (`T == --"x"`, or
`to_python(T) == "x"`). It does not catch `d[T]`, `T in some_dict`,
`json.dumps(T)`, `len(T)`, str methods, a comparison inside a helper or in
another function, or a container built at runtime: those follow the raw-out
contract above.

The same holds in a comprehension or generator expression whose FIRST
`for` clause is a `--` goal (`{K: V for K, V in --kv(K, V)}`), and for the
dotted runtime form `--m.pred(X)`.

A term is a non-empty tuple, so it is always true: `assert --edge(zzz, X)`,
`if --g and ready:`, `x if --g else y`, `bool(--g)`, `not --g` outside an
`if`/`while` test, and a comprehension's `if --g` filter never run the goal.
Each such site raises a `ClausalBooleanSeamWarning` at load; put the goal in
goal position, or, as an expression, write `any(True for X in --g)` with `X`
a variable of the goal.

`UndefinedAnswer` and `ResidualConstraints` are both importable from
`clausal.logic.seam`.

**How far the strictness reaches.** Everywhere. A WFS-conditional (undefined)
answer raises `UndefinedAnswer` (use `query_wfs` for truth values and delays)
whatever the goal's shape: a bare tabled call (`if --wins(a):`, `for X in
--wins(X):`), a conjunction (`if --(X is a, wins(X)):`), an untabled wrapper
(`if --p(a):` with `p(X) <- wins(X)`), a call fed through `++`
(`if --classify(++item, S, X):`), a negation delayed inside any clause
body on the way. The whole goal-position solve runs under one throwaway tabling
leader, so the judgement is exactly the delays the answer's own derivation
incurred, never reconstructed from a table key afterwards. Each answer is judged
on its own: a definite one is exported as soon as it is found; a conditional one
is held back until the search is exhausted and global resolution has run, then
raised (still undefined), exported (resolved true) or dropped (resolved false) —
the order a tabled root already delivers in. `query_wfs` judges by the same
core, so a composite goal now reports real `_truth`/`_delays` there too. The one
refusal: a `++` that reads a variable of the same goal in a single tabled call
(`if --wins(++len(X)):`) has no value before the search and raises a
`SyntaxError`. A `++` value is evaluated by the query exactly once.

"Each answer on its own" is meant strictly, and cuts BOTH ways: a branch that
delayed and then failed does not make the next answer undefined (conditions
are trailed and retracted with the branch's bindings), and an answer that has
ANY delay-free derivation is true — a definite clause alongside a conditional
one, or a table row that a later re-derivation settled unconditionally. Two
`--` loops alive at the same time keep their conditions apart: a suspended
judged goal holds no place on the tabling leader stack. See `docs/wfs.md`.

A module-level `--goal:` over a predicate defined in the same file fails
during that file's load — the Python body runs before the file's own
clauses are compiled. Over an imported predicate it works.

## The converters: `to_python`, `to_clausal`, `term_key`

Three names, exported from `clausal`, are the explicit conversions between a
term and a Python value. They are driven by ONE registry
(`clausal.logic.python_terms`: `TO_TERM` by exact Python type, `FROM_TERM` by
functor), so a class registered once — `register(cls, functor, to_fn,
from_fn)` — crosses in both directions.

```python
import datetime as dt
from clausal import to_python, to_clausal, term_key
from clausal.logic.cells import chars

to_clausal(dt.date(2023, 6, 1))        # ('date', 2023, 6, 1)   the term
to_python(("date", 2023, 6, 1))        # datetime.date(2023, 6, 1)
to_clausal((1, 2))                     # ('()', 1, 2)           tuple DATA cell
to_python(("()", 1, chars("t")))       # (1, 't')
to_python(("cite", "art52", chars("s")))   # ('cite', 'art52', 's')  unregistered: a tuple
to_clausal(object())                   # TypeError: no registered conversion
sorted([("f", 1), "a", 1], key=term_key)   # [1, 'a', ('f', 1)]  the standard order
```

**`to_python(term)` — deep OUT.** Every engine shape converts all the way
down: an atom is its `str`, a string (the chars carrier, a ground
`SegString`, an all-chars `SegList`) its text, a cell a tuple of converted
elements — unless its functor is registered, in which case the registered
rebuild answers (`('date', …)` is a `datetime.date`, `('()', …)` a Python
tuple; a look-alike whose components do not rebuild stays a cell). A
`SetTerm` is a `frozenset`; a `DictTerm` is a
`dict` with keys converted and normalised — an atom key and the string of its
spelling become **one** Python key. A non-ground `Seg*` crosses raw (there is
no text yet). This is what every `py.*` wrapper argument gets.

**`to_clausal(obj)` — deep IN.** `python_terms.to_term(strict=True)`: a `str`
is the atom (text is written `chars("…")`), a `Var` or engine term is left
alone, a registered type takes its shape, a list or dict converts its
contents, a tuple becomes the `('()', …)` data cell, and an unregistered class
**raises** `TypeError` naming the fix. The documented hazard: a tuple that
already spells a well-formed registered term — `("date", 2023, 6, 1)` — is
read as that term, not wrapped as data; wrap it yourself (`("()", *t)`) if you
meant data.

**`term_key(term)`** is the standard order of terms as a sort key: total over
every value a term can hold (a mixed list never raises), the same order
`msort/2`, `sort/2` and `compare/3` use. A `SegString`/`SegList`/`SegBytes`
keys as the string/list/code list it walks to — so `compare/3` answers `=`
for a ground `SegString` against its string, and `sort/2` keeps one of them;
one that still holds an unbound hole keys in an opaque band after everything
else.

`to_python` and `to_clausal` are NOT what `++`/`--` do. The seams have their
own, narrower rules — a `++` argument is unwrapped one level, a goal-position
`--` answer is exported (both below) — and you call a converter by name when
you want the whole value in the other representation.

## Crossing the boundary: atoms and strings

An atom **is** a Python `str` (`bar` is `'bar'`); a string is the cell
`('$chars', text)`. Every outbound conversion hands an atom over as the `str`
it already is; what differs between them is how deep they turn a **string**
into text.

There are **two** outbound conversions, and which one a boundary gets is a
decided trade rather than an accident.

`clausal.to_python` is the **deep** one, and every `py.*`
wrapper argument goes through it:

| Term | What the Python callee sees |
|---|---|
| atom `bar` | the `str` `'bar'` — the atom itself |
| string `"bar"` (the cell `('$chars', 'bar')`) | the `str` `'bar'` — its text |
| a partial string that has become ground | the `str` it walks to |
| compound cell `foo("x", 1)` | the tuple `('foo', 'x', 1)` (converted elementwise) |
| a cell whose functor is REGISTERED — `date(2023, 6, 1)`, the data cell `('()', 1, 2)` | the registered Python object — `datetime.date(2023, 6, 1)`, `(1, 2)` |
| `SetTerm` / ground `SegList` | a `frozenset` / the list |
| list `[bar, "x"]` | `['bar', 'x']` |
| `DictTerm` / dict | a `dict`, **keys converted and normalised** (an atom key and its text merge into one) |
| a non-ground `Seg*`, anything else | itself |

`clausal.logic.to_python.unwrap_atom` is the **shallow** one, and it is what
a `++` escape or an f-string argument gets: a string **argument** becomes its
text, and so does a string **element of a list argument** (one level, so
`", ".join(W)` works); everything else is handed over as it stands.

| Term at a `++` / f-string argument | What the Python expression sees |
|---|---|
| atom `bar` | the `str` `'bar'` |
| string `"bar"` | the `str` `'bar'` |
| list `["x", "y"]` | `['x', 'y']` |
| anything else, **including deeper containers** | itself, unconverted |

So a string nested deeper crosses **raw**: `++repr(L)` on `L = [f("x")]` sees
`[('f', ('$chars', 'x'))]`, and a `DictTerm` argument arrives as a `DictTerm`.
Atoms need nothing: `++len(L)` on `L = [bar, baz]` sees `['bar', 'baz']`. When
you want the deep conversion at a `++`, ask for it by name — `from
clausal import to_python` in the Python module you are escaping into, and call
it on the argument there.

Why the asymmetry: a `py.*` call crosses a bounded argument list into a
foreign library that cannot read engine terms at all, and pays for the walk
once. A `++` escape is inline in a clause body, runs in the inner loop, and is
written by someone who can see exactly what they are passing — and the walk
cost 7.4 % of a `++`-heavy benchmark against a 3 % bar (the design's §9.1
recorded this fallback in advance; it was applied 2026-09-07 on the measurement).

Inbound, a plain Python `str` coming back through `++` is an **atom** — the
same value an atom is — so an atom that crosses out and back is unchanged,
and text that crosses out comes back as an atom, not a string:

```clausal
-private([bar])

round_trip(X, Y) <- (Y is ++X)

test("an atom crosses out and back as the same atom") <- (
    round_trip(bar, Y),
    atom(Y),
    Y is bar
)

test("text crosses back as an atom, not a string") <- (
    round_trip("bar", Y),
    atom(Y),
    not (Y is "bar")
)
```

A program that needs a string back **makes one**: `atom_chars(Y, Text)` in
Clausal, or hands the carrier itself back — a goal-position answer that is a
string comes out as the carrier, and `++` passes it in unchanged, so
`for T in --txt(T): ... if --txt(++T)` is the identity round trip. (The
2026-09-21 design that tagged atoms on the way out and read a plain `str` as
text on the way in was superseded by the dumb seam on 2026-09-26.)

#### Deprecated: the `atom` boundary class

`clausal.logic.atoms.atom` — the `str` subclass that tagged a value as an
atom under the 2026-09-21 design — is **deprecated** as of 2026-09-27 and is
**removed in 2.0**. The engine no longer hands one out: every answer's atom is
the plain `str`. Constructing one emits `ClausalAtomClassDeprecationWarning`
(in `clausal.lint_warnings`), once per call
site. It is a `UserWarning` (via `ClausalLintWarning`), not a
`DeprecationWarning`, so it is **shown by default** in library code too;
silence it with `warnings.filterwarnings("ignore",
category=ClausalAtomClassDeprecationWarning)`. Until 2.0 the class keeps working exactly as before — equality, hashing,
interning and pickling are unchanged — and an instance handed in through
`++`, a seam's bare name or `solve`/`once`/`call` is still stripped to its
`str` (the leak rule), without a warning.

| Old | Now |
|---|---|
| `atom('permitted')` | `'permitted'` — the atom **is** the `str` |
| `isinstance(v, atom)` | `type(v) is str`, or `clausal.logic.atoms.is_atom(v)` |
| `v == atom('x')` | `v == 'x'`, or `v == --x` for a whole term (`V == --result(permitted, art_6)`) |
| reading an answer's text | `clausal.to_python(v)` |

`isinstance(v, atom)` does **not** warn, and it is now `False` for every value
the engine produces — a collector that filtered on it goes silently empty
rather than failing. Find those sites with the census tool, which reads source
by AST and never imports or runs it:

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/atom_class_census/census.py --self-test
PYTHONDONTWRITEBYTECODE=1 python3 tools/atom_class_census/census.py --sites <your tree>
```

`from clausal import atom` is a different object — the builtin `atom/1` goal —
and is not deprecated.

### The Python atom API

```python
from clausal.logic.atoms import mint, is_atom, spelling, char_atom

print(repr(mint("bar")))           # 'bar'   the atom for a spelling: the str itself
print(is_atom("bar"))              # True    the term test: an atom is a plain str
print(is_atom(("bar",)))           # False   ('bar',) is the RESERVED 1-tuple, not an atom
print(is_atom(("$chars", "bar")))  # False   that is the string "bar"
print(repr(spelling("bar")))       # 'bar'   TypeError if not an atom
print(repr(char_atom("a")))        # 'a'     the one-character atom
```

Write new Python-side atom handling against these four names rather than
against a representation. Compare atoms with `==`, **never** with `is`: an
atom is a plain `str`, and Python does not promise that two equal strings are
the same object.

A module attribute for a declared atom is that atom:

```python
import my_module
from clausal.logic.atoms import mint

print(my_module.bar == mint("bar"))   # True
print(repr(my_module.bar))            # 'bar'
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
    The thunk path converts a **top-level** string (and a list's string
    elements) only, so any other interpolated container reaches `format()` as the engine term it is — `f"{D}"` on a dict
    `D = {a: 1}` renders that `DictTerm`'s own `__format__`/`repr`, with the
    key still the atom `'a'` and a string value still the cell
    `('$chars', ...)`. For a rendering you control, ask for one:
    `term_to_string(D, S)` (or `print_term/1`), then interpolate `S`.

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

This means `Decimal`, `pathlib.Path`, and any other Python type with `__eq__` works as a logic term without wrapping. Dates and times are the exception on the **query** path: a date is the term `("date", Y, M, D)` (likewise `("datetime", …)`, `("time", …)` and `("timedelta", …)`), and that term is what a query passes — `solve(("same_day", ("date", 2024, 1, 1), X), module=m)`, directly or nested inside a list or compound argument. A bare Python `datetime.date` as a query argument is refused with a `NotImplementedError` that names the term to write, rather than binding by reference and quietly matching nothing. An object with no term form at all — a socket, a lock, a plain `object()` — crosses a query BY REFERENCE, at the top level or nested in a list or compound argument: `solve(("=", X, sock), module=m)` binds `X` to that very socket. Call methods via `++()`:

```clausal
-import_from(date_time, [date])

iso_date(Y, M, D, S) <- (
    date(Y, M, D, DT),
    S is ++DT.isoformat()
)
```

---

## Listing the atoms a module declares: `declared_atoms`

`clausal.declared_atoms(module_or_package)` answers which atom names a
module's own files declare: the names in each file's `-module(Name, [...])`
export list and `-private([...])` list. It returns a `frozenset` of `str`.

```python
import clausal
import shapes                          # a package: shapes/__init__.clausal,
import shapes.colours, shapes.forms    # shapes/colours.clausal, shapes/forms.clausal

clausal.declared_atoms("shapes")       # frozenset({'red', 'green', 'circle', ...})
clausal.declared_atoms(shapes.forms)   # just forms.clausal's declarations
```

- **An imported atom is not included.** An atom a file gets through
  `-import_from` is bound in its namespace, but the file did not declare it;
  the module that declares it does. A file that names an imported atom in
  its own `-module` list re-exports it, and that counts as a declaration.
- **The answer does not depend on import order.** It reads each file's
  own declaration record, not the module namespace (which also holds
  predicates, builtins and imported names) and not the process-wide atom
  pool.
- **A package counts its loaded submodules.** For a package the answer is
  the union over the package's own `__init__` and every submodule already in
  `sys.modules` whose file is under the package directory. It never imports
  a submodule: asking a question must not run module bodies. Import the
  submodules you want counted first.
- The argument is an imported module, a `Module`, or a dotted name. A name
  is looked up in `sys.modules` the way `module=` is, and one that is not
  loaded raises `existence_error(module, …)`.

## Listing the atoms a module imports: `imported_atoms`

`clausal.imported_atoms(module_or_package)` is the companion of
`declared_atoms`: the atoms a module's own files bring in through
`-import_from` **without** declaring them, as a `dict` from atom name to the
dotted name of the module that exports it.

```python
import clausal
import shop             # shop/__init__.clausal has no -module list:
                        #   -import_from(shop.vocabulary, [open_kind, ...])

clausal.declared_atoms("shop")   # frozenset()
clausal.imported_atoms("shop")   # {'open_kind': 'shop.vocabulary', ...}
```

- **Only atoms the exporter declares.** An entry counts when the exporter's
  own file declares the name in its `-module`/`-private` list: one level,
  the way the import itself resolves it. An imported predicate is not an
  atom, and a module that only imports an atom and passes it on is not its
  exporter. For a single-file exporter this is `declared_atoms(exporter)`;
  for a package exporter only its `__init__` counts, so the answer does not
  depend on which of its submodules are loaded.
- **Disjoint from `declared_atoms`.** An imported atom that a file in scope
  re-declares in its own `-module`/`-private` list belongs to
  `declared_atoms`. So `declared_atoms(m) | imported_atoms(m).keys()` is every
  atom the files can name.
- **The key is the atom.** `alias(orig, local)` reports `orig`, the atom the
  local name is bound to. The exporter is the module's `sys.modules` name
  (its `__name__`), which `declared_atoms` accepts.
- **Clashes are deterministic.** When two exporters that both declare an
  atom are imported, the atom is the same (atoms are global by spelling) and
  only the attribution differs. Within one file the later `-import_from`
  that names the atom wins, whatever local name it binds (`alias(x, y)`
  names the atom `x`, the same as a plain `x`). Across a package's files,
  the package's `__init__` is asked first, then its loaded submodules in
  sorted name order, and the first file that imports the atom wins.
- Package scoping, the argument forms and the errors are those of
  `declared_atoms`. The result is a fresh `dict` with sorted keys.

---

## Using `Module` Directly

For tests or programmatic use without the [import hook](import.md), load a
`.clausal` file from its path — each call compiles it afresh, with its own
database — and query it exactly as above:

```python
from clausal import Var, solve
from clausal.testing import load_clausal_module

fibonacci = load_clausal_module("clausal/examples/fibonacci.clausal")
for trail in solve(("fib", 10, F := Var()), module=fibonacci):
    print(F.value)  # 55
```

To add clauses at runtime, declare the predicate `-dynamic` in a `.clausal`
file and run `assertz`/`retract` as goals (see
[assertz/retract from Python](#assertzretract-from-python)); an undeclared or
static predicate is refused.

!!! warning "Internal API"
    The block below fills a bare `Module` through the `Database`, `Clause`
    and the compiler directly. None of these is covered by the 1.0 promise
    (see [Public API](public-api.md)), and the direct `db.assertz` skips the
    `-dynamic` check the `assertz/1` goal makes. It is shown for engine
    tests and tooling.

The clause head is a cell, the database holds the clauses, and the predicate
is compiled once; a later `db.assertz` on the same database recompiles it on
its next call:

```python
from clausal import Module, Var, solve
from clausal.logic.database import Clause
from clausal.logic.compiler import compile_predicate_trampoline

graph = Module("graph")
db = graph.db
for a, b in [("a", "b"), ("b", "c")]:
    db.assertz(Clause(head=("edge", a, b), body=[]))
compile_predicate_trampoline("edge", 2, db.clauses_for("edge", 2), db)

db.assertz(Clause(head=("edge", "c", "d"), body=[]))
for trail in solve(("edge", X := Var(), Y := Var()), module=graph):
    print(X.value, Y.value)  # a b / b c / c d
```

A rule's body is a list of compiled goal nodes, not cells — write rules in a
`.clausal` file and load it as above.

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

    `call(functor, *args, module=…)` resolves predicates in this order:

    1. A module-qualified handle as `functor` (a module attribute such as
       `fibonacci.fib`) switches to the module that owns it.
    2. The module's own binding for the name, at the arity it was defined or
       imported at — resolved with `_dispatch_at(binding, arity, db)`. A
       binding is the owning module's predicate **handle** (a `str`), so this
       step reads the owner's row, not an attribute of the binding.
    3. `get_builtin_predicate(functor, arity, db)` — builtin predicates.
    4. `module.db.get_dispatch(functor, arity)` — the module's own database
       row.

    Nothing answering is `PredicateNotFoundError`, a `KeyError` whose `.term`
    is the ISO `existence_error(procedure, Name/Arity)`.

    ### `structural_unify`

    `clausal.logic.builtins.structural_unify(t1, t2, trail)` is a Python-level recursive unifier for cells and `@dataclass` instances. It is internal (not covered by the 1.0 promise); use `unify` from `clausal.logic.variables`, whose C implementation handles `Var` binding, tuples, lists, and atomic equality.

    ### Term Dereferencing

    `deref(var)` unwraps one level. For full recursive dereferencing (an
    internal helper; `to_python` is the covered deep conversion):

    ```python
    from clausal.logic.solve import _deref_walk

    _deref_walk(term)  # recursively dereferences cells, lists, etc.
    ```

    ### Builtin Term Constructors

    A builtin whose name is a Python identifier is exported from `clausal`
    as a term constructor, and calling it **builds a cell** — it does not
    run anything. (The predicate is covered by the 1.0 promise; the Python
    object is not, so a plain cell is the stable spelling.) Run the cell like
    any other goal:

    ```python
    from clausal import Module, Var, solve, append

    goal = append([1, 2], [3], L := Var())   # → ('append', [1, 2], [3], L)
    for trail in solve(goal, module=Module("scratch")):
        print(L.value)  # [1, 2, 3]
    ```

    Iterating the cell itself (`for _ in append(...)`) walks the tuple's
    elements — it never runs the goal.

    Multi-arity builtins (`maplist`, `phrase`) pick the signature by argument
    count.

    ### assertz/retract from Python

    Run the builtin as a goal. In a `.seam` file that is `if --assertz(counter(1)):`;
    from a `.py` file, pass the clause as a cell and the module that owns the
    predicate:

    ```python
    from clausal import once

    once(("assertz", ("counter", 1)), module=m)    # m declares -dynamic(counter/1)
    once(("retract", ("counter", 0)), module=m)
    ```

    The builtins:

    1. Check that the target predicate is not locked (see [Directives](directives.md) for `-dynamic`) — a static one raises ISO `permission_error(modify, static_procedure, Name/Arity)`
    2. Resolve the predicate's row: the module's binding for the name is the owner's handle, and `resolve_predicate_row` finds the owner's row (`db.row(functor, arity)` in that owner's database), so a write through an `-import_from` lands in the owner's clause list
    3. assertz/retract the clause on that [Database](database_ops.md) row
    4. Recompile against the owner's module globals

    ### `++()` Implementation

    The `++` syntax is detected by `visit_UnaryOp` in `term_rewriting.py` as `UAdd(UAdd(expr))`. The compiler emits a `_pyt_<id>(deref(...))` call wrapping the expression in a `PyThunk` lambda.

---

*See also: [I/O](io.md) — write, writeln, f-strings for formatted output.*
*See also: [Predicates](predicates.md) — defining predicates in `.clausal` files.*
