# P3-3 Task 9 — reconciliation + perf gate

Branch `feat/p33-state-reloc`, base `1f86daf4`, HEAD `022208ba`.
This task is a GATE: measure and report. **No engine code was modified, and
nothing was committed** (see §5 for the one status note).

Bullets 1–3 of `task-9-brief.md` only. Bullet 4 (whole-branch final review) is
dispatched separately by the controller and is **not** covered here.

---

## §1 Reconciliation

### Command and extraction

Both runs used the exact form the prior gates used (read off `task-8-report.md`
§6 and its fix-round-1 gate block):

```
PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests \
    --continue-on-collection-errors -q -p no:cacheprovider -rfE
```

Run FOREGROUND, one at a time, never concurrently.

Names were extracted from the `short test summary info` section only, matching
`^(FAILED|ERROR) `, stripping the prefix and the trailing ` - <message>`,
`sort -u`. Before trusting it on new output, the extractor was **validated
against a known-good artifact**: replaying it over `task-8-fix1-full.txt`
reproduced `task-8-fix1-failed-names.txt` byte-for-byte (`cmp` exit 0, 145
names). Script: `scratchpad/extract.py`.

### Run 1

```
144 failed, 12389 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 102.48s (0:01:42)
```

Artifacts: `task-9-run1-full.txt`, `task-9-run1-failed-names.txt` (145 names).

```
cmp task-3-base-failed-names.txt task-9-run1-failed-names.txt   →  exit 0
```

### Run 2

```
144 failed, 12389 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 101.38s (0:01:41)
```

Artifacts: `task-9-run2-full.txt`, `task-9-run2-failed-names.txt` (145 names).

```
cmp task-3-base-failed-names.txt task-9-run2-failed-names.txt   →  exit 0
```

### Result

