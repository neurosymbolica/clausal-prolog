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
results = [deref(GRANDCHILD) for _ in call("grandparent", "tom", GRANDCHILD, module=family)]
# → ['ann', 'pat']
```

### Arithmetic

```prolog
# fib.clausal
fib(0, 0),
fib(1, 1),
fib(N, RESULT) <- (
    N > 1,
    N1 == N - 1,
    N2 == N - 2,
    fib(N1, A),
    fib(N2, B),
    RESULT == A + B
)
```

### Tabling (memoisation for cyclic graphs)

```prolog
-table(path/2)

edge(1, 2),
edge(2, 3),
edge(3, 1),

path(X, Y) <- edge(X, Y)
path(X, Y) <- (edge(X, Z), path(Z, Y))
```

### DCGs

```prolog
sentence >> (noun_phrase, verb_phrase)
noun_phrase >> (["the", "dog"] or ["the", "cat"])
verb_phrase >> (["runs"] or ["barks"])
```

```python
from clausal import once
result = once(call("phrase", "sentence", ["the", "cat", "runs"], module=grammar))
```

### CLP(FD) — constraint logic programming over integers

```prolog
sendmoney(S, E, N, D, M, O, R, Y) <- (
    in_domain([S, E, N, D, M, O, R, Y], 0, 9),
    all_different([S, E, N, D, M, O, R, Y]),
    S != 0,
    M != 0,
    label([S, E, N, D, M, O, R, Y]),
    SEND  == S * 1000 + E * 100 + N * 10 + D,
    MORE  == M * 1000 + O * 100 + R * 10 + E,
    MONEY == M * 10000 + O * 1000 + N * 100 + E * 10 + Y,
    SEND + MORE == MONEY
)
```

### Meta-predicates

```prolog
squares(NS, SQUARES) <- (
    findall(
        SQ,
        (in_(X, NS), SQ == X * X),
        SQUARES
    )
)
```

## Testing

`.clausal` files can include inline tests as `test/1` clauses:

```prolog
test("fib(5) = 5") <- fib(5, 5)
test("tom's grandchildren") <- (
    grandparent(tom, ann),
    grandparent(tom, pat)
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
