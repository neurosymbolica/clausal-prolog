# Move CLP(B) BDD operations to C

## Context

`clausal/logic/clpb.py` (645 lines) implements the Boolean constraint solver
using Binary Decision Diagrams (BDDs).  BDD operations are pointer/node-heavy
with hash-consing and memoisation — classic C territory.

Not hot in current benchmarks, but essential for Boolean satisfiability,
circuit verification, and combinatorial problems.

## What to move

### Tier 1 — BDD node operations

```python
# clausal/logic/clpb.py

# BDD nodes are (var_id, lo_child, hi_child) triples
# with hash-consing in a global table

_bdd_node(var_id, lo, hi)     # create/retrieve node (hash-consed)
_bdd_and(a, b)                # conjunction with memoisation
_bdd_or(a, b)                 # disjunction
_bdd_not(a)                   # negation
_bdd_ite(f, g, h)             # if-then-else (core operation)
_bdd_restrict(node, var, val) # Shannon cofactor
_bdd_count(node)              # count satisfying assignments
_bdd_any_sat(node)            # find one satisfying assignment
```

### Tier 2 — Constraint interface

```python
sat(expr, trail)               # post Boolean constraint
taut(expr, t_var, trail)       # tautology check
sat_count(expr, count, trail)  # count solutions
bool_labeling(vars, trail)     # enumerate assignments
```

### Tier 3 — Variable ordering and reordering

```python
enumerate_var(var)             # assign ordering ID
_get_var_for_id(var_id)        # reverse lookup
```

## Build approach

Create `clausal/logic/_clpb_core.c`.  BDD implementations in C are well-studied
(e.g., BuDDy, CUDD).  The clausal implementation is simpler (no dynamic
reordering) but the same node representation works:

```c
typedef struct {
    int32_t var_id;
    int32_t lo;   // index into node table
    int32_t hi;   // index into node table
} BDDNode;

// Hash-consing: (var_id, lo, hi) → node_index
// Memo tables for and/or/ite operations
```

## Gotchas

1. **Hash-consing is critical** for BDD performance.  The Python implementation
   uses dicts.  The C version should use a dedicated hash table with open
   addressing for cache-friendliness.

2. **Garbage collection**: BDD nodes that are no longer reachable should be
   freed.  The Python implementation relies on Python GC.  A C implementation
   needs either reference counting or mark-and-sweep within the BDD arena.

3. **Variable ordering** dramatically affects BDD size.  The current
   implementation uses creation order.  If adding dynamic reordering later,
   design the C node table to support it.

4. **Integration with trail**: Boolean constraints create attributed variables.
   Backtracking must undo BDD assertions.  The trail integration follows the
   same pattern as CLP(FD).

## Overlaps

None with existing todos.  Independent of CLP(FD) and CLP(R).

## How to verify

```bash
python -m pytest tests/ -k "clpb or bool or sat" -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: BDD-heavy workloads (sat_count, large Boolean formulae) see 10–100x
speedup.  Result values must not change.
