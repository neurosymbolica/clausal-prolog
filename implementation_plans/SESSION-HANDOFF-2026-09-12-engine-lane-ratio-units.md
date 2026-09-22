# Engine lane handoff — 2026-09-12, ratio units

Continues `SESSION-HANDOFF-2026-09-11-engine-lane-minor-units-END.md`, whose "Open" list had
ratio units as the designed-but-unbuilt item and corpus-lane's live blocker. They are built.

## 1. What landed

`percent` and `basis_point`, **dimensionless scaled units**, in `clausal/modules/units.py`:

    RATIO_UNITS = {"percent": 2, "basis_point": 4}     # name -> decimal exponent
    percent     = _make_ratio_unit("percent")          # Quantity(Decimal('0.01'),   {})
    basis_point = _make_ratio_unit("basis_point")      # Quantity(Decimal('0.0001'), {})

    -constant_number_units(min_leverage, 300, basis_point)

      stored                    Quantity(Decimal('0.0300'), {})
      constant_number_units/3   300, basis_point
      constant_value/2          Quantity(Decimal('0.0300'), {})

The previous landing's claim that "the mechanism needs nothing new" held exactly: the
directive, the `300 (basis_point)` annotation sugar and the arithmetic all took them
unmodified. The whole feature is a 3-line table, a 1-line factory and two bindings.

**Singular, not plural.** Every other unit name in the repo is singular (`metre`, `usd_cent`,
`penny`) and `docs/currency.md` already spelled it `basis_point`. The todo's title said
`basis_points`; the convention won. `bps` and `pct` are NOT units — they stay abbreviations
the vocabulary does not hold, which is what keeps the scale lint's hand-maintained half alive.

## 2. The exactness question the todo said to verify — and why its reason was wrong

The todo warned that the currency coercion path might be what makes minor units exact, and
that a dimensionless quantity may not have it. Measured **with a negative control**, because
a probe that cannot show inexactness cannot certify exactness:

    300 (basis_point)        Decimal('0.0300')      exact
    5.25 (percent)           Decimal('0.0525')      exact
    0.5 (basis_point)        Decimal('0.00005')     exact
    Fraction(1,3) (percent)  Fraction(1, 300)       exact
    7 (gram)   [control]     0.007, a binary float  INEXACT

It is **not** the currency coercion. `_to_decimal` is keyed on an `is_currency` dimension and
lives in the branch of `Quantity.__init__` that a scaled unit returns before reaching
(`terms.py:2372`). Exactness comes from `_num_pair`, which is **dimension-agnostic** and reads
a float beside a `Decimal` as `Decimal(str(f))`.

So the single load-bearing requirement is that the FACTOR is a `Decimal` — which is what
`_make_minor_unit` already argued for currencies, and what `gram = Quantity(1e-3, …)` does not
have. The `scaleb`-check-the-multiplication contingency the todo held in reserve was not
needed.

**Worth keeping as a shape**: the todo's worry named the right risk and the wrong mechanism.
Minor units and ratio units are exact for the SAME reason, and it was never the currency one.
A correct conclusion resting on a wrong mechanism survives until the mechanism is the thing
that changes.

## 3. Two instruments this landing broke, both invisible before it

### 3a. The exporter's inline refusal was blind to exactly this shape

`_is_known_scaled_unit` selected `isinstance(v, Quantity) and v.dims`. **`and v.dims` excludes
a dimensionless scaled unit** — a ratio unit's shape. Measured blind before the fix, with a
dimensioned probe as the positive control showing the checker can refuse:

    dimensioned scaled unit  (control)  refused = True
    DIMENSIONLESS scaled unit           refused = False      <- the defect
    usd_cent (real minor unit)          refused = True

The DECLARATION path (`_base_unit_names`) refused correctly throughout. Only the inline path
was blind — the same half-covered-surface shape corpus-lane found on 2026-09-11, when
`pay(155000(cent))` reached `_try_quantity` rather than `_collect_constant`.

**It matters more here than for `cent`:** dropping `basis_point` from `300(basis_point)` emits
`300` against a stored `0.03`, a **10000x** error, and `<downstream-domain>` — the
domain that motivated ratio units — is on the export roster.

