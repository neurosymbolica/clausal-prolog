# fix(A03-F007): specialization silently drops MI goals between MatchClause and the recursive call

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F007
**Design:** A03-D003 (parked — recommendation: refuse loudly now, support later)
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF007SpecializationDropsMidBodyGoals` (1 xfail — flip to pass)

## Bug

`analyze_mi` (`specialization.py:187-198`) classifies MI body goals as
pre-match (`range(match_idx)`) or post-match (`range(last_mi_idx+1, …)`).
Goals at indices between `MatchClause` and the last MI-related goal that
are not themselves MI-related are in NEITHER list — dropped from every
specialized clause without a warning:

    SolveGuard([G,*Gs], P, LIM) <- (MatchClause(G,B,P), LIM > 0,
        append(B,Gs,ALL), LIM1 := LIM-1, SolveGuard(ALL,P,LIM1))
    -specialize(SolveGuard, NatProg, alias=SolveGuardNat)
    SolveGuardNat(NAT3, 1)   # succeeds — depth guard gone; generic fails

Inconsistent with the module's own posture: other unrecognized shapes raise
`CannotSpecialize` (which aborts module load — loud).

## Fix direction

Minimal (recommended first): detect non-MI goals with
`match_idx < i < last_mi_idx` in `analyze_mi` and raise `CannotSpecialize`
naming the offending goal. Full support later: thread them into
`_unfold_tail`/`_unfold_split`/`_make_residual_clause` at their original
relative position (they may reference BODY/ALL_GOALS — substitution maps
already exist).

## Acceptance

- Either `SolveGuardNat` respects the guard (full support) or the
  `-specialize` line fails the module load with a clear error (then the
  test fixture and xfail need updating to assert the refusal).
- SolveLimit (pre-match) and SolveCount (post-match) fixtures stay green.
