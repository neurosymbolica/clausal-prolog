# An answer is not reported last through catch/3, an if-then-else with an else, setup_call_cleanup/3 or a tabled call

Filed 2026-10-24, with the determinism signal (`solve_with_last`,
CONTINUATION_TCO_PLAN Phase 4). Not a correctness bug: these answers report
`last=False` (unknown), so a top-level asks `;` and then prints `false.`
where Scryer prints the full stop. Soundness is unaffected.

## What / Repro

`tests/iso/test_last_answer_scryer.py` pins each against Scryer:

| Query | Clausal | Scryer |
|---|---|---|
| `catch(member(X, [a,b]), _, true)` | `p p` | `p f` |
| `(member(X, [a,b]) -> true ; true)` | `p` | `f` |

and, not in that table: `setup_call_cleanup/3` (its cleanup runs only at
exhaustion, never at a deterministic exit), a tabled predicate (its answers
come from a table), `time_goal/1` (it reports after exhaustion), the
lambda library's `\X^G` calls, and goals behind a goal boundary whose
woken goal had answers of its own.

## Why each is conservative

- **catch/3**: the compiled `try` has an `except` that answers (the
  recovery goal); `compiler/final_yields.py` leaves an answer under any
  handler other than the `GeneratorExit` bookkeeping non-final. The
  recovery can only run if the protected goal raises when resumed, which
  a FINAL goal does not, so the handler could be allowed when every answer
  inside is itself final.
- **if-then-else with an else**: after the then-branch's answer comes
  `if not _ite_taken: <else>`, which the pass does not prove dead (the flag
  was set True on the path to the answer).
- **setup_call_cleanup/3**: ISO runs Cleanup when Goal exits
  deterministically. Forwarding FINAL would let the cleanup run at the
  deterministic exit instead of at exhaustion -- an observable change in
  when a side effect happens. Needs a ruling: run cleanup at the
  deterministic exit (ISO, Scryer) or keep it at exhaustion.
- **tabled calls**: the wrapper yields its table's answers; FINAL could be
  emitted for the last answer of a completed table.
- **first-argument exclusion** covers only the first argument and heads
  whose key is static (`compiler/predicate.py` `_later_clauses_excluded`);
  Scryer's indexing is per argument.
