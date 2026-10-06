# Clausal Prolog for Prolog Programmers

You know Prolog. You think in relations, you read clauses declaratively, and
you reach for the most general query to understand a predicate. This page tells
you what's the same, what's different, and where Python comes in.

The short version: **Clausal Prolog** (`.clausal` files) *is* Prolog. It uses
ISO syntax and aims for ISO Prolog conformity, so you write ordinary Prolog.
What it leaves out is cut. See [Clausal Prolog](clausal_prolog.md) for the
reference.

---

## The philosophy is the same

Clausal Prolog is built on the same foundations you know:

- **Predicates define relations.** Clauses state conditions under which
  relations hold. Facts are unconditionally true. Rules have bodies.
- **Unification is bidirectional.** Variables on either side can be bound.
- **Search is via backtracking.** Multiple clauses are logical alternatives.
- **[Purity](purity.md) matters.** Clausal Prolog has [`dif/2`](constraints.md), [CLP(ℤ)](constraints.md), [CLP(B)](clpb.md), [CLP(ℝ)](clpr.md), [reified
  if-then-else](reified_ite.md), and [tabling](tabling.md) — all the tools for staying in the pure monotonic
  core.
- **No cut.** Clausal Prolog does not have `!/0`, by design.

The intellectual debt to Markus Triska's "The Power of Prolog" and Ulrich
Neumerkel's work on purity is explicit and pervasive.

---

## What is the same

Most of it. A `.clausal` file is read by an ISO Prolog front end:

- **ISO syntax**: `Head :- Body.`, `%` and `/* */` comments, operators,
  `TitleCase` variables, `_` and `_Name`, `[H|T]` lists, quoted atoms.
- **ISO builtin names**, with ISO arithmetic: `X is N - 1` evaluates and
  `=` unifies.
- **ISO error terms** in Scryer's form, `error(Formal, Context)`.
- **Modules**: `:- module(Name, Exports).`, `:- use_module(library(L))`,
  `:- use_module(M, [p/2])`, and qualified goals `M:G`.
- **DCGs**: `-->` with `phrase/2,3`.
- **Tabling**: `:- table(p/2).`
- **Libraries**: `library(clpz)`, `library(reif)`, `library(lists)`, `dif/2`.
- **Double quotes**: `"..."` is a string, a list of characters, as in Scryer
  and Trealla.

