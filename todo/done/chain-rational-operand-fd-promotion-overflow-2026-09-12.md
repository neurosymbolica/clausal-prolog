# chain/2 and zcompare/3 with a rational operand overflow in the FD → CLP(Q) promotion

**Filed 2026-09-12** while reviewing the units side channel; pre-existing and
unit-independent. Measured on `64f04898`:

    chain([X, Fraction(21, 2)], "lt")   ->  OverflowError: cannot convert Infinity to integer ratio

`chain` calls `_ensure_fd` on every unbound var BEFORE posting the pairwise
comparators (clausal/logic/clpfd.py, `chain`), giving it an unbounded FD
domain; `fd_lt` then meets the rational, dispatches to `q_lt`, and
`_promote_fd_to_q` (clausal/logic/clpq.py) converts the infinite bound with
`Fraction(...)`, which overflows. `X < Fraction(21, 2)` on its own works
because the comparators do not pre-ensure FD state. With units this shows as
`chain([X, 10.50(euro)], "lt")`.

`zcompare/3` with a ground Order has the same shape (`_ensure_fd` on both
operands before delegating to `fd_lt`/`fd_gt`).

Do: either drop the pre-`_ensure_fd` in `chain` and `zcompare` (let each comparator choose
its solver, as it does when called directly) or make `_promote_fd_to_q` map
an unbounded FD bound to `None`. Pin both the plain and the money spelling.

**Footer:** finishing this todo includes `git mv`-ing it to `todo/done/`.

**Done 2026-09-12** on `feat/clp-units-side-channel-2026-09-12`: the
pre-`_ensure_fd` was dropped from `chain/2`, and moved in `zcompare/3` to the
unbound-Order branch that actually posts `ZcompareConstraint`. Pinned for the
plain rational and the money spelling in tests/test_units_clp.py
(`TestReviewRoundSixteen`).
