# Cross-module tabled NAF never fires WFS delay semantics

Split out of `todo/done/tabling-lifecycle-gaps-rewrap-and-cross-module-table.md`
(finding 3, P3) when findings 1 and 2 were fixed on
`fix/tabling-wrapper-survives-recompile`. UNTRIAGED — the parent todo recorded
it by reading the code, not by reproducing it.

`_is_tabled_naf` (`logic/compiler/tabled_naf.py:22-32`) asks the *caller's*
per-module db whether the callee is tabled, under the dotted name. An imported
callee is tabled in its own module's db and not in the caller's, so
`not Imported(...)` compiles as plain NAF rather than the WFS-sound
`$naf_tabled` form.

Sound for completed evaluations — the callee's own dispatch is still the tabling
wrapper, so answer dedup and termination are intact. What does not propagate is
the delay/conditional-answer machinery: a cycle through negation that crosses a
module boundary cannot produce `undefined`, where the same cycle inside one
module can.

Note the fix for finding 2 narrowed the workaround space rather than widening
it: `-table` in the *importing* module is now a load error, so an author cannot
mark the callee locally to get the tabled-NAF lowering. Whatever the fix is, it
has to read tabledness from the module that owns the predicate.

Open, in rough order of appetite:

1. Have `_is_tabled_naf` resolve the callee's own module and ask *its* db. Needs
   a caller → callee-module lookup at compile time that does not exist yet; the
   `PredicateMeta` is in `module_dict`, so `__module__` plus
   `sys.modules[...].__clausal_module__.db` is probably enough.
2. Record tabledness on the `PredicateMeta` itself at load, so it travels with
   the class across modules and neither db needs consulting. Cheapest to read,
   and one more piece of state to keep in step with `Database._tabled`.
3. Leave it, and document that WFS `undefined` is a within-module guarantee.

First step is a reproduction: a two-module even/odd cycle through negation whose
single-module twin yields `undefined`, and a check of what the cross-module one
yields. Until that exists the severity is a guess.

## Fixed (2026-08-31)

**Triage: real soundness bug.** Repro: lib module tables the symmetric
`Win(X) <- (Move(X, Y), not Win(Y))` cycle (Move 1↔2); importer does
`-import_from(lib, [Win])`, `-table(Res/1)`, `Res(X) <- (not Win(X))`.
Measured via `query_wfs`:

- single-module twin, `Res(1)`: `[(Undefined, delays={Win(1)})]` — correct WFS.
- cross-module, `Res(1)`: `[]` — **definite false** where WFS says Undefined.
- cross-module POSITIVE `Win(1)` through the importer: `Undefined` (fine —
  the tabling wrapper travels with the class; only the NAF lowering was lost).

**Fix — option 2 (class stamp), plus two gaps the todo did not anticipate:**

1. `PredicateMeta._tabled_home_db` (default `None`) is stamped by
   `Database.mark_tabled` with the marking db (last marker wins — one load
   pipeline marks the same predicate on an exec-time db and then the compile
   pipeline's db; an `is None` guard let the throwaway win). The stamp
   travels with the shared class across `-import_from`.
2. Compile seam: `_is_tabled_naf` / `_compile_tabled_naf_simple` resolve
   through `db.module_dict` → stamp (`_resolve_tabled_call`). Two facts the
   todo missed: the import rewrite compiles the negated call under the
   DOTTED name (`"lib.Win"`, resolvable via the dotted module_dict key
   compiler_v2 stores), and the home db keys tables/dispatch/signatures by
   the predicate's own `__name__` — so resolution canonicalizes the name.
3. Runtime: the compiled seam passes the CALLER's `$table_store`/`$naf_db`,
   so flipping only the compile decision would have consulted the wrong
   store (and answered a wrong definite True instead). `_naf_tabled` now
   redirects to the home db/store (same `module_dict` → stamp walk,
   duck-typed-db safe) and canonicalizes the functor; delays it records
   carry the home store on `DelayedNegation.store` (excluded from eq/hash)
   so `_delay_target_entry` can decide a delay whose target lives in a
   different module's store (keeps the asymmetric/definite case definite).

`-table` in the importing module stays a load error (untouched; pinned by
`TestTableTargetRefused`). NAF over an imported UNTABLED predicate stays
plain NAF. Tests: `tests/test_wfs.py::TestCrossModuleTabledNaf` (6 tests —
symmetric cycle Undefined + delay partner, single-module twin guard,
definite cross-module stays definite, untabled import unchanged, compile
decision unit).

Design notes / conservative choices:
- `DelayedNegation.store` deliberately does NOT participate in
  equality/hash (kept on `(functor, arity, key, frozen_args)`): two
  same-named predicates from different modules negated under one leader
  would merge their delays. Judged an acceptable, rare edge; widening eq
  would have changed identity for every existing delay consumer.
- Option 1 (resolve via `__module__` + `sys.modules`) was not taken for the
  compile seam — the class stamp is direct and does not depend on
  `sys.modules` state — but the equivalent walk already exists at the
  query surface (`solve._tabled_entry_for_goal`) and is untouched.
- Delay resolution for a cross-module delay recorded WITHOUT the store tag
  (e.g. constructed by legacy callers) keeps the historical same-store
  lookup and stays conservatively Undefined rather than resolving.
