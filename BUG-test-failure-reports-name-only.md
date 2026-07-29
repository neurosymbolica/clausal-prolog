# Bug: a failing Clausal test reports only its NAME — no goal, no expected, no actual

**Reported:** 2026-07-29, from the clausify formalizer-training harness
**Severity:** high — this is the single biggest blocker to automated repair.

## Symptom

A test module with 13 tests, one failing, produces **150 characters of output in
total**:

```
FAILURES:
  test_public_interface.clausal::public interface resolves on the parallel_below_threshold fixture

13 tests: 12 passed, 1 failed [FAILED]
```

That is the complete output. It does not say:

- which **goal inside the test body** failed
- what the failing goal **expected**
- what it actually **got** (or that it simply found no solution)
- any binding values at the point of failure

The test in question asserts two goals:

```clausal
Test("public interface resolves on the parallel_below_threshold fixture") <- (
    amlr_bo_chain_subject("parallel_below_threshold"),
    amlr_bo_chain_assess("parallel_below_threshold",
        amlr_bo_chain_verdict(not_beneficial_owner, _EFFECTIVE_OWNERSHIP_BPS, _CITATIONS))
)
```

Either goal could be the failure, for any of several reasons.

## Why it matters

This harness has an LLM author a domain and repair it against gate output. The gate
output *is* the entire repair signal. "Test named X failed" is close to no signal:
the author must guess which conjunct failed and why, with no observation of the
actual computed verdict.

Measured impact — Qwen3.6-27B authoring `eu/aml/amlr_bo_chain`, phase P3b:

| attempt | result |
|---|---|
| a0 | undeclared atoms `eligible`, `ineligible`, `true` — **named, fixed next round** |
| a1 | undeclared atoms `entity`, `holdings`, `person` — **named, fixed next round** |
| a2 | maximum recursion depth exceeded on a fixture — **located, fixed next round** |
| a3 | `12 passed, 1 failed` — **not actionable** |
| a4 | identical |
| a5 | identical (stall detected) |
| a6 | identical (stall detected) → phase blocked |

The contrast is the evidence: every error that **named its subject** was fixed on
the following attempt. The one that named only a test consumed four attempts with
byte-identical output and blocked the run at 12/13 passing. Diagnostic quality, not
model capability, was the binding constraint.

## Requested fix

On assertion failure, report the first goal that could not be satisfied, with the
bindings established up to that point:

```
FAILURES:
  test_public_interface.clausal:55 :: public interface resolves on the parallel_below_threshold fixture
    goal 2 of 2 failed:
      amlr_bo_chain_assess("parallel_below_threshold",
                           amlr_bo_chain_verdict(not_beneficial_owner, _EFFECTIVE_OWNERSHIP_BPS, _CITATIONS))
    bindings at failure: (none from goal 1)
    the predicate DID have a solution, which did not unify:
      amlr_bo_chain_assess("parallel_below_threshold",
                           amlr_bo_chain_verdict(beneficial_owner, 2500, [cite(amlr_art52_1)]))
```

Priority order, if it needs to be staged:

1. **Which goal failed** (index + source text) and the **line number** — cheap, and
   on its own would likely have unblocked the run above.
2. **Bindings established** before the failing goal.
3. **Nearest solution**, when the predicate is satisfiable but did not unify with
   the asserted pattern. This is the one that turns a guess into a fix: it shows
   `beneficial_owner` where `not_beneficial_owner` was asserted.

## Interim mitigation (harness side)

`clausify`'s `gate_load` now echoes the **source of each named failing test** into
the repair prompt (commit in `clausify-executor-train`, `auto/gates.py`
`_failing_test_sources`). That tells the author what is being asserted, but still
not which goal failed or what was actually computed — the information simply does
not exist in the runner's output. It is a workaround, not a fix.

## Related

- `BUG-unattributable-functor-field-mismatch.md` — same class: an error with no
  location or subject, unrepairable by an automated author.
- Precedent: the `-module` arity error was changed to print the offending directive
  text, which turned a 3-attempt dead end into a 1-attempt fix.
