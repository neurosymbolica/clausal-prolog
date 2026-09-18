# Engine lane handoff — 2026-09-18 (session c, END) — the flip landed, P4 prerequisites landed, P2 planned

Follows `SESSION-HANDOFF-2026-09-18-engine-lane-stage2.md` (on the stage-2 branch, now in main's history).
Everything below is on CANONICAL main unless it says otherwise. Nothing is pushed to GitLab (the standing barrier
note stands: two census sweep tools hardcode the private corpus path).

## Where the trees are

| tree | tip | carries |
| --- | --- | --- |
| canonical main `/workspace/clausal` | `fb0106f3` | atoms-as-str flip stages 1+2 (merges `1f864b39`, `be5cbc3a`), docs pass, P4 prerequisites |
| clone main `/workspace/clausal-bug-fix` | `5bf7a8db` | the same, by merge (its main carries other sessions' work) |
| box `/workspace/clausal` | `fb0106f3` | pushed; extensions force-rebuilt at `3fcfd29e` (x86_64), no C change since |
| branch `feat/predmeta-p2-terms-as-tuples-2026-09-18` | `ec06556f` + Task 1's commit when it lands | the P2 PLAN and the P2 census (in flight, see NEXT) |

Extensions in the canonical checkout were rebuilt at `3fcfd29e` in a same-sha worktree and swapped by
copy-then-move (two law-portal runservers had the old ones mapped). No C changed after that.

## What landed tonight, in order (each gated NEW 0 / GONE 0 on detached arms; the flip's handoff has its own record)

1. **The atoms-as-str flip, both stages** — an atom IS the interned `str`; a string is the `('$chars', s)` carrier;
   `('x',)` is RESERVED and refused; no class is an atom. Landed at the operator's word after iso-export-lane's G3
   on the stage-1 freeze came back byte-identical (1755 staged `.pl`, 0 differing, 75 domains). Announcements with
   LANDED banners: `CHARS-CARRIER-STAGE1-FROZEN-2026-09-18.md`, `ATOMS-AS-STR-STAGE2-BUILT-2026-09-18.md` in the
   lanes' shared directory (the latter carries the successor sha `fb0106f3`).
2. **Docs pass** (12 user docs, snippet suite green, three stale-docs todos closed into `todo/done/`). One claim a
   sonnet agent reported as "measured" was not: body-position `"a"[0]` is DICT-only subscript on every engine,
   so that table row is notation; fixed to "no fixed point: the element of `"a"` is the char atom".
3. **P4 prerequisites** (4 commits): the 0-arity-predicate-as-value ORDER caveat closed (a pre-pass over the raw
   module collects 0-arity clause heads; it only ever bit under `-implicit_atoms`); a bare 0-arity goal in a body
   (`t(R) <- (p, R is yes)`) is accepted (it was refused in EVERY spelling before, on the stage-1 base too; only
   `p()`/`call(p)` loaded); a declared functor that `-discontiguous`/`-table`/`-shallow` names gets its Database
   row. The BROAD form (every fielded declaration mints a row) FAILED its gate for a reason `test_predrow` pins: a
   declared DATA functor must stay rowless (a row made `cite(KEY)` in a body read as a call). That finding became
   ruling R-P2-1.

## Rulings taken with the operator tonight (do not re-open)

* **R-P2-1** one declaration registry on the Database with a `data`/`predicate` kind; the module-level
  `FUNCTOR_SIGNATURES_KEY` map is retired into it.
* **R-P2-2** `m.pred(X)` from Python is retired WITH the class in P4, no proxy; the forms are
  `call("pred", X, module=m)` and `solve(("pred", X), module=m)`.
* **R-P2-3** `-implicit_atoms` is deprecated this landing, removed the next (0 of 875 corpus files, 4 engine test
  sources, 12 docs use it; `-hide` is the Ciao-style per-module identity and is a different axis).
* **R-P2-4** sequencing OPTION 2: P2 runs BEFORE L3's rules/directives phases. L3 is MERGED but at FACTS ONLY
  (`clausal/tools/iso_l3.py`, 4 tests in `tests/iso_l3/`, refuses rules); its facts harness is one of P2's controls
  and its later phases are written once against the tuple AST. The design's §5 reason (never make a lowering bug
  and a representation bug in one change range) is honoured by keeping the ranges separate.

## The P2 plan

`docs/superpowers/plans/2026-09-18-predmeta-p2-terms-as-tuples.md` on the P2 branch: the representation stated
once, the THREE REWRITES every site must be one of (constructor / decomposer / type-test), nine tasks in dependency
order with the sweep ordered by measured site counts, gates per §7 (clean-base A/B, twin parity, exporter goldens,
`tests/iso`, `tests/rewrite`, `tests/iso_l3`, corpus ANSWER-SET axis before promotion, class count and construct/
unify bench as exit numbers), and an explicit not-in-P2 list (goal position = P3, deleting the class = P4, L3
rules, `Compound`). Corrected counts: `packages/` has 7 source files touching the class layer (an earlier 44 counted
`build/` copies); `reflection.py` mints 9 vocabulary classes (Task 6). `specialization.py`'s 32 mentions are
annotations only — one signature change, no class-identity dependence.

## NEXT

1. **Task 1 (the census with kinds) is DONE and VERIFIED**: P2 branch tip `421a9fa0` = the agent's
   `2e75cf62` (walker + 405 labelled rows over 52 files; population 524 files; all four controls reproduced, two
   deltas explained) + my verification commit (the walker now REFUSES to overwrite a labelled TSV without
   `--force` -- a plain re-run clobbered the labels once; `control.py:53` relabelled goal-position). Kinds:
   decomposer 152, typetest-compound 75, typetest-predicate 61, package 41, constructor 33, c-arm 17,
   definition 13, annotation 12; 45 rows `needs-db` (17 in specialization.py); 22 `._fields` rows are KWTerm/ast
   false positives kept with notes. Task 2 (the registry) is next.
2. Task 2 (the registry) is the first engine change; it subsumes the fb0106f3 row minting.
3. Lanes: harness-batch-lane's RE-BASELINE sweep on `fb0106f3` (told); corpus-lane's attribution of the two
   newly-exportable wrong-answer domains (GDPR breach notification, Peppol) — theirs, not an engine block;
   iso-export-lane: done for this window.
4. Parked from earlier: Q3 writeq, the operator's `-float_literals` idea, the 8 `normalize_seg_input` callers that
   read a bare-str atom as text in `phrase/2` and friends (not a regression).

## Instruments and pitfalls added tonight

* A failure-set diff cannot see what its baseline holds: transplant onto a CLEAN base (done for every gate).
* Copying a `.so` into a snapshot is sound ONLY from the same sha (iso-export-lane's caveat for C-changing ranges).
* An "already applied" check of `old not in s and new in s` is WRONG when `new` contains `old` — it re-applied a
  patch four times. Exact-text patches keep hitting interleaved comment lines: read the span RAW before writing an
  old-string.
* `git worktree add` acts on the repo of the CWD, not of the branch name — a clone merge silently targeted canonical.
* Two full suites in parallel make one perf test flake (`test_F026_multi_star_splits_bounded_for_moderate_input`);
  rerun alone before counting it.
* Subagent spend: general-purpose with no `model:` inherits the session model. The six pin agents cost ~224k tokens
  each on it; the docs and census agents ran on sonnet (docs: 251k). Pass `model: sonnet` for mechanical work.
