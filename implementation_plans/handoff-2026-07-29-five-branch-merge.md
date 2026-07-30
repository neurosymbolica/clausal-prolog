# Handoff — 2026-07-29 — five verified branches awaiting merge

Written because the session that produced these ran out of context. Everything
needed is on the branches, in the commits, and in `todo/`. Nothing is only in
the previous session's head. Read §6 (pitfalls) before running anything — most
of it is about verification that *looks* green and isn't.

---

## 0. Done — 2026-07-30

All five merged to `main` in the recommended order and synced. **The handoff is
closed; §§1–7 below are the record of how, not work outstanding.**

| # | merge commit | branch |
|---|---|---|
| 1 | `20e95b46` | `fix/var-shaped-predicate-name` |
| 2 | `fe2aa7a1` | `fix/package-segment-nonidentifier-diagnostic` |
| 3 | `3f3cc6c5` | `fix/renderer-completeness-comparechain-setliteral` |
| 4 | `f501f223` | `fix/tabling-wrapper-survives-recompile` |
| 5 | `a05020d9` | `perf/const-list-membership-frozenset` |

- **Clone suite green after every merge**, one at a time: `10520 → 10534 →
  10550 → 10605 → 10617 → 10664` passed, with only the pre-existing
  doc-snippet failure standing. 145 new tests (14+16+55+12+48), all passing;
  the `F026` flake failed in the last full run and passed alone (3.02s against
  a 3.0s threshold), which is the whole of the `+144`-vs-`+145` gap.
- **One interaction, found by the per-merge gate**, not by the branches:
  merge #2's intermediate-segment test imported `[G]`, and merge #1's new
  refusal rejects an ALL-CAPS `-import_from` name at load time, preempting the
  import failure the test asserts. #1's refusal is right; the name was
  incidental and is `[Gber]` now, folded into `fe2aa7a1` so `main` is green at
  every commit. Merging in the other order would have hidden it until later.
- **Doc-snippet violations: 28, same 28**, only line numbers moved
  (`directives.md:314→328`, `import.md:318/373/389 → 354/409/425`).
- **Domain suites green against the merged tree**, and against the *merged*
  tree specifically — the §6 `PYTHONPATH` trap was avoided with throwaway
  `*_branch.sh` copies kept in the firb dir (since removed) and confirmed by
  `print(c.__file__)` plus the presence of `const_set` and `_install ->
  Callable`. `au/firb` 46+27+32+18 with 4/4 controls load-bearing, ALL GREEN;
  `us/sara_irc_tax` 41/41.
- **`/workspace/clausal` fast-forwarded to `a05020d9`**, working tree now
  identical to the clone. Failure *set* diffed, not the count: **142 before,
  the same 142 after**, `10308 → 10453` passed. `--ignore=tests/test_clportools.py`
  is required or collection aborts and *no tests run at all* — the first
  attempt captured one `ERROR` line and nothing else.
- **§6 gets a new entry: under pytest, cwd beats `PYTHONPATH`.** Running the
  clone's `tests/test_tabling_lifecycle.py` with `PYTHONPATH=/workspace/clausal`
  reported 12/12 green — from the *clone's* `clausal`, because pytest prepends
  its rootdir. A red-green gate built that way passes both halves and means
  nothing. Copying the test into the canonical tree and running it there gave
  the real answer: **7 of 12 fail** without the fix, matching §2's 7/12. That
  run also dumped a 512MB `core`, so on pre-fix code the lost-tabling
  left-recursion does not merely hang, it can take the interpreter down.
- Five merged branches and the five dead `worktree-agent-*` branches deleted
  with their worktrees. `fix/imported-functor-clause-destruction` and its
  worktree are **kept, unmerged**, per §5.

---

## 1. What already landed and is synced

Three merges went to `main` in `/workspace/clausal-bug-fix` and were
fast-forwarded into `/workspace/clausal`:

