# investigate(A12-F001): tabled answer replay discards dif/CLP(FD) constraints — pick a sound semantics (Opus)

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md` A12-F001
**Tests:** `tests/audit_2026_07_05/test_12_seams.py::TestF001TablingReplayDropsConstraints` (2 xfail — flip to pass)
**Design:** A12-D001 (parked) — store-residue vs refuse-to-table vs document

## Bug

`-table(td/1)` with `td(X) <- (X is not 1)`:

- **First** query `td(X)`: the answer var carries the dif attr (sound).
- **Second** identical query replays the table: the answer var has NO dif
  attr, and `unify(Y, 1)` then succeeds — `td(1)` is now "provable" even
  though the body constrains `X is not 1`. Same shape with
  `in_domain(X, 1, 3)`: the FD domain is gone on replay.
- Identical queries returning semantically different answers breaks
  monotonicity — the second answer set is a strict superset of the first's
  meaning.

The stored answer is the normalized skeleton (`tabling.py` `add_answer` /
`_normalize_for_key` path); attributes never make it into the table, and
replay does NOT build fresh vars (corrected 2026-10-16, D68 review F2): the
frozen row keeps the answer's own unbound Var objects (`freeze_args` is a
deref-walk), whose attributes were trailed and undone when the derivation
backtracked, so replay unifies the caller with the SAME, now attribute-free,
variables -- every replay of the row shares them (todo/tabled-answer-rows-
share-their-unbound-variables-2026-10-16.md).

Note the converse direction is CORRECT and regression-pinned: a
*caller*-constrained var filters replayed answers through its hooks
(`TestTablingReplayRespectsCallerConstraints`).

## Interaction with D68 (2026-10-16)

Operator ruling D68 made a tabled call complete its table before its first
answer, delivering every answer from the table.  That would have dropped the
constraint from the FIRST evaluation too (the two tests
`test_first_evaluation_answer_carries_dif` / `_fd_domain` failed).  Stopgap:
the leader still hands an unconditional answer that carries an attributed
variable over live, when derived, before its table completes
(`tabling._has_attributed_var`), under a cut-check record (a cut over it
raises, naming the constraint as the reason).  Such answers keep the pre-D68
weaknesses: a second call of the same table in the caller's continuation
sees a partial table (the review's F1: with `c(X) :- dif(X, a). c(1).
c(2).` tabled, `findall(X-Y, (c(X), c(Y)), L)` gives 7 pairs, not 9, and a
tabled `tp(N)` over the same findall tables [7, 9], not [9]; pinned xfail in
tests/iso_l3/test_l3_tabled_complete_first.py::
test_constrained_answers_pair_with_every_answer and
::test_constrained_answers_pair_inside_a_table_once).  Shipped as a
RECORDED LIMITATION (provisional, pending ruling 2026-10-16, Q1).
Resolving this todo (storing the residue) removes the stopgap.

## Can a table store constraints? Yes (plan, 2026-10-18)

There is prior art: XSB tables answers that carry attributed variables,
and runs CLP(Q) under tabling (Cui & Warren; Schrijvers & Warren on CHR
with tabling; check the citations before quoting them). A table row
becomes a pair: the answer term, and the constraints left on its unbound
variables (its residue).

1. **Store the residue with each answer.** In `add_answer`, take a
   `copy_term/3`-style copy: a fresh copy of the term plus the goals that
   rebuild its constraints (`dif(X, a)`, `X in 1..3`, `freeze(X, G)`).
   This also fixes the shared-variable bug
   (todo/tabled-answer-rows-share-their-unbound-variables-2026-10-16.md):
   the row no longer holds the derivation's own variables.
2. **Re-post the residue on replay.** Each replay takes a fresh copy of
   the row and calls its goals. The caller's own constraints then filter
   the answer through normal propagation; an incompatible answer fails.
3. **Leave constraints out of the call key.** Today the call key ignores
   the caller's constraints and replay filters through the caller's
   hooks (`TestTablingReplayRespectsCallerConstraints`, correct). Keep
   that. It is sound and simple; the cost is that a caller's constraint
   cannot prune the table's evaluation.
4. **Duplicate check.** Start with variance on the pair (term, normalised
   residue goals). That is sound but incomplete: the same constraints
   written two ways are kept as two answers. The better check is
   entailment between residues, which needs the solver to answer "does
   this imply that": CLP(Q) can, `dif` mostly, CLP(FD) only weakly. Make
   it a later, optional step.

### What is missing today

- **No general `attribute_goals` / `copy_term/3` protocol.** Only the
  CLP(Q) port can export its store as goals
  (`clausal/logic/clpq/residual_constraints.py`
  `all_attribute_goals`, `projection.py`). dif, freeze, CLP(FD) and
  CLP(B) each need a projection hook.
- **CLP(FD) projection is the hard case.** Domains are trivial;
  propagators that run through variables outside the answer mean storing
  goals over those existential variables too. That is sound but bulky,
  and it weakens the variance check.
- **Z3 and OR-Tools have no attribute hooks** (A08-F013). A table must
  refuse their answers with a clear error, never drop the constraint.

### Risks

- **Termination.** A table can grow without end through ever-different
  residues (`X #> 0`, `X #> 1`, ...) where today it would stop. Under
  D68, an incomplete table never answers (D74 Q3), so this shows as a
  hang.
- **WFS.** A conditional answer then carries a residue as well as its
  delays. More bookkeeping, no new idea.
- **A04-F005 (unhashable answers).** The new row representation should
  solve it too; check.

### Phases

1. A general `attribute_goals` hook per attribute family, and
   `copy_term/3`. Useful on its own.
2. Store the residue and re-post it for dif, freeze and CLP(FD) domains;
   variance duplicate check. Remove the D68 stopgap
   (`tabling._has_attributed_var` live hand-over and its cut-check
   record): constrained answers then wait for completion like the rest.
3. CLP(B) (BDD projection) and CLP(Q) (the port's projection).
4. Refuse answers from families with no hook, with a clear error.
5. Optional: entailment-based duplicate check.

The fast path is unchanged: the copy runs only when an answer has an
attributed variable.

## Acceptance

- Both xfail tests in `TestF001TablingReplayDropsConstraints` flip, and
  first and second queries agree.
- The two D68 xfails flip:
  `tests/iso_l3/test_l3_tabled_complete_first.py::
  test_constrained_answers_pair_with_every_answer` (9 pairs, not 7) and
  `::test_constrained_answers_pair_inside_a_table_once`.
- A cut over a constrained tabled call no longer raises
  `permission_error(cut, incomplete_table, _)`.
- An answer from a family with no projection hook raises a clear error.
- docs/tabling.md drops the "constrained answers" limitation (D74 Q1).
