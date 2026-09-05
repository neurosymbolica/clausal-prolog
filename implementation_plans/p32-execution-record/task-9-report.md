# Task 9: whole-suite reconciliation + perf gate — evidence report

HEAD at start: `aac9895acd873442bddbc898cfaee55dcccd238c` (Tasks 0-8 + 2C complete).
Branch base for A/B: `5bcd66ec8293896db79572e0743a5f4a0fc54b66` (verified via
`/workspace/clausal-bug-fix/.git/HEAD` -> `ref: refs/heads/main` and
`/workspace/clausal-bug-fix/.git/refs/heads/main` = `5bcd66ec8293896db79572e0743a5f4a0fc54b66`;
read via `cat`, not `git`, per the worktree-isolation sandbox rule that blocks git
commands targeting the parent clone).

## 1. Reconciliation — two consecutive full-suite runs

Command (both runs, foreground):
`/workspace/clausal/venv/bin/python -m pytest tests/ --continue-on-collection-errors --tb=no -q -rf`

Transcripts: `task9-full-run-1.txt`, `task9-full-run-2.txt`.

Run 1 summary line:
```
144 failed, 12053 passed, 56 skipped, 37 xfailed, 747 warnings, 1 error in 95.49s (0:01:35)
```

Run 2 summary line:
```
144 failed, 12053 passed, 56 skipped, 37 xfailed, 747 warnings, 1 error in 94.47s (0:01:34)
```

Failure-name sets: `diff` between run 1 and run 2's `FAILED ...` name lists (test id only,
error-message suffix stripped) is **empty** — identical failure sets both runs.

Diff of run 1's names against `baseline-failed-names.txt` (also suffix-stripped): the only
line-level difference is
`tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input`,
present in baseline (145 names) and absent from both task-9 runs (144 names) — this is the
ledgered C17-perf flake, which **passed** in both task-9 runs. Modulo that flake, run-1 ==
run-2 == baseline **exactly**. Reconciliation: **CLEAN**.

## 2. Straggler sweep

| Pattern | Hits | Disposition |
|---|---|---|
| `tagged_terms\|TAGGED_TERMS` | ~60 across tests/, implementation_plans/, docs/directives.md, clausal/logic/cells.py:146, clausal/logic/compiler/globals_env.py:385, clausal/import_hook.py:404, benchmarks/workloads.py:220 | All expected-historical: test module docstrings/comments narrating the retired `-tagged_terms` bridge, the `tests/tagged_terms_support.py` / `test_tagged_terms*.py` module+file names (kept as parity-anchor filenames per plan), `tests/fixtures/*_tagged.clausal` prose comments and filenames, `docs/directives.md`'s "### -tagged_terms (removed)" section, and `implementation_plans/*.md` historical plan docs. No live directive parsing, no live identifier named `TAGGED_TERMS_FLAG`/`_TAGGED_TERMS_STACK` remains (confirmed separately below). **No stragglers.** |
| `TAGGED_TERMS_FLAG` as a live identifier | 0 (the only source hit, cells.py:146, is inside a comment sentence, in backticks, narrating history) | Expected-historical (tombstone comment). |
| `-tagged_terms` in `.clausal` fixtures (live directive line, not a `#` comment) | 0 | Clean — grepped for `-tagged_terms` outside `#`-prefixed lines in `tests/fixtures/*.clausal`; every hit is prose inside a `#` header comment. |
| `_charlist_to_str_or_none` | 2 (test_class_C15 docstring; `list_dispatch.py:217` comment) | Both are comment/docstring references to the historical name, not a live definition (`grep 'def _charlist_to_str_or_none'` = 0 hits). Expected-historical. |
| `cell_functor_for_instance` | 0 | Clean. |
| `cell_functor_for_name(.*scope` | 0 | Clean. |
| `is_data_functor` | 1 (`terms_to_ast.py:221`, inside the "(The class-shaped data-functor gate... is DELETED.)" tombstone comment block) | Expected-historical — documents the T2 deletion, no live reference. |
| `TAGGED_TERMS_FLAG` (identifier form) | see above | 0 live. |
| `own-module\|own module` in compiler comments | 1 (`tabled_naf.py:28`: "An `-import_from`-ed callee is tabled only in its OWN module's db") | Not a straggler — this is about **tabling** module-scoping (an unrelated feature/topic), not a leftover claim about strict-atoms declaredness-per-module. No live incorrect claim found. |
| `_SIMPLE_AST_NODE_NAMES` | 2 (`compiler_v2.py:954`, `:969`) | Both are docstring narration of Task 8's fix-round-1→2 history ("`_SIMPLE_AST_NODE_NAMES` is deleted: it is fully redundant..."); `grep '_SIMPLE_AST_NODE_NAMES ='` / a live definition = 0 hits. Expected-historical, matches the brief's "2 known docstring narrations" exactly. |

**No live stragglers found.**

## 3. Adjacent suites (untouched-green)

- `tests/toklex/` (includes `test_reader_corpus.py`, the scryer-corpus-driven reader
  integration test — Task 6 of the toklex formalism plan, running the full reader stack
  over the real Scryer Prolog library source corpus): `423 passed, 2 warnings in 4.94s`.
  (Transcript: `task9-toklex-run.txt`.) These tests are also part of the `tests/` root
  suite and show zero `FAILED toklex` lines in both reconciliation runs.
- `packages/clausal-scryer/tests/` (the separate scryer-**backend** package — ISO
  conformance translation tests, a different subsystem from the toklex reader): **not
  collectible** in this venv — `ModuleNotFoundError: No module named 'clausal.scryer'`.
  This package lives outside `tests/`, is not part of the baseline gate, and its
  `clausal/scryer/__init__.py` exists on disk but isn't importable from this venv (no
  editable install wiring it in — a pre-existing, unrelated environment gap, not
  something this branch touched or broke; not treated as a defect of this task).

