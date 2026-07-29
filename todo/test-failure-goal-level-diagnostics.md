# Bug: a failing Clausal test reports only its NAME — no goal, no expected, no actual

**Reported:** 2026-07-29, from the clausify formalizer-training harness
**Severity:** high — this is the single biggest blocker to automated repair.

---

## STATUS: FIXED — all three stages landed (2026-07-29)

All of stage 1 (failing goal index + source + line), stage 2 (bindings) and
stage 3 (nearest solution) are implemented in `clausal/testing.py`; tests in
`tests/test_testing_diagnostics.py`.  Kept in `todo/` rather than `todo/done/`
only because of the open items listed at the bottom.

### New output

The motivating example now reports (real output, from a fixture reproducing
the report's shape):

```
FAILURES:
  long.clausal:9 :: public interface resolves on the parallel_below_threshold fixture
    goal 2 of 2 failed:
      amlr_bo_chain_assess('parallel_below_threshold',
                           amlr_bo_chain_verdict(not_beneficial_owner, _EFFECTIVE_OWNERSHIP_BPS, _CITATIONS))
    bindings at failure: (none from goal 1)
    the predicate DID have a solution, which did not unify (argument 2 differs):
      amlr_bo_chain_assess('parallel_below_threshold',
                           amlr_bo_chain_verdict(beneficial_owner, 2500, [cite(amlr_art52_1)]))

1 tests: 0 passed, 1 failed [FAILED]
```

Format, line by line:

* `  <relpath>:<line> :: <description>` — was `  <relpath>::<description>`.
  `:<line>` is omitted when the clause has no source position (e.g. `<load>`
  failures, `assertz`-ed tests), giving `  <relpath> :: <description>`.
  An erroring test keeps its ` — <error>` suffix on this line.
* `    goal <i> of <n> failed:` (or `raised:`), then the goal's **source
  text**, wrapped at top-level argument commas with continuations aligned
  under the open paren when it exceeds 96 columns.  For `raised`, the
  exception line follows.
* `    bindings at failure: NAME = VALUE, ...`, or one of
  `(none — goal 1 is the first goal)` / `(none from goal 1)` /
  `(none from goals 1..k)` / `(unavailable — …)`.
* `    the predicate DID have a solution, which did not unify (argument N
  differs):` followed by the goal re-rendered with that argument replaced by
  what was actually computed (and the goal's other variables instantiated to
  their live bindings).  Alternatives when there is no near miss:
  `the predicate has no solution for ANY arguments at this point (…)`,
  `the predicate has solutions, but none within one argument of this goal —
  two or more arguments differ`, or
  `no solution (this conjunct is not a predicate call, …)`.
* `    note: …` lines for every degradation (budget exceeded, recursion limit,
  diagnostic unavailable, database mutated by the re-run, conjunct cap hit,
  re-run disagreed with the verdict).

Unchanged: the `N tests: X passed, Y failed [STATUS]` summary line, the
`[NO TESTS]` paths, `-v` per-test lines, and the exit codes (0/1/2).
Passing tests produce byte-identical output to before.

### How it works

`run_file` calls `run_test(..., diagnose=True)`; on failure only,
`diagnose_failure` re-runs the test's clause body:

1. Locate the `Test/1` clause by description (`db.clauses_for("Test", 1)`);
   `clause.position[0]` is the line number.
2. Source text comes from `clausal.reflection.reify_file` +
   `render_source` — the reified-term→source renderer, not a hand-rolled
   printer and not `visualize.predicate_to_source`.  The reified clause is
   matched to the runtime clause **by source position**, and only accepted
   when the conjunct counts agree, so a mis-association is impossible; it
   falls back to `clausal.terms.term_str` otherwise.
3. Execute cumulative prefixes `body[:1]`, `body[:2]`, … (`And`-chained,
   driven by `clausal.logic.solve.solve`).  The first prefix with no solution
   names the failing conjunct; the first that raises names a raising one.
4. Re-establish the prefix, and with its bindings live read them off the
   runtime `Var`s.  Source variable *names* come from walking the runtime goal
   and its reified twin in lockstep (`_pair_vars`), which aborts rather than
   guess if the two shapes diverge.
5. Nearest solution: re-run the failing goal with one argument replaced by a
   fresh `Var` (positional args first, then keyword args), take the first
   solution, and splice the computed value back into the *reified* goal for
   rendering.  Whole-argument generalisation is strictly more general than
   generalising anything inside that argument, so a failed whole-argument
   probe rules out every deeper one — the search is linear in arity.  If no
   single argument explains it, one all-arguments-free probe distinguishes
   "two or more arguments differ" from "unsatisfiable at all".

Runtime→reified conversion for step 5 (`_reify_value`) is the missing inverse
edge: `reify_*` maps *source* to reified terms, but a value computed at run
time has no source.  It covers scalars, lists, tuples, dicts, atoms
(`PredicateMeta` classes), `Compound`, `KWTerm` and predicate-term instances,
and raises on anything else rather than emitting text that does not mean what
it says.

### Bounds and degradation

* Wall-clock budget per failing test, default 10s, `$CLAUSAL_TEST_DIAG_BUDGET`
  to override.  Enforced two ways: a coarse deadline check between steps, and
  a `SIGALRM` watchdog that interrupts a wedged probe.  The watchdog exception
  is a `BaseException` subclass on purpose — an `Exception` could be absorbed
  by an `except Exception` somewhere in the solver and be misread as "no
  solutions", which is the one misdiagnosis that must not happen.  Where
  `SIGALRM` is unavailable (Windows, non-main thread) only the coarse check
  applies.
* Conjunct cap `DIAG_MAX_GOALS = 64`; term-depth cap `DIAG_MAX_DEPTH = 40`.
* One solution per probe — never enumerates.
* Every failure mode becomes a `note:` line.  **The diagnostic never changes a
  verdict**: `passed` is decided before it starts, and if the re-run finds a
  solution for every conjunct (non-determinism, or state the first run
  changed) it says so instead of inventing a culprit.

Note on the report's `RecursionError` concern: the trampoline's
`except RuntimeError` is narrowed to PEP-479 `StopIteration` wrappers
(`clausal/logic/trampoline.py:243`), so a genuine `RecursionError` does
propagate rather than looking like exhaustion.  It is caught and noted anyway.

### Side-effect exposure (measured, documented, partially mitigated)

The re-run executes real goals, so `assertz`/`retract` and I/O in a test body
**do run again**, and the cumulative-prefix walk executes conjunct *i* once per
prefix containing it — an `assertz` in goal 1 of an n-conjunct test can be
applied up to n extra times.  There is no transactional rollback for a logic
database, so this cannot be fully avoided.  Mitigations applied:

* `stdout`/`stderr` are captured and discarded during the re-run, so `write/1`
  noise cannot re-appear in (or corrupt) the report a gate parses.
* The module database's clause count is compared before and after; a change is
  reported as
  `note: the diagnostic re-run changed the database (+N clause(s)) — this test
  has side effects` rather than silently absorbed.
* Diagnostics are **opt-in** (`run_test(..., diagnose=True)`).  `conftest.py`'s
  pytest integration calls `run_test/2` and is unaffected.

### Not done / open

* The pytest plugin (`conftest.py`) still reports only
  `test(...) failed (no solutions)`; wiring `diagnose=True` into
  `ClausalItem.runtest` would give the same detail under `pytest`.
* Nearest-solution search generalises **one argument at a time** at the top
  level.  When two or more arguments differ it reports that fact but shows no
  term.  A minimal-generalisation refinement (shrink back into the argument to
  the smallest sub-term that still admits a solution) was deliberately not
  built — the whole-argument form is what the report asked for and is harder
  to get subtly wrong.
* Bindings are reported for variables in the goals *before* the failing one.
  Variables first introduced by the failing goal itself are not listed (they
  are unbound by definition).
* An infinite loop in a test body still hangs the *original* run — that is
  pre-existing and out of scope here; the bound added covers only the extra
  diagnostic work.

---

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
