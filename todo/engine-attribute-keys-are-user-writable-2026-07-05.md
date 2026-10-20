# put_attr/3 writes the engine's own attribute keys with any value (A05-D002)

**Status: open, needs a ruling.** Design decision A05-D002 of the
2026-07-05 audit, split out of
todo/done/investigate-A05-parked-design-decisions.md on 2026-10-20. Full
statement: docs/superpowers/audits/2026-07-05-fable-partition/05-constraints-core/design-questions.md.

## What

The keys the solvers own (`dif`, `fd`, `clpb`, `real`, `units`, ...) are
plain global attribute names, so `put_attr/3` can store any value under
them, and the solver hooks then read it. The A05-F002 segfault this caused
is fixed (the dif hook validates its pairs), but the channel is open.
Probed 2026-10-20 from Python (`clausal.logic.variables.put_attr`, then
`unify(X, 1)`):

| attribute written | result of the binding |
|---|---|
| `dif` = `[42]` | `TypeError: _dif_hook: attr pairs must be 2-tuples` (raw Python error) |
| `dif` = `[(X, 2)]` (well formed, bogus) | succeeds: the store now means something else |
| `fd` = `42` | `AttributeError: 'int' object has no attribute 'constraints'` |

SWI avoids this by module-scoping attributes.

## Options (from the audit)

(a) validate in every hook and document the keys as reserved
(recommended); (b) make `put_attr/3` fail on a hook-registered key (breaks
hand-posting constraints); (c) namespace user attributes (`user.<key>`, a
breaking rename). Under (a) the raw TypeError/AttributeError above should
become typed errors (the error convention of A09-D002, ruled 2026-07-07).
