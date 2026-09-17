# Engine lane handoff — written 2026-09-16, work done 2026-09-15

Supersedes `SESSION-HANDOFF-2026-09-15-engine-lane-END.md`, which this session
began by reading. That one's OPEN items 1 and 2 are now CLOSED.

## LANDED 2026-09-16 (later session, on the operator's direct word)

NEXT item 1 is DONE. `c69a59b9` (tree `fdfac1e9`) is now on canonical main and
the box main by fast-forward, and on the clone main by merge commit `0b39a913`.
Pure Python, no rebuild; observed on canonical and box with the 37 new/renamed
tests + funnel lint (exit 0). GitLab not pushed. Items 2–4 below are unchanged.

NEXT item 2 (the transfer form + quantity_number/2) is BUILT on this branch:
c6819b7e..440a526d, gated NEW 0 against qt-baseline (e43d2fa6),
49 tests added. Spec docs/superpowers/specs/2026-09-16-quantity-transfer-form-design.md,
plan docs/superpowers/plans/2026-09-16-quantity-transfer-form.md. Not promoted:
it lands with the dates-are-terms work, behind harness-batch-lane's date
migration. The exporter's Prolog-side quantity_number/2 is still theirs.
OPEN for the consumer design: `from_transfer` converts any tuple headed
`quantity`/`rdiv` at any depth, so the first real boundary needs a ruling on
a rulebase's own `quantity/2` term crossing it.

NEXT item 3 (PredicateMeta P1 reroutes) is BUILT on this branch:
`eef9d8b2..HEAD`, gated NEW 0 against p1-baseline (`eef9d8b2`), 37 tests added
by the build and 18 more by the FIX WAVE (2026-09-17, `5555bfc7..f55b0a31`
plus this handoff commit, closing roborev job 73 and the final opus review;
`tests/predmeta_p1/` collects 59); spec
`docs/superpowers/specs/2026-09-17-predmeta-p1-reroutes-design.md`,
plan `docs/superpowers/plans/2026-09-17-predmeta-p1-reroutes.md`.

Census (`tools/predmeta_census/P1_SITES.tsv`): 10 rows CLOSED — 6 `-done`
(4 `R!-done`, 1 `S-done`, 1 `R-enum-done`) and 4 `R-fallback` (rerouted
row-FIRST with a class read deliberately kept and reported) — 40 still
expected. The fix wave expected 8 done + 2 fallback and MEASURED 6 + 4: its
own M2 and L4 fixes put a reported class fallback back into
`globals_env.signature_for` and `testing._note_generic_compound_confusion`,
which is the same shape `database_ops._find_pred_cls` has, and the new
region check FOUND both before they were re-booked. `check_p1.py` closes a
row by REGION now (the enclosing def in the working tree, located by the
qualified name the canonical line sits in) rather than by literal-snippet
absence, holds `R-fallback` rows to the opposite requirement (the class read
must be present, with a row read beside it), and UNIONs the table's closed
rows into check 1's population so it survives landing.

Four sites LEFT, each with an in-tree measurement, at these WORKTREE lines
(canonical-tree line numbers in the TSV, which drift from these):

* `compiler_v2.py:239` (S) — the guard is not redundant: 34 of 14,615
  arrivals over the suite find a non-class under a functor that has clause
  nodes.
* `compiler_v2.py:292` (R, THE WART) — the `-dynamic` set lives on the
  class's own row, and for a clause-less declaration that row is still
  DETACHED here, so `db` cannot name it; the set does not move.
* `compiler_v2.py:930` and `compiler_v2.py:968` (R) — a predicate DECLARED
  with no clauses has a class and no row at all; `db.row(...)` would refuse
  a `-discontiguous`/`-table` load these two sites accept today (spec §4).

Class reads left at CLOSED sites (deliberate, not leftover — this is the list
P4 has to remove, and it is the list the final review found incomplete):

* `compiler/arg_index.py` `hint_row` — the own-row fallback the four R! sites
  share. Row first; when `(fname, arity)` misses, the object bound under
  `fname` in `base_globals` answers through ITS own row, and only when that
  row's key agrees with the call's arity. No longer restricted to the dotted
  spelling (final review I3, ruled), so a rowless callee keeps its hints.
