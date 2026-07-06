# fix(A03-F009): CPD extension chaining emits duplicate Evaluate targets — deep solutions lost

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
