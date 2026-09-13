# Porting Holzbaur's CLP(Q) to C — design

**Date** 2026-09-13 · **Status** approved in principle, unreviewed by a second party
**Goal** speed. Replace Clausal's Python CLP(Q) with a faithful C port of Holzbaur's solver,
then optimise the tableau as a separate phase.

## 1. Why

Clausal's `clausal/logic/clpq.py` (1767 lines, pure Python) is **quadratic by construction**, not
merely slow: `_snapshot_tableau` performs a full `_tableaux[tid].copy()` before each
constraint-posting operation, at five call sites. Measured: ~326x slower than Z3 at 1000
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

**`compat.pl` is an assumption, not a finding.** Its 29 clauses must each be triaged and annotated
like any other; if any carries real semantics the mapping above changes.

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

**Licensing.** GMP is dual-licensed LGPLv3+ / GPLv2+; take the LGPLv3+ arm. Unmodified use does not
affect Clausal's own licence. Obligations attach on DISTRIBUTION: notice, and the ability to relink
against a different GMP. Dynamic linking satisfies relinking; **vendoring GMP into a wheel
(`auditwheel`) does not** and is the practical trap. Rule: link dynamically, do not vendor.
Documented fallback if the licence answer ever turns awkward: build rationals on CPython's `PyLong`
C API (PSF-licensed, no new dependency, slower than GMP but far above the current `Fraction` path).

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

The `@notported` set is a reviewable artefact in its own right: the explicit list of what was left
behind. It is non-empty by construction — the upstream log already shows 546 lines of dead
`compile_Qn` removed.

### 4.3 The other three instruments

* **The 83 example tests ported** — 42 CLP(Q) + 41 CLP(R), from `test_examples_clpq.pl` /
  `test_examples_clpr.pl`, plus `test_clpq.pl` / `test_clpr.pl`.
* **Randomised differential testing against Scryer** — random constraint systems run through both.
  Requires a **canonical form** for residual stores: ordering and variable naming differ, so
  comparison is on a normalised projection, not raw text.
* **Per-layer equivalence harness** — each layer diffed against the Prolog as it lands, so a
  defect is attributed to the layer that introduced it rather than found in the finished whole.

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

`arith_q` -> `store`/`itf3` -> `nf` -> `bv` -> `ineq` -> `fourmotz`/`project`/`dump`/`redund` ->
`bb`. Each layer lands with annotations complete and its equivalence harness green before the next
begins. §3.2's aliasing/hook question is resolved during `store`/`itf3`, before `bv`.

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

## 7. Not established

* whether the attributed-variable seam (§3.2) is reproducible in C — the highest risk, unresolved
* `bb.pl`'s use of non-backtrackable global state (`bb_put`/`bb_delete`) crossing into C
* the `geler.pl` delayed-goal machinery crossing into C
* nonlinear constraint handling
* GMP lifetime and memory management under backtracking
* error and exception semantics at the Python boundary
* whether coefficient blowup is real on corpus data
* a second-party review: a Fable review was dispatched and died on a spend limit, producing nothing
