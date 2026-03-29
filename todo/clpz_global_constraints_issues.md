# Known issues with CLP(Z) global constraints implementation

## Correctness

### 1. Cumulative uses stale domain snapshots for compulsory parts

`CumulativeConstraint.propagate()` snapshots `s_lo`/`s_hi` for all tasks at the
top of propagation, then uses those stale values when computing compulsory parts
while filtering later tasks.  If narrowing task i tightens its bounds, the
compulsory-part calculation for task j (j > i) still uses the old bounds.

**Effect**: Weaker filtering, not unsoundness — the AC-3 fixpoint loop will
re-propagate until stable, but each pass does less work than it could.

**Fix**: Re-read `domain_min`/`domain_max` from the live FD state inside the
inner loop instead of using the `tasks_info` snapshot.

### 2. Cumulative and TuplesIn silently skip unbounded domain intervals

Both constraints guard their per-value enumeration with:
```python
if t_lo == _NEG_INF or t_hi == _POS_INF:
    continue  # skip unbounded intervals
```

This means a variable with domain `(-inf, +inf)` or `(0, +inf)` gets **zero
filtering** from these constraints.  For cumulative this is arguably acceptable
(you need finite bounds for scheduling), but TuplesIn should be able to narrow
an unbounded var to the finite set of values that appear in the relation.

**Fix for TuplesIn**: Instead of iterating domain values and removing
disallowed ones, build the allowed domain directly from the relation and
intersect it with the current domain:
```python
allowed_dom = ()
for val in sorted(allowed):
    allowed_dom = domain_union(allowed_dom, domain_from_range(val, val))
new_d = domain_intersection(state.domain, allowed_dom)
```

**Fix for cumulative**: Require finite domains at posting time (raise
`ValueError` if any start var has an unbounded domain), matching the semantics
of SWI-Prolog's `cumulative/2` which expects `Tasks` to have finite domains.

### 3. TuplesIn per-value removal is O(domain_size * relation_size)

The narrowing loop iterates every integer in every domain interval, calling
`domain_remove` for each disallowed value.  Each `domain_remove` rebuilds the
domain tuple.  For a domain of size N with K removals this is O(N * K * N)
in the worst case (quadratic in domain size per removal).

**Fix**: Same as #2 — build the allowed domain from the relation and intersect,
which is O(|relation| log |relation| + |domain|).

## Performance

### 4. Cumulative time-table is per-value, not event-point-based

The filtering loop iterates `range(t_lo, t_hi + 1)` for each domain interval of
each task, and for each candidate start time checks `range(t, t + duration)`
time points.  This is O(D * W * K) per task (D = domain size, W = max duration,
K = number of tasks), giving O(D * W * K^2) total.

Real time-table implementations work with **event points** (the union of all
interval endpoints) rather than individual time values, achieving O(K^2)
per propagation pass regardless of domain size.

**When this matters**: Scheduling problems with horizons of hundreds or
thousands and many tasks.  For small toy problems (< 20 tasks, horizon < 50)
the current implementation is fine.

## Missing constraints from the todo

### 5. `automaton/8` not implemented (Tier 1)

The todo lists `automaton/8` as Tier 1 / high priority.  It was not implemented
because it requires building a layered DAG from a finite automaton specification
and propagating arc-inconsistency — significantly more complex than the other
constraints.

### 6. `lex_chain/1` not implemented (Tier 2)

Lexicographic ordering of lists.  Not implemented.  Could be decomposed into
a sequence of `zcompare` + implications, or implemented as a dedicated
constraint with a simple left-to-right propagation algorithm.

### 7. Tier 3 constraints not implemented

`serialized/2`, `disjoint2/1`, `geost/2` — listed as lower priority in the
todo and not implemented.