| commit | what |
|---|---|
| `ea0a6282` | arity-mismatch diagnostic + the `_dispatch_at` protocol repair |
| `6cce910c` | atoms-vs-strings docs correction (`docs/syntax.md` had a false claim) |
| `ea317aae` | `_LazyHookFinder.find_spec` infinite recursion |

**`/workspace/clausal` is at `ea317aae`. The clone's `main` is at `64d376b2`**
(one todo-only commit ahead — `todo: file the two findings left open by today's
merges`). That commit is docs/todo only, so the gap is harmless, but a sync is
owed either way. `main` is ~47 commits ahead of the `local/main` remote; nothing
has been pushed.

## 2. The five branches to merge

All five were produced by subagents from untriaged todos, then verified by the
main session (red-green + reproduction + suite). Order below is the recommended
merge order: lowest blast radius first, compiled-output changes last.

| # | branch | commit | what it fixes | verification done |
|---|---|---|---|---|
| 1 | `fix/var-shaped-predicate-name` | `d5b9abf3` | `P(a,1)` + a body mentioning `P` crashed at load with `TypeError: 'AttVar' object is not callable`; now a load-time `SyntaxError` naming both lines | reproduced both sides; red-green 9/14; blast radius **0 hits** across suite + 767 corpus files + 346 repo files (measured by logging instead of raising) |
| 2 | `fix/package-segment-nonidentifier-diagnostic` | **`0de17d7e`** | a dotted import failing on a non-identifier directory (`eu/state-aid` for `eu.state_aid`) produced **no diagnostic at all**; now names the segment, the directory and the rename | reproduced both sides; red-green 12/14; Fable-reviewed → merge-with-fixes; **FIX 1 already applied** in `0de17d7e` (was `4eb45974`) |
| 3 | `fix/renderer-completeness-comparechain-setliteral` | **`fea842b2`** | renderer refused CompareChain, SetLiteral, Await/Yield, None/bytes/Ellipsis — and, after FIX 2, also renders ListComp/SetComp/DictComp/GeneratorExpr | red-green 32 fail on revert, then 19/19 for FIX 2; Fable-reviewed → merge-with-fixes; **FIX 2 applied** in `fea842b2` (was `76ed9a40`) |
| 4 | `fix/tabling-wrapper-survives-recompile` | `0a0341c7` | **correctness bug**: an `assertz` into a tabled predicate replaced `tabled_dispatch` with the raw fn, turning a terminating left-recursive query into an infinite hang | hang reproduced independently on `main` (exit 124) and shown fixed; red-green 7/12 |
| 5 | `perf/const-list-membership-frozenset` | `47e3f58d` | `X in [c1, c2, …]` compiles to a set — 8.9× at 4 atoms, 302× at 64, flat in list length | semantics compared main-vs-branch byte-identical for order, duplicates, `1 in [1.0,1]`; corpus green |

Each branch is checked out in its own worktree under
`.claude/worktrees/agent-*` — see `git worktree list`. They are branched off
`main` at `64d376b2` or earlier; #4 and #5 may need `git merge main` first.

House merge style is `--no-ff` with a message whose subject names the fault
concretely and whose body explains why *that* seam. Read `git log` for voice.

## 3. After merging #4 and #5 — run the domain suites

These two touch dispatch and compiled output respectively, which is exactly what
the corpus gold suites are sensitive to. The others don't need it.

```
cd /workspace/clausify-domains/au/firb && ./run_tests.sh      # expect ALL GREEN, 4/4 controls load-bearing
cd /workspace/clausify-domains && PYTHONPATH=/workspace/clausify/kit:/workspace/clausify \
  /workspace/clausal/venv/bin/python -m clausal.testing us/sara_irc_tax/tests/test_public_interface.clausal
```

`au/firb` = 46+27+32+18 tests; `sara_irc_tax` = 41. Both were green today
against `main` and against branches #4 and #5 individually.

## 4. Baselines — do not trust a count without them

| tree | baseline |
|---|---|
| clone (`pyenv 3.13.3`, `PYTHONPATH=<tree>`) | **`1 failed, 10520 passed, 136 skipped, 44 xfailed`** at `64d376b2` |
| `/workspace/clausal` with its own venv | **142 failed**, ~10300 passed |

