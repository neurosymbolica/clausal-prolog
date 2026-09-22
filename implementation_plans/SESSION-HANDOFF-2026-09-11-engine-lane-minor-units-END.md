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
  (`<downstream-domain>` computes in bps throughout, with `leverage_ratio_bps/2` EXPORTED).
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

---

# Continued: four more commits, all from review

`12f5e42c` above was written after ONE commit. Four more landed the same session, every one
of them from a peer finding a defect in the previous one. The final state:

    6e18af69  cent, an ordinary scaled unit
    12f5e42c  (this handoff, written too early)
    c045d5d6  currency-literal warning + BOTH exporter refusals
    301ad6a7  minor units for AUD, THB, GBP
    6bc72731  same-named dimensions say which is which

    clone main      6bc72731
    canonical       96cc8df6   STILL UNTOUCHED — the operator's hold stands
    engine suite    144 failed / 15903 passed / 1 error, name set identical to baseline
    doc blocks      38, unchanged

## What the reviews found, in order

1. **`-constant_number_units` is not the only shape.** `pay(155000(cent))` reaches
   `_try_quantity`, not `_collect_constant`, and still emitted `155000`. The refusal covered
   half the surface and the missed half looked identical from outside.
2. **The two refusals need OPPOSITE polarity.** Reusing the declaration rule (refuse unless
   known base) on the inline path broke 15 tests — the TitleCase `Metre` alias and four
   `iso_type_checking` roundtrips. Inline refuses only what is known SCALED. Documented in
   both the todo and the docs because they look like copies.
3. **A guard placed before identification refuses everything.** `_try_quantity` is reached by
   every one-argument call and returns None for non-quantities; my check sat above that and
   refused `implements(k1)`.
4. **The docs example demonstrated the SAFE case.** Both values in it round-trip exactly; the
   "off by two cents" came from float ARITHMETIC inside my own probe being reported as a loss
   from a float LITERAL. And the prose said "essentially always" where my own measurement
   said 83%.
5. **EUR/USD did not cover the corpus.** 139 identifiers across 27 domains, 6 of which used a
   currency with no minor unit — so the identifier most needing a checkable unit
   (`target_au_turnover_cents`) was the one that could not have one.
6. **`dollar vs dollar`.** The mismatch message was unusable on exactly the case the widening
   exists to catch, for 25 shared currency names.
7. **The fix for 6 over-applied one level down**, decorating a `second` that was identical on
   both sides, with a memory address that changed every run.

## The one lesson that covers all seven

**An instrument must be able to produce the negative result, over a space large enough to
contain the defect.**

Three of today's failures were instruments that could only say yes: a verifier that caught
its own `TypeError` in the handler for the refusal it was testing and printed REFUSED; a test
that asserted a warning APPEARS, which a safe value in the hazard band also satisfies; a test
that asserted `UnitsMismatch` is raised, which cannot tell a message that explains from one
that does not. In the last two the assertion was already right and was being evaluated over
too small a space — the fixes were to change what the test OBSERVES (render differently;
subprocess into fresh interpreters) rather than what it asserts.

Companion, from the harness lane: **name the instrument, not the commit.** "Re-measure on
the new sha" collects the cheapest thing resembling measurement, which is a load census, and
a load census cannot see a compiler change.

And, from corpus-lane: **when a probe computes the value it is meant to be testing, it can
only confirm itself.**

## Still open

- **Option 2 for the exporter** — fold to the base magnitude. Both refusals are a holding
  position and lift together. It is the prerequisite for migrating any domain that is also
  on the ISO publish list.
- **Ratio units** (`basis_points`, `percent`) — designed, unbuilt, corpus-lane's live
  blocker. Verify the dimensionless path's exactness first; the guarantee measured here comes
  from the CURRENCY coercion, and a dimensionless Quantity may not have it.
- **Mike's calls, unchanged**: base-vs-minor for the migration, dropping the 71-name rename,
  the `.seam` remainder, iso-export-lane's `remedies_ineffectiveness` roster gap.

---

# Continued again: the naming rule, `4a362c88`

Asked "how do we reliably tell euro cents from dollar cents in a calculation?", the answer
turned out to be **you cannot get it wrong in a calculation, and you could get it wrong in
the source** — which produced one more commit.

**In calculations there is nothing to get wrong.** A cent does not survive to the
calculation: it converts where it is written, and what remains is a currency-dimensioned
amount. `euro vs dollar` is the existing dimension guard, and same-named currencies now read
`dollar (AUD) vs dollar (USD)`.

**In the source, two measured holes**, both closed by the operator's rule that a shared
subunit word carries its currency in its name (`eur_cent`, `usd_cent`, `aud_cent`; `penny`
and `satang` unique, so bare):

