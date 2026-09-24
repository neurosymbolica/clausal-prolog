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

## RULED 2026-09-24 (operator): a local p/2 beside an imported p/1 LOADS, in BOTH eras

Name and arity make a different predicate. The class era now gives the
handle era's answer.

## Resolved (branch feat/drop-vocabulary-implements-2026-09-24)

`compiler_v2._load_through` builds the `through=` for every load write (the
step-3d pre-pass, step 4's clause gate, step 5's dispatch gate): the name's
class, else the `-import_from` binding -- but NOT an imported class reading
another database's row at another arity (`is_foreign_class_at_other_arity`,
which reads the BOUND ROW's arity, `row.key[1]`, not `len(_fields)`). In the
handle era `through=` already resolved at the written arity. So the owner's
`p/1` row is no longer in the blast radius of B's own `p/2` write, and with
round 5 (no bind, no dispatch on the foreign class) B's `p/2` is fully B's.

Tests moved to the ruled behaviour, both eras: B loads, B's `p/2` answers,
A's `p/1` is untouched --
`test_import_arity_resolution.py::TestALocalPredicateAtAnotherArityLoads`
(was `TestBlastRadiusRefusalNamesTheAttemptedKey`, fixture
`t5b_dual_arity_clash` re-commented) and
`test_vocabulary_implements_refused.py::test_a_plain_exporter_s_loaded_clauses_do_not_stop_another_arity`.

Other pins of the old text ("reached by writing"): only
`test_import_arity_resolution.py:123`, which asserts the phrase is ABSENT for
a same-arity functor clash -- not this case, unchanged and passing. The
`attempted=` formatting in `database.refusal_error` stays: it still serves
any through-row at another key (e.g. an aliased spelling).
