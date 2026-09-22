# Engine lane handoff — 2026-09-21, P2 Task 7 done

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**,
tip `18a8f749`, 65 ahead of `main` (`bd774c46`), 0 behind. Nothing on main.
**Nothing has landed in C** — main and branch C are still identical.

**HOUSE GATE: 146 failed, 16726 passed, 50 skipped, 40 xfailed, exit 1;
extraction 146 = summary 146. NEW 0 / GONE 0 vs main AND vs the Task 5 tip.**

**PACKAGE GATE: NEW 0 / GONE 0 across all 12 packages**, 11 backed by a real
pytest summary; the twelfth (clausal-yaml) HANGS identically on both sides and
is recorded as such rather than counted as passing.

Rooms: `.../823f67d2-.../scratchpad/{kwwt,mainnow}`, 12 `.so` each, venv
symlinked.

## Task 7 in one line

Only **clausal-provenance** needed anything. The plan's other named file,
`packages/clausal-scipy/.../scipy_stats.py`, does not decompose terms at all —
its census hit was a test class called `TestPredicateMeta`. Measure before
working from a file list written three tasks ago.

`engine.py` is built around predicate CLASSES (they carry `_clauses`, and
`-bottom_up`/`pure_` registration hangs off them), so a CELL must be resolved
back to its class through the module. Three readers now own the shape —
`_term_args`, `_class_for_term`, `_term_to_tuple` — and the four dispatch
sites go through them.

## THE PACKAGES ARE NOT GATED, AND ARE BROKEN ON MAIN

`todo/packages-are-not-gated-and-are-broken-on-main-2026-09-21.md`.
**402 failed, 3493 passed, 319 errors on main**, plus clausal-yaml hanging.
The house run never touches `packages/` and the packages are not installed in
the venv, so an engine change can break all twelve with the gate still green —
the same blind spot as `_get_dispatch`'s out-of-tree implementors. Sampled
causes are purity/protocol drift, NOT the cell flip.

## The downstream checks, and why it is in the todo verbatim

**I got it wrong twice, and both wrong versions reported NEW 0.** There are
THREE contribution layouts (`clausal/modules/py/<n>.py`,
`clausal/modules/<n>/`, `clausal/<n>/`); each target is a REGULAR package so
PEP 420 will not merge it, and `__path__` must be extended explicitly. Missing
a layout is a silent no-op: every test then fails with `ModuleNotFoundError`
IDENTICALLY ON BOTH SIDES, and the diff comes back clean over two piles of
rubble. Fixing it moved clausal-jax from "4 passed" to **1000 passed** and
clausal-scipy from "4 passed" to **1493**.

Do not `pip install -e` into `/workspace/clausal/venv` — it is SHARED, and an
editable install points every lane at whichever room installed last.

**Rule that would have caught it: a NEW-0 is only evidence if the run printed
a summary AND the thing under test actually imported.** The plugin takes a
`PKG_PROBE` for exactly that positive control.

## Two defects I introduced and removed, both this branch's recurring shapes

1. `goal_cls_initial` cannot name a CELL's class without a module, so it
   answered the TERM — and the root check `cls is goal_cls_initial(...)`
   silently stopped matching. The "goal is not -bottom_up" ValueError stopped
   firing and resurfaced 80 lines later as an unrelated TypeError. **A reader
   that cannot answer must not be in a dispatch chain's identity test.**
2. `head_key` RAISES for the reserved 1-tuple, `()` and a TUPLE_TAG data
   tuple, so `_class_for_term` propagated instead of answering None. Same rule
   as `is_v` and clpb's `_bool_binary_operands`: **a type question answers.**

## Next

* **The aliased-`assertz` adoption change** — RULED 2026-09-20, option (a),
  adoption wins.
  `todo/aliased-assertz-loses-the-owner-under-cells-2026-09-20.md`. **The two
  `xfail(strict=True)` in tests/test_mutation_gate.py come off with it.**
  This is the only thing between this branch and a merge.
* **Task 8** — deprecate `-implicit_atoms` (R-P2-3).
* **Task 9** — gates, handoff, announcement.
* **Task 5 step 2** stays blocked until P4's head channel;
  `todo/task-5-c-arms-are-all-still-live-2026-09-20.md` has the measurement.
