# Engine lane handoff — 2026-09-11, minor currency units, END

Continues `SESSION-HANDOFF-2026-09-11-engine-lane-END.md`, whose §4a/§4b task is now DONE —
but **not by the design §4b ruled for.** Read §2 below before trusting anything in §4b.

## 1. State of the world

    clone main        6e18af69      (this landing)
    canonical main    96cc8df6      UNCHANGED — the operator held the landing
    box main          not queried from here (no `box` remote in the clone; it lives on
                      /workspace/clausal)

**The operator explicitly chose "Hold — clone only".** Nothing crossed into
`/workspace/clausal`, so no lane's tree moved. A sync is a clean fast-forward whenever it is
wanted (`git merge-base --is-ancestor` confirmed), and there are **no C changes**, so no `.so`
rebuild and none of the rename-swap hazard applies.

Three claims, separately, none implying another:

| axis | who | measured on | result |
| --- | --- | --- | --- |
| engine suite | me | 6e18af69 | 144 failed / 15877 passed / 1 error — failure NAME SET **identical** to the 946d7296 baseline (0 new, 0 fixed; both sets 144, both non-empty) |
| doc blocks | me | 6e18af69 | 38 violations before and after; scanner confirmed to reach `docs/currency.md` (11 of the 38 are there) and none falls inside the new section |
| corpus / batch bodies | — | not run | untouched: nothing left the clone |

Extractions: `$CLAUDE_JOB_DIR/tmp/after.fail` (144) against `tip.sorted`. Regenerate rather
than trust them.

## 2. What landed, and why it is not what §4b ruled

`cent`, an **ordinary scaled unit** of its base currency:

    # clausal/modules/countries/united_states.py   (generated)
    cent = _make_minor_unit(dollar)        # Quantity(Decimal('0.01'), {dollar: 1})

    -import_from(united_states, [dollar, cent])
    -constant_number_units(sga_monthly, 155000, cent)

      stored                    Quantity(Decimal('1550.00'), dollar)
      constant_number_units/3   155000, cent
      constant_value/2          Quantity(Decimal('1550.00'), dollar)

That is §4b's behaviour table *exactly*, reached by defining a unit instead of building a
compile-time spelling recogniser. The feature is a 35-line factory plus one generated line per
currency — **no change to the directive, the annotation sugar, or arithmetic**, and it works
in value position and in arithmetic, which §4b's design could not.

§4b ruled against a real scaled unit on three reasons. **Two do not survive measurement on
this tree**, and the operator ruled for the real-unit design after seeing them:

- *"one careless `0.01` from putting money in floats"* — **false for currency.** The currency
  path coerces every magnitude through `Decimal(str(f))`: even `Quantity(0.01, {dollar: 1})`
  stores `Decimal('0.01')`. The `gram = Quantity(1e-3, …)` hazard is real for PHYSICAL units
  and blocked here. `_make_minor_unit` also never writes a factor — it derives one from the
  currency's own ISO scale with `scaleb`.
- *"a real `eur_cents` would turn 5000 into 50 euro"* — it turns it into `Decimal('50.00')
  euro`, the correct amount and the single representation §4b itself wanted. Normalisation
  MULTIPLIES by the factor. Not a difference between the designs.
- *"a dimension per currency-scale doubles the dimension table"* — stands, but applies to a
  BASE dimension. A scaled unit adds none.

The ambiguity objection (`cent` means different amounts in different currencies) is answered
by putting the currency **in scope** rather than in the name: `united_states.cent` and
`european_union.cent` are distinct and never add — the rule that already governs `dinar`.

**The lesson, and it is the one that keeps recurring here:** all three reasons were written as
measured facts. Two were extrapolations from the physical-units code to the currency code,
which behaves differently, and neither had been run. One grep-and-run settled both.

## 3. Also in this landing

