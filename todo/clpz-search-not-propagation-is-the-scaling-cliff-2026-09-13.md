# CLP(Z)'s scaling cliff is in LABELLING, not in the C propagator

**Filed 2026-09-13 by engine-lane.** Found while correcting a wrong claim of my own, not by looking
for it. Harness: `implementation_plans/z3-c-bridge-prototype-2026-09-13/` (see `race_fd.py`).

## The measurement that separates the two phases

n-queens, posting-and-propagating timed separately from labelling:

    N    post+propagate    label/search    constraints   post us/constraint
     8         0.5 ms           4.3 ms            56           8.7
    12         1.1 ms          25.9 ms           132           8.6
    14         1.5 ms         239.5 ms           182           8.3
    16         1.7 ms        1804.6 ms           240           6.9
    18         2.1 ms        9076.2 ms           306           6.8
    20         2.7 ms       54885.5 ms           380           7.1

**Posting and propagation are FLAT: ~7-9 us per constraint at every N**, total 0.5 ms -> 2.7 ms.
The C propagator is not the problem and scales linearly with the constraint count.

**Search grows ~6x per +2 in N** — 4.3 ms -> 54,885 ms, about 12,700x, while the problem itself
grew 6.8x. That is exponential, and it is the whole cliff.

## Why this matters more than it looks

The first write-up of the Z3 comparison excused CLP(Z)'s 132x loss at 20-queens as "our PYTHON CLP
against Z3's C++". **That was wrong.** CLP(FD)/CLP(Z) is C — `_clpfd_propagate.c` (3484 lines),
`_clpfd_core.c` (676), `_clpfd_domain_ops.h` (530) — and at runtime `_USE_C_DOMAINS` and
`_USE_C_PROPAGATE` are both True, with the C module REPLACING `FDVar`, every constraint class,
`propagate`, `_narrow` and `_post_constraint`. So a C propagator was losing, and the excuse hid it.

(CLP(Q) genuinely is pure Python — no `_clpq_core.c` exists, though CLP(R) and CLP(B) both have a
C core. That is a separate question and a separate todo's worth of work.)

## What the shape points at

Propagation flat + search exponential is the signature of **chronological backtracking with no
conflict-driven learning**. Z3 wins these because CDCL learns a clause from every conflict and
never re-enters that subtree; naive labelling re-derives the same contradiction repeatedly.

**Two of the obvious candidates are now CHECKED, so they need not be re-investigated:**

**1. First-fail is ALREADY implemented — this is NOT a missing variable-ordering heuristic.**
`label/2` -> `_label_fd` collects unbound FD vars and picks the SMALLEST DOMAIN first
(`clausal/logic/clpfd.py:2313`, "Uses first-fail strategy"). The cheap standard win is already
taken, which makes the remaining explanations more interesting, not less.

**2. `all_different` is FORWARD-CHECKING ONLY — this is the prime suspect.** `alldiff_propagate`
(`_clpfd_propagate.c:1463`) collects the ground values, removes them from every free variable's
domain, and fails on a duplicate ground value. That is all it does. There is **no Hall-interval
reasoning, no matching, no Regin** — a grep for `hall|matching|interval|regin|pigeon` across the
propagator finds nothing.

Forward-checking `all_different` prunes far less than bounds- or domain-consistent propagation, so
the SEARCH is left to discover by backtracking what a stronger propagator would have deduced at the
node. **That is exactly the signature measured: propagation cheap and flat, search exponential.**
It also explains why propagation time looks suspiciously constant — it is doing little work per
node.

**So the ranked work is now:**

1. **Bounds-consistent `all_different` (Hall intervals, Puget's algorithm)** — the best
   payoff-to-effort ratio, and a well-specified, self-contained change to one C propagator.
   Domain-consistent (Regin, matching-based) is stronger again and much more work.
2. **Nogood recording / conflict learning** — the real answer to why Z3 wins, and by far the
   largest job. Do not start here.
3. Value-ordering and restarts — cheap to try, unlikely to move an exponential on its own.

## Caveats on the numbers

n-queens is ONE shape and a famously search-heavy one; a legal rulebase is mostly linear
constraints where CLP(Z) may never reach the cliff. Two instances of the probe overlapped briefly
during collection, so individual figures carry some contention noise (N=16 read 1622 ms and 1805 ms
on two passes) — **the pattern is unambiguous, the third significant figure is not.**

Re-derive with `race_fd.py` and the phase-split probe rather than trusting these.
