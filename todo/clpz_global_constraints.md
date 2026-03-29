# Add CLP(Z) global constraints

## Context

Triska's `library(clpz)` provides global constraints that are the bread and
butter of practical constraint programming — scheduling, rostering, vehicle
routing, etc.  Clausal currently has `all_different/1`, `element/3`,
`circuit/1`, `sum_/3`, and `scalar_product/4`.  Several important global
constraints are missing.

This todo should be done AFTER `clpz_upgrade.md` (infinite domain support).

## What to add

### Tier 1 — High priority (widely used)

**`cumulative/2`** — resource-constrained scheduling
```
cumulative(Tasks, Options)
```
Each task has start time, duration, end time, and resource consumption.
The constraint ensures that at no point does the total resource consumption
exceed a given limit.  This is THE constraint for job-shop scheduling.

**Implementation**: Use the "time-table" filtering algorithm (O(n^2) per
propagation) for a first version.  Can upgrade to "timetable edge-finding"
later.

**`global_cardinality/2`** — counting constraint
```
global_cardinality(Vars, Pairs)
```
Pairs is a list of `Value-Count` pairs.  The constraint ensures that each value
appears exactly Count times in Vars.  Used in rostering, Sudoku variants, etc.

**Implementation**: Decompose into `sum` constraints per value, or implement
the dedicated propagation algorithm (bounds-consistency via flow networks).

**`automaton/8`** — finite automaton constraint
```
automaton(Sequence, Template, Signature, Nodes, Arcs, Sink, Counters, Options)
```
Constrains a sequence of variables to follow transitions of a finite automaton.
Used for pattern constraints (e.g., "no three consecutive shifts").

**Implementation**: Build a layered DAG from the automaton and variable domains,
then propagate by removing arc-inconsistent values.  This is complex but
well-documented in the constraint programming literature.

### Tier 2 — Moderate priority

**`chain/2`** — ordering constraint
```
chain(Vars, Relation)
```
Posts Relation between consecutive pairs: `chain([A,B,C], #<)` means `A #< B, B #< C`.
Simple decomposition — just post pairwise constraints.

**`lex_chain/1`** — lexicographic ordering
```
lex_chain(Lists)
```
Each list is lexicographically ≤ the next.  Used in symmetry breaking.

**`tuples_in/2`** — table constraint
```
tuples_in(Tuples, Relation)
```
Each tuple in Tuples must be a member of Relation (a list of allowed tuples).
Used for extensional constraints (truth tables).

**Implementation**: GAC via "simple tabular reduction" (STR) or compressed
table representation.

**`zcompare/3`** — three-way comparison
```
zcompare(Order, X, Y)
```
Order is `<`, `=`, or `>` depending on X vs Y.  Reified comparison.

### Tier 3 — Lower priority

**`serialized/2`** — disjunctive scheduling (no resource sharing)
**`disjoint2/1`** — 2D rectangle non-overlap
**`geost/2`** — geometric constraint (n-dimensional non-overlap)

## Gotchas

1. **`cumulative` is the most complex** to implement correctly.  Start with the
   simple time-table algorithm: for each time point in the union of all task
   intervals, check that total consumption ≤ limit.  This is O(n^2) but correct.

2. **`automaton` requires understanding the layered-graph representation**.  See
   Beldiceanu, Carlsson, Petit (2004) "Deriving Filtering Algorithms from
   Constraint Checkers".

3. **All global constraints need trail integration** — when propagation narrows
   a domain, the change must be trailable.  Use the same `_narrow` / `put_attr`
   pattern as existing constraints.

4. **Propagation strength matters**.  `global_cardinality` with simple
   decomposition (sum constraints) gives weaker propagation than the dedicated
   flow-based algorithm.  Start with decomposition, add flow-based later.

5. **Test with real problems**: Sudoku (needs `all_different` — already done),
   N-queens (already done), job-shop scheduling (needs `cumulative`),
   nurse rostering (needs `global_cardinality` + `automaton`).

## Tests to write

Create `tests/test_global_constraints.py`.  Follow the pattern in
`tests/test_clpfd.py`: imports from `clausal.logic.variables` and
`clausal.logic.clpfd`.  Helper: `def fresh_trail(): return Trail()`.

### TestCumulative

