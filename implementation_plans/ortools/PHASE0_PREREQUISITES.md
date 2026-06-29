# Phase 0: Prerequisites

Exact imports, helper functions, conventions, and API reference that all
subsequent phases depend on.  Read this first.

---

## 1. Variable Primitives

All variable operations come from one module:

```python
from clausal.logic.variables import (
    Var,        # AttVar — the logic variable type
    Trail,      # Trail object for backtracking
    deref,      # Follow variable bindings: deref(x) -> bound value or x if unbound
    is_var,     # True if term is an unbound variable
    unify,      # unify(t1, t2, trail) -> bool; binds variables on success
    put_attr,   # put_attr(var, key, value, trail) — store attribute, trailed
)
```

### Trail API

```python
trail = Trail()

mark = trail.mark()         # -> int: snapshot of trail length
trail.undo(mark)            # Undo all bindings/attrs/callbacks recorded after mark
trail.record(fn)            # Push a no-arg callback; called on undo (backtrack)
```

- `trail.record(fn)`: The callback `fn()` is invoked with **no arguments** when
  `trail.undo()` processes this entry.  Exceptions are silently swallowed so
  undo always completes.
- `unify(t1, t2, trail)` returns `True` on success and records bindings on the
  trail.  On failure, returns `False` and the trail is NOT automatically undone
  (the caller must undo if needed).

### Attribute Variables

```python
put_attr(var, "or", ORVarInfo(cpsat_var, 'int'), trail)
```

Stores a key-value attribute on a `Var`.  Trail-safe: the old attribute is
restored on backtrack.  Each solver backend uses a unique key string
(`"fd"`, `"bdd"`, `"z3"`, `"sat"`, and for OR-Tools: `"or"`).

---

## 2. AST Node Classes

All AST nodes live in `clausal.pythonic_ast.nodes`.  They are **dataclasses**
decorated with `@node_class`.  Binary operators have `left` and `right`
attributes; unary operators have `operand`.

### Import block (copy this into `clportools.py`)

```python
from clausal.pythonic_ast.nodes import (
    # Arithmetic
    Add as _Add,
    Sub as _Sub,
    Mult as _Mult,
    FloorDiv as _FloorDiv,
    Mod as _Mod,
    Negate as _Negate,
    # Bitwise / Boolean
    BitAnd as _BitAnd,
    BitOr as _BitOr,
    BitXor as _BitXor,
    Invert as _Invert,
    # Logical
    And as _And,
    Or as _Or,
    Not as _Not,
    # Comparison
    ArithEq as _ArithEq,
    ArithNeq as _ArithNeq,
    Lt as _Lt,
    LtE as _LtE,
    Gt as _Gt,
    GtE as _GtE,
    CompareChain as _CompareChain,
)
```

### Class hierarchy

```
Node
├── BinOp          (left: Node, right: Node)
│   ├── Add        op = '+'
│   ├── Sub        op = '-'
│   ├── Mult       op = '*'
│   ├── FloorDiv   op = '//'
│   ├── Mod        op = '%'
│   ├── BitOr      op = '|'
│   ├── BitAnd     op = '&'
│   ├── BitXor     op = '^'
│   ├── BoolOp
│   │   ├── And    op = 'and'
│   │   └── Or     op = 'or'
│   └── CmpOp
│       ├── ArithEq    op = '=='
│       ├── ArithNeq   op = '!='
│       ├── Lt         op = '<'
│       ├── LtE        op = '<='
│       ├── Gt         op = '>'
│       └── GtE        op = '>='
├── UnaryOp        (operand: Node)
│   ├── Negate     op = '-'
│   ├── Invert     op = '~'
│   └── Not        op = 'not'
└── CompareChain   (comparisons: list[CmpOp])
```

### Construction

These are dataclasses.  Create with keyword arguments:

```python
Add(left=x, right=y)         # x + y
Sub(left=x, right=y)         # x - y
Mult(left=x, right=y)        # x * y
Negate(operand=x)             # -x
Invert(operand=x)             # ~x
ArithEq(left=x, right=y)     # x == y
Lt(left=x, right=y)          # x < y
```

### Important: Comparison nodes are `Lt`, NOT `ArithLt`

The comparison node names are:

| `.clausal` syntax | AST node class | Module alias |
|---|---|---|
| `X == Y` | `ArithEq` | `_ArithEq` |
| `X != Y` | `ArithNeq` | `_ArithNeq` |
| `X < Y` | `Lt` | `_Lt` |
| `X <= Y` | `LtE` | `_LtE` |
| `X > Y` | `Gt` | `_Gt` |
| `X >= Y` | `GtE` | `_GtE` |

