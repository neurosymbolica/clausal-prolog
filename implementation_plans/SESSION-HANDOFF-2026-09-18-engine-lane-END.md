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

## ADDENDUM (same session, later): stage 1 of the chars carrier is STARTED on a branch

The operator chose to begin in this context ("spec-writing is lossy"). Branch
`feat/chars-carrier-stage1-2026-09-18` in the CANONICAL repo (worktree
`…/scratchpad/s1wt` of this session; recreate with `git worktree add <path> <branch>` and
`setup.py build_ext --inplace` — it carries C changes), slice 1 at `1fb39385`:

    DONE  cells.py CHARS_TAG/chars/is_chars/chars_text; tag excluded from "compound" beside TUPLE_TAG
    DONE  term_rewriting: a "..." literal under -double_quotes(chars) compiles to Constant(('$chars', text))
    DONE  lists.py entry points (_as_items/_was_string/_seq_result -> carrier out), append/3 kind tracking
    DONE  clpfd._text_list_eq, type_checks string/1, _helpers standard-order key (carrier keys as its char list)
    DONE  C: _variables.c unwraps a carrier right before the str<->list unify arms (after var handling);
          _list_unify.c seq helpers, star splat, walked segment, promotion -> carrier
    DONE  tests/test_chars_carrier.py (8) + 7 pins flipped; neighbour suites green (728)
    OPEN  the full-suite fallout snapshot (running at handoff time; see the memory note for the result)
    OPEN  every other producer/consumer of a bare str as TEXT: the seam (`to_term`: a Python str crossing in
          becomes the carrier in stage 1; `text_of`), SegString.__walk__, the text builtins beyond lists
          (atom_chars/atom_length/sub_atom/format/write/writeq print the TEXT, never the tag), DCG terminal
          constants (`_dcg_terminal_text` stays str today), the 3 other `isinstance(x, str)` sites in
          lists.py, the TEXT rows of tools/atoms_flip/STR_SITES.tsv (the human read), _variables.c's other
          PyUnicode sites (2517/2624: standard order / type in C?), the exporter's 37 branch lines
    OPEN  THEN arm the loud interim rule (a bare str reaching a text entry point RAISES) as the positive
          control; THEN gate (engine A/B on a clean base + exporter goldens) and FREEZE for
          harness-batch-lane's pre-landing sweep (informative diff, not a re-baseline)
    RULE  bare str is ACCEPTED as text at every patched site until the interim rule is armed — the
          suite must stay runnable between slices; commit each slice

## ADDENDUM 2 (end of the 2026-09-18 session): stage 1 slice 2 committed; the fallout MAP for the successor

Branch `feat/chars-carrier-stage1-2026-09-18` (canonical repo), slice 2 at `8853fc9c`: the carrier
reads as its text at three FUNNELS — the py-modules' shared `to_text` (regex, sqlite, crypto, json,
tcp, uuid, logging, z3 all pass through it), `normalize_seg_input` (every list consumer that walks a
Seg*), and the test runner's test names (`test("…")` is a chars string, so every `.clausal` test file
went red at once until the runner read the carrier — one funnel, many rows; the same runner serves the
closed corpus, fixed once).

Fallout snapshots vs the canonical-engine failure set (145 names): slice 1 = NEW 358 / GONE 0
(16,247 passed); slice 2 = NEW=299 GONE=0 (slice 1 was NEW 358) (443 failed, 16306 passed, 52 skipped, 38 xfailed, 923 warnin). The map, by shape rather than by file:

* **FUNNELS still to unwrap** (engine work, small): `unpack/2` (`=..`) has its own list check and
  raises `type_error(list, carrier)` — it is what poisons `tests/fixtures/docs/builtins_sig_tests.clausal`
  (125 rows), `z3_integer` (14), `io_to_string` (9) despite the runner fix; the text builtins in
  `builtins/chars.py`/`inspection.py` (`atom_chars`, `atom_length`, `sub_atom`, `string_*`, `format`,
  `write`/`writeq` — print the TEXT, never the tag); DCG terminal constants (`_dcg_terminal_text` still
  emits a bare str); `SegString.__walk__` (returns str); the seam `to_term` (a Python str crossing IN
  becomes the carrier in stage 1) and `text_of`; the 3 other `isinstance(x, str)` sites in lists.py;
  the TEXT rows of `tools/atoms_flip/STR_SITES.tsv`; `_variables.c` PyUnicode sites 2517/2624
  (check what they decide); the exporter's 37 branch lines.
* **TEST PINS expecting a bare str** (mechanical, large): `[('$chars', '')] == ['']` shapes across
  test_regex (86 at slice 1), test_string_list_builtins, test_string_higher_order, logging, currency
  money, python_fallbacks, … — rewrite `'text'` expectations to `chars('text')` (or compare through
  `chars_text`); a helper in `tests/` conftest would make this one edit per file.
* **THEN** arm the loud interim rule (bare str at a text entry raises) as the positive control, run the
  engine A/B on a clean base + exporter goldens, and FREEZE for harness-batch-lane's pre-landing sweep.

Method that worked: fix a funnel, rerun the neighbour set (chars, double_quotes, dcg, bytes, standard
order, iso, value_terms, seam, the carrier file — green at 728 after slice 1), commit, full snapshot in
the background, read NEW by file. Never `pytest | tail && commit` — gate on pytest's own exit.