## 4. Perf gate — interleaved A/B, branch base vs HEAD

### Defect found and worked around (reported, not silently fixed)

The parent clone (`/workspace/clausal-bug-fix`, base commit `5bcd66ec`) has a **stale
Python bytecode cache** under `tests/fixtures/__pycache__/` (and possibly elsewhere)
that makes `bench_struct_tabling` crash deterministically —
`AttributeError: 'str' object has no attribute 'T'` — when invoked as an ordinary
fresh-process import (`sys.path` explicitly rooted at the parent clone, matching how a
real caller would use it), independent of `n`/`reps` (reproduced down to `n=10`).
Root-caused by tracing the `cons`-chain walk: the terminator that should be the `nil`
0-arity-atom **class** (`type(nil) is PredicateMeta`, confirmed) instead surfaces as the
bare Python string `"nil"` partway through the tabling-answer copy, so `node is nil`
never fires and the walk falls off the end into `"nil".T`. Confirmed as a stale-cache
artifact, not a real base-commit behavior bug: redirecting bytecode caching away from the
parent's on-disk cache via `PYTHONPYCACHEPREFIX=<scratch dir>` (zero writes to the parent
clone) makes the identical call succeed correctly (`bench_struct_tabling(10, 1) == 10`,
`bench_struct_tabling(1500, 3) == 1500`). This is a pyc-cache-staleness hazard of the same
class as the "check the parent's `.so` files are current" caution in the brief, just on
the Python side — **flagging as a defect for the controller** (the parent clone's
`tests/fixtures/__pycache__` should be considered untrustworthy for ad-hoc invocation
until cleared/regenerated); worked around here via `PYTHONPYCACHEPREFIX`, no writes made
to `/workspace/clausal-bug-fix`.

Both base and HEAD runs used `PYTHONPYCACHEPREFIX` pointed at separate scratch
directories, for consistency and to guarantee zero incidental writes to either clone.

### Method

- Driver: `/tmp/claude-1000/.../scratchpad/bench_driver.py`, invoked as a fresh process
  per (round, role): asserts the marker (`'clausal-bug-fix' in clausal.__file__ and
  'worktrees' not in clausal.__file__` for base; `'p32-cell-flip' in clausal.__file__`
  for head), then times one call each of `bench_fib(25)` and
  `bench_struct_tabling(1500, 3)` via `time.perf_counter()`.
- `cwd=/workspace/clausal-bug-fix` for base (with `sys.path.insert(0, os.getcwd())` inside
  the driver, since bare-script/`-c` invocation does NOT put `cwd` on `sys.path` by
  default — confirmed this matters: without it, imports silently fall back to an
  unrelated third `clausal` install living at `/workspace/clausal` via that venv's
  `__editable__.clausal-0.4.0.pth`).
- `cwd=/workspace/clausal-bug-fix/.claude/worktrees/p32-cell-flip` for head.
- 5 rounds, interleaved base→head→base→head→...→base→head (10 process invocations, 5 of
  each role). Full transcript with both marker assertions visible in every round:
  `task9-bench.txt`.

### Results (seconds; head/base ratio = gate metric; PASS threshold: no ratio > 1.03)

| Bench | base min | base median | head min | head median | head/base (min) | head/base (median) | Gate |
|---|---|---|---|---|---|---|---|
| bench_fib | 3.3898 | 3.4254 | 3.3655 | 3.4071 | 0.9928 | 0.9947 | PASS (flat, within noise — expected, fib doesn't touch cell representation) |
| bench_struct_tabling | 4.1837 | 4.2375 | 2.5375 | 2.5693 | 0.6065 | 0.6063 | PASS — **WIN**, ~39% faster on HEAD |

Raw per-round values in `task9-bench.txt`. bench_struct_tabling's ~0.606 ratio is in the
same ballpark as the plan's cited Phase-2 spot-check expectation (walker-heavy B/A =
0.561) — not identical (different harness/hardware/run), but the same order of
magnitude and clearly a win, not a regression. **Gate: PASS, no regression on any
metric.**

## 5. Defects found

1. **Parent-clone stale `__pycache__` (Python bytecode cache staleness hazard)** — see
   §4 above. Made `bench_struct_tabling` crash deterministically when invoked outside the
   full pytest harness against `/workspace/clausal-bug-fix`. Worked around via
   `PYTHONPYCACHEPREFIX` for this task's measurements (no parent-clone writes). Root
   cause not fully diagnosed beyond "stale bytecode cache under
   `tests/fixtures/__pycache__` disagreeing with the currently-loaded engine" — flagging
   for the controller to decide whether/how to clear it (a `find ... -name __pycache__
   -exec rm -rf` in the parent, or a `.pyc`-cache-invalidation check in
   `load_clausal_module`/the import hook, if this can recur for other callers of the
   parent clone).
2. No suite-reconciliation defects (empty diff, both runs identical).
3. No live stragglers (all hits historical/expected per the table in §2).
4. No perf-gate defects (both benches pass; bench_struct_tabling is a clear win).

## Files

- `.superpowers/sdd/p32-cell-default-flip/task9-full-run-1.txt`,
  `task9-full-run-2.txt` — reconciliation transcripts.
- `.superpowers/sdd/p32-cell-default-flip/task9-toklex-run.txt` — adjacent-suite
  transcript.
- `.superpowers/sdd/p32-cell-default-flip/task9-scryer-run.txt` — packages/clausal-scryer
  collection-error transcript (environment gap, not a defect of this branch).
- `.superpowers/sdd/p32-cell-default-flip/task9-bench.txt` — full interleaved A/B
  transcript with both marker assertions.
