# A tabled leader charges a clause-prefix delay to its FIRST answer only

Found by the opus review of `fix/wfs-goal-leader-2026-09-08` (2026-09-08,
finding 2). PRE-EXISTING: identical on `a6baeaf1` and on canonical before the
WFS work.

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
`not u(one)` and both should be Undefined. Measured:

```
pp truth= True       X= ('two',)      <-- wrong: unconditionally true off an
pp truth= Undefined  X= ('one',)          undefined premise
```

## The fix, and a CORRECTION to what this file said before

**Dropping the per-answer `entry._current_delays.clear()` in
`make_tabled_wrapper_trampoline` DOES fix it** (keep the end-of-pass one):

```
pp truth= Undefined  X= ('one',)
pp truth= Undefined  X= ('two',)
```

An earlier revision of this todo said the opposite — that the fix had been
implemented, "measured NOT to fix it", and reverted. **That measurement was
invalid and the claim is withdrawn.** The probe was run as
`cd <worktree> && venv/bin/python /abs/path/scratchpad/probe.py`, which puts the
SCRIPT's directory on `sys.path[0]`, so it imported the editable-installed
CANONICAL `clausal` and never executed the edited worktree at all. Markers
inserted at both wrapper factories' hot paths never fired, which is what
exposed it. A Fable design review reached the correct result because its
monkeypatch (`exec` into the imported module's dict) hit whatever module was
actually loaded. Diagnosis in that review — the bucket is cleared after the
first answer while `r(X)`'s choice point is the only one, so the clause prefix
never re-runs and the second answer sees an empty bucket — matches the trace.

The spawn-boundary suspicion the earlier revision raised is NOT the cause.

## What still needs doing before this lands

- The one-line removal, with the witness above as a pin (it is currently
  unpinned in either direction).
- A full-suite name-set diff: this is the tabling core, on the hot path for
  every tabled predicate, so the 0-NEW gate is the bar. The Fable review
  reports 224/224 on the four WFS/tabling files and an identical full-suite
  failure set, but that was measured through a runtime monkeypatch, not the
  source edit — re-measure as a source change.
- `make_tabled_wrapper_simple` carries the same clear. `ensure_tabled_wrapper`
  only ever builds the trampoline wrapper, so it is unreachable today; decide
  whether to change it for symmetry or leave it.

## Related

- `clausal/logic/tabling.py::make_tabled_wrapper_trampoline`, `::_charge_delays`
- [[running-tests-in-bug-fix-clone]] — the sys.path trap that produced the
  false negative

## Closed 2026-09-30 (stale)

Fixed by b2b2911d ("a clause-prefix delay covers every answer, not just the
first"): the trampoline wrapper dropped the per-answer clear, and the witness
is pinned in tests/test_wfs.py. Re-measured on f01790d2: both `pp` answers are
Undefined.