- The single clone failure is `tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks`
  — pre-existing, fails everywhere, 28 violations. If you add docs prose, diff
  its violation list before/after and confirm only line numbers moved.
- The canonical tree's **142** failures are pre-existing solver-environment
  breakage (55 `test_clpsat`, `test_clportools_lp`, `pysat_boolean` fixtures) plus
  a collection error in `tests/test_clportools.py`
  (`NameError: _CpSolverSolutionCallback`, needs `--ignore`). The clone shows 1
  only because its pyenv lacks the solver packages. **Diff the failure set, never
  the count.**
- `test_F026_multi_star_splits_bounded_for_moderate_input` is a known timing
  flake (3.68s vs a 3.0s threshold on a loaded box) and fails on pristine `main`.
  Re-run it alone before blaming a change.

Run the clone suite with:

```
PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/ -q -p no:randomly
```

The clone's own venv lacks pytest.

## 5. Loose ends

**Both Fable-review fixes are applied.** (Agent `aedd8c6af0fe8dbf3`, which was
still running when the first draft of this handoff was written — the table in §2
now carries the final shas.)

- **FIX 1 — `0de17d7e`.** `_misnamed_path_entry` documented that a
  correctly-spelled entry anywhere on the search path aborts the scan, but
  checked per-directory, so a misnamed entry in an earlier `sys.path` dir beat a
  correct one in a later dir — producing *wrong rename advice*, the exact failure
  the branch exists to prevent. Now two passes over one set of listings: sweep
  the whole path for a correct spelling first. Also softened `_prefix_target`'s
  overclaiming sentence to "the segment 'b' did not resolve, so neither can
  'a.b.c'" — the segment is a fact from the exception and the rest an
  entailment, so it is true whoever raised. Same 78-column single line, so the
  `_KNOWN_UNCOMPILABLE` fence numbers do not shift.
- **FIX 2 — `fea842b2`.** The `RENDER_EXCLUSIONS` justification for the
  comprehension entries ("does not compile — NameError on the loop var") was
  **false when the loop variable collides with a declared atom**: `-private([x])`
  with `Sq(L, M) <- (M is [x * x for x in L])` imports, runs and yields a
  solution. Rather than just correct the reason, the agent **implemented
  rendering** for ListComp/SetComp/DictComp/GeneratorExpr and dropped those four
  exclusions, having checked that every reachable surface round-trips (filters,
  multiple for-clauses, nesting, `async for`, and atom/dotted-atom/logic-var/`_`
  targets). Two refusals kept on house precedent: empty `clauses`, and a tuple
  target (unparses bare, which `EmbedTransformer` rejects). `ForClause` stays
  excluded with a corrected reason. The false reason was corrected in all three
  places it had been recorded.

Still open from FIX 2's neighbourhood, recorded in the slice/ellipsis todo: the
tuple-target `AssertionError`, and the missing diagnostic for a logic variable
used as a comprehension loop variable.

One count note, since it looks like a discrepancy and is not: FIX 1's run
reports `1 failed, 10536 passed` against a `10533` reference. The reference run
had **two** failures — the doc-snippet one *and* the F026 flake. Here F026
passed, so +1 from that and +2 from FIX 1's new tests. FIX 2's `10575` is
`10556 + 19` exactly.

**`fix/imported-functor-clause-destruction` (`ec6bf7bf`) — do NOT merge.** Open
user decision, and a defect: see
`todo/imported-clause-refusal-misattributes-ownership.md`. It reads clauses its
own earlier load deposited on a shared imported class as the *exporter's*
declaration, so a second load of identical source refuses and the message names a
module that declared nothing. Order- and process-state-dependent. Domain suites
pass against it and structurally cannot see it (they load each module once per
process). The open question — whether Clausal should grow a `-multifile` opt-in —
would not fix this case.

**Five `worktree-agent-*` branches** are dead scaffolding (all at `64d376b2`);
delete with `git branch -d` after removing their worktrees.

