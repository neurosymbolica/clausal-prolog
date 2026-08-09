# BUG: numeric literal in a ruled-clause head is not unified against a query variable

**Reported 2026-06-23** (found while writing a Prolog→Clausal cheat-sheet for a downstream
consumer; every example was executed via `python -m clausal.testing`).

**RESOLVED 2026-06-23.** Root cause: in `clausal/logic/compiler/head_match.py`, an int/float/complex
head literal was compiled to a Python `MatchValue` literal pattern (`case [_v0, 20000]`), which only
matches when the deref'd argument already *equals* the literal (input mode). An unbound `Var` caller
(output / var-query mode) silently failed the match → no solution. Strings, atoms, and bare facts
already used a capture + `unify()` guard, which is why existing tests missed it. Fix: numeric head
literals now take the same capture + `unify()` path (`if _ncap0 == 20000 or unify(_ncap0, 20000, trail)`),
binding the literal into the caller's `Var`. Regression test: `tests/test_numeric_head_literal.py`
(fixture `tests/clausal_modules/numeric_head_literal.clausal`); red-green verified. The repro below now
passes 11/11.

## Symptom

A **ruled** clause (`head <- body`) whose head contains a **numeric literal** (int or float) in an
argument position does **not** bind that literal into a caller's variable at that position. The query
silently yields **no solution** (not an error). The clause succeeds only if the caller supplies the
literal directly.

## Minimal repro

```clausal
fine(DAYS, 20000) <- (DAYS >= 40)

Test("query as var")        <- (fine(50, F), F == 20000)   # FAILS — no solution
Test("literal given direct") <- fine(50, 20000)            # passes
```

Run: `cd /workspace/clausal && source venv/bin/activate && python -m clausal.testing todo/numeric_head_literal_repro.clausal`
(repro file saved alongside this note).

## Scope (what I confirmed)

| Head literal | ruled clause `head <- body`, queried as var | notes |
|---|---|---|
| **int** (`20000`) | **FAIL** (no solution) | any arg position: first / middle / last |
| **float** (`3.5`) | **FAIL** (no solution) | |
| double-quoted string (`"yes"`) | passes | |
| single-quoted atom (`'yes'`) | passes | `"yes" is 'yes'` also passes — the two quote forms unify in this build |
| int/float supplied directly as input | passes | so it's purely the output/var-binding direction |
| **bare fact** (`fine(50, 20000),`) queried as var | passes | bug is specific to *ruled* clauses |
| trivial body (`<- (DAYS is DAYS)`) | still FAILS | not caused by the guard goal |

So the trigger is precisely: **numeric (int/float) literal in the head of a `<-` clause, queried with a
variable in that position.** Textual literals are fine; bare facts are fine; input-mode is fine.

## Hypothesis

A numeric head literal looks like it's being compiled into an arithmetic/CLP context (treated as an
operand to evaluate/constrain) rather than as a plain term to unify with the caller's argument — so
nothing binds and the clause just fails to match in the var-query direction. Textual literals take the
ordinary unification path, which is why they work.

## Impact

- **Silent** — returns no solution rather than erroring, so it's easy to ship a rulebase that quietly
  drops valid answers depending on call mode. For a language sold as monotonic/sound this is a sharp edge
  even if some arithmetic interpretation is intended.
- Hits a very common rulebase idiom (a clause that returns a fixed numeric output under a guard, e.g. a
  capped fine, a fixed score, a fixed count).

## Workaround (already documented in the downstream consumer's cheat-sheet)

Bind numeric outputs in the **body**, not the head:

```clausal
fine(DAYS, FINE) <- (DAYS >= 40, FINE == 20000)   # works in all modes
```

This reads more relationally anyway. Textual-label outputs in heads are safe and need no workaround.