Where ISO 13211-1 speaks, Clausal Prolog follows it. Where ISO is silent, it
follows [Scryer Prolog](https://www.scryer.pl/) (not SWI).

### Tabling

```prolog
% graph.clausal
:- module(graph, [path/2]).

:- table(path/2).

edge(1, 2).
edge(2, 3).
edge(3, 1).

path(X, Y) :- path(X, Z), edge(Z, Y).   % left recursion: fine when tabled
path(X, Y) :- edge(X, Y).

test("path terminates on the cycle") :-
    findall(Y, path(1, Y), Ys), msort(Ys, [1, 2, 3]).

:- end_module(graph).
```

Same semantics as SWI's or XSB's [tabling](tabling.md). Write the
directive with parentheses, `:- table(path/2).`: `table` is not a prefix
operator here, so `:- table path/2.` is a syntax error.

A `test/1` (or `test/2`) clause is a unit test, run by
`python -m clausal.testing graph.clausal` or by pytest (see
[Testing](testing.md)).

### CLP(ℤ)

Prefer CLP(ℤ) to `is/2` for integer arithmetic, as Triska recommends: it
works in every direction.

```prolog
% queens.clausal
:- module(queens, [n_queens/2]).
:- use_module(library(clpz)).

n_queens(N, Qs) :-
    length(Qs, N),
    Qs ins 1..N,
    safe_queens(Qs),
    labeling([ff], Qs).

safe_queens([]).
safe_queens([Q|Qs]) :- safe_queens(Qs, Q, 1), safe_queens(Qs).

safe_queens([], _, _).
safe_queens([Q|Qs], Q0, D0) :-
    Q0 #\= Q,
    abs(Q0 - Q) #\= D0,
    D1 #= D0 + 1,
    safe_queens(Qs, Q0, D1).

test("the first 8-queens placement") :-
    once(n_queens(8, Qs)), Qs = [1, 5, 8, 6, 3, 7, 2, 4].

:- end_module(queens).
```

This is the program from "The Power of Prolog", unchanged. See
[Constraints](constraints.md).

### DCGs and strings

```prolog
% greet.clausal
:- module(greet, [greeting//0]).

greeting --> "hello ", name.
name --> "world".
name --> "prolog".

test("parse") :- phrase(greeting, "hello prolog").
test("generate") :-
    findall(S, phrase(greeting, S), Ss),
    Ss = ["hello world", "hello prolog"].
test("a string is a list of characters") :- "ab" = [a, b].

:- end_module(greet).
```

`"..."` is a list of characters (`double_quotes` is `chars`, the default in
Scryer and Trealla), so a string literal is a DCG terminal. See
[DCGs](dcg.md) and [Atoms vs strings](syntax.md#atoms-vs-strings).

### Errors and the database

```prolog
% errs.clausal
:- module(errs, []).

colour(red).

test("ISO error terms, in Scryer's form") :-
    catch(atom_length(1, _), error(E, C), true),
    E == type_error(atom, 1), C == atom_length/2.
test("assertz creates a dynamic procedure") :-
    assertz(seen(x)), seen(x).
test("a static procedure cannot be modified") :-
    catch(assertz(colour(blue)), error(E, _), true),
    E == permission_error(modify, static_procedure, colour/1).
test("integer division truncates toward zero") :- X is -7 // 2, X == -3.

:- end_module(errs).
```

An uncaught error prints the term first, as Scryer does:
`Uncaught logic exception: error(type_error(atom,1),atom_length/2)`. See
[Exceptions](exceptions.md) and
[`assert_creates_dynamic`](flags.md#assert_creates_dynamic).

### [Meta-predicates](meta_predicates.md)

[`findall/3`, `bagof/3`, `setof/3`](meta_predicates.md), `forall/2`,
`\+/1`, `once/1` and [`call/1..8`](higher_order.md) are builtins.

### [Modules](import.md)

A predicate sees the names of its own module, never the caller's. A
library that takes a goal argument declares it with `meta_predicate/1`, and
the goal is then resolved in the caller, as in Scryer:

```prolog
% lib.clausal
:- module(lib, [all_hold/2]).
:- meta_predicate(all_hold(1, ?)).

all_hold(G, Xs) :- maplist(G, Xs).

:- end_module(lib).
```

```prolog
% main.clausal
:- module(main, [small_list/0]).
:- use_module(lib, [all_hold/2]).

small(X) :- X < 10.
small_list :- all_hold(small, [1, 2, 3]).

:- end_module(main).
```

Without the `meta_predicate` declaration, `small` is looked up in `lib` and
the call raises `existence_error(procedure, small/1)`; `main:small` names
it explicitly. There is no flat global predicate database. See
[Name resolution is lexical, not dynamic](import.md#name-resolution-is-lexical-pythonic-not-dynamic-prolog).

---

## What is different

### No cut, by design

`!`, `->` (if-then and if-then-else) and `*->` (soft cut) are refused when
the file loads, with an error naming the file and line:

```text
c.clausal:2: `!` (cut) is refused: Clausal is cut-free with no committed
choice, by design (ruling): !, -> and *-> are refused
```

(`*->` is not an operator here, so it is a syntax error.) A `!` built at
run time and passed to `call/1` raises an error instead of running. The
design philosophy is that cut destroys monotonicity, separability, and
multi-directional use — all the properties that make logic programming
worthwhile.

Where you would use a cut or `->`, Clausal Prolog offers:

- **[Reified if-then-else](reified_ite.md)** — `if_/3` and the reified
  predicates of `library(reif)` (`=/3`, `memberd_t/3`, `tfilter/3`, …)
- **[CLP(ℤ) and dif/2](constraints.md)** — replace cut-based pruning with
  constraints
- **`once/1`** — when you want the first solution and say so
- **[First-argument indexing](indexing.md)** — automatic, so the green cuts
  that only removed a choice point are unnecessary

```prolog
% pure.clausal
:- module(pure, [max_of/3, sign/2, first_member/2]).
:- use_module(library(clpz)).
:- use_module(library(reif)).

% max(X, Y, X) :- X >= Y, !.   max(_, Y, Y).
max_of(X, Y, Z) :- Z #= max(X, Y).

% sign(X, S) :- ( X =:= 0 -> S = zero ; S = nonzero ).
sign(X, S) :- if_(X = 0, S = zero, ( dif(X, 0), S = nonzero )).

% first_member(X, Xs) :- member(X, Xs), !.
first_member(X, Xs) :- once(member(X, Xs)).

test("max_of") :- max_of(3, 7, 7), max_of(7, 3, 7).
test("sign") :- sign(0, zero), sign(4, nonzero).
test("sign general") :- findall(X-S, sign(X, S), [0-zero, _-nonzero]).
test("first_member") :- first_member(X, [a, b]), X == a.

:- end_module(pure).
```

The `if_/3` version of `sign/2` answers the most general query
`sign(X, S)` correctly; the `->` version would not.

### Modules end with `end_module/1`

A module file must end with `:- end_module(Name).`, as every example on
this page does. Only comments and layout may follow it. A missing directive
is the ISO error `error(existence_error(directive, end_module(Name)), load/1)`.
The flag `require_end_module` turns the requirement off for one file
(`:- set_prolog_flag(require_end_module, false).`) or for the process. See
[`end_module`](importing_prolog.md#end_module-closing-a-module).

Scryer does not accept `end_module/1`: a file meant for Scryer as well
leaves it out (with the flag set to `false`), or has it removed with
`clausal.end_module.strip_end_module`.

### No importing `.pl` modules

A `.clausal` module may not import a `.pl` module, because ISO Prolog may
use cut. `:- use_module(oldcode, ...)` on an `oldcode.pl` is refused at load
with `permission_error(access, prolog_module, oldcode)`, and so are the
run-time routes (`M:G`, `call/N` of a qualified goal). The dependency is
one-way: a `.pl` module may import a `.clausal` one. To reuse `.pl` code,
convert it to `.clausal`, or wrap it in a `.seam` module.

### Python only through `library(...)` and `.seam` modules

There is no `++expr` or other Python escape in Clausal Prolog. It reaches
Python only through:

1. **`library(...)` facades** over the engine's Python modules
   (`library(datetime)`, `library(json)`, `library(units)`, …), loaded like
   any Scryer library;
2. **Python-free `.seam` modules**: Clausal code written in seam syntax,
   checked transitively;
3. **Python bridges**: `.seam` modules that do run Python, listed under
   `[tool.clausal] python_bridges` in the nearest `pyproject.toml` above
   the importing `.clausal` file.

```prolog
% app.clausal
:- module(app, [due/1, quadruple/2]).
:- use_module(library(datetime), [date_add/3, timedelta/3]).   % a facade
:- use_module(helpers, [double/2]).                             % Python-free helpers.seam

due(D) :- timedelta(30, 0, TD), date_add(date(2026, 1, 15), TD, D).
quadruple(X, Y) :- double(X, Z), double(Z, Y).

:- end_module(app).
```

Anything else is refused at load: a `.seam` module that runs Python without
being listed raises `permission_error(import, python_bridge, M)`, and
`:- use_module(py/datetime, ...)` raises
`permission_error(access, python_module, py.datetime)`, naming the facade to
use instead. See
[Python bridges](importing_prolog.md#python-bridges-which-seam-modules-clausal-prolog-may-import).

### Python calls Prolog

The other direction is open: any Python code can query a `.clausal`
module. After `import clausal`, `import family` loads `family.clausal`. In a
`.seam` file, a goal in `for` position is the toplevel's `?-`:

```python
# ask.seam
-import_from(family, [grandparent])
-private([tom])

for GRANDCHILD in --grandparent(tom, GRANDCHILD):
    print(GRANDCHILD)
```

Answers are the engine's own terms: an atom is a Python `str`, a compound
term is a tuple `('f', 1, 2)`. From a plain `.py` file, use
`clausal.call` or `clausal.solve`. See
[Python Integration](python_integration.md#goal-position-if-goal-for-in-goal).

### [Compilation](compiler.md), not interpretation

Clausal Prolog compiles predicates to Python generator functions at import
time. There is no WAM and no interpreter loop:

- Bytecode is [cached](caching.md) in `__pycache__`
- [First-argument indexing](indexing.md) is computed at compile time
- Groundness-keyed dispatch generates specialized code paths

---

## Existing `.pl` code

A `.pl` file is regular ISO Prolog, cut included. You have two ways to run
it.

**On a real ISO engine.** The [Scryer](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scryer/docs/scryer.md) and [Trealla](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-trealla/docs/trealla.md)
embeddings run unrestricted ISO Prolog in-process, cut and all, and you
query them from Python with lazy iteration.

**On the native engine, by importing it.** Place it on `sys.path` and
import it like a module:

```python
import clausal
import my_prolog_module     # loads my_prolog_module.pl, cached as .pyc
```

!!! warning "Experimental in 1.0"
    The in-process `.pl` loader is experimental: what it accepts and how it
    names things may change in a minor release (see
    [Public API](public-api.md)). It does not run cut yet: `!` and `->` in
    a `.pl` file are refused when it loads, as they are in `.clausal`.
    That is a current limitation of this loader, not a property of `.pl`.

Cross-file `use_module` between `.pl` files works, and a `.pl` file may
import a `.clausal` module. In a `.pl` file `end_module/1` is optional.
If the same directory holds `name.clausal` and `name.pl`, the
`.clausal` file is loaded. See [Importing Prolog Code](importing_prolog.md)
for the full guide.

---

## A reminder about relational thinking

Even experienced Prolog programmers sometimes drift into procedural habits.
Clausal Prolog's documentation is written to reinforce relational thinking
throughout:

- We say predicates **describe** relations, not compute results
- We say clauses **hold** when conditions are met, not that they "match" or
  "execute"
- We encourage the **most general query** as a diagnostic
- We prefer **relational names** (nouns describing arguments) over imperative
  names (verbs describing actions)

If you've read Triska's "The Power of Prolog" or studied with Neumerkel, this
will feel natural. If not, [Thinking Relationally](thinking_relationally.md)
and [Purity and Monotonicity](purity.md) lay out these ideas explicitly.

---

## The seam: the Python-syntax boundary

The engine reads a third surface, the **seam** (`.seam`). It is Python
syntax, and it is where Python escapes (`++expr`), hosted Python
statements and the adapters over Python libraries live. Many other pages of
these docs show their examples in seam syntax. The semantics are shared;
the spellings differ:

| ISO / Clausal Prolog | Seam (`.seam`) | Notes |
|---|---|---|
| `parent(tom, bob).` | `parent(tom, bob),` | Trailing comma, not period. Bare atoms must be declared (`-module`/`-private`) or quoted. |
| `head :- a, b.` | `head <- (a, b)` | |
| `X`, `Parent` | `X`, `PARENT`, `Parent` | `ALL_CAPS` is the native style |
| `X = Y` | `X is Y` | In the seam `is` **unifies** |
| `X is E`, `X #= E` | `X == E` | In the seam `==` **evaluates** (CLP(ℤ) equality) |
| `X =\= Y`, `X #\= Y` | `X != Y` | `#` starts a Python comment |
| `\+ G` | `not G` | |
| `dif(X, Y)` | `X is not Y` or `dif(X, Y)` | |
| `a --> b, c.` | `a >> (b, c)` | |
| `:- module(m, [p/1]).` … `:- end_module(m).` | `-module(m, [p(X)])` | No `end_module` in the seam |
| `:- use_module(lib, [p/1]).` | `-import_from(lib, [p])` | |
| `:- table(p/2).` | `-table(p/2)` | |
| `M:p(X)` | `m.p(X)` | |
| `?- goal.` | `for X in --goal(X):` | In a `.seam` file |
| — | `++expr` | Python; not available in Clausal Prolog |

See [Clausal Prolog](clausal_prolog.md#differences-from-the-seam) for the
side-by-side reference and [Syntax](syntax.md) for the seam grammar.

---

## Getting started

1. Read [Clausal Prolog](clausal_prolog.md) for the surface and its rules
2. Browse the [Predicate Index](builtins.md) for the builtins
3. Look at [Examples](examples.md) for N-Queens, Sudoku, map colouring,
   and more

---

*See also: [Importing Prolog Code](importing_prolog.md) — `.pl` import,
`end_module`, `library(...)` facades and Python bridges.*

*See also: [Prolog Translation](prolog_translation.md) — translation
between seam and Prolog syntax.*

*See also: [Scryer Prolog Embedding](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scryer/docs/scryer.md) — an in-process ISO Prolog
engine for programs that need cut.*

*See also: [Thinking Relationally](thinking_relationally.md) — the mindset
behind good logic programming.*
