# Engine-lane handoff, 2026-09-24 (b) -- P4 / PredicateMeta retirement, evening

Successor of SESSION-HANDOFF-2026-09-24-engine-lane.md. Canonical main: **cb57e75a**.
Box/GitLab NOT pushed. Gate baseline: 146 failed (known F026 timing flake
test_F026_multi_star_splits_bounded_for_moderate_input and
test_many_distinct_strings_sort_in_linear_time appear under load; re-run to attribute).
Operator preference: SHOW CODE when discussing code issues (memory show-code-not-prose).

## Landed today (in order)
lock loop (6b118e5b) - row 24 source stamp (dde50d49) - rows 27/29 (d505f69e) - F4
(c1819a20) - call/N+phrase+time_goal raise (fe23c369) - stranded rows 34/57 (ac2320e3) -
row 4 (eefab5fc) - rows 32/33+QA+QB (5d713093) - row 35 data half (cbd7eef2) - Q0/X3
(7fc6f3ae) - rows 58/59 (a3d6eb01) - QC test migration (c549c7e1) - ruling S (8269550e) -
W4b-3 dispatch conversions (c68d6552) - row 60 (754a2bbd) - signature source (a5c4fab8)
- name+arity ruling incl. aliased-import leak + meta-calls (cb57e75a).
ALL SEVEN blocked F1 rows are done.

## Operator rulings made today (do not re-ask) -- full text in memory predicatemeta-retirement-design.md
D1 imports bind the OWNER's handle; Q0 caller's db first, registry only for the cross-
module remainder; X3 mint handles from the db; S self-denoting atom in data position is
PLAIN (mind -hide); QA refuse multi-arity MI; QB mint -specialize target row early; QC
(b) direct specialize_mi requires a Module db at W4b-3; QE mangled input resolving to
nothing raises (not for -hide atoms); ruling 2 extended to phrase/time_goal; name+arity:
a call at another arity resolves normally in the namespace named, under the name used
(class-era refusal was an artefact); aliased import grants no other arity/name; partial
application through an alias resolves as the owner's name (controller decision,
reported); vocabulary-implements DROPPED (load error); a local p/2 beside an imported
p/1 LOADS; signature stamped from HeadFieldNames incl. imported-atom names; todo batch:
1 B (drop declared-at line), 2 A (goal builtins resolve atom goals in caller's module,
then plain atom in clause source), 3 A (import wins), 4 C (written arity, phrase appends).
Downstream remedy for m.pred(...) sites is a CELL handed to solve(..., module=m), NOT
--m.pred(...) (ruled all-solve; two out-paths disagree).

## In flight (branches; each needs merge main -> full gate -> roborev until only Lows -> land)
- feat/drop-vocabulary-implements-2026-09-24 (/workspace/_vocabdrop): 8 NEW failures after
  merging main (interaction with name+arity); agent working.
- fix/q0-wire-db-hint-2026-09-24 (/workspace/_q0wire) tip 6e8cd714: round-2 done, needs gate+review.
- fix/small-todos-batch-2026-09-24 (/workspace/_todobatch): items 2 A and 4 C being
  implemented; its earlier gate is VOID (tree edited during it). Items 1 B and 3 A wait
  for the vocabulary branch to land (same code).
- spike/w4b2d-flip-dry-run-2026-09-24 (/workspace/_flipdry): NOT for landing. Report:
  implementation_plans/w4b2d-flip-dry-run-2026-09-24.md -- the pre-flip task list (10 tasks).

## Pre-flip task list (from the dry run)
1 bare-name-as-argument (= ruling 2 A, in flight) - 2 land vocabulary drop - 3 handle-only
popped-owner lookup / Q0 registry at RUNTIME (resolve_module) + _field_names_for_name db -
4 real module installed during compile (placeholder $module trap; namespace_db() helper on
the Q0 branch is its single home) - 5 clause heads built without calling the binding; arity-
only placeholder names into the db; head arity check home - 6 move class-stored data:
_te_predicate_nodes, _tabled_home_db (BOTH tabled_naf.py and tabling.py together),
_registered_at - 7 small fixes (listing(p) bare, analyze_mi(mod.solve), step 4a, tabling
guard, cell spelling) - 8 the flip - 9 migrate 484 class-pinning tests (class-listing
harnesses would pass vacuously) - 10 re-gate.
Also: 18 list/higher-order builtins + functor/3, =../2, callable/1, _is_goal call
_ensure_trampoline_dispatch with no db (Q0 todo, round 2 section).

## Downstream (information barrier: details only outside the engine repo)
Downstream sites go LOUD at the flip; remedy = cells to solve. The downstream owners have
the list. Operator confirmed the two relays (W4 census GO, reflect.py repair GO) the offline
predecessor carried.

## Working rules re-learned today
- Every review round after a gate needs a RE-gate on the final commit before landing.
- Merge main into a branch before its gate; check `git merge-base --is-ancestor main HEAD`;
  a conflicted merge must be aborted -- a gate on a half-merged tree is void.
- Never let an agent edit a worktree while a gate runs in it.
- A refusal check that "stands aside" hands the case to step 4's bind -- trace step 4 first.
- roborev "no agents available" is transient; retry once.
- Never pkill by pattern (a dry-run agent did; could have killed another lane's suite).