1. `-import_from` binds a duplicate name **silently, last-one-wins, no warning**. Two
   jurisdictions' `cent` collided and the second won. A rulebase computing throughout in what
   it believed were euro cents would hold dollars and never raise, because nothing would ever
   meet a euro amount to mismatch against.
2. `constant_number_units/3` reports the declared SPELLING, so both sides answered `cent` —
   and the qualified `united_states.cent`, the spelling that would have disambiguated,
   registers **nothing at all** (`_units_ast_to_term` returns None for an `Attribute`, so the
   declaration is skipped).

**Still open, and they are the residue of those two:**

- Hole 1 remains for **currency** names: 25 are shared (dollar ×22, franc ×17, pound ×12,
  dinar ×10), and `-import_from(bahrain,[dinar])` then `-import_from(kuwait,[dinar])` is
  still silent last-one-wins. The naming rule fixed minor units by construction; currencies
  were never in scope for it.
- Hole 2 is filed: `todo/qualified-unit-declarations-have-no-slash-3-answer-2026-09-11.md`,
  with the term-shape question (`('.', ('bahrain',), ('dinar',))` vs one flat atom) as the
  only real decision.

**Method note worth keeping.** The operator's answer was better than both fixes I offered,
and the reason generalises: my options were *guards* on a hazard, theirs *removed the
condition that creates it*. A name that cannot collide needs no collision check.

---

# Continued: major currencies, `9fd8e7f9`

The `bahrain.dinar` vs `kuwait.dinar` residue recorded above as "still open" is now closed —
the operator applied the minor-unit rule to major currencies.

    a word naming exactly ONE CURRENT currency is kept       134 currencies
    otherwise the currency is bound by its lowercase code    120 currencies

    euro, yen, baht, sterling, lira, mark, escudo, koruna, guilder, colon   kept
    dollar -> usd/aud/cad/...   dinar -> bhd/kwd/jod/...   franc, pound,
    peso, rupee, shilling, rial, ruble, won, krone, krona, ...              coded

**No identifier is bound in two jurisdictions any more**, which is the property the whole
thing exists for: the silent last-one-wins import collision cannot be written.

Keeping the word for a sole current user is the generator's own within-jurisdiction
convention extended across them, and it pays twice: a legal text says "lira", not "TRY", and
**`try` is a Python keyword** that could never be an identifier. TRY is the only current lira,
so the rule needs no carve-out. Verified none of the 254 bindings is a keyword, shadows a
builtin, or collides with a currency word, a unit name or a minor-unit name.

**The display word is unchanged.** `_name` is still "dollar", so `money_format` gives
"500.00 dollar" and a mismatch reads `dollar (AUD) vs dollar (USD)`. The disambiguation
landed earlier today is what keeps those messages legible now that identifiers and displayed
words differ. This changes what a rulebase WRITES, not what the system PRINTS.

## Two traps this turned up, both worth the next reader's attention

**A set keyed on a name the checked thing no longer uses.** `_base_unit_names` in the
exporter was built from `r["name"]`, the word. After the rename it contained "dollar", which
nothing can write, and lacked "usd", which everything writes — so this morning's scaled-unit
refusal would have fired on `500(usd)`, the most ordinary declaration there is. The check
kept working and checked the wrong population. Same shape as the inline-quantity hole.

**A grep over a currency word is almost all false positives.** The first blast-radius
measurement said 1788 references across 318 files. `mark` accounted for 1601 of them —
`trail.mark()`. `won` was prose. Constrained to real usage shapes (import lists, `N(unit)`
annotations, `from …countries.X import`, `<jurisdiction>.<word>`) the true figure was ~74 in
8 files. A word that is also an ordinary English word or a method name cannot be counted by
grepping for it.

## Still open after this

- The qualified-unit `/3` gap is unchanged and still filed:
  `todo/qualified-unit-declarations-have-no-slash-3-answer-2026-09-11.md`. Its "related but
  not the same" section about import shadowing is now **closed for currencies**, since no
  identifier is bound twice — the todo needs that paragraph updated when someone takes it.
- The corpus writes `dollar`; those sites need `usd` or `aud`. corpus-lane and
  iso-export-lane have both been told, with the display-word caveat flagged as something for
  them to confirm rather than take on my word.

---

# Continued: `-constant_number_currency`, `303c2934` + `52a24676`

    -constant_number_currency(sga_monthly, 155000, usd_cent)

A money-specific declaration, named for its claim and enforcing it as
`-constant_number_units` is named for "only numbers carry units".

