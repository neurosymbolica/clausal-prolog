**DONE (with residual) — commit 5f0a5088.** Numeric leaves (bool/float/complex)
are type-tagged `(type, value)` in `_normalize_for_key` (Py + C do_normalize,
P52 parity); exact int stays canonical. Tabled `tt(X)` now yields all four
types; `make_subgoal_key([1]) != [True] != [1.0]`. Semantics-neutral (answer
unification untouched, deferring to A01-D001). **Residual:** Decimal/Fraction
are left raw in BOTH impls (still conflate with int) — a narrower documented
residual, tied to A01-D001; not exercised by any fixture.

---

# fix(A04-F006): tabling conflates 1/True/1.0/Decimal(1) in variant keys and answer dedup

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F006
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF006CrossTypeConflation` (1 xfail — flip to pass; 2 guards)
**Design:** A04-D003 → cite A02-D002 / A01-D001 (parked) — do NOT decide unification semantics here

## Bug

Variant keys (`_normalize_for_key`, `tabling.py:149-178`; C
`_tabling_core.c:58-184`) and the answer dedup set
(`TableEntry.answer_set`) rely on Python `==`/`hash`, where
`1 == True == 1.0 == Decimal(1)`:

- Facts `tt(1), tt(True), tt(2.0), tt(2)` tabled → `tt(X)` yields
  `[1, 2.0]`; untabled twin yields all four (types preserved). Tabled vs
  untabled solution sets diverge — the differential-oracle definition of
  a bug.
- `make_subgoal_key([1]) == make_subgoal_key([True]) ==
  make_subgoal_key([1.0])`: `p(True)` consumes `p(1)`'s table.

C and Python agree (P52 differential) — the defect is the equality
relation, not an implementation drift.

## Fix direction (interim, semantics-neutral)

Type-tag scalars in the variant key and the dedup key:
`(type(v), v)` for bool/int/float/Decimal/Fraction leaves (mirror in
`do_normalize`). This makes tabled dedup structural (variant-check
semantics, ISO-aligned) without touching unification. The COMPLETE-path
answer unification is unchanged, so `tt(1)` still unifies with a stored
`True` answer exactly as the untabled dispatch would — parity preserved
whichever way A01-D001 lands.

Keep the change in one helper shared by key + dedup (see
`fix-A04-tabled-answer-hashability.md` — same code motion).

## Acceptance

- Tabled `tt(X)` yields 4 answers, types preserved, order matching the
  untabled twin.
- `make_subgoal_key([1]) != make_subgoal_key([True]) !=
  make_subgoal_key([1.0])` (update the mechanism guard test, which
  currently pins the conflating behaviour).
- `tests/test_tabling.py` key-computation unit tests reviewed for pinned
  conflation.
