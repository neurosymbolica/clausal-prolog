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
ff. **DO NOT LAND YET**: the downstream lane's verdict is 26 of 28 downstream
answer-set checks red, every red attributed to unmigrated residue and none to the seam
(the 2 rows with a clean import graph score 42/42 and 110/110, identical to
main).

**The residue fix is `solve(goal, module=m)`** — one added keyword, the plain
module object the bodies already hold. NOT the `(':', m, (NAME, args))` tuple,
which I recommended first and withdrew: it writes internal term
representation into 111 hand-written call sites, against the 2026-09-21
boundary ruling ("No term space in hand-written source"). 80 tuple sites in 38
bodies were re-pointed; the downstream lane verified `module=` on both engines
INCLUDING the `fresh_per_case` reload case, and the downstream domain
one downstream row scores 341/341 on the P2 candidate with per-site solution
counts and lint identical.

**A phantom dependency cost ~24h**: memory and the P2 handoff both recorded the
28-answer-set check run as "dispatched 2026-09-21". That lane had no such request. Confirm
receipt, or the record manufactures a blocker.

## W1 HAS REPORTED — P4 is a MIGRATION, not a flag day

    W1a goal-call shape        230 sites / 81 bodies  (119 migrated, 111 not)
        + computed-name form     9 sites /  7 bodies  (getattr-of-call)
    W1b non-goal object access  31 downstream / 5 bodies;  ~0 non-downstream
    W6  Compound / KWTerm        0 downstream; 28 non-downstream, ALL IN TEST FILES

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


## APPENDIX 2 — W2 closed out at 3 of 7; tip `ff19d57f`

Retired by ELIMINATION, each with a raising tombstone:
`_dynamic_arities`, `_clauses_source`, `_signature`. The instance
read-through face is down from 7 names to 4.

**The remaining four cannot move before P4, with a reason each:**

    _clauses          compiler/predicate.py:1470,2061 = the `else` of
                      `if db is not None`; builtins/io.py:743 reads it off an
                      ARBITRARY TERM value under only an isinstance guard
    _dispatch_fn      _install writes inside `with ctx` where `_bind_row` ran
                      ONLY `if db is not None`; _registry.py's builtins are
                      deliberately detached
    _lazy_recompile   same _install site (its ONE production site)
    _locked           _registry.py x2, deliberately detached
    _index_plans      _compile_predicate_trampoline_impl(..., db=None,
                      pred_cls=None)

`db=None` is the DOCUMENTED DEFAULT of every compile entrypoint, so these
sites exist FOR the row-less case. Spelling the fallback at the site buys
nothing structurally and duplicates the facade. Leave them for P4.

**So W2 is not "the bulk of the diff" the plan expects.** It is three
eliminations and four blocked attributes. Re-scope it on that basis.


## APPENDIX 3 — W2 CLOSED at 7 of 7; tip `9028f9b3`

The operator said "work on them", so the four blocked attributes got a
second look, and Appendix 2's blocking reasons dissolve under one
observation: **`_detached_row()` already returned `cls._row` when it was
set.**  Every facade body `(cls._row or cls._detached_row()).x` was
therefore `cls._detached_row().x` — the accessor existed, it was just named
as if it always minted.  Renamed `_state_row()`, it IS "the row obtained
from the class" that the todo's honest version asked for.

That makes the per-site decision three-valued and mechanical, not blocked:

    a Database in hand          db.row(f, n).<field>
    class only, WRITE           cls._state_row().<field>       (mints, as before)
    class only, READ, no mint   cls._row.<field> if cls._row is not None else <default>

