# clausal

A Prolog-style logic programming DSL embedded in Python. write relational logic
programs in `.clausal` source files that load via Python's standard import
system, with full constraint solving, tabling, DCGs, and a rich standard library.

## Features

- **`.clausal` source files** — import logic modules with Python's standard import system
- **Prolog-style predicates** — Horn clauses, unification, backtracking search
- **Constraint solving** — CLP(FD) for integers, CLP(B) for booleans, `dif/2` disequality
- **SLG tabling** — memoised subgoal calls for termination on cyclic structures
- **DCGs** — Definite Clause Grammars with `>>` syntax and `Phrase/2,3`
- **Well-Founded Semantics** — negation-as-failure for tabled predicates
- **Module system** — `-import_from/2`, `-import_module/1`, qualified calls
- **Meta-predicates** — `findall/3`, `bagof/3`, `setof/3`, `forall/2`, `Call/N`
- **Higher-order** — `maplist/2,3`, `foldl/4`, `include/3`, `exclude/3`
- **Python interop** — `++expr` escape, lambda goal closures, f-string support in terms
- **SciPy integration** — wrappers for `scipy.special`, `scipy.linalg`, `scipy.optimize`, `scipy.interpolate`, `scipy.signal`
- **Regex** — `match/2,3`, `search/2,3`, `replace/4`, `split/3` with auto-binding goal expansion
- **Term expansion** — macro system for source-level term rewriting
- **C extensions** — fast logic variables, trail-based backtracking, trampoline (no WAM)

## Installation

```bash
pip install clausal
```

Requires Python ≥ 3.13 and a C compiler (used automatically by pip when building from source).

## Quick start

### `.clausal` source files

Facts use a trailing comma. Rules use `<-` with a parenthesised, comma-separated body.
Predicate names are lowercase (`snake_case` by convention); variables are ALL_CAPS.

```prolog
# family.clausal
parent(tom, bob),
parent(tom, liz),
parent(bob, ann),
parent(bob, pat),

grandparent(X, Z) <- (parent(X, Y), parent(Y, Z))
```

```python
import family   # .clausal files load via the import hook

from clausal import call, deref, Var

GRANDCHILD = Var()
results = [deref(GRANDCHILD) for _ in call("Grandparent", "tom", GRANDCHILD, module=family)]
# → ['ann', 'pat']
```

### Arithmetic

```prolog
# fib.clausal
Fib(0, 0),
Fib(1, 1),
Fib(N, RESULT) <- (
    N > 1,
    N1 := N - 1,
    N2 := N - 2,
    Fib(N1, A),
    Fib(N2, B),
    RESULT := A + B
)
```

### Tabling (memoisation for cyclic graphs)

```prolog
-table(Path/2)

Edge(1, 2),
Edge(2, 3),
Edge(3, 1),

Path(X, Y) <- Edge(X, Y)
Path(X, Y) <- (Edge(X, Z), Path(Z, Y))
```

### DCGs

```prolog
Sentence >> (NounPhrase, VerbPhrase)
NounPhrase >> (["the", "dog"] or ["the", "cat"])
VerbPhrase >> (["runs"] or ["barks"])
```

```python
from clausal import once
result = once(call("Phrase", "Sentence", ["the", "cat", "runs"], module=grammar))
```

### CLP(FD) — constraint logic programming over integers

```prolog
Sendmoney(S, E, N, D, M, O, R, Y) <- (
    in_domain([S, E, N, D, M, O, R, Y], 0, 9),
    all_different([S, E, N, D, M, O, R, Y]),
    S != 0,
    M != 0,
    label([S, E, N, D, M, O, R, Y]),
    SEND  := S * 1000 + E * 100 + N * 10 + D,
    MORE  := M * 1000 + O * 100 + R * 10 + E,
    MONEY := M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    SEND + MORE == MONEY
)
```

### Meta-predicates

```prolog
Squares(Ns, Squares) <- (
    findall(
        Sq,
        (in_(X, Ns), Sq := X * X),
        Squares
    )
)
```

## Testing

`.clausal` files can include inline tests as `Test/1` clauses:

```prolog
Test("fib(5) = 5") <- Fib(5, 5)
Test("tom's grandchildren") <- (
    Grandparent(tom, ann),
    Grandparent(tom, pat)
)
```

**Standalone runner:**

```bash
python -m clausal.testing clausal/examples/           # all .clausal files
python -m clausal.testing clausal/examples/hanoi.clausal  # single file
python -m clausal.testing -v clausal/examples/        # verbose
```

**Via pytest** (`.clausal` tests collected automatically):

```bash
python -m pytest tests/ clausal/examples/ -q
```

## Logic variables and backtracking

The C extension `clausal.logic.variables` provides Prolog-style logic variables
and trail-based backtracking without a Warren Abstract Machine.

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
- [pyyaml](https://pypi.org/project/PyYAML/) ≥ 6.0
- C compiler (for building from source)

## License

MIT
