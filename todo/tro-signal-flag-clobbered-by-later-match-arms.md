# P1: signal-mode TRO flag clobbered by later match arms — lost solutions

Found by the 2026-07-11 Fable audit of the call-site fixes (two agents
converged independently, both VERIFIED with probes, both confirmed the
defect reproduces byte-identically at baseline f7a0bcae — pre-existing,
engine-wide, NOT introduced by the call-site/secondary-dispatch fixes).

## Mechanism

`_compile_tro_tail` (compiler/tro.py:586-602) emits only the `$tro_state`
stores — there is NO per-arm early exit in SIGNAL mode; the single
`if $tro_state[0]: return` is appended AFTER all match arms
(compiler/predicate.py, `tro_mode == "signal"` branch — the old comment
claiming per-arm checks were emitted was false and has been corrected).
So when a TRO arm signals and is NOT the last arm of its bucket/fallback,
later arms still run with the flag set:

1. Later arms `yield (proceed, None)` solutions while the flag is set —
   during that suspension, ANY re-entry into the same predicate (a nested
   call in a sibling clause body, another suspended StepGenerator of the
   same predicate under backtracking) resets the shared `$tro_state[0]`
   at its dispatch-loop/wrapper entry, destroying the pending tail call
   and its args → the enclosing loop sees False → tail call dropped →
   **silently missing solutions**.
2. Even without clobbering, running later arms before the re-dispatch
   changes solution ORDER vs standard Prolog clause order (TRO clause's
   continuation solutions arrive after later arms' — separate P2).

## Verified repros (2026-07-11)

- Same-module: `ProbeP("k",N,X) <- (N>0, M is N-1, ProbeP("k",M,X))` as a
  NON-last arm + `ProbeP("k",N,X) <- (X is N+0)` + padding facts to reach
  `_INDEX_THRESHOLD`; driver `LDriver3(X) <- (ProbeP("k",2,X), ProbeP("w",0,_))`
  → 1 solution instead of 3 (the nested `ProbeP("w",0,_)` call resets the
  flag). Control without re-entry: 3 ✓. Below-threshold (loop-mode TRO,
  local `_tro` flag): 3 ✓ — signal-mode-specific.
- Secondary path: hierarchical-shape predicate, unbound-key call → 6
  solutions vs oracle (CLAUSAL_DISABLE_OPT=tro) 18.
- Groundness path: same shape → ×3 vs oracle 9. Single-position buckets DO
  get tro_indices, so bucket-internal arm ordering triggers it too.
- Identical under the C driver and pure-Python StepGenerator.

## Candidate fixes (semantics decision needed)

1. Emit `if $tro_state[0]: return` immediately after each TRO arm's match
   statement — makes the set→check window truly synchronous; ALSO changes
   (fixes) solution order to standard clause order. Preferred but needs an
   order-sensitivity sweep of existing tests.
2. Restrict signal-mode `tro_indices` to clauses that are the LAST arm of
   their bucket/fallback (cheap, conservative: fewer TRO opportunities,
   no order change).
3. Per-generator (non-shared) tro_state — removes the clobber class
   entirely but touches the compiled-code ABI (`$tro_state` global).

Note: `_make_call_site_bucket_trampoline` and all dispatch TRO loops
correctly assume a synchronous set→check window; the window is only
broken by non-last TRO arms — fix at the emission site, not the loops.
