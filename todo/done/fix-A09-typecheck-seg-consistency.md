# fix(A09-F029): type-check predicates disagree on ground Seg* values

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F029

## Bug

For a ground `SegString(["ab"])`: `is_str` ✓, `string` ✓, `is_list` ✓ — but
`atomic` ✗ (comment claims "every Seg* shape is structurally compound",
type_checks.py:126-155) and `is_chars` ✗ (docstring: "list or a string",
type_checks.py:255-263). is_str(X) implying not-atomic(X) is incoherent —
elsewhere the 2026-06-13 user decision is "Seg* never appear at the Clausal
surface — walk to ground form first" (functor/arg/unpack do exactly that).

## Fix direction

Apply the walk-to-ground-form rule uniformly: `atomic` and `is_chars` (and
`compound` — a ground SegString should NOT be compound if is_str holds)
normalize ground Seg* via `normalize_seg_input` before classifying.
Non-ground Seg* keep current behaviour.

## Acceptance

- Matrix coherent: for ground SegString, is_str = string = atomic = is_chars
  = is_list = True, compound = False; existing type-check tests green.