**The gap it closes is narrower than it looks, and two of the three obvious failures were
already covered.** Measured before building:

    -constant_number_units(fee, 5000, dollar)   NameError            already caught
    -constant_number_units(fee, 5000, usdd)     NameError            already caught
    -constant_number_units(fee, 5000, metre)    Quantity(5000, metre)   SILENT

A mistyped or unbound currency cannot be written, because a currency identifier has to be
BOUND — a property the ISO-code rename strengthened. What was silent is a unit that loads
fine and is not money: asking for money and getting an int-valued length.

**Money is a SHAPE, not a type: one currency at exponent one.** The first version required
the argument to BE a currency and so refused `usd_cent`. That was type-purity about the
argument, where the property asserted is about the constant — and it split the two safety
properties so that an author could have the currency gate or the minor-unit scale but never
both, with all 139 migration identifiers falling on the ungated side.

## Method notes from this stretch

- **`kilometre` is the discriminating test row.** A Quantity over a single non-currency base
  at exponent one — structurally identical to `usd_cent` except `is_currency`. Every other
  refusal fails for a shape reason and would survive a checker that dropped the currency
  test. Mutation-verified: dropping just that clause fails only this row.
- **Mutation-test a new gate.** Two of these tests originally passed while the directive did
  not exist, matching the unknown-directive `SyntaxError` through a loose
  `pytest.raises(Exception)`. Neutering the check must fail exactly the refusal tests.
- **The doc-block COUNT caught a regression the name-set diff could not.** The new section
  showed a refusal in a ```clausal block, which cannot compile by design: 38 -> 39 while the
  failure name set stayed at 144, because that test was already failing. Retyped as ```text.
- **A census of NAMES is never evidence about BINDINGS** (corpus-lane). Three of my errors
  today are this one shape: an AU corpus claim inferred from a `_cents` name census when no
  AU domain imports a currency at all; a blast radius of 1788 that was 74 once `trail.mark()`
  was excluded; and `_base_unit_names` keyed on a word nothing could write after the rename.

## Verification of the whole series, by iso-export-lane

Zero bytes across 1560 exported files, canonical `96cc8df6` against clone `303c2934`, with
**both engine trees hashed before and after the run** rather than pinned by sha alone — a
sha names what HEAD said, not what was read, and the clone had 42 modified files during an
earlier comparison. Their caveat, their fix.

## State

    clone main    52a24676
    canonical     96cc8df6      untouched all session; the operator's hold stands
    engine suite  144 failed / 15928 passed / 1 error, name set identical to baseline
    doc blocks    38

Corpus exposure on promotion is six sites in two US files (`dollar` -> `usd`), failing loud
with an `ImportError` naming both the name and the module. No AU site exists today.

---

# Continued: the scale-in-a-name lint, `d728d2a9`

Operator, 2026-09-11: *"bare integers for currencies is begging for trouble."* Measured, and
the second case is the argument — not a wrong number, a **reversed answer**:

    two 'cents' integers, different currencies
      bare ints :  5000000 + 155000  ->  5155000    AUD and USD, silently summed
      as money  :  UnitsMismatch: dollar (AUD) vs dollar (USD)

    a cents value against a dollars threshold
      bare ints :  155000 > 1550     ->  True       "exceeds the threshold"
      as money  :  1550.00 > 1550    ->  False      it does not

`ClausalScaleInNameWarning` fires when a name ending in a scale word carries a bare numeric
literal — once per (file, identifier), on two shapes: a FACT argument, and a
`-constant_value` declared without a unit.

**Reading facts is the point.** Declaring constants fixes constants; it does nothing for
`minimum_leverage_bps(300)`, and `leverage_ratio.clausal:111` is exactly that — the deciding
literal is bare while the declared fact is the copy that cannot change an answer. A
constants-only instrument would report that domain migrated while the number that decides
went untouched.

**It empties itself.** The discriminator is a bare numeric LITERAL, so a converted site is
`155000 (usd_cent)`, a Call, and goes quiet. The warning count falling is a better progress
measure for the migration than counting edited files.

Money suffixes are DERIVED from `MINOR_UNIT_WORDS` (so a new minor unit extends the lint with
no second edit); only the ratio words are written out, and that list shrinks to the
derivation when ratios become units.

**Coupling worth knowing:** it piggybacks on `_lint_titlecase`'s nineteen call sites rather
than adding its own — those are exactly the points where the transformer has recognised a
CLAUSAL subtree. Removing a `_lint_titlecase` call would silently narrow this lint too.
Documented at both ends.

Noise floor: **two** warnings across the full engine suite, both true positives by the rule
(`reaches_percent(X, 10000, 50, V)`, `threshold_bps`).

## State at end of this stretch

    clone main    d728d2a9
    canonical     96cc8df6      untouched all session
    engine suite  144 failed / 15936 passed / 1 error, name set identical to baseline
    doc blocks    38