Do NOT use names like `ArithLt` — those don't exist.

### CompareChain

`1 < X < 10` compiles to `CompareChain([Lt(1, X), Lt(X, 10)])`.  When
translating expressions, check for `_CompareChain` and iterate its
`.comparisons` list, translating each `CmpOp` individually.

---

## 3. Compound Terms

```python
from clausal.terms import Compound
```

`Compound` is a simple dataclass:

```python
@dataclass
class Compound:
    functor: str | Var    # e.g. "arc", "interval", "supply"
    args: tuple           # e.g. (0, 1, 20)
```

Used to represent Prolog-style compound terms at runtime.  In `.clausal`
files, `arc(0, 1, 20)` becomes `Compound("arc", (0, 1, 20))`.

**Pattern matching** (used in Phases 4, 6, 7):

```python
term = deref(term)
if isinstance(term, Compound) and term.functor == 'arc' and len(term.args) == 3:
    from_, to_, cap = term.args
    ...
```

---

## 4. `_as_list` Helper

Copy this into each `clportools*.py` file, or import from `clpsat.py`:

```python
def _as_list(val: Any) -> list:
    """Coerce a Clausal term to a Python list.

    Handles: list, tuple, single Var/int, Prolog cons-list.
    """
    val = deref(val)
    if isinstance(val, list):
        return val
    if isinstance(val, tuple):
        return list(val)
    if is_var(val) or isinstance(val, int):
        return [val]
    try:
        from clausal.terms import cons_to_list
        return cons_to_list(val)
    except (ValueError, TypeError, ImportError):
        raise TypeError(
            f"Expected a list, got {type(val).__name__!r}: {val!r}"
        )
```

This is defined in `clausal/logic/clpsat.py:472-488`.  The `cons_to_list`
import handles Prolog-style linked lists (`[H|T]` → `Compound(".", (H, T))`).

---

## 5. `_builtin` Decorator

```python
from clausal.logic.builtins._registry import _builtin
```

### How it works

`_builtin(functor, arity)` registers a **simple-mode** generator function
as a Clausal builtin predicate.  The decorator auto-wraps it for the
trampoline protocol.

### Signature convention

```python
@_builtin("ortools.cpsat.in", 3)
def _ortools_cpsat_in(var, lo, hi, trail, k):
    # Positional args (3 of them, matching arity=3)
    # trail: Trail object
    # k: continuation token (internal to trampoline — ignore it)
    ...
    yield None   # each yield = one solution
```

**Rules:**

1. The function takes exactly `arity` positional args, then `trail`, then `k`
2. `trail` is the Trail for backtracking
3. `k` is the trampoline continuation — **never use it**; it's consumed by
   the wrapper.  Just accept it as a parameter
4. `yield None` to produce a solution (like Prolog succeeding)
5. `yield from some_generator` to delegate to another generator (e.g.,
   `yield from label_or(vars, trail)`)
6. `return` (or fall off the end) to fail (no more solutions)
7. Use `if condition: yield None` for deterministic predicates (succeed once
   or fail)

### Example patterns

**Deterministic predicate (succeeds once or fails):**

```python
@_builtin("ortools.cpsat.all_different", 1)
def _cpsat_all_different(vars_list, trail, k):
    from clausal.logic.clportools import or_all_different
    if or_all_different(vars_list, trail):
        yield None
```

**Generator predicate (multiple solutions):**

```python
@_builtin("ortools.cpsat.solve", 1)
def _cpsat_solve(vars_list, trail, k):
    from clausal.logic.clportools import label_or
    yield from label_or(vars_list, trail)
```

**Predicate that unifies a result:**

```python
@_builtin("ortools.cpsat.count", 2)
def _cpsat_count(vars_list, n, trail, k):
    from clausal.logic.clportools import or_count
    from clausal.logic.variables import unify, deref
    count = or_count(deref(vars_list), trail)
    if unify(n, count, trail):
        yield None
```

### Lazy imports

All builtin functions use **lazy imports** (`from ... import ...` inside the
function body) to avoid circular imports.  This is the established pattern
in `sat_constraints.py` and `z3_constraints.py`.

---

## 6. State Registry Pattern

Every solver backend follows this pattern.  Copy it exactly:

```python
import weakref

_my_states: dict[int, MyState] = {}   # module-level dict

def get_my_state(trail: Trail) -> MyState:
    tid = id(trail)
    state = _my_states.get(tid)
    if state is not None:
        return state
    state = MyState()
    _my_states[tid] = state
    weakref.finalize(trail, _cleanup, tid)   # clean up when Trail is GC'd
    return state

def _cleanup(tid: int) -> None:
    _my_states.pop(tid, None)
```

