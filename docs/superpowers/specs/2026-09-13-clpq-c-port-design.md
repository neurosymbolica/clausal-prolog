# Porting Holzbaur's CLP(Q) to C — design

**Date** 2026-09-13 · **Status** approved in principle, unreviewed by a second party
**Goal** speed. Replace Clausal's Python CLP(Q) with a faithful C port of Holzbaur's solver,
then optimise the tableau as a separate phase.

## 1. Why

Clausal's `clausal/logic/clpq.py` (1767 lines, pure Python) is **quadratic by construction**, not
merely slow: `_snapshot_tableau` performs a full `_tableaux[tid].copy()` before each
constraint-posting operation, at **ten call sites across nine functions**
(`clpq.py:899, 1034, 1076, 1105, 1166, 1200, 1228, 1401, 1423, 1628`). It deduplicates within a
single trail position (`clpq.py:838`), so the cost is one copy per choice point, not per call.
**This document first said "five call sites" — an undercount of the measurement the whole project
rests on, corrected after review.** Measured: ~326x slower than Z3 at 1000
variables, scaling ~quadratically (2.3 s -> 62.8 s for 5x the problem).

Holzbaur's design does not copy. The tableau is **distributed across attributed variables** — each
variable's `lin` attribute IS its row — so Prolog's native per-variable trailing restores exactly
what changed. **The expected win is therefore asymptotic, not the C-vs-Python constant factor.**
For calibration, GMP rational arithmetic measured only ~11x faster per operation than Python's
`Fraction` (0.084 vs 0.922 us); if arithmetic were the whole story the port would not be worth it.

The operator's ruling: **Holzbaur is the reference gold standard.** Clausal's current CLP(Q) is
based on SWI's, which has known defects, and is to be REPLACED. Where the port and `clpq.py`
disagree, Holzbaur wins; `test_clpq.py`'s 120 tests are not a contract to preserve and may encode
the defects being removed. Each is triaged against Holzbaur, converted rather than deleted where
the underlying hazard is still real.

## 2. Source of truth

`/workspace/claude_sicstus_clpq/clpq_scryer/` — 18 modules, 5331 lines, **906 clauses**.
Largest: `bv.pl` 1270/165 (simplex), `ineq.pl` 1009/108, `nf.pl` 826/200, `fourmotz.pl` 302/71.

**`ANALYSIS.md` in that repo is NOT a specification.** Markus Triska found factual errors in it.
The Prolog source is the only specification. Where this design describes behaviour, it is to be
confirmed against source before implementation, not against that document.

CLP(R) is the same solver over a different number type: `clpr_scryer/` contains only `arith_r.pl`
and `nfr.pl`; the single-file Scryer builds differ by **193 lines of 5844 (3.3%)**, concentrated in
`eval_q`/`eval_r`/`arith_eval`/`eps`. Q and R are therefore built together.

## 3. Architecture

### 3.1 One C translation unit per Prolog module

`_clpq_arith.c`, `_clpq_store.c`, `_clpq_itf.c`, `_clpq_nf.c`, `_clpq_bv.c`, `_clpq_ineq.c`,
`_clpq_fourmotz.c`, `_clpq_project.c`, `_clpq_dump.c`, `_clpq_redund.c`, `_clpq_bb.c`,
`_clpq_class.c`, `_clpq_geler.c`, `_clpq_ordering.c`, `_clpq_interval.c`.

That is 15 units for 18 modules. The three that do not get their own `.c`, stated explicitly so
the mapping is total:

| module | where it goes | why |
| --- | --- | --- |
| `arith_q.pl` | the numeric macro header (§3.3) | it IS the Q/R seam; a `.c` would be compiled twice into contradictory symbols |
| `nfq.pl` | same | 5 clauses, the Q half of normal-form arithmetic |
| `compat.pl` | expected `@notported` | Prolog-level compatibility shims with no C counterpart — to be CONFIRMED clause by clause, not assumed |

**`compat.pl` was an assumption and the assumption was WRONG** — see §4.2's taxonomy: it holds
`top_sort/2`, the ISO error-term constructors, and the non-backtrackable `bb_*` store. It is
`@notported host-builtin`, each clause citing forward to its C implementation, not plumbing. The
row above stands only in the sense that it gets no `.c` of its own; its obligations go to
`_clpq_compat.c`. Corrected after review.

