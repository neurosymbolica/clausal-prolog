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
- **Purity matters.** Clausal has `dif/2`, CLP(FD), CLP(B), CLP(R), reified
  if-then-else, and tabling — all the tools for staying in the pure monotonic
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
| `parent(alice, bob).` | `parent("alice", "bob"),` | Trailing comma, not period. Atoms are strings. |
| `X`, `Parent` | `X`, `PARENT` | Variables are ALLCAPS (or trailing underscore: `x_`) |
| `_` | `_` | Anonymous variable — same |
| `head :- body.` | `head <- (body)` | `<-` instead of `:-`. Multi-goal bodies parenthesized. |
| `a, b, c` (conjunction) | `a, b, c` | Same — comma is conjunction |
| `a ; b` (disjunction) | `a \| b` or separate clauses | Prefer separate clauses |
| `\+(Goal)` | `not Goal` | Python's `not` keyword |
| `X = Y` | `X is Y` | Unification uses `is` |
| `X \= Y` | `not (X is Y)` | Immediate check |
| `dif(X, Y)` | `X is not Y` or `Dif(X, Y)` | Constraint — survives |
| `X is Expr` | `X := Expr` | Arithmetic evaluation |
| `X =:= Y` | `X == Y` | Arithmetic / CLP(FD) equality |
| `X =\= Y` | `X != Y` | Arithmetic / CLP(FD) disequality |
| `X #= Y` | `X #= Y` | CLP(FD) — same |
| `append/3` | `Append/3` | Builtins are PascalCase |
| `member/2` | `In/2` | Uses Python's `in` semantics |
| `msort/2` | `MergeSort/2` | Full names, not abbreviations |
| `phrase(NT, Ls)` | `phrase(nt, LS)` | DCGs use `>>` instead of `-->` |
| `?- goal.` | `clausal.query(goal)` | From Python; or `*(goal)` in IPython |

---

## What you already know that applies directly

### Tabling (SLG resolution)

```clausal
-table(fib/2),

fib(0, 0),
fib(1, 1),
fib(N, F) <- (
    N > 1,
    N1 := N - 1,
    N2 := N - 2,
    fib(N1, F1),
    fib(N2, F2),
    F := F1 + F2
)
```

Same semantics as SWI's or XSB's tabling. The `-table` directive is
Clausal's equivalent of `:- table`.

### CLP(FD)

```clausal
-import_from(clpfd, [AllDifferent, Labeling]),

n_queens(N, QUEENS) <- (
    Length(QUEENS, N),
    QUEENS ins 1..N,
    AllDifferent(QUEENS),
    safe_queens(QUEENS)
)
```

The constraint operators (`#=`, `#<`, `#>`, `#<=`, `#>=`, `#!=`) are the same.
`ins` works as you'd expect. `AllDifferent`, `Labeling`, and other global
constraints are available as PascalCase builtins.

### DCGs

```clausal
greeting >> [hello], name,
name >> [world],
name >> [clausal],
```

`>>` is Clausal's `-->`. Terminals are lists, non-terminals are bare calls,
inline goals use `{ }` or `++()`. `phrase/2` and `phrase/3` work as expected.

### Meta-predicates

`FindAll/3`, `BagOf/3`, `SetOf/3`, `ForAll/2`, and `Call/1..8` are all
available as builtins.

### Module system

```clausal
-import_from(utils, [Double, Helper]),
-import_module(math_utils),
```

Equivalent to Prolog's `use_module` family. Qualified calls use dot notation:
`math_utils.Factorial(N, F)`.

---

## What's genuinely different

### No cut, by design

Clausal does not have `!/0`. The design philosophy is that cut destroys
monotonicity, separability, and multi-directional use — all the properties
that make logic programming worthwhile.

Where you would use green cuts in Prolog, Clausal offers:

- **First-argument indexing** — automatic, no manual intervention needed
- **Reified if-then-else** — `(THEN if COND else ELSE)` with monotonic, three-valued semantics
- **CLP(FD) and dif/2** — replace cut-based pruning with constraints
- **Groundness-keyed dispatch** — the compiler generates specialized code
  paths based on which arguments are ground

### Atoms are strings

Prolog's atoms (`foo`, `bar`, `'hello world'`) are Python strings in Clausal
(`"foo"`, `"bar"`, `"hello world"`). There is no separate atom type. This
simplifies interop with Python — every Python string is a valid Clausal term.

### Naming conventions

| Prolog convention | Clausal convention |
|---|---|
| `lowercase_atoms` for predicates | `lowercase` for user predicates |
| `TitleCase` for variables | `ALLCAPS` for variables |
| `abbreviations` (`msort`, `succ`, `nb_getval`) | Full names (`MergeSort`, `Successor`, ...) |
| `library(lists)` | `PascalCase` builtins (`Append`, `In`, `Sort`) |

The philosophy: spell out names. Only keep abbreviations that are the
universal name (e.g., `DCG`, `CLP`). This makes code readable without
memorizing a shorthand lexicon.

### Python interop is native

You can call any Python expression from within a clause using `++()`:

```clausal
word_count(TEXT, N) <- (N is ++len(TEXT.split()))
```

And call any Clausal predicate from Python:

```python
from my_module import reachable
solutions = list(clausal.query(reachable("a", DEST)))
```

No subprocess, no marshalling, no FFI. Logic predicates are Python classes.
Logic variables are Python objects. Everything runs on one VM.

### Compilation, not interpretation

Clausal compiles predicates to Python generator functions at import time.
There is no interpreter loop. This means:

- Bytecode is cached in `__pycache__`
- First-argument indexing is computed at compile time
- Groundness-keyed dispatch generates specialized code paths
- The Python JIT (3.13+) can optimize hot paths

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

*See also: [Thinking Relationally](thinking_relationally.md) — the mindset
behind good logic programming.*
