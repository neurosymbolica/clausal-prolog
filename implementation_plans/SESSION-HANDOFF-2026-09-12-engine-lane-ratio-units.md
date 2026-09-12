# Engine lane handoff — 2026-09-12, ratio units

Continues `SESSION-HANDOFF-2026-09-11-engine-lane-minor-units-END.md`, whose "Open" list had
ratio units as the designed-but-unbuilt item and corpus-lane's live blocker. They are built.

## 1. What landed

`percent` and `basis_point`, **dimensionless scaled units**, in `clausal/modules/units.py`:

    RATIO_UNITS = {"percent": 2, "basis_point": 4}     # name -> decimal exponent
    percent     = _make_ratio_unit("percent")          # Quantity(Decimal('0.01'),   {})
    basis_point = _make_ratio_unit("basis_point")      # Quantity(Decimal('0.0001'), {})

    -constant_number_units(min_leverage, 300, basis_point)

      stored                    Quantity(Decimal('0.0300'), {})
      constant_number_units/3   300, basis_point
      constant_value/2          Quantity(Decimal('0.0300'), {})

The previous landing's claim that "the mechanism needs nothing new" held exactly: the
directive, the `300 (basis_point)` annotation sugar and the arithmetic all took them
unmodified. The whole feature is a 3-line table, a 1-line factory and two bindings.

**Singular, not plural.** Every other unit name in the repo is singular (`metre`, `usd_cent`,
`penny`) and `docs/currency.md` already spelled it `basis_point`. The todo's title said
`basis_points`; the convention won. `bps` and `pct` are NOT units — they stay abbreviations
the vocabulary does not hold, which is what keeps the scale lint's hand-maintained half alive.

## 2. The exactness question the todo said to verify — and why its reason was wrong

The todo warned that the currency coercion path might be what makes minor units exact, and
that a dimensionless quantity may not have it. Measured **with a negative control**, because
a probe that cannot show inexactness cannot certify exactness:

    300 (basis_point)        Decimal('0.0300')      exact
    5.25 (percent)           Decimal('0.0525')      exact
    0.5 (basis_point)        Decimal('0.00005')     exact
    Fraction(1,3) (percent)  Fraction(1, 300)       exact
    7 (gram)   [control]     0.007, a binary float  INEXACT

It is **not** the currency coercion. `_to_decimal` is keyed on an `is_currency` dimension and
lives in the branch of `Quantity.__init__` that a scaled unit returns before reaching
(`terms.py:2372`). Exactness comes from `_num_pair`, which is **dimension-agnostic** and reads
a float beside a `Decimal` as `Decimal(str(f))`.

So the single load-bearing requirement is that the FACTOR is a `Decimal` — which is what
`_make_minor_unit` already argued for currencies, and what `gram = Quantity(1e-3, …)` does not
have. The `scaleb`-check-the-multiplication contingency the todo held in reserve was not
needed.

**Worth keeping as a shape**: the todo's worry named the right risk and the wrong mechanism.
Minor units and ratio units are exact for the SAME reason, and it was never the currency one.
A correct conclusion resting on a wrong mechanism survives until the mechanism is the thing
that changes.

## 3. Two instruments this landing broke, both invisible before it

### 3a. The exporter's inline refusal was blind to exactly this shape

`_is_known_scaled_unit` selected `isinstance(v, Quantity) and v.dims`. **`and v.dims` excludes
a dimensionless scaled unit** — a ratio unit's shape. Measured blind before the fix, with a
dimensioned probe as the positive control showing the checker can refuse:

    dimensioned scaled unit  (control)  refused = True
    DIMENSIONLESS scaled unit           refused = False      <- the defect
    usd_cent (real minor unit)          refused = True

The DECLARATION path (`_base_unit_names`) refused correctly throughout. Only the inline path
was blind — the same half-covered-surface shape corpus-lane found on 2026-09-11, when
`pay(155000(cent))` reached `_try_quantity` rather than `_collect_constant`.