**Symbol namespacing.** §3.3 compiles the WHOLE shared core twice (Q and R), so "compiled twice
into contradictory symbols" applies to all 15 units, not just `arith_q`. The mechanism is a prefix
macro plus separate output directories per variant, so `_clpq_bv.c` and `_clpr_bv.c` are the same
source compiled with different prefixes. `itf3.pl` maps to `_clpq_itf3.c` (not `_clpq_itf.c`), so
the mechanical "`@from <m>.pl` lands in `_clpq_<m>.c`" rule holds without exception.

**The module -> unit map is an explicit DATA TABLE the checker reads**, not a string-munging rule,
so `compat.pl`, `arith_q.pl`, `nfq.pl`, `arith_r.pl` and `nfr.pl` each have a defined destination
and a citation can never land nowhere.

This is deliberately **not** a C-idiomatic grouping. It is chosen so a citation `@from bv.pl:412`
always lands in `_clpq_bv.c`, coverage is checkable per module, and a reviewer can read the two
side by side. This single decision is what makes the traceability requirement affordable.

### 3.2 The variable seam

A CLP(Q) variable carries 11 attribute slots in Holzbaur (uses across the tree): `type` 63,
`lin` 58, `strictness` 36, `class_atts` 17, `class` 16, `goals` 8, `order` 6, `forward` 3,
`all_nonlin` 3, plus `nonzero` and `target` flags. These become **one C struct per variable**, hung
off Clausal's existing `put_attr`/`get_attr` under the `"clpq"` key, with an attr hook for
unification.

**Trailing is per FIELD, not per tableau.** Each mutation records a value-level undo on Clausal's
`Trail`. This is the change that removes the quadratic behaviour.

**OPEN RISK — the highest in the plan.** Holzbaur relies on Prolog semantics that a C struct does
not automatically reproduce: variable aliasing when two CLP(Q) variables unify, attr-hook firing
order, and what happens to a `lin` row when its variable is bound. This must be established from
`itf3.pl`, `store.pl` and `class.pl` BEFORE `bv.pl` is attempted, and is the first thing an
independent reviewer should attack.

### 3.3 Numbers

GMP `mpq_t`, linked **dynamically**. Verified present: `libgmp.so`, `gmp.h` (aarch64).

Q vs R by compiling the shared core **twice** behind a numeric macro header rather than a runtime
vtable — the Prolog proves the seam is confined to the arithmetic layer, and indirect calls in the
pivot loop would tax the path this project exists to fix.

Four GMP properties, all verified by running them, that are design requirements rather than trivia:

1. **`mpq` does not canonicalize itself, and skipping it is SILENTLY WRONG.** Verified:
   `mpq_set_si(a,2,4)` then `mpq_equal(a, 1/2)` answers NO. Every direct component write needs
   `mpq_canonicalize`.
2. **Division by zero dumps core** (SIGFPE, exit 136) — verified. In a CPython extension this kills
   the interpreter with no catchable exception. Every `mpq_div` needs an explicit zero test.
3. **Out of memory calls `abort()`** by default. Install allocators via `mp_set_memory_functions`.
4. **No NaN/Inf/signed zero.** Relevant if CLP(R) is ever backed by rationals, since `clpr.pl`'s
   epsilon tolerance has no `mpq` analogue.

**Property 1 is a faithfulness hazard peculiar to this port.** The Prolog reference runs on
Scryer's native rationals, which canonicalize AUTOMATICALLY. So every place Holzbaur relies on
`rdiv` returning a normalized rational, the C port carries an obligation with **no counterpart line
to cite** — nothing is missing from the C, so traceability coverage stays green while semantics
drift. See §4.4.

Clausal's landed rule that integral rationals present as ints (`4/2` binds `2`) is honoured at the
binder boundary, not inside the core.

### 3.4 Licensing — TWO questions, and only one is about GMP

**The ported code (decided 2026-09-13, by the operator).** Clausal's `LICENSE` is MIT, (c) 2026
Michael Amy. The source carries `(c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
Artificial Intelligence`, and there is **no LICENSE or COPYING file anywhere** in the source tree —
only the per-file OFAI header. A line-by-line C translation is a derivative work by construction,
and this design's traceability scheme is documentary evidence of exactly that.

History: Holzbaur has been uncontactable for ~20 years; OFAI was written to seeking permission
(`/workspace/email_ofai_clpqr.txt`, April 2026) and did not reply; SWI-Prolog's port has shipped
since 2004 under GPL-2 with permission from OFAI and Holzbaur.

