# A tabled leader charges a clause-prefix delay to its FIRST answer only

Found by the opus review of `fix/wfs-goal-leader-2026-09-08` (2026-09-08,
finding 2) and **verified as PRE-EXISTING**: the same program behaves
identically on `a6baeaf1` and on the branch, so this is not fallout from the
condition trailing — it is the older accumulate-and-clear approximation that
trailing was expected to retire, and does not.

## Witness

```clausal
-table(u/1)
-table(pp/1)
u(X) <- (not u(X))
r(one),
r(two),
pp(X) <- (not u(one), r(X))
```

`u(one)` is WFS-undefined, so BOTH answers of `pp/1` stand on the same delayed
`not u(one)` and both should be Undefined. Measured, on both trees:

```
pp truth= True       X= ('two',)
pp truth= Undefined  X= ('one',)
```

`pp(two)` is reported unconditionally true off an undefined premise — the
unsound direction.

## What was tried, and did NOT fix it

The review's proposed fix was to drop the per-answer
`entry._current_delays.clear()` in both leader fixpoint loops
(`make_tabled_wrapper_simple`, `make_tabled_wrapper_trampoline`), on the
grounds that every addition is now trailed (`tabling._charge_delays`) and the
pass already ends with `trail.undo(mark)`. That was implemented and MEASURED:
the witness above is unchanged. So the delay is being lost somewhere other
than the `clear()` — the next step is to instrument `_charge_delays` and find
which undo retracts it, rather than to remove the clears again. (The change
was reverted: an unwitnessed edit to the tabling core is not worth its blast
radius.)

Suspicion worth checking first: `not u(one)` is a TABLED negation, so it runs
through `_naf_tabled`'s spawn drive, and `_spawn_ctx` deliberately suppresses
some attribution across the spawn boundary (`_streaming_consumer_leader`
returns None at a boundary). The delay may be charged inside the spawn and
retracted with it, in which case the first answer keeps it only by accident of
ordering.

## Related

- `clausal/logic/tabling.py::_charge_delays`, `::_delay_negation`,
  `::make_tabled_wrapper_simple`, `::make_tabled_wrapper_trampoline`
- `todo/done/wfs-delays-through-composite-goals-in-goal-position-2026-09-08.md`
  (the judging leader's own copy of this defect IS fixed — it does not clear)