**It matters more here than for `cent`:** dropping `basis_point` from `300(basis_point)` emits
`300` against a stored `0.03`, a **10000x** error, and `eu/banking/crr_leverage_ratio` — the
domain that motivated ratio units — is on the export roster.

**The clause excluded NOTHING on the day it was written.** There were zero dimensionless
`Quantity` constants in `units.py`, so no instrument could have noticed; the fix adds exactly
`{basis_point, percent}` to the refused set and removes nothing, which is also why it cannot
regress an existing export. This is the hard version of "an instrument keyed on a property the
checked thing does not have": invisible until the population changes.

### 3b. The TitleCase alias gate required an alias for units that cannot have one

`test_alias_table_is_complete` asserts every lowercase unit appears in
`_DEPRECATED_UNIT_NAMES.values()`. It was written when every unit in `units.py` had a
TitleCase ancestor. TitleCase became a **load-time error** on 2026-09-10, so a unit added
after that has no ancestor, and minting `Percent` would be adding to the vocabulary that error
exists to remove.

Fixed by exempting `set(units.RATIO_UNITS)` — **derived, not listed by name**, so a third
ratio unit needs no edit here. Mutation-verified in both directions: dropping every alias for
an existing unit still fails it, and emptying the exemption fails it too.

**A method note about my own instrument, not the code.** My first mutation probe popped the
key `"Kilometre"`, which does not exist (the real keys are `Kilometer`/`kilometer`), so the
gate "passed" under a mutation that never happened and I briefly had a gate that looked
toothless. The probe reported success for doing nothing — the dominant failure mode in this
repo's notes, arriving this time inside the tool built to check for it.

## 4. The scale lint's hand-maintained half shrank, and its own control said so

`_HAND_MAINTAINED_SCALE_WORDS` carried `bps`, `basis_points`, `percent`, `pct` with a comment
saying they move to the derived half when ratios land. They did.

Done deliberately in two steps: the derivation was extended **first, with the hand list
untouched**, purely to watch the overlap assertion fire. It did, naming both words to drop.
A half designed to shrink now has a demonstrated way of noticing that it should have — which
is the property harness-batch-lane asked for when they built it and which nothing had yet
exercised.

`bps` and `pct` stay: abbreviations no vocabulary holds and no derivation will produce. The
hand half shrank without emptying, which is the outcome that keeps the residue question
answerable.

**The inline copy of the derivation inside `_scale_suffixes` was deleted** in favour of calling
`_derived_scale_words()`. Two copies would have let the overlap control go on checking a set
the lint no longer used — and the extension had to reach both, so this was required rather
than tidying.

Net new suffixes: `basis_point` (singular) and `percents`. `percent` and `basis_points` were
already in the set by hand, so the lint's population barely moves.

## 5. Where this leaves corpus-lane's blocker — read this before migrating

Ratio units are built, and `crr_leverage_ratio` **still cannot migrate and stay exported**:
the exporter refuses a ratio-unit amount for the same reason it refuses every scaled unit.
Option 2 (`todo/exporter-folds-scaled-units-to-the-wrong-magnitude-2026-09-11.md`) was already
load-bearing after the "follow statutes" ruling; it now also blocks the blocker this landing
was meant to clear. **That is the honest status: the engine half is done, the path is not.**

Unchanged and still true from the todo's own analysis:

* A domain whose PUBLIC interface computes in bps (`leverage_ratio_bps/2` is exported) must
  rescale producers and consumers together. Cheaper — no representation changes at any
  interface — not free.
* The bare `300` at `leverage_ratio.clausal:111` under `check_ratio_gte/6` is **still
  invisible** to the lint, because the discriminator is the FUNCTOR's name. Ratio units do not
  touch that; the callee's-parameter design in the previous handoff is still the fix, and it
  is the one that would check the site that decides.

## 6. The three claims — and only one of the three was actually measured here