**The clause excluded NOTHING on the day it was written.** There were zero dimensionless
`Quantity` constants in `units.py`, so no instrument could have noticed; the fix adds exactly
`{basis_point, percent}` to the refused set and removes nothing, which is also why it cannot
regress an existing export. This is the hard version of "an instrument keyed on a property the
checked thing does not have": invisible until the population changes.

### 3b. The TitleCase alias gate required an alias for units that cannot have one

`test_alias_table_is_complete` asserts every lowercase unit appears in
`_DEPRECATED_UNIT_NAMES.values()`. It was written when every unit in `units.py` had a
TitleCase ancestor. TitleCase became a **load-time error** on 2026-09-10, so a unit added
after that has no ancestor, and minting `Percent` would be adding to the vocabulary that error
exists to remove.

Fixed by exempting `set(units.RATIO_UNITS)` — **derived, not listed by name**, so a third
ratio unit needs no edit here. Mutation-verified in both directions: dropping every alias for
an existing unit still fails it, and emptying the exemption fails it too.

**A method note about my own instrument, not the code.** My first mutation probe popped the
key `"Kilometre"`, which does not exist (the real keys are `Kilometer`/`kilometer`), so the
gate "passed" under a mutation that never happened and I briefly had a gate that looked
toothless. The probe reported success for doing nothing — the dominant failure mode in this
repo's notes, arriving this time inside the tool built to check for it.

## 4. The scale lint's hand-maintained half shrank, and its own control said so

`_HAND_MAINTAINED_SCALE_WORDS` carried `bps`, `basis_points`, `percent`, `pct` with a comment
saying they move to the derived half when ratios land. They did.

Done deliberately in two steps: the derivation was extended **first, with the hand list
untouched**, purely to watch the overlap assertion fire. It did, naming both words to drop.
A half designed to shrink now has a demonstrated way of noticing that it should have — which
is the property the harness lane asked for when they built it and which nothing had yet
exercised.

`bps` and `pct` stay: abbreviations no vocabulary holds and no derivation will produce. The
hand half shrank without emptying, which is the outcome that keeps the residue question
answerable.

**The inline copy of the derivation inside `_scale_suffixes` was deleted** in favour of calling
`_derived_scale_words()`. Two copies would have let the overlap control go on checking a set
the lint no longer used — and the extension had to reach both, so this was required rather
than tidying.

Net new suffixes: `basis_point` (singular) and `percents`. `percent` and `basis_points` were
already in the set by hand, so the lint's population barely moves.

## 5. Where this leaves corpus-lane's blocker — read this before migrating

Ratio units are built, and `<downstream-domain>` **still cannot migrate and stay exported**:
the exporter refuses a ratio-unit amount for the same reason it refuses every scaled unit.
Option 2 (`todo/exporter-folds-scaled-units-to-the-wrong-magnitude-2026-09-11.md`) was already
load-bearing after the "follow statutes" ruling; it now also blocks the blocker this landing
was meant to clear. **That is the honest status: the engine half is done, the path is not.**

Unchanged and still true from the todo's own analysis:

* A domain whose PUBLIC interface computes in bps (`leverage_ratio_bps/2` is exported) must
  rescale producers and consumers together. Cheaper — no representation changes at any
  interface — not free.
* The bare `300` at `leverage_ratio.clausal:111` under `check_ratio_gte/6` is **still
  invisible** to the lint, because the discriminator is the FUNCTOR's name. Ratio units do not
  touch that; the callee's-parameter design in the previous handoff is still the fix, and it
  is the one that would check the site that decides.

## 6. The three claims — and only one of the three was actually measured here

