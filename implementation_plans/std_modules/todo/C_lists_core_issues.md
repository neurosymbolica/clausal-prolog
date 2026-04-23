# _lists_core.c — known issues and future work

Follow-up issues from the Option B implementation of `_lists_core.c`.

## ~~1. trail.mark()/undo() go through PyObject_CallMethod~~ DONE

Switched to `_variables_capi.h` C API.  `VarAPI->trail_mark()` and
`VarAPI->trail_undo()` are direct C function calls (trail_mark just
reads `trail->length`; trail_undo calls `trail_undo_to` directly).
Also uses `VarAPI->unify()` (no occurs check) instead of going through
`PyObject_CallFunctionObjArgs(fn_unify, ...)`.

Added `unify` (oc=0) to the `VariablesCAPI` struct alongside the
existing `unify_oc` (oc=1), since list predicates use standard
unification without occurs check.

## ~~2. make_seq_result validation is O(n) per call~~ DONE

Added `seq_join_chars()` fast path that calls `PyUnicode_Join` directly
without per-element validation.  Used in `append_split_find`,
`select_find`, and `permutation_find` where the `was_str`/`out_str`
flag guarantees all items are single-char strings (they came from
`_as_items()` on a string input).  The validating `make_seq_result()`
is retained for the general case.

## 3. No direct trail access on error paths — NO ACTION NEEDED

Design note: matches Python behavior.  The trampoline protocol guarantees
cleanup via the caller's mark/undo.  Not a bug.

## 4. SegList inputs silently fall through — NO ACTION NEEDED

Matches pre-existing Python behavior.  SegList gap is documented with tests
in `tests/test_term_inspection.py` (TestCopyTermSegList, TestTermVariablesSegList).
Same pattern as DictTerm gap.  Will be addressed if SegList walking is ever
needed for list predicates.

## 5. Option A upgrade for hot predicates — DEFERRED

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