Asked of corpus-lane, for when it reaches canonical and not before: a load census counting
warnings per domain. That is the migration's real size in the shape now ruled for, and being
a count of BINDINGS rather than names it will differ from the 139 in both directions.

## CORRECTION to the section above: the lint misses the site it was motivated by

Measured by corpus-lane and reproduced here. On `<downstream-domain>` the lint warns at `:93`,
the scale-named fact that no longer decides anything, and is **silent at `:111`**, which is
`check_ratio_gte(P, tier1, total, 300, ...)` — the 3% floor that does decide. The
discriminator is the FUNCTOR'S name, so a bare literal in an argument of a functor claiming
no scale is invisible. A control in the same argument slot with a scale-named functor does
warn, so body position is reached and the name really is the test.

**So the paragraph above that cites `leverage_ratio.clausal:111` as the motivation is wrong,
and it is wrong in the way that matters**: converting `:93` silences the domain while the
deciding literal is untouched. The self-emptying property — designed as the progress signal —
would empty on a domain whose defect is untouched. corpus-lane's phrase for it is the right
one: **the right verdict about the wrong site**, the same failure the constants-only
instrument had, moved one step later.

How I got it wrong is worth more than the fix: I inferred the SHAPE of `:111` from a
description of its ROLE ("the floor is the bare literal 300 at :111") and assumed a
scale-named fact. Same family as "a census of names is never evidence about bindings" —
a description of what a site DOES is not evidence about what it LOOKS like.

Pinned by `test_the_lint_is_BLIND_to_a_literal_under_an_unscaled_functor` and its
position control, so the limit is a test rather than a footnote. Docs carry a
"What it cannot see, and why that matters" section saying plainly that an emptied
list is not a completeness claim.

**The harder half, unbuilt and worth designing when ratios land** (corpus-lane's analysis,
which I agree with): a literal under an unscaled functor has nothing in the source to key on.
The promising signal is the CALLEE'S PARAMETER — if `check_ratio_gte/6`'s fourth parameter
were declared to take a ratio, the literal would be checkable at the call site. A same-value
or same-file heuristic is not promising: it learns the cases it was built from. The
parameter-side version is also the one that would make the migration mean something, because
it checks the site that decides.

**corpus-lane's static prediction, for checking the load census against when this lands:**
76 (file, identifier) pairs across 23 domains, 1 under `eval/` — 15 `<downstream-domain>`, 12 `th/visa`,
10 `<downstream-domain>`, 5 each `<downstream-domain>` and
`<downstream-domain>`, 3 each for five more. A materially different load
census means one of the two instruments is wrong, and the difference is the finding.

---

# PROMOTED: canonical is `3b0e3547`

    canonical   96cc8df6 -> 3b0e3547    21 commits, clean ff, NO C changes
    clone       3b0e3547                 identical
    box         NOT landed — separate, needs the ssh alias

Verified by **observation in the canonical tree**, engine path asserted by realpath first:
`usd.iso_code == "USD"`, `bhd.iso_code == "BHD"`, `155000 * usd_cent == 1550.00`,
`CURRENCY_BINDINGS["USD"] == "usd"`, and a bare `dollar` raising `ImportError`. A ref and an
exit code say a merge happened; they do not say the tree behaves.

**The operator's go was taken directly, not from the relay.** corpus-lane reported the ruling
accurately, and I still asked him before touching canonical: promoting rewrites source under
every lane reading the tree, and a ruling relayed through a third party is not the word of the
operator to the lane that will execute it.

**What crossed is the approved sha PLUS ONE commit.** He approved `c06d5426`; `3b0e3547` is
that plus `fix(exporter): the scaled-unit refusal names the directive that was WRITTEN`. I
held the promotion to include it rather than land it under corpus-lane afterwards, and said so
to him and to both lanes. "Approved sha + 1" must never be silent, even when the commit is a
string.

## What landed, in one list

    cent + minor units as ordinary scaled units       6e18af69 · 301ad6a7 · 4a362c88
    ISO-code naming for shared currency words         9fd8e7f9
    the currency-literal warning + exporter refusals  c045d5d6
    same-named dimensions say which is which          6bc72731
    -constant_number_currency + the money SHAPE gate  303c2934 · 52a24676
    the scale-in-a-name lint (+ its blind spot)       d728d2a9 · de1e2e4b
    compatible_units/2                                25f06542
    currency_code/2 relational; accessors raise       7a851c7c
    number/1 accepts a quantity; sum_list sums money  06290b23
    reflected operands raise symmetrically            c06d5426
    the refusal names the written directive           3b0e3547