- **A real float leak, fixed.** `constant_number_units/3` reported the declared magnitude as a
  binary FLOAT (`19.99`) though the constant's VALUE is `Decimal('19.99')` — the one channel
  whose whole job is fidelity to the declaration was the one place money went binary. The
  declared magnitude now follows the value's numeric kind. Ints and non-currency floats are
  untouched, each with a negative-control test.
- **Both landed documents that stated the superseded ruling now record what changed**, rather
  than being silently rewritten: `docs/currency.md` (the section is replaced, with a "What
  changed, and why") and
  `todo/constant-number-units-3-reports-normalised-not-declared-2026-09-11.md` (a SUPERSEDED
  section appended).
- **The generator is the source of truth.** `MINOR_UNITS = {"EUR": "cent", "USD": "cent"}` in
  `scripts/gen_currencies.py`, with an assertion that a subunit word never collides with a
  currency word in the same jurisdiction. The two generated modules were hand-edited to match
  byte-for-byte because **babel is not installed in this venv**, so the generator cannot be
  run here to verify. Anyone who installs babel should run it and confirm the diff is empty.

## 4. Open, and what it needs

- **`clausal_to_prolog` folds a scaled-unit constant to the wrong magnitude.** A minor-unit
  constant exports 100x too large (`pay(155000)` where the engine holds `1550.00 dollar`),
  flagged only by a `/* LOSSY: */` comment. **Pre-existing and general** — `30 day` exports as
  `30` though the engine stores 2592000 seconds. Not fixed here: the correct fix is the
  exporter's, and it is scope, not a line. Pinned by a characterisation test, warned about in
  the docs, three costed options in
  `todo/exporter-folds-scaled-units-to-the-wrong-magnitude-2026-09-11.md`. **iso-export-lane
  has been told.** Do not export a rulebase declaring constants in minor units until it lands.
- **Ratio units (`basis_points`, `percent`) — the obvious next task.** Designed, not built:
  `todo/ratio-declaration-units-basis-points-and-percent-2026-09-11.md`. This landing proved
  the mechanism needs nothing new, so it is small. It is **corpus-lane's live blocker**
  (`crr_leverage_ratio` computes in bps throughout, with `leverage_ratio_bps/2` EXPORTED).
  One thing to verify first, don't assume it: the exactness that makes currency safe comes
  from the CURRENCY coercion path, and a DIMENSIONLESS quantity may not have it.
- **Only EUR and USD have a minor unit.** Adding one is a `MINOR_UNITS` entry plus a
  regeneration. 238 of 254 currencies have a subunit; the 16 at ISO scale 0 (yen, won) are
  refused by construction.
- Everything in the previous handoff's §5 is unchanged: `_add_lossy` is still a write-only
  channel, the `++` operator export is still unsolved, the CLP(B) `id(Var)` registry is still
  a hazard with no reproduction.

## 5. The corpus migration — one input it did not have

Base-currency decimals were **already exact**: `-constant_number_units(x, 1550.00, dollar)`
stores `Decimal('1550.0')`, and the precision check rejects sub-scale digits. So minor units
buy fidelity to what the SOURCE said — not safety the base form lacked. That matters for the
re-costing, which the previous handoff left open in both directions.

What they DO buy is the option of not renaming: a parameter can keep the name it has while the
declaration carries the currency and the scale, which may make most of the 71-name cross-lane
rename unnecessary and gives the "name says `_cents`, declaration doesn't" gate a mechanism.
**All four lanes have been told**; corpus-lane owns the decision.

## 6. Method notes worth keeping

- The operator answered two of three questions with **questions back**, one of which
  ("why can't we use the base currency in constants?") challenged the premise of the whole
  task. Measuring before answering is what turned up both the float-leak defect and the fact
  that §4b's design was unnecessary. Answer a challenge with a measurement, not a defence.
- The failure-set diff cannot see a COUNT change inside a test that was already failing. The
  doc-block test asserts on a count of violations; it needed its own before/after, plus a
  positive control that the scanner actually reaches the file I edited. Three of the 38 would
  have been mine and the set diff would still have said "0 new".
