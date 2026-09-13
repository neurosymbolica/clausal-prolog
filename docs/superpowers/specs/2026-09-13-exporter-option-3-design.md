# Exporter option 3: the declaration crosses, carrying its unit

**Status**: design, awaiting review. Operator chose option 3 over option 2 on 2026-09-12, after
ruling on 2026-09-12 that the constants family should exist in Scryer and Trealla via term
expansion.

Supersedes the plan in `todo/exporter-folds-scaled-units-to-the-wrong-magnitude-2026-09-11.md`,
whose option 2 was "the one worth costing".

## What it is for

Today a constant's unit is discarded and its DECLARED magnitude is emitted:

```text
-constant_number_units(fee, 5000, euro)     ->   /* LOSSY: unit discarded */
pay(constant(fee))                               pay(5000).
```

For a base unit the number is right and only the unit is lost. For a SCALED unit the number is
wrong — `155000 usd_cent` would emit `155000` where the engine holds `1550.00` — which is why
both the declaration and the inline form are currently REFUSED outright.

Option 3 emits the declaration so the **pair** crosses, rather than folding it away.

## The finding that changes the shape of the work

**Option 3 does not replace option 2 — it contains it.** Stated plainly because the operator
chose option 3 *instead of* option 2, and that is only half available:

* **Use sites still need a number.** `pay(constant(fee))` becomes `pay(<number>)`, and that
  number must be the BASE magnitude, not the declared one. Emitting `constant_value(fee, V)` as
  a goal instead would turn a value position into a conjunction and rewrite the shape of every
  exported clause — far larger, and not what was chosen.
* **So the unit-resolution-and-conversion step is still required**, and it is exactly option 2's
  content. Option 3 adds the declaration on top.

What option 3 avoids is not the work; it is the *lossiness*. The magnitude fix stops being a
consolation prize for dropping the unit, because the unit no longer gets dropped.

## Verified prerequisite: term expansion has the module, in both targets

Measured 2026-09-13, locally (`/workspace/scryer-prolog/target/release/scryer-prolog`,
`/workspace/trealla-prolog/tpl` — **not** on box, whatever this lane's notes used to say):

| | Scryer | Trealla |
| --- | --- | --- |
| `prolog_load_context/2` present | yes | yes |
| inside `:- module(my_mod, …)` reports | `my_mod` | `my_mod` |
| a `term_expansion/2` hook fires AND sees the module | `exp_mod` | `exp_mod` |

The third row is the load-bearing one: a hook fired during load, called
`prolog_load_context(module, M)` from inside itself, and wrote the enclosing module into the
expanded fact. That is the same compile-time module insertion the engine now performs for
`constant_number_units/3`, available on the Prolog side by the same mechanism.

**`prolog_load_context/2` is NOT ISO.** It is a de-facto convention these two share. If the
roster ever targets a third system, this is the dependency that would need re-checking — and it
belongs in the design rather than being discovered later.

## What gets emitted

For each declaration, a directive the prelude expands:

```text
:- constant_number_units(fee, 5000, euro).
:- constant_number_currency(sga, 155000, usd_cent).
```

and at use sites, the BASE magnitude:

```text
pay(5000).            % euro is a base unit: unchanged
allot(1550.00).       % usd_cent resolved and converted
```

The `/* LOSSY */` comment goes away for any unit the exporter can resolve, because nothing is
lost: the magnitude is the stored one and the pair is in the program.

## The prelude, which is the actual hard part

`clausal_to_prolog.py` already says so, at the `-constants` refusal: *"the packaging of the
prelude is unsolved in both reference systems"*. This design does not get to wave that away, so:

**Contents** — the family, as the engine now has it:
`constant_value/2` (program-wide, Triska's spelling), `constant_number_units/3`,
`module_constant/3`, `module_constant_units/4`, and a `term_expansion/2` that turns each
directive into facts carrying `prolog_load_context(module, M)`.

**Packaging — three candidates, and this is the part needing a decision:**

1. **Inline the prelude into every exported file.** No dependency, no install step, runs
   anywhere. Costs duplication across 1560 files and makes every file's head noisy.
2. **Emit one library file beside the roster** and a `:- use_module(library(clausal_constants))`
   in each file. Clean, and introduces an install/packaging step the roster does not have today.
3. **Emit the facts directly, no expansion.** `constant_number_units(fee, 5000, euro).` as a
   plain fact, with the module argument filled in by the EXPORTER rather than by a hook. No
   prelude at all, no `prolog_load_context` dependency, and therefore no ISO-conformance
   question — at the cost of the directive form the operator's ruling asked for.

**(3) deserves more weight than its position suggests.** The exporter knows the module
statically, exactly as the engine's transformer does — so the one thing term expansion buys
(module context at load) is something the exporter can supply at export time. That would make
the Prolog side need *no* non-ISO feature, which is the stated direction for the roster.

Recommendation: **(3) for the roster, with (2) available** for anyone consuming the declarations
by hand. But this is the operator's call, because (3) trades the directive surface for ISO
cleanliness and the ruling asked for term expansion.

## Scope

* Delete the two refusals (`_is_known_scaled_unit` inline, `_base_unit_names` declaration) and
  the pinning test `test_the_exporter_folds_a_minor_unit_to_its_declared_magnitude`, plus the
  "Known divergence" warning in `docs/currency.md` — the todo says to do this as part of whichever
  option lands.
* Unit resolution uses static data only: `_data.py`'s `scale` for a minor unit, the `Quantity`
  factor for a physical one, `RATIO_UNITS` for a ratio. Resolving a NAME is not executing the
  file, which is the objection that does not apply.
* Refuse what cannot be resolved, rather than guessing.

## Testing

* a minor-unit constant exports the BASE magnitude (`1550.00`, not `155000`)
* a ratio-unit constant likewise (`0.03`, not `300`)
* a base-unit constant is unchanged — the regression guard
* the declaration appears in the output with its unit
* an unresolvable unit still refuses
* **the emitted program actually runs under both Scryer and Trealla**, and answers the declared
  pair back. This is the test that matters: the existing refusal exists precisely to avoid
  "emitting something that parses and does not run", and nothing short of executing it proves
  otherwise.

## Blast radius

`clausal_to_prolog.py` is iso-export-lane's file and the roster is 1560 files — every one of them
changes if the prelude is inlined, and none if option (3) emits facts and no corpus file declares
a constant. Export-bytes is therefore the axis that measures this, and it will be a large
non-zero by design; the meaningful check is that the DIFFERENCE is confined to constant-declaring
files plus whatever the prelude adds.