## Open after the promotion

- **BUG #2, the module/profile-key shadow.** `-import_from(currency, …)` binds a Python
  MODULE; a bare profile key is the interned atom `('currency',)`; they are different kinds of
  thing competing for one namespace slot, which is why the shadow is SILENT rather than a
  redefinition error. Reproduced at engine level by corpus-lane, and the first thing anyone
  writing the <downstream-domain> migration will hit. **The resolution-order ruling is open and is this
  lane's.** Deliberately not smuggled into a currency landing.
- **Option 2 for the exporter** — fold to the BASE magnitude. Now load-bearing, not optional:
  the operator ruled "follow statutes, it's daft but that's law", so minor units go wherever
  the statutory verbatim states the amount that way, and those are exactly the declarations the
  exporter refuses. NOTE for whoever builds it: the export stays LOSSY by the 2026-09-08
  ruling — ISO Prolog cannot carry a quantity — so option 2 fixes only the MAGNITUDE
  (`pay(1550)` rather than `pay(155000)`), not the unit.
- **Ratio units** (`basis_points`, `percent`) — designed, unbuilt, still corpus-lane's blocker.
- **<downstream-domain>** proceeds as a separate migration. Its BR-CO tolerance is a READ-THE-STANDARD
  question, ruled: `within_one`'s "1" is one of WHAT? Comparing a base-unit `.value` against a
  bare `1` makes it 1 euro rather than 1 cent — a 100x widening with a green suite, measured.
- **`Undefined` -> `undefined`**: corpus-side uses the alias; the engine rename is NOT bundled
  here. A separate surface change with its own blast radius does not belong in a landing
  measured for something else.
- Box is not landed.

## The three claims for this landing

| axis | who | result |
| --- | --- | --- |
| engine suite | me, on the promoted tree | 144 failed / 15966 passed / 1 error — failure NAME SET identical to the `946d7296` baseline |
| export bytes | iso-export-lane, canonical `3b0e3547` | 0 across 1560 files, RAW **and** normalised, both engine trees content-pinned, corpus `b6f2c367` |
| domain answers | the harness lane, `26c1fdc0` | 82 rows, 82 unchanged, 0 moved, 0 no-score, 0 torn, one fingerprint — **after it caught a regression at `7449448b`** |

**This landing is the cleanest demonstration yet that none of the three implies another.** The
engine suite was green and the export roster was zero bytes across 1560 files while a domain
was raising `type_error(number, Fraction(...))` at solve time. Only the answer diff could see
it. `sum_list/2`'s new pre-validation used `isinstance(v, (int, float))`, which excludes
`Fraction` and `Decimal` — and `Decimal` is the magnitude of every currency amount, so the
worse half was invisible to all three instruments and came out of DIAGNOSING the lesser one.
Fixed at `26c1fdc0` with `numbers.Number`; the broken row was re-measured alone and then again
inside the sweep, agreeing both times.

The domain axis has now run across **103 commits from `820dc66f`** with no moved answer, and
has fired three times where the other two axes could not. That is the argument for keeping it
in the set rather than treating it as confirmation.

**A zero is not always the same result, and the difference is worth naming** (iso-export-lane).
The `-constant_number_currency` zero was cheap: nothing in the corpus writes that directive,
so nothing exercised the new code. The `sum_list/2` zero is expensive: seeding from the first
element is behavioural and sits on the path of every aggregate in every domain, so the changed
code RAN 1560 times and agreed. "The changed code ran and produced the same bytes" and
"nothing reaches the changed code" are different claims and only the first is worth much.

They also ran a NORMALISED arm beside the raw one, which excludes two changes cancelling
within one file — cheap once it exists, and it closes the reading a sceptic raises next.

### Why the domain axis stays in the set (the harness lane, recorded at their request)

It has now been measured across **101 engine commits** from `820dc66f` without a single moved
answer — and **twice in that span the sweep was the thing that found a defect the other two
axes could not see.** That is the argument for keeping it rather than treating it as
confirmation: an instrument that has never fired is not thereby useless, provided you can say
when it DID fire. Export bytes are not answers; a green engine suite says the engine behaves,
not that the corpus still answers the same.

Three candidate movers were named before the run rather than after, which is the half that
makes a zero informative: `sum_list/2` (behavioural, every aggregate — the one to bet against
a null prediction on), `number/1` accepting a `Quantity` (changes a branch only where a guard
meets data that could carry one), and the currency renames (should fail LOUD; their instrument
reports a load failure as a no-score row carrying the exception type, so that case is visible
rather than folded into a score).

---

# BUG #2 — CLOSED, on canonical at `64f04898`

    -import_from(currency, [currency_code])
    inv({currency: eur}),
    look(C) <- (inv(I), get(I, currency, C))

    before  []        after  [('eur',)]