Both runs are **byte-identical** to `task-3-base-failed-names.txt` (145 names =
Task 0's normalized baseline + the `tests/test_clportools.py` collection ERROR).

**Name-diff = ∅**, which is exactly the accumulated inversion ledger through
Task 8 (EMPTY — every per-task gate from Task 1 through Task 8 fix round 1
produced the same 145-name set; controller ruling (2)). Nothing to cite against
R10/R11 or a task ruling, because nothing inverted.

The known wall-clock flake `test_F026_multi_star_splits_bounded_for_moderate_input`
did **not** appear in either run, nor in the baseline (`grep -c` = 0 in all
three files), so no single-file rerun was needed.

The `144 failed … 1 error` summary is 145 distinct identities once FAILED+ERROR
names are deduplicated — the same arithmetic Task 8 recorded.

---

## §2 Straggler sweep

`grep`/`ripgrep` over `clausal/` (not `tests/`) unless noted.

| pattern | expected | hits | file:line + verdict |
|---|---|---|---|
| `_pred_cls_for` | 0 | **0** | No hits anywhere in `clausal/`. Pinned by a test: `tests/test_predrow.py:533` `test_database_no_longer_has_pred_cls_for` asserts `not hasattr(Database, "_pred_cls_for")`. CLEAN. |
| `_dispatch_fn =` (assignment) outside the txn paths in `database.py`/`predicate.py` | 0 LIVE | **0 live stragglers** (7 assignment hits, all accounted for) | see the per-hit table below |
| `_clauses_source` writers | row-only | **1 live writer, row-routed** | see below |
| `_infer_module` cell reachability | comment-pinned at the site | **pinned, twice** | see below |
| `make_predicate(` in `specialization.py` — REDEFINED per controller ruling (1) as "0 UNBOUND mints" | 0 unbound | **3 mints, all bound** | see below |
| mirror-comment residue in `database.py` | 0 | **0 residue** (5 textual `mirror` hits, all deliberate or unrelated) | see below |

### `_dispatch_fn` assignments (`grep -rn "_dispatch_fn *=" clausal/`)

The gate is enforced at the ROW, not at the call site:
`PredicateMeta._dispatch_fn` (setter, `clausal/logic/predicate.py:918-920`)
forwards to `PredRow.dispatch_fn` (setter, `clausal/logic/database.py:233-263`),
which **raises `RuntimeError` when `self._txn == 0`** for a non-`None` install,
and routes `None` to `invalidate()`. So every class-side spelling in the tree is
gated whether or not its author remembered.

| file:line | verdict |
|---|---|
| `clausal/logic/compiler/predicate.py:2131` `pred_cls._dispatch_fn = fn` | LIVE, IN TXN. Inside `with ctx:` where `ctx` is `db.mutate(functor, arity, author=db.load_author(), kind="recompile", detail="install", through=pred_cls)` (or `pred_cls._mutate(...)` when `db is None`), lines 2124-2131. Not a straggler. |
| `clausal/logic/compiler_v2.py:350` `pred_cls._dispatch_fn = wrapped` | LIVE, IN TXN. Inside `with db.mutate(functor, arity, author=author, kind=WRITE_LOAD_DISPATCH, detail="table-wrap", through=pred_cls):` at line 345-347. Not a straggler. |
| `clausal/logic/builtins/_registry.py:483` `cls._dispatch_fn = dispatch_fn` | LIVE, IN TXN. Inside `with cls._mutate("builtin-registry", "recompile"):` (line 482) — the class's own private detached row, comment-pinned at 478-481. Not a straggler. |
| `clausal/logic/builtins/_registry.py:494` `cls._dispatch_fn = dispatch_fn` | LIVE, IN TXN. Same shape, `with cls._mutate("builtin-registry", "recompile"):` at line 493 (multi-arity arm). Not a straggler. |
| `clausal/logic/builtins/_registry.py:300` `self._dispatch_fn = dispatch_fn` | NOT THE SAME STATE. `BuiltinPredicate.__init__` — a plain instance attribute on an ordinary object, not a `PredicateMeta` class, so it never touches a row. Out of scope. |
| `clausal/logic/builtins/_registry.py:310` / `:314` `self._dispatch_fn = ...` | NOT THE SAME STATE. Same `BuiltinPredicate` instance attribute, lazily filled in `_get_dispatch`. Out of scope. |
| `clausal/logic/database.py:248`, `clausal/logic/predicate.py:761`, `clausal/logic/compiler/README.md:151` | COMMENT/DOC. Prose quoting the spelling; not assignments. Don't count. |

No `_dispatch_fn` assignment anywhere in `clausal/` reaches the state outside a
transaction. **0 live stragglers.**

### `_clauses_source` writers (`grep -rn "_clauses_source" clausal/`)

| file:line | verdict |
|---|---|
| `clausal/logic/predicate.py:126` `pred_cls._clauses_source = (module_name, module_source_path(module_dict))` | LIVE WRITE, ROW-ROUTED. Goes through the `_clauses_source` setter at `predicate.py:910-911`, which is `(cls._row or cls._detached_row()).source = value` — the row, not a class attribute. Compliant. |
| `clausal/logic/predicate.py:897` / `:910` | The property + setter themselves — the row-routing definition. Not a straggler. |
| `clausal/import_diagnostics.py:510` | READ only (`getattr(pred_cls, "_clauses_source", None)`). |
| `clausal/logic/predicate.py:569`, `:631`, `:723`, `:762` | Name-list entry / comments. Don't count. |

Exactly one live writer and it is row-only. **CLEAN.**

### `_infer_module` cell reachability (`grep -rn "_infer_module" clausal/`)

4 hits, all in `clausal/logic/solve.py` (756 = def, 703 = the only call site, 676
and 680 = the call site's docstring). Comment-pinned in **both** places:

At the call site, `_module_for_moduleless_solve`'s docstring
(`clausal/logic/solve.py:674-681`):

> "any other CELL goal has no module at all, and none can be guessed: a cell is
> a plain tuple, so there is no defining class to walk back to (which is what
> `_infer_module` does) and the tuple's functor is a bare name that any number
> of modules may define. Guessing here is exactly the module-locality bug this
> task exists to prevent, so the gap is REPORTED."

And at the definition itself (`clausal/logic/solve.py:762-767`):

> "LEGACY CUSTOMERS ONLY (P3-3 Task 6). A CELL goal never reaches here: a cell
> is a plain tuple with a bare-name functor, so there is no defining class to
> walk back to and any number of modules may define that name.
> `_module_for_moduleless_solve` refuses it with an `existence_error` naming the
> gap instead of guessing — see the module-locality rule R10."

Verified structurally, not just by comment: the sole call at line 703 is
preceded by the `if is_cell_goal:` block (line 684) which either returns via
`_strip_module_qualification` or `raise`s an `existence_error` — control cannot
fall through to line 703 with a cell. **PINNED.**

### `make_predicate(` in `specialization.py` — controller ruling (1)

3 hits, each guarded by `if pred_cls is None:` — the three `specialize_mi*`
entry points. Ruling (1) redefines the check as "0 UNBOUND mints": each mint
must reach `_install_specialized`, which row-binds through `db.mutate`.

| mint | binding line | verdict |
|---|---|---|
| `clausal/logic/specialization.py:428` (guard at 427) | `return _install_specialized(...)` at **:444** | BOUND. No `return`/`raise` between 428 and 444 (verified by grep over the span). |
| `clausal/logic/specialization.py:1443` (guard at 1442) | `return _install_specialized(...)` at **:1468** | BOUND. No `return`/`raise` in the span. |
| `clausal/logic/specialization.py:1781` (guard at 1780) | `return _install_specialized(...)` at **:1804** | BOUND. No `return`/`raise` in the span. |

`_install_specialized` (`clausal/logic/specialization.py:289`) does all of its
work inside
`with db.mutate(new_name, arity, author=author, kind=WRITE_LOAD_CLAUSES, detail="-specialize", through=pred_cls) as row:`
— the namespace binding, `_bind_row`, the clause write and the dispatch install
are all inside the transaction (Task 7, fix round 1 F5). **0 unbound mints.**

### mirror-comment residue in `database.py` (`grep -rn -i "mirror" clausal/logic/database.py`)

5 textual hits, **0 residue**:

| file:line | verdict |
|---|---|
| `clausal/logic/database.py:773` | `assertz` docstring: *"P3-3 Task 2: there is no longer a second clause store to mirror onto."* — a deliberate statement that the mirror is GONE, and why the class still sees the clause. Keep. |
| `clausal/logic/database.py:777` | Same docstring: *"(The deleted mirror was arity-BLIND: …)"* — the recorded reason the mirror was a bug. Keep. |
| `clausal/logic/database.py:796` (`asserta`) and `:809` (`retract`) | *"See `assertz` for why no class mirror is needed any more"* — cross-references to the above. Keep. |
| `clausal/logic/database.py:1190` | *"Mirrors `_normalize_dataclass_fact` but for structural args only"* — ordinary English usage about two parallel helpers, unrelated to the class/DB clause mirror. Keep. |

None describes live behaviour or an un-removed code path. **CLEAN.**

---

## §3 Perf gate

Full transcript: `.superpowers/sdd/p33-state-relocation/task9-bench.txt`.

### Trees

`git diff --stat 1f86daf4..HEAD -- '*.c' '*.h'` is **empty** — no C on this
branch — so the A/B is a pure-Python swap over shared `.so` artifacts, the
method of `task2-bench.txt` and `task4-bench.txt`.

- **base** `…/scratchpad/p33t9-basetree` — byte copy of the worktree's
  `clausal/` + `benchmarks/` + `tests/fixtures/` with the **18** files
  `git diff --name-only 1f86daf4..HEAD -- 'clausal/*.py'` lists reverted via
  `git show 1f86daf4:<path>`.
- **head** `…/scratchpad/p33t9-headtree` — the same copy, no reverts.

**Departure from Tasks 2/4, deliberately:** head is a copy rather than the live
worktree. The scratchpad is on `overlay`, `/workspace` is on `virtiofs`, and
`bench_struct_tabling` reloads the `.clausal` fixture *inside* the timed region —
so the old shape put a filesystem difference inside the measurement and charged
it to head. Run A below keeps the old shape as a cross-check; runs B/C are the
same-filesystem instrument.

The two trees were proven to differ in exactly those 18 files and nothing else
(recursive byte compare, `__pycache__` excluded): `differing files: 18` (all
expected), `only in base: none`, `only in head: none`, `TREES OK: True`.

Every sample runs in a **fresh process** that asserts both `clausal.__file__`
and `benchmarks.workloads.__file__` are under the tree it was told to measure
**before** running any workload (the 70x-wrong precedent), and echoes the
resolved path on its result line. Driver is interleaved with **alternating**
order (base-first on odd rounds, head-first on even).

**Gated statistic: median of the per-pair head/base ratios. > 1.03 fails.**

### Pair table

| bench | pairs | base median (s) | head median (s) | median ratio | verdict |
|---|---|---|---|---|---|
| `bench_struct_tabling(1500,3)` run A (head = live worktree, cross-shape) | 10 | 2.0442 | 2.0924 | **1.0254** (+2.54%) | PASS |
| `bench_struct_tabling(1500,3)` run B (same-filesystem) | 10 | 2.0552 | 2.0905 | **1.0194** (+1.94%) | PASS |
| `bench_struct_tabling(1500,3)` run C (same-filesystem) | 10 | 2.0465 | 2.0674 | **1.0141** (+1.41%) | PASS |
| `bench_fib(25)` (same-filesystem) | 10 | 3.3687 | 3.4002 | **1.0025** (+0.25%) | PASS |
| Task 2 spot §2 — QUERY half (3× `Nats(1500,_)`) | 10 | 2.0212 | 2.0316 | **1.0010** (+0.10%) | PASS |
| Task 2 spot §2 — LOAD half (3 loads) | 10 | 0.0246 | 0.0245 | **1.0126** (+1.26%) | PASS |

Per-pair ratio lists, raw seconds and stdevs are in `task9-bench.txt` §§1–5.

Three runs of the identical driver on identical code land at +2.54% / +1.94% /
+1.41% — a 1.1-point spread while nothing changes, against a base-side stdev of
0.019–0.031 s (1–1.5%). The arithmetic rules the residue out as real work: the
query half is 98% of the macro and moves +0.10%; the load half is 1.2% of the
macro and moves at most +1.3% of itself.

### Task 2/4 spot benches re-run at head

**Microbench (Task 2 §3), 3 alternating pairs, min of 5 × timeit(200 000):**

| read | base (ns) | head (ns) | delta | Task 2's figure |
|---|---|---|---|---|
| `cls._get_dispatch()` | 80.3 | 103.7 | +23 | +24 |
| `cls._get_dispatch(2)` | 101.1 | 126.6 | +26 | +26 |
| `cls._clauses` | 20.6 | 89.4 | +69 | +75 |

The load-bearing fact is the delta *between these two measurements, six tasks
apart*: Tasks 3–8 added nothing further to the per-read cost.

**cProfile call counts (Task 2 §4 / Task 4 §3) — decisive, counts don't drift:**

| profile | base | head | delta |
|---|---|---|---|
| QUERY `Nats(700,_)` total calls | 103 269 | 103 970 | **+701** |
| QUERY primitive calls | 100 269 | 100 970 | +701 |
| QUERY `dict.get` | 2 305 | 3 006 | **+701** |
| LOAD 10× `load_clausal_module` total calls | 320 926 | 325 256 | +4 330 (= +433/load) |
| LOAD `dict.get` | 9 250 | 9 660 | +410 |

700 subgoals, exactly +1 `dict.get` each — identical to `task2-bench.txt` §4,
i.e. **six further tasks added zero calls to the query path**. At 23 ns that is
16 µs of a 2.07 s run (0.0008%). The +433 calls/load is the mutation gate's
per-predicate transaction plus bake-in/specialization row work — compile time,
once per predicate per load, never per goal, and §2's load half prices all of it
at under 1.3% of a 1.2% slice.

### PASS/FAIL

**PASS.** Worst gated statistic anywhere: **1.0254** (+2.54%), on the
cross-filesystem run A; the two clean-instrument runs are 1.0194 and 1.0141, and
`bench_fib(25)` — the dispatch-densest macro — is 1.0025. All well inside the
>1.03-fails bar. No optimization performed or warranted; the C lever was not
reached for.

---

## §4 Toklex / scryer-reader status

Identified by `ls tests/ | grep -iE "toklex|scryer|reader|token"` (→ the
`tests/toklex/` package, 18 modules) plus `grep -rl -iE "toklex|scryer" tests/`,
which additionally names `tests/test_prolog_dialect.py` and
`tests/test_prolog_golden.py` (the reader/dialect suites) — the engine side is
`clausal/tools/toklex/` (there is no top-level `toklex` package; the tests import
`clausal.tools.toklex.*`).

**Untouched.** Both diffstats are empty:

```
git diff --stat 1f86daf4..HEAD -- clausal/tools/toklex tests/toklex          → (empty)
git diff --stat 1f86daf4..HEAD -- tests/toklex toklex clausal/toklex \
        tests/test_prolog_dialect.py tests/test_prolog_golden.py             → (empty)
```

**Green.** No name matching `toklex|prolog_dialect|prolog_golden|scryer` appears
in either run's failing set (`grep -c` = 0 in both
`task-9-run1-failed-names.txt` and `task-9-run2-failed-names.txt`), and run
directly:

```
pytest tests/toklex tests/test_prolog_dialect.py tests/test_prolog_golden.py
→ 574 passed, 2 warnings in 5.87s
```

(Hits for `toklex`/`scryer` also appear in `tests/audit_2026_07_05/test_11_modules_interop.py`,
`tests/test_hide_directive.py` and `tests/fixtures/docs/misc_phase7_sigs.txt` —
incidental mentions, not toklex suites; none is in either failing set either.)

---

## §5 Concerns

1. **Nothing committed, nothing modified.** `git status --porcelain` shows no
   staged or modified TRACKED files. It does list **8 untracked
   `todo/*.md` files** written by earlier tasks in this branch's session
   (timestamps 2026-09-05 22:42 through 2026-09-06 05:08, all predating this
   task). They are not mine, I did not touch them, and per the "never
   `git add -A` in the shared clone" rule they were left alone. Flagging so the
   controller decides whether Tasks 4–8 meant to commit them:
   `bare-zero-arity-predicate-body-goal-does-not-compile-2026-09-06.md`,
   `imported-atom-shadows-local-arity-n-predicate-at-call-site-2026-09-06.md`,
   `importer-without-dynamic-locks-shared-dynamic-predicate-for-its-owner-2026-09-05.md`,
   `listing-of-a-bare-atom-lists-only-arity-0-2026-09-06.md`,
   `mixed-apply-and-read-of-imported-dual-declared-atom-gets-the-class-2026-09-06.md`,
   `query-cache-keys-on-id-of-a-possibly-transient-module-2026-09-06.md`,
   `table-times-specialize-refusal-may-be-over-broad-2026-09-06.md`,
   `tabled-entry-dotted-walk-should-converge-on-resolve-module-2026-09-06.md`.
   The new files I created are the Task 9 artifacts only, all under
   `.superpowers/sdd/p33-state-relocation/` (`task-9-report.md`,
   `task9-bench.txt`, `task-9-run{1,2}-full.txt`,
   `task-9-run{1,2}-failed-names.txt`) — also untracked, as the prior tasks'
   artifacts were until their task commit.

2. **The macro's +1.4–2.5% is unexplained by any counted work, and I could not
   drive it to zero.** Three runs disagree with each other by 1.1 points on
   byte-identical code, the query half is +0.10%, and the call counts move by
   +701 on a 2.07 s run (16 µs). Every decomposition says "instrument", and the
   same pattern is on record in `task2-bench.txt` (+1.1% to +4.6% across four
   runs of one driver) and `task4-bench.txt` (-1.55% and +1.35%). But it is a
   consistently *positive* residue across all three of my runs and both of Task
   4's newer ones, so it is worth naming rather than declaring settled. It does
   not threaten the gate (worst case 2.54% vs a 3% bar), but a future task that
   adds even a small real cost on top will find the bar close.

3. **`bench_struct_tabling` reloads the fixture inside its timed region**, which
   is what let the base/head filesystem asymmetry leak into Tasks 2's and 4's
   A/Bs (both had base on `overlay`, head on `virtiofs`). Their numbers are
   still inside their bars, so nothing needs re-litigating, but the macro is
   ~1.2% load and ~98% query, and any future gate on it should either copy both
   trees to one filesystem (as done here) or gate on the query half.

4. **`BuiltinPredicate._dispatch_fn`** (`clausal/logic/builtins/_registry.py:300,
   310, 314`) is an instance attribute that shares its NAME with the gated
   metaclass property but not its state — it never touches a row and is not
   gated. Not a defect (the two are different objects and the builtin-instance
   path has no row to protect), but the shared spelling is exactly the kind of
   thing a future straggler sweep will re-flag. A one-line comment at line 300
   distinguishing it from `PredicateMeta._dispatch_fn` would retire the question
   permanently. Not done here — Task 9 is a gate and may not edit engine code.

5. **Bullet 4 of the brief (whole-branch final review) is NOT covered by this
   report** — per the dispatch it is dispatched separately by the controller. No
   subagents were used.
