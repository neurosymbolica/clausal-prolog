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

Companion, from harness-batch-lane: **name the instrument, not the commit.** "Re-measure on
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

Measured by corpus-lane and reproduced here. On `crr_leverage_ratio` the lint warns at `:93`,
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
76 (file, identifier) pairs across 23 domains, 1 under `eval/` — 15 `us/snap`, 12 `th/visa`,
10 `au/merger_clearance`, 5 each `au/corps_act_disclosure` and
`eu/procurement/selection_criteria/tests`, 3 each for five more. A materially different load
census means one of the two instruments is wrong, and the difference is the finding.