`_process_imports` bound the module object under its user-facing name for dotted-name
resolution. That name holds a Python MODULE; a bare profile key is the interned atom
`('currency',)`. Two different KINDS of thing in one namespace slot, which is why the
collision was SILENT rather than a redefinition error — the lookup found nothing and the rule
answered `unknown([key])`. The corpus held it off by emitting imports in a fixed ORDER, with a
regression test pinning the order.

**Only a SINGLE-SEGMENT name can collide** — the only form that is also a writable Clausal
identifier. A dotted path binds under `py.units`, which nothing can write. Kept for dotted,
dropped for single-segment.

Measured both ways rather than argued: **removing the binding entirely fails 5 tests** in
imported-atom/functor resolution (it is load-bearing), **restricting it to dotted paths fails
nothing** — plus the positive control, because a green suite says nothing broke, not that the
bug is fixed.

Each directive now does what its name says: `-import_from` binds the names it lists,
`-import_module` binds the module. The operator ruled the one affected shape (`uuid.X` after
importing only names) can be renamed; nothing depends on it.

## Three claims, on the tree that carries them

| axis | who | result |
| --- | --- | --- |
| engine suite | me | 144 failed / 15973 passed / 1 error — name set identical to the `946d7296` baseline |
| export bytes | iso-export-lane | 0 across 1560 files, raw and normalised, both trees content-pinned |
| domain answers | the harness lane | 82 unchanged, 0 moved, zero torn — `64f04898/so1789092742`, 106 commits from `820dc66f` |

