# `do_unify`'s C tuple branch is still `PyTuple_Check` (inclusive), unlike every other tuple twin

Found during P3-2 Task 2C fix round 1 (2026-09-05), while making
`c_copy_term`/`c_collect_vars`/`c_is_ground`'s new tuple branches exact-type
(`PyTuple_CheckExact`) per the reviewer's tuple-subclass-incoherence finding.
Parked at the time as pre-existing and out of the authorized scope (Task 2C's
scope was those three functions only). Ledger: "park for the Phase 4
dict-pair/atom-string audit (same family); surface in close-out todos."

## The inconsistency

`_variables.c:1118`, `do_unify`'s structural-tuple branch:

```c
if (PyTuple_Check(t1) && PyTuple_Check(t2)) {
```

`PyTuple_Check` is the INCLUSIVE check — true for `tuple` and any subclass of
it. Every OTHER tuple-recognizing branch this phase touched or introduced is
EXACT-TYPE:

- `c_copy_term`, `c_collect_vars`, `c_is_ground` (Task 2C, this branch's own
  siblings) — all `PyTuple_CheckExact` after the fix-round-1 ruling.
- `cells.py`'s `is_cell`/`_cell_shape` (Task 5) — `type(term) is tuple`,
  exact, by design (cells and their construction discipline exclude tuple
  subclasses on purpose).

So a `tuple` SUBCLASS instance is treated as cell-shaped by unification (it
structurally unifies element-by-element against another tuple/cell) but
opaque by every walker (copy, term_variables, ground treat it as a leaf, per
the Task 2C ruling that restored pre-flip namedtuple opacity). That is an
internally inconsistent story for the SAME object: unify says "this has
sub-terms," the walkers say "this does not."

## Why it's pre-existing, not something this phase introduced

`do_unify`'s inclusive `PyTuple_Check` on the tuple branch predates P3-2 (and
predates the tagged-tuple program entirely — it is the ordinary structural
tuple-unification branch, unrelated to cells). Task 2C's authorized scope was
narrowly `c_copy_term`/`c_collect_vars`/`c_is_ground` (the three C twins that
had NO tuple branch at all before this phase and needed one to avoid a
disclosed ~3.4x regression); `do_unify` already had a tuple branch and was
never touched.

## Why it's not fixed here

- Out of Task 2C's authorized scope (a user-ruling-gated C change, scoped
  specifically to the three walkers).
- No engine term type is currently a tuple subclass (verified by the Task 2C
  reviewer during the exact-type ruling) — so this is LATENT, not exercised by
  any in-tree program today.
- It belongs with the Phase 4 dict-pair/atom-string audit
  (`implementation_plans/tagged-tuple-term-representation.md` §6 hazard 2),
  which is already scoped to revisit tuple-adjacent representation questions
  as a batch, rather than as a one-off C patch now.

## The fix, when picked up

Mirror the Task 2C precedent exactly: change `_variables.c:1118`'s
`PyTuple_Check(t1) && PyTuple_Check(t2)` to `PyTuple_CheckExact` on both sides,
matching the walkers and `cells.py`. Add a twin-corpus case (a `tuple`
subclass instance on both sides of `do_unify`) alongside whatever Phase 4's
dict-pair audit already builds, since dict/set pairs will also need exact-type
tuple discipline once they migrate to `(tuple, k, v)` cells.

## Where to look

- `clausal/logic/variables/_variables.c:1118` — the branch itself.
- `clausal/logic/variables/_variables.c:2198` — a comment already on record
  ("first cut of this branch used the inclusive PyTuple_Check, mirroring...")
  from a DIFFERENT branch that was already fixed; useful precedent/wording to
  reuse for `do_unify`'s fix.
- `.superpowers/sdd/p32-cell-default-flip/task-2c-report.md` — the Task 2C
  fix-round-1 ruling this todo inherits its exact-type rationale from.
