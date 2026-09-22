# Engine lane handoff — 2026-09-22, P2 integration + W2 of the P4 retirement

## State

    canonical main                    f3caddd5   (unmoved by this session)
    P2 landing candidate              b45171a b  feat/predmeta-p2-integrated-main-2026-09-22
    P2 frozen tip (untouched)         223f2bd4   feat/predmeta-p2-head-cells-2026-09-19
    THIS BRANCH                       d495d2ae   feat/predmeta-w2-facades-2026-09-22
    spike (not for landing)           6c6ddfe4   spike/dynamic-arities-option-d-2026-09-22

Rooms (12 `.so` each, venv symlinked; NO build needed — C is byte-identical
across main, P2 and this branch):

    /tmp/claude-1000/-workspace-clausal-bug-fix/1766141c-b36d-4ae5-9b57-21ed576ef6a5/scratchpad/w2       this branch
    /tmp/claude-1000/-workspace-clausal-bug-fix/1766141c-b36d-4ae5-9b57-21ed576ef6a5/scratchpad/basewt   2288bd1a, the main-equivalent gate baseline
    /tmp/claude-1000/-workspace-clausal-bug-fix/1766141c-b36d-4ae5-9b57-21ed576ef6a5/scratchpad/p2int    b45171ab, the P2 integration

Gate command, and the baseline set is `/tmp/claude-1000/-workspace-clausal-bug-fix/1766141c-b36d-4ae5-9b57-21ed576ef6a5/scratchpad/base.set` (146 names):

    cd <room> && ./venv/bin/python -m pytest tests -q -rfE -p no:cacheprovider \
      --continue-on-collection-errors --ignore=tests/test_clportools.py

Every code commit on this branch: **NEW 0 / GONE 0**, extraction = summary on
both arms. Do NOT trust that number from this file — regenerate it.

## P2: the engine half is DONE, landing is downstream

P2 merges onto current main with NO conflicts and gates NEW 0 / GONE 0
(146 / 16804 vs 146 / 16777). `b45171ab` CONTAINS main, so landing is a plain
ff. **DO NOT LAND YET**: harness-batch-lane's verdict is 26 of 28 sealed
scorers red, every red attributed to unmigrated residue and none to the seam
(the 2 rows with a clean import graph score 42/42 and 110/110, identical to
main).

**The residue fix is `solve(goal, module=m)`** — one added keyword, the plain
module object the bodies already hold. NOT the `(':', m, (NAME, args))` tuple,
which I recommended first and withdrew: it writes internal term
representation into 111 hand-written call sites, against the 2026-09-21
boundary ruling ("No term space in hand-written source"). 80 tuple sites in 38
bodies were re-pointed; harness-batch-lane verified `module=` on both engines
INCLUDING the `fresh_per_case` reload case, and eu/procurement
selection_criteria scores 341/341 on the P2 candidate with per-site solution
counts and lint identical.

**A phantom dependency cost ~24h**: memory and the P2 handoff both recorded the
28-scorer run as "dispatched 2026-09-21". That lane had no such request. Confirm
receipt, or the record manufactures a blocker.

## W1 HAS REPORTED — P4 is a MIGRATION, not a flag day

    W1a goal-call shape        230 sites / 81 bodies  (119 migrated, 111 not)
        + computed-name form     9 sites /  7 bodies  (getattr-of-call)
    W1b non-goal object access  31 sealed / 5 bodies;  ~0 non-sealed
    W6  Compound / KWTerm        0 sealed; 28 non-sealed, ALL IN TEST FILES

Everything large has a dual-engine migration path. W6 downstream looks close
to free, against the plan's 361 + 118 refs.

## What this branch did (10 commits)

    dae5f795  todo: W2 has no db.row() path for a detached row
    443b2e3b  step 7 locks only names the Database holds a row for
    15e57771  clpb BoolEq/BoolImpl -> functions  (instances=True bridge 2 -> 0)
    c2c977bd  reflection's nine -> constructors
    bec725ea  stop minting detached rows on the load path (12 -> 2)
    8bd10bec  term_expansion's two vocabularies -> constructors
    861ac79b  todo: the wart quantified, 207 of 214 engine mints
    ae51facc  option D: derive the declared-arity set from the OWNER's db
    39544097  todo: close the wart; W2's load-path half is done
    d495d2ae  W2: the FIRST FACADE retired -- _dynamic_arities + its row field

**Detached rows on the load path: 18 -> 0.** The `instances=True` bridge is 0.

## NEXT ACTION — the re-point is ~26 sites, NOT 66, and it is NOT MECHANICAL

**Both halves of what I first wrote here were wrong. I tried three sites and
found out.**

### The count was inflated ~2.5x by a grep that conflated two objects

`_clauses`, `_dispatch_fn` and `_lazy_recompile` are attribute names on the
**Database** as well as on `PredicateMeta`. `db._clauses` is
`dict[(functor, arity), list[Clause]]`; `cls._clauses` is the facade. Counting
`\._clauses\b` counted both.

    attribute         total   db-ish (NOT a target)   class-ish (a target)
    _clauses             31          16                      9
    _dispatch_fn         16           8                      5
    _lazy_recompile       9           6                      1
    _signature            5           0                      5
    _locked               2           0                      2
    _index_plans          3           0                      3
    _clauses_source       0           0                      0
                                                   ~25, +2 in _registry.py
                                                   (`other._dispatch_fn`)

### And it is not a textual swap — three DIFFERENT shapes in the first three sites

