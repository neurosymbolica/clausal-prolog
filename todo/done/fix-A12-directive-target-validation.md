# fix(A12-F003): `-table` (and sibling directives) with a dangling target is a silent no-op

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md` A12-F003
**Tests:** `tests/audit_2026_07_05/test_12_seams.py::TestF003DirectiveTargetValidation` (2 xfail — flip to pass)

## Bug

- `-table(zzz_no_such_pred/2)` in a module that never defines that
  predicate: loads without any diagnostic.
- `-table(reach/3)` where only `reach/2` is defined: loads clean and
  `reach/2` runs UNtabled — a diamond-graph query returns duplicate
  answers, and left-recursive predicates regain their infinite-loop risk.

A one-character typo in a `-table` target silently forfeits the
termination/dedup guarantees the author explicitly asked for. This audit
lost half a probe-session to exactly this (a fixture renamed `walk/2` →
`reach/2` while the directive still said `walk/2`).

Family of A10-F012 (malformed directive silently ignored) — but these
directives are WELL-formed; it is the target that dangles, so the fix is
different: end-of-load validation, not parse-time validation.

## Fix direction

At module-load completion, check every `-table`/`-dynamic`/
`-discontiguous` (and any other name/arity-targeted directive) resolved to
a defined predicate with matching arity; raise a load error naming the
directive, the target, and any near-miss (same name, different arity).
Forward declaration stays legal — the check runs after all clauses are
collected. `-dynamic` with zero clauses is legitimate ISO usage and must
NOT error once A12-F005 is fixed — for `-dynamic`, "defined" includes
"minted by the directive itself".

## Acceptance

- Both xfail tests flip: undefined target and wrong-arity target are
  load errors.
- Existing suites still pass (no directive in-tree currently dangles —
  verify, then fix any that do).
