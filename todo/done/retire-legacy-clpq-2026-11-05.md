# Retire the legacy CLP(Q) solver

**Status: FIXED 2026-11-06 (commits 08ba4e5b, 294c6afa, 15914cf4, and the
docs commit that moved this file).** `clausal/logic/clpq/legacy.py` is
deleted, the port of clp(q,r) 1.3.3 is the only CLP(Q) solver, and
`CLAUSAL_CLPQ=legacy` raises a named ValueError. Pinned in
tests/clpq_port/test_package_surface.py::test_legacy_raises_a_named_error
and ::test_the_legacy_module_is_gone.

**Date:** 2026-11-05. **Operator ruling 2026-11-05:** "we should retire
legacy CLPQ".

## State

`CLAUSAL_CLPQ` selects the solver (`clausal/logic/clpq/__init__.py`):
`legacy` (the default, the solver from before 2026-10-12) or `holzbaur`
(the port of clp(q,r) 1.3.3, see `clausal/logic/clpq/PROVENANCE.md`).
Both solvers' attribute hooks are registered whichever is selected
(ruling R1). The full suite is gated under both.

## Plan

1. Make `holzbaur` the default. Gate it, and have the corpus and harness
   re-checked, since every CLP(Q) answer can change wording or order.
2. Remove `legacy.py` and the code only it uses, the `legacy` value of
   `CLAUSAL_CLPQ` (a named error for it, not a silent fallback), the legacy
   attribute hooks, and the tests and fixtures that pin legacy-only
   behaviour.
3. Close or reject the legacy-only todos (`legacy-clpq-*`) as the code they
   describe goes.
4. Check what still imports legacy-only private names (`__init__.py`
   re-exports them for Q_KEY users, the tests and the CLI), and CLP(R).
5. Update `docs/` and the CHANGELOG.

## Progress

**Step 1 done 2026-11-06:** `CLAUSAL_CLPQ` defaults to `holzbaur`
(`clausal/logic/clpq/__init__.py`, `clausal/logic/builtins/flags.py`);
`CLAUSAL_CLPQ=legacy` still works. Docs and CHANGELOG updated. The gate
already ran under `GATE_CLPQ=holzbaur`, so the suite's expectations were
the port's; only tests that read the environment variable with a `legacy`
default, and the test that pinned the default, changed.

**Step 2 done 2026-11-06**, in the order below, one commit each:

1. 08ba4e5b: the six boundary helpers moved to `clpq/boundary.py`.
2. 294c6afa: the tests and fixtures converted or deleted as listed.  Also
   legacy-only, not in the list: tests/test_clpq_deep_terms.py's walk
   parametrisations at :476-479 and :599-615 and
   test_a_shared_subterm_linearises_once_per_occurrence,
   tests/test_clpq_undo_on_backtracking.py:95 (`_tableaux.clear()`), and
   audit test_08's `_tableaux` import.  `tests/clpq_oracle.py` keeps its
   `solver` argument (the callers pass `"holzbaur"`).
3. 15914cf4: `legacy.py`, its key and hook rows and the solver switches
   deleted; `CLAUSAL_CLPQ=legacy` raises `ValueError: CLAUSAL_CLPQ=legacy
   was removed after clausal 1.4.0 (operator ruling 2026-11-05); ...` at
   the package's import (the first CLP(Q) use); any other value but
   `holzbaur` is refused as before.  `tools/division_census` retargeted
   to `normal_form.normal_form_divide` (its `install()` fails at base on
   an unrelated stale name, `terms_to_ast._exact_div`; not fixed here).
4. Docs (`docs/clpq.md`'s "How it works" rewritten for the port,
   `docs/cli.md`, `docs/flags.md`), CHANGELOG (Removed), DEVIATIONS.md
   D20, the AGENTS.md maps; the four todos below closed (the
   disequality one after its port pin,
   tests/test_clpq_strict_bounds.py::test_a_disequation_the_inequalities_close_fails_in_every_order),
   the two that stay open lose their legacy mentions, and this file
   moved to `todo/done/`.

## Step 2 (deletion): the plan, for review before anything is deleted

Line numbers are as of the commit that adds this section.

