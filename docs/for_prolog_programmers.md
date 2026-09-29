# Clausal for Prolog Programmers

You know Prolog. You think in relations, you read clauses declaratively, and
you reach for the most general query to understand a predicate. This page tells
you what's the same, what's different, and how to translate your knowledge.

---

## The philosophy is the same

Clausal is built on the same foundations you know:

- **Predicates define relations.** Clauses state conditions under which
  relations hold. Facts are unconditionally true. Rules have bodies.
- **Unification is bidirectional.** Variables on either side can be bound.
- **Search is via backtracking.** Multiple clauses are logical alternatives.
- **[Purity](purity.md) matters.** Clausal has [`dif/2`](constraints.md), [CLP(ℤ)](constraints.md), [CLP(B)](clpb.md), [CLP(ℝ)](clpr.md), [reified
  if-then-else](reified_ite.md), and [tabling](tabling.md) — all the tools for staying in the pure monotonic
  core.
- **No cut.** Clausal does not have `!/0`, by design.

The intellectual debt to Markus Triska's "The Power of Prolog" and Ulrich
Neumerkel's work on purity is explicit and pervasive.

---

## Syntax at a glance

All Clausal code is valid Python syntax. This is the fundamental design
constraint — it means Python tooling (editors, linters, formatters) works
out of the box, but some Prolog conventions must change.