**Operator's ruling: the attempt was made in good faith, and the work proceeds.** Recorded as a
decision, not an open item.

**What follows from it, and it is cheap.** Non-response is not a grant, so the CLP(Q)/CLP(R) C
subtree must not silently inherit Clausal's MIT claim — that is a claim made to downstream users
that cannot be supported for code that is not ours to relicense. Therefore:

* the subtree carries its own `NOTICE`: Holzbaur's copyright, OFAI attribution, and the contact
  history including the unanswered request
* that subtree's licence status is stated as **unresolved pending OFAI**, not MIT
* the permission-seeking email is committed in-repo as evidence of the attempt
* every `_clpq_*.c` carries the OFAI attribution header

**Licensing of GMP (the dependency) is a separate question.** GMP is dual-licensed LGPLv3+ / GPLv2+; take the LGPLv3+ arm. Unmodified use does not
affect Clausal's own licence. Obligations attach on DISTRIBUTION: notice, and the ability to relink
against a different GMP. Dynamic linking satisfies relinking; **vendoring GMP into a wheel
(`auditwheel`) does not** and is the practical trap. Rule: link dynamically, do not vendor.
Documented fallback if the licence answer ever turns awkward: build rationals on CPython's `PyLong`
C API (PSF-licensed, no new dependency, slower than GMP but far above the current `Fraction` path).

### 3.5 The Clausal-side seam — the part with NO Prolog line to cite

Holzbaur's variable carries `type`/`lin`/`strictness`/`class`; Clausal's carries
`QVar(lo, hi, tab_id)`. Every site below depends on today's representation and breaks — or worse,
silently stops firing — on the new one. **None of it has a Prolog counterpart, so none of it is
covered by traceability; it belongs to §4.4.**

| site | what it does | hazard on the new representation |
| --- | --- | --- |
| `clpfd.py:396-407` | imports `Q_KEY, QVar`; **writes** `put_attr(var, Q_KEY, QVar(...))` to sync FD and Q bounds | no Holzbaur counterpart at all — the FD<->Q bridge must be redesigned, not ported |
| `clpfd.py:1690, 1966, 2028, 2067, 2108` | `get_attr(x, Q_KEY)` + `q_eq`/`q_ne`/`q_lt`/`q_le` | dispatch breaks |
| `units_clp.py:194`, `units_constraint.py:89` | gate on `get_attr(v, "clpq") is not None` | **FAILS OPEN** — a changed key or shape returns False and silently DISABLES dimension checking rather than erroring |
| `builtins/constraints.py` | 9 entry points: `in_q`, `sup`, `inf`, `entailed`, `maximize`, `minimize`, `dump_q`, `bb_inf`, `clpq_constraint_block` | the public surface; preserved verbatim |

**The units gate is the dangerous one** and gets an explicit test that the detector still returns
True on a port-created CLP(Q) variable — a positive control, because its failure mode is silence.

`dump_q`'s output shape is part of this seam: §4.3 compares residuals exactly, so what `dump_q`
returns is both an interface and an oracle.

### 3.6 CLP(R) — ported, kept ALONGSIDE the existing interval solver

Ruled 2026-09-13. Clausal already ships `clausal/logic/_clpr_core.c` (492 lines): an **interval**
solver over IEEE doubles with outward rounding. `clpr.pl` is **epsilon-tolerance** floats. Same
name, different semantics, and interval arithmetic gives soundness guarantees epsilon-tolerance
does not.

**Both are kept, as separate solvers under distinct names and attribute keys.** No behaviour change
for existing users of the interval solver; the Holzbaur R lands beside it. Cost: two CLP(R)s to
document and maintain, and the distinction must be explained at the user surface.

`clpr_scryer/arith_r.pl` and `nfr.pl` fold into the numeric macro header (§3.3), as `arith_q`/`nfq`
do; they are the R half of the same seam.

## 4. Proving faithfulness

Four independent instruments. None is sufficient alone.

### 4.1 Bidirectional traceability (operator requirement)

Prolog side — a **vendored copy pinned at a git sha** — every clause carries exactly one of:

    %% @ported  _clpq_bv.c:pivot_select  — Bland's rule, entering variable
    %% @notported reason: Prolog module plumbing, no C counterpart

C side — every function or block cites its origin **with the source text quoted**:

    /* @from bv.pl:412  "var_intern(Type,Var,Keep) :- ..."
     * <how this was implemented, and any deviation>
     */

