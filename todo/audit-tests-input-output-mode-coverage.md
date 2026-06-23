# TODO: audit the test suite for input/output mode coverage

**Opened 2026-06-23** as follow-up to `equality-vs-unification-audit.md`.

## Why

The numeric-head-literal bug (and its bool/None sibling) survived **8085 tests**
because every existing test exercised those heads in **input mode** only — the
caller supplied the literal, or the numeric output was bound in the body. The
**output / var-query mode** (caller passes an unbound `Var` in that position)
was never tested, so the silent "no solution" went unnoticed.

This is a *mode-coverage* gap, not a one-off. The same blind spot likely hides
elsewhere: anything that behaves differently when an argument is ground (input)
vs. an unbound `Var` (output) needs tests in **both** directions.

## Scope to audit

For each, confirm there is at least one test in **both** input and output mode:

1. **Head literals**, every kind in the audit table: int, float, complex, bool,
   None, str, bytes, atom, list, dict, set, Compound, functor-instance. (The
   atomic kinds are now covered by `tests/test_numeric_head_literal.py`;
   structural kinds are the known gap.)
2. **Builtins / library predicates** that are relational (meant to run in
   multiple modes): arithmetic (`is`, `Sign`, `Gcd`, `DivMod`), list ops
   (`append`, `length`, `MapList`, `Filter`, `FoldLeft`), term inspection,
   string/regex predicates, CLP labeling, meta-predicates (`FindAll`, `BagOf`).
3. **First-argument indexing & groundness-keyed dispatch** — the ground path and
   the var path take different compiled plans (this is what masked the head-bug
   for indexed positions). Ensure both plans are tested per predicate.

## Approach

- Mechanically enumerate predicates/builtins and grep fixtures for var-mode
  vs ground-mode call sites. A fan-out of agents over test files is a good fit
  (one agent per area: head patterns, builtins, CLP, meta).
- Produce a coverage matrix (predicate × {input, output}) and list the holes.
- Backfill missing output-mode tests; for any that *reveal* a bug, file it under
  `todo/` and fix via the systematic-debugging flow.

## Done when

- Coverage matrix exists and every relational predicate has both-mode tests (or
  a documented reason it's single-mode).
- New output-mode regression tests added for the holes found.
