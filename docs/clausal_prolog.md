# Clausal Prolog

**Clausal Prolog** is the language of `.clausal` files: ISO Prolog syntax,
ISO builtin names and ISO error terms, without cut. It is the default
surface for writing logic programs, and the project is working towards ISO
Prolog conformity. Where ISO is silent, Clausal Prolog follows
[Scryer Prolog](https://www.scryer.pl/).

The engine reads three source surfaces:

| Extension | Surface | Syntax | Read by |
|---|---|---|---|
| `.clausal` | **Clausal Prolog** | ISO Prolog, cut-free | the native ISO front end, always |
| `.pl` | **ISO Prolog** | Regular ISO Prolog, cut included | external Prolog systems (the Scryer and Trealla embeddings); experimental in-process import via `CLAUSAL_PL_FRONTEND` |
| `.seam` | **the seam** | Python syntax | `PredicateLoader` |

The seam is the boundary with Python. It is where the `++expr` escape,
hosted Python statements and the adapters over Python libraries live. Most
of the language pages in these docs still show seam syntax, and they say
so. The semantics they describe (unification, search, tabling, constraints,
modules) are shared by all three surfaces.

!!! note "The extension flip"
    Before 1.0, `.clausal` was the Python-syntax seam language. It is now
    Clausal Prolog, and seam source is named `.seam`. A seam file still
    named `.clausal` fails to load with a Prolog syntax error. To migrate,
    run `git mv name.clausal name.seam`. Move the file rather than copying
    it: a stale `name.clausal` beside `name.seam` is a different module,
    written in Prolog. In one directory, `name.seam` beats `name.clausal`,
    which beats `name.pl`.

---

## A module

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

Query it from Python:

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

The goal's variables become ordinary Python locals, bound to each answer
in turn. Atoms used in a `.seam` file are declared, here with `-private`.

Run its tests with `python -m clausal.testing family.clausal`, or let
pytest collect them (see [Testing](testing.md)).

---

## Libraries, constraints and DCGs

Load libraries with `use_module/1,2`. Grammar rules use `-->` and run with
`phrase/2,3`.

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

classify(X, R) :- if_(X = a, R = yes, R = no).

test("dcg") :- phrase(greeting, [hello, prolog]).
test("send more money") :- send_more([9,5,6,7,1,0,8,2]).
test("if_") :- classify(a, yes), classify(b, no).
test("dif") :- dif(X, a), X = b.
test("double quotes are strings") :- X = "abc", string(X).

:- end_module(puzzles).
```

---

## The rules

Clausal Prolog is ISO Prolog with a few deliberate rules. Each one is
checked when the file loads, and a violation is a load error naming the
file and line.

### Cut-free

`!`, `->` (if-then, and if-then-else) and `*->` (soft cut) are refused:

```text
c.clausal:2: `!` (cut) is refused: Clausal is cut-free with no committed
choice, by design (ruling): !, -> and *-> are refused
```

Use the pure alternatives instead. These are `dif/2`, `if_/3` and the
reified predicates from `library(reif)` (see
[If-Then-Else](reified_ite.md)), constraints, `once/1`, and first-argument
indexing (see [Purity](purity.md)). The same rule applies to `{!}` in a
grammar body.

### Modules end with `end_module/1`

A module file (one with `:- module(Name, Exports).`) must end with
`:- end_module(Name).`. Only comments and layout may follow it. A missing
directive is the ISO error
`error(existence_error(directive, end_module(Name)), load/1)`.

Whether it is required is decided by, most specific first:

1. the file's own `:- set_prolog_flag(require_end_module, true|false).`;
2. the process-wide setting: `set_prolog_flag(require_end_module, V)` run
   as a goal, or the environment variable `CLAUSAL_REQUIRE_END_MODULE`;
3. the surface default: required for `.clausal`, not required for `.pl`.

See [Importing Prolog](importing_prolog.md) for the full error table.

### No imports of ISO Prolog

A `.clausal` module may not import a `.pl` module, because a `.pl` module
may use cut. The refusal is
`permission_error(access, prolog_module, M)`. It applies to `use_module`
and to the run-time routes (`M:G`, `call/N` of a qualified goal). The
dependency is one-way: a `.pl` module may import a `.clausal` one. To reuse
`.pl` code, convert it to `.clausal`, or wrap it in a `.seam` module.

### Python only through the seam

Clausal Prolog reaches Python only through:

1. **engine-shipped modules**: the `library(...)` facades over the engine's
   Python modules (`library(json)`, `library(datetime)`, `library(units)`,
   …), the standard library and the engine's own adapters;
2. **Python-free `.seam` modules**: Clausal code written in seam syntax.
   These are checked transitively;
3. **Python bridges**: `.seam` modules that do run Python, listed in
   `[tool.clausal] python_bridges` of the nearest `pyproject.toml` above
   the *importing* `.clausal` file, optionally pinned by sha256.

```prolog
:- use_module(library(datetime), [date_add/3]).   % a facade: allowed
:- use_module(helpers, [double/2]).               % Python-free helpers.seam: allowed
```

Anything else is refused at load with
`permission_error(import, python_bridge, M)`, and a direct import of a
Python module by path with `permission_error(access, python_module, M)`.
See [Importing Prolog: Python bridges](importing_prolog.md) and
[Python Integration](python_integration.md).

---

## Differences from the seam

If you know the seam syntax from the other pages of these docs, these are
the spellings that change:

| | Seam (`.seam`) | Clausal Prolog (`.clausal`) |
|---|---|---|
| Fact | `parent(tom, bob),` | `parent(tom, bob).` |
| Rule | `p(X) <- (q(X), r(X))` | `p(X) :- q(X), r(X).` |
| Variables | `ALL_CAPS` | ISO: `X`, `Rest`, `_` |
| Arithmetic | `N1 == N - 1` | `N1 #= N - 1` (CLP(Z), preferred; works in both directions), or ISO `N1 is N - 1` |
| Unify | `X is Y` | `X = Y` |
| Module | `-module(m, [p(X)])` | `:- module(m, [p/1]).` … `:- end_module(m).` |
| Import | `-import_from(lib, [p])` | `:- use_module(lib, [p/1]).` |
| Table | `-table(path/2)` | `:- table(path/2).` |
| Grammar rule | `s >> (np, vp)` | `s --> np, vp.` |
| Test | `test("t") <- goal` | `test("t") :- goal.` |
| Python | `++expr`, hosted Python | not available: go through a `.seam` module |

---

## Tools

- `python -m clausal.testing` and the pytest plugin run `test/1` and
  `test/2` clauses in `.clausal` files ([Testing](testing.md)).
- `clausal-fmt` and `clausal-rewrite` work on `.seam` files only, and
  refuse Prolog-syntax files.
- To run unrestricted ISO Prolog (with cut) alongside Clausal Prolog, use
  the [Scryer](scryer.md) or [Trealla](trealla.md) embeddings.
