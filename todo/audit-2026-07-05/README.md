# Audit 2026-07-05 — queued todos

Fixes are QUEUED here, never applied by the audit sessions.

- `fix-<ID>-<slug>.md` — remediation understood; any implementer.
- `investigate-<ID>-<slug>.md` — needs deeper root-cause/design work; tagged for Opus.

Completed todos move to this directory's own `done/` — **not** the repo-level
`todo/done/`. Session 12 dedups and maintains this index.

## Counts (2026-07-06, A12 synthesis)

161 fix + 23 investigate = 184 todos (A01–A12). Re-verification 2026-07-06: all
11 subsystem test files reproduce their recorded pass/xfail counts exactly — no
finding was culled as a false positive, no regression guard broke.

## Status (2026-07-30)

**160 of 185 closed; 25 open.** The Status column below was regenerated from
`done/` on 2026-07-30 — until then every row still read `queued`/`parked`,
including 159 whose files had already moved, so the table read as though nothing
had been fixed. One row was missing entirely (`fix-A06-alldiff-int64-sentinel.md`,
added by the 2026-07-10 fix-review) and has been added.

The 25 open items are 6 `fix-*` and 19 `investigate-*`. Almost all are open *by
decision*, not by neglect: the `fix-*` ones are gated on parked design questions
(A06-D002/D005, A08-D001/D003), and the `investigate-*` ones are either the
parked questions themselves or Opus-tagged design work. Two exceptions worth
knowing: `investigate-A10-imported-head-clobber.md` has a real fix sitting on the
unmerged branch `fix/imported-functor-clause-destruction`, blocked by
`todo/imported-clause-refusal-misattributes-ownership.md`; and A01-D001's
resolution (2026-07-07) unblocked its whole cluster, but only A07 and A09 acted
on it — A02-D002, A05-D001 and A06-D005 are now ripe and untouched.

**The cluster lists and per-subsystem `design-questions.md` Status columns below
are stale**, in both directions: the clusters still name items that are closed,
and the subsystem ledgers still say "open" for questions the user resolved on
2026-07-07 and for all 11 A11 questions that landed fixes.
`docs/superpowers/audits/2026-07-05-fable-partition/DESIGN-DECISIONS.md` plus the
fix commits are the only reliable record of what was decided.

## Cross-cutting clusters (fix once, close many)

Triage these against `docs/superpowers/audits/2026-07-05-fable-partition/DESIGN-DECISIONS.md`
§"Triage order" — each cluster is one decision plus mechanical fixes:

1. **Error protocol / raw-exception escapes** (A09-D002 + A11-D001):
   `fix-A09-raw-exception-escapes.md`, `fix-A09-db-permission-logic-exception.md`,
   `fix-A11-module-pred-error-protocol.md`, `fix-A11-wrapper-error-escapes.md`,
   `fix-A04-drive-until-yield-runtime-error.md`, `investigate-A09-runtimeerror-swallow.md`,
   `fix-A06-element-unbounded-index.md` (error type), `fix-A12-eq-nonnumeric-operand.md`
   (error type), `fix-A05-has-units-error-path.md`. One boundary-conversion fix at the
   ModulePredicate/trampoline layer + a narrowed drive-loop catch closes most of these.
2. **Cross-type conflation (bool/int/float identity, A01-D001)**:
   `fix-A04-tabling-cross-type-conflation.md`, `fix-A06-bool-hook-divergence.md`,
   `fix-A09-bool-acceptance-matrix.md`, parked design files for A02/A05/A07/A09.
   Decide A01-D001 first; the fixes then follow one policy.
3. **Container/walker blindness (A01-F008 walk vs _deref_walk split)**:
   `investigate-A01-walk-vs-deref-walk-split.md`, `fix-A01-occurs-check-compound-blindness.md`,
   `fix-A05-dif-collect-free-vars-container-blindness.md`,
   `fix-A05-term-attvars-container-blindness.md`, `fix-A09-sort-msort-deref.md`.
   A unified term-traversal API is the single fix these all want.
4. **`//` and `%` semantics (A08-D001)**: `fix-A08-z3-floordiv-mod-translation.md`
   (also cited by A06-F014), `fix-A08-ortools-floordiv-mod-translation.md`,
   `fix-A11-prolog-mod-semantics.md`, `fix-A11-prolog-floordiv-export.md`.