```python
class TestCumulative:
    def test_no_overlap_two_tasks(self):
        """Two tasks needing full capacity cannot overlap."""
        trail = fresh_trail()
        s1, s2 = Var(), Var()
        # Task 1: start=s1, duration=3, resource=1
        # Task 2: start=s2, duration=2, resource=1
        # Capacity: 1
        assert in_domain([s1, s2], 0, 10, trail)
        assert cumulative(
            [(s1, 3, 1), (s2, 2, 1)],  # (start, duration, resource)
            1,  # capacity
            trail
        )
        assert fd_eq(s1, 0, trail)
        # s2 must start at 3 or later
        state = get_attr(s2, FD_KEY)
        assert domain_min(state.domain) >= 3

    def test_overlapping_tasks_within_capacity(self):
        """Two tasks with combined resource <= capacity CAN overlap."""
        trail = fresh_trail()
        s1, s2 = Var(), Var()
        assert in_domain([s1, s2], 0, 10, trail)
        assert cumulative(
            [(s1, 3, 1), (s2, 2, 1)],
            2,  # capacity 2 — both fit simultaneously
            trail
        )
        # Both can start at 0
        assert fd_eq(s1, 0, trail)
        assert fd_eq(s2, 0, trail)

    def test_three_tasks_propagation(self):
        """Three unit-duration tasks, capacity 1 → all different start times."""
        trail = fresh_trail()
        s1, s2, s3 = Var(), Var(), Var()
        assert in_domain([s1, s2, s3], 1, 3, trail)
        assert cumulative(
            [(s1, 1, 1), (s2, 1, 1), (s3, 1, 1)],
            1,
            trail
        )
        results = []
        for _ in label([s1, s2, s3], trail):
            results.append(sorted([deref(s1), deref(s2), deref(s3)]))
        # All solutions should be permutations of [1, 2, 3]
        assert all(r == [1, 2, 3] for r in results)

    def test_infeasible(self):
        """Three tasks of duration 2, capacity 1, horizon 4 → only if no overlap."""
        trail = fresh_trail()
        s1, s2, s3 = Var(), Var(), Var()
        assert in_domain([s1, s2, s3], 0, 2, trail)
        # 3 tasks × duration 2 = 6 time units needed, but horizon only 4
        # with capacity 1 — should fail
        result = cumulative(
            [(s1, 2, 1), (s2, 2, 1), (s3, 2, 1)],
            1,
            trail
        )
        if result:
            # If posting succeeds, labeling should find no solutions
            solutions = list(label([s1, s2, s3], trail))
            assert len(solutions) == 0
```

### TestGlobalCardinality

```python
class TestGlobalCardinality:
    def test_basic_cardinality(self):
        """[X, Y, Z] with value 1 appearing exactly twice."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 3, trail)
        # Value 1 appears 2 times, value 2 appears 1 time
        assert global_cardinality(
            [x, y, z],
            [(1, 2), (2, 1)],
            trail
        )
        results = []
        for _ in label([x, y, z], trail):
            results.append((deref(x), deref(y), deref(z)))
        # All solutions should have exactly two 1s and one 2
        for r in results:
            assert r.count(1) == 2
            assert r.count(2) == 1

    def test_cardinality_zero_count(self):
        """Value 3 appears 0 times → excluded from all vars."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 3, trail)
        assert global_cardinality([x, y], [(3, 0)], trail)
        # 3 should be removed from both domains
        sx = get_attr(x, FD_KEY)
        assert not domain_contains(sx.domain, 3)
```

### TestChain

```python
class TestChain:
    def test_increasing_chain(self):
        """chain([X, Y, Z], #<) → X < Y < Z."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 5, trail)
        assert chain([x, y, z], "lt", trail)
        # Should propagate: X in 1..3, Y in 2..4, Z in 3..5
        assert fd_eq(x, 1, trail)
        assert fd_eq(y, 2, trail)
        assert fd_eq(z, 3, trail)

    def test_decreasing_chain(self):
        """chain([X, Y, Z], #>) → X > Y > Z."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 3, trail)
        assert chain([x, y, z], "gt", trail)
        assert deref(x) == 3
        assert deref(y) == 2
        assert deref(z) == 1
```

### TestTuplesIn

```python
class TestTuplesIn:
    def test_basic_table(self):
        """[X, Y] must be one of [(1,2), (3,4)]."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert tuples_in([[x, y]], [(1, 2), (3, 4)], trail)
        results = []
        for _ in label([x, y], trail):
            results.append((deref(x), deref(y)))
        assert set(results) == {(1, 2), (3, 4)}

    def test_table_propagation(self):
        """If X=1, then Y must be 2 (only matching tuple)."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert tuples_in([[x, y]], [(1, 2), (3, 4)], trail)
        assert fd_eq(x, 1, trail)
        assert deref(y) == 2

    def test_table_no_match_fails(self):
        """If X=2, no tuple matches → fail."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert tuples_in([[x, y]], [(1, 2), (3, 4)], trail)
        assert not fd_eq(x, 2, trail)
```

### Edge cases across all global constraints

- **Empty task list**: `cumulative([], 1, trail)` → trivially true
- **Single task**: `cumulative([(s, 5, 1)], 1, trail)` → no constraint needed
- **Zero duration tasks**: `cumulative([(s, 0, 1)], 1, trail)` → trivially true
- **Empty tuple relation**: `tuples_in([[x, y]], [], trail)` → fails immediately
- **Chain of length 1**: `chain([x], "lt", trail)` → trivially true
- **Cardinality with variable count**: `global_cardinality([x, y], [(1, N)], trail)` where N is a Var
- **Backtracking**: all constraints must be undone cleanly by `trail.undo(mark)`

## How to verify

```bash
# New global constraint tests
python -m pytest tests/test_global_constraints.py -x -v

# Existing tests must still pass
python -m pytest tests/ -k "clpfd or clp_fd or nqueens or sudoku" -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q

# Benchmarks
python benchmarks/workloads.py
```