| axis | who | result |
| --- | --- | --- |
| engine suite | me | baseline `144 failed / 16199 passed / 1 error`; after `144 failed / 16219 passed / 1 error` — failure NAME SETS **identical**, 0 new / 0 fixed, both sets non-empty at 144. The +20 passed are exactly the 20 new tests. Same single collection error (`test_clportools.py`) in both arms. |
| doc blocks | me | 38 before and after — and the scanner was **positive-controlled** into the new section: breaking one new ```clausal block took it to 39, restoring took it back to 38. |
| scale lint noise floor | me | 2 warnings in each arm, unchanged from the recorded floor. |
| export bytes | iso-export-lane | **NOT RUN.** `clausal/tools/clausal_to_prolog.py` changed. |
| domain answers | the harness lane | **NOT RUN.** `clausal/templating/term_rewriting.py` and `clausal/modules/units.py` changed, and term_rewriting is on the load path for all 82 harness bodies. |

**How the engine-suite arm was measured, because the method is the claim.** Both arms ran in
ONE throwaway worktree (`.claude/worktrees/ratio-baseline`, detached at `c8f38336`, with the
24 `.so` files copied in and the engine path asserted by `realpath` before trusting anything
it said). The baseline ran the untouched checkout; then the six changed files were copied in
and the after arm ran. Nothing in the shared clone was reverted at any point, which is the
hazard the previous handoff names: reverting engine source in a tree other lanes are reading
surfaces as a `SyntaxError` blamed on an unrelated file.

The six files were confirmed **byte-identical** between the clone and the measured worktree
and content-pinned at `sha256 a6518ff0…`, because a sha names what HEAD said, not what was
read (iso-export-lane's rule, 2026-09-11).

**A first run was DISCARDED and it is worth saying why.** I started an after-arm in the clone
and then kept editing source while it ran. That is a torn read by construction; it happened to
be running during the alias-gate fix. Reported as a number it would have looked like a
measurement. The only thing wrong with it was invisible from its output.

**What the engine-suite arm cannot see, stated so someone who knows more can act on it.** Both
arms ran inside `.claude/worktrees/`, where this repo's notes say the fmt/rewrite corpus tests
are red by construction. That distortion is symmetric across the two arms and cancels in a set
diff — but it means the 144 is a worktree number that happens to agree with the recorded
baseline, not an independent confirmation of it in the primary tree.

## 7. Open after this

- **Option 2 for the exporter** — fold to the BASE magnitude. Now blocks ratio-unit migration
  as well as minor-unit migration; export stays lossy either way (it fixes the magnitude, not
  the unit).
- **The lint is still blind to a bare literal under an unscaled functor**, which is where
  `<downstream-domain>`'s deciding `300` sits. Ratio units do not change that. The
  callee's-parameter design is the fix worth building, because it checks the site that decides.
- **Only two ratio units.** `per_mille` and friends are one `RATIO_UNITS` entry plus a
  binding; `test_every_declared_ratio_unit_is_bound_in_the_module` fails until the binding
  exists, and the lint and exporter pick it up with no edit.
- Everything else from the previous handoff's Open list is unchanged, **Box included** — it is
  still the only tree on the old vocabulary.

## 8. The one method note worth carrying forward

Three separate instruments in this landing were wrong in the same direction, and none of them
was wrong about its own subject:

* `_is_known_scaled_unit` filtered on `v.dims` — correct about every value that existed when
  it was written.
* `test_alias_table_is_complete` required a TitleCase ancestor — correct about every unit that
  existed when it was written.
* my own mutation probe popped `"Kilometre"` — correct about a key that does not exist.

The first two are the previous handoff's "the instrument stayed the same while the world it
measures moved". The third is not: it was wrong on the day it was written and reported success
anyway. **The difference is worth keeping, because the fixes differ.** A stale instrument needs
its enumeration derived from an authority. An instrument that can only say yes needs a
negative control — and the cheapest one is to mutate the thing it checks and require it to
fail. Every gate touched here now has one.

---

# Peer measurements, same day — two of my open questions answered by other lanes

## corpus-lane: the new suffixes are dead, and here is what ratio units actually unlock

My handoff flagged that `basis_point` (singular) and `percents` might shift their 76-pair
prediction, and said I could not check it from here. Measured: **zero corpus identifiers end
in either.** The lint's suffix set grew without moving the count, so the 76/23 prediction
stands unchanged.

The number neither of us had, which is the one worth keeping:

    ratio-suffixed functors carrying a bare literal:  21 (file, identifier) pairs, 9 domains

      5  <downstream-domain>        5  <downstream-domain>
      2  <downstream-domain>
      2  <downstream-domain>             2  <downstream-domain>
      2  <downstream-domain>
      1  <downstream-domain>           1  <downstream-domain>

45 ratio-suffixed functors exist corpus-wide; 21 pairs carry a bare literal and are therefore
migratable. Money was 171 values across 15 domains, so **ratios are about an eighth of the
work across 9 domains rather than 15.**

They also record that `<downstream-domain>`'s five `_percent` warnings were previously reported to Mike as
"genuinely not migratable", and that sentence is now wrong — they are migratable the moment
this reaches canonical. Their own framing: an accounting of a domain's remaining warnings had
a shelf life measured in HOURS. That is the shape-list-ages rule from 2026-09-11 in different
clothes, and it applies to counts reported upward, not only to instruments.

## iso-export-lane: no export arm, on a measured basis — and they checked what I did not

They skipped the export-bytes run, having measured reachability rather than taking my word:
**no corpus or library file writes a ratio unit as a unit literal** — `basis_point`,
`basis_points`, `percent`, `percentage`, `bps`, `pct` all return zero `N (unit)` sites across
the pinned corpus and library. What `<downstream-domain>` carries is `leverage_ratio_bps`,
`minimum_leverage_bps`, `gsii_buffer_rate_bps`, `gold_ratio_bps` — bare integers with the
scale in the NAME, the identical pattern to the 139 `_cents`/`_satang` identifiers. So the
changed selection is unreached and a zero would have been the cheap kind.

**The part worth carrying: my set-difference argument was sound and incomplete, and they said
so.** It was scoped to `_is_known_scaled_unit`'s refused population and silent about the other
two changed files. They checked those separately (units.py adds definitions nothing writes;
term_rewriting.py is a lint vocabulary producing warnings, not exported bytes). Their
sentence for it is the keeper: **"the commit I reasoned about is fine" is not the same claim
as "the landing is fine".** Flagging all three files is what let them check; reasoning about
one of three would have looked like reasoning about the landing.

They also noted the failure-set diff is stronger for both arms being non-empty at 144 than it
would be for two green runs, because **a diff of nothing against nothing is satisfied by an
instrument that ran nothing.**

## The sequencing fact both lanes independently landed on

Option 2 for the exporter was already a prerequisite after the "follow statutes" ruling. It
now ALSO gates the feature built to fix leverage ratios. **Two independent routes to the same
blocker makes it a sequencing fact rather than a preference**, and iso-export-lane is taking
it to Mike in those terms while he decides whether option 2 stands alongside the Prolog units
library.

## the harness lane: canonical is clean, and the transform-time argument is VERIFIED not agreed

    82 rows on c8f38336, fingerprint c8f38336/so1789092742, one value, zero torn
    82 unchanged   0 moved   0 no-score   0 unpinned

That closes a five-commit live gap on canonical — `term_rewriting.py` had been edited by two
separate landings (the scale-lint declared union, and this one) with no sweep between them.
Nothing moved, so the wide bisect range never mattered; it was still the right thing to name
in advance, because a moved row would have had a 5-commit range and not a 1-commit one.

**On whether the clone's missing compiled trampoline matters for these two commits.** I argued
it does not, because both load-path changes are transform-time rather than runtime. That is
the kind of argument that is convenient enough to deserve checking, and it was checked twice —
by the harness lane and then independently here:

    _name_claims_a_scale  has exactly TWO call sites, term_rewriting.py:6424 and :7986,
    and both terminate in `warnings.warn`. Neither mutates the AST or the emitted Python.

So widening the suffix set cannot change the transformed output by a byte, and what the
trampoline later solves is identical either way. The `units.py` half is additive module-level
names nothing imports — import-time only, equally out of the trampoline's reach.

**The bound the harness lane put on that, which is the part worth keeping:** it holds
because those two call sites were read, NOT because transform-time changes are a category
that is exempt. A transform-time change that altered emitted output would be exactly as
exposed as `sum_list/2` was. The argument is about these two commits, not about a kind of
commit.

**Why the clone's trampoline was not built.** The procedure in
[[rename-swap-so-under-live-importers]] has a SIGBUS failure mode that lands on whichever lane
has the clone mapped — a risk taken in someone else's session to measure two commits that are
going to canonical anyway. Promote-then-sweep gets the compiled path for free and puts the
risk nowhere. the harness lane will run it on canonical once promotion is approved.

## A design property for assertions, from this landing's one genuinely new idea

The overlap control fired and **named the two words to drop**. A control that fires tells you
something is wrong; a control that names what to do tells you what to do next, and I did not
have to work out which words the derivation had taken over — the assertion said. Worth asking
of every new assertion, and it is cheap: the information is almost always already in hand at
the raise site, since the check just computed it.

---

# PROMOTED: canonical is `cc008788` (2026-09-12)

    canonical   c8f38336 -> cc008788   4 commits (2 code, 2 handoff), clean ff, NO C changes
    clone       cc008788               identical
    box         NOT landed — still the only tree on the old vocabulary

Pre-flight, all done rather than assumed: ff confirmed possible by `merge-base`; crossing range
checked for other lanes' commits (none, all four mine); barrier scan of the added lines clean;
canonical's working tree carried no tracked modifications to disturb.

Verified by **observation in the canonical tree**, engine path realpath-asserted first:
`RATIO_UNITS == {'percent': 2, 'basis_point': 4}`, `300 (basis_point)` is `Decimal('0.0300')`,
`5.25 (percent)` is `Decimal('0.0525')`, `300 bps == 3 percent`, the exporter REFUSES inline
`300(basis_point)`, `basis_point` is a live lint suffix, `percent` has left the hand half and
`bps` has stayed.

## The first fast-forward did nothing, and the exit code was not what caught it

`git -C /workspace/clausal merge --ff-only <sha>` fails with "not something we can merge" —
canonical has no remote for the clone. **This was already written in this lane's notes, dated
2026-09-11, with the exact failure string and the exact working form. I did not read it before
acting.** What caught it was hashing the three engine files before and after the merge and
finding the hash unchanged (`09cd1344` both times; after the real ff, `be7144b6`).

The working form is `git fetch /workspace/clausal-bug-fix main && git merge --ff-only FETCH_HEAD`.

**The generalisable half is which check caught it.** The notes already said "verify by
observation in the canonical tree" and that would also have worked — but you only run the
observation check if you believe something landed. A merge that did not happen at all is
precisely the case where verification gets skipped, because there is nothing you think needs
verifying. The before/after content hash covers that gap and is cheaper. **A ref is a claim
about the tree; a content hash is an observation of it.** Had the retry been skipped, every
downstream measurement — including another lane's sweep — would have been of the OLD tree
while everyone believed it was the new one.

## Canonical engine suite: 147 failed / 16218 passed / 1 error — and the 3 extra are not mine

My worktree pair said 144. Canonical says 147. Rather than attribute the difference to "a
different tree", each was run down:

| canonical-only failure | cause, measured |
| --- | --- |
| `test_transitive_py_module_import.py` ×2 | They **SKIP in the clone** ("no project venv interpreter with an installed clausal distribution found"), so neither worktree arm ever ran them. Both also fail on `c8f38336` source — the fixture writes `Test(...)`, the TitleCase spelling that became a load-time error on 2026-09-10. Pre-existing, and invisible to my arms rather than introduced by them. |
| `test_atoms_as_cells_flip.py::…is_zero_field_class` | Canonical's WORKING TREE, not its source. The guard AST-parses every `*.py` under `clausal/` and `tests/`, and two untracked generated artifacts (`tests/**/__transformed__/*.py`) are not valid Python. **Passes on identical `cc008788` source in a clean worktree.** Filed: `todo/class-test-guard-scans-generated-transformed-artifacts-2026-09-12.md`. |

**The lesson is about the skips, not the failures.** Two tests skipped silently in both of my
arms, so a set diff between them was structurally incapable of saying anything about those
tests — and the set diff reported 0 new / 0 fixed, which reads as coverage it did not have. A
failure-set diff is blind to everything that skips on both sides, and skips do not announce
themselves in a count of failures. The skip COUNT differing between trees (52 vs 50) was the
only visible signal, and I nearly explained it away.

## The three claims on the promoted tree

| axis | who | result |
| --- | --- | --- |
| engine suite | me | 147 failed / 16218 passed / 1 error on canonical; all 3 above the worktree pair's 144 run down to skips and working-tree artifacts, none to these commits |
| export bytes | iso-export-lane | **0** across 1560 files, raw and normalised, engine content-pinned across the run |
| domain answers | the harness lane | sweeping `cc008788`, extensions verified byte-identical to the `c8f38336` sweep so these two commits are the only variable |

## iso-export-lane's finding, which outlives this landing

Their export zero came with a discovery: their baseline was `3b0e3547`, **56 commits back**
(counted with `rev-list --count` on both sides, after their own eyeball estimate of ~70 —
an unmeasured number inside a report about unmeasured numbers, as they put it). That range
included `6d609eb1`, `-import_from` binding names rather than the module, which sits directly
on the exporter's path.

**"A measured skip is about a change; it is not a claim about a tree."** Their skip of the
ratio-units run was correct and remains correct; what was stale was the inherited "the export
is clean on canonical", which had been carrying a date nobody was watching.

They built a recorder for it (`record`/`age`/`describe`: stores engine and corpus shas with
each verification and reports how far each has moved since, counted rather than estimated),
with the load-bearing test being the STALENESS direction — a recorder that can only ever say
"current" is the same defect as a gate that can only refuse.

**Note for anyone adopting it here: their module lives OUTSIDE the clausal repo** (`859c701` is
not an object in this repo), so importing it into clausal would cross the information barrier.
The idea transfers; the code cannot.

**And it applies one level up, to this lane's own baseline.** I have been careful to say the
144 agrees with the recorded baseline rather than independently confirming it — but that
recorded baseline is itself a measurement with a date and a tree, and nothing watches its age
either. The existing answer in this lane's notes is "never trust a written-down baseline,
regenerate it", which is safe because regeneration is ~3 minutes. That answer stops scaling
exactly where regeneration gets expensive, which is where iso-export-lane and
the harness lane live.

---

# A DEFECT IN THE PROMOTED LANDING, found and fixed: canonical is `dfe1d8f0`

Found by **checking a peer's exoneration instead of accepting it.** the harness lane read
one row as 340/341 once in fourteen sweeps and attributed it to their own instrument. I knew
something about my diff they could not, so I looked.

## What was wrong

`_derived_scale_words()` did `from clausal.modules import units as _units` to read
`RATIO_UNITS`, and `_scale_suffixes()` calls it on **every transform**. Measured in both
directions, engine path asserted in each tree:

    c8f38336 (pre):  transform a unit-free .clausal  ->  clausal.modules.units NOT imported
    cc008788 (post): transform a unit-free .clausal  ->  clausal.modules.units IMPORTED

That is not merely an import. `clausal/logic/_units_flag.py` promises in its own docstring
that **"a program that imports no unit module pays nothing"**. Importing units builds 84
`Quantity` constants, and `Quantity.__init__` calls `_units_flag.touch()`. The flag is read at
six sites in `clpfd.py` (2609, 2748, 3187, 3221, 3291, 3306) and four in `units_clp.py`. So
the landing turned the CLP units side channel ON for every program in the corpus, including
ones with no units anywhere.

**Fix**: `RATIO_UNITS` moves to `clausal/modules/_ratio_data.py`, which constructs nothing;
`units.py` re-exports it so `units.RATIO_UNITS` is unchanged for the exporter and the tests;
the lint reads the data module. Mirrors `countries._data`, a data-only module the same lint
already reads for exactly this reason.

Pinned by `test_transforming_a_unit_free_file_does_not_import_the_units_module`, in a
subprocess because the flag is process-global, **with a positive control** — a test asserting
only "units not imported" would also pass if the lint had stopped reading the vocabulary
entirely.

**It was NOT the cause of the 340/341.** the harness lane scanned all 82 domains for
constraint operators, `all_different` and `label(` — zero hits, `<downstream-domain>` included.
So the branch this enabled is one their axis never takes. A real candidate eliminated by
measurement rather than an absence of one. Their anomaly stays open and theirs; they have
since measured their own error rate at **1 unexplained deviation in 986 row-measurements**,
with 3 of the 4 deviations being true positives.

## The reasoning error, which is the reusable part

I told both lanes the load-path change was "warning-only and cannot change emitted bytes".
the harness lane verified it by tracing `_name_claims_a_scale` to its two call sites and
confirming both terminate in `warnings.warn`. **That was true, and it is still true.**

What neither of us asked is what the function IMPORTS.

* Call sites answer **what the code DOES**.
* Imports answer **what the code BRINGS**.

I made a category argument; they replaced it with an enumeration, which was a strict
improvement and still missed, because an enumeration answers precisely the question its axis
was chosen for. Their formulation: *the enumeration was as narrow as the category had been.*

The candidate replacement, harder to answer and therefore the reason neither of us asked it:
**what is different about the process after this has run that was not different before?** That
covers emitted output, imports, global flags and caches in one question.

## Two instrument failures of my own in the same hour, both fail-open

1. **`-rf -rs` is not both.** pytest's `-r` is a STORE option, so `-rs` REPLACED `-rf`: the
   short summary carried only SKIPPED lines, `grep '^FAILED '` returned nothing from a run
   reporting `145 failed`, and the empty set made every baseline name look "fixed". Write
   **`-rfs`**. The irony is load-bearing: **I added `-rs` to capture the skip set — the
   hardening for the skip-blindness found earlier the same day — and it destroyed the failure
   extraction it was meant to sit beside.** A new arm on an instrument can disable an existing
   arm, and the instrument still reports.
2. **An extractor that PRINTS its count does not ENFORCE it.** Mine printed `0` and I read on.
   It now exits non-zero on an empty set, with both controls run: refuse the bad log, still
   return 144 on a good one.

And a mechanical one worth having: **never `tr -d '\033'` before the ANSI `sed`** — it deletes
the ESC, leaves the literal `[33m`, and every `^ANCHOR` grep then fails silently.

## State

    canonical   dfe1d8f0     the fix, promoted and verified by observation
    clone       dfe1d8f0     identical
    box         NOT landed

    engine suite   144 failed / 16284 passed / 1 error -- failure NAME SET identical to the
                   pre-fix arm, 0 new / 0 fixed, both non-empty at 144
    skip set       52 lines, extracted and recorded for the first time
    domain axis    the harness lane re-running <downstream-domain> against the fix

**A shared box note, from the harness lane's contention experiment:** four `while :; do :;
done` spinners leaked for ten minutes because `LOADPIDS=$(jobs -p)` inside a non-interactive
`zsh -c` captures nothing, so `kill $LOADPIDS` fired at nothing with its error hidden by
`2>/dev/null`. **A deliberate-load experiment needs its teardown verified the same way its
measurement is** — and a load experiment changes conditions for every other measurement on the
box, including the ones it is being compared against. Had I read my suite's slowdown as a
property of my own fix rather than checking `ps`, I would have had a confident wrong answer.

## The three claims on `dfe1d8f0`, complete

| axis | who | result |
| --- | --- | --- |
| engine suite | me | 144 failed / 16284 passed / 1 error — failure NAME SET identical to the pre-fix arm, 0 new / 0 fixed, both non-empty at 144; **skip set (52) extracted for the first time** |
| export bytes | iso-export-lane | 0 across 1560 files, raw and normalised, engine content-pinned across the run |
| domain answers | the harness lane | **82 unchanged, 0 moved, 0 no-score, 0 unpinned, one fingerprint, zero torn**, quiet box, 158 commits from `820dc66f` |

**My named candidate mover was censused before the run and came back empty**, which is what makes
the null informative rather than decorative:

    harness bodies mentioning units at all                      0 of 82
    bodies using a unit construct WITHOUT importing the module  0
    domains declaring units in their RULEBASE                   19

The 19 that touch units declare them explicitly, which puts `clausal.modules.units` in
`sys.modules` exactly as before — the case I bet was safe. Nothing in the population relied on
the side effect that was removed.

**What this does NOT establish, and the asymmetry cannot be closed now.** The removal of an
unintended side effect moved no answer. It does not show the side effect never moved one *while
present*: `cc008788` was swept exactly once, and that sweep is the one carrying the 340/341.
Re-sweeping a tip nobody should return to is the only way to close it, so it stays open as a
known gap rather than a resolved one.

## An open lead for whoever next touches the units surface

`<downstream-domain>` — the anomalous domain — **is one of the 19 that declare
units**, currency units in its queries file. So the one unexplained reading in 1068 sits on a
units-using domain, on the axis of the engine that has moved most this week.

**That is a coincidence worth recording, not an explanation**, and the harness lane declined
to dress it as more. It does not reproduce: 14 targeted runs green on the unfixed tip (6 of them
under genuine four-way load) and 6 green on the fix. Recorded here because the next person to
change the units surface should know which domain to run alone first, and because a lead with no
mechanism is still worth more than an unexplained number with no lead.

Their instrument figures, in the form worth copying:

    1068 row-measurements across 13 sweeps
       4 deviations — 3 real regressions this axis caught, 1 unexplained
       mechanism unknown; TWO candidates eliminated (mine, by census AND by outcome)

**A number with its denominator, its eliminated hypotheses and its open question stated
together** is a far more useful thing to hand the next person than either "it's flaky" or
"it's clean".

And one more instance of the day's dominant shape, theirs: their first check for units in that
domain globbed `*.seam` and found nothing, because the domain has not been renamed and its
sources are still `.clausal`. **The glob answered precisely what it asked.** They checked which
files exist before repeating the claim.