* `compiler_v2.py` ~312 `cls_row = getattr(pred_cls, "_row", None)` — the
  `-dynamic` site's membership test IS a class read: the set lives on the
  CLASS's own row and `db.row(functor, arity)` is vacuously true there. The
  row cannot close without the class; booked `R-fallback`, not `R-done`.
* `compiler_v2.py` 313-332 keeps `pred_cls` for `_belongs_elsewhere`/
  `_bind_row` after that read.
* `database_ops.py` `_find_pred_cls` keeps the `type(head)` identity
  comparison, and the arity-checked class read answers on THREE legs now: no
  row here, the named row holds a class of another arity, and neither the
  module's binding nor the head's own class is on the named row (final review
  I1 + roborev L3).
* `compiler/globals_env.py` `_GlobalsDb.signature_for` — the class answers for
  a hand-built globals dict with no `$module`, arity-checked (roborev M2).
* `testing.py` `_note_generic_compound_confusion` — the class leg sits ahead
  of the atom branch so a DECLARED clause-less predicate still gets its
  generic-compound note (roborev L4).
* `compiler_v2.py` ~868's `_redefinition_error` diagnostic still takes
  `pred_cls` as an argument (it arrives already resolved — the isinstance
  test there was a `None` check).

FILES TOUCHED BEYOND THE PLAN'S FILE MAP, both justified (final review minor
9): `compiler/arg_index.py` — the four R! sites' shared callee resolution was
factored into `hint_row` there rather than copied four times, which is where
the class read they keep now lives; and `compiler/goal_shallow.py` — the
production caller of `call_site.analyse`/`populate_runtime_from_plan`, which
had to thread `ctx.db` into them for the reroute to see a Database at all.

