# P1: signal-mode TRO flag clobbered by later match arms — lost solutions

## STATUS: DONE (2026-07-20) — P1 clobber fixed for all loadable programs

Fix landed in `clausal/logic/compiler/arg_index.py`: new delegating generator
`_drive_tro_bucket(gen, tro_state, arity, pending)` wraps every signal-mode
bucket drive in all five TRO dispatch trampolines (`_make_call_site_bucket_
trampoline`, `_make_joint_dispatch_trampoline`, `_make_secondary_dispatch_impl`,
and both single-/multi-plan branches of `_make_groundness_dispatch_trampoline`).
It snapshots the pending tail-call into a per-activation `pending` list the
instant `tro_state[0]` goes True — BEFORE yielding the solution downstream, i.e.
before any re-entry can reset the shared cell. The dispatch loop then
re-dispatches from `pending`, not from the (re-entrant) shared `tro_state`.
It is a full PEP-380 delegating generator (forwards send/throw/close) so the
trampoline Step protocol keeps working — a plain for-loop wrapper broke `.send`.

Chosen over the todo's candidate 1 (immediate per-arm return — WRONG: skips the
later clauses entirely, ×losses) and candidate 2 (restrict TRO to last-arm — too
aggressive: the existing `secondary_dispatch_tro.clausal` fixture intentionally
TROs a NON-last recursive clause and `test_tro_is_active` pins it). This is
candidate 3's spirit without the ABI change: the shared cell stays, but each
activation captures its own pending signal.

Regression: `tests/test_tro_nonlast_arm_clobber.py` +
`tests/fixtures/tro_nonlast_arm_clobber.clausal` (`Drv(X)` was 1 solution,
now 3). Full suite: ~8250 pass, 0 new failures (batched to avoid OOM).

Key insight that scoped the fix: `$tro_state` is PER-PREDICATE (each predicate's
`base_globals` owns one). So cross-predicate re-entry never clobbered; and since
each dispatch activation now holds its own `pending`, a separate suspended
activation of the same predicate resuming under backtracking no longer drops the
tail either.

RESIDUAL (theorised, could NOT be demonstrated): I worried that a NON-last TRO
clause followed by a sibling clause whose body re-enters the SAME predicate as a
*non-tail* subgoal might still lose the tail (the nested dispatch resets
`tro_state[0]` before any yield reaches `_drive_tro_bucket`). I built several
loadable constructions of exactly this shape (e.g. `Foo("k",…)` recursive +
sibling `Foo("k",…) <- (Helper(Z), Z==0, X is N)` with `Helper(Z) <-
(Foo("w",0,Z))`). ALL give the correct solution count — on BOTH the post-fix and
the PRE-fix engine — i.e. this shape never actually triggered the clobber. So the
theorised residual is not a reproducible soundness bug; the trampoline's
proceed-step interleaving appears to keep the flag observable at the snapshot
point. If a real repro ever surfaces, the complete fix is per-activation TRO
state (the ABI change candidate 3 describes).

(Earlier I mis-attributed a "load failure" to this shape. That was a red herring:
predicate names like `P`/`Q` collide with the SI unit / quantity parser, so the
self-call in the body parses as a Quantity/AttVar, giving "'AttVar' object is not
callable" at load. Filed separately as
[[predicate-name-collides-with-unit-quantity-parser]]. Real predicate names
(`Foo`, `Prc`) load fine.)

P2 (solution ORDER) is unchanged and still open — see
[[tro-nonlast-arm-solution-order]]. The fix preserves the existing "later arms
then re-dispatched tail" order (reverse of standard Prolog for these shapes);
that was explicitly a separate, lower-priority issue.

---

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
