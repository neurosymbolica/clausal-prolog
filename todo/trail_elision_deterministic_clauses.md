# Elide trail mark/undo for deterministic clauses

## Context

The compiler wraps every clause alternative in trail mark/undo pairs so that
bindings can be rolled back on backtracking.  For clauses that are deterministic
(single matching clause after indexing, no choice points in body), the mark/undo
is pure overhead.

### Profile data

| Operation | Benchmark | Calls | tottime |
|-----------|-----------|-------|---------|
| `trail.mark()` | fib | 1,485,365 | 0.145s |
| `trail.undo()` | fib | 635,618 | 0.059s |
| `trail.mark()` | nqueens | 2,178,057 | 0.192s |
| `trail.undo()` | nqueens | 2,420,842 | 0.230s |
| `trail.mark()` | tabling | 450,020 | 0.046s |
| `trail.undo()` | tabling | 451,526 | 0.045s |

Total across benchmarks: ~0.72s (mark) + ~0.33s (undo) = ~0.75s.  Even a 20%
reduction in call count would save ~0.15s.

### Existing optimization

The compiler already has a partial optimization: in `compile_head_to_match_case`
(compiler.py line ~7000), when a clause has no head variables, no dup guards,
and no list guards, the mark/undo is omitted.  This handles pure ground facts
like `edge(a, b)`.

### What remains

Clauses with head variables that are dispatched via first-argument indexing into
a single-clause bucket are effectively deterministic — if the index matched,
there's only one clause to try, so mark/undo is unnecessary (there's nothing to
backtrack to within this predicate).

## What to do

**File:** `clausal/logic/compiler.py`

### Approach: single-clause bucket elision

In `_make_groundness_dispatch_trampoline` and its simple-mode counterpart, when
building the index dict, detect buckets that contain exactly one clause and are
not the default fallback.  For those buckets, compile the clause body without
the mark/undo wrapper.

This requires:

1. **Detect single-clause buckets at compile time.**  In `_build_first_arg_index`
   (or wherever the index dict is constructed), tag each bucket with its clause
   count.

2. **Compile a "no-trail" variant** of the clause body for single-clause buckets.
   This means skipping the `mark_assign` and `undo_stmt` AST nodes in
   `compile_head_to_match_case` (line ~6794–6802).

3. **Ensure correctness**: the clause body itself might create choice points
   (e.g., calling a non-deterministic predicate).  The trail is still needed for
   the BODY's own internal mark/undo pairs.  What we're eliding is only the
   OUTER mark/undo that wraps the entire clause — the one that would undo head
   unification bindings on clause failure.  Since the clause is the only one in
   its bucket, "failure" means the whole predicate fails, and the caller's
   mark/undo will clean up.

### Gotchas (no prior attempt — this was deferred as too complex)

1. **The existing ground-head optimization is in `compile_head_to_match_case`**
   (compiler.py line ~7000).  Look for the condition
   `not head_var_ctx and not dup_guards and not list_guards`.  This is the
   starting point — understand what it does before extending.

2. **cProfile shows mark/undo tottime is already low per call** (~97ns for mark,
   ~93ns for undo — both are C functions).  The savings come from eliminating
   CALLS, not from making each call faster.  If you can't reduce the call count
   by at least 10–20%, don't bother.

3. **The trail is shared across the entire search tree.**  A clause's head
   bindings are trailed so that when the ENGINE backtracks past this clause, it
   can undo them.  If you skip trailing for a single-clause bucket, the bindings
   are still on the trail from the caller's mark.  Make sure the caller's undo
   will clean them up.

4. **Be careful with the distinction between "single clause in bucket" and
   "single clause in predicate".**  A predicate might have multiple clauses but
   indexing dispatches to a specific bucket.  The optimization applies per-bucket,
   not per-predicate.

5. **Body goals create their own mark/undo pairs** for choice points within the
   body (e.g., disjunction, findall, negation).  Those are independent and must
   NOT be elided.  Only the OUTER mark/undo wrapping the head unification is the
   target.

### Risk

This is a subtle optimization.  The invariant is: if a clause is the sole
occupant of an index bucket, its head unification bindings don't need trailing
because there's no sibling clause to try.  But:

- The clause body might call `unify` which trails bindings.  Those are fine —
  body-level trailing is independent.
- If the clause body fails partway through, bindings from head unification
  are NOT undone.  This is correct because the caller's mark will undo everything.
- If the predicate is called inside a choice point (e.g., `member(X, L), pred(X)`),
  the outer mark from the choice point will undo head bindings on backtrack.

**Test thoroughly.** Run the full test suite and all benchmarks.

## How to verify

```bash
# Before
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep -E '(mark|undo)'

# After
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep -E '(mark|undo)'

# Correctness (CRITICAL — run full suite)
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
python -m pytest clausal/examples/ -x -q
```

Expected: 10–20% reduction in mark/undo call counts, ~0.10–0.15s improvement.
Result values must not change.