Appendix 2's four "cannot move" entries, resolved that way:

    _clauses          compiler/predicate.py db=None closures: _state_row()
                      (the class's row IS the only store there);
                      io.py listing/1: the no-mint read; compiler_v2's
                      -table check: the no-mint read
    _dispatch_fn      _install: `row = pred_cls._state_row()` inside the
                      ctx (bound by the branch above when db is given,
                      minted by `_mutate` when it is not); _registry.py:
                      `row = cls._state_row()` -- detached ON PURPOSE, still
    _lazy_recompile   same `row` in _install
    _locked           _registry.py: same `row`
    _index_plans*     `_plan_row = pred_cls._state_row()` once per branch

"Spelling the fallback at the site duplicates the facade" was the wrong
objection: with the facades DELETED there is nothing to duplicate, and the
one accessor is documented once.  The detached mode survives (goes with
`make_predicate` at P4, as ruled) as one method, not 7 properties + 4
injected instance descriptors + the `_RELOCATED_STATE_NAMES` machinery.

**Tombstones now raise `RetiredStateError(Exception)`, not
`AttributeError`.**  Found while migrating: `builtins/control.py` probed
`getattr(cls, '_dispatch_fn', None)` — an AttributeError tombstone makes
that answer None SILENTLY, which is the failure a tombstone exists to
prevent.  Not RuntimeError either (the drive loop reads one out of a
generator as exhaustion).  The three earlier tombstones moved to it.  The
metaclass tombstone is a data descriptor, so `cls._locked` raises even on a
class with a FIELD named `_locked`; the instance still reads the field.

Sweep size, measured: ~26 engine sites by hand; ~240 test sites by a
receiver-aware regex (Database receivers `db`/`owner`/`self` excluded), 16
getattr/hasattr probes by hand (7 `hasattr(pred_cls, "_index_plans")`
assertions were VACUOUS — the attribute always existed — and now assert the
class is on its row), test_predrow's F1 section rewritten to pin the new
contract, 4 sites in `packages/clausal-provenance` (a local `_clauses_of`
helper; that suite has no working gate, see W3).  C reads none of the names.

Gate: baseline REGENERATED at 34a6dc79 (146 / 16804), candidate 146 / 16804,
NEW 0 / GONE 0.  One transient NEW — test_funnel_lint pins a MECHANICAL
line number in testing.py, moved by one line; the pin's trail is updated.

Left for P4 proper: `_state_row()` itself and the detached mode; the
`db=None` default of the compile entrypoints; `make_predicate`.  W2 is done.

### Review round — `23a371ea`

roborev job 80 on 9028f9b3, each finding VERIFIED before acting: the
dataclass-goal regression in `builtins/control.py` was REAL (`is_term_instance`
is true of a `@dataclass`; its class has no `_row`) — fixed with
`getattr(cls, "_row", None)` and a test; the "`inspect.getmembers` blows up"
finding was WRONG (tombstones are metaclass attributes, `dir(cls)` never lists
them — measured, pinned). Sweep-mangled prose restored; user docs updated.
The branch tip for landing is `23a371ea`; gate re-run on it is the last
number in this file's scratch (`cand3`).

## APPENDIX 4 — coordination round (operator: "get as far as you can towards P4")

**P2's picture in this file is STALE — corrected by the downstream lane 2026-09-22:**
the `module=` migration is DONE (their own initiative, never dispatched):
102 module-explicit goal sites, 9 implicit left (helpers that take the goal
or predicate as a parameter, no single receiver in scope — their tool
refuses rather than picks). The fix was at ~111 sites in ~49 bodies, not 38.
Answer-set checks on b45171ab vs main: **23 IDENTICAL, 5 red** (was 2/26). Of the 5,
three have exactly one implicit site left. **TWO ARE REAL P2 COUNTEREXAMPLES
with ZERO residue**: `row R1` 12/12 -> 7/12
and `row R2` 1423/1423 -> 1413/1423 — clean runs, some cases
answering differently. **DO NOT LAND b45171ab.** Repro requested from
the downstream lane (per-case diffs, a one-case command against a room path);
my suspects, unmeasured: answer ORDER over cells vs instances, a dedup/
equality edge, a bare-class handle used as a value.

**Downstream census for W2/W3** (all three lanes, same day): 0 retired-facade
reads and 0 `_get_dispatch` calls in the downstream trees; W2 needs no shim. The
constraints on W3 are in `todo/w3-get-dispatch-protocol-downstream-constraints-2026-09-22.md`.

**W3 has a gate now**: `tools/w3_package_gate.sh` (c7cddb55), own venv, 105 /
1566 baseline at 34a6dc79, W2 tip NEW 0 / GONE 0.

Branch tip for landing W2: `c7cddb55` (code at 23a371ea, gate NEW 0 / GONE 0).

### Appendix 4 correction — the two "P2 counterexamples" are DOWNSTREAM-SIDE

the downstream lane measured both rows at SOLVE level on both engines: every
predicate identical in call count, answer count, distinct-answer count and
content under a representation-independent digest (cell `('f', a, b)` and
instance `f(a, b)` fold together). Nothing lost, merged, reordered or
changed. The divergence is the downstream lane's hand-rolled walk over the
answer term (`_atoms_in(item)`: "item malformed", "checklist is missing the
publication row") — the atoms-as-str class-3 family, code inspecting terms
by hand rather than through the seam. **P2 is cleared for both rows.** Not
yet pinned: which representation difference the walker trips on (their
lane). The rulebases: row R1 sort/2 findall/20,
row R2 sort/0 findall/22, no tabling, no NAF, no handle tables.

**Seal lesson, recorded so it is not repeated:** I asked for per-case gold
(case id, expected, answer on each engine) and a `--case` driver. Both are
the §9 leak; a peer cannot waive it and I cannot accept it. The MECHANISM
was the right ask and was all that was needed.

**b45171ab landing now waits on the downstream lane alone**: the 9 implicit
helper sites threaded with `module=`, their walker fixed, the 28 re-run.
No engine change is pending for P2.

### Appendix 4, second correction — the moved rows were the PYTHON BOUNDARY, read through `type(x) is str`

the downstream lane pinned it: their `_atoms_in` collector filtered leaves with
`type(x) is str`, which collected 3/5 atoms per item on their "main" and ZERO
on the candidate, because the candidate's leaves are `atom` (a `str`
subclass). They read that as an engine inconsistency (`is_atom` refuses the
engine's own `atom` class). VERIFIED, it is not:

* `class atom(str)` and `export()` handing out `atom` for an atom and plain
  `str` for text are the RULED Python boundary (2026-09-21; 818143d2 step 1,
  ec30f483 step 2), on CURRENT main f3caddd5 as well as b45171ab. Their
  reference engine 11c38df0 is an ancestor of main that PREDATES both.
* `is_atom` is a TERM-space test and refuses `atom` BY DESIGN (docstring:
  "NOT A TERM, AND is_atom SAYS SO"). Nothing to change in the engine.
* The boundary discriminator is `isinstance(v, atom)`. `isinstance(v, str)`
  (their applied fix, the downstream bodies) also collects TEXT leaves, silently, since
  strings export as plain str on both engines — told them.
* Lesson for both lanes: a "main" reference room must be current main; and a
  digest that folds representation together (theirs folded atom/str via repr)
  cannot see a representation change — agreement is not a result.

P2 stays cleared. b45171ab landing waits on the downstream lane: re-baseline on
current main, the 9 helper sites, the collector fix, re-run the 28.

the downstream lane confirmed, room asserted, and their table is the whole
change in one place:

    engine                     an ATOM comes out as    a STRING comes out as
    11c38df0 (their old ref)   str                     ('$chars', s) tuple
    f3caddd5 (main now)        atoms.atom              plain str
    b45171ab (P2 candidate)    atoms.atom              plain str

`isinstance(value, atom)` applied across the downstream bodies, 12/12 on both engines;
no degrade-to-old-engine form kept. EVERY NUMBER THEY SENT TODAY BEFORE THIS
(incl. 23/28) was against the dead reference; a full sweep on f3caddd5 and a
fresh 28 on b45171ab are running and supersede it.

**OPERATOR CALL, surfaced, not mine or theirs:** the downstream lane's
the downstream sweep reference (dated 2026-09-16) is stale on two axes — the atoms
flip and the boundary landing. Regenerating at a red count would freeze
breakage as expected; it needs re-baselining against current main with the
reds marked KNOWN-RED.

**RULED (operator, 2026-09-22, relayed to the downstream lane):** re-baseline
the downstream sweep reference against current main (f3caddd5), reds recorded as
KNOWN-RED, not frozen as correct. Awaiting their sweep table and the fresh 28.

## APPENDIX 5 — P2 GATE CLEARED: 28 of 28 on b45171ab

the downstream lane, re-baselined downstream checks: **28 match, 0 differ** on b45171ab.
The last three reds were the three bodies with an implicit goal site; ZERO
implicit sites remain (230/230 module-explicit). The two afternoon rows are
green on both engines.

Route change ruled by the operator in their lane: every downstream checks goal site is
`solve(goal, module=m)`; the `--` seam form is DROPPED in the downstream checks (119
sites reverted, 0 remain). Reason: the two out-paths disagree at the boundary
— `--`/`export()` tags atoms as `atoms.atom`, a `solve`+deref answer is a
plain `str` — so no single local atom test is right in a body that mixes
them. All-solve is uniform. Filed engine-side as
`todo/two-out-paths-disagree-about-atom-tagging-2026-09-22.md` (design
question, parked).

Caveats they attached, honestly: the 28/28 was taken BEFORE a units migration
(many downstream corpus files being rewritten by a lane that is not a downstream user, not
downstream checks, not engine — citations/parameters .clausal, new .seam siblings,
a downstream key-spelling helper) reached the downstream declaration files; five domains
currently die on `strict_atoms: undeclared atom 'units' used as a dict key`
in a sweep on main, which is that half-applied migration, not the engine.
They will re-run the 28 alongside the downstream sweep reference re-baseline once the
tree is quiescent. Their eval bodies are UNCOMMITTED pending the
operator's commit-boundary call.

**Landing:** W2 branch tip carries P2; `main..tip` is a fast-forward. Engine
gates on 23a371ea: house NEW 0 / GONE 0, packages NEW 0 / GONE 0. Awaiting the
operator's "land it" (recommended: after the settled-tree confirmation run).

**Appendix 5 follow-up:** the many downstream corpus files rewrite was a downstream user — the
operator ruled "a dict key is an ATOM", so every chars-carrier key in the downstream corpus become bare atoms, and `_key_spelling` now REFUSES the
carrier and the reserved 1-tuple. Applied in place, broke five domains via
inherited `-strict_atoms` (downstream declaration files with no directive of their own are
still strict), REVERTED; tree consistent at 8309eab7 + the downstream eval bodies.
Redo goes through a worktree and lands in one pass. Two consequences for P4:
the downstream re-baseline and the settled-tree 28 wait for that single pass;
and a downstream user now counts an ATOM read as an object-shaped access, so the
non-downstream W1 answer is 3, not 0 — note for W4's sizing, not a blocker.

## APPENDIX 6 — LANDED on main `1c1afb76`; one downstream break surfaced, and it is P2's

Landed as a fast-forward of a rebuilt branch (code trees byte-identical to
the gated one; notes rewritten neutrally). The downstream lane's re-baseline
is done and the downstream answer-set checks are 28/28 on the landed engine.

**The break**: a downstream pre-commit check does
`isinstance(item, reflection.Clause)` then reads `item.goals` (10 sites, 2
files). Measured on three engines: on the OLD engine the nine reflection
vocabulary names were classes whose calls built instances; on the P2
candidate they were still classes but their calls built CELLS, so
`isinstance` was already FALSE and `.goals` already gone — the check had
been silently skipping every item since P2; on main they are constructor
FUNCTIONS (c2c977bd) and `isinstance` raises TypeError. W2 made a silent
skip loud. NOT reverted. The migration spellings predate W2 and are
exported from `clausal.reflection`: `is_v(term, Clause)` (False, never
raises, on a non-cell; accepts a tuple) and `vfield(term, "goals")` (by
field NAME off `_VOCAB_FIELDS`; raises unless `default=`). Handed to the
A downstream user, whose tooling it is.

**Census lesson (the downstream lane's, kept):** W1b's "31 sites hold a
class as a value / 0 isinstance on PredicateMeta" is a FLOOR. A census keyed
on the NAME `PredicateMeta` cannot see an ALIAS of a vocabulary class —
`reflection.Clause`, `Goal`, `Atom`, `Variable`, clpb's, term_expansion's.
Before W4, sweep the aliases: every exported vocabulary name, by name.

**Appendix 6 follow-up:** a downstream user migrated its tooling (their
e2066b11) and the pre-commit check runs again. CORRECTED COUNT: **13
`isinstance(x, reflection.<Name>)` sites + 31 cell-FIELD reads**
(`.name` 11, `.args` 6, `.kwargs` 3, `.position` 3, `.goals` 3, `.head` 2,
`.value/.keys/.values` 3) — the field reads are the larger half and break
identically (`('Atom', 'units').name` is an AttributeError); a census of
`isinstance` cannot see them. Verified by positive control (traceback 1 -> 0,
a units report 0 -> 1, a 24-test suite 2 -> 24 passed). Every green from
that check between P2 and now was over an EMPTY population. Open: their
`_tools/test_check_provisions.py` is 259 failed / 12 passed with tooling
unmodified, before and after — asked for error SHAPES to say if it is ours.

**Answered:** of the 259, 257 were the `isinstance` TypeError from one
tooling line — P2's representation change, repaired by the `vfield`
migration (259 -> 102 once stale `__pycache__` was cleared; the "identical
before and after" was two trees running the same pre-fix `.pyc`). The
remaining 102 are assertion/KeyError shapes with ZERO RetiredStateError and
zero tuple-attribute errors: the checker now RUNS and reports content its
tests disagree with — the first honest look at that suite since P2, and not
the engine's.

## APPENDIX 7 — W3 LANDED on main `c5d62557` (operator: "when W3 is ready, land it")

Three commits, fast-forward: `DispatchTargetError(LogicException)` from the
funnel's tail (e7ac22ad), the tabling pass reading dispatch off the row plus
the rulings in the scope note (a58d38f9), and the review round (c5d62557:
culprit is the value, repr bounded, end-to-end module-shadow test with a
stdin-probe positive control). Gates on c5d62557: house 146 / 16814 vs
146 / 16807, NEW 0 / GONE 0; package gate 105 / 1566, NEW 0 / GONE 0.
Barrier scan of the range: 0 hits. Both downstream gates were re-keyed
BEFORE landing (two-arm markers); told to drop the old arm now. The
downstream lane told main moved. NOT pushed to box or GitLab.

**W3 is done.** Left for W4: `PredicateMeta._get_dispatch(arity)` and the
funnel's `PredicateMeta` arm, which go with the class; and BEFORE W4 is
sized, the alias sweep — every exported vocabulary name (reflection's nine,
clpb's, term_expansion's two) and every cell-FIELD read, since three
censuses today each turned out to be a floor.
