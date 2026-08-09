# BUG: sequential solve() queries on one loaded module accumulate state → later queries lose/duplicate solutions

> **PARTIAL FIX 2026-06-24** — one real contributor fixed; two distinct issues remain. Status below.
>
> ## Contributor #1 — dif constraint growth not trailed  →  FIXED (commit f59c41a0)
> A second+ `dif` constraint on a variable was appended to the attribute list
> *in place* without trailing (`PyList_Append` in `_constraints_dif.c`,
> `list.append` in `constraints.py`). On backtrack the append survived, leaving a
> stale disequality on any variable that outlived the query → accumulates across
> queries on a long-lived module. Fixed by replacing the in-place append with a
> trailed `put_attr(v, DIF_KEY, existing + [pair], trail)` (shared `attach_dif_pair`
> helper covers both `dif()` and the propagation hook). Repro leak dropped
> 27 → 19/1836. Unit tests: `tests/test_dif.py::TestDifBacktracking`.
>
> ## The repro metric conflates two different failures
> `seq_leak_repro.py` flags any query whose result ≠ gold. But several flagged
> cases are **wrong even as the FIRST query on a freshly loaded module** — they
> are *not* sequential accumulation at all. Verified: `diversity_2_test_30`
> returns `['no','no']` on a fresh single-query load. The true accumulation set
> (correct fresh, wrong sequential — e.g. `diversity_1_test_192`) must be measured
> by diffing fresh-load vs sequential, not by comparing to gold
> (`classify_leaks.py`).
>
 > ## Remaining issue #2 — duplicate verdicts are a RULEBASE non-determinism, NOT an engine bug
> Fully traced (`probe_*.py`). `diversity_2_test_30 → ['no','no']` on a fresh load,
> and **both tuples are identical** `('no','not_met','not_complete',['strawbridge'])`
> — a true duplicate from jurisdiction clause 2 alone. The `amount_satisfied`
> theory was wrong: `amount_label` is single-valued (`['not_met']`). The duplicate
> comes from `diversity_fail_cites → diversity_defeated(test_30, ['strawbridge'])`,
> which **succeeds twice with identical bindings**, because defeater clause D3a is
> `same_state_pd(CASE), CITES is ["strawbridge"]` and **`same_state_pd` is an
> existence test written as an enumerable goal** — it has 2 witnesses for test_30
> (two same-state P–D pairs), so it yields twice. Standard Prolog semantics: a
> goal with 2 solutions yields 2 times. **This is the rulebase author's bug**
> (wrap the defeater existence-tests in `once/1`, or make them semidet), and a
> false positive in the repro's gold-comparison metric — not the engine, not the
> sequential accumulation. The other "duplicate-solution" leaks are almost
> certainly the same class (existence tests enumerating multiple witnesses).
>
  > ## Audit of all generated `finally` sites (for the same GeneratorExit bug class)