5. **Tabling answer representation**: `fix-A04-tabled-answer-hashability.md`,
   `investigate-A12-tabling-answer-constraints.md`,
   `investigate-A04-slg-completion-architecture.md` — one re-architecture covers
   hashability, constraint residue and completion.
6. **Directive robustness (A10-F012 family)**: `fix-A10-malformed-directive-silent-noop.md`,
   `fix-A12-directive-target-validation.md`, `fix-A12-dynamic-forward-declaration.md`,
   `fix-A10-zero-arity-fact-silent-noop.md` — one load-time validation pass.
7. **Namespace reservation (both directions)**: `fix-A10-clausal-call-shadowed.md`,
   `fix-A12-engine-namespace-leak.md`, `fix-A10-stdlib-shadowing-docs-guard.md`.

Dedup notes: cross-subsystem duplicates were already filed against a single todo
by the sessions (A06-F014 → A08's z3 todo; A05-F006 → A01's occurs-check todo;
A11-F043/F044 cite A09-F007's swallow). No fully-duplicate todo files were found
to delete; the clusters above are the collapse points.


| Todo | Kind | Severity | Finding | Owning subsystem | Status |
|------|------|----------|---------|------------------|--------|
| `fix-A01-occurs-check-compound-blindness.md` | fix | correctness | A01-F001 | A01 term-layer | done |
| `fix-A01-capi-put-attr-promote-path.md` | fix | correctness (latent C; unconfirmed — capi-only) | A01-F002 | A01 term-layer | done |
| `fix-A01-compound-var-functor.md` | fix | correctness | A01-F003 | A01 term-layer | done |
| `fix-A01-kwterm-unify-hook.md` | fix | correctness | A01-F004 | A01 term-layer | done |
| `fix-A01-seg-unify-gens-retention.md` | fix | memory | A01-F005 | A01 term-layer | done |
| `fix-A01-seglist-element-var-ground-path.md` | fix | correctness | A01-F006 | A01 term-layer | done |
| `fix-A01-seglist-bytes-target.md` | fix | correctness | A01-F007 | A01 term-layer | done |
| `investigate-A01-walk-vs-deref-walk-split.md` | investigate (Opus) | design/correctness | A01-F008 (+ `_deref_walk` seam → A04/A09) | A01 ↔ A04/A09 | done |
| `fix-A01-segstring-scalar-varseg-guard.md` | fix | error-path | A01-F009 | A01 term-layer | done |
| `fix-A01-seg-getitem-slice-in-prefix.md` | fix | design (low) | A01-F010 | A01 term-layer | done |
| `fix-A01-terms-all-exports.md` | fix | doc-drift | A01-F011 | A01 term-layer | done |
| `investigate-A01-parked-design-decisions.md` | investigate (**USER**, not Opus) | design | A01-D001 / A01-D002 / A01-D004 | A01 (D001 cross-cuts A02/A04) | parked by user 2026-07-05 |
| `fix-A02-dispatch-partial-term-fallback.md` | fix | correctness | A02-F001 | A02 compiler-heads | done |
| `fix-A02-list-dispatch-fallthrough.md` | fix | correctness | A02-F002 | A02 compiler-heads | done |
| `fix-A02-head-wildcard-accept-all.md` | fix | correctness | A02-F003 | A02 compiler-heads (assertz seam → A09) | done |
| `fix-A02-multistar-trailing-fixed.md` | fix | correctness | A02-F004 | A02 compiler-heads | done |
| `fix-A02-dispatch-docstring-arg-offsets.md` | fix | doc-drift | A02-F005 | A02 compiler-heads | done |
| `investigate-A02-parked-design-decisions.md` | investigate (**USER**, not Opus) | design | A02-D002 (depends on A01-D001) | A02 (cross-cuts A04 tabling keys) | parked by user preference 2026-07-05 |
| `fix-A03-tro-nondet-prefix.md` | fix | correctness (solution loss) | A03-F001 | A03 compiler-goals | done |
| `fix-A03-dr-nondet-prefix.md` | fix | correctness (data corruption; same root as F001) | A03-F002 | A03 compiler-goals | done |
| `fix-A03-tro-signal-bucket-not-generator.md` | fix | correctness (crash) | A03-F003 | A03 compiler-goals | done |
| `fix-A03-catch-functor-catcher.md` | fix | correctness | A03-F004 | A03 compiler-goals (unify seam → A01-D004) | done |
| `fix-A03-setof-not-sorted.md` | fix | correctness | A03-F005 | A03 compiler-goals | done |
| `fix-A03-findall-template-sharing.md` | fix | correctness | A03-F006 | A03 compiler-goals (design A03-D002) | done |
| `fix-A03-specialize-midbody-goals.md` | fix | correctness | A03-F007 | A03 specialization (design A03-D003) | done |
| `fix-A03-deep-unfold-const-args.md` | fix | correctness | A03-F008 | A03 specialization | done |
| `fix-A03-cpd-extension-chaining.md` | fix | correctness (solution loss) | A03-F009 | A03 specialization | done |
| `fix-A03-readme-ctco-drift.md` | fix | doc-drift | A03-F010 | A03 compiler-goals | done |
| `investigate-A03-parked-design-decisions.md` | investigate (**USER**, not Opus) | design | A03-D001 / A03-D002 / A03-D003 (+ determinism-table governance) | A03 (D001 cross-cuts A01) | parked by user preference 2026-07-05 |
| `fix-A04-drive-until-yield-runtime-error.md` | fix | correctness | A04-F009 | A04 runtime-tabling | done |
| `fix-A04-naf-tabled-no-entry.md` | fix | correctness | A04-F002 | A04 runtime-tabling | done |
| `fix-A04-poisoned-evaluating-tables.md` | fix | correctness | A04-F007 | A04 runtime-tabling | done |
| `fix-A04-query-wfs-truth-stub.md` | fix | correctness | A04-F004 | A04 runtime-tabling | done |
| `fix-A04-root-suspend-spurious-solution.md` | fix | correctness | A04-F008 | A04 runtime-tabling | done |
| `fix-A04-tabled-answer-hashability.md` | fix | correctness | A04-F005 | A04 runtime-tabling | done |
| `fix-A04-tabling-cross-type-conflation.md` | fix | correctness | A04-F006 | A04 runtime-tabling | done |
| `fix-A04-when-disjunction-fired-flag.md` | fix | correctness | A04-F010 | A04 runtime-tabling | done |
| `fix-A05-dif-collect-free-vars-container-blindness.md` | fix | correctness | A05-F001 | A05 constraints-core | done |
| `fix-A05-dif-hook-malformed-attr-segfault.md` | fix | correctness (C crash) | A05-F002 | A05 constraints-core | done |
| `fix-A05-has-units-error-path.md` | fix | error-path | A05-F005 | A05 constraints-core | done |
| `fix-A05-structural-eq-asymmetry-consistency.md` | fix | correctness | A05-F003 | A05 constraints-core | done |
| `fix-A05-term-attvars-container-blindness.md` | fix | correctness | A05-F004 | A05 constraints-core | done |
| `fix-A06-bool-hook-divergence.md` | fix | correctness | A06-F009 | A06 clpfd | queued |
| `fix-A06-capi-fdvar-duck-typing.md` | fix | memory (C) | A06-F016 | A06 clpfd | done |
| `fix-A06-crosscutting-doc-drift.md` | fix | doc-drift | A06-F017 | A06 clpfd | done |
| `fix-A06-element-unbounded-index.md` | fix | correctness (error-path) | A06-F005 | A06 clpfd | done |
| `fix-A06-gcc-var-count.md` | fix | correctness | A06-F013 | A06 clpfd | done |
| `fix-A06-indomain-no-propagation.md` | fix | correctness | A06-F008 | A06 clpfd | done |
| `fix-A06-int64-boundary-sentinel.md` | fix | correctness | A06-F007 | A06 clpfd | done |
| `fix-A06-linear-eq-unbounded-narrowing.md` | fix | correctness | A06-F002 | A06 clpfd | done |
| `fix-A06-ne-expression-operands.md` | fix | correctness | A06-F001 | A06 clpfd | done |
| `fix-A06-ne-reflexive.md` | fix | correctness | A06-F010 | A06 clpfd | done |
| `fix-A06-plus-type-check.md` | fix | correctness | A06-F015 | A06 clpfd | done |
| `fix-A06-rational-subexpr-typeerror.md` | fix | correctness | A06-F006 | A06 clpfd | done |
| `fix-A06-scalar-bignum-float-division.md` | fix | correctness | A06-F004 | A06 clpfd | done |
| `fix-A06-sum-op-strings.md` | fix | design | A06-F011 | A06 clpfd | queued |
| `fix-A06-sum-scalar-double-rounding.md` | fix | correctness | A06-F003 | A06 clpfd | done |
| `fix-A06-sum-type-check.md` | fix | correctness | — | A06 clpfd | done |
| `fix-A06-zcompare-weak-propagation.md` | fix | correctness | A06-F012 | A06 clpfd | done |
| `fix-A06-alldiff-int64-sentinel.md` | fix | correctness (latent C; unsound) | A06-F007 sibling | A06 clpfd | done |
| `fix-A07-bool-labeling-ground-validation.md` | fix | error-path | A07-F009 | A07 clpb-sat | done |
| `fix-A07-clpb-aliasing-no-rebuild.md` | fix | correctness | A07-F002 | A07 clpb-sat | done |
| `fix-A07-clpb-c-recursion-overflow.md` | fix | correctness (C crash) | A07-F007 | A07 clpb-sat | done |
| `fix-A07-clpb-doc-drift.md` | fix | doc-drift | A07-F011 | A07 clpb-sat | done |
| `fix-A07-clpb-global-table-leak.md` | fix | memory | A07-F006 | A07 clpb-sat | done |
| `fix-A07-clpb-python-fallback-rebinding.md` | fix | correctness | A07-F008 | A07 clpb-sat | done |
| `fix-A07-clpsat-bindings-invisible.md` | fix | correctness | A07-F005 | A07 clpb-sat | done |
| `fix-A07-collect-bdd-var-ids-exponential.md` | fix | correctness/perf | A07-F001 | A07 clpb-sat | done |
| `fix-A08-clpq-empty-domain-check.md` | fix | correctness | A08-F003 | A08 clpqr-z3 | done |
| `fix-A08-clpq-fix-variable-bound-overwrite.md` | fix | correctness | A08-F001 | A08 clpqr-z3 | done |
| `fix-A08-clpq-float-mixing-enforcement.md` | fix | correctness | A08-F007 | A08 clpqr-z3 | queued |
| `fix-A08-clpq-tableau-weakref-lifecycle.md` | fix | memory | A08-F005 | A08 clpqr-z3 | done |
| `fix-A08-clpr-imod-interval.md` | fix | correctness | A08-F009 | A08 clpqr-z3 | done |
| `fix-A08-clpr-pyfallback-nan-corners.md` | fix | correctness | A08-F012 | A08 clpqr-z3 | done |
| `fix-A08-clpr-strict-and-ne-aliasing.md` | fix | correctness | A08-F010 / A08-F011 | A08 clpqr-z3 | done |
| `fix-A08-ortools-floordiv-mod-translation.md` | fix | correctness | A08-F015 | A08 clpqr-z3 | queued |
| `fix-A08-ortools-lp-strict-epsilon-doc.md` | fix | design | A08-F017 | A08 clpqr-z3 | done |
| `fix-A08-ortools-optimize-unify-failures.md` | fix | correctness | A08-F016 | A08 clpqr-z3 | done |
| `fix-A08-z3-floordiv-mod-translation.md` | fix | correctness | A06-F014 / A08-F014 | A08 clpqr-z3 | queued |
| `fix-A09-arith-type-checks.md` | fix | correctness | A09-F011 | A09 builtins | done |
| `fix-A09-assertz-rule-lowering.md` | fix | correctness | A09-F005 | A09 builtins | done |
| `fix-A09-atom-chars-str-args.md` | fix | correctness | A09-F017 | A09 builtins | done |
| `fix-A09-bool-acceptance-matrix.md` | fix | correctness (design-gated) | A09-F015 | A09 builtins | done |
| `fix-A09-char-type-py-fallback.md` | fix | correctness | A09-F014 | A09 builtins | done |
| `fix-A09-char-type-unicode-enum.md` | fix | correctness | A09-F013 | A09 builtins | done |
| `fix-A09-chars-core-trail-check.md` | fix | memory (C) | A09-F020 | A09 builtins | done |
| `fix-A09-db-permission-logic-exception.md` | fix | correctness | A09-F006 | A09 builtins | done |
| `fix-A09-doc-drift.md` | fix | doc-drift | A09-F023 / A09-F024 / A09-F025 / A09-F026 | A09 builtins | done |
| `fix-A09-filter-map-binding-capture.md` | fix | correctness | A09-F002 | A09 builtins | done |
| `fix-A09-functor-nonatom-names.md` | fix | design | A09-F027 | A09 builtins | done |
| `fix-A09-ho-var-element-bindings.md` | fix | correctness | A09-F003 | A09 builtins | done |
| `fix-A09-lists-core-arg-validation.md` | fix | memory (C crash) | A09-F021 | A09 builtins | done |
| `fix-A09-minor-iso-divergences.md` | fix | design | A09-F028 / A09-F030 / A09-F031 | A09 builtins | done |
| `fix-A09-must-be-list-strings.md` | fix | correctness | A09-F016 | A09 builtins | done |
| `fix-A09-pairs-malformed-pairs.md` | fix | correctness | A09-F018 | A09 builtins | done |
| `fix-A09-raw-exception-escapes.md` | fix | correctness | A09-F012 | A09 builtins | done |
| `fix-A09-retract-bindings.md` | fix | correctness (design-gated) | A09-F008 | A09 builtins | done |
| `fix-A09-same-length-seg.md` | fix | correctness | A09-F019 | A09 builtins | done |
| `fix-A09-seq-promotion-was-string.md` | fix | correctness | A09-F032 | A09 builtins | done |
| `fix-A09-sequence-unify-terminals.md` | fix | correctness | A09-F009 | A09 builtins | done |
| `fix-A09-sort-msort-deref.md` | fix | correctness | A09-F001 | A09 builtins | done |
| `fix-A09-typecheck-seg-consistency.md` | fix | design | A09-F029 | A09 builtins | done |
| `fix-A10-arrow-lambda-source-lines.md` | fix | correctness | A10-F006 | A10 rewriting-import | done |
| `fix-A10-clausal-call-shadowed.md` | fix | correctness | A10-F013 | A10 rewriting-import | done |
| `fix-A10-comparechain-goal-lowering.md` | fix | design | A10-F009 | A10 rewriting-import | done |
| `fix-A10-dump-transformed-black-unboundlocal.md` | fix | correctness | A10-F007 | A10 rewriting-import | done |
| `fix-A10-edcg-plain-dcg-threading.md` | fix | correctness | A10-F003 | A10 rewriting-import | done |
| `fix-A10-embed-visitname-store-context.md` | fix | correctness | A10-F002 | A10 rewriting-import | done |
| `fix-A10-import-alias-single-letter-lint.md` | fix | design | A10-F017 | A10 rewriting-import | done |
| `fix-A10-infer-args-walrus-order.md` | fix | correctness | A10-F015 | A10 rewriting-import | done |
| `fix-A10-magic-args-stopiteration.md` | fix | correctness | A10-F014 | A10 rewriting-import | done |
| `fix-A10-malformed-directive-silent-noop.md` | fix | design | A10-F012 | A10 rewriting-import | done |
| `fix-A10-pl-cut-emitted-as-dead-goal.md` | fix | correctness | A10-F001 | A10 rewriting-import | done |
| `fix-A10-pyc-transformer-version-tag.md` | fix | design (unconfirmed) | A10-F018 | A10 rewriting-import | done |
| `fix-A10-pythonic-ast-traversal-exports.md` | fix | doc-drift | A10-F016 | A10 rewriting-import | done |
| `fix-A10-regex-autobind-body-vars.md` | fix | correctness | A10-F005 | A10 rewriting-import | queued |
| `fix-A10-stdlib-shadowing-docs-guard.md` | fix | correctness | A10-F010 | A10 rewriting-import | done |
| `fix-A10-term-expansion-doc-examples.md` | fix | doc-drift | A10-F008 | A10 rewriting-import | done |
| `fix-A10-zero-arity-fact-silent-noop.md` | fix | correctness | A10-F011 | A10 rewriting-import | done |
| `fix-A11-c2p-cut-emission.md` | fix | design | A11-F036 | A11 modules-interop | done |
| `fix-A11-datetime-component-coercion.md` | fix | correctness | A11-F015 | A11 modules-interop | done |
| `fix-A11-graphs-dedup-adjacency.md` | fix | design | A11-F051 | A11 modules-interop | done |
| `fix-A11-graphs-doc-drift.md` | fix | doc-drift | A11-F054 / A11-F058 | A11 modules-interop | done |
| `fix-A11-graphs-is-isolated.md` | fix | correctness | A11-F046 | A11 modules-interop | done |
| `fix-A11-graphs-iterative-dfs.md` | fix | correctness | A11-F043 / A11-F044 | A11 modules-interop | done |
| `fix-A11-graphs-multidispatch-params.md` | fix | design | A11-F053 | A11 modules-interop | done |
| `fix-A11-graphs-negative-weights.md` | fix | correctness | A11-F045 | A11 modules-interop | done |
| `fix-A11-graphs-path-cost-parallel.md` | fix | correctness | A11-F049 | A11 modules-interop | done |
| `fix-A11-graphs-spanning-disconnected.md` | fix | correctness | A11-F050 | A11 modules-interop | done |
| `fix-A11-graphs-type-robustness.md` | fix | design | A11-F052 | A11 modules-interop | done |
| `fix-A11-module-pred-error-protocol.md` | fix | correctness; design | A11-F004 / A11-F005 | A11 modules-interop | done |
| `fix-A11-prolog-arith-structural-eq.md` | fix | correctness | A11-F032 | A11 modules-interop | done |
| `fix-A11-prolog-arrow-metacall-reject.md` | fix | correctness | A11-F024 | A11 modules-interop | done |
| `fix-A11-prolog-atom-representation.md` | fix | correctness | A11-F025 / A11-F035 | A11 modules-interop | done |
| `fix-A11-prolog-dcg-pushback-reject.md` | fix | correctness | A11-F039 | A11 modules-interop | done |
| `fix-A11-prolog-dead-code.md` | fix | maintenance | A11-F042 | A11 modules-interop | done |
| `fix-A11-prolog-floordiv-export.md` | fix | correctness | A11-F031 | A11 modules-interop | done |
| `fix-A11-prolog-mod-semantics.md` | fix | correctness | A11-F020 | A11 modules-interop | done |
| `fix-A11-prolog-op-table-completeness.md` | fix | correctness; design | A11-F026 / A11-F027 / A11-F041 | A11 modules-interop | done |
| `fix-A11-prolog-parser-assoc-enforcement.md` | fix | correctness | A11-F028 / A11-F038 | A11 modules-interop | done |
| `fix-A11-prolog-pow-assoc-emit.md` | fix | correctness | A11-F030 | A11 modules-interop | done |
| `fix-A11-prolog-token-spans.md` | fix | correctness | A11-F029 / A11-F037 | A11 modules-interop | done |
| `fix-A11-prolog-tokenizer-escapes.md` | fix | correctness; design | A11-F034 / A11-F040 | A11 modules-interop | done |
| `fix-A11-prolog-truncdiv-bignum.md` | fix | correctness | A11-F021 | A11 modules-interop | done |
| `fix-A11-prolog-tuple-arg-arity.md` | fix | correctness | A11-F023 | A11 modules-interop | done |
| `fix-A11-prolog-univ-qualified.md` | fix | correctness | A11-F033 | A11 modules-interop | done |
| `fix-A11-prolog-var-rename-injective.md` | fix | correctness | A11-F022 | A11 modules-interop | done |
| `fix-A11-reflection-anon-var-collision.md` | fix | correctness (design-gated) | A11-F011 | A11 modules-interop | done |
| `fix-A11-reflection-dict-term.md` | fix | correctness | A11-F013 | A11 modules-interop | done |
| `fix-A11-reflection-kwhead-order.md` | fix | correctness (design-gated) | A11-F010 | A11 modules-interop | done |
| `fix-A11-reflection-unbound-inputs.md` | fix | design | A11-F014 | A11 modules-interop | done |
| `fix-A11-regex-doc-drift.md` | fix | design; doc-drift | A11-F008 / A11-F009 | A11 modules-interop | done |
| `fix-A11-regex-dynamic-pattern-autobind.md` | fix | design | A11-F007 | A11 modules-interop | done |
| `fix-A11-regex-expansion-name-gate.md` | fix | correctness | A11-F003 | A11 modules-interop | done |
| `fix-A11-regex-mixed-groups.md` | fix | design | A11-F006 | A11 modules-interop | done |
| `fix-A11-regex-shim-module.md` | fix | correctness | A11-F001 | A11 modules-interop | done |
| `fix-A11-regex-subject-coercion.md` | fix | correctness | A11-F002 | A11 modules-interop | done |
| `fix-A11-reify-ast-arrow-repair.md` | fix | correctness | A11-F012 | A11 modules-interop | done |
| `fix-A11-units-docs-and-constants.md` | fix | correctness; doc-drift | A11-F048 / A11-F055 / A11-F056 / A11-F059 | A11 modules-interop | done |
| `fix-A11-units-negative-literal-sugar.md` | fix | correctness | A11-F047 | A11 modules-interop | done |
| `fix-A11-units-pow-integer-only.md` | fix | design | A11-F057 | A11 modules-interop | done |
| `fix-A11-wrapper-error-escapes.md` | fix | design | A11-F016 / A11-F017 / A11-F018 / A11-F019 | A11 modules-interop | done |
| `fix-A12-directive-target-validation.md` | fix | correctness | A12-F003 | A12 seams | done |
| `fix-A12-dynamic-forward-declaration.md` | fix | correctness | A12-F005 | A12 seams | done |
| `fix-A12-engine-namespace-leak.md` | fix | design | A12-F004 | A12 seams | done |
| `fix-A12-eq-nonnumeric-operand.md` | fix | correctness | A12-F002 | A12 seams | done |
| `investigate-A04-parked-design-decisions.md` | investigate (Opus) | design | A04-F011 | A04 runtime-tabling | queued |
| `investigate-A04-slg-completion-architecture.md` | investigate (Opus) | correctness | A04-F001 | A04 runtime-tabling | done |
| `investigate-A04-wfs-variant-resolution.md` | investigate (Opus) | correctness | A04-F003 | A04 runtime-tabling | queued |
| `investigate-A05-parked-design-decisions.md` | investigate (USER) | design | A05-D001 / A05-D002 | A05 constraints-core | parked by user preference |
| `investigate-A06-parked-design-decisions.md` | investigate (Opus) | design | A06-F018 | A06 clpfd | queued |
| `investigate-A07-parked-design-decisions.md` | investigate (Opus) | correctness (design-gated) | A07-F003 / A07-F004 | A07 clpb-sat | queued |
| `investigate-A08-clpq-bound-enforcement.md` | investigate (Opus) | correctness | A08-F002 / A08-F006 | A08 clpqr-z3 | queued |
| `investigate-A08-clpq-prolog-oracle.md` | investigate (Opus) | infrastructure | — | A08 clpqr-z3 | queued |
| `investigate-A08-clpq-strict-inequalities.md` | investigate (Opus) | correctness; design | A08-F004 / A08-F008 | A08 clpqr-z3 | queued |
| `investigate-A08-parked-design-decisions.md` | investigate (Opus) | design (unconfirmed impact) | A08-F018 | A08 clpqr-z3 | queued |
| `investigate-A08-solver-store-sync-hooks.md` | investigate (Opus) | correctness | A08-F013 | A08 clpqr-z3 | queued |
| `investigate-A09-copy-term-attrs.md` | investigate (Opus) | correctness (design-gated) | A09-F010 | A09 builtins | queued |
| `investigate-A09-ho-committed-choice.md` | investigate (Opus) | correctness (design-gated) | A09-F004 | A09 builtins | queued |
| `investigate-A09-parked-design-decisions.md` | investigate (USER) | design | A09-D001..D005 (+F022) | A09 builtins | parked by user preference |
| `investigate-A09-runtimeerror-swallow.md` | investigate (Opus) | correctness (design-gated) | A09-F007 | A09 builtins | done |
| `investigate-A10-imported-head-clobber.md` | investigate (Opus) | correctness (design-gated) | A10-F004 | A10 rewriting-import | queued |
| `investigate-A10-parked-design-decisions.md` | investigate (USER) | design | A10-D001..D004 | A10 rewriting-import | parked by user preference |
| `investigate-A11-parked-design-decisions.md` | investigate (USER) | design | A11-D001..D011 | A11 modules-interop | done |
| `investigate-A12-tabling-answer-constraints.md` | investigate (Opus) | correctness | A12-F001 | A12 seams | queued |
