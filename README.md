<p align="center"><img src="https://raw.githubusercontent.com/neurosymbolica/clausal-prolog/main/docs/assets/logo/clausal-banner.png" alt="Clausal Prolog" width="460"></p>

# Prolog in Python for Neurosymbolic AI

**Documentation: [clausal.pl](https://clausal.pl)** · start with the
[Tutorial](https://clausal.pl/tutorial/).

Neural networks are good at perception, language and pattern-matching, but are
slow, resource-hungry, unreliable and need to be constrained. Symbolic AI is
good at rules, reasoning and guarantees but can't deal with the real world.
Clausal Prolog puts both in one Python process: a neural network can call
symbolic logic that in turn calls neural predicates, nested as deeply as you
like, with no serialisation, IPC or second runtime in between. Combining the
two gives systems that are:

- **Explainable**: conclusions come from rules you can read and a derivation
  you can trace, not only from weights.
- **Reliable**: hard constraints such as regulations, safety rules and
  business policy hold exactly, every time, rather than approximately.
- **Data-efficient**: knowledge you can state as a rule doesn't have to be
  learned from examples.
- **Correctable**: change a rule and the behaviour changes, with no
  retraining.

Clausal Prolog is a Prolog implemented in Python that aims for ISO Prolog
conformity. Logic programs go in `.clausal` files, written in Clausal Prolog:
ISO syntax without cut or committed choice, which guarantees properties of
programs that let you realise [The Power of Prolog](https://www.metalevel.at/prolog).
Existing ISO Prolog goes in `.pl` files. The seam (`.seam`) is a Python-syntax
surface for the adapters that give controlled access\* to the whole Python
ecosystem. All three import with Python's standard import system, and the
import rules preserve each surface's guarantees. The engine includes
constraint solving, tabling, DCGs and a large standard library.

\*Python seam adaptors assume the Python programmer takes full
responsibility for correctness (in the Pythonic way).

The package is `clausal`: `pip install clausal`, `import clausal`.

## Three source surfaces

| Extension | Surface | Syntax | Use it for |
|---|---|---|---|
| `.clausal` | **Clausal Prolog** | ISO Prolog, without cut | Your logic programs. The default choice. |
| `.pl` | **ISO Prolog** | Regular ISO Prolog, cut included | External Prolog code, for Prolog systems such as Scryer or Trealla |
| `.seam` | **Seam** | Python syntax | The boundary with Python: `++` escapes, hosted Python, adapters |

All three are importable modules once `clausal` is imported. In one
directory, `name.seam` beats `name.clausal`, which beats `name.pl`.

> **Changed in 1.0 (the extension flip).** `.clausal` used to be the
> Python-syntax seam language. It is now Clausal Prolog, and seam source is
> named `.seam`. A seam file still named `.clausal` fails to load with a
> Prolog syntax error. To migrate, run `git mv name.clausal name.seam` for
> each one. Move it rather than copying it: a `name.clausal` left beside
> `name.seam` is a different module, written in Prolog. See
> [CHANGELOG.md](https://github.com/neurosymbolica/clausal-prolog/blob/main/CHANGELOG.md).

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
- **Regular ISO Prolog alongside**: `.pl` files, run in the Scryer or
  Trealla embeddings, or imported directly (experimental)
- **Python interop through the seam**: `library(...)` facades over the
  engine's Python modules (`library(json)`, `library(datetime)`, …),
  Python-free `.seam` modules, and allowlisted Python bridges
- **Asyncio, not a home-grown scheduler** (experimental): queries run on
  Python's own `asyncio` event loop, so they wait on models, databases,
  people and event streams alongside any async Python library, with
  timeouts, cancellation and racing straight from `asyncio`. Backtracking
  still works across waits. See [docs/asyncio.md](docs/asyncio.md)
- **ISO direction**: ISO builtin names, ISO error terms and ISO modules;
  where ISO is silent, Scryer Prolog's behaviour
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
:- use_module(library(clpz)).

parent(tom, bob).
parent(tom, liz).
parent(bob, ann).
parent(bob, pat).

grandparent(X, Z) :- parent(X, Y), parent(Y, Z).

% CLP(Z) arithmetic: fib/2 runs in both directions.
fib(0, 0).
fib(1, 1).
fib(N, F) :-
    N #> 1,
    N1 #= N - 1, N2 #= N - 2,
    F #>= N1, F #= F1 + F2,
    fib(N1, F1), fib(N2, F2).

% Tabling terminates on the cycle.
:- table(path/2).
edge(1, 2).
edge(2, 3).
edge(3, 1).
path(X, Y) :- edge(X, Y).
path(X, Y) :- edge(X, Z), path(Z, Y).

test("tom's grandchildren") :- grandparent(tom, ann), grandparent(tom, pat).
test("fib(10) = 55") :- fib(10, 55).
test("which fib is 55?") :- once(fib(N, 55)), N == 10.
test("path reaches the whole cycle") :- findall(Y, path(1, Y), Ys), msort(Ys, [1, 2, 3]).
test("tom has no grandparent", fail) :- grandparent(_, tom).

:- end_module(family).
```

A Clausal Prolog module file must end with `:- end_module(Name).`.

### Running it

```bash
clausal family.clausal -g "grandparent(tom, X)"   # X = ann.  X = pat.
clausal --test family.clausal                      # runs the test clauses
```

`clausal FILE` on its own runs the program's `main/0`. See
[docs/cli.md](https://clausal.pl/cli/).

### Querying it from Python

Python asks the questions from a `.seam` file, with a goal in `for`
position after `--`:

```python
# app.seam
-import_from(family, [grandparent, fib])
-private([tom])

for GRANDCHILD in --grandparent(tom, GRANDCHILD):
    print(GRANDCHILD)               # ann, then pat

for N in --fib(N, 55):
    print(N)                        # 10
    break
```

```bash
python -c "import clausal, app"     # import clausal installs the import hook
```

See [Python Integration](https://clausal.pl/python_integration/) for more ways to query.

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

- **Cut-free.** `!` and `->` are refused, and `*->` is not an operator.
  Use `dif/2`, `if_/3`,
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

See [docs/importing_prolog.md](https://clausal.pl/importing_prolog/) for the full rules.

## ISO Prolog `.pl` files

A `.pl` file is regular, external ISO Prolog: it is not restricted to the
cut-free subset, and that is why a `.clausal` module may not import one.
To run full ISO Prolog, cut included, alongside Clausal Prolog, use the
[Scryer](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scryer/docs/scryer.md) or
[Trealla](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-trealla/docs/trealla.md) embeddings.

Importing a `.pl` file straight into the engine (put it on `sys.path` and
`import` it) is
**experimental** and outside the 1.0 compatibility promise. That in-process
loader does not run cut yet: a `.pl` file that uses `!` or `->` fails to
load there. `CLAUSAL_PL_FRONTEND` selects its front end (`translator` by
default, or `native`, the ISO reader that `.clausal` files always use).

## The seam: `.seam` files

Code that must call Python lives in `.seam` files. These use the older
Python-syntax surface, with the `++expr` escape, hosted Python statements
and adapters over Python libraries. A `.clausal` module imports a `.seam`
module like any other (subject to the
[Python-bridge rules](#what-clausal-prolog-restricts)). Keep `.seam`
modules small and write your logic in Clausal Prolog. `clausal-fmt` and
`clausal-rewrite` work on `.seam` files only. See
[docs/clausal_prolog.md](https://clausal.pl/clausal_prolog/) for how the two surfaces
differ.

## Testing

A module carries its tests inline as `test/1` clauses, or as `test/2`
with the option `fail` for a goal that must have no solution:

```prolog
test("fib(5) = 5") :- fib(5, 5).
test("no grandparent", fail) :- grandparent(_, tom).
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

## Requirements

- Python ≥ 3.13 and [greenlet](https://pypi.org/project/greenlet/) (the only
  runtime dependency; it lets queries run on `asyncio`)
- C compiler (for building from source)

Optional packages wrap Python libraries for use from Clausal Prolog. Each is
on PyPI and is also available as an extra of `clausal`:

```bash
pip install clausal-scipy        # or: pip install "clausal[scipy]"
```

| Package | Wraps |
|---|---|
| [`clausal-jax`](https://pypi.org/project/clausal-jax/) | JAX (plus optax, equinox, flax as extras) |
| [`clausal-opencv`](https://pypi.org/project/clausal-opencv/) | OpenCV |
| [`clausal-scipy`](https://pypi.org/project/clausal-scipy/) | SciPy |
| [`clausal-sklearn`](https://pypi.org/project/clausal-sklearn/) | scikit-learn |
| [`clausal-spacy`](https://pypi.org/project/clausal-spacy/) | spaCy |
| [`clausal-sympy`](https://pypi.org/project/clausal-sympy/) | SymPy |
| [`clausal-torch`](https://pypi.org/project/clausal-torch/) | PyTorch |
| [`clausal-yaml`](https://pypi.org/project/clausal-yaml/) | PyYAML |

The Scryer, Trealla and GNU Prolog embeddings live in
[`packages/`](https://clausal.pl/packages/) too, but need native builds and
are not on PyPI yet.

## License

MIT