> After fixing #3, audited every `finally` the compiler emits into *generated*
> (suspendable) code:
> - **head-match per-clause `finally: trail.undo`** (`head_match.py`) — was the #3
>   bug. **FIXED.**
> - **catch/3** (`_compile_catch_impl`) — **SAFE**: `finalbody=[]`; the
>   `trail.undo` lives inside the `except Exception` handler, and `GeneratorExit`
>   is a `BaseException`, not `Exception`, so it isn't caught and no undo runs on
>   close.
> - **setup_call_cleanup/3 & call_cleanup/2** (`_compile_setup_call_cleanup`) —
>   **HAS A RELATED BUG** (distinct, lower severity, niche builtin). Its
>   `finalbody=[<run Cleanup goal>, reraise]` runs the Cleanup goal on
>   `GeneratorExit`. When the Call is non-deterministic and the choicepoint is cut
>   (`once`/`\+`), the generator is abandoned and Cleanup is **deferred to
>   generator close (GC)** instead of running promptly at the cut. Confirmed:
>   after `once(setup_call_cleanup(True, in_(X,[1,2,3]), Cleaned is 99))`,
>   `Cleaned` is unbound — cleanup did not run. Unlike #3 this does *not* truncate
>   the trail (it appends cleanup bindings), so it doesn't corrupt the search; the
>   defect is **cleanup timing** (runs late, at GC, on whatever trail the stale
>   generator frame holds) — which defeats the point of a resource-cleanup
>   predicate. Not fixed: the correct fix is broader — `once`/`\+`/if-then-else
>   should *close* the sub-generators they abandon (so cleanup runs promptly at
>   the cut and nothing is left for GC). That also removes the engine's remaining
>   reliance on GC timing. Flagged as a follow-up.
>   **Update (investigated):** close-on-commit is NOT a localized change. The
>   committed-choice constructs do abandon a generator (`once`/`\+` break out of
>   their drive loop), but `.close()`-ing that generator does NOT cascade to the
>   nested clause/SCC generators — the trampoline's StepGenerators form reference
>   cycles (a child's `proceed`/`fail` point back at the parent), so the nested
>   generators survive the close and are only finalized when cyclic GC collects
>   them. Verified: adding `once_gen.close()` leaves `setup_call_cleanup`'s cleanup
>   still un-run (`Cleaned` unbound). Making cleanup deterministic would require
>   breaking those StepGenerator cycles or adding a cascade-close to the C
>   trampoline — a substantial change. Given the #3 correctness bug is already
>   fixed (skip-undo) and the residual is only SCC cleanup *timing* (niche, no
>   search corruption), deferred.
> - Other `finally` blocks (`predicate.py`, `compile_ctx.py`) are **compile-time**
>   only (`_pop_position()`, restoring `tro_plan`/globals) — not generated code.
>
> ## Issue #3 — the actual residual accumulation (lost solutions)  →  FIXED
> **Root cause: a GC-triggered trail corruption.** Confirmed by `gc.disable()`
> eliminating all flips, and a tight repro: repeating one query
> (`jurisdiction(diversity_1_test_192)`) on one module flips correct→`[]`→correct
> at reps 67/92/131 with GC on, **0 flips with GC off**. Per-clause head-match
> compiled to `_mark = trail.mark(); try: <body with yields> finally:
> trail.undo(_mark)`. When such a generator is an **abandoned choicepoint**
> (suspended at a yield after `once`/`\+` committed past it) and the GC reclaims
> it mid-query, CPython throws `GeneratorExit` and the `finally` runs
> `trail.undo(_mark)` — **truncating the live trail back to an old mark and
> destroying the in-flight search's bindings** → lost solution (and, elsewhere,
> spurious duplicates). Reproduced in isolation in ~15 lines.
> Fix (`head_match.py` `compile_head_to_match_case`): skip the undo when the
> generator is being closed — `except GeneratorExit: _closing=True; raise` +
> `finally: if not _closing: trail.undo(_mark)`. An abandoned choicepoint's
> bindings are reclaimed by the enclosing mark/undo (or discarded with the
> per-query trail), never by this finally. After the fix: 2000 repeats → 0 flips;
> GC-on 300 reps → 0 wrong (was ~10). Note: the only `finally: trail.undo` site
> is per-clause head-match; once/findall/negation use explicit post-loop undos
> (safe). (catch/3 has a `finally` that runs a recovery goal — a separate, not-
> yet-audited concern, not exercised here.)
>
> ### (superseded) earlier framing of #3
> The TRUE accumulation is the **lost-solution** cases (got `[]`) that are correct
> on a fresh load (e.g. `diversity_1_test_192`). Mechanism: `jurisdiction` returns
> `[]` only if clause 2 fails → `not complete_diversity` fails → `complete_diversity`
> wrongly **succeeds** → which requires `diversity_defeated` to wrongly **fail**.
> `diversity_defeated` uses `dif`/negation, so residual attributed-variable state
> (a second source beyond the dif-list append fixed in #1) flips it after a few
> hundred queries. This is the real remaining bug; reproducing it needs the
> accumulation (hundreds of preceding queries), so it is harder than #2. Next:
> hunt the second non-trailed/at-query-end-not-reset attributed-variable mutation
> (candidates: nested-negation interaction with the dif hook re-attachment, or a
> var that outlives the query carrying a constraint that the end-of-query trail
> unwind doesn't reach).
>
> ## Net assessment (after all fixes)
> The reported "≈25 leaks" tangled three different things. Repro now: **10/1836**
> (was 27), and the remaining ones are the #2 rulebase duplicates.
> - **#3 — GC-triggered trail truncation** (commit 9b0c5398): the dominant engine
>   bug. A `finally: trail.undo(_mark)` in an abandoned clause choicepoint
>   generator fired by `GeneratorExit` when GC reclaimed it mid-query, wiping the
>   live search's bindings. This IS the "sequential accumulation" — GC fires more
>   as a long-lived process accumulates garbage. Fixed; lost-solution flips gone
>   (repeat-one-query: 6→0 over 2000; GC-on 300 reps: 10→0 wrong).
> - **#1 — dif constraint append not trailed** (commit f59c41a0): a second, real
>   accumulation contributor. Fixed.
> - **#2 — duplicate verdicts**: rulebase non-determinism (`same_state_pd` and
>   peers are existence-tests that enumerate multiple witnesses); deterministic,
>   reproduces on a fresh load, fixable only in the rulebase (`once/1`). Not an
>   engine bug; a false positive in the gold-comparison metric. These are the
>   ~10 that remain.
>
> Repro helpers added: `bisect_leak.py` (reset-mode bisect — ruled out the query
> cache and the tabling leader stack), `classify_leaks.py`, `probe_test30.py`.
>
> ---
> *Original report follows.*

**Reported 2026-06-24.** Found scoring an external benchmark's diversity calibration. This is the **residual after the
`_query_cache` fix** — a *different* mechanism: the cache bug returned a wrong *value*; this one **drops or
duplicates whole solutions**. High severity: it silently corrupts any long-lived multi-query harness (the
normal test/scoring shape), and it is **non-deterministic** (the affected set varies run to run).

## Symptom

Load a module once, then run many **independent** top-level `solve()` queries against it (each a distinct
ground goal). After a few hundred queries, some queries that have exactly **one** correct solution instead
return **`[]`** (solution lost) or the **same solution twice**. The *same* query is correct when it is the
first query, or when run on a freshly loaded module instance. The leak does **not** come from the facts
coexisting in one DB (a single query against the all-facts module is correct) — it comes from **repeated
querying** of one loaded module.

## Self-contained repro

`todo/seq-leak-repro/` (no external deps beyond clausal):
- `diversity_all.clausal` — a real rulebase (cut-free §9901 diversity engine: negation + `is not`/dif +
  disjoint defeater clauses) with 1836 case fact-blocks baked in.
- `query_order.json` — the 1836 `(case_id, expected_verdict)` pairs.
- `seq_leak_repro.py` — loads the module **once**, queries each case sequentially, reports leaks, then
  re-queries each leaked id as the **first** query on a **freshly loaded** module (the control).

```
cd /workspace/clausal && source venv/bin/activate
python todo/seq-leak-repro/seq_leak_repro.py
```

Observed (`repro_output.log`; counts vary run-to-run — 22–25 typical):
```
Sequential queries on ONE loaded module: 25 / 1836 leaked
  lost-solution (empty []): 15   duplicate-solution: 10
    diversity_1_test_92  gold no -> got []
    diversity_1_test_99  gold no -> got []
    diversity_2_test_30  gold no -> got ['no', 'no']
Control — each leaked id as the FIRST query on a freshly loaded module:
    diversity_1_test_92  -> fresh-first: ['no'] (gold no) OK
    diversity_1_test_99  -> fresh-first: ['no'] (gold no) OK
    ... (all leaked ids correct when loaded fresh)
```

## Scope (what isolates vs not)

- **Fresh module instance per query (unique module name) — ISOLATES.** Verified separately: 100 sequential
  cases via fresh `_load_module` each show **0** leaks. (So the earlier scorer claim that "fresh module per
  case still leaks" was the *old* `_query_cache` bug, now fixed; post-fix, only the shared-loaded-module
  sequential-query path leaks.)
- **One OS process per case** — isolates (trivially).
- **Single query on the all-facts module — correct.** Coexisting facts are not the trigger; repeated
  querying is.
- A **2-party synthetic** (negation + `is not` only, 4000 sequential queries) did **not** reproduce — the
  trigger needs the fuller rulebase structure (multiple disjoint defeater clauses + dif + negation), so the
  accumulating state is likely tied to choicepoint/trail/attributed-variable (dif) handling, not plain NAF.

## Impact

Any harness that loads a rulebase once and queries it many times (every multi-case oracle / test suite)
can silently **under-count** (lost solutions read as abstentions) or **double-count**. My calibration
scorer hit exactly this: `fast_score.py` reported 1818/1836 with "18 abstentions"; per-fresh-load the true
score is **1836/1836** — the 18 were this leak, not a rulebase gap.

## Likely cause (tentative — prior mechanism guesses here were wrong, treat as a hint)

Trail / choicepoint / attributed-variable (dif) state not fully reclaimed between independent top-level
queries on a long-lived `Module`; it accumulates until it perturbs negation/dif evaluation a few hundred
queries in. Non-determinism suggests order/heap-dependent residue rather than a deterministic cache key.

## Workaround (in use)

Fresh `_load_module` per query (unique module name) — fully isolates in testing — or one OS process per case.
