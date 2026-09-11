# Engine lane handoff — 2026-09-11 END

**You are the engine lane AND the coordinator.** Read this file first. The 2026-09-10 END
handoff is now history except for its §5a/§5c/§5e lessons, which still hold.

## 1. State of the world

    clone / canonical / box main   946d7296   (rev-parse x2 + ls-remote, verified after each landing)

Engine suite in the clone at that tip: **144 failed / 15862 passed / 1 error**, all
environmental. That failure NAME SET is identical to the one measured at `9a719536` at the
START of the day — every landing below moved it by zero. The extraction is at
`/home/node/.claude/jobs/af5b4bbe/tmp/tip.fail` (144 names); regenerate rather than trust it.

**Three claims, separately, none implying another** (the standing rule):

| axis | who | measured on | result |
| --- | --- | --- | --- |
| engine suite | me | 946d7296 | 0 new failures vs the 9a719536 baseline |
| corpus loads | corpus-lane | 946d7296 predecessors | 71 asserted clean / 0 defects / 7 not checked, cold AND warm |
| batch bodies | harness-batch-lane | not re-run today | — ask before relying on it |

## 2. What landed today, in order

    375acf8f..e030988b   constants respelled: lowercase names, `_CONSTANT_` retired,
                         the classifier carve-out gone from all five copies
    7e825cdf             Trail_dealloc untracks before clearing weakrefs (SEGFAULT fix)
    25fe9dce             c_make_node owns its borrowed references
    671a697e             exporter folds a declared constant to its literal
    c4c7d6c9             constant_number_units/3 + the directive renamed to match
    6e00bc75             that predicate reports the DECLARED pair
    8b23615f             CLAUSAL_BYTECODE_TAG 12 -> 13
    a9989b7a             the tag is derived from an engine fingerprint (automatic now)
    960edd94             no minor-unit currency, no ratio units — ruled and documented
    946d7296             constant(name) is the retrieval form, replacing ++name

## 3. The surface as it now stands

    -constant_value(name, value)                  declare
    -constant_number_units(name, number, units)   declare, unit kept out of the value
    constant(name)                                RETRIEVE — not ++name
    constant_value(Name, Value)                   query; Name is an ATOM
    constant_number_units(Name, Number, Units)    query; reports what was DECLARED

Rulings behind it, all the operator's, all 2026-09-11:

- **A bare name is the ATOM**, never the value. One name carries both readings.
- **Declaring a constant does NOT declare the atom** — my conservative call, not his. A name
  written BARE as an atom still needs its `-module` listing. This does NOT affect
  `constant(name)`, which needs no listing (measured); I stated it too broadly on 2026-09-11
  and inflated a costing by 88 edits.
- **`constant_number_units/3` reports the DECLARED pair.** `30 day` answers `30, day` while
  `constant_value/2` answers `2592000 second`. They disagree on purpose, because only the
  declared unit lets a gate check that a parameter's unit matches what its NAME claims.
- **No minor-unit currency, ever.** `cent` is ambiguous — euros have cents, dollars have
  cents. Base currency with decimals. Extended to ratios: no `percent`, no `basis_point`.
- **Durations are date arithmetic, not units.** Months vary; business days need holidays.

## 4. The corpus migration — APPROVED, then RE-OPENED on the first real domain

88 parameters / 28 domains / 337 call sites + 5 in eval bodies. 24 keyed parameters stay facts.
corpus-lane owns it and has touched nothing.

**The costing this was approved on is wrong in BOTH directions. Do not inherit either number.**

*Smaller per parameter:* two edits, not three. `constant(name)` consumes the name, so it never
becomes a bare-atom reference and needs no `-module` listing — measured. My "every migrated
parameter needs a module-list entry" came from a test that wrote the name BARE, which is a
different thing, and it inflated the estimate by 88 edits.

*Much larger per domain*, which is the finding that matters. corpus-lane staged
`eu/banking/crr_leverage_ratio` and stopped before editing:

- The domain **computes in bps throughout**. `leverage_ratio_bps/2` is EXPORTED, the kit
  supplies `ratio_bps`, 15 `bps` references span the public interface, queries and tests.
  Converting the parameter to `0.03` without rescaling its producers and consumers makes the
  comparison wrong; rescaling means changing a public predicate, a kit helper, the tests and
  the oracle. `au/merger_clearance` shows the same shape: 8 `_cents` parameters, 69 `_cents`
  references.
- **The value is already in two places** — `minimum_leverage_bps(300)` and a bare `300` at
  `leverage_ratio.clausal:111`. Converting the fact leaves the literal, so the DRY problem the
  migration exists to fix SURVIVES it. That is a hole in the premise, not a cost line. An
  upper bound of 74 of 112 parameters show the shape, with real noise — treat it as a shape.

So the ruling that unblocked the migration (`_cents` and `_bps` become decimals) is what makes
it expensive, because those are exactly the two groups it redirects. Being re-decided with the
real number. **Do not start corpus work here** — it is corpus-lane's, and it is not costed.

