# Engine lane handoff — 2026-09-18 END (engine-lane [bd4549], sessions of 09-17 and 09-18)

Supersedes `SESSION-HANDOFF-2026-09-17-engine-lane-b-END.md`. Written at ~78% context; the successor
starts fresh. Nothing is pushed to GitLab (operator: not soon; barrier todo lists what remains).

## State

    canonical main   /workspace/clausal           <this commit>   (ae25a25e + this handoff)
    box main                                       same, ff'd and observed at every landing
    clone main       /workspace/clausal-bug-fix    merge of canonical + the clone-side todos
    clone checkout   another session's branch — untouched all day; every commit via a temp worktree

## Landed 2026-09-18, in order (all gated: engine failure-set A/B on a clean base, harness where it could reach a scorer)

1. rdiv/decimal line COMPLETE: step 2 evaluator (9e30afa9), cell-operand fix (8f8ab9dd), twin/wrapper
   parity test (c3f4196e), step 7 measured, steps 6+3 under RULED Q6=C/Q7=c (4f0af19b; design status
   8dfd2734). Harness 82/82 on every sha with live controls; two re-ask CONDITIONS recorded (mixed-scale
   decimals; unit-bearing quantity literals). Corpus census (mine + corpus-lane's AST walk): ZERO
   migration — 0 float constants, 0 united, 2 inline negative fixtures; that domain's runner green.
2. G3 load blockers from iso-export-lane (987772f5) and corpus-lane's `<-` lambda lowering (c070d33f)
   landed on the operator's word in THIS session (a relayed approval was refused; the word came here).
3. **The atoms-as-str flip: SPEC ONLY, nothing built.** `docs/superpowers/specs/2026-09-18-atoms-as-str-design.md`
   + `tools/atoms_flip/STR_SITES.tsv` (147 str type tests, disposition column blank). RULED: proceed;
   `$chars` carrier; carrier FIRST under a LOUD interim rule (bare str as text raises), then the atom
   flip (`('x',)` refused after). Open §8: Q1 (str at the seam = atom), Q3, Q4, Q5 — recommendations given.
   Named dependencies: the kit's raw-string escape hatch (conditional, fail-closed BY DESIGN — its
   undeclared branch must emit `$chars`); closed-side sizing is 214 sites/72 files CEILING (84 in sealed
   bodies this lane cannot read); stage 1 is SWEPT before landing, stages keep separate shas; landing
   waits for iso-export-lane's first G3 result on a frozen sha; do the flip BEFORE P4.

## NEXT, in order

1. Build stage 1 (the `$chars` carrier) on a branch off canonical: reader emits `('$chars', s)` for a
   chars string; the str≡char-list equivalence layer (`_text_list_eq`, `_cons_key` str branch,
   `normalize_seg_input`, Seg* walkers, `atom_chars`/text builtins) re-keys on the tag; a bare Python
   str reaching a text site RAISES (the interim rule = positive control); transfer layer carries the
   tag as itself. Gate: A/B, exporter goldens, standard-order + twin-parity suites; then FREEZE and ask
   harness-batch-lane (informative diff). The §7 human read of STR_SITES.tsv (TEXT sites flip) is the
   size of this step; corpus-lane's silent-unmatch grep (quoted literals in term patterns) before it lands.
2. Stage 2 (the atom flip) behind the atoms API — separate sha; harness RE-BASELINE at landing.
3. Small, parked: Q3 writeq recommendation; the operator's `-float_literals(decimal|rational)`
   read-time directive idea (a language choice; corpus needs no migration).

## Instruments that failed open this session (all in memory)

pkill self-match (exit 144); `pytest | tail && git commit` committing on red (again — gate on $?);
a vacuous list-`==` assertion over Decimals; a fix measured on the Python twin while the C wrapper is
loaded (defect in the GAP); a read-only census silent about sealed bodies BY RULE (4.5x under);
`git branch --contains` reading a cherry-pick as "not landed".

## Peers
harness-batch-lane [803e60] (sequential sweeps; atom-literal census tool on the box; re-baseline
protocol agreed); iso-export-lane [e8cdc5] (G3 first run on a frozen sha before stage 1 lands);
corpus-lane [0dfae0] (AST instruments immune by construction; rulebase axis unaffected).
