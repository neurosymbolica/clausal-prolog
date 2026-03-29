# _lists_core.c — known issues and future work

Follow-up issues from the initial Option B implementation of `_lists_core.c`.

## 1. trail.mark()/undo() go through PyObject_CallMethod

Every call to `trail_mark()` and `trail_undo()` in the C helpers goes through
`PyObject_CallMethod`, which involves method name lookup, argument tuple
creation, and Python method dispatch.  Since `Trail` is a C type defined in
`_variables.c`, we could instead:

- Export a C-level header with the `TrailObject` struct layout, or
- Add `trail_mark_fast` / `trail_undo_fast` as C API functions in `_variables.c`
  and call them directly via a cached function pointer.

This would eliminate ~200ns per mark/undo call, which adds up in tight loops
like `member_find` over long lists.

## 2. make_seq_result validation is O(n) per call

`make_seq_result(items, was_string=1)` validates that ALL items are single-char
strings before calling `PyUnicode_Join`.  In `append_split_find`, this runs for
every split candidate, making the total validation work O(n^2).

When `out_str=True` in the append split case, `items` always came from
`list(string)`, so every element is guaranteed to be a single-char string.
We could add a `skip_validation` parameter or a separate `seq_join_chars`
fast path that skips the per-element check.

## 3. No direct trail access on error paths

If `call_unify` returns -1 (Python exception), the C helpers return NULL
without undoing the trail to the mark.  This matches the Python generators
(they also don't explicitly undo on exception — the trampoline's
`LogicException` unwinding handles it).

However, if the exception is caught and execution continues, the trail could
have partial bindings from the failed iteration.  Worth auditing whether the
trampoline protocol guarantees cleanup in all exception paths.

## 4. SegList inputs silently fall through

The C helpers only receive Python lists (from `_as_items()`).  SegList values
cause `_as_items()` to return None, skipping the loop entirely.  This matches
the pre-existing Python behavior but means partially-bound lists are never
iterated by member/append/select etc.

If SegList walking is ever needed for these predicates, the C helpers would
need to either accept SegList objects directly or the Python caller would need
to walk the SegList before calling the C helper.

## 5. Option A upgrade for hot predicates

The current implementation is Option B (C helpers called from Python
generators).  The Python generator frame creation and trampoline yield/resume
cycle still runs in Python.  For the hottest predicates (`in_/2`, `append/3`),
an Option A implementation (C-native StepGenerator) would eliminate the
generator overhead entirely.

This requires implementing a C type that conforms to the StepGenerator
`send()` protocol — see `_trampoline.c` for the interface.  The C object would
maintain iteration state internally and produce `(parent, None)` / `(parent,
DONE)` tuples directly.

## 6. Tier 3 predicates not yet accelerated

The current implementation covers Tier 1 (`in_/2`, `append/3`, `length/2`,
`reverse/2`, `last/2`) and Tier 2 (`permutation/2`, `select/3`, `get_item/3`).

Remaining Tier 2: `msort/2`, `sort/2` — these use Python's `sorted()` which
is already C-accelerated.  Limited benefit from moving the wrapper to C.

Tier 3 predicates (`flatten/2`, `subtract/3`, `intersection/3`, `union/3`,
`list_to_set/2`, `take/3`, `drop/3`, `split_at/4`, `zip_/3`, `numlist/2,3`)
are all deterministic single-unify predicates.  The per-predicate overhead is
small, but collectively they account for significant Python frame creation if
called in tight loops.  Could benefit from Option C (single C function that
does everything and returns True/False).