### 4.2 The checker is the deliverable, not the comments

1. **Coverage** — all 906 clauses carry `@ported` or `@notported`; uncovered count must be ZERO.
2. **Citation validity** — every `@from file:line` resolves AND the quoted snippet still matches
   that line at the pinned sha. A bare line number rots silently the moment the Prolog is touched,
   and a rotted citation is worse than none because it reads as verified.
3. **Bidirectional consistency** — if C cites `bv.pl:412`, then `bv.pl:412` must name that C
   symbol. Catches one-way drift.
4. **A positive control on the checker itself** — deliberately corrupt a citation and confirm it
   goes red; run this in CI, not once by hand. A traceability checker that passes on an empty
   annotation set is the exact failure mode that would let an unfaithful port ship wearing a proof.

**`@notported` carries a REASON from a fixed taxonomy, because one bucket hides obligations:**

    @notported host-builtin: implemented at _clpq_compat.c:top_sort   <- MUST cite forward
    @notported dead-code: superseded by <clause>
    @notported prolog-plumbing: no semantic content

Only the third is genuinely "nothing to do". **`compat.pl` proves why this matters** — §3.1 first
assumed it was plumbing; reading it shows 29 clauses containing `top_sort/2` plus graph
construction, `msb_val/2`, `term_variables_set/2`, `illarg/3` and `must_be/4` — **which construct
the ISO error terms thrown at the user boundary** (`instantiation_error`, `type_error`,
`system_error`) — and `bb_put`/`bb_get`/`bb_delete`, implemented with `assertz`/`retract`, i.e. the
non-backtrackable global store §7 lists as a top risk. It exists because these are SICStus
builtins; the SICStus fragment set (`clpq/`, 16 files) has no `compat.pl`.

Under a single bucket, `@notported: no C counterpart` would be true of every clause and wrong about
every obligation — and §7's `bb` risk would be marked resolved because its implementation was
filed as plumbing.

The `@notported` set is then a reviewable artefact in its own right: the explicit list of what was
left behind, and why. It is non-empty by construction — the upstream log shows 546 lines of dead
`compile_Qn` removed.

### 4.2a Three mechanical prerequisites the scheme does not survive without

**(i) The fragments are NOT modules — the per-layer harness cannot call them as specified.**
`grep '^:- *module'` over `clpq_scryer/` returns **nothing**: the 18 files are fragments of a
concatenated build, the module declaration lives in `clpq_header.pl`, and it exports only
`{}/1, maximize/1, minimize/1, inf/2, inf/4, sup/2, sup/4, bb_inf/3, bb_inf/5, ordering/1,
entailed/1, dump/3, projecting_assert/1`. So `arith_q`, `store`, `itf3`, `nf` and `bv` have no
externally callable predicates — **and §3.2's highest-risk question, slated for resolution during
store/itf3, is unanswerable by the stated method.**
*Resolution:* a distinct HARNESS BUILD from the same pinned sha with a generated header carrying a
widened export list, plus a check asserting harness and reference builds differ **in the export
list alone**. The reference build is never mutated, so citations stay anchored.

**(ii) In-place annotation invalidates every citation already written.** Inserting `%% @ported`
above a clause shifts every line below it; annotating bottom-up through a 1270-line `bv.pl` over
weeks would turn hundreds of correct citations red on every annotation commit, and the predictable
response is to weaken the one instrument this design calls the deliverable.
*Resolution:* **annotate all 906 clauses in ONE commit up front, before any C is written.** Line
numbers freeze before they are ever cited. This also yields the `@notported` triage — including the
`compat.pl` question — as a reviewable artefact BEFORE implementation, rather than discovering it
mid-port.

**(iii) The pinned artefact and the runnable oracle are different files.** Citations target
`clpq_scryer/*.pl` (5331 lines, 18 fragments); the runnable oracle is the concatenated single-file
build (5844 lines). *Resolution:* pin the concatenation step and have the checker verify the
single file reproduces from the fragments at the pinned sha, so a differential failure maps back to
a fragment line.

