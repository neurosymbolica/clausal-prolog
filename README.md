# clausal

Logic programming embedded in Python. Write relational programs in
**Clausal Prolog**, a cut-free, ISO-like Prolog, and import them with
Python's standard import system. The engine includes constraint solving,
tabling, DCGs and a large standard library. Clausal also loads ISO Prolog
`.pl` files, and keeps a Python-syntax surface, the **seam**, for code that
has to call Python.

## Three source surfaces

| Extension | Surface | Syntax | Use it for |
|---|---|---|---|
| `.clausal` | **Clausal Prolog** | ISO Prolog, without cut | Your logic programs. The default choice. |
| `.pl` | **ISO Prolog** | ISO Prolog | Existing Prolog code (cut-free; experimental) |
| `.seam` | **Seam** | Python syntax | The boundary with Python: `++` escapes, hosted Python, adapters |

All three are importable modules once `clausal` is imported. In one
directory, `name.seam` beats `name.clausal`, which beats `name.pl`.

> **Changed in 1.0 (the extension flip).** `.clausal` used to be the
> Python-syntax seam language. It is now Clausal Prolog, and seam source is
> named `.seam`. A seam file still named `.clausal` fails to load with a
> Prolog syntax error. To migrate, run `git mv name.clausal name.seam` for
> each one. Move it rather than copying it: a `name.clausal` left beside
> `name.seam` is a different module, written in Prolog. See
> [CHANGELOG.md](CHANGELOG.md).

## Features

- **Clausal Prolog**: ISO syntax, ISO builtin names and error terms, `"…"`
  as a string, and modules with `module/2`, `use_module/1,2` and
  `end_module/1`
- **Purity by design**: no cut, `->` or `*->`; use `dif/2`, `if_/3` from
  `library(reif)`, constraints and first-argument indexing instead
- **Constraint solving**: CLP(Z) for integers, CLP(B), CLP(Q), CLP(R) and
  `dif/2`
- **SLG tabling** and **well-founded semantics** for negation over tabled
  predicates
- **DCGs**: `-->` grammar rules with `phrase/2,3`
- **ISO Prolog import**: load `.pl` files directly (experimental)
- **Python interop through the seam**: `library(...)` facades over the
  engine's Python modules (`library(json)`, `library(datetime)`, …),
  Python-free `.seam` modules, and allowlisted Python bridges
- **C extensions**: logic variables, trail-based backtracking and a
  trampoline, with no WAM

## Installation

```bash
pip install clausal
```

Requires Python ≥ 3.13 and a C compiler (pip uses it automatically when
building from source).

## Quick start

### A Clausal Prolog module

```prolog
% family.clausal
:- module(family, [grandparent/2, fib/2, path/2]).

parent(tom, bob).
parent(tom, liz).
parent(bob, ann).
parent(bob, pat).

grandparent(X, Z) :- parent(X, Y), parent(Y, Z).

fib(0, 0).
fib(1, 1).
fib(N, F) :-
    N > 1,
    N1 is N - 1, N2 is N - 2,
    fib(N1, F1), fib(N2, F2),
    F is F1 + F2.

% Tabling terminates on the cycle.
:- table(path/2).
edge(1, 2).
edge(2, 3).
edge(3, 1).
path(X, Y) :- edge(X, Y).
path(X, Y) :- edge(X, Z), path(Z, Y).

test("tom's grandchildren") :- grandparent(tom, ann), grandparent(tom, pat).
test("fib(10) = 55") :- fib(10, 55).
test("path reaches the whole cycle") :- findall(Y, path(1, Y), Ys), msort(Ys, [1, 2, 3]).
test("tom has no grandparent", fail) :- grandparent(_, tom).

:- end_module(family).
```

A Clausal Prolog module file must end with `:- end_module(Name).`.

### Querying it from Python

```python
import clausal                      # installs the import hook
import family                       # loads family.clausal
from clausal import call, deref, Var

GRANDCHILD = Var()
print([deref(GRANDCHILD) for _ in call("grandparent", "tom", GRANDCHILD, module=family)])
# ['ann', 'pat']
```

### Constraints, DCGs and reified conditions

```prolog
% puzzles.clausal
:- module(puzzles, [greeting//0, send_more/1, classify/2]).
:- use_module(library(clpz)).
:- use_module(library(reif)).

greeting --> [hello], name.
name --> [world].
name --> [prolog].

send_more([S,E,N,D,M,O,R,Y]) :-
    Vars = [S,E,N,D,M,O,R,Y],
    Vars ins 0..9, all_different(Vars),
    S #\= 0, M #\= 0,
    1000*S + 100*E + 10*N + D + 1000*M + 100*O + 10*R + E #=
        10000*M + 1000*O + 100*N + 10*E + Y,
    label(Vars).

% if_/3 instead of (Cond -> Then ; Else): it stays correct when X is unbound.
classify(X, R) :- if_(X = a, R = yes, R = no).

test("dcg") :- phrase(greeting, [hello, prolog]).
test("send more money") :- send_more([9,5,6,7,1,0,8,2]).
test("if_") :- classify(a, yes), classify(b, no).
test("dif") :- dif(X, a), X = b.

:- end_module(puzzles).
```

