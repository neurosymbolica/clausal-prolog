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
| `parent(alice, bob).` | `parent("alice", "bob"),` | Trailing comma, not period. Undeclared atoms are strings; declared atoms are zero-arity classes. |
| `X`, `Parent` | `X`, `PARENT` | Variables are ALLCAPS (or leading underscore: `_x`) |
| `_` | `_` | Anonymous variable — same |
| `head :- body.` | `head <- (body)` | `<-` instead of `:-`. Multi-goal bodies parenthesized. |
| `a, b, c` (conjunction) | `a, b, c` | Same — comma is conjunction |
| `a ; b` (disjunction) | `a \| b` or separate clauses | Prefer separate clauses |
| `\+(Goal)` | `not Goal` | Python's `not` keyword |
| `X = Y` | `X is Y` | Unification uses `is` |
| `X \= Y` | `not (X is Y)` | Immediate check |
| `dif(X, Y)` | `X is not Y` or `dif(X, Y)` | Constraint — survives |
| `X is Expr` | `eval_(Expr, X)` | Eager arithmetic evaluation; prefer `X == Expr` (CLP) |
| `X =:= Y` | `X == Y` | Arithmetic / CLP(ℤ) equality |
| `X =\= Y` | `X != Y` | Arithmetic / CLP(ℤ) disequality |
| `X #= Y` | `X #= Y` | CLP(ℤ) — same |
| `append/3` | `append/3` | Same — builtins are `snake_case` |
| `member/2` | `in_/2` | Uses Python's `in` semantics |
| `msort/2` | `msort/2` | Full names, not abbreviations |
| `phrase(NT, Ls)` | `phrase(nt, LS)` | DCGs use `>>` instead of `-->` |
| `?- goal.` | `for trail in goal:` | From Python; or `*(goal)` in IPython |

---

## What you already know that applies directly

### Tabling (SLG resolution)

```clausal
-table(fib/2),

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
-import_from(clpfd, [all_different, labeling]),

n_queens(N, QUEENS) <- (
    length(QUEENS, N),
    QUEENS ins 1..N,
    all_different(QUEENS),
    safe_queens(QUEENS)
)
```

The constraint operators (`#=`, `#<`, `#>`, `#<=`, `#>=`, `#!=`) are the same.
`ins` works as you'd expect. `all_different`, `labeling`, and other global
constraints are available as `snake_case` builtins.

### DCGs

```clausal
greeting >> [hello], name,
name >> [world],
name >> [clausal],
```

`>>` is Clausal's `-->`. Terminals are lists, non-terminals are bare calls,
inline goals use `{ }` or `++()`. `phrase/2` and `phrase/3` work as expected. See [DCGs](dcg.md) for the full reference.

### [Meta-predicates](meta_predicates.md)

[`findall/3`, `bagof/3`, `setof/3`](meta_predicates.md), `forall/2`, and [`Call/1..8`](higher_order.md) are all
available as builtins.

### [Module system](import.md)

```clausal
-import_from(utils, [Double, Helper]),
-import_module(math_utils),
```

equivalent to Prolog's `use_module` family. Qualified calls use dot notation:
`math_utils.Factorial(N, F)`.

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

Atoms declared in `-private` or `-module` directives are zero-arity
PredicateMeta classes with identity semantics (`red() is red`). Undeclared
atoms (string literals like `"foo"`, `"bar"`) remain plain Python strings.
Both work in unification and pattern matching.

### Naming conventions

| Prolog convention | Clausal convention |
|---|---|
| `lowercase_atoms` for predicates | `snake_case` for predicates and builtins (`append`, `in_`, `read_file`, `find_path`) |
| `TitleCase` for variables | `ALL_CAPS` (or leading `_lowercase`) for variables (`X`, `LIST`, `SAMPLE_SIZE`, `_rest`) |
| `TitleCase` for compound functors | `TitleCase` for atoms and functors declared via `-module`/`-private` (`Red`, `Point(X, Y)`) |
| `abbreviations` (`nb_getval`) | spell names out; keep only universal abbreviations (`DCG`, `CLP`, `msort`, `succ`) |

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

And call any Clausal predicate from Python:

```python
from clausal import Var
from my_module import reachable

for trail in reachable("a", DEST := Var()):
    print(DEST.value)
```

No subprocess, no marshalling, no FFI. Logic predicates are Python classes.
Logic variables are Python objects. Everything runs on one VM.

### [Compilation](compiler.md), not interpretation

Clausal compiles predicates to Python generator functions at import time.
There is no interpreter loop. This means:

- Bytecode is [cached](caching.md) in `__pycache__`
- [First-argument indexing](indexing.md) is computed at compile time
- Groundness-keyed dispatch generates specialized code paths
- The Python JIT (3.13+) can optimize hot paths

---

## Importing existing Prolog code

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
error messages. Bare lowercase atoms (like `red`, `foo`) used as data values
need to be quoted strings or integers — see
[Importing Prolog](importing_prolog.md) for details.

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
