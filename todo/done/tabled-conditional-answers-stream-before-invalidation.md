# A streamed conditional answer can be invalidated after the caller saw it

**Written:** 2026-08-27, from the review of the WFS truth-surface work
(review finding; measured, minimally repro'd below).
**Severity:** medium. `query_wfs` is immune (it completes the computation,
then drops falsified rows); the plain `solve()`/`call()` surface is not.

## The observation

The tabled leader streams answers to its caller incrementally, during the
fixpoint — including CONDITIONAL answers whose delayed negations are only
resolved at root exit. An answer that resolution then invalidates
(`_FAILED`) has already been delivered and cannot be retracted, so the same
ground query's answer SET differs between the first and second invocation:

```python
lm = _module(_load("wfs_posneg_true"))   # Qw(6) true → Pw(6) false
[deref(X) for _ in call("Pw", X, module=lm)]   # → [1, 6]  (6 streamed, then falsified)
[deref(X) for _ in call("Pw", X, module=lm)]   # → [1]     (complete path skips _FAILED)
```

## Why it is this way

Streaming conditional answers is the engine's documented WFS surface
behaviour ("undefined answers are yielded alongside true ones"), and
mid-fixpoint consumers legitimately need them for joins. The problem is
only the sliver between "streamed to the ROOT caller" and "invalidated at
root exit".

## Directions

1. **Defer root-caller delivery of conditional answers** until the root
   leader completes and resolution has run; unconditional answers keep
   streaming. Inner (non-root) consumers are unaffected — they read
   `entry.answers` directly / re-derive per pass. Needs care in the
   trampoline wrapper: the leader cannot know it is root-consumed at yield
   time; the deferral would have to live in the root drivers
   (`solutions`/`_drive_until_yield` pull sites) or be keyed off
   `len(_leader_ctx.stack)`.
2. **Surface-side re-check**: have `query()`/`call()`'s iteration re-verify
   each yielded answer against the table's final conditions... impossible
   for a true stream (the caller may act on the answer immediately).
3. Document the first-call anomaly and point three-valued callers at
   `query_wfs` (which is already correct). Weakest, but honest.

Related: `todo/done/wfs-undefined-lost-at-query-surface.md` (the work that
made invalidation actually happen at root exit — before it, the answer was
wrongly kept True forever, so the sets "agreed" by both being wrong).

---

## Fixed (2026-08-31)

Direction 1, implemented in `make_tabled_wrapper_trampoline`
(`clausal/logic/tabling.py`): the OUTERMOST leader — identified by an empty
leader stack at push time, which is also the leader whose exit runs global
resolution — DEFERS conditional answers (a `deferred` index set covering both
newly-derived rows and re-lead replays) and delivers the survivors after
resolution, skipping `_FAILED`, re-unifying in index order like the COMPLETE
path.  Unconditional answers stream exactly as before, and inner (non-root)
leaders still stream conditionals to their mid-fixpoint consumers.  The
alternative deferral site (the `solutions`/`_drive_until_yield` pull loops)
was rejected: those are C/Python twins and cannot tell a conditional yield
from an unconditional one without a new protocol sentinel.

The repro is now stable (`[1]` on both invocations; `wfs_posneg_undef`'s
surviving Undefined rows still `[1, 6]` on both).  One visible change at the
streaming surface: surviving conditional answers arrive after the fixpoint
completes instead of interleaved — set-identical, row order may differ.

Coverage: `tests/test_wfs.py::TestRootLeadConditionalDeferral`, including a
streaming-preserved pin (an answer is consumable while the table still says
"evaluating" for a negation-free predicate).
