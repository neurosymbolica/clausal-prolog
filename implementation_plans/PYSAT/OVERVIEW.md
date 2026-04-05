# PySAT Integration for Clausal

A plan to integrate PySAT (python-sat) as a Boolean satisfiability backend for
Clausal, providing access to 15+ state-of-the-art SAT solvers through a
per-solver constraint block API that follows the established CLP module pattern.

---

## Sub-Plans (Detailed)

| Phase | Sub-Plan | Focus |
|-------|----------|-------|
| 1 | [PHASE1_CORE_INFRASTRUCTURE.md](PHASE1_CORE_INFRASTRUCTURE.md) | SATState, Var mapping, activation literals, trail sync |
| 2 | [PHASE2_CNF_TRANSLATION.md](PHASE2_CNF_TRANSLATION.md) | Tseitin transformation, constraint blocks, labeling |
| 3 | [PHASE3_CARDINALITY_PB.md](PHASE3_CARDINALITY_PB.md) | Cardinality constraints, pseudo-Boolean via pysat.card/pb |
| 4 | [PHASE4_BUILTINS_API.md](PHASE4_BUILTINS_API.md) | Builtin registration, .clausal integration, docs |

---

## Table of Contents (this document)

1. [Motivation](#1-motivation)
2. [Why Wrap PySAT, Not Individual Solvers](#2-why-wrap-pysat-not-individual-solvers)
3. [Architecture Overview](#3-architecture-overview)
4. [The Activation Literal Technique](#4-the-activation-literal-technique)
5. [Operator Syntax](#5-operator-syntax)
6. [API Design](#6-api-design)
7. [Phase Summaries](#7-phase-summaries)
8. [Comparison with Existing Backends](#8-comparison-with-existing-backends)
9. [Appendix A: PySAT Solver Overview](#appendix-a-pysat-solver-overview)
10. [Appendix B: Existing Prolog + SAT Projects](#appendix-b-existing-prolog--sat-projects)

---

## 1. Motivation

Clausal has two existing ways to handle Boolean constraints:

| Module | Algorithm | Strengths | Weaknesses |
|--------|-----------|-----------|------------|
| `clpb.py` | BDDs (Triska design) | Exact model counting, tautology check, projection | Exponential blowup on some formulas |
| `clpz3.py` (BoolSort) | Z3 DPLL(T) | Theory combination, optimization | Heavy startup, overkill for pure SAT |

Neither leverages the decades of engineering in **dedicated CDCL SAT solvers**.
Modern solvers like CaDiCaL, Kissat, and Glucose can handle millions of
variables and clauses, with conflict-driven clause learning, restarts, and
phase saving.  For pure Boolean satisfiability problems (graph coloring, circuit
verification, scheduling, combinatorial puzzles, cryptanalysis), a native SAT
solver is dramatically faster than both BDDs and SMT.

PySAT provides a unified Python interface to 15+ such solvers.  Integrating it
gives Clausal users access to industrial-strength SAT solving with the familiar
constraint block syntax.

---

## 2. Why Wrap PySAT, Not Individual Solvers

PySAT already provides `Solver(name='cadical195')` with a unified API over all
backends.  Wrapping PySAT rather than individual solver C libraries:

- **One integration layer** for 15+ solvers (CaDiCaL, Glucose, Minisat, Kissat,
  Lingeling, Maplesat, CryptoMinisat, Mergesat, Minicard, ...)
- **Maintained upstream**: PySAT handles version tracking, build, ABI changes
- **Rich encodings**: `pysat.card` (cardinality), `pysat.pb` (pseudo-Boolean),
  `pysat.formula` (CNF/WCNF) come for free
- **Single `pip install python-sat`** — no per-solver packaging headaches

---

## 3. Architecture Overview

Follows the established pattern from `clpz3.py`:

```
Clausal Var  <--->  SAT variable number (positive int)
     |
SATState (per Trail) {
  solver:         pysat.solvers.Solver instance
  var_map:        dict[int, int]     # id(Var) -> SAT var number
  rev_map:        dict[int, Var]     # SAT var number -> Var
  assumptions:    list[int]          # active activation literals
  _counter:       int                # next SAT variable number
  solver_name:    str                # e.g. 'cadical195'
}
     |
Trail.record(callback) -> remove activation lit from assumptions
```

**Variable mapping**: Each Clausal `Var` that participates in SAT constraints
gets a unique positive integer.  The mapping is cached in `var_map` (keyed by
`id(Var)`) and reverse-mapped in `rev_map`.  A `SATVarInfo` attribute is stored
on the Var under key `"sat"` (trail-safe via `put_attr`).

**State lifecycle**: One `SATState` per Trail, keyed by `id(trail)` in a
module-level dict.  Cleaned up via `weakref.finalize` when the Trail is GC'd.

**Solver selection**: The solver name is fixed when the first constraint block
is posted on a given Trail.  Mixing solvers within a single query is an error.

---

## 4. The Activation Literal Technique

### The problem

PySAT solvers **do not support push/pop**.  Once `add_clause([1, -2, 3])` is
called, that clause is permanent.  This is fundamentally different from Z3 where
`solver.push()/pop()` syncs directly with Clausal's trail.

### The solution

**Activation literals** (also called "assumption variables" or "selector
variables") are a standard technique in incremental SAT solving.

Instead of adding a clause directly:

    add_clause([x, -y, z])          # permanent!

We create a fresh activation variable `a` and add a guarded clause:

    add_clause([-a, x, -y, z])      # dormant unless a is assumed True

When solving, we pass all active activation literals as assumptions:

    solver.solve(assumptions=[a1, a2, a3, ...])

The solver treats assumptions as unit clauses for that solve call only.  Clauses
guarded by `a1` are only active when `a1` is in the assumptions list.

### Trail synchronization

```python
def sat_push(trail: Trail) -> None:
    """Create a new activation literal scope."""
    state = get_sat_state(trail)
    state._counter += 1
    act_lit = state._counter        # fresh variable
    state.assumptions.append(act_lit)
    trail.record(lambda: state.assumptions.remove(act_lit))
```

On backtrack, `trail.undo(mark)` fires the callback, removing the activation
literal from the assumptions list.  The guarded clauses remain in the solver but
become dormant — they cannot contribute to unit propagation or conflict analysis
when their guard is absent.

### Why this works for nested search

```
Outer scope:  assumptions = [a1]
  Inner scope: assumptions = [a1, a2]
    Deepest:   assumptions = [a1, a2, a3]
  Backtrack:   assumptions = [a1, a2]      # a3 removed
Backtrack:     assumptions = [a1]           # a2 removed
```

Each nesting level adds its own activation literal.  Unwinding removes them in
LIFO order.  This perfectly mirrors trail-based backtracking.

### Performance implications

- **Clause learning is preserved**: Clauses learned during one `solve()` call
  remain useful in subsequent calls, even after backtracking.  This is a net
  performance *win* over push/pop, which discards learned clauses.
- **Memory**: Dormant clauses consume memory but are cheap (just integers).
  For very long searches, the solver can be periodically recreated.
- **Assumptions overhead**: Minimal — assumptions are processed once at the
  start of each `solve()` call via unit propagation.

---

## 5. Operator Syntax

Clausal's compiler transforms Python operators into AST nodes in `.clausal`
files:

| Python syntax | AST node | SAT meaning |
|---|---|---|
| `X \| Y` | `BitOr(left, right)` | Disjunction (OR) |
| `X & Y` | `BitAnd(left, right)` | Conjunction (AND) |
| `~X` | `Invert(operand)` | Negation (NOT) |
| `X ^ Y` | `BitXor(left, right)` | Exclusive OR (XOR) |

These are the same nodes used by CLP(B)'s `sat()` and Z3's `z3.boolean(())`.
No new operator machinery is needed.

Python's `and`/`or`/`not` keywords cannot be overloaded (they short-circuit),
so the bitwise operators are the correct and only choice.  This is consistent
with SWI-Prolog's CLP(B) which also uses `#\` (not), `#/\` (and), `#\/` (or),
`#\` (xor) — non-arithmetic operator symbols.

**Within a constraint block**, each top-level element in the tuple is a clause
(disjunction).  Elements are combined conjunctively (all must hold):

```python
# In .clausal file:
pysat.cadical((
    X | Y,          # clause 1: (X v Y)
    ~X | Z,         # clause 2: (!X v Z)
    ~Y | ~Z,        # clause 3: (!Y v !Z)
))
```

**Nested Boolean operators** are supported via Tseitin transformation — `&`
and `^` within a clause are automatically converted to auxiliary CNF clauses:

```python
# This:
pysat.cadical(((X & Y) | Z,))

# Becomes (via Tseitin):
#   t <-> (X & Y)        auxiliary variable t
#   (t | Z)              original clause with t substituted
# Encoded as CNF:
#   (~t | X), (~t | Y), (t | ~X | ~Y), (t | Z)
```

---

## 6. API Design

### Constraint block builtins (one per solver)

```python
pysat.cadical((X | Y, ~X | Z))       # CaDiCaL 1.9.5
pysat.glucose((X | Y, ~X | Z))       # Glucose 4.2.1
pysat.minisat((X | Y, ~X | Z))       # MiniSat 2.2
pysat.kissat((X | Y, ~X | Z))        # Kissat
pysat.lingeling((X | Y, ~X | Z))     # Lingeling
pysat.maplesat((X | Y, ~X | Z))      # MapleLCM/MapleChrono
pysat.mergesat((X | Y, ~X | Z))      # Mergesat 3
pysat.minicard((X | Y, ~X | Z))      # Minicard (native cardinality)
```

Each posts Boolean constraints to the named solver.  The first call on a given
Trail creates the solver; subsequent calls on the same Trail reuse it (and must
use the same solver name).

### Labeling and query builtins

```python
pysat.solve(Vars)                     # enumerate satisfying 0/1 assignments
pysat.check                           # succeed iff current constraints are SAT
pysat.count(Vars, N)                  # N = number of satisfying assignments
pysat.model(Vars, Model)              # Model = list of 0/1 values (first soln)
```

### Cardinality and pseudo-Boolean builtins

```python
pysat.at_most(Vars, K)               # at most K variables are 1
pysat.at_least(Vars, K)              # at least K variables are 1
pysat.exactly(Vars, K)               # exactly K variables are 1
```

These use PySAT's `pysat.card.CardEnc` to generate CNF encodings (sequential
counter by default; configurable).

### Example: 3-coloring in .clausal

```prolog
-use_module(pysat).

color(Node, R, G, B) :-
    pysat.cadical((R | G | B,)),       % at least one color
    pysat.at_most([R, G, B], 1).       % at most one color

edge_constraint(R1, G1, B1, R2, G2, B2) :-
    pysat.cadical((
        ~R1 | ~R2,                     % not both red
        ~G1 | ~G2,                     % not both green
        ~B1 | ~B2                      % not both blue
    )).

three_color(Vars) :-
    color(a, AR, AG, AB),
    color(b, BR, BG, BB),
    color(c, CR, CG, CB),
    edge_constraint(AR, AG, AB, BR, BG, BB),
    edge_constraint(BR, BG, BB, CR, CG, CB),
    edge_constraint(AR, AG, AB, CR, CG, CB),
    Vars = [AR, AG, AB, BR, BG, BB, CR, CG, CB],
    pysat.solve(Vars).
```

---

## 7. Phase Summaries

### Phase 1: Core Infrastructure

**File**: `clausal/logic/clpsat.py` (first ~300 lines)

- `SATVarInfo` — attribute stored on Var under key `"sat"`
- `SATState` — per-Trail solver state
- `get_sat_state(trail, solver_name)` — state registry with weakref cleanup
- `sat_var_for(var, trail)` — bidirectional variable mapping
- `sat_push(trail)` — activation literal scope management
- `sat_add_clause(clause, trail)` — add activation-guarded clause
- `sat_check(trail)` — satisfiability test with current assumptions
- Basic tests: variable mapping, clause addition, backtracking, UNSAT

### Phase 2: CNF Translation & Labeling

**File**: `clausal/logic/clpsat.py` (next ~300 lines)

- `clausal_to_literal(expr, trail)` — translate Var/ground to signed SAT literal
- `clausal_to_cnf(expr, trail)` — Tseitin transformation for arbitrary Boolean
  expressions (BitOr, BitAnd, BitXor, Invert, Not, And, Or) into CNF clauses
- `sat_constraint_block(constraint_set, solver_name, trail)` — walk tuple,
  translate each element, add clauses
- `label_sat(vars_list, trail)` — enumerate satisfying assignments:
  solve + extract model + bind Clausal vars + add blocking clause + repeat
  (same pattern as `label_z3` in `clpz3.py:478-543`)
- `sat_count(vars_list, trail)` — count solutions
- Tests: constraint blocks, Tseitin correctness, labeling, blocking clauses

### Phase 3: Cardinality & Pseudo-Boolean

**File**: `clausal/logic/clpsat.py` (next ~150 lines)

- `sat_at_most(vars_list, k, trail)` — encode via `CardEnc.atmost`
- `sat_at_least(vars_list, k, trail)` — encode via `CardEnc.atleast`
- `sat_exactly(vars_list, k, trail)` — encode via `CardEnc.equals`
- Optional: `sat_pb_leq/geq/eq` via `pysat.pb.PBEnc` for weighted constraints
- Auxiliary variables from encodings are tracked in `SATState._counter`
- Tests: pigeonhole, at-most-one, exactly-k

### Phase 4: Builtins & Module API

**Files**: `clausal/logic/builtins/sat_constraints.py`, update to
`clausal/logic/builtins/constraints.py`

- Register `pysat.cadical/1`, `pysat.glucose/1`, etc.
- Register `pysat.solve/1`, `pysat.check/0`, `pysat.count/2`
- Register `pysat.at_most/2`, `pysat.at_least/2`, `pysat.exactly/2`
- Integration tests with `.clausal` files
- Documentation examples

---

## 8. Comparison with Existing Backends

| Feature | CLP(B) | Z3 BoolSort | PySAT |
|---------|--------|-------------|-------|
| **Algorithm** | BDDs | DPLL(T) | CDCL |
| **Scalability** | ~100 vars | ~10K vars | ~1M+ vars |
| **Model counting** | Exact (polynomial for BDDs) | Approximate | Enumeration |
| **Tautology check** | Native (BDD == TRUE) | solver.check(Not(e)) | Not direct |
| **Theory combination** | No | Yes (all Z3 sorts) | No (Boolean only) |
| **Incremental** | Natural | Push/Pop | Assumptions |
| **Backtracking** | Trail-safe BDD nodes | solver.push()/pop() | Activation literals |
| **Cardinality** | BDD encoding | Z3 PbLe/PbGe | pysat.card (10 encodings) |
| **Optimization** | No | Yes (maximize/minimize) | No (use MaxSAT separately) |
| **Use case** | Small Boolean, counting | Mixed theories, optimization | Large pure SAT |

---

## Appendix A: PySAT Solver Overview

PySAT provides unified access to these solvers via `Solver(name='abbr')`:

| Solver | Abbreviation | Notable Features |
|--------|-------------|------------------|
| CaDiCaL 1.9.5 | `cadical195` | CDCL, fastest all-rounder, SAT Competition winner |
| CaDiCaL 1.5.3 | `cadical153` | Stable older version |
| Glucose 4.2.1 | `g421` | LBD-based clause management |
| Glucose 4.1 | `g4` | Older Glucose |
| Glucose 3.0 | `g3` | Classic Glucose |
| Kissat | `kissat` | By CaDiCaL author, SAT Competition 2020 winner |
| Lingeling | `lgl` | Maintained by Armin Biere |
| MapleLCM | `mcl` | SAT Competition 2017 winner |
| MapleChrono | `mcb` | Chronological backtracking |
| Maplesat | `mpl` | Learning-rate branching |
| Mergesat 3 | `mg3` | Merge resolution |
| Minisat 2.2 | `m22` | Classic CDCL reference implementation |
| Minisat (GitHub) | `mgh` | Updated Minisat |
| Minicard | `mc` | Native cardinality constraints |
| CryptoMinisat | (via formula) | Native XOR constraints |

**Default recommendation**: `cadical195` — consistently the fastest modern
solver across diverse benchmarks.

---

## Appendix B: Existing Prolog + SAT Projects

### SICStus Prolog CLP(B)

Markus Triska's CLP(B) uses BDDs, not SAT solvers.  The `sat/1` predicate
posts a BDD constraint.  Model counting and tautology checking are native BDD
operations.  Clausal's `clpb.py` is based on this design.

### SWI-Prolog + PicoSAT

SWI-Prolog has `library(sat)` binding PicoSAT, but it is minimal: just
`sat(+Clauses)` returning a model.  No incremental solving, no backtracking
integration, no constraint propagation.

### ECLiPSe ic library

ECLiPSe's `ic` library can delegate Boolean subproblems to a SAT solver, but
the integration is at the propagator level (domain filtering), not at the
user-facing constraint level.

### The Clausal approach

Clausal's PySAT integration is closer to the ECLiPSe model in spirit but with
a cleaner user-facing API.  The activation literal technique for backtracking
is well-established in the SAT solving community (MiniSat's original
incremental interface, IPASIR standard) but has not been applied to Prolog-style
logic programming trail-based backtracking before.  This is a novel combination.

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `clausal/logic/clpsat.py` | Create | Core SAT integration (~600-800 lines) |
| `clausal/logic/builtins/sat_constraints.py` | Create | Builtin registrations (~80-100 lines) |
| `clausal/logic/builtins/constraints.py` | Modify | Import sat_constraints module |
| `tests/test_clpsat.py` | Create | Test suite (~200-300 lines) |

---

## Verification

```bash
pip install python-sat
pytest tests/test_clpsat.py -v
```

Quick smoke test (Python):

```python
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.clpsat import sat_constraint_block, label_sat

trail = Trail()
x, y, z = Var(), Var(), Var()
# (x | y) & (~x | z) & (~y | ~z)
from clausal.pythonic_ast.nodes import BitOr, Invert
sat_constraint_block((
    BitOr(left=x, right=y),
    BitOr(left=Invert(operand=x), right=z),
    BitOr(left=Invert(operand=y), right=Invert(operand=z)),
), 'cadical195', trail)
solutions = []
for _ in label_sat([x, y, z], trail):
    solutions.append((deref(x), deref(y), deref(z)))
print(solutions)  # [(1, 0, 1), (0, 1, 0), (1, 1, 0)]
```