### What legacy provides that the port does not

1. **Six helpers the port imports from legacy.** `holzbaur.py:92-94`
   imports `_block_cell_as_node`, `_cell_as_node`, `_cells_as_nodes`,
   `_units_result`, `_units_strip`, `_units_strip_expr` from `legacy.py`
   (:1835-1905, :2983-2998, with `_ensure_units_imports` :1868, the
   `_strip_for_solver` globals :1862-1865, `_ensure_term_imports` :156 and
   `_BLOCK_CELL_NODES`). They are boundary code, not solver code: move them
   into the port (a new `clpq/boundary.py`, or `holzbaur.py` itself) first,
   as a separate commit with no behaviour change.
2. **The package surface.** `clpq/__init__.py:17-36` star-imports legacy,
   copies every private legacy name into the package, then overlays
   `HOLZBAUR_API`. After: the package exports `holzbaur`'s `HOLZBAUR_API`
   (and `SOLVER = "holzbaur"` while anything reads it), and
   `CLAUSAL_CLPQ=legacy` raises a named error
   (`ValueError: CLAUSAL_CLPQ=legacy was removed ...`), not a silent
   fallback. Legacy-only public names that go: `Tableau`, `QVar`, `DQ`
   (no user outside tests found) and the incidental re-exports
   (`Fraction`, `ZERO`, ...; none used through the package).
