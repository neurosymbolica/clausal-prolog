# Exporter constants: a per-dialect capability, not one trade-off

**Status**: design, awaiting review. Supersedes the first version of this file (same path,
2026-09-13), which picked one side of a trade-off and was unhappy about it.

Operator, 2026-09-13: *"there are two sides to this: our side, where we can do what we want, and
the export side, where we have to take care that things are understood by another Prolog… just
add a switch to the exporter to tell it how to export. Then we don't have to pick only one side
of a trade-off and be unhappy about it."*

## Why the first version was wrong

It argued term expansion against ISO cleanliness and recommended one. That framing assumed the
exporter has a single target. **It does not — it already has a dialect.** The trade-off is not
ours to resolve; it is a property of whatever system is receiving the file, and the exporter is
precisely the boundary where that becomes known.

## The mechanism already exists

`clausal/tools/prolog_dialect.py` has `Dialect` with capability fields and factories for
**iso, swi, scryer, trealla, gprolog**. The exporter takes one (`ExportVisitor(dialect, …)`) and
already gates on it — `if self.dialect.module_system == "none"` — and `module_system` already
uses the exact pattern needed here: `"iso"` / `"swi"` / `"none"`, with `"none"` for the dialect
that lacks the feature.

So this is **one new capability field**, set by each factory. Not a new concept, not a parallel
switch.

```text
constants: str = "facts"        # "none" | "facts" | "expansion"
```

| dialect | `constants` | why |
| --- | --- | --- |
| `iso` | `facts` | no `prolog_load_context/2`; the EXPORTER fills the module in, which it knows statically |
| `scryer` | `expansion` | verified: `term_expansion/2` fires and sees the module |
| `trealla` | `expansion` | same, verified |
| `swi` | `expansion` | has `prolog_load_context/2` |
| `gprolog` | `none` | no module system either; refuse rather than emit something that will not run |

### What each emits

**`expansion`** — the directive, expanded on load by a prelude:

```text
:- constant_number_units(fee, 5000, euro).
```

**`facts`** — the same information with the module filled in at export time, needing no
extension of the receiving system:

```text
constant_number_units(my_module, fee, 5000, euro).
```

The exporter knows the module statically, exactly as the engine's transformer now does for
`constant_number_units/3`. So the one thing term expansion buys — module context at load — is
something the export side can supply for free when the target cannot.

**`none`** — refuse, as today. Loud beats a file that parses and does not run.

## What is the same in every case

**Use sites fold to the BASE magnitude.** `pay(constant(fee))` becomes `pay(1550.00)`, never
`pay(155000)`. This is dialect-independent and is option 2's entire content:

> **Option 3 does not replace option 2 — it contains it.** Emitting `constant_value(fee, V)` as a
> goal instead would turn value positions into conjunctions and rewrite every exported clause.
> What option 3 avoids is the LOSSINESS, not the work.

Unit resolution uses static data only (`_data.py`'s `scale`, a `Quantity` factor, `RATIO_UNITS`).
Resolving a NAME is not executing the file, which is the objection that does not apply. Anything
unresolvable refuses, in every dialect.

## Verified prerequisite

Measured 2026-09-13 against the real binaries, locally — `/workspace/scryer-prolog/target/release/scryer-prolog`
and `/workspace/trealla-prolog/tpl`, **not** box, whatever this lane's notes used to say:

| | Scryer | Trealla |
| --- | --- | --- |
| `prolog_load_context/2` present | yes | yes |
| inside `:- module(my_mod, …)` reports | `my_mod` | `my_mod` |
| a `term_expansion/2` hook fires AND sees the module | `exp_mod` | `exp_mod` |

The third row is load-bearing: a hook fired during load, asked for the module from inside itself,
and wrote it into the expanded fact.

**`prolog_load_context/2` is not ISO** — a de-facto convention these two share. That is precisely
why it belongs behind a dialect capability rather than in the emitter unconditionally.

## The prelude, and why the switch shrinks it

`clausal_to_prolog.py` says the prelude's packaging *"is unsolved in both reference systems"*.
The switch does not solve that — it **confines** it. Only `expansion` dialects need a prelude at
all, so the unsolved question stops blocking the ISO roster, which is the roster that exists.

Packaging for `expansion`, still open and deferred: inline per file, or one library file plus
`:- use_module(library(clausal_constants))`. Both are reasonable; neither needs deciding to ship
`facts`.

## What still does NOT cross: the decimal SCALE

Measured 2026-09-13 by running the exporter's own output. The exporter writes
`constant_number_units(fees, sga, 1550.00, usd_cent)`; both systems read `1550.00` as a float and
print `1550.0`. **The magnitude survives, the scale does not**, because Prolog has no decimal
type.

So the decimal-string work (`-constant_number_units(fee, "292.00", usd)`) keeps a statutory scale
exact **inside the engine** and loses it at the Prolog boundary. That is a smaller loss than the
100x magnitude error option 3 fixes, and it is not fixable by this design — carrying it would need
an exported representation Prolog can hold exactly, which is a separate question from whether the
declaration crosses.

Worth stating because the obvious next assumption is that a declaration crossing intact means the
value crosses intact. It does not, in one specific respect.

## Scope

* one field on `Dialect`, set by five factories
* the emitter branches on it in `_collect_constant`'s output path
* delete the two refusals (`_is_known_scaled_unit` inline, `_base_unit_names` declaration), the
  pinning test `test_the_exporter_folds_a_minor_unit_to_its_declared_magnitude`, and the "Known
  divergence" warning in `docs/currency.md` — the todo says to do this with whichever option lands
* `constant_value/2` keeps Triska's spelling and its program-wide reading wherever it appears

## Testing

Per dialect, because a switch untested on a branch is a branch that does not work:

* `iso` emits facts with the module; `scryer`/`trealla` emit the directive; `gprolog` refuses
* a minor-unit constant exports the BASE magnitude (`1550.00`, not `155000`); a ratio unit
  likewise (`0.03`, not `300`); a base unit is unchanged — the regression guard
* an unresolvable unit refuses in every dialect
* **the emitted program runs under the real binary and answers the declared pair back** — for
  `scryer` and `trealla` via the prelude, for `iso` as plain facts. The existing refusal exists to
  avoid "something that parses and does not run", and only execution disproves that. Both binaries
  are present locally, so this is a real test and not a skipped one.
* a mutation control: neutering the dialect branch must fail exactly the dialect tests, not all of
  them

## Blast radius

`clausal_to_prolog.py` is a downstream user's file; the roster is every exported file. Today **no corpus file
declares a constant**, so the roster's bytes should not move at all — the change is reachable only
by files that declare one. That makes export-bytes the measuring axis and a ZERO the expected
result, with the caveat that a zero here is the cheap kind: nothing reaches the new code yet. The
meaningful test is the per-dialect execution above.
