# docs/strings_as_lists.md is stale after P3-1 Task 5 (cons-rule retirement)

`docs/strings_as_lists.md`'s core "unification" and "empty_string" examples
(backed by `tests/fixtures/docs/strings_as_lists_examples.clausal`) document
`"abc" is ["a", "b", "c"]` and `"" is []` as working, equivalent forms. P3-1
Task 5 (§1b) retires the C str~char-list cons rule these examples rely on —
both now FAIL (a bare str no longer unifies with a char-list literal via a
direct body `is`/unify with no star; the fixture file has been updated to
pin the new, retired behaviour with inverted assertions and a citation).

**Still true / unaffected** (verified during Task 5): SegString explicitly
remains the char-list optimisation (unifies with lists/SegLists
element-wise); any STAR-containing list pattern (`[*PREFIX, *_]` etc.) or
ANY clause-HEAD list pattern (star or not) still destructures a bare str
natively via `_head_list_unify_input` (`clausal/logic/runtime/list_unify.py`)
— this is a separate, older mechanism the cons-rule retirement does not
touch. The `pattern_matching`, `append_examples`, `length_example`,
`member_examples`, `reverse_example`, `take_drop_split`,
`list_item_example`, and `type_checking` sections of the same fixture file
all still pass unmodified.

## Disposition

Parked for Task 8 (close-out, per the plan: "Design doc: §5 stale-order-
claim correction; §1a/§1b STATUS note... strict-atoms migration note
updated for -hide" — this belongs in the same doc-staleness sweep, echoing
Task 3's precedent of deferring `directives.md`/`import.md`/`-overwrites`
staleness to Task 8).

## What needs to change in the prose

- The "unification" section's headline claim ("a str IS interchangeable
  with its char-list") needs qualifying: true for head-position patterns
  and star-containing body patterns; NOT true for a direct `is`/`==`
  between a bare str and a bare list literal (retired).
- The "empty_string" section's `"" is []` example needs replacing or
  removing.
- Consider a new subsection citing §1b explicitly: "what changed in P3-1".

## CLOSED 2026-09-18

Done in the docs pass after the atoms-as-str flip (stages 1+2 landed on main at 3fcfd29e): docs branch `docs/atoms-as-str-doc-pass-2026-09-18`, fast-forwarded onto main. Every claim was measured against the landed engine; the doc-snippet suite (tests/fixtures/docs) is green. The current model: an atom IS the interned Python str, a string is the list of its char atoms (the `$chars` carrier internally), an atom key and a same-spelled STRING key are different keys, an atom key and its quoted spelling are one.