## 4a. NEXT ENGINE TASK: minor-currency units — handed over, NOT started

**Handed to the engine lane by corpus-lane on the operator's instruction, 2026-09-11, late.
Nothing has been done. The operator explicitly said: record it, do not start it.**

> "there must be units eur_cents and usd_cents in the currency module, with scale factor vs
> base euro/usd. constant_number_units() should be clear about the unit. euro numbers must be
> addable to eur_cents." — the operator

    -constant_number_units(sga_monthly_amount, 155000, usd_cents)

says the currency AND the scale in the declaration, where the ENGINE can see both, instead of
encoding them in the identifier where only a human can.

### THIS SUPERSEDES A RULING LANDED EARLIER THE SAME DAY — fix the docs WITH the work

`docs/currency.md` currently carries a section headed **"There is no minor-unit currency, and
there will not be"** (landed `960edd94`, on all three trees). That is now wrong and must be
rewritten as part of this task. Do not leave it: it is a landed document that states the
opposite of the current direction.

**The ruling was not reversed arbitrarily — it was refined, and the refinement answers its own
first objection.** The three reasons that section gives are:

1. *`cent` is ambiguous* — euros have cents, dollars have cents. **`eur_cents`/`usd_cents`
   answers this exactly**: the currency is IN the unit name, so the quantity says which.
2. *a scaled minor unit would rescale* — still live, see the design question below.
3. *it would put money in floats* — still live, and it is the hard constraint.

So reasons 2 and 3 become the IMPLEMENTATION CONSTRAINTS rather than objections.

### The hard constraint, measured on this tree

The numeric type follows the FACTOR's own type:

    gram      = Quantity(0.001, kilogram)   float factor   ->  7 gram  = 0.007  FLOAT
    day       = Quantity(86400, second)     int factor     ->  int
    kilometre = Quantity(1000, metre)       int factor     ->  int
    euro amounts                                            ->  Decimal, always

**Define the minor units with `Decimal` (or `Fraction`) factors, never float.**
`Decimal('0.01')` against euro keeps `5000 eur_cents` exact and addable to `euro` with neither
side going binary. Money in this corpus is stored in integer minor units precisely to stay out
of binary floating point; a float factor would reintroduce the thing the design exists to
prevent.

### The design question to decide EXPLICITLY, and it is the operator's

Does `5000 eur_cents` **normalise** to `Decimal('50') euro`, or stay `5000 eur_cents`?

Every non-base unit in the library currently normalises to its base. `constant_number_units/3`
reports the DECLARED pair either way (that ruling already landed), so this is about what
`constant_value/2` and arithmetic return.

corpus-lane's preference, and their reasoning is sound: **stay in the declared unit** — a
statutory "155000 cents" that reads back as "1550 dollars" is the same recoverability problem
`/3` was just fixed for. Not their call, and not mine; decide it before implementing, because
it decides whether this is a new kind of unit or an ordinary scaled one.

### Corpus state this lands on

- `clausify-domains 73edb41d` renamed the two ambiguous identifiers that were cleanly
  corpus-lane's: `sum_cents -> sum_eur_cents`,
  `sga_monthly_amount_cents -> sga_monthly_amount_usd_cents`. Gates and oracles byte-identical.
- **71 further ambiguous `_cents` names are NOT one lane's**: 13 are profile keys (oracle
  interface), 56 reach `eval/` bodies (harness-batch-lane), 27 are anchored in mutation
  catalogs.
- **Worth putting to the operator when reporting**: once these units exist, those names can
  carry the currency in the DECLARATION instead of the identifier, which may make most of the
  71 renames unnecessary — turning a 71-name three-lane rename into an engine feature plus a
  much smaller corpus pass. That is the strategic argument for doing this work first.

corpus-lane handed off at 83% context; anything corpus-side now goes to the next corpus-lane
session.

## 4b. THE DESIGN for 4a — ruled by the operator 2026-09-11, NOT implemented

**Scale is a property of the WRITTEN FORM, not of the quantity.**

One dimension per currency. Every amount is a `Decimal` in the base unit, always.
`eur_cents`/`usd_cents` exist as a **declaration spelling**, not as units in the dimension
system.

    -constant_number_units(sga_monthly, 155000, usd_cents)

      stored:    Quantity(Decimal('1550.00'), usd)   <- ONE representation, always
      /3 says:   155000, usd_cents                   <- what the declaration said
      /2 says:   Quantity(Decimal('1550.00'), usd)

Conversion is `Decimal(n).scaleb(-currency_scale(c))`. **Verified exact and round-tripping**
for 155000@2, 4999999@2, 300@4 (bps) and 1@0 (a scale-0 currency like JPY).

### Why not a real scaled unit

Each of these is measured on this tree, not argued:

- **Rescaling surprise.** Every non-base unit normalises to its base, so a real `eur_cents`
  would turn `5000 eur_cents` into `50 euro` and we would relitigate "does it normalise?"
  forever. With one representation the question does not exist.
