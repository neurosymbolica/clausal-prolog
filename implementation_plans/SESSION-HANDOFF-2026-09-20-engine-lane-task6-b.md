# Engine lane handoff — 2026-09-20b, P2 Task 6 COMPLETE: the bridge is empty

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**,
tip `8ccb9d87`, 60 commits ahead of `main` (`bd774c46`), 0 behind.
Nothing on main.

**GATE, both rooms re-run from scratch today: NEW 0 / GONE 0 vs main AND vs
the pre-slice-C branch tip.** Extraction count printed beside the summary,
146 = 146 on every arm, pytest exit 1 on both (the 146 are main's too).

    main bd774c46   146 failed, 16710 passed, 50 skipped, 37 xfailed
    branch (pre-C)  146 failed, 16715 passed, 50 skipped, 40 xfailed
    branch 8ccb9d87 146 failed, 16722 passed, 50 skipped, 40 xfailed

The GONE 1 the previous handoff carried (the load-sensitive C17 perf test)
did NOT recur on either of today's runs.

Rooms, faithful and reusable, 12 `.so` each, venv symlinked:
`/tmp/claude-1000/-workspace-clausal-bug-fix/823f67d2-.../scratchpad/{kwwt,mainnow}`.
C is identical main<->branch, so no rebuild dance.

## Task 6 is DONE

    bridge (`instances=True`)   15 -> 0    reflection 9 (A), term_expansion 4 (B),
                                           clpb 2 (C)

No class under `clausal/` requests the bridge. What still matches a grep:
`make_predicate`'s own implementation of the flag (`predicate.py:1829`) and
two docstring mentions in `term_expansion.py`. Tests that build the flag
deliberately (`test_fast_construction.py`'s 48, two audit files,
`test_second_package_copy_term_identity.py`) are exercising the instance path
ON PURPOSE and stay.

**Task 5 (17 C `PredicateMeta_type` arms) is unblocked.** Structural exit is
still 79 + 76, unmoved, and that is still correct — every cell arm sits
BESIDE an instance arm, and the arms delete in Task 5 and later, not here.

## The one thing slice C found that the sizing did not

The previous handoff sized slice C at "22 structural read sites" and named
`_expr_to_bdd` as the place to read first. That was right but incomplete:
**the two variable collectors in the same file, `_collect_bool_vars` and
`_collect_bool_var_objects`, reach a BoolEq's operands through a generic**

    elif hasattr(expr, 'left') and hasattr(expr, 'right'):

**and a grep for `BoolEq` cannot find them.** A cell carries neither field,
so the arm did not fire, no variables were collected, and `sat` bound nothing
and answered False. 16 tests went red with `assert False` — no error, no
traceback pointing anywhere near clpb.

This is the handoff's own "what ELSE already matches a tuple" rule, and the
lesson generalises for Task 5/7: **when you flip a producer, the sites to find
are not the ones that NAME it.** Grep the consuming file for `hasattr(`,
`getattr(`, `.left`, `.right`, and any `isinstance(x, tuple)` — not for the
functor.

One correction to the previous handoff while carrying it forward: it read
`_expr_to_bdd`'s `getattr(..., _MISSING)` as "the exact fail-open shape" that
produced six of slice A's defects. It is the same SHAPE, but that site fails
LOUD — the miss lands on the unsupported-expression TypeError right below it.
What makes a fail-open read silent is a weaker fallback underneath it to
swallow the miss. The collectors had one; `_expr_to_bdd` did not.

## `tests/audit_2026_07_05/` IS NOT IN THE HOUSE RUN

`--ignore=tests/test_clportools.py` is the only ignore on the command line,
but `audit_2026_07_05` is excluded by the house convention, and
`test_07_clpb_sat.py` caught **two regressions the full gate reported as NEW
0**. Its independent truth-table oracle walks expressions with its own
`.left`/`.right`.

**Run it explicitly, in both rooms, after any clpb/clpz3 change.** Main was
38 passed / 9 skipped / 2 xfailed; the branch matches exactly.

## Shape of the fix, for the next walker you convert

All three clpb walkers share ONE reader, `_bool_binary_operands`:

* cell arm first, instance arm second (`hasattr`, never a default, so an
  unrecognised shape is a miss by DECISION);
* the **ARITY** decides, not the functor name — the name is not owned, and
  `make_predicate("BoolEq", ["x"])` declared elsewhere builds a well-formed
  `('BoolEq', X)` meaning something else. Two tests already pinned this;
* it **ANSWERS** for the reserved 1-tuple `('x',)` rather than propagating
  `compound_cell_shape`'s refusal. A type test in a dispatch chain cannot
  raise.

`clpz3` imports that reader rather than spelling a second one — its own
`getattr(type(expr), '_functor', None)` answered None for a tuple and fell
straight through to `clausal_to_z3`.

## Next

* **Task 5** — 17 C `PredicateMeta_type` arms. Unblocked as of this commit.
  A C change means swapping the `.so` wherever the tree is checked out; build
  in a same-sha worktree and cp-then-mv inside the destination directory,
  never `build_ext --inplace` on a tree live processes have imported.
* **The aliased-`assertz` adoption change** — RULED 2026-09-20, option (a),
  adoption wins. Todo:
  `todo/aliased-assertz-loses-the-owner-under-cells-2026-09-20.md`. **The two
  `xfail(strict=True)` markers in tests/test_mutation_gate.py come OFF with
  it** — strict, so they fail loudly if not. This is the ruling that gated
  the branch from landing.
* Then Task 7 (packages, 17 source files), 8, 9.
* Still parked, needs no action:
  `todo/two-copy-diagnostic-after-the-cell-flip-2026-09-20.md`.
