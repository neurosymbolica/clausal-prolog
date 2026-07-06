# investigate(A12-F001): tabled answer replay discards dif/CLP(FD) constraints — pick a sound semantics (Opus)

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md` A12-F001
**Tests:** `tests/audit_2026_07_05/test_12_seams.py::TestF001TablingReplayDropsConstraints` (2 xfail — flip to pass)
**Design:** A12-D001 (parked) — store-residue vs refuse-to-table vs document

## Bug

`-table(td/1)` with `td(X) <- (X is not 1)`:

- **First** query `td(X)`: the answer var carries the dif attr (sound).
- **Second** identical query replays the table: the answer var has NO dif
  attr, and `unify(Y, 1)` then succeeds — `td(1)` is now "provable" even
  though the body constrains `X is not 1`. Same shape with
  `in_domain(X, 1, 3)`: the FD domain is gone on replay.
- Identical queries returning semantically different answers breaks
  monotonicity — the second answer set is a strict superset of the first's
  meaning.

The stored answer is the normalized skeleton (`tabling.py` `add_answer` /
`_normalize_for_key` path); attributes never make it into the table, and
replay builds plain fresh vars.

Note the converse direction is CORRECT and regression-pinned: a
*caller*-constrained var filters replayed answers through its hooks
(`TestTablingReplayRespectsCallerConstraints`).

## Investigation

1. Decide semantics (A12-D001): (a) SLG(C)-style — store constraint residue
   per answer, re-post on replay; (b) refuse to table answers carrying
   attrs (clear error); (c) document. Recommendation: (b) as stopgap, (a)
   folded into the `investigate-A04-slg-completion-architecture.md` rework
   where answer representation is already on the table.
2. Survey which attr families can reach answers today: dif (A05), FD
   (A06), CLP(B) (A07); CLP(Q/R)/Z3/ortools have no hooks yet (A08-F013) —
   the chosen contract must anticipate them.
3. Check interaction with A04-F005 (unhashable answers) — the answer
   representation fix should solve both.

## Acceptance

- Both xfail tests flip (or, under option (b), are rewritten to assert the
  explicit error) and first/second queries agree.
