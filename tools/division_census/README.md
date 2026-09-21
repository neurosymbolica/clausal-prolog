# Division census

Answers one question: **do the corpus's genuine-division sites ever divide
unevenly?**

The exporter lowers corpus arithmetic to clpz `#=`, which is CLP over the
integers. `#=(X, 6/2)` binds 3; `#=(X, 7/2)` does not raise, it silently finds
no solution. So an exported program agrees with the corpus exactly where a
division comes out exact. Eight corpus sites do a genuine numeric division
(iso-export-lane, 2026-09-19, by a structural walk of the emitted AST), and
whether those are exact in practice is **not knowable from anything on disk** —
the runtime census records `{file, line, path}` and no operand values.

This measures it in the ENGINE, where the quotients are actually computed, so
nothing in the export pipeline has to change to answer it.

## Running it

Over a scorer run (the population that matters):

```sh
PYTHONPATH=<engine>/tools/division_census \
DIVISION_CENSUS_OUT=/tmp/div.tsv \
  python -c "import division_census; division_census.verify()" ...   # then the run
```

Over a pytest suite:

```sh
PYTHONPATH=tools/division_census DIVISION_CENSUS_OUT=/tmp/div.tsv \
  python -m pytest <paths> -p division_census
```

**Import it before any `.clausal` module is compiled.** Generated modules
capture the arithmetic runtime names into their own namespace at exec time, so
a hook installed afterwards is not in them.

## Reading the output

The header prints the size of every population — divisions evaluated, distinct
sites, INEXACT count, which bindings fired, and **which installed bindings
never fired**. That last line is the one that catches a census measuring
nothing: five bindings are wrapped because `exact_div` is bound by name in
several places, and a binding that never fires may mean that path was not
exercised — or that the wrap missed.

`division_census.verify()` is the positive control: it asserts the hook sees a
division at all and tells an exact one from an inexact one. Run it.

Three outcome classes, because `#=` fails differently for each and lumping
them together cannot be acted on: `exact` (an integer quotient — `#=` computes
it), `INEXACT` (an exact non-integer — **`#=` finds no solution, silently**,
and this is the class the question is about), and `float` (a float operand —
`#=` raises `domain_error`, which is loud, and 0 corpus sites are exposed).

A `count` is EVALUATIONS, not calls — `==` evaluates its arithmetic twice per
solution (measured). A site reads `<pred half__2>` when a compiled clause body
did the division (compiled bodies run in `<template>` frames, so there is no
`.clausal` line to report) and `file:line` when a source frame was on the
stack.

## Six of the eight sites do not need this census at all

The export lane derived eight genuine-division sites from the emitted AST
(2026-09-19). Their shape, which is what decides how to read a result:

* **six divide by a CONSTANT** (a basis-point scale, or a quarter), so their
  exactness is a property of the NUMERATOR alone: `X * Y / 10000` is exact iff
  `X * Y` is a multiple of 10000. Decidable statically — no census needed, and
  an INEXACT there is a question about which numerators, not about denominators.
* **two divide by a runtime quantity**, and those are the only ones a
  denominator census actually has to answer.

The site list itself is closed-side; ask the export lane for it.

## Running it over the corpus

The tool loads, but the corpus's per-domain import roots are the harness's
knowledge, not this repo's: loading division-bearing domain files directly got
only a subset (the downstream corpus's own import roots resolve differently
per domain). Measured working end to end on those 6 — real site attribution
(`categorisation.clausal:149`) and real operand values — so the instrument is
not the blocker.

For the full population, hand it to the lane that owns the scorer runs: set
`PYTHONPATH` to include this directory, set `DIVISION_CENSUS_OUT`, and import
`division_census` (calling `verify()`) before the run loads any `.clausal`.
The header line "bindings installed but NEVER fired" is the check that the run
actually exercised the arithmetic paths.
