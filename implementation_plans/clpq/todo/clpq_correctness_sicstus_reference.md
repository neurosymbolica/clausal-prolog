# CLP(Q): correctness story + which implementation is canonical

**Status:** open / deferred — "could turn into a longer story" (noted 2026-06-17)

## Background

There have been two lines of CLP(Q) work:

1. **Original, home-grown CLP(Q)** — the first implementation. It is now considered
   **out of date and incorrect in certain situations**.
2. **SICStus-based port** — later work modelling CLP(Q) on the SICStus Prolog
   implementation (Christian Holzbaur's design), which is **more correct**.

The SICStus-based port is the one being **evaluated for use in Scryer Prolog**.
Markus Triska was contacted to help track down Christian Holzbaur for the
original design/reference, but Holzbaur has effectively disappeared.

## Decision / what to use

- **The SICStus → Scryer port is the reference implementation.** Prefer it over
  the original home-grown CLP(Q).
- The original CLP(Q) should be treated as deprecated/suspect for correctness.

## Open questions (need owner confirmation)

- Which code currently in `clausal/logic/clpq.py` (main) corresponds to the
  original vs. the SICStus port? The home-grown version may still be the one in
  `main`; the SICStus/Holzbaur work (implicit-equality detection, diseq wake
  hooks, bound propagation) lives at least partly on the
  `clausal-clpq_diseq_wake_hook` clone. This mapping needs to be confirmed before
  any branch is deleted or any code is replaced.
- Decide whether to land the SICStus port into `main` (replacing/superseding the
  original) and on what timeline.

## Related clones (do NOT delete pending the above)

- `clausal-clpq_diseq_wake_hook` — furthest-along CLP(Q) branch (contains
  `clausal-faster`; adds diseq wake hooks, bound propagation, Holzbaur-style
  implicit equality, `int_minimize`). Possibly the SICStus-aligned work.
- `clausal-faster` — ancestor of `clpq_diseq_wake_hook` (subset).
- `clausal-clpq_rational_constraints` — separate earlier line; core superseded by
  main's Phase A–D, but keep until the original-vs-port mapping is settled.
