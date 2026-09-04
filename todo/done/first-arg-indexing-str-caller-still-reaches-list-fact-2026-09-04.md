# First-arg indexing: str caller still reaches a list-headed fact after cons-rule retirement

Status: FIXED, in P3-2 Task 4 (2026-09-05). Original todo (parked by P3-1
Task 5) preserved above the line for context; this section records the
trace and the fix.

## Original observation (P3-1 Task 5, kept verbatim)

Found during P3-1 Task 5 (cons-rule retirement) while fixing
`tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py::test_F095_first_arg_index_coalesces_str_and_charlist`.

With a 5-fact predicate `TestPred(1), TestPred(2), TestPred(3), TestPred("abc"),
TestPred(['a','b','c'])`:

- `TestPred(['a','b','c'])` (list caller) -> 1 solution (correct: only the
  list-headed fact matches, now that `unify("abc", ['a','b','c'])` is
  retired).
- `TestPred("abc")` (str caller) -> **2 solutions** (the str-headed fact,
  same-type, PLUS the list-headed fact `['a','b','c']`). This is asymmetric
  with the list-caller case and should — under §1b ("lists unify with
  lists, str unifies with str") — also be 1.

Confirmed NOT caused by the `_variables.c` `do_unify` str<->list block that
task removes (verified directly: `unify("abc", ['a','b','c'], trail)` is
`False` in isolation, on the rebuilt extension).

### Hypothesis (P3-1 Task 5, unconfirmed at the time)

`_normalize_dataclass_fact` (`clausal/logic/database.py:414`) hoists a fact
whose head is a *ground value* into a Var-headed clause + a body `Unify`
goal (`TestPred(V) <- Unify(V, "abc")`). If a ground LIST literal head
(`['a','b','c']`, no Vars/StarUnpack) is hoisted the same way, both the str-
and list-headed facts would compile to Var-headed clauses — which
first-arg indexing likely cannot bucket on caller type, so they land in
whatever "unindexable" bucket gets scanned unconditionally.

## P3-2 Task 4: the trace

The plan's R8 checkbox expected that retiring `_charlist_to_str_or_none`
(the compile-time str/char-list bucket-key coalescing in `arg_index.py`)
would, by itself, flip this repro to symmetric 1-solution behavior. Measured
directly (not assumed): after retiring the coalesce, the repro was
UNCHANGED — still 2 solutions for the str caller, 1 for the list caller.
So the hypothesis behind that expectation needed re-tracing, per this
todo's own follow-up section.

**`_normalize_dataclass_fact` hoisting was traced and ruled out** as an
explanation on its own: it hoists str and list literal fact heads
IDENTICALLY (both are `_is_ground_value` — a plain list of ground
elements counts). That symmetry in hoisting doesn't by itself produce or
explain an asymmetric OUTCOME; the actual mechanism is one level deeper,
in what happens to the hoisted list clause once indexing decides it is
unindexable:

1. Post-R8, `_arg_to_index_key(['a','b','c'])` returns `_INDEX_VAR` (a
   str-content list is no longer coalesced to a str key). `_build_arg_index`
   therefore treats the list-headed clause as a "default" (matches-anything)
   clause and MERGES it into EVERY specific-key bucket — including the
   str-headed fact's own `"abc"` bucket (previously, pre-R8, the two
   clauses shared that bucket for a different reason: the coalesce gave
   them the SAME specific key, not a default merge — same end bucket
   membership, different mechanism, which is why removing the coalesce
   alone didn't change this particular repro's bucket membership).
2. Bucket compilation runs `_lift_clause_at_pos` on every clause in a
   specific-key bucket, including merged-in defaults. Before this task,
   nothing in `_lift_clause_at_pos` skipped a plain ground `list` literal,
   so the list clause got lifted: its head became a sequence PATTERN
   (`case [_lcap0]: ... $head_list_unify_input(_lcap0, ['a','b','c'], ...)`)
   instead of staying a Var head + body `Unify`.
