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

---

## Progress / findings (2026-06-26)

**Named gap CLOSED — structural head literals in output mode.** The atomic head
kinds were already covered by `test_numeric_head_literal.py`; the structural
kinds (Compound / functor-instance / nested compound / list) had only
compile-time normalization tests (`test_structural_head_normalization.py`), no
end-to-end var-query tests. Added them:
`tests/test_structural_head_output_mode.py` (+ fixture
`tests/clausal_modules/structural_head_output_mode.clausal`) — compound,
functor-instance, nested-compound and list heads all correctly BIND an unbound
caller Var, couple a partially-instantiated caller term, and enumerate
relationally. All pass. (The only structural limitation is the documented,
deferred "undeclared bare-functor construction" — `point(1,2)` with no declared
`point` still raises "not in scope as a term class" in output mode.)

**Relational builtins — representative survey (both modes).** Exercised in
output / reverse / generative modes; all behave correctly in their supported
modes (no silent-wrong/no-answer of the numeric-head kind):
`append` (split/prefix), `length` (measure + generative), `between` (generate),
`succ` (both directions), `plus` (solve any arg), `in_` (membership generative),
`list_item` (index→elem and elem→index), `select` (elem→rest, var-elem
enumeration), `subtract`, `sort`/`msort`, `numlist`, `reverse` (forward),
`findall`.

| Predicate | input mode | output / reverse mode |
|---|---|---|
| append/3 | ✓ | ✓ (split, prefix) |
| length/2 | ✓ (measure) | ✓ (generative) |
| succ/2, plus/3 | ✓ | ✓ (any arg) |
| between/3 | ✓ | ✓ (generate) |
| in_/2, list_item/3 | ✓ | ✓ |
| select/3 | ✓ | ✓ (enumerate) |
| subtract/3, sort, msort, numlist | ✓ | ✓ |
| **reverse/2** | ✓ (forward) | ✗ **forward-only** — see below |

**Genuine finding — `reverse/2` is forward-only.** `reverse(L, [3,2,1])` with a
proper logic-var `L` yields no solution (SWI is bidirectional). Not a
silent-correctness bug (it fails, doesn't lie), but a mode-incompleteness. Filed:
`todo/reverse-not-bidirectional.md`.

**Meta-finding — the mixed-case-name trap recurs.** A bare name that is
Capitalized-but-not-ALL-CAPS (`Rest`, `St`) is NOT a logic variable
(`_is_logic_var_name` requires ALL-CAPS or `_leading`), so it silently becomes an
atom — turning an intended output variable into a constant and yielding no
solution. This is the same root cause as the callgoal-imported-lambda bug. It bit
this very audit (a `select(_, _, Rest)` probe). A lint could flag it, but
mixed-case names are legitimately constructors/atoms too, so it would be noisy —
noted as a consideration, not implemented.

### Still open (deep sweep not yet exhaustive)
- CLP labeling (`label`, `in`, `#=` reverse), string/regex predicates, full
  term-inspection (`functor`, `arg`, `=..`), and meta-predicates (`bagof`,
  `setof`, `aggregate_all`) have not been swept mode-by-mode. No bug found in the
  representative survey, but the matrix above is not yet complete for these.
