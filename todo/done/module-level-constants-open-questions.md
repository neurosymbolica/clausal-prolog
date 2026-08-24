# RESOLVED: open questions for module-level constants (`_PI_`) + singleton lint

**Filed:** 2026-08-24. **Resolved:** 2026-08-24, interactively. Decisions are folded into
`implementation_plans/module-level-constants.md`; this file is the record of what was asked
and chosen.

1. **`_UNUSED` suffix spelling** → single canonical `_UNUSED`; `_unused` is not an
   exemption. One grep target, one inverse-lint rule; the mixed-case jar of
   `_reason_UNUSED` on a deliberately-dead name is accepted as a feature.
2. **RHS grammar** → closed grammar (ground literals, prior constants, arithmetic) **plus
   compile-time `++(expr)`** — evaluated during directive processing (never lowered to a
   goal; the `++escape`-as-goal form always succeeds), then groundness-checked. The
   reproducibility caveat is documented, not guaranteed: `_N_ = ++os.cpu_count()` is legal
   and machine-dependent.
3. **Lexical edges** → interior must start with a non-digit (`_1_` rejected); `_X_UNUSED_`
   is legal but linted (visual collision with the unused-marker suffix). `__`, `_X__`,
   `__X_` remain excluded by the exactly-one-underscore-each-end rule.
4. **Classifier conformance test** → one test file importing all five
   `_is_logic_var_name` copies, running a shared spelling corpus, asserting identical
   answers; the `_X_`-shape corpus census grep lives in the same file as a guard until the
   re-carve lands.
5. **Singleton-lint rollout** → default-on with a per-file opt-out directive (strict-atoms
   precedent). Census at decision time: 439 singletons in 310 clauses across 102 of 370
   files (314 ALL_CAPS / 125 underscore style); largest cluster in generated clausal-scipy
   bidir fixtures. Same series: fix the fixture generator, mechanically clean the rest;
   warnings don't fail the suite, so partial cleanup doesn't block.
6. **Head-occurrence lint** → none. `area(_PI_, R)` is `area(3.14159, R)`; dispatch on a
   named ground value is a legitimate idiom.
7. **Bare-unification sugar** (`_PI_ = 3.14159` at module level) → stays deferred until
   after the directive form ships; sugar-first is the hard-to-reverse direction.
