# fix-A05: structural_eq asymmetric + inconsistent with reify_eq (A05-F003)

**Severity: correctness.** `structural_eq`
(`clausal/logic/constraints.py:36-138`):

1. **Not symmetric**: `structural_eq("ab", SegString(["ab"]))` → True
   (str arm `:54` delegates to `==`, which SegString answers) but
   `structural_eq(SegString(["ab"]), "ab")` → False (SegString arm
   `:94-103` demands both sides SegString).
2. **str ↔ char-list**: `structural_eq("ab", ["a","b"])` → False even
   though the standing contract says a string IS a list of single-char
   strings and `reify_eq("ab", ["a","b"], t)` → True (identical — zero
   bindings needed to unify).
3. **ground SegList vs list**: `structural_eq(SegList([ConcreteSeg([1,2])]), [1,2])`
   → False both directions despite walking to the same value.

Invariant to restore: `structural_eq(x, y) ⟺ reify_eq(x, y) is True`
(structural equality = unifiable with no bindings). dif/2 and setof/2
(via A03) key on this notion.

## Fix

- Seg* arms: if `__walk__()` grounds the term, compare the walked value
  against the *other side as-is* via structural_eq recursion (not only
  when both sides are the same Seg type).
- str-vs-list arm: add the Liskov char-list comparison (mirror what
  `do_unify` does for str↔list), or simply implement
  `structural_eq(x, y)` as `reify_eq(x, y, scratch_trail) is True` and
  keep a fast path for atomics — that makes the invariant true by
  construction and removes the maintenance of a third structural walker.
- Cross-type numerics (`structural_eq(1, 1.0)` → True) is **parked**
  under A05-D001 / A01-D001 — do not change direction here, only keep
  it consistent with whatever unify does.

## Verify

Flip `TestF003StructuralEqInconsistencies` xfails to plain asserts;
the 4 controls (incl. DictTerm↔dict documented equivalence and
tuple≠list) must stay green.