**Measured on BOTH execution paths.** The clone sweep at `6d609eb1` ran the interpreted
trampoline (the clone has 12 loadable extensions to canonical's 13); this one ran the
compiled path. Same 82 answers, no row moved on either.

`<downstream-domain>` was run ALONE first — 59/59 — because corpus-lane's census makes it the
only surviving module-name/profile-key pair in the corpus, so it is the one domain where the
change has anything to act on. Retiring the shape with a named mechanism before the broad run
means a later move would have moved WITHOUT one, which changes how hard to chase it. Worth
doing whenever a census has already named the candidate.

## The week's most reusable finding, and it is about reporting

**The reportable unit is not the number — it is the number plus what the instrument could not
see.** This landing's gap (the fix measured only on the interpreted path) was findable ONLY
because the harness lane volunteered that the clone lacked the compiled trampoline. Reported
as "82 unchanged, clean", it would have been a null that was silent on the axis that mattered,
and nobody would have known to look.

Three instances from three lanes in one week makes it a practice rather than an anecdote:
that caveat; the fingerprint runner that hardcoded the default engine path while its
measurement took one as an argument; and "clone `9fd8e7f9` is a weaker pin than it looks,
because the arm was a DIRECTORY with 42 modified files". Caveats are not politeness, they are
load-bearing — a reader who knows something you do not can only act on a limitation if you
state it.

The question that finds this class: **has the CHANGE been measured, or the INTERACTION?** A
null covering the change says nothing about the pairing, and where two implementations share
one contract — a C wrapper and a Python twin — the pairing is where a difference hides
without either side being wrong.

## Still open

- **Option 2 for the exporter** — fold to the BASE magnitude. Load-bearing since the "follow
  statutes" ruling. Export stays LOSSY: it fixes the magnitude, not the unit.
- **Ratio units** (`basis_points`, `percent`) — designed, unbuilt, corpus-lane's blocker.
- **<downstream-domain>** as a separate migration; its BR-CO tolerance is a read-the-standard question.
- **CLP units via a side channel** — `todo/clp-units-side-channel-2026-09-12.md`, earmarked
  for a fable agent. NOTE recorded there and in its commit: the "extract the rule from a
  Prolog definition" half has NO basis in this repo, and the only real `library(clpfd)` source
  on the machine is SICStus's — wrong semantics for us, and commercially licensed.
- **corpus-lane** retires the import-order mitigation and RE-POINTS its regression test at the
  new guarantee rather than deleting it.
- **Box** is the only tree still on the old vocabulary.

---

# 2026-09-12: tables, the re-readable renderer, and BUG #2 — all on canonical `a25bc430`

    -constants_number_currency(snap_max/2, [(1, 29200), (2, 53600)], usd_cent, money_at(2))
    -constants_number_units(span/2, [(short, 5)], metre, number_at(2))

The declaration **defines the predicate the rulebase already calls**, so 217 indexed money
rows across ~8 domains migrate with ZERO call-site churn. Nothing is reached through
`constant/1`: that substitutes a single value at COMPILE time, a table is a lookup by key at
RUNTIME. Implemented as a source-level expansion in a `visit_Module` prepass so the generated
facts are the same kind of predicate as the fact lines they replace.

`str(Quantity)` now emits text that parses back to an equal value — `292.00 (usd)`,
`3 (metre / second)`, `4 (dimensionless)`, `10 (usd) / 3`. What it produced before resembled
source and was not: bare juxtaposition is a SyntaxError, `·` and `^` are not syntax at all,
and `dollar` has not resolved since the ISO-code rename. ONE renderer, so mismatches read
`aud vs usd` — unambiguous by construction, retiring the collision-qualifier for currencies.

BUG #2: `-import_from` binds the names it lists, not the module.

## Three claims

| axis | result |
| --- | --- |
| engine suite | 144 failed / 16259 passed — name set identical to the `946d7296` baseline |
| export bytes | 0 across 1560 files (measured at `303c2934`; no exporter change since) |
| domain answers | 82 unchanged, 0 moved, zero torn — `a25bc430/so1789092742`, **147 commits from `820dc66f`** |

The answer diff was ordered: a census named the four bodies carrying a renamed unit word in a
string literal (`<downstream-domain>`, `<downstream-domain>`, `<downstream-domain>`, `<downstream-domain>`),
those four ran ALONE first and were at their recorded numbers, then the full 82.

## Two rules this day produced, both about instruments rather than code

**A targeted run and a broad run answer different questions, and the targeted one is only
worth doing when its census limits are stated with it.** Otherwise "the four at-risk domains
are clean" reads as "the at-risk domains are clean". Their blind spots are complementary: a
census names candidates in advance and cannot see data a body READS; a sweep sees everything
and names nothing in advance. Neither is a weaker version of the other.

**A property test is only as complete as its SHAPE LIST, and the shape list ages.** The
round-trip property was called total over eight shapes. It was total over the shapes CHOSEN,
selected before another lane made a currency Quantity hold an exact `Fraction` — and the
missing shape was the worst kind: `'10/3 (usd)'` parses as `10 / 3(usd)`, same magnitude,
**inverted dimension**. Looks right, is not.

**The failure mode is not that the instrument was wrong; it is that it stayed the same while
the world it measures moved** (the harness lane's formulation). That is a maintenance
obligation distinct from correctness, and nothing was watching it.

### The shape for it: derive the instrument's coverage from the AUTHORITY

`test_the_shape_list_covers_every_magnitude_type_a_quantity_holds` reads the magnitude types
out of `_to_decimal` and fails if one has no round-trip case. Adding a type to the engine now
fails a test until a shape covers it. The scale lint already had this shape — its suffixes
come from `MINOR_UNIT_WORDS`, so a new minor unit extends it with no second edit.

Generalised: **wherever an instrument enumerates, enumerate FROM the thing that defines the
set, not from a list written beside it.** A hand list is correct on the day it is written and
has no way to notice it has stopped being.

## Open

- Option 2 for the exporter (fold to the BASE magnitude) — load-bearing since "follow
  statutes"; export stays lossy, it fixes the magnitude not the unit.
- Ratio units (`basis_points`, `percent`) — designed, unbuilt.
- <downstream-domain> as a separate migration; its BR-CO tolerance is a READ-THE-STANDARD question.
- The decimal-literal gap: source `292.00` is a float and loses its trailing zero before any
  Quantity exists. Minor units preserve it exactly, which is one more argument for declaring
  in cents where the statute states cents.
- corpus-lane migrates `<downstream-domain>` (30 rows) and `<downstream-domain>` (81), and retires the
  import-order mitigation — RE-POINTING its regression test at the new guarantee, not
  deleting it.
- **Box is the only tree still on the old vocabulary.**

---

# Notes to survive this session's context (2026-09-12)

## 1. The scale lint's warning count is wrong in BOTH directions

It **under-reports**: a bare literal under a functor claiming no scale is invisible, and that
is where a deciding value can sit — `leverage_ratio.clausal:111` is a bare `300` in
`check_ratio_gte/6`, while the scale-named fact at `:93` no longer decides anything. So a
domain can reach zero warnings with its deciding literal untouched.

It **over-reported** on migrated tables until `e7123f2e`, which exempts any row carrying a
unit — as a property of the ROW, not of the directive, so a hand-written fact with a united
column is silent too.

**A falling count is evidence of progress, not a measure of it, and zero is not a
certificate.** Stated in `docs/currency.md`.

## 2. `X == <quantity>` collapses a dimensionless Quantity to a bare int

The CLP path, not the parse. `parse(str(q))` is faithful and returns a `Quantity`; binding
through `==` returns `4`. Recorded so the next person who writes a round-trip check, gets `4`
and suspects the renderer does not spend an afternoon establishing which path is right — the
two differ and the parse is the correct one.

## 3. A property test is only as complete as its SHAPE LIST, and the shape list ages

The most reusable thing this session produced, and it generalises well past units.

The `str(Quantity)` round-trip property was called total over eight shapes. It was total over
the shapes CHOSEN, selected before another lane made a currency Quantity hold an exact
`Fraction`. The missing shape was the worst kind: `'10/3 (usd)'` parses as `10 / 3(usd)` —
same magnitude, **INVERTED dimension**, dollars-per-unit rather than dollars. It looked right
and survived a passing suite.

**The failure mode is not that the instrument was wrong; it is that it stayed the same while
the world it measures moved** (the harness lane). That is a maintenance obligation distinct
from correctness, and nothing watches it by default.

Two shapes for it, and the second bounds the first:

- **Derive the instrument's enumeration from the AUTHORITY**, not a list beside it.
  `test_the_shape_list_covers_every_magnitude_type_a_quantity_holds` reads the types out of
  `_to_decimal` and fails if one has no case.
- **But derive only for CONFORMANCE questions.** A RESIDUE question — "does this contain
  traces of the old world" — needs a set the authority has already FORGOTTEN, and the
  forgetting is the event that makes the question necessary. After the ISO rename, `dollar`
  was in no table; a census deriving from the authority would have reported a confident zero
  on the four corpus bodies carrying it. So: **declared union**, derived plus hand-maintained,
  each marked, each with a control — empty-derived means blind on the vocabulary, empty-hand
  means blind on residue, and OVERLAP means the authority has taken a word back and the hand
  list should shrink.
- And: a complete word set is a useless FILTER (486 words flagged 81 of 82 bodies).
  **Enumerate from the authority; constrain by the SHAPE.**

## 4. Telling another lane a change is safe

**Name the FILE, not the nature of the change.** "Docs, one test and a suffix set" was true of
the content and silent about the location — and that suffix set is in `term_rewriting.py`, on
the load path for all 82 harness bodies. A reader's instrument reacts to location; only the
owner knows the content. The less informative-sounding sentence is the more useful one.

## Open for whoever picks this lane up

- **Mike's Q6, unanswered**: should a `[date, value, cite]` row carry a currency-valued
  magnitude? A units question, not a constants one.
- Option 2 for the exporter (fold to the BASE magnitude) — load-bearing since "follow
  statutes"; export stays lossy, it fixes the magnitude not the unit.
- Ratio units (`basis_points`, `percent`) — designed, unbuilt; when they land, the scale
  lint's hand-maintained half must shrink and its overlap control will say so.
- <downstream-domain> as a separate migration; its BR-CO tolerance is a READ-THE-STANDARD question.
- The decimal-literal gap: source `292.00` is a float and loses its trailing zero before any
  Quantity exists. Minor units preserve it exactly.
- **Box is the only tree still on the old vocabulary.**
- corpus-lane's side needs no reconstruction: `_tools/MIGRATION-money-constants.md`.

## ADDENDUM: the scale lint over-reports on a table's CALL SITES

Found by corpus-lane 2026-09-12, after `e7123f2e`. The row-level exemption works — a migrated
DECLARATION is silent. What fires is the call site:

    use(X) <- ( t_usd_cents(1, X) )          warns   <- `1` is the INDEX KEY, not money
    use(X) <- ( t_usd_cents(K, X), K == 1 )  silent

The functor claims a scale and carries a bare literal, and **`money_at(N)` lives on the
DECLARATION — a call site does not carry it**, so the discriminator cannot tell a key column
from a money column there.

**It moves the count the WRONG WAY on migration.** `<downstream-domain>`'s tables are read with literal
keys throughout (household size 1..8), so converting its 30 rows silences 30 declaration
warnings and lights up every call site naming a size — each a false positive telling an author
to declare a household size as money.

**The fix is available in principle and was NOT built**, deliberately: exempt a bare literal
in a NON-money column of a predicate declared by a table directive. The expansion knows the
predicate name, its arity and `money_at(N)` at transform time, so recording that on the
transformer and consulting it in `_lint_scale_in_name` is the shape. It was left because the
lint is on the load path for all 82 harness bodies and this session had no margin left to
verify a change there — the two regressions today were both in code that looked safe.

So the count now has **three known distortions**, all documented in `docs/currency.md`:
blind to a deciding literal under an unscaled functor; over-reporting on table call sites;
and formerly over-reporting on migrated rows (fixed). The wording already in the docs covers
it — a falling count is evidence of progress rather than a measure of it, and zero is not a
certificate — which is a good sign for that wording rather than a reason to stop counting.