The equivalence has a measured LIMIT: `db.row(f, a) is not None` is exact for
clause-having and `-dynamic`-declared predicates, and WRONG for a predicate
DECLARED with no clauses and not `-dynamic` — that shape is a `PredicateMeta`
in the module dict with no row at all. `tests/predmeta_p1/test_membership_equivalence.py`
now pins this as a NEGATIVE case
(`test_row_existence_is_NOT_equivalent_for_a_declared_clause_less_predicate`):
if it ever starts passing because `row()` changed meaning, the three sites
left on the class for this reason (`compiler_v2.py` 930/968 and
`_find_pred_cls`'s fallback) can be reconsidered.

harness-batch-lane measured 82 of 82 sealed harnesses UNCHANGED at branch tip
`6aab7b14` — a CUMULATIVE null across the range `c69a59b9..6aab7b14`
containing the arity-exact change, NOT an attributable "P1 moved no row" (it
is written exactly that way on purpose). **That sweep PREDATES `13dcd93e`
(the first review round's class fallback) and the whole fix wave, which adds
two more behaviour changes — a rowless callee now gets hints, and
`signature_for` is arity-exact. The agreed re-run at the FINAL tip is
therefore REQUIRED before promotion, not optional**; iso-l3 must sit at that
sha and not move while they copy the `.so` files. Their constraint:
`b26f41dc` (bare-date refusal) promotes TOGETHER with dates-as-terms.

LANDING DAY, the full procedure:

1. `P1_SITES.tsv` column 2 holds CANONICAL line numbers. Refresh it for every
   NON-CLOSED row (the 40 still expected) once these commits reach the
   canonical tree: their sites do not move, but everything above them does.
   The 10 closed rows keep the line they have — it is their identity in the
   census's key space, not a pointer to live code.
2. Do NOT expect the closed rows to survive in the canonical scan. SEVEN of
   the ten are mechanically sourced (`M` in column 3 — measured, where the
   earlier note said six; the other three are `H`, recorded in
   `census.VERDICTS`, which is a static dict and survives landing on its
   own). The seven were in check 1's population only because
   `census.classify` still finds their pre-reroute spelling in
   `/workspace/clausal`; the moment these commits land there, that spelling
   is gone and they would read as "in table, absent from census". Check 1
   UNIONs the table's own closed rows into the population for exactly this
   reason (`census_A_sites(rows)`), so nothing has to be done for them —
   simulated: population without the union 40 vs 50 table rows = 10 EXTRA and
   a RED checker for having been landed; with it, 50 and 0.
3. Re-run `check_p1.py` and `check_p1.py --controls` in the canonical tree
   after the refresh. Nine controls must fire and the real table must PASS.
4. The closed rows are judged against the WORKING tree, so they answer the
   same before and after landing; a canonical-tree run is a check of the
   refreshed column 2, not of the reroutes.

Todos filed on this branch: `dynamic-at-another-arity-moves-the-class`
(pre-existing, found by Task 3, `todo/dynamic-at-another-arity-moves-the-class-2026-09-17.md`);
`bind-row-does-not-migrate-index-plans`
(`todo/bind-row-does-not-migrate-index-plans-2026-09-17.md`, filed this
session, not yet committed); `bucket-refs-ir-parallel-parity-is-vacuous`
(`todo/bucket-refs-ir-parallel-parity-is-vacuous-2026-09-17.md`, filed this
session, not yet committed).

## State: NOTHING LANDED — but the blocker is gone

    canonical main                        42160eb5   untouched
    clone main                            067de86d   untouched
    feat/iso-l3-lowering-2026-09-14       72 commits, clean, head ad63a18c
    iso/dims-rekey-on-canonical-2026-09-15 clean, head c69a59b9   <- THE MEASURABLE TREE

    box  /workspace/clausal        main 42160eb5 + both branches above
    box  the corpus tree                    (72 commits, ff'd)
    box  the kit tree                       (126 commits, ff'd)

**The `_dims` rekey is FULLY GATED on both axes and is not promoted.** Promotion
is now a decision, not a dependency. It needs the operator's direct word.

---

# 1. What was RULED — the `quantity` encoding, four questions closed

Operator's rulings, interactively, 2026-09-15. Recorded in
`docs/superpowers/specs/2026-09-14-retire-predicatemeta-section4-answer.md` and
the design record `docs/design-records/terms-as-tuples.html` (republished to the
same URL — the README is right that a new URL is worse than a dead one).

* **A quantity is a PYTHON OBJECT, not a term.** It stands in for a NUMBER: it
  must be an operand of `#=/2` and the CLP arithmetic, and a compound term is
  not a number. That is the line against `date`, which is never an operand.
* **Why a tuple form exists at all:** subinterpreters (or-parallelism), process
  boundaries, and `.pyc` bytecode caches. **NOT same-interpreter seam crossings**
  — a seam passes the object. My naming the seam was wrong.
* **The named unit does NOT survive; the RATIO does.** `unit(Ratio, Dimensions)`,
  always `unit/2`. Currency names survive anyway, free, because a currency is a
  SELF-KEYED BASE DIMENSION — which is why "1550.00 euro wants to print as euro"
  was never at risk.
* **Dimensionless is the atom `dimensionless`** — already a real unit predicate,
  already what `str()` emits so the value round-trips.
* **Conversion is EXPLICIT:** `quantity_number(QuantityTerm, Number)`. Clausal
  binds the object; a units-less Prolog binds the number scaled to the standard
  unit. Call sites are per-boundary, deliberately unfixed.
* **Dims are a plain DICT inside, a TUPLE on the wire.** The hashability
  argument that first chose the tuple was about a RUNTIME term and never reached
  the stored map: `__hash__` is `hash((value, frozenset(dims.items())))`, so
  `_dims` was ALWAYS unhashable. The `mappingproxy` was the only thing blocking
  marshal.

Two things I asserted and had to withdraw, both measured false by the operator's
challenge:

* **A dict DOES have an ISO spelling.** Scryer and Trealla both read
  `{'metre':1,'second':-2}` as `{}(','(:(metre,1),:(second,-2)))`.
* **The canonical sort is NOT an invariant.** Dicts are order-insensitive, so it
  is a BOUNDARY step. It returns on emit, because a curly term is a term over
  there: `{a:1,b:2} == {b:2,a:1}` is false in Scryer (measured with a positive
  control so the test could say yes).

The wire form stays a tuple for one measured reason: **a dict literal cannot be
a bytecode constant.** The tuple folds whole into `co_consts` (2 opcodes); the
dict does not fold at all and is rebuilt per evaluation (12). And the conversion
is free by a coincidence the operator spotted — the functor-first pair form IS
what `dict()` accepts: `dict(t[1:])` 133 ns, `('dimensions', *sorted(d.items()))`
220 ns.

---

# 2. What was BUILT — the `_dims` rekey, four gated tasks

Plan: `docs/superpowers/plans/2026-09-15-dims-rekey-to-atoms.md`.

    9615e8b1  plan
    077dee2c  the unit-metadata registry, keyed by atom      (+ injectivity gate)
    e57b0f67  _dims a plain dict; `dims` returns the view
    07e3816c  metadata from the registry, not off the key
    6eb7afa5  _dims keyed by ATOMS
    7b9162e3  the last three dims assertions
    ad63a18c  funnel-lint: re-anchor the terms.py allowlist end

`clausal/modules/_unit_registry.py` is new: atom -> `UnitInfo`, data-only like
`_ratio_data` (it must never import `units`, which builds 84 Quantity constants
and turns the CLP side channel on for the process).

**THE PART THE PLAN GOT WRONG, and it is this spec's own §4 lesson landing on its
author.** A dims mapping is stored in FOUR places and I normalised one:

    Quantity._dims        normalised in the first pass
    UnitState.dims        MISSED -- constraint stops matching the quantity that satisfies it
    constrain_var_dims    MISSED -- `clean` is compared against existing.dims
    Link.dims             MISSED -- shadow binds, user's var never gets its units back

Every one of those failures is **silent**: the goal simply stops holding. There
is now one `atom_keyed_dims()` in `clausal/terms.py` and all four call it.
Rulebase code reaches it too, via `make_quantity/3` and `++`.

**A latent bug the rekey FIXES:** `_helpers.py`'s standard-order key is
`tuple(sorted(term.dims.items()))`. With predicate keys that could only ever
have worked for SINGLE-dimension quantities — two or more raise
`TypeError: '<' not supported`. So `sort/2`, `msort/2`, `setof/3`, `compare/3`
over quantities of differing dimensions RAISE on canonical and succeed after.
That was the one change capable of moving a corpus answer, and it turns an error
into a result rather than one number into another.

Test migration: 117 of 126 failures were assertions about the OLD
REPRESENTATION. Migrated mechanically — 194 keys across 8 files, driven by the
REGISTRY's own atom set, not a guessed name list — plus seven hand-fixed.
`test_bit_dim_key_is_predicate` is RENAMED to `..._is_the_atom`: its name
asserted the thing that changed.

---

# 3. The GATES — both axes, and neither was sufficient alone

    engine A/B vs a plain-canonical twin    NEW 0, GONE 0
                                            145/16278 -> 145/16305
                                            +27 passed = exactly the tests added
    domain axis (harness-batch-lane)        82/82 unchanged, one fingerprint,
                                            0 torn / 0 scoreless, COMPILED path
    dims-key reads                          0 corpus-side, 0 sealed-side
    sort x quantity                         does not exist on either side

**The A/B could not be run on the feature branch.** harness-batch-lane found
why: the unresolved dates-are-terms change sits 73 commits below the `_dims`
range and refuses a Python date, so 23 of 74 domains fail for reasons unrelated
to atoms. The measurable tree is the five rekey commits cherry-picked onto
canonical — `/workspace/_dims-rekey-isolated`, branch
`iso/dims-rekey-on-canonical-2026-09-15`, head `c69a59b9`, extensions built.
A plain-canonical twin for the A/B is at `/workspace/_dims-rekey-base`.

**THE FINDING THAT JUSTIFIES THE WHOLE ISOLATION EXERCISE, and it is structural:**

> **A failure-set diff can only see what its baseline does not already contain.**

The branch gate reported NEW 0 at every task and was BLIND to a `test_funnel_lint`
regression — that test was ALREADY RED in the branch baseline, because the
branch's own earlier commits had pushed an allowlisted site past its line-range
end before the rekey touched anything. The A/B on a clean base reported NEW 1.
The gate was not run carelessly; it was blind by construction.

(The defect was benign once traced: `test_funnel_lint`'s allowlist is keyed by
LINE RANGE and its one permitted site — `term_str`'s locale-translation branch —
sits exactly on the range END, so ANY insertion above it trips it. Re-anchored,
as the entry's own history shows done twice before. Verified the same way they
did: it is the only violation in the tree, so widening hides nothing.)

---

# 4. Coordination with harness-batch-lane — the model to repeat

Each lane found the other's blind spot. Their date-masking argument made the
engine A/B possible; that A/B surfaced the lint regression my gate could not
report. Both of us corrected findings that favoured us.

**The sort risk, closed on both sides of the seal.** My visible-corpus sweep gave
a cross-product of 5 files; I traced all eleven sort sites TO GROUND rather than
reading variable names, at their insistence:

    selection_criteria_limb_ids([suitability_to_pursue_professional_activity, ...])
    selection_criteria_lawfulness_ground_ids([permitted_criteria_scope, ...])
    modification_gateway_satisfied's GATEWAY_ID is a literal atom in every head
    us/snap sorts missing_keys output -- key NAMES, not money values

Literal fact lists in every one. Their side: 232 sorts in the sealed bodies, 0
over quantities, 0 occurrences of the Quantity class. **The product does not
exist.**

**They ran all 82 rather than the 43-of-54 intersection I proposed**, on the
grounds that the next person cannot tell an unrun axis from a clean one. That is
the better answer. My 63-domain partition mapped cleanly onto their 74.

---

# 5. Instruments that failed open — count 21, and one NEW SHAPE

Full list in the memory. The ones this session earned:

* **A pytest run that ran ZERO tests, reported by the task as exit 0.**
  `-p nocleanup` could not import; the wrapper's own exit was 0. A runner must
  propagate pytest's status and log `TREE-SHA` / `IMPORTED` / `PLUGIN-OK`.
  Also: the inherited `gate_run.sh` `cd`s to the MAIN CHECKOUT — gating a
  worktree through it measures a tree you are not editing. Use
  `gate_iso_l3.sh`.
* **A grep pattern starting with `-` is parsed as OPTIONS, and `2>/dev/null`
  hides it.** Returned 0 files, contradicting a positive control run minutes
  earlier. Use `-e`; never suppress stderr on an instrument.
* **A sweep of a NON-EXISTENT directory reports 0 matches.** Print the
  POPULATION SIZE before the match count.
* **Abbreviated SHAs of different lengths compare unequal.** `d9ae9f4` vs
  `d9ae9f4a` — one a prefix of the other. Compare full SHAs.

**THE NEW SHAPE, and it is harness-batch-lane's formulation:**

> **An instrument's breakage masquerades as a CAVEAT, not only as a finding —
> and a caveat gets less scrutiny precisely because it sounds like humility.
> The tell is that you STOPPED INVESTIGATING. A real limitation has a next
> question; a false one does not.**

Two instances the same afternoon. They nearly published "my run only covers the
interpreted solve path" as a limitation — it would have UNDERSTATED a valid
result. I told the operator "the box engine is broken" and never chased it. Both
were the same stale module path: **`_trampoline` moved to
`clausal.logic.runtime._trampoline`**, and `trampoline.py` imports the Python
twin UNCONDITIONALLY for a different symbol set, so the twin's presence proves
nothing. **The only trustworthy test is identity:**

    T.StepGenerator is sys.modules["clausal.logic.runtime._trampoline"].StepGenerator

Run it against LIVE CANONICAL as a positive control — a check that condemns
canonical is broken, and that is what catches it.

---

# 6. NEXT, in order

1. **Promote the rekey, if the operator says so.** The clean path is
   `iso/dims-rekey-on-canonical-2026-09-15` (`c69a59b9`) — canonical-based, and
   the exact tree the 82 measured. The feature branch still carries the
   unresolved dates-are-terms work underneath. **Needs a direct per-landing go**;
   a landing rewrites source under any lane reading the tree.
2. **The transfer form** — `TO_TERM`/`FROM_TERM` entries for quantity, and
   `quantity_number/2`. Designed, not built. Wants its own plan.
3. **P1's 14 actionable reroute sites** — `tools/predmeta_census/P1_SITES.tsv`,
   anchored by SNIPPET. Unchanged from the previous handoff.
4. `rdiv`/`decimal` arithmetic, sequenced WITH the parked CLP(Q) C port.

# 7. OPEN

* **The ratio slot is asymmetric — read-side only.** The object has two slots
  and neither is a ratio, so Clausal never EMITS a ratio other than 1:
  `5 kilometre` round-trips as `('quantity', 5000, ('unit', 1, ...))`, not as
  written. Making a quantity round-trip the unit it was WRITTEN in is a change
  to the OBJECT (a third slot), not to the transfer form, and is not ruled.
* **`1E+5` and `Quantity`-is-unruled are CLOSED** (52ab6b30, and §1 above). The
  previous handoff still lists them as open; it is wrong about that.
