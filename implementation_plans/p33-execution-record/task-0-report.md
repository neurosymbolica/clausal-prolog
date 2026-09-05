# Task 0 report — baseline + anchor sweep

Measurement only. No commits, no production-code edits. Ledger untouched (controller-owned).

## Baseline run

Worktree: `/workspace/clausal-bug-fix/.claude/worktrees/p33-state-reloc`, HEAD `d3cfe27a` (feat/p33-state-reloc, plan commit).
Command: `/workspace/clausal/venv/bin/python -m pytest tests/ --continue-on-collection-errors --tb=no -q -rf`, run in foreground (99.75s), full output in `baseline-full.txt`, sorted failure names in `baseline-failed-names.txt`.

Summary line (verbatim):
```
144 failed, 12058 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 99.75s (0:01:39)
```

The "1 error" is the known pre-existing ortools collection error that `--continue-on-collection-errors` is required to survive (per memory baseline note); no traceback surfaced with `--tb=no`/`-rf` since it isn't a failed test.

### Family breakdown (144 failed names)

- 76 — `tests/fixtures/ortools_*.clausal` + `tests/fixtures/pysat_boolean.clausal` (solver-dependency skips presenting as failures)
- 6 — `tests/fixtures/first_class_constraints.clausal` (same solver-dependency family, ortools/pysat/cpsat)
- 59 — `tests/test_clpsat.py` + `tests/test_clportools_lp.py` (`ImportError: P...` — same solver-dependency family)
- 1 — `tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks`
- 2 — `tests/fmt/test_corpus.py::test_the_corpus_is_not_empty` + `tests/rewrite/test_corpus.py::test_the_corpus_is_not_empty` (the known worktree-artifact: `.claude/worktrees/...` path makes the corpus self-skip, per the plan's Global Constraints)

141 solver-dep + 1 doc-snippet = 142, matching the clone-root baseline family from memory; +2 corpus-path names = 144 total, exactly the brief's expected ~144. Passed count (12058) is somewhat below the brief's "~12,100+" estimate but this tracks with the corpus self-skip removing ~1570 collected items from two directories; not treated as anomalous given the failure-name-set match is exact in both count and composition. No C17-perf flake appeared this run (it's described as an intermittent flake in memory, not expected every run).

**Run executed — confirmed.**

## Anchor sweep

Full table in `task-0-anchors.md`. Highlights:

- 20 of 23 listed anchors HOLD at the exact brief-given line (or line range).
- 3 anchors MOVED by small offsets (1-27 lines), consistent with "branch base includes the R1-revised commit": mutators (:740-771→:738-770), `_get_dispatch` (:800-811→:777-817), `register_signature` (:166→:167), mirror blocks (:93-160→:93-~155), `head_key` (near :517-541→def at :544, explicitly a grep anchor).
- 1 anomaly, not a MISSING/BLOCKED: **`add_clause`** — no such name exists anywhere in `clausal/logic/database.py`'s git history. The line range given (:345-366) lands on `Database.define_predicate` (:335-364), which does the described job (assertz a compiled Clause + register its signature). Recording this as the intended anchor under a different name; flagging for controller confirmation.
- No anchor is MISSING. No BLOCKED condition.

## Anomalies

1. Passed-count is 12058 vs. brief's "~12,100+" — explained by corpus self-skip; not investigated further since failure-NAME-set match is exact.
2. `add_clause` anchor name does not exist in the codebase or its history; `define_predicate` at the given vicinity is functionally equivalent (see anchors doc). Needs controller sign-off that this is the intended target before later tasks reference it by that name.
3. Anchor 20's "4th `make_predicate|make_atom` grep hit" resolves to the import statement at specialization.py:26, not a second call site — there is no `make_atom` reference anywhere in that file.