## 6. Pitfalls that cost the last session real time

**The domain scripts silently defeat `PYTHONPATH`.** `au/firb/run_tests.sh:18`
builds `PYTHONPATH="…:/workspace/clausal:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"`
— canonical comes *before* anything inherited — and
`au/firb/negative_controls.sh:27` overwrites `PYTHONPATH` outright from a
hardcoded `CLAUSAL=/workspace/clausal` (line 20). **Setting `PYTHONPATH` and
getting ALL GREEN tells you about canonical `main`, not your branch.** This
produced a false ALL GREEN today. To test a branch, replicate the script's
`python -m clausal.testing` calls with the worktree first and
`/workspace/clausal` omitted, or `sed` the one `PYTHONPATH=` line into a
throwaway copy kept *in the firb dir* (the script needs `$0`-relative `HERE`).
Always confirm with:

```
python -c "import clausal.logic.compiler_v2 as c; print(c.__file__)"
```

**`git checkout` inside a worktree can fail on a dubious-ownership check** while
`git -C <worktree> checkout` works. A silently failed revert makes a red-green
gate report GREEN for both halves. Check the revert actually happened.

**`git stash push -- <paths>` creates nothing when the tree is clean**, so a
stash-based red-green gate is a no-op. Use `git checkout main -- clausal/`
instead, and restore with `git checkout HEAD -- clausal/`.

**A hang looks like success.** `timeout 25 python x.py | tail` reports `tail`'s
exit status, and buffered stdout is lost on SIGKILL — so an infinite loop
presents as *empty output, exit 0*. Use `python -u`, redirect to a file, and read
`$?` with no pipe.

**Fresh worktrees lack the gitignored `.so` files.** Copy them from
`/workspace/clausal-bug-fix` or `build_ext --inplace`; commit nothing from that.

**`.clausal` syntax traps** hit repeatedly while writing probe fixtures:
a clause body with a conjunction must be parenthesised (`h <- (a, b),`); no
trailing `.` (that's Prolog); `=<` and `\+` are invalid (use `<=`, `not`, and
parenthesise `not` after an operator); a 0-arity predicate is **not iterable
from Python** (`p()` raises `'PredicateMeta' object is not iterable` — give it a
dummy argument); undeclared atoms need `-private([a, b])` under strict atoms; and
a predicate named for a Python builtin (`ord`) fails with
`TypeError: ord() takes no keyword arguments`.

## 7. Todos filed today, not fixed

- `imported-clause-refusal-misattributes-ownership.md` — blocks the branch above
- `lazy-stub-accumulates-duplicates-on-meta-path.md` — stub reinstalls itself;
  the merged recursion guard is per-instance
- `dynamic-declared-arity-not-used-by-the-arity-diagnostic.md`
- `higher-order-meta-call-wrong-arity.md` — maplist/foldl/include still leak the
  old message (16 sites)
- `same-name-two-arities-silently-merge.md`
- `cross-module-tabled-naf-loses-wfs-delay.md` (split out of the tabling work)
- `slice-and-ellipsis-in-clause-body-crash-with-notimplementederror.md`
- **`unify-failure-pays-two-attributeerrors.md`** — a *failing* `unify()` costs
  957 ns vs 117 ns succeeding; 792 ns is two discarded `AttributeError`s from
  `__unify__` lookups on both operands. Failing unifications are the common case
  in search, so this is a much wider win than the membership optimization that
  found it. **Probably the highest-value item on the list.**

## 8. One observation about the backlog

Of the five untriaged todos worked today, **three had a wrong premise**: the
finder one pointed at the wrong location (and the real fault was worse — no
diagnostic at all), the renderer one named two non-gaps and missed six real ones,
and the unit/quantity one blamed the wrong subsystem entirely (it is
`_is_logic_var_name`, nothing to do with the SI parser). A fourth was filed as a
lifecycle/perf gap and is a correctness bug (the hang). Reproduce before
implementing, and treat the todo's stated mechanism as a hypothesis.