3. The runtime helper behind that pattern — `_head_list_unify_input_py`
   (`clausal/logic/runtime/list_unify.py`) and its C twin — still implements
   the PRE-P3-1 "a string is a list of its chars" contract for HEAD-PATTERN
   destructuring (this is also the documented, currently-live "Pattern
   Matching" feature in `docs/strings_as_lists.md`, e.g. `[H, *T]`
   destructuring a string one character at a time). This is a SEPARATE code
   path from the `_variables.c` `do_unify` cons rule that P3-1 retired, and
   was untouched by that retirement.
4. So the lifted list-literal pattern, reached only because the list was
   merged in as a bucket default, wrongly ACCEPTS a same-length str caller
   (`_head_list_unify_input_py("abc", ['a','b','c'], None, [], trail)`
   iterates and unifies each literal char against `"abc"[i]` and succeeds).
   The str-headed clause's own lifted pattern is a plain `MatchValue`
   (equality only) with no such reciprocal leniency, which is why the
   asymmetry runs only one way.

This is genuinely one level deeper than the todo's own hypothesis pointed:
not `_normalize_dataclass_fact` hoisting itself, but `_lift_clause_at_pos`
turning a merged-in-as-default list literal into a head PATTERN whose
runtime destructuring helper still honours the retired strings-as-lists
identity.

## The fix

`_lift_clause_at_pos` (`clausal/logic/compiler/list_dispatch.py`) now also
skips lifting a ground `list` literal, narrowed to lists that are NOT
byte-list-coalescible (`_bytelist_to_bytes_or_none(lift_term) is None`):

- A str-content (or otherwise non-numeric) ground list keys `_INDEX_VAR`
  post-R8 and is exactly the case above — skip lifting; the body `Unify`
  stays in place and uses the real runtime `unify()`, which correctly
  enforces §1b ("lists unify with lists, str unifies with str").
- A ground list of ints in [0, 255] is still byte-list-coalescible (a
  SPECIFIC key — the joined `bytes` value — never merged as a default into
  an unrelated bucket), so it is NOT skipped: lifting it stays safe, and is
  unchanged (regression-tested against
  `tests/test_funnel_accessors.py::TestMigrationRegression::test_list_dispatch_rebuilds_term_instance_head_at_pos`,
  which relies on exactly this still being lifted).

The genuine `[H, *T]`-with-Vars-or-`StarUnpack` "Pattern Matching" feature
(`docs/strings_as_lists.md`) is untouched: such a pattern is never hoisted
by `_normalize_dataclass_fact` in the first place (only GROUND lists are),
so it never reaches `_lift_clause_at_pos` at all.

## Result (measured, both callers)

Before (post-R8, pre-list-skip): str caller `"abc"` -> 2 solutions; list
caller `['a','b','c']` -> 1 solution.

After (this fix): str caller `"abc"` -> 1 solution; list caller
`['a','b','c']` -> 1 solution. Fully symmetric, matching §1b.

## Where this is exercised

- `tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py::test_F095_first_arg_index_coalesces_str_and_charlist`
  — the original repro, rewritten to pin §1b/R8 (1 solution each).
- `tests/audit_2026_07_05/test_02_compiler_heads.py::TestIndexedDispatchGuards::test_str_charlist_heads_no_longer_coalesce_for_list_caller`
  — an independent occurrence of the SAME bug (`coll/2`'s str vs list
  facts), found already citing this todo; updated to the same symmetric
  result.
- `tests/test_first_arg_index.py::TestLiftClauseAtPos::test_ground_str_content_list_literal_is_not_lifted` /
  `::test_ground_int_list_literal_is_still_lifted` / `::test_bytes_literal_is_still_not_lifted` /
  `::test_str_literal_is_now_lifted` — unit-level pins of the fixed
  `_lift_clause_at_pos` skip logic.