**Key points:**

- Keyed by `id(trail)` — each Trail gets its own solver state
- `weakref.finalize` ensures cleanup when the Trail is garbage collected
- For PySAT, `_cleanup` also calls `state.solver.delete()` (PySAT requires
  explicit cleanup).  CP-SAT and LP solvers don't need this — Python GC
  handles them

---

## 7. File Organization

Follow this layout (mirrors `clpsat.py` + `sat_constraints.py`):

```
clausal/logic/
  clportools.py              # CP-SAT: state, vars, constraints, labeling
  clportools_lp.py           # LP/MIP: state, vars, constraints, solve
  clportools_graph.py        # Graph: max_flow, min_cost_flow, assignment, knapsack
  clportools_routing.py      # Routing: tsp, vrp, vrptw

clausal/logic/builtins/
  ortools_constraints.py     # All @_builtin registrations for ortools.*

tests/
  test_clportools.py         # CP-SAT tests
  test_clportools_lp.py      # LP/MIP tests
  test_clportools_graph.py   # Graph tests
  test_clportools_routing.py # Routing tests
```

The builtins file must be imported (directly or indirectly) from
`clausal/logic/builtins/constraints.py` to be registered at startup:

```python
# At the end of constraints.py:
import clausal.logic.builtins.ortools_constraints  # noqa: F401
```

---

## 8. Backtracking is Invisible to Users

The three backtracking strategies used across OR-Tools solvers (OnlyEnforceIf
for CP-SAT, constraint-set rebuild for LP/MIP, and one-shot for graph/routing)
are **entirely internal**.  From the user's `.clausal` code, every solver
follows the same pattern:

1. Declare variables
2. Post constraints
3. Solve / label

Constraints posted inside a choice point are automatically retracted on
backtrack, regardless of which solver is used.  The user never sees activation
literals, scope IDs, or model rebuilds.

The only visible API difference is that graph/routing/knapsack predicates are
**all-in-one** (take input + return output in a single call) rather than
incremental (declare, constrain, solve).  But that reflects the problem type,
not a backtracking difference.

---

## 9. Existing Reference Implementations

When in doubt, read these files — they are the canonical examples:

| What | File | Lines |
|------|------|-------|
| State registry, var mapping, activation literals | `clausal/logic/clpsat.py` | 1-150 |
| Tseitin CNF translation, constraint blocks | `clausal/logic/clpsat.py` | 150-400 |
| Labeling with blocking clauses | `clausal/logic/clpsat.py` | 400-500 |
| Cardinality constraints | `clausal/logic/clpsat.py` | 500-600 |
| Builtin registration (per-solver factory) | `clausal/logic/builtins/sat_constraints.py` | all |
| Z3 expression translation (arithmetic + comparison) | `clausal/logic/clpz3.py` | 200-300 |
| Z3 push/pop trail synchronization | `clausal/logic/clpz3.py` | 100-200 |
| Z3 labeling with model extraction | `clausal/logic/clpz3.py` | 478-543 |
| Builtin registration for Z3 | `clausal/logic/builtins/z3_constraints.py` | all |

---

## 10. Common Gotchas

### deref before isinstance

Always `deref()` before checking types:

```python
# WRONG:
if isinstance(expr, _Add): ...

# RIGHT:
expr = deref(expr)
if isinstance(expr, _Add): ...
```

A Clausal `Var` bound to an `Add` node will look like a `Var` until dereffed.

### unify returns bool, does not undo on failure

`unify(t1, t2, trail)` returns `False` on failure but does NOT undo partial
bindings.  If you need clean failure, use `mark/undo`:

```python
mark = trail.mark()
if not unify(x, 42, trail):
    trail.undo(mark)
```

### yield None, not yield True

Builtins signal success by `yield None`, not `yield True`.  The trampoline
protocol uses `None` as the "solution" sentinel.

### No return value from generators

Builtin generators must not `return` a value.  Use `yield None` for success,
`return` (bare) or fall off end for failure.

### weakref.finalize callback must not capture trail

The cleanup function receives `tid` (an int), not the trail object.
Capturing the trail in the closure would prevent GC:

```python
# WRONG — prevents GC:
weakref.finalize(trail, lambda: _my_states.pop(id(trail), None))

# RIGHT — captures only the int:
tid = id(trail)
weakref.finalize(trail, _cleanup, tid)
```
