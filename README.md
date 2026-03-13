# clausal

A Prolog-style logic programming DSL embedded in Python, built on a simplified AST and a generator-based trampoline.

## Modules

- **`clausal.simple_ast`** — Simplified Python AST with context-split nodes (no `Load`/`Store` context fields; separate `LoadName`/`StoreName` etc. types).
- **`clausal.conversion`** — Converts CPython `ast` trees into `simple_ast` nodes.
- **`clausal.term_rewriting`** — `TermTransformer` and `EmbedTransformer`: DSL syntax (`--expr`, `head<-body`, trailing-comma facts, `with the_following`) rewritten to `simple_ast` constructors.
- **`clausal.template_compiler`** — `@{}`-decorated function templates that expand to AST-building functions.
- **`clausal.trampoline`** — Generator-based trampoline with `Step`/`trampoline()` for stack-safe recursive computations.
- **`clausal.continuation_search`** — `Search`: greenlet-based iterator for continuation-passing search functions.
- **`clausal.import_hook`** — Import hook for `.clausal` predicate modules; `enable_ipython()` for interactive use.
- **`clausal.simple_ast_node`** — `@node_class` decorator that generates `visit_children`, `transform_children`, and `__call__` via AST.
- **`clausal.logic.variables`** — Prolog-style logic variables, attributed variables, and trail-based backtracking (C extension, WAM-less).
- **`clausal.logic.constraints`** — Constraint solvers: `dif/2` disequality constraint via attributed variables.
- **`clausal.logic.tabling`** — SLG tabling: memoised subgoal calls with suspension/resumption for termination.

## Installation

```bash
pip install clausal
```

## Quick start

```python
import ast
from clausal import simple_ast

tree = ast.parse("x = 1 + 2")
simple = simple_ast.simplify(tree)
print(simple_ast.dump(simple))
```

### Embedding DSL terms

```python
from clausal.import_hook import enable_ipython
enable_ipython(globals())   # in IPython / Jupyter

result = --(x + y)   # produces simple_ast.Add node
```

### Prolog-style predicates

```python
# family.clausal      ← .clausal extension activates the import hook
parent(tom, bob)<-True,
parent(bob, ann)<-True,
```

## Testing

`.clausal` files can include inline tests as `test/1` clauses:

```
test("fib(5) = 5") <- fib(5, 5)
```

A test passes if its body produces at least one solution.

**Standalone runner** (no pytest needed):

```bash
python -m clausal.testing clausal/examples/           # all .clausal files
python -m clausal.testing clausal/examples/hanoi.clausal  # single file
python -m clausal.testing -v clausal/examples/        # verbose
```

**Via pytest** (`.clausal` tests are collected automatically alongside Python tests):

```bash
python -m pytest clausal/examples/ -v        # just .clausal tests
python -m pytest tests/ clausal/examples/ -q  # everything together
```

See [docs/testing.md](docs/testing.md) for details.

## Requirements

