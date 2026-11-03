# Making the Holzbaur port the default CLP(Q) solver (2026-11-03)

The question is whether the default flips from `CLAUSAL_CLPQ=legacy` to
`CLAUSAL_CLPQ=holzbaur`. The port is `clausal/logic/clpq/holzbaur.py` and
the modules it drives. Its departures from 1.3.3 are D1-D25 in
`clausal/logic/clpq/DEVIATIONS.md`.

## Recommendation

Not yet. Flip once the two items under "Before a flip" are closed. Each one
is small. Nothing in the suite blocks the flip: under the two solvers the gate
fails the same tests.

## The full suite under each solver (branch at 157320a5)

| Solver | Failed | Passed | Skipped | xfailed | xpassed |
|---|---|---|---|---|---|
| holzbaur | 82 | 36,650 | 73 | 31 | 7 |
| legacy | 82 | 36,593 | 130 | 32 | 6 |

The 82 failures are the same tests under both solvers. None of them is a CLP(Q)
test; all of them are in the main baseline. Most of the 57 extra skips under
legacy are tests marked as port-only, such as `tests/clpq_port/test_resource_caps.py`
and `tests/clpq_port/test_switch_engine.py`. One test xpasses under the port
and xfails under legacy. Packages: 0 failures under each solver.

The box gate exports `CLAUSAL_CLPQ=${GATE_CLPQ-holzbaur}`. Until this run, it
had only ever tested the port, never the default we ship. No GitHub
workflow runs the engine suite. So until now nothing checked the shipped
default across the whole suite.

## What the port changes from Holzbaur's algorithms

Most of D1-D25 are representation or presentation: rationals as int pairs,
creation-order variables, error shapes, and residual output. Three change
answers. Each was ruled a correctness fix (R25, R26). None has been checked
against SICStus: 1.3.3 runs only there, SICStus is not available here (todo
MORNING-SICSTUS), and the original 1.3.3 sources are no longer on this box (Scryer's clpq.pl keeps an adapted copy). All three
rest on a reading of the 1.3.3 text; D18's has also been run (below).

**D19, a binding checks that its strict bounds can still hold.** This is the
strongest of the three. bv.pl's `rcbl/3` does not re-examine a variable that a
pivot moves into the basis at a strict bound. So a binding that leaves the
store unsatisfiable is accepted. Scryer's clpq accepts the seed-30 store, and
z3 says it is unsatisfiable.

The port keeps 1.3.3's pass and adds a check after it.

- **Evidence:** a z3 fuzz over 30,000 seeds. Without the check, 73
  bindings and 26 equation steps disagree with z3. With it, none do.
- **Soundness:** the check's invariant is asserted at every call over the
  fuzz.
- **Each part is needed:** removing any part makes a test fail.
- **Cost:** 1-9% on the measured workloads.
- **Weakness:** a refusal inside the check's walk is argued unreachable, not
  proven. If it were reached, it would show as a missing answer.

**D17, the `bb_inf` incumbent is local to each search.** In bb.pl the
incumbent is one global record (`bb_put(incumbent, ...)`). A `bb_inf` that
wakes inside another `bb_inf`'s search clears that record. The outer search
then answers worse than its optimum, or fails.

- **Evidence:** a copy of the port that uses one shared record answers 2, as
  Scryer does. The port answers 1, and the true minimum is 1. Without the
  inner `bb_inf`, all three answer 1.
- **Reach:** only a delayed `bb_inf` that wakes during another search. That
  is rare.
- **Weakness:** this rests on reading bb.pl. One could argue that 1.3.3
  intends the global record. Even so, the outer search ends with no
  incumbent and answers a non-optimum, which is no consistent semantics.

**D18, `round_rational` is ISO `round/1`, not `roundq/4`.** arith.pl's `roundq/4`
takes `I is N//D` and tests the sign of I, not of x. For x in (-1, -1/2], I is
0, so x rounds to +1: `round(-3/4) = 1`. bb.pl rounds the vertex of a leaf with
it.

- **Evidence, confirmed 2026-11-03:** Scryer's clpq.pl keeps 1.3.3's
  `roundq/4` text. Run directly under Scryer, whose `//` truncates toward
  zero as SICStus's does, it gives `round(-3/4) = 1` and `round(-1/2) = 1`.
  D18 now records this run.
- **Not evidence:** D18 used to say "Scryer agrees with the port" on a
  `bb_inf` query. Scryer's copy does not expand `arith_eval`, so its `bb_inf`
  rounds with Scryer's native `round/1`, never with `roundq`. D18 now says so.

For D19 we cannot say for certain that 1.3.3 itself answers this way, as
opposed to Scryer's copy. Ruling R25 puts correctness first, so the
port answers correctly either way.

The other deviations do not change which answers are found, but D24's caps
change whether a long query answers at all. Past a cap it raises
`resource_error`, where 1.3.3 has no cap. The defaults refuse no query in
the tests and none of the cases where the reviews saw 1.3.3 answer in
seconds.

## What users would see change

The per-solver branches in the tests pin each of these.

- **`bb_inf/3`:** legacy binds the variables to their optimal values. The
  port binds only `Inf`, as 1.3.3 does. `bb_inf/5` returns the vertex.
- **`maximize/1` and `minimize/1`:** they answer differently on bounded boxes
  (`tests/test_clpq_box_bounded_optimum.py`).
- **Residual output:** `dump/3` and the top level print equivalent but
  differently spelled stores. The port drops redundant bounds, as 1.3.3
  does. Legacy prints, for example, `{-X =< 0}` where the port prints
  `{X >= 0}`.
- **Non-linear constraints:** the port delays them until they become linear,
  as 1.3.3 does. Legacy raises `domain_error(linear_expression, E)`. That
  error landed on this branch; it was a Python `TypeError` before.
- **Speed:**
  - Unifying two constrained variables is slower under the port: at
    n = 200, 12.25 s against 0.77 s.
  - Binding constrained variables to numbers is faster, about 9× at
    n = 200.
- **Long queries:** the D24 caps can raise `resource_error`.

## Before a flip

1. **Var-var unification speed (D24, deferred under R34).** Profile it and fix
   it, or accept it and record the acceptance. 16× at n = 200 is the one
   regression a user would notice.
2. **Gate the default.** After a flip the gate's `holzbaur` default matches
   the shipped default again. Until then, run `GATE_CLPQ=legacy` before a
   release. A workflow that runs the CLP(Q) tests under both solvers would
   make this permanent.

Deep-term `RecursionError` (D24) is shared code. It does not block a flip, since
both solvers have it.

## The flip itself

- Change the default in `clausal/logic/clpq/__init__.py`.
- Update `docs/clpq.md`, which documents legacy as the default.
- Add a CHANGELOG entry that lists the changes above.
- Keep `CLAUSAL_CLPQ=legacy` for one release as an escape hatch.
- The per-solver test branches stay as they are.
