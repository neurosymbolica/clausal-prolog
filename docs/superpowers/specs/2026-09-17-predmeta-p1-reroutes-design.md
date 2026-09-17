# PredicateMeta retirement, P1: the 14 actionable reroute sites — design

Date: 2026-09-17. Approved by the operator in session ("item 2 design looks ok, proceed").
Builds phase P1 of `2026-09-14-retire-predicatemeta-design.md` §6 over the census in
`tools/predmeta_census/FINDINGS.md` and the per-site table `tools/predmeta_census/P1_SITES.tsv`
(dispositions R, R!, R-enum, S = 14 rows). Nothing else in that table is in scope.

## 1. The two facts that make P1 actionable now (measured 2026-09-17)

* **An imported predicate HAS a row in the importer's Database, and it is the exporter's row
  object.** `Database.row(f, a)` consults `_rows` and `_adopted`; `-import_from` adopts the
  exporter's row (`Database.row`'s own comment: "A row this module ADOPTED at import answers a
  read"). Measured: `importer.db.row('p', 1) is exporter.db.row('p', 1)`, dispatch identical.
  So rerouting a name lookup to `db.row(f, a)` drops nothing imported. (The memory note that the
  shared row was "recorded NOT implemented" is stale.)
* **`db.row(f, a) is not None` is the equivalent of the isinstance test** — pinned by
  `tests/predmeta_p1/test_membership_equivalence.py`; `is_defined` is stricter and WRONG.

**CORRECTION (P1 Task 3, measured 2026-09-17, reproduced in review): that
equivalence has a LIMIT, and two of the 14 sites fall outside it.** `Database.row`'s
`known` test consults `_clauses`, `_dispatch`, `_lazy_recompile`, `_signatures` and
`_dynamic`, plus `_adopted`. So a row exists for a predicate that has CLAUSES here, a
dispatch, a registered signature, a `-dynamic(f/N)` declaration (step 2's `mark_dynamic`
writes `_dynamic` before anything else runs), or an `-import_from`'d name (whose row this
database ADOPTED). **Nothing else mints one.** `-module`/`-private` list membership is a
module binding, and `-discontiguous`/`-table`/`-shallow` write their own sets, none of
which `row()` reads. A name declared with fields and given no clauses is therefore a
`PredicateMeta` in the module dict with **no row at all** —
`isinstance(module_dict.get(f), PredicateMeta)` is True while `db.row(f, a)` is None, for
the same name at the same arity. Pinned as a NEGATIVE test in
`test_membership_equivalence.py`. Consequences: `compiler_v2`'s
`_validate_directive_targets` (census 851) and `_refuse_untablable_target` (882) stay on
the class — they ask "is this name a predicate DECLARED here", which is the §4 question —
and `database_ops._find_pred_cls` (275) routes through the row but keeps a CLASS FALLBACK
for the rowless case, which is how a predicate reached by a plain Python import (never
through `-import_from`, so no row was adopted) stays visible to `listing/1` and
`_namespace_dispatch`.

## 2. The design, four parts

1. **Index plans get a row home.** `_index_plans`, `_index_plans_joint`,
   `_index_plans_hierarchical` are the only state the 14 sites read that the census records as
   CLASS-ONLY. Add three row-local fields to `PredRow` (`index_plans`, `index_plans_joint`,
   `index_plans_hierarchical`, `default_factory=dict`, `repr=False, compare=False`) and make the
   three class attributes read-through PROPERTIES with setters on `PredicateMeta`, exactly the
   shape `_signature` has: `(cls._row or cls._detached_row()).index_plans`. The writer in
   `clausal/logic/compiler/predicate.py` (`pred_cls._index_plans = {...}`) is untouched — the
   assignment now lands on the row. Zero behaviour change; a detached class (minted outside a
   load) keeps working through its private row.
2. **Membership reroutes.** `isinstance(module_dict.get(f), PredicateMeta)` (with or without a
   `len(_fields) == arity` check) becomes `db.row(f, arity) is not None`, and a state read after
   it (`_signature`, `_dynamic_arities`, `_locked`, `_fields`-length) becomes the row's field
   (`signature`, `dynamic_arities`, `locked`; the arity is the row's own key). The `db` is the one
   in scope at the site; where only a module dict is in scope it is
   `module_dict["$module"].db` (FINDINGS "wrong turn": never a predicate's `_row.db`, which is a
   different Database for an imported name).
3. **The four arity-tightening sites (R!).** `goal_trampoline.py` (two) and
   `optimisations/call_site.py` (two) look `fname` up in `base_globals`, test the class, read
   `_locked` and `_index_plans*` off it, and never use the `arity` they computed. They read
   `db.row(fname, arity)` instead, with `db` threaded in EXPLICITLY from the compile pipeline
   (`compile_predicate_trampoline` has it) — not looked up through `$module`, so a test that
   builds `base_globals` by hand keeps working by passing `db`. BEHAVIOUR CHANGE, stated: a call
   at arity N no longer sees the plans compiled for a same-name predicate at arity M. A test pins
   that each arity gets its own plans and never the other's, and a positive control pins that the
   ordinary load path still produces hints.
4. **The enumeration (R-enum).** `[k for k, v in module_dict.items() if isinstance(v,
   PredicateMeta)]` in a diagnostic becomes the names of `db._rows` ∪ `db._adopted`, sorted.

**The wart to respect, not fix:** `dynamic_arities` is a per-NAME set stored on the CLASS's own
row (`PredRow` docstring). The two `-dynamic` sites (`compiler_v2.py` census lines 276/285) read
and write it through the class today; the reroute must reach the SAME row (`db.row(functor,
<the class's arity>)` — i.e. the row the class is bound to), not `db.row(functor, arity)` for the
declared arity, or a declaration at a second arity would land on a different row and the "set of
size > 1" distinction the docstring names would silently vanish. If that row cannot be named
without the class, the site keeps the class for the WRITE and reroutes only the membership test,
and says so.

## 3. Where a site still needs the class after the test

Some R sites use the class for something other than membership afterwards
(`_belongs_elsewhere(pred_cls, db)`, `term_field_names_of_class(cls)`, identity against
`type(head)`). P1's exit criterion is "the class is no longer on the ROUTING path", not "no site
touches a class". So: the membership test and the state reads move to the row; a remaining
class use is left in place and REPORTED per site, so the final review can list exactly what P4
still has to remove. Never invent a row→class accessor to avoid that report.

## 4. Gate

Engine failure-set diff on the branch against a baseline taken at the start (the branch baseline
is red; enumerate already-red tests in every touched test file first). The arg-index test files
(`tests/test_first_arg_index.py`, `tests/test_optimisations_call_site.py`,
`tests/test_bucket_refs_ir_parallel.py`, `tests/test_deep_indexing.py`) and
`tests/predmeta_p1/` run alone as well. Because part 3 changes which index plans a call site
can use, the landing is followed by a QUESTION to harness-batch-lane for the 82-row answer diff
(their protocol; ~3 minutes on their side) — not by an engine-side claim that answers cannot move.

## 5. Not in scope

The five P4 rows (`predicate.py` "resolve pred_cls by name if not passed" ×4 + 2218 — one helper
when the metaclass goes); the Q rows (`Database.arities_for`-shaped functor-only lookups exist
but the sites are `-specialize` internals); the X4/X4+Q rows (a census REFRESH is warranted now
that adoption is measured, but it is a separate pass); the NO row.
