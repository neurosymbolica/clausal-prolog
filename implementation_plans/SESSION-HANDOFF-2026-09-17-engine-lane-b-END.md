# Engine lane handoff — 2026-09-17 (second session of the day, engine-lane [bd4549])

Supersedes `SESSION-HANDOFF-2026-09-17-engine-lane-END.md` (on `feat/iso-l3-lowering-2026-09-14`).
Its NEXT items 1–4 are all done or designed; the user said "not pushing any time soon".

## State

    canonical main  /workspace/clausal          <this commit>   ff'd, observed
    box main                                    <this commit>   ff'd via a temp branch, observed
    clone main      /workspace/clausal-bug-fix  merge of canonical main + the clone-side todos
    GitLab origin                               NOT pushed (411 commits behind main at 09b6bb75; the
                                                pre-push list is in the barrier todo)

Four commits on canonical this session, all docs/tools, no engine source, no `.so`:

1. `c3ef6079` predmeta census re-anchored on 38d3cb32 (NEXT 1). `check_p1` GREEN (50/50, 11
   controls). Two things the 09-16 procedure got wrong: CLOSED rows also expire on landing — their
   region was found by the def enclosing a canonical LINE and three resolved to a NEIGHBOURING def
   (false UNDONE at 1008, false STALE at 796); so `P1_SITES.tsv` has column 7 = QUALNAME and the
   checker regions by it. And `census.VERDICTS` is keyed by canonical lines too, so the refresh had
   to re-key it (42 of 83 moved, ONE regex pass — a sequential replace chained 678→745→812 and the
   count assertion caught it). STILL-TO-READ 44 → 5 (P1's own kept reads + 2 prose).
2. `09b6bb75` barrier scrub (NEXT 2). The two corpus sweep tools take `CORPUS_ROOT`; six doc lines
   and seven unpushed test comments reworded. The scan (2,579 tracked files; 411 unpushed commits,
   64,426 added lines; positive control 238) found 63 path hits, 55 already on origin (historical,
   not purged per the 2026-08-23 calibration) and 32 domain-name lines still in docs/handoffs of
   several lanes — LISTED in the barrier todo for the operator's call before any push.
3. `a0e9f0d1` X4/Q census refresh (NEXT 3), measured on a two-module probe: adoption works plain
   and aliased, `owns()` is the ownership test, the adopted row's db reports tabledness (the
   `_tabled_home_db` stamp is redundant), `functors()` sees adopted names. No X4 rows remain: 8→R,
   8→P4, 2 stay Q. GAP found: `arities_for` and `signature_for` ignore `_adopted` while `row()` and
   `functors()` consult it (clone todo `arities-for-and-signature-for-ignore-adopted-rows`).
4. this commit: the rdiv/decimal arithmetic DESIGN (NEXT 4), nothing built —
   `docs/superpowers/specs/2026-09-17-rdiv-decimal-arithmetic-design.md`. Recommends the ordering
   GUARD first (no port dependency), then option B: numbers stay Python number objects, the two
   cells are transfer forms + source spellings so a cell never survives as a compound. The
   CLP(Q)-port collision the section-4 answer feared is specific to the rejected option A. Five
   operator questions parked in `todo/rdiv-decimal-arithmetic-design-questions-2026-09-17.md`
   (clone) with recommendations; Q1 (re-align the decimal ruling to the quantity ruling) gates
   everything above the guard. NEW measured fact: the evaluator refuses a Python Decimal LEAF
   today (`'is'(X, D + 1)` on a declared decimal constant raises).

## Instruments that failed open — new this session

* A checker that anchors CLOSED rows by a canonical line expires on landing day like live rows.
* A sequential string re-key CHAINS; assert `count == 1` per key and the dict size after.
* A closed-side path in a TOOL is code, not a clue; the scan must split hits by "already on origin".
* A memory note said the standard-order branch was NOT landed; `git branch --merged` says it is.

## NEXT, in order

1. Operator's answers to the five parked questions (Q1 first). Until then, the ordering guard
   (design §2 C) is buildable and gate-able on its own: engine A/B on a clean base.
2. `arities_for`/`signature_for` adopted-rows gap — small fix with its negative control; unblocks
   P1 row compiler_v2:1853.
3. The P1 R rows now unblocked by adoption (8 sites, design notes in the table): term_expansion's
   row field is the only prerequisite among them.
4. Barrier: the 32 domain-name doc lines before any push (operator's call).
5. CLP(Q) port resume list is unchanged (its own handoff on the branch).

## Peers

the harness lane [803e60] (82-row sweep, QUESTION protocol, freeze a sha first);
harness-date-migration [06e695]; iso-export-lane [e8cdc5] (owed a message before a decimal term can
reach an export — not yet applicable); corpus-lane [0dfae0] (the canary domain; the count of
`is/2`-on-decimal-constant sites). Three sessions carried the `engine-lane` name; use the ref.
