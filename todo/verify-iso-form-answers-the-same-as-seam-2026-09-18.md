# Verify the ISO form answers the same as the seam form

**Operator's framing, 2026-09-18:** once the formalisation pipeline is migrated to output
Clausal ISO form, verify it is consistent with what it outputs today. It should be — it is
already very close.

**Status: two engine-side gaps block it; the harness half is specified below and is the
export lane's.** Nothing here is started.

## Why this is the useful verification

It tests the migration's only real risk. Everything else about moving the corpus to ISO
syntax is mechanical; the thing that could go wrong silently is a domain answering
DIFFERENTLY after the move. This catches exactly that, per domain, against the behaviour
the corpus has today.

It is deliberately NOT the retired G4-as-reimport gate. That one round-tripped
`.pl` back through the reverse translator, which is measured not an inverse (7 breakages).
This loads the `.pl` **natively** — nothing is translated back, so a disagreement indicts
the two forms rather than a translator sitting between them.

## What is already established (measured 2026-09-18, canonical 38d3cb32)

Subject: `eu/banking/crr_leverage_ratio` — small, exports with zero errors, carries
`basis_point` constants.

**The seam side yields a real answer set:**

```
bank_above_leverage    -> eligible
bank_below_leverage    -> ineligible
bank_missing_exposure  -> indeterminate
```

**The exported `.pl` loads back into Clausal and defines every predicate the seam module
does**, including `ratio_bps` resolved through `formalize_lib`. The round trip is live.

So the premise holds: the logic transfers intact. What differs is addressing and
declaration, not semantics.

## GAP 1 (engine) — relative module paths do not resolve

The export emits, correctly for Prolog:

```prolog
:- use_module('../../../../formalize_lib', [ratio_bps/4, check_ratio_gte/6, ...]).
```

Loading that into Clausal fails with `SyntaxError: invalid syntax (leverage_ratio.pl,
line 6)`. A filesystem-relative path is a valid Prolog module reference and is not a
Clausal module name.

**Reproduction:** rewriting `use_module('../../x'` to `use_module(x` with one `sed` makes
the module load immediately, with all predicates present. That is the whole of gap 1.

**Where it belongs:** the `.pl` loader. Note the ISO front end (L3) settles this by
construction — a `.clausal` file addresses modules the Clausal way and never emits a
relative path — so this may be worth fixing only as far as the harness needs, rather than
properly.

## GAP 2 (engine) — a bare compound data term needs declaring in Clausal

With gap 1 worked around, the query fails:

```
NameError: Predicate 'attribute/2' is not in scope as a term class.
```

`attribute/2` is only ever CONSTRUCTED as a data term in the export and never defined —
which is correct and unremarkable in Prolog, where a compound needs no declaration. Under
Clausal's strict-atoms regime a term constructor must be in scope. This is Clausal being
STRICTER than ISO, not the export being wrong.

**Where it belongs:** the engine. Either a relaxed mode for a re-imported ISO module, or a
rule that compounds appearing only in data position need no declaration. The second is the
more interesting question and should not be decided just to unblock a harness.

## The harness (export lane, blocked on the two gaps above)

Per domain:

1. Load the seam module; enumerate the domain's own fixtures and run its public query
   predicates; record the ANSWER SET.
2. Load the exported `.pl` natively; run the identical goals; record the ANSWER SET.
3. Compare the SETS, not counts, and not pass/fail.

**Non-negotiables, each learned from a failure this project actually had:**

* **Answer sets, never counts.** A form that answers with FEWER solutions still "passes" a
  count-level comparison. This is the single most likely shape of a real regression here.
* **Assert which form ran.** A run that silently loaded the seam module twice and reported
  "identical" is the exact failure the harness exists to prevent. Pin the module's origin
  path, the way the sweep asserts which engine tree `import clausal` resolved.
* **A negative control.** Perturb one clause in the exported form and require the harness
  to catch it. A comparison that cannot say NO is not a comparison.
* **Print the denominator** — domains compared, goals run, answers collected. A shrinking
  population must be visible.

**Baseline value:** this can be built and run against TODAY's pipeline, before any
migration. Then the migration is checked against a recorded baseline rather than against a
baseline reconstructed afterwards from memory.

## What this does not do

It compares the exported form against the seam form. It says nothing about whether EITHER
is a correct formalisation of the law — that is what the domain's own oracle harness is
for, and it is a different question.