**Cardinality and the enumerator.** §4.2.1's "exactly one of" assumes a 1:1 mapping the port will
not have: one Prolog clause routinely becomes several C functions and vice versa, and `nfq.pl`'s
5 clauses are DCG rules, raising what counts as a clause in the 906. **N:M citations are allowed
explicitly**, and §4.2.3's bidirectionality is defined as "every C citation names a clause that
names it back", not a bijection.
**The clause enumerator gets its own positive control** — per-file counts pinned as a test
(`bv.pl` 165, `nf.pl` 200, `ineq.pl` 108, `fourmotz.pl` 71, `compat.pl` 29, ... total 906); delete
a clause, confirm the count moves. Without it, an enumerator that silently sees 700 clauses reports
100% coverage: the fail-open shape §4.2.4 guards against, one level up.

### 4.3 The other instruments

* **The 83 example tests ported** — 42 CLP(Q) + 41 CLP(R), from `test_examples_clpq.pl` /
  `test_examples_clpr.pl`, plus `test_clpq.pl` / `test_clpr.pl`.
* **Randomised differential testing against Scryer** — random constraint systems run through both.
  Requires a **canonical form** for residual stores: ordering and variable naming differ, so
  comparison is on a normalised projection, not raw text.
* **Per-layer equivalence harness** — each layer diffed against the Prolog as it lands, so a
  defect is attributed to the layer that introduced it rather than found in the finished whole.

* **A corpus-answer gate — the fifth instrument.** Under the `{...}` ruling CLP(Q) becomes the
  default arithmetic surface, so its answers are corpus-visible. The 28 sealed answer-set scorers
  (`<downstream-domain>` et al.) exist precisely to catch engine changes that move corpus answers, and
  they run port-vs-`clpq.py` at the `ineq` stage and again at freeze. **Differences are EXPECTED**
  — removed SWI defects are the point — so each is triaged as defect-removal or regression, by
  corpus-lane, and recorded. Without this the port is faithful to Holzbaur, all instruments green,
  and rulebase answers move anyway, discovered downstream with no attribution.

**Residual/projected answers are compared exactly, not just sat/unsat.** Two solvers can agree on
satisfiability and disagree on the projection, and for a legal rulebase the residual IS the answer.

### 4.4 What the traceability scheme does NOT catch

Stated explicitly so no one mistakes green coverage for proof:

* an obligation with no counterpart line — §3.3 canonicalization is the known instance
* a faithful line-by-line translation with wrong INTEGER semantics (C overflow where Prolog had
  bignums) — mitigated by `mpq_t` but live anywhere a loop counter or index is a C `int`
* correct clauses composed in the wrong ORDER, since citations are per clause, not per control flow
* Prolog backtracking behaviour, which has no line to cite at all — §3.2's risk

The differential and equivalence instruments exist to cover exactly these.

### 4.5 The oracle has a known bug

`scryer_3295_findings.md` documents a Scryer ENGINE defect (`arg/1` with `==`) that affects the
simplex. **A differential red flag must therefore be triaged against the Prolog SOURCE before it is
treated as a port bug.** There is no SICStus on this machine to act as a third opinion, so the
source is the tiebreak and disagreements of this class must be recorded, not silently resolved.

## 5. Staging

### 5.0 Stage 0 — prerequisites, with exit criteria

Nothing in stage 1 is startable without these:

* the vendored copy, **pinned at a sha**, and the concatenation step pinned with it
* **all 906 clauses annotated in one commit** (§4.2a(ii)), `@notported` triaged by reason
* the checker, including both positive controls (citation corruption; clause enumerator)
* the harness build with the widened export list (§4.2a(i))
* **the differential oracle named**: WHICH Scryer binary, built from WHICH sha. There are at least
  three candidate trees (`/workspace/scryer-prolog`, `-CLPQ_R`, `-clpq`), `scryer-prolog` is not on
  `PATH`, and one carries the `#3295` defect §4.5 warns about
* the `NOTICE` and attribution headers (§3.4)

*Exit criterion:* checker green on a port with zero C written — coverage 100%, every citation
resolving, both positive controls demonstrated red when broken.

### 5.1 Success criteria — what "done" means

**A faithful port may be SLOWER than `clpq.py` on small problems** (per-field trail entries,
`mpq_t` allocation per coefficient), and without a stated threshold that discovery becomes an
argument rather than a decision.

* at freeze: **no worse than `clpq.py` at <=20 variables, and sub-quadratic scaling demonstrated to
  1000 variables** — the curve, not a single point, since the curve is the reason for the project
* optimisation phase exits when the corpus workload is no longer marshalling/solve-bound, not "when
  it feels fast"
* measured by **interleaved A/B in the same process** against `clpq.py`, per this repo's perf-gate
  practice — never against saved baselines