3. **Private legacy names still used through the package** (none in the
   engine; all in tests or tools):
   - `_tableaux`, `_last_snapshot` (tableau cleanup fixtures):
     `tests/test_clpq.py:11,19-25`, `tests/test_clpq_undo_on_backtracking.py:13,21-22`,
     `tests/test_integral_rationals.py:219-254,442-449`,
     `tests/test_clpq_box_bounded_optimum.py:20,33-38`. Delete the fixtures.
   - `_linearize`, `_get_tableau`: `tests/test_clpq.py:11,625-665,1148-1163`
     (legacy internals: delete those tests).
   - `tools/division_census/division_census.py:184-217` monkeypatches
     `clpq._linearize`'s `_Div` arm. Retarget to the port's
     `normal_form` (nf.pl's division) if cheap, else retire the tool
     (operator ruling 2026-11-06, below).
4. **Attribute keys and hooks.** Legacy registers `Q_KEY = "clpq"` with
   `_q_hook` at import (`legacy.py:46,1734`, ruling R1). Remove with:
   `clausal/sandbox.py:766` (ENGINE_ATTR_KEYS row),
   `tests/clpq_port/test_attribute_hooks.py:920` (`_KNOWN_HOOKS` row),
   the hard-coded `"clpq"` key in `clausal/logic/units_constraint.py:94`
   and `clausal/logic/units_clp.py:228-231`, and the R1 comment in
   `tests/clpq_port/test_attribute_hooks.py:57-62`.
5. **Solver switches in engine code.** `clausal/cli.py:345-350` (legacy's
   `_Q` numbering offset), `clausal/logic/builtins/flags.py:49-52,184-197`
   (the cap flags become unconditional), `clausal/logic/clpfd.py:1989`
   (comment). `clpfd.py:461-468` (the FD-to-Q bound sync) and
   `clpfd.py:2218,2253,2301,2782,2860,3142,3194,5249` import `Q_KEY`,
   `sync_fd_bounds`, `q_*` from the package; all are in `HOLZBAUR_API`,
   so they keep working unchanged. `_clpfd_propagate.c:3630-3636` reads
   `q_eq`, `q_ne`, `q_lt`, `q_le` from the package at init: same.
   `clausal/logic/tabling.py:1380,1420`, `clausal/logic/residuals.py:522`
   and `clausal/logic/builtins/constraints.py:200-506` likewise.
6. **CLP(R): no dependency.** `clausal/logic/clpr.py` and
   `_clpr_core.c` import nothing from `clpq` (one comment,
   `clpr.py:505`). Nothing to do.
7. **packages/: no user.** No optional package imports `clpq`.
8. **Modules only legacy uses: none.** `legacy.py` is self-contained (its
   only import from the package is `arithmetic.is_number`, :42). Every
   other module in `clausal/logic/clpq/` is a ported 1.3.3 file that
   `holzbaur.py` reaches: `bounded_simplex` (bv.pl), `fourier_motzkin`
   (fourmotz.pl), `inequalities` (ineq.pl), `redundancy` (redund.pl),
   `projection`, `branch_and_bound`, `normal_form`, `linear_forms`,
   `components`, `delayed_goals`, `residual_constraints`,
   `variable_ordering`, `attributes`, `attribute_hooks`, `arithmetic`,
   `limits`. So step 2 deletes `legacy.py` (3,040 lines) and nothing
   else in `clpq/`.

### Behaviour that goes with legacy: decided (operator rulings 2026-11-06)

- **D1. `int_minimize/3`: binds.** It keeps its documented contract under
  the port: bb_inf/3's search, then the variables bound to bb_inf/5's
  vertex (done before the flip). Nothing is lost with legacy.
- **D2. `maximize/minimize` bind one optimal vertex under legacy**; the
  port posts `Expr = Opt` and keeps an optimal face as constraints
  (1.3.3, correct). Accepted with the flip.
- **D3. Chain unification is slower: floor accepted.** The port's loops
  run in C (`clpq/_linear_forms_core.c`); what remains is 1.3.3's cubic
  work, 2.5 to 5.6 times legacy at n = 50 to 400 (DEVIATIONS.md D24).
  The next step is todo/clpq-row-order-key-cache-2026-11-06.md.
- **D4. The `-g` printer past the projection cap raises: accepted.** No
  unprojected fallback (DEVIATIONS.md D24, Medium 3).
- **D5. Integrality within Eps: accepted.** **D6. 1.3.3's float reading:
  accepted** (todo clpq-silently-accepts-floats-and-real-variables stays
  open on the separate question A08-D003).
- **D7. Docs: rewrite.** In step 2, the `docs/clpq.md` "How it works"
  sections (from "algorithm overview" to "the coefficient growth
  problem") are rewritten to describe the port's algorithm (1.3.3's
  bounded-variable simplex, class.pl components, project.pl's
  projection), not deleted.
- **`tools/division_census`:** retarget its patch of `clpq._linearize`
  to the port (nf.pl's division in `normal_form`) if that is cheap,
  otherwise retire the tool, in step 2.

### Tests and fixtures

Delete (legacy only):
- `tests/test_clpq_legacy_not_linear.py` (whole file).
- `tests/test_clpq_legacy_strict_bounds.py`: the `legacy` parameter
  (:24-28), `test_legacy_*` (:168, :284, :292), the legacy-vs-port
  differential (:366); keep the port cases as a port test (rename the file).
- `tests/test_clpq_deep_terms.py`: the `legacy` parameter (:32),
  `_legacy_linearize_recursive` and the tests on it (:232-293),
  `test_a_cyclic_term_under_legacy_is_not_evaluable` (:305),
  `test_legacy_refuses_a_deep_non_linear_term` (:339).
- `tests/test_residual_goals.py:227-260`
  (`test_legacy_names_unprojected_variables_after_the_answer`) and the
  `legacy` parameter at :69.
- `tests/clpq_port/test_resource_caps.py:1327`
  (`test_the_legacy_switch_has_no_cap_flags`); the `_HOLZBAUR` skipifs
  (:1207) become unconditional.
- `tests/clpq_port/test_oracle_tool.py:78-181`, the `solver="legacy"`
  cases (or point them at the port).
- `tests/clpq_port/test_switch.py`: `LEGACY_SUITES` and the nested runs
  (:33-36, :89-101), the `legacy` parametrisation (:66-80),
  `test_legacy_s_block_answers_once` (:203),
  `test_fd_to_q_bare_and_under_a_driver_against_legacy_and_the_oracle`
  (:523, keep its oracle half). `tests/clpq_port/test_package_surface.py`:
  rewrite for one solver plus the named error for `legacy`.
- `tests/clpq_port/test_projection_strictness_and_implied_equalities.py:102-125`:
  the `legacy` parameters (their xfail(strict) cases go).

Convert (drop the `legacy` parameter or branch, keep the port's answer):
- Parametrised over both solvers: `tests/test_clpq_entailed_strict.py:29-34`,
  `tests/test_clpq_error_terms.py:33,211,295-296`,
  `tests/test_clpq_entailed_relation_cells.py:131`,
  `tests/test_clpq_prolog_surface_builtins.py:17,182`,
  `tests/test_clpq_nonlinear_braces_in_pl.py:47-51` (delete that test),
  `tests/iso_l3/test_l3_clpq_brace_meta_call.py:88,104`,
  `tests/iso_l3/test_l3_hash_constant.py:278,317`.
- `HOLZBAUR`/`SOLVER` branches: `tests/test_clpq.py:49` (and its
  branches), `tests/test_dump_q_projection.py:22,60,71,136`,
  `tests/test_clpq_box_bounded_optimum.py:29,171,210`,
  `tests/test_units_clp.py:462-471,1530-1533`,
  `tests/test_clpq_fd_promotion_optima.py:316`,
  `tests/test_cli.py:232-240`, `tests/iso/test_copy_term_3_scryer.py:187-196,258`,
  `tests/iso/test_prolog_flags_scryer.py:113-118`,
  `tests/audit_2026_07_05/test_08_clpqr_z3.py:79` (and the F006 xfail at
  :137-141, which passes under the port: make it a plain test),
  `tests/clpq_port/test_switch_engine.py:20` and
  `tests/clpq_port/differential/test_differential_*.py` skipifs (become
  unconditional), `tests/clpq_port/differential/regenerate.py:39`.
- Docstrings that say "run the file under both":
  `tests/test_clpq_tabled_answers.py:17`, `tests/test_clpq_fd_dual_post.py:21`,
  `tests/test_clpq_fd_promotion_optima.py:18`,
  `tests/test_clpq_tabled_answer_subsumption.py:22`.
- Fixtures: `tests/fixtures/docs/clpq_sig_tests.clausal:94-108`
  (`clpq_port`/`bound_at_optimum` collapse to the port's answer),
  `tests/fixtures/docs/clpq_sigs.txt` comments.
- `tests/clpq_oracle.py:553` keeps its `solver` argument for the oracle
  tool or drops it.

### The legacy-only todos

- `todo/legacy-clpq-bb-inf-cannot-branch-on-an-eliminated-variable-2026-07-05.md`:
  close (move to `todo/done/`) as fixed by the port; the F006 pin passes
  under it and loses its xfail.
- `todo/legacy-clpq-disequality-closed-by-inequalities-is-accepted-2026-10-28.md`:
  close as fixed by the port, which fails `{X =\= Y}, {X =< Y}, {Y =< X}`
  as 1.3.3 does; add a port pin first (none found in tests/).
- `todo/clpq-projection-strictness-and-implied-equalities-2026-10-11.md`:
  says "close this when the port becomes the default": close with step 2,
  its pins (`tests/clpq_port/test_projection_strictness_and_implied_equalities.py`)
  keep the port's cases.
- `todo/clpq-snapshot-copies-the-whole-store-2026-10-11.md`: legacy's
  `_snapshot_tableau` (`legacy.py:1186`); close with the code (check
  first that the port keeps no whole-store copy per post).
- Stay open, drop their legacy mentions:
  `todo/clpq-silently-accepts-floats-and-real-variables-2026-07-05.md`
  (cites `legacy._linearize`; the port's read is
  `arithmetic.arithmetic_normalize`) and
  `todo/clpq-fd-constraints-posted-before-promotion-are-not-in-the-relaxation-2026-11-04.md`.

### Order

1. Move the six boundary helpers out of `legacy.py` (no behaviour change).
   `legacy.int_minimize` (:2864) goes with legacy; the package's
   `int_minimize` is the port's (HOLZBAUR_API).
2. Convert and delete the tests above; gate.
3. Delete `legacy.py`, its hook and key rows, the `legacy` value (named
   error), the solver switches; gate.
4. Docs (`docs/clpq.md`, `docs/cli.md`, `docs/flags.md`), CHANGELOG,
   `DEVIATIONS.md` D20's "legacy API" wording, the AGENTS.md maps, and the
   todos above.
