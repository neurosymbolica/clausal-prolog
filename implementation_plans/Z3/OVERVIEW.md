# Z3 Integration for Clausal

A phased plan to use Microsoft's Z3 theorem prover as a constraint-solving
backend for Clausal, preserving Clausal's syntax and relational semantics while
gaining Z3's industrial-strength solver, theory combination, and advanced
capabilities (optimization, quantifiers, unsat cores, bitvectors, strings, etc.).

---

## Sub-Plans (Detailed)

Each phase has a dedicated sub-plan with full implementation details, code
examples, edge cases, gotchas, tests, and implementation ordering:

| Phase | Sub-Plan | Lines | Focus |
|-------|----------|-------|-------|
| 1 | [PHASE1_CORE_INFRASTRUCTURE.md](PHASE1_CORE_INFRASTRUCTURE.md) | ~400 | Z3State, Var↔Z3 mapping, expression translation, trail sync |
| 2 | [PHASE2_INTEGER_CONSTRAINTS.md](PHASE2_INTEGER_CONSTRAINTS.md) | ~500 | `in_z3`, `all_different_z3`, `label_z3`, arithmetic dispatch |
| 3 | [PHASE3_BOOLEAN_CONSTRAINTS.md](PHASE3_BOOLEAN_CONSTRAINTS.md) | ~400 | `sat_z3`, `taut_z3`, `label_z3_bool`, cardinality constraints |
| 4 | [PHASE4_REAL_RATIONAL_CONSTRAINTS.md](PHASE4_REAL_RATIONAL_CONSTRAINTS.md) | ~400 | `in_z3_real`, `maximize_z3`, nonlinear arithmetic |
| 5 | [PHASE5_USER_PROPAGATE.md](PHASE5_USER_PROPAGATE.md) | ~350 | `ClausalPropagator`, nested trampoline, table constraints |
| 6 | [PHASE6_ADVANCED_THEORIES.md](PHASE6_ADVANCED_THEORIES.md) | ~400 | Bitvectors, arrays, strings, sets, quantifiers, datatypes |
| 7 | [PHASE7_OPTIMIZATION.md](PHASE7_OPTIMIZATION.md) | ~300 | Soft constraints, MaxSAT, multi-objective optimization |
| 8 | [PHASE8_DIAGNOSTICS.md](PHASE8_DIAGNOSTICS.md) | ~400 | Unsat cores, entailment, model inspection, solver config |

---

## Table of Contents (this document)

