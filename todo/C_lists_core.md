# Move core list predicates to C

## Context

`clausal/logic/builtins/lists.py` (610 lines) implements 28 list predicates.
Many are standard Prolog (ISO or SWI-Prolog).  The core predicates —
`append/3`, `length/2`, `member/2` (via `in_/2`), `reverse/2` — are called
from many user programs and internal operations.

Not separately visible in profiles (they run as compiled trampoline predicates
via the template system), but list operations are a fundamental building block.

## What to move

### Tier 1 — Most-used list predicates

```python
# clausal/logic/builtins/lists.py

append/3     # list concatenation — the most-used list predicate in Prolog
length/2     # list length (bidirectional)
in_/2        # member/2 — list membership with backtracking
reverse/2    # list reversal
last/2       # last element
```

### Tier 2 — Sorting and set operations

```python
msort/2          # merge sort (stable)
sort/2           # sort with dedup
permutation/2    # generate permutations (used in nqueens)
select/3         # select element from list
```

### Tier 3 — List manipulation

```python
flatten/2        # flatten nested lists
subtract/3       # list subtraction
intersection/3   # list intersection
union/3          # list union
list_to_set/2    # remove duplicates
take/3, drop/3   # list slicing
split_at/4       # split at index
zip_/3           # zip two lists
numlist/2,3      # generate number list
```

## Implementation approach

These predicates are currently implemented as Python generator functions that
follow the trampoline protocol or simple-mode protocol.  Moving them to C means
implementing them as C functions that produce solutions via the trampoline
protocol.

This is more complex than moving pure functions to C because:
1. Predicates produce multiple solutions (backtracking)
2. They call `unify()` which may fail (requiring trail undo)
3. They follow the trampoline protocol (yield generator tuples)

### Option A: C generators via the trampoline protocol

Implement each predicate as a C function that returns a `StepGenerator`-compatible
object.  This requires understanding the trampoline protocol in `_trampoline.c`.

### Option B: C helper functions called from Python generators

Keep the Python generator structure but replace the inner loops with C functions.
For example, `append/3` could call a C function that does the list walking and
unification, returning True/False per candidate.

### Option C: Direct iteration in C

For deterministic predicates (`length/2` in check mode, `reverse/2`), implement
as a single C function that calls `unify` once and returns True/False.  Only
non-deterministic predicates (member, append in generate mode) need the generator
structure.

**Recommendation:** Start with Option B for the hot predicates, then move to
Option A for the ones where Python generator overhead is measurable.

## Gotchas

1. **Bidirectional predicates** like `append/3` have multiple modes:
   - `append([1,2], [3], X)` — deterministic concatenation
   - `append(X, Y, [1,2,3])` — non-deterministic splitting
   - `append(X, [3], [1,2,3])` — pattern matching
   The C implementation must handle all modes.

2. **`permutation/2` is used in nqueens** — it shows up in the nqueens profile
   as `_permutation__2` with 40K calls / 0.043s.  This is a good candidate for
   C acceleration.

3. **Trail integration**: every `unify` call must go through the trail.  The C
   code must use the same `unify()` function from `_variables.c`.

4. **SegList handling**: some list operations may receive `SegList` objects
   (partially-bound lists from partial unification).  The C code must either
   handle SegLists or call back into Python for them.

5. **`in_/2` (member)** is the Prolog `member/2` — it iterates through a list
   yielding each element.  In the trampoline protocol, this means yielding
   `(parent, None)` for each solution.  The C version needs to produce these
   yield values.

## Overlaps

- `C_head_list_unify.md` — covers list destructuring in clause heads, which is
  the main list bottleneck.  This todo covers list PREDICATES (append, member,
  etc.) which are called from clause bodies.

## How to verify

```bash
python benchmarks/workloads.py
python -m pytest tests/ -k "list or append or member or sort" -x -q
python -m pytest tests/conformity/test_iso_list_operations.py -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: Programs heavy in list operations (qsort, graph) should see
improvement.  Result values must not change.
