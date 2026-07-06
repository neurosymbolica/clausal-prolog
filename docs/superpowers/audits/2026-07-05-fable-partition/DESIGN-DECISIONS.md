# Cross-cutting design decisions — 2026-07-05 audit

Append `resolved-by-user` and `open` design questions here as sessions
resolve them, so later sessions check here BEFORE asking the user again.

| ID | Status | Title | Decision + rationale | Raised by | Affects |
|----|--------|-------|----------------------|-----------|---------|
| A02-D001 | resolved-from-docs | Indexed dispatch must be semantics-preserving for every caller shape (uncomputable non-var key ⇒ all-clauses fallback, never the default bucket) | F095 fix history restored unify parity at the dispatch layer; indexing is threshold-triggered (≥4 clauses) so solution sets must not depend on clause count. See A02 design-questions.md | A02 | A02 arg_index/list_dispatch; A03 predicate.py always-fail defaults |
| A02-D002 | open — parked by user preference | Cross-type numeric index keys (Decimal/Fraction/complex ↔ int buckets) — blocked on A01-D001 (cross-type unification) | Recommendation: fallback-scan now (falls out of the A02-F001 fix); key-by-`numbers.Number` only if A01-D001 endorses Python `==` semantics. `todo/audit-2026-07-05/investigate-A02-parked-design-decisions.md` | A02 | A02 dispatch keys; A04 tabling keys; A01-D001 |