| axis | who | result |
| --- | --- | --- |
| engine suite | me | baseline `144 failed / 16199 passed / 1 error`; after `144 failed / 16219 passed / 1 error` — failure NAME SETS **identical**, 0 new / 0 fixed, both sets non-empty at 144. The +20 passed are exactly the 20 new tests. Same single collection error (`test_clportools.py`) in both arms. |
| doc blocks | me | 38 before and after — and the scanner was **positive-controlled** into the new section: breaking one new ```clausal block took it to 39, restoring took it back to 38. |
| scale lint noise floor | me | 2 warnings in each arm, unchanged from the recorded floor. |
| export bytes | iso-export-lane | **NOT RUN.** `clausal/tools/clausal_to_prolog.py` changed. |
| domain answers | harness-batch-lane | **NOT RUN.** `clausal/templating/term_rewriting.py` and `clausal/modules/units.py` changed, and term_rewriting is on the load path for all 82 harness bodies. |

**How the engine-suite arm was measured, because the method is the claim.** Both arms ran in
ONE throwaway worktree (`.claude/worktrees/ratio-baseline`, detached at `c8f38336`, with the
24 `.so` files copied in and the engine path asserted by `realpath` before trusting anything
it said). The baseline ran the untouched checkout; then the six changed files were copied in
and the after arm ran. Nothing in the shared clone was reverted at any point, which is the
hazard the previous handoff names: reverting engine source in a tree other lanes are reading
surfaces as a `SyntaxError` blamed on an unrelated file.

The six files were confirmed **byte-identical** between the clone and the measured worktree
and content-pinned at `sha256 a6518ff0…`, because a sha names what HEAD said, not what was
read (iso-export-lane's rule, 2026-09-11).

**A first run was DISCARDED and it is worth saying why.** I started an after-arm in the clone
and then kept editing source while it ran. That is a torn read by construction; it happened to
be running during the alias-gate fix. Reported as a number it would have looked like a
measurement. The only thing wrong with it was invisible from its output.

**What the engine-suite arm cannot see, stated so someone who knows more can act on it.** Both
arms ran inside `.claude/worktrees/`, where this repo's notes say the fmt/rewrite corpus tests
are red by construction. That distortion is symmetric across the two arms and cancels in a set
diff — but it means the 144 is a worktree number that happens to agree with the recorded
baseline, not an independent confirmation of it in the primary tree.

## 7. Open after this

- **Option 2 for the exporter** — fold to the BASE magnitude. Now blocks ratio-unit migration
  as well as minor-unit migration; export stays lossy either way (it fixes the magnitude, not
  the unit).
- **The lint is still blind to a bare literal under an unscaled functor**, which is where
  `crr_leverage_ratio`'s deciding `300` sits. Ratio units do not change that. The
  callee's-parameter design is the fix worth building, because it checks the site that decides.
- **Only two ratio units.** `per_mille` and friends are one `RATIO_UNITS` entry plus a
  binding; `test_every_declared_ratio_unit_is_bound_in_the_module` fails until the binding
  exists, and the lint and exporter pick it up with no edit.
- Everything else from the previous handoff's Open list is unchanged, **Box included** — it is
  still the only tree on the old vocabulary.

## 8. The one method note worth carrying forward

Three separate instruments in this landing were wrong in the same direction, and none of them
was wrong about its own subject:

* `_is_known_scaled_unit` filtered on `v.dims` — correct about every value that existed when
  it was written.
* `test_alias_table_is_complete` required a TitleCase ancestor — correct about every unit that
  existed when it was written.
* my own mutation probe popped `"Kilometre"` — correct about a key that does not exist.

The first two are the previous handoff's "the instrument stayed the same while the world it
measures moved". The third is not: it was wrong on the day it was written and reported success
anyway. **The difference is worth keeping, because the fixes differ.** A stale instrument needs
its enumeration derived from an authority. An instrument that can only say yes needs a
negative control — and the cheapest one is to mutate the thing it checks and require it to
fail. Every gate touched here now has one.