- Python ≥ 3.14
- [greenlet](https://pypi.org/project/greenlet/) (for `clausal.continuation_search`)

## License

MIT

---

## `clausal.logic.variables` — Logic variables and backtracking

A C extension implementing Prolog-style **logic variables** and **trail-based backtracking** without a Warren Abstract Machine. Derived by studying GNU Prolog (`wam_inst.h`, `unify.c`) and Scryer Prolog (`machine_state_impl.rs`, `unify.rs`).

### Quick start

```python
from clausal.logic.variables import Var, Trail, unify, walk, is_var

trail = Trail()

X = Var()
Y = Var()

# Unify X with 42
assert unify(X, 42, trail)
assert X.value == 42

# Unify a compound term
A = Var()
assert unify(("point", A, 0), ("point", 3, 0), trail)
assert A.value == 3

# Backtrack
mark = trail.mark()
unify(Y, "temporary", trail)
assert Y.value == "temporary"
trail.undo(mark)
assert is_var(Y)           # Y is unbound again
```

### API Reference

#### `Var()`

Create an unbound logic variable.

| Property | Type | Description |
|----------|------|-------------|
| `is_bound` | `bool` | `True` if this variable has been assigned any value, including another `Var`. Use `is_var()` to test for a ground binding. |
| `value` | any | The fully dereferenced value (follows the binding chain). Returns `self` if unbound. |
| `_id` | `int` | Monotonic creation counter. Newer vars (larger `_id`) are bound to older ones in var-var unification. |

Variables are hashable and use identity-based equality — suitable as dict keys.

---

#### `Trail()`

Records variable bindings so they can be undone during backtracking.

- **`trail.mark() -> int`** — Return the current trail length as a backtrack mark. Save before a speculative computation; pass to `undo()` to roll back.
- **`trail.undo(mark: int)`** — Restore all bindings recorded after `mark`. Processes entries in reverse chronological order. `unify()` calls this automatically on failure.
- **`trail.reset()`** — Undo every binding. Equivalent to `trail.undo(0)`.
- **`len(trail)`** — Number of recorded bindings.

---

#### `unify(t1, t2, trail) -> bool`

Try to unify two terms under `trail`. Returns `True` on success (bindings recorded on `trail`). Returns `False` on failure — **partial bindings are automatically rolled back**.

**Term representation:**

| Python type | Prolog analogue |
|-------------|----------------|
| `Var` | unbound variable |
| `tuple` | compound term — elements unified pairwise |
| `list` | sequence — elements unified pairwise |
| any other | atomic — compared with `==` |

In a `Var`–`Var` unification, the newer variable (larger `_id`) is bound to the older one, keeping the oldest as the canonical representative. Without `unify_with_occurs_check()`, binding `X` to `f(X)` succeeds and creates a cyclic term.

---

#### `unify_with_occurs_check(t1, t2, trail) -> bool`

Like `unify()` but fails if the variable being bound appears free anywhere in the term, preventing circular terms.

```python
x = Var()
unify_with_occurs_check(x, ("f", x), trail)   # False — would be circular
```

---

#### `deref(term) -> term`

Follow the variable binding chain to its root. Returns `self` if unbound. Does not recurse into compound subterms — use `walk()` for deep substitution.

---

#### `walk(term) -> term`

Deeply substitute all bound variables throughout a term. Rebuilds tuples and lists with bound vars replaced by their values; unbound vars are left in place. Returns a new object.

```python
x = Var()
unify(x, 5, trail)
walk(("f", x, [x, 2]))   # → ("f", 5, [5, 2])
```

---

#### `is_var(term) -> bool`

Return `True` if `term` dereferences to an unbound `Var`.

---

#### `occurs_check(var, term) -> bool`

Return `True` if `var` appears free anywhere inside `term`. Used to detect would-be circular bindings before calling `unify()`.

---

### Backtracking pattern

```python
from clausal.logic.variables import Var, Trail, unify

def solve(goal, trail):
    for clause_head, clause_body in database:
        mark = trail.mark()
        head = rename(clause_head)   # fresh vars per invocation
        if unify(goal, head, trail):
            yield from solve_body(clause_body, trail)
        trail.undo(mark)   # backtrack before trying next clause
```

`unify()` already rolls back on failure, so `trail.undo(mark)` is only needed to undo successful bindings when moving to the next alternative.

### Constraints

Logic variables support constraints via the attributed variable infrastructure. The `dif/2` constraint ensures two terms remain different:

```python
from clausal.logic.variables import Var, Trail, unify
from clausal.logic.constraints import dif

trail = Trail()
x, y = Var(), Var()

dif(x, y, trail)       # post constraint: x ≠ y
unify(x, 1, trail)     # ok — constraint re-checked, still satisfiable
unify(y, 2, trail)     # ok — constraint satisfied (1 ≠ 2)

# But:
trail2 = Trail()
a, b = Var(), Var()
dif(a, b, trail2)
unify(a, 1, trail2)
unify(b, 1, trail2)    # False — constraint violated (1 = 1)
```

In `.clausal` files, `is not` has dif semantics:
```
safe(X_, Y_) <- (X_ is not Y_ and X_ is 1 and Y_ is 2)  # succeeds
```

See [docs/constraints.md](docs/constraints.md) for details.

### Notes

- **Partial lists** (`[H|T]` where `T` is a variable) are not directly supported. Use a tuple `(".", H, T)` or a dedicated cons type built on top of `Var`.
- **Dicts** are treated as atomic (compared by `==`). Wrap in tuples to unify dict-structured terms.
- **Thread safety:** not thread-safe. Use a separate `Trail` per thread and avoid sharing `Var` objects between threads without external locking.
