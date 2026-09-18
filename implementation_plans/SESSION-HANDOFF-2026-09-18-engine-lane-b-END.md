# Engine lane handoff — 2026-09-18 (session b) — stage 1 of the atoms-as-str flip: the `$chars` carrier

Supersedes `SESSION-HANDOFF-2026-09-18-engine-lane-END.md`'s ADDENDUM 2. Branch
`feat/chars-carrier-stage1-2026-09-18` in the CANONICAL repo; worktree in this session's scratchpad
(`s1wt`; recreate with `git worktree add <path> <branch>` + `setup.py build_ext --inplace` — it carries C:
`_variables.c`, `_list_unify.c`, `_lists_core.c`). Nothing landed on main. Nothing pushed.

## What is built (all on the branch, each slice gated on neighbours + every docs fixture, then a full
## snapshot on a DETACHED worktree with the .so copied)

    slice 1  1fb39385  reader → ('$chars', text); unify/list-unify C arms; lists entry points; type/order keys
    slice 2  8853fc9c  to_text, normalize_seg_input, runner test names (three funnels)
    slice 3  36c7ccca  the carrier is a HEAD LITERAL (it was hoisted to a body Unify: every test("...") head
                       held a Var and the runner ran the FIRST clause for every test); =.. cons; term_str;
                       fd_eq/fd_ne; z3; json; regex; dict keys; io producers
    slice 4  6a7ca325  the Seg* layer: walks, VarSeg bindings, star slices, star lists → carrier in BOTH twins
                       (C seq_slice sliced the carrier TUPLE); DCG terminal + remainders; head multi-star guard
                       ($unwrap_chars/$seg_slice_out); reify_fd; Seg-vs-Seg unify; SPELLING-PARITY instrument
    slice 5  d6f15d86  seam: to_term/from_term, $unwrap_atom/$text_in (thunk in/out), py-module text_result
                       sweep (16 modules), chars goal refusal, reflection names
    slice 6a 01f2d951  the LOUD INTERIM RULE as a switch (cells.refuse_bare_str, 12 entry points,
                       CLAUSAL_BARE_STR_TEXT=allow|refuse) + the producers it found (arg/3 tails, datetime,
                       json generate, module defaults via option(), phrase/2+3 re-normalising, C join in
                       _lists_core.c)
    slice 6b a2db1338  SegList carrier-bound hole; module_constant_units/4 reads the name thunk's carrier
    slice 7  d26e1df8  the PIN rewrite: 835 rows / 95 files, six parallel agents under PIN-BRIEF.md (tests only)
    slice 6c 826ebc6b  the engine rows the agents refused: regex static auto-bind on a carrier literal (a REAL
                       regression: an absent optional group came back UNBOUND, not None), first-arg indexing of a
                       carrier head literal (would have missed char-list/bare-str callers), _text_list_eq must NOT
                       refuse (reified NAMES compared with !=), replicate/set-ops/csv/clause_source/translate/
                       currency/catch/http producers, _helpers decomposition of a carrier, ++ reads carriers one
                       level down in a list
    slice 8  d5da6812  ARMED by default (CLAUSAL_BARE_STR_TEXT=allow is the override); positive control =
                       tests/test_chars_carrier.py::TestTheInterimRuleIsArmed
    slice 9  1c24bd65  the A/B's ten late pins + unwrap_atom keeps list identity when nothing inside is a carrier

## Instruments and their controls
* Snapshot diffs vs canonical baseline (145): slice 2 NEW 299, 3 NEW 154, 4 NEW 228, 5 NEW 379 (pins grow as
  walks and module results become carriers); armed survey at 6a: 979 failed / NEW 835 = the pin population.
* Spelling parity (tests/test_chars_carrier.py): 40 goals must answer alike for carrier / char list (and the
  bare str while `allow`); it found include/exclude's kind gate and reify_fd.
* Positive control for the rule: `_as_items('ab')` raises under refuse (observed on every snapshot).
* Clean-base A/B: base = canonical main daaf952d in a detached worktree with its OWN build (12 .so) plus the
  stray `clausal/logic/_trampoline` .so mirrored so both trees carry the SAME extension set (13);
  candidate = 1c24bd65 (slice 9, ARMED default), same shape.  RESULT: base 144 failed / 16597 passed;
  candidate 144 failed / 16663 passed; failure-name-set NEW 0 / GONE 0; skip sets identical (52); both
  extractions non-empty; the standing 144 are the environmental names (ortools/pysat/doc-coverage/clportools).
* Exporter goldens (tests/test_clausal_to_prolog*, tests/rewrite, tests/iso): green under allow AND refuse.

## Open / parked
* Q3 writeq recommendation; the operator's `-float_literals(decimal|rational)` idea.
* STR_SITES.tsv disposition column: filled implicitly by the funnel sweep; the C sites 2517/2624 in
  _variables.c are NAME sites (Compound functor), untouched.
* `tests/fmt/test_corpus.py` / `tests/rewrite/test_corpus.py` rows are red inside worktrees by construction.
* The C twin `_head_list_unify_input` does not refuse a bare str target (only the Python twin does): the rule
  is armed at Python entry points; note for the harness lane.

## What a downstream lane must do at the seam (announce before landing)
* Text INPUT to the engine is `chars("...")` (`clausal.logic.cells`), a list of char atoms, or an atom; a bare
  Python str handed over as text RAISES `TypeError: stage 1 of the atoms-as-str flip ...` (override:
  `CLAUSAL_BARE_STR_TEXT=allow`, diagnostic only).  `++value` and `to_term` do this for you.
* Text RESULTS are the carrier `('$chars', s)`: read with `chars_text`, test with `is_chars`; `to_python`,
  `from_term`, `text_of` and a `++` argument read it as the str.
* The kit's raw-string escape hatch: its undeclared branch must emit the carrier (spec §3).

## Peers / landing
harness-batch-lane: FREEZE sha = this commit's parent 1c24bd65 (engine tip; this commit is docs only) for the pre-landing sweep (informative diff, NOT a re-baseline); the
kit's raw-string escape hatch must emit the carrier on its undeclared branch. iso-export-lane: G3 first run
on a frozen sha gates the landing window. corpus-lane: silent-unmatch grep (quoted literals in term patterns).
