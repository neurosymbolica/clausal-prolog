# Engine lane handoff — 2026-09-21, P2: Tasks 5–9. ONE BLOCKER LEFT

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**.
Tip at the time of writing: see `git log -1`. 0 behind `main` (`bd774c46`).
**Nothing has landed in C** — main and branch C are identical.

Rooms: `/tmp/claude-1000/-workspace-clausal-bug-fix/823f67d2-.../scratchpad/{kwwt,mainnow}`,
12 `.so` each, venv symlinked. Package downstream checks: see the todo named below.

## Gates, all re-run today

* **House run: 146 failed, 16729 passed, 50 skipped, 40 xfailed, exit 1.
  Extraction 146 = summary 146. NEW 0 / GONE 0 vs main.**
* **Packages: NEW 0 / GONE 0 across all 12**, 11 with real summaries;
  clausal-yaml HANGS identically on both sides.
* **Spec §7 exit numbers**, loading the 37 `tests/fixtures/docs` fixtures:
  live term INSTANCES **534 -> 0**; `PredicateMeta` classes 574 -> 574,
  unchanged BY DESIGN (the class is the predicate handle until P4).

## THE ONE BLOCKER

**The aliased-`assertz` change is the only thing between this branch and a
merge, and it is NOT done.** The ruling (adoption wins) is taken; the
implementation needs ONE more decision.

`todo/aliased-assertz-loses-the-owner-under-cells-2026-09-20.md` now carries
the full account: the chain (the write's home comes from the CLASS via
`_find_pred_cls` -> `_home_db`, and `_find_pred_cls`'s identity leg used
`type(head)`, which under P2 is `tuple` — that leg is dead), **four routes
tried and exactly how each failed**, and the knot:

> `gate_alias_user.clausal` declares BOTH `-dynamic(bo_p/1)` AND
> `-import_from(..., [alias(bo_p, AliasS)])`. "Ignore a local `-dynamic` on an
> imported name" and "the importer's `-dynamic` is what permits the write" are
> BOTH load-bearing today, and they contradict.

**Decide first: may a module declare `-dynamic` on a name it imports?**
The todo spells out the implementation for each answer. Nothing was landed —
the tree is exactly as Task 7 left it, and the two `xfail(strict=True)`
markers in `tests/test_mutation_gate.py` STAY until it is finished.

## What got done

* **Task 6 slice C** — clpb's `BoolEq`/`BoolImpl` retire. **The
  `instances=True` bridge is EMPTY (15 -> 0).**
* **Task 5 step 1** — the twin-parity corpus had lost its instance rows to the
  Task 3 constructor flip; restored and pinned. **Step 2 is BLOCKED**: an
  instrumented `.so` says not one of the 17 C arms is dead.
  `todo/task-5-c-arms-are-all-still-live-2026-09-20.md`.
* **Task 7** — packages. Only clausal-provenance needed work.
  `todo/packages-are-not-gated-and-are-broken-on-main-2026-09-21.md`:
  **402 package tests already fail on main, with nothing gating them.**
* **Task 8** — `-implicit_atoms` deprecated, warns once per FILE.
* **Task 9** — gates + the numbers above + `docs/terms-are-tuples.md`
  (the announcement).

## Task 9, what is NOT done

* **The corpus ANSWER-SET axis.** Ask the downstream lane to run the 28 downstream
  answer-set checks on the frozen tip. **Landing waits for that**, as the atoms flip's
  did. Not started — it is another lane's run and the user was away.
* The clean-base A/B with its own 13-extension build. The NEW 0 above is
  against the `mainnow` room, which is a faithful room but not a fresh build.

## Three rules this branch paid for repeatedly

1. **A type question must ANSWER, not raise.** Paid three times: `is_v`,
   clpb's `_bool_binary_operands`, provenance's `_class_for_term`.
2. **A constructor flip silently re-points every test fixture that used the
   constructor**, and the fixture keeps passing under its old name.
3. **A NEW-0 is evidence only if the run printed a summary AND the thing under
   test actually imported.** Two wrong package gatees both reported NEW 0.
