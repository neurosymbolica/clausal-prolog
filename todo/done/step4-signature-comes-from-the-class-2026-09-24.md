# Step 4's keyword signature comes from the CLASS — nothing supplies it after the flip

**Found:** 2026-09-24, fixing F1 row 24 (`compiler_v2` step 4). **Blocks the flip.**
Tripwire: `tests/test_step4_row_stamps.py::test_an_undeclared_predicate_carries_the_field_names_of_its_head`
— it WILL go red when the flip lands, on purpose.

## The site

    _sig_row = pred_cls._row
    if _sig_row.signature is None:
        _sig_row.signature = pred_cls._fields

## Measured (house suite, 16,157 step-4 arrivals)

* 8,978 class arrivals reach this line with NO signature registered by
  `define_predicate` (`_extract_param_names` answered None) — the class's
  `_fields` is the only source.
* Of those, 2,310 match a declaration in `db._declared`, 6 DISAGREE with one,
  and **6,662 have no declaration at all**: their names exist only on the
  class, derived by the rewriter (`term_rewriting._derive_field_names`: a
  head variable's lowercased id, else `arg_<i>`; e.g. `cg1(G)` → `('g',)`,
  `p(1)` → `('arg_0',)`).
* After the flip the binding is a mangled atom; `field_names_for` answers
  None for an ordinary clause-defined predicate (measured in F9), so
  `row.signature` silently stays None for those 6,662 and
  `globals_env.signature_for` (keyword-argument goals) loses them.

## Design question (not guessed)

Where do the rewriter's derived field names live once there is no class?
Candidates: the rewriter registers them into the db at mint time
(`register_signature`), or `define_predicate` derives them the same way
`_derive_field_names` does. The 6 declared-vs-class disagreements need
looking at under either option — they say which source wins today.

## Resolved (2026-09-24, option C, operator-approved)

Design: `implementation_plans/step4-signature-source-design-2026-09-24.md`.

* The rewriter emits a `HeadFieldNames(fields={name: tuple})` module item at
  the end of `visit_Module` -- a snapshot of `EmbedTransformer._seen_functors`,
  the exact tuple the class used to be minted with (first registration wins).
  Module items are re-derived by re-parsing on a bytecode-cache hit, so it is
  present on both load paths. `reflection._SKIPPED_ITEMS` skips it.
* `compile_module` step 4 stamps `row.signature` from it (arity-checked) on
  `db.row(functor, arity, create=True)` -- the row `record_clause_source`
  stamps -- **whatever the name is bound to** (operator ruling 2026-09-24:
  `t5b_slot/2`, `s4rs_slot/2` now answer `(arg_0, arg_1)` instead of nothing).
  The class-read stamp is gone. The step-4a stamp was dead (0 arrivals, probed)
  and is removed.
* The declare-then-import-then-define disagreements (`fnm_verdict/2`,
  `impord_fverdict/2`) now carry the module's own declaration
  `(STATUS, CITATIONS)` instead of the exporter's placeholder -- a correction.
* Parity (tools/step4_signature_census/plugin.py, 84 targeted files, 2,751
  passed / 2 pre-existing failures): 2,450 / 2,457 stamping class arrivals
  agree with `pred_cls._fields`; the 7 are exactly the allowed keys, each equal
  to the declaration; 0 class arrivals unstamped; 21/21 non-class stamping
  arrivals stamped; 2,785/2,785 later arrivals unchanged; denominator 5,263.
* The tripwire `tests/test_step4_row_stamps.py::test_an_undeclared_predicate_
  carries_the_field_names_of_its_head` is now permanent: it must stay GREEN at
  the flip.