### 5.2 Rollout, coexistence, rollback

`clpq.py` **stays importable behind a selector for the duration of the project** — it is the A/B
counterpart of §5.1 and the rollback path. GMP is detected at BUILD time with the `PyLong` path as
a fallback build, so `import clausal` cannot fail on a machine without libgmp; this also covers the
x86_64 box and the drift-gated forks, which build the extension family independently.

### 5.3 Order

`arith_q` -> `store`/`itf3` -> `nf` -> `bv` -> `ineq` -> `fourmotz`/`project`/`dump`/`redund` ->
`bb`. Each layer lands with annotations complete and its equivalence harness green before the next
begins. §3.2's aliasing/hook question is resolved during `store`/`itf3`, before `bv`.

**`bv` and `ineq` are sub-staged.** They are 1270 and 1009 lines — 43% of the total — and are not
incrementally reviewable as single stages. `bv` splits along its internal structure
(var_intern/store maintenance -> pivot selection -> the simplex loop -> optimisation queries) and
`ineq` likewise, each sub-stage with a citable Prolog range and its own harness scenarios.

Then **FREEZE** as the reference implementation. Only then does optimisation begin, with frozen-C
as an oracle alongside the Prolog — two independent references instead of one.

## 6. Optimisation phase (after freeze only)

Targets, in the order the port is expected to expose them:

* **pivot selection** beyond Bland's rule — Bland's is anti-cycling but slow; Dantzig or
  steepest-edge with a Bland fallback preserves termination
* **sparse row representation**
* **`mpq_t` allocation churn** in the pivot inner loop

**Do not assume the third is the bottleneck.** An attempt to reproduce exact-rational coefficient
blowup failed: 200 pivots over a 40-wide row stayed at 26-50 bits and 1.0 ms total. That is weak
evidence — blowup is problem-structure dependent and the probe used small values with cancelling
gcds — so the optimisation phase must measure against REAL corpus constraint systems first.

## 6a. Cross-cutting concerns

* **Concurrency / free-threading.** `setup.py` has explicit `Py_GIL_DISABLED` handling. Today's
  solver keys global state by `id(trail)` (`_tableaux`, `_last_snapshot`) and `bb.pl` adds genuinely
  non-backtrackable globals. **State it: C solver state is per-engine, not process-global**, and
  say what two concurrent engines do.
* **Lifetime and teardown.** `clpq.py:834` ties tableau cleanup to trail finalisation via
  `weakref`. This repo has already taken a trail-dealloc/weakref SEGFAULT; `mpq_t`s are manually
  freed, so the teardown path needs an explicit discipline, not just "GMP lifetime under
  backtracking" as a risk line.
* **Exception safety across the boundary.** Holzbaur throws ISO error terms from `compat.pl`'s
  `illarg/3`; Clausal has a ruled spelling for CLP errors (`system_error(units_mismatch)`). Define
  what the C raises and how it unwinds **with `mpq_t`s live** — a longjmp past an un-cleared `mpq_t`
  leaks on every caught error.
* **Landing mechanics.** Adding a `.so` family to a tree long-lived processes import has caused a
  SIGBUS here before. The build/landing procedure is named in the plan, not left to the implementer.

## 6b. Non-goals

* preserving `test_clpq.py`'s 120 tests as a behavioural contract (ruled: Holzbaur wins)
* replacing or changing `_clpr_core.c`'s interval semantics (§3.6: both kept)
* nonlinear constraint handling beyond what Holzbaur already does — no new capability
* ANY performance work before freeze (§5) — including "obvious" wins noticed while porting
* CLP(Q) API changes: the 9 entry points in §3.5 are preserved verbatim

## 7. Not established

* whether the attributed-variable seam (§3.2) is reproducible in C — the highest risk, unresolved
* `bb.pl`'s use of non-backtrackable global state (`bb_put`/`bb_delete`) crossing into C
* the `geler.pl` delayed-goal machinery crossing into C
* nonlinear constraint handling
* GMP lifetime and memory management under backtracking
* error and exception semantics at the Python boundary
* whether coefficient blowup is real on corpus data
* whether OFAI ever replies (§3.4 — proceeding on the operator's ruling, not on a grant)
* a second-party review of THIS revision. The first spec was reviewed (roborev job 70, verdict
  Fail, 15 findings); every deciding fact was independently verified and all 15 are addressed
  above. A Fable review was also dispatched and died on a spend limit, producing nothing.