- **The numeric type follows the FACTOR's type.** `gram` is `Quantity(0.001, kilogram)` with a
  FLOAT factor, which is why `7 gram` is `0.007` binary float. A minor unit carrying a factor
  is one careless `0.01` from putting money in floats. `scaleb` has no factor to get wrong.
- **A dimension per currency-scale** doubles the dimension table for no expressive gain:
  `eur_cents` and `euro` measure the same thing.

It meets both stated requirements directly: the declaration names the currency AND the scale
where the engine can see them, and euro amounts are addable to eur_cents amounts **trivially,
because after declaration they ARE euro amounts** — no conversion logic, no mixed-dimension
arithmetic.

### What it unlocks

`constant_number_units/3` reporting the DECLARED pair becomes the mechanism for the gate
corpus-lane wanted: **a parameter whose name ends `_cents` but whose declaration does not say
a minor unit is a defect**, mechanically checkable. That is the whole "documented not
represented" problem, closed. Eventually the suffix disappears because the declaration carries
it — which is the argument for doing this BEFORE the 71-name cross-lane rename, since it may
make most of that rename unnecessary.

Generalises unchanged to ratios: `basis_points`, `percent` as declaration spellings for
dimensionless ratios, exact via the same `scaleb`.

### Where it differs from the literal request

The operator asked for "units in the currency module with scale factor vs base". This gives the
observable behaviour asked for but **NOT a separate unit in the dimension system** — there is
no `Quantity(Decimal('0.01'), euro)` factor object. The thing worth preserving (what the
statute said) is already preserved by `/3`, without paying for it in the value representation.
**The operator has seen this distinction stated and ruled for this design.**

### What it does NOT solve

Nothing here touches corpus-lane's two findings: a domain whose PUBLIC interface computes in
bps (`leverage_ratio_bps/2` exported), and values DUPLICATED as bare literals (the `300` at
`leverage_ratio.clausal:111`). The second means the migration's DRY premise is partly false
until the literal sites also become `constant(...)`. This design makes both cheaper — no
numeric representation changes at any interface — but not free.

### Also required with the work

`docs/currency.md`'s "There is no minor-unit currency, and there will not be" section
(`960edd94`) is superseded and must be rewritten, not left. Its reason 1 (ambiguity) is
ANSWERED by naming the currency in the unit; reasons 2 and 3 (rescaling, floats) become the
constraints above.

## 5. Open, and what they need

- ~~The `-module` listing relaxation~~ **CLOSED** — moot. `constant(name)` needs no listing;
  the question only ever applied to a name written BARE as an atom.
- **`_add_lossy` is a write-only channel** — nothing reads `_all_lossy`, so every unit
  discarded on export is silent. `todo/exporter-lossy-channel-is-write-only-2026-09-11.md`
  has three options and the golden-output churn each costs.
- **The `++` operator export** — a non-constant `++` still emits `???`. The prelude packaging
  is unsolved in both Scryer and Trealla (self-applying `term_expansion/2` hangs Trealla; an
  included prelude hangs Trealla and Scryer rejects it positionally).
- **CLP(B) registry keyed on `id(Var)`** — a real design hazard with NO known reproduction.
  `todo/clpb-registry-keyed-on-object-addresses-2026-09-11.md`. Do not treat it as live.

## 6. Three lessons that cost real time today

**"Disabling X makes the crash go away" identifies a TRIGGER, not a cause.** The segfault
looked like CLP(B) for most of a day because CLP(B) is the only code that puts a
`weakref.finalize` on a Trail. `gc.disable()`, neutering the finalizer, skipping any one of
three dict pops, even reverting an unrelated transformer file — all "fixed" it, all real
measurements, all pointing at the wrong thing. The real bug was `Trail_dealloc` clearing
weakrefs while still GC-tracked. For a memory fault, anything that moves allocation or GC
phase masks or unmasks it.

**A load census cannot detect a compiler change.** Stale bytecode loads perfectly. Asking a
lane to "re-measure on the new sha" tests the new engine only if their caches were cold — and
even cold, "does it load" is the wrong instrument for a transformer change. **Name the
instrument you need** (behavioural probe, oracle, answer diff), not just the sha. I asked for
re-measurements the wrong way repeatedly today.

**An instrument that can only report success reports nothing.** Today's crop: a bisect that
used `str.replace` with no assertion and "proved" a change innocent; an awk detector that
matched its own comment; a `git grep` that said 0 downstream where a filesystem walk said 322;
an extraction that silently produced empty output and read as a clean sweep. Every instrument
needs a positive control, and you read the evidence line, not the verdict.

## 7. Lanes

corpus-lane [0dfae0] holds the migration and is the most active. iso-export-lane [e8cdc5],
harness-batch-lane [803e60], law-portal-1a [718243] have not been engaged today — none of
today's landings was flagged to them, which is worth doing if anything here reaches their
trees. The `.so` changed today (`7e825cdf`, `25fe9dce`), so **any lane with a long-lived
process that imported the engine before ~09:00 is running the old extension.**