1. **Row guaranteed → re-pointable.** The ordinary compiler sites.
2. **Receiver is an arbitrary TERM value.** `builtins/io.py:743` does
   `clauses = val._clauses` under only `isinstance(val, PredicateMeta)` — a
   user-facing listing builtin, so `val` can be a bare `make_predicate` class
   from user Python and `_row` CAN be None. Needs the fallback AT the site.
3. **The site exists FOR the no-row case and can never be re-pointed.**
   `compiler/predicate.py:1470` and `:2061`:

       if db is not None:
           next_clauses = db.clauses_for(functor, arity)
       else:
           next_clauses = pred_cls._clauses if pred_cls is not None else clauses

   That `else` IS the no-Database path, and `db=None` is the DOCUMENTED
   DEFAULT of `compile_predicate_trampoline` / `compile_predicate_shallow` /
   `compile_predicate` (see `compiler/README.md`). Re-pointing it to
   `pred_cls._row.clauses` would be wrong by construction.

### So W2's completion is gated on P4, not on the load path

The load path being clean makes the *guaranteed-row subset* re-pointable, and
that subset has to be identified SITE BY SITE — there is no blanket rewrite.
Every site whose receiver can be a class minted outside a load keeps the
facade until `make_predicate` goes at P4. Budget an audit of ~26 sites with a
per-site decision, not a sweep.

## Rulings taken (do not re-open)

* **`make_predicate` goes with the class at P4** (operator). It is literally
  `PredicateMeta(name, (), {"_fields": ...})`. So
  make_predicate-without-a-Database does not survive P4.
* **Option D** for the `_dynamic_arities` wart (operator): derive from
  `cls._row._db._dynamic`, delete the step-4a stamp.
* **`module=`, not the goal tuple**, for the downstream residue.

## Numbers NOT to re-measure

    PredicateMeta classes created per suite run   10293
      ... that ever mint a detached row             102
      ... _bind_row calls                        25044
    mark_dynamic calls per suite                   693
    _declared_arity calls / non-None                22 / 7   (3 names)
    _get_dispatch out-of-tree implementors          11 real (3 packages)
      ... of which mention PredicateMeta             1
    packages/ SOURCE files calling make_predicate    0

**EAGER row minting is DEAD**: it would create 10,191 private Databases nothing
touches, for 102. `_detached_row`'s "a class that never touches predicate
state never pays" is right at 99%. Do not propose it.

## Open, not mine

* **W3 has NO working gate.** 11 implementors in 3 packages; all 3 suites are
  RED on main because the distributions are not installed and their `clausal/`
  trees are not on `clausal.__path__` (the merge is keyed to site-packages by
  design). So "package gate NEW 0 / GONE 0 across all 12" compares two piles
  of rubble. Fix = give the gate its own venv; do not install into the shared
  one every lane symlinks.
* `todo/head-fold-structured-guard-never-excluded-a-vocabulary-cell-2026-09-22.md`
  — a rewrite-rule clause may produce a spurious answer; behaviour PRESERVED,
  question filed, needs its own gate.
* `todo/w2-facade-retirement-has-no-path-for-a-detached-row-2026-09-22.md` —
  updated with the load-path half closed.

## Traps paid for this session

* A two-arm A/B whose arms **AGREED because both imported the canonical
  engine** — the probe script lived in a scratchpad dir, so `sys.path[0]` was
  that dir. Run probes on STDIN from inside the room and
  `assert clausal.__file__.startswith(room)`. Agreement is not a result.
* **A NEW-0 gate cannot see a test going VACUOUS.** Option D made 4 tests pass
  for the wrong reason (they assert a DECLINE, which a declaration that never
  took also satisfies) while only 1 failed. Read the tests.
* **A pin naming an incidental class goes vacuous silently** — `not
  md["BoolEq"]._locked` stopped meaning anything when BoolEq stopped being a
  class. Mint the subject inside the test.
* `git mv` + append: my `git add` listed a stale pre-move path, git ABORTED the
  whole add, and the commit captured the rename with NONE of the content, while
  looking clean. Verify with `git show HEAD:<path> | grep -c`.
* A `.clausal`/`.seam` file can hold a Python `isinstance` inside `++`. Search
  those extensions, not just `.py`.
* A mint census keyed on LINE NUMBERS goes stale against the tree you are
  editing. Key on a symbol.
* Twice, a sound derivation was rejected by arguing against a SINGLE-KEY
  version of it (my import objection; `database.py`'s "cannot be
  reconstructed"). Check which object the derivation starts from.


---

## APPENDIX 2026-09-22 — two facades retired; the rest wait for P4

Tip `0758019a`. `_dynamic_arities` and `_clauses_source` are both gone, each
with a RAISING TOMBSTONE on the metaclass (`_RETIRED_STATE_NAMES`), because
deleting a property's SETTER is SILENT -- measured: the assignment succeeds as
a plain class-attribute write and the row never sees it.

**Only 3 engine sites ever see a row-less class in a whole suite run**
(compiler_v2:485, compiler_v2:1110, specialization.py:106). But three shapes
make the remaining facades unre-pointable ahead of P4:
`builtins/_registry.py` mints builtin classes **deliberately detached**
(and they never show in a census because they run at import, before a plugin
can patch -- absence there is an artifact);
`compiler/predicate.py`'s `_clauses`/`_index_plans` sites sit on the
**documented `db=None` path**; and `builtins/io.py:743` reads `val._clauses`
off an **arbitrary term value**.

**The pattern that works is ELIMINATION, not re-pointing**: find a facade
whose production users can be removed, then delete it and leave a tombstone.
Both retirements went that way. `_signature` (5 sites) is the next candidate
to assess.
