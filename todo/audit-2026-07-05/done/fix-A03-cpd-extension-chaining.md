# fix(A03-F009): CPD extension chaining emits duplicate Evaluate targets — deep solutions lost

**DONE — commit 70fafac5.** Both halves of the two-fold bug resolved by the
STATUS-recommended "one pass" direction: `_unfold_body_goal` now splices a
single remapped copy of the CONSTANT per-step template
(`pattern.pre/post_match_goals`) per level, telescoped at the recursive-call
boundary (pattern head-role → current rec-extra R, rec-role → fresh F, new rec
call extra → F), and keeps the accumulated body goals untouched. That both
removes the LHS collision and adds exactly one link per level (no off-by-one).
`CountGraphCPD` == generic `("b",2),("c",4),("d",4)`. Added `LimNatCPD` guard
for the symmetric pre-match path (depth cutoff == non-CPD). Full suite: 8808
passed, 0 failures.

---


**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F009
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF009CpdExtensionChaining` (1 xfail — flip to pass)

## Bug

With `cpd=True` on an MI carrying post-match extras (SolveCount), the
second deforestation level produces clauses whose Evaluate chain reuses a
variable as LHS twice (dump of `CountGraphCPD` clauses [7]/[8]):

    rec(fresh)                       # _316
    _309 := _316 + 1
    _313 := _309 + 1
    _309 := _313 + 1                 # ← _309 already bound → always fails
    _304 := _309 + 1

so every ≥2-hop clause fails: `CountGraphCPD([["path","a",Y]], C)` returns
only `("b", 2)`; generic and non-CPD specialization return
`("b",2), ("c",4), ("d",4)`. Plain-`Solve` CPD (no extras) is correct.

Root: `_unfold_body_goal`'s `chain_subst` (`specialization.py:1918-1935`)
maps `head_var → rec_var` and `rec_var → fresh` per level, but the
recursive `_deforest_clause` call re-chains a clause whose post-match
goals already reference the previous level's intermediates; `_subst` is
single-level (no chain-following), and the second level's chain map
collides with the first's variable roles.

## Fix direction

Rebuild the chaining so each deforestation level freshens ALL intermediate
extra-arg vars before splicing (e.g. `_copy_term` the chained pre/post
copies with a per-level var_map, then substitute the boundary vars), or
compute the whole chain in one pass per final clause instead of re-chaining
recursively. Property to enforce: within one output clause body, every
`Evaluate` LHS is a distinct, previously-unbound var, and the chain
telescopes from the rec-call's count var to the head's count var.

## Acceptance

- `CountGraphCPD` counts equal generic (`("b",2),("c",4),("d",4)`).
- Controls stay green: plain CPD == generic, non-CPD CountGraph == generic,
  in-tree `specialize_cpd.clausal` fixture, SolveLimit pre-match chaining
  (docs claim `MAX > 0, MAX1 == MAX-1` chains per inlined step — add a CPD
  SolveLimit test while here; the same chain_subst path emits it).

## STATUS 2026-07-07 (attempted, reverted — still xfail)

Root cause confirmed **two-fold**, not one:

1. **LHS collision** (the dump above): the recursive `_deforest_clause`
   re-chain reuses a var as `Evaluate` LHS twice, so the clause always fails
   and deep solutions are lost. A per-level freshening map for the chained
   pre/post copies (a `_subst` map that mints a fresh `Var` for any non-seeded
   id, seeded with the head→rec / rec→fresh boundary telescoping) makes every
   LHS distinct and restores the deep solutions.

2. **Off-by-one in the telescoped count** — the harder half. After (1),
   `CountGraphCPD` returns `("c",5)`/`("d",5)` instead of `4`: clause 7 (the
   2-hop path) emits **4** increments where the generic emits 3. The buggy
   dump ALSO had 4 (with the collision), so just breaking the collision keeps
   the extra link. The collision point is not a var that should be *freshened*
   (that ADDS a link) — it is the **boundary where the inner level's
   head-count var should JOIN the outer level's rec-count var** (one shared
   increment, not two). Freshening and joining are opposite operations at
   that seam.

**Direction for the retry:** compute the whole extra-arg chain in ONE pass per
final clause (the todo's second option) rather than re-chaining recursively —
track, per output clause, the ordered list of increment links and coalesce the
inner-head↔outer-rec boundary so consecutive chained/original segments share
one link. The recursive `chain_subst` seam cannot express the join with a
single-level `_subst`. Reverted the freshening-only attempt because it ships
plausible-but-wrong counts (worse than the current lost-solutions failure).