1. [Motivation](#1-motivation)
2. [Architecture Overview](#2-architecture-overview)
3. [Datatype Mapping](#3-datatype-mapping)
4. [Trail ↔ Push/Pop Synchronization](#4-trail--pushpop-synchronization)
5. [The Nested Trampoline Insight](#5-the-nested-trampoline-insight)
6. [Phase 1 — Core Infrastructure (`clpz3.py`)](#phase-1--core-infrastructure-clpz3py)
7. [Phase 2 — CLP(Z3) Integer Constraints](#phase-2--clpz3-integer-constraints)
8. [Phase 3 — CLP(Z3) Boolean Constraints](#phase-3--clpz3-boolean-constraints)
9. [Phase 4 — CLP(Z3) Real/Rational Constraints](#phase-4--clpz3-realrational-constraints)
10. [Phase 5 — UserPropagateBase Integration](#phase-5--userpropagatebase-integration)
11. [Phase 6 — Advanced Z3 Theories](#phase-6--advanced-z3-theories)
12. [Phase 7 — Optimization & Soft Constraints](#phase-7--optimization--soft-constraints)
13. [Phase 8 — Diagnostics (Unsat Cores, Explanations)](#phase-8--diagnostics-unsat-cores-explanations)
14. [Appendix A — Z3 Python API Ergonomics](#appendix-a--z3-python-api-ergonomics)
15. [Appendix B — Existing Prolog + Z3 Projects](#appendix-b--existing-prolog--z3-projects)

---

## 1. Motivation

Clausal currently has four independent constraint solvers:

| Module | Domain | Algorithm |
|--------|--------|-----------|
| `clpfd.py` | Integers (finite domain) | Interval domains + propagation queue |
| `clpb.py` | Booleans | BDDs (Markus Triska design) |
| `clpq.py` | Rationals | Gaussian elimination + simplex |
| `clpr.py` | Reals | Interval arithmetic |

Each is self-contained and cannot interact with the others. A mixed-domain
problem (e.g., integer variables constrained by Boolean logic over rational
bounds) requires manual decomposition.

Z3 provides a **single solver** that natively handles all of these domains plus
many more, with built-in theory combination (Nelson-Oppen). It also adds
capabilities that Clausal lacks entirely:

- **Optimization** (minimize/maximize with hard and soft constraints)
- **Quantifiers** (∀/∃ with E-matching)
- **Unsat cores** (explain why constraints are unsatisfiable)
- **Bitvectors** (fixed-width machine arithmetic)
- **Arrays** (SMT arrays with select/store)
- **Strings/Sequences** (string constraints, regex membership)
- **Sets** (set theory operations)
- **Algebraic datatypes** (recursive data structures)

The goal is **Clausal syntax and semantics, Z3 power**: the user writes `.clausal`
files using familiar predicates, and Z3 handles the solving.

---

## 2. Architecture Overview

```
┌────────────────────────────────────────────────────┐
│  .clausal source files                             │
│  ─ Familiar Prolog-like syntax                     │
│  ─ in_z3(Vars, 1, 9), all_different(Vars), ...    │
└────────────────────┬───────────────────────────────┘
                     │ compile + execute
                     ▼
┌────────────────────────────────────────────────────┐
│  Clausal Runtime                                   │
│  ─ Unification, backtracking (Trail)               │
│  ─ Generator-based trampoline                      │
│  ─ Module system, builtins                         │
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  clpz3.py  (new module)                      │  │
│  │  ─ Var ↔ Z3 constant registry                │  │
│  │  ─ Constraint translation                    │  │
│  │  ─ Trail ↔ push/pop sync                     │  │
│  │  ─ Labeling via check() + model()            │  │
│  └──────────────┬───────────────────────────────┘  │
│                 │                                   │
│  ┌──────────────▼───────────────────────────────┐  │
│  │  Z3 Solver (z3-solver Python package)        │  │
│  │  ─ CDCL + theory solvers                     │  │
│  │  ─ push()/pop() for incremental solving      │  │
│  │  ─ UserPropagateBase for callbacks → Clausal │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

**Key design decisions:**

1. **Z3 as a parallel backend, not a replacement.** The existing CLP(FD)/CLP(B)/
   CLP(Q)/CLP(R) solvers remain unchanged. Z3 is a new option the user opts
   into, either per-variable (`in_z3(X, 1, 9)`) or per-module (`-solver z3`).

2. **Clausal owns unification and search.** Z3 handles constraint satisfaction.
   The Trail remains the single source of truth for variable bindings.

3. **Z3's Solver.push()/pop() mirrors Trail.mark()/undo().** Constraint scopes
   stay synchronized with Prolog backtracking.

4. **Labeling calls check() + model().** Instead of enumerating domains, Z3 finds
   satisfying assignments directly. Solution enumeration uses blocking clauses.

---

## 3. Datatype Mapping

### Variables

| Clausal | Z3 Python | Creation |
|---------|-----------|----------|
| `Var()` with FD constraint | `Int('x_NNN')` | On first `in_z3()` |
| `Var()` with Bool constraint | `Bool('b_NNN')` | On first `sat_z3()` |
| `Var()` with Q/R constraint | `Real('r_NNN')` | On first `in_z3_real()` |
| `Var()` with BitVec | `BitVec('bv_NNN', width)` | On first `in_z3_bv()` |

Each Clausal `Var` gets a corresponding Z3 symbolic constant, stored as an
attribute: `put_attr(var, "z3", Z3VarState(z3_const, sort), trail)`. The
mapping is lazily created on first constraint posting.

### Constraints

| Clausal syntax | Z3 translation |
|----------------|----------------|
| `in_z3(X, 1, 9)` | `And(x >= 1, x <= 9)` |
| `X == Y` (arithmetic) | `x == y` (Z3 ArithRef) |
| `X != Y` | `x != y` |
| `X < Y` | `x < y` |
| `X + Y == Z` | `x + y == z` |
| `all_different(Vs)` | `Distinct(*z3_vars)` |
| `dif(X, Y)` | `x != y` |
| `sat_z3(X & Y)` | `And(x, y)` (Z3 BoolRef) |
| `sat_z3(X \| Y)` | `Or(x, y)` |
| `sat_z3(~X)` | `Not(x)` |
| `in_z3_real(X, 0, 10)` | `And(x >= 0, x <= 10)` on RealSort |
| `X + Y <= 16` (rational) | `x + y <= 16` (Z3 ArithRef, RealSort) |
| `maximize_z3(Expr, Obj)` | `Optimize.maximize(expr)` |

### Compound Terms (future)

| Clausal | Z3 |
|---------|-----|
| Lists | `Array(IntSort(), ElemSort())` or sequences |
| Enums | `EnumSort('Color', ['red', 'green', 'blue'])` |
| Records | `Datatype` declarations |

---

## 4. Trail ↔ Push/Pop Synchronization

This is the critical correctness invariant. Clausal's Trail and Z3's Solver
scope stack must stay synchronized so that backtracking is consistent.

### The Trail (C implementation)

```
Trail = [entry₀, entry₁, ..., entryₙ]
                              ↑ trail.length

trail.mark()  → returns trail.length (an integer)
trail.undo(m) → for i in [n, n-1, ..., m]: undo(entryᵢ)
                trail.length = m
```

Three entry kinds:
- **TRAIL_BINDING**: variable binding `var.binding = old_value`
- **TRAIL_ATTR**: attribute change `put_attr(var, key, old, trail)`
- **TRAIL_CALLBACK**: undo callback `fn()` called on undo

### Z3 Solver Push/Pop

```python
solver.push()        # save assertion scope
solver.add(...)      # add constraints in this scope
solver.pop()         # remove all constraints added since push()
solver.num_scopes()  # current nesting depth
```

Z3's Solver implements `__enter__`/`__exit__`, so `with solver:` is safe:

```python
with solver:                    # solver.push()
    solver.add(temporary)
    solver.check()
# solver.pop() — even on exception or early return
```

### Synchronization Strategy

The `clpz3` module maintains a `Z3State` object attached to the Trail via
`trail.record()` callbacks:

```python
class Z3State:
    """Per-query Z3 solver state, attached to the trail."""

    def __init__(self):
        self.solver = Solver()
        self.var_map = {}      # Clausal Var id → Z3 ExprRef
        self.rev_map = {}      # Z3 ExprRef id → Clausal Var

    def push(self, trail):
        """Called before a choice point. Records undo callback."""
        self.solver.push()
        trail.record(lambda: self.solver.pop())

    def add(self, constraint):
        """Add a Z3 constraint in the current scope."""
        self.solver.add(constraint)
```

When Clausal backtracks (`trail.undo(mark)`), the trail replays undo entries
in reverse — including the `trail.record()` callback that calls `solver.pop()`.
This automatically retracts all Z3 constraints added since the corresponding
`push()`.

**Invariant:** Every `solver.push()` is paired with a `trail.record(solver.pop)`
so that backtracking always keeps the solver in sync.

### Alternative: Context Manager in Labeling

For the labeling generator (which yields solutions), the context manager
protects against abandoned generators:

```python
def z3_label(variables, trail):
    state = get_z3_state(trail)
    z3_vars = [state.var_map[id(v)] for v in variables]

    while True:
        with state.solver:                # push
            if state.solver.check() == sat:
                m = state.solver.model()
                mark = trail.mark()
                for v, z3v in zip(variables, z3_vars):
                    unify(v, m.eval(z3v, model_completion=True).as_long(), trail)
                yield None                # solution — back to trampoline
                trail.undo(mark)
                # block this solution
                state.solver.add(Or([z3v != m.eval(z3v, model_completion=True)
                                     for z3v in z3_vars]))
            else:
                return                    # pop (via __exit__)
        # pop happened here (via __exit__), even if generator abandoned
```

---

## 5. The Nested Trampoline Insight

Z3's `UserPropagateBase` callbacks are synchronous — you cannot `yield` from
inside them. But Clausal's trampoline is **just a while loop**:

```python
# The entire trampoline (from trampoline.py):
gen, value = root.send(None)
while gen is not None:
    gen, value = gen.send(value)
return value
```

This means you can **start a new trampoline inside a Z3 callback**, passing it
the same Trail and a fresh continuation:

```python
class ClausalPropagator(UserPropagateBase):
    def __init__(self, solver, trail):
        super().__init__(solver)
        self.trail = trail
        self.scope_marks = []
        self.add_fixed(self.on_fixed)
        self.add_final(self.on_final)

    def push(self):
        # Z3 is making a CDCL decision — save trail position
        self.scope_marks.append(self.trail.mark())

    def pop(self, num_scopes):
        # Z3 is backtracking — undo trail to saved positions
        for _ in range(num_scopes):
            mark = self.scope_marks.pop()
            self.trail.undo(mark)

    def fresh(self, new_ctx):
        return ClausalPropagator(None, self.trail)

    def on_fixed(self, z3_var, z3_value):
        clausal_var = self.rev_map[z3_var.get_id()]
        value = z3_value_to_python(z3_value)

        # Run a full Clausal goal inside this callback:
        sg = StepGenerator(
            some_propagation_predicate,
            None,           # parent=None (fresh root)
            clausal_var, value,
            self.trail
        )
        result = trampoline(sg)

        # Translate consequences back to Z3
        if result is FAIL:
            self.conflict([z3_var.get_id()])
        elif result is not None:
            for z3_constraint in translate_consequences(result):
                self.propagate(z3_constraint, [z3_var.get_id()])
```

**Why this works:**

1. **Trail is just a C object.** It doesn't care who calls `mark()`/`undo()` —
   Clausal's trampoline, Z3's propagator, or a nested trampoline inside a
   callback. Bindings go on the same stack.

2. **The trampoline is reentrant.** It's a local while loop with local variables
   (`gen`, `value`). Starting a new one inside a callback doesn't interfere with
   the outer trampoline (which is blocked at `solver.check()`).

3. **Z3's push/pop aligns with trail.mark/undo.** The propagator's `push()` saves
   a trail mark; `pop()` undoes to it. Any bindings made by the inner trampoline
   are on the trail and get undone when Z3 backtracks.

4. **The inner trampoline can do its own backtracking.** If it has choice points,
   it does `trail.mark()` / `trail.undo()` internally — these are nested within
   Z3's scope and get cleaned up. The trail is a stack; nesting works.

### Control Flow Diagram

```
Clausal generator (outer trampoline)
  │
  ├─ posts constraints via clpz3 → solver.add(...)
  │
  ├─ calls z3_label(Vars)
  │     │
  │     └─ solver.check()          ← blocks here
  │          │
  │          │  Z3 CDCL loop
  │          ├─ UserPropagateBase.push()    → trail.mark()
  │          ├─ UserPropagateBase.on_fixed(x, v)
  │          │     │
  │          │     └─ inner_trampoline = trampoline(StepGenerator(..., trail))
  │          │           │
  │          │           ├─ runs Clausal goals
  │          │           ├─ trail.mark() / trail.undo()  (nested, local)
  │          │           └─ returns result
  │          │     │
  │          │     ├─ self.propagate(z3_consequence, ...)
  │          │     └─ or self.conflict(...)
  │          │
  │          ├─ UserPropagateBase.pop(n)    → trail.undo() × n
  │          │
  │          └─ returns sat/unsat
  │     │
  │     ├─ model() → bind Clausal vars
  │     └─ yield None  ← back to outer trampoline
  │
  └─ next solution...
```

---

## Phase 1 — Core Infrastructure (`clpz3.py`)

**Goal:** Create the foundational module that manages the Clausal Var ↔ Z3
constant mapping and Trail ↔ Solver synchronization.

### Files

- `clausal/logic/clpz3.py` — core module
- `clausal/logic/builtins/z3_constraints.py` — builtin registration

### API Surface

```python
# ── Variable Registration ────────────────────────────────────────────

def get_z3_state(trail: Trail) -> Z3State:
    """Get or create the per-query Z3State from the trail."""

def z3_var_for(var: Var, sort: z3.SortRef, trail: Trail) -> z3.ExprRef:
    """Get or create a Z3 constant for a Clausal Var.

    Lazily creates the Z3 constant and stores the mapping as an
    attribute on the Var: put_attr(var, 'z3', Z3VarInfo(...), trail).
    """

# ── Constraint Posting ───────────────────────────────────────────────

def z3_add(constraint: z3.BoolRef, trail: Trail) -> bool:
    """Add a Z3 constraint. Returns False if immediately unsat."""

def z3_push(trail: Trail):
    """Push a Z3 scope, recording undo callback on trail."""

# ── Expression Translation ───────────────────────────────────────────

def clausal_to_z3(expr, trail: Trail) -> z3.ExprRef:
    """Translate a Clausal arithmetic/boolean expression to Z3.

    Walks the simple_ast node tree, replacing Vars with their Z3
    constants and operators with Z3 function applications.
    """

def z3_to_python(z3_val: z3.ExprRef) -> int | float | bool | Fraction:
    """Convert a Z3 model value to a Python value."""

# ── State ────────────────────────────────────────────────────────────

class Z3VarInfo:
    """Attribute value stored on a Clausal Var under key 'z3'."""
    __slots__ = ('z3_const', 'sort')

class Z3State:
    """Per-query Z3 solver state."""
    solver: z3.Solver
    var_map: dict[int, z3.ExprRef]    # id(Var) → Z3 const
    rev_map: dict[int, Var]           # z3_const.get_id() → Var
```

### Expression Translation Table

The `clausal_to_z3` function walks Clausal's `simple_ast` nodes:

```python
# simple_ast node → Z3 expression
TRANSLATION = {
    Add:      lambda l, r: l + r,
    Sub:      lambda l, r: l - r,
    Mult:     lambda l, r: l * r,
    FloorDiv: lambda l, r: l / r,       # Z3 integer division
    Mod:      lambda l, r: l % r,
    # Comparisons → BoolRef
    ArithEq:  lambda l, r: l == r,
    ArithNeq: lambda l, r: l != r,
    Lt:       lambda l, r: l < r,
    LtE:      lambda l, r: l <= r,
    Gt:       lambda l, r: l > r,
    GtE:      lambda l, r: l >= r,
    # Boolean
    And:      lambda l, r: z3.And(l, r),
    Or:       lambda l, r: z3.Or(l, r),
    Not:      lambda x:    z3.Not(x),
    # Bitwise (overloaded for BoolRef as logical ops)
    BitAnd:   lambda l, r: z3.And(l, r),
    BitOr:    lambda l, r: z3.Or(l, r),
    BitXor:   lambda l, r: z3.Xor(l, r),
}
```

### Tests (Phase 1)

```python
def test_var_registration():
    trail = Trail()
    x = Var()
    z3_x = z3_var_for(x, z3.IntSort(), trail)
    assert z3_x.sort() == z3.IntSort()
    # Same var returns same Z3 constant
    assert z3_var_for(x, z3.IntSort(), trail) is z3_x

def test_trail_sync():
    trail = Trail()
    state = get_z3_state(trail)
    mark = trail.mark()
    z3_push(trail)
    state.solver.add(z3.Int('x') > 0)
    assert state.solver.num_scopes() == 1
    trail.undo(mark)
    assert state.solver.num_scopes() == 0  # pop happened via callback

def test_expression_translation():
    trail = Trail()
    x, y = Var(), Var()
    z3_x = z3_var_for(x, z3.IntSort(), trail)
    z3_y = z3_var_for(y, z3.IntSort(), trail)
    # Translate: x + y == 10
    node = ArithEq(Add(x, y), 10)
    z3_expr = clausal_to_z3(node, trail)
    assert z3.is_eq(z3_expr)
```

---

## Phase 2 — CLP(Z3) Integer Constraints

**Goal:** Integer constraint predicates that use Z3 instead of CLP(FD).

### Clausal Syntax

The user-facing API mirrors existing CLP(FD) predicates but with a `z3` suffix
(or selected via a module directive):

```prolog
# Explicit Z3 predicates
Sudoku(ROWS) <- (
    flatten(ROWS, VS),
    in_z3(VS, 1, 9),
    maplist(all_different_z3, ROWS),
    transpose(ROWS, COLUMNS),
    maplist(all_different_z3, COLUMNS),
    Blocks(R1, R2, R3),
    label_z3(VS)
)

# Or via module directive (switches all constraint predicates to Z3):
-solver z3

Sudoku(ROWS) <- (
    flatten(ROWS, VS),
    in_domain(VS, 1, 9),          # dispatches to Z3 via directive
    maplist(all_different, ROWS),
    label(VS)
)
```

### Builtin Registration

```python
# clausal/logic/builtins/z3_constraints.py

@_builtin("in_z3", 3)
def _in_z3__3(var_or_list, lo, hi, trail, k):
    """in_z3(Var, Lo, Hi) — post integer domain [Lo, Hi] via Z3."""
    from clausal.logic.clpz3 import in_z3 as _fn
    if _fn(var_or_list, lo, hi, trail):
        yield None

@_builtin("all_different_z3", 1)
def _all_different_z3__1(vars_list, trail, k):
    """all_different_z3(Vars) — Z3 Distinct constraint."""
    from clausal.logic.clpz3 import all_different_z3 as _fn
    if _fn(vars_list, trail):
        yield None

@_builtin("label_z3", 1)
def _label_z3__1(vars_list, trail, k):
    """label_z3(Vars) — enumerate solutions via Z3 check/model."""
    from clausal.logic.clpz3 import label_z3 as _fn
    yield from _fn(vars_list, trail)
```

### Implementation

```python
# clausal/logic/clpz3.py

def in_z3(var_or_list, lo, hi, trail):
    """Post integer domain constraint [lo, hi] via Z3."""
    lo, hi = deref(lo), deref(hi)
    state = get_z3_state(trail)

    def _post_one(v):
        v = deref(v)
        if not is_var(v):
            return lo <= v <= hi          # ground check
        z3_v = z3_var_for(v, z3.IntSort(), trail)
        state.solver.add(z3_v >= lo)
        state.solver.add(z3_v <= hi)
        return True

    var_or_list = deref(var_or_list)
    if isinstance(var_or_list, list):
        return all(_post_one(v) for v in var_or_list)
    return _post_one(var_or_list)


def all_different_z3(vars_list, trail):
    """Post Z3 Distinct constraint."""
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    z3_vars = [z3_var_for(deref(v), z3.IntSort(), trail) for v in vars_list]
    state.solver.add(z3.Distinct(*z3_vars))
    return True


def label_z3(vars_list, trail):
    """Enumerate solutions via Z3.

    Generator that yields None for each satisfying assignment.
    Uses blocking clauses to enumerate all solutions.
    """
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    z3_vars = [z3_var_for(deref(v), z3.IntSort(), trail) for v in vars_list]
    clausal_vars = [deref(v) for v in vars_list]

    while state.solver.check() == z3.sat:
        m = state.solver.model()
        mark = trail.mark()
        # Bind Clausal vars to Z3's solution
        ok = True
        for cv, z3v in zip(clausal_vars, z3_vars):
            val = m.eval(z3v, model_completion=True).as_long()
            if not unify(cv, val, trail):
                ok = False
                break
        if ok:
            yield None                    # solution — back to trampoline
        trail.undo(mark)
        # Block this solution and find the next
        state.solver.add(z3.Or([z3v != m.eval(z3v, model_completion=True)
                                for z3v in z3_vars]))
    # Exhausted — generator returns
```

### Example: SEND + MORE = MONEY

```prolog
# sendmore_z3.clausal
Sendmoney(S, E, N, D, M, O, R, Y) <- (
    in_z3([S, E, N, D, M, O, R, Y], 0, 9),
    all_different_z3([S, E, N, D, M, O, R, Y]),
    S != 0,
    M != 0,
    (S * 1000 + E * 100 + N * 10 + D +
     M * 1000 + O * 100 + R * 10 + E
     == M * 10000 + O * 1000 + N * 100 + E * 10 + Y),
    label_z3([S, E, N, D, M, O, R, Y])
)
```

Usage from Python:

```python
from clausal import Var, solve
import sendmore_z3

S, E, N, D, M, O, R, Y = (Var() for _ in range(8))
for trail in solve(sendmore_z3.Sendmoney(S, E, N, D, M, O, R, Y)):
    print(f"{deref(S)}{deref(E)}{deref(N)}{deref(D)} + "
          f"{deref(M)}{deref(O)}{deref(R)}{deref(E)} = "
          f"{deref(M)}{deref(O)}{deref(N)}{deref(E)}{deref(Y)}")
```

### Tests (Phase 2)

- N-Queens (compare results with CLP(FD) `label`)
- SEND+MORE=MONEY
- Sudoku (4×4 and 9×9)
- Pigeonhole (expect failure)
- All-different with ground variables
- Mixed ground + unbound variables

---

## Phase 3 — CLP(Z3) Boolean Constraints

**Goal:** Boolean constraint predicates backed by Z3's SAT solver.

### Clausal Syntax

```prolog
# Pigeonhole via Z3 Booleans
PigeonHole(N, M, ASSIGNMENT) <- (
    length(HOLES, M),
    maplist(make_pigeon_vars(N), HOLES),
    # Each pigeon in exactly one hole
    maplist(exactly_one_z3, PIGEONS),
    # Each hole has at most one pigeon
    maplist(at_most_one_z3, HOLES),
    label_z3_bool(flatten(ASSIGNMENT))
)

# Circuit satisfiability
Circuit(X, Y, Z, OUT) <- (
    sat_z3(BoolEq(OUT, (X & Y) | (~X & Z))),
    OUT == 1,
    label_z3_bool([X, Y, Z])
)
```

### Implementation

```python
def sat_z3(expr, trail):
    """Post a Boolean constraint via Z3.

    Translates Clausal Boolean expression (using &, |, ^, ~, BoolEq, BoolImpl)
    to Z3 BoolRef and adds to solver.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_bool_to_z3(expr, trail)
    state.solver.add(z3_expr)
    # Quick consistency check
    return state.solver.check() != z3.unsat


def label_z3_bool(vars_list, trail):
    """Enumerate 0/1 assignments for Boolean variables via Z3."""
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    z3_vars = [z3_var_for(deref(v), z3.BoolSort(), trail) for v in vars_list]
    clausal_vars = [deref(v) for v in vars_list]

    while state.solver.check() == z3.sat:
        m = state.solver.model()
        mark = trail.mark()
        for cv, z3v in zip(clausal_vars, z3_vars):
            val = 1 if z3.is_true(m.eval(z3v, model_completion=True)) else 0
            unify(cv, val, trail)
        yield None
        trail.undo(mark)
        state.solver.add(z3.Or([z3v != m.eval(z3v, model_completion=True)
                                for z3v in z3_vars]))


def at_most_z3(vars_list, k, trail):
    """At most k of the Boolean vars are true."""
    state = get_z3_state(trail)
    z3_vars = [z3_var_for(deref(v), z3.BoolSort(), trail) for v in vars_list]
    state.solver.add(z3.AtMost(*z3_vars, k))
    return True


def at_least_z3(vars_list, k, trail):
    """At least k of the Boolean vars are true."""
    state = get_z3_state(trail)
    z3_vars = [z3_var_for(deref(v), z3.BoolSort(), trail) for v in vars_list]
    state.solver.add(z3.AtLeast(*z3_vars, k))
    return True
```

### Mapping: CLP(B) → Z3

| CLP(B) | Z3 |
|--------|-----|
| `sat(X & Y)` | `solver.add(And(x, y))` |
| `sat(X \| Y)` | `solver.add(Or(x, y))` |
| `sat(~X)` | `solver.add(Not(x))` |
| `sat(X ^ Y)` | `solver.add(Xor(x, y))` |
| `sat(BoolEq(X, Y))` | `solver.add(x == y)` |
| `sat(BoolImpl(X, Y))` | `solver.add(Implies(x, y))` |
| `taut(Expr, T)` | `solver.check(Not(expr)) == unsat` → T=1 |
| `sat_count(Expr, N)` | enumerate + count (or `#SAT` via AllSMT) |
| `bool_labeling(Vs)` | `label_z3_bool(Vs)` |

**New capabilities from Z3:**
- `AtMost(*vars, k)` / `AtLeast(*vars, k)` — cardinality constraints
- `PbLe([(x, w), ...], k)` — pseudo-Boolean constraints
- Native unsat core for Boolean conflicts

---

## Phase 4 — CLP(Z3) Real/Rational Constraints

**Goal:** Linear arithmetic over reals/rationals backed by Z3's simplex solver.

### Clausal Syntax

```prolog
# Linear programming
LP(X, Y, OBJ) <- (
    in_z3_real([X, Y], 0, 1000),
    2 * X + Y <= 16,
    X + 2 * Y <= 11,
    X + 3 * Y <= 15,
    maximize_z3(30 * X + 50 * Y, OBJ)
)

# Mixed integer-real
MixedIP(X, Y) <- (
    in_z3([X], 0, 100),              # X is integer
    in_z3_real([Y], 0, 100),         # Y is real
    X + Y == 10,
    2 * X + 3 * Y <= 25,
    label_z3([X]),                    # enumerate integer X
    label_z3_real([Y])                # Z3 finds real Y from model
)
```

### Implementation

```python
def in_z3_real(var_or_list, lo, hi, trail):
    """Declare real-sorted variable(s) with bounds."""
    state = get_z3_state(trail)

    def _post_one(v):
        v = deref(v)
        if not is_var(v):
            return lo <= v <= hi
        z3_v = z3_var_for(v, z3.RealSort(), trail)
        state.solver.add(z3_v >= z3.RealVal(lo))
        state.solver.add(z3_v <= z3.RealVal(hi))
        return True

    var_or_list = deref(var_or_list)
    if isinstance(var_or_list, list):
        return all(_post_one(v) for v in var_or_list)
    return _post_one(var_or_list)


def maximize_z3(expr, result_var, trail):
    """Maximize a linear expression via Z3 Optimize."""
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(expr, trail)

    opt = z3.Optimize()
    # Copy all current assertions into the optimizer
    for a in state.solver.assertions():
        opt.add(a)
    handle = opt.maximize(z3_expr)

    if opt.check() == z3.sat:
        m = opt.model()
        obj_val = m.eval(z3_expr)
        return unify(result_var, z3_to_python(obj_val), trail)
    return False


def minimize_z3(expr, result_var, trail):
    """Minimize a linear expression via Z3 Optimize."""
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(expr, trail)

    opt = z3.Optimize()
    for a in state.solver.assertions():
        opt.add(a)
    handle = opt.minimize(z3_expr)

    if opt.check() == z3.sat:
        m = opt.model()
        obj_val = m.eval(z3_expr)
        return unify(result_var, z3_to_python(obj_val), trail)
    return False
```

### Mapping: CLP(Q)/CLP(R) → Z3

| CLP(Q)/CLP(R) | Z3 |
|----------------|-----|
| `in_q(X, Lo, Hi)` | `And(x >= Lo, x <= Hi)` on `RealSort` |
| `X + Y == 10` | `x + y == 10` |
| `2*X + Y <= 16` | `2*x + y <= 16` |
| `maximize(Expr, Obj)` | `Optimize.maximize(expr)` |
| `minimize(Expr, Obj)` | `Optimize.minimize(expr)` |
| `int_minimize(IVs, Expr, Min)` | Optimize + `ForAll` integrality |
| `entailed(X <= 5)` | `solver.check(Not(x <= 5)) == unsat` |
| `sup(Expr, S)` | `Optimize.maximize(expr)` |
| `inf(Expr, I)` | `Optimize.minimize(expr)` |

**New capability:** Z3 handles nonlinear real arithmetic (NRA) via NLSAT —
something CLP(Q)'s simplex cannot do:

```prolog
Circle(X, Y) <- (
    in_z3_real([X, Y], -10, 10),
    X * X + Y * Y <= 25,        # nonlinear! CLP(Q) can't do this
    X + Y >= 3
)
```

---

## Phase 5 — UserPropagateBase Integration

**Goal:** Allow Z3 to call back into Clausal for custom constraint propagation.
This enables hybrid solving where Z3 handles standard theories and Clausal
handles domain-specific constraints.

### Architecture

```python
class ClausalPropagator(UserPropagateBase):
    """Bridge Z3's CDCL loop to Clausal's constraint propagation.

    Z3 drives the search. When it assigns a variable, it calls on_fixed().
    The propagator starts a nested Clausal trampoline to run propagation
    logic, then translates consequences back to Z3.
    """

    def __init__(self, solver, trail, propagation_goals):
        super().__init__(solver)
        self.trail = trail
        self.scope_marks = []
        self.propagation_goals = propagation_goals  # Clausal predicates
        self.add_fixed(self.on_fixed)
        self.add_final(self.on_final)

    def push(self):
        self.scope_marks.append(self.trail.mark())

    def pop(self, num_scopes):
        for _ in range(num_scopes):
            self.trail.undo(self.scope_marks.pop())

    def fresh(self, new_ctx):
        # Z3 parallel solving — create a new propagator with the same goals
        return ClausalPropagator(None, Trail(), self.propagation_goals)

    def on_fixed(self, z3_var, z3_value):
        """Z3 assigned a variable — run Clausal propagation."""
        clausal_var = self.rev_map.get(z3_var.get_id())
        if clausal_var is None:
            return

        value = z3_value_to_python(z3_value)

        # Start a nested trampoline with the SAME trail
        for goal in self.propagation_goals:
            sg = StepGenerator(goal, None, clausal_var, value, self.trail)
            try:
                result = trampoline(sg)
            except Exception:
                self.conflict([z3_var.get_id()])
                return

            if result is FAIL:
                self.conflict([z3_var.get_id()])
                return

            # Translate Clausal-side consequences to Z3
            for consequence in extract_consequences(result):
                self.propagate(consequence, [z3_var.get_id()])

    def on_final(self):
        """Z3 found a complete assignment — verify with Clausal."""
        # Optional: run a full Clausal verification goal
        pass
```

### Use Case: Table Constraints

Z3 doesn't have native table (extensional) constraints. Clausal can provide
them via UserPropagateBase:

```prolog
# Table constraint: (X, Y, Z) must be one of the listed tuples
TableConstraint(X, Y, Z) <- (
    in_z3([X, Y, Z], 1, 5),
    z3_table([X, Y, Z], [[1,2,3], [2,3,4], [3,4,5]]),
    label_z3([X, Y, Z])
)
```

The `z3_table` predicate registers a `ClausalPropagator` whose `on_fixed`
callback filters the table based on assigned values.

### Use Case: Tabling + Z3

SLG tabling can run inside a `UserPropagateBase` callback. When Z3 assigns
a variable, the propagator queries a tabled Clausal predicate to look up
valid combinations:

```python
def on_fixed(self, z3_var, z3_value):
    # Run a tabled Clausal query
    results = []
    sg = StepGenerator(tabled_lookup, None, z3_value, self.trail)
    for _ in solutions(sg):
        results.append(deref(self.result_var))

    # Constrain Z3 based on tabled results
    if not results:
        self.conflict([z3_var.get_id()])
    else:
        z3_out = self.var_map[id(self.output_var)]
        self.propagate(z3.Or([z3_out == r for r in results]),
                       [z3_var.get_id()])
```

---

## Phase 6 — Advanced Z3 Theories

**Goal:** Expose Z3-only theories that have no CLP equivalent.

### Bitvectors

```prolog
# 8-bit arithmetic with overflow detection
Overflow(X, Y, SUM, OVERFLOW) <- (
    in_z3_bv([X, Y], 8),              # 8-bit bitvectors
    SUM == bv_add(X, Y),
    sat_z3(BoolEq(OVERFLOW, bv_ugt(SUM, X))),
    label_z3_bv([X, Y])
)
```

```python
def in_z3_bv(var_or_list, width, trail):
    """Declare bitvector variable(s) of given width."""
    state = get_z3_state(trail)
    for v in to_var_list(var_or_list):
        z3_var_for(v, z3.BitVecSort(width), trail)
    return True
```

### Arrays

```prolog
# Array constraints
ArrayExample(A, V) <- (
    z3_array(A, int, int),              # Array(IntSort, IntSort)
    z3_store(A, 0, 42, A1),            # A1 = Store(A, 0, 42)
    z3_select(A1, 0, V),               # V = Select(A1, 0)
    label_z3([V])                       # V = 42
)
```

### Strings

```prolog
# String constraints
StringExample(S, N) <- (
    z3_string(S),
    z3_str_contains(S, "hello"),
    z3_str_length(S, N),
    N <= 10,
    label_z3_str([S])
)
```

### Quantifiers

```prolog
# Universal quantification
AllPositive(F) <- (
    z3_function(F, int, int),
    z3_forall(X, z3_implies(X > 0, f(X) > 0)),
    z3_check()                          # satisfiable?
)
```

### Sets

```prolog
# Set constraints
SetExample(S1, S2, INTER) <- (
    z3_set(S1, int),
    z3_set(S2, int),
    z3_set_add(S1, 1, S1a),
    z3_set_add(S1a, 2, S1b),
    z3_set_add(S2, 2, S2a),
    z3_set_add(S2a, 3, S2b),
    z3_set_intersect(S1b, S2b, INTER),
    z3_set_member(2, INTER)             # 2 ∈ S1 ∩ S2
)
```

---

## Phase 7 — Optimization & Soft Constraints

**Goal:** Expose Z3's `Optimize` solver for optimization problems.

### Clausal Syntax

```prolog
# Hard + soft constraints
Scheduling(TASKS, COST) <- (
    in_z3(TASKS, 0, 100),
    all_different_z3(TASKS),
    # Hard constraints
    nth(1, TASKS, T1), nth(2, TASKS, T2),
    T1 + 5 <= T2,                       # Task 1 before Task 2
    # Soft constraints (preferences with weights)
    z3_soft(T1 <= 10, 3),               # prefer T1 early (weight 3)
    z3_soft(T2 <= 20, 2),               # prefer T2 early (weight 2)
    # Minimize total cost
    minimize_z3(T1 + T2, COST)
)

# MaxSAT
MaxSAT(VARS, SATISFIED) <- (
    z3_bool_vars(VARS, 5),              # 5 Boolean variables
    # Hard constraint
    sat_z3(nth(1,VARS) | nth(2,VARS)),
    # Soft constraints
    z3_soft(nth(1,VARS), 1),
    z3_soft(~nth(3,VARS), 2),
    z3_soft(nth(4,VARS) & nth(5,VARS), 3),
    z3_max_sat(SATISFIED)
)
```

### Implementation

```python
def z3_soft(constraint_expr, weight, trail):
    """Add a soft constraint with weight to the Z3 Optimize solver."""
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(constraint_expr, trail)
    state.ensure_optimize()  # switch to Optimize if not already
    state.optimizer.add_soft(z3_expr, weight)
    return True
```

---

## Phase 8 — Diagnostics (Unsat Cores, Explanations)

**Goal:** Expose Z3's diagnostic capabilities for debugging constraint programs.

### Clausal Syntax

```prolog
# Get unsat core when constraints are unsatisfiable
Debug(CORE) <- (
    in_z3([X, Y], 1, 5),
    z3_named(X > 3, "x_big"),
    z3_named(X < 2, "x_small"),
    z3_named(Y == X, "y_eq_x"),
    z3_unsat_core(CORE)                 # CORE = ["x_big", "x_small"]
)

# Check if a constraint is implied by the current store
Entailed(X) <- (
    in_z3(X, 1, 5),
    X > 3,
    z3_entailed(X > 2, TRUE),          # TRUE = true (implied)
    z3_entailed(X > 4, MAYBE)          # MAYBE = unknown
)
```

### Implementation

```python
def z3_unsat_core(core_var, trail):
    """Get the unsat core as a list of constraint names."""
    state = get_z3_state(trail)
    if state.solver.check() == z3.unsat:
        core = [str(c) for c in state.solver.unsat_core()]
        return unify(core_var, core, trail)
    return False


def z3_entailed(constraint_expr, result_var, trail):
    """Check if constraint is implied by current store.

    Checks solver.check(Not(constraint)) == unsat.
    """
    state = get_z3_state(trail)
    z3_expr = clausal_to_z3(constraint_expr, trail)

    state.solver.push()
    state.solver.add(z3.Not(z3_expr))
    r = state.solver.check()
    state.solver.pop()

    if r == z3.unsat:
        return unify(result_var, True, trail)
    elif r == z3.sat:
        return unify(result_var, False, trail)
    else:
        return unify(result_var, "unknown", trail)
```

---

## Appendix A — Z3 Python API Ergonomics

### Push/Pop — Built-in Context Manager

Z3's `Solver` implements `__enter__`/`__exit__`:

```python
with solver:                    # solver.push()
    solver.add(x < 10)
    with solver:                # nested push
        solver.add(x == 5)
        solver.check()
    # inner pop
# outer pop
```

### Solver.check() Inside Generators — Works

```python
def all_solutions(solver, variables):
    while solver.check() == sat:
        m = solver.model()
        yield m
        solver.add(Or([v != m.eval(v, model_completion=True) for v in variables]))
```

Z3 state persists across `yield`. `check()` is a blocking C call; the
generator suspends normally.

**Caveat:** If you `push()` before `yield` and the consumer abandons the
generator, the `pop()` never runs → scope leaks. Use `with solver:` or
`try/finally`. For Clausal, we avoid this by using `trail.record()` for
cleanup instead of relying on generator finalization.

### UserPropagateBase — Inverted Control, No Yield

```python
class MyPropagator(UserPropagateBase):
    def push(self): ...          # Z3 calls this (CDCL decision)
    def pop(self, n): ...        # Z3 calls this (backtrack)
    def fresh(self, ctx): ...    # Z3 calls this (parallel clone)

    def on_fixed(self, x, v):    # Z3 calls this (variable assigned)
        self.propagate(expr, ids)      # tell Z3 a consequence
        self.conflict(ids)             # tell Z3 about a conflict
```

You **cannot yield** from these callbacks — Z3 owns the call stack during
`check()`. But you **can** start a new Clausal trampoline (it's just a
while loop) and run it to completion synchronously.

### Performance Notes

- `push()`/`pop()` prevents some Z3 preprocessing optimizations. For
  one-shot problems, a fresh solver per check may be faster.
- Z3's `SolverFor("QF_LIA")` selects a logic-specific solver that may be
  orders of magnitude faster for the right domain.
- `model_completion=True` is essential when variables may be unconstrained.
- Z3 solver objects are **not thread-safe**. Each thread needs its own.

---

## Appendix B — Existing Prolog + Z3 Projects

### swi-prolog-z3

Repository: `github.com/turibe/swi-prolog-z3`

Three-tier architecture: C FFI → Prolog wrapper → high-level API. Maps Prolog
attributed variables to Z3 constants. Uses Z3 push/pop for Prolog backtracking.
Supports int/real/bool, propositional logic, equality, arithmetic, bitvectors.
Includes QuickXplain for minimal unsatisfiable subsets.

**Relevance:** Closest prior art. Clausal's architecture (Python + AttVar +
Trail) supports the same approach with less FFI friction since Z3 has a native
Python API.

### SWIPrologZ3

Repository: `github.com/mistupv/SWIPrologZ3`

Simpler integration via `swipl-ld`. Same basic approach.

### Philip Zucker's Z3 AST Prolog

Blog: `philipzucker.com/knuck_prolog/`

Builds a Prolog interpreter directly on Z3's ExprRef AST — uses Z3's built-in
unification. Novel but acknowledged as inefficient. Demonstrates that Z3's
expression language is rich enough to represent Prolog terms.

### IDP-Z3

Documentation: `docs.idp-z3.be`

Knowledge-base system built on Z3. Implements model expansion, propagation,
and optimization. Closest to the "Z3 as backend" architecture we propose.

---

## Summary: Phase Dependencies

```
Phase 1 (Core Infrastructure)
  │
  ├── Phase 2 (Integer Constraints)
  │     │
  │     └── Phase 7 (Optimization)
  │
  ├── Phase 3 (Boolean Constraints)
  │     │
  │     └── Phase 8 (Diagnostics)
  │
  ├── Phase 4 (Real/Rational Constraints)
  │     │
  │     └── Phase 7 (Optimization)
  │
  └── Phase 5 (UserPropagateBase)
        │
        └── Phase 6 (Advanced Theories)
```

Phases 2, 3, and 4 are independent of each other and can proceed in parallel
after Phase 1. Phase 5 is also independent but more complex. Phases 6, 7, 8
build on the earlier phases as shown.

---

## Predicate Naming Convention and Future Disambiguation

All Z3 predicates use explicit, unambiguous functor names with a `_z3` suffix
(`z3_eq`, `z3_ne`, `in_z3`, `all_different_z3`, `label_z3`, `sat_z3`, etc.).
Standard Clausal operators (`!=`, `==`, `+`) continue to route to their existing
solvers (CLP(FD), CLP(B), etc.) and are never implicitly redirected to Z3.

This is the correct design. The planned long-term approach to multi-solver
disambiguation follows the Prolog CLPQR `{}` convention:

```prolog
% Route all constraints in {} to the named solver:
z3({ S != 0, S*1000 + E*100 + N*10 + D + M*1000 + ... == M*10000 + ... })

% Or qualified by solver variant:
clpz({ X in 1..9, all_different([X,Y,Z]) })
z3.portfolio({ X > 0, X*X < 100 })
```

Under this scheme the parser/compiler sees a single functor `z3/1` (or `clpz/1`
etc.) whose argument is a conjunction of constraints expressed in standard Clausal
operator syntax. The wrapper dispatches the entire block to the named solver,
preserving familiar operator notation inside without touching the dispatch layer
of any other solver.

**Until that wrapper is implemented**, use the explicit `_z3`-suffixed predicates.
All phase plans are written with this convention. Do not add implicit dispatch
hooks (e.g., `fd_eq` checking for a Z3 attribute) as they would be removed when
the wrapper arrives.