| Prolog | Clausal | Notes |
|---|---|---|
| `parent(alice, bob).` | `parent(alice, bob),` | Trailing comma, not period. Atoms are written bare (declare them in `-module`/`-private`) or single-quoted (`'alice'`, no declaration needed); each is the interned Python `str` itself. A double-quoted `"alice"` is a **string** (a character list), as in Scryer and Trealla; [`-double_quotes(atom)`](directives.md#-double_quotes) is a temporary per-module setting that reads it as an atom instead. |
| `X`, `Parent` | `X`, `PARENT` | Variables are ALLCAPS (or leading underscore: `_x`) |
| `_` | `_` | Anonymous variable — same |
| `_Foo` singleton silently allowed | [`_UNUSED` suffix](syntax.md#singleton-variables-and-_unused) (`_foo_UNUSED`, `FOO_UNUSED`) | Clausal warns by default on *any* named variable used once, in both styles — matching SWI's `singleton variable` warning, but the suppression is a **suffix**, not a leading-underscore reading. Leading underscore is already a first-class variable *style* here (`_x`), so it can't double as "don't warn" too — and a case-based exemption would be blind for caseless-script variables, which are forced into leading-underscore spelling. `-allow_singletons` opts a whole file out. An imported `.pl` file keeps the Prolog reading: its `_Foo` is not warned about. |
| — (no equivalent) | [`++pi`](syntax.md#constants) module-level constant | Prolog has no compile-time constants — the nearest idiom is a fact plus an extra goal (`pi_value(PI), A #= PI * R * R`). Clausal's `-constant_value(pi, 3.14159)` binds a module global; `++pi` is the value (`A == ++pi * R * R`), while a bare `pi` is the atom `pi` and must be declared like any other atom. See [Constants](syntax.md#constants). The Prolog exporter substitutes the value. |
| `head :- body.` | `head <- (body)` | `<-` instead of `:-`. Multi-goal bodies parenthesized. |
| `a, b, c` (conjunction) | `a, b, c` | Same — comma is conjunction |
| `a ; b` (disjunction) | `(a or b)` or separate clauses | Prefer separate clauses |
| `\+(Goal)` | `not Goal` | Python's `not` keyword |
| `X = Y` | `X is Y` | Unification uses `is` |
| `X \= Y` | `not (X is Y)` | Immediate check |
| `dif(X, Y)` | `X is not Y` or `dif(X, Y)` | Constraint — survives |
| `X is Expr` | `'is'(X, Expr)` or `eval_(Expr, X)` | Eager arithmetic evaluation — the quoted `'is'` is ISO `is/2`; a bare `X is Y` is unification. Prefer `X == Expr` (CLP). See [Operators](operators.md) and [Arithmetic](arithmetic.md) |
| `X =:= Y` | `X == Y` | Arithmetic / CLP(ℤ) equality |
| `X =\= Y` | `X != Y` | Arithmetic / CLP(ℤ) disequality |
| `X #= Y` | `X == Y`, or `'#='(X, Y)` | `#` starts a Python comment, so the CLP(ℤ) operators are written as Python comparisons (or quoted) |
| `append/3` | `append/3` | Same — builtins are `snake_case` |
| `member/2` | `in_/2` | Uses Python's `in` semantics |
| `msort/2` | `msort/2` | Full names, not abbreviations |
| `phrase(NT, Ls)` | `phrase(nt, LS)` | DCGs use `>>` instead of `-->` |
| `?- goal.` | `for X in --goal(X):` | In a `.clausal`/`.seam` file ([goal position](python_integration.md#goal-position-if-goal-for-in-goal)); `solve(goal, module=m)` from a plain `.py` file; `*(goal)` in IPython |

---

## What you already know that applies directly

### Tabling (SLG resolution)

```clausal
-table(fib/2)

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
```

Same semantics as SWI's or XSB's [tabling](tabling.md). The `-table` [directive](directives.md) is
Clausal's equivalent of `:- table`.

### CLP(ℤ)

```clausal
-private([safe_queens(QS), no_attack(Q, QS, D)])

n_queens(N, QUEENS) <- (
    length(QUEENS, N),
    in_domain(QUEENS, 1, N),
    all_different(QUEENS),
    safe_queens(QUEENS),
    label(QUEENS)
)

safe_queens([]),
safe_queens([Q, *QS]) <- (
    no_attack(Q, QS, 1),
    safe_queens(QS)
)

no_attack(_, [], _),
no_attack(Q, [Q1, *QS], D) <- (
    Q != Q1 + D,
    Q != Q1 - D,
    D1 == D + 1,
    no_attack(Q, QS, D1)
)

test("the first 6-queens placement") <- once(n_queens(6, [2, 4, 6, 1, 3, 5]))
```

`#` starts a Python comment, so the constraint operators are spelled as
Python comparisons: `==`, `!=`, `<`, `>`, `<=`, `>=` post CLP(ℤ) constraints
(`#=`, `#\=`, `#<`, …); the quoted forms (`'#='(X, Y)`) also work.
`X ins 1..N` is `in_domain(X, 1, N)` and `labeling/2` is `label/1`
(first-fail). `all_different` and the other global constraints are builtins,
in scope without an import. See [Constraints](constraints.md).

### DCGs

```clausal
greeting >> (['hello'], name)
name >> ['world']
name >> ['clausal']

test("parse") <- phrase(greeting, ['hello', 'world'])
test("generate") <- findall(S, phrase(greeting, S), [['hello', 'world'], ['hello', 'clausal']])
```

`>>` is Clausal's `-->`. Terminals are lists, non-terminals are bare calls,
inline goals use `{ }` or `++()`. `phrase/2` and `phrase/3` work as expected. See [DCGs](dcg.md) for the full reference.

### [Meta-predicates](meta_predicates.md)

[`findall/3`, `bagof/3`, `setof/3`](meta_predicates.md), `forall/2`, and [`call/1..8`](higher_order.md) are all
available as builtins.

### [Module system](import.md)

```clausal
-import_from(py.csv, [parse_row])
-import_module(py.json)

row_fields(LINE, FIELDS) <- parse_row(LINE, FIELDS)
json_value(TEXT, VALUE) <- py.json.parse(TEXT, VALUE)

test("a qualified call") <- (json_value("[1, 2]", V), V is [1, 2])
```

`-import_from` is `use_module/2` and `-import_module` is `use_module/1` with
every call qualified. Qualified calls use dot notation: `py.json.parse(T, V)`,
where Prolog writes `m:p(X)`; a qualified call is also how two modules'
same-named predicates are told apart (there is no `as` rename in ISO or
Scryer, and none in `.pl` import). An import entry `p/1` imports one arity,
as `use_module(m, [p/1])` does; a bare `p` imports every arity. A procedure
is a name and an arity, as in ISO: `p/1` and `p/2` may share a file.

> **One genuine difference — read this.** Names resolve **lexically, against the
> defining module** (Python-style): there is no flat global predicate database
> and no implicit `meta_predicate` context-module threading. A library predicate
> sees the names in *its own file*, never the caller's, so to call back into a
> predicate the importer owns you **pass it in as a goal argument**. (Modular
> SWI/SICStus resolves ordinary calls the same way — what's gone is the implicit
> module-threading of meta-predicates.) See
> [Name resolution is lexical, not dynamic](import.md#name-resolution-is-lexical-pythonic-not-dynamic-prolog).

---

## What's genuinely different

### No cut, by design

Clausal does not have `!/0`. The design philosophy is that cut destroys
monotonicity, separability, and multi-directional use — all the properties
that make logic programming worthwhile.

Where you would use green cuts in Prolog, Clausal offers:

- **[First-argument indexing](indexing.md)** — automatic, no manual intervention needed
- **[Reified if-then-else](reified_ite.md)** — `(THEN if COND else ELSE)` with monotonic, three-valued semantics
- **[CLP(ℤ) and dif/2](constraints.md)** — replace cut-based pruning with constraints
- **Groundness-keyed dispatch** — the [compiler](compiler.md) generates specialized code
  paths based on which arguments are ground

### Atoms

An atom **is** the interned Python `str` — no wrapper — and is compared with
**`==`** (interning makes `is` agree too, but `==` is the test to write).
Write one bare (`red`, declared in `-private`/`-module`, or imported) or
single-quoted (`'hello world'`, no declaration needed).

A double-quoted `"red"` is a **string** — the list of its character atoms,
`-double_quotes(chars)`, the default in Scryer and Trealla. Atoms and strings
never unify. [`-double_quotes(atom)`](directives.md#-double_quotes) is a
temporary per-module setting for old code. See
[Atoms vs strings](syntax.md#atoms-vs-strings).

### Standards: ISO first, then Scryer

Where ISO 13211-1 speaks, Clausal follows it; where ISO is silent, it follows
Scryer Prolog (not SWI). Two places you will notice:

- **Error terms** are ISO `error(Formal, Context)` terms in Scryer's form: the
  context is the culprit's predicate indicator, and the printed exception
  shows the term first —
  `Uncaught logic exception: error(type_error(atom,1),atom_length/2)`. See
  [Exceptions](exceptions.md).
- **The database is declare-first.** `assertz`/`retract` work only on a
  predicate declared `-dynamic(name/arity)`; a static one raises
  `permission_error(modify, static_procedure, Name/Arity)`.

[Operators](operators.md) lists which spellings follow Python and which follow
Scryer: bare `-7 // 2` is `-4` (Python floor division), quoted
`'//'(-7, 2)` is `-3` (ISO truncation).

### Naming conventions

| Prolog convention | Clausal convention |
|---|---|
| `lowercase_atoms` for predicates | `snake_case` for predicates and builtins (`append`, `in_`, `read_file`, `find_path`) |
| `TitleCase` for variables | `TitleCase` works unchanged (`Foo`, `Total`); `ALL_CAPS` or leading `_lowercase` are the native styles (`X`, `LIST`, `SAMPLE_SIZE`, `_rest`) |
| `TitleCase` for compound functors | `snake_case`, declared via `-module`/`-private` (`red`, `point(X, Y)`) — a *bare* `TitleCase` functor is a load error (quote it, `'Foo'(X)`, to mean the atom), and a Python class is reached as `++Name` |
| `abbreviations` (`nb_getval`) | spell names out; keep only universal abbreviations (`DCG`, `CLP`, `msort`, `succ`) |

A Prolog variable therefore needs no transliteration: `p(Foo) :- bar(Foo).` becomes
`p(Foo) <- (bar(Foo))` with the spelling intact. A Prolog *functor* does, because that is the
one position where the two languages disagree — see
[One asymmetry: TitleCase in functor position](syntax.md#one-asymmetry-titlecase-in-functor-position).

`snake_case` for predicates is a **convention, not a language rule** — the parser accepts any
lowercase-initial identifier. It mirrors Python's standard library and SWI-Prolog, so code reads
naturally and LLMs trained on Prolog generate it reliably; where the two pull apart, Python-side
consistency wins.

The philosophy: spell out names. Only keep abbreviations that are the
universal name (e.g., `DCG`, `CLP`). This makes code readable without
memorizing a shorthand lexicon.

### Python interop is native

You can call any Python expression from within a clause using [`++()`](python_integration.md):

```clausal
word_count(TEXT, N) <- (N is ++len(TEXT.split()))
```

And query any predicate from Python hosted in a `.clausal` or `.seam` file —
`--goal` in goal position is Clausal's `?-`:

```python
# report.seam
-import_module(graph)

def destinations(source):
    return [DEST for DEST in --graph.reachable(++source, DEST)]
```

From a plain `.py` file, build the goal as a cell (a tuple: the name, then
the arguments) and run it against its module:

```python
from clausal import Var, solve
import graph

for trail in solve(("reachable", "a", DEST := Var()), module=graph):
    print(DEST.value)
```

No subprocess, no marshalling, no FFI. Answers are the engine's own terms: an
atom is a Python `str`, a compound term is a tuple `('f', 1, 2)`, a string is
`('$chars', text)`; `clausal.to_python` converts one deeply. See
[Python Integration](python_integration.md).

### [Compilation](compiler.md), not interpretation

Clausal compiles predicates to Python generator functions at import time.
There is no interpreter loop. This means:

- Bytecode is [cached](caching.md) in `__pycache__`
- [First-argument indexing](indexing.md) is computed at compile time
- Groundness-keyed dispatch generates specialized code paths
- The Python JIT (3.13+) can optimize hot paths

---

## Importing existing Prolog code

!!! warning "Experimental in 1.0"
    `.pl` import goes through a translator that is being replaced; what it
    accepts and how it names things may change in a minor release (see
    [Public API](public-api.md)).

You don't have to rewrite your `.pl` files to use them in Clausal. Place them
on `sys.path` and import directly:

```python
import clausal
import my_prolog_module     # translates my_prolog_module.pl on the fly
```

The `.pl` file is translated to Clausal syntax, compiled, and cached as
`.pyc` bytecode. Subsequent imports skip translation entirely.

Cross-file `use_module` works too — if `main.pl` uses
`:- use_module(helpers, [double/1]).`, importing `main` will recursively
translate and load `helpers.pl`.

**What works:** facts, rules, arithmetic, lists, DCGs, `dynamic`,
`discontiguous`, `table`, `use_module` with import lists.

**What doesn't:** cut (`!`) and if-then-else (`->`) are rejected with clear
error messages — see [Importing Prolog](importing_prolog.md) for details.

See [Importing Prolog Code](importing_prolog.md) for the full guide.

---

## A reminder about relational thinking

Even experienced Prolog programmers sometimes drift into procedural habits.
Clausal's documentation is written to reinforce relational thinking throughout:

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

## Getting started

1. Read the [Syntax reference](syntax.md) for the full mapping
2. Browse the [Predicate Index](builtins.md) — most Prolog builtins have
   Clausal equivalents
3. Try the [IPython REPL](ipython.md) — `*(goal)` is Clausal's toplevel
4. Look at [Examples](examples.md) for N-Queens, Sudoku, map colouring,
   and more

---

*See also: [Syntax](syntax.md) — complete grammar and operator reference.*

*See also: [Prolog Translation](prolog_translation.md) — automatic
bidirectional translation between Clausal and Prolog syntax.*

*See also: [Scryer Prolog Embedding](scryer.md) — if you want to run your
Prolog programs on an actual ISO Prolog engine, Clausal embeds Scryer Prolog
in-process. Load `.clausal` or `.pl` files and query with lazy iteration —
no subprocess, no serialisation overhead.*

*See also: [Thinking Relationally](thinking_relationally.md) — the mindset
behind good logic programming.*
