# investigate(A04-F001): SLG completion cannot resume consumer continuations — answers silently lost [Opus]

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F001
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF001CompletionLosesConsumers` (4 xfail — flip to pass)

## Bug

When a tabled consumer suspends before the answers it needs exist, the
leader's completion phase (`tabling.py:507-543`) resumes the consumer's
generator, but:

1. The consumer's **parent chain is dead** — the original dispatch
   generator `_gen` already yielded DONE, so any clause-continuation yield
   routed upward hits an exhausted generator.
2. The interception arm `gen is sc._proceed and value is None` freezes
   `sc.args` — the consumer's *call args*, which after unifying a stored
   answer just reproduce that answer. The clause body AFTER the recursive
   call never executes, so the completion phase can never derive anything
   new. Completion is effectively a no-op answer-wise.
3. Cross-predicate: an inner leader (mutual recursion) marks itself
   `complete` when its own dispatch exhausts, even though it has a
   consumer suspended on an outer, still-evaluating table — premature
   completion with a permanently-cached wrong (empty) answer set. No SCC
   tracking exists.

Confirmed consequences (all silent wrong answers, no errors):

- Facts-first, TWO recursive clauses (idiomatic!): `p(X)` = `[1,2,3]`,
  expected `[1,2,3,4,5]`.
- Recursive-clause-first: `p(X)` = `[1]`.
- Mutual recursion rec-first: `ra(1,Y)` = `[2]` (expected `[2,4]`), `rb`
  cached complete-empty (expected `{1,3}`).

In-tree fixtures pass only because one-recursive-clause + facts-first
reaches fixpoint during the LIVE phase (the consumer iterates
`entry.answers` while it grows).

## Why investigate, not fix

The defect is architectural: correct SLG completion requires either
(a) keeping the derivation context of suspended consumers alive (the
dispatch generator must not be exhausted before completion — restructure
the leader to interleave), (b) re-running the consumer's *clause* from
scratch against the grown answer set (answer-subsumption-safe re-derivation,
XSB-style local scheduling), or (c) SCC-aware completion: entries complete
only when their strongly-connected component of dependent subgoals has
reached global fixpoint (needs a dependency stack). Option (c) is the
textbook fix and also gives F003/D004 the structure they need.

Related: A04-F008 (orphaned-consumer suspend misread as solution) becomes
unreachable if completion/abandonment are fixed; keep its root-driver fix
anyway (defense in depth).

## Acceptance

- All four F001 xfails flip to pass; facts-first mutual control stays green.
- `tests/test_tabling.py`, `test_slg_termination.py`, `test_wfs.py` stay green.
- New invariant test: tabled solution sets are clause-order-independent
  (permutations of the F001 fixture agree).