## What Clausal Prolog restricts

Clausal Prolog is ISO Prolog with a few deliberate rules. Each one is
enforced when the file loads:

- **Cut-free.** `!`, `->` and `*->` are refused. Use `dif/2`, `if_/3`,
  `once/1`, constraints or first-argument indexing.
- **Modules close.** A module file must end with `:- end_module(Name).`.
  A file can opt out with `:- set_prolog_flag(require_end_module, false).`.
- **One-way dependency on ISO Prolog.** A `.clausal` module may not import
  a `.pl` module, which may use cut. It is refused with
  `permission_error(access, prolog_module, M)`. A `.pl` module may import a
  `.clausal` one.
- **Python only through the seam.** A `.clausal` file reaches Python
  through engine-shipped `library(...)` facades (for example
  `:- use_module(library(datetime), [date_add/3]).`), through Python-free
  `.seam` modules, or through `.seam` modules listed under
  `[tool.clausal] python_bridges` in the importing project's
  `pyproject.toml`. Anything else is refused with
  `permission_error(import, python_bridge, M)`.

See [docs/importing_prolog.md](docs/importing_prolog.md) for the full rules.

## ISO Prolog `.pl` files

Put a `.pl` file on `sys.path` and import it:

```python
import clausal
import my_prolog_module   # loads my_prolog_module.pl
```

`.pl` import is **experimental** and outside the 1.0 compatibility promise.
Clausal is cut-free on every surface, so a `.pl` file that uses `!` or `->`
is refused here too. `CLAUSAL_PL_FRONTEND=native` selects the native ISO
reader that Clausal Prolog always uses. The default is `translator`. To run
unrestricted ISO Prolog alongside Clausal, use the
[Scryer](packages/clausal-scryer/docs/scryer.md) or
[Trealla](packages/clausal-trealla/docs/trealla.md) embeddings.

## The seam: `.seam` files

The seam is Clausal's Python-syntax surface. Facts end with a comma, rules
use `<-`, and variables are ALL_CAPS. Atoms must be declared, in the
`-module` export list or with `-private`. In the seam, `==` evaluates
arithmetic and `is` unifies, which is the reverse of ISO.

```seam
# demo.seam
-module(demo, [fib(N, F), grandparent(X, Z)])
-private([tom, bob, liz, ann, pat])

parent(tom, bob),
parent(tom, liz),
parent(bob, ann),
parent(bob, pat),

grandparent(X, Z) <- (parent(X, Y), parent(Y, Z))

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

test("fib(10) = 55") <- fib(10, 55)
test("grandchildren") <- (grandparent(tom, ann), grandparent(tom, pat))
```

Use `.seam` where code must touch Python: the `++expr` escape, hosted Python
statements, or wrapping a Python library. Everything else belongs in
`.clausal`. `clausal-fmt` and `clausal-rewrite` work on `.seam` files and
refuse Prolog-syntax ones. The [docs](docs/index.md) cover the seam syntax
in depth.

## Testing

Any of the three surfaces can carry inline tests as `test/1` clauses, or
as `test/2` with the option `fail` for a goal that must have no solution:

```prolog
test("fib(5) = 5") :- fib(5, 5).                 % .clausal / .pl
test("no grandparent", fail) :- grandparent(_, tom).
```

```seam
test("fib(5) = 5") <- fib(5, 5)                  # .seam
```

**Standalone runner:**

```bash
python -m clausal.testing path/to/dir/              # every .seam, .clausal and .pl file
python -m clausal.testing family.clausal            # a single file
python -m clausal.testing -v clausal/examples/      # verbose
```

**Via pytest**: test clauses in `.seam`, `.clausal` and `.pl` files are
collected automatically.

```bash
python -m pytest tests/ clausal/examples/ -q
```

## Logic variables and backtracking

The C extension `clausal.logic.variables` provides Prolog-style logic
variables and trail-based backtracking without a Warren Abstract Machine.

```python
from clausal.logic.variables import Var, Trail, unify, is_var

trail = Trail()
X = Var()
Y = Var()

unify(X, 42, trail)
assert X.value == 42

mark = trail.mark()
unify(Y, "temporary", trail)
trail.undo(mark)
assert is_var(Y)   # Y is unbound again
```

### Constraints

```python
from clausal.logic.variables import Var, Trail, unify
from clausal.logic.constraints import dif

trail = Trail()
X, Y = Var(), Var()

dif(X, Y, trail)      # post: X ≠ Y
unify(X, 1, trail)    # ok — still satisfiable
unify(Y, 2, trail)    # ok — satisfied (1 ≠ 2)
```

## Requirements

- Python ≥ 3.13
- [greenlet](https://pypi.org/project/greenlet/)
- C compiler (for building from source)

YAML support is the optional package `clausal-yaml` (`pip install clausal[yaml]`).

## License

MIT
