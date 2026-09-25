# Engine-lane handoff, 2026-09-25

**Canonical main is 45ca3f41.** Box and GitLab are NOT pushed: the operator asked us to wait for stability. The release and push plan is drafted in `release-1.0.0-and-push-plan-2026-09-25.md`, with 1.0.0 to come after W4b-3.

## Landed (each: clean gate, roborev Lows only, a clean downstream sweep)
| sha | change |
|---|---|
| e91fac3e | real module during compile |
| ae7c210d | class-only data moved to the Database |
| 2e20f16f | heads without calling the binding |
| df0d0c53 | Q0 runtime registry |
| 4da6ec17 | a direct unknown call raises ISO existence_error |
| 8b02f4f8 | call/N runs body terms |
| ae1a456d | rulings 1B/2A/3A/4C/S, -meta_predicate, Scryer listing, ISO arity errors |
| 0738b335 | pre-flip small arms |
| d724dd52 | call/N runs special-form cells |
| 4b5fae49 | ISO clause/2 (Clause.hoisted) |
| 3e41e1e1 | a dotted meta argument is a qualified goal |
| **e107929e** | **W4b-2d, the flip:** module-dict predicate bindings are the owner's handle |
| 45ca3f41 | user docs teach the post-flip Python API |

## Ready branches, waiting on the operator's landing go
| branch | worktree | tip | status |
|---|---|---|---|
| fix/python-api-silent-cell-iteration-2026-09-25 | /workspace/_pyapi | 489614cc | gate clean, reviewed; needs a downstream sweep |
| feat/w4b3-delete-predicatemeta-2026-09-25 | /workspace/_w4b3 | fb69e75b | slices 1-2 (refuse an unowned class, delete dead arms); gate clean, reviewed; needs a sweep |
| chore/disable-provenance-2026-09-25 | /workspace/_provoff | fd92cb9e | gate clean |

## Open operator questions
1. `clausal.<builtin>` called from Python builds a cell, so iterating it is silently wrong. Option B (recommended) is a runner that requires module=, inside W4b-3 slice 3.
2. A predicate exported with no clauses is treated as data. Should it stay a procedure, as ISO has it?
3. The release questions in the release plan.

## W4b-3 slices
Slices 1-2 are done on the branch. Remaining:
3. Builtins stop being classes.
4. Specialization stops minting classes. This is a clean break: `specialize_mi*` returns a handle.
5. The rewriter stops emitting class blocks. Needs a downstream A/B.
6. Retire the Python-API arm.
7. Delete PredicateMeta.
8. The C tail.

Rulings made today are recorded in the lane's memory notes.
