# fix-A07: `_collect_bdd_var_ids` traverses shared BDDs as trees — exponential sat/sat_count

**Finding:** A07-F001 (`docs/superpowers/audits/2026-07-05-fable-partition/07-clpb-sat/findings.md`).
**Severity:** correctness/perf — CLP(B) is unusable beyond ~26 XOR-connected vars.

Both implementations of the var-id collector recurse into `high`/`low` with no
visited set, so a BDD *DAG* is walked once per root-to-leaf path:

- Python: `clausal/logic/clpb.py:540-546` (`_collect_bdd_var_ids`)
- C: `clausal/logic/_clpb_core.c:709-725` (`c_collect_ids_rec`)

An n-var XOR chain's BDD has 2n-1 nodes but 2^n paths. Callers hit on every
`sat` post (network merge at clpb.py:484 and `_propagate_forced` at 514),
every binding (`_bool_hook` at 698/713), and every `sat_count` (583).
Measured: `sat(X1^...^X24)` 4.6 s, xor-26 18.9 s, 4x per +2 vars; the pytest
guard runs xor-30 in a 5 s-budget subprocess.

**Fix:** add a `seen` set of node ids (Python) / a pointer-set or the
result-set-membership check (C: after `PySet_Add`, short-circuit when the vid
was already present AND the node pointer was seen — needs a separate seen set
keyed by node pointer, e.g. a temporary PySet of `PyLong_FromVoidPtr`).
While there, consider the same memoization for `_propagate_forced`'s
per-variable `restrict` sweep (it is O(vars x nodes) after the fix — fine —
but each `restrict` result is discarded; a single downward sweep computing
forced literals is O(nodes)).

**Test:** `tests/audit_2026_07_05/test_07_clpb_sat.py::TestSuspectedBugs::test_A07_F001_xor_chain_sat_not_exponential`
(xfail strict=False — flip to plain assert once fixed).
