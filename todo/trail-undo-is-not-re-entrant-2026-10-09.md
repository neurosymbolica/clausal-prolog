# trail.undo is not re-entrant: a destructor that undoes mid-undo crashes

Pre-existing (main fcdd82c2 segfaults too). Found by the 2026-10-09 security
review of the pending-goal channel.

`trail_undo_to` (`clausal/logic/variables/_variables.c`) walks the entries
newest first and DECREFs what each one held. A DECREF can run arbitrary
Python (`__del__` of a bound value, of a queued goal, a weakref callback).
If that code calls `trail.undo(m)` on the same trail, the nested call undoes
entries the outer loop then undoes again, and the outer loop finally sets
`length = mark` over entries already freed: a double DECREF and a segfault
(`Garbage-collecting`). Reproduced with a binding entry on main, and with a
TRAIL_PENDING entry on the pending-goal candidate.

Fix direction: detach the range before releasing it. Copy the entries
`[mark, length)` out (or swap in a fresh buffer), set `length = mark` first,
restore each entry's state, then DECREF from the detached copy, so a nested
undo only ever sees entries still owned by the trail. The same shape
applies to `Trail_clear`/dealloc. Add a re-entrancy test with a `__del__`
that calls `undo(0)`.
