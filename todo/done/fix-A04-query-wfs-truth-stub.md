**DONE — commit 433ca79e.** query_wfs identifies the goal's tabled entry, matches each result to a stored answer by normalized value, and reports TableEntry.truth_value(i) (True | undefined). Non-tabled stays True; composite goals keep True (min-truth deferred). Symmetric win reports undefined.

---

# fix(A04-F004): query_wfs hardcodes _truth=True — never reads table conditions

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F004
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF004QueryWfsStub` (xfail — flip to pass)

## Bug

`solve.py:596-621`: after collecting solutions, `query_wfs` loops
`r["_truth"] = True` over every result. `docs/wfs.md` §"The query_wfs API"
promises `True` | `"undefined"`. Symmetric win/move: both answers are
internally conditional (`TableEntry.truth_value(i) == "undefined"` — the
guard test proves the machinery knows) yet `query_wfs` reports `True`.
The in-tree test (`tests/test_wfs.py:486-502`) only covers a program
where every answer IS true, so the stub passes.

## Fix direction

After `solve()` completes, match each result against the relevant
`TableEntry.answers`/`conditions` to annotate truth:

- The goal's predicate + arity + variant key identify the entry;
  `truth_value(i)` for the matching frozen answer gives the annotation.
- Non-tabled goals: keep `True` (documented).
- Composite goals (conjunctions touching several tabled predicates) need a
  defined semantics — minimum: min-truth over the tabled conjuncts
  (True > undefined); document whatever is chosen.
- Blocked partially by A04-F003 (conditions may themselves be wrongly
  stuck undefined) — fixing the stub is still worthwhile: it makes F003
  *visible* to users instead of silently reporting True.

## Acceptance

- Symmetric win: `query_wfs(win(X), …)` returns two results with
  `_truth == "undefined"`.
- Asymmetric win (docs order): `win("a")` annotated `True`.
- `tests/test_wfs.py::test_query_wfs_*` stays green.
