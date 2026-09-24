# An imported class at ANOTHER arity refuses a local predicate only in the class era

**Found:** 2026-09-24, round-5 review of the vocabulary-implements drop.
**Design question for the flip, not guessed.**

Module A exports a STATIC `p/1` with load clauses; module B does
`-import_from(a, [p])` and defines its own `p(1, 2),`.

* **Class era (today):** refused at load. The gate's blast radius includes
  the row the shared class reads (A's owned `p/1`), so B is told "may not
  write p/1 (reached by writing p/2)". This is the ruled M-e behaviour pinned
  by `tests/test_import_arity_resolution.py::TestBlastRadiusRefusalNamesTheAttemptedKey`
  (there with an imported dual-declared atom `k/0` vs a local `k/2`) and by
  `tests/test_vocabulary_implements_refused.py::test_a_plain_exporter_s_loaded_clauses_still_refuse_another_arity`.
* **Handle era (measured by rebinding the name to `mangle("a", "p")` at
  step 3d):** the SAME load succeeds -- `through=` resolves the handle at the
  written arity (`p/2`), A has no `p/2` row, nothing is refused -- and B's
  `p/2` answers while A's `p/1` is untouched.

When A's `p/1` is a `-dynamic` holding only runtime clauses, or a load row
since emptied, BOTH eras load (round 5 made the class era stop binding A's
class to B's `p/2` row; `test_a_local_predicate_at_another_arity_than_an_imported_class_loads`).

So the M-e refusal flips at the PredicateMeta flip unless someone decides.
Question: is a local `p/2` beside an imported `p/1` a legitimate local
predicate (handle-era answer; `is_declared_predicate` is arity-strict and the
round-5 step-4 fix already treats the head as B's own), or a clash to refuse
(class-era answer)? Whichever is chosen, both eras should give it, and the
M-e test and the plain-exporter pin should say so.
